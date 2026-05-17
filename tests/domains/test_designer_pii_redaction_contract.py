"""C7/C9 PII redaction contract tests."""

from __future__ import annotations

from foms.services.designer.pii_redactor import redact_raw_pii_text, scan_for_raw_pii


def test_free_text_redaction_removes_phone_address_and_name():
    raw = "고객 홍길동님 요청: 서울시 강남구 테헤란로 10 101호, 연락처 010-1234-5678"

    redacted, found = redact_raw_pii_text(raw)

    assert "010-1234-5678" not in redacted
    assert "홍길동" not in redacted
    assert "서울시 강남구 테헤란로" not in redacted
    assert "[PHONE_REDACTED]" in redacted
    assert "[CUSTOMER_REDACTED]" in redacted
    assert "[ADDRESS_REDACTED]" in redacted
    assert {"phone", "customer_name", "address"}.issubset(set(found))
    assert "phone" not in scan_for_raw_pii(redacted)


def test_known_raw_values_are_redacted_before_persistence():
    raw = "고객 요청 메모: 김테스트 특수 시공"

    redacted, found = redact_raw_pii_text(raw, known_raw_values=["김테스트"])

    assert "김테스트" not in redacted
    assert "[PII_REDACTED]" in redacted
    assert "known_pii_value" in found
