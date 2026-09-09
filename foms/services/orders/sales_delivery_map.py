"""AS 영업/택배 전달 건 -> 기준 실측 주문 역방향 맵 (실측 대시보드 배지/카드용).

스펙: docs/specs/2026-09-09-as-sales-delivery-measurement-assignment-design.md §4.2.

AS 영업/택배 탭의 전달 건(주문)은 `structured_data.shipment.sales_delivery_link` 에
자신이 배정된 **실측 주문 id**(`ref_order_id`)를 들고 있다(정방향 링크 SSOT는
`foms/services/orders/sales_delivery_link.py`). 실측 대시보드는 반대 방향
("이 실측 건에 어떤 전달이 태워져 있나")이 필요하므로, 미완료 AS ∩ 영업/택배
모집단을 전량 읽어 파이썬에서 `ref_order_id` 기준으로 뒤집는다.

**JSONB 역질의 금지**: `ref_order_id` 에는 인덱스가 없다. 실측 주문마다
`WHERE structured_data ->> ... = :ref_order_id` 를 걸면 N+1 이자 매번 풀스캔이 된다.
전량 로드 1회 + 파이썬 dict 뒤집기가 유일하게 안전한 모양이다(운영 규모 4건 — 스펙 §4.2).

`item_text`(무엇을 들고 가나) 근거: `structured_data.shipment` 에 전달 품목 전용
필드는 없다. 품목 요약을 만드는 `foms.services.erp_display.apply_erp_display_fields`
는 ORM 객체를 제자리에서 mutate 해 읽기 전용 맵에서 재사용하기 안전하지 않다.
대신 **AS 내용**(`shipment.as_content`)을 평문 한 줄로 줄여 쓴다 — 출고 AS 추천 카드가
이미 같은 소스를 `as_content_text` 로 쓰고 있어(`shipment_as_recommendation_cache.py`)
표현이 갈리지 않는다. 영업담당이 현장에서 필요한 정보가 정확히 이 문장이다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, load_only

from foms.services.as_content_safety import as_content_html_to_text
from foms.services.as_dashboard_read_model import build_as_tab_query_conditions
from foms.services.orders.sales_delivery_link import derive_display_state, read_link
from foms.services.schedule_recommendations import (
    get_order_display_address,
    get_order_display_customer_name,
)
from models import Order

# 카드 한 줄에 들어가는 길이. 넘으면 말줄임한다.
_ITEM_TEXT_MAX = 60

_INCLUDED_STATES = ("assigned", "delivered")


def _dialect_name(db: Session) -> str:
    """세션 바인드의 dialect 이름을 소문자로 반환한다('postgresql'/'sqlite'/'').

    Args:
        db: SQLAlchemy 세션.

    Returns:
        dialect 이름(소문자). 바인드가 없으면 빈 문자열.
    """
    bind = db.get_bind() if hasattr(db, "get_bind") else None
    return ((bind.dialect.name or "") if bind and bind.dialect else "").lower()


def _item_text_of(sd: dict[str, Any] | None) -> str:
    """AS 내용(`shipment.as_content`) 을 카드 한 줄짜리 평문으로 줄인다.

    Args:
        sd: 전달 건 주문의 structured_data(None 허용).

    Returns:
        개행을 공백으로 접고 `_ITEM_TEXT_MAX` 자에서 말줄임한 평문. 내용이 없으면 ''.
    """
    shipment = (sd or {}).get("shipment")
    if not isinstance(shipment, dict):
        return ""
    text = as_content_html_to_text(shipment.get("as_content")).replace("\n", " ").strip()
    if len(text) <= _ITEM_TEXT_MAX:
        return text
    return text[: _ITEM_TEXT_MAX - 1].rstrip() + "…"


def _row_to_item(order: Order, link: dict[str, Any], state: str) -> dict[str, Any]:
    """AS 전달 주문 1건 + 그 링크 + 표시 상태 -> 실측 대시보드 item dict(스펙 §4.2).

    Args:
        order: 전달 건 Order(id/customer_name/address/structured_data 만 로드됨).
        link: `read_link(order.structured_data)` 결과(None 아님이 호출부 전제).
        state: `derive_display_state` 결과("assigned" 또는 "delivered").

    Returns:
        `{order_id, customer_name, address, item_text, state, ref_date, ref_manager,
        assigned_by, assigned_at}`.
    """
    return {
        "order_id": order.id,
        "customer_name": get_order_display_customer_name(order),
        "address": get_order_display_address(order),
        "item_text": _item_text_of(order.structured_data),
        "state": state,
        "ref_date": link.get("ref_date"),
        "ref_manager": link.get("ref_manager"),
        "assigned_by": link.get("assigned_by"),
        "assigned_at": link.get("assigned_at"),
    }


def build_sales_delivery_by_ref(db: Session, *, cap: int = 300) -> dict[str, Any]:
    """미완료 AS ∩ 영업/택배 배정 건을 실측 주문 id(ref_order_id) 로 역방향 인덱싱한다.

    모집단은 `build_as_tab_query_conditions()["sales_delivery_condition"]`
    (= 미완료 AS ∩ `sales_delivery=true`, AS 탭 카운트와 같은 SSOT)를 그대로 재사용한다.
    그중 실제로 실측 일정에 배정된 링크가 있고(`read_link`) method 가 parcel 이
    아닌(`derive_display_state` ∈ assigned|delivered) 건만 결과에 담는다 — 미배정·택배
    전환 건은 실측 대시보드에 보여줄 배정 정보가 없다.

    Args:
        db: SQLAlchemy 세션.
        cap: 전량 로드 상한(대시보드 캡 공시 규약). 모집단이 이를 넘으면 뒤쪽은
            잘리고 `truncated=True` 로 공시한다.

    Returns:
        `{"by_ref": {ref_order_id: [item, ...]}, "total": int, "truncated": bool}`.
        `total` 은 `by_ref` 에 실제로 담긴 건수(모집단 전체가 아니라 링크가 있는 건만).
    """
    conditions = build_as_tab_query_conditions(dialect_name=_dialect_name(db))
    query = (
        db.query(Order)
        .options(load_only(Order.id, Order.customer_name, Order.address, Order.structured_data))
        .filter(Order.active_filter(), conditions["sales_delivery_condition"])
        .order_by(Order.id.desc())
    )
    rows = query.limit(cap + 1).all()
    truncated = len(rows) > cap
    rows = rows[:cap]

    by_ref: dict[int, list[dict[str, Any]]] = {}
    for order in rows:
        sd = order.structured_data if isinstance(order.structured_data, dict) else None
        link = read_link(sd)
        if link is None:
            continue
        state = derive_display_state(sd)
        if state not in _INCLUDED_STATES:
            continue
        ref_id = link.get("ref_order_id")
        if ref_id is None:
            continue
        by_ref.setdefault(ref_id, []).append(_row_to_item(order, link, state))

    total = sum(len(items) for items in by_ref.values())
    return {"by_ref": by_ref, "total": total, "truncated": truncated}
