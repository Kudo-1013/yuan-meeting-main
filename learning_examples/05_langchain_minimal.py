import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


project_root = Path(__file__).resolve().parents[1]
load_dotenv(project_root / "backend" / ".env")

llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "qwen-plus"),
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.getenv(
        "OPENAI_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    temperature=0,
)

messages = [
    SystemMessage(content="你是一个简洁的计算助手。"),
    HumanMessage(content="12 加 8 等于多少？"),
]


if __name__ == "__main__":
    response = llm.invoke(messages)
    print("消息类型：", type(response).__name__)
    print("模型回答：", response.content)
