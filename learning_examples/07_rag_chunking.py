import sys
from pathlib import Path


project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "backend"))

from app.services.document_chunker import DocumentChunker


text = (
    "第一部分：产品经理提出登录页面需要增加手机验证码。"
    "第二部分：张三负责前端页面，计划周三完成。"
    "第三部分：李四负责后端验证码接口，计划周四完成。"
    "第四部分：测试人员计划周五开始联调。"
    "第五部分：当前风险是短信服务可能出现延迟。"
    "第六部分：团队决定下周一正式上线。"
)

# 项目默认是 1000/200；这里缩小参数，方便观察分块和重叠。
chunker = DocumentChunker(chunk_size=60, chunk_overlap=25)
chunks = chunker.split_with_metadata(
    text,
    {"title": "登录功能评审会"},
)

for chunk in chunks:
    metadata = chunk["metadata"]
    print(
        f"\n--- chunk {metadata['chunk_index'] + 1}/"
        f"{metadata['total_chunks']}，长度 {len(chunk['content'])} ---"
    )
    print(chunk["content"])
    print("metadata:", metadata)
