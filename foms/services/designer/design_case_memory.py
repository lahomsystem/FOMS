"""FOMS Brain PG-L1 — Design Case Memory Service.

Stores human-approved, validator-passed design cases as the core
learning asset for Retrieval-Augmented Design Brain (PG-L2).

Contract:
- save_design_case() only accepts project_version_id that already exists.
- Only approved extractions or explicit approval actions trigger case creation.
- No raw PII (customer_name/phone/address) is written into design_cases.
- Dimensions (width/height/depth) are extracted for fast similarity search.
- AI MUST NOT call save_design_case() directly; routes/API layer only.

Retrieval (PG-L2) will query:
- by furniture_type
- by approximate dimensions (width/height ± tolerance)
- by tags
- by product_name
- by module_count
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_VALID_FURNITURE_TYPES = frozenset({
    "wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"
})


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

def save_design_case(
    *,
    project_version_id: int,
    furniture_type: str,
    design_graph: dict[str, Any],
    project_id: int | None = None,
    drawing_artifact_id: int | None = None,
    approved_extraction_id: int | None = None,
    product_name: str | None = None,
    bom: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    internal_structure: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    source_quality_score: float = 1.0,
    approval_user_id: int | None = None,
) -> dict[str, Any]:
    """Save an approved, validated design as a learning case.

    Args:
        project_version_id: Must exist — validator has already passed.
        furniture_type: One of wardrobe/shoe_rack/kitchen_base/kitchen_wall/custom_storage.
        design_graph: PII-free design graph dict (DesignGraph.to_dict() output).
        project_id: Source project ID.
        drawing_artifact_id: Source drawing artifact, if from uploaded drawing.
        approved_extraction_id: Source extraction, if from Gemini extraction flow.
        product_name: Product label (e.g. "붙박이장 3칸").
        bom: Bill of materials dict.
        options: Options/hardware dict (color, handle, etc.) — PII-free.
        internal_structure: Internal structure description.
        tags: Searchable tags (e.g. ["no_molding", "reform", "3_bay"]).
        source_quality_score: 0.0–1.0 quality signal.
        approval_user_id: User who approved this design.

    Returns:
        dict with design case id and metadata.

    Raises:
        ValueError: If furniture_type is unknown or project_version_id does not exist.
        RuntimeError: If DB write fails.
    """
    if furniture_type not in _VALID_FURNITURE_TYPES:
        raise ValueError(
            f"Unknown furniture_type: {furniture_type!r}. "
            f"Valid: {sorted(_VALID_FURNITURE_TYPES)}"
        )

    from db import db_session
    from foms.persistence.designer.models import (
        DesignerDesignCase,
        DesignerProjectVersion,
    )

    # Verify project version exists (validator must have passed)
    pv = db_session.get(DesignerProjectVersion, project_version_id)
    if pv is None:
        raise ValueError(
            f"project_version_id={project_version_id} not found. "
            "Design case can only be created after a validated project version exists."
        )

    # Extract dimensions for fast similarity search
    width_mm, height_mm, depth_mm, module_count = _extract_dimensions(design_graph)

    # Sanitize — ensure no PII slips in
    clean_graph = _strip_pii_fields(design_graph)

    case = DesignerDesignCase(
        project_id=project_id,
        project_version_id=project_version_id,
        drawing_artifact_id=drawing_artifact_id,
        approved_extraction_id=approved_extraction_id,
        furniture_type=furniture_type,
        product_name=product_name,
        design_graph_json=clean_graph,
        bom_json=bom or {},
        options_json=options or {},
        internal_structure_json=internal_structure or {},
        tags_json=tags or [],
        width_mm=width_mm,
        height_mm=height_mm,
        depth_mm=depth_mm,
        module_count=module_count,
        source_quality_score=max(0.0, min(1.0, source_quality_score)),
        approval_user_id=approval_user_id,
        approved_at=datetime.now(timezone.utc),
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    logger.info(
        "[DESIGN_CASE] saved: id=%d type=%s W=%s H=%s quality=%.2f",
        case.id, furniture_type, width_mm, height_mm, source_quality_score,
    )
    return _case_to_dict(case)


def list_design_cases(
    furniture_type: str | None = None,
    width_mm_min: int | None = None,
    width_mm_max: int | None = None,
    height_mm_min: int | None = None,
    height_mm_max: int | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Query design cases for retrieval.

    All returned payloads are PII-free and safe for Gemini prompt injection.

    Args:
        furniture_type: Filter by furniture type.
        width_mm_min/max: Dimension range filters.
        height_mm_min/max: Dimension range filters.
        tags: Require all listed tags (AND).
        limit: Max rows returned.

    Returns:
        List of case dicts ordered by created_at desc.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerDesignCase

    q = db_session.query(DesignerDesignCase)

    if furniture_type:
        q = q.filter(DesignerDesignCase.furniture_type == furniture_type)
    if width_mm_min is not None:
        q = q.filter(DesignerDesignCase.width_mm >= width_mm_min)
    if width_mm_max is not None:
        q = q.filter(DesignerDesignCase.width_mm <= width_mm_max)
    if height_mm_min is not None:
        q = q.filter(DesignerDesignCase.height_mm >= height_mm_min)
    if height_mm_max is not None:
        q = q.filter(DesignerDesignCase.height_mm <= height_mm_max)

    cases = (
        q.order_by(DesignerDesignCase.created_at.desc())
        .limit(limit)
        .all()
    )

    result = [_case_to_dict(c) for c in cases]

    # Filter by tags in Python (JSON array containment)
    if tags:
        result = [
            c for c in result
            if all(t in (c.get("tags") or []) for t in tags)
        ]

    return result


def find_similar(
    furniture_type: str,
    width_mm: int,
    height_mm: int | None = None,
    depth_mm: int | None = None,
    tolerance_mm: int = 200,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find approved design cases similar to given dimensions.

    Used by Retrieval-Augmented Design Brain (PG-L2) to fetch
    top-k similar cases to include in Gemini prompt context.

    Returns cases ordered by dimension closeness (approximate).
    """
    cases = list_design_cases(
        furniture_type=furniture_type,
        width_mm_min=width_mm - tolerance_mm,
        width_mm_max=width_mm + tolerance_mm,
        height_mm_min=(height_mm - tolerance_mm) if height_mm else None,
        height_mm_max=(height_mm + tolerance_mm) if height_mm else None,
        limit=limit * 3,  # oversample then sort
    )
    if not cases:
        return []

    # Sort by Manhattan distance to target dimensions
    def dist(c: dict) -> int:
        d = abs((c.get("width_mm") or 0) - width_mm)
        if height_mm:
            d += abs((c.get("height_mm") or 0) - height_mm)
        if depth_mm:
            d += abs((c.get("depth_mm") or 0) - depth_mm)
        return d

    return sorted(cases, key=dist)[:limit]


def get_case_count(furniture_type: str | None = None) -> dict[str, int]:
    """Return count of design cases by furniture type."""
    from db import db_session
    from foms.persistence.designer.models import DesignerDesignCase
    from sqlalchemy import func

    q = db_session.query(
        DesignerDesignCase.furniture_type,
        func.count(DesignerDesignCase.id).label("count"),
    ).group_by(DesignerDesignCase.furniture_type)

    if furniture_type:
        q = q.filter(DesignerDesignCase.furniture_type == furniture_type)

    return {row.furniture_type: row.count for row in q.all()}


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

_PII_PATHS = {
    "customer_name", "phone", "address", "customer_phone",
    "customer_address", "client_name",
}


def _strip_pii_fields(graph: dict[str, Any]) -> dict[str, Any]:
    """Remove known PII keys from graph dict (shallow first level + metadata)."""
    import copy
    clean = copy.deepcopy(graph)
    for key in list(clean.keys()):
        if key in _PII_PATHS:
            del clean[key]
    # Also clean nested metadata if present
    meta = clean.get("metadata") or {}
    for key in list(meta.keys()):
        if key in _PII_PATHS:
            del meta[key]
    return clean


def _extract_dimensions(graph: dict[str, Any]) -> tuple[int | None, int | None, int | None, int | None]:
    """Extract W/H/D/module_count from design graph dict for fast indexing."""
    asm = graph.get("assembly") or {}
    dims = asm.get("dimensions") or {}
    width = _to_int(dims.get("width"))
    height = _to_int(dims.get("height"))
    depth = _to_int(dims.get("depth"))
    module_count = _to_int(asm.get("module_count"))
    return width, height, depth, module_count


def _to_int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _case_to_dict(case: Any) -> dict[str, Any]:
    return {
        "id": case.id,
        "project_id": case.project_id,
        "project_version_id": case.project_version_id,
        "drawing_artifact_id": case.drawing_artifact_id,
        "furniture_type": case.furniture_type,
        "product_name": case.product_name,
        "width_mm": case.width_mm,
        "height_mm": case.height_mm,
        "depth_mm": case.depth_mm,
        "module_count": case.module_count,
        "tags": case.tags_json or [],
        "source_quality_score": case.source_quality_score,
        "approved_at": case.approved_at.isoformat() if case.approved_at else None,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        # Full payloads (PII-free)
        "design_graph_json": case.design_graph_json,
        "bom_json": case.bom_json,
        "options_json": case.options_json,
        "internal_structure_json": case.internal_structure_json,
    }
