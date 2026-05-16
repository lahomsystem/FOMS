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
GEMINI_TIMEOUT_SECONDS = 90

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

_EXTRACTION_PROMPT = """당신은 한국 가구 도면 전문 설계 이해 AI입니다.
목표는 단순 치수 OCR이 아니라, 도면의 가구 설계 의도와 조립 구조를 이해하여
FOMS Brain Designer가 재사용 가능한 설계 블록/규칙/재질 후보를 학습할 수 있게 하는 것입니다.
제공된 가구 도면 이미지를 분석하여 아래 JSON 형식으로 정확하게 추출하세요.

규칙:
1. 모든 치수는 밀리미터(mm) 단위입니다. 단위 표시 없는 숫자도 mm로 처리합니다.
2. 도면에서 명확히 읽을 수 있는 값만 확정값으로 추출하세요. 추측하지 마세요.
3. 읽을 수 없거나 도면에 없는 필드는 unresolved_fields에 추가하세요.
4. furniture_type은 3D 생성/검증용 상위 실행 타입입니다. 반드시 다음 중 가장 가까운 하나를 선택하세요:
   wardrobe / shoe_rack / kitchen_base / kitchen_wall / custom_storage
   단, 새로운 커스텀 디자인 카테고리는 furniture_type을 새 문자열로 만들지 말고
   design_understanding.learned_design_category에 후보로 기록하세요.
5. confidence는 0.0(데이터 없음)~1.0(완전히 확신) 범위입니다.
6. parts_table의 code는 [SR], [EP], [DOOR], [마이다], [옷봉], 보조목 등을 그대로 추출합니다.
7. 설계 이해는 layout_graph, block_candidates, materials_textures, construction_rules에 기록하세요.
8. 새 블록/규칙은 "후보"로만 기록하세요. 프로그램에 자동 반영할 확정값처럼 쓰지 마세요.
9. 확정 치수와 추론한 설계 패턴을 구분하세요. 추론은 confidence와 evidence를 함께 기록하세요.
10. custom_storage처럼 기존 분류로 부족한 디자인은 learned_design_category.is_new_category_candidate=true로 두고,
    category_key, label_ko, similarity_tags, layout_signature를 기록하세요.
11. 비슷한 도면들이 나중에 자동 그루핑될 수 있도록 similarity_tags와 layout_signature는 일관된 짧은 키로 작성하세요.
12. design_understanding.outline_polygon에 도면 외관 폴리곤을 추출하세요.
    - view: 도면 투영 방향 (front/side/top)
    - vertices_mm: mm 단위 꼭짓점 좌표 목록 (시계 반대 방향 또는 시계 방향 순서)
    - shape_type: rect(직사각형)/L_shape(ㄱ자)/T_shape(ㅜ자)/U_shape(ㄷ자)/irregular(기타)
    - 도면에서 외관선이 명확하지 않으면 outline_polygon을 null로 반환하세요.

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
  "design_understanding": {
    "layout_graph": {
      "coordinate_system": "front_view_mm",
      "overall_shape": null,
      "zones": [
        {
          "id": "zone_1",
          "role": "hanging|shelves|drawers|appliance|open_space|unknown",
          "x_mm": null,
          "y_mm": null,
          "width_mm": null,
          "height_mm": null,
          "depth_mm": null,
          "evidence": "dimension_line|parts_table|visual_layout|text_label"
        }
      ],
      "modules": [
        {
          "id": "module_1",
          "type": "vertical_bay|drawer_stack|shelf_stack|door_panel|side_panel|top_panel|bottom_panel|rail|hardware|unknown",
          "position": {"x_mm": null, "y_mm": null, "z_mm": null},
          "dimensions": {"width_mm": null, "height_mm": null, "depth_mm": null},
          "relations": ["left_of:module_2", "contains:part_1"],
          "confidence": 0.0
        }
      ]
    },
    "block_candidates": [
      {
        "block_key": "wardrobe.vertical_bay.shelf_stack",
        "label": "재사용 가능한 설계 블록명",
        "furniture_types": ["wardrobe"],
        "factory_params": {},
        "constraints": [],
        "source_evidence": [],
        "confidence": 0.0
      }
    ],
    "learned_design_category": {
      "category_key": null,
      "label_ko": null,
      "base_furniture_type": "custom_storage",
      "is_new_category_candidate": false,
      "similarity_tags": [],
      "layout_signature": {
        "module_pattern": null,
        "zone_roles": [],
        "dominant_structure": null,
        "material_signature": [],
        "hardware_signature": []
      },
      "grouping_hints": {
        "similar_to_known": [],
        "distinguishing_features": [],
        "evidence": []
      },
      "confidence": 0.0
    },
    "materials_textures": [
      {
        "part": "door|body|shelf|hardware|unknown",
        "material": null,
        "color": null,
        "texture": null,
        "evidence": "text_label|visual_pattern|unknown",
        "confidence": 0.0
      }
    ],
    "hardware_and_joinery": [
      {
        "name": null,
        "code": null,
        "quantity": null,
        "used_for": null,
        "confidence": 0.0
      }
    ],
    "construction_rules": [
      {
        "rule_key": "module_width_sum_equals_total_width",
        "description": "설계/시공 규칙",
        "condition": null,
        "formula": null,
        "evidence": [],
        "confidence": 0.0
      }
    ],
    "dimension_rules": [
      {
        "target": "width|height|depth|module_width|gap|offset",
        "formula": null,
        "source_dimensions": [],
        "confidence": 0.0
      }
    ],
    "learning_summary": {
      "reusable_patterns": [],
      "new_module_candidates": [],
      "uncertain_design_points": []
    },
    "outline_polygon": {
      "view": "front",
      "vertices_mm": [[0,0], [2288,0], [2288,1880], [1376,1880], [1376,2225], [0,2225]],
      "shape_type": "L_shape",
      "confidence": 0.9
    }
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
        from google.genai import types
        return genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=_get_timeout_ms()),
        )
    except ImportError as exc:
        raise GeminiProviderError(
            "google-genai package not installed. "
            "Run: pip install google-genai"
        ) from exc


def _get_timeout_seconds() -> int:
    raw = os.environ.get("DESIGNER_GEMINI_TIMEOUT_SECONDS", str(GEMINI_TIMEOUT_SECONDS))
    try:
        value = int(raw)
    except ValueError as exc:
        raise GeminiProviderError(
            "DESIGNER_GEMINI_TIMEOUT_SECONDS must be an integer number of seconds."
        ) from exc
    if value < 10 or value > 600:
        raise GeminiProviderError(
            "DESIGNER_GEMINI_TIMEOUT_SECONDS must be between 10 and 600 seconds."
        )
    return value


def _get_timeout_ms() -> int:
    return _get_timeout_seconds() * 1000


def _format_gemini_call_error(exc: Exception, elapsed_ms: int) -> str:
    timeout_ms = _get_timeout_ms()
    if elapsed_ms >= timeout_ms - 1000:
        return (
            f"Gemini API call timed out after {_get_timeout_seconds()}s "
            f"(configured by DESIGNER_GEMINI_TIMEOUT_SECONDS)."
        )
    return f"Gemini API call failed after {elapsed_ms}ms: {exc}"


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
        timeout_ms = _get_timeout_ms()
        logger.info(
            "[GEMINI] extraction start model=%s mime=%s bytes=%d timeout_ms=%d",
            model_name, mime_type, len(image_bytes), timeout_ms,
        )
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _EXTRACTION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,  # deterministic extraction
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=timeout_ms),
            ),
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        raise GeminiProviderError(_format_gemini_call_error(exc, elapsed_ms)) from exc

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
        timeout_ms = _get_timeout_ms()
        response = client.models.generate_content(
            model=model_name,
            contents=_CONNECTIVITY_PROMPT,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=timeout_ms),
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
        error = _format_gemini_call_error(exc, latency_ms)
        logger.error("[GEMINI] connectivity FAILED model=%s error=%s", model_name, error)
        return {"ok": False, "model": model_name, "latency_ms": latency_ms, "error": error}


# ──────────────────────────────────────────────────────────
# Cost estimation
# ──────────────────────────────────────────────────────────

# Gemini Developer API paid standard tier, USD per 1M tokens.
# Default cost estimate follows the current dev extraction model: gemini-2.5-flash.
# Output price includes thinking tokens for models that report them.
_DEFAULT_PRICING_MODEL = "gemini-2.5-flash"
_MODEL_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "gemini-3.1-pro-preview": {
        "input_le_200k": 2.00,
        "output_le_200k": 12.00,
        "input_gt_200k": 4.00,
        "output_gt_200k": 18.00,
    },
    "gemini-3.1-pro-preview-customtools": {
        "input_le_200k": 2.00,
        "output_le_200k": 12.00,
        "input_gt_200k": 4.00,
        "output_gt_200k": 18.00,
    },
    "gemini-2.5-flash": {
        "input_le_200k": 0.30,
        "output_le_200k": 2.50,
        "input_gt_200k": 0.30,
        "output_gt_200k": 2.50,
    },
    "gemini-2.5-pro": {
        "input_le_200k": 1.25,
        "output_le_200k": 10.00,
        "input_gt_200k": 2.50,
        "output_gt_200k": 15.00,
    },
    "gemini-2.0-flash": {
        "input_le_200k": 0.10,
        "output_le_200k": 0.40,
        "input_gt_200k": 0.10,
        "output_gt_200k": 0.40,
    },
    "gemini-2.0-flash-001": {
        "input_le_200k": 0.10,
        "output_le_200k": 0.40,
        "input_gt_200k": 0.10,
        "output_gt_200k": 0.40,
    },
    "gemini-2.0-flash-lite": {
        "input_le_200k": 0.05,
        "output_le_200k": 0.20,
        "input_gt_200k": 0.05,
        "output_gt_200k": 0.20,
    },
    "gemini-2.0-flash-lite-001": {
        "input_le_200k": 0.05,
        "output_le_200k": 0.20,
        "input_gt_200k": 0.05,
        "output_gt_200k": 0.20,
    },
}


def estimate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    model_name: str | None = None,
) -> float:
    """Return estimated USD cost for a single Gemini call.

    Uses gemini-2.5-flash pricing by default. Gemini 3.1 Pro pricing remains
    available when model_name explicitly points to a 3.1 Pro model. Output token
    counts include thinking tokens when the API reports them in candidates_token_count.
    """
    model = model_name or os.environ.get("DESIGNER_GEMINI_MODEL", _DEFAULT_PRICING_MODEL)
    pricing = _MODEL_PRICING_PER_1M.get(model, _MODEL_PRICING_PER_1M[_DEFAULT_PRICING_MODEL])
    suffix = "gt_200k" if input_tokens > 200_000 else "le_200k"
    input_cost = input_tokens * pricing[f"input_{suffix}"] / 1_000_000
    output_cost = output_tokens * pricing[f"output_{suffix}"] / 1_000_000
    return input_cost + output_cost


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
    data.setdefault("design_understanding", {})
    data.setdefault("unresolved_fields", [])
    data.setdefault("confidence", 0.0)

    # Attach provider metrics (prefixed with _ to distinguish from extraction data)
    cost_usd = estimate_cost_usd(input_tokens, output_tokens, model_name=model_name)
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
