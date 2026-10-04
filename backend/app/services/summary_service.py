"""纪要生成业务逻辑层"""

import uuid
import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meeting import Meeting
from app.models.summary import Summary
from app.models.action_item import ActionItem
from app.models.risk import Risk
from app.models.transcript import Transcript
from app.agents.meeting_graph import MeetingAgentState
from app.agents.harness import BudgetGuard, set_harness_context

logger = logging.getLogger(__name__)

SummaryProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


# 是否启用 Harness 升级版（v2）。True 用 v2，False 退回 v1。
USE_HARNESS_V2 = True


class SummaryService:
    """纪要生成与管理"""

    async def list_summaries(
        self, db: AsyncSession, skip: int = 0, limit: int = 20
    ) -> tuple[list[tuple[Summary, Meeting]], int]:
        """获取所有纪要列表（附带会议信息）"""
        result = await db.execute(
            select(Summary, Meeting)
            .join(Meeting, Summary.meeting_id == Meeting.id)
            .order_by(Summary.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = list(result.all())

        count_result = await db.execute(select(func.count(Summary.id)))
        total = count_result.scalar_one()

        return rows, total

    async def _build_transcript_text(
        self, db: AsyncSession, meeting_id: uuid.UUID
    ) -> str:
        """构建转写文本（供 Agent 使用）"""
        result = await db.execute(
            select(Transcript)
            .where(Transcript.meeting_id == meeting_id)
            .order_by(Transcript.seq_index)
        )
        transcripts = list(result.scalars().all())

        if not transcripts:
            return ""

        lines = []
        for t in transcripts:
            speaker = t.speaker or "未知"
            lines.append(f"[{speaker}]: {t.content}")
        return "\n".join(lines)

    async def generate_summary(
        self,
        db: AsyncSession,
        meeting_id: uuid.UUID,
        on_event: SummaryProgressCallback | None = None,
    ) -> Optional[Summary]:
        """触发 Multi-Agent 生成纪要（Harness 升级版）"""
        # 1. 获取会议
        meeting_result = await db.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        meeting = meeting_result.scalar_one_or_none()
        if not meeting:
            return None

        # 2. 构建转写文本
        transcript_text = await self._build_transcript_text(db, meeting_id)
        if not transcript_text:
            logger.warning(f"会议 {meeting_id} 无转写内容")
            return None

        # 3. 删除旧的纪要/行动项/风险
        await db.execute(
            delete(Summary).where(Summary.meeting_id == meeting_id)
        )
        await db.execute(
            delete(ActionItem).where(ActionItem.meeting_id == meeting_id)
        )
        await db.execute(
            delete(Risk).where(Risk.meeting_id == meeting_id)
        )
        await db.flush()

        # 4. 创建纪要记录（状态：生成中）
        summary = Summary(
            meeting_id=meeting_id,
            content="",
            status="generating",
        )
        db.add(summary)
        await db.flush()
        if on_event:
            await on_event({
                "type": "started",
                "message": "Multi-Agent 正在分析会议内容",
            })

        # 5. 创建 AgentRun（Harness 升级版新增）
        agent_run = None
        if USE_HARNESS_V2:
            try:
                from app.services.agent_run_service import agent_run_service
                agent_run = await agent_run_service.create_run(
                    meeting_id=str(meeting_id),
                    graph_name="meeting_summary_graph_v2",
                    max_tokens=50000,
                    max_cost_usd=0.5,
                )
                await agent_run_service.start_run(agent_run.id)
                logger.info(f"[Harness] AgentRun 创建: {agent_run.id}")
            except Exception as e:
                logger.warning(f"[Harness] AgentRun 创建失败（降级继续）: {e}")
                agent_run = None

        # 6. 构建 BudgetGuard
        budget_guard = BudgetGuard(
            run_id=agent_run.id if agent_run else "",
            max_tokens=50000,
            max_cost_cny=0.5,
        ) if USE_HARNESS_V2 else None

        # 7. 调用工作流
        if USE_HARNESS_V2:
            return await self._run_v2_workflow(
                db, meeting_id, meeting, transcript_text, summary,
                agent_run, budget_guard, on_event,
            )
        else:
            return await self._run_v1_workflow(
                db, meeting_id, meeting, transcript_text, summary, on_event,
            )

    async def _invoke_graph_with_events(
        self,
        graph,
        initial_state: dict,
        on_event: SummaryProgressCallback | None,
    ) -> dict:
        """运行 LangGraph；启用 SSE 时按节点结果推送增量事件。"""
        if not on_event:
            return await graph.ainvoke(initial_state)

        final_state = initial_state
        last_payloads: dict[str, Any] = {}

        async for mode, payload in graph.astream(
            initial_state,
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                final_state = payload
                continue

            for update in payload.values():
                if not isinstance(update, dict):
                    continue

                content = update.get("summary")
                if content:
                    summary_payload = {
                        "type": "summary",
                        "content": content,
                        "key_points": update.get("key_points", []),
                        "message": "摘要已生成，正在处理其他结构化结果",
                    }
                    if summary_payload != last_payloads.get("summary"):
                        last_payloads["summary"] = summary_payload
                        await on_event(summary_payload)

                if "action_items" in update:
                    items = update.get("action_items", [])
                    action_payload = {
                        "type": "progress",
                        "stage": "action_items",
                        "message": f"已提取 {len(items)} 个行动项",
                    }
                    if action_payload != last_payloads.get("action_items"):
                        last_payloads["action_items"] = action_payload
                        await on_event(action_payload)

                if "risks" in update:
                    risks = update.get("risks", [])
                    risk_payload = {
                        "type": "progress",
                        "stage": "risks",
                        "message": f"已识别 {len(risks)} 个风险",
                    }
                    if risk_payload != last_payloads.get("risks"):
                        last_payloads["risks"] = risk_payload
                        await on_event(risk_payload)

        return final_state

    async def _run_v2_workflow(
        self,
        db: AsyncSession,
        meeting_id: uuid.UUID,
        meeting: Meeting,
        transcript_text: str,
        summary: Summary,
        agent_run,
        budget_guard: BudgetGuard,
        on_event: SummaryProgressCallback | None = None,
    ) -> Optional[Summary]:
        """执行 Harness v2 工作流"""
        from app.agents.meeting_graph_v2 import meeting_graph_v2
        from app.services.agent_run_service import agent_run_service

        # 设置 Harness 上下文（contextvar，跨节点传递）
        run_id = agent_run.id if agent_run else ""
        set_harness_context(run_id, budget_guard)

        initial_state = {
            "meeting_id": str(meeting_id),
            "meeting_title": meeting.title,
            "meeting_date": meeting.start_time.isoformat() if meeting.start_time else None,
            "transcript_text": transcript_text,
            "summary": "",
            "key_points": [],
            "action_items": [],
            "risks": [],
            "errors": [],
            # Harness 字段（agent_run_id / budget_guard 通过 contextvar 传递）
            "plan": {},
            "transcript_compressed": False,
            "summary_agent_retry": 0,
            "action_items_agent_retry": 0,
            "risks_agent_retry": 0,
            "valid": False,
            "retry_node": None,
            "retry_reason": None,
            "paused": False,
            "approved": False,
            "review_status": None,
            "decisions": [],  # Q8 决策：decision_extractor 节点输出
        }

        try:
            final_state = await self._invoke_graph_with_events(
                meeting_graph_v2, initial_state, on_event
            )

            # 暂停（等人工审批）
            if final_state.get("paused"):
                logger.info(f"[Harness] Run 暂停等待审批: {agent_run.id if agent_run else ''}")
                summary.status = "paused"
                summary.content = "⏸️ 会议识别为高风险/敏感内容，已暂停等待人工审批。\n\n请在 Agent 运行面板审批后继续。"
                summary.key_points = []
                await db.flush()
                await db.refresh(summary)
                return summary

            # 标记 AgentRun 完成
            errors: list[str] = final_state.get("errors", [])
            if agent_run:
                if errors:
                    await agent_run_service.finish_run(
                        agent_run.id, "failed",
                        error="; ".join(dict.fromkeys(errors)),
                    )
                else:
                    await agent_run_service.finish_run(agent_run.id, "succeeded")

            if errors:
                unique_errors = list(dict.fromkeys(errors))
                error_msg = unique_errors[0]
                summary.status = "failed"
                summary_content = final_state.get("summary", "")
                if summary_content:
                    summary.content = f"{summary_content}\n\n---\n\n⚠️ 部分内容生成失败：{error_msg}"
                else:
                    summary.content = f"⚠️ {error_msg}"
                summary.key_points = final_state.get("key_points", [])
                await self._save_action_items_and_risks(db, meeting_id, final_state)
                await db.flush()
                await db.refresh(summary)
                logger.warning(f"会议 {meeting_id} 纪要生成部分失败: {error_msg}")
                return summary

            # 成功
            summary.content = final_state.get("summary", "")
            summary.key_points = final_state.get("key_points", [])
            summary.status = "completed"
            await self._save_action_items_and_risks(db, meeting_id, final_state)
            # 决策落库（Q9 决策：即时向量关联，失败不影响纪要）
            decisions = final_state.get("decisions", [])
            if decisions:
                try:
                    from app.services.decision_graph_service import decision_graph_service
                    await decision_graph_service.save_decisions(db, meeting_id, decisions)
                    logger.info(f"[Harness] 决策落库 {len(decisions)} 条，meeting={meeting_id}")
                except Exception as e:
                    logger.warning(f"决策落库失败（不影响纪要）: {e}")
            await db.flush()
            await db.refresh(summary)
            logger.info(f"会议 {meeting_id} 纪要生成完成（Harness v2）")

            # 自动索引到知识库
            try:
                from app.services.knowledge_service import knowledge_service
                await knowledge_service.index_meeting_summary(
                    db=db,
                    meeting_id=meeting_id,
                    meeting_title=meeting.title,
                    summary_content=summary.content,
                )
            except Exception as idx_err:
                logger.warning(f"知识库索引失败: {idx_err}")

            return summary

        except Exception as e:
            logger.error(f"[Harness v2] 纪要生成失败: {e}")
            if agent_run:
                try:
                    await agent_run_service.finish_run(agent_run.id, "failed", error=str(e))
                except Exception:
                    pass
            summary.status = "failed"
            summary.content = f"⚠️ 纪要生成异常：{str(e)}"
            await db.flush()
            await db.refresh(summary)
            return summary

    async def _run_v1_workflow(
        self,
        db: AsyncSession,
        meeting_id: uuid.UUID,
        meeting: Meeting,
        transcript_text: str,
        summary: Summary,
        on_event: SummaryProgressCallback | None = None,
    ) -> Optional[Summary]:
        """执行 v1 工作流（降级用）"""
        from app.agents.meeting_graph import meeting_graph

        initial_state: MeetingAgentState = {
            "meeting_id": str(meeting_id),
            "meeting_title": meeting.title,
            "transcript_text": transcript_text,
            "summary": "",
            "key_points": [],
            "action_items": [],
            "risks": [],
            "errors": [],
        }

        try:
            final_state = await self._invoke_graph_with_events(
                meeting_graph, initial_state, on_event
            )
            errors: list[str] = final_state.get("errors", [])
            if errors:
                unique_errors = list(dict.fromkeys(errors))
                error_msg = unique_errors[0]
                summary.status = "failed"
                summary_content = final_state.get("summary", "")
                if summary_content:
                    summary.content = f"{summary_content}\n\n---\n\n⚠️ 部分内容生成失败：{error_msg}"
                else:
                    summary.content = f"⚠️ {error_msg}"
                summary.key_points = final_state.get("key_points", [])
                await self._save_action_items_and_risks(db, meeting_id, final_state)
                await db.flush()
                await db.refresh(summary)
                return summary

            summary.content = final_state.get("summary", "")
            summary.key_points = final_state.get("key_points", [])
            summary.status = "completed"
            await self._save_action_items_and_risks(db, meeting_id, final_state)
            await db.flush()
            await db.refresh(summary)

            try:
                from app.services.knowledge_service import knowledge_service
                await knowledge_service.index_meeting_summary(
                    db=db,
                    meeting_id=meeting_id,
                    meeting_title=meeting.title,
                    summary_content=summary.content,
                )
            except Exception as idx_err:
                logger.warning(f"知识库索引失败: {idx_err}")

            return summary

        except Exception as e:
            logger.error(f"纪要生成失败: {e}")
            summary.status = "failed"
            summary.content = f"⚠️ 纪要生成异常：{str(e)}"
            await db.flush()
            await db.refresh(summary)
            return summary

    async def _save_action_items_and_risks(
        self, db: AsyncSession, meeting_id: uuid.UUID, final_state: dict
    ) -> None:
        """保存行动项和风险（成功或部分失败时都调用）"""
        for item in final_state.get("action_items", []):
            due_date = None
            if item.get("due_date"):
                try:
                    due_date = date.fromisoformat(item["due_date"])
                except (ValueError, TypeError):
                    pass

            action_item = ActionItem(
                meeting_id=meeting_id,
                title=item.get("title", ""),
                assignee=item.get("assignee"),
                due_date=due_date,
                priority=item.get("priority", "medium"),
                status="pending",
            )
            db.add(action_item)

        for risk in final_state.get("risks", []):
            risk_item = Risk(
                meeting_id=meeting_id,
                description=risk.get("description", ""),
                severity=risk.get("severity", "medium"),
                mitigation=risk.get("mitigation"),
            )
            db.add(risk_item)

    async def get_summary(self, db: AsyncSession, meeting_id: uuid.UUID) -> Optional[Summary]:
        """获取会议纪要"""
        result = await db.execute(
            select(Summary).where(Summary.meeting_id == meeting_id)
        )
        return result.scalar_one_or_none()

    async def get_action_items(self, db: AsyncSession, meeting_id: uuid.UUID) -> list[ActionItem]:
        """获取行动项"""
        result = await db.execute(
            select(ActionItem)
            .where(ActionItem.meeting_id == meeting_id)
            .order_by(ActionItem.created_at)
        )
        return list(result.scalars().all())

    async def get_risks(self, db: AsyncSession, meeting_id: uuid.UUID) -> list[Risk]:
        """获取风险"""
        result = await db.execute(
            select(Risk)
            .where(Risk.meeting_id == meeting_id)
            .order_by(Risk.created_at)
        )
        return list(result.scalars().all())


# 全局实例
summary_service = SummaryService()
