"""사례 질문 앞 대화(설계서 17.2.2 — 사장님 11-05 "수정한 내용은 CS 에이전트가 학습해야 돼, 이전 대화 맥락을 이해하면서").

사례를 적을 때(보내기 그대로 · 고침, 직원 직접 답) 그 질문 **앞** 공개 대화를 가려 ``masked_context`` 에 두고, 다음 초안의 '비슷한
지난 상담'(고침 · 직접 답만)과 주간 고침 안 재료에 같이 싣는다. 여기서 보는 것: 머리표 · 가림 · 비공개 메모 뺌 · 상한, 보내기 길과
직접 답 길이 둘 다 적음, 사례 재료 · 두뇌 글 꼴(앞 대화 없으면 옛 꼴 그대로), 주간 고침 안 재료 · 작은 창으로 보낸 상담원도 직원
수에 듦, 마이그레이션 사슬.

채널톡 · 두뇌는 가짜(네트워크 없음), 손으로 꾸민 합성 글만(전화 꼴 숫자는 실행 때 만든다). 시각은 2026-11 KST.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from db import db_session
from foms.services.cs_agent import brain_cases, case_material, case_memory, realtime, weekly_fix
from foms.services.cs_agent.drafting_read import ChatLine
from models import CsAgentTurn
from tests.domains.test_cs_case_memory import QUESTION, staff
from tests.domains.test_cs_drafting import channel  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_realtime import Talk, rows, sec, switch_on, tick
from tests.domains.test_cs_send import NOW, FakeSender, fresh, posted, ready, switches, user  # noqa: F401 — ready
from tests.domains.test_cs_wam_send import call
from tests.support.cs_agent_fakes import api_message, at, derived, keys  # noqa: F401 — keys 는 fixture

ROOT = Path(__file__).resolve().parents[2]
PHONE = "-".join(("0" + "1" + "0", "2" * 4, "7" * 4))  # 전화 꼴(실행 때 만든다 — 공개 저장소에 두지 않는다)


def said(msg_id, minute, person, text, **extra):
    return ChatLine(derived(msg_id, at(2, 8, minute), person, text, **extra), text)


# ── 앞 대화 만들기 ───────────────────────────────────────────────────────
def test_prior_context_tags_masks_and_skips_private_memos():
    lines = [said("a1", 1, "user", "합성 안방 붙박이장 가로 2400 문의드려요"),
             said("a2", 2, "manager", "합성 실측 지역이 어디세요?"),
             said("a3", 3, "manager", "내부메모표지 확인 필요", options=["private"]),
             said("a4", 4, "user", f"합성시예요 연락처 {PHONE}"),
             said("a5", 5, "manager", "합성 가능합니다"),
             said("q1", 6, "user", "그럼 값은 얼마예요?")]
    context = case_memory.prior_context(lines, 5)
    assert context.split("\n")[0] == "[손님] 합성 안방 붙박이장 가로 2400 문의드려요"
    assert [row.split(" ")[0] for row in context.split("\n")] == ["[손님]", "[직원]", "[손님]", "[직원]"]
    assert "내부메모표지" not in context and PHONE not in context and "값은" not in context  # 메모 · 전화 · 질문은 없다
    assert case_memory.prior_context(lines, 0) is None  # 앞 대화가 없으면 비움


def test_prior_context_keeps_the_latest_lines_within_the_caps():
    many = [said(f"u{n}", n, "user", f"합성 손님 글 {n}") for n in range(9)]
    assert case_memory.prior_context(many, 9).split("\n") == [f"[손님] 합성 손님 글 {n}" for n in range(3, 9)]  # 최근 6줄
    long = [said(f"l{n}", n, "user", "가" * 400) for n in range(5)]
    capped = case_memory.prior_context(long, 5)
    assert all(len(row) <= len("[손님] ") + case_memory.CONTEXT_LINE_CHARS for row in capped.split("\n"))
    assert len(capped) <= case_memory.CONTEXT_CHARS and capped.count("\n") == 2  # 합 800자 — 오래된 줄부터 뺀다


# ── 적는 곳 둘: 보내기 길 · 직접 답 길 ─────────────────────────────────────
def test_a_sent_case_stores_the_conversation_before_the_question(app, ready):
    turn_id = posted(ready)
    ready.messages["uc-1"][:0] = [api_message("p-1", at(2, 8, 10), "user", "합성 앞 손님 글"),
                                  api_message("p-2", at(2, 8, 20), "manager", "합성 앞 직원 답")]
    result = call(app, ready, "cs.draft.send", {"turn": turn_id, "chat": "uc-1"}, sender=FakeSender(ready))
    assert result["result"]["code"] == "sent"
    assert fresh(turn_id).masked_context == "[손님] 합성 앞 손님 글\n[직원] 합성 앞 직원 답"


def test_a_direct_reply_case_stores_the_conversation_before_the_question(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-0", sec(0), text="합성 앞 질문이에요")
    staff(talk, "s-0", sec(5), "합성 앞 답이에요")
    talk.say("m-1", sec(10), text=QUESTION)
    tick(channel, sec(30), memory)
    staff(talk, "s-1", sec(50), "합성 선반 깊이는 350mm 입니다. 다른 크기는 따로 여쭤 주세요")
    tick(channel, sec(50 + 121), memory)
    row = next(r for r in rows() if r.outcome is not None)
    assert row.masked_context == "[손님] 합성 앞 질문이에요\n[직원] 합성 앞 답이에요"


# ── 쓰는 곳: 비슷한 지난 상담 · 두뇌 글 ────────────────────────────────────
def _case(chat, outcome, context):
    row = CsAgentTurn(brand="LAHOM", chat_id=chat, last_user_message_id=f"m-{chat}", state="stored", attempts=1,
                      masked_question="선반 깊이 문의드려요", staff_reply_masked=f"합성 답 {chat}", outcome=outcome,
                      masked_context=context)
    db_session.add(row)
    db_session.commit()
    return row


def test_edited_and_direct_cases_carry_their_last_three_context_lines(app):
    context = "\n".join(f"[손님] 합성 앞 글 {n}" for n in range(5))
    _case("c-as-is", "as_is", context)
    _case("c-direct", "direct", context)
    _case("c-edited", "edited", context)
    _case("c-old", "edited", None)  # 앞 대화가 없는 옛 사례
    found = case_material.similar_cases(db_session, "LAHOM", [said("q", 9, "user", "선반 깊이 문의드려요")])
    by_answer = {item[1]: item for item in found}
    tail = tuple(f"[손님] 합성 앞 글 {n}" for n in (2, 3, 4))
    assert by_answer["합성 답 c-edited"].context == tail and by_answer["합성 답 c-direct"].context == tail
    assert by_answer["합성 답 c-as-is"] == ("선반 깊이 문의드려요", "합성 답 c-as-is")  # 그대로 사례는 옛 짝
    assert by_answer["합성 답 c-old"] == ("선반 깊이 문의드려요", "합성 답 c-old")
    lines = brain_cases.case_lines(brain_cases.case_pairs(found))
    assert lines[1] == brain_cases.CASES_CONTEXT_HEAD
    at_edited = lines.index(f"사례 {found.index(by_answer['합성 답 c-edited']) + 1} 앞 대화(그 손님과 이미 나눈 말):")
    assert lines[at_edited + 1:at_edited + 4] == [f"| {line}" for line in tail]
    old = brain_cases.case_lines((("선반 깊이 문의드려요", "합성 답"),))  # 앞 대화가 없으면 옛 꼴 글자 그대로
    assert old == [brain_cases.CASES_HEAD, "사례 1 손님 글:", "| 선반 깊이 문의드려요", "사례 1 사람 답:", "| 합성 답"]


def test_case_context_shape_is_checked():
    item = brain_cases.CaseItem("질문", "답", context=("[손님] 하나", "[손님] 둘", "[손님] 셋", "[손님] 넷"))
    with pytest.raises(ValueError):
        brain_cases.case_pairs((item,))
    wide = brain_cases.CaseItem("질문", "답", context=("가" * (brain_cases.CONTEXT_LINE_LIMIT + 1),))
    with pytest.raises(ValueError):
        brain_cases.case_pairs((wide,))
    full = tuple(brain_cases.CaseItem("질문", "답", context=("가" * 150,) * 3) for _ in range(3))
    with pytest.raises(ValueError):  # 다섯 사례 합 상한
        brain_cases.case_pairs(full)


# ── 주간 고침 안 재료 ────────────────────────────────────────────────────
def test_weekly_fix_material_carries_context_and_counts_window_senders(app):
    sent_at = (NOW - datetime.timedelta(days=1)).astimezone(datetime.timezone.utc).replace(tzinfo=None)
    for chat, staff_id, manager in (("w-1", 7, None), ("w-2", None, "mgr-9"), ("w-3", None, None)):
        db_session.add(CsAgentTurn(brand="LAHOM", chat_id=chat, last_user_message_id=f"m-{chat}", state="posted",
                                   attempts=1, intent="price", outcome="edited", edit_reason="wrong_fact",
                                   masked_question="합성 질문", staff_reply_masked="합성 고친 답", sent_at=sent_at,
                                   sent_by_user_id=staff_id, desk_manager_id=manager,
                                   masked_context="[손님] 합성 앞 글" if chat == "w-1" else None))
    db_session.commit()
    (group,) = weekly_fix.collect_groups(db_session, NOW)
    assert [case["staff"] for case in group.cases] == [7, "m:mgr-9", None]  # FOMS 짝 없는 상담원도 직원으로 센다
    lines = weekly_fix._group_lines(1, group)
    first = next(case["turn_id"] for case in group.cases if case["context"])
    at_context = lines.index(f"사례 {first} 앞 대화(그 손님과 이미 나눈 말):")
    assert lines[at_context + 1] == "| [손님] 합성 앞 글" and lines[at_context + 2] == f"사례 {first} 손님 글:"


# ── 마이그레이션 ─────────────────────────────────────────────────────────
def test_csagent_07_adds_one_nullable_text_column_and_keeps_one_head():
    path = ROOT / "migrations" / "versions" / "csagent_07_turn_masked_context.py"
    spec = importlib.util.spec_from_file_location("csagent_07_unit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "csagent_07"
    source = path.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    column = CsAgentTurn.__table__.c.masked_context
    ((name, type_, nullable, default),) = module.TURN_COLUMNS
    assert (name, nullable, default) == ("masked_context", True, None) and column.nullable is True
    assert type(column.type).__name__ == type(type_).__name__ == "Text"
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1 and "csagent_07" in {rev.revision for rev in script.walk_revisions("base", heads[0])}
