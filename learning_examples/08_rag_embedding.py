import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv


project_root = Path(__file__).resolve().parents[1]
load_dotenv(project_root / "backend" / ".env")
sys.path.insert(0, str(project_root / "backend"))

from app.services.embedding_service import embedding_service


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(left, right))
    left_length = sum(value * value for value in left) ** 0.5
    right_length = sum(value * value for value in right) ** 0.5
    return dot_product / (left_length * right_length)


async def main():
    texts = [
        "修复登录功能的用户认证问题",
        "解决账号登录时的身份验证故障",
        "安排周末团建聚餐活动",
    ]

    vectors = await embedding_service.embed_batch(texts)
    if any(vector is None for vector in vectors):
        raise RuntimeError("向量生成失败，请检查 API 配置和终端日志")

    login_vector, auth_vector, activity_vector = vectors

    print("向量数量：", len(vectors))
    print("每个向量的维度：", len(login_vector))
    print("登录 vs 身份验证：", round(cosine_similarity(login_vector, auth_vector), 4))
    print("登录 vs 团建活动：", round(cosine_similarity(login_vector, activity_vector), 4))


if __name__ == "__main__":
    asyncio.run(main())
