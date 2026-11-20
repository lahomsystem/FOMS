"""AS 접수 취소 계약 (설계서 2026-11-20-multi-item-split-schedule §4.4, 결정 M9 ~ M12).

``POST /api/orders/<id>/as/cancel`` 이 잘못 접수한 현재 건(접수 상태)을 걷어 내고 주문을 접수 전 모습으로 되돌린다.
고정하는 것: 건은 ``cancelled_cycles[]`` 로 옮긴다(순번이 안 틀리게) · 상태 글과 평면 칸을 다시 맞춘다 · 접수 글과
방문일을 비운다 · 그 건 기록 줄은 가림 표시만 한다 · 시스템 줄 하나 + 이벤트 + 감사.
대조군: 처리 중 · 완료 · AS 없는 주문은 409, 권한 없는 사람은 403, 열린 AS 도면 요청이 걸리면 409.
이름 · 주소는 지어낸 것.
"""
from __future__ import annotations

import itertools

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.order_event_display import generate_change_description, translate_event_type_to_korean
from foms.services.orders.as_cancel_policy import as_cancel_allowed, user_may_cancel_as
from foms.services.orders.as_cycle_cancel import DRAWING_OPEN_MESSAGE, NOT_RECEIVED_MESSAGE
from foms.services.orders.as_cycle_view import as_cycle_detail_payload, current_cycle_ordinal
from foms.services.orders.state_axes import read_as_status
from models import Order, OrderEvent, OrderScheduleDate, SecurityLog, User

_seq = itertools.count(1)
REASON = "다른 고객 주문에 잘못 접수"


def _login(client, *, role: str = "ADMIN", team: str | None = "CS") -> User:
    n = next(_seq)
    user = User(username=f"as-cancel-{n}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"가짜사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


def _order(*, stage: str = "PRODUCTION", status: str | None = None, sd_extra: dict | None = None) -> int:
    sd = {"workflow": {"stage": stage}, "shipment": {"construction_workers": ["가짜기사"]},
          "parties": {"customer": {"name": "가짜고객"}}, **(sd_extra or {})}
    order = Order(received_date="2026-11-01", customer_name="가짜고객", phone="010-0000-0000", address="가짜시 가짜로 1",
                  product="가짜장", status=status or stage, manager_name="가짜영업", is_erp_order=True,
                  erp_stage_code=stage, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order.id


def _reload(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _register(client, order_id: int, content: str = "가짜 문짝 처짐", **extra) -> None:
    resp = client.post(f"/api/orders/{order_id}/as/register", json={"as_content": content, **extra})
    assert resp.status_code == 200, resp.get_data(as_text=True)


def _cancel(client, order_id: int, reason: str | None = REASON):
    return client.post(f"/api/orders/{order_id}/as/cancel", json={} if reason is None else {"reason": reason})


def _log(order: Order) -> list[dict]:
    return list(((order.structured_data or {}).get("shipment") or {}).get("as_log") or [])


# ── 성공 ────────────────────────────────────────────────────────────────────

def test_cancel_restores_the_order_to_before_the_reception(client) -> None:
    _login(client)
    oid = _order(stage="PRODUCTION")
    _register(client, oid)
    resp = client.post(f"/api/orders/{oid}/as/schedule", json={"visit_date": "2026-12-01", "visit_time": "14:30"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    before = _reload(oid)
    cycle_id = before.structured_data["as_lifecycle"]["current_cycle_id"]
    assert before.status == "AS_RECEIVED" and before.as_axis_status == "RECEIVED" and before.as_received_date
    assert db_session.query(OrderScheduleDate).filter_by(order_id=oid, kind="as_visit").count() == 1
    version = before.mutation_version

    resp = _cancel(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    assert body["data"]["new_status"] == "PRODUCTION" and body["data"]["cycle_no"] == 0

    saved = _reload(oid)
    sd = saved.structured_data
    # 상태 글 · 평면 칸 · 단계
    assert saved.status == "PRODUCTION" and sd["workflow"]["stage"] == "PRODUCTION"
    assert saved.as_axis_status is None and saved.as_received_date is None and saved.as_completed_date is None
    assert read_as_status(saved) == "NONE" and saved.mutation_version == version + 1
    # 건 장부 — 빼서 따로 보관
    lifecycle = sd["as_lifecycle"]
    assert lifecycle["cycles"] == [] and lifecycle["current_cycle_id"] is None
    (gone,) = lifecycle["cancelled_cycles"]
    assert gone["cycle_id"] == cycle_id and gone["cancel_reason"] == REASON and gone["cancelled_at"]
    assert gone["transitions"][-1]["command"] == "AS_CANCEL" and gone["transitions"][-1]["to"] == "NONE"
    # 접수 글 · 방문일 · 일정 줄
    assert sd["shipment"]["as_content"] == ""
    assert sd["schedule"]["as_visit"]["date"] is None and sd["schedule"]["as_visit"]["time"] is None
    assert "schedule_link" not in sd["schedule"]["as_visit"]
    assert db_session.query(OrderScheduleDate).filter_by(order_id=oid, kind="as_visit").count() == 0
    # 접수가 덮은 시공자 칸은 되돌리지 못한다(스냅샷 없음) — 건드리지 않는다
    assert sd["shipment"]["construction_workers"] == ["가짜기사"]
    # 기록 줄 — 그 건 줄은 가림 표시(원문은 남는다), 취소 사실 한 줄
    lines = _log(saved)
    stamped = [e for e in lines if e.get("cycle_id") == cycle_id]
    assert stamped and all(e["deleted"] is True and e["deleted_reason"] == "AS_CANCEL" for e in stamped)
    assert any(e["type"] == "reception" and "가짜 문짝 처짐" in e["text"] for e in stamped)  # 원문 보존
    visible = [e for e in lines if e.get("deleted") is not True]
    assert [e["text"] for e in visible] == [f"AS 접수 취소됨 · {REASON}"]
    assert visible[0]["type"] == "system" and "cycle_id" not in visible[0]
    # 이벤트 · 감사 · 글
    event = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="AS_CANCELLED").one()
    assert event.payload["reason"] == REASON and event.payload["cycle_id"] == cycle_id
    assert event.payload["remaining_cycles"] == 0
    assert translate_event_type_to_korean("AS_CANCELLED") == "AS 접수 취소"
    assert generate_change_description("AS_CANCELLED", "", "", "", event.payload) == f"AS 접수를 취소했습니다 ({REASON})"
    audit = db_session.query(SecurityLog).filter_by(action="AS_CANCELLED", target_id=oid).one()
    assert audit.detail["reason"] == REASON and "AS 접수 취소" in audit.message


def test_next_reception_after_cancel_is_not_counted_as_second(client) -> None:
    _login(client)
    oid = _order(stage="CS")
    _register(client, oid, "잘못 접수한 글")
    assert _cancel(client, oid).status_code == 200
    resp = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "진짜 접수", "billing_type": "paid",
                                                               "amount": 30000})
    assert resp.status_code == 200 and resp.get_json()["cycle_no"] == 1 and resp.get_json()["is_new_cycle"] is True
    saved = _reload(oid)
    assert current_cycle_ordinal(saved.structured_data) == 1
    detail = as_cycle_detail_payload(saved.structured_data)
    assert detail["cycle_no"] == 1 and detail["prev_cycle"] is None and detail["last_closed_cycle"] is None
    assert saved.status == "AS_RECEIVED" and saved.as_axis_status == "RECEIVED"
    # 취소가 미확정 추정 비용을 걷어 냈으므로 새 접수가 고른 유상이 심긴다
    assert saved.structured_data["shipment"]["as_billing"]["type"] == "paid"
    assert saved.structured_data["shipment"]["as_content"] == "진짜 접수"


def test_cancel_with_an_earlier_completed_cycle_goes_back_to_as_completed(client) -> None:
    _login(client)
    oid = _order(stage="COMPLETED")
    _register(client, oid, "첫 AS 글", billing_type="paid", amount=50000)
    resp = client.post("/api/update_order_field",
                       json={"order_id": oid, "field": "as_completed_date", "value": "2026-11-05"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    first = _reload(oid)
    first_id = first.structured_data["as_lifecycle"]["current_cycle_id"]
    assert first.status == "AS_COMPLETED" and first.as_completed_date == "2026-11-05"
    first_received = first.as_received_date

    _register(client, oid, "잘못 접수한 둘째 글")
    second = _reload(oid)
    assert second.status == "AS_RECEIVED" and current_cycle_ordinal(second.structured_data) == 2
    assert second.structured_data["shipment"]["as_billing"]["type"] == "free"  # 둘째 접수가 다시 심은 값

    resp = _cancel(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"] == {**resp.get_json()["data"], "new_status": "AS_COMPLETED", "cycle_no": 1}
    saved = _reload(oid)
    sd = saved.structured_data
    assert saved.status == "AS_COMPLETED" and saved.as_axis_status == "COMPLETED"
    assert saved.as_completed_date == "2026-11-05" and saved.as_received_date == first_received
    assert sd["as_lifecycle"]["current_cycle_id"] == first_id and len(sd["as_lifecycle"]["cycles"]) == 1
    assert len(sd["as_lifecycle"]["cancelled_cycles"]) == 1
    assert sd["shipment"]["as_content"] == "첫 AS 글"
    assert sd["shipment"]["as_billing"]["type"] == "paid" and sd["shipment"]["as_billing"]["amount"] == 50000
    kept = [e for e in _log(saved) if e.get("cycle_id") == first_id]
    assert kept and all(e.get("deleted") is not True for e in kept)  # 남은 건 기록은 그대로
    # 그다음 접수는 2번째다(취소한 건은 세지 않는다)
    resp = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "진짜 둘째"})
    assert resp.get_json()["cycle_no"] == 2


def test_legacy_as_order_without_cycle_record_is_bridged_then_cancelled(client) -> None:
    _login(client)
    oid = _order(stage="CS", status="AS_RECEIVED", sd_extra={"shipment": {"as_content": "<p>옛 접수 글</p>"}})
    legacy = _reload(oid)
    legacy.as_received_date = "2026-10-01"
    legacy.as_axis_status = "RECEIVED"
    db_session.commit()

    resp = _cancel(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    saved = _reload(oid)
    lifecycle = saved.structured_data["as_lifecycle"]
    assert saved.status == "CS" and saved.as_axis_status is None and saved.as_received_date is None
    assert lifecycle["cycles"] == [] and lifecycle["current_cycle_id"] is None
    assert lifecycle["cancelled_cycles"][0]["origin"] == "LEGACY_BRIDGE"
    assert saved.structured_data["shipment"]["as_content"] == ""


def test_legacy_order_whose_stage_is_stuck_on_as_is_refused(client) -> None:
    """단계 글이 AS 로 굳은 옛 주문은 돌아갈 본공정 단계를 모른다 — 지어내지 않고 막는다."""
    _login(client)
    oid = _order(stage="AS_RECEIVED", status="AS_RECEIVED")
    resp = _cancel(client, oid)
    assert resp.status_code == 409 and "본공정 단계" in resp.get_json()["error"]
    saved = _reload(oid)
    assert saved.status == "AS_RECEIVED" and "as_lifecycle" not in (saved.structured_data or {})


# ── 막는 경우 ────────────────────────────────────────────────────────────────

def test_cancel_is_refused_when_in_progress_completed_or_absent(client) -> None:
    _login(client)
    started = _order(stage="CS")
    _register(client, started)
    assert client.post(f"/api/orders/{started}/as/start",
                       json={"reason": "방문", "description": "점검"}).status_code == 200
    resp = _cancel(client, started)
    assert resp.status_code == 409 and resp.get_json() == {"success": False, "data": None, "error": NOT_RECEIVED_MESSAGE}
    assert _reload(started).status == "AS"

    done = _order(stage="CS")
    _register(client, done)
    assert client.post("/api/update_order_field",
                       json={"order_id": done, "field": "as_completed_date", "value": "2026-11-05"}).status_code == 200
    assert _cancel(client, done).status_code == 409 and _reload(done).status == "AS_COMPLETED"

    plain = _order(stage="CS")
    resp = _cancel(client, plain)
    assert resp.status_code == 409 and "취소할 AS 접수가 없습니다" in resp.get_json()["error"]
    assert _reload(plain).status == "CS"


def test_cancel_needs_reason_and_admin_or_cs_capability(client) -> None:
    _login(client)
    oid = _order(stage="CS")
    _register(client, oid)
    for blank in (None, "", "   "):
        resp = _cancel(client, oid, blank)
        assert resp.status_code == 400 and resp.get_json()["success"] is False

    _login(client, role="STAFF", team="SALES")
    resp = _cancel(client, oid)
    assert resp.status_code == 403 and "관리자" in resp.get_json()["error"]
    assert _reload(oid).status == "AS_RECEIVED"

    _login(client, role="STAFF", team="ACCOUNTING")  # 회계팀은 CS 능력을 같이 갖는다
    assert _cancel(client, oid).status_code == 200
    assert _reload(oid).status == "CS"


def test_cancel_is_blocked_while_an_as_drawing_request_is_open(client) -> None:
    _login(client)
    oid = _order(stage="CS")
    resp = client.post(f"/api/orders/{oid}/as/register",
                       json={"as_content": "가짜 도면 필요", "drawing_request": {"memo": "문짝 치수 다시"}})
    assert resp.status_code == 200 and resp.get_json()["as_drawing"] == "opened"
    resp = _cancel(client, oid)
    assert resp.status_code == 409 and resp.get_json()["error"] == DRAWING_OPEN_MESSAGE
    assert _reload(oid).status == "AS_RECEIVED"

    resp = client.post(f"/api/orders/{oid}/drawing/as/cancel", json={"reason": "잘못 부탁"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _cancel(client, oid).status_code == 200  # 요청을 닫으면 취소된다
    assert _reload(oid).status == "CS"


# ── 단추 ────────────────────────────────────────────────────────────────────

def test_cancel_predicate_matches_state_and_permission(client) -> None:
    admin = User(role="ADMIN", team=None)
    cs = User(role="STAFF", team="CS")
    sales = User(role="STAFF", team="SALES")
    assert user_may_cancel_as(admin) and user_may_cancel_as(cs) and not user_may_cancel_as(sales)
    assert not user_may_cancel_as(None)
    received = db_session.get(Order, _order(stage="CS", status="AS_RECEIVED"))
    in_progress = db_session.get(Order, _order(stage="CS", status="AS"))
    completed = db_session.get(Order, _order(stage="CS", status="AS_COMPLETED"))
    plain = db_session.get(Order, _order(stage="CS"))
    assert as_cancel_allowed(received, admin) and as_cancel_allowed(received, cs)
    assert not as_cancel_allowed(received, sales) and not as_cancel_allowed(received, None)
    assert not any(as_cancel_allowed(o, admin) for o in (in_progress, completed, plain, None))


@pytest.mark.parametrize("mobile", [False, True])
def test_order_screen_draws_cancel_button_only_when_allowed(client, monkeypatch, mobile) -> None:
    admin = _login(client)
    if mobile:
        monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
        monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(admin.id))
    received = _order(stage="CS")
    _register(client, received)
    plain = _order(stage="CS")
    marker = f'data-erp-as-cancel data-order-id="{received}"'
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"} if mobile else {}

    html = client.get(f"/edit/{received}", headers=headers).get_data(as_text=True)
    assert marker in html and "erp-as-cancel.js" in html
    assert ("erp-mobile-stage-row__controls" in html) is mobile  # 휴대폰 화면 틀 · PC 틀이 각각 실제로 그려졌다
    assert "data-erp-as-cancel" not in client.get(f"/edit/{plain}", headers=headers).get_data(as_text=True)

    client.post(f"/api/orders/{received}/as/start", json={"reason": "방문", "description": "점검"})
    assert "data-erp-as-cancel" not in client.get(f"/edit/{received}", headers=headers).get_data(as_text=True)

    other = _order(stage="CS")
    _register(client, other)
    _login(client, role="STAFF", team="SALES")
    assert "data-erp-as-cancel" not in client.get(f"/edit/{other}", headers=headers).get_data(as_text=True)


def test_as_round_chart_draws_cancel_button_only_when_allowed(client) -> None:
    _login(client)
    oid = _order(stage="CS")
    _register(client, oid)
    marker = f'data-erp-as-cancel data-order-id="{oid}"'
    assert marker in client.get(f"/erp/as/timeline/{oid}").get_data(as_text=True)
    assert marker in client.get(f"/erp/as/card-detail/{oid}").get_data(as_text=True)
    assert "data-erp-as-cancel" not in client.get(f"/erp/as/timeline/{oid}?readonly=1").get_data(as_text=True)
    assert "erp-as-cancel.js') }}?v=20261121a" in open(
        "templates/cs/partials/as_dashboard_body.html", encoding="utf-8").read()

    client.post(f"/api/orders/{oid}/as/start", json={"reason": "방문", "description": "점검"})
    assert "data-erp-as-cancel" not in client.get(f"/erp/as/timeline/{oid}").get_data(as_text=True)

    other = _order(stage="CS")
    _register(client, other)
    _login(client, role="STAFF", team="SALES")
    assert "data-erp-as-cancel" not in client.get(f"/erp/as/timeline/{other}").get_data(as_text=True)
