"""FOMS Brain PG-B3A — PII Redaction + Model Payload Builder.

Redacts customer PII (name/phone/address) before sending to external AI models.

Contract:
- raw PII (customer_name, phone, address) stays inside FOMS service boundary.
- Gemini API payload receives CUSTOMER_001/PHONE_001/ADDRESS_001 pseudonyms.
- Mapping is deterministic per (project_id, artifact_id) scope.
- provider request logs must never contain raw PII values.
- model output is re-linkable to raw PII only inside FOMS boundary.
- provider response logs are scanned before persistence (scan_response_for_raw_pii).

Usage:
    from foms.services.designer.pii_redactor import RedactionContext, build_redacted_payload

    ctx = RedactionContext(project_id=1, artifact_id=10)
    redacted = ctx.redact_extraction(raw_extraction)
    # Send redacted to Gemini
    ctx.raw_map  # preserved internally for ERP/user workflows
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# PII field patterns
# ──────────────────────────────────────────────────────────

# Korean phone patterns: 010-1234-5678, 02-1234-5678, 010 1234 5678 etc.
_PHONE_PATTERN = re.compile(
    r'(?:0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4})'
)

# Free-text redaction patterns used for human-authored explanation/RAG text.
_NAME_CONTEXT_PATTERN = re.compile(
    r'(?P<label>고객|고객명|성함|이름)\s*[:：]?\s*(?P<name>[가-힣]{2,5})'
)
_HONORIFIC_NAME_PATTERN = re.compile(r'(?P<name>[가-힣]{2,5})(?=님)')
_ADDRESS_FRAGMENT_PATTERN = re.compile(
    r'((?:[가-힣A-Za-z0-9]+(?:시|도|군|구|읍|면|동|로|길)\s*){2,}'
    r'(?:\d+(?:-\d+)?(?:번지)?\s*)?(?:\d+호)?)'
)

# Korean address indicators (partial — for log scanning only)
_ADDRESS_KEYWORDS = {"시", "구", "동", "로", "길", "아파트", "빌라", "번지", "호"}


# ──────────────────────────────────────────────────────────
# Redaction context
# ──────────────────────────────────────────────────────────

@dataclass
class RedactionContext:
    """Holds raw→pseudonym mapping for a drawing intake session.

    Scope: per (project_id, artifact_id) pair.
    Mapping is deterministic: same input always produces same pseudonym within scope.
    """

    project_id: int | None = None
    artifact_id: int | None = None
    raw_map: dict[str, str] = field(default_factory=dict)  # pseudonym → raw value

    def _get_or_create_pseudonym(self, field_type: str, raw_value: str, index: int = 1) -> str:
        """Return pseudonym for a raw PII value, creating mapping if needed."""
        if not raw_value:
            return raw_value
        pseudonym = f"{field_type.upper()}_{index:03d}"
        # Only store if not already mapped
        if pseudonym not in self.raw_map:
            self.raw_map[pseudonym] = raw_value
            logger.debug("[PII] mapped %s -> %r (raw preserved internally)", pseudonym, raw_value[:3] + "***")
        return pseudonym

    def redact_extraction(self, extraction: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of extraction with PII fields pseudonymized.

        Modifies:
          extraction['customer_info']['customer_name'] -> CUSTOMER_001
          extraction['customer_info']['phone'] -> PHONE_001
          extraction['customer_info']['address'] -> ADDRESS_001

        Does NOT modify:
          - dimensions (W/D/H)
          - parts_table
          - furniture_type
          - any non-PII fields
        """
        import copy
        redacted = copy.deepcopy(extraction)

        ci = redacted.get("customer_info") or redacted.get("_customer_info") or {}
        if not ci:
            return redacted

        idx = 1
        if ci.get("customer_name"):
            ci["customer_name"] = self._get_or_create_pseudonym("CUSTOMER", ci["customer_name"], idx)
            idx += 1
        if ci.get("phone"):
            ci["phone"] = self._get_or_create_pseudonym("PHONE", ci["phone"], 1)
        if ci.get("address"):
            ci["address"] = self._get_or_create_pseudonym("ADDRESS", ci["address"], 1)

        # Update in redacted dict
        if "customer_info" in redacted:
            redacted["customer_info"] = ci
        if "_customer_info" in redacted:
            redacted["_customer_info"] = ci

        return redacted

    def restore_pii(self, redacted: dict[str, Any]) -> dict[str, Any]:
        """Restore raw PII values from pseudonyms (FOMS internal use only)."""
        import copy
        restored = copy.deepcopy(redacted)
        _restore_dict(restored, self.raw_map)
        return restored

    def get_raw_mapping(self) -> dict[str, str]:
        """Return pseudonym→raw mapping for internal storage."""
        return dict(self.raw_map)


def _restore_dict(obj: Any, mapping: dict[str, str]) -> None:
    """Recursively replace pseudonym values with raw values."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v in mapping:
                obj[k] = mapping[v]
            else:
                _restore_dict(v, mapping)
    elif isinstance(obj, list):
        for item in obj:
            _restore_dict(item, mapping)


# ──────────────────────────────────────────────────────────
# Log scanner — check for raw PII leakage
# ──────────────────────────────────────────────────────────

def scan_for_raw_pii(text: str, known_raw_values: list[str] | None = None) -> list[str]:
    """Scan a string (log line, JSON dump) for raw PII indicators.

    Returns list of detected PII type strings (e.g. ["phone", "address"]).
    Used to validate provider request/response logs before persistence.

    Args:
        text: String to scan.
        known_raw_values: Optional list of known raw PII values to check for exact matches.

    Returns:
        List of PII type strings found (empty = clean).
    """
    found: list[str] = []

    # Check for phone-like patterns
    if _PHONE_PATTERN.search(text):
        found.append("phone")

    # Check for address keywords
    words = set(text.split())
    if words & _ADDRESS_KEYWORDS:
        found.append("address")

    # Check against known raw values (exact match)
    if known_raw_values:
        for raw in known_raw_values:
            if raw and len(raw) >= 3 and raw in text:
                found.append("known_pii_value")
                break

    return found


def redact_raw_pii_text(
    text: str,
    known_raw_values: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Redact raw PII from free-form text before persistence or RAG.

    This is intentionally conservative: it removes clear phone/address/name
    patterns and exact known values while leaving dimensions, part names, and
    design rationale intact.

    Returns:
        (redacted_text, detected_types)
    """
    if not text:
        return text, []

    redacted = text
    found: list[str] = []

    if known_raw_values:
        for raw in known_raw_values:
            if raw and len(raw) >= 2 and raw in redacted:
                redacted = redacted.replace(raw, "[PII_REDACTED]")
                if "known_pii_value" not in found:
                    found.append("known_pii_value")

    redacted, phone_count = _PHONE_PATTERN.subn("[PHONE_REDACTED]", redacted)
    if phone_count:
        found.append("phone")

    def _redact_name(match: re.Match[str]) -> str:
        label = match.group("label")
        return f"{label} [CUSTOMER_REDACTED]"

    redacted, name_count = _NAME_CONTEXT_PATTERN.subn(_redact_name, redacted)
    if name_count:
        found.append("customer_name")

    redacted, honorific_count = _HONORIFIC_NAME_PATTERN.subn("[CUSTOMER_REDACTED]", redacted)
    if honorific_count:
        found.append("customer_name")

    redacted, address_count = _ADDRESS_FRAGMENT_PATTERN.subn("[ADDRESS_REDACTED]", redacted)
    if address_count:
        found.append("address")

    # Run the existing scanner as a safety net for patterns not replaced above.
    for pii_type in scan_for_raw_pii(redacted, known_raw_values=None):
        if pii_type not in found:
            found.append(pii_type)

    return redacted, found


def assert_no_raw_pii_in_payload(payload: str, known_raw_values: list[str] | None = None) -> None:
    """Assert that a provider payload string contains no raw PII.

    Raises:
        ValueError: If PII is detected in the payload.
    """
    found = scan_for_raw_pii(payload, known_raw_values)
    if found:
        raise ValueError(
            f"PII detected in provider payload: {found}. "
            "Apply redact_extraction() before sending to external model. "
            "Raw PII must never appear in provider request logs."
        )


# ──────────────────────────────────────────────────────────
# Model payload builder
# ──────────────────────────────────────────────────────────

def build_gemini_payload(
    extraction: dict[str, Any],
    ctx: RedactionContext,
    include_customer_info: bool = True,
) -> dict[str, Any]:
    """Build a Gemini-safe payload from extraction data.

    1. Redacts PII from customer_info.
    2. Validates no raw PII in output.
    3. Returns payload ready for Gemini API.

    Args:
        extraction: Raw extraction dict (may contain PII).
        ctx: RedactionContext for PII mapping.
        include_customer_info: If True, include redacted customer_info in payload.

    Returns:
        dict with PII replaced by pseudonyms.

    Raises:
        ValueError: If PII leaks through redaction (safety gate).
    """
    redacted = ctx.redact_extraction(extraction)

    if not include_customer_info:
        redacted.pop("customer_info", None)
        redacted.pop("_customer_info", None)

    # Safety gate: scan redacted payload for raw PII
    import json
    payload_str = json.dumps(redacted, ensure_ascii=False)
    known_raw = list(ctx.raw_map.values())
    assert_no_raw_pii_in_payload(payload_str, known_raw)

    return redacted
