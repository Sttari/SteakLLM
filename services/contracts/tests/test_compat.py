"""v1 is frozen: live schemas must still satisfy every reader written against the golden file."""

import copy
import json
import pathlib

from steakllm_contracts.compat import breaking_changes, fingerprints

GOLDEN = pathlib.Path(__file__).parent / "golden" / "v1.json"

BREAKING = (
    "\n\nThis is a breaking change to contract v1. Do not edit v1: create <Event>.v2.schema.json"
    " and let readers opt in. (If the change is additive and intentional, regenerate the golden"
    " file in its own reviewed commit: uv run python tests/golden/regenerate.py)"
)


def golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_live_schemas_are_compatible_with_golden_v1():
    problems = breaking_changes(golden(), fingerprints())
    assert not problems, "\n".join(problems) + BREAKING


def test_golden_covers_every_schema():
    assert set(golden()) == set(fingerprints())


# The checker itself, exercised on mutated copies so its verdicts are trusted.


def test_checker_allows_additive_changes():
    live = copy.deepcopy(fingerprints())
    live["SummaryReady"]["data_properties"]["new_optional"] = {"type": "string"}
    live["SummaryReady"]["data_properties"]["backend"]["enum"].append("openai")
    live["Brand.New.Event"] = {"type": "BrandNew"}
    assert breaking_changes(golden(), live) == []


def test_checker_catches_removed_required_field():
    live = copy.deepcopy(fingerprints())
    live["DocumentUploaded"]["data_required"].remove("sha256")
    del live["DocumentUploaded"]["data_properties"]["sha256"]
    problems = breaking_changes(golden(), live)
    assert any("'sha256' is no longer required" in p for p in problems)
    assert any("field 'sha256' removed" in p for p in problems)


def test_checker_catches_retype_and_lost_enum_value():
    live = copy.deepcopy(fingerprints())
    live["ChatCompleted"]["data_properties"]["latency_ms"]["type"] = "string"
    live["SummaryReady"]["data_properties"]["backend"]["enum"].remove("bedrock")
    problems = breaking_changes(golden(), live)
    assert any("latency_ms.type changed 'integer' -> 'string'" in p for p in problems)
    assert any("backend lost enum value 'bedrock'" in p for p in problems)
