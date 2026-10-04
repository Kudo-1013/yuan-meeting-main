import sys
from pathlib import Path


project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "backend"))

from app.services.knowledge_service import knowledge_service


vector_results = [
    {"id": "A", "title": "账号认证故障"},
    {"id": "B", "title": "登录页面评审"},
    {"id": "C", "title": "周末团建安排"},
]

fulltext_results = [
    {"id": "B", "title": "登录页面评审"},
    {"id": "D", "title": "登录接口测试"},
    {"id": "A", "title": "账号认证故障"},
]

fused_results = knowledge_service._rrf_fusion(
    vector_results,
    fulltext_results,
)

print("向量检索排名：", [item["id"] for item in vector_results])
print("全文检索排名：", [item["id"] for item in fulltext_results])
print("RRF 最终排名：")

for rank, item in enumerate(fused_results, 1):
    print(
        f"{rank}. {item['id']} {item['title']} "
        f"score={item['score']:.6f}"
    )
