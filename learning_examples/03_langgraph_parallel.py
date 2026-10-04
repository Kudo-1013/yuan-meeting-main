"""最小 LangGraph 并行示例：三个节点同时处理同一份会议文本。"""

import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class MeetingState(TypedDict):
    transcript: str
    summary: str
    actions: list[str]
    risks: list[str]


def summary_agent(state: MeetingState) -> dict:
    print("摘要节点开始，读取：", state["transcript"])
    time.sleep(1)
    return {"summary": "会议讨论了登录功能上线"}


def actions_agent(state: MeetingState) -> dict:
    print("行动项节点开始，读取：", state["transcript"])
    time.sleep(1)
    return {"actions": ["完成登录功能测试"]}


def risks_agent(state: MeetingState) -> dict:
    print("风险节点开始，读取：", state["transcript"])
    time.sleep(1)
    return {"risks": ["测试时间不足"]}


workflow = StateGraph(MeetingState)
workflow.add_node("summary_agent", summary_agent)
workflow.add_node("actions_agent", actions_agent)
workflow.add_node("risks_agent", risks_agent)

workflow.add_edge(START, "summary_agent")
workflow.add_edge(START, "actions_agent")
workflow.add_edge(START, "risks_agent")
workflow.add_edge("summary_agent", END)
workflow.add_edge("actions_agent", END)
workflow.add_edge("risks_agent", END)

app = workflow.compile()


if __name__ == "__main__":
    started_at = time.perf_counter()
    final_state = app.invoke(
        {
            "transcript": "讨论登录功能上线",
            "summary": "",
            "actions": [],
            "risks": [],
        }
    )

    print("最终状态：", final_state)
    print(f"总耗时：{time.perf_counter() - started_at:.2f} 秒")
    assert final_state["summary"]
    assert final_state["actions"]
    assert final_state["risks"]
