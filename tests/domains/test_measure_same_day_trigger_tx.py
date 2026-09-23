"""당일 실측 긴급 추가 알림 — 판정 규칙·savepoint 계약(``test_measure_same_day_trigger`` 의 짝).

* 순수 판정: 트랜잭션 처음 값(origin) 기준, 드래프트 규칙, 멱등 키 모양.
* savepoint: 감사 로그 ``log_access`` 는 저장마다 savepoint 를 연다. savepoint 커밋·롤백이
  바깥 트랜잭션의 판정을 훔치거나(알림 누락) 되돌려진 값으로 알리면(허위 알림) 안 된다.
"""

from __future__ import annotations

import copy

from db import db_session
from foms.services.notifications import measure_same_day as msd
from tests.domains.test_measure_same_day_trigger import (  # noqa: F401 - fixture 재사용
    TODAY,
    TOMORROW,
    _assert_single_alert,
    _erp_sd,
    _login,
    _make_order,
    _make_user,
    _outbox_rows,
    _state_user_ids,
    captured,
    clock,
    sales,
)


# --------------------------------------------------------------------------- #
# 4. 순수 판정
# --------------------------------------------------------------------------- #
class _FakeSession:
    def __init__(self) -> None:
        self.info: dict = {}


def test_detect_keeps_transaction_origin(clock):
    s, order = _FakeSession(), object()
    assert msd.detect_same_day_additions(s, order, {TOMORROW}, {TODAY}, False, False) == TODAY
    # 두 번째 flush: before 는 이미 오늘이지만 origin 은 처음 값(내일)이다.
    assert msd.detect_same_day_additions(s, order, {TODAY}, {TODAY}, False, False) == TODAY
    # 마지막 flush 에서 오늘이 빠지면 판정도 사라진다.
    assert msd.detect_same_day_additions(s, order, {TODAY}, {TOMORROW}, False, False) is None


def test_detect_draft_rules(clock):
    assert msd.detect_same_day_additions(_FakeSession(), object(), set(), {TODAY}, False, True) is None
    assert msd.detect_same_day_additions(_FakeSession(), object(), {TODAY}, {TODAY}, True, False) == TODAY
    assert msd.detect_same_day_additions(_FakeSession(), object(), {TODAY}, {TODAY}, False, False) is None


def test_dedupe_key_shape():
    assert msd.build_dedupe_key(42, TODAY) == "meas_same_day:42:2026-09-23"


# --------------------------------------------------------------------------- #
# 5. savepoint (감사 로그 log_access 가 저장마다 연다)
# --------------------------------------------------------------------------- #
def test_savepoint_commit_does_not_steal_outer_verdict(app, clock, captured, sales):
    """savepoint 커밋에도 before/after_commit 이 온다 — 바깥 커밋 때 한 번만 알린다."""
    order = _make_order(_erp_sd(TOMORROW))
    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TODAY
    order.structured_data = sd
    db_session.flush()
    savepoint = db_session.begin_nested()
    savepoint.commit()
    assert _outbox_rows() == []  # 아직 바깥 커밋 전
    db_session.commit()
    _assert_single_alert(order.id, {sales["sales"]})


def test_savepoint_rollback_keeps_change_flushed_before_it(app, clock, captured, sales):
    """savepoint 밖에서 flush 된 변경은 savepoint 롤백 뒤에도 살아 있으니 알린다."""
    order = _make_order(_erp_sd(TOMORROW))
    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TODAY
    order.structured_data = sd
    db_session.flush()
    savepoint = db_session.begin_nested()
    savepoint.rollback()
    db_session.commit()
    _assert_single_alert(order.id, {sales["sales"]})


def test_savepoint_rollback_of_the_change_itself_creates_nothing(app, clock, captured, sales):
    """오늘로 바꾼 flush 가 savepoint 안에서 되돌려졌다면 알리지 않는다."""
    order = _make_order(_erp_sd(TOMORROW))
    order_id = order.id
    savepoint = db_session.begin_nested()
    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TODAY
    order.structured_data = sd
    db_session.flush()
    savepoint.rollback()
    db_session.commit()
    assert _outbox_rows(order_id) == []


# --------------------------------------------------------------------------- #
# 6. 쓰기 경로 보강 · 추가한 본인 수신
# --------------------------------------------------------------------------- #
def test_call_log_measurement_today_creates_single_alert(client, clock, captured, sales):
    """통화 기록 API 로 실측일을 오늘로 잡아도 같은 훅을 지나 outbox 1행이 생긴다."""
    _login(client, _make_user("msd_call", role="ADMIN", team="CS"))
    order_id = _make_order(_erp_sd(TOMORROW)).id
    resp = client.post(
        f"/api/orders/{order_id}/call-log",
        json={"result": "schedule_confirmed", "measurement_date": TODAY},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    _assert_single_alert(order_id, {sales["sales"], sales["measure"]})


def test_sales_user_who_added_it_also_receives(client, clock, captured, sales):
    """추가한 본인(영업)도 받는다(스펙 §8-1)."""
    actor = _make_user("msd_self", role="ADMIN", team="SALES")
    actor_id = actor.id
    _login(client, actor)
    order_id = _make_order(_erp_sd(TOMORROW)).id
    resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd(TODAY)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    notif = _assert_single_alert(order_id, {sales["sales"]})
    assert notif.created_by_user_id == actor_id
    assert actor_id in _state_user_ids(notif.id)
