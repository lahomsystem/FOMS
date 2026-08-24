"""T16-A 발주 상태 추출 단위 테스트 (mapping 순수 함수)."""
from foms.services.integrations.naver_commerce.mapping import extract_place_status


def test_not_yet_is_not_confirmed():
    got = extract_place_status({"productOrder": {"placeOrderStatus": "NOT_YET",
                                                 "shippingDueDate": "2026-09-08T23:59:59.000+09:00"}})
    assert got["status"] == "NOT_YET"
    assert got["label"] == "발주확인 전"
    assert got["confirmed"] is False
    assert got["shipping_due"].startswith("2026-09-08")


def test_ok_is_confirmed():
    got = extract_place_status({"productOrder": {"placeOrderStatus": "OK"}})
    assert got["confirmed"] is True
    assert got["label"] == "발주확인 완료"


def test_unknown_status_is_treated_as_pending_and_shown_verbatim():
    """모르는 값을 완료로 읽으면 처리할 건이 화면에서 사라진다 — 안전한 쪽으로 틀린다."""
    got = extract_place_status({"productOrder": {"placeOrderStatus": "WEIRD_NEW_CODE"}})
    assert got["confirmed"] is False
    assert got["label"] == "WEIRD_NEW_CODE"


def test_missing_status_is_pending_not_crash():
    for payload in ({}, {"productOrder": {}}, {"order": {}}, None, "junk"):
        got = extract_place_status(payload if isinstance(payload, dict) else {})
        assert got["confirmed"] is False
        assert got["status"] == ""
