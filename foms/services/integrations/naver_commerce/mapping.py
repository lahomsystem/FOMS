"""네이버 상품주문 상세 → FOMS Order 필드 매핑 (NAVER-INGEST-01 §3.6).

**순수 함수만** 둔다(DB·네트워크 없음). 주문 생성은 :mod:`~foms.services.integrations.naver_commerce.ingest`
가 :func:`~foms.services.orders.order_create.create_order` 를 통해 한다.

설계 메모:

* **좌표를 `Order.lat/lng` 에 넣지 않는다.** 네이버 좌표는 주문서에 적힌 주소 기준이고 실제
  고객(시공) 주소와 다른 경우가 많다. 넣으면 ``geocode_status='success'`` 라 재지오코딩에서도
  빠져 틀린 값이 조용히 굳는다. 수집 주문도 기존 주문과 똑같이 지오코딩한다.
  네이버 좌표는 참고용으로 ``structured_data['naver']`` 에만 남긴다.
* **주문자 ≠ 수취인** 케이스가 실재한다(대리주문). 배송지 이름/전화를 고객으로 쓰고,
  주문자는 ``parties.orderer`` 에 따로 보존한다.
* ``takingAddress`` 는 반품 수거지(자사 주소)다. 고객 정보가 아니라서 버린다.
* ``productOption`` 은 **원문 그대로** 보관한다(v1 자동 파싱 없음 — 스펙 §7 Q2).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from foms.services.integrations.naver_commerce.constants import SOURCE_MARKER

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


def build_structured_data(detail: dict) -> dict:
    """ERP structured_data 를 만든다(canonical 키 위치 사용).

    ERP 대시보드·통합검색이 읽는 자리에 맞춘다: 고객은 ``parties.customer``, 주문자는
    ``parties.orderer``, 주소는 ``site``, 품목은 ``items[]``. 네이버 고유 값은
    ``naver`` 아래로 몰아 다른 채널이 생겨도 충돌하지 않게 한다.
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
            },
            # 대리주문이면 주문자와 수취인이 다르다 — 해피콜 대상 판단에 필요해 보존한다.
            "orderer": {
                "name": _text(order.get("ordererName")),
                "phone": _text(order.get("ordererTel")),
            },
        },
        "site": {
            "address_full": address,
            "address_main": _text(shipping.get("baseAddress")),
            "address_detail": _text(shipping.get("detailedAddress")),
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
            "shipping_memo": _text(shipping.get("shippingMemo")),
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

    items = []
    option_lines = []
    # 품목은 **대표 본품이 1번**이어야 한다 — 사람이 편집기에서 처음 보는 행이 33,200원짜리
    # 길이추가 옵션이면 본품을 찾아 헤맨다(2026-08-14 실사용 피드백). 대표 먼저, 나머지는
    # 원래 순서 유지.
    display_order = [lead] + [d for i, d in enumerate(details) if i != lead_index]
    for detail in display_order:
        _order, product_order, _shipping = unwrap_detail(detail)
        name = _text(product_order.get("productName"))
        option = _text(product_order.get("productOption"))
        items.append({
            "product_name": name,
            "name": name,
            "options": option,
            "quantity": _int(product_order.get("quantity")) or 1,
            "price": _int(product_order.get("totalPaymentAmount")),
            "naver_product_order_id": _text(product_order.get("productOrderId")),
            # 편집기·목록이 본품/추가옵션을 구분해 보여줄 근거(대표 = 본품).
            "naver_role": "main" if detail is lead else "addon",
        })
        if option:
            option_lines.append(f"{name}: {option}" if len(details) > 1 else option)

    structured["items"] = items
    structured["totals"] = {"items_total": total}
    # 옵션 원문은 사람이 규격을 채우는 근거다 — 묶으면 건별로 구분해 이어 붙인다.
    order_fields["options"] = "\n".join(option_lines) or None
    structured["naver"]["product_order_ids"] = [
        _text(unwrap_detail(d)[1].get("productOrderId")) for d in details
    ]
    structured["naver"]["grouped_count"] = len(details)
    return (order_fields, structured)


__all__ = [
    "COLLECTIBLE_STATUS",
    "group_key",
    "map_group",
    "KST",
    "NaverMappingError",
    "REQUIRED_FIELDS",
    "SOURCE_MARKER",
    "build_address",
    "build_order_fields",
    "build_structured_data",
    "extract_external_id",
    "is_collectible",
    "map_detail",
    "parse_order_datetime",
    "unwrap_detail",
]
