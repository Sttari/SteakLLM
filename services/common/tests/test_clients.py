"""Client factories on moto (S3, DynamoDB in-process) and a mocked embeddings endpoint."""

import json

import httpx
import pytest
from moto import mock_aws

from steakllm_common.clients import catalog_table, embed, s3_client


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        yield


def test_s3_round_trip_on_moto(aws, settings):
    s3 = s3_client(settings)  # no endpoint → "real" S3, which moto intercepts
    s3.create_bucket(Bucket=settings.documents_bucket)
    s3.put_object(Bucket=settings.documents_bucket, Key="quarantine/a.txt", Body=b"hi")
    assert (
        s3.get_object(Bucket=settings.documents_bucket, Key="quarantine/a.txt")["Body"].read()
        == b"hi"
    )


def test_s3_uses_minio_credentials_when_configured(monkeypatch, settings):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("MINIO_ROOT_USER", "u")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "p")
    from steakllm_common.settings import Settings

    c = s3_client(Settings(_env_file=None))
    assert c.meta.endpoint_url == "http://localhost:9000"


def test_catalog_table_round_trip_on_moto(aws, settings):
    import boto3

    boto3.resource("dynamodb", region_name=settings.aws_region).create_table(
        TableName=settings.catalog_table,
        KeySchema=[{"AttributeName": "doc_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "doc_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    t = catalog_table(settings)
    t.put_item(Item={"doc_id": "d", "status": "uploaded"})
    assert t.get_item(Key={"doc_id": "d"})["Item"]["status"] == "uploaded"


def test_embed_calls_the_openai_route_and_checks_the_size(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        payload = json.loads(request.read())
        n = len(payload["input"]) if isinstance(payload["input"], list) else 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [0.1] * settings.embedding_dim} for i in range(n)
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    vectors = embed(settings, ["a", "b"], client=client)
    assert len(vectors) == 2 and len(vectors[0]) == settings.embedding_dim


def test_embed_rejects_the_wrong_dimension(settings):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0] * 3}]})
        )
    )
    with pytest.raises(ValueError, match="EMBEDDING_DIM"):
        embed(settings, ["a"], client=client)
