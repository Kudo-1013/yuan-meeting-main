import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv


project_root = Path(__file__).resolve().parents[1]
load_dotenv(project_root / "backend" / ".env")
sys.path.insert(0, str(project_root / "backend"))

from app.services.chat_service import SYSTEM_PROMPT, chat_service


context = """[1] 来源：会议纪要 - 登录功能评审会
内容：团队决定采用短信验证码登录，张三负责前端页面。

[2] 来源：决策库 - 登录认证方案选择
已选方案：短信验证码
背景：评审比较了密码登录和短信验证码，最终选择短信验证码。

[3] 来源：文档 - 登录模块需求文档
内容：验证码有效期为五分钟，连续输错五次后暂时锁定账号。"""

messages = [
    {"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
    {"role": "user", "content": "登录认证最终选择了什么方案？请说明来源。"},
]


async def main():
    if chat_service.client is None:
        raise RuntimeError("模型客户端未初始化，请检查 backend/.env")

    stream = await chat_service.client.chat.completions.create(
        model=chat_service.model,
        messages=messages,
        stream=True,
        temperature=0,
    )

    print("模型回答：", end="", flush=True)
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
