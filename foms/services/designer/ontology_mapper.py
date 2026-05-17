"""FOMS Brain PG-B7 — Ontology Mapper + Candidate Graph Builder.

Maps Gemini extraction results → factory params → DesignGraphCandidate.

Mapping chain:
  title block product_name → furniture_type hint
  site_size / extracted_params W/D/H → assembly dimensions
  dimension_candidates stacked heights → module layout hints
  parts_table SR/EP/DOOR/etc. → component/material hints
  Gemini unresolved_fields → candidate.unresolved_fields
  Gemini confidence → candidate.confidence
  validator result → candidate.validation_result

Contract:
- No candidate is ever auto-approved. approved=False always on exit.
- unresolved_fields must be empty before the candidate can be applied.
- validator is run inside this module and attached to candidate.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Furniture type resolution
# ──────────────────────────────────────────────────────────

_PRODUCT_NAME_HINTS: dict[str, str] = {
    "붙박이장": "wardrobe",
    "옷장": "wardrobe",
    "드레스룸": "wardrobe",
    "신발장": "shoe_rack",
    "슈즈장": "shoe_rack",
    "주방": "kitchen_base",
    "부엌": "kitchen_base",
    "부엌가구": "kitchen_base",
    "싱크대": "kitchen_base",
    "상부장": "kitchen_wall",
    "주방상부": "kitchen_wall",
    "수납장": "custom_storage",
    "tv장": "custom_storage",
    "거실장": "custom_storage",
}

_VALID_TYPES = frozenset({
    "wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"
})


def resolve_furniture_type(
    extraction: dict[str, Any],
) -> tuple[str, float]:
    """Resolve furniture_type from extraction data.

    Returns:
        (furniture_type, confidence). confidence < 0.5 means uncertain.
    """
    # 1. Gemini explicit
    gemini_type = extraction.get("furniture_type", "")
    if gemini_type in _VALID_TYPES:
        return gemini_type, 0.9

    # 2. Product name hint
    ci = extraction.get("customer_info") or {}
    product_name = str(ci.get("product_name") or "").strip().lower()
    for hint, ftype in _PRODUCT_NAME_HINTS.items():
        if hint in product_name:
            return ftype, 0.7

    # 3. Parts table hints
    parts = extraction.get("parts_table") or []
    codes = {str(p.get("code", "")).upper() for p in parts}
    if "[SR]" in codes or "[EP]" in codes:
        return "wardrobe", 0.6
    if any("주방" in str(p.get("description", "")) for p in parts):
        return "kitchen_base", 0.55

    return "custom_storage", 0.3


# ──────────────────────────────────────────────────────────
# Factory param extraction
# ──────────────────────────────────────────────────────────

def extract_factory_params(
    extraction: dict[str, Any],
    furniture_type: str,
) -> tuple[dict[str, Any], list[str]]:
    """Map extraction to factory params dict + unresolved_fields list.

    Returns:
        (params, unresolved_fields)
    """
    params: dict[str, Any] = {}
    unresolved: list[str] = list(extraction.get("unresolved_fields") or [])

    ep = extraction.get("extracted_params") or {}
    ss = extraction.get("site_size") or {}

    # W/H/D
    for dim, aliases in [
        ("width", ["width", "w"]),
        ("height", ["height", "h"]),
        ("depth", ["depth", "d"]),
    ]:
        val = None
        for alias in aliases:
            candidate = ep.get(alias) or ss.get(f"{alias}_mm")
            if candidate:
                try:
                    val = int(candidate)
                    break
                except (TypeError, ValueError):
                    pass
        if val and 100 <= val <= 12000:
            params[dim] = val
        else:
            unresolved.append(dim)

    # Module count (wardrobe / kitchen)
    if furniture_type in ("wardrobe", "kitchen_base", "kitchen_wall"):
        mw = ep.get("module_widths") or ep.get("_module_widths") or []
        if mw:
            params["module_count"] = len(mw)
            params["module_widths"] = [int(v) for v in mw if v]
        elif "module_count" not in unresolved:
            unresolved.append("module_count")

    # Tier count (shoe_rack)
    if furniture_type == "shoe_rack":
        tc = ep.get("tier_count")
        if tc:
            params["tier_count"] = int(tc)

    # Door type
    dt = ep.get("door_type")
    if dt in ("swing", "sliding", "open"):
        params["door_type"] = dt

    return params, unresolved


# ──────────────────────────────────────────────────────────
# Candidate builder
# ──────────────────────────────────────────────────────────

@dataclass
class MappedCandidate:
    """Design graph candidate from ontology mapping."""

    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    furniture_type: str = "custom_storage"
    factory_params: dict[str, Any] = field(default_factory=dict)
    unresolved_fields: list[str] = field(default_factory=list)
    approved: bool = False          # always False — human review required
    confidence: float = 0.0
    validation_result: dict[str, Any] | None = None
    parts_table: list[dict[str, Any]] = field(default_factory=list)
    dimensions_parsed: dict[str, Any] = field(default_factory=dict)
    view_type: str = "unknown"
    source_extraction_id: int | None = None

    def can_apply(self) -> bool:
        """True only when human-approved and no unresolved fields."""
        return (
            self.approved
            and not self.unresolved_fields
            and self.validation_result is not None
            and self.validation_result.get("valid", False)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "furniture_type": self.furniture_type,
            "factory_params": self.factory_params,
            "unresolved_fields": self.unresolved_fields,
            "approved": self.approved,
            "confidence": self.confidence,
            "can_apply": self.can_apply(),
            "validation_result": self.validation_result,
            "parts_table": self.parts_table,
            "dimensions_parsed": self.dimensions_parsed,
            "view_type": self.view_type,
            "source_extraction_id": self.source_extraction_id,
        }


def build_candidate(
    extraction: dict[str, Any],
    source_extraction_id: int | None = None,
    run_validator: bool = True,
) -> MappedCandidate:
    """Build a MappedCandidate from a Gemini extraction result.

    This is the primary entry point for PG-B7 mapping.

    Args:
        extraction: Raw Gemini extraction dict.
        source_extraction_id: DB id of DesignerDrawingExtraction row.
        run_validator: Whether to run the factory validator.

    Returns:
        MappedCandidate with approved=False always.
    """
    furniture_type, type_conf = resolve_furniture_type(extraction)
    factory_params, unresolved = extract_factory_params(extraction, furniture_type)

    # Confidence = geometric mean of type confidence and extraction confidence
    extraction_conf = float(extraction.get("confidence") or 0.0)
    combined_conf = (type_conf * extraction_conf) ** 0.5 if extraction_conf > 0 else type_conf * 0.5

    # Validator
    validation_result = None
    if run_validator and factory_params and not unresolved:
        try:
            from foms.services.designer.factory_registry import validate_params
            errors = validate_params(furniture_type, factory_params)
            validation_result = {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": [],
            }
        except Exception as exc:
            logger.warning("[MAPPER] validator failed: %s", exc)
            validation_result = {"valid": False, "errors": [str(exc)], "warnings": []}

    # Parts table
    parts = extraction.get("parts_table") or []
    ep = extraction.get("extracted_params") or {}
    if not parts:
        parts = ep.get("_parts_table") or []

    # View type
    meta = extraction.get("drawing_meta") or ep.get("_drawing_meta") or {}
    view_type = str(meta.get("view_type") or "unknown")

    candidate = MappedCandidate(
        furniture_type=furniture_type,
        factory_params=factory_params,
        unresolved_fields=unresolved,
        approved=False,  # ALWAYS False — human review required
        confidence=round(combined_conf, 4),
        validation_result=validation_result,
        parts_table=parts,
        dimensions_parsed={
            "width": factory_params.get("width"),
            "height": factory_params.get("height"),
            "depth": factory_params.get("depth"),
        },
        view_type=view_type,
        source_extraction_id=source_extraction_id,
    )

    logger.info(
        "[MAPPER] candidate built: type=%s unresolved=%s confidence=%.2f can_apply=%s",
        furniture_type, unresolved, combined_conf, candidate.can_apply(),
    )
    return candidate


def build_candidates_from_pages(
    pages: list[dict[str, Any]],
    source_extraction_id: int | None = None,
) -> list[MappedCandidate]:
    """Build candidates from all pages of a multi-page drawing."""
    return [
        build_candidate(page, source_extraction_id=source_extraction_id)
        for page in pages
    ]
