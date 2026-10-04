"""离线自检：生成任务显式取消时关闭上游，并保存前缀与取消状态。

运行：.venv/Scripts/python.exe -X utf8 scripts/test_chat_stream_cancel.py
使用假数据库与假模型，不调用付费 API。
"""

import asyncio
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.chat_service import ChatService


class FakeDB:
    def __init__(self):
        self.messages = []
        self.closed = False
        self.rolled_back = False

    async def rollback(self):
        await asyncio.sleep(0)
        self.rolled_back = True

    async def close(self):
        await asyncio.sleep(0)
        self.closed = True


class FakeStream:
    def __init__(self, mode, waiting):
        self.mode = mode
        self.waiting = waiting
        self.closed = False

    async def __aiter__(self):
        for index, text in enumerate(["已生成", "完整回复"]):
            if index == 1 and self.mode == "read":
                self.waiting.set()
                await asyncio.Event().wait()
            yield SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content=text),
            )])

    async def close(self):
        # 被取消的 AnyIO 任务仍必须执行这个 await。
        await asyncio.sleep(0)
        self.closed = True


async def check(mode):
    db = FakeDB()
    waiting = asyncio.Event()
    upstream = FakeStream(mode, waiting)
    service = ChatService()
    model_called = False

    async def save_message(_db, session_id, role, content, metadata=None, created_at=None):
        await asyncio.sleep(0)
        message = SimpleNamespace(
            role=role, content=content, metadata_=metadata,
            created_at=created_at or datetime.now(timezone.utc),
        )
        db.messages.append(message)
        return message

    async def history(*args):
        return db.messages

    async def search(*args, **kwargs):
        if mode == "retrieval":
            waiting.set()
            await asyncio.Event().wait()
        return []

    async def create(**kwargs):
        nonlocal model_called
        model_called = True
        assert kwargs["stream"] is True
        if mode == "before":
            waiting.set()
            await asyncio.Event().wait()
        return upstream

    service.save_message = save_message
    service.get_session_messages = history
    service.client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create),
    ))
    generation_id = str(uuid.uuid4())
    events = []

    async def consume():
        chunks = service.chat_stream(db, str(uuid.uuid4()), "会议进展如何？", None, generation_id)
        try:
            async for delta in chunks:
                events.append(delta)
                if mode == "send":
                    return  # 显式关闭停在 yield 的生成器
                if mode == "send_error":
                    raise OSError("output closed")
        finally:
            with anyio.move_on_after(15, shield=True):
                await chunks.aclose()
                await db.close()

    with (
        patch("app.services.chat_service.knowledge_service.search", search),
        patch("app.services.chat_service.decision_graph_service.search", search),
    ):
        task = asyncio.create_task(consume())
        if mode in {"retrieval", "before", "read"}:
            await asyncio.wait_for(waiting.wait(), timeout=3)
            task.cancel()
        try:
            await asyncio.wait_for(task, timeout=3)
        except asyncio.CancelledError:
            assert mode in {"retrieval", "before", "read"}
        except OSError:
            assert mode == "send_error"

    assert db.closed, "HTTP 断开后数据库连接未释放"
    assert db.messages[0].metadata_["generation_id"] == generation_id
    assistant = db.messages[-1]
    assert assistant.role == "assistant"
    assert assistant.metadata_["generation_id"] == generation_id
    assert 0 < (assistant.created_at - db.messages[0].created_at).total_seconds() < 0.001
    if mode == "complete":
        assert assistant.content == "已生成完整回复"
        assert assistant.metadata_["status"] == "completed"
        assert events == ["已生成", "完整回复"]
    else:
        assert assistant.metadata_["status"] == "cancelled"
        assert assistant.content == ("已生成" if mode in {"read", "send", "send_error"} else "")
        assert db.rolled_back
    if mode in {"complete", "read", "send", "send_error"}:
        assert upstream.closed, "模型 HTTP 响应流未关闭"
    if mode == "retrieval":
        assert not model_called, "检索取消后仍调用了模型"
    print(f"chat stream {mode}: ok")


async def main():
    for mode in ["complete", "retrieval", "before", "read", "send", "send_error"]:
        await check(mode)


if __name__ == "__main__":
    asyncio.run(main())
