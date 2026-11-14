"""운영 AI · 일정 AI 훑기 규칙(설계서 2026-11-14-foms-graft 3.10 · D207 · D214) + 밤 단계 두 줄.

완료 기준:
- 규칙마다 만들기와 안 만들기 — S1(시공일 이미 있음 · 요청 닫힘 · 지난 날짜) · O1(알림톡 기록 있음 · 직접 실측 · 협력사 · 모레) ·
  O2(처음 수준 0 · 작업 미승인 · 2일 안 · 도면 단계) · O3(담당 있음 · 2일 안).
- 수준 0 이면 그 직원 제안 0 · 날짜는 한국 오늘 기준 · 한 번에 상한까지 · 다시 돌려도 겹치지 않음 · 실행 기록(단계 · 시간 · 수 ·
  제안 출처 번호).
- 스위치 끔 → 0 개 · 읽기 · 쓰기 없음 · 단계 exit 0. 훑기는 알림톡을 보내지 않는다(보내는 함수가 불리면 실패).
- 밤 단계: NIGHTLY_STEPS 에 기간 끝남 닫기 → 훑기 차례로 ``--apply`` · 스크립트 파일 있음 · 기간 끝남 닫기 커밋 · 시험 돌리기 되돌림.
합성 주문 · 합성 협력사만. 바깥 호출 없음.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.persistence.graft.models import AiAgentRun, ErpActionProposal
from foms.services import kakao_alimtalk
from foms.services.ai_staff import registry, sweeps
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import preview
from foms.services.erp_actions.lifecycle import propose
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import Order, PartnerOrg, SystemSetting
from tools.cron import ai_staff_sweep, erp_actions_expire
from tools.cron.nightly import NIGHTLY_STEPS, REPO_ROOT

TODAY = get_today_kst()


def _day(offset: int, base: datetime.date = TODAY) -> str:
    return (base + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture
def proposers(app, monkeypatch):
    """접목판 스위치를 모두 끈 뒤 훑기만 켠다. 알림톡은 보내면 실패, 발송 자격은 통과로 둔다(제안만 보므로)."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    monkeypatch.setenv("FOMS_GRAFT_PROPOSERS_ENABLED", "1")

    def _never(*_args, **_kwargs):
        pytest.fail("훑기는 알림톡을 보내지 않는다")

    monkeypatch.setattr(kakao_alimtalk, "_solapi_send", _never)
    monkeypatch.setattr(kakao_alimtalk, "send_alimtalk", _never)
    monkeypatch.setattr(preview, "_ineligible_reason", lambda order, sd: None)
    return monkeypatch


def _levels(value: dict) -> None:
    db_session.add(SystemSetting(setting_key=registry.SETTINGS_KEY, setting_value=value))
    db_session.commit()


def _order(stage: str, *, partner: bool = False, self_measure: bool = False, stage_days: float = 0, **sd_extra) -> Order:
    sd = {"workflow": {"stage": stage,
                       "stage_updated_at": (now_utc_naive() - datetime.timedelta(days=stage_days)).isoformat()},
          **sd_extra}
    org_id = None
    if partner:
        org = PartnerOrg(name=f"합성 협력사 {db_session.query(PartnerOrg).count() + 1}")
        db_session.add(org)
        db_session.flush()
        org_id = org.id
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd, partner_org_id=org_id,
                  is_self_measurement=self_measure)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _made(action: str) -> set[int]:
    return {row.order_id for row in db_session.query(ErpActionProposal).filter(ErpActionProposal.action == action)}


def _sweep(**kw) -> sweeps.SweepResult:
    result = sweeps.run_sweep(db_session, **kw)
    db_session.commit()
    return result


# ── S1 일정 ──────────────────────────────────────────────────────────────
def test_s1_partner_wish_date_becomes_a_schedule_proposal(proposers):
    wish = {"partner_intake": {"requested_construction": {"date": _day(5), "time": "오후"}}}
    yes = _order("PRODUCTION", partner=True, **wish)
    free_time = _order("PRODUCTION", partner=True,
                       partner_intake={"requested_construction": {"date": _day(6), "time": "10:30"}})
    has_date = _order("PRODUCTION", partner=True, schedule={"construction": {"date": _day(3)}}, **wish)
    closed = _order("CONSTRUCTION", partner=True, **wish)
    past = _order("PRODUCTION", partner=True, partner_intake={"requested_construction": {"date": _day(-1)}})
    ours = _order("PRODUCTION", **wish)  # 우리 주문 — 협력사 희망 시공일 규칙 밖
    result = _sweep()
    assert result.enabled is True and result.by_rule["S1"] == 2
    assert _made("schedule_construction") == {yes.id, free_time.id}
    assert not {has_date.id, closed.id, past.id, ours.id} & _made("schedule_construction")
    row = db_session.query(ErpActionProposal).filter(ErpActionProposal.order_id == yes.id).one()
    assert row.params == {"date": _day(5), "time": "오후"} and row.proposed_by == "agent:schedule" and row.level == 2
    assert row.source_kind == "sweep" and row.evidence == [{"kind": "order", "ref": f"erp:order/{yes.id}",
                                                            "label": f"주문 #{yes.id}"}]
    assert "합성손님" not in (row.reason or "")
    other = db_session.query(ErpActionProposal).filter(ErpActionProposal.order_id == free_time.id).one()
    assert other.params["time"] == ""  # 정한 넷이 아닌 시간대는 '정하지 않음'


# ── O1 실측 예약 알림톡 ──────────────────────────────────────────────────
def test_o1_tomorrow_measure_without_alimtalk_record(proposers):
    tomorrow = {"schedule": {"measurement": {"date": _day(1)}}}
    yes = _order("MEASURE", **tomorrow)
    sent = _order("MEASURE", alimtalk_measurement={"sent_at": "2030-01-01T00:00:00", "message_id": "m1"}, **tomorrow)
    self_measure = _order("MEASURE", self_measure=True, **tomorrow)
    partner = _order("MEASURE", partner=True, **tomorrow)
    later = _order("MEASURE", schedule={"measurement": {"date": _day(2)}})
    result = _sweep()
    assert result.by_rule["O1"] == 1 and _made("send_measure_alimtalk") == {yes.id}
    assert not {sent.id, self_measure.id, partner.id, later.id} & _made("send_measure_alimtalk")
    row = db_session.query(ErpActionProposal).filter(ErpActionProposal.action == "send_measure_alimtalk").one()
    assert row.proposed_by == "agent:ops" and row.level == 1 and row.status == "open"


def test_dates_follow_the_korean_today(proposers):
    """오늘은 한국 날짜(get_today_kst) — 그 다음 날 실측만 '내일'이다."""
    korean_today = TODAY + datetime.timedelta(days=10)
    proposers.setattr(sweeps, "get_today_kst", lambda: korean_today)
    hit = _order("MEASURE", schedule={"measurement": {"date": _day(1, korean_today)}})
    miss = _order("MEASURE", schedule={"measurement": {"date": _day(1)}})
    _sweep()
    assert _made("send_measure_alimtalk") == {hit.id} and miss.id not in _made("send_measure_alimtalk")
    ctx = sweeps.SweepContext(now=datetime.datetime(2030, 1, 1, 16, 0), today=datetime.date(2030, 1, 2))
    assert ctx.tomorrow == "2030-01-03"  # UTC 로는 1월 1일 16시지만 한국은 1월 2일


# ── O2 단계 넘기기(처음 수준 0) ───────────────────────────────────────────
def _quest(stage: str, status: str) -> dict:
    return {"quests": [{"stage": stage, "status": status, "team_approvals": {}}]}


def test_o2_starts_at_level_zero_then_proposes_when_raised(proposers):
    stuck = _order("MEASURE", stage_days=3, **_quest("MEASURE", "COMPLETED"))
    assert registry.level_of(db_session, "ops", "advance_stage") == 0
    _sweep()
    assert _made("advance_stage") == set()  # D214 — 처음엔 만들지 않는다

    _levels({"ops": {"advance_stage": 1}})
    open_quest = _order("MEASURE", stage_days=3, **_quest("MEASURE", "OPEN"))
    fresh = _order("MEASURE", stage_days=1, **_quest("MEASURE", "COMPLETED"))
    drawing = _order("DRAWING", stage_days=3, **_quest("DRAWING", "COMPLETED"))
    confirm_blocked = _order("CONFIRM", stage_days=3, **_quest("CONFIRM", "COMPLETED"))  # 도면 수령 확정 전
    confirm_ok = _order("CONFIRM", stage_days=3, drawing={"status": "CONFIRMED"}, **_quest("CONFIRM", "COMPLETED"))
    result = _sweep()
    assert result.by_rule["O2"] == 2 and _made("advance_stage") == {stuck.id, confirm_ok.id}
    assert not {open_quest.id, fresh.id, drawing.id, confirm_blocked.id} & _made("advance_stage")


# ── O3 도면 담당 ────────────────────────────────────────────────────────
def test_o3_drawing_without_draftsman_for_two_days(proposers):
    yes = _order("DRAWING", stage_days=3)
    has = _order("DRAWING", stage_days=3, assignments={"drawing_assignee_user_ids": [7]})
    fresh = _order("DRAWING", stage_days=1)
    result = _sweep()
    assert result.by_rule["O3"] == 1 and _made("assign_draftsman") == {yes.id}
    assert not {has.id, fresh.id} & _made("assign_draftsman")
    row = db_session.query(ErpActionProposal).filter(ErpActionProposal.action == "assign_draftsman").one()
    assert row.params == {"user_ids": []}  # 담당 칸은 비워 둔다 — 승인자가 고른다(T14 꼴 users)


# ── 수준 · 상한 · 겹침 · 실행 기록 ──────────────────────────────────────
def test_level_zero_agent_makes_nothing(proposers):
    _levels({"schedule": {"schedule_construction": 0}, "ops": {"send_measure_alimtalk": 0, "assign_draftsman": 0}})
    _order("PRODUCTION", partner=True, partner_intake={"requested_construction": {"date": _day(5)}})
    _order("MEASURE", schedule={"measurement": {"date": _day(1)}})
    _order("DRAWING", stage_days=3)
    result = _sweep()
    assert result.created == 0 and db_session.query(ErpActionProposal).count() == 0
    runs = {run.agent: run for run in db_session.query(AiAgentRun)}
    assert set(runs) == {"ops", "schedule"} and {run.outcome for run in runs.values()} == {"level_zero"}
    assert all(step["detail"] == "수준 0 — 제안 안 만듦" for run in runs.values() for step in run.steps)


def test_cap_rerun_and_run_records(proposers):
    for _ in range(3):
        _order("DRAWING", stage_days=3)
    first = _sweep(limit=2)
    assert first.created == 2 and len(_made("assign_draftsman")) == 2
    again = _sweep()
    assert again.created == 1  # 남은 하나만 — 이미 열린 제안은 다시 만들지 않는다
    assert _sweep().created == 0
    ops_runs = db_session.query(AiAgentRun).filter(AiAgentRun.agent == "ops").order_by(AiAgentRun.id).all()
    assert [run.proposals for run in ops_runs] == [2, 1, 0]
    steps = ops_runs[0].steps
    assert {step["tool"] for step in steps} >= {"erp.order.list", "actions.propose"}
    assert all(isinstance(step["ms"], int) and step["ms"] >= 0 for step in steps)
    assert ops_runs[0].total_ms is not None and ops_runs[0].source_kind == "sweep"
    sources = {row.source_ref for row in db_session.query(ErpActionProposal)}
    assert sources <= {str(run.id) for run in ops_runs}


def test_rules_table_names_agents_and_actions():
    assert list(sweeps.RULES) == ["S1", "O1", "O2", "O3"]
    for rule in sweeps.RULES.values():
        assert rule.agent in registry.AGENTS and registry.AGENTS[rule.agent].duty(rule.action) is not None
        assert rule.tool in registry.TOOLS
    assert sweeps.MAX_PROPOSALS == 30
    assert registry.AGENTS["ops"].duty("advance_stage").level == 0


# ── 스위치 끔 ────────────────────────────────────────────────────────────
def test_switch_off_creates_nothing_and_the_step_exits_zero(proposers, monkeypatch):
    monkeypatch.delenv("FOMS_GRAFT_PROPOSERS_ENABLED", raising=False)
    _order("DRAWING", stage_days=3)
    _order("MEASURE", schedule={"measurement": {"date": _day(1)}})

    def _no_query(*_args, **_kwargs):
        pytest.fail("스위치가 꺼지면 후보를 읽지 않는다")

    monkeypatch.setattr(sweeps, "_orders", _no_query)
    result = sweeps.run_sweep(db_session)
    assert result.enabled is False and result.created == 0 and result.runs == []
    assert db_session.query(ErpActionProposal).count() == 0 and db_session.query(AiAgentRun).count() == 0
    assert ai_staff_sweep.run(apply=True, session=db_session)["enabled"] is False
    monkeypatch.setattr(ai_staff_sweep, "_make_session", _no_query)
    assert ai_staff_sweep.main(["--apply"]) == 0


def test_sweep_step_dry_run_rolls_back_and_apply_commits(proposers):
    order = _order("DRAWING", stage_days=3)
    order_id = order.id
    assert ai_staff_sweep.run(apply=False, session=db_session)["created"] == 1
    assert db_session.query(ErpActionProposal).count() == 0
    summary = ai_staff_sweep.run(apply=True, session=db_session)
    assert summary == {"enabled": True, "created": 1, "by_rule": {"O1": 0, "O2": 0, "O3": 1, "S1": 0},
                       "applied": True}
    assert _made("assign_draftsman") == {order_id}


# ── 밤 단계 ──────────────────────────────────────────────────────────────
def test_nightly_steps_wire_expire_then_sweep_with_apply():
    names = [step.name for step in NIGHTLY_STEPS]
    assert names.index("erp_actions_expire") < names.index("ai_staff_sweep")
    for name, script in (("erp_actions_expire", "tools/cron/erp_actions_expire.py"),
                         ("ai_staff_sweep", "tools/cron/ai_staff_sweep.py")):
        step = next(s for s in NIGHTLY_STEPS if s.name == name)
        assert step.script == script and step.args == ("--apply",) and (REPO_ROOT / script).is_file()


def test_expire_step_closes_due_proposals(proposers):
    order = _order("DRAWING", stage_days=3)
    row = propose(db_session, action="assign_draftsman", proposed_by="agent:ops", order=order, params={},
                  reason="합성 이유", evidence=[], source_kind="sweep", source_ref="1", level=1,
                  now=now_utc_naive() - datetime.timedelta(days=8))
    db_session.commit()
    row_id = row.id
    assert erp_actions_expire.run(apply=False, session=db_session)["expired"] == 1
    assert db_session.get(ErpActionProposal, row_id).status == "open"  # 시험 돌리기는 되돌린다
    summary = erp_actions_expire.run(apply=True, session=db_session)
    assert summary["expired"] == 1 and summary["applied"] is True
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, row_id).status == "expired"
