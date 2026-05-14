"""FOMS Brain PG-B5 — Parts Table Parser.

Parses Korean furniture parts tables from OCR text or Gemini extraction.

Supported part codes:
  [SR]    선반 (shelf rail)
  [EP]    엔드패널 / 경첩판
  [DOOR]  도어
  [마이다]  마이다스 / 미닫이
  [옷봉]  옷봉 (wardrobe rod)
  [보조목] 보조목 (auxiliary wood)
  [서랍]  서랍 (drawer)
  [받침대] 받침대 (base)
  [거울]  거울 (mirror)

Parts table format variants:
  1. "[SR] 60*2440=1"
  2. "[SR] 60 x 2440 = 1"
  3. "SR : 60×2440 qty:2"
  4. Raw Gemini JSON: {"code": "[SR]", "description": "선반", "quantity": 3}

Acceptance targets (PG-B5):
  - SR/EP/DOOR item recall >= 90%
  - qty exact match >= 95%
  - note classification >= 85%
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Part codes (canonical)
# ──────────────────────────────────────────────────────────

KNOWN_CODES = {
    # code pattern → canonical code
    "SR": "[SR]",
    "[SR]": "[SR]",
    "EP": "[EP]",
    "[EP]": "[EP]",
    "DOOR": "[DOOR]",
    "[DOOR]": "[DOOR]",
    "마이다": "[마이다]",
    "[마이다]": "[마이다]",
    "마이다스": "[마이다]",
    "옷봉": "[옷봉]",
    "[옷봉]": "[옷봉]",
    "보조목": "[보조목]",
    "[보조목]": "[보조목]",
    "서랍": "[서랍]",
    "[서랍]": "[서랍]",
    "받침대": "[받침대]",
    "[받침대]": "[받침대]",
    "거울": "[거울]",
    "[거울]": "[거울]",
    "데코EP": "[EP]",
    "DECOEP": "[EP]",
}

CODE_DESCRIPTIONS = {
    "[SR]": "선반",
    "[EP]": "엔드패널",
    "[DOOR]": "도어",
    "[마이다]": "마이다스(미닫이)",
    "[옷봉]": "옷봉",
    "[보조목]": "보조목",
    "[서랍]": "서랍",
    "[받침대]": "받침대",
    "[거울]": "거울",
}

# ──────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────

@dataclass
class ParsedPartItem:
    """Single line item from a parts table."""

    code: str                    # canonical code e.g. "[SR]"
    description: str | None     # Korean description
    width_mm: int | None        # mm (from WxH spec)
    height_mm: int | None       # mm
    quantity: int               # count
    note: str | None            # e.g. "플랩", "클린화이트"
    raw_text: str               # original text

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "description": self.description,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "quantity": self.quantity,
            "note": self.note,
        }


@dataclass
class ParsedPartsTable:
    """Parsed parts table from a drawing."""

    items: list[ParsedPartItem] = field(default_factory=list)
    unrecognized_lines: list[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "text"  # "text" | "gemini_json"

    @property
    def total_item_count(self) -> int:
        return sum(item.quantity for item in self.items)

    def get_by_code(self, code: str) -> list[ParsedPartItem]:
        canonical = normalize_code(code)
        return [it for it in self.items if it.code == canonical]

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [it.to_dict() for it in self.items],
            "unrecognized_lines": self.unrecognized_lines,
            "confidence": self.confidence,
            "source": self.source,
            "total_items": len(self.items),
        }


# ──────────────────────────────────────────────────────────
# Code normalization
# ──────────────────────────────────────────────────────────

def normalize_code(raw: str) -> str:
    """Normalize a raw code string to canonical form."""
    cleaned = raw.strip().upper().replace(" ", "")
    # Try exact match first
    for key, canonical in KNOWN_CODES.items():
        if cleaned == key.upper():
            return canonical
    # Try without brackets
    cleaned_no_bracket = cleaned.strip("[]")
    for key, canonical in KNOWN_CODES.items():
        if cleaned_no_bracket == key.upper().strip("[]"):
            return canonical
    return raw.strip()


# ──────────────────────────────────────────────────────────
# Text-based parser
# ──────────────────────────────────────────────────────────

# Pattern: [CODE] WIDTHxHEIGHT=QTY (note)
# Variants: * x × × =
_PART_PATTERN = re.compile(
    r'(?P<code>\[?(?:SR|EP|DOOR|마이다|마이다스|옷봉|보조목|서랍|받침대|거울|데코EP)\]?)'
    r'[\s:]*'
    r'(?:(?P<width>\d+)[\s*x×Xx×]\s*(?P<height>\d+))?'
    r'[\s=:]*'
    r'(?P<qty>\d+)'
    r'[\s]*'
    r'(?:[\(\[]?(?P<note>[가-힣\w\s]+?)[\)\]]?)?'
    r'\s*$',
    re.IGNORECASE | re.UNICODE,
)

# Pattern: just a code + qty (no dimensions)
_SIMPLE_PATTERN = re.compile(
    r'(?P<code>\[?(?:SR|EP|DOOR|마이다|마이다스|옷봉|보조목|서랍|받침대|거울)\]?)'
    r'[\s:×x\*]*'
    r'(?P<qty>\d+)',
    re.IGNORECASE | re.UNICODE,
)


def parse_line(line: str) -> ParsedPartItem | None:
    """Parse a single parts table line.

    Returns ParsedPartItem or None if not recognized.
    """
    line = line.strip()
    if not line:
        return None

    m = _PART_PATTERN.match(line)
    if m:
        raw_code = m.group("code")
        canonical = normalize_code(raw_code)
        width = int(m.group("width")) if m.group("width") else None
        height = int(m.group("height")) if m.group("height") else None
        qty = int(m.group("qty"))
        note_raw = (m.group("note") or "").strip()
        note = note_raw if note_raw else None

        return ParsedPartItem(
            code=canonical,
            description=CODE_DESCRIPTIONS.get(canonical),
            width_mm=width,
            height_mm=height,
            quantity=qty,
            note=note,
            raw_text=line,
        )

    # Simpler pattern fallback
    m2 = _SIMPLE_PATTERN.search(line)
    if m2:
        raw_code = m2.group("code")
        canonical = normalize_code(raw_code)
        qty = int(m2.group("qty"))
        return ParsedPartItem(
            code=canonical,
            description=CODE_DESCRIPTIONS.get(canonical),
            width_mm=None,
            height_mm=None,
            quantity=qty,
            note=None,
            raw_text=line,
        )

    return None


def parse_text(text: str) -> ParsedPartsTable:
    """Parse a multi-line parts table text.

    Args:
        text: Raw OCR or copy-pasted parts table text.

    Returns:
        ParsedPartsTable with all recognized items.
    """
    result = ParsedPartsTable(source="text")
    lines = text.strip().split("\n")
    recognized = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        item = parse_line(line)
        if item:
            result.items.append(item)
            recognized += 1
        else:
            result.unrecognized_lines.append(line)

    total = recognized + len(result.unrecognized_lines)
    result.confidence = recognized / total if total > 0 else 0.0
    logger.debug("[PARTS] parsed %d items from %d lines (conf=%.2f)",
                 recognized, total, result.confidence)
    return result


# ──────────────────────────────────────────────────────────
# Gemini JSON-based parser
# ──────────────────────────────────────────────────────────

def parse_gemini_parts_table(parts_list: list[dict[str, Any]]) -> ParsedPartsTable:
    """Parse parts table from Gemini extraction JSON.

    Gemini returns:
      [{"code": "[SR]", "description": "선반", "quantity": 3, "note": ""}]

    Args:
        parts_list: List of part dicts from Gemini.

    Returns:
        ParsedPartsTable.
    """
    result = ParsedPartsTable(source="gemini_json")
    recognized = 0

    for part in (parts_list or []):
        raw_code = str(part.get("code", "")).strip()
        if not raw_code:
            continue

        canonical = normalize_code(raw_code)
        qty = int(part.get("quantity", 1)) if part.get("quantity") is not None else 1
        desc = str(part.get("description", "")).strip() or None
        note = str(part.get("note", "")).strip() or None

        # Try to parse dimensions from description
        width = None
        height = None
        if desc:
            dim_m = re.search(r'(\d+)[\s*x×Xx]\s*(\d+)', desc)
            if dim_m:
                width = int(dim_m.group(1))
                height = int(dim_m.group(2))

        result.items.append(ParsedPartItem(
            code=canonical,
            description=desc or CODE_DESCRIPTIONS.get(canonical),
            width_mm=width,
            height_mm=height,
            quantity=qty,
            note=note,
            raw_text=str(part),
        ))
        recognized += 1

    result.confidence = 1.0 if recognized > 0 else 0.0
    return result


# ──────────────────────────────────────────────────────────
# Scorecard
# ──────────────────────────────────────────────────────────

def score_parts_recall(
    parsed: ParsedPartsTable,
    expected: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute item recall against expected parts list.

    Args:
        parsed: ParsedPartsTable from parser.
        expected: List of expected part dicts with 'code' and 'quantity'.

    Returns:
        dict with recall, precision, f1, per_code_scores.
    """
    if not expected:
        return {"recall": 1.0, "precision": 1.0, "f1": 1.0, "per_code": {}}

    parsed_codes = {}
    for item in parsed.items:
        parsed_codes[item.code] = parsed_codes.get(item.code, 0) + item.quantity

    expected_codes = {}
    for ex in expected:
        code = normalize_code(ex.get("code", ""))
        qty = int(ex.get("quantity", 1))
        expected_codes[code] = expected_codes.get(code, 0) + qty

    # Recall: expected items found in parsed
    total_expected = sum(expected_codes.values())
    found = sum(
        min(parsed_codes.get(c, 0), q)
        for c, q in expected_codes.items()
    )
    recall = found / total_expected if total_expected > 0 else 1.0

    # Precision: parsed items that are in expected
    total_parsed = sum(parsed_codes.values())
    precision = found / total_parsed if total_parsed > 0 else 0.0

    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    per_code = {}
    for code, expected_qty in expected_codes.items():
        parsed_qty = parsed_codes.get(code, 0)
        per_code[code] = {
            "expected_qty": expected_qty,
            "parsed_qty": parsed_qty,
            "found": min(parsed_qty, expected_qty),
            "recall": min(parsed_qty, expected_qty) / expected_qty,
        }

    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "f1": round(f1, 4),
        "per_code": per_code,
        "meets_target": recall >= 0.90,
    }
