"""最小自检：LangGraph 节点更新会转换成纪要 SSE 增量事件。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.summary_service import summary_service


class FakeGraph:
    async def astream(self, initial_state, *, stream_mode):
        assert stream_mode == ["updates", "values"]
        yield "values", initial_state
        yield "updates", {
            "summary_agent": {
                "summary": "登录功能评审完成。",
                "key_points": ["周五联调"],
            }
        }
        yield "updates", {
            "action_items_agent": {"action_items": [{"title": "完成联调"}]}
        }
        yield "updates", {
            "risks_agent": {"risks": [{"description": "测试时间不足"}]}
        }
        yield "values", {
            **initial_state,
            "summary": "登录功能评审完成。",
            "key_points": ["周五联调"],
            "action_items": [{"title": "完成联调"}],
            "risks": [{"description": "测试时间不足"}],
        }


async def main() -> None:
    events = []

    async def collect(event):
        events.append(event)

    final_state = await summary_service._invoke_graph_with_events(
        FakeGraph(),
        {"summary": "", "key_points": [], "action_items": [], "risks": []},
        collect,
    )

    assert [event["type"] for event in events] == [
        "summary",
        "progress",
        "progress",
    ]
    assert events[0]["content"] == "登录功能评审完成。"
    assert final_state["risks"][0]["description"] == "测试时间不足"
    print("summary stream events: ok")


if __name__ == "__main__":
    asyncio.run(main())
