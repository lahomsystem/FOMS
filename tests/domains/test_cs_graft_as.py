"""상담 AI 접목 AS 빈 곳 둘(사용자 결정 D235 · D224 · 점검 2차 w6-06 · w6-07).

완료 기준:
- 방문 옮기기(AS): 본인이 확인된 주문에 **열린 AS(접수 · 진행) 방문일이 앞날**이고 손님이 그 날을 바꾸자고 하면(넘김 까닭 일정 ·
  직원 참고 '일정 변경') ``schedule_as_visit`` 제안 하나 — 실측 · 시공 옮기기와 같은 조심(날짜를 못 읽으면 · 날이 둘이면 · 지난
  날 · 지금 날과 같은 날이면 안 만든다, 열린 AS 가 없거나 방문일이 지났으면 안 만든다). AS 방문이 앞날이 아니면 예전 답 그대로.
  AI 직원 수준 표(상담 AI 할 일)에 들어 있고 처음 수준 2.
- AS 접수: 무상 AS = 시공일로부터 1년(D224). 제안 이유 · 승인 창 바뀌는 칸에 '무상 기간 안 · 지남(시공일 YYYY-MM-DD)' · '시공일이
  없어 무상 기간을 몰라요'. 지남 · 모름이면 무상 · 유상 칸은 '미정'(사람이 정한다) — 접수 본체에 넘길 값 :func:`billing_for_register`.
  경계: 1년 되는 날까지 안, 다음 날부터 지남, 2월 29일 시공은 다음 해 2월 28일까지.
합성 글 · 합성 주문 · 가짜 채널톡 · 가짜 두뇌(네트워크 0).
"""

from __future__ import annotations

import copy
import datetime
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.ai_staff import registry as staff
from foms.services.cs_agent import graft_step
from foms.services.erp_actions import as_warranty, preview
from foms.services.erp_sync_columns import sync_erp_flat_columns
from tests.domains.test_cs_drafting import FakeBrain, channel, result, run, turn  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_graft_step import (  # noqa: F401 — graft_env_off 는 바깥 env 끄기 fixture
    TODAY, chat, day, graft_env_off, proposals, said, seed_order, switches,
)
from tests.support.cs_agent_fakes import keys  # noqa: F401 — keys 는 fixture

ASK = result(staff_note="일정 변경 요청")
MOVES = ("move_measurement", "move_construction", "schedule_as_visit")


def _moves(answer, order, text):
    """규칙 ③(옮기기)이 만든 계획만 — AS 낱말이 든 글은 규칙 ① · ②(AS 접수 · 시공 메모)도 계획을 낸다(막는 조건은 아직 안 봤다)."""
    return [plan for plan in graft_step.plans(answer, order, [text], TODAY) if plan.action in MOVES]


def _cycle(status: str = "RECEIVED") -> dict:
    return {"current_cycle_id": "c1", "cycles": [{"cycle_id": "c1", "transitions": [
        {"seq": 1, "command": "AS_REGISTER", "from": "NONE", "to": status, "payload": {}, "at": "2030-01-01T00:00:00"}]}]}


def _plain(stage="COMPLETED", *, visit=None, as_status="RECEIVED", construction=None, measurement=None):
    """규칙만 보는 합성 주문(DB 없음)."""
    schedule = {k: {"date": v.isoformat()} for k, v in (("measurement", measurement), ("construction", construction),
                                                        ("as_visit", visit)) if v}
    sd = {"schedule": schedule, **({"as_lifecycle": _cycle(as_status)} if as_status else {})}
    return SimpleNamespace(id=7, erp_stage_code=stage, erp_measurement_date=None, erp_construction_date=None,
                           status=stage, structured_data=sd)


# ── 방문 옮기기(AS) — 규칙 ───────────────────────────────────────────────
def test_an_open_as_visit_moves_to_the_written_day():
    order = _plain(visit=day(5))
    (plan,) = _moves(ASK, order, f"AS 방문 날을 {said(day(9))}로 바꿔 주세요")
    assert (plan.action, plan.params) == ("schedule_as_visit", {"date": day(9).isoformat()})
    assert "AS 방문 날을" in plan.reason and "손님" in plan.reason
    (bare,) = graft_step.plans(ASK, order, [f"방문 날짜를 {said(day(9))}로 바꿔 주세요"], TODAY)  # 앞날이 AS 방문뿐
    assert bare.action == "schedule_as_visit"


@pytest.mark.parametrize("case, order, text", [
    ("no_open_as", _plain(visit=day(5), as_status=None), "AS 방문 날을 {d9}로 바꿔 주세요"),
    ("as_done", _plain(visit=day(5), as_status="COMPLETED"), "AS 방문 날을 {d9}로 바꿔 주세요"),
    ("visit_past", _plain(visit=day(-1)), "AS 방문 날을 {d9}로 바꿔 주세요"),
    ("no_visit", _plain(), "AS 방문 날을 {d9}로 바꿔 주세요"),
    ("same_day", _plain(visit=day(9)), "AS 방문 날을 {d9}로 바꿔 주세요"),
    ("two_days", _plain(visit=day(5)), "AS 방문 날을 {d9}이나 {d10}로 바꿔 주세요"),
    ("weekday", _plain(visit=day(5)), "AS 방문 날을 다음 주 금요일로 바꿔 주세요"),
    ("past_day", _plain(visit=day(5)), "AS 방문 날을 {dm2}로 바꿔 주세요"),
])
def test_no_as_move_without_an_open_visit_ahead_or_a_clear_day(case, order, text):
    words = text.format(d9=said(day(9)), d10=said(day(10)), dm2=said(day(-2)))
    assert _moves(ASK, order, words) == [], case


def test_no_schedule_ask_means_no_as_move():
    assert _moves(result(), _plain(visit=day(5)), f"AS 방문 날을 {said(day(9))}로 바꿔 주세요") == []


def test_measurement_and_construction_answers_stay_as_before():
    """AS 방문이 앞날이 아니면 예전 답 그대로 · 실측이나 앞날 시공을 말하면 그쪽이 먼저(대조군)."""
    plain = _plain("MEASURE", as_status=None, measurement=day(3))
    assert [p.action for p in _moves(ASK, plain, f"수리 날짜 {said(day(8))}로 바꿔 주세요")] == ["move_measurement"]
    both = _plain("PRODUCTION", visit=day(4), construction=day(20))
    assert [p.action for p in _moves(ASK, both, f"설치를 {said(day(25))}로 해 주세요")] == ["move_construction"]
    assert [p.action for p in _moves(ASK, both, f"AS 기사님 {said(day(6))}로 와 주세요")] == ["schedule_as_visit"]
    measure = _plain("MEASURE", visit=day(4), measurement=day(3))
    assert [p.action for p in _moves(ASK, measure, f"실측 AS {said(day(6))}로요")] == ["move_measurement"]


def test_the_cs_agent_has_the_as_move_duty(app):
    assert staff.AGENTS["cs"].duty("schedule_as_visit").level == 2
    assert staff.level_of(db_session, "cs", "schedule_as_visit") == 2


def _seed_as(visit: datetime.date):
    """본인 확인으로 찾을 끝난 주문 + 열린 AS 방문일."""
    order = seed_order("COMPLETED", construction=day(-200))
    sd = copy.deepcopy(order.structured_data)
    sd["as_lifecycle"] = _cycle()
    sd["schedule"]["as_visit"] = {"date": visit.isoformat(), "time": "", "type": "AS"}
    order.structured_data = sd
    sync_erp_flat_columns(order, sd)
    order.erp_stage_code = "COMPLETED"
    db_session.commit()
    return order


def test_a_chat_asking_to_move_the_as_visit_makes_one_proposal(channel):
    switches(actions=True)
    order = _seed_as(day(5))
    chat(channel, f"AS 방문 날을 {said(day(12))}로 바꾸고 싶어요")
    run(channel, brain_fn=FakeBrain(result(staff_note="일정 변경 요청 — 손님이 원하는 날")))
    (made,) = proposals()  # AS 접수 제안은 '이미 열린 AS' 막는 조건에 걸려 생기지 않는다
    assert (made.action, made.params, made.order_id, made.level) == ("schedule_as_visit", {"date": day(12).isoformat()},
                                                                    order.id, 2)
    assert made.preview[0]["field"] == "AS 방문 날짜" and turn().state == "stored"


# ── 무상 AS 기간 — 1년(D224) ─────────────────────────────────────────────
def _built(on: str | None):
    return SimpleNamespace(structured_data={"schedule": {"construction": {"date": on}}} if on else {},
                           erp_construction_date=None)


@pytest.mark.parametrize("built, today, verdict", [
    ("2025-03-10", "2026-03-10", "in"),  # 딱 1년 되는 날까지 안
    ("2025-03-10", "2026-03-11", "over"),  # 다음 날부터 지남
    ("2025-03-10", "2025-03-10", "in"),
    ("2024-02-29", "2025-02-28", "in"),  # 2월 29일 시공 → 다음 해 2월 28일까지
    ("2024-02-29", "2025-03-01", "over"),
    ("2025-01-02, 2025-03-10", "2026-03-10", "in"),  # 여러 날이면 마지막 날
    (None, "2026-03-10", "unknown"),
])
def test_the_one_year_boundary(built, today, verdict):
    order = _built(built)
    assert as_warranty.state(order, datetime.date.fromisoformat(today))[0] == verdict
    assert as_warranty.billing_for_register(order, datetime.date.fromisoformat(today)) == (
        "free" if verdict == "in" else "undecided")
    assert as_warranty.FREE_AS_YEARS == 1


def test_labels_name_the_construction_day():
    today = datetime.date(2026, 3, 11)
    assert as_warranty.label(_built("2025-03-10"), today) == "무상 기간 지남(시공일 2025-03-10)"
    assert as_warranty.label(_built("2025-09-01"), today) == "무상 기간 안(시공일 2025-09-01)"
    assert as_warranty.label(_built(None), today) == "시공일이 없어 무상 기간을 몰라요"


@pytest.mark.parametrize("built, phrase, after", [
    (-400, "무상 기간 지남(시공일 {d})", "미정 — 무상 · 유상은 사람이 정해요"),
    (-30, "무상 기간 안(시공일 {d})", "무상 추정(확정 전)"),
    (None, "시공일이 없어 무상 기간을 몰라요", "미정 — 무상 · 유상은 사람이 정해요"),
])
def test_the_intake_reason_and_the_approve_window_show_the_free_period(built, phrase, after):
    on = day(built).isoformat() if built is not None else None
    order = SimpleNamespace(id=7, erp_stage_code="COMPLETED", erp_measurement_date=None, erp_construction_date=None,
                            status="COMPLETED", structured_data={"schedule": {"construction": {"date": on}}} if on else {})
    (plan,) = graft_step.plans(result(), order, ["손잡이가 고장 났어요"], TODAY)
    text = phrase.format(d=on)
    assert plan.action == "register_as" and text in plan.reason
    assert ("무상 · 유상은 사람이 정해요" in plan.reason) is (after != "무상 추정(확정 전)")
    rows = preview.preview("register_as", order, plan.params)
    assert rows[0]["field"] == "AS 건" and rows[1] == {"field": "무상 AS", "before": text, "after": after}


def test_an_old_order_intake_through_the_chat_keeps_the_free_period_words(channel):
    switches(actions=True)
    seed_order("CS", construction=day(-500))
    chat(channel, "설치한 문짝이 처졌어요")
    run(channel, brain_fn=FakeBrain(result()))
    (made,) = proposals()
    assert made.action == "register_as" and f"무상 기간 지남(시공일 {day(-500).isoformat()})" in made.reason
    assert made.preview[1]["before"] == f"무상 기간 지남(시공일 {day(-500).isoformat()})"
