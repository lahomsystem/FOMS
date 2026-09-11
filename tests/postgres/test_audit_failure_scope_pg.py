"""감사 기록 실패가 호출자 트랜잭션을 죽이지 않는다 — 실 PostgreSQL 계약 (2026-09-11).

도메인(SQLite) 레인의 ``tests/domains/test_audit_failure_scope.py`` 와 같은 축이지만,
**SAVEPOINT 의미론은 백엔드마다 다르다**. 운영은 PostgreSQL 이므로 여기서 한 번 더 고정한다.

``log_access`` 는 감사 행을 SAVEPOINT 안에서 쓰고, 실패하면 그 savepoint 만 되감는다.
예전 구현은 호출자 세션을 통째로 ``rollback()`` 해서, ``auto_commit=False`` 로 호출자
트랜잭션에 얹는 자리(초안 등록)는 감사 한 줄 실패로 방금 만든 주문이 사라졌다.
"""

from __future__ import annotations

from sqlalchemy import text

from models import Order, SecurityLog
from foms.web.auth import routes as auth_routes
from foms.web.auth.routes import log_access

_ACTION_FAIL = "PGTEST_AUDIT_FAIL"
_ACTION_OK = "PGTEST_AUDIT_OK"


def _pending_order(pg_session) -> int:
    """커밋하지 않고 flush 만 한 주문 = 호출자가 쌓아둔 작업."""
    order = Order(
        received_date="2026-09-11",
        customer_name="감사 범위 대상 PG",
        phone="010-3333-4444",
        address="Seoul",
        product="Kitchen",
        status="RECEIVED",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    pg_session.add(order)
    pg_session.flush()
    return int(order.id)


def test_audit_failure_keeps_caller_work_on_postgres(pg_session, monkeypatch):
    """감사 flush 가 깨져도 호출자의 주문은 커밋된다(JSONB 직렬화 실패 주입)."""
    order_id = _pending_order(pg_session)
    monkeypatch.setattr(
        auth_routes, "normalize_security_detail", lambda _detail: {"broken": {1, 2}}
    )

    log_access("감사 실패 주입", None, auto_commit=False, action=_ACTION_FAIL, db=pg_session)
    pg_session.commit()

    survived = pg_session.execute(
        text("SELECT COUNT(*) FROM orders WHERE id = :oid"), {"oid": order_id}
    ).scalar_one()
    assert survived == 1, "감사 실패가 호출자의 주문을 되감았다"

    audit_rows = (
        pg_session.query(SecurityLog).filter(SecurityLog.action == _ACTION_FAIL).count()
    )
    assert audit_rows == 0, "깨진 감사 행이 남았다"


def test_normal_audit_row_is_committed_on_postgres(pg_session):
    """음성 대조군 — 주입하지 않으면 감사 행이 실제로 남는다(savepoint 가 정상 release)."""
    order_id = _pending_order(pg_session)
    log_access(
        "정상 기록",
        None,
        auto_commit=False,
        action=_ACTION_OK,
        target_type="order",
        target_id=order_id,
        detail={"draft_key": "pg-lane"},
        db=pg_session,
    )
    pg_session.commit()

    row = pg_session.query(SecurityLog).filter(SecurityLog.action == _ACTION_OK).one()
    assert row.target_id == order_id
    assert row.detail["draft_key"] == "pg-lane"
