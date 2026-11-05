"""네이버 안심번호(050X) 대신 주문자 실제 번호를 고객 연락처로 쓴다(사용자 11-05 핫픽스)."""

from foms.services.integrations.naver_commerce.mapping import (
    build_order_fields,
    build_structured_data,
)


def _detail(tel1, orderer_tel):
    return {
        "order": {"orderId": "1", "ordererName": "JINXIANGHUA", "ordererTel": orderer_tel},
        "productOrder": {
            "productOrderId": "2",
            "productName": "옷장",
            "quantity": 1,
            "shippingAddress": {"name": "JINXIANGHUA", "tel1": tel1, "baseAddress": "서울"},
        },
    }


def test_safe_number_replaced_by_orderer_tel():
    d = _detail("0502-2773-1128", "010-6713-5598")
    assert build_order_fields(d, today="2026-11-05")["phone"] == "010-6713-5598"
    assert build_structured_data(d)["parties"]["customer"]["phone"] == "010-6713-5598"


def test_real_recipient_number_kept():
    d = _detail("010-1111-2222", "010-6713-5598")
    assert build_order_fields(d, today="2026-11-05")["phone"] == "010-1111-2222"


def test_safe_number_kept_when_no_orderer_tel():
    d = _detail("0502-2773-1128", "")
    assert build_order_fields(d, today="2026-11-05")["phone"] == "0502-2773-1128"
