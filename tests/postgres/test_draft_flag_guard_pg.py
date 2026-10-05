"""초안 표식 규칙의 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite 도메인 레인(``tests/domains/test_draft_flag_invariant_monitor.py``·
``test_erp_draft_flag_invariant.py``·``test_trash_restore_draft.py``)이 못 증명하는 것만 본다.

1. 감시 술어(:func:`hidden_draft_shape_filter`)가 실 JSONB 에서 "화면 술어가 숨기는데 status 는 실제
   단계인 ERP 행"과 **정확히 같은 집합**을 낸다 — 글자 ``"true"`` 표식처럼 화면이 숨기는 모양도 센다.
   음성 대조군(정상 초안·승격 주문·버린 초안·정본 삭제 초안·비ERP)은 세지 않는다.
2. 감시 도구의 연결은 정말 읽기 전용이다 — 같은 세션의 쓰기가 SQLSTATE 25006 으로 막힌다.
3. 정본 전이의 잠금 아래 백스톱 — 실 ``FOR UPDATE`` 로 잠근 초안 행에 ``DraftNotPromotedError``.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError

import foms.api.orders.status  # noqa: F401  (정본 전이 command SET_MAIN_STAGE 등록)
from foms.services.db_url_resolver import pg_error_code
from foms.services.orders.draft_guard import (
    DraftNotPromotedError,
    is_unrestorable_trashed_draft,
)
from foms.services.orders.order_transition_service import transition_order
from models import Order, User
from tools.ops import check_draft_flag_invariant as monitor

_TRASHED = "2026-10-05 00:00:00"


def _row(key: str, *, status: str, flag, erp: bool = True, deleted_at=None) -> dict:
    meta = {} if flag is None else {"draft": flag}
    return {
        "received_date": "2026-10-05", "customer_name": f"감시PG_{key}", "phone": "010-0000-0000",
        "address": "서울", "product": "붙박이장", "status": status, "is_erp_order": erp,
        "deleted_at": deleted_at,
        "structured_data": {"meta": meta, "workflow": {"stage": "MEASURE"}},
    }


_CASES = {
    "hidden_alive": _row("hidden_alive", status="MEASURE", flag=True),
    "hidden_trashed": _row("hidden_trashed", status="RECEIVED", flag=True, deleted_at=_TRASHED),
    "hidden_text_true": _row("hidden_text_true", status="RECEIVED", flag="true"),
    # 음성 대조군
    "draft": _row("draft", status="DRAFT", flag=True),
    "promoted": _row("promoted", status="RECEIVED", flag=False),
    "discarded": _row("discarded", status="DELETED", flag=True, deleted_at=_TRASHED),
    "trashed_draft": _row("trashed_draft", status="DRAFT", flag=True, deleted_at=_TRASHED),
    "non_erp": _row("non_erp", status="MEASURE", flag=True, erp=False),
    "no_meta": _row("no_meta", status="MEASURE", flag=None),
}
_HIDDEN_KEYS = ("hidden_alive", "hidden_trashed", "hidden_text_true")


@pytest.fixture
def committed_cases(pg_engine):
    """다른 연결(읽기 전용 감시 세션)에서도 보이도록 커밋한 경우 행 → {key: id}."""
    ids: dict[str, int] = {}
    with pg_engine.begin() as conn:
        for key, values in _CASES.items():
            ids[key] = conn.execute(insert(Order).values(**values).returning(Order.id)).scalar_one()
    try:
        yield ids
    finally:
        with pg_engine.begin() as conn:
            conn.execute(Order.__table__.delete().where(Order.id.in_(list(ids.values()))))


def test_monitor_counts_exactly_what_screens_hide(pg_engine, committed_cases):
    url = pg_engine.url.render_as_string(hide_password=False)
    session, engine = monitor._make_readonly_session(url)
    try:
        found = {row["id"] for row in monitor.find_hidden_draft_orders(session)}
        # 화면 술어 교차 확인: ERP · status 가 DRAFT/DELETED 아님 · 그런데 화면(휴지통 포함)이 숨긴다.
        screens_hide = set(session.execute(
            select(Order.id).where(
                Order.is_erp_order.is_(True),
                Order.status.notin_(("DRAFT", "DELETED")),
                ~Order.active_including_trashed_filter(),
            )
        ).scalars())
    finally:
        session.close()
        engine.dispose()

    mine = set(committed_cases.values())
    expected = {committed_cases[key] for key in _HIDDEN_KEYS}
    assert found & mine == expected
    assert screens_hide & mine == expected


def test_monitor_session_is_read_only(pg_engine):
    url = pg_engine.url.render_as_string(hide_password=False)
    session, engine = monitor._make_readonly_session(url)
    try:
        with pytest.raises(DBAPIError) as excinfo:
            session.execute(text("UPDATE orders SET notes = notes WHERE id = -1"))
        assert pg_error_code(excinfo.value) == "25006"  # read_only_sql_transaction
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def test_transition_backstop_under_real_row_lock(pg_session):
    actor = User(username="dg_pg_actor", password="x", role="ADMIN", team="CS", name="dg",
                 is_active=True)
    pg_session.add(actor)
    draft = Order(**_row("lock_draft", status="DRAFT", flag=True))
    draft.structured_data = {"meta": {"draft": True}, "workflow": {"stage": "RECEIVED"}}
    pg_session.add(draft)
    pg_session.flush()
    digest = hashlib.sha256(f"dg-pg:{draft.id}".encode("utf-8")).hexdigest()

    with pytest.raises(DraftNotPromotedError):
        transition_order(
            pg_session, command_id="SET_MAIN_STAGE", order_id=draft.id, actor_user_id=actor.id,
            expected_from="RECEIVED", target_value="MEASURE", scope_hash=digest,
            request_hash=digest,
        )

    pg_session.expire_all()
    reloaded = pg_session.get(Order, draft.id)
    assert reloaded.status == "DRAFT"
    assert reloaded.structured_data["meta"]["draft"] is True
    # 휴지통 판정도 실 JSONB 행(dict 로 돌아온 structured_data)에서 같은 답을 낸다.
    assert is_unrestorable_trashed_draft(reloaded) is True
