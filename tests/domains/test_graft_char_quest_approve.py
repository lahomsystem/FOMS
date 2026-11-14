"""특성 시험 — 현재 작업 승인 ``POST /api/orders/<id>/quest/approve`` 의 지금 행동 (T13 · D206).
T14 가 처리기 본체(``foms/api/quest.py`` ``api_order_quest_approve``)를 함수로 떼어 낸다. 떼어 낸 뒤에도
이 파일을 **한 글자도 고치지 않은 채** 초록이어야 행동이 같다는 증거다. 그래서 장면마다 답 코드 ·
답 값의 칸 · 주문 자국(일 기록 · 감사 · 원장 · 알림 · 바깥 일 · 영수증 · 단계 · 납작 칸 ·
``mutation_version``)의 앞뒤 차이 **전체**를 글자 그대로 견준다(``tests/support/graft_char.py``).
이상해 보여도 지금 행동이면 그대로 못박았다(고치는 일은 이 일감 몫이 아니다):
* ``order.updated_at = now`` 는 ``orders`` 에 없는 칸이라 아무것도 남지 않는다(그래서 견주지 않는다).
* 팀을 적어 다시 누르면 막 넘어온 단계를 승인해 한 단계 더 넘어간다(``ALREADY_TRANSITIONED`` 는 팀 없는 요청만).
* 같은 ``Idempotency-Key`` 를 다른 주문에 쓰면 앞 주문의 영수증을 되풀이해 승인만 남고 단계는 그대로다.
* 도면 단계는 관리자 뚫기로도 409(``STAGE_COMMAND_REQUIRED``)이고 아무것도 남지 않는다.
* 재전이 답에는 ``missing_team_labels`` 칸이 없다(CS 재전이는 ``completion_blocked`` 만 있다).
* 다음 단계 퀘스트의 ``owner_person`` 은 사용자 번호 글자다(템플릿 합성 퀘스트는 아이디).
* 시험 레인은 정책 가드(``AUTH_POLICY_ENABLED``)가 꺼져 있다 — 켠 장면을 따로 둔다.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.api import quest as quest_api
from foms.services.orders import order_transition_service, quest_transition_service
from foms.services.orders.erp_policy_quests import create_quest_from_template
from models import OrderAssignment
from tests.support import graft_char as gc
from tests.support.confirm_seed import confirmed_drawing_sd

SD = ("workflow.stage", "blueprint", "workflow.history")
FLAT = ("status", "erp_stage_code", "erp_stage_updated_at", "structured_updated_at", "measurement_completed")
KEYS = ["all_approved", "auto_transitioned", "completion_blocked", "missing_team_labels",
        "missing_teams", "next_stage", "quest", "retransitioned", "success"]
RETRANS_KEYS = [k for k in KEYS if k not in ("completion_blocked", "missing_team_labels")]
ROUTE = "quest.api_order_quest_approve"


@pytest.fixture
def out(monkeypatch):
    """바깥 보내기를 가짜로 바꾼다 — 이 길은 아무것도 밖으로 보내지 않아야 한다."""
    return gc.install_fakes(monkeypatch)


def _quest(stage: str, **over) -> dict:
    """템플릿 그대로의 현재 단계 퀘스트(``over`` 로 칸을 덮는다)."""
    return {**create_quest_from_template(stage, "", {}), **over}


def _order(stage: str, quests: list, extra: dict | None = None, **cols) -> int:
    """ERP 주문 1건(``workflow.stage`` · 퀘스트 · 지어낸 영업 이름)."""
    sd = {"workflow": {"stage": stage}, "quests": quests, "parties": {"manager": {"name": "특성 영업"}}}
    sd.update(extra or {})
    return gc.make_order(sd, status=cols.pop("status", stage), erp_stage_code=stage, **cols)


def _approve(client, order_id: int, body: dict | None = None, headers: dict | None = None):
    """승인을 부르고 (답, 앞뒤 차이, 새 줄)을 돌려준다."""
    kw = {"sd_paths": SD, "flat": FLAT, "views": {"quests": gc.quest_rows}}
    before = gc.snapshot(order_id, **kw)
    resp = client.post(f"/api/orders/{order_id}/quest/approve", json=body if body is not None else {},
                       headers=headers)
    after = gc.snapshot(order_id, **kw)
    return resp, gc.delta(before, after), gc.new_rows(before, after)


def _answer(resp) -> tuple:  # (답 코드, 퀘스트 칸을 뺀 답 값)
    return resp.status_code, {k: v for k, v in resp.get_json().items() if k != "quest"}


def _ok(**over) -> dict:
    """정상 승인 답 값(퀘스트 칸 뺌)의 기본 꼴."""
    return {"success": True, "all_approved": True, "auto_transitioned": True, "retransitioned": False,
            "missing_teams": [], "missing_team_labels": [], "completion_blocked": None, **over}


def _flat_moved(frm: str, to: str) -> dict:
    return {"status": (frm, to), "erp_stage_code": (frm, to), "erp_stage_updated_at": (None, gc.TS)}


def _received_expected(uid: int) -> dict:
    """주문접수 CS 승인 한 번이 남기는 자국 전체(대조군도 이 값과 견준다)."""
    return {
        "events": {"MEASUREMENT_REQUESTED": 1, "QUEST_APPROVAL_CHANGED": 1}, "audit": {"QUEST_APPROVED": 1},
        "outbox": {"STAGE_NOTIFICATION": 1}, "receipts": {"STATE_REQUEST_MEASUREMENT": 1},
        "sd": {"workflow.stage": ("RECEIVED", "MEASURE"),
               "quests": ([("RECEIVED", "OPEN", "team", {"CS": (False, None, None)}, (None, None), "")],
                          [("RECEIVED", "COMPLETED", "team", {"CS": (True, uid, "CS")}, (None, None), ""),
                           ("MEASURE", "OPEN", "assignee", {}, (False, None), str(uid))])},
        "flat": _flat_moved("RECEIVED", "MEASURE"), "mutation_version": 1}


def _received_run(client):
    cs = gc.make_user("qa-cs", team="CS")
    gc.login_as(client, cs)
    oid = _order("RECEIVED", [_quest("RECEIVED")])
    return (cs, oid, *_approve(client, oid, {"team": "CS"}))


def test_주문접수_CS팀_승인_한_번으로_실측_단계로_넘어가고_밖으로는_아무것도_안_보낸다(client, out):
    cs, oid, resp, d, rows = _received_run(client)
    assert _answer(resp) == (200, _ok(next_stage="실측"))
    assert sorted(resp.get_json()) == KEYS
    assert d == _received_expected(cs.id)
    assert rows == {
        "events": [
            ("QUEST_APPROVAL_CHANGED", {
                "domain": "RECEIVED_DOMAIN", "action": "QUEST_APPROVAL_CHANGED", "target": "quest.team_approvals.CS",
                "team": "CS", "stage": "RECEIVED", "before": "not_approved", "after": "approved",
                "change_method": "API", "source_screen": "erp_dashboard", "reason": "CS 팀 승인 완료",
                "is_override": False, "override_reason": None}),
            ("MEASUREMENT_REQUESTED", {
                "command": "REQUEST_MEASUREMENT", "axis": "MAIN", "from": "RECEIVED", "to": "MEASURE",
                "reason": "주문접수 최종 승인", "source_screen": "erp_dashboard", "emergency_override": False})],
        "audit": [("QUEST_APPROVED", "order", oid, f"주문 #{oid} (특성시험 손님) — 퀘스트 승인: CS",
                   {"team": "CS", "customer_name": "특성시험 손님", "order_type": "주문"})],
        "outbox": [("STAGE_NOTIFICATION", {"order_id": oid, "command": "REQUEST_MEASUREMENT",
                                           "axis": "MAIN", "from": "RECEIVED", "to": "MEASURE"}, "PENDING")]}
    broad = ("orders", "measurement", "shipment", "construction", "history", "production", "drawing")
    assert (out.summary(), out.cache) == ({}, [("families", broad), ("families", ("orders",))])


def test_필수팀이_둘이면_첫_승인은_기록만_하고_마지막_승인으로_넘어간다(client, out):
    cs, sales = gc.make_user("qa-cs", team="CS"), gc.make_user("qa-sales", team="SALES")
    oid = _order("RECEIVED", [_quest("RECEIVED", required_approvals=["CS", "SALES"])])
    gc.login_as(client, cs)
    resp, d, _ = _approve(client, oid, {"team": "CS"})
    assert _answer(resp) == (200, _ok(all_approved=False, auto_transitioned=False, missing_teams=["SALES"],
                                      missing_team_labels=["영업팀"], next_stage=None))
    half = [("RECEIVED", "IN_PROGRESS", "team", {"CS": (True, cs.id, "CS")}, (None, None), "")]
    assert d == {"events": {"QUEST_APPROVAL_CHANGED": 1}, "audit": {"QUEST_APPROVED": 1},
                 "sd": {"quests": ([("RECEIVED", "OPEN", "team", {"CS": (False, None, None)}, (None, None), "")],
                                   half)}}
    gc.login_as(client, sales)
    resp, d, _ = _approve(client, oid, {"team": "SALES"})
    assert _answer(resp) == (200, _ok(next_stage="실측"))
    done = {"CS": (True, cs.id, "CS"), "SALES": (True, sales.id, "SALES")}
    assert d == {
        "events": {"MEASUREMENT_REQUESTED": 1, "QUEST_APPROVAL_CHANGED": 1}, "audit": {"QUEST_APPROVED": 1},
        "outbox": {"STAGE_NOTIFICATION": 1}, "receipts": {"STATE_REQUEST_MEASUREMENT": 1},
        "sd": {"workflow.stage": ("RECEIVED", "MEASURE"),
               "quests": (half, [("RECEIVED", "COMPLETED", "team", done, (None, None), ""),
                                 ("MEASURE", "OPEN", "assignee", {}, (False, None), str(sales.id))])},
        "flat": _flat_moved("RECEIVED", "MEASURE"), "mutation_version": 1}


def _measure_expected(quest_before: list, quest_after: list) -> dict:
    return {"events": {"MEASUREMENT_COMPLETED": 1, "QUEST_APPROVAL_CHANGED": 1}, "audit": {"QUEST_APPROVED": 1},
            "outbox": {"STAGE_NOTIFICATION": 1}, "receipts": {"STATE_COMPLETE_MEASUREMENT": 1},
            "sd": {"workflow.stage": ("MEASURE", "DRAWING"), "quests": (quest_before, quest_after)},
            "flat": _flat_moved("MEASURE", "DRAWING"), "mutation_version": 1}


M_OPEN = [("MEASURE", "OPEN", "assignee", {}, (False, None), "")]


def test_실측_담당자_승인으로_도면_단계로_넘어간다(client, out):
    sales = gc.make_user("qa-sales", team="SALES")
    gc.login_as(client, sales)
    oid = _order("MEASURE", [_quest("MEASURE")])
    resp, d, rows = _approve(client, oid, {})
    assert _answer(resp) == (200, _ok(next_stage="도면"))
    assert d == _measure_expected(M_OPEN, [("MEASURE", "COMPLETED", "assignee", {}, (True, sales.id), "")])
    assert rows["events"][0] == ("QUEST_APPROVAL_CHANGED", {
        "domain": "SALES_DOMAIN", "action": "QUEST_ASSIGNEE_APPROVED", "target": "quest.assignee_approval",
        "stage": "MEASURE", "before": "not_approved", "after": "approved", "change_method": "API",
        "source_screen": "erp_dashboard", "reason": "실측 담당자 승인 완료",
        "is_override": False, "override_reason": None})


def test_자가실측_주문은_실측완료_체크를_같이_켜고_커밋_뒤_감사를_남긴다(client, out):
    sales = gc.make_user("qa-sales", team="SALES")
    gc.login_as(client, sales)
    oid = _order("MEASURE", [_quest("MEASURE")], is_self_measurement=True)
    resp, d, rows = _approve(client, oid, {})
    assert resp.status_code == 200
    expected = _measure_expected(M_OPEN, [("MEASURE", "COMPLETED", "assignee", {}, (True, sales.id), "")])
    expected["events"]["REGIONAL_CHECKLIST_UPDATED"] = 1
    expected["audit"]["ORDER_CHECKLIST_UPDATED"] = 1
    expected["field_changes"] = {"measurement_completed set False -> True": 1}
    expected["flat"]["measurement_completed"] = (False, True)
    assert d == expected
    assert rows["events"][2] == ("REGIONAL_CHECKLIST_UPDATED", {"field": "measurement_completed", "value": True})
    assert rows["audit"][1] == (
        "ORDER_CHECKLIST_UPDATED", "order", oid, f"자가실측 주문 #{oid} (특성시험 손님) — 실측완료: 해제 → 완료",
        {"field": "measurement_completed", "before": False, "after": True, "change_set": gc.GROUP,
         "customer_name": "특성시험 손님", "order_type": "자가실측 주문"})


def test_현재_단계_퀘스트가_없으면_템플릿으로_만들어_승인한다(client, out):
    cs = gc.make_user("qa-cs", team="CS")
    gc.login_as(client, cs)
    resp, d, _ = _approve(client, _order("MEASURE", []), {})
    assert _answer(resp) == (200, _ok(next_stage="도면"))
    assert resp.get_json()["quest"]["stage"] == "실측"
    assert d == _measure_expected([], [("실측", "COMPLETED", "assignee", {}, (True, cs.id), "qa-cs")])


@pytest.mark.parametrize("role, body, code, message", [
    ("STAFF", {}, "COMMAND_REQUIRED", "도면 단계는 단독 퀘스트 승인이 아니라 전용 command로 진행해야 합니다."),
    ("ADMIN", {}, "COMMAND_REQUIRED", "도면 단계는 단독 퀘스트 승인이 아니라 전용 command로 진행해야 합니다."),
    ("ADMIN", {"admin_override": True, "override_reason": "시험 사유"}, "STAGE_COMMAND_REQUIRED",
     "DRAWING 단계는 standalone quest 승인이 아니라 전용 command 로만 전이합니다."),
])
def test_도면_단계는_409이고_관리자_뚫기로도_아무것도_남지_않는다(client, out, role, body, code, message):
    gc.login_as(client, gc.make_user("qa-draw", role=role, team="DRAWING"))
    resp, d, _ = _approve(client, _order("DRAWING", [_quest("DRAWING")]), body)
    assert _answer(resp) == (409, {"success": False, "code": code, "message": message})
    assert d == {}


@pytest.mark.parametrize("drawing, status, message", [
    ({}, "NONE", "도면 수령 확정 기록이 없습니다. 도면 전달과 수령 확정을 먼저 해 주세요."),
    (confirmed_drawing_sd(drawing_status="RETURNED"), "RETURNED",
     "도면 수정 요청이 진행 중입니다. 수정본을 받아 수령 확정한 뒤 고객 컨펌을 완료하세요."),
    (confirmed_drawing_sd(drawing_status="TRANSFERRED"), "TRANSFERRED",
     "새로 전달된 도면을 아직 수령 확정하지 않았습니다. 도면을 확인하고 수령 확정부터 해 주세요."),
])
def test_고객컨펌은_도면_확정_전이면_409_DRAWING_STATUS(client, out, drawing, status, message):
    gc.login_as(client, gc.make_user("qa-sales", team="SALES"))
    resp, d, _ = _approve(client, _order("CONFIRM", [_quest("CONFIRM")], extra=drawing), {})
    assert _answer(resp) == (409, {"success": False, "code": "DRAWING_STATUS", "message": message,
                                   "drawing_status": status})
    assert d == {}


def _confirm_expected(uid: int, name: str) -> dict:
    return {"events": {"CUSTOMER_CONFIRMED": 1, "QUEST_APPROVAL_CHANGED": 1}, "audit": {"QUEST_APPROVED": 1},
            "outbox": {"STAGE_NOTIFICATION": 1}, "receipts": {"STATE_CUSTOMER_CONFIRM": 1},
            "sd": {"workflow.stage": ("CONFIRM", "PRODUCTION"),
                   "blueprint": (gc.ABSENT, {"customer_confirmed": True, "confirmed_at": gc.TS, "confirmed_by": name}),
                   "quests": ([("CONFIRM", "OPEN", "assignee", {}, (False, None), "")],
                              [("CONFIRM", "COMPLETED", "assignee", {}, (True, uid), "")])},
            "flat": _flat_moved("CONFIRM", "PRODUCTION"), "mutation_version": 1}


def test_고객컨펌_도면_확정이면_생산으로_넘기고_고객확인을_남긴다(client, out):
    sales = gc.make_user("qa-sales", team="SALES")
    gc.login_as(client, sales)
    resp, d, _ = _approve(client, _order("CONFIRM", [_quest("CONFIRM")], extra=confirmed_drawing_sd()), {})
    assert _answer(resp) == (200, _ok(next_stage="생산"))
    assert d == _confirm_expected(sales.id, "qa-sales")


def test_고객컨펌_관리자_뚫기는_사유를_남기고_생산으로_넘긴다(client, out):
    admin = gc.make_user("qa-admin", role="ADMIN", team="SALES")
    gc.login_as(client, admin)
    oid = _order("CONFIRM", [_quest("CONFIRM")])
    resp, d, rows = _approve(client, oid, {"admin_override": True, "override_reason": "시험 사유"})
    assert _answer(resp) == (200, _ok(next_stage="생산"))
    expected = _confirm_expected(admin.id, "qa-admin")
    expected["events"]["ADMIN_OVERRIDE_USED"] = 1
    expected["audit"]["ADMIN_OVERRIDE_USED"] = 1
    assert d == expected
    used = {"gate": "DRAWING_STATUS", "gates": ["DRAWING_STATUS"], "route": ROUTE, "axis": "QUEST",
            "from": "", "to": "", "reason": "시험 사유", "bulk": False, "drawing_status": "NONE",
            "actor": {"id": admin.id, "name": "qa-admin 직원", "role": "ADMIN"}}
    assert rows["events"][2] == ("ADMIN_OVERRIDE_USED", used)
    assert rows["audit"][1] == ("ADMIN_OVERRIDE_USED", "order", oid,
                                f"주문 #{oid} 관리자 강제 진행(건너뛴 검사: DRAWING_STATUS) — {ROUTE} (시험 사유)", used)


@pytest.mark.parametrize("role, body, status, code, message", [
    ("STAFF", {"admin_override": True, "override_reason": "x"}, 403, "ADMIN_ONLY", "관리자만 검사를 건너뛸 수 있습니다."),
    ("ADMIN", {"admin_override": True}, 422, "REASON_REQUIRED", "검사를 건너뛰려면 사유가 필요합니다."),
    ("ADMIN", {"admin_override": {"x": 1}}, 400, "ADMIN_OVERRIDE_SHAPE",
     "주문별 관리자 강제 진행은 받지 않습니다. 요청 본문 맨 위에 admin_override 와 사유를 한 번만 넣으세요."),
])
def test_뚫기_요청의_모양_권한_사유가_틀리면_거부하고_감사에만_남긴다(client, out, role, body, status, code, message):
    gc.login_as(client, gc.make_user("qa-x", role=role, team="SALES"))
    oid = _order("CONFIRM", [_quest("CONFIRM")])
    resp, d, rows = _approve(client, oid, body)
    assert _answer(resp) == (status, {"success": False, "code": code, "message": message, "error": message})
    assert d == {"audit": {"ADMIN_OVERRIDE_DENIED": 1}}
    assert rows["audit"] == [("ADMIN_OVERRIDE_DENIED", "order", oid,
                              f"주문 #{oid} 관리자 강제 진행 거부({code}) — {ROUTE}",
                              {"gate": code, "route": ROUTE, "actor_role": role})]


@pytest.mark.parametrize("status, extra", [("DRAFT", {}), ("RECEIVED", {"meta": {"draft": True}})])
def test_승격_전_초안은_409_DRAFT_NOT_PROMOTED(client, out, status, extra):
    gc.login_as(client, gc.make_user("qa-cs", team="CS"))
    oid = _order("RECEIVED", [_quest("RECEIVED")], extra=extra, status=status)
    resp, d, _ = _approve(client, oid, {"team": "CS"})
    text = "아직 저장(등록)하지 않은 초안입니다. 먼저 주문을 저장한 뒤 단계를 바꿀 수 있습니다."
    assert _answer(resp) == (409, {"success": False, "code": "DRAFT_NOT_PROMOTED", "error": text,
                                   "message": text, "data": {"order_id": oid}})
    assert d == {}


@pytest.mark.parametrize("missing, status, message", [
    ("stage", 400, "현재 단계가 없습니다."), ("order", 404, "주문을 찾을 수 없습니다.")])
def test_현재_단계가_없으면_400_주문이_없으면_404(client, out, missing, status, message):
    gc.login_as(client, gc.make_user("qa-cs", team="CS"))
    oid = gc.make_order({"quests": []}) if missing == "stage" else 4242
    resp, d, _ = _approve(client, oid, {"team": "CS"})
    assert _answer(resp) == (status, {"success": False, "message": message})
    assert d == {}


@pytest.mark.parametrize("role, body, status, message", [
    ("STAFF", {"team": "PRODUCTION"}, 403, "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)"),
    ("STAFF", {"emergency_override": True, "override_reason": "급함"}, 403, "긴급 오버라이드는 관리자만 가능합니다."),
    ("MANAGER", {"emergency_override": True}, 422, "오버라이드 승인은 사유(override_reason)가 필수입니다."),
])
def test_팀과_긴급_오버라이드_거부_갈래(client, out, role, body, status, message):
    gc.login_as(client, gc.make_user("qa-x", role=role, team="SALES"))
    resp, d, _ = _approve(client, _order("PRODUCTION", [_quest("PRODUCTION")]), body)
    assert _answer(resp) == (status, {"success": False, "message": message})
    assert d == {}


def test_매니저_긴급_오버라이드는_필수팀_칸에_누른_팀을_따로_적는다(client, out):
    mgr = gc.make_user("qa-mgr", role="MANAGER", team="SALES")
    gc.login_as(client, mgr)
    body = {"emergency_override": True, "override_reason": "급함", "team": "PRODUCTION"}
    resp, d, rows = _approve(client, _order("PRODUCTION", [_quest("PRODUCTION")]), body)
    assert _answer(resp) == (200, _ok(auto_transitioned=False, next_stage="시공"))
    assert d["sd"]["quests"][1] == [("PRODUCTION", "COMPLETED", "team", {"PRODUCTION": (True, mgr.id, "SALES")},
                                     (None, None), "")]
    assert rows["events"][0][1]["is_override"] is True and rows["events"][0][1]["override_reason"] == "급함"


def test_생산_승인은_기록만_하고_단계를_옮기지_않는다(client, out):
    prod = gc.make_user("qa-prod", team="PRODUCTION")
    gc.login_as(client, prod)
    resp, d, _ = _approve(client, _order("PRODUCTION", [_quest("PRODUCTION")]), {"team": "PRODUCTION"})
    assert _answer(resp) == (200, _ok(auto_transitioned=False, next_stage="시공"))
    assert d == {"events": {"QUEST_APPROVAL_CHANGED": 1}, "audit": {"QUEST_APPROVED": 1},
                 "sd": {"quests": ([("PRODUCTION", "OPEN", "team", {"PRODUCTION": (False, None, None)},
                                     (None, None), "")],
                                   [("PRODUCTION", "COMPLETED", "team", {"PRODUCTION": (True, prod.id, "PRODUCTION")},
                                     (None, None), "")])}}


@pytest.mark.parametrize("who, assigned, message", [
    ("con", True, None),
    ("other", True, "이 주문에 배정된 시공 담당자만 승인할 수 있습니다."),
    ("draw", False, "시공 승인 권한이 없는 팀입니다."),
])
def test_시공은_배정된_사람만_승인한다(client, out, who, assigned, message):
    con = gc.make_user("qa-con", team="CONSTRUCTION")
    actor = {"con": con, "other": gc.make_user("qa-con2", team="CONSTRUCTION"),
             "draw": gc.make_user("qa-draw", team="DRAWING")}[who]
    oid = _order("CONSTRUCTION", [_quest("CONSTRUCTION")])
    if assigned:
        db_session.add(OrderAssignment(order_id=oid, domain="CONSTRUCTION", user_id=con.id,
                                       source="TEAM_REPLACE", active=True, assigned_by_user_id=con.id))
        db_session.commit()
    gc.login_as(client, actor)
    resp, d, _ = _approve(client, oid, {"team": "CONSTRUCTION"})
    if message:
        assert _answer(resp) == (403, {"success": False, "message": message}) and d == {}
        return
    assert _answer(resp) == (200, _ok(auto_transitioned=False, next_stage="CS"))
    assert (d["events"], d["audit"], set(d)) == ({"QUEST_APPROVAL_CHANGED": 1}, {"QUEST_APPROVED": 1}, {"events", "audit", "sd"})


def test_로그인_안_하면_로그인_화면으로_돌려보내고_아무것도_안_남긴다(client, out):
    oid = _order("RECEIVED", [_quest("RECEIVED")])
    resp, d, _ = _approve(client, oid, {"team": "CS"})
    assert (resp.status_code, resp.headers["Location"]) == (302, f"/login?next=/api/orders/{oid}/quest/approve")
    assert d == {}


def test_조회_전용_역할은_첫_화면으로_돌려보내고_감사_한_줄을_남긴다(client, out):
    gc.login_as(client, gc.make_user("qa-viewer", role="VIEWER", team="CS"))
    oid = _order("RECEIVED", [_quest("RECEIVED")])
    resp, d, rows = _approve(client, oid, {"team": "CS"})
    assert (resp.status_code, resp.headers["Location"]) == (302, "/")
    assert d == {"audit": {gc.NO_ACTION: 1}}
    assert rows["audit"] == [(gc.NO_ACTION, None, None, f"권한 없는 접근 시도: /api/orders/{oid}/quest/approve", None)]


def test_정책_가드를_켜면_조회_전용은_처리기_앞에서_403(client, out, app, monkeypatch):
    monkeypatch.setitem(app.config, "AUTH_POLICY_ENABLED", True)
    gc.login_as(client, gc.make_user("qa-viewer", role="VIEWER", team="CS"))
    resp, d, _ = _approve(client, _order("RECEIVED", [_quest("RECEIVED")]), {"team": "CS"})
    text = "조회 전용 계정은 이 작업을 할 수 없습니다."
    assert _answer(resp) == (403, {"success": False, "code": "FORBIDDEN", "data": None, "error": text, "message": text})
    assert d == {"audit": {"ACCESS_DENIED": 1}}


def test_이미_넘어간_주문을_팀_없이_다시_누르면_409_ALREADY_TRANSITIONED(client, out):
    gc.login_as(client, gc.make_user("qa-cs", team="CS"))
    resp, d, _ = _approve(client, _order("MEASURE", [_quest("RECEIVED", status="COMPLETED")]), {})
    assert _answer(resp) == (409, {"success": False, "code": "ALREADY_TRANSITIONED",
                                   "message": "이미 실측 단계로 넘어간 주문입니다. 화면을 새로고침하세요."})
    assert d == {}


def test_팀을_적어_다시_누르면_막_넘어온_단계를_승인해_한_단계_더_넘어간다(client, out):
    cs, oid, _, _, _ = _received_run(client)
    resp, d, _ = _approve(client, oid, {"team": "CS"})
    assert _answer(resp) == (200, _ok(next_stage="도면"))
    received = ("RECEIVED", "COMPLETED", "team", {"CS": (True, cs.id, "CS")}, (None, None), "")
    expected = _measure_expected(
        [received, ("MEASURE", "OPEN", "assignee", {}, (False, None), str(cs.id))],
        [received, ("MEASURE", "COMPLETED", "assignee", {}, (True, cs.id), str(cs.id))])
    expected["flat"]["erp_stage_updated_at"] = (gc.TS, gc.NEW_TS)
    assert d == expected


def test_강제_단계_변경_뒤_완료된_퀘스트는_승인_기록을_두고_재전이만_한다(client, out):
    gc.login_as(client, gc.make_user("qa-sales", team="SALES"))
    oid = _order("MEASURE", [_quest("MEASURE", status="COMPLETED", completed_at="2031-01-02T10:00:00")])
    resp, d, rows = _approve(client, oid, {})
    assert _answer(resp) == (200, {"success": True, "all_approved": True, "auto_transitioned": True,
                                   "retransitioned": True, "missing_teams": [], "next_stage": "도면"})
    assert sorted(resp.get_json()) == RETRANS_KEYS
    assert d == {"events": {"MEASUREMENT_COMPLETED": 1}, "audit": {"QUEST_APPROVED": 1},
                 "outbox": {"STAGE_NOTIFICATION": 1}, "receipts": {"STATE_COMPLETE_MEASUREMENT": 1},
                 "sd": {"workflow.stage": ("MEASURE", "DRAWING")}, "flat": _flat_moved("MEASURE", "DRAWING"),
                 "mutation_version": 1}
    assert rows["events"][0][1]["reason"] == "실측 재전이(완료 quest, 강제 단계 변경 뒤)"
    assert rows["audit"][0][3] == f"주문 #{oid} (특성시험 손님) — 퀘스트 승인: 재전이"


def test_같은_멱등_열쇠를_다른_주문에_쓰면_앞_주문_영수증을_되풀이해_단계는_그대로다(client, out):
    cs = gc.make_user("qa-cs", team="CS")
    gc.login_as(client, cs)
    first, second = _order("RECEIVED", [_quest("RECEIVED")]), _order("RECEIVED", [_quest("RECEIVED")])
    assert _approve(client, first, {"team": "CS"}, {"Idempotency-Key": "k-1"})[0].status_code == 200
    resp, d, _ = _approve(client, second, {"team": "CS"}, {"Idempotency-Key": "k-1"})
    assert _answer(resp) == (200, _ok(auto_transitioned=False, next_stage="주문접수"))
    done = [("RECEIVED", "COMPLETED", "team", {"CS": (True, cs.id, "CS")}, (None, None), "")]
    assert d == {"events": {"QUEST_APPROVAL_CHANGED": 1}, "audit": {"QUEST_APPROVED": 1}, "sd": {"quests": (
        [("RECEIVED", "OPEN", "team", {"CS": (False, None, None)}, (None, None), "")], done)}}
    resp, d, _ = _approve(client, second, {"team": "CS", "idempotency_key": "k-1"})
    assert _answer(resp) == (409, {"success": False, "code": "IDEMPOTENCY_KEY_CONFLICT",
                                   "message": "idempotency key reused with a different request hash."})
    # 감사 줄은 견주지 않는다 — SQLite 레인은 쓰기 전 SAVEPOINT 의 RELEASE 가 커밋돼 롤백 뒤에도 남는다(PG 는 사라진다).
    assert {k: v for k, v in d.items() if k != "audit"} == {}


def _cs_done(uid: int, by_team: str, name: str) -> dict:
    history = [{"stage": "COMPLETED", "updated_at": gc.TS, "updated_by": name, "note": "CS 완료 -> 최종 완료"}]
    return {"events": {"CS_COMPLETED": 1, "QUEST_APPROVAL_CHANGED": 1}, "audit": {gc.NO_ACTION: 1, "QUEST_APPROVED": 1},
            "outbox": {"STAGE_NOTIFICATION": 1}, "receipts": {"STATE_CS_COMPLETE": 1},
            "sd": {"workflow.stage": ("CS", "COMPLETED"), "workflow.history": (gc.ABSENT, history),
                   "quests": ([("CS", "OPEN", "team", {"CS": (False, None, None)}, (None, None), "")],
                              [("CS", "COMPLETED", "team", {"CS": (True, uid, by_team)}, (None, None), "")])},
            "flat": _flat_moved("CS", "COMPLETED"), "mutation_version": 1}


@pytest.mark.parametrize("team", ["CS", "ACCOUNTING"])
def test_CS_승인은_같은_트랜잭션에서_최종_완료까지_보낸다(client, out, team):
    actor = gc.make_user("qa-cs", team=team)
    gc.login_as(client, actor)
    oid = _order("CS", [_quest("CS")])
    resp, d, rows = _approve(client, oid, {"team": team})
    assert _answer(resp) == (200, _ok(next_stage="완료"))
    assert d == _cs_done(actor.id, team, "qa-cs 직원")
    assert rows["audit"][1] == (gc.NO_ACTION, None, None, f"주문 #{oid} CS 완료 -> 최종 완료", None)


@pytest.mark.parametrize("user_kw, body, extra, blocked", [
    ({"team": "CS"}, {"team": "CS"}, {"workflow": {"stage": "CS", "hold": {"active": True}}},
     {"code": "HOLD_ACTIVE", "message": "CS 확인은 기록됐지만 보류 중이라 완료로 넘기지 못했습니다. 보류를 풀고 다시 눌러 주세요."}),
    ({"role": "MANAGER", "team": "PRODUCTION"}, {"team": "CS", "emergency_override": True, "override_reason": "급함"}, {},
     {"code": "NO_COMPLETE_PERMISSION", "message": "CS 확인은 기록됐지만 완료 처리 권한이 없어 CS 단계에 남습니다."}),
])
def test_CS_승인이_완료로_못_넘어가면_승인만_남기고_까닭을_답한다(client, out, user_kw, body, extra, blocked):
    gc.login_as(client, gc.make_user("qa-x", **user_kw))
    resp, d, _ = _approve(client, _order("CS", [_quest("CS")], extra=extra), body)
    assert _answer(resp) == (200, _ok(auto_transitioned=False, completion_blocked=blocked, next_stage="완료"))
    assert set(d) == {"events", "audit", "sd"}
    assert d["events"] == {"QUEST_APPROVAL_CHANGED": 1} and d["audit"] == {"QUEST_APPROVED": 1}


def test_CS_완료_퀘스트가_남은_주문은_같은_버튼으로_완료까지_재전이한다(client, out):
    gc.login_as(client, gc.make_user("qa-cs", team="CS"))
    resp, d, _ = _approve(client, _order("CS", [_quest("CS", status="COMPLETED")]), {})
    assert _answer(resp) == (200, {"success": True, "all_approved": True, "auto_transitioned": True,
                                   "retransitioned": True, "missing_teams": [], "next_stage": "완료",
                                   "completion_blocked": None})
    expected = _cs_done(0, "", "qa-cs 직원")
    expected["events"].pop("QUEST_APPROVAL_CHANGED")
    expected["sd"].pop("quests")
    assert d == expected


# --------------------------------------------------------------------------- #
# 대조군 — 옆 효과 하나를 시험 안에서 없애면 같은 견주기가 빨개져야 자국이 못박힌 것이다.
# --------------------------------------------------------------------------- #
def test_대조군_감사_줄을_빼면_견주기가_빨개진다(client, out, monkeypatch):
    monkeypatch.setattr(quest_api, "_audit_quest", lambda *a, **k: None)
    cs, _, resp, d, _ = _received_run(client)
    assert resp.status_code == 200 and d != _received_expected(cs.id) and "audit" not in d


def test_대조군_다음_단계_퀘스트를_안_만들면_견주기가_빨개진다(client, out, monkeypatch):
    monkeypatch.setattr(quest_transition_service, "_append_next_stage_quest", lambda *a, **k: None)
    cs, _, _, d, _ = _received_run(client)
    assert d != _received_expected(cs.id) and len(d["sd"]["quests"][1]) == 1


def test_대조군_줄_세운_바깥_일을_빼면_견주기가_빨개진다(client, out, monkeypatch):
    monkeypatch.setattr(order_transition_service, "enqueue_side_effect",
                        lambda *a, **k: type("Row", (), {"id": None})())
    cs, _, _, d, _ = _received_run(client)
    assert d != _received_expected(cs.id) and "outbox" not in d
