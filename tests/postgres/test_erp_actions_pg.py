"""ERP 할 일 제안 PostgreSQL 레인(설계서 2026-11-14-foms-graft 3.4 · 10) — 부분 유일 색인 · 줄 잠금 · 동시 승인 한 번만.

- 부분 유일 색인 ``uq_erp_action_proposals_open_dedupe``: 같은 열쇠의 ``open`` 은 둘이 될 수 없다(``rejected`` 와는 같이 있다).
- 겹침 확인을 지난 동시 만들기는 색인에 걸려 저장점만 되감기고(``None``) 바깥 트랜잭션은 그대로 쓸 수 있다.
- 두 연결이 같은 제안을 동시에 승인하면 실행기는 한 번만 돈다(제안 줄 ``FOR UPDATE`` — 다른 쪽은 ``ACTION_NOT_OPEN``).
``FOMS_TEST_DATABASE_URL`` 이 없으면 conftest 가 레인을 건너뛴다. 합성 계정 · 합성 주문만.
"""

from __future__ import annotations

import datetime
import threading
import time

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.persistence.graft.models import ErpActionProposal
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import lifecycle
from foms.services.erp_actions.lifecycle import ActionError, approve, propose
from foms.services.erp_actions.runners import RunOutcome
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order, User

_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _seed(pg_engine) -> tuple[int, int]:
    """ADMIN 한 명 · 주문 하나를 커밋한다 — (사용자 번호, 주문 번호)."""
    _SEQ[0] += 1
    session = _session(pg_engine)
    try:
        admin = User(username=f"pg_ea_{_SEQ[0]}_{int(time.time() * 1000) % 100000}", role="ADMIN", is_active=True,
                     password=generate_password_hash("pw"), name="합성 관리자")
        sd = {"workflow": {"stage": "RECEIVED"}}
        order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                      product="합성 품목", status="RECEIVED", is_erp_order=True, structured_data=sd)
        sync_erp_flat_columns(order, sd)
        session.add_all([admin, order])
        session.commit()
        return admin.id, order.id
    finally:
        session.close()


def _propose(session, order, *, day_offset: int = 9):
    day = (get_today_kst() + datetime.timedelta(days=day_offset)).isoformat()
    return propose(session, action="schedule_construction", proposed_by="agent:schedule", order=order,
                   params={"date": day, "time": "오전"}, reason="합성 이유", evidence=[], source_kind="sweep",
                   source_ref="1", level=2, now=now_utc_naive())


def _row(dedupe: str, status: str, order_id: int) -> ErpActionProposal:
    return ErpActionProposal(action="schedule_construction", proposed_by="agent:schedule", order_id=order_id,
                             params={}, preview=[], level=2, status=status, dedupe_key=dedupe,
                             created_at=now_utc_naive())


def test_partial_unique_index_allows_one_open_per_key(pg_engine):
    _admin_id, order_id = _seed(pg_engine)
    session = _session(pg_engine)
    try:
        session.add_all([_row("pg:key", "open", order_id), _row("pg:key", "rejected", order_id)])
        session.commit()
        session.add(_row("pg:key", "open", order_id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.query(ErpActionProposal).filter_by(dedupe_key="pg:key").count() == 2
    finally:
        session.close()


def test_racing_propose_rolls_back_only_its_savepoint(pg_engine, monkeypatch):
    _admin_id, order_id = _seed(pg_engine)
    first, second = _session(pg_engine), _session(pg_engine)
    try:
        assert _propose(first, first.get(Order, order_id)) is not None
        first.commit()
        monkeypatch.setattr(lifecycle, "_taken", lambda session, key: False)  # 겹침 확인을 지난 동시 만들기 흉내
        assert _propose(second, second.get(Order, order_id)) is None
        assert second.query(ErpActionProposal).filter_by(order_id=order_id).count() == 1  # 바깥 트랜잭션은 살아 있다
        second.commit()
    finally:
        first.close()
        second.close()


def test_concurrent_approve_runs_the_runner_once(pg_engine):
    admin_id, order_id = _seed(pg_engine)
    setup = _session(pg_engine)
    try:
        row = _propose(setup, setup.get(Order, order_id))
        setup.commit()
        proposal_id, base = row.id, row.base_version
    finally:
        setup.close()
    runs: list[int] = []
    outcomes: list[str] = []
    gate = threading.Barrier(2)

    def slow_runner(session, req):
        runs.append(req.proposal_id)
        time.sleep(0.5)
        return RunOutcome.executed("합성 실행")

    def worker() -> None:
        session = _session(pg_engine)
        try:
            actor = session.get(User, admin_id)
            gate.wait(timeout=10)
            out = approve(session, proposal_id, actor=actor, runners={"schedule_construction": slow_runner},
                          base_version=base, now=now_utc_naive())
            outcomes.append(out["status"])
        except ActionError as exc:
            session.rollback()
            outcomes.append(exc.code)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert runs == [proposal_id]
    assert sorted(outcomes) == ["ACTION_NOT_OPEN", "executed"]
    check = _session(pg_engine)
    try:
        assert check.get(ErpActionProposal, proposal_id).status == "executed"
    finally:
        check.close()
