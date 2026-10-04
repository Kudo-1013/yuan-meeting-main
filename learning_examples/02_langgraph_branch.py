"""最小 LangGraph 条件分支：根据 State 选择下一个节点。"""

from typing import TypedDict

from langgraph.graph import END, StateGraph


class NumberState(TypedDict):
    number: int
    category: str


def double(state: NumberState) -> dict:
    result = state["number"] * 2
    print(f"double：{state['number']} × 2 = {result}")
    return {"number": result}


def choose_next(state: NumberState) -> str:
    route = "large" if state["number"] >= 5 else "small"
    print(f"choose_next：number 是 {state['number']}，选择 {route}")
    return route


def mark_large(state: NumberState) -> dict:
    return {"category": "large"}


def mark_small(state: NumberState) -> dict:
    return {"category": "small"}


workflow = StateGraph(NumberState)
workflow.add_node("double", double)
workflow.add_node("large", mark_large)
workflow.add_node("small", mark_small)
workflow.set_entry_point("double")
workflow.add_conditional_edges(
    "double",
    choose_next,
    {"large": "large", "small": "small"},
)
workflow.add_edge("large", END)
workflow.add_edge("small", END)

app = workflow.compile()


if __name__ == "__main__":
    final_state = app.invoke({"number": 2, "category": ""})
    print("最终状态：", final_state)
    assert final_state == {"number": 4, "category": "small"}
