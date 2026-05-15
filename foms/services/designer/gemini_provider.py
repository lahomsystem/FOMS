"""FOMS Brain PG-B0A — Gemini Vision Provider.

Single-model Gemini adapter for Korean furniture drawing extraction.

Architecture contract:
- GEMINI_API_KEY environment variable required. Never hardcoded.
- DESIGNER_GEMINI_MODEL env var selects model (default: gemini-3.1-pro-preview).
- All calls are logged with latency_ms and token usage for cost tracking.
- Returns raw extraction dict matching extract_candidate() interface.
- PII fields (customer_name, phone, address) are returned RAW here.
  PII redaction (PG-B3A pii_redactor.py) happens BEFORE calling this provider.
- This provider never creates project versions or auto-approves candidates.
- On error: raises GeminiProviderError (never silently returns partial data).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Environment config
# ──────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Default model: gemini-3.1-pro-preview (Gemini 3.1 Pro Preview — billing required)
# Override with DESIGNER_GEMINI_MODEL env var (e.g. gemini-2.5-flash for cost)
GEMINI_MODEL = os.environ.get("DESIGNER_GEMINI_MODEL", "gemini-3.1-pro-preview")

# Valid furniture types (must match VALID_FURNITURE_TYPES in vision_types.py)
_VALID_FURNITURE_TYPES = frozenset(
    {"wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"}
)

# ──────────────────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────────────────


class GeminiProviderError(Exception):
    """Raised on any Gemini API or parsing error. Never silent."""


class GeminiAPIKeyMissing(GeminiProviderError):
    """Raised when GEMINI_API_KEY is not set."""


# ──────────────────────────────────────────────────────────
# Extraction prompt
# ──────────────────────────────────────────────────────────

_EXTRACTION_PROMPT = """당신은 한국 가구 도면 전문 데이터 추출 AI입니다.
제공된 가구 도면 이미지를 분석하여 아래 JSON 형식으로 정확하게 정보를 추출하세요.

규칙:
1. 모든 치수는 밀리미터(mm) 단위입니다. 단위 표시 없는 숫자도 mm로 처리합니다.
2. 도면에서 명확히 읽을 수 있는 값만 추출하세요. 추측하지 마세요.
3. 읽을 수 없거나 도면에 없는 필드는 unresolved_fields에 추가하세요.
4. furniture_type은 반드시 다음 중 하나여야 합니다:
   wardrobe / shoe_rack / kitchen_base / kitchen_wall / custom_storage
5. confidence는 0.0(데이터 없음)~1.0(완전히 확신) 범위입니다.
6. parts_table의 code는 [SR], [EP], [DOOR], [마이다], [옷봉], 보조목 등을 그대로 추출합니다.

다음 JSON 구조로만 응답하세요 (JSON 외 텍스트 금지):
{
  "furniture_type": "wardrobe",
  "extracted_params": {
    "width": null,
    "depth": null,
    "height": null,
    "module_count": null,
    "module_widths": [],
    "door_count": null,
    "drawer_count": null,
    "shelf_count": null
  },
  "parts_table": [
    {"code": "[SR]", "description": "선반", "quantity": 3}
  ],
  "customer_info": {
    "customer_name": null,
    "phone": null,
    "address": null,
    "product_name": null,
    "color": null
  },
  "drawing_meta": {
    "page_number": null,
    "view_type": "front",
    "drawing_style": "technical"
  },
  "unresolved_fields": [],
  "confidence": 0.0
}"""

_CONNECTIVITY_PROMPT = (
    "FOMS Brain Gemini connectivity check. "
    "Reply with exactly: {\"status\": \"ok\", \"model\": \"<model name>\"}"
)


# ──────────────────────────────────────────────────────────
# Client factory (lazy — avoids import cost at startup)
# ──────────────────────────────────────────────────────────

def _get_client():
    """Return authenticated google.genai Client. Raises GeminiAPIKeyMissing if no key.

    Always reads GEMINI_API_KEY dynamically from os.environ at call time
    so tests can pop/restore the env var reliably.
    """
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise GeminiAPIKeyMissing(
            "GEMINI_API_KEY environment variable is not set. "
            "Set it in Railway secrets or local .env file. "
            "Never hardcode the key in source code."
        )
    try:
        from google import genai
        return genai.Client(api_key=key)
    except ImportError as exc:
        raise GeminiProviderError(
            "google-genai package not installed. "
            "Run: pip install google-genai"
        ) from exc


# ──────────────────────────────────────────────────────────
# Core extraction
# ──────────────────────────────────────────────────────────

def extract_from_image_bytes(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    model: str | None = None,
) -> dict[str, Any]:
    """Call Gemini with raw image bytes and return extraction dict.

    Args:
        image_bytes: Raw image data (JPEG, PNG, PDF page, etc.)
        mime_type: MIME type of image_bytes.
        model: Gemini model name (defaults to DESIGNER_GEMINI_MODEL env var).

    Returns:
        dict with keys: furniture_type, extracted_params, parts_table,
        customer_info, drawing_meta, unresolved_fields, confidence,
        _metrics (latency_ms, input_tokens, output_tokens, model).

    Raises:
        GeminiProviderError: On any API or parsing error.
        GeminiAPIKeyMissing: If GEMINI_API_KEY not set.
    """
    client = _get_client()
    model_name = model or os.environ.get("DESIGNER_GEMINI_MODEL", GEMINI_MODEL)

    try:
        from google.genai import types
    except ImportError as exc:
        raise GeminiProviderError("google-genai types not available") from exc

    t0 = time.monotonic()
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _EXTRACTION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,  # deterministic extraction
                response_mime_type="application/json",
            ),
        )
    except Exception as exc:
        raise GeminiProviderError(f"Gemini API call failed: {exc}") from exc

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Token usage
    input_tokens = getattr(getattr(response, "usage_metadata", None), "prompt_token_count", 0) or 0
    output_tokens = getattr(getattr(response, "usage_metadata", None), "candidates_token_count", 0) or 0

    raw_text = response.text or ""
    logger.info(
        "[GEMINI] model=%s latency_ms=%d in_tok=%d out_tok=%d",
        model_name, latency_ms, input_tokens, output_tokens,
    )

    return _parse_and_validate(raw_text, model_name, latency_ms, input_tokens, output_tokens)


def extract_from_image_path(
    image_path: str | Path,
    model: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper: load image file and call extract_from_image_bytes."""
    path = Path(image_path)
    if not path.exists():
        raise GeminiProviderError(f"Image file not found: {path}")
    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".pdf": "application/pdf",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(suffix, "image/jpeg")
    image_bytes = path.read_bytes()
    return extract_from_image_bytes(image_bytes, mime_type=mime_type, model=model)


def extract_from_url(
    image_url: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Download image from URL and call extract_from_image_bytes."""
    try:
        import urllib.request
        with urllib.request.urlopen(image_url, timeout=30) as resp:
            image_bytes = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    except Exception as exc:
        raise GeminiProviderError(f"Failed to download image from {image_url}: {exc}") from exc
    return extract_from_image_bytes(image_bytes, mime_type=content_type, model=model)


# ──────────────────────────────────────────────────────────
# Connectivity check
# ──────────────────────────────────────────────────────────

def check_connectivity(model: str | None = None) -> dict[str, Any]:
    """Send a minimal text-only ping to verify API key and connectivity.

    Returns:
        dict with keys: ok (bool), model, latency_ms, error (str or None).
    """
    client = _get_client()
    model_name = model or os.environ.get("DESIGNER_GEMINI_MODEL", GEMINI_MODEL)
    t0 = time.monotonic()
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=model_name,
            contents=_CONNECTIVITY_PROMPT,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        raw = response.text or "{}"
        data = json.loads(raw)
        logger.info("[GEMINI] connectivity OK model=%s latency_ms=%d", model_name, latency_ms)
        return {"ok": data.get("status") == "ok", "model": model_name, "latency_ms": latency_ms, "error": None}
    except GeminiAPIKeyMissing:
        raise
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("[GEMINI] connectivity FAILED model=%s error=%s", model_name, exc)
        return {"ok": False, "model": model_name, "latency_ms": latency_ms, "error": str(exc)}


# ──────────────────────────────────────────────────────────
# Cost estimation
# ──────────────────────────────────────────────────────────

# Gemini 2.0 Flash pricing (2026-05 per Google AI pricing page)
# Input: $0.075 / 1M tokens | Output: $0.30 / 1M tokens
_COST_PER_INPUT_TOKEN = 0.075 / 1_000_000
_COST_PER_OUTPUT_TOKEN = 0.30 / 1_000_000


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for a single extraction call."""
    return (input_tokens * _COST_PER_INPUT_TOKEN) + (output_tokens * _COST_PER_OUTPUT_TOKEN)


# ──────────────────────────────────────────────────────────
# Response parser
# ──────────────────────────────────────────────────────────

def _parse_and_validate(
    raw_text: str,
    model_name: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    """Parse Gemini JSON response and attach metrics. Raises GeminiProviderError on bad JSON."""
    # Strip markdown fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiProviderError(
            f"Gemini returned non-JSON response. "
            f"raw={raw_text[:200]!r} error={exc}"
        ) from exc

    # Normalize furniture_type
    ft = data.get("furniture_type", "custom_storage")
    if ft not in _VALID_FURNITURE_TYPES:
        logger.warning("[GEMINI] unknown furniture_type=%r, defaulting to custom_storage", ft)
        data["furniture_type"] = "custom_storage"

    # Ensure required keys
    data.setdefault("extracted_params", {})
    data.setdefault("parts_table", [])
    data.setdefault("customer_info", {})
    data.setdefault("drawing_meta", {})
    data.setdefault("unresolved_fields", [])
    data.setdefault("confidence", 0.0)

    # Attach provider metrics (prefixed with _ to distinguish from extraction data)
    cost_usd = estimate_cost_usd(input_tokens, output_tokens)
    data["_metrics"] = {
        "model": model_name,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
    }

    logger.info(
        "[GEMINI] extraction ok furniture_type=%s confidence=%.2f cost_usd=%.4f",
        data["furniture_type"], data["confidence"], cost_usd,
    )
    return data
