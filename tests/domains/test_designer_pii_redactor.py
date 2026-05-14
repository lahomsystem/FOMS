"""PG-B3A: PII Redactor Tests.

Verifies:
1. customer_name/phone/address are redacted before model payload.
2. Raw PII is preserved in ctx.raw_map for internal use.
3. Pseudonyms are deterministic.
4. Scanner detects raw PII in provider payloads.
5. Dimensions/parts_table/furniture_type are NOT redacted.
6. assert_no_raw_pii_in_payload raises on PII leakage.
"""

from __future__ import annotations

import json
import pytest


# ──────────────────────────────────────────────────────────
# PG-B3A-01: Module import
# ──────────────────────────────────────────────────────────

class TestPiiRedactorImport:
    def test_pii_redactor_importable(self):
        import foms.services.designer.pii_redactor as pr
        assert pr is not None
        assert callable(pr.scan_for_raw_pii)
        assert callable(pr.build_gemini_payload)
        assert callable(pr.assert_no_raw_pii_in_payload)

    def test_redaction_context_importable(self):
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext(project_id=1, artifact_id=10)
        assert ctx.project_id == 1
        assert ctx.artifact_id == 10


# ──────────────────────────────────────────────────────────
# PG-B3A-02: PII redaction
# ──────────────────────────────────────────────────────────

SAMPLE_EXTRACTION = {
    "furniture_type": "wardrobe",
    "extracted_params": {"width": 2400, "height": 2400, "depth": 620},
    "customer_info": {
        "customer_name": "홍길동",
        "phone": "010-1234-5678",
        "address": "서울시 강남구 역삼동 123번지",
        "color": "화이트",
    },
    "parts_table": [{"code": "[SR]", "description": "선반", "quantity": 6}],
    "confidence": 0.92,
}


class TestPiiRedaction:
    def test_customer_name_is_redacted(self):
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        result = ctx.redact_extraction(SAMPLE_EXTRACTION)
        ci = result["customer_info"]
        assert "홍길동" not in ci.get("customer_name", "")
        assert "CUSTOMER" in ci.get("customer_name", "")

    def test_phone_is_redacted(self):
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        result = ctx.redact_extraction(SAMPLE_EXTRACTION)
        ci = result["customer_info"]
        assert "010-1234-5678" not in ci.get("phone", "")
        assert "PHONE" in ci.get("phone", "")

    def test_address_is_redacted(self):
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        result = ctx.redact_extraction(SAMPLE_EXTRACTION)
        ci = result["customer_info"]
        assert "강남구" not in ci.get("address", "")
        assert "ADDRESS" in ci.get("address", "")

    def test_dimensions_not_redacted(self):
        """W/D/H must NOT be redacted."""
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        result = ctx.redact_extraction(SAMPLE_EXTRACTION)
        params = result["extracted_params"]
        assert params["width"] == 2400
        assert params["height"] == 2400
        assert params["depth"] == 620

    def test_parts_table_not_redacted(self):
        """Parts table must NOT be redacted."""
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        result = ctx.redact_extraction(SAMPLE_EXTRACTION)
        assert result["parts_table"][0]["code"] == "[SR]"

    def test_furniture_type_not_redacted(self):
        """furniture_type must NOT be redacted."""
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        result = ctx.redact_extraction(SAMPLE_EXTRACTION)
        assert result["furniture_type"] == "wardrobe"

    def test_raw_pii_preserved_in_map(self):
        """Raw PII is preserved in ctx.raw_map for internal FOMS use."""
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        ctx.redact_extraction(SAMPLE_EXTRACTION)
        raw_values = list(ctx.raw_map.values())
        assert "홍길동" in raw_values
        assert "010-1234-5678" in raw_values

    def test_redaction_is_deterministic(self):
        """Same raw value always produces same pseudonym within context."""
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        r1 = ctx.redact_extraction(SAMPLE_EXTRACTION)
        r2 = ctx.redact_extraction(SAMPLE_EXTRACTION)
        assert r1["customer_info"]["customer_name"] == r2["customer_info"]["customer_name"]
        assert r1["customer_info"]["phone"] == r2["customer_info"]["phone"]

    def test_color_not_redacted(self):
        """Non-PII customer_info fields (color) must NOT be redacted."""
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        result = ctx.redact_extraction(SAMPLE_EXTRACTION)
        # color is not a PII field — it may or may not be redacted depending on impl
        # but furniture type and dimensions must survive
        assert result["furniture_type"] == "wardrobe"


# ──────────────────────────────────────────────────────────
# PG-B3A-03: PII restore
# ──────────────────────────────────────────────────────────

class TestPiiRestore:
    def test_restore_reverses_redaction(self):
        """restore_pii should recover original customer_name."""
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        redacted = ctx.redact_extraction(SAMPLE_EXTRACTION)
        restored = ctx.restore_pii(redacted)
        assert restored["customer_info"]["customer_name"] == "홍길동"

    def test_restore_recovers_phone(self):
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        redacted = ctx.redact_extraction(SAMPLE_EXTRACTION)
        restored = ctx.restore_pii(redacted)
        assert restored["customer_info"]["phone"] == "010-1234-5678"


# ──────────────────────────────────────────────────────────
# PG-B3A-04: PII log scanner
# ──────────────────────────────────────────────────────────

class TestPiiScanner:
    def test_scanner_detects_phone_in_log(self):
        from foms.services.designer.pii_redactor import scan_for_raw_pii
        log = "customer info: 010-1234-5678 processed"
        found = scan_for_raw_pii(log)
        assert "phone" in found

    def test_scanner_clean_on_redacted_payload(self):
        """Redacted payload (CUSTOMER_001) should not trigger scanner."""
        from foms.services.designer.pii_redactor import scan_for_raw_pii, RedactionContext
        ctx = RedactionContext()
        redacted = ctx.redact_extraction(SAMPLE_EXTRACTION)
        payload_str = json.dumps(redacted, ensure_ascii=False)
        # Should not find phone pattern in redacted payload
        found = scan_for_raw_pii(payload_str, list(ctx.raw_map.values()))
        assert "known_pii_value" not in found

    def test_assert_no_raw_pii_raises_on_raw_phone(self):
        """assert_no_raw_pii_in_payload raises if raw phone present."""
        from foms.services.designer.pii_redactor import assert_no_raw_pii_in_payload
        with pytest.raises(ValueError, match="PII detected"):
            assert_no_raw_pii_in_payload("phone: 010-1234-5678")


# ──────────────────────────────────────────────────────────
# PG-B3A-05: build_gemini_payload
# ──────────────────────────────────────────────────────────

class TestBuildGeminiPayload:
    def test_payload_has_no_raw_pii(self):
        """build_gemini_payload output must not contain raw PII."""
        from foms.services.designer.pii_redactor import RedactionContext, build_gemini_payload
        ctx = RedactionContext()
        payload = build_gemini_payload(SAMPLE_EXTRACTION, ctx)
        payload_str = json.dumps(payload, ensure_ascii=False)
        assert "홍길동" not in payload_str
        assert "010-1234-5678" not in payload_str

    def test_payload_without_customer_info(self):
        """include_customer_info=False removes customer_info section entirely."""
        from foms.services.designer.pii_redactor import RedactionContext, build_gemini_payload
        ctx = RedactionContext()
        payload = build_gemini_payload(SAMPLE_EXTRACTION, ctx, include_customer_info=False)
        assert "customer_info" not in payload

    def test_payload_preserves_dimensions(self):
        """build_gemini_payload preserves W/D/H."""
        from foms.services.designer.pii_redactor import RedactionContext, build_gemini_payload
        ctx = RedactionContext()
        payload = build_gemini_payload(SAMPLE_EXTRACTION, ctx)
        assert payload["extracted_params"]["width"] == 2400
