"""FOMS Brain PG-B6 — View Type Detector.

Detects the view type (front / side / top / isometric) of a drawing page
from text labels, Gemini extraction metadata, or filename hints.

View accuracy target: >= 90%.
"""

from __future__ import annotations

import re
from typing import Any

VALID_VIEWS = frozenset({"front", "side", "top", "isometric", "photo", "unknown"})

_TEXT_HINTS: dict[str, str] = {
    "정면": "front", "정면도": "front", "front": "front",
    "측면": "side", "측면도": "side", "side": "side",
    "평면": "top", "평면도": "top", "top": "top", "top view": "top",
    "투상": "isometric", "iso": "isometric", "isometric": "isometric", "3d": "isometric",
    "사진": "photo", "photo": "photo", "현장사진": "photo",
}

_VIEW_PATTERN = re.compile(
    r'(?P<view>정면도?|측면도?|평면도?|투상|isometric|front|side|top|사진|photo)',
    re.IGNORECASE | re.UNICODE,
)


def detect_view_from_text(text: str) -> str:
    """Detect view type from OCR text or page label.

    Returns one of: front / side / top / isometric / photo / unknown.
    """
    lower = text.lower()
    for keyword, view in _TEXT_HINTS.items():
        if keyword in lower:
            return view
    # Regex fallback
    m = _VIEW_PATTERN.search(text)
    if m:
        return _TEXT_HINTS.get(m.group("view").lower(), "unknown")
    return "unknown"


def detect_view_from_gemini(drawing_meta: dict[str, Any]) -> str:
    """Extract view type from Gemini drawing_meta dict."""
    if not drawing_meta:
        return "unknown"
    raw = str(drawing_meta.get("view_type") or "").lower().strip()
    return _TEXT_HINTS.get(raw, raw if raw in VALID_VIEWS else "unknown")


def classify_page_views(pages: list[dict[str, Any]]) -> list[str]:
    """Classify view types for all pages in a multi-page drawing.

    Args:
        pages: List of page dicts, each may have 'drawing_meta' or 'notes'.

    Returns:
        List of view type strings in page order.
    """
    result = []
    for page in pages:
        meta = page.get("drawing_meta") or page.get("_drawing_meta") or {}
        view = detect_view_from_gemini(meta)
        if view == "unknown":
            notes = str(page.get("notes") or "")
            view = detect_view_from_text(notes)
        result.append(view)
    return result


def score_view_accuracy(
    detected: list[str],
    expected: list[str],
) -> dict[str, Any]:
    """Score view type classification accuracy."""
    if not expected:
        return {"accuracy": 1.0, "correct": 0, "total": 0, "meets_target": True}
    total = min(len(detected), len(expected))
    correct = sum(
        1 for d, e in zip(detected[:total], expected[:total])
        if d == e
    )
    accuracy = correct / total if total > 0 else 1.0
    return {
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "total": total,
        "meets_target": accuracy >= 0.90,
    }
