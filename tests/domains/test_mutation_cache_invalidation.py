"""MUT-CACHE-01: canonical order mutation → dashboard 캐시 자동 무효화 계약.

2026-08-10 운영 사고(#4717 삭제 후 실측 집계 5분 잔존)와 스테이징 재현(단계 강제 변경 후
주문 단계별 건수 310초 지연)의 공통 원인은 **라우트마다 손으로 붙이는 무효화**였다. 붙이는
걸 잊으면 조용히 TTL(300초)만큼 stale 이 된다.

그래서 :func:`foms.services.orders.revision.execute_order_mutation` 이 무효화 intent 를
``session.info`` 에 남기고, ``after_commit`` 리스너가 커밋 성공 뒤 소비한다. 이 파일은
그 두 축을 고정한다:

* intent 기록 — 변경 전/후 stage 수집, 삭제(TRASH_INDEX)는 broad 표식.
* 소비 — 커밋 후 무효화 1회, 롤백 시 무효화 0(그리고 다음 트랜잭션으로 누출 없음).
"""

from types import SimpleNamespace

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User
from foms.services.common import dashboard_cache as dc
from foms.services.orders.revision import execute_order_mutation
from foms.services.orders.soft_delete import soft_delete_order


def _make_user(username):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_order(stage="MEASURE"):
    order = Order(
        received_date="2026-08-10",
        customer_name="홍길동",
        phone="010-0000-0000",
        address="서울",
        product="침대",
        status=stage,
        is_erp_order=True,
        erp_stage_code=stage,
        structured_data={"workflow": {"stage": stage}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _pop_intent():
    return db_session.info.pop(dc.MUTATION_CACHE_INTENT_KEY, None)


# --- intent 기록 (엔진 쪽) ---------------------------------------------------


def test_mutation_records_stage_move_intent(app):
    """단계 이동 mutation 은 변경 전/후 stage 를 intent 에 남긴다(양쪽 탭 무효화 근거)."""
    actor = _make_user("mutcache_actor_1")
    order = _make_order("MEASURE")
    _pop_intent()

    def _mutate(session, orders):
        o = orders[0]
        o.erp_stage_code = "CONSTRUCTION"
        o.structured_data = {"workflow": {"stage": "CONSTRUCTION"}}
        return {o.id: ["ORDERS_INDEX", f"ORDER_DETAIL:{o.id}"]}

    execute_order_mutation(
        db_session,
        actor_user_id=actor.id,
        policy_id="TEST_MUT_CACHE",
        order_ids=[order.id],
        scope_hash="scope",
        request_hash="req",
        mutation=_mutate,
    )

    # 커밋 전에 확인한다 — 커밋하면 after_commit 리스너가 intent 를 소비(pop)한다.
    intent = db_session.info.get(dc.MUTATION_CACHE_INTENT_KEY)
    assert intent is not None, "mutation 이 무효화 intent 를 남기지 않았다"
    assert intent["broad"] is False
    assert "MEASURE" in intent["stages"] and "CONSTRUCTION" in intent["stages"]
    assert set(dc.dashboard_families_for_mutation_intent(intent)) == {
        "orders",
        "measurement",
        "construction",
    }

    db_session.commit()
    # 앱에 배선된 리스너가 실제로 소비했는지(end-to-end 배선) 확인.
    assert dc.MUTATION_CACHE_INTENT_KEY not in db_session.info


def test_soft_delete_records_broad_intent(app):
    """삭제는 전 탭에서 사라지는 전이 → intent 가 broad(=전체 family)."""
    actor = _make_user("mutcache_actor_2")
    order = _make_order("MEASURE")
    _pop_intent()

    soft_delete_order(db_session, order_id=order.id, actor_user_id=actor.id)

    intent = db_session.info.get(dc.MUTATION_CACHE_INTENT_KEY)
    assert intent is not None and intent["broad"] is True
    assert dc.dashboard_families_for_mutation_intent(intent) == dc.ALL_DASHBOARD_FAMILIES

    db_session.commit()
    assert dc.MUTATION_CACHE_INTENT_KEY not in db_session.info


# --- intent 소비 (리스너 쪽) -------------------------------------------------


def _capture_listeners(monkeypatch):
    """register_* 가 등록하는 리스너를 실제 Session 에 붙이지 않고 가로챈다."""
    captured = {}

    def _fake_listens_for(target, event_name):
        def _decorator(fn):
            captured[event_name] = fn
            return fn

        return _decorator

    monkeypatch.setattr("sqlalchemy.event.listens_for", _fake_listens_for)
    dc.register_dashboard_cache_invalidation_listener()
    return captured


def test_listener_invalidates_once_after_commit(monkeypatch):
    seen = []
    monkeypatch.setattr(dc, "invalidate_dashboard_families", lambda *f: seen.extend(f) or len(f))
    listeners = _capture_listeners(monkeypatch)

    session = SimpleNamespace(info={dc.MUTATION_CACHE_INTENT_KEY: {"broad": False, "stages": ["MEASURE", "MEASURE"]}})
    listeners["after_commit"](session)
    listeners["after_commit"](session)  # intent 는 pop 되므로 두 번째 커밋은 무효화 없음

    assert seen == ["orders", "measurement"]
    assert dc.MUTATION_CACHE_INTENT_KEY not in session.info


def test_listener_does_nothing_without_intent(monkeypatch):
    seen = []
    monkeypatch.setattr(dc, "invalidate_dashboard_families", lambda *f: seen.extend(f) or len(f))
    listeners = _capture_listeners(monkeypatch)

    listeners["after_commit"](SimpleNamespace(info={}))

    assert seen == []


def test_rollback_drops_intent_so_next_commit_does_not_invalidate(monkeypatch):
    """롤백된 트랜잭션의 의도가 다음 트랜잭션으로 새면 안 된다(무효화 오발)."""
    seen = []
    monkeypatch.setattr(dc, "invalidate_dashboard_families", lambda *f: seen.extend(f) or len(f))
    listeners = _capture_listeners(monkeypatch)

    session = SimpleNamespace(info={dc.MUTATION_CACHE_INTENT_KEY: {"broad": True, "stages": []}})
    listeners["after_soft_rollback"](session, None)
    listeners["after_commit"](session)

    assert seen == []


def test_listener_failure_is_swallowed_with_log(monkeypatch, caplog):
    """무효화 실패가 이미 커밋된 업무 변경을 되돌릴 수는 없다 — fail-open + 로그."""
    def _boom(*_families):
        raise RuntimeError("redis down")

    monkeypatch.setattr(dc, "invalidate_dashboard_families", _boom)
    listeners = _capture_listeners(monkeypatch)

    session = SimpleNamespace(info={dc.MUTATION_CACHE_INTENT_KEY: {"broad": False, "stages": ["MEASURE"]}})
    with caplog.at_level("WARNING"):
        listeners["after_commit"](session)

    assert "mutation invalidate failed" in caplog.text
