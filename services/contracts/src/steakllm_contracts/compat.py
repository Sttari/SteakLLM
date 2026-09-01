"""What a v1 reader relies on, reduced to a comparable fingerprint.

The compatibility test (tests/test_compat.py) compares the live schemas' fingerprints against the
golden snapshot in tests/golden/v1.json. Anything a reader depends on that changes or disappears
is a breaking change and belongs in a v2 file, not in an edit to v1.
"""

from __future__ import annotations

from typing import Any

from . import EVENT_TYPES
from .validate import load_schema

_FACTS = ("type", "const", "enum", "pattern", "minimum", "minLength", "maxLength", "maxItems")


def _props(props: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, spec in sorted(props.items()):
        facts = {k: spec[k] for k in _FACTS if k in spec}
        if "items" in spec and isinstance(spec["items"], dict):
            facts["items"] = {k: spec["items"][k] for k in _FACTS if k in spec["items"]}
        out[name] = facts
    return out


def fingerprint(name: str) -> dict[str, Any]:
    """The reader-relevant facts of ``<name>.v1``: required fields and each field's constraints."""
    s = load_schema(name)
    if name == "envelope":
        return {"required": sorted(s["required"]), "properties": _props(s["properties"])}
    data = s["properties"]["data"]
    return {
        "type": s["properties"]["type"]["const"],
        "source": sorted(s["properties"]["source"]["enum"]),
        "data_required": sorted(data.get("required", [])),
        "data_properties": _props(data["properties"]),
    }


def fingerprints() -> dict[str, dict[str, Any]]:
    return {name: fingerprint(name) for name in ("envelope", *EVENT_TYPES)}


def breaking_changes(golden: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """Every way ``live`` would break a reader written against ``golden``. Empty means compatible.

    Allowed (additive): new schemas, new optional fields, new enum values, a looser pattern is NOT
    checked (patterns must match exactly). Forbidden: removing a schema, a required field, or any
    field; changing a type, const or pattern; removing an enum value; tightening a bound.
    """
    problems: list[str] = []
    for schema, g in golden.items():
        if schema not in live:
            problems.append(f"{schema}: schema removed")
            continue
        lv = live[schema]
        for key in ("required", "data_required"):
            missing = set(g.get(key, [])) - set(lv.get(key, []))
            for f in sorted(missing):
                problems.append(f"{schema}: required field {f!r} is no longer required")
        for key in ("type",):
            if key in g and g[key] != lv.get(key):
                problems.append(f"{schema}: {key} changed {g[key]!r} -> {lv.get(key)!r}")
        if "source" in g:
            for v in sorted(set(g["source"]) - set(lv.get("source", []))):
                problems.append(f"{schema}: source {v!r} may no longer write this event")
        for key in ("properties", "data_properties"):
            for field, gf in g.get(key, {}).items():
                lf = lv.get(key, {}).get(field)
                if lf is None:
                    problems.append(f"{schema}: field {field!r} removed")
                    continue
                for fact in ("type", "const", "pattern"):
                    if fact in gf and gf[fact] != lf.get(fact):
                        problems.append(
                            f"{schema}: {field}.{fact} changed {gf[fact]!r} -> {lf.get(fact)!r}"
                        )
                if "enum" in gf:
                    for v in sorted(set(gf["enum"]) - set(lf.get("enum", []))):
                        problems.append(f"{schema}: {field} lost enum value {v!r}")
                for bound, tighter in (
                    ("minimum", 1),
                    ("minLength", 1),
                    ("maxLength", -1),
                    ("maxItems", -1),
                ):
                    if bound in gf and bound in lf and (lf[bound] - gf[bound]) * tighter > 0:
                        problems.append(
                            f"{schema}: {field}.{bound} tightened {gf[bound]} -> {lf[bound]}"
                        )
    return problems
