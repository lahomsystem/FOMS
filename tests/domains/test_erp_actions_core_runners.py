"""단계 넘기기 · 도면 담당 맡기기 · 방문 옮기기(실측) 실행기(T14 · D206 · 설계서 2026-11-14-foms-graft 3.12).

- **같음 시험**: 똑같이 만든 주문 둘 — 하나는 지금 길(그 처리기 주소)로, 하나는 제안 승인(승인 대기 API → 실행기)으로 처리한
  뒤 특성 시험 도우미(``tests/support/graft_char.py``)로 뜬 자국이 글자까지 같다. 실행기 쪽에만 ``ERP_ACTION_APPROVED`` ·
  ``ERP_ACTION_EXECUTED`` 감사 줄이 더 있다. 다른 것은 날짜 표 훅의 출처(``request.endpoint``)뿐 — 승인 API 이름이 된다.
- **막힘**: 도면 문지기 · 권한 없는 팀 · 승격 전 초안 · 담당을 안 고름 → 409 ``ACTION_PRECONDITION``, 주문 · 제안 그대로.
- **뚫기 값**: 넣을 값 · 고친 값에 끼울 수 없고 본문은 정한 칸뿐이다. 앞 문지기 정책 · 역할 장식자는 가드가 꺼져도 다시 본다.
- 막는 조건 · 바뀌는 칸 · 끝난 조건(되맞추기) · 차례 · 고를 사람 목록. 바깥 보내기는 모두 가짜. 지어낸 계정 · 주문만.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
from types import SimpleNamespace

import pytest

import foms.api.erp_action_runners as api_runners
from db import db_session
from foms.persistence.graft.models import ErpActionProposal
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_actions import preview
from foms.services.erp_actions.lifecycle import propose, reconcile
from foms.services.erp_actions.runners import RunRequest
from foms.services.graft_flags import FLAGS
from foms.services.orders.erp_policy_quests import create_quest_from_template
from foms.services.orders.order_mutation_policy import policy_id_for_endpoint
from models import Order
from tests.support import graft_char as gc
from tests.support.confirm_seed import confirmed_drawing_sd

BASE = "/api/erp-actions"
D1, D2 = "2031-05-06", "2031-05-09"
QUEST_KW = {"sd_paths": ("workflow.stage", "blueprint", "workflow.history"), "views": {"quests": gc.quest_rows},
            "flat": ("status", "erp_stage_code", "erp_stage_updated_at", "structured_updated_at")}
ASSIGN_KW = {"sd_paths": ("assignments", "drawing_assignees", "shipment", "workflow"),
             "flat": ("status", "erp_stage_code", "structured_updated_at")}
MEASURE_KW = {"sd_paths": ("schedule", "drawing_transfer_history"),
              "flat": ("measurement_date", "erp_measurement_date", "status", "structured_updated_at")}
ERP_AUDIT = {"ERP_ACTION_APPROVED": 1, "ERP_ACTION_EXECUTED": 1}
BLOCKED_AUDIT = {"audit": {"ERP_ACTION_APPROVED": 1, "ERP_ACTION_FAILED": 1}}  # 실행기가 막힘 — 주문 자국 없음
BODIES = ("approve_quest_from_payload", "assign_draftsman_from_payload", "update_order_field_from_payload")


@pytest.fixture
def out(monkeypatch):
    """바깥 보내기(푸시 · 화면 알림 · 알림톡)를 가짜로 — 시험은 아무것도 밖으로 보내지 않는다."""
    return gc.install_fakes(monkeypatch)


@pytest.fixture
def switches(monkeypatch):
    """접목판 스위치를 모두 끈 뒤 회사 지식 새 화면 · 할 일만 모두에게 켠다."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    for env in ("FOMS_GRAFT_BRAIN_UI", "FOMS_GRAFT_ACTIONS"):
        monkeypatch.setenv(f"{env}_ENABLED", "1")
        monkeypatch.setenv(f"{env}_COHORT", "all")
    return monkeypatch


@pytest.fixture
def bodies(monkeypatch):
    """실행기가 부른 본체와 그 본문을 적는다(진짜 본체를 그대로 부른다)."""
    seen: dict[str, list] = {name: [] for name in BODIES}
    for name in BODIES:
        real = getattr(api_runners, name)

        def spy(*args, _name=name, _real=real, **kwargs):
            seen[_name].append(args[1] if _name != BODIES[2] else args[0])
            return _real(*args, **kwargs)

        monkeypatch.setattr(api_runners, name, spy)
    return seen


def _quest(stage: str, **over) -> dict:
    return {**create_quest_from_template(stage, "", {}), **over}


def _order(stage: str, quests: list | None = None, extra: dict | None = None, **cols) -> int:
    sd = {"workflow": {"stage": stage}, "parties": {"manager": {"name": "특성 영업"}}}
    if quests is not None:
        sd["quests"] = quests
    sd.update(extra or {})
    return gc.make_order(sd, status=cols.pop("status", stage), erp_stage_code=stage, **cols)


def _stuck(stage: str, extra: dict | None = None, **cols) -> int:
    """승인을 다 받았는데 단계가 그대로인 주문(강제 단계 변경 뒤 — 훑기 O2 가 단계 넘기기를 제안하는 꼴)."""
    return _order(stage, [_quest(stage, status="COMPLETED", completed_at="2031-01-02T10:00:00")], extra, **cols)


def _measure(date: str | None) -> int:
    return _order("RECEIVED", extra={"schedule": {"measurement": {"date": date, "time": "10시"}}} if date else None)


def _propose(order_id: int, action: str, params: dict | None = None, agent: str = "agent:ops") -> tuple[int, int]:
    row = propose(db_session, action=action, proposed_by=agent, order=db_session.get(Order, order_id),
                  params=params or {}, reason="합성 이유", evidence=[], source_kind="sweep", source_ref="1", level=1,
                  now=now_utc_naive())
    db_session.commit()
    assert row is not None
    return row.id, row.base_version


def _approve(client, pid: int, base: int, **body):
    return client.post(f"{BASE}/proposals/{pid}/approve", json={"base_version": base, **body})


def _run(order_id: int, call, kw: dict):
    """``call()`` 앞뒤로 주문 자국을 떠 (답, 앞뒤 차이, 새 줄)."""
    before = gc.snapshot(order_id, **kw)
    resp = call()
    after = gc.snapshot(order_id, **kw)
    return resp, gc.delta(before, after), gc.new_rows(before, after)


def _norm(rows: dict, order_id: int) -> str:
    """새 줄 글자에서 주문 번호만 접는다(같은 꼴로 만든 두 주문은 번호만 다르다)."""
    text = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return (text.replace(f"#{order_id} ", "#<주문> ").replace(f'"order", {order_id},', '"order", "<주문>",')
            .replace(f'"order_id": {order_id}', '"order_id": "<주문>"'))


def _same(route: tuple, runner: tuple, route_oid: int, runner_oid: int) -> None:
    """같음 — 실행기 쪽에서 승인 대기 감사 둘(승인 먼저 · 실행 끝)을 빼면 지금 길의 차이 · 새 줄과 글자까지 같다."""
    d_run, rows_run = dict(runner[1]), dict(runner[2])
    audit = dict(d_run.pop("audit", {}))
    assert {name: audit.pop(name, 0) for name in ERP_AUDIT} == ERP_AUDIT
    assert ({**d_run, "audit": audit} if audit else d_run) == route[1]
    actions = [row[0] for row in rows_run["audit"]]
    assert actions[0] == "ERP_ACTION_APPROVED" and actions[-1] == "ERP_ACTION_EXECUTED"
    rows_run["audit"] = [row for row in rows_run["audit"] if not str(row[0]).startswith("ERP_ACTION_")]
    assert _norm(rows_run, runner_oid) == _norm(route[2], route_oid)


def _executed(resp) -> dict:
    body = resp.get_json()
    assert resp.status_code == 200 and body["data"]["status"] == "executed", body
    return body["data"]


def _blocked(resp, reason: str) -> None:
    body = resp.get_json()
    assert resp.status_code == 409 and body["data"]["code"] == "ACTION_PRECONDITION", body
    assert body["data"]["reason"] == reason and body["error"] == reason


def _status(pid: int) -> str:
    db_session.expire_all()
    return db_session.get(ErpActionProposal, pid).status


# ── 같음 시험 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("stage, team, moved", [("MEASURE", "SALES", ("MEASURE", "DRAWING")),
                                                 ("CS", "CS", ("CS", "COMPLETED"))])
def test_단계_넘기기_실행기는_지금_길과_같은_자국을_남긴다(client, out, switches, bodies, stage, team, moved):
    actor = gc.make_user("cr-actor", team=team)
    gc.login_as(client, actor)
    a, b = _stuck(stage), _stuck(stage)
    route = _run(a, lambda: client.post(f"/api/orders/{a}/quest/approve", json={}), QUEST_KW)
    pid, base = _propose(b, "advance_stage")
    runner = _run(b, lambda: _approve(client, pid, base), QUEST_KW)
    assert route[0].status_code == 200 and route[1]["sd"]["workflow.stage"] == moved
    data = _executed(runner[0])
    assert (data["result"]["from_stage"], data["result"]["to_stage"]) == moved and data["message"] == "단계를 넘겼어요."
    _same(route, runner, a, b)
    (sent,) = bodies["approve_quest_from_payload"]
    assert list(sent) == ["idempotency_key"] and sent["idempotency_key"].startswith(f"erp-action-{pid}-")
    assert _status(pid) == "executed"


def test_도면_담당_맡기기_실행기는_지금_길과_같은_자국을_남긴다(client, out, switches, bodies):
    admin, drawer = gc.make_user("cr-admin", role="ADMIN", team="CS"), gc.make_user("cr-draw", team="DRAWING")
    gc.login_as(client, admin)
    a, b = _order("DRAWING"), _order("DRAWING")
    route = _run(a, lambda: client.post(f"/api/orders/{a}/assign-draftsman", json={"user_ids": [drawer.id]}),
                 ASSIGN_KW)
    pid, base = _propose(b, "assign_draftsman")
    runner = _run(b, lambda: _approve(client, pid, base, edits={"user_ids": [drawer.id]}), ASSIGN_KW)
    assert route[0].status_code == 200 and _executed(runner[0])["result"]["count"] == 1
    _same(route, runner, a, b)
    assert bodies["assign_draftsman_from_payload"] == [{"user_ids": [drawer.id]}]
    db_session.expire_all()
    row = db_session.get(ErpActionProposal, pid)
    assert (row.status, row.edited_params, row.decided_action) == ("executed", {"user_ids": [drawer.id]}, "edit_approve")
    stored = json.dumps([row.params, row.preview, row.result, row.edited_params, row.reason], ensure_ascii=False)
    assert "cr-draw" not in stored and "직원" not in stored  # 제안 줄에 직원 이름을 남기지 않는다


def test_방문_옮기기_실측_실행기는_지금_길과_같은_자국을_남긴다(client, out, switches, bodies):
    gc.login_as(client, gc.make_user("cr-sales", team="SALES"))
    a, b = _measure(D1), _measure(D1)
    route = _run(a, lambda: client.post("/api/update_order_field",
                                        json={"order_id": a, "field": "measurement_date", "value": D2}), MEASURE_KW)
    pid, base = _propose(b, "move_measurement", {"date": D2}, agent="agent:cs")
    runner = _run(b, lambda: _approve(client, pid, base), MEASURE_KW)
    assert route[0].status_code == 200 and _executed(runner[0])["result"]["date"] == D2
    _same(route, runner, a, b)
    assert bodies["update_order_field_from_payload"] == [{"order_id": b, "field": "measurement_date", "value": D2}]
    assert out.alimtalk == [a, b]  # 커밋 뒤 자동 알림톡 시도도 같다(가짜)


@pytest.mark.parametrize("module, name", [("foms.api.orders.field_update", "log_access"),
                                          ("foms.api.orders.field_update", "record_field_changes")])
def test_대조군_실행기_쪽_옆_효과_하나를_빼면_같음_견주기가_빨개진다(client, out, switches, monkeypatch, module, name):
    gc.login_as(client, gc.make_user("cr-sales", team="SALES"))
    a, b = _measure(D1), _measure(D1)
    route = _run(a, lambda: client.post("/api/update_order_field",
                                        json={"order_id": a, "field": "measurement_date", "value": D2}), MEASURE_KW)
    pid, base = _propose(b, "move_measurement", {"date": D2}, agent="agent:cs")
    monkeypatch.setattr(module + "." + name, lambda *args, **kwargs: 0)
    runner = _run(b, lambda: _approve(client, pid, base), MEASURE_KW)
    _executed(runner[0])
    with pytest.raises(AssertionError):
        _same(route, runner, a, b)


def test_오늘로_옮기면_당일_알림도_같고_날짜_표_출처만_승인_API_이름이다(client, out, switches):
    gc.make_user("cr-sales2", team="SALES")
    gc.login_as(client, gc.make_user("cr-sales", team="SALES"))
    a, b = _measure(None), _measure(None)
    route = _run(a, lambda: client.post("/api/update_order_field",
                                        json={"order_id": a, "field": "measurement_date", "value": gc.FAKE_TODAY}),
                 MEASURE_KW)
    pid, base = _propose(b, "move_measurement", {"date": gc.FAKE_TODAY}, agent="agent:cs")
    runner = _run(b, lambda: _approve(client, pid, base), MEASURE_KW)
    _executed(runner[0])
    d_run = {k: v for k, v in runner[1].items() if k != "audit"}
    assert d_run == {k: v for k, v in route[1].items() if k != "audit"}
    assert route[1]["events"] == {"MEASURE_SAME_DAY_ADDED": 1} and route[1]["notification_states"] == 2
    sources = [rows[2]["events"][0][1]["source"] for rows in (route, runner)]
    assert sources == ["orders.update_order_field", "erp_actions_api.erp_actions_approve"]
    assert len(out.push) == 2 and [n for n, kind in out.emit] == [2, 2]


# ── 막힘 갈래 — 409 · 주문 · 제안 그대로 ────────────────────────────────────
def test_도면_문지기는_막는_조건과_본체_둘_다에서_막는다(client, out, switches, monkeypatch):
    gc.login_as(client, gc.make_user("cr-sales", team="SALES"))
    oid = _stuck("CONFIRM", extra=confirmed_drawing_sd())
    pid, base = _propose(oid, "advance_stage")
    order = db_session.get(Order, oid)
    order.structured_data = {**order.structured_data, **confirmed_drawing_sd(drawing_status="RETURNED")}
    db_session.commit()
    resp, d, _ = _run(oid, lambda: _approve(client, pid, base), QUEST_KW)
    _blocked(resp, "도면 수정 요청이 진행 중입니다. 수정본을 받아 수령 확정한 뒤 고객 컨펌을 완료하세요.")
    assert d == {} and _status(pid) == "open"
    # 막는 조건을 지나도(경합) 본체의 도면 문지기가 409 로 막는다 — 실행기는 막힘으로 옮기고 주문은 그대로
    fns = preview.FUNCTIONS["advance_stage"]
    monkeypatch.setitem(preview.FUNCTIONS, "advance_stage", dataclasses.replace(fns, check=lambda o, p: None))
    other = _stuck("CONFIRM")
    pid2, base2 = _propose(other, "advance_stage")
    resp, d, _ = _run(other, lambda: _approve(client, pid2, base2), QUEST_KW)
    _blocked(resp, "도면 수령 확정 기록이 없습니다. 도면 전달과 수령 확정을 먼저 해 주세요.")
    assert d == BLOCKED_AUDIT and _status(pid2) == "open"


def test_권한_없는_팀은_본체가_막고_주문과_제안이_그대로다(client, out, switches):
    drawer = gc.make_user("cr-draw", team="DRAWING")
    stage_oid, assign_oid = _stuck("RECEIVED"), _order("DRAWING")
    stage_pid, stage_base = _propose(stage_oid, "advance_stage")
    assign_pid, assign_base = _propose(assign_oid, "assign_draftsman")
    gc.login_as(client, gc.make_user("cr-prod", team="PRODUCTION"))  # 정책(STAFF_MUTATION)은 지나고 본체가 막는 팀
    resp, d, _ = _run(stage_oid, lambda: _approve(client, stage_pid, stage_base), QUEST_KW)
    _blocked(resp, "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)")
    assert d == BLOCKED_AUDIT and _status(stage_pid) == "open"
    resp, d, _ = _run(assign_oid, lambda: _approve(client, assign_pid, assign_base, edits={"user_ids": [drawer.id]}),
                      ASSIGN_KW)
    _blocked(resp, "도면 담당자 지정 권한이 없습니다. (관리자/도면팀/지정 도면담당자만 가능)")
    assert d == BLOCKED_AUDIT and _status(assign_pid) == "open"


@pytest.mark.parametrize("action, make, params, kw", [
    ("advance_stage", lambda: _stuck("RECEIVED"), {}, QUEST_KW),
    ("assign_draftsman", lambda: _order("DRAWING"), {}, ASSIGN_KW),
    ("move_measurement", lambda: _measure(D1), {"date": D2}, MEASURE_KW),
])
def test_승격_전_초안이_되면_막는_조건이_409로_막는다(client, out, switches, action, make, params, kw):
    gc.login_as(client, gc.make_user("cr-admin", role="ADMIN", team="CS"))
    oid = make()
    pid, base = _propose(oid, action, params)
    order = db_session.get(Order, oid)
    order.status = "DRAFT"
    db_session.commit()
    resp, d, _ = _run(oid, lambda: _approve(client, pid, base), kw)
    _blocked(resp, "아직 등록 전인 초안 주문이에요.")
    assert d == {} and _status(pid) == "open"


def test_담당을_안_고르고_승인하면_본체가_막고_제안이_열린_채다(client, out, switches):
    gc.login_as(client, gc.make_user("cr-admin", role="ADMIN", team="CS"))
    oid = _order("DRAWING")
    pid, base = _propose(oid, "assign_draftsman")
    resp, d, _ = _run(oid, lambda: _approve(client, pid, base), ASSIGN_KW)
    _blocked(resp, "담당자를 선택해주세요.")
    assert d == BLOCKED_AUDIT and _status(pid) == "open"


# ── 뚫기 값 · 앞 문지기 · 역할 ─────────────────────────────────────────────
def test_뚫기_값은_넣을_값에도_고친_값에도_끼울_수_없다(client, out, switches, bodies):
    gc.login_as(client, gc.make_user("cr-admin", role="ADMIN", team="CS"))
    stuck, drawing, measure = _stuck("MEASURE"), _order("DRAWING"), _measure(D1)
    for oid, action, params in ((stuck, "advance_stage", {"team": "CS"}),
                                (stuck, "advance_stage", {"admin_override": True, "override_reason": "급함"}),
                                (drawing, "assign_draftsman", {"user_ids": [], "emergency_override": True}),
                                (measure, "move_measurement", {"date": D2, "field": "status"})):
        assert propose(db_session, action=action, proposed_by="agent:ops", order=db_session.get(Order, oid),
                       params=params, reason="", evidence=[], source_kind="sweep", source_ref="1", level=1,
                       now=now_utc_naive()) is None
    pid, base = _propose(stuck, "advance_stage")
    for edits in ({"emergency_override": True, "override_reason": "급함"}, {"admin_override": True},
                  {"team": "PRODUCTION"}):
        resp, d, _ = _run(stuck, lambda: _approve(client, pid, base, edits=edits), QUEST_KW)
        assert resp.status_code == 400 and resp.get_json()["data"] == {"code": "ACTION_SHAPE", "fields": ["edits"]}
        assert d == {}
    assert all(not calls for calls in bodies.values()) and _status(pid) == "open"


def test_앞_문지기_정책은_가드가_꺼진_맥락에서도_길_목록_정책으로_다시_본다(app, client, out, switches, bodies,
                                                                     monkeypatch):
    endpoints = (api_runners.QUEST_APPROVE_ENDPOINT, api_runners.ASSIGN_DRAFTSMAN_ENDPOINT,
                 api_runners.UPDATE_FIELD_ENDPOINT)
    assert {e: policy_id_for_endpoint(e) for e in endpoints} == dict.fromkeys(endpoints, "STAFF_MUTATION")
    assert set(endpoints) <= {rule.endpoint for rule in app.url_map.iter_rules()}
    gc.login_as(client, gc.make_user("cr-sales", team="SALES"))
    oid = _measure(D1)
    pid, base = _propose(oid, "move_measurement", {"date": D2}, agent="agent:cs")
    monkeypatch.setattr(api_runners, "policy_id_for_endpoint", lambda endpoint: "ADMIN_OPS")  # 관리자만인 정책이면
    resp, d, _ = _run(oid, lambda: _approve(client, pid, base), MEASURE_KW)
    _blocked(resp, "이 작업 권한이 없는 팀입니다.")
    assert d == BLOCKED_AUDIT and not bodies["update_order_field_from_payload"]


@pytest.mark.parametrize("role", ["staff", "VIEWER", "PARTNER", None])
def test_단계_넘기기는_길의_역할_장식자와_같은_비교로_막는다(app, bodies, role):
    actor = SimpleNamespace(id=1, role=role, team="CS", username="cr-x", is_active=True)
    req = RunRequest(proposal_id=1, action="advance_stage", order_id=1, params={}, actor=actor)
    outcome = api_runners.run_advance_stage(db_session, req)
    assert (outcome.status, outcome.message) == ("blocked", api_runners._ROLE_DENIED)
    assert not bodies["approve_quest_from_payload"]


def test_스위치가_꺼지면_승인_대기는_없는_것과_같고_본체를_부르지_않는다(client, out, bodies, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
    gc.login_as(client, gc.make_user("cr-sales", team="SALES"))
    oid = _stuck("MEASURE")
    pid, base = _propose(oid, "advance_stage")
    resp, d, _ = _run(oid, lambda: _approve(client, pid, base), QUEST_KW)
    assert resp.status_code == 404 and d == {} and not bodies["approve_quest_from_payload"]


# ── 막는 조건 · 바뀌는 칸 · 끝난 조건 · 차례 · 고를 사람 ───────────────────────
NOT_YET = "아직 승인하지 않은 현재 작업이 있어요 — 주문 화면에서 승인해 주세요."


@pytest.mark.parametrize("stage, quests, extra, reason, stuck", [
    ("DRAWING", "done", None, "도면 단계는 도면 전달 · 수령 확정으로 넘어가요.", False),
    ("PRODUCTION", "done", None, "생산 단계는 생산 완료로 넘어가요.", False),
    ("CONSTRUCTION", "done", None, "시공 단계는 시공 완료로 넘어가요.", False),
    ("COMPLETED", None, None, "더 넘길 단계가 없어요.", False),
    ("RECEIVED", "open", None, NOT_YET, False), ("MEASURE", None, None, NOT_YET, False),
    ("CONFIRM", "done", None, "도면 수령 확정 기록이 없습니다. 도면 전달과 수령 확정을 먼저 해 주세요.", True),
    ("CONFIRM", "done", confirmed_drawing_sd(), None, True), ("RECEIVED", "done", None, None, True),
    ("CS", "done", None, None, True),
])
def test_단계_넘기기는_재전이_길만_지나고_끝난_조건은_막다른_길이_풀림(app, stage, quests, extra, reason, stuck):
    done = {"done": [_quest(stage, status="COMPLETED")], "open": [_quest(stage)], None: []}[quests]
    order = db_session.get(Order, _order(stage, done, extra))
    assert preview.check("advance_stage", order, {}) == reason
    assert preview.verify("advance_stage", order, {}) is not stuck


def test_단계_넘기기_바뀌는_칸과_차례는_본체가_하는_일만(app):
    received, measure, cs = (db_session.get(Order, _stuck(s)) for s in ("RECEIVED", "MEASURE", "CS"))
    assert preview.preview("advance_stage", measure, {}) == [{"field": "주문 단계", "before": "실측", "after": "도면"}]
    again = "FOMS 현재 작업 승인 다시 걸기 — 주문 화면 [승인]과 같은 기능(승인 기록은 그대로)"
    assert preview.steps("advance_stage", received, {}) == [again, "단계 넘김 — 주문접수 → 실측", "실측 현재 작업 새로 만들기"]
    assert preview.steps("advance_stage", measure, {}) == [again, "단계 넘김 — 실측 → 도면"]
    assert preview.steps("advance_stage", cs, {}) == [
        "FOMS 최종 완료 — CS 완료와 같은 기능(보류 · 진행 중 AS 가 있으면 막혀요)", "단계 넘김 — CS → 완료"]


def test_실행_중에_멈춘_단계_넘기기는_주문이_넘어갔으면_실행됨으로_맞춘다(client, out, switches):
    sales = gc.make_user("cr-sales", team="SALES")
    moved, stuck = _stuck("MEASURE"), _stuck("MEASURE")
    pids = [_propose(oid, "advance_stage")[0] for oid in (moved, stuck)]
    for pid in pids:
        row = db_session.get(ErpActionProposal, pid)
        row.status, row.decided_by, row.decided_action = "executing", sales.id, "approve"
        row.decided_at = now_utc_naive() - datetime.timedelta(minutes=5)
    db_session.commit()
    gc.login_as(client, sales)
    assert client.post(f"/api/orders/{moved}/quest/approve", json={}).status_code == 200  # 본체는 커밋하고 죽었다
    assert reconcile(db_session, now_utc_naive()) == 2
    db_session.commit()
    assert [_status(pid) for pid in pids] == ["executed", "open"]


def test_도면_담당_고를_사람은_승인_창을_열_때_켜진_도면팀만_이름_차례로(client, out, switches):
    admin = gc.make_user("cr-admin", role="ADMIN", team="CS")
    later, first = gc.make_user("cr-b", team="DRAWING"), gc.make_user("cr-a", team=" DRAWING ")
    gc.make_user("cr-off", team="DRAWING", active=False)
    gc.make_user("cr-sales", team="SALES")
    oid = _order("DRAWING")
    pid, _ = _propose(oid, "assign_draftsman")
    gc.login_as(client, admin)
    data = client.get(f"{BASE}/proposals/{pid}").get_json()["data"]
    assert (data["mode"], data["phone_ok"], data["changes"]) == (
        "run", False, [{"field": "도면 담당", "before": "없음", "after": "승인하는 사람이 고름"}])
    assert data["params"] == [{"name": "user_ids", "label": "도면 담당", "kind": "users", "value": [], "required": True, "choices": [
        {"value": first.id, "label": "cr-a 직원"}, {"value": later.id, "label": "cr-b 직원"}]}]
    assert data["steps"] == ["FOMS 도면 담당 지정 — 주문 화면 도면 담당 칸과 같은 기능", "단계 이력에 '도면 담당자 지정' 한 줄"]
    order = db_session.get(Order, oid)
    assert preview.preview("assign_draftsman", order, {"user_ids": [first.id]})[0]["after"] == "1명"
    assert not preview.verify("assign_draftsman", order, {"user_ids": [first.id]})


def test_방문_옮기기_실측_차례는_본체가_하는_일만(app, monkeypatch):
    order = db_session.get(Order, _measure(D1))
    write = "FOMS 실측일 쓰기 — 주문 화면 실측일 칸과 같은 기능"
    assert preview.steps("move_measurement", order, {"date": D2}) == [write]  # 자동 알림톡 꺼짐 · 오늘 아님
    monkeypatch.setattr(preview, "get_today_kst", lambda: datetime.date.fromisoformat(D2))
    monkeypatch.setattr(preview, "_env_flag", lambda name: name == "FOMS_ALIMTALK_AUTO_ENABLED")
    monkeypatch.setattr(preview, "_ineligible_reason",
                        lambda o, sd: None if sd["schedule"]["measurement"] == {"date": D2, "time": "10시"} else "x")
    assert preview.steps("move_measurement", order, {"date": D2}) == [
        write, "영업팀 모두에게 알림 — 오늘 실측이 새로 생김",
        "손님 알림톡 1건 — 실측 예약 안내(자동 보내기 · 같은 일정 안내를 이미 보냈으면 안 나가요)"]
