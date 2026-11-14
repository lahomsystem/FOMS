"""상담 AI 접목 한 걸음(설계서 2026-11-14-foms-graft 3.9 · 3.11 · 7절) — 초안 두뇌 뒤 근거 남기기 · 규칙 제안 셋.

완료 기준: 관리 칸 둘이 끔이면 초안 길 · 차례 줄이 지금과 같고 표 쓰기 0 · 근거 남기기(겹침 한 번 · 주문 키) · 규칙 셋의 만들기와
안 만들기(주문 확인 안 됨 · 요일만 적힘 · 시공일이 지남 · 수준 0) · 실패해도 초안이 나감(로그 코드) · 로그에 손님 글 없음.
합성 글 · 합성 주문 · 가짜 채널톡 · 가짜 두뇌(네트워크 0). 날짜는 실행하는 날(한국 오늘) 기준으로 만든다(CI 는 UTC).
"""

from __future__ import annotations

import copy
import datetime
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainObject
from foms.persistence.graft.models import BrainUsageEvent, ErpActionProposal
from foms.services.cs_agent import graft_step
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.graft_settings import GRAFT_ACTIONS_FIELD, GRAFT_EVIDENCE_FIELD
from foms.services.cs_agent.onto_settings import ONTO_ORDER_FIELD
from foms.services.cs_agent.order_block import ORDER_RULES
from foms.services.cs_agent.order_step import ASK_TEXT
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import SystemSetting
from tests.domains.test_cs_drafting import CUSTOMER, DRAFT, FakeBrain, channel, customer, result, run, turn  # noqa: F401
from tests.domains.test_cs_order_lookup import NAME, PHONE, add_order, asked_before
from tests.support.cs_agent_fakes import at, keys  # noqa: F401 — keys 는 fixture

TODAY = get_today_kst()


def day(offset: int) -> datetime.date:
    return TODAY + datetime.timedelta(days=offset)


def said(when: datetime.date) -> str:
    """손님 글 꼴 'M월 D일'."""
    return f"{when.month}월 {when.day}일"


def switches(*, evidence=False, actions=False, order=True):
    value = {**st.DEFAULTS, ONTO_ORDER_FIELD: order, GRAFT_EVIDENCE_FIELD: evidence, GRAFT_ACTIONS_FIELD: actions}
    row = db_session.get(SystemSetting, st.SETTINGS_KEY)
    if row is None:
        db_session.add(SystemSetting(setting_key=st.SETTINGS_KEY, version=1, setting_value=value))
    else:
        row.setting_value = value
    db_session.commit()


def seed_order(stage="MEASURE", *, measurement=None, construction=None, time="오전"):
    """본인 확인으로 찾을 합성 주문 — 실측 · 시공 날은 오늘 기준(납작 칸은 구조화 칸에서 맞춘다)."""
    order = add_order(stage=stage, measurement=measurement.isoformat() if measurement else None)
    sd = copy.deepcopy(order.structured_data)
    sd["workflow"] = {"stage": stage}
    if measurement is None:
        sd["schedule"].pop("measurement", None)
    if construction is not None:
        sd["schedule"]["construction"] = {"date": construction.isoformat(), "time": time}
    order.structured_data = sd
    sync_erp_flat_columns(order, sd)
    order.erp_stage_code = stage
    db_session.commit()
    return order


def chat(channel, first, *, reply=f"{NAME} {PHONE}"):
    """손님 물음 → 직원(공개)이 성함 · 휴대폰을 물음 → 손님 답(그 답으로 두뇌 전에 주문을 찾는다)."""
    asked_before()
    customer(channel, text=first, when=at(2, 8, 20),
             more=[("m-ask", at(2, 8, 30), "manager", ASK_TEXT, {}), ("m-uc-1-2", at(2, 8, 50), "user", reply, {})])


def proposals():
    db_session.expire_all()
    return db_session.scalars(select(ErpActionProposal).order_by(ErpActionProposal.id)).all()


def uses():
    db_session.expire_all()
    return db_session.execute(select(BrainUsageEvent.item_key, BrainUsageEvent.reader, BrainUsageEvent.ref_kind,
                                     BrainUsageEvent.ref_id).order_by(BrainUsageEvent.id)).all()


def doc_item(key="common/shelf-depth", *, doc_id="shelf-depth", visibility="all", name="합성 선반 깊이"):
    """초안 근거 id 에 이어진 회사 지식 항목 한 줄(지금 판) — 반영 길을 타면 초안 시험의 지식 문서와 맞추기가 돌아 표에 바로 넣는다."""
    db_session.add(BrainObject(item_key=key, version=1, brand="COMMON", layer="common", item_type="fact", name=name,
                               text="합성 설명", status="active", visibility=visibility, confidence="confirmed",
                               created_by="import", payload={"doc_id": doc_id}))
    db_session.commit()
    return key


# ── 끔 = 지금 그대로 ──────────────────────────────────────────────────────
def test_both_switches_off_write_nothing_and_the_turn_is_unchanged(channel, monkeypatch):
    switches()
    seed_order("PRODUCTION", construction=day(10))
    chat(channel, f"{CUSTOMER} 문에서 끼익 소리가 나요. 시공을 {said(day(14))}로 미뤄 주세요")
    for name in ("record_uses", "propose", "doc_keys", "level_of"):
        monkeypatch.setattr(graft_step, name, lambda *a, **k: pytest.fail("끈 칸인데 접목 걸음이 돌았다"))
    brain_fn = FakeBrain(result(staff_note="일정 변경 요청"))
    run(channel, brain_fn=brain_fn)
    row = turn()
    assert (row.state, row.masked_draft, row.error_code) == ("stored", DRAFT, None)
    assert len(brain_fn.requests) == 1 and brain_fn.requests[0].order_lines  # 주문 확인은 지금 그대로 돈다
    assert uses() == [] and proposals() == []


def test_a_refused_answer_takes_no_step(channel, monkeypatch):
    switches(evidence=True, actions=True)
    monkeypatch.setattr(graft_step, "record_uses", lambda *a, **k: pytest.fail("거절된 답인데 근거를 남겼다"))
    graft_step.after_draft(SimpleNamespace(session=db_session), SimpleNamespace(id=1), SimpleNamespace(refused=True),
                           [])


# ── 근거 남기기 ──────────────────────────────────────────────────────────
def test_evidence_records_knowledge_and_the_confirmed_order_once(channel):
    switches(evidence=True)
    key = doc_item()
    order = seed_order("MEASURE", measurement=day(5))
    chat(channel, "선반 깊이 문의드려요")
    run(channel, brain_fn=FakeBrain(result(evidence_ids=("shelf-depth", "shelf-depth", "no-such-doc"))))
    row = turn()
    assert row.state == "stored"
    assert uses() == [(key, "cs_draft", "cs_turn", str(row.id)), (f"erp:order/{order.id}", "cs_draft", "cs_turn",
                                                                  str(row.id))]
    assert proposals() == []  # 할 일 칸은 꺼져 있다


def test_evidence_without_a_confirmed_order_keeps_only_knowledge(channel):
    switches(evidence=True, order=False)
    key = doc_item()
    customer(channel, text="선반 깊이 문의드려요")
    run(channel, brain_fn=FakeBrain(result()))
    assert [k for k, *_ in uses()] == [key]


# ── 규칙 셋 — 드는 길 ────────────────────────────────────────────────────
def test_as_words_on_a_cs_stage_order_propose_an_as_intake(channel):
    switches(actions=True)
    order = seed_order("CS")
    chat(channel, "설치한 문짝이 처졌어요")
    run(channel, brain_fn=FakeBrain(result()))
    (made,) = proposals()
    row = turn()
    assert (made.action, made.status, made.level, made.order_id) == ("register_as", "open", 2, order.id)
    assert (made.proposed_by, made.source_kind, made.source_ref) == ("agent:cs", "cs_turn", str(row.id))
    assert "처졌어요" in made.params["as_content"] and PHONE not in made.params["as_content"]
    assert [e["kind"] for e in made.evidence] == ["cs_turn", "order"]
    assert row.state == "stored"  # 초안은 그대로 나간다


def test_trouble_before_construction_proposes_a_note_for_the_small_window(channel):
    switches(actions=True)
    seed_order("PRODUCTION", construction=day(6))
    chat(channel, "문에서 끼익 소리가 나요")
    run(channel, brain_fn=FakeBrain(result()))
    (made,) = proposals()
    assert made.action == "add_construction_note"
    assert made.params == {"note": "채널톡 상담: 문에서 끼익 소리가 나요 — 시공 때 확인"}
    assert NAME not in made.params["note"] and PHONE not in made.params["note"]  # 성함 · 휴대폰 답 글은 싣지 않는다


def test_a_schedule_request_with_a_written_date_moves_the_measurement(channel):
    switches(actions=True)
    seed_order("MEASURE", measurement=day(5))
    chat(channel, f"실측을 {said(day(12))}로 바꾸고 싶어요")
    run(channel, brain_fn=FakeBrain(result(staff_note="일정 변경 요청 — 손님이 원하는 날")))
    (made,) = proposals()
    assert (made.action, made.params) == ("move_measurement", {"date": day(12).isoformat()})
    assert made.preview[0]["field"] == "실측 날짜"


def test_a_schedule_handoff_moves_the_construction_and_keeps_its_time_slot(channel):
    switches(actions=True)
    seed_order("PRODUCTION", construction=day(7), time="오후")
    chat(channel, f"시공 날짜를 {said(day(7))}에서 {said(day(15))}로 미뤄 주세요")
    run(channel, brain_fn=FakeBrain(result(draft="", evidence_ids=(), handoff=True, handoff_reason="schedule")))
    (made,) = proposals()
    assert (made.action, made.params) == ("move_construction", {"date": day(15).isoformat(), "time": "오후"})
    assert turn().error_code == "handoff"  # 넘김은 지금처럼 건너뜀 — 제안만 승인 대기로 간다


# ── 규칙 셋 — 안 드는 길 ─────────────────────────────────────────────────
def test_no_confirmed_order_means_no_proposal(channel):
    switches(actions=True, order=False)
    seed_order("PRODUCTION", construction=day(6))
    customer(channel, text=f"{NAME} {PHONE} 문에서 끼익 소리가 나요")
    run(channel, brain_fn=FakeBrain(result()))
    assert proposals() == []


@pytest.mark.parametrize("text", ["실측을 다음 주 금요일로 바꾸고 싶어요", "실측을 25일로 바꾸고 싶어요"])
def test_a_weekday_or_a_bare_day_makes_no_move(channel, text):
    switches(actions=True)
    seed_order("MEASURE", measurement=day(5))
    chat(channel, text)
    run(channel, brain_fn=FakeBrain(result(staff_note="일정 변경 요청")))
    assert proposals() == []


def test_a_past_construction_date_makes_no_note_and_no_move(channel):
    switches(actions=True)
    seed_order("PRODUCTION", construction=day(-1))
    chat(channel, f"문에서 끼익 소리가 나요. 시공을 {said(day(9))}로 바꿔 주세요")
    run(channel, brain_fn=FakeBrain(result(staff_note="일정 변경 요청")))
    assert proposals() == []


def test_level_zero_makes_no_proposal(channel):
    switches(actions=True)
    db_session.add(SystemSetting(setting_key="ai_staff_levels", setting_value={"cs": {"add_construction_note": 0}}))
    db_session.commit()
    seed_order("PRODUCTION", construction=day(6))
    chat(channel, "문에서 끼익 소리가 나요")
    run(channel, brain_fn=FakeBrain(result()))
    assert proposals() == []


# ── 실패 · 로그 ──────────────────────────────────────────────────────────
def test_a_failing_step_leaves_the_draft_and_logs_only_a_code(channel, monkeypatch, caplog):
    switches(evidence=True, actions=True)
    seed_order("PRODUCTION", construction=day(6))
    chat(channel, f"{CUSTOMER} 문에서 끼익 소리가 나요")

    def broken(*_a, **_k):
        raise RuntimeError(f"{CUSTOMER} 예외 글")

    monkeypatch.setattr(graft_step, "propose", broken)
    caplog.set_level(logging.DEBUG, logger="foms")
    run(channel, brain_fn=FakeBrain(result()))
    row = turn()
    assert (row.state, row.masked_draft) == ("stored", DRAFT)  # 초안 길은 그대로
    assert [k for k, *_ in uses()] and proposals() == []  # 근거 걸음은 따로 저장점이라 남는다
    assert "[CS 접목] 걸음 건너뜀" in caplog.text and "code=RuntimeError" in caplog.text
    assert CUSTOMER not in caplog.text and "끼익" not in caplog.text


def test_a_failing_rule_read_also_leaves_the_draft(channel, monkeypatch, caplog):
    switches(actions=True)
    seed_order("PRODUCTION", construction=day(6))
    chat(channel, "문에서 끼익 소리가 나요")
    monkeypatch.setattr(graft_step, "plans", lambda *a, **k: 1 / 0)
    caplog.set_level(logging.WARNING, logger="foms")
    run(channel, brain_fn=FakeBrain(result()))
    assert (turn().state, turn().masked_draft) == ("stored", DRAFT) and proposals() == []
    assert "step=proposals code=ZeroDivisionError" in caplog.text


def test_logs_carry_no_customer_text_when_proposals_are_made(channel, caplog):
    switches(evidence=True, actions=True)
    seed_order("PRODUCTION", construction=day(6))
    chat(channel, f"{CUSTOMER} 문에서 끼익 소리가 나요. 시공을 {said(day(13))}로 미뤄 주세요")
    caplog.set_level(logging.DEBUG, logger="foms")
    run(channel, brain_fn=FakeBrain(result(staff_note="일정 변경 요청")))
    assert sorted(p.action for p in proposals()) == ["add_construction_note", "move_construction"]
    for secret in (CUSTOMER, "끼익", NAME, PHONE, said(day(13))):
        assert secret not in caplog.text, secret
    assert "[CS 접목] 제안 만듦" in caplog.text


# ── 순수 규칙 ────────────────────────────────────────────────────────────
def test_written_dates_need_a_month_and_a_day():
    today = datetime.date(2026, 12, 20)
    texts = ["1월 5일로 바꿔 주세요", "12월 25일 가능해요?", "2027년 1월 7일도 돼요", "2월 30일", "12월 10일은 지났죠",
             "다음 주 금요일", "25일", "치수 1200 x 600"]
    assert graft_step.asked_days(texts, today) == [datetime.date(2026, 12, 25), datetime.date(2027, 1, 5),
                                                   datetime.date(2027, 1, 7)]
    assert graft_step.asked_days(["다음 주 금요일로요"], today) == []


def test_the_schedule_marker_is_the_one_the_order_block_asks_for():
    assert any(graft_step.SCHEDULE_NOTE in rule and "staff_note" in rule for rule in ORDER_RULES)


def test_rules_read_the_stage_and_the_dates_of_the_order():
    def order(stage, measurement=None, construction=None):
        schedule = {k: {"date": v.isoformat()} for k, v in (("measurement", measurement),
                                                            ("construction", construction)) if v}
        return SimpleNamespace(id=7, erp_stage_code=stage, erp_measurement_date=None, erp_construction_date=None,
                               structured_data={"schedule": schedule})

    plain = result()
    as_text = ["손잡이가 고장 났어요"]
    assert [p.action for p in graft_step.plans(plain, order("COMPLETED"), as_text, TODAY)] == ["register_as"]
    assert graft_step.plans(plain, order("MEASURE", measurement=day(3)), as_text, TODAY) == []  # 끝난 단계가 아님
    complaint = result(handoff=True, handoff_reason="complaint", draft="", evidence_ids=())
    note = graft_step.plans(complaint, order("PRODUCTION", construction=day(4)), ["배송 기사님이 불친절했어요"], TODAY)
    assert [p.action for p in note] == ["add_construction_note"]  # 불만으로 넘긴 글도 '불편 뜻'
    both = order("MEASURE", measurement=day(3), construction=day(20))
    ask = result(staff_note="일정 변경 요청")
    assert graft_step.plans(ask, both, [f"설치를 {said(day(25))}로 해 주세요"], TODAY)[0].action == "move_construction"
    assert graft_step.plans(ask, both, [f"{said(day(8))}로 바꿔 주세요"], TODAY)[0].action == "move_measurement"
    two = [f"{said(day(8))}이나 {said(day(9))}로 바꿔 주세요"]
    assert graft_step.plans(ask, both, two, TODAY) == []  # 날이 둘이면 어느 날인지 모른다
    assert graft_step.plans(result(), both, [f"{said(day(8))}로 바꿔 주세요"], TODAY) == []  # 일정 바꾸기 요청이 아님
