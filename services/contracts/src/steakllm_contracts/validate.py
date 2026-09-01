"""Validate events against the contracts. Every service validates the same way, through here."""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from . import SCHEMA_DIR

__all__ = ["ValidationError", "errors", "load_schema", "validate", "validator_for"]


def load_schema(name: str) -> dict[str, Any]:
    """Load ``<name>.v1.schema.json`` from the package, e.g. ``"envelope"``."""
    return json.loads((SCHEMA_DIR / f"{name}.v1.schema.json").read_text(encoding="utf-8"))


@cache
def _registry() -> Registry:
    """All schemas, addressable by their ``$id``, so one schema can ``$ref`` another."""
    resources = []
    for path in SCHEMA_DIR.iterdir():
        if path.name.endswith(".schema.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


@cache
def validator_for(name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(name), registry=_registry())


def errors(event: dict[str, Any], name: str | None = None) -> list[str]:
    """Human-readable problems, empty when valid. ``name`` defaults to the event's ``type``."""
    name = name or event.get("type", "envelope")
    found = []
    for err in sorted(validator_for(name).iter_errors(event), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        found.append(f"{where}: {err.message}")
    return found


def validate(event: dict[str, Any], name: str | None = None) -> None:
    """Raise ``ValidationError`` listing every problem; return None when valid."""
    problems = errors(event, name)
    if problems:
        raise ValidationError("\n".join(problems))
