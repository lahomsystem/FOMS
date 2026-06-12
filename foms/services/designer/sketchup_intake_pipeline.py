"""SketchUp intake pipeline — analyzer result → DB rows.

Plan §4.1 / §B3 / §B5. The pipeline is invoked by the parser worker
once `sketchup_worker_client.run_analyzer()` has returned a validated
`AnalyzerRunResult`. It persists, in one transaction:

  1. `DesignerSketchUpModelSnapshot` — immutable parse-time evidence.
  2. Synthetic `DesignerDrawingPage` so SketchUp uploads can rejoin the
     existing extraction/candidate review surface (plan §4.1).
  3. `DesignerDrawingExtraction` carrying the layout_json placeholder
     and a drawing-extraction-compatible `parsed_json` so the existing
     review UI can key off the same shape (plan §B5).
  4. `DesignerExtractionCandidate` in `pending_review` with
     `preview_allowed=False` until B6 mapper fills the design graph.

Defense in depth — schema validation:
- Workers call `sketchup_worker_client.run_analyzer()` which already
  validates the analyzer output before calling us. We re-validate at
  pipeline entry so any *other* caller (B5 integration tests, future
  retry tools, manual ops scripts) cannot insert malformed payloads.
- A schema violation raises `SchemaInvalidPayloadError` — the
  transaction has not started yet, so the caller is guaranteed there is
  no partial DB write to clean up (plan §B5 acceptance: "schema invalid
  output is job failed and leaves no DB partial success").
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.persistence.designer.models import (
    DesignerDrawingArtifact,
    DesignerDrawingExtraction,
    DesignerDrawingPage,
    DesignerExtractionCandidate,
    DesignerSketchUpModelSnapshot,
    DesignerSketchUpParseJob,
)
from foms.services.designer.sketchup_graph_mapper import (
    map_sketchup_layout_to_design_graph,
)
from foms.services.designer.sketchup_layout_extractor import (
    extract_layout_graph,
)
from foms.services.designer.sketchup_raw_schema import (
    SchemaValidationResult,
    validate_layout_graph_json,
    validate_raw_model_json,
)


logger = logging.getLogger(__name__)


EXTRACTOR_VERSION_BY_WORKER_KIND = {
    "c_api": "sketchup-capi-v1",
    "desktop_ruby": "sketchup-ruby-v1",
    "fake_contract": "sketchup-fake-v1",
}

# Historical placeholder reasons surfaced by the pre-B6 stub pipeline.
# Kept as constants so existing tests / callers that grep for them
# continue to compile, but real blockers now come from
# `LayoutExtractionResult.blocking_reasons` + `_validate_design_graph`.
LAYOUT_PENDING_REASON = "layout_extractor_not_implemented_b6"
MAPPER_PENDING_REASON = "design_graph_mapper_not_implemented_b6"


class SchemaInvalidPayloadError(ValueError):
    """Raised when the analyzer payload fails schema validation at pipeline entry.

    Carries the validation result so the worker can log the exact
    jsonschema errors that triggered the rejection. No DB write has
    occurred when this is raised.
    """

    def __init__(self, validation: SchemaValidationResult):
        super().__init__(validation.as_error_text())
        self.validation = validation


@dataclass
class IntakeResult:
    snapshot_id: int
    page_id: int
    extraction_id: int
    candidate_id: int
    extractor_version: str
    warnings: list[str]


def _extractor_version(worker_kind: str) -> str:
    return EXTRACTOR_VERSION_BY_WORKER_KIND.get(worker_kind, "sketchup-unknown-v1")


def _bbox_size_mm(raw: dict) -> dict[str, float]:
    """Pull (width, height, depth) in mm from the raw model bbox.

    SketchUp internally stores in inches; the analyzer is required to
    pre-convert (plan §6.3) so we just read the `size` field. If the
    analyzer didn't include `size`, derive it from `max - min` as a
    defensive fallback.
    """
    model = raw.get("model") or {}
    bbox = model.get("bbox_mm") or {}
    size = bbox.get("size")
    if size:
        return {
            "width_mm": float(size.get("width") or 0),
            "height_mm": float(size.get("height") or 0),
            "depth_mm": float(size.get("depth") or 0),
        }
    mn = bbox.get("min") or {}
    mx = bbox.get("max") or {}
    return {
        "width_mm": float((mx.get("x") or 0) - (mn.get("x") or 0)),
        "height_mm": float((mx.get("z") or 0) - (mn.get("z") or 0)),
        "depth_mm": float((mx.get("y") or 0) - (mn.get("y") or 0)),
    }


def _module_widths_hint(raw: dict) -> list[float]:
    """Best-effort module width hint from top-level group nodes.

    Until B6 lands a real layout extractor we cannot say which nodes are
    truly "modules". As a stop-gap we surface the width of every visible
    top-level `group` node so the existing review UI's `module_widths_mm`
    column has *something* useful to display. Ambiguous and explicitly
    marked as such via warnings — never trusted by the approval gate.
    """
    widths: list[float] = []
    for node in raw.get("nodes") or []:
        if node.get("kind") != "group":
            continue
        if node.get("parent_id") is not None:
            continue
        bbox = node.get("bbox_mm") or {}
        size = bbox.get("size") or {}
        w = size.get("width")
        if w is None:
            mn = bbox.get("min") or {}
            mx = bbox.get("max") or {}
            w = (mx.get("x") or 0) - (mn.get("x") or 0)
        if w:
            widths.append(round(float(w), 2))
    return widths


def _build_layout_graph(raw: dict, *, source_artifact_id: int):
    """Run the B6 layout extractor and return its result.

    Returns the full `LayoutExtractionResult` so the caller can lift
    `blocking_reasons` / `unresolved_fields` / `warnings` onto the
    candidate row without reparsing the embedded layout dict.
    """
    return extract_layout_graph(raw, source_artifact_id=source_artifact_id)


def _build_parsed_json(raw: dict, *, layout: dict, snapshot_warnings: list[str]) -> dict[str, Any]:
    """Drawing-extraction-compatible summary (plan §B5).

    Mirrors the key set produced by `drawing_intake_pipeline.run_intake_pipeline()`
    so the existing review UI / fixture tooling can read SketchUp
    extractions without learning a second shape. Fields that don't make
    sense for SketchUp source are returned empty (e.g. `parts_table`,
    `customer_info`) — never null, never silently fabricated.
    """
    bbox = layout["overall"]["bbox_mm"]
    module_widths = _module_widths_hint(raw)
    materials = raw.get("materials") or []
    return {
        "source_kind": "sketchup_model",
        "furniture_type": "unknown",
        "site_size": {
            "width_mm": bbox["width_mm"],
            "height_mm": bbox["height_mm"],
            "depth_mm": bbox["depth_mm"],
        },
        "module_widths_mm": module_widths,
        "extracted_params": {
            "width": bbox["width_mm"] or None,
            "height": bbox["height_mm"] or None,
            "depth": bbox["depth_mm"] or None,
        },
        # PII channels stay empty — SketchUp uploads do not carry
        # customer text. Keep the keys present so consumers can do a
        # uniform `.get(...)`.
        "parts_table": [],
        "customer_info": {},
        "drawing_meta": {
            "parser": (raw.get("parser") or {}).get("kind"),
            "parser_version": (raw.get("parser") or {}).get("version"),
            "file_sha256": (raw.get("file") or {}).get("sha256"),
            "load_status": (raw.get("file") or {}).get("load_status"),
            "skb_policy": (raw.get("file") or {}).get("skb_policy"),
        },
        "design_understanding": {
            "node_count": len(raw.get("nodes") or []),
            "definition_count": len(raw.get("definitions") or []),
            "material_count": len(materials),
            "material_names": [m.get("name") for m in materials if m.get("name")],
        },
        "unresolved_fields": [LAYOUT_PENDING_REASON],
        "confidence": 0.0,
        "warnings": snapshot_warnings,
    }


def _component_index(raw: dict) -> dict[str, Any]:
    nodes = raw.get("nodes") or []
    by_definition: dict[str, list[str]] = {}
    by_layer: dict[str, list[str]] = {}
    for n in nodes:
        defn = n.get("definition_id")
        if defn:
            by_definition.setdefault(defn, []).append(n["node_id"])
        layer = n.get("layer")
        if layer:
            by_layer.setdefault(layer, []).append(n["node_id"])
    return {
        "by_definition_id": by_definition,
        "by_layer": by_layer,
        "total_nodes": len(nodes),
    }


def _material_index(raw: dict) -> dict[str, Any]:
    materials = raw.get("materials") or []
    return {
        "by_id": {m["material_id"]: m for m in materials if "material_id" in m},
        "count": len(materials),
    }


def store_analyzer_result(
    *,
    job: DesignerSketchUpParseJob,
    raw_model_json: dict,
    preview_assets_json: dict | None = None,
    metrics: dict | None = None,
    skip_validation: bool = False,
) -> IntakeResult:
    """Persist analyzer output for one parse job.

    Contract:
    - Caller has already locked the job's lease — this function does
      NOT mutate job status. The worker flips to succeeded/failed via
      `finish_sketchup_job` after this returns. Splitting those
      responsibilities keeps lease ownership checks in the repository
      helper.
    - `raw_model_json` is revalidated against `foms-sketchup-raw-v1`
      unless `skip_validation=True` (worker already validated). On
      schema failure raises `SchemaInvalidPayloadError` *before* any DB
      write, so the caller is guaranteed no partial rows.
    - Rolls back on any other exception. The worker maps it to
      `error_code='INTAKE_PIPELINE_FAILED'`.
    """
    if not skip_validation:
        validation = validate_raw_model_json(raw_model_json)
        if not validation.is_valid:
            logger.warning(
                "[SKETCHUP] intake rejected job=%d schema_invalid errors=%d",
                job.id, len(validation.errors),
            )
            raise SchemaInvalidPayloadError(validation)

    artifact = db_session.get(DesignerDrawingArtifact, job.artifact_id)
    if artifact is None:
        raise RuntimeError(
            f"artifact {job.artifact_id} disappeared while running intake pipeline"
        )

    extractor_version = _extractor_version(job.worker_kind or "")

    layout_result = _build_layout_graph(
        raw_model_json,
        source_artifact_id=artifact.id,
    )
    layout_json = layout_result.layout_graph

    snapshot_warnings = list(raw_model_json.get("warnings") or [])
    parsed_json = _build_parsed_json(
        raw_model_json,
        layout=layout_json,
        snapshot_warnings=[
            w if isinstance(w, str) else (w.get("code") if isinstance(w, dict) else str(w))
            for w in snapshot_warnings
        ],
    )

    raw_copy = copy.deepcopy(raw_model_json)
    model = raw_copy.get("model") or {}

    try:
        # 1) Synthetic Page — keeps the review API uniform with PDF/image flow.
        page = DesignerDrawingPage(
            artifact_id=artifact.id,
            page_no=1,
            image_url=None,
            template_key="sketchup_model",
            rotation_deg=0,
        )
        db_session.add(page)
        db_session.flush()

        # 2) Extraction row — carries layout + parser metrics.
        extraction = DesignerDrawingExtraction(
            page_id=page.id,
            extractor_version=extractor_version,
            raw_ocr_json=None,
            layout_json=layout_json,
            parsed_json=parsed_json,
            confidence_json={
                "extraction_confidence": parsed_json.get("confidence", 0.0),
                "blocking_reasons": list(layout_result.blocking_reasons),
                "metrics": metrics or {},
            },
            status="draft",
            model_name=(raw_copy.get("parser") or {}).get("version"),
        )
        db_session.add(extraction)
        db_session.flush()

        # 3) Snapshot — immutable evidence.
        snapshot = DesignerSketchUpModelSnapshot(
            artifact_id=artifact.id,
            parse_job_id=job.id,
            extraction_id=extraction.id,
            parser_version=job.parser_version,
            sketchup_api_version=(raw_copy.get("parser") or {}).get("sketchup_api_version"),
            sketchup_model_version=None,
            load_status=(raw_copy.get("file") or {}).get("load_status"),
            units_json={
                "internal_unit": model.get("internal_unit"),
                "unit_scale_to_mm": model.get("unit_scale_to_mm"),
            },
            bbox_json=model.get("bbox_mm") or {},
            raw_model_json=raw_copy,
            layout_graph_json=layout_json,
            component_index_json=_component_index(raw_copy),
            material_index_json=_material_index(raw_copy),
            preview_assets_json=preview_assets_json,
            warnings_json=snapshot_warnings,
        )
        db_session.add(snapshot)
        db_session.flush()

        # 4) Run the B6 graph mapper *after* extraction.id exists so the
        # DesignGraph carries `source_extraction_id` for retrieval.
        mapping_result = map_sketchup_layout_to_design_graph(
            layout_json,
            source_extraction_id=extraction.id,
            upstream_blocking_reasons=layout_result.blocking_reasons,
        )

        candidate = DesignerExtractionCandidate(
            extraction_id=extraction.id,
            furniture_type=(layout_json.get("overall") or {}).get("furniture_type") or "unknown",
            extracted_params_json={
                "source_kind": "sketchup_model",
                "snapshot_id": snapshot.id,
                "bbox_mm": layout_json["overall"]["bbox_mm"],
                "module_count": len(layout_json.get("modules") or []),
                "component_count": len(layout_json.get("components") or []),
            },
            unresolved_fields_json=list(layout_result.unresolved_fields),
            confidence=mapping_result.confidence,
            status="pending_review",
            blocking_reasons_json=list(mapping_result.approval_blocking_reasons),
            preview_allowed=mapping_result.preview_allowed,
            design_graph_candidate_json=mapping_result.design_graph,
            mapping_report_json={
                "source_kind": "sketchup_model",
                "warnings": list(mapping_result.warnings),
                "unresolved_fields": list(mapping_result.unresolved_fields),
                "approval_blocking_reasons": list(mapping_result.approval_blocking_reasons),
                "mapper": "sketchup_graph_mapper_b6",
                "component_count": len(mapping_result.design_graph.get("components") or []),
            },
            validation_json={
                "valid": not mapping_result.approval_blocking_reasons,
                "errors": list(mapping_result.approval_blocking_reasons),
            },
        )
        db_session.add(candidate)
        for attr in (
            "extracted_params_json",
            "unresolved_fields_json",
            "blocking_reasons_json",
            "design_graph_candidate_json",
            "mapping_report_json",
            "validation_json",
        ):
            flag_modified(candidate, attr)
        db_session.flush()

        # Artifact moves to "parsed, awaiting review".
        artifact.status = "done"
        db_session.commit()
    except SchemaInvalidPayloadError:
        # Schema validation happens before any DB write; if a downstream
        # placeholder build still raises this (defensive), make sure we
        # never leak a partial transaction.
        db_session.rollback()
        raise
    except Exception:
        db_session.rollback()
        raise

    logger.info(
        "[SKETCHUP] intake artifact=%d job=%d snapshot=%d extraction=%d candidate=%d",
        artifact.id, job.id, snapshot.id, extraction.id, candidate.id,
    )

    return IntakeResult(
        snapshot_id=snapshot.id,
        page_id=page.id,
        extraction_id=extraction.id,
        candidate_id=candidate.id,
        extractor_version=extractor_version,
        warnings=list(layout_json["warnings"]),
    )


__all__ = [
    "EXTRACTOR_VERSION_BY_WORKER_KIND",
    "LAYOUT_PENDING_REASON",
    "MAPPER_PENDING_REASON",
    "IntakeResult",
    "SchemaInvalidPayloadError",
    "store_analyzer_result",
]
