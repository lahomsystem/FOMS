"""Phone digit normalization for indexed ERP search (P1-02)."""

from __future__ import annotations

import re

__all__ = [
    "normalize_phone_digits",
    "extract_phone_digit_query",
    "is_phone_digit_query",
]

_DIGIT_RE = re.compile(r"[^0-9]")


def normalize_phone_digits(phone: str | None) -> str | None:
    """
    Strip non-digits from a phone string for indexed lookup.

    Args:
        phone: Raw phone text (e.g. ``010-2690-2242``).

    Returns:
        Digits-only string or ``None`` when empty after normalization.
    """
    if phone is None:
        return None
    digits = _DIGIT_RE.sub("", str(phone).strip())
    return digits or None


def extract_phone_digit_query(query: str) -> str | None:
    """
    Extract searchable digit run from a user query.

    Args:
        query: Raw search input.

    Returns:
        Normalized digits when query is phone-like (>=4 digits), else ``None``.
    """
    digits = normalize_phone_digits(query)
    if not digits or len(digits) < 4:
        return None
    compact = "".join(str(query or "").split())
    if not compact:
        return None
    digit_ratio = len(digits) / len(compact)
    if digit_ratio < 0.5:
        return None
    return digits


def is_phone_digit_query(query: str) -> bool:
    """Return True when query should use ``erp_phone_digits`` indexed lookup."""
    return extract_phone_digit_query(query) is not None
