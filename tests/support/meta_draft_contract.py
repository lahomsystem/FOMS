"""초안 술어 동치 대조 도구 (DRAFTIDX-00 계약 테스트 공용).

``models.Order`` 의 초안 술어는 2026-10-05 에 "행마다 ``structured_data`` 의 ``meta.draft`` 를 풀어
읽기"에서 "표식이 켜진 번호 목록에 있나"로 바뀌었다(스펙
``docs/specs/2026-10-05-perf-db-draft-flag-and-stats_SPEC.md`` P2-1, 결정 1-가). 결과는 한 행도
달라지면 안 된다 — 표식이 남아 모든 화면에서 빠져 있는 실제 주문(운영 7건·스테이징 4건)도
그대로 숨어 있어야 한다(보이게 할지는 따로 정할 사용자 결정 2).

그래서 바뀌기 **전** 식을 여기에 고정하고, 새 술어와 같은 행을 고르는지 SQLite·PostgreSQL
레인에서 대조한다. 음성 대조군(status 만 보는 술어, 결정 3-나)은 대조기가 차이를 실제로 잡는다는
증거다 — 숨은 주문 모양에서 반드시 갈린다.
"""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import and_, insert, not_, or_
from sqlalchemy.engine import Connection

from models import Order
from tests.support.search_index_contract import load_migration

DRAFTIDX = load_migration("draftidx_00_meta_draft_partial_index.py")

FILTER_NAMES = (
    "active_filter",
    "active_including_trashed_filter",
    "erp_draft_filter",
    "erp_draft_predicate",
)


def frozen_old_draft_predicate() -> Any:
    """2026-10-05 이전 ``Order.erp_draft_predicate()`` 그대로 — 행마다 표식 JSON 을 읽는다."""
    return and_(
        Order.is_erp_order.is_(True),
        or_(
            Order.status == "DRAFT",
            Order.structured_data[("meta", "draft")].as_boolean().is_(True),
        ),
    )


def status_only_draft_predicate() -> Any:
    """음성 대조군 — 표식을 무시하고 status 만 본다(결정 3-나: 뜻이 바뀐다)."""
    return and_(Order.is_erp_order.is_(True), Order.status == "DRAFT")


def filters_from(draft_predicate: Callable[[], Any]) -> dict[str, Callable[[], Any]]:
    """초안 술어 하나로 네 필터를 ``models.Order`` 와 같은 모양으로 짠다."""
    return {
        "active_filter": lambda: and_(Order.not_deleted_filter(), not_(draft_predicate())),
        "active_including_trashed_filter": lambda: not_(draft_predicate()),
        "erp_draft_filter": lambda: and_(Order.not_deleted_filter(), draft_predicate()),
        "erp_draft_predicate": draft_predicate,
    }


OLD_FILTERS = filters_from(frozen_old_draft_predicate)
NEGATIVE_CONTROL_FILTERS = filters_from(status_only_draft_predicate)
NEW_FILTERS: dict[str, Callable[[], Any]] = {name: getattr(Order, name) for name in FILTER_NAMES}

_DELETED_AT = "2026-07-02 10:00:00"
_SQL_NULL = object()  # structured_data 칸을 아예 안 넣는다 → SQL NULL (JSON null 과 다르다)

# (key, status, is_erp_order, structured_data, deleted, original_status)
_CASES: tuple[tuple[str, str, bool, Any, bool, str | None], ...] = (
    ("draft_status_flag_on", "DRAFT", True, {"meta": {"draft": True}}, False, None),
    ("draft_status_no_meta", "DRAFT", True, {}, False, None),
    # 숨은 실제 주문 — 자동저장이 승격 직후 표식을 되살린 모양(106df4c11). 계속 숨어야 한다.
    ("hidden_real_order", "MEASURE", True, {"meta": {"draft": True}, "parties": {"customer": {"name": "x"}}},
     False, None),
    ("hidden_real_order_received", "RECEIVED", True, {"meta": {"draft": True}}, False, None),
    ("promoted_flag_off", "RECEIVED", True, {"meta": {"draft": False}}, False, None),
    ("no_draft_key", "RECEIVED", True, {"meta": {}}, False, None),
    ("no_meta", "MEASURE", True, {"parties": {}}, False, None),
    ("sd_sql_null", "RECEIVED", True, _SQL_NULL, False, None),
    ("sd_json_null", "RECEIVED", True, None, False, None),
    ("flag_json_null", "RECEIVED", True, {"meta": {"draft": None}}, False, None),
    # 지운 초안(정리 크론·옛 삭제 경로) — 휴지통 포함 화면에서도 빠져야 한다.
    ("deleted_draft", "DELETED", True, {"meta": {"draft": True}}, True, "DRAFT"),
    ("deleted_promoted_flag_on", "DELETED", True, {"meta": {"draft": True}}, True, "RECEIVED"),
    ("trashed_normal", "DELETED", True, {"meta": {"draft": False}}, True, "RECEIVED"),
    ("deleted_at_only_flag_on", "RECEIVED", True, {"meta": {"draft": True}}, True, None),
    ("non_erp_flag_on", "RECEIVED", False, {"meta": {"draft": True}}, False, None),
    ("non_erp_draft_status", "DRAFT", False, {}, False, None),
    # 글자 "true": PostgreSQL 은 참, SQLite 는 거짓(기존 방언 차이, 스펙 §9). 옛/새는 방언마다 같아야 한다.
    ("flag_string_true", "RECEIVED", True, {"meta": {"draft": "true"}}, False, None),
    ("flag_string_false", "RECEIVED", True, {"meta": {"draft": "false"}}, False, None),
)

CASE_KEYS = tuple(case[0] for case in _CASES)
HIDDEN_ORDER_KEYS = ("hidden_real_order", "hidden_real_order_received")
FIRST_CASE_ID = 900001


def case_row(order_id: int, key: str, status: str, is_erp: bool, structured: Any, deleted: bool,
             original_status: str | None) -> dict[str, Any]:
    """경우 하나를 orders 행 값으로 만든다(``_SQL_NULL`` 이면 ``structured_data`` 를 뺀다)."""
    row: dict[str, Any] = {
        "id": order_id,
        "received_date": "2026-07-01",
        "customer_name": f"draftcase-{key}",
        "phone": "010-0000-0000",
        "address": "서울",
        "product": "붙박이장",
        "status": status,
        "original_status": original_status,
        "is_erp_order": is_erp,
        "deleted_at": _DELETED_AT if deleted else None,
    }
    if structured is not _SQL_NULL:
        row["structured_data"] = structured
    return row


def insert_cases(conn: Connection, first_id: int = FIRST_CASE_ID) -> dict[int, str]:
    """경우 행을 하나씩 넣고 ``{id: key}`` 를 돌려준다(칸 묶음이 행마다 달라 한 줄씩 넣는다)."""
    ids: dict[int, str] = {}
    for offset, case in enumerate(_CASES):
        order_id = first_id + offset
        conn.execute(insert(Order.__table__).values(case_row(order_id, *case)))
        ids[order_id] = case[0]
    return ids
