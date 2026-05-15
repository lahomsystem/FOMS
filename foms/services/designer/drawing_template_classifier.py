"""FOMS Brain PG-B4 — Drawing Template Classifier.

Classifies drawing template/style before routing to the model.

Template keys:
  lahom_standard      — 라홈 표준 도면 양식 (제목블록/부품표/치수선)
  benissimo_standard  — 베니시모 표준 도면
  ehf_standard        — EHF(이한풍) 표준 도면
  multi_page_detail   — 다중 페이지 상세 도면 (사진+정면도+부품표 혼합)
  unknown             — 분류 불가 (Gemini가 직접 해석)

Classification is based on:
1. Image metadata (filename hints, page count)
2. Visual structure hints sent to Gemini
3. Keyword matching for known company names

Gemini is the final judge — classifier provides routing hints only.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Template keys
# ──────────────────────────────────────────────────────────

TEMPLATE_KEYS = frozenset({
    "lahom_standard",
    "benissimo_standard",
    "ehf_standard",
    "multi_page_detail",
    "unknown",
})

# Company name → template key mapping
_COMPANY_HINTS: dict[str, str] = {
    "라홈": "lahom_standard",
    "lahom": "lahom_standard",
    "베니시모": "benissimo_standard",
    "benissimo": "benissimo_standard",
    "이한풍": "ehf_standard",
    "ehf": "ehf_standard",
}


# ──────────────────────────────────────────────────────────
# Classification result
# ──────────────────────────────────────────────────────────

@dataclass
class TemplateClassificationResult:
    """Result of drawing template classification."""

    template_key: str
    confidence: float           # 0.0–1.0
    method: str                 # "filename_hint" | "keyword" | "gemini" | "default"
    page_count: int = 1
    is_multi_page: bool = False
    hints: dict[str, Any] | None = None

    def is_known_template(self) -> bool:
        return self.template_key != "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_key": self.template_key,
            "confidence": self.confidence,
            "method": self.method,
            "page_count": self.page_count,
            "is_multi_page": self.is_multi_page,
            "hints": self.hints or {},
        }


# ──────────────────────────────────────────────────────────
# Classifier
# ──────────────────────────────────────────────────────────

def classify_from_filename(filename: str) -> TemplateClassificationResult:
    """Fast classification from filename alone (no image required).

    Returns 'unknown' if no match.
    """
    lower = filename.lower()
    for keyword, template_key in _COMPANY_HINTS.items():
        if keyword in lower:
            logger.debug("[CLASSIFY] filename hint: %s -> %s", filename, template_key)
            return TemplateClassificationResult(
                template_key=template_key,
                confidence=0.7,
                method="filename_hint",
                hints={"matched_keyword": keyword},
            )

    # Multi-page hints
    if any(x in lower for x in [".pdf", "_multi", "_all", "_pages"]):
        return TemplateClassificationResult(
            template_key="multi_page_detail",
            confidence=0.6,
            method="filename_hint",
            is_multi_page=True,
        )

    return TemplateClassificationResult(
        template_key="unknown",
        confidence=0.0,
        method="filename_hint",
    )


def classify_from_metadata(
    filename: str,
    page_count: int = 1,
    notes: str | None = None,
) -> TemplateClassificationResult:
    """Classification from file metadata (filename + page count + notes).

    Args:
        filename: Drawing file name.
        page_count: Number of pages (PDFs may have multiple).
        notes: Optional text notes from user or OCR.

    Returns:
        TemplateClassificationResult.
    """
    # Multi-page detection
    if page_count > 1:
        result = classify_from_filename(filename)
        result.is_multi_page = True
        result.page_count = page_count
        if result.template_key == "unknown":
            result.template_key = "multi_page_detail"
            result.confidence = 0.65
            result.method = "page_count"
        return result

    # Filename-based
    result = classify_from_filename(filename)
    result.page_count = page_count

    # Notes-based keyword check
    if notes and result.template_key == "unknown":
        notes_lower = notes.lower()
        for keyword, template_key in _COMPANY_HINTS.items():
            if keyword in notes_lower:
                result.template_key = template_key
                result.confidence = 0.55
                result.method = "keyword"
                result.hints = {"matched_in_notes": keyword}
                break

    return result


def classify_with_gemini(
    filename: str,
    image_bytes: bytes | None = None,
    page_count: int = 1,
) -> TemplateClassificationResult:
    """Use Gemini to classify the drawing template.

    Falls back to metadata-based classification if Gemini is unavailable.
    """
    # Fast path: metadata classification first
    fast_result = classify_from_metadata(filename, page_count)
    if fast_result.confidence >= 0.7:
        return fast_result

    # Gemini classification
    if not os.environ.get("GEMINI_API_KEY") or image_bytes is None:
        logger.info("[CLASSIFY] Gemini not available, using metadata result")
        return fast_result

    try:
        from foms.services.designer.gemini_provider import GEMINI_MODEL, _get_client
        from google.genai import types

        client = _get_client()
        prompt = (
            "도면 이미지의 양식을 분류하세요. "
            "반드시 다음 중 하나만 JSON으로 답하세요:\n"
            '{"template_key": "lahom_standard|benissimo_standard|ehf_standard|multi_page_detail|unknown", '
            '"confidence": 0.0-1.0, "reason": "..."}'
        )

        response = client.models.generate_content(
            model=os.environ.get("DESIGNER_GEMINI_MODEL", GEMINI_MODEL),
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )

        import json
        data = json.loads(response.text or "{}")
        template_key = data.get("template_key", "unknown")
        if template_key not in TEMPLATE_KEYS:
            template_key = "unknown"

        return TemplateClassificationResult(
            template_key=template_key,
            confidence=float(data.get("confidence", 0.5)),
            method="gemini",
            page_count=page_count,
            is_multi_page=page_count > 1,
            hints={"reason": data.get("reason", "")},
        )

    except Exception as exc:
        logger.warning("[CLASSIFY] Gemini classification failed: %s, using metadata", exc)
        return fast_result
