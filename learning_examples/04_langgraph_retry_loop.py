"""最小 LangGraph 循环示例：校验失败后重新生成。"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class RetryState(TypedDict):
    transcript: str
    answer: str
    attempts: int
    valid: bool


def generate(state: RetryState) -> dict:
    attempts = state["attempts"] + 1
    answer = "修复登录问题" if attempts == 1 else state["transcript"]
    print(f"第 {attempts} 次生成：{answer}")
    return {"answer": answer, "attempts": attempts}


def validate(state: RetryState) -> dict:
    valid = "张三" in state["answer"] and "周五前" in state["answer"]
    print("校验结果：", valid)
    return {"valid": valid}


def choose_next(state: RetryState) -> str:
    return "finish" if state["valid"] else "retry"


workflow = StateGraph(RetryState)
workflow.add_node("generate", generate)
workflow.add_node("validate", validate)

workflow.add_edge(START, "generate")
workflow.add_edge("generate", "validate")
workflow.add_conditional_edges(
    "validate",
    choose_next,
    {"retry": "generate", "finish": END},
)

app = workflow.compile()


if __name__ == "__main__":
    final_state = app.invoke(
        {
            "transcript": "张三在周五前修复登录问题",
            "answer": "",
            "attempts": 0,
            "valid": False,
        }
    )
    print("最终状态：", final_state)
    assert final_state["attempts"] == 2
    assert final_state["valid"] is True
