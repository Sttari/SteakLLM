import pytest
from pydantic import ValidationError

from steakllm_common.settings import Settings


def test_loads_from_environment(settings):
    assert settings.documents_bucket == "steakllm-documents"
    assert settings.kafka_bootstrap == "localhost:9092"  # a local-only default
    assert settings.retry_backoff_seconds == [1.0, 4.0, 16.0]


def test_missing_required_key_fails_fast_and_names_it(monkeypatch):
    monkeypatch.delenv("DOCUMENTS_BUCKET", raising=False)
    monkeypatch.setenv("CATALOG_TABLE", "catalog")
    with pytest.raises(ValidationError, match="documents_bucket"):
        Settings(_env_file=None)


def test_types_are_enforced(monkeypatch, settings):
    monkeypatch.setenv("EMBEDDING_DIM", "not-a-number")
    with pytest.raises(ValidationError, match="embedding_dim"):
        Settings(_env_file=None)


def test_lists_parse_from_json(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_BUCKET", "b")
    monkeypatch.setenv("CATALOG_TABLE", "t")
    monkeypatch.setenv("RETRY_BACKOFF_SECONDS", "[0.01, 0.02]")
    assert Settings(_env_file=None).retry_backoff_seconds == [0.01, 0.02]
