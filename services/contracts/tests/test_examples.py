"""Every example validates against its schema; broken ones fail with a pointed message."""

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from steakllm_contracts import EVENT_TYPES, EXAMPLE_DIR
from steakllm_contracts.validate import ValidationError, errors, load_schema, validate


def example(name: str) -> dict:
    return json.loads((EXAMPLE_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["envelope", *EVENT_TYPES])
def test_schema_itself_is_valid_2020_12(name):
    Draft202012Validator.check_schema(load_schema(name))


@pytest.mark.parametrize("name", EVENT_TYPES)
def test_example_validates_against_its_schema_and_the_envelope(name):
    ev = example(name)
    assert errors(ev) == []  # by ev["type"]
    assert errors(ev, "envelope") == []


@pytest.mark.parametrize("name", EVENT_TYPES)
def test_example_rejected_by_every_other_schema(name):
    ev = example(name)
    for other in EVENT_TYPES:
        if other != name:
            assert errors(ev, other), f"{name} example wrongly accepted as {other}"


def test_uploaded_sha256_equals_doc_id():
    ev = example("DocumentUploaded")
    assert ev["data"]["sha256"] == ev["doc_id"]


def test_missing_required_body_field_is_named():
    ev = copy.deepcopy(example("DocumentUploaded"))
    del ev["data"]["sha256"]
    with pytest.raises(ValidationError, match="sha256"):
        validate(ev)


def test_unknown_backend_is_rejected():
    ev = copy.deepcopy(example("SummaryReady"))
    ev["data"]["backend"] = "openai"
    assert any("backend" in e for e in errors(ev))


def test_wrong_source_is_rejected():
    ev = copy.deepcopy(example("SummaryReady"))
    ev["source"] = "ingest"  # ingest may not write summaries
    assert any(e.startswith("source") for e in errors(ev))


def test_unknown_extra_field_is_tolerated():
    ev = copy.deepcopy(example("DocumentIndexed"))
    ev["data"]["added_in_v1_later"] = "still valid for old readers"
    assert errors(ev) == []
