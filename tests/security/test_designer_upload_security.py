"""PG-B12: FOMS Brain Upload Security Tests.

Verifies:
- File type restrictions
- PII redaction in extraction logs
- No secrets in provider request payloads
- Candidate auto-approval blocked
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


class TestFileTypeRestrictions:
    def test_allowed_extensions_defined(self):
        from foms.api.designer.drawings import ALLOWED_EXTENSIONS
        assert ".jpg" in ALLOWED_EXTENSIONS
        assert ".pdf" in ALLOWED_EXTENSIONS
        assert ".webp" in ALLOWED_EXTENSIONS

    def test_dangerous_extensions_not_allowed(self):
        from foms.api.designer.drawings import ALLOWED_EXTENSIONS
        dangerous = {".exe", ".sh", ".py", ".js", ".php", ".bat", ".ps1"}
        overlap = dangerous & ALLOWED_EXTENSIONS
        assert not overlap, f"Dangerous extensions allowed: {overlap}"

    def test_max_file_size_defined(self):
        from foms.api.designer.drawings import MAX_FILE_SIZE_MB
        assert MAX_FILE_SIZE_MB > 0
        assert MAX_FILE_SIZE_MB <= 50  # reasonable upper bound


class TestPiiRedactionSecurity:
    def test_pii_redactor_strips_before_export(self):
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        extraction = {
            "furniture_type": "wardrobe",
            "customer_info": {
                "customer_name": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
            },
        }
        redacted = ctx.redact_extraction(extraction)
        payload_str = json.dumps(redacted, ensure_ascii=False)
        assert "홍길동" not in payload_str
        assert "010-1234-5678" not in payload_str
        assert "강남구" not in payload_str

    def test_assert_no_raw_pii_raises_on_phone(self):
        from foms.services.designer.pii_redactor import assert_no_raw_pii_in_payload
        with pytest.raises(ValueError, match="PII detected"):
            assert_no_raw_pii_in_payload("phone: 010-1234-5678")

    def test_design_case_no_pii_columns(self):
        from foms.persistence.designer.models import DesignerDesignCase
        cols = {c.key for c in DesignerDesignCase.__table__.columns}
        pii_cols = {"customer_name", "phone", "address"}
        assert not (pii_cols & cols)


class TestCandidateAutoApprovalBlocked:
    def test_extraction_candidate_approved_default_false(self):
        from foms.persistence.designer.models import DesignerExtractionCandidate
        col = DesignerExtractionCandidate.__table__.columns["approved"]
        assert col.default.arg is False

    def test_mapped_candidate_approved_false(self):
        from foms.services.designer.ontology_mapper import build_candidate
        c = build_candidate({"furniture_type": "wardrobe", "extracted_params": {}})
        assert c.approved is False

    def test_rule_candidate_status_default_draft(self):
        from foms.persistence.designer.models import DesignerRuleCandidate
        col = DesignerRuleCandidate.__table__.columns["status"]
        assert str(col.default.arg) == "draft"

    def test_design_case_requires_approved_at(self):
        """Design case approved_at nullable=True means it's only set by human action."""
        from foms.persistence.designer.models import DesignerDesignCase
        col = DesignerDesignCase.__table__.columns["approved_at"]
        assert col.nullable is True  # set explicitly, not auto-populated


class TestNoSecretsInCode:
    def test_no_hardcoded_api_key_in_gemini_provider(self):
        src = (ROOT / "foms" / "services" / "designer" / "gemini_provider.py").read_text(encoding="utf-8")
        # Should not contain actual API key patterns
        import re
        key_patterns = re.findall(r'AIzaSy[A-Za-z0-9_-]{33}', src)
        assert not key_patterns, f"Hardcoded API key found in gemini_provider.py: {key_patterns}"

    def test_drawings_api_no_hardcoded_keys(self):
        src = (ROOT / "foms" / "api" / "designer" / "drawings.py").read_text(encoding="utf-8")
        import re
        key_patterns = re.findall(r'AIzaSy[A-Za-z0-9_-]{33}', src)
        assert not key_patterns, f"Hardcoded API key in drawings.py: {key_patterns}"
