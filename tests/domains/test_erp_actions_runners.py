"""ERP 할 일 실행기(설계서 2026-11-14-foms-graft 3.3 · 3.4 · 3.11) — 실행기마다 감싼 함수가 그 값으로 불렸나 · 남는 기록.

- 시공 잡기: 시공일 쓰기(협력사 주문은 희망 확정 길) · 감사 ``ORDER_FIELD_UPDATED``(+ ``source``) · 커밋 뒤 알림 마무리.
- 방문 옮기기(시공): 사유를 물을 변경이면 승인 창 사유가 지금 사유 원장(같은 변경 묶음)에.
- 방문 옮기기(AS): ``schedule_as_cycle``(옛 AS 끌어올림 · 영수증 열쇠) · AS 기록 한 줄 · 감사 ``AS_SCHEDULED`` · 캐시 비우기.
- 알림톡(실측 예약): 중복 막기 열쇠 ``alimtalk:measure:<주문>:action:<제안>`` · 감사 ``ALIMTALK_MANUAL_SENT`` · 못 보내면 실패.
- 시공 메모: 한 줄 · 판 번호 올림 · 감사에 메모 글 없음. AS 접수(api 층): 접수 본체 · 출처 ``source_screen``.
- 감싼 기능이 거절하면 막힘(주문 안 바뀜). **바깥 보내기는 모두 가짜**(Solapi · 푸시 · 실시간) — 부르면 시험이 깨진다.
합성 주문 · 합성 글만.
"""

from __future__ import annotations

import datetime

import pytest
from flask import jsonify
from werkzeug.security import generate_password_hash

import foms.api.erp_action_runners as api_runners
import foms.services.kakao_alimtalk as kakao
import foms.services.orders.construction_schedule as schedule_mod
from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import preview, runners
from foms.services.erp_actions.runners import SERVICE_RUNNERS, RunRequest
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.construction_schedule import ScheduleConflict
from models import Order, OrderChangeReason, OrderEvent, PartnerOrg, SecurityLog, User

CUSTOMER = "합성손님"


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture(autouse=True)
def no_outbound(monkeypatch):
    """바깥 보내기 · 알림 마무리를 모두 가짜로 — 진짜 Solapi 를 부르면 시험이 깨진다."""
    def _never(*args, **kwargs):
        raise AssertionError("시험에서 바깥으로 보내면 안 된다")

    monkeypatch.setattr(kakao, "_solapi_send", _never)
    monkeypatch.setattr(kakao, "_solapi_send_text", _never)
    calls: dict[str, list] = {"finalize": [], "alerts": [], "caches": []}
    monkeypatch.setattr(runners, "finalize_schedule_notifications", lambda db, result: calls["finalize"].append(result))
    monkeypatch.setattr(runners, "finalize_note_notifications", lambda db, result: calls["finalize"].append(result))
    monkeypatch.setattr(schedule_mod, "apply_drawing_order_change_alert",
                        lambda *a, **k: (calls["alerts"].append("drawing"), (None, False))[1])
    monkeypatch.setattr(schedule_mod, "apply_production_change_alert",
                        lambda *a, **k: (calls["alerts"].append("production"), ([], False))[1])
    monkeypatch.setattr(runners, "invalidate_all_dashboard_slice_caches", lambda: calls["caches"].append("dashboard"))
    monkeypatch.setattr(runners, "invalidate_shipment_as_recommendation_cache",
                        lambda reason: calls["caches"].append(reason))
    return calls


def _admin() -> User:
    user = User(username="rn_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order(stage: str, *, construction=None, partner: bool = False, **sd_extra) -> Order:
    sd = {"workflow": {"stage": stage}, **sd_extra}
    if construction:
        sd["schedule"] = {"construction": {"date": construction[0], "time": construction[1]}}
    order = Order(received_date="2030-01-01", customer_name=CUSTOMER, phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd)
    if partner:
        org = PartnerOrg(name="합성 협력사")
        db_session.add(org)
        db_session.flush()
        order.partner_org_id = org.id
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _req(order: Order, action: str, params: dict, actor: User, **extra) -> RunRequest:
    return RunRequest(proposal_id=41, action=action, order_id=order.id, params=params, actor=actor,
                      now=now_utc_naive(), **extra)


def _audit(action: str) -> SecurityLog:
    rows = db_session.query(SecurityLog).filter(SecurityLog.action == action).all()
    assert len(rows) == 1, (action, len(rows))
    return rows[0]


def _spy(monkeypatch, module, name):
    seen: list = []
    real = getattr(module, name)

    def wrapper(*args, **kwargs):
        seen.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return seen


def test_schedule_construction_writes_audits_then_finalizes(app, monkeypatch, no_outbound):
    admin, order = _admin(), _order("MEASURE")
    seen = _spy(monkeypatch, runners, "write_construction_schedule")
    out = SERVICE_RUNNERS["schedule_construction"](db_session, _req(order, "schedule_construction",
                                                                   {"date": _day(9), "time": "오후"}, admin))
    assert out.status == "executed" and out.result["date"] == _day(9) and out.result["time"] == "오후"
    assert seen[0][1] == {"date": _day(9), "time": "오후"} and seen[0][0][2] is admin
    db_session.expire_all()
    construction = db_session.get(Order, order.id).structured_data["schedule"]["construction"]
    assert construction == {"date": _day(9), "time": "오후"}
    log = _audit("ORDER_FIELD_UPDATED")
    assert log.detail["source"] == "erp_action:41" and log.detail["field"] == "scheduled_date"
    assert log.detail["change_set"] == out.result["change_set"] and log.user_id == admin.id
    assert len(no_outbound["finalize"]) == 1


def test_partner_first_date_uses_the_hope_confirm_path(app, monkeypatch):
    admin = _admin()
    order = _order("CONFIRM", partner=True, partner_intake={"requested_construction": {"date": _day(8)}})
    order.structured_data = {**order.structured_data, "schedule": {"construction": {"date": "", "time": "종일"}}}
    db_session.commit()
    seen = _spy(monkeypatch, runners, "confirm_partner_request")
    out = SERVICE_RUNNERS["schedule_construction"](db_session, _req(order, "schedule_construction",
                                                                   {"date": _day(8), "time": "오전"}, admin))
    assert out.status == "executed" and len(seen) == 1 and out.result["time"] == "종일"  # 있던 시간대는 그대로


def test_wrapped_conflict_is_blocked_without_writing(app, monkeypatch):
    admin = _admin()
    order = _order("CONFIRM", partner=True)

    def _conflict(*args, **kwargs):
        raise ScheduleConflict("다른 사람이 먼저 시공일을 정했어요.")

    monkeypatch.setattr(runners, "confirm_partner_request", _conflict)
    out = SERVICE_RUNNERS["schedule_construction"](db_session, _req(order, "schedule_construction",
                                                                   {"date": _day(8), "time": ""}, admin))
    assert (out.status, out.message) == ("blocked", "다른 사람이 먼저 시공일을 정했어요.")
    assert db_session.query(SecurityLog).count() == 0


def test_blocked_under_lock_when_the_order_moved(app):
    admin, order = _admin(), _order("MEASURE", construction=(_day(3), "오전"))
    out = SERVICE_RUNNERS["schedule_construction"](db_session, _req(order, "schedule_construction",
                                                                   {"date": _day(9), "time": ""}, admin))
    assert out.status == "blocked" and "이미 시공일이 있어요" in out.message


def test_move_with_reason_goes_to_the_reason_ledger(app):
    admin, order = _admin(), _order("CONFIRM", construction=(_day(3), "오전"))
    req = _req(order, "move_construction", {"date": _day(5), "time": "오전"}, admin,
               reason_code="customer_request", reason_note=None)
    out = SERVICE_RUNNERS["move_construction"](db_session, req)
    assert out.status == "executed" and out.result["reason_required"] and out.result["reason_attached"]
    reason = db_session.query(OrderChangeReason).one()
    assert (reason.change_set_id, reason.reason_code, reason.actor_user_id) == (
        out.result["change_set"], "customer_request", admin.id)


def _as_order(admin: User) -> Order:
    cycle = {"cycle_id": "c1", "opened_at": "2030-01-01T00:00:00", "opened_by": admin.id, "initial_content": "합성 증상",
             "classification": {}, "transitions": [{"seq": 1, "command": "AS_REGISTER", "from": "NONE",
                                                    "to": "RECEIVED", "payload": {}, "actor_id": admin.id,
                                                    "at": "2030-01-01T00:00:00"}]}
    return _order("COMPLETED", as_lifecycle={"current_cycle_id": "c1", "cycles": [cycle]})


def test_as_visit_runs_the_as_schedule_path(app, monkeypatch, no_outbound):
    admin = _admin()
    order = _as_order(admin)
    version = order.mutation_version
    seen = _spy(monkeypatch, runners, "schedule_as_cycle")
    out = SERVICE_RUNNERS["schedule_as_visit"](db_session, _req(order, "schedule_as_visit", {"date": _day(4)}, admin))
    assert out.status == "executed" and out.result == {"visit_date": _day(4)}
    kwargs = seen[0][1]
    assert kwargs["legacy_bridge"] is True and kwargs["visit_time"] is None
    assert kwargs["idempotency_key"].startswith("erp-action-41-") and kwargs["actor_user_id"] == admin.id
    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved.structured_data["schedule"]["as_visit"]["date"] == _day(4) and saved.mutation_version == version + 1
    assert any("방문일 확정" in str(e.get("text")) for e in saved.structured_data["shipment"]["as_log"])
    assert _audit("AS_SCHEDULED").detail["source"] == "erp_action:41"
    assert no_outbound["caches"] == ["dashboard", "erp_action_as_schedule"]


def test_as_visit_without_open_as_is_blocked(app):
    admin, order = _admin(), _order("COMPLETED")
    out = SERVICE_RUNNERS["schedule_as_visit"](db_session, _req(order, "schedule_as_visit", {"date": _day(4)}, admin))
    assert out.status == "blocked" and "열린 AS 가 없어요" in out.message


@pytest.mark.parametrize("sent", [True, False])
def test_measure_alimtalk_uses_the_action_key(app, monkeypatch, sent):
    admin, order = _admin(), _order("MEASURE")
    calls: list = []
    monkeypatch.setattr(kakao, "is_configured", lambda brand=None: True)
    monkeypatch.setattr(preview, "_ineligible_reason", lambda o, sd: None)
    monkeypatch.setattr(kakao, "send_alimtalk", lambda order_id, **kw: (
        calls.append((order_id, kw)), {"sent": sent, "error": None if sent else "network"})[1])
    out = SERVICE_RUNNERS["send_measure_alimtalk"](db_session, _req(order, "send_measure_alimtalk", {}, admin))
    assert calls == [(order.id, {"manual_by": admin.id, "dedupe_key": f"alimtalk:measure:{order.id}:action:41"})]
    assert out.status == ("executed" if sent else "failed")
    log = _audit("ALIMTALK_MANUAL_SENT")
    assert (log.detail["sent"], log.detail["template"], log.detail["source"]) == (sent, "measure", "erp_action:41")


def test_measure_alimtalk_not_configured_never_sends(app, monkeypatch):
    admin, order = _admin(), _order("MEASURE")
    monkeypatch.setattr(kakao, "is_configured", lambda brand=None: False)
    monkeypatch.setattr(kakao, "send_alimtalk", lambda *a, **k: pytest.fail("보내면 안 된다"))
    out = SERVICE_RUNNERS["send_measure_alimtalk"](db_session, _req(order, "send_measure_alimtalk", {}, admin))
    assert out.status == "blocked" and db_session.query(SecurityLog).count() == 0


def test_construction_note_runner(app, no_outbound):
    admin = _admin()
    order = _order("CONFIRM", notes={"construction_note": "현관 좁음"})
    version = order.mutation_version
    out = SERVICE_RUNNERS["add_construction_note"](db_session, _req(order, "add_construction_note",
                                                                   {"note": "자재 먼저 내림"}, admin))
    assert out.status == "executed"
    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved.structured_data["notes"]["construction_note"] == "현관 좁음\n자재 먼저 내림"
    assert saved.mutation_version == version + 1
    log = _audit("ORDER_FIELD_UPDATED")
    assert log.detail["field"] == "construction_note" and log.detail["source"] == "erp_action:41"
    assert "자재" not in log.message and "자재" not in str(log.detail) and len(no_outbound["finalize"]) == 1


def test_register_as_runner_calls_the_intake_body(app):
    admin, order = _admin(), _order("COMPLETED")
    with app.test_request_context("/api/erp-actions/proposals/41/approve", method="POST"):
        out = api_runners.RUNNERS["register_as"](db_session, _req(order, "register_as",
                                                                {"as_content": "문 경첩 소리 남"}, admin))
    assert out.status == "executed"
    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved.as_axis_status == "RECEIVED"
    event = db_session.query(OrderEvent).filter_by(order_id=order.id, event_type="AS_REGISTERED").one()
    assert event.payload["source_screen"] == "erp_action:41"


def test_register_as_blocked_when_as_is_open(app, monkeypatch):
    admin = _admin()
    order = _as_order(admin)
    monkeypatch.setattr(api_runners, "register_as_from_payload", lambda *a, **k: pytest.fail("부르면 안 된다"))
    out = api_runners.run_register_as(db_session, _req(order, "register_as", {"as_content": "합성"}, admin))
    assert out.status == "blocked" and "이미 열린 AS" in out.message


@pytest.mark.parametrize("payload, status, want", [
    ({"success": True, "message": "AS 접수가 등록되었습니다."}, 200, "executed"),
    ({"success": False, "message": "현재 AS 상태에서 수행할 수 없는 작업입니다."}, 409, "blocked"),
    ({"success": False, "message": "boom"}, 500, "failed"),
    ({"success": False}, 200, "blocked"),
])
def test_outcome_from_response(app, payload, status, want):
    with app.test_request_context():
        out = api_runners.outcome_from_response((jsonify(payload), status), done_message="합성")
    assert out.status == want and out.result["http_status"] == status
    if want == "failed":
        assert "boom" not in out.message


def test_runner_tables():
    assert set(SERVICE_RUNNERS) == {"schedule_construction", "move_construction", "schedule_as_visit",
                                    "send_measure_alimtalk", "add_construction_note"}
    assert set(api_runners.RUNNERS) == set(SERVICE_RUNNERS) | {"register_as", "advance_stage", "assign_draftsman",
                                                               "move_measurement"}  # D206 · T14
