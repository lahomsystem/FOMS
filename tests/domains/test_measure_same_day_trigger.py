"""당일 실측 긴급 추가 알림 — 감지·예약 계약.

실측일 집합에 **오늘(KST)** 이 새로 들어온 비드래프트 주문만 커밋 뒤 1회 알린다.
여기서 고정하는 것:

* 대표 쓰기 경로(PUT 전체 저장 · PATCH 필드 · 빠른수정 · 마법사 제출 · 레거시 주문 추가)가
  모두 전역 flush 훅을 지나 outbox 1행 + Notification 1건 + 영업 state 를 만든다.
* 허위 알림 0: 내일 · 시간만 변경 · 같은 날 두 번(지웠다 다시 넣기) · 롤백 · 드래프트.
* 드래프트 → 승격 PUT 은 날짜 차이가 없어도 알린다.
* 커밋 뒤 단계가 터져도 요청은 200 이다.

오늘 날짜는 ``measure_same_day.get_today_kst`` 를 바꿔 고정한다(CI 는 UTC 라 실제 날짜를
쓰면 밤에 깨진다). 외부 발송(푸시 enqueue·socket emit)은 전부 가로챈다.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
from typing import Any

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.notifications import measure_same_day as msd
from models import DomainSideEffectOutbox, Notification, NotificationUserState, Order, OrderEvent, User

TODAY = "2026-09-23"
TOMORROW = "2026-09-24"
YESTERDAY = "2026-09-22"


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #
class _Clock:
    """테스트가 도중에 '오늘'을 바꿀 수 있게 하는 가짜 KST 날짜."""

    def __init__(self, iso: str) -> None:
        self.iso = iso

    def __call__(self) -> _dt.date:
        return _dt.date.fromisoformat(self.iso)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock(TODAY)
    monkeypatch.setattr(msd, "get_today_kst", fake)
    return fake


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """커밋 뒤 외부로 나가는 것(푸시 enqueue·socket emit)을 가로챈다."""
    from foms.services.notifications import push_sender, realtime_notifications

    calls: dict[str, list] = {"push": [], "emit": []}
    monkeypatch.setattr(
        push_sender,
        "enqueue_push_for_notification",
        lambda nid, db=None: calls["push"].append(int(nid)) or {"enqueued": True, "reason": None},
    )
    monkeypatch.setattr(
        realtime_notifications,
        "emit_erp_notification_to_users",
        lambda ids, payload=None: calls["emit"].append((sorted(ids), dict(payload or {}))) or len(ids),
    )
    return calls


@pytest.fixture
def inline_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "true")


def _make_user(username: str, *, role: str = "STAFF", team: str | None = None, active: bool = True) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=active,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _erp_sd(measure_date: str = "", *, time: str = "14시", draft: bool = False) -> dict:
    sd: dict[str, Any] = {
        "workflow": {"stage": "RECEIVED"},
        "parties": {
            "customer": {"name": "당일 고객", "phone": "010-1234-5678"},
            "manager": {"name": "김영업"},
        },
        "site": {"address_full": "서울 강남구 테헤란로 123", "address_main": "서울 강남구 테헤란로 123"},
        "items": [{"product_name": "붙박이장"}],
        "schedule": {"measurement": {"date": measure_date, "time": time}} if measure_date else {},
        "shipment": {},
    }
    if draft:
        sd["meta"] = {"draft": True}
    return sd


def _make_order(sd: dict | None, *, status: str = "RECEIVED", is_erp_order: bool = True,
                measurement_date: str | None = None) -> Order:
    order = Order(
        received_date="2026-09-01",
        customer_name="당일 고객",
        phone="010-1234-5678",
        address="서울 강남구 테헤란로 123",
        product="붙박이장",
        status=status,
        manager_name="김영업",
        is_erp_order=is_erp_order,
        structured_data=sd,
        erp_stage_code="RECEIVED" if is_erp_order else None,
        measurement_date=measurement_date,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _outbox_rows(order_id: int | None = None) -> list[DomainSideEffectOutbox]:
    db_session.expire_all()
    rows = db_session.query(DomainSideEffectOutbox).filter(
        DomainSideEffectOutbox.effect_type == msd.EFFECT_TYPE
    ).all()
    if order_id is None:
        return rows
    return [r for r in rows if (r.payload or {}).get("order_id") == order_id]


def _notifications(order_id: int | None = None) -> list[Notification]:
    db_session.expire_all()
    q = db_session.query(Notification).filter(Notification.notification_type == msd.NOTIFICATION_TYPE)
    if order_id is not None:
        q = q.filter(Notification.order_id == order_id)
    return q.all()


def _state_user_ids(notification_id: int) -> set[int]:
    return {
        int(uid)
        for (uid,) in db_session.query(NotificationUserState.user_id).filter(
            NotificationUserState.notification_id == notification_id
        )
    }


def _assert_single_alert(order_id: int, recipients: set[int]) -> Notification:
    rows = _outbox_rows(order_id)
    assert len(rows) == 1, [r.payload for r in rows]
    row = rows[0]
    assert row.dedupe_key == f"meas_same_day:{order_id}:{TODAY}"
    assert row.source_domain == "ORDER_EVENT"
    anchor = db_session.get(OrderEvent, row.order_event_id)
    assert anchor is not None and anchor.event_type == "MEASURE_SAME_DAY_ADDED"
    notifs = _notifications(order_id)
    assert len(notifs) == 1
    notif = notifs[0]
    assert (notif.target_type, notif.target_team, notif.is_urgent) == ("TEAM", "SALES", False)
    assert row.payload["notification_id"] == notif.id
    assert row.payload["date"] == TODAY
    assert recipients <= _state_user_ids(notif.id)
    return notif


@pytest.fixture
def sales(app) -> dict[str, int]:
    """영업 수신자 2명(SALES 표기·MEASURE 표기) + 비수신자 1명."""
    return {
        "sales": _make_user("msd_sales", team="SALES").id,
        "measure": _make_user("msd_measure", team="MEASURE").id,
        "cs": _make_user("msd_cs", team="CS").id,
    }


# --------------------------------------------------------------------------- #
# 1. 대표 쓰기 경로
# --------------------------------------------------------------------------- #
def test_put_full_save_to_today_creates_single_alert(client, clock, captured, sales):
    admin = _make_user("msd_put", role="ADMIN", team="CS")
    admin_id = admin.id
    _login(client, admin)
    order_id = _make_order(_erp_sd(TOMORROW)).id
    assert _outbox_rows() == []

    resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd(TODAY)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    notif = _assert_single_alert(order_id, {sales["sales"], sales["measure"]})
    assert sales["cs"] not in _state_user_ids(notif.id)
    assert notif.created_by_user_id == admin_id
    assert captured["push"] == [notif.id]
    assert len(captured["emit"]) == 1
    ids, payload = captured["emit"][0]
    assert set(ids) >= {sales["sales"], sales["measure"]}
    assert payload["interrupt"] is True
    assert payload["alert_kind"] == "measure_same_day"
    assert "urgent" not in payload
    for key in ("customer_name", "area", "time", "manager", "added_by", "added_at", "order_url"):
        assert key in payload
    assert payload["customer_name"] == "당일 고객"
    assert payload["area"] == "서울 강남구"
    assert payload["time"] == "14시"
    assert payload["manager"] == "김영업"
    assert payload["order_url"] == f"/erp/orders/{order_id}"


def test_patch_field_to_today_creates_alert(client, clock, captured, sales, inline_enabled):
    _login(client, _make_user("msd_patch", role="ADMIN", team="CS"))
    order_id = _make_order(_erp_sd(TOMORROW)).id

    resp = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        json={"field": "schedule.measurement.date", "value": TODAY},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    _assert_single_alert(order_id, {sales["sales"]})


def test_update_order_field_to_today_creates_alert(client, clock, captured, sales):
    _login(client, _make_user("msd_field", role="ADMIN", team="CS"))
    order_id = _make_order(_erp_sd(TOMORROW)).id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "measurement_date", "value": TODAY},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True
    _assert_single_alert(order_id, {sales["sales"]})


def test_wizard_submit_with_today_creates_alert(client, clock, captured, sales, monkeypatch):
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")
    _login(client, _make_user("msd_wizard", role="ADMIN", team="CS"))
    key = "new.msd-submit"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "마법사 고객",
            "phone": "010-9999-8888",
            "address": "경기도 성남시 분당구",
            "received_date": "2026-09-23",
            "items": [{"product_name": "주방장"}],
            "schedule": {"measurement_date": TODAY, "measurement_time": "16시"},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    resp = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    order_id = resp.get_json()["data"]["order_id"]
    _assert_single_alert(order_id, {sales["sales"], sales["measure"]})


def test_legacy_add_order_with_today_creates_alert(client, clock, captured, sales):
    _login(client, _make_user("msd_legacy", role="ADMIN", team="CS"))
    resp = client.post(
        "/add",
        data={
            "received_date": "2026-09-23",
            "received_time": "09:00",
            "customer_name": "레거시 고객",
            "phone": "010-2222-3333",
            "address": "인천 연수구 송도동",
            "product": "붙박이장",
            "status": "RECEIVED",
            "measurement_date": TODAY,
            "measurement_time": "11시",
            "sales_owner_id": str(sales["sales"]),
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]
    db_session.expire_all()
    order = db_session.query(Order).filter(Order.customer_name == "레거시 고객").one()
    notif = _assert_single_alert(order.id, {sales["sales"]})
    assert notif.title.startswith("[긴급 실측] 오늘 11시")


def test_orm_write_outside_request_creates_alert_without_actor(app, clock, captured, sales):
    """스크립트·워커 저장도 같은 훅을 지난다(actor 없음, 앱 컨텍스트 밖이면 emit 생략)."""
    order = _make_order(_erp_sd(TOMORROW))
    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TODAY
    order.structured_data = sd
    db_session.commit()

    notif = _assert_single_alert(order.id, {sales["sales"]})
    assert notif.created_by_user_id is None


# --------------------------------------------------------------------------- #
# 2. 허위 알림 0
# --------------------------------------------------------------------------- #
def test_tomorrow_creates_nothing(client, clock, captured, sales):
    _login(client, _make_user("msd_tmr", role="ADMIN", team="CS"))
    order_id = _make_order(_erp_sd(YESTERDAY)).id
    resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd(TOMORROW)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _outbox_rows() == [] and _notifications() == []
    assert captured["push"] == [] and captured["emit"] == []


def test_time_only_change_creates_nothing(client, clock, captured, sales):
    _login(client, _make_user("msd_time", role="ADMIN", team="CS"))
    clock.iso = YESTERDAY  # 어제 등록(오늘 실측) — 그때는 '당일'이 아니었다
    order_id = _make_order(_erp_sd(TODAY, time="10시")).id
    clock.iso = TODAY
    assert _outbox_rows() == []

    resp = client.put(
        f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd(TODAY, time="15시")}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _outbox_rows() == [] and _notifications() == []


def test_same_day_twice_and_remove_readd_creates_one(client, clock, captured, sales):
    _login(client, _make_user("msd_twice", role="ADMIN", team="CS"))
    order_id = _make_order(_erp_sd(TOMORROW)).id

    for target in (TODAY, TODAY, TOMORROW, TODAY):
        resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd(target)})
        assert resp.status_code == 200, resp.get_data(as_text=True)

    _assert_single_alert(order_id, {sales["sales"]})
    assert len(captured["push"]) == 1
    # 중복으로 막힌 예약은 기준 이벤트도 남기지 않는다(롤백).
    anchors = db_session.query(OrderEvent).filter(
        OrderEvent.order_id == order_id, OrderEvent.event_type == "MEASURE_SAME_DAY_ADDED"
    ).all()
    assert len(anchors) == 1


def test_remove_and_readd_within_one_transaction_is_not_new(app, clock, captured, sales):
    """한 트랜잭션 안에서 오늘을 지웠다 다시 넣으면 처음 값 기준으로 '변화 없음'."""
    clock.iso = YESTERDAY
    order = _make_order(_erp_sd(TODAY))
    clock.iso = TODAY

    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TOMORROW
    order.structured_data = sd
    db_session.flush()
    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TODAY
    order.structured_data = sd
    db_session.commit()
    assert _outbox_rows() == []


def test_flush_then_rollback_creates_nothing(app, clock, captured, sales):
    order = _make_order(_erp_sd(TOMORROW))
    order_id = order.id
    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TODAY
    order.structured_data = sd
    db_session.flush()
    db_session.rollback()

    # 다음 트랜잭션의 무관한 커밋으로 새어가지 않는다.
    _make_user("msd_after_rb", team="CS")
    assert _outbox_rows(order_id) == [] and _notifications(order_id) == []


def test_draft_order_save_creates_nothing(app, clock, captured, sales):
    order = _make_order(_erp_sd(TOMORROW, draft=True), status="DRAFT")
    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TODAY
    order.structured_data = sd
    db_session.commit()
    assert _outbox_rows() == [] and _notifications() == []


def test_draft_promotion_put_creates_alert(client, clock, captured, sales):
    """드래프트 → 승격은 날짜 차이가 없어도 '오늘 실측이 새로 생긴 것'이다."""
    _login(client, _make_user("msd_promote", role="ADMIN", team="CS"))
    order_id = _make_order(_erp_sd(TODAY, draft=True), status="DRAFT").id
    assert _outbox_rows() == []

    resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd(TODAY)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, order_id).status != "DRAFT"
    _assert_single_alert(order_id, {sales["sales"]})


def test_soft_deleted_order_creates_nothing(app, clock, captured, sales):
    order = _make_order(_erp_sd(TOMORROW))
    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = TODAY
    order.structured_data = sd
    order.status = "DELETED"
    order.deleted_at = "2026-09-23 10:00:00"
    db_session.commit()
    assert _outbox_rows() == []


# --------------------------------------------------------------------------- #
# 3. 커밋 뒤 실패는 요청을 깨지 않는다
# --------------------------------------------------------------------------- #
def test_after_commit_failure_keeps_request_200(client, clock, captured, sales, monkeypatch):
    def _boom(**_kwargs):
        raise RuntimeError("dispatch exploded")

    monkeypatch.setattr(msd, "dispatch_measure_same_day_alert", _boom)
    _login(client, _make_user("msd_boom", role="ADMIN", team="CS"))
    order_id = _make_order(_erp_sd(TOMORROW)).id

    resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd(TODAY)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True
    db_session.expire_all()
    saved = db_session.get(Order, order_id).structured_data
    assert saved["schedule"]["measurement"]["date"] == TODAY
    # 알림 행은 주문 저장과 같은 트랜잭션에 남는다 — 커밋 뒤 단계가 터져도 빠지지 않는다.
    _assert_single_alert(order_id, {sales["sales"]})


def test_push_and_emit_failures_do_not_undo_alert(client, clock, sales, monkeypatch):
    """푸시·emit 이 터져도 알림 행과 outbox 행은 이미 커밋돼 남는다."""
    from foms.services.notifications import push_sender, realtime_notifications

    def _raise(*_a, **_k):
        raise RuntimeError("down")

    monkeypatch.setattr(push_sender, "enqueue_push_for_notification", _raise)
    monkeypatch.setattr(realtime_notifications, "emit_erp_notification_to_users", _raise)
    _login(client, _make_user("msd_down", role="ADMIN", team="CS"))
    order_id = _make_order(_erp_sd(TOMORROW)).id

    resp = client.put(f"/api/orders/{order_id}/structured", json={"structured_data": _erp_sd(TODAY)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    _assert_single_alert(order_id, {sales["sales"]})
