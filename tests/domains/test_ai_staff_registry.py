"""AI 직원 목록 · 수준 읽기(설계서 2026-11-14-foms-graft 3.10).

완료 기준: 직원 다섯 · 도구 이름이 한 표 · 처음 수준 ≤ 할 일 수준 상한 · 수준 3 없음 · 할 일 열쇠가 할 일 목록 이름이면 ``human``
아님 · 제안자 이름 ``agent:<열쇠>`` 왕복 · 수준 표가 없거나 꼴이 틀리면 처음 값 · 수준 0 · 못 함 · 모르는 직원 · 할 일은 0.
지어낸 값만 쓴다. 바깥 호출 없음.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from db import db_session
from foms.services.ai_staff import registry as a
from foms.services.erp_actions.registry import ACTIONS, MAX_LEVEL, MODE_HUMAN
from models import SystemSetting


def store(value):
    db_session.add(SystemSetting(setting_key=a.SETTINGS_KEY, setting_value=value))
    db_session.commit()


# ── 선언 ────────────────────────────────────────────────────────────────
def test_five_agents_with_known_tools():
    assert list(a.AGENTS) == ["cs", "drawing", "ask", "ops", "schedule"]
    assert all(len(key) <= 16 for key in a.AGENTS)  # 표 칸 ai_agent_runs.agent String(16)
    assert all(tool.name in a.TOOLS and tool.what for agent in a.AGENTS.values() for tool in agent.tools)
    assert [k for k, agent in a.AGENTS.items() if agent.trial] == ["ops", "schedule"]
    assert {t.name for t in a.AGENTS["ask"].tools} == {"mask.apply", "knowledge.search", "erp.order.get",
                                                       "erp.visit.list"}
    assert a.AGENTS["cs"].status_label == "있음" and a.AGENTS["ops"].status_label == "새로 · 시험 중"


def test_first_levels_never_exceed_the_action_cap_and_there_is_no_level_three():
    for agent in a.AGENTS.values():
        keys = [duty.key for duty in agent.duties]
        assert len(keys) == len(set(keys)), agent.key
        for duty in agent.duties:
            assert duty.level is None or 0 <= duty.level <= MAX_LEVEL, (agent.key, duty.key)
            if duty.is_action and duty.level is not None:
                spec = ACTIONS[duty.key]
                assert spec.mode != MODE_HUMAN and duty.level <= spec.level_cap, (agent.key, duty.key)


def test_who_proposes_what():
    assert a.AGENTS["cs"].actions() == ("move_construction", "register_as", "add_construction_note")
    assert a.AGENTS["ops"].actions() == ("send_measure_alimtalk", "assign_draftsman", "advance_stage")  # D214 규칙 O2
    assert a.AGENTS["schedule"].actions() == ("schedule_construction",)
    assert a.AGENTS["ask"].actions() == () and a.AGENTS["drawing"].actions() == ()  # 읽기만 · 판 1 에 새 할 일 없음
    assert a.AGENTS["cs"].duty("send_measure_alimtalk").level is None  # 상담 AI 는 알림톡을 못 한다


def test_proposer_round_trip():
    assert a.proposer("schedule") == "agent:schedule" and len(a.proposer("schedule")) <= 64
    assert a.agent_of("agent:ops") is a.AGENTS["ops"]
    for other in ("user:7", "agent:nope", "agent:", None, 7):
        assert a.agent_of(other) is None
    with pytest.raises(ValueError):
        a.proposer("nope")


# ── 수준 읽기 ────────────────────────────────────────────────────────────
def test_without_a_level_table_the_first_levels_apply(app):
    assert a.level_of(db_session, "schedule", "schedule_construction") == 2
    assert a.level_of(db_session, "ops", "send_measure_alimtalk") == 1
    assert a.level_of(db_session, "cs", "add_construction_note") == 2
    assert a.level_of(db_session, "cs", "send_measure_alimtalk") == 0  # 못 함
    assert a.level_of(db_session, "cs", "schedule_construction") == 0  # 그 직원에게 없는 할 일
    assert a.level_of(db_session, "nope", "schedule_construction") == 0
    assert a.level_of(db_session, "ask", "erp_read") == 0


def test_stored_levels_apply_only_when_their_shape_is_right(app):
    store({"schedule": {"schedule_construction": 0},
           "ops": {"send_measure_alimtalk": 2, "assign_draftsman": True},  # 상한(1) 넘음 · 참거짓
           "cs": {"move_construction": 3, "register_as": "2", "add_construction_note": 1,  # 3 · 글 · 바른 값
                  "send_measure_alimtalk": 1, "cs_draft": 0}})  # 못 함 · 직원만의 일은 표로 바꾸지 않는다
    assert a.level_of(db_session, "schedule", "schedule_construction") == 0  # 0 = 제안을 만들지 않음
    assert a.level_of(db_session, "ops", "send_measure_alimtalk") == 1
    assert a.level_of(db_session, "ops", "assign_draftsman") == 1
    assert a.level_of(db_session, "cs", "move_construction") == 2
    assert a.level_of(db_session, "cs", "register_as") == 2
    assert a.level_of(db_session, "cs", "add_construction_note") == 1
    assert a.level_of(db_session, "cs", "send_measure_alimtalk") == 0
    assert a.level_table(db_session)["cs"]["cs_draft"] == 1


def test_a_broken_level_table_falls_back_to_first_levels(app):
    store(["not", "a", "dict"])
    assert a.level_of(db_session, "schedule", "schedule_construction") == 2
    db_session.get(SystemSetting, a.SETTINGS_KEY).setting_value = {"schedule": "x"}
    db_session.commit()
    assert a.level_of(db_session, "schedule", "schedule_construction") == 2


def test_level_table_reads_the_setting_once(app):
    store({"schedule": {"schedule_construction": 1}})
    db_session.expire_all()
    seen = []
    engine = db_session.get_bind()

    def listener(conn, cursor, statement, *rest):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", listener)
    try:
        table = a.level_table(db_session)
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(seen) == 1
    assert table["schedule"] == {"schedule_construction": 1}
    assert table["cs"]["send_measure_alimtalk"] is None and table["drawing"] == {"weekly_note": 1}
