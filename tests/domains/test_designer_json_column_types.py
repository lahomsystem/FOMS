"""Designer JSON columns must declare the column type production actually has.

SQLAlchemy never turns ``JSON`` into ``jsonb`` on its own. Until 2026-09-29 every designer
column was plain ``JSON`` while 13 of them are ``jsonb`` in production (their migrations used
JSONB). With psycopg the bound value carries the declared type (``'...'::json``), so writes
still worked through the json→jsonb assignment cast but any ``column = :value`` comparison
would fail with ``operator does not exist: jsonb = json``.

The snapshot below is the production schema read on 2026-09-29 (``information_schema.columns``,
read-only). A new designer JSON column must be added here with its real production type.
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import JSON

import foms.persistence.designer.models as designer_models

_PRODUCTION_JSONB = frozenset({
    ("designer_ai_runs", "input_json"),
    ("designer_ai_runs", "output_json"),
    ("designer_ai_runs", "state_json"),
    ("designer_corrections", "after_json"),
    ("designer_corrections", "before_json"),
    ("designer_embeddings", "metadata_json"),
    ("designer_ontology_versions", "rules_json"),
    ("designer_project_versions", "bom_json"),
    ("designer_project_versions", "design_json"),
    ("designer_project_versions", "validation_json"),
    ("designer_rule_candidates", "candidate_json"),
    ("designer_rule_candidates", "replay_report_json"),
    ("designer_rule_candidates", "source_correction_ids"),
})

_PRODUCTION_JSON = frozenset({
    ("designer_block_ontology_relations", "evidence_case_ids_json"),
    ("designer_block_ontology_relations", "params_json"),
    ("designer_block_ontology_relations", "replay_report_json"),
    ("designer_design_cases", "bom_json"),
    ("designer_design_cases", "design_graph_json"),
    ("designer_design_cases", "internal_structure_json"),
    ("designer_design_cases", "options_json"),
    ("designer_design_cases", "tags_json"),
    ("designer_drawing_extractions", "confidence_json"),
    ("designer_drawing_extractions", "layout_json"),
    ("designer_drawing_extractions", "parsed_json"),
    ("designer_drawing_extractions", "raw_ocr_json"),
    ("designer_drawing_extractions", "redaction_report_json"),
    ("designer_drawing_extractions", "routing_json"),
    ("designer_extraction_candidates", "blocking_reasons_json"),
    ("designer_extraction_candidates", "design_graph_candidate_json"),
    ("designer_extraction_candidates", "extracted_params_json"),
    ("designer_extraction_candidates", "mapping_report_json"),
    ("designer_extraction_candidates", "unresolved_fields_json"),
    ("designer_extraction_candidates", "validation_json"),
    ("designer_outline_polygons", "vertices_mm_json"),
    ("designer_reusable_blocks", "geometry_json"),
    ("designer_reusable_blocks", "parameters_json"),
    ("designer_reusable_blocks", "tags_json"),
    ("designer_sketchup_model_snapshots", "bbox_json"),
    ("designer_sketchup_model_snapshots", "component_index_json"),
    ("designer_sketchup_model_snapshots", "layout_graph_json"),
    ("designer_sketchup_model_snapshots", "material_index_json"),
    ("designer_sketchup_model_snapshots", "preview_assets_json"),
    ("designer_sketchup_model_snapshots", "raw_model_json"),
    ("designer_sketchup_model_snapshots", "units_json"),
    ("designer_sketchup_model_snapshots", "warnings_json"),
    ("designer_sketchup_parse_jobs", "metrics_json"),
    ("designer_sketchup_parse_jobs", "storage_keys_json"),
})


def _declared_json_columns() -> dict[tuple[str, str], str]:
    """(table, column) -> "jsonb" | "json" as the models render on PostgreSQL."""
    pg = postgresql.dialect()
    out: dict[tuple[str, str], str] = {}
    for table in designer_models.Base.metadata.tables.values():
        if not table.name.startswith("designer_"):
            continue
        for column in table.columns:
            impl = column.type.dialect_impl(pg)
            if isinstance(impl, JSON):
                out[(table.name, column.name)] = "jsonb" if isinstance(impl, postgresql.JSONB) else "json"
    return out


def test_snapshot_covers_every_designer_json_column() -> None:
    declared = set(_declared_json_columns())
    assert declared == _PRODUCTION_JSONB | _PRODUCTION_JSON, (
        f"new: {sorted(declared - _PRODUCTION_JSONB - _PRODUCTION_JSON)} "
        f"gone: {sorted((_PRODUCTION_JSONB | _PRODUCTION_JSON) - declared)} — add with its production type"
    )


@pytest.mark.parametrize("key", sorted(_PRODUCTION_JSONB | _PRODUCTION_JSON))
def test_designer_json_column_type_matches_production(key: tuple[str, str]) -> None:
    expected = "jsonb" if key in _PRODUCTION_JSONB else "json"
    assert _declared_json_columns()[key] == expected


def test_jsonb_variant_is_plain_json_on_sqlite() -> None:
    """The SQLite test lane keeps plain JSON (no JSONB there)."""
    from sqlalchemy.dialects import sqlite

    impl = designer_models.JSON_PG_JSONB.dialect_impl(sqlite.dialect())
    assert isinstance(impl, JSON) and not isinstance(impl, postgresql.JSONB)
