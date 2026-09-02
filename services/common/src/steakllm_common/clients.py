"""One factory per dependency, endpoints from settings — the demo's calls, packaged."""

from __future__ import annotations

from typing import Any

import boto3
import httpx

from .settings import Settings


def s3_client(s: Settings, public: bool = False):
    """MinIO locally (explicit dev credentials), real S3 in the cloud (the pod's role).
    `public=True` signs for the client-reachable endpoint (presigned URLs)."""
    kwargs: dict[str, Any] = {"region_name": s.aws_region}
    endpoint = (s.s3_public_endpoint_url or s.s3_endpoint_url) if public else s.s3_endpoint_url
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if s.minio_root_user and s.minio_root_password:
        kwargs["aws_access_key_id"] = s.minio_root_user
        kwargs["aws_secret_access_key"] = s.minio_root_password
    return boto3.client("s3", **kwargs)


def catalog_table(s: Settings):
    """DynamoDB Local accepts any credentials; real DynamoDB uses the pod's role."""
    kwargs: dict[str, Any] = {"region_name": s.aws_region}
    if s.dynamodb_endpoint_url:
        kwargs.update(
            endpoint_url=s.dynamodb_endpoint_url,
            aws_access_key_id="local",
            aws_secret_access_key="local",
        )
    return boto3.resource("dynamodb", **kwargs).Table(s.catalog_table)


def qdrant_client(s: Settings):
    from qdrant_client import QdrantClient

    return QdrantClient(url=s.qdrant_url)


def bedrock_client(s: Settings):
    session = boto3.Session(profile_name=s.aws_profile or None, region_name=s.aws_region)
    return session.client("bedrock-runtime")


def embed(s: Settings, texts: list[str], client: httpx.Client | None = None) -> list[list[float]]:
    """OpenAI-compatible /v1/embeddings (Ollama locally; anything else later). Checks the size."""
    c = client or httpx.Client(timeout=120)
    r = c.post(f"{s.embeddings_url}/embeddings", json={"model": s.embedding_model, "input": texts})
    r.raise_for_status()
    vectors = [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    if any(len(v) != s.embedding_dim for v in vectors):
        raise ValueError(f"embedding size differs from EMBEDDING_DIM={s.embedding_dim}")
    return vectors
