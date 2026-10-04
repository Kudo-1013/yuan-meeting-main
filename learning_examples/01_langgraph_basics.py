"""最小 LangGraph 示例：让两个普通 Python 函数按顺序执行。"""

from typing import TypedDict

from langgraph.graph import END, StateGraph


class NumberState(TypedDict):
    number: int


def add_one(state: NumberState) -> dict:
    result = state["number"] + 1
    print(f"add_one：{state['number']} + 1 = {result}")
    return {"number": result}


def double(state: NumberState) -> dict:
    result = state["number"] * 2
    print(f"double：{state['number']} × 2 = {result}")
    return {"number": result}

# 配置工作流
workflow = StateGraph(NumberState)
workflow.add_node("add_one", add_one)
workflow.add_node("double", double)
workflow.set_entry_point("double")
workflow.add_edge("double", "add_one")
workflow.add_edge("add_one", END)
# 把配置好的工作流编译成可运行对象
app = workflow.compile()


if __name__ == "__main__":
    final_state = app.invoke({"number": 3})
    print("最终状态：", final_state)
    assert final_state["number"] == 7
