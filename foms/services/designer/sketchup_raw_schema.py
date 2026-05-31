"""SketchUp Raw / Layout JSON schema validation surface.

Wraps `jsonschema` so service callers get a small, typed error envelope
instead of raw `ValidationError` objects bubbling up. The intake pipeline
calls `validate_raw_model_json()` *before* inserting a snapshot so a
schema violation can never produce a partial DB row (plan §B5 Stop Rule).

Schema files live under `tools/sketchup_analyzer/schema/`. The same
schemas are bundled with `sketchup_analyzer.exe` so the C++ side can
self-validate during development.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator


SCHEMA_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tools"
    / "sketchup_analyzer"
    / "schema"
)

RAW_SCHEMA_ID = "foms-sketchup-raw-v1"
LAYOUT_SCHEMA_ID = "foms-sketchup-layout-v1"
ASSIST_SCHEMA_ID = "foms-sketchup-assist-v1"


@dataclass
class SchemaValidationResult:
    """Outcome of validating one analyzer payload.

    `errors` contains the full ordered list of jsonschema errors (path +
    message). `is_valid` is the only signal callers should branch on —
    the structured `errors` is for logs and the worker-side `error_text`
    column.
    """

    schema_id: str
    is_valid: bool
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_error_text(self, *, limit: int = 5) -> str:
        head = self.errors[:limit]
        more = max(0, len(self.errors) - limit)
        lines = [f"  - {e['path']}: {e['message']}" for e in head]
        if more:
            lines.append(f"  - ... (+{more} more)")
        return f"{self.schema_id} validation failed\n" + "\n".join(lines)


@lru_cache(maxsize=4)
def _load_schema(schema_id: str) -> dict[str, Any]:
    path = SCHEMA_DIR / f"{schema_id}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"missing schema file: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=4)
def _validator_for(schema_id: str) -> Draft202012Validator:
    schema = _load_schema(schema_id)
    # Draft 2020-12 matches the `$schema` field in our JSON files.
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _format_path(path: Any) -> str:
    parts: list[str] = []
    for item in path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}" if parts else str(item))
    return "".join(parts) or "(root)"


def validate_payload(payload: dict, schema_id: str) -> SchemaValidationResult:
    """Validate `payload` against the named schema.

    Returns a SchemaValidationResult — never raises on validation
    failures; the caller decides whether to abort the job. A missing
    schema file *does* raise (it's a deployment bug, not a data bug).
    """
    validator = _validator_for(schema_id)
    errors: list[dict[str, Any]] = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path)):
        errors.append(
            {
                "path": _format_path(err.absolute_path),
                "message": err.message,
                "validator": err.validator,
            }
        )
    return SchemaValidationResult(
        schema_id=schema_id,
        is_valid=not errors,
        errors=errors,
    )


def validate_raw_model_json(payload: dict) -> SchemaValidationResult:
    return validate_payload(payload, RAW_SCHEMA_ID)


def validate_layout_graph_json(payload: dict) -> SchemaValidationResult:
    return validate_payload(payload, LAYOUT_SCHEMA_ID)


def validate_assist_output_json(payload: dict) -> SchemaValidationResult:
    return validate_payload(payload, ASSIST_SCHEMA_ID)


__all__ = [
    "RAW_SCHEMA_ID",
    "LAYOUT_SCHEMA_ID",
    "ASSIST_SCHEMA_ID",
    "SchemaValidationResult",
    "validate_payload",
    "validate_raw_model_json",
    "validate_layout_graph_json",
    "validate_assist_output_json",
]
