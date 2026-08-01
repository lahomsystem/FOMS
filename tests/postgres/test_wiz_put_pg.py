"""WIZ-01 PostgreSQL 동시성 계약 테스트 (PGTEST-00 lane).

도면 마법사 PUT 이 REV-00 ``FOR UPDATE`` 로 직렬화될 때, 서버 소유 ``pending`` 이
동시 저장 사이에서 소실되지 않음을(P0-4) 실 PostgreSQL 다중 커밋 세션으로 증명한다.
route 의 락 아래 로직(``session.refresh`` → :func:`_project_wizard_state` → updated_*)을
그대로 미러하는 mutation 콜러블을 REV-00 :func:`execute_order_mutation` 에 넣어 검증한다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에
비밀번호를 넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import threading
import time

from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from foms.api.drawing.wizard import _load_structured_data, _project_wizard_state
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.revision import execute_order_mutation
from models import Order, User

_H = "a" * 64
_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_user(session):
    _SEQ[0] += 1
    u = User(
        username=f"wiz_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password="pw-not-committed",
        name="도면작업자",
        role="ADMIN",
        team="DRAWING",
        is_active=True,
    )
    session.add(u)
    session.commit()
    return u


def _make_order_with_pending(session):
    """pending 1건이 이미 있는 drawing_wizard 를 가진 ERP 주문."""
    o = Order(
        received_date="2026-07-24",
        customer_name="서으뜸",
        phone="010-0000-0000",
        address="대구",
        product="붙박이장",
        is_erp_order=True,
        structured_data={
            "drawing_wizard": {
                "v": 1,
                "sheets": [{"id": "s-1", "name": "seed", "form": {}, "objects": []}],
                "pending": {
                    "s-1": {"key": "orders/x/exports/1_a.png", "filename": "a.png",
                            "at": "2026-07-07 10:00", "sheet_name": "도면 1"},
                },
                "updated_at": "2026-07-24 00:00:00",
            }
        },
    )
    session.add(o)
    session.commit()
    return o


def _wizard_mutate(actor, sheet_name, *, hold_event=None, sleep_s=0.0):
    """route 의 락-아래 로직(refresh → projection → updated_*)을 미러한 콜러블."""

    def _m(session, orders):
        o = orders[0]
        session.refresh(o)
        sd = _load_structured_data(o)
        saved = sd.get("drawing_wizard")
        state = {"v": 1, "sheets": [{"id": "s-1", "name": sheet_name, "form": {}, "objects": []}]}
        projected = _project_wizard_state(saved, state)
        projected["updated_at"] = now_utc_naive().strftime("%Y-%m-%d %H:%M:%S.%f")
        projected["updated_by"] = actor.id
        projected["updated_by_name"] = actor.name
        sd["drawing_wizard"] = projected
        o.structured_data = sd
        flag_modified(o, "structured_data")
        if hold_event is not None:
            hold_event.set()
        if sleep_s:
            time.sleep(sleep_s)  # 락을 잡은 채 대기 → 경합 스레드가 FOR UPDATE 로 블록
        return {o.id: ["ORDER_DETAIL:%d" % o.id]}

    return _m


def test_concurrent_wizard_put_serialized_preserves_pending(pg_engine):
    """동시 PUT 두 건이 직렬화되고(version 2,3) 서버 pending 이 소실되지 않는다."""
    setup = _session(pg_engine)
    try:
        actor = _make_user(setup)
        order = _make_order_with_pending(setup)
        order_id, actor_id, actor_name = order.id, actor.id, actor.name
    finally:
        setup.close()

    started = threading.Event()
    versions: dict[str, int] = {}

    def _run(tag, sheet_name, hold):
        sess = _session(pg_engine)
        try:
            actor_obj = sess.query(User).filter_by(id=actor_id).one()
            res = execute_order_mutation(
                sess,
                actor_user_id=actor_id,
                policy_id="DRAWING_WIZARD_PUT",
                order_ids=[order_id],
                scope_hash=_H,
                request_hash=_H,
                mutation=_wizard_mutate(
                    actor_obj, sheet_name,
                    hold_event=started if hold else None,
                    sleep_s=0.6 if hold else 0.0,
                ),
            )
            sess.commit()
            versions[tag] = res.body["resources"][0]["resulting_version"]
        finally:
            sess.close()

    ta = threading.Thread(target=_run, args=("A", "sheet-A", True))
    ta.start()
    started.wait(2.0)
    tb = threading.Thread(target=_run, args=("B", "sheet-B", False))
    tb.start()
    ta.join(5.0)
    tb.join(5.0)

    # 직렬화 → version 단조(2,3), lost update 0.
    assert sorted(versions.values()) == [2, 3], versions

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=order_id).one()
        dw = o.structured_data["drawing_wizard"]
        assert o.mutation_version == 3
        # 핵심: 두 동시 저장을 거쳐도 서버 pending 이 그대로 보존된다(P0-4).
        assert set(dw["pending"].keys()) == {"s-1"}
        # 마지막 writer 의 sheets 가 반영된다(둘 중 하나).
        assert dw["sheets"][0]["name"] in ("sheet-A", "sheet-B")
    finally:
        check.close()
