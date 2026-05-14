"""FOMS Brain Post-V1 — Vision Extractor.

PV2-B6: fake deterministic extractor + provider adapter interface.

Contract:
- Output is ALWAYS DesignGraphCandidate — never design truth.
- candidate.can_apply() returns False until human approval.
- Real provider is env-gated; unavailable is explicit error (not silent).
- unresolved fields must be empty before apply is permitted.
"""

from __future__ import annotations

import os
import logging
from typing import Any

from foms.services.designer.vision_types import VisionInput, DesignGraphCandidate

logger = logging.getLogger(__name__)

_FAKE_EXTRACTOR = os.environ.get("DESIGNER_FAKE_VISION", "0") == "1"
_VISION_PROVIDER = os.environ.get("DESIGNER_VISION_PROVIDER", "")


# ──────────────────────────────────────────────────────────
# Provider adapter interface
# ──────────────────────────────────────────────────────────

class VisionProviderUnavailable(Exception):
    """Raised when the configured vision provider cannot be reached."""


def _call_real_provider(vision_input: VisionInput) -> dict[str, Any]:
    """Call external OCR/vision provider.

    This is the ONLY place real provider calls should happen.
    Raises VisionProviderUnavailable explicitly — never silent.
    """
    if not _VISION_PROVIDER:
        raise VisionProviderUnavailable(
            "DESIGNER_VISION_PROVIDER is not set. "
            "Set to a supported provider name or use DESIGNER_FAKE_VISION=1."
        )
    # Future: dispatch to provider adapter (Google Vision, Azure CV, etc.)
    raise VisionProviderUnavailable(
        f"Provider {_VISION_PROVIDER!r} is not yet implemented. "
        "Set DESIGNER_FAKE_VISION=1 to use the test extractor."
    )


# ──────────────────────────────────────────────────────────
# Fake deterministic extractor (for tests / MVP)
# ──────────────────────────────────────────────────────────

_FAKE_FIXTURE_DB: dict[str, dict] = {
    "fixture_wardrobe_3000": {
        "furniture_type": "wardrobe",
        "extracted_params": {"width": 3000, "height": 2400, "depth": 620, "module_count": 3},
        "unresolved_fields": [],
        "confidence": 0.92,
    },
    "fixture_wardrobe_2400": {
        "furniture_type": "wardrobe",
        "extracted_params": {"width": 2400, "height": 2200, "depth": 600, "module_count": 2},
        "unresolved_fields": [],
        "confidence": 0.88,
    },
    "fixture_shoe_rack": {
        "furniture_type": "shoe_rack",
        "extracted_params": {"width": 800, "height": 1200, "depth": 350, "tier_count": 4},
        "unresolved_fields": [],
        "confidence": 0.85,
    },
    "fixture_ambiguous": {
        "furniture_type": "wardrobe",
        "extracted_params": {"height": 2200, "depth": 600},
        "unresolved_fields": ["width", "module_count"],
        "confidence": 0.45,
    },
}


def _fake_extract(vision_input: VisionInput) -> dict[str, Any]:
    """Deterministic fake extraction from image metadata."""
    # Use attachment_id or image_url as fixture key
    key = None
    if vision_input.image_url:
        for fixture_key in _FAKE_FIXTURE_DB:
            if fixture_key in vision_input.image_url:
                key = fixture_key
                break
    if key is None and vision_input.attachment_id:
        # Simple mapping: attachment_id % len fixtures
        keys = list(_FAKE_FIXTURE_DB.keys())
        key = keys[vision_input.attachment_id % len(keys)]
    if key is None:
        key = "fixture_wardrobe_2400"  # default fallback

    fixture = _FAKE_FIXTURE_DB[key]
    logger.info("[VISION] fake extractor: fixture=%s confidence=%.2f", key, fixture["confidence"])
    return fixture


# ──────────────────────────────────────────────────────────
# Candidate validator
# ──────────────────────────────────────────────────────────

def _validate_candidate(
    furniture_type: str,
    extracted_params: dict[str, Any],
) -> dict[str, Any]:
    """Run factory validate_params against extracted values."""
    from foms.services.designer.factory_registry import validate_params
    errors = validate_params(furniture_type, extracted_params)
    return {"valid": len(errors) == 0, "errors": errors, "warnings": []}


# ──────────────────────────────────────────────────────────
# Public extraction function
# ──────────────────────────────────────────────────────────

def extract_candidate(vision_input: VisionInput) -> DesignGraphCandidate:
    """Extract a DesignGraphCandidate from a VisionInput.

    Contract:
    - This function NEVER creates or modifies a project version.
    - candidate.approved is always False on exit (human review required).
    - If extraction fails, returns a candidate with high unresolved_fields.

    In fake mode (DESIGNER_FAKE_VISION=1): uses test fixture lookup.
    In real mode: calls configured provider; raises VisionProviderUnavailable if unavailable.
    """
    if _FAKE_EXTRACTOR:
        data = _fake_extract(vision_input)
    else:
        try:
            data = _call_real_provider(vision_input)
        except VisionProviderUnavailable as exc:
            logger.error("[VISION] provider unavailable: %s", exc)
            raise

    furniture_type = data.get("furniture_type") or vision_input.target_furniture_type or "wardrobe"
    extracted_params = data.get("extracted_params", {})
    unresolved = data.get("unresolved_fields", [])
    confidence = float(data.get("confidence", 0.0))

    # Validate extracted params (if any resolved)
    validation_result = None
    validated = False
    if not unresolved and extracted_params:
        validation_result = _validate_candidate(furniture_type, extracted_params)
        validated = validation_result["valid"]

    candidate = DesignGraphCandidate(
        vision_input_id=vision_input.id,
        furniture_type=furniture_type,
        extracted_params=extracted_params,
        unresolved_fields=unresolved,
        confidence=confidence,
        source="fake_extractor" if _FAKE_EXTRACTOR else _VISION_PROVIDER,
        validated=validated,
        validation_result=validation_result,
        approved=False,  # always False — human review required
    )
    return candidate
