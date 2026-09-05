"""tls_kwargs: nothing for PLAINTEXT; SSL with a file, or a CA fetched once from Secrets Manager."""

from __future__ import annotations

from steakllm_common.kafka import tls_kwargs
from steakllm_common.settings import Settings


def _settings(**kw) -> Settings:
    return Settings(documents_bucket="b", catalog_table="t", **kw)


def test_plaintext_adds_nothing():
    assert tls_kwargs(_settings()) == {}


def test_ssl_with_a_ca_file_passes_it_through():
    kw = tls_kwargs(_settings(kafka_security_protocol="SSL", kafka_ssl_cafile="/etc/kafka/ca.pem"))
    assert kw == {
        "security_protocol": "SSL",
        "ssl_cafile": "/etc/kafka/ca.pem",
        "ssl_check_hostname": True,
    }


def test_ssl_with_a_secret_fetches_the_ca_once(monkeypatch, tmp_path):
    calls = []

    class FakeSM:
        def get_secret_value(self, **kw):
            calls.append(kw["SecretId"])
            return {"SecretString": "-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n"}

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: FakeSM())
    monkeypatch.setattr("steakllm_common.kafka.os.path.exists", lambda p: p in seen)
    seen: set[str] = set()
    real_open = open

    def fake_open(path, mode="r", *a, **k):
        seen.add(path)
        return real_open(tmp_path / "ca.pem", mode, *a, **k)

    monkeypatch.setattr("builtins.open", fake_open)
    s = _settings(kafka_security_protocol="SSL", kafka_ca_secret_id="steakllm/kafka-ca")
    assert tls_kwargs(s)["ssl_cafile"] == "/tmp/kafka-ca.pem"
    assert tls_kwargs(s)["ssl_cafile"] == "/tmp/kafka-ca.pem"
    assert calls == ["steakllm/kafka-ca"]  # fetched once, reused on the warm path
