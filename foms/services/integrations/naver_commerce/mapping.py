"""네이버 상품주문 상세 → FOMS Order 필드 매핑 (NAVER-INGEST-01 §3.6).

**순수 함수만** 둔다(DB·네트워크 없음). 주문 생성은 :mod:`~foms.services.integrations.naver_commerce.ingest`
가 :func:`~foms.services.orders.order_create.create_order` 를 통해 한다.

설계 메모:

* **좌표를 `Order.lat/lng` 에 넣지 않는다.** 네이버 좌표는 주문서에 적힌 주소 기준이고 실제
  고객(시공) 주소와 다른 경우가 많다. 넣으면 ``geocode_status='success'`` 라 재지오코딩에서도
  빠져 틀린 값이 조용히 굳는다. 수집 주문도 기존 주문과 똑같이 지오코딩한다.
  네이버 좌표는 참고용으로 ``structured_data['naver']`` 에만 남긴다.
* **주문자 ≠ 수취인** 케이스가 실재한다(대리주문). 배송지 이름/전화를 고객으로 쓰고,
  주문한 사람은 ``parties.buyer`` 에 따로 보존한다. ``parties.orderer`` 는 **발주사**
  자리라 여기에 사람 이름을 넣으면 안 된다 — 넣었더니 알림톡이 하우드 프로필로 나가고
  도면에 하우드 로고가 찍혔다(ORDERER-AXIS-01). 발주사는 항상 ``DEFAULT_ORDERER_NAME``.
* ``takingAddress`` 는 반품 수거지(자사 주소)다. 고객 정보가 아니라서 버린다.
* ``productOption`` 은 **원문 그대로** 보관한다(v1 자동 파싱 없음 — 스펙 §7 Q2).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from foms.services.integrations.naver_commerce.constants import (
    ADDON_PRODUCT_CLASS,
    DEFAULT_ORDERER_NAME,
    SOURCE_MARKER,
)

KST = timezone(timedelta(hours=9))

#: 주문 생성에 반드시 있어야 하는 값(없으면 쓰레기 주문 대신 PENDING_REVIEW).
REQUIRED_FIELDS = ("external_id", "customer_name", "phone", "address", "product")

#: 신규 수집 대상 상태. 결제완료만 가져온다(스펙 §3.3 — 상품 필터는 없다).
COLLECTIBLE_STATUS = "PAYED"


class NaverMappingError(ValueError):
    """필수 값 누락·형식 불일치 — 주문을 만들지 않고 보류(PENDING_REVIEW) 로 남긴다."""


def _text(value: Any) -> str:
    """None/공백을 빈 문자열로 정규화한 문자열."""
    if value is None:
        return ""
    return str(value).strip()


def _int(value: Any) -> int:
    """금액류를 정수로. 콤마·소수점·빈 값을 견딘다(파싱 실패는 0)."""
    raw = _text(value).replace(",", "")
    if not raw:
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def unwrap_detail(detail: dict) -> tuple[dict, dict, dict]:
    """상세 응답 1건을 ``(order, product_order, shipping_address)`` 로 푼다.

    네이버 응답은 ``{"order": {...}, "productOrder": {...}}`` 중첩이지만, 배치 조회 형태에
    따라 평평하게 오는 경우도 있어 양쪽을 모두 받아준다.

    Args:
        detail: ``product-orders/query`` 응답의 항목 1개.

    Returns:
        ``(order, productOrder, shippingAddress)`` — 없으면 빈 dict.
    """
    if not isinstance(detail, dict):
        return ({}, {}, {})
    order = detail.get("order") if isinstance(detail.get("order"), dict) else {}
    product_order = (
        detail.get("productOrder") if isinstance(detail.get("productOrder"), dict) else detail
    )
    shipping = product_order.get("shippingAddress")
    if not isinstance(shipping, dict):
        shipping = detail.get("shippingAddress") if isinstance(detail.get("shippingAddress"), dict) else {}
    return (order, product_order, shipping)


def extract_external_id(detail: dict) -> str:
    """멱등 키(``productOrderId``)를 뽑는다. 없으면 빈 문자열."""
    _order, product_order, _shipping = unwrap_detail(detail)
    return _text(product_order.get("productOrderId"))


def is_collectible(status_entry: dict) -> bool:
    """변경분 항목이 신규 수집 대상(결제완료)인지 판정한다.

    ``last-changed-statuses`` 는 상태 변경 이벤트를 전부 준다(3일에 163건). 그중
    ``PAYED`` 만 신규 주문 후보다. 상품 필터는 없다(전 상품 수집 — 스펙 §7 Q4).
    """
    if not isinstance(status_entry, dict):
        return False
    return _text(status_entry.get("productOrderStatus")).upper() == COLLECTIBLE_STATUS


def parse_order_datetime(value: Any) -> tuple[str, Optional[str]]:
    """네이버 ISO 시각을 KST 기준 ``(YYYY-MM-DD, HH:MM)`` 으로 바꾼다.

    파싱 실패 시 날짜는 빈 문자열, 시각은 None 을 준다(호출자가 오늘 날짜로 대체).

    Args:
        value: ``2026-08-12T14:23:11.000+09:00`` 형태의 문자열.

    Returns:
        ``(날짜문자열, 시각문자열|None)``.
    """
    raw = _text(value)
    if not raw:
        return ("", None)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        # 날짜만 온 경우(YYYY-MM-DD)는 그대로 쓴다.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return (raw, None)
        return ("", None)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    kst = parsed.astimezone(KST)
    return (kst.strftime("%Y-%m-%d"), kst.strftime("%H:%M"))


def build_address(shipping: dict) -> str:
    """``baseAddress`` + ``detailedAddress`` 를 하나의 주소 문자열로 결합한다."""
    base = _text(shipping.get("baseAddress"))
    detail = _text(shipping.get("detailedAddress"))
    return " ".join(part for part in (base, detail) if part).strip()


def extract_shipping_memo(detail: dict) -> str:
    """배송 요청사항(배송메모) 원문을 뽑는다.

    **실위치는 ``productOrder.shippingMemo`` 다** — 2026-08-14 스테이징 실수집 42건 전수
    조사로 확인했다(13건 비어 있지 않음). 초기 구현은 ``shippingAddress.shippingMemo`` 를
    읽었는데 그 키는 응답에 아예 없어서 **항상 빈 값**이었다(조용한 유실). 폴백 2개는
    응답이 평평하게 오는 경로와 주문 단위로 오는 변형 대비로 남긴다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        메모 원문(없으면 빈 문자열).
    """
    order, product_order, shipping = unwrap_detail(detail)
    return (
        _text(product_order.get("shippingMemo"))
        or _text(shipping.get("shippingMemo"))
        or _text(order.get("shippingMemo"))
    )


#: 사람이 읽는 클레임 상태 라벨. 없는 값은 원문 그대로 보여준다(모르는 상태를 숨기지 않는다).
CLAIM_STATUS_LABELS = {
    "CANCEL_REQUEST": "취소 요청",
    "CANCEL_DONE": "취소 완료",
    "CANCEL_REJECT": "취소 거부",
    "RETURN_REQUEST": "반품 요청",
    "RETURN_DONE": "반품 완료",
    "EXCHANGE_REQUEST": "교환 요청",
    "EXCHANGE_DONE": "교환 완료",
    "PURCHASE_DECISION_HOLDBACK": "구매확정 보류",
}

#: 주문을 만들면 안 되는 클레임 상태(취소·반품 진행/완료). 거부·철회는 정상 진행이라 뺀다.
BLOCKING_CLAIM_STATUSES = frozenset({
    "CANCEL_REQUEST", "CANCEL_REQUESTED", "CANCELING", "CANCEL_DONE",
    "RETURN_REQUEST", "RETURN_REQUESTED", "RETURN_DONE", "COLLECTING", "COLLECT_DONE",
})


def extract_claim(detail: dict) -> dict:
    """취소·반품·교환(클레임) 상태를 뽑는다.

    **``productOrderStatus`` 만 봐서는 취소를 알 수 없다** — 2026-08-14 스테이징 실측:
    상태가 ``PAYED`` 인데 ``claimStatus = CANCEL_REQUEST`` 인 건이 실재했다(수집 필터가
    PAYED 하나뿐이라 취소 요청 건도 그대로 수집된다). 그 값을 아무도 읽지 않아 화면에
    표시되지 않았고, 사람이 "주문 만들기"를 누르면 취소 건이 정상 주문이 됐다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        ``{"status", "type", "reason", "requested_at", "label", "blocking"}``.
        클레임이 없으면 ``status`` 가 빈 문자열이고 ``blocking`` 은 False.
    """
    order, product_order, _shipping = unwrap_detail(detail)
    cancel = detail.get("cancel") if isinstance(detail.get("cancel"), dict) else {}
    current = detail.get("currentClaim") if isinstance(detail.get("currentClaim"), dict) else {}
    current_cancel = current.get("cancel") if isinstance(current.get("cancel"), dict) else {}
    source = cancel or current_cancel or {}

    status = (_text(product_order.get("claimStatus"))
              or _text(source.get("claimStatus"))
              or _text(order.get("claimStatus")))
    upper = status.upper()
    return {
        "status": status,
        "type": _text(product_order.get("claimType")) or _text(source.get("claimType")),
        "reason": _text(source.get("cancelReason")) or _text(source.get("returnReason")),
        "requested_at": _text(source.get("claimRequestDate")),
        "label": CLAIM_STATUS_LABELS.get(upper, status),
        "blocking": upper in BLOCKING_CLAIM_STATUSES,
    }


#: 사람이 읽는 발주 상태 라벨. 모르는 값은 원문을 그대로 보여준다(숨기지 않는다).
PLACE_STATUS_LABELS = {
    "NOT_YET": "발주확인 전",
    "OK": "발주확인 완료",
}

#: 발주확인이 끝난 것으로 보는 값. 여기 없으면 "아직"으로 취급한다 —
#: 모르는 값을 완료로 읽으면 처리해야 할 건이 화면에서 사라진다(안전한 쪽으로 틀린다).
CONFIRMED_PLACE_STATUSES = frozenset({"OK"})


def place_status_view(status: str) -> dict:
    """발주 상태 문자열 하나를 표시용 dict 로 편다.

    ``ExternalOrderLink.place_order_status`` 컬럼(수집·스윕·우리 발주확인이 갱신)과
    원본 스냅샷을 **같은 규칙**으로 읽기 위한 공용 변환이다. 컬럼이 표시 SSOT 이고
    스냅샷은 컬럼이 비었을 때의 폴백이다 — 둘이 갈리면 버튼이 사라지지 않는다.

    Args:
        status: 원문 상태값(빈 문자열 허용).

    Returns:
        ``{"status", "label", "confirmed"}``.
    """
    text = _text(status)
    upper = text.upper()
    return {
        "status": text,
        "label": PLACE_STATUS_LABELS.get(upper, text),
        "confirmed": upper in CONFIRMED_PLACE_STATUSES,
    }


def extract_place_status(detail: dict) -> dict:
    """발주(발주확인) 상태를 뽑는다 — NAVER-INGEST-02 T16-A.

    ``placeOrderStatus`` 는 수집 시점 원본에 이미 들어온다(2026-08-19 스테이징 실측:
    ``"NOT_YET"``). 네이버에 아무것도 쓰지 않고 "발주확인이 아직인 건"을 화면에서 가려낼 수
    있다는 뜻이다. 판매자센터나 API 로 발주확인을 하면 이 값이 바뀐다.

    ``shipping_due`` 를 같이 싣는 이유: 발송기한이 곧인데 발주확인 전이면 그게 급한 건이다.

    Args:
        detail: 상품주문 상세 1건(``{"order":…, "productOrder":…}`` 또는 평평한 형태).

    Returns:
        ``{"status", "label", "confirmed", "placed_at", "shipping_due"}``.
        값이 없으면 ``status`` 는 빈 문자열이고 ``confirmed`` 는 False(=아직으로 취급).
    """
    order, product_order, _shipping = unwrap_detail(detail)
    status = (_text(product_order.get("placeOrderStatus"))
              or _text(order.get("placeOrderStatus")))
    upper = status.upper()
    return {
        "status": status,
        "label": PLACE_STATUS_LABELS.get(upper, status),
        "confirmed": upper in CONFIRMED_PLACE_STATUSES,
        "placed_at": _text(product_order.get("placeOrderDate")),
        "shipping_due": _text(product_order.get("shippingDueDate")),
    }


def build_payment_info(detail: dict) -> dict:
    """결제·금액 상세. 지금까지 ``totalPaymentAmount`` 하나만 쓰고 나머지를 버렸다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        결제 시각·수단·단가·할인·쿠폰·정산예정액 dict(없으면 빈 값/0).
    """
    order, product_order, _shipping = unwrap_detail(detail)
    coupons = product_order.get("appliedCoupons")
    coupon_rows = []
    if isinstance(coupons, list):
        for coupon in coupons:
            if not isinstance(coupon, dict):
                continue
            coupon_rows.append({
                "class_code": _text(coupon.get("couponClassCode")),
                "discount_amount": _int(coupon.get("couponDiscountAmount")),
            })
    return {
        "paid_at": _text(order.get("paymentDate")),
        "means": _text(order.get("paymentMeans")),
        "location_type": _text(order.get("payLocationType")),
        "unit_price": _int(product_order.get("unitPrice")),
        "option_price": _int(product_order.get("optionPrice")),
        "product_discount_amount": _int(product_order.get("productDiscountAmount")),
        "expected_settlement_amount": _int(product_order.get("expectedSettlementAmount")),
        "coupons": coupon_rows,
    }


def build_structured_data(detail: dict) -> dict:
    """ERP structured_data 를 만든다(canonical 키 위치 사용).

    ERP 대시보드·통합검색이 읽는 자리에 맞춘다: 고객은 ``parties.customer``, 발주사는
    ``parties.orderer``(항상 라홈), 주문한 사람은 ``parties.buyer``, 주소는 ``site``,
    품목은 ``items[]``. 네이버 고유 값은 ``naver`` 아래로 몰아 다른 채널이 생겨도
    충돌하지 않게 한다.
    """
    order, product_order, shipping = unwrap_detail(detail)
    address = build_address(shipping)
    quantity = _int(product_order.get("quantity")) or 1
    return {
        "source": SOURCE_MARKER,
        "parties": {
            "customer": {
                "name": _text(shipping.get("name")) or _text(order.get("ordererName")),
                "phone": _text(shipping.get("tel1")) or _text(order.get("ordererTel")),
                # 보조 연락처(실측 47건 중 6건). 첫 번호로 연락이 안 될 때 쓰는 값이라
                # 버리면 다시 구할 방법이 없다. Order.phone 은 그대로 tel1 이다.
                "phone2": _text(shipping.get("tel2")),
            },
            # 발주사. ERP 에서 이 자리는 라홈/하우드 같은 발주처를 뜻하고, 알림톡 브랜드
            # 프로필·도면 로고·퀘스트 CS 팀·견적서 양식이 이 값으로 갈린다.
            "orderer": {"name": DEFAULT_ORDERER_NAME},
            # 주문한 사람. 대리주문이면 수취인과 다르다 — 해피콜 대상 판단에 필요해 보존한다.
            "buyer": {
                "name": _text(order.get("ordererName")),
                "phone": _text(order.get("ordererTel")),
            },
        },
        # FOMS 정본 주소 형태: full == main(합본 문자열) · detail 은 빈 값.
        # ``order_geocode.sync_site_address`` 가 모든 저장에서 그렇게 맞추고, ERP 편집 폼은
        # 로드할 때 full 뒤에 detail 을 이어 붙여 한 칸에 보여준다. 수집이 detail 을 따로
        # 남기면 이미 detail 을 품은 full 뒤에 detail 이 한 번 더 붙어 저장된다
        # (2026-08-14 운영 실측: ``… 103동 605호 103동 605호``).
        # 상세주소 원문이 필요하면 아래 ``naver`` 원본 필드가 아니라 주소 문자열을 쓴다.
        "site": {
            "address_full": address,
            "address_main": address,
            "address_detail": "",
            "zip_code": _text(shipping.get("zipCode")),
        },
        "items": [
            {
                "product_name": _text(product_order.get("productName")),
                "name": _text(product_order.get("productName")),
                # v1 은 파싱하지 않는다. 사람이 ERP 에서 규격/색상을 채운다.
                "options": _text(product_order.get("productOption")),
                "quantity": quantity,
                "price": _int(product_order.get("totalPaymentAmount")),
            }
        ],
        "naver": {
            "product_order_id": _text(product_order.get("productOrderId")),
            "order_no": _text(order.get("orderId")),
            "product_order_status": _text(product_order.get("productOrderStatus")),
            "shipping_due_date": _text(product_order.get("shippingDueDate")),
            "seller_product_code": _text(product_order.get("sellerProductCode")),
            "shipping_memo": extract_shipping_memo(detail),
            # 상품 식별자 — 나중에 "이 상품은 규격이 이렇다"를 자동화할 때 기초가 된다.
            "product_id": _text(product_order.get("productId")),
            "original_product_id": _text(product_order.get("originalProductId")),
            "item_no": _text(product_order.get("itemNo")),
            "inflow_path": _text(product_order.get("inflowPath")),
            # 취소·반품 상태. 없으면 status 가 빈 문자열이다(정상 주문).
            "claim": extract_claim(detail),
            "payment": build_payment_info(detail),
            # 참고용 좌표. Order.lat/lng 에 넣지 않는다(모듈 docstring 참조).
            "longitude": shipping.get("longitude"),
            "latitude": shipping.get("latitude"),
        },
    }


def build_order_fields(detail: dict, *, today: str) -> dict[str, Any]:
    """create_order 에 넘길 ``Order`` scalar 필드 dict 를 만든다.

    Args:
        detail: 상품주문 상세 1건.
        today: ``orderDate`` 파싱 실패 시 쓸 접수일(``YYYY-MM-DD``).

    Returns:
        ``Order`` scalar kwargs. 좌표 필드는 넣지 않는다(지오코딩이 채운다).
    """
    order, product_order, shipping = unwrap_detail(detail)
    received_date, received_time = parse_order_datetime(order.get("orderDate"))
    return {
        "received_date": received_date or today,
        "received_time": received_time,
        "customer_name": _text(shipping.get("name")) or _text(order.get("ordererName")),
        "phone": _text(shipping.get("tel1")) or _text(order.get("ordererTel")),
        "address": build_address(shipping),
        "product": _text(product_order.get("productName")),
        "options": _text(product_order.get("productOption")) or None,
        "payment_amount": _int(product_order.get("totalPaymentAmount")),
        "status": "RECEIVED",
        "is_regional": False,
    }


def map_detail(detail: dict, *, today: str) -> tuple[str, dict[str, Any], dict]:
    """상세 1건을 ``(external_id, order_fields, structured_data)`` 로 매핑한다.

    Args:
        detail: 상품주문 상세 1건.
        today: 접수일 대체값(``YYYY-MM-DD``).

    Returns:
        ``(external_id, order_fields, structured_data)``.

    Raises:
        NaverMappingError: 필수 값이 없을 때. 호출자는 주문을 만들지 않고
            ``PENDING_REVIEW`` 링크만 남긴다.
    """
    external_id = extract_external_id(detail)
    order_fields = build_order_fields(detail, today=today)
    candidates = {"external_id": external_id, **order_fields}
    missing = [name for name in REQUIRED_FIELDS if not _text(candidates.get(name))]
    if missing:
        raise NaverMappingError(f"필수 값 누락: {', '.join(missing)}")
    return (external_id, order_fields, build_structured_data(detail))



def group_key(detail: dict) -> tuple[str, str, str]:
    """묶음 판정 키 — ``(네이버 주문번호, 수취인 전화, 주소)``.

    같은 주문번호라도 **분할배송**이면 수취인·주소가 다를 수 있다. 그때 하나로 합치면
    남의 주소로 시공을 나가는 사고가 된다. 주문번호만으로 묶지 않는 이유다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        같은 값이면 한 주문으로 묶어도 되는 키.
    """
    order, _product_order, shipping = unwrap_detail(detail)
    return (
        _text(order.get("orderId")),
        _text(shipping.get("tel1")),
        build_address(shipping),
    )


#: 묶음키 문자열의 구분자. 주소·이름에 나올 수 없는 제어문자를 쓴다 — 구분자가 값 안에
#: 섞이면 서로 다른 집이 같은 키로 접힌다.
GROUP_KEY_SEP = "\x1f"

#: 컬럼(String(200)) 길이 예산. 주문번호·전화가 짧으므로 주소를 잘라 맞춘다.
#: 자르는 지점이 같으면 같은 집은 여전히 같은 키다(앞에서부터 자르므로 접두사가 보존된다).
GROUP_KEY_MAX_LEN = 200


def group_key_text(detail: dict) -> str:
    """:func:`group_key` 의 3-튜플을 **컬럼에 저장할 문자열**로 정규화한다.

    화면 두 곳이 같은 정의를 쓰려면 세밀한 키를 SQL 로도 셀 수 있어야 하고, 그러려면
    값이 컬럼에 있어야 한다(주소는 ``raw_snapshot`` 안에서 파이썬으로 조립해야 나온다).

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        같은 집이면 같은 문자열. 원본이 비어 키를 못 만들면 빈 문자열(호출자가 폴백한다).
    """
    order_no, tel, address = group_key(detail)
    if not (order_no or tel or address):
        return ""
    raw = GROUP_KEY_SEP.join((order_no, tel, address))
    return raw[:GROUP_KEY_MAX_LEN]


def _join_options(main_option: str, addon_options: list[str]) -> str:
    """본품 옵션 원문 + 추가옵션 원문들을 한 칸에 이어 붙인다(줄바꿈 구분)."""
    parts = [line for line in ([main_option] + list(addon_options)) if line]
    return "\n".join(parts)


def is_addon_detail(detail: dict) -> bool:
    """이 상품주문이 **추가옵션**인가(``productClass`` 정본).

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        추가옵션이면 True. 값이 없는 옛 원본은 본품으로 본다(모르면 항목을 남긴다).
    """
    _order, product_order, _shipping = unwrap_detail(detail)
    return _text(product_order.get("productClass")) == ADDON_PRODUCT_CLASS


def split_main_groups(details: list[dict], *,
                      fallback_index: int = 0) -> list[tuple[dict, list[dict]]]:
    """상세 목록을 **본품 → 그 본품의 추가옵션** 으로 묶는다.

    귀속 판정은 :func:`attribution.attribute_addons` 가 한다(수집 순서 우선, 본품이 앞에
    몰려 온 배치는 사양 축 일치). 화면(도크)과 **같은 함수**를 쓴다 — 한쪽만 바뀌면 품목
    금액과 화면 귀속이 어긋난다.

    Args:
        details: 같은 묶음의 상세 목록(수집 순서 그대로).
        fallback_index: 귀속이 미정인 옵션을 붙일 본품의 인덱스(기본 = 첫 본품).
            금액을 잃지 않으려면 어딘가에는 붙여야 한다. 화면에서는 여전히 "선택 필요"로 뜬다.

    Returns:
        ``[(본품 detail, [추가옵션 detail, ...]), ...]`` — 본품 등장 순서 보존.
        본품이 하나도 없으면 첫 건을 본품으로 삼는다(빈 묶음 방지).
    """
    from foms.services.integrations.naver_commerce.attribution import attribute_addons

    rows = []
    for detail in details:
        _order, product_order, _shipping = unwrap_detail(detail)
        rows.append({
            "is_main": not is_addon_detail(detail),
            "product_name": _text(product_order.get("productName")),
            "option_text": _text(product_order.get("productOption")),
        })
    main_indexes = [i for i, row in enumerate(rows) if row["is_main"]]
    if not main_indexes:
        # 전부 추가옵션으로 온 비정상 원본 — 첫 건을 본품으로 세운다.
        return [(details[0], list(details[1:]))] if details else []

    owners = attribute_addons(rows)
    buckets: dict[int, list[dict]] = {index: [] for index in main_indexes}
    default_main = main_indexes[min(fallback_index, len(main_indexes) - 1)]
    for index, detail in enumerate(details):
        if rows[index]["is_main"]:
            continue
        owner, _reason = owners[index]
        buckets[owner if owner in buckets else default_main].append(detail)
    return [(details[index], buckets[index]) for index in main_indexes]


def map_group(details: list[dict], *, today: str) -> tuple[dict[str, Any], dict]:
    """같은 묶음의 상품주문 여러 건을 **주문 1건**으로 매핑한다 (T13).

    네이버는 붙박이장 본품과 구성 옵션(반옷장·긴옷장 등, 금액 0원 포함)을 각각 다른
    ``productOrderId`` 로 준다. 상품주문 1건 = FOMS 주문 1건으로 두면 한 집 시공이
    주문 3~4건으로 쪼개져 일정·정산이 어긋난다(2026-08-14 실데이터: 12개 주문번호 → 34건).

    대표값 규칙:

    * 고객·주소·접수일시 — **금액이 가장 큰** 상품주문 기준(본품이 대표가 된다).
      금액이 같으면 입력 순서를 유지해 안정적으로 고른다.
    * ``product`` — 대표 제품명, 2건 이상이면 ``외 N건`` 을 덧붙인다.
    * ``payment_amount`` — 묶음 **합계**.
    * ``items[]`` — 상품주문마다 1행(0원 구성도 그대로 남긴다 — 뭘 받았는지가 정보다).

    Args:
        details: 같은 :func:`group_key` 를 가진 상세 목록(1건 이상).
        today: 접수일 대체값.

    Returns:
        ``(order_fields, structured_data)``.

    Raises:
        NaverMappingError: 비어 있거나 대표 건의 필수 값이 없을 때.
    """
    if not details:
        raise NaverMappingError("묶을 상세가 없다")

    ordered = sorted(
        enumerate(details),
        key=lambda pair: (-_int(unwrap_detail(pair[1])[1].get("totalPaymentAmount")), pair[0]),
    )
    lead_index, lead = ordered[0]
    _external_id, order_fields, structured = map_detail(lead, today=today)

    total = sum(_int(unwrap_detail(d)[1].get("totalPaymentAmount")) for d in details)
    order_fields["payment_amount"] = total
    if len(details) > 1:
        order_fields["product"] = f"{order_fields['product']} 외 {len(details) - 1}건"

    # **품목은 본품만 만든다** (2026-08-18 사용자 확정). 추가옵션(수납구성·EP마감·서랍·
    # 제로조인트·길이추가)까지 항목으로 만들면 한 집이 14행이 되어 규격을 채울 행을 찾기가
    # 어렵다. 옵션은 항목이 아니라 **그 본품 항목의 부속 정보**로 싣는다(도크에도 원문 그대로).
    # 금액은 잃지 않는다 — 본품 항목 금액 = 본품 + 그 본품에 귀속된 옵션 합계라서
    # ``items_total`` 이 묶음 합계와 정확히 같다.
    groups = split_main_groups(details)
    lead_first = sorted(
        groups,
        key=lambda pair: 0 if pair[0] is lead else 1,
    )
    items = []
    option_lines = []
    for main, addons in lead_first:
        _order, product_order, _shipping = unwrap_detail(main)
        name = _text(product_order.get("productName"))
        option = _text(product_order.get("productOption"))
        price = _int(product_order.get("totalPaymentAmount"))
        addon_rows = []
        addon_options = []
        for addon in addons:
            _o, addon_po, _s = unwrap_detail(addon)
            addon_name = _text(addon_po.get("productName"))
            addon_option = _text(addon_po.get("productOption"))
            addon_price = _int(addon_po.get("totalPaymentAmount"))
            price += addon_price
            addon_rows.append({
                "product_name": addon_name,
                "options": addon_option,
                "quantity": _int(addon_po.get("quantity")) or 1,
                "price": addon_price,
                "naver_product_order_id": _text(addon_po.get("productOrderId")),
            })
            if addon_option:
                addon_options.append(f"{addon_name}: {addon_option}")
        items.append({
            "product_name": name,
            "name": name,
            # 규격을 채우는 사람이 한 칸에서 본품·옵션 원문을 다 보게 이어 붙인다.
            "options": _join_options(option, addon_options),
            "quantity": _int(product_order.get("quantity")) or 1,
            "price": price,
            "naver_product_order_id": _text(product_order.get("productOrderId")),
            "naver_role": "main",
            # 항목으로 만들지 않은 추가옵션 원본 — 추적·역산용(화면 표시는 도크가 한다).
            "naver_addons": addon_rows,
        })
        if option:
            option_lines.append(f"{name}: {option}" if len(details) > 1 else option)
        option_lines.extend(addon_options)

    structured["items"] = items
    structured["totals"] = {"items_total": total}
    # 옵션 원문은 사람이 규격을 채우는 근거다 — 묶으면 건별로 구분해 이어 붙인다.
    order_fields["options"] = "\n".join(option_lines) or None
    structured["naver"]["product_order_ids"] = [
        _text(unwrap_detail(d)[1].get("productOrderId")) for d in details
    ]
    structured["naver"]["grouped_count"] = len(details)
    # 배송메모는 상품주문마다 따로 달린다. 대표 것만 쓰면 다른 줄에 적힌 요청이 조용히
    # 사라지므로 **서로 다른 값은 전부** 남긴다(중복은 제거, 표시 순서는 대표 먼저).
    memo_order = [lead] + [d for i, d in enumerate(details) if i != lead_index]
    memos: list[str] = []
    for detail in memo_order:
        memo = extract_shipping_memo(detail)
        if memo and memo not in memos:
            memos.append(memo)
    structured["naver"]["shipping_memo"] = "\n".join(memos)
    return (order_fields, structured)


__all__ = [
    "COLLECTIBLE_STATUS",
    "GROUP_KEY_MAX_LEN",
    "GROUP_KEY_SEP",
    "group_key",
    "group_key_text",
    "map_group",
    "KST",
    "NaverMappingError",
    "REQUIRED_FIELDS",
    "SOURCE_MARKER",
    "build_address",
    "build_order_fields",
    "build_structured_data",
    "BLOCKING_CLAIM_STATUSES",
    "CLAIM_STATUS_LABELS",
    "build_payment_info",
    "extract_claim",
    "extract_place_status",
    "place_status_view",
    "PLACE_STATUS_LABELS",
    "CONFIRMED_PLACE_STATUSES",
    "extract_external_id",
    "extract_shipping_memo",
    "is_collectible",
    "map_detail",
    "parse_order_datetime",
    "unwrap_detail",
]
