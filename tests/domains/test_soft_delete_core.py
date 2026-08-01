"""DELETE-CORE-00 canonical soft-delete/restore 계약 테스트.

delete 축 projection(``deleted_at``)만 set/clear 되고 main/overlay 축은 보존되며,
``mutation_version`` bump + OrderEvent 기록 + hard-delete 미발생 + status string 미기록 +
멱등 no-op + version 충돌 409 를 고정한다.

기본 lane 은 self-contained **SQLite in-memory**(외부 의존 0)라 ``pytest`` 만으로 green.
``FOMS_TEST_DATABASE_URL`` (local admin DSN)이 있으면 같은 파일이 throwaway ``foms_test_*``
PostgreSQL DB 로 실행된다(+PG green). 비밀번호는 env 로만 주입 — 커밋 파일엔 없다.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Iterator, Tuple

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# app import 로 모든 모델을 Base.metadata 에 등록(root conftest 가 이미 import 했으면 no-op).
import app  # noqa: F401
from db import Base
from models import Order, OrderEvent, OrderMutationReceipt, User
from foms.services.orders.revision import RevisionConflictError
from foms.services.orders.soft_delete import (
    EVENT_RESTORED,
    EVENT_SOFT_DELETED,
    restore_order,
    soft_delete_order,
)
from foms.services.orders.state_axes import read_state_axes
from tests.postgres.conftest import (
    assert_local_admin_url,
    assert_test_db_name,
    _admin_dsn_from_env,
    _raw_connect,
)

_SEQ = [0]


def _make_pg_engine() -> Tuple[Engine, "callable"]:
    """throwaway ``foms_test_*`` PG DB 를 만들고 (engine, drop) 을 돌려준다.

    tests/postgres/conftest 의 안전 helper(local-only host·foms_test_ 접두어 강제·env DSN)
    를 재사용한다. 커밋 파일에 비밀번호를 넣지 않는다.
    """
    admin_url = assert_local_admin_url(_admin_dsn_from_env())
    admin_dbname = admin_url.database or "postgres"
    db_name = assert_test_db_name(f"foms_test_delcore_{uuid.uuid4().hex[:12]}")

    conn = _raw_connect(admin_url, admin_dbname)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()

    engine = create_engine(
        admin_url.set(drivername="postgresql+psycopg2", database=db_name),
        connect_args={"client_encoding": "utf8"},
    )

    def _drop() -> None:
        engine.dispose()
        assert_test_db_name(db_name)  # defense in depth before DROP
        c = _raw_connect(admin_url, admin_dbname)
        c.autocommit = True
        try:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            c.close()

    return engine, _drop


@pytest.fixture
def session() -> Iterator[Session]:
    """DELETE-CORE 전용 세션. FOMS_TEST_DATABASE_URL 있으면 PG, 없으면 SQLite in-memory."""
    if _admin_dsn_from_env():
        engine, drop = _make_pg_engine()
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        drop = engine.dispose

    Base.metadata.create_all(bind=engine)
    sess = sessionmaker(bind=engine)()
    try:
        yield sess
    finally:
        sess.close()
        drop()


def _make_user(session: Session) -> User:
    _SEQ[0] += 1
    user = User(
        username=f"delcore_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password="pw-not-committed",
        name="작업자",
        role="ADMIN",
        is_active=True,
    )
    session.add(user)
    session.commit()
    return user


def _make_order(session: Session, **kw) -> Order:
    """다축(main=PRODUCTION·logistics=SCHEDULED·hold=HELD) order 로 축 보존을 검증한다."""
    order = Order(
        received_date="2026-07-24",
        customer_name="홍길동",
        phone="010-0000-0000",
        address="서울",
        product="침대",
        status="PRODUCTION",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "PRODUCTION", "hold": {"active": True}},
            "shipment": {"logistics_status": "SCHEDULED"},
        },
        erp_stage_code="PRODUCTION",
    )
    for k, v in kw.items():
        setattr(order, k, v)
    session.add(order)
    session.commit()
    return order


def _events(session: Session, order_id: int, event_type: str) -> int:
    return (
        session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .count()
    )


def test_soft_delete_sets_projection_and_preserves_all_other_axes(session: Session) -> None:
    actor = _make_user(session)
    order = _make_order(session)
    before = read_state_axes(order)
    assert before.deleted == "NONE"
    assert order.mutation_version == 1

    result = soft_delete_order(
        session, order_id=order.id, actor_user_id=actor.id, reason="검수 반려"
    )
    session.commit()

    assert result is not None and result.replayed is False
    session.refresh(order)
    axes = read_state_axes(order)
    # delete projection set, 나머지 축 전부 보존.
    assert axes.deleted == "DELETED"
    assert axes.main == before.main == "PRODUCTION"
    assert axes.logistics == before.logistics == "SCHEDULED"
    assert axes.hold == before.hold == "HELD"
    assert axes.as_status == before.as_status
    assert axes.construction == before.construction
    # projection SSOT = deleted_at 컬럼; status string 은 직접 저장하지 않는다.
    assert order.deleted_at is not None
    assert order.status == "PRODUCTION"
    # version bump + delete metadata + event.
    assert order.mutation_version == 2
    assert order.structured_data["delete"] == {
        "deleted_by": actor.id,
        "deleted_at": order.deleted_at,
        "reason": "검수 반려",
    }
    assert _events(session, order.id, EVENT_SOFT_DELETED) == 1


def test_restore_clears_projection_and_preserves_axes(session: Session) -> None:
    actor = _make_user(session)
    order = _make_order(session)
    soft_delete_order(session, order_id=order.id, actor_user_id=actor.id, reason="x")
    session.commit()

    result = restore_order(session, order_id=order.id, actor_user_id=actor.id)
    session.commit()

    assert result is not None
    session.refresh(order)
    axes = read_state_axes(order)
    assert axes.deleted == "NONE"
    assert order.deleted_at is None
    assert "delete" not in (order.structured_data or {})
    # 나머지 축 여전히 보존, status 불변, version 두 번 bump(delete→restore).
    assert axes.main == "PRODUCTION"
    assert axes.logistics == "SCHEDULED"
    assert axes.hold == "HELD"
    assert order.status == "PRODUCTION"
    assert order.mutation_version == 3
    assert _events(session, order.id, EVENT_RESTORED) == 1


def test_repeated_soft_delete_is_idempotent_noop(session: Session) -> None:
    actor = _make_user(session)
    order = _make_order(session)
    soft_delete_order(session, order_id=order.id, actor_user_id=actor.id)
    session.commit()
    session.refresh(order)
    version_after_first = order.mutation_version
    deleted_at_after_first = order.deleted_at

    # 이미 삭제 → no-op(version/event 폭주 없음).
    second = soft_delete_order(session, order_id=order.id, actor_user_id=actor.id)
    session.commit()

    assert second is None
    session.refresh(order)
    assert order.mutation_version == version_after_first
    assert order.deleted_at == deleted_at_after_first
    assert _events(session, order.id, EVENT_SOFT_DELETED) == 1


def test_repeated_restore_on_live_order_is_idempotent_noop(session: Session) -> None:
    actor = _make_user(session)
    order = _make_order(session)  # 삭제된 적 없음

    result = restore_order(session, order_id=order.id, actor_user_id=actor.id)
    session.commit()

    assert result is None
    session.refresh(order)
    assert order.mutation_version == 1
    assert order.deleted_at is None
    assert _events(session, order.id, EVENT_RESTORED) == 0


def test_soft_delete_version_conflict_409_no_change(session: Session) -> None:
    actor = _make_user(session)
    order = _make_order(session)  # version 1

    with pytest.raises(RevisionConflictError) as ei:
        soft_delete_order(
            session,
            order_id=order.id,
            actor_user_id=actor.id,
            expected_version=99,  # stale
        )
    session.rollback()

    assert ei.value.current_versions == {order.id: 1}
    fresh = session.query(Order).filter_by(id=order.id).one()
    assert fresh.mutation_version == 1
    assert fresh.deleted_at is None
    assert read_state_axes(fresh).deleted == "NONE"
    assert _events(session, order.id, EVENT_SOFT_DELETED) == 0


def test_soft_delete_does_not_hard_delete_or_write_status_string(session: Session) -> None:
    actor = _make_user(session)
    order = _make_order(session)
    order_id = order.id

    soft_delete_order(session, order_id=order_id, actor_user_id=actor.id)
    session.commit()

    # hard delete 아님 — row 물리 잔존.
    survivor = session.query(Order).filter_by(id=order_id).one_or_none()
    assert survivor is not None
    # status string 을 'DELETED' 로 직접 저장하지 않는다(projection 경유).
    assert survivor.status == "PRODUCTION"
