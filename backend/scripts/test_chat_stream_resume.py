"""离线自检：断开/补发/结束事件恢复/幂等创建/显式取消/缓存过期。

运行：.venv/Scripts/python.exe -X utf8 scripts/test_chat_stream_resume.py
假模型与假数据库；断线补发必须只创建一次模型请求。
"""

import asyncio
import json
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from app.api import chat as api
from app.services import chat_generation_service as generations
from app.services.chat_service import ChatService
from scripts.test_chat_stream_cancel import FakeDB


@contextmanager
def fixture():
    store = generations.ChatGenerations()
    db = FakeDB()
    gate = asyncio.Event()
    model_started = asyncio.Event()
    upstream = SimpleNamespace(closed=False, calls=0, fail=False)
    service = ChatService()

    async def save(_db, session_id, role, content, metadata=None, created_at=None):
        message = SimpleNamespace(
            role=role, content=content, metadata_=metadata.copy(),
            created_at=created_at or datetime.now(timezone.utc),
        )
        db.messages.append(message)
        await asyncio.sleep(0)
        return message

    async def history(*args):
        return db.messages

    async def search(*args, **kwargs):
        return []

    class ModelStream:
        async def __aiter__(self):
            for index, text in enumerate(["一", "二", "三"]):
                if index == 1:
                    if upstream.fail:
                        raise RuntimeError("test model failure")
                    await gate.wait()
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])

        async def close(self):
            await asyncio.sleep(0)
            upstream.closed = True

    async def create(**kwargs):
        upstream.calls += 1
        model_started.set()
        return ModelStream()

    service.save_message = save
    service.get_session_messages = history
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with (
        patch.object(api, "chat_generations", store),
        patch.object(generations, "chat_service", service),
        patch.object(generations, "async_session_factory", return_value=db),
        patch("app.services.chat_service.knowledge_service.search", search),
        patch("app.services.chat_service.decision_graph_service.search", search),
    ):
        yield SimpleNamespace(store=store, db=db, gate=gate, model_started=model_started, upstream=upstream)


async def consume(response, *, disconnect_after=None, send_error=False):
    events = []
    disconnected = asyncio.Event()

    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        body = message.get("body", b"").decode()
        data = next((line[6:] for line in body.splitlines() if line.startswith("data: ")), None)
        if data is None:
            return
        event = json.loads(data)
        assert f"id: {event['seq']}" in body
        events.append(event)
        if event["seq"] == disconnect_after:
            if send_error:
                raise OSError("browser disconnected")
            disconnected.set()
            await asyncio.Event().wait()

    try:
        await asyncio.wait_for(response({"type": "http", "headers": []}, receive, send), timeout=3)
    except ExceptionGroup as exc:
        assert send_error and exc.subgroup(OSError) is not None
    return events


async def request(sid, gid, *, last_seq=0, resume=False, query="会议进展如何？"):
    return await api.chat_stream(sid, api.ChatRequest(
        query=query, generation_id=gid, last_seq=last_seq, resume=resume,
    ))


async def expect_status(status, awaitable):
    try:
        await awaitable
    except HTTPException as exc:
        assert exc.status_code == status, exc
    else:
        raise AssertionError(f"expected HTTP {status}")


async def resume_check(send_error=False):
    with fixture() as f:
        try:
            sid, gid = str(uuid.uuid4()), str(uuid.uuid4())
            first = await consume(await request(sid, gid), disconnect_after=1, send_error=send_error)
            run = f.store.runs[(sid, gid)]
            assert run.subscribers == 0 and not run.task.done()
            assert not f.upstream.closed, "断网错误地取消了模型"
            replay = asyncio.create_task(consume(await request(sid, gid, last_seq=1, resume=True)))
            f.gate.set()
            rest = await replay
            assert [e["seq"] for e in first + rest] == [1, 2, 3, 4]
            assert "".join(e.get("content", "") for e in first + rest) == "一二三"
            assert rest[-1]["type"] == "done"
            assert f.upstream.calls == 1 and f.upstream.closed and f.db.closed
            assert [m.role for m in f.db.messages] == ["user", "assistant"]
            assert f.db.messages[-1].metadata_["status"] == "completed"

            # 重复创建请求/补回漏收的结束事件都不能创建第二次模型请求。
            again = await consume(await request(sid, gid))
            terminal = await consume(await request(sid, gid, last_seq=3, resume=True))
            assert len(again) == 4 and [e["type"] for e in terminal] == ["done"]
            assert f.upstream.calls == 1 and len(f.db.messages) == 2
            await expect_status(409, request(sid, gid, last_seq=99, resume=True))
            await expect_status(409, request(sid, gid, query="不同的问题"))
            await expect_status(410, request(str(uuid.uuid4()), gid, resume=True))

            f.store._expire(run)
            await expect_status(410, request(sid, gid, resume=True))
            assert f.upstream.calls == 1
            print(f"resume after {'send failure' if send_error else 'disconnect'}, terminal replay, idempotency: ok")
        finally:
            await f.store.aclose()


async def cancellation_check():
    with fixture() as f:
        try:
            sid, gid = str(uuid.uuid4()), str(uuid.uuid4())
            await consume(await request(sid, gid), disconnect_after=1)
            await api.cancel_generation(uuid.UUID(sid), uuid.UUID(gid))
            await api.cancel_generation(uuid.UUID(sid), uuid.UUID(gid))
            run = f.store.runs[(sid, gid)]
            await asyncio.gather(run.task, return_exceptions=True)
            await asyncio.sleep(0)
            assert run.status == "cancelled" and f.upstream.closed and f.db.closed
            assert f.db.messages[-1].content == "一"
            assert f.db.messages[-1].metadata_["status"] == "cancelled"
            rest = await consume(await request(sid, gid, last_seq=1, resume=True))
            assert [e["type"] for e in rest] == ["cancelled"]
            assert f.upstream.calls == 1

            # 取消先到、创建请求后到：后者必须只得到取消记录。
            late = str(uuid.uuid4())
            await api.cancel_generation(uuid.UUID(sid), uuid.UUID(late))
            stopped = await consume(await request(sid, late))
            assert stopped[0]["type"] == "cancelled" and f.upstream.calls == 1
            print("explicit stop, repeated cancel, stop-before-create: ok")
        finally:
            await f.store.aclose()


async def limits_check():
    with fixture() as f, patch.object(generations, "MAX_EVENTS", 2):
        try:
            sid, gid = str(uuid.uuid4()), str(uuid.uuid4())
            f.gate.set()
            response = await request(sid, gid)
            run = f.store.runs[(sid, gid)]
            await run.task
            await asyncio.sleep(0)
            assert len(run.events) == 2
            await expect_status(410, request(sid, gid, resume=True))
            # 关闭最初没有消费的响应，再从仍在缓存中的位置恢复。
            await response.body_iterator.aclose()
            remaining = await consume(await request(sid, gid, last_seq=2, resume=True))
            assert [e["seq"] for e in remaining] == [3, 4]
            print("bounded cache and expired cursor: ok")
        finally:
            await f.store.aclose()

    with fixture() as f, patch.object(generations, "DISCONNECT_GRACE_SECONDS", 0.03):
        try:
            sid, gid = str(uuid.uuid4()), str(uuid.uuid4())
            await consume(await request(sid, gid), disconnect_after=1)
            run = f.store.runs[(sid, gid)]
            await asyncio.wait_for(asyncio.gather(run.task, return_exceptions=True), timeout=1)
            await asyncio.sleep(0)
            assert run.status == "cancelled" and f.upstream.closed
            print("abandoned task grace timeout: ok")
        finally:
            await f.store.aclose()

    with fixture() as f, patch.object(generations, "REPLAY_TTL_SECONDS", 0.03):
        try:
            sid, gid = str(uuid.uuid4()), str(uuid.uuid4())
            f.gate.set()
            await consume(await request(sid, gid))
            await asyncio.sleep(0.05)
            await expect_status(410, request(sid, gid, resume=True))
            assert f.upstream.calls == 1
            print("completed replay TTL: ok")
        finally:
            await f.store.aclose()

    with fixture() as f:
        sid, gid = str(uuid.uuid4()), str(uuid.uuid4())
        await consume(await request(sid, gid), disconnect_after=1)
        await f.store.aclose()
        assert f.upstream.closed and f.db.closed and not f.store.runs
        assert f.db.messages[-1].metadata_["status"] == "cancelled"
        print("application shutdown closes active generation: ok")


async def failure_check():
    with fixture() as f, patch.object(generations.logger, "error"), patch("app.services.chat_service.logger.error"):
        try:
            f.upstream.fail = True
            sid, gid = str(uuid.uuid4()), str(uuid.uuid4())
            events = await consume(await request(sid, gid))
            assert [e["type"] for e in events] == ["token", "error"]
            assert f.db.messages[-1].content == "一"
            assert f.db.messages[-1].metadata_["status"] == "failed"
            assert f.upstream.closed and f.db.closed
            replay = await consume(await request(sid, gid, last_seq=1, resume=True))
            assert [e["type"] for e in replay] == ["error"] and f.upstream.calls == 1
            print("failed generation preserves prefix and replays terminal error: ok")
        finally:
            await f.store.aclose()


async def main():
    await resume_check()
    await resume_check(send_error=True)
    await cancellation_check()
    await limits_check()
    await failure_check()


if __name__ == "__main__":
    asyncio.run(main())
