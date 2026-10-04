"""聊天生成任务与 SSE 连接分离：缓存事件，按游标重放，显式取消。

ponytail: 缓存和任务属于单个进程；多 worker/跨重启恢复时改用共享任务队列与 Redis Streams。
"""

import asyncio
import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field

import anyio
from fastapi import HTTPException

from app.db.session import async_session_factory
from app.services.chat_service import chat_service

logger = logging.getLogger(__name__)
REPLAY_TTL_SECONDS = 300
DISCONNECT_GRACE_SECONDS = 60
MAX_GENERATION_SECONDS = 600
MAX_GENERATIONS = 64
MAX_EVENTS = 4096
MAX_CACHE_BYTES = 2 * 1024 * 1024


@dataclass
class Generation:
    session_id: str
    id: str
    fingerprint: str | None
    events: deque = field(default_factory=deque)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    disconnect_timer: asyncio.TimerHandle | None = None
    expiry_timer: asyncio.TimerHandle | None = None
    subscribers: int = 0
    seq: int = 0
    cache_bytes: int = 0
    status: str = "generating"
    cancel_requested: bool = False

    def publish(self, event: dict) -> None:
        event = {**event, "generation_id": self.id, "seq": self.seq + 1}
        size = len(json.dumps(event, ensure_ascii=False).encode())
        if size > MAX_CACHE_BYTES:
            raise RuntimeError("单条输出超过恢复缓存上限")
        self.seq += 1
        self.events.append((event, size))
        self.cache_bytes += size
        while len(self.events) > MAX_EVENTS or self.cache_bytes > MAX_CACHE_BYTES:
            # 至少留下最新事件，使过旧游标得到明确的过期错误。
            if len(self.events) == 1:
                break
            _, removed_size = self.events.popleft()
            self.cache_bytes -= removed_size
        self.changed.set()

    def validate_cursor(self, last_seq: int) -> None:
        if last_seq > self.seq:
            raise HTTPException(409, "恢复游标超过已有事件序号")
        if self.events and last_seq < self.events[0][0]["seq"] - 1:
            raise HTTPException(410, "恢复内容已过期，请重新加载会话中的已保存回复")


class ChatGenerations:
    def __init__(self):
        self.runs: dict[tuple[str, str], Generation] = {}
        self.closed = False

    def _reserve(self, session_id: str, generation_id: str, fingerprint: str | None) -> Generation:
        if self.closed:
            raise HTTPException(503, "服务正在关闭")
        if len(self.runs) >= MAX_GENERATIONS:
            raise HTTPException(503, "生成缓存已满，请稍后重试")
        run = Generation(session_id, generation_id, fingerprint)
        self.runs[(session_id, generation_id)] = run
        return run

    def start_or_resume(
        self, session_id: str, generation_id: str, query: str,
        images: list[str] | None, *, resume: bool, last_seq: int,
    ) -> Generation:
        fingerprint = hashlib.sha256(json.dumps([query, images], ensure_ascii=False).encode()).hexdigest()
        run = self.runs.get((session_id, generation_id))
        if run is None:
            if resume or last_seq:
                # 缓存过期/服务重启时绝不把恢复请求变成一次新的模型生成。
                raise HTTPException(410, "这轮生成已无法恢复，请重新加载会话中的已保存回复")
            run = self._reserve(session_id, generation_id, fingerprint)
            run.task = asyncio.create_task(self._produce(run, query, images))
            run.task.add_done_callback(lambda task: self._finished(run, task))
            self._arm_disconnect(run)
        elif run.fingerprint is not None and run.fingerprint != fingerprint:
            raise HTTPException(409, "生成编号已用于另一条问题")
        run.validate_cursor(last_seq)
        return run

    async def _produce(self, run: Generation, query: str, images: list[str] | None) -> None:
        # 数据库与模型流由生成任务持有，HTTP 断开只结束订阅。
        db = async_session_factory()
        chunks = chat_service.chat_stream(db, run.session_id, query, images, run.id)
        try:
            async with asyncio.timeout(MAX_GENERATION_SECONDS):
                async for delta in chunks:
                    run.publish({"type": "token", "content": delta})
        finally:
            try:
                with anyio.move_on_after(12, shield=True):
                    await chunks.aclose()
            finally:
                with anyio.move_on_after(5, shield=True):
                    await db.close()

    def _finished(self, run: Generation, task: asyncio.Task) -> None:
        if run.disconnect_timer:
            run.disconnect_timer.cancel()
            run.disconnect_timer = None
        if task.cancelled():
            run.status = "cancelled"
            run.publish({"type": "cancelled"})
        elif task.exception() is not None:
            run.status = "failed"
            logger.error("生成 %s 失败", run.id, exc_info=task.exception())
            run.publish({"type": "error", "message": "生成失败，请稍后重试或查看会话记录"})
        else:
            run.status = "completed"
            run.publish({"type": "done"})
        self._arm_expiry(run)

    def _arm_expiry(self, run: Generation) -> None:
        if not self.closed:
            run.expiry_timer = asyncio.get_running_loop().call_later(
                REPLAY_TTL_SECONDS, self._expire, run,
            )

    def _expire(self, run: Generation) -> None:
        key = (run.session_id, run.id)
        if self.runs.get(key) is run:
            self.runs.pop(key)

    def _arm_disconnect(self, run: Generation) -> None:
        if run.status == "generating" and not run.subscribers and not run.disconnect_timer:
            run.disconnect_timer = asyncio.get_running_loop().call_later(
                DISCONNECT_GRACE_SECONDS, self.cancel, run.session_id, run.id,
            )

    async def subscribe(self, run: Generation, last_seq: int):
        run.subscribers += 1
        if run.disconnect_timer:
            run.disconnect_timer.cancel()
            run.disconnect_timer = None
        try:
            while True:
                run.validate_cursor(last_seq)
                pending = [event for event, _ in run.events if event["seq"] > last_seq]
                for event in pending:
                    yield event
                    last_seq = event["seq"]
                if run.status != "generating" and last_seq >= run.seq:
                    return
                if pending:
                    continue
                # 这里到 wait 之前没有 await，不会漏掉并发 publish 的唤醒。
                run.changed.clear()
                try:
                    await asyncio.wait_for(run.changed.wait(), timeout=15)
                except TimeoutError:
                    yield None  # SSE 注释心跳，不占业务事件序号
        finally:
            run.subscribers -= 1
            self._arm_disconnect(run)

    def cancel(self, session_id: str, generation_id: str) -> Generation:
        run = self.runs.get((session_id, generation_id))
        if run is None:
            # 停止请求可能先于创建请求抵达；保留取消记录，阻止迟到请求启动模型。
            run = self._reserve(session_id, generation_id, None)
            run.status = "cancelled"
            run.publish({"type": "cancelled"})
            self._arm_expiry(run)
        elif run.task and not run.task.done() and not run.cancel_requested:
            run.cancel_requested = True
            run.task.cancel()
        return run

    async def cancel_session(self, session_id: str) -> None:
        tasks = []
        for (sid, generation_id), run in list(self.runs.items()):
            if sid == session_id and run.task and not run.task.done():
                self.cancel(sid, generation_id)
                tasks.append(run.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def aclose(self) -> None:
        self.closed = True
        tasks = []
        for run in self.runs.values():
            for timer in (run.disconnect_timer, run.expiry_timer):
                if timer:
                    timer.cancel()
            if run.task and not run.task.done():
                if not run.cancel_requested:
                    run.cancel_requested = True
                    run.task.cancel()
                tasks.append(run.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.runs.clear()


chat_generations = ChatGenerations()
