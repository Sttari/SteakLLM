"""Configuration from the environment only — the `.env` keys as typed, validated fields.

A missing required value fails at process start with the key's name. Local-only defaults exist for
endpoints (so `make up` + `uv run …` works with no extra setup) and for nothing else that matters.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = Field(default="unknown", description="Set by each service's main().")

    # AWS: only Bedrock is real locally; everything else is a stand-in.
    aws_region: str = "us-east-1"
    aws_profile: str | None = None
    bedrock_model_id: str = "amazon.nova-micro-v1:0"

    # S3 / MinIO
    s3_endpoint_url: str | None = None  # None = real S3
    minio_root_user: str | None = None  # when set, used as the S3 credentials (MinIO)
    minio_root_password: str | None = None
    documents_bucket: str
    quarantine_prefix: str = "quarantine/"
    upload_max_bytes: int = 20 * 1024 * 1024
    upload_content_types: list[str] = ["application/pdf", "text/markdown", "text/plain"]

    # DynamoDB
    dynamodb_endpoint_url: str | None = None
    catalog_table: str

    # Kafka
    kafka_bootstrap: str = "localhost:9092"
    topic_documents: str = "documents"
    topic_documents_retry: str = "documents.retry"
    topic_documents_dlq: str = "documents.dlq"
    topic_chats: str = "chats"
    consumer_batch_size: int = 50
    retry_attempts: int = 3
    retry_backoff_seconds: list[float] = [1.0, 4.0, 16.0]

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "documents"

    # Embeddings (OpenAI-compatible /v1/embeddings)
    embeddings_url: str = "http://localhost:11434/v1"
    embedding_model: str = "all-minilm"
    embedding_dim: int = 384

    # vLLM (the stub locally) and the gateway
    vllm_url: str = "http://localhost:8081"
    gateway_url: str = "http://localhost:8000/v1"
    gateway_api_key: str = "change-me"

    # Summarizer
    summarizer_max_chars: int = 6000  # prompt budget: the first N characters of the document
    summarizer_prefer_vllm_seconds: int = 600  # hint to the gateway: wait this long for vLLM

    # Probes
    probe_port: int = 8080


@lru_cache
def get_settings() -> Settings:
    """One validated Settings per process. Call at start-up so a bad environment fails fast."""
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
