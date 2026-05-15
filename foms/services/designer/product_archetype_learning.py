"""FOMS Brain PG-L3 — Product Archetype Learning.

Mines repeated approved design cases to discover new product archetypes.

Contract:
- Minimum 3 approved cases required to form an archetype candidate.
- Candidate includes supporting case IDs as evidence.
- Candidate is NOT a production factory until human-approved + replay-passed.
- Known extended archetypes are pre-seeded for matching.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from foms.services.designer.product_archetype_types import (
    ProductArchetypeCandidate,
    KNOWN_EXTENDED_ARCHETYPES,
)

logger = logging.getLogger(__name__)

MIN_CASES = 3  # minimum approved cases to form an archetype candidate


# ──────────────────────────────────────────────────────────
# Tag extraction from design cases
# ──────────────────────────────────────────────────────────

_TAG_HINTS: dict[str, list[str]] = {
    "no_molding": ["무몰딩", "no_molding", "몰딩없음"],
    "reform": ["리폼", "reform", "기존장"],
    "refrigerator": ["내장고", "냉장고", "refrigerator"],
    "tv": ["tv", "TV", "거실장", "티비"],
    "bathroom": ["화장실", "bathroom", "방습"],
    "dressroom": ["드레스룸", "dressroom", "워크인"],
    "split": ["상하분할", "split", "분할장"],
    "hanger": ["행거", "hanger"],
    "kitchen_combined": ["주방상하", "kitchen_combined", "상하복합"],
    "combined": ["복합", "combined"],
}


def extract_tags_from_case(case: dict[str, Any]) -> list[str]:
    """Extract semantic tags from a design case dict."""
    tags: set[str] = set(case.get("tags") or [])

    # Add tags from product_name and options
    product_name = str(case.get("product_name") or "").lower()
    options = case.get("options_json") or {}

    all_text = product_name + " " + str(options).lower()
    for tag, hints in _TAG_HINTS.items():
        if any(h.lower() in all_text for h in hints):
            tags.add(tag)

    for understanding in _iter_design_understanding_payloads(case):
        category = understanding.get("learned_design_category") or {}
        for tag in category.get("similarity_tags") or []:
            _add_normalized_tag(tags, tag)

        category_key = category.get("category_key")
        if category_key:
            _add_normalized_tag(tags, category_key)

        signature = category.get("layout_signature") or {}
        for key in ("module_pattern", "dominant_structure"):
            _add_normalized_tag(tags, signature.get(key))
        for key in ("zone_roles", "material_signature", "hardware_signature"):
            for tag in signature.get(key) or []:
                _add_normalized_tag(tags, tag)

        summary = understanding.get("learning_summary") or {}
        for key in ("reusable_patterns", "new_module_candidates"):
            for tag in summary.get(key) or []:
                _add_normalized_tag(tags, tag)

        for block in understanding.get("block_candidates") or []:
            if isinstance(block, dict):
                _add_normalized_tag(tags, block.get("block_key"))

    return sorted(tags)


def _iter_design_understanding_payloads(case: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    candidates = [
        case,
        case.get("options_json") or {},
        case.get("internal_structure_json") or {},
        case.get("design_graph_json") or {},
        case.get("redacted_extraction") or {},
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if "layout_graph" in candidate or "learned_design_category" in candidate:
            payloads.append(candidate)
        nested = candidate.get("design_understanding")
        if isinstance(nested, dict):
            payloads.append(nested)
    return payloads


def _add_normalized_tag(tags: set[str], value: Any) -> None:
    if value is None:
        return
    tag = str(value).strip().lower().replace(" ", "_")
    if tag:
        tags.add(tag)


# ──────────────────────────────────────────────────────────
# Archetype discovery
# ──────────────────────────────────────────────────────────

def discover_archetypes_from_cases(
    cases: list[dict[str, Any]],
    min_count: int = MIN_CASES,
) -> list[ProductArchetypeCandidate]:
    """Mine approved design cases for repeated archetype patterns.

    Args:
        cases: List of approved design case dicts (PII-free).
        min_count: Minimum cases sharing a pattern.

    Returns:
        List of ProductArchetypeCandidate (not yet saved).
    """
    # Group cases by (furniture_type, tag_signature)
    groups: dict[str, list[dict]] = {}
    for case in cases:
        ft = case.get("furniture_type", "custom_storage")
        tags = tuple(sorted(extract_tags_from_case(case)))
        key = f"{ft}::{':'.join(tags)}" if tags else ft
        groups.setdefault(key, []).append(case)

    candidates = []
    for group_key, group_cases in groups.items():
        if len(group_cases) < min_count:
            continue

        # Determine archetype key
        parts = group_key.split("::", 1)
        ft = parts[0]
        tag_pattern = parts[1].split(":") if len(parts) > 1 else []

        archetype_key = _match_known_archetype(ft, tag_pattern) or f"custom_{ft}_{len(candidates)}"
        known = KNOWN_EXTENDED_ARCHETYPES.get(archetype_key, {})

        supporting_ids = [c.get("id") for c in group_cases if c.get("id")]
        case_ids_int = [i for i in supporting_ids if i is not None]

        # Sample options from most recent case
        sample_options = {}
        for c in group_cases[:3]:
            opts = c.get("options_json") or {}
            sample_options.update(opts)

        evidence = len(group_cases)
        confidence = min(1.0, evidence / 10.0)

        candidate = ProductArchetypeCandidate(
            key=archetype_key,
            label_ko=known.get("label_ko", archetype_key),
            base_type=known.get("base_type", ft),
            supporting_case_ids=case_ids_int[:20],
            tag_pattern=tag_pattern,
            sample_options=sample_options,
            evidence_count=evidence,
            confidence=confidence,
            auto_generated=True,
            approved=False,
        )
        candidates.append(candidate)
        logger.info(
            "[ARCHETYPE] candidate=%s count=%d confidence=%.2f",
            archetype_key, evidence, confidence,
        )

    return candidates


def _match_known_archetype(furniture_type: str, tags: list[str]) -> str | None:
    """Match tags to a known extended archetype key."""
    tag_set = set(tags)
    best: str | None = None
    best_score = 0
    for key, info in KNOWN_EXTENDED_ARCHETYPES.items():
        if info["base_type"] != furniture_type and furniture_type not in (key, "custom_storage"):
            if info["base_type"] != furniture_type:
                continue
        known_tags = set(info.get("tags", []))
        overlap = len(known_tags & tag_set)
        if overlap > best_score:
            best_score = overlap
            best = key
    return best if best_score > 0 else None


# ──────────────────────────────────────────────────────────
# Full pipeline
# ──────────────────────────────────────────────────────────

def run_archetype_discovery_pipeline(
    furniture_type: str | None = None,
    min_count: int = MIN_CASES,
) -> list[dict[str, Any]]:
    """Load approved cases → discover archetypes → return candidate dicts.

    Does NOT save to DB (candidates are review-only at this stage).

    Returns:
        List of archetype candidate dicts.
    """
    try:
        from foms.services.designer.design_case_memory import list_design_cases
        cases = list_design_cases(furniture_type=furniture_type, limit=200)
    except Exception as exc:
        logger.warning("[ARCHETYPE] load cases failed: %s", exc)
        return []

    if not cases:
        logger.info("[ARCHETYPE] no approved cases found")
        return []

    candidates = discover_archetypes_from_cases(cases, min_count=min_count)
    return [c.to_dict() for c in candidates]


def get_archetype_summary() -> dict[str, Any]:
    """Return summary of known and discovered archetypes."""
    discovered = run_archetype_discovery_pipeline()
    return {
        "known_extended": list(KNOWN_EXTENDED_ARCHETYPES.keys()),
        "discovered_candidates": discovered,
        "total_known": len(KNOWN_EXTENDED_ARCHETYPES),
        "total_candidates": len(discovered),
    }
