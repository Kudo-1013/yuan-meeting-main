import sys
from pathlib import Path

from dotenv import load_dotenv


project_root = Path(__file__).resolve().parents[1]
load_dotenv(project_root / "backend" / ".env")
sys.path.insert(0, str(project_root / "backend"))

from app.services.chat_service import SYSTEM_PROMPT, chat_service


doc_results = [
    {
        "id": "doc-1",
        "source_type": "meeting_summary",
        "title": "登录功能评审会",
        "content": "团队决定采用短信验证码登录，张三负责前端页面。",
    },
    {
        "id": "doc-2",
        "source_type": "uploaded_doc",
        "title": "登录模块需求文档",
        "content": "验证码有效期为五分钟，连续输错五次后暂时锁定账号。",
    },
]

decision_results = [
    {
        "id": "decision-1",
        "source_type": "decision",
        "title": "登录认证方案选择",
        "chosen_option": "短信验证码",
        "context": "评审比较了密码登录和短信验证码，最终选择短信验证码。",
    },
    {
        "id": "decision-2",
        "source_type": "decision",
        "title": "登录功能上线时间",
        "chosen_option": "下周一上线",
        "context": "测试完成后于下周一发布。",
    },
]

fused_results = chat_service._rrf_fuse(
    doc_results,
    decision_results,
    top_k=4,
)

context_parts = []
for index, result in enumerate(fused_results, 1):
    if result.get("source_type") == "decision":
        context_parts.append(
            f"[{index}] 来源：决策库 - {result['title']}\n"
            f"已选方案：{result.get('chosen_option')}\n"
            f"背景：{result.get('context')}"
        )
    else:
        source = "会议纪要" if result.get("source_type") == "meeting_summary" else "文档"
        context_parts.append(
            f"[{index}] 来源：{source} - {result['title']}\n"
            f"内容：{result['content']}"
        )

context = "\n\n".join(context_parts)
messages = [
    {"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
    {"role": "user", "content": "登录认证最终选择了什么方案？"},
]

print("融合后的来源顺序：")
for result in fused_results:
    print(result["source_type"], result["title"], result["rrf_score"])

print("\n注入模型的 context：\n")
print(context)
print("\n用户问题：", messages[1]["content"])
