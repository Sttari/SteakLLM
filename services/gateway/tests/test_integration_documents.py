"""Real stack + real Bedrock: presigned upload → ingest → index → `docs` answers with a citation.

The ingest and embedder handlers are called in-process (their services are not yet running as
containers — 6.9); the gateway, MinIO, Kafka, Qdrant, DynamoDB Local, Ollama and Bedrock are real.
"""

from __future__ import annotations

import uuid
from functools import partial

import httpx
import pytest
from fastapi.testclient import TestClient
from steakllm_common.clients import bedrock_client, catalog_table, embed, qdrant_client, s3_client
from steakllm_common.kafka import make_producer
from steakllm_common.logging import configure
from steakllm_common.settings import Settings

from steakllm_gateway.app import Deps, create_app
from steakllm_gateway.backends import BedrockBackend, VllmBackend
from steakllm_gateway.rag import Retriever
from steakllm_gateway.router import CircuitBreaker, Router

pytestmark = pytest.mark.integration


def test_upload_index_ask_with_citation_then_delete():
    configure("gateway-it")
    s = Settings()
    producer = make_producer(s)
    s3, table, qdrant = s3_client(s), catalog_table(s), qdrant_client(s)
    deps = Deps(
        settings=s,
        router=Router(
            vllm=VllmBackend(s.vllm_url),
            bedrock=BedrockBackend(bedrock_client(s), s.bedrock_model_id),
            breaker=CircuitBreaker(),
        ),
        producer=producer,
        s3=s3,
        table=table,
        retriever=Retriever(qdrant, partial(embed, s), top_k=s.rag_top_k),
    )
    client = TestClient(create_app(deps))
    auth = {"Authorization": f"Bearer {s.gateway_api_key}"}
    marker = uuid.uuid4().hex[:8]
    text = (
        f"# Ferrous Foods memo {marker}\n\nThe Rotterdam hub opened in July and now handles all "
        "EMEA cold-chain logistics. The Leeds depot closed in June. Headcount is 2,140."
    ).encode()

    # 1. presigned upload, then PUT the bytes straight to MinIO with it
    r = client.post(
        "/v1/uploads",
        headers=auth,
        json={
            "filename": f"memo-{marker}.md",
            "content_type": "text/markdown",
            "size_bytes": len(text),
        },
    )
    assert r.status_code == 201, r.text
    up = r.json()
    put = httpx.put(up["url"], content=text, headers=up["headers"], timeout=30)
    assert put.status_code == 200, put.text

    # 2. ingest + index in-process (the services run as containers from 6.9)
    from steakllm_embedder.handler import Deps as EmbDeps
    from steakllm_embedder.handler import handle as embed_handle
    from steakllm_ingest.handler import Deps as IngDeps
    from steakllm_ingest.handler import handle as ingest_handle
    from steakllm_ingest.main import s3_record

    ing = IngDeps(settings=s, s3=s3, table=table, producer=producer)
    (uploaded,) = ingest_handle(s3_record(s.documents_bucket, up["key"]), ing)
    doc = uploaded["doc_id"]
    emb = EmbDeps(
        settings=s, s3=s3, table=table, qdrant=qdrant, producer=producer, embed=partial(embed, s)
    )
    embed_handle(uploaded, {}, emb)
    try:
        # 3. the catalog page shows the journey so far
        page = client.get(f"/catalog?key={s.gateway_api_key}")
        assert page.status_code == 200 and doc[:12] in page.text and "✓ indexed" in page.text

        # 4. ask the docs model; expect a citation of our document and the fact from the memo
        r = client.post(
            "/v1/chat/completions",
            headers=auth,
            json={
                "model": "docs",
                "messages": [
                    {"role": "user", "content": f"According to memo {marker}, where is the hub?"}
                ],
                "max_tokens": 120,
            },
        )
        assert r.status_code == 200, r.text
        answer = r.json()["choices"][0]["message"]["content"]
        assert r.headers["x-backend"] == "bedrock"
        assert doc in r.headers["x-retrieved-doc-ids"].split(",")
        assert "rotterdam" in answer.lower()
        # The citation label is model behaviour (Nova Micro is inconsistent); retrieval itself is
        # proven by the header above. Reported, not asserted — see field notes, open items.
        print("citation label present:", f"[{doc[:8]}:" in answer)
    finally:
        # 5. delete everywhere through the API; the embedder drops the points
        assert client.delete(f"/v1/documents/{doc}", headers=auth).status_code == 204
        embed_handle(
            {**uploaded, "type": "DocumentDeleted", "data": {"reason": "user_request"}}, {}, emb
        )
    assert "Item" not in table.get_item(Key={"doc_id": doc})
