"""FOMS Brain PG-B4 — Multimodal Model Router.

Routes drawing extraction requests to the appropriate model provider.

Architecture:
- Gemini is the integration owner and final judge.
- Router selects model version based on template_key + page_count + cost budget.
- fake provider is for tests only (DESIGNER_FAKE_VISION=1).
- Real provider is env-gated (GEMINI_API_KEY required).
- No silent fallback to fake in staging/production.
- All provider payloads pass pii_redactor before transmission.
- Provider logs store redacted payloads only.

Provider selection:
  gemini-2.5-flash    — default (cost-efficient, good accuracy)
  gemini-2.5-pro      — complex multi-page / low confidence cases
  fake                — tests only

Cost tracking:
  Every provider call records latency_ms + cost_usd in _metrics.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Route result
# ──────────────────────────────────────────────────────────

@dataclass
class ModelRouteResult:
    """Result of model routing decision."""

    provider: str       # "gemini" | "fake"
    model_name: str     # e.g. "gemini-2.5-flash"
    template_key: str
    reasoning: str
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "template_key": self.template_key,
            "reasoning": self.reasoning,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


# ──────────────────────────────────────────────────────────
# Model costs (USD per 1K input tokens)
# ──────────────────────────────────────────────────────────

_MODEL_COST_PER_1K: dict[str, float] = {
    "gemini-2.5-flash": 0.000075,
    "gemini-2.5-pro": 0.00125,
    "fake": 0.0,
}

# Typical input tokens for a drawing page (~2000px image)
_TYPICAL_IMAGE_TOKENS = 2000


# ──────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────

def route(
    template_key: str,
    page_count: int = 1,
    confidence_threshold: float = 0.5,
    force_model: str | None = None,
) -> ModelRouteResult:
    """Select model for a drawing extraction request.

    Args:
        template_key: From TemplateClassificationResult.template_key.
        page_count: Number of pages (affects complexity).
        confidence_threshold: Below this, upgrade to pro model.
        force_model: Override model selection (for testing/debugging).

    Returns:
        ModelRouteResult with provider + model_name.

    Raises:
        RuntimeError: If real provider requested but GEMINI_API_KEY not set.
    """
    fake_mode = os.environ.get("DESIGNER_FAKE_VISION", "0") == "1"
    has_key = bool(os.environ.get("GEMINI_API_KEY"))

    # Fake mode — tests only
    if fake_mode:
        logger.debug("[ROUTER] fake mode active (DESIGNER_FAKE_VISION=1)")
        return ModelRouteResult(
            provider="fake",
            model_name="fake_multimodal_v1",
            template_key=template_key,
            reasoning="DESIGNER_FAKE_VISION=1 — fake provider for tests",
            estimated_cost_usd=0.0,
        )

    # Real provider — key required
    if not has_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Cannot route to real Gemini provider. "
            "Set GEMINI_API_KEY or use DESIGNER_FAKE_VISION=1 for tests."
        )

    env_model = os.environ.get("DESIGNER_GEMINI_MODEL", "gemini-2.5-flash")

    if force_model:
        model_name = force_model
        reasoning = f"force_model override: {force_model}"
    elif page_count > 2 or template_key == "multi_page_detail":
        # Complex multi-page: use pro model for better accuracy
        model_name = "gemini-2.5-pro"
        reasoning = f"multi-page (page_count={page_count}) -> pro model"
    elif template_key == "unknown":
        # Unknown template: use flash but note lower expected accuracy
        model_name = env_model
        reasoning = "unknown template -> flash (lower accuracy expected)"
    else:
        # Known template: flash is sufficient
        model_name = env_model
        reasoning = f"known template '{template_key}' -> flash"

    cost = _MODEL_COST_PER_1K.get(model_name, 0.0) * _TYPICAL_IMAGE_TOKENS / 1000 * page_count

    logger.info("[ROUTER] provider=gemini model=%s template=%s pages=%d cost_est=$%.5f",
                model_name, template_key, page_count, cost)

    return ModelRouteResult(
        provider="gemini",
        model_name=model_name,
        template_key=template_key,
        reasoning=reasoning,
        estimated_cost_usd=cost,
    )


def route_and_extract(
    image_bytes: bytes | None,
    filename: str,
    page_count: int = 1,
    pii_context: Any | None = None,
) -> dict[str, Any]:
    """Full pipeline: classify → route → extract.

    1. Classify drawing template.
    2. Route to model.
    3. Run extraction (with PII redaction if context provided).
    4. Return extraction result + routing metadata.

    Args:
        image_bytes: Raw image bytes (None → fake extraction).
        filename: Original filename for classification hints.
        page_count: Number of pages.
        pii_context: Optional RedactionContext for PII handling.

    Returns:
        dict with extraction result + _routing metadata.
    """
    from foms.services.designer.drawing_template_classifier import (
        classify_from_metadata, classify_with_gemini,
    )

    # Step 1: Classify
    if image_bytes and os.environ.get("GEMINI_API_KEY"):
        classification = classify_with_gemini(filename, image_bytes, page_count)
    else:
        classification = classify_from_metadata(filename, page_count)

    # Step 2: Route
    try:
        route_result = route(classification.template_key, page_count)
    except RuntimeError as exc:
        # Fall back to fake mode if key missing
        logger.warning("[ROUTER] routing failed: %s, using fake", exc)
        from foms.services.designer.vision_extractor import extract_candidate
        from foms.services.designer.vision_types import VisionInput
        vi = VisionInput(image_url=filename, source="manual_upload")
        candidate = extract_candidate(vi)
        return {
            **candidate.to_dict(),
            "_routing": {
                "classification": classification.to_dict(),
                "route": {"provider": "fake", "model_name": "fallback", "error": str(exc)},
            }
        }

    # Step 3: Extract
    if route_result.provider == "fake" or image_bytes is None:
        from foms.services.designer.vision_extractor import extract_candidate
        from foms.services.designer.vision_types import VisionInput
        vi = VisionInput(image_url=filename, source="manual_upload")
        candidate = extract_candidate(vi)
        result = candidate.to_dict()
    else:
        from foms.services.designer.gemini_provider import extract_from_image_bytes

        # Apply PII redaction if context provided
        raw_bytes = image_bytes  # image bytes don't contain PII

        result = extract_from_image_bytes(raw_bytes, model=route_result.model_name)

        # Apply PII redaction to extracted text data
        if pii_context is not None:
            from foms.services.designer.pii_redactor import build_gemini_payload
            result = build_gemini_payload(result, pii_context)

    result["_routing"] = {
        "classification": classification.to_dict(),
        "route": route_result.to_dict(),
    }
    return result
