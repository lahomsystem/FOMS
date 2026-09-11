"""감사 기록 실패의 사정거리는 감사 행 하나다 (2026-09-11).

``log_access`` 는 fail-open 이다 — 감사 한 줄을 못 써도 원 요청을 죽이지 않는다. 그 판단은
옳지만, 예전 구현은 실패 시 **호출자의 세션을 통째로** ``rollback()`` 했다. ``auto_commit=False``
로 호출자 트랜잭션에 얹는 자리(초안 등록 ``foms/api/erp_order_draft.py:660-679``)에서는
감사 한 줄이 실패하면 방금 만든 주문·첨부 승격·초안 삭제가 전부 사라지는데, 호출부는 그것을
모른 채 ``db.commit()`` 으로 빈 트랜잭션을 커밋하고 ``200 + order_id`` 를 돌려줬다.
화면은 등록됐다고 믿고 이동하고 DB 에는 주문이 없다.

이제 감사 행은 SAVEPOINT 안에서 쓰고, 실패하면 그 savepoint 만 되감는다.
``auto_commit=True``(감사가 트랜잭션을 소유)일 때만 예전처럼 넓게 되감는다.

주입 방법: ``normalize_security_detail`` 이 JSON 으로 직렬화할 수 없는 값을 돌려주게 해
flush 를 깨뜨린다. 실패 자리가 **DB flush** 여야 savepoint 경로를 실제로 지난다.
"""

from __future__ import annotations

import logging

import pytest

from db import db_session
from models import Order, SecurityLog
from foms.web.auth import routes as auth_routes
from foms.web.auth.routes import log_access


def _make_pending_order() -> int:
    """커밋하지 않은 채 flush 만 한 주문(= 호출자가 쌓아둔 작업)."""
    order = Order(
        received_date="2026-09-11",
        customer_name="감사 범위 대상",
        phone="010-1111-2222",
        address="Seoul",
        product="Kitchen",
        status="RECEIVED",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.flush()
    return order.id


def _break_audit(monkeypatch) -> None:
    """감사 행 flush 가 깨지게 만든다(set 은 JSON 직렬화가 안 된다)."""
    monkeypatch.setattr(
        auth_routes, "normalize_security_detail", lambda _detail: {"broken": {1, 2}}
    )


def _audit_rows(action: str):
    db_session.expire_all()
    return db_session.query(SecurityLog).filter(SecurityLog.action == action).all()


def test_audit_failure_keeps_caller_work(app, monkeypatch, caplog):
    """auto_commit=False: 감사가 실패해도 호출자가 쌓아둔 주문은 커밋된다."""
    with app.app_context():
        order_id = _make_pending_order()
        _break_audit(monkeypatch)
        with caplog.at_level(logging.WARNING):
            log_access(
                "감사 실패 주입",
                1,
                auto_commit=False,
                action="TEST_AUDIT_FAIL",
                db=db_session,
            )
        db_session.commit()

    db_session.expire_all()
    assert db_session.get(Order, order_id) is not None, "호출자 작업이 감사 실패에 휩쓸렸다"
    assert _audit_rows("TEST_AUDIT_FAIL") == [], "깨진 감사 행이 남았다"
    assert any("[LOG ERROR]" in message for message in caplog.messages), "실패를 조용히 삼켰다"


def test_audit_failure_is_fail_open(app, monkeypatch):
    """감사 실패는 예외로 번지지 않는다(fail-open 유지)."""
    with app.app_context():
        _break_audit(monkeypatch)
        log_access("감사 실패 주입", 1, auto_commit=True, action="TEST_AUDIT_FAIL2")
    assert _audit_rows("TEST_AUDIT_FAIL2") == []


def test_normal_audit_still_written_both_modes(app):
    """음성 대조군 — 주입하지 않으면 두 모드 모두 감사 행이 실제로 남는다."""
    with app.app_context():
        log_access("정상 기록 A", 1, auto_commit=True, action="TEST_AUDIT_OK_A")
        log_access("정상 기록 B", 1, auto_commit=False, action="TEST_AUDIT_OK_B", db=db_session)
        db_session.commit()

    assert len(_audit_rows("TEST_AUDIT_OK_A")) == 1
    assert len(_audit_rows("TEST_AUDIT_OK_B")) == 1


def test_caller_owned_transaction_is_never_rolled_back_by_audit() -> None:
    """소스 계약 — auto_commit=False 에서는 호출자 세션을 되감지 않는다."""
    source = (
        pytest.importorskip("pathlib").Path(auth_routes.__file__).read_text(encoding="utf-8")
    )
    body = source.split("def log_access(")[1].split("\ndef ")[0]
    assert "begin_nested()" in body, "감사 행을 SAVEPOINT 로 감싸지 않는다"
    assert "savepoint.rollback()" in body
    # 넓은 rollback 은 감사가 트랜잭션을 소유할 때만 남는다.
    assert "if auto_commit and session_db is not None:" in body
    assert body.count("session_db.rollback()") == 1
