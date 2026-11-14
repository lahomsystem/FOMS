"""ERP 할 일 제안 생명주기(설계서 2026-11-14-foms-graft 3.4) — 만들기 · 겹침 · 거절된 것 다시 안 만듦 · 승인(두 걸음) · 두 번
누름 409 · 기준 판 바뀜 409 와 새 카드 · 막는 조건 409 · 실행 실패 → failed · [다시] · 막힘 → open · 되맞추기 두 갈래 · 바로가기
닫기 · 기간 끝남 · 나중에 · 감사 줄에 글 없음.

실행기는 가짜(:class:`RunOutcome` 만 돌려준다) — 실제 감싼 기능은 ``test_erp_actions_runners.py``. 합성 주문 · 합성 글만.
"""

from __future__ import annotations

import dataclasses
import datetime

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session
from foms.persistence.graft.models import BrainUsageEvent, ErpActionProposal
from foms.services.ai_staff.registry import SETTINGS_KEY as AI_LEVELS_KEY
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import lifecycle, registry
from foms.services.erp_actions.lifecycle import ActionError, approve, expire_due, propose, reconcile, reject, snooze
from foms.services.erp_actions.registry import ActionShapeError, dedupe_key
from foms.services.erp_actions.runners import RunOutcome
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order, SecurityLog, SystemSetting, User

NOW = now_utc_naive()
CUSTOMER = "합성손님"
REASON = "손님이 오전 방문을 원한다고 적음"


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def _user(name: str = "lc_admin", role: str = "ADMIN", team=None) -> User:
    user = User(username=name, password=generate_password_hash("pw"), role=role, team=team, name=f"{name}-이름",
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order(stage: str = "CONFIRM", construction=None, **sd_extra) -> Order:
    sd = {"workflow": {"stage": stage}, **sd_extra}
    if construction:
        sd["schedule"] = {"construction": {"date": construction[0], "time": construction[1]}}
    order = Order(received_date="2030-01-01", customer_name=CUSTOMER, phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _propose(target: Order, action: str = "schedule_construction", **overrides) -> ErpActionProposal | None:
    args = dict(action=action, proposed_by="agent:schedule", order=target, params={"date": _day(10), "time": "오전"},
                reason=REASON, evidence=[{"kind": "brain", "ref": "cs/lesson/weekend", "label": "주말 시공"},
                                         {"kind": "order", "ref": f"erp:order/{target.id}", "label": "주문"}],
                source_kind="sweep", source_ref="7", level=2, now=NOW)
    args.update(overrides)
    row = propose(db_session, **args)
    db_session.commit()
    return row


def _runner(calls: list, outcome: RunOutcome | None = None, effect=None):
    def run(session, req):
        calls.append(req)
        if effect is not None:
            effect(session, req)
        return outcome or RunOutcome.executed("합성 실행", done=True)
    return run


def _approve(row, actor, runners, **kwargs):
    kwargs.setdefault("base_version", row.base_version)
    return approve(db_session, row.id, actor=actor, runners=runners, now=NOW, **kwargs)


def _as_link(monkeypatch, name: str = "assign_draftsman") -> None:
    """판 1 끝에는 바로가기 할 일이 없다(D206 · T14) — 바로가기 길(떼어 내기가 막힌 할 일의 꼴)은 하나를 바꿔 끼워 본다."""
    monkeypatch.setitem(registry.ACTIONS, name, dataclasses.replace(registry.ACTIONS[name], mode=registry.MODE_LINK))


def _audits(code: str) -> list[SecurityLog]:
    return db_session.query(SecurityLog).filter(SecurityLog.action == code).all()


def test_propose_makes_open_row_with_preview_and_usage(app):
    order = _order("RECEIVED")
    row = _propose(order)
    assert row.status == "open" and row.level == 2 and row.base_version == order.mutation_version
    assert row.params == {"date": _day(10), "time": "오전", "notify_customer": True}  # 손님 알림톡 처음 값 켬(D213)
    assert row.dedupe_key == dedupe_key("schedule_construction", order.id, row.params)
    assert row.preview[0]["field"] == "시공 날짜" and row.preview[0]["before"] == "없음"
    assert row.preview[0]["after"].endswith("오전") and row.reason == REASON
    assert NOW < row.expires_at <= NOW + datetime.timedelta(days=7)
    uses = db_session.query(BrainUsageEvent).all()
    assert [(u.item_key, u.reader, u.ref_kind, u.ref_id) for u in uses] == [
        ("cs/lesson/weekend", "erp_action", "proposal", str(row.id))]


def test_same_key_is_not_made_twice_and_rejected_never_comes_back(app):
    order = _order("RECEIVED")
    first = _propose(order)
    assert _propose(order) is None
    reject(db_session, first.id, actor=_user(), code="no_slot", now=NOW)
    db_session.commit()
    assert _propose(order) is None
    assert db_session.query(ErpActionProposal).count() == 1


def test_racing_duplicate_hits_the_unique_index_and_keeps_the_session(app, monkeypatch):
    order = _order("RECEIVED")
    first = _propose(order)
    monkeypatch.setattr(lifecycle, "_taken", lambda session, row: False)  # 겹침 확인을 지난 동시 만들기 흉내
    assert _propose(order) is None
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, first.id).status == "open"  # 같은 열쇠는 밀어내지 않는다
    assert db_session.query(ErpActionProposal).count() == 1


def test_newer_proposal_supersedes_the_open_one(app):
    order = _order("RECEIVED")
    old = _propose(order)
    new = _propose(order, params={"date": _day(11), "time": "오후"})
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, old.id).status == "superseded"
    assert db_session.get(ErpActionProposal, new.id).status == "open"


@pytest.mark.parametrize("overrides", [
    {"level": 0}, {"order": None}, {"params": {"date": _day(-1), "time": "오전"}}, {"params": {"date": "내일"}},
    {"reason": "연락은 010-2345-6789 로"}, {"evidence": [{"kind": "brain", "ref": "k", "label": "010-2345-6789"}]},
    {"evidence": [{"kind": "invoice", "ref": "k", "label": "x"}]},
])
def test_propose_skips_without_raising(app, overrides):
    assert _propose(_order("RECEIVED"), **overrides) is None
    assert db_session.query(ErpActionProposal).count() == 0


def test_check_blocks_creation(app):
    assert _propose(_order("CONFIRM", construction=(_day(5), "오전"))) is None  # 시공일이 이미 있으면 시공 잡기 아님
    draft = _order("RECEIVED")
    draft.status = "DRAFT"
    db_session.commit()
    assert _propose(draft) is None  # 승격 전 초안 주문


@pytest.mark.parametrize("change, message", [
    ({"deleted_at": NOW}, "삭제된 주문이에요."), ({"status": "DRAFT"}, "아직 등록 전인 초안 주문이에요."),
])
def test_order_deleted_or_draft_after_proposal_is_409(app, change, message):
    admin, order = _user(), _order("RECEIVED")
    row = _propose(order)
    for name, value in change.items():
        setattr(order, name, value)
    db_session.commit()
    with pytest.raises(ActionError) as blocked:
        _approve(row, admin, {"schedule_construction": _runner([])})
    assert (blocked.value.code, blocked.value.message) == ("ACTION_PRECONDITION", message)


@pytest.mark.parametrize("overrides, error", [
    ({"action": "cancel_order", "params": {}}, ActionShapeError), ({"proposed_by": "user:1"}, ValueError),
    ({"level": 3}, ValueError), ({"source_kind": "chat"}, ValueError),
    ({"action": "send_measure_alimtalk", "params": {}, "proposed_by": "agent:ops", "level": 2}, ValueError),
])
def test_caller_contract_errors_raise(app, overrides, error):
    with pytest.raises(error):
        _propose(_order("RECEIVED"), **overrides)


def test_approve_executes_once_and_audits_without_text(app):
    admin, order = _user(), _order("RECEIVED")
    row, calls = _propose(order), []
    out = _approve(row, admin, {"schedule_construction": _runner(calls)}, view_ms=1500)
    assert out == {"status": "executed", "code": "OK", "message": "합성 실행", "result": {"done": True}}
    assert len(calls) == 1 and calls[0].params == row.params and calls[0].source == f"erp_action:{row.id}"
    db_session.expire_all()
    saved = db_session.get(ErpActionProposal, row.id)
    assert (saved.status, saved.decided_by, saved.decided_action, saved.view_ms) == ("executed", admin.id, "approve", 1500)
    with pytest.raises(ActionError) as again:
        _approve(saved, admin, {"schedule_construction": _runner(calls)})
    assert again.value.code == "ACTION_NOT_OPEN" and len(calls) == 1
    for log in _audits("ERP_ACTION_APPROVED") + _audits("ERP_ACTION_EXECUTED"):
        text = f"{log.message} {log.detail}"
        assert CUSTOMER not in text and REASON not in text and "010" not in text
        assert log.detail["proposal_id"] == row.id and log.detail["agent"] == "schedule"
    assert len(_audits("ERP_ACTION_APPROVED")) == len(_audits("ERP_ACTION_EXECUTED")) == 1


def test_base_changed_returns_409_refreshes_card_then_approves(app):
    admin, order = _user(), _order("CONFIRM", construction=(_day(5), "오전"))
    row, calls = _propose(order, action="move_construction", proposed_by="agent:cs",
                          params={"date": _day(6), "time": "오전"}), []
    sd = dict(order.structured_data)
    sd["schedule"] = {"construction": {"date": _day(5), "time": "오후"}}
    order.structured_data = sd
    db_session.commit()
    runners = {"move_construction": _runner(calls)}
    with pytest.raises(ActionError) as changed:
        _approve(row, admin, runners)
    assert changed.value.code == "ACTION_BASE_CHANGED" and changed.value.proposal_id == row.id and not calls
    db_session.expire_all()
    fresh = db_session.get(ErpActionProposal, row.id)
    assert fresh.status == "open" and fresh.preview[0]["before"].endswith("오후")
    with pytest.raises(ActionError) as stale:
        _approve(fresh, admin, runners, base_version=fresh.base_version - 1)
    assert stale.value.code == "ACTION_BASE_CHANGED"
    assert _approve(fresh, admin, runners, reason_code="customer_request")["status"] == "executed" and len(calls) == 1


def test_precondition_is_409_and_keeps_the_card_open(app):
    admin, order = _user(), _order("RECEIVED")
    row = _propose(order)
    row.params = {"date": _day(-2), "time": "오전"}  # 만든 뒤 날짜가 지남
    db_session.commit()
    with pytest.raises(ActionError) as blocked:
        _approve(row, admin, {"schedule_construction": _runner([])})
    assert blocked.value.code == "ACTION_PRECONDITION" and blocked.value.message == "지난 날짜예요."
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, row.id).status == "open"


def test_failed_run_then_retry_from_failed(app):
    admin, order = _user(), _order("RECEIVED")
    row, calls = _propose(order), []
    out = _approve(row, admin, {"schedule_construction": _runner(calls, RunOutcome.failed(sent=False))})
    assert out["status"] == "failed" and out["code"] == "ACTION_FAILED"
    db_session.expire_all()
    failed = db_session.get(ErpActionProposal, row.id)
    assert (failed.status, failed.error_code, failed.result) == ("failed", "ACTION_FAILED", {"sent": False})
    assert _approve(failed, admin, {"schedule_construction": _runner(calls)})["status"] == "executed"
    assert len(calls) == 2


def test_runner_exception_uses_the_order_trace(app):
    admin, order = _user(), _order("RECEIVED")
    row = _propose(order)

    def write_then_crash(session, req):
        target = session.get(Order, req.order_id)
        target.structured_data = {**target.structured_data,
                                  "schedule": {"construction": {"date": req.params["date"], "time": "오전"}}}
        session.commit()
        raise RuntimeError("합성 실패")

    out = _approve(row, admin, {"schedule_construction": _runner([], effect=write_then_crash)})
    assert out["status"] == "executed" and out["result"] == {"verified": True}

    other = _propose(_order("RECEIVED"), params={"date": _day(12), "time": "오후"})
    crash = _runner([], effect=lambda s, r: (_ for _ in ()).throw(RuntimeError("합성 실패")))
    assert _approve(other, admin, {"schedule_construction": crash})["status"] == "failed"


def test_blocked_run_reopens_with_the_wrapped_message(app):
    admin, order = _user(), _order("RECEIVED")
    row = _propose(order)
    blocked = RunOutcome.blocked("다른 사람이 먼저 시공일을 정했어요.")
    with pytest.raises(ActionError) as caught:
        _approve(row, admin, {"schedule_construction": _runner([], blocked)})
    assert caught.value.code == "ACTION_PRECONDITION" and caught.value.message == blocked.message
    db_session.expire_all()
    saved = db_session.get(ErpActionProposal, row.id)
    assert saved.status == "open" and saved.decided_by is None and saved.decided_action is None
    assert _audits("ERP_ACTION_FAILED")[0].detail["outcome"] == "blocked"


def test_link_mode_and_missing_runner_are_shape_errors(app, monkeypatch):
    admin = _user()
    _as_link(monkeypatch)
    link = _propose(_order("DRAWING"), action="assign_draftsman", proposed_by="agent:ops", params={}, level=1)
    with pytest.raises(ActionError) as shape:
        _approve(link, admin, {"assign_draftsman": _runner([])})
    assert shape.value.code == "ACTION_SHAPE" and shape.value.fields == ("action",)
    row = _propose(_order("RECEIVED"))
    with pytest.raises(ActionError) as missing:
        _approve(row, admin, {})
    assert missing.value.code == "ACTION_SHAPE"


def test_edits_and_change_reason(app):
    admin, order = _user(), _order("CONFIRM", construction=(_day(5), "오전"))
    row, calls = _propose(order, action="move_construction", proposed_by="agent:cs",
                          params={"date": _day(6), "time": "오전"}), []
    runners = {"move_construction": _runner(calls)}
    for kwargs, field in (({"edits": {"crew": 2}}, "edits"), ({"reason_code": "weather"}, "reason_code"),
                          ({"reason_code": "other"}, "reason_note"), ({"edits": {"time": "밤"}}, "time")):
        with pytest.raises(ActionError) as bad:
            _approve(row, admin, runners, **kwargs)
        assert bad.value.code == "ACTION_SHAPE" and field in bad.value.fields
    _approve(row, admin, runners, edits={"time": "오후"}, reason_code="customer_request")
    assert calls[0].params["time"] == "오후" and calls[0].reason_code == "customer_request"
    db_session.expire_all()
    saved = db_session.get(ErpActionProposal, row.id)
    assert saved.edited_params == {"time": "오후"} and saved.decided_action == "edit_approve"


def test_reject_and_snooze(app):
    admin = _user()
    row = _propose(_order("RECEIVED"))
    with pytest.raises(ActionError) as bad:
        reject(db_session, row.id, actor=admin, code="nope", now=NOW)
    assert bad.value.code == "ACTION_SHAPE"
    moment = datetime.datetime(2030, 3, 4, 3, 0)  # 한국 12:00 → 다음 날 06:00 한국 = 3/4 21:00 UTC
    snoozed = snooze(db_session, row.id, actor=admin, now=moment)
    assert snoozed.status == "open" and snoozed.snoozed_until == datetime.datetime(2030, 3, 4, 21, 0)
    rejected = reject(db_session, row.id, actor=admin, code="already_done", view_ms=900, now=NOW)
    db_session.commit()
    assert (rejected.status, rejected.reject_code, rejected.decided_action) == ("rejected", "already_done", "reject")
    with pytest.raises(ActionError) as again:
        snooze(db_session, row.id, actor=admin, now=NOW)
    assert again.value.code == "ACTION_NOT_OPEN"
    assert len(_audits("ERP_ACTION_SNOOZED")) == len(_audits("ERP_ACTION_REJECTED")) == 1


def test_expire_due_by_date_and_by_seven_days(app):
    dated = _propose(_order("RECEIVED"), params={"date": _day(2), "time": ""})
    later = _propose(_order("RECEIVED"), params={"date": _day(30), "time": ""})
    assert expire_due(db_session, NOW) == 0
    assert expire_due(db_session, NOW + datetime.timedelta(days=3)) == 1
    assert expire_due(db_session, NOW + datetime.timedelta(days=8)) == 1
    db_session.commit()
    assert {db_session.get(ErpActionProposal, r.id).status for r in (dated, later)} == {"expired"}


def test_reconcile_two_ways_and_link_close(app, monkeypatch):
    admin = _user()
    _as_link(monkeypatch)
    done_order, lost_order = _order("RECEIVED"), _order("RECEIVED")
    done, lost = _propose(done_order), _propose(lost_order, params={"date": _day(12), "time": "오후"})
    recent = _propose(_order("RECEIVED"), params={"date": _day(13), "time": ""})
    for row, when in ((done, NOW - datetime.timedelta(minutes=5)), (lost, NOW - datetime.timedelta(minutes=5)),
                      (recent, NOW)):
        row.status, row.decided_by, row.decided_at, row.decided_action = "executing", admin.id, when, "approve"
    done_order.structured_data = {**done_order.structured_data,
                                  "schedule": {"construction": {"date": done.params["date"], "time": "오전"}}}
    link_order = _order("DRAWING")
    link = _propose(link_order, action="assign_draftsman", proposed_by="agent:ops", params={}, level=1)
    link_order.structured_data = {**link_order.structured_data, "assignments": {"drawing_assignee_user_ids": [admin.id]}}
    db_session.commit()
    assert reconcile(db_session, NOW) == 3
    db_session.commit()
    db_session.expire_all()
    states = {r.id: db_session.get(ErpActionProposal, r.id) for r in (done, lost, recent, link)}
    assert (states[done.id].status, states[done.id].result) == ("executed", {"code": "RECONCILED"})
    assert states[lost.id].status == "open" and states[lost.id].decided_by is None
    assert states[recent.id].status == "executing"
    assert (states[link.id].status, states[link.id].decided_action) == ("executed", lifecycle.DECIDED_LINK)


def test_unknown_or_invisible_proposal_is_forbidden(app):
    viewer = _user("lc_viewer", role="VIEWER")
    row = _propose(_order("RECEIVED"))
    for target, actor in ((row.id + 99, _user("lc_admin2")), (row.id, viewer), ("1", viewer)):
        with pytest.raises(ActionError) as hidden:
            approve(db_session, target, actor=actor, runners={}, base_version=1, now=NOW)
        assert hidden.value.code == "ACTION_FORBIDDEN"


# ── 검수 R1 고침(R-01 · R-09 · R-10) ─────────────────────────────────────
def _levels(**agents: dict) -> None:
    """AI 직원 수준 표(ADMIN 이 고치는 SystemSetting 한 줄)를 합성 값으로."""
    row = db_session.get(SystemSetting, AI_LEVELS_KEY)
    if row is None:
        db_session.add(SystemSetting(setting_key=AI_LEVELS_KEY, setting_value=dict(agents)))
    else:
        row.setting_value = dict(agents)
    db_session.commit()


def test_reason_required_change_cannot_run_without_a_reason_code(app):
    """R-01 — 고객 컨펌 뒤 시공일 옮기기는 사유를 묻는 변경이다. 사유 코드 없이 승인하면 400 ``reason_code``, 실행기는 안 돈다."""
    admin, order = _user(), _order("CONFIRM", construction=(_day(5), "오전"))
    row, calls = _propose(order, action="move_construction", proposed_by="agent:cs",
                          params={"date": _day(7), "time": "오후"}), []
    runners = {"move_construction": _runner(calls)}
    for kwargs in ({}, {"reason_code": ""}, {"reason_code": None, "reason_note": "메모만"}):
        with pytest.raises(ActionError) as missing:
            _approve(row, admin, runners, **kwargs)
        assert (missing.value.code, missing.value.fields) == ("ACTION_SHAPE", ("reason_code",))
    db_session.expire_all()
    saved = db_session.get(ErpActionProposal, row.id)
    assert saved.status == "open" and saved.decided_by is None and not calls and _audits("ERP_ACTION_APPROVED") == []
    assert _approve(saved, admin, runners, reason_code="customer_request")["status"] == "executed"
    assert calls[0].reason_code == "customer_request"


def test_change_without_reason_question_still_runs_without_a_reason(app):
    """R-01 — 사유를 묻지 않는 변경(접수 단계 시공 잡기)은 지금처럼 사유 없이 실행된다."""
    admin, order = _user(), _order("RECEIVED")
    row, calls = _propose(order), []
    assert _approve(row, admin, {"schedule_construction": _runner(calls)})["status"] == "executed"
    assert calls[0].reason_code is None


def test_taken_lookup_filters_by_order_and_rides_the_order_status_index(app):
    """R-09 — 같은 열쇠 찾기에 주문 번호 조건이 있어 ``(order_id, status)`` 색인을 탄다(부분 유일 색인은 open 만 덮는다)."""
    first = _propose(_order("RECEIVED"))
    assert first.order_id and first.dedupe_key  # 커밋 뒤 다시 읽기를 듣기 전에 끝낸다
    seen: list[tuple] = []

    def grab(_conn, _cursor, statement, parameters, _context, _many):
        seen.append((statement, parameters))

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", grab)
    try:
        assert lifecycle._taken(db_session, first) is True
    finally:
        event.remove(engine, "before_cursor_execute", grab)
    statement, parameters = next(item for item in seen if "erp_action_proposals" in item[0])
    assert "erp_action_proposals.order_id = " in statement and "erp_action_proposals.dedupe_key = " in statement
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            plan = " ".join(str(r[-1]) for r in conn.exec_driver_sql("EXPLAIN QUERY PLAN " + statement, parameters))
        assert "ix_erp_action_proposals_order_status" in plan, plan


def test_level_zero_blocks_approve_of_an_open_proposal_until_raised(app):
    """R-10 — 수준을 0 으로 내리면 이미 열린 그 직원의 제안은 승인 · 실행되지 않는다(409 · 제안은 열린 채 · 거절은 된다)."""
    admin = _user()
    row, calls = _propose(_order("RECEIVED")), []
    runners = {"schedule_construction": _runner(calls)}
    _levels(schedule={"schedule_construction": 0})
    with pytest.raises(ActionError) as paused:
        _approve(row, admin, runners)
    assert (paused.value.code, paused.value.message) == ("ACTION_PRECONDITION", lifecycle.LEVEL_ZERO_REASON)
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, row.id).status == "open" and not calls
    _levels(schedule={"schedule_construction": 1})
    assert _approve(row, admin, runners)["status"] == "executed" and len(calls) == 1
    other = _propose(_order("RECEIVED"), params={"date": _day(14), "time": ""})
    _levels(schedule={"schedule_construction": 0})
    assert reject(db_session, other.id, actor=admin, code="other", now=NOW).status == "rejected"


def test_level_zero_also_blocks_the_shared_service_runner_path(app, monkeypatch):
    """R-10 — 채널톡 작은 창 [같이 넣기]가 타는 길(:func:`approve` + ``SERVICE_RUNNERS``)도 같이 막힌다 — 주문이 안 바뀐다."""
    from foms.services.erp_actions import runners as runner_mod

    monkeypatch.setattr(runner_mod, "finalize_note_notifications", lambda db, result: None)
    admin, order = _user(), _order("CONFIRM", construction=(_day(5), "오전"))
    row = _propose(order, action="add_construction_note", proposed_by="agent:cs", params={"note": "합성 자재 먼저"})
    _levels(cs={"add_construction_note": 0})
    with pytest.raises(ActionError) as paused:
        _approve(row, admin, runner_mod.SERVICE_RUNNERS)
    assert paused.value.message == lifecycle.LEVEL_ZERO_REASON
    db_session.expire_all()
    assert "notes" not in (db_session.get(Order, order.id).structured_data or {})
    assert db_session.get(ErpActionProposal, row.id).status == "open"
