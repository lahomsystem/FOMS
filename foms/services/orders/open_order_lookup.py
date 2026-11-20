"""같은 고객의 진행 중 주문 찾기 — 새 주문 안내 한 줄과 생성 기록이 같이 쓴다.

설계서 2026-11-20 "한 주문 여러 시공일 1단계" 6.1 · 6.2 (M15 ~ M17). 주문 6026 처럼 남은 제품을
새 주문으로 다시 등록하기 전에 "이 고객의 진행 중인 주문이 있다"를 알리는 것이 목적이다.

**진행 중**(M16): 운영 화면 기준(:meth:`models.Order.active_filter` — 휴지통 · 초안 · 숨은 초안 제외) ·
ERP 주문 · 단계가 완료가 아님. 완료됐는데 AS 가 열린 주문은 진행 중이 아니다(상담 AI 의
"열린 주문" :mod:`foms.services.cs_agent.order_find` 과 여기만 다르다).

**찾는 축**: 전화(숫자 칸 포함 검색 뒤 번호 조각을 정확히 견줌 — 번호를 두 개 적은 주문도 맞는다),
또는 주소(도로명 + 건물번호 + 동 · 호). 이름만 같은 것은 치지 않는다(동명이인).

주문 한 줄을 통째로 읽지 않는다 — ``structured_data`` 를 풀면 느려진다. 칸만 고른다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import or_, select

from foms.services.common.address_query import unit_address_key
from foms.services.erp_sync_columns import is_placeholder_phone
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.phone_search import normalize_phone_digits, split_phone_pieces
from models import Order, OrderScheduleDate

logger = logging.getLogger(__name__)

__all__ = [
    "DONE_STAGE_CODES",
    "OPEN_ORDER_NOTICE_LIMIT",
    "OPEN_ORDER_RECORD_CAP",
    "created_event_payload",
    "find_open_orders_for_customer",
    "find_open_orders_with_more",
]

#: 안내 한 줄에 보여 주는 주문 수(넘으면 "외 n건").
OPEN_ORDER_NOTICE_LIMIT = 3
#: 생성 기록(``ORDER_CREATED`` payload ``open_order_ids``)에 남기는 번호 수 상한.
OPEN_ORDER_RECORD_CAP = 20
#: 완료 단계(옛 한글 값 포함). 이 단계가 아니면 진행 중이다.
DONE_STAGE_CODES = ("COMPLETED", "AS_COMPLETED", "완료", "AS완료")

#: 전화 축 한 번호당 읽는 줄 상한.
_PHONE_SCAN_CAP = 50
#: 주소 축이 읽는 줄 상한 — 도로명 포함 검색이라 같은 길의 다른 집이 섞여 들어온다.
_ADDRESS_SCAN_CAP = 200
#: 입력 전화에서 쓰는 번호 수(고객 칸에 번호를 둘까지 적는다).
_MAX_INPUT_PHONES = 2

_COLUMNS = (
    Order.id,
    Order.erp_stage_code,
    Order.status,
    Order.customer_name,
    Order.address,
    Order.erp_phone_digits,
)


def _input_phones(phone: Any) -> tuple[str, ...]:
    """입력 전화 → 견줄 번호들(자리표시자 · 겹침 빼고 둘까지).

    >>> _input_phones("010-1234-5678 / 010-9876-5432")
    ('01012345678', '01098765432')
    >>> _input_phones("010-0000-0000")
    ()
    >>> _input_phones("000-0000-0000")
    ()
    """
    pieces = split_phone_pieces(normalize_phone_digits(phone))
    real = [piece for piece in dict.fromkeys(pieces) if not _is_placeholder(piece)]
    return tuple(real[:_MAX_INPUT_PHONES])


def _is_placeholder(piece: str) -> bool:
    """실제 번호가 아닌가 — 전부 0 · 자릿수 모자람 · ``010-0000-0000`` 처럼 국번 뒤가 전부 0."""
    return is_placeholder_phone(piece) or set(piece[3:]) == {"0"}


def _open_orders(exclude_order_id: Optional[int], scope_clause: Any):
    """진행 중 주문 고르기(칸만) — 부르는 쪽이 축 조건 · 상한을 더한다."""
    stmt = select(*_COLUMNS).where(
        Order.active_filter(),
        Order.is_erp_order.is_(True),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(DONE_STAGE_CODES)),
    )
    if exclude_order_id:
        stmt = stmt.where(Order.id != int(exclude_order_id))
    if scope_clause is not None:
        stmt = stmt.where(scope_clause)
    return stmt.order_by(Order.id.desc())


def _by_phone(db: Any, base: Any, phones: tuple[str, ...]) -> list[Any]:
    """그 번호가 든 진행 중 주문(새 주문 먼저). 포함 검색 뒤 번호 조각이 정확히 같은 줄만 남긴다."""
    found: list[Any] = []
    for piece in phones:
        rows = db.execute(
            base.where(Order.erp_phone_digits.contains(piece))  # perf-ok: ix_orders_erp_phone_digits_trgm
            .limit(_PHONE_SCAN_CAP)
        ).all()
        found.extend(row for row in rows if piece in split_phone_pieces(row.erp_phone_digits))
    return found


def _by_address(db: Any, base: Any, address: Any) -> list[Any]:
    """같은 집(도로명 + 건물번호 + 동 · 호)의 진행 중 주문. 동 · 호가 없는 주소는 견주지 않는다."""
    key = unit_address_key(address)
    if key is None:
        return []
    rows = db.execute(
        base.where(Order.address.contains(key[0]))  # perf-ok: 진행 중 주문만 훑는다(주소 칸 색인 없음)
        .limit(_ADDRESS_SCAN_CAP)
    ).all()
    return [row for row in rows if unit_address_key(row.address) == key]


def _matches(
    db: Any, *, phone: Any, address: Any, exclude_order_id: Optional[int], scope_clause: Any
) -> list[tuple[Any, str]]:
    """걸린 주문 ``(줄, 근거)`` — 전화로 걸린 것 먼저, 그다음 주소로만 걸린 것(각각 새 주문 먼저)."""
    base = _open_orders(exclude_order_id, scope_clause)
    seen: dict[int, tuple[Any, str]] = {}
    for row in _by_phone(db, base, _input_phones(phone)):
        seen.setdefault(int(row.id), (row, "phone"))
    by_phone = sorted(seen.values(), key=lambda pair: -int(pair[0].id))
    by_address = [
        (row, "address") for row in _by_address(db, base, address) if int(row.id) not in seen
    ]
    return by_phone + by_address


def _construction_dates(db: Any, order_ids: list[int]) -> dict[int, list[str]]:
    """주문별 시공일 전부(날짜순 · 겹침 없이). 납작 칸은 첫 날짜만 담아 이틀 시공을 한 날로 보여 준다."""
    if not order_ids:
        return {}
    rows = db.execute(
        select(OrderScheduleDate.order_id, OrderScheduleDate.date).where(
            OrderScheduleDate.order_id.in_(order_ids),
            OrderScheduleDate.kind == "construction",
        )
    ).all()
    dates: dict[int, set[str]] = {}
    for order_id, date in rows:
        if date:
            dates.setdefault(int(order_id), set()).add(str(date))
    return {order_id: sorted(values) for order_id, values in dates.items()}


def _stage_label(stage_code: Optional[str], status: Optional[str]) -> str:
    """단계 글(``생산`` · ``시공`` …). 단계 칸이 빈 옛 주문은 상태로, 옛 한글 값은 그대로."""
    return STAGE_LABELS.get(stage_code or "") or STAGE_LABELS.get(status or "") or (stage_code or "")


def find_open_orders_with_more(
    db: Any,
    *,
    phone: Any,
    name: Any = None,
    address: Any = None,
    exclude_order_id: Optional[int] = None,
    scope_clause: Any = None,
    limit: int = OPEN_ORDER_NOTICE_LIMIT,
) -> tuple[list[dict[str, Any]], int]:
    """같은 고객의 진행 중 주문 ``limit`` 건과, 그 밖에 더 걸린 건수("외 n건").

    Args:
        db: DB 세션.
        phone: 고객 전화(하이픈 · 번호 둘 붙임 허용). 자리표시자면 전화 축을 건너뛴다.
        name: 고객 이름. **찾는 데 쓰지 않는다**(이름만 같은 것은 치지 않는다 — M16).
        address: 고객 주소. 도로명 + 건물번호 + 동 · 호가 다 있어야 주소 축이 돈다.
        exclude_order_id: 빼는 주문 번호(자기 자신 · 자기 초안 줄).
        scope_clause: 보는 사람 범위 SQL 조건(없으면 전체).
        limit: 돌려주는 건수.

    Returns:
        ``(주문 목록, 더 걸린 건수)``. 주문 한 줄은 ``order_id`` · ``stage_code`` · ``stage_label`` ·
        ``construction_dates`` · ``address`` · ``customer_name`` · ``reason``(``phone`` | ``address``).
    """
    matches = _matches(
        db, phone=phone, address=address, exclude_order_id=exclude_order_id, scope_clause=scope_clause
    )
    shown = matches[: max(0, int(limit))]
    dates = _construction_dates(db, [int(row.id) for row, _ in shown])
    orders = [
        {
            "order_id": int(row.id),
            "stage_code": row.erp_stage_code,
            "stage_label": _stage_label(row.erp_stage_code, row.status),
            "construction_dates": dates.get(int(row.id), []),
            "address": row.address or "",
            "customer_name": row.customer_name or "",
            "reason": reason,
        }
        for row, reason in shown
    ]
    return orders, len(matches) - len(shown)


def find_open_orders_for_customer(
    db: Any,
    *,
    phone: Any,
    name: Any = None,
    address: Any = None,
    exclude_order_id: Optional[int] = None,
    scope_clause: Any = None,
    limit: int = OPEN_ORDER_NOTICE_LIMIT,
) -> list[dict[str, Any]]:
    """같은 고객의 진행 중 주문(휴지통 · 초안 · 완료 단계 · 자기 자신 제외). 없으면 빈 목록.

    인자 · 돌려주는 줄은 :func:`find_open_orders_with_more` 와 같다.
    """
    orders, _more = find_open_orders_with_more(
        db,
        phone=phone,
        name=name,
        address=address,
        exclude_order_id=exclude_order_id,
        scope_clause=scope_clause,
        limit=limit,
    )
    return orders


def created_event_payload(db: Any, order: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """``ORDER_CREATED`` payload 에 그 순간 같은 고객의 진행 중 주문 번호(``open_order_ids``)를 더한다.

    4~8주 뒤 "진행 중 주문이 있는데도 새로 만든 주문" 수를 여기서 센다(M17). 화면이 없는 길(채널톡 ·
    협력사 · 옛 폼 · 네이버)도 같은 기록을 남긴다. 찾기가 실패해도 주문 생성은 막지 않는다 — 그때는
    열쇠를 넣지 않아 "없었다"(빈 목록)와 "못 셌다"(열쇠 없음)를 가른다.

    Args:
        db: 주문을 만드는 세션(자동 flush 없이 읽는다 — 만드는 중인 줄을 중간에 밀어 넣지 않는다).
        order: 방금 만든(또는 승격하는) 주문. ``phone`` · ``address`` · ``id`` 를 읽는다.
        payload: 원래 payload.

    Returns:
        ``open_order_ids`` 가 더해진 새 dict.
    """
    out = dict(payload)
    try:
        with db.no_autoflush:
            matches = _matches(
                db,
                phone=getattr(order, "phone", None),
                address=getattr(order, "address", None),
                exclude_order_id=getattr(order, "id", None),
                scope_clause=None,
            )
        out["open_order_ids"] = [int(row.id) for row, _ in matches[:OPEN_ORDER_RECORD_CAP]]
    except Exception:
        logger.warning(
            "open_order_ids 기록을 건너뜀 order_id=%s", getattr(order, "id", None), exc_info=True
        )
    return out
