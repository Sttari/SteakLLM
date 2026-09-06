"""resolve_bootstrap: the setting in-cluster; outside, the NLB found by the controller tag."""

from __future__ import annotations

import pytest

from steakllm_common.kafka import resolve_bootstrap
from steakllm_common.settings import Settings


def _settings(**kw) -> Settings:
    return Settings(documents_bucket="b", catalog_table="t", **kw)


class FakeElb:
    def __init__(self, lbs):
        self.lbs = lbs

    def get_paginator(self, name):
        lbs = self.lbs

        class P:
            def paginate(self):
                yield {"LoadBalancers": [{"LoadBalancerArn": a, "DNSName": d} for a, d, _ in lbs]}

        return P()

    def describe_tags(self, ResourceArns):  # noqa: N803 — boto3's naming
        return {
            "TagDescriptions": [
                {"ResourceArn": a, "Tags": [{"Key": "service.k8s.aws/stack", "Value": t}]}
                for a, _, t in self.lbs
                if a in ResourceArns
            ]
        }


def test_without_a_tag_the_setting_is_returned():
    assert resolve_bootstrap(_settings(kafka_bootstrap="kafka:9092")) == "kafka:9092"


def test_with_a_tag_the_matching_nlb_is_found(monkeypatch):
    import boto3

    monkeypatch.setattr(
        boto3,
        "client",
        lambda *a, **k: FakeElb(
            [
                ("arn:1", "one.elb", "kafka/other"),
                ("arn:2", "door.elb", "kafka/steakllm-kafka-lambda-bootstrap"),
            ]
        ),
    )
    s = _settings(
        kafka_bootstrap="placeholder:9094",
        kafka_bootstrap_lookup_tag="kafka/steakllm-kafka-lambda-bootstrap",
    )
    assert resolve_bootstrap(s) == "door.elb:9094"


def test_no_match_is_an_error(monkeypatch):
    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: FakeElb([]))
    with pytest.raises(RuntimeError):
        resolve_bootstrap(_settings(kafka_bootstrap_lookup_tag="kafka/none"))
