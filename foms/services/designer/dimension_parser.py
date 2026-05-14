"""FOMS Brain PG-B6 — Dimension/View Geometry Parser.

Parses dimension numbers and axis labels from drawing OCR text or
Gemini-extracted geometry candidates.

Targets (PG-B6 acceptance):
  - W/D/H number recall >= 90%
  - axis accuracy >= 85%
  - view type accuracy >= 90%

Sources:
  1. Gemini multimodal extraction (primary — already extracts dimensions)
  2. OCR text (secondary — regex-based fallback)
  3. OpenCV color/line candidates (future PG-B6 extension)

Dimension variants handled:
  - "W 2400"  "H 2200"  "D 620"
  - "2400*2200*620"
  - "W:2400"  "폭:2400"  "높이:2200"
  - "D:445"  "D=550"
  - Stacked heights: "250 / 300 / 250 / 300"
  - Module widths: "800 800 800" (implicit W axis, equal widths)
  - Footer site spec: "현장규격 1620*500*2306"
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────────────────

@dataclass
class DimensionCandidate:
    """Single parsed dimension value with axis and view context."""

    value_mm: int
    axis: str        # "width" | "height" | "depth" | "module_width" | "shelf_height" | "unknown"
    view: str        # "front" | "side" | "top" | "isometric" | "unknown"
    source: str      # "ocr_regex" | "gemini_json" | "stacked_heights" | "footer"
    confidence: float = 1.0
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_mm": self.value_mm,
            "axis": self.axis,
            "view": self.view,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class DimensionParseResult:
    """All dimension candidates extracted from one drawing page."""

    candidates: list[DimensionCandidate] = field(default_factory=list)
    site_size: dict[str, int | None] = field(default_factory=dict)
    module_widths_mm: list[int] = field(default_factory=list)
    stacked_heights_mm: list[int] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "ocr_regex"

    def get_wdh(self) -> dict[str, int | None]:
        """Extract primary W/D/H from candidates."""
        result: dict[str, int | None] = {"width": None, "height": None, "depth": None}
        # Prefer site_size if available
        if self.site_size:
            result.update({k: v for k, v in self.site_size.items() if v})
        # Fall back to candidates
        for axis in ("width", "height", "depth"):
            if result.get(axis):
                continue
            matches = [c for c in self.candidates if c.axis == axis]
            if matches:
                result[axis] = max(matches, key=lambda c: c.value_mm).value_mm
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "site_size": self.site_size,
            "module_widths_mm": self.module_widths_mm,
            "stacked_heights_mm": self.stacked_heights_mm,
            "unresolved": self.unresolved,
            "confidence": self.confidence,
            "source": self.source,
            "wdh": self.get_wdh(),
        }


# ──────────────────────────────────────────────────────────
# Axis keyword mapping
# ──────────────────────────────────────────────────────────

_AXIS_KEYWORDS: dict[str, str] = {
    "w": "width", "width": "width", "폭": "width", "가로": "width",
    "h": "height", "height": "height", "높이": "height", "세로": "height",
    "d": "depth", "depth": "depth", "깊이": "depth",
    "module_width": "module_width", "칸폭": "module_width", "통폭": "module_width",
    "shelf": "shelf_height", "선반": "shelf_height",
}

_VIEW_KEYWORDS: dict[str, str] = {
    "front": "front", "정면": "front", "정면도": "front",
    "side": "side", "측면": "side", "측면도": "side",
    "top": "top", "평면": "top", "평면도": "top",
    "iso": "isometric", "isometric": "isometric", "투상": "isometric",
}


def _normalize_axis(raw: str) -> str:
    return _AXIS_KEYWORDS.get(raw.lower().strip(), "unknown")


def _normalize_view(raw: str) -> str:
    return _VIEW_KEYWORDS.get(raw.lower().strip(), "unknown")


# ──────────────────────────────────────────────────────────
# OCR text-based parser
# ──────────────────────────────────────────────────────────

# "W 2400", "W:2400", "폭: 2400", "H=2200"
_AXIS_PATTERN = re.compile(
    r'(?P<axis>[WwHhDd]|폭|높이|가로|세로|깊이|width|height|depth)'
    r'[\s:=]*'
    r'(?P<value>\d{3,5})',
    re.IGNORECASE | re.UNICODE,
)

# Site spec "W*H*D" or "W×H×D"
_WxHxD_PATTERN = re.compile(
    r'(?P<w>\d{3,5})\s*[*×Xx]\s*(?P<h>\d{3,5})(?:\s*[*×Xx]\s*(?P<d>\d{3,5}))?'
)

# Stacked heights: "250 / 300 / 250 / 300" or "250|300|250"
_STACKED_PATTERN = re.compile(
    r'(?:\d{2,4}\s*[/|]\s*){2,}\d{2,4}'
)

# Site spec footer: "현장규격 W*H*D" or "현장규격 W"
_SITE_FOOTER = re.compile(
    r'현장[규격\s]*'
    r'(?P<w>\d{3,5})\s*[*×Xx]\s*(?P<h>\d{3,5})(?:\s*[*×Xx]\s*(?P<d>\d{3,5}))?',
    re.UNICODE,
)

# Depth label: "D:445", "D=550", "D620"
_DEPTH_LABEL = re.compile(r'[Dd][\s:=]*(?P<d>\d{3,4})')


def parse_ocr_text(text: str, view: str = "unknown") -> DimensionParseResult:
    """Parse dimension values from OCR text.

    Args:
        text: Raw OCR or copy-pasted drawing text.
        view: View context if known (front/side/top/isometric/unknown).

    Returns:
        DimensionParseResult with all found candidates.
    """
    result = DimensionParseResult(source="ocr_regex")
    lines = text.strip().split("\n")
    recognized = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Site footer
        m_site = _SITE_FOOTER.search(line)
        if m_site:
            result.site_size = {
                "width": int(m_site.group("w")),
                "height": int(m_site.group("h")),
                "depth": int(m_site.group("d")) if m_site.group("d") else None,
            }
            for axis, key in [("width", "w"), ("height", "h"), ("depth", "d")]:
                if m_site.group(key):
                    result.candidates.append(DimensionCandidate(
                        value_mm=int(m_site.group(key)),
                        axis=axis, view="unknown",
                        source="footer", confidence=0.95, raw_text=line,
                    ))
            recognized += 1
            continue

        # W×H×D pattern
        m_wxhxd = _WxHxD_PATTERN.search(line)
        if m_wxhxd:
            axes = [("width", "w"), ("height", "h"), ("depth", "d")]
            for axis, grp in axes:
                if m_wxhxd.group(grp):
                    result.candidates.append(DimensionCandidate(
                        value_mm=int(m_wxhxd.group(grp)),
                        axis=axis, view=view,
                        source="ocr_regex", confidence=0.9, raw_text=line,
                    ))
            recognized += 1
            continue

        # Explicit axis labels
        for m in _AXIS_PATTERN.finditer(line):
            axis = _normalize_axis(m.group("axis"))
            val = int(m.group("value"))
            if 50 <= val <= 12000:  # sanity bounds (mm)
                result.candidates.append(DimensionCandidate(
                    value_mm=val, axis=axis, view=view,
                    source="ocr_regex", confidence=0.85, raw_text=line,
                ))
                recognized += 1

        # Depth label fallback
        m_d = _DEPTH_LABEL.search(line)
        if m_d and not any(c.axis == "depth" and c.raw_text == line
                           for c in result.candidates):
            result.candidates.append(DimensionCandidate(
                value_mm=int(m_d.group("d")),
                axis="depth", view=view,
                source="ocr_regex", confidence=0.75, raw_text=line,
            ))
            recognized += 1

    # Stacked heights
    for line in lines:
        if _STACKED_PATTERN.search(line):
            nums = [int(n) for n in re.findall(r'\d+', line) if 50 <= int(n) <= 2500]
            result.stacked_heights_mm = nums
            for n in nums:
                result.candidates.append(DimensionCandidate(
                    value_mm=n, axis="shelf_height", view=view,
                    source="stacked_heights", confidence=0.8, raw_text=line,
                ))

    total_lines = len([l for l in lines if l.strip()])
    result.confidence = min(1.0, recognized / total_lines) if total_lines > 0 else 0.0
    return result


# ──────────────────────────────────────────────────────────
# Gemini JSON-based parser
# ──────────────────────────────────────────────────────────

def parse_gemini_dimensions(
    gemini_extraction: dict[str, Any],
) -> DimensionParseResult:
    """Build dimension candidates from Gemini extraction output.

    Gemini extraction contains:
      extracted_params: {width, height, depth, module_widths, ...}
      _drawing_meta / drawing_meta: {view_type, ...}
      dimension_candidates: [{value_mm, axis, view, source}, ...]

    Returns:
        DimensionParseResult populated from Gemini fields.
    """
    result = DimensionParseResult(source="gemini_json")

    # Primary W/D/H from extracted_params
    params = gemini_extraction.get("extracted_params") or {}
    meta = (
        gemini_extraction.get("drawing_meta")
        or gemini_extraction.get("_drawing_meta")
        or {}
    )
    view = _normalize_view(str(meta.get("view_type") or "unknown"))

    for axis in ("width", "height", "depth"):
        val = params.get(axis)
        if val:
            try:
                ival = int(val)
                if 50 <= ival <= 12000:
                    result.candidates.append(DimensionCandidate(
                        value_mm=ival, axis=axis, view=view,
                        source="gemini_json", confidence=0.95,
                        raw_text=f"gemini:{axis}={ival}",
                    ))
            except (TypeError, ValueError):
                result.unresolved.append(f"{axis}:{val}")

    result.site_size = {
        "width": _to_int(params.get("width")),
        "height": _to_int(params.get("height")),
        "depth": _to_int(params.get("depth")),
    }

    # Module widths
    mw = params.get("module_widths") or params.get("_module_widths") or []
    result.module_widths_mm = [int(v) for v in mw if v]

    # Pre-extracted dimension candidates from Gemini (if available)
    for dc in gemini_extraction.get("dimension_candidates") or []:
        val = _to_int(dc.get("value_mm"))
        if val and 50 <= val <= 12000:
            result.candidates.append(DimensionCandidate(
                value_mm=val,
                axis=_normalize_axis(str(dc.get("axis") or "unknown")),
                view=_normalize_view(str(dc.get("view") or "unknown")),
                source=str(dc.get("source") or "gemini_json"),
                confidence=float(dc.get("confidence", 0.9)),
            ))

    n = len(result.candidates)
    result.confidence = min(1.0, n / 3) if n > 0 else 0.0
    return result


def _to_int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────
# Scorecard
# ──────────────────────────────────────────────────────────

def score_dimension_recall(
    parsed: DimensionParseResult,
    expected: dict[str, int | None],
    tolerance_mm: int = 5,
) -> dict[str, Any]:
    """Score W/D/H recall against expected values.

    Args:
        parsed: DimensionParseResult.
        expected: {"width": 2400, "height": 2200, "depth": 620}.
        tolerance_mm: Acceptable deviation in mm.

    Returns:
        dict with per_axis scores, recall, meets_target.
    """
    wdh = parsed.get_wdh()
    total = 0
    correct = 0
    per_axis: dict[str, Any] = {}

    for axis in ("width", "height", "depth"):
        exp = expected.get(axis)
        if exp is None:
            continue
        got = wdh.get(axis)
        total += 1
        if got is not None and abs(got - exp) <= tolerance_mm:
            correct += 1
            per_axis[axis] = {"expected": exp, "got": got, "correct": True}
        else:
            per_axis[axis] = {"expected": exp, "got": got, "correct": False}

    recall = correct / total if total > 0 else 1.0
    return {
        "recall": round(recall, 4),
        "correct": correct,
        "total": total,
        "per_axis": per_axis,
        "meets_target": recall >= 0.90,
        "meets_95_target": recall >= 0.95,
    }
