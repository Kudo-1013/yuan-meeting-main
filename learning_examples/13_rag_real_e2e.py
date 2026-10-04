import json

import httpx


BASE_URL = "http://127.0.0.1:8787/api"
TITLE = "[学习验证] 北极星 RAG 技术约定"
SESSION_TITLE = "[学习验证] RAG 真实闭环"
QUERY = "北极星 RAG 使用哪个 Embedding 模型、多少维向量，以及什么数据库扩展？"
CONTENT = """北极星 RAG 验证文档。

项目的 Embedding 模型确定为 text-embedding-v3，输出 1024 维向量。
向量、正文和元数据统一保存在 PostgreSQL 中，使用 pgvector 扩展执行 cosine 距离检索。
知识文档默认按 1000 字符切块，相邻块重叠 200 字符。
检索阶段同时使用向量检索和全文检索，再通过 RRF 合并排名。
"""


with httpx.Client(timeout=120) as client:
    # 删除上一次学习验证数据，让脚本可以重复运行。
    old_documents = client.get(
        f"{BASE_URL}/knowledge/documents",
        params={"page": 1, "page_size": 100},
    ).json()
    for document in old_documents:
        if document["title"] in {
            TITLE,
            "[学习验证] Yuan Meeting README 2026-09-11",
        }:
            client.delete(f"{BASE_URL}/knowledge/documents/{document['id']}")

    old_sessions = client.get(f"{BASE_URL}/chat/sessions").json()
    for session in old_sessions:
        if session["title"] == SESSION_TITLE:
            client.delete(f"{BASE_URL}/chat/sessions/{session['id']}")

    index_response = client.post(
        f"{BASE_URL}/knowledge/index",
        json={
            "title": TITLE,
            "content": CONTENT,
            "source_type": "uploaded_doc",
            "metadata": {"purpose": "rag-e2e-learning"},
        },
    )
    index_response.raise_for_status()
    indexed_chunks = index_response.json()
    print("入库 chunk 数量：", len(indexed_chunks))

    search_response = client.post(
        f"{BASE_URL}/knowledge/search",
        json={"query": QUERY, "top_k": 3},
    )
    search_response.raise_for_status()
    search_results = search_response.json()["results"]

    print("\n真实检索结果：")
    for index, result in enumerate(search_results, 1):
        print(
            f"{index}. {result['title']} score={result['score']:.4f}\n"
            f"   {result['content'][:160].replace(chr(10), ' ')}"
        )

    if not any(result["title"] == TITLE for result in search_results):
        raise RuntimeError("刚写入的测试知识没有进入检索结果")

    session_response = client.post(
        f"{BASE_URL}/chat/sessions",
        json={"title": SESSION_TITLE},
    )
    session_response.raise_for_status()
    session_id = session_response.json()["id"]

    print("\n模型流式回答：", end="", flush=True)
    with client.stream(
        "POST",
        f"{BASE_URL}/chat/sessions/{session_id}/stream",
        json={"query": QUERY},
    ) as stream_response:
        stream_response.raise_for_status()
        for line in stream_response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "token":
                print(event["content"], end="", flush=True)
            elif event["type"] == "error":
                raise RuntimeError(event["message"])
    print()

    messages_response = client.get(
        f"{BASE_URL}/chat/sessions/{session_id}/messages"
    )
    messages_response.raise_for_status()
    assistant_messages = [
        message
        for message in messages_response.json()
        if message["role"] == "assistant"
    ]
    assistant_message = assistant_messages[-1]
    metadata = assistant_message.get("metadata") or {}

    print("\n会话 ID：", session_id)
    print("回答已保存：", bool(assistant_messages))
    print("保存的来源：")
    for source in metadata.get("sources", []):
        print(f"- {source['source_type']} | {source['title']} | {source['score']}")
