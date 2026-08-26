"""원본에 이미 오는데 화면이 안 읽던 필드 3종 추출 계약 (F-1·F-2·F-3).

근거는 ``docs/guides/NAVER_FIELD_INVENTORY.md`` §2.3(부분취소 잔여)·§2.4(배송 축)·
§2.5(클레임 상세)의 스테이징 실데이터 전수 census 다. 픽스처는 그 census 가 적은
**실데이터 모양**을 본떴다 — 네이버로 나가는 호출은 없다(원본 스냅샷만 읽는다).
"""
from foms.services.integrations.naver_commerce.mapping import (
    build_structured_data,
    extract_claim,
    extract_delivery,
    extract_partial_cancel,
)

#: ``extract_claim`` 이 원래 주던 키. **뜻도 값도 그대로여야 한다**(회귀 방지).
LEGACY_CLAIM_KEYS = ("status", "type", "reason", "requested_at", "label", "blocking")


def _snapshot(**product_order) -> dict:
    """실데이터 모양의 상품주문 상세 1건.

    ``initial*``·``remain*`` 는 실제로 **281/281 전 건에** 오므로 기본 픽스처에도
    넣는다(같은 값 = 부분취소 없음). 이게 F-3 의 함정 그 자체다.
    """
    base = {
        "quantity": 1,
        "totalPaymentAmount": 594000,
        "initialQuantity": 1,
        "remainQuantity": 1,
        "initialPaymentAmount": 594000,
        "remainPaymentAmount": 594000,
        "productName": "라홈 붙박이장",
        "productOrderId": "2026082512345678",
        "shippingAddress": {
            "name": "김실측",
            "tel1": "010-1111-2222",
            "baseAddress": "서울 강남구 테헤란로 1",
            "detailedAddress": "101동 202호",
            "zipCode": "06234",
        },
    }
    base.update(product_order)
    return {
        "order": {
            "orderId": "2026082599999999",
            "ordererName": "김실측",
            "ordererTel": "010-1111-2222",
            "orderDate": "2026-08-25T10:12:00.000+09:00",
        },
        "productOrder": base,
    }


# ---------------------------------------------------------------- F-1 사유 원문

def test_detailed_reason_from_cancel_block():
    """취소 사유 원문이 ``cancel`` 블록에 오는 형태."""
    detail = _snapshot(claimStatus="CANCEL_REQUEST")
    detail["cancel"] = {
        "claimStatus": "CANCEL_REQUEST",
        "cancelReason": "SIMPLE_INTENT_CHANGED",
        "cancelDetailedReason": "일시불 재결제 예정",
        "claimRequestDate": "2026-08-25T11:00:00.000+09:00",
    }
    claim = extract_claim(detail)
    assert claim["detailed_reason"] == "일시불 재결제 예정"
    # 코드값과 원문은 **다른 축**이다 — 합치면 집계도 사람도 못 읽는다.
    assert claim["reason"] == "SIMPLE_INTENT_CHANGED"


def test_detailed_reason_from_current_claim_block():
    """``cancel`` 이 없고 ``currentClaim.cancel`` 로만 오는 형태도 잡는다."""
    detail = _snapshot()
    detail["currentClaim"] = {"cancel": {"claimStatus": "CANCEL_REQUEST",
                                         "cancelReason": "MISTAKE_ORDER",
                                         "cancelDetailedReason": "카드 바꿔서 다시 결제할게요"}}
    assert extract_claim(detail)["detailed_reason"] == "카드 바꿔서 다시 결제할게요"


def test_detailed_reason_from_return_claim():
    """반품 원문(``returnDetailedReason``)도 같은 자리로 나온다 — 취소만 읽으면 반쪽이다."""
    for holder in ("cancel", "currentClaim"):
        detail = _snapshot()
        block = {"claimStatus": "RETURN_REQUEST", "returnReason": "PRODUCT_DEFECT",
                 "returnDetailedReason": "문짝 모서리가 깨져서 왔어요"}
        detail[holder] = block if holder == "cancel" else {"cancel": block}
        claim = extract_claim(detail)
        assert claim["detailed_reason"] == "문짝 모서리가 깨져서 왔어요"
        assert claim["reason"] == "PRODUCT_DEFECT"


def test_no_claim_keeps_legacy_keys_and_empty_detailed_reason():
    """클레임이 없으면 원문은 빈 문자열이고 **기존 6키는 그대로**다(회귀 방지)."""
    claim = extract_claim(_snapshot())
    assert claim["detailed_reason"] == ""
    assert set(claim) == set(LEGACY_CLAIM_KEYS) | {"detailed_reason"}
    assert claim["status"] == "" and claim["type"] == "" and claim["reason"] == ""
    assert claim["requested_at"] == "" and claim["label"] == "" and claim["blocking"] is False


def test_detailed_reason_does_not_move_legacy_values():
    """원문이 있어도 기존 6키의 **값**이 흔들리지 않는다."""
    plain = _snapshot(claimStatus="CANCEL_REQUEST")
    plain["cancel"] = {"cancelReason": "SIMPLE_INTENT_CHANGED",
                       "claimRequestDate": "2026-08-25T11:00:00.000+09:00"}
    with_reason = _snapshot(claimStatus="CANCEL_REQUEST")
    with_reason["cancel"] = dict(plain["cancel"], cancelDetailedReason="일시불 재결제 예정")

    before, after = extract_claim(plain), extract_claim(with_reason)
    assert {k: before[k] for k in LEGACY_CLAIM_KEYS} == {k: after[k] for k in LEGACY_CLAIM_KEYS}
    assert before["detailed_reason"] == "" and after["detailed_reason"] == "일시불 재결제 예정"


def test_detailed_reason_lands_in_structured_data():
    """신규 수집분 structured_data 에도 실린다(화면이 원본을 다시 열지 않아도 된다)."""
    detail = _snapshot(claimStatus="CANCEL_REQUEST")
    detail["cancel"] = {"cancelDetailedReason": "일시불 재결제 예정"}
    assert (build_structured_data(detail)["naver"]["claim"]["detailed_reason"]
            == "일시불 재결제 예정")


# ------------------------------------------------------------------ F-2 배송 축

def test_delivery_axis_is_read_verbatim():
    """실데이터 모양 — 자사 직접 전달·추적 없음·발송처리 시각."""
    detail = _snapshot()
    detail["delivery"] = {"deliveryMethod": "DIRECT_DELIVERY",
                          "deliveryStatus": "NOT_TRACKING",
                          "sendDate": "2026-08-25T14:03:11.000+09:00",
                          "isWrongTrackingNumber": False}
    got = extract_delivery(detail)
    assert got["method"] == "DIRECT_DELIVERY"
    assert got["status"] == "NOT_TRACKING"
    assert got["status_label"] == "배송추적 없음"
    # 시각은 **원문 그대로** — 사람이 읽는 형식 변환은 화면 몫이다.
    assert got["send_date"] == "2026-08-25T14:03:11.000+09:00"
    assert got["wrong_tracking"] is False


def test_delivery_missing_block_is_empty_not_error():
    """``delivery`` 블록은 108/281 에만 있다 — 없는 건에서 터지면 화면이 통째로 죽는다."""
    for payload in (_snapshot(), {}, {"productOrder": {}}, {"delivery": None}, "junk"):
        got = extract_delivery(payload if isinstance(payload, dict) else {})
        assert got == {"method": "", "status": "", "status_label": "",
                       "send_date": "", "wrong_tracking": False}


def test_delivery_unknown_status_is_shown_verbatim():
    """모르는 상태 코드를 숨기지 않는다(발주·클레임 라벨과 같은 규율)."""
    detail = _snapshot()
    detail["delivery"] = {"deliveryStatus": "BRAND_NEW_CODE"}
    got = extract_delivery(detail)
    assert got["status"] == "BRAND_NEW_CODE" and got["status_label"] == "BRAND_NEW_CODE"


def test_delivery_wrong_tracking_flag():
    """송장 오류 표식. 문자열 ``"false"`` 를 참으로 읽으면 멀쩡한 건이 오류로 뜬다."""
    detail = _snapshot()
    detail["delivery"] = {"isWrongTrackingNumber": True}
    assert extract_delivery(detail)["wrong_tracking"] is True
    detail["delivery"] = {"isWrongTrackingNumber": "false"}
    assert extract_delivery(detail)["wrong_tracking"] is False


def test_delivery_from_flat_shape():
    """평평하게 오는 변형(``productOrder`` 없이 통째)도 같은 값을 준다."""
    flat = {"productOrderId": "2026082512345678",
            "delivery": {"deliveryStatus": "NOT_TRACKING",
                         "sendDate": "2026-08-25T14:03:11+09:00"}}
    assert extract_delivery(flat)["status_label"] == "배송추적 없음"


# -------------------------------------------------------------- F-3 부분취소 잔여

def test_equal_initial_and_remain_is_not_partial():
    """**가장 중요한 단언** — 281/281 이 이 필드를 갖고 있다.

    존재 여부로 판정하면 **모든 집이 부분취소로 보인다**. 값이 같으면 부분취소가 아니다.
    """
    got = extract_partial_cancel(_snapshot())
    assert got["is_partial"] is False
    assert got["initial_quantity"] == 1 and got["remain_quantity"] == 1
    assert got["initial_amount"] == 594000 and got["remain_amount"] == 594000


def test_partial_cancel_reports_both_sides_as_int():
    """일부만 취소된 집 — 수량·금액이 초기/잔여 둘 다 정수로 나온다."""
    got = extract_partial_cancel(_snapshot(
        quantity=1, totalPaymentAmount=198000,
        initialQuantity=3, remainQuantity=1,
        initialPaymentAmount="594,000", remainPaymentAmount="198000",
    ))
    assert got == {"is_partial": True, "initial_quantity": 3, "remain_quantity": 1,
                   "initial_amount": 594000, "remain_amount": 198000}
    assert all(isinstance(got[key], int) for key in
               ("initial_quantity", "remain_quantity", "initial_amount", "remain_amount"))


def test_amount_only_difference_is_partial():
    """수량은 그대로인데 금액만 깎인 부분취소(옵션만 뺀 경우)도 잡는다."""
    got = extract_partial_cancel(_snapshot(initialPaymentAmount=594000,
                                           remainPaymentAmount=560000))
    assert got["is_partial"] is True


def test_missing_fields_are_zero_and_not_partial():
    """값이 아예 없으면 '모른다' — 0 으로 채우되 부분취소라고 말하지 않는다."""
    assert extract_partial_cancel({"productOrder": {"productOrderId": "1"}}) == {
        "is_partial": False, "initial_quantity": 0, "remain_quantity": 0,
        "initial_amount": 0, "remain_amount": 0}


def test_one_sided_values_do_not_claim_partial():
    """한쪽만 온 원본은 판정 근거가 없다 — 침묵하는 쪽이 거짓말을 안 한다."""
    only_initial = extract_partial_cancel({"productOrder": {"initialQuantity": 3,
                                                            "initialPaymentAmount": 594000}})
    assert only_initial["is_partial"] is False
    assert only_initial["initial_quantity"] == 3 and only_initial["remain_quantity"] == 0


def test_partial_cancel_from_flat_shape():
    """평평한 변형도 같은 규칙으로 읽는다."""
    flat = {"productOrderId": "1", "initialQuantity": 2, "remainQuantity": 2,
            "initialPaymentAmount": 100, "remainPaymentAmount": 100}
    assert extract_partial_cancel(flat)["is_partial"] is False
