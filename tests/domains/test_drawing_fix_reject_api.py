"""생산 넘어간 주문의 도면 수정 D4 — 공장 요청 [요청 반려] · [반영 완료] API · 단계 나감 · 작업실 요청사항 칸(설계서 2026-11-25 §2-2 · §3-2 ·
§4-1 · §4-2 · N4 · N5 · §6 · §10).

* 누가: 도면팀 누구나 + 관리자(``can_fix_production_drawing``) — 영업 · 반장 · 파트 계정 · 생산팀 MANAGER = 403 ``FIX_FORBIDDEN``.
* [요청 반려]: 사유 빈 글 400 ``REJECT_NOTE_REQUIRED`` → ``rejected``(막힘 풀림) · 이벤트 · 감사 · 공장 '바뀐 것' "도면 수정 요청 반려"
  "도면 2 · 사유: …" · 요청한 사람 한 명에게 종 + 폰(확인 창 없음). 이미 반려 = 200 ``changed:false``, 수정본으로 닫힌 요청 = 409
  ``REQUEST_CLOSED``, 없는 요청 = 404.
* [반영 완료] · [완료 해제]: ``checked`` 만 — 막힘 그대로(사장님 "[반영 완료]를 먼저 누르기" · 수정본이 갈 때까지 막힌 채). 그 뒤 수정본
  전달이 지나가고 요청이 ``done``. 같은 값 = 200 ``changed:false``.
* 단계가 생산 밖으로 나가면(제작 완료 · 되돌림) 열린 요청을 같은 쓰기에서 닫는다(``done`` + ``via: stage_exit`` · ``log`` 줄 — 반려가
  아니라 알림 · '바뀐 것' 줄 없음). 시공 대기 상세에서도 [반영 완료] · [요청 반려]가 된다.
* 작업실 상세 요청사항 칸: 공장 요청 줄이 영업 요청과 같은 목록 맨 위에 — "수정 요청 · 공장" · 시각 · 요청한 사람 · 대상 칩 · "사유: …" ·
  사진 · 단추 · 반려 기록 줄. 영업 요청 줄 · 글은 그대로(대조군).

되돌리면 실패: 사유 없는 반려 200 · 반려 뒤 막힘이 남음 · 반영 완료가 막힘을 풂 · 수정본으로 닫힌 요청을 반려 · 단계를 나가도 요청이 열린
채 시공 대기를 막음 · 요청한 사람에게 알림이 안 감. 이름은 모두 지어낸 값이다(실제 알림 · 폰 발송 없음 — 가짜로 받는다).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

import foms.api.drawing.erp_orders_drawing_fix as fix_api
from db import db_session
from foms.services.orders import drawing_fix as fx
from foms.services.orders.order_mutation_policy import load_policy_manifest
from foms.services.production_change_alerts import collect_production_change_alerts
from foms.services.request_write_guard import load_write_guard_manifest
from models import Notification, NotificationUserState, Order, OrderEvent, SecurityLog, User
from tests.support.drawing_fix_transfer_seed import send
from tests.support.drawing_fix_workbench_seed import day, login, make_order, make_user, people, sales_request, sd_of
from tests.support.production_steps_seed import mark_order_inspected

FORBIDDEN = "도면 수정은 도면팀이나 관리자만 표시할 수 있어요."
CLOSED = "이미 처리된 요청이에요. 화면을 다시 열어 주세요."


@pytest.fixture
def who():
    return people()


@pytest.fixture
def sent(monkeypatch):
    """폰 · 실시간 알림을 가짜로 받는다(수정본 전달 길의 알림도 끈다 — D2 시험과 같은 꼴)."""
    box = SimpleNamespace(push=[], emits=[])
    monkeypatch.setattr(fix_api, "enqueue_push_for_notification", lambda nid, **k: box.push.append(nid))
    monkeypatch.setattr(fix_api, "emit_erp_notification_to_users", lambda ids, data: box.emits.append((set(ids), data)))
    monkeypatch.setattr("foms.api.drawing.erp_orders_drawing.emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.realtime_notifications.emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.push_sender.enqueue_push_for_notification", lambda *a, **k: None)
    return box


def _request(by_user_id=None, *, rid: str = "fr_a1", targets=("sheet:s1",), numbers=(2,), state: str = "open",
             checked: bool = False, photos=()) -> dict:
    """D4 N3 가 적는 모양 그대로(요청한 사람 · 사유 · 사진)."""
    return {"id": rid, "from": "factory", "targets": list(targets), "numbers": list(numbers), "note": "측판 길이가 실측과 달라요",
            "photos": list(photos), "factory": 1, "by_user_id": by_user_id, "by_name": "박반장", "at": "2026-11-25T04:40:00Z",
            "state": state, "checked": checked, "checked_by_name": "김도면" if checked else None,
            "checked_at": "2026-11-25T05:00:00Z" if checked else None, "resolved": [], "done_at": None,
            "rejected_by_user_id": None, "rejected_by_name": None, "rejected_at": None, "reject_note": None}


def _order(who, *, stage: str = "PRODUCTION", **kw) -> int:
    return make_order(3, stage=stage, cdate=day(3), extra={"drawing_fix": {"requests": [_request(who.lead.id, **kw)], "log": []}})


def _reject(client, oid: int, note: str = "실측과 같아요. 측판은 그대로예요", rid: str = "fr_a1"):
    return client.post(f"/api/orders/{oid}/drawing/fix/requests/{rid}/reject", json={"note": note})


def _check(client, oid: int, checked: bool, rid: str = "fr_a1"):
    return client.post(f"/api/orders/{oid}/drawing/fix/requests/{rid}/check", json={"checked": checked})


def _code(res) -> str | None:
    return ((res.get_json() or {}).get("data") or {}).get("code")


def _req(oid: int) -> dict:
    return sd_of(oid)["drawing_fix"]["requests"][0]


def _events(oid: int, event_type: str) -> list[OrderEvent]:
    db_session.expire_all()
    return db_session.query(OrderEvent).filter_by(order_id=oid, event_type=event_type).all()


# --- 누가 -------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["sales", "lead", "part", "viewer", "prod_manager"])
def test_only_drawing_team_and_admin_handle_factory_requests(client, sent, who, name):
    oid = _order(who)
    login(client, getattr(who, name))
    for res in (_reject(client, oid), _check(client, oid, True)):
        assert res.status_code == 403 and _code(res) == "FIX_FORBIDDEN" and res.get_json()["error"] == FORBIDDEN
    assert _req(oid)["state"] == "open" and _req(oid)["checked"] is False


# --- [요청 반려] -------------------------------------------------------------------


def test_reject_needs_a_reason(client, sent, who):
    oid = _order(who)
    login(client, who.staff)
    res = _reject(client, oid, note="   ")
    assert res.status_code == 400 and _code(res) == "REJECT_NOTE_REQUIRED" and res.get_json()["error"] == "반려 사유를 적어 주세요."
    assert _req(oid)["state"] == "open" and not sent.push


def test_reject_closes_unblocks_notifies_requester_and_adds_a_changes_line(client, sent, who):
    oid = _order(who)
    assert fx.blocked(sd_of(oid)).idents == frozenset({"sheet:s1"})
    before = db_session.get(Order, oid).mutation_version
    login(client, who.manager)
    res = _reject(client, oid)
    assert res.status_code == 200 and res.get_json()["data"]["changed"] is True, res.get_json()
    req = _req(oid)
    assert (req["state"], req["rejected_by_name"], req["rejected_by_user_id"], req["reject_note"]) == (
        "rejected", "오도면", who.manager.id, "실측과 같아요. 측판은 그대로예요")
    assert req["rejected_at"].endswith("Z") and fx.blocked(sd_of(oid)).idents == frozenset()        # 막힘 풀림
    assert sd_of(oid)["drawing_fix"]["log"][-1] | {"at": None} == {"act": "reject", "idents": ["sheet:s1"], "numbers": [2],
                                                                     "requests": ["fr_a1"], "by_name": "오도면", "at": None}
    db_session.expire_all()
    assert db_session.get(Order, oid).mutation_version == before + 1
    [event] = _events(oid, "DRAWING_FIX_REQUEST_REJECTED")
    assert event.payload["numbers"] == [2] and event.payload["note"] == "실측과 같아요. 측판은 그대로예요"
    assert db_session.query(SecurityLog).filter_by(action="DRAWING_FIX_REQUEST_REJECTED", target_id=oid).count() == 1
    note = db_session.query(Notification).filter_by(order_id=oid, notification_type="DRAWING_FACTORY_REQUEST_REJECTED").one()
    assert (note.target_type, note.target_user_id, note.title) == ("USER", who.lead.id, "도면 수정 요청 반려")
    assert note.message == f"주문 #{oid} (정하늘) 도면 2 수정 요청이 반려됐어요. 사유: 실측과 같아요. 측판은 그대로예요"
    assert {s.user_id for s in db_session.query(NotificationUserState).filter_by(notification_id=note.id)} == {who.lead.id}
    assert sent.push == [note.id] and [ids for ids, _d in sent.emits] == [{who.lead.id}]
    assert "interrupt" not in sent.emits[0][1]                                       # 요청한 사람은 종 + 폰(확인 창 아님)
    alerts = collect_production_change_alerts(db_session, [db_session.get(Order, oid)], None)[oid]["alerts"]
    assert [(a["label"], a["detail"], a["by_name"], a["by_id"]) for a in alerts if a["label"] == "도면 수정 요청 반려"] == [
        ("도면 수정 요청 반려", "도면 2 · 사유: 실측과 같아요. 측판은 그대로예요", "오도면", who.manager.id)]


def _notes(oid: int) -> list[Notification]:
    db_session.expire_all()
    return db_session.query(Notification).filter_by(order_id=oid, notification_type="DRAWING_FACTORY_REQUEST_REJECTED").all()


def test_rejecting_your_own_request_makes_no_notification_but_keeps_the_changes_line(client, sent, who):
    """반려한 사람이 요청한 사람 본인(관리자가 공장에서 요청하고 작업실에서 반려 등)이면 알림 줄 · state · 폰 0."""
    oid = make_order(3, cdate=day(3), extra={"drawing_fix": {"requests": [_request(who.admin.id)], "log": []}})
    login(client, who.admin)
    assert _reject(client, oid).status_code == 200 and _req(oid)["state"] == "rejected"
    assert _notes(oid) == [] and sent.push == [] and sent.emits == []
    assert len(_events(oid, "DRAWING_FIX_REQUEST_REJECTED")) == 1


def test_inactive_requester_gets_no_notification_line(client, sent, who):
    oid = _order(who)
    user = db_session.get(User, who.lead.id)
    user.is_active = False
    db_session.commit()
    login(client, who.staff)
    assert _reject(client, oid).status_code == 200
    assert _notes(oid) == [] and sent.push == [] and len(_events(oid, "DRAWING_FIX_REQUEST_REJECTED")) == 1
    active = _order(who)                                                     # 대조군: 켜진 요청자는 알림 한 줄
    db_session.get(User, who.lead.id).is_active = True
    db_session.commit()
    assert _reject(client, active).status_code == 200 and len(_notes(active)) == 1


def test_reject_twice_is_quiet_and_a_request_closed_by_the_fix_is_refused(client, sent, who):
    oid = _order(who)
    login(client, who.staff)
    assert _reject(client, oid).status_code == 200
    again = _reject(client, oid)
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False and len(sent.push) == 1
    done = _order(who, state="done", checked=True)
    res = _reject(client, done)
    assert res.status_code == 409 and _code(res) == "REQUEST_CLOSED" and res.get_json()["error"] == CLOSED
    assert _req(done)["state"] == "done"
    missing = _reject(client, oid, rid="fr_nope")
    assert missing.status_code == 404 and _code(missing) == "REQUEST_NOT_FOUND"


# --- [반영 완료] · [완료 해제] · 그 뒤 수정본 ---------------------------------------------------


def test_check_keeps_the_block_until_the_fix_is_sent_then_the_request_is_done(client, sent, who):
    oid = _order(who)
    login(client, who.staff)
    assert _code(send(client, "drawing", oid, "s1")) == "FACTORY_REQUEST_OPEN"           # 반영 완료 전에는 못 보냄(D2)
    res = _check(client, oid, True)
    assert res.status_code == 200 and res.get_json()["data"]["request"]["checked"] is True
    req = _req(oid)
    assert (req["state"], req["checked_by_name"]) == ("open", "김도면") and req["checked_at"].endswith("Z")
    assert fx.blocked(sd_of(oid)).idents == frozenset({"sheet:s1"})                    # [반영 완료] 뒤에도 막힌 채
    assert [e.payload["checked"] for e in _events(oid, "DRAWING_FIX_REQUEST_CHECKED")] == [True] and not sent.push
    assert _check(client, oid, True).get_json()["data"]["changed"] is False              # 같은 값 = 쓰기 0
    ok = send(client, "drawing", oid, "s1")
    assert ok.status_code == 200, ok.get_json()
    req = _req(oid)
    assert req["state"] == "done" and req["resolved"] == ["sheet:s1"] and fx.blocked(sd_of(oid)).idents == frozenset()
    res = _check(client, oid, False)
    assert res.status_code == 409 and _code(res) == "REQUEST_CLOSED"                     # 닫힌 요청은 못 고친다


def test_uncheck_clears_who_and_when(client, sent, who):
    oid = _order(who, checked=True)
    login(client, who.admin)
    res = _check(client, oid, False)
    assert res.status_code == 200 and res.get_json()["data"]["changed"] is True
    req = _req(oid)
    assert (req["checked"], req["checked_by_name"], req["checked_at"], req["state"]) == (False, None, None, "open")


# --- 단계 나감 · 시공 대기 ----------------------------------------------------------------


def test_leaving_production_closes_open_requests_in_the_same_write(client, sent, who):
    oid = _order(who, checked=True)
    mark_order_inspected(oid)
    login(client, who.admin)
    res = client.post(f"/api/orders/{oid}/production/complete",
                      json={"admin_override": True, "override_reason": "시험 — 공장 요청 열린 채 시공으로"})
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    req = sd["drawing_fix"]["requests"][0]
    assert sd["workflow"]["stage"] == "CONSTRUCTION" and fx.blocked(sd).idents == frozenset()   # 시공 대기에 막힘이 안 남는다
    assert (req["state"], req["via"], req["rejected_by_name"], req["reject_note"]) == ("done", "stage_exit", None, None)
    assert req["done_at"] and req["checked"] is True
    assert sd["drawing_fix"]["log"][-1] | {"at": None} == {
        "act": "done", "idents": ["sheet:s1"], "numbers": [2], "requests": ["fr_a1"], "closed": ["fr_a1"], "by_name": "한관리",
        "at": None, "via": "stage_exit", "to": "CONSTRUCTION"}
    db_session.expire_all()
    assert not db_session.query(Notification).filter_by(order_id=oid).count()          # 반려가 아니다 — 알림 없음
    assert not _events(oid, "DRAWING_FIX_REQUEST_REJECTED")


def test_override_back_to_confirm_closes_and_coming_back_does_not_resurrect(client, sent, who):
    oid = _order(who)
    login(client, who.admin)
    for to in ("CONFIRM", "PRODUCTION"):
        res = client.post(f"/api/orders/{oid}/workflow/stage-override", json={"to_stage": to, "reason": "시험 되돌림", "confirm": True})
        assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert sd["workflow"]["stage"] == "PRODUCTION" and _req(oid)["state"] == "done" and fx.blocked(sd).idents == frozenset()


def test_waiting_order_detail_handles_a_left_over_open_request(client, sent, who):
    oid = _order(who, stage="CONSTRUCTION")
    login(client, who.staff)
    html = client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True)
    assert 'data-dfr-act="check"' in html and 'data-dfr-act="reject"' in html and "workbench-factory-request.js" in html
    assert _reject(client, oid).status_code == 200 and fx.blocked(sd_of(oid)).idents == frozenset()


# --- 작업실 상세 요청사항 칸 -------------------------------------------------------------


def _requests_block(html: str) -> str:
    start = html.index("<span><i class=\"fas fa-comments\"></i> 요청사항</span>")
    return html[start:html.index("</details>", start)]


def test_detail_lists_factory_request_with_reason_photo_chips_and_buttons(client, sent, who):
    photos = [{"key": "orders/{oid}/drawing_gateway/revisions/p0.jpg", "filename": "측판.jpg"}]
    oid = make_order(3, cdate=day(3), status="RETURNED", history=[sales_request("2026-11-25 02:05:00", targets=[])])
    sd = sd_of(oid)
    req = _request(who.lead.id, photos=[{k: v.format(oid=oid) for k, v in p.items()} for p in photos])
    order = db_session.get(Order, oid)
    order.structured_data = {**sd, "drawing_fix": {"requests": [req]}}
    db_session.commit()
    login(client, who.staff)
    block = _requests_block(client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True))
    assert re.search(r'<span class="badge bg-light text-dark border">\s*2\s*</span>', block)          # 영업 1 + 공장 1
    assert block.index("수정 요청 · 공장") < block.index("상판 깊이 600 → 580")                       # 공장 요청 맨 위
    assert "수정 요청 · 공장</span> 11/25 13:40 · 박반장" in block and "사유: 측판 길이가 실측과 달라요" in block
    assert '<span class="dw-target-chip-no">2번</span>' in block and "측판.jpg" in block               # 대상 칩 · 사진(지금 보기 길)
    assert f'data-view-url="/api/files/view/orders/{oid}/drawing_gateway/revisions/p0.jpg"' in block
    assert '<span class="badge dfr-open">미완료</span>' in block and "bg-secondary\">미완료" in block    # 공장 = 주황 · 영업 = 지금 그대로
    assert 'data-dfr-act="check" data-next-checked="true"' in block and "요청 반려</button>" in block
    assert 'data-confirm="반려 사유를 적어 주세요. 요청한 사람에게 알림이 가고, 도면 2 막힘이 풀려요."' in block


def test_rejected_request_keeps_a_record_line_and_no_buttons(client, sent, who):
    oid = _order(who)
    login(client, who.manager)
    assert _reject(client, oid, note="그대로 가요").status_code == 200
    block = _requests_block(client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True))
    assert re.search(r"반려 · 오도면 · \d{1,2}/\d{1,2} \d{2}:\d{2} · 사유: 그대로 가요", block)
    assert "data-dfr-act" not in block and "dfr-open" not in block and "workbench-factory-request.js" not in block


def test_sales_rows_and_empty_text_stay_as_today_without_factory_requests(client, sent, who):
    """대조군: 공장 요청이 없으면 요청사항 칸은 지금 그대로(빈 글 · 영업 줄)."""
    oid = make_order(3, cdate=day(3))
    login(client, who.staff)
    block = _requests_block(client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True))
    assert "수정 요청 이력이 없습니다." in block and "dfr" not in block


def test_readonly_viewer_sees_the_row_without_buttons(client, sent, who):
    oid = _order(who)
    login(client, who.sales)
    block = _requests_block(client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True))
    assert '<span class="dwp-req dfr-src">수정 요청 · 공장</span>' in block and "data-dfr-act" not in block


# --- 매니페스트 ---------------------------------------------------------------------


def test_routes_are_in_both_manifests_as_drawing_team_guard():
    policy, guard = load_policy_manifest()["routes"], load_write_guard_manifest()["routes"]
    for act in ("reject", "check"):
        endpoint = f"erp_orders_drawing_fix.api_drawing_fix_request_{act}"
        rule = f"/api/orders/<int:order_id>/drawing/fix/requests/<rid>/{act}"
        assert policy[endpoint] == {"mode": "guard", "policy_id": "DRAWING_TEAM", "rule": rule}
        assert guard[endpoint] == {"mode": "guard", "rule": rule}
