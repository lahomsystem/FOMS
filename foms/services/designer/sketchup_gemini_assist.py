"""SketchUp Gemini Assist — PII-free context + advisory analysis.

Plan §7. Gemini is *never* the source of truth for SketchUp candidates:
the analyzer + layout extractor + graph mapper own the DesignGraph, and
this module only attaches *advisory* hints. The contract is enforced in
three places:

  1. `build_assist_context()` — strips PII and refuses to include
     anything that wasn't already PII-free (raw SKP bytes, customer
     names, file URLs, presigned URLs, temp paths).
  2. `call_gemini_for_assist()` — calls Gemini with the PII-free
     context and validates the response against
     `foms-sketchup-assist-v1`.
  3. `attach_assist_to_candidate()` — writes the assist payload to
     `extraction.confidence_json.assist` + `snapshot.warnings_json`
     and creates a `DesignerAIRun` audit row. It NEVER touches
     `candidate.design_graph_candidate_json` or any other source of truth
     field.

Failure modes:
  - GEMINI_API_KEY missing → `GeminiAPIKeyMissing` propagates so the
    API layer can return HTTP 503 with `code='GEMINI_KEY_MISSING'`.
  - Gemini reply not schema-valid → raise `AssistSchemaInvalidError`
    *before* persisting; the candidate is left untouched.
  - Gemini transport error → raise `GeminiProviderError`; same as above.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.persistence.designer.models import (
    DesignerAIRun,
    DesignerDrawingExtraction,
    DesignerExtractionCandidate,
    DesignerSketchUpModelSnapshot,
)
from foms.services.designer.sketchup_raw_schema import (
    SchemaValidationResult,
    validate_assist_output_json,
)


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Constants — PII channels the assist context must NEVER carry
# ──────────────────────────────────────────────────────────

# Plan §7.1 explicit blocklist. These keys are looked up case-insensitively
# in any input dict and stripped from the assist payload before it leaves
# the process. A defensive guard, since by design we never put PII into
# DesignGraph in the first place — but a future caller mistake here is
# easier to catch in a single chokepoint.
PII_FIELD_NAMES = frozenset({
    # Korean
    "고객명", "고객", "이름", "전화", "전화번호", "휴대폰", "주소", "배송주소",
    # English
    "customer_name", "customer", "name", "phone", "phone_number",
    "mobile", "address", "delivery_address", "email", "contact",
    # Storage / parser internals — never useful to Gemini
    "file_url", "presigned_url", "storage_key", "temp_path",
    "raw_bytes", "skp_bytes", "skb_bytes",
})


GEMINI_ASSIST_MODEL = os.environ.get("DESIGNER_SKETCHUP_GEMINI_MODEL", "gemini-1.5-pro")
GEMINI_ASSIST_PROMPT = """\
You are FOMS-Brain, helping a Korean furniture-ERP team review a SketchUp model.

You are given:
- A pre-extracted FOMS LayoutGraph (semantic components + modules + relations).
- A summary of the candidate DesignGraph the system already produced.
- An optional component tree summary.
- Optional summaries of approved similar design cases (PII-free).

You MUST NOT:
- Speculate about customers, project names, or any personal information.
- Output a new DesignGraph or modify field values that already exist —
  only suggest, label, or flag.

Respond with a single JSON object matching the foms-sketchup-assist-v1 schema:

{
  "schema_version": "foms-sketchup-assist-v1",
  "summary": {"furniture_type": "...", "product_label_ko": "...", "confidence": 0..1},
  "missing_or_uncertain": [{"target": "component:..", "issue": "...", "suggestion": "...", "severity": "info|review|blocker"}],
  "semantic_labels": [{"component_id": "...", "suggested_role": "shelf|door|drawer|...", "confidence": 0..1, "evidence": ["..."]}],
  "layout_signature": {"module_pattern": "...", "zone_roles": ["..."], "dominant_structure": "...", "material_signature": ["..."], "hardware_signature": ["..."]},
  "learning_candidates": {"rule_hypotheses": [], "archetype_hypotheses": []},
  "review_questions": ["..."]
}

Output ONLY the JSON object. No markdown, no explanation.
"""


# ──────────────────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────────────────


class AssistSchemaInvalidError(ValueError):
    """Gemini returned a payload that does not match foms-sketchup-assist-v1."""

    def __init__(self, validation: SchemaValidationResult):
        super().__init__(validation.as_error_text())
        self.validation = validation


# ──────────────────────────────────────────────────────────
# Result envelope
# ──────────────────────────────────────────────────────────


@dataclass
class AssistResult:
    """Outcome of one assist run.

    `ai_run_id` is the audit row id (`DesignerAIRun` with
    graph_name='sketchup_gemini_assist'); the API can return it so the
    UI can link back to the raw exchange.
    """

    assist_payload: dict[str, Any]
    ai_run_id: int
    context_size_chars: int
    latency_ms: int
    model: str
    warnings_added: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────
# PII-free context builder
# ──────────────────────────────────────────────────────────


def _strip_pii(value: Any, *, path: str = "") -> Any:
    """Recursively drop any key in `PII_FIELD_NAMES` (case-insensitive).

    We drop the *key* rather than mask the value — masking can still leak
    structure ("address: <redacted>" still tells the model an address
    existed). The contract is: assist context has no PII, so the key
    should not appear at all.
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and k.lower() in PII_FIELD_NAMES:
                continue
            out[k] = _strip_pii(v, path=f"{path}.{k}")
        return out
    if isinstance(value, list):
        return [_strip_pii(item, path=f"{path}[{i}]") for i, item in enumerate(value)]
    # Strings/numbers/None pass through. We don't attempt regex PII
    # detection on free text — the LayoutGraph carries no free text by
    # design, so anything that looks like a name in the values would be
    # a layer/material/component label which is meant to be passed.
    return value


def _summarize_design_graph(design_graph: dict | None) -> dict[str, Any] | None:
    """Compact view of the candidate DesignGraph for the assist prompt.

    Sends only the shape Gemini needs to reason about — id/kind/role/
    dimensions per component, no source_node_ids, no large evidence
    lists. Keeps the token budget tight and removes any pathway through
    which a future graph addition could smuggle PII in.
    """
    if not design_graph:
        return None
    asm = design_graph.get("assembly") or {}
    components = []
    for c in design_graph.get("components") or []:
        components.append({
            "id": c.get("id"),
            "kind": c.get("kind"),
            "role": c.get("role"),
            "dimensions": c.get("dimensions"),
            "module_id": c.get("module_id"),
            "material": c.get("material"),
            "confidence": c.get("confidence"),
        })
    return {
        "schema_version": design_graph.get("schema_version"),
        "unit": design_graph.get("unit"),
        "assembly": {
            "id": asm.get("id"),
            "type": asm.get("type"),
            "dimensions": asm.get("dimensions"),
            "module_count": asm.get("module_count"),
        },
        "component_count": len(components),
        "components": components,
    }


def _summarize_layout(layout_graph: dict | None) -> dict[str, Any] | None:
    if not layout_graph:
        return None
    return {
        "schema_version": layout_graph.get("schema_version"),
        "coordinate_system": layout_graph.get("coordinate_system"),
        "overall": layout_graph.get("overall"),
        "modules": layout_graph.get("modules") or [],
        "components": layout_graph.get("components") or [],
        "relations": layout_graph.get("relations") or [],
        "unresolved_fields": layout_graph.get("unresolved_fields") or [],
        "warnings": layout_graph.get("warnings") or [],
    }


def build_assist_context(
    *,
    candidate: DesignerExtractionCandidate,
    snapshot: DesignerSketchUpModelSnapshot,
    similar_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble a PII-free prompt context.

    The output is guaranteed to:
      - exclude any key in `PII_FIELD_NAMES`,
      - exclude raw SKP/SKB bytes (never stored on candidate/snapshot —
        the caller is structurally prevented from passing them),
      - exclude file URLs / storage keys / temp paths,
      - carry only the layout, candidate summary, and a list of
        already-approved similar-case summaries.
    """
    layout = _summarize_layout(snapshot.layout_graph_json)
    design_graph_summary = _summarize_design_graph(candidate.design_graph_candidate_json)

    context: dict[str, Any] = {
        "schema_version": "foms-sketchup-assist-context-v1",
        "candidate": {
            "id": candidate.id,
            "furniture_type": candidate.furniture_type,
            "status": candidate.status,
            "confidence": candidate.confidence,
            "blocking_reasons": candidate.blocking_reasons_json or [],
            "unresolved_fields": candidate.unresolved_fields_json or [],
        },
        "layout_graph": layout,
        "design_graph_summary": design_graph_summary,
        "parse_metadata": {
            "parser_version": snapshot.parser_version,
            "sketchup_api_version": snapshot.sketchup_api_version,
            "load_status": snapshot.load_status,
        },
        "similar_cases": [
            {
                # Only fields safe for retrieval — see DesignerDesignCase
                # docstring: customer_name/phone/address are NOT stored on
                # design_cases by construction.
                "furniture_type": s.get("furniture_type"),
                "product_name": s.get("product_name"),
                "width_mm": s.get("width_mm"),
                "height_mm": s.get("height_mm"),
                "depth_mm": s.get("depth_mm"),
                "module_count": s.get("module_count"),
                "tags": s.get("tags_json") or s.get("tags") or [],
            }
            for s in (similar_cases or [])
        ],
    }
    return _strip_pii(context)


def assert_context_pii_free(context: dict) -> None:
    """Defensive check used by tests + production runtime.

    Walks the context one more time and raises if any PII key snuck
    through. The cost is negligible relative to a Gemini round-trip
    and protects against future refactors that bypass `build_assist_context`.
    """
    def walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and k.lower() in PII_FIELD_NAMES:
                    raise RuntimeError(
                        f"PII leak — key '{k}' present at {path or '(root)'}"
                    )
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
    walk(context)


# ──────────────────────────────────────────────────────────
# Gemini call
# ──────────────────────────────────────────────────────────


def call_gemini_for_assist(
    context: dict[str, Any],
    *,
    model: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Call Gemini once with the prepared context, return (payload, latency_ms).

    Raises:
        GeminiAPIKeyMissing: GEMINI_API_KEY env var unset.
        GeminiProviderError: network / parse failure.
        AssistSchemaInvalidError: Gemini reply doesn't match the schema.
    """
    # Import here so the rest of the module stays usable in environments
    # where google-genai is not installed (e.g. tests with stub mode).
    from foms.services.designer.gemini_provider import (
        GeminiProviderError,
        _get_client,
        _get_timeout_ms,
    )

    assert_context_pii_free(context)

    model_name = model or GEMINI_ASSIST_MODEL
    client = _get_client()

    try:
        from google.genai import types
    except ImportError as exc:  # pragma: no cover — covered by main provider
        raise GeminiProviderError("google-genai types not available") from exc

    body = json.dumps(context, ensure_ascii=False, sort_keys=True)
    t0 = time.monotonic()
    try:
        timeout_ms = _get_timeout_ms()
        response = client.models.generate_content(
            model=model_name,
            contents=[
                GEMINI_ASSIST_PROMPT,
                f"INPUT CONTEXT (JSON):\n{body}",
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=timeout_ms),
            ),
        )
    except Exception as exc:  # pragma: no cover — network paths
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        raise GeminiProviderError(
            f"Gemini assist call failed after {elapsed_ms}ms: {exc}"
        ) from exc

    latency_ms = int((time.monotonic() - t0) * 1000)
    raw_text = response.text or ""

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise GeminiProviderError(
            f"Gemini assist returned non-JSON ({len(raw_text)} chars): {exc.msg}"
        ) from exc

    validation = validate_assist_output_json(payload)
    if not validation.is_valid:
        raise AssistSchemaInvalidError(validation)

    return payload, latency_ms


# ──────────────────────────────────────────────────────────
# Persistence — suggestion only, never overwrite source of truth
# ──────────────────────────────────────────────────────────


def attach_assist_to_candidate(
    *,
    candidate: DesignerExtractionCandidate,
    snapshot: DesignerSketchUpModelSnapshot,
    assist_payload: dict[str, Any],
    context: dict[str, Any],
    latency_ms: int,
    model: str,
    user_id: int | None = None,
) -> AssistResult:
    """Persist assist output as suggestion-only (plan §7.3).

    Writes:
      - extraction.confidence_json["assist"] = payload + audit metadata
      - snapshot.warnings_json appends "assist_<severity>:<target>" rows
        from `missing_or_uncertain` so the review banner can surface
        them inline.
      - DesignerAIRun(graph_name='sketchup_gemini_assist') with the
        PII-free context as input_json and the assist payload as
        output_json (this is the audit trail for replay).

    Never touches:
      - candidate.design_graph_candidate_json (source of truth)
      - candidate.status / approved / preview_allowed
      - any DesignerDesignCase row
    """
    extraction = candidate.extraction
    if extraction is None:
        raise RuntimeError(f"candidate {candidate.id} has no extraction row")

    # Confidence JSON merge — keep prior keys intact.
    conf = copy.deepcopy(extraction.confidence_json or {})
    conf["assist"] = {
        "schema_version": assist_payload.get("schema_version"),
        "summary": assist_payload.get("summary"),
        "missing_or_uncertain": assist_payload.get("missing_or_uncertain") or [],
        "semantic_labels": assist_payload.get("semantic_labels") or [],
        "layout_signature": assist_payload.get("layout_signature"),
        "review_questions": assist_payload.get("review_questions") or [],
        "model": model,
        "latency_ms": latency_ms,
    }
    extraction.confidence_json = conf
    flag_modified(extraction, "confidence_json")

    # Warnings — append a flat tag per missing_or_uncertain entry so the
    # review UI banner can pick them up without learning the assist shape.
    warnings_added: list[str] = []
    snap_warnings = list(snapshot.warnings_json or [])
    for entry in assist_payload.get("missing_or_uncertain") or []:
        severity = entry.get("severity") or "review"
        target = entry.get("target") or "?"
        tag = f"assist_{severity}:{target}"
        snap_warnings.append(tag)
        warnings_added.append(tag)
    snapshot.warnings_json = snap_warnings
    flag_modified(snapshot, "warnings_json")

    # AI run audit — the raw exchange. thread_id ties multiple assist
    # passes to the same candidate (we use candidate id as the thread).
    ai_run = DesignerAIRun(
        graph_name="sketchup_gemini_assist",
        graph_version="b8-0.1.0",
        thread_id=f"sketchup_candidate_{candidate.id}",
        status="succeeded",
        input_json={
            "candidate_id": candidate.id,
            "snapshot_id": snapshot.id,
            "context": context,
        },
        state_json={"phase": "assist_done", "model": model, "latency_ms": latency_ms},
        output_json=assist_payload,
        created_by_user_id=user_id,
    )
    db_session.add(ai_run)

    db_session.commit()
    db_session.refresh(ai_run)
    db_session.refresh(extraction)
    db_session.refresh(snapshot)
    db_session.refresh(candidate)

    logger.info(
        "[SKETCHUP] assist attached candidate=%d snapshot=%d ai_run=%d warnings=%d latency_ms=%d",
        candidate.id, snapshot.id, ai_run.id, len(warnings_added), latency_ms,
    )

    return AssistResult(
        assist_payload=assist_payload,
        ai_run_id=ai_run.id,
        context_size_chars=len(json.dumps(context, ensure_ascii=False)),
        latency_ms=latency_ms,
        model=model,
        warnings_added=warnings_added,
    )


__all__ = [
    "ASSIST_SCHEMA_ID",  # re-export for callers (alias of sketchup_raw_schema)
    "PII_FIELD_NAMES",
    "GEMINI_ASSIST_MODEL",
    "AssistResult",
    "AssistSchemaInvalidError",
    "assert_context_pii_free",
    "attach_assist_to_candidate",
    "build_assist_context",
    "call_gemini_for_assist",
]


# Re-export so callers don't need to import from two modules.
from foms.services.designer.sketchup_raw_schema import ASSIST_SCHEMA_ID  # noqa: E402
