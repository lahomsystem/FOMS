"""Construction type helpers shared by ERP regional order flows."""

from __future__ import annotations

from typing import Any


REGIONAL_CONSTRUCTION_TYPES = frozenset({"하우드 시공", "협력사 시공"})


def normalize_regional_construction_type(value: Any) -> str:
    """Normalize regional construction type labels to dashboard filter values."""
    raw = str(value or "").strip()
    aliases = {
        "하우드": "하우드 시공",
        "협력사": "협력사 시공",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in REGIONAL_CONSTRUCTION_TYPES else ""
