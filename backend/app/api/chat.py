"""对话 API：会话管理 + SSE 流式对话"""

import json
import uuid

import anyio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Send

from app.api.deps import get_db
from app.services.chat_service import chat_service
from app.services.chat_generation_service import chat_generations

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatStreamingResponse(StreamingResponse):
    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            # 若取消发生在 ASGI send 中，框架不会自动关闭停在 yield 的生成器。
            with anyio.move_on_after(20, shield=True):
                await self.body_iterator.aclose()


# ── 请求/响应模型 ──

class CreateSessionRequest(BaseModel):
    meeting_id: str | None = None
    title: str | None = None


class ChatRequest(BaseModel):
    query: str
    images: list[str] | None = None  # base64 data URL 列表，用于多模态对话
    generation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    last_seq: int = Field(default=0, ge=0)
    resume: bool = False


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    metadata: dict | None = None
    created_at: str


class SessionResponse(BaseModel):
    id: str
    meeting_id: str | None = None
    title: str | None = None
    created_at: str


# ── 会话管理 ──

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    req: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建对话会话"""
    session = await chat_service.create_session(
        db,
        meeting_id=req.meeting_id,
        title=req.title,
    )
    return SessionResponse(
        id=str(session.id),
        meeting_id=str(session.meeting_id) if session.meeting_id else None,
        title=session.title,
        created_at=session.created_at.isoformat(),
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    meeting_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取会话列表"""
    sessions = await chat_service.list_sessions(db, meeting_id)
    return [
        SessionResponse(
            id=str(s.id),
            meeting_id=str(s.meeting_id) if s.meeting_id else None,
            title=s.title,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取会话消息历史"""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的会话 ID")

    msgs = await chat_service.get_session_messages(db, session_id)
    return [
        MessageResponse(
            id=str(m.id),
            session_id=str(m.session_id),
            role=m.role,
            content=m.content,
            metadata=m.metadata_,
            created_at=m.created_at.isoformat(),
        )
        for m in msgs
    ]


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除会话"""
    session_id = str(session_id)
    await chat_generations.cancel_session(session_id)
    ok = await chat_service.delete_session(db, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"message": "已删除"}


# ── SSE 流式对话 ──

@router.post("/sessions/{session_id}/generations/{generation_id}/cancel")
async def cancel_generation(session_id: uuid.UUID, generation_id: uuid.UUID):
    run = chat_generations.cancel(str(session_id), str(generation_id))
    return {"generation_id": run.id, "status": "cancelling" if run.cancel_requested and run.status == "generating" else run.status}


@router.post("/sessions/{session_id}/stream")
async def chat_stream(
    session_id: str,
    req: ChatRequest,
):
    """SSE 流式对话

    返回 Server-Sent Events：
    - data: {"type": "token", "content": "..."}  增量内容
    - data: {"type": "done"}  完成；所有事件携带 generation_id、seq
    - data: {"type": "error", "message": "..."} 错误
    - data: {"type": "cancelled"} 主动取消或断开后超过恢复等待时间
    resume=true 只订阅已有任务，从 last_seq+1 补发，不会重新调用模型。
    """
    try:
        session_id = str(uuid.UUID(session_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的会话 ID")

    if not req.query.strip():
        raise HTTPException(status_code=400, detail="查询不能为空")

    generation_id = str(req.generation_id)
    run = chat_generations.start_or_resume(
        session_id, generation_id, req.query, req.images,
        resume=req.resume, last_seq=req.last_seq,
    )

    async def event_generator():
        subscription = chat_generations.subscribe(run, req.last_seq)
        try:
            async for event in subscription:
                if event is None:
                    yield ": keep-alive\n\n"
                else:
                    yield f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        except HTTPException as exc:
            # 连接已打开后才发生缓存淘汰：发送终止错误，前端不从头生成。
            event = {"type": "error", "message": exc.detail, "generation_id": generation_id, "seq": run.seq}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            # 断网只释放此订阅；生成任务继续等待客户端恢复，主动停止走 cancel。
            with anyio.move_on_after(5, shield=True):
                await subscription.aclose()

    return ChatStreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
