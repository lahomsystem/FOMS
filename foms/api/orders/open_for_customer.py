"""새 주문 안내 읽기 API — 같은 고객의 진행 중 주문 (설계서 2026-11-20 6.1 · M15 ~ M17).

``GET /api/orders/open-for-customer?phone=&name=&address=&exclude_order_id=``. PC 주문 폼(전화 · 주소 칸을
벗어날 때)과 휴대폰 마법사 마지막 단계가 부른다. 본사 직원 전용이다 — 프리랜서 · 협력사는 문지기 허용
목록에 없어 403 이고, 화면은 조용히 넘어간다(남의 주문 정보가 새지 않게).
"""

from __future__ import annotations

from flask import jsonify, request, url_for

from db import get_db
from foms.services.error_logging import log_handled_exception
from foms.services.orders.open_order_lookup import find_open_orders_with_more


def open_orders_for_customer_response():
    """같은 고객의 진행 중 주문 세 건까지 + 그 밖의 건수.

    Query params:
        phone: 고객 전화(하이픈 · 번호 둘 허용).
        name: 고객 이름(받기만 하고 찾는 데 쓰지 않는다 — 이름만 같은 것은 치지 않는다. 화면은 보내지 않는다).
        address: 고객 주소(도로명 + 건물번호 + 동 · 호가 있어야 주소로 찾는다).
        exclude_order_id: 빼는 주문 번호(쓰고 있는 초안 줄 · 복사본 자기 자신).

    Returns:
        ``{success, data: {orders: [...], more}, error}``. ``orders`` 한 줄은 찾기 함수의 칸에서 고객 이름을 뺀 것
        + ``url``(PC 주문 화면) · ``mobile_url``(휴대폰 주문 상세). ``more`` 는 세 건 밖에 더 걸린 건수다.
    """
    try:
        orders, more = find_open_orders_with_more(
            get_db(),
            phone=(request.args.get("phone") or "").strip(),
            name=(request.args.get("name") or "").strip(),
            address=(request.args.get("address") or "").strip(),
            exclude_order_id=request.args.get("exclude_order_id", type=int),
        )
    except Exception:
        log_handled_exception("open-for-customer")
        return (
            jsonify({"success": False, "data": None, "error": "진행 중 주문을 확인하지 못했습니다."}),
            500,
        )
    for row in orders:
        row.pop("customer_name", None)  # 화면이 그리지 않는다 — 남의 이름을 응답에 싣지 않는다
        row["url"] = url_for("order_edit.edit_order", order_id=row["order_id"], open="erp-order")
        row["mobile_url"] = url_for("erp_dashboard.erp_order_mobile_detail", order_id=row["order_id"])
    return jsonify({"success": True, "data": {"orders": orders, "more": more}, "error": None})


__all__ = ["open_orders_for_customer_response"]
