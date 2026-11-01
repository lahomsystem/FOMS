"""사례 기억(L0 — 플랜 C10-4 · 설계서 17.2 · 17.6) — 합성 글로 완료 기준 ①~⑨ 를 시험한다.

① 직접 답 → 그 차례 줄에 가린 직원 답 · 가린 손님 질문 · '직접 답' · 상담원 id ② 메모 글과 거의 같은 직원 답 → '복사' · 다음
초안 재료에 안 들어감(음성 대조군: 조금 고친 답은 '직접 답', 지우지 못한 앞 메모를 복사해도 '복사') ③ 다음 초안 재료에 같은
브랜드 비슷한 사례가 들어감 · 다른 브랜드 · 떼어 둔 사례 · 복사 · 버림 · 안 비슷한 사례는 안 들어감 ④ 가림 깨진 글은 저장 안 함
⑤ 보낸 글 id 와 같은 직원 글은 '직접 답'이 안 됨 ⑥ 사례 속 금액 · 날짜가 새 초안에 옮겨지면 검사가 막음 ⑦ 직원 글 · 이름 ·
상담원 id 가 로그 · 요약에 안 나옴 ⑧ 마이그레이션 꼴 · 모델과 DDL 일치 ⑨ 15분 바퀴만 켜진 상태(빠른 길 꺼짐)에서도 직접 답이
붙음. 둘레: 직원 답이 끝나기(조용 기다림 · 다음 손님 글)를 기다림 · 바퀴마다 읽기 상한 · 비슷함 셈이 pg_trgm 과 같음 · 직원 번호 ·
상담원 id 를 보여 주는 화면 · 집계 없음(R10-28).

두뇌 · 메모 감싸개 · 채널톡은 가짜(네트워크 · 키 없음), 손으로 꾸민 합성 글만 쓴다(전화 꼴 숫자 · 실제 가격 없음). 시각은
2026-11 KST(11-02 월요일), 달력은 '주말만 쉼' 가짜 달력이다.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import logging
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from db import db_session
from foms.services.cs_agent import (
    brain, brain_cases, brain_prompt, case_material, case_memory, drafting, loop, realtime, turns_fields,
)
from foms.services.cs_agent.drafting_read import ChatLine
from foms.services.cs_agent.masking import MaskLeak, mask
from models import CsAgentTurn
from tests.domains.test_cs_drafting import (  # noqa: F401 — channel 은 fixture
    CUSTOMER, DRAFT, FakeBrain, FakePoster, channel, customer, result, run,
)
from tests.domains.test_cs_realtime import Talk, rows, sec, switch_on, tick
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    FakeAnthropic, FakeClock, derived, keys, make_reader, weekdays_only,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "csagent_03_turn_case_memory.py"
STAFF = "초록고래직원답표지"  # 직원 답 표지 — 가린 칸에만 있고 로그 · 요약에는 없어야 한다
STAFF_NAME = "연두고래직원명찰"  # 직원이 글에 쓴 이름 표지 — 가린 직원 답 칸에만, 로그 · 요약에는 없어야 한다
PROFILE_NAME = "하늘고래프로필명찰"  # 채널톡 글의 상담원 프로필 칸 — 읽지 않으니 어디에도 없어야 한다
MANAGER = "mgr-synthetic-7"  # 데스크 상담원 id(채널톡 personId 꼴)
QUESTION = f"{CUSTOMER} 선반 깊이 문의드려요"  # Talk 의 처음 손님 글
COPY = DRAFT + " 감사합니다."  # 메모 글을 복사해 끝 인사만 붙임(글자 비슷함 0.91)
EDITED = "안녕하세요 고객님, 합성 선반 깊이는 350mm 이고 원하시면 더 깊게도 맞춰 드립니다."  # 문장 하나 고침(0.78 — '고침')
DIRECT = "고객님 선반은 350mm 입니다. 다른 크기는 따로 여쭤 주세요."  # 메모와 다른 답(0.44 — '직접 답')
DRAFT_B = "안녕하세요 고객님, 문의 주신 합성 선반은 깊이 350mm 제품만 있습니다."


def staff(talk, msg_id, when, text):
    """공개 직원 글 — 웹훅 수신 줄과 가짜 채널톡 글에 같은 상담원 id · 프로필 칸(이름 표지)을 싣는다."""
    talk.say(msg_id, when, "manager", text, personId=MANAGER, profile={"name": PROFILE_NAME})


def case_row(chat, *, question="선반 깊이 문의드려요", answer="합성 답", brand="LAHOM", outcome="direct",
             held_out=False):
    """이미 쌓인 사례 줄(끝난 차례)."""
    row = CsAgentTurn(brand=brand, chat_id=chat, last_user_message_id=f"m-{chat}", state="stored", attempts=1,
                      masked_question=question, staff_reply_masked=answer, outcome=outcome, held_out=held_out)
    db_session.add(row)
    db_session.commit()
    return row


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── ① 직접 답 → 짝 ──────────────────────────────────────────────────────
def test_a_direct_reply_is_attached_with_the_masked_question_and_the_desk_manager(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0), text=QUESTION)
    talk.say("m-2", sec(4), text="주소: 합성시 가상로 12 입니다")
    tick(channel, sec(20), memory)
    assert [(row.state, row.outcome, row.held_out) for row in rows()] == [("stored", None, False)]
    staff(talk, "s-1", sec(40), f"{STAFF} 선반 깊이는 350mm 입니다. 가상로 12 매장도 있습니다")
    staff(talk, "s-2", sec(50), "추가로 궁금하신 점 있으시면 말씀 주세요")
    early = tick(channel, sec(50 + 60), memory)  # 마지막 직원 글 뒤 2분 전 — 직원이 더 쓸 수 있어 기다린다
    assert (early.cases["pending"], early.cases["ready"], rows()[0].outcome) == (1, 0, None)
    later = tick(channel, sec(50 + 121), memory)
    (row,) = rows()
    assert (row.state, row.outcome, row.desk_manager_id) == ("stored", "direct", MANAGER)
    assert later.summary()["cases"] == {"pending": 1, "ready": 1, "reads": 1, "direct": 1, "edited": 0, "copied": 0,
                                        "discarded": 0, "no_text": 0, "read_errors": 0, "conflicts": 0, "halted": None}
    reply = row.staff_reply_masked
    assert STAFF in reply and "추가로" in reply and "[도로명주소]" in reply and "가상로" not in reply  # 두 말풍선 · 가림
    assert row.masked_question.split("\n") == [QUESTION, "주소: 합성시 [주소]"]  # 그 차례 손님 글 둘(가린 것)
    expected = Decimal(str(round(1 - case_memory.text_similarity(DRAFT, mask(reply)), 3)))
    assert row.edit_ratio == expected and Decimal("0") < row.edit_ratio <= Decimal("1")


def test_the_next_customer_message_closes_the_reply_window_without_waiting(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0), text=QUESTION)
    tick(channel, sec(16), memory)
    staff(talk, "s-1", sec(30), f"{STAFF} 첫 답입니다")
    talk.say("m-2", sec(40), text="네 그럼 서랍도 문의드려요")  # 손님이 이어 씀 — 직원 답 창이 닫힌다
    staff(talk, "s-2", sec(41), "서랍 답은 다음 차례 몫입니다")
    tick(channel, sec(42), memory)  # 조용 기다림(2분) 없이 붙인다
    first = rows()[0]
    assert (first.outcome, first.staff_reply_masked) == ("direct", f"{STAFF} 첫 답입니다")


def test_a_turn_whose_window_closed_without_a_reply_gets_nothing_and_the_next_turn_gets_the_reply(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0), text="", files=[{"id": "f-1"}])  # 사진만 — 건너뜀
    tick(channel, sec(16), memory)
    talk.say("m-2", sec(30), text=QUESTION)  # 직원 답 전에 손님이 이어 씀 — 앞 차례 창은 답 없이 닫혔다
    tick(channel, sec(46), memory)
    staff(talk, "s-1", sec(60), f"{STAFF} 사진과 문의 함께 봤습니다")
    result_ = tick(channel, sec(60 + 121), memory)
    photo, text_turn = rows()
    assert (photo.state, photo.error_code, photo.outcome) == ("skipped", "photo_only", "discarded")  # 직원 답은 뒤 차례 몫
    assert (text_turn.outcome, text_turn.staff_reply_masked) == ("direct", f"{STAFF} 사진과 문의 함께 봤습니다")
    assert text_turn.masked_question.split("\n") == ["(사진 · 파일 첨부)", QUESTION]  # 묶음의 손님 글 모두
    assert (result_.cases["pending"], result_.cases["ready"], result_.cases["reads"], result_.cases["discarded"]) == (
        2, 1, 1, 1)


# ── ② 복사 판정 · 재료에서 뺌 ─────────────────────────────────────────────
def test_a_copied_memo_is_copied_and_never_becomes_material_but_an_edited_reply_does(channel):
    switch_on()
    memory = realtime.TickMemory()
    copied, edited = Talk(channel, "uc-1"), Talk(channel, "uc-2")
    for talk in (copied, edited):
        talk.say(f"m-{talk.chat}", sec(0), text=QUESTION)
    tick(channel, sec(16), memory)
    staff(copied, "s-1", sec(30), COPY)
    staff(edited, "s-2", sec(30), EDITED)  # 음성 대조군: 문장 하나를 고친 답(R14-5 — 중간 띠는 '고침')
    tick(channel, sec(30 + 121), memory)
    (copy_row,), (edit_row,) = rows("uc-1"), rows("uc-2")
    assert (copy_row.outcome, copy_row.edit_ratio) == ("copied", Decimal("0.089"))
    assert (edit_row.outcome, edit_row.edit_ratio) == ("edited", Decimal("0.224"))
    asker, brain_fn = Talk(channel, "uc-3"), FakeBrain()
    asker.say("m-uc-3", sec(300), text=QUESTION)
    tick(channel, sec(316), memory, brain_fn=brain_fn)
    (request,) = brain_fn.requests
    assert request.cases == ((QUESTION, EDITED),)  # 복사(무게 0)는 재료가 아니다


def test_copying_an_older_memo_that_could_not_be_removed_is_still_copied(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    brain_fn = FakeBrain(result(draft=DRAFT), result(draft=DRAFT_B))
    talk.say("m-1", sec(0), text=QUESTION)
    tick(channel, sec(16), memory, brain_fn=brain_fn)
    talk.say("m-2", sec(30), text="합성 다른 색도 있나요")
    tick(channel, sec(31), memory, brain_fn=brain_fn)  # 앞 차례는 '지난 초안' — 앞 메모는 지우지 못한다(Q21)
    tick(channel, sec(46), memory, brain_fn=brain_fn)
    assert [(row.state, row.masked_draft) for row in rows()] == [("superseded", DRAFT), ("stored", DRAFT_B)]
    staff(talk, "s-1", sec(60), COPY)  # 직원이 앞 메모(DRAFT)를 복사
    result_ = tick(channel, sec(60 + 121), memory, brain_fn=brain_fn)
    old, new = rows()
    assert (old.outcome, new.outcome) == (None, "copied")  # 지난 초안은 사례가 아니고, 새 차례가 '복사'로 남는다
    assert (result_.cases["pending"], result_.cases["conflicts"]) == (1, 0)  # 지난 초안은 살펴보지도 않는다(M12)
    assert new.masked_question.split("\n") == [QUESTION, "합성 다른 색도 있나요"]


# ── ③ 다음 초안 재료 ─────────────────────────────────────────────────────
def test_the_next_draft_gets_similar_same_brand_cases_only(channel):
    keep = [case_row("c-direct", answer="합성 답 직접"), case_row("c-as-is", answer="합성 답 그대로", outcome="as_is"),
            case_row("c-edited", answer="합성 답 고침", outcome="edited")]
    case_row("c-haud", answer="합성 답 하우드", brand="HAUD")
    case_row("c-held", answer="합성 답 떼어 둠", held_out=True)
    case_row("c-copied", answer="합성 답 복사", outcome="copied")
    case_row("c-discarded", answer="합성 답 버림", outcome="discarded")
    case_row("c-far", question="배송 일정이 궁금합니다", answer="합성 답 안 비슷함")
    case_row("c-open", answer="합성 답 아직", outcome=None)  # 사례가 아직 없는 줄
    customer(channel, "uc-1", text=QUESTION)
    brain_fn = FakeBrain()
    run(channel, brain_fn=brain_fn)
    (request,) = brain_fn.requests
    assert request.cases == tuple((row.masked_question, row.staff_reply_masked) for row in reversed(keep))
    task = brain_prompt.task_text(purpose="draft", chat_id="uc-1", medium="native", now=sec(0), calculator_lines=(),
                                  conversation="[손님] 합성", cases=request.cases)
    head = task.index(brain_cases.CASES_HEAD)
    assert task.index("계산 결과") < head < task.index("상담 글(")
    assert ["사례 1 손님 글:", "| 선반 깊이 문의드려요"] == task.split(brain_cases.CASES_HEAD)[1].splitlines()[1:3]
    assert brain_cases.CASES_HEAD not in brain_prompt.task_text(  # 사례가 없으면 칸도 없다(예전 글 그대로)
        purpose="draft", chat_id="uc-1", medium="native", now=sec(0), calculator_lines=(), conversation="[손님] 합성")


def test_cases_are_ordered_by_similarity_and_capped(app):
    for number in range(7):
        case_row(f"c-{number}", answer=f"합성 답 {number}")
    closer = case_row("c-closer", question=f"{CUSTOMER} 선반 깊이 문의드려요 합성", answer="합성 답 가장 비슷")
    found = case_material.similar_cases(db_session, "LAHOM", _lines(QUESTION + " 합성"))
    assert len(found) == brain_cases.MAX_CASES == 5
    assert found[0] == (closer.masked_question, "합성 답 가장 비슷")
    assert [answer for _, answer in found[1:]] == [f"합성 답 {n}" for n in (6, 5, 4, 3)]  # 같은 비슷함이면 새 사례부터
    assert case_material.similar_cases(db_session, "LAHOM", []) == ()  # 지금 손님 글이 없으면 재료 없음


def _lines(text):
    """손님 글 하나짜리 상담 줄(읽기 도우미 꼴)."""
    return [ChatLine(derived("m-q", sec(0), "user", text), text)]


def test_trigram_similarity_matches_pg_trgm():
    assert round(case_material.trigram_similarity("word", "two words"), 6) == 0.363636  # pg_trgm 문서의 보기 값
    assert case_material.trigram_similarity("선반 깊이", "선반 깊이") == 1.0
    assert case_material.trigram_similarity("선반", "배송") == 0.0 and case_material.trigram_similarity("", "선반") == 0.0
    assert case_memory.text_similarity(DRAFT, COPY) >= case_memory.COPY_SIMILARITY > case_memory.text_similarity(
        DRAFT, EDITED)


# ── ④ 가림 깨진 글은 저장 안 함 ─────────────────────────────────────────
def test_text_that_fails_the_mask_check_is_not_stored(channel, monkeypatch, caplog):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0), text=QUESTION)
    talk.say("m-2", sec(2), text="주소는 가상로 12 입니다")
    tick(channel, sec(18), memory)
    staff(talk, "s-1", sec(30), f"{STAFF} 가상로 12 로 오시면 됩니다")
    monkeypatch.setattr(turns_fields, "mask", lambda text: text)  # 가림이 구멍 난 때 — 검사가 마지막 문이다
    monkeypatch.setattr(case_memory, "mask", lambda text: text)
    result_ = tick(channel, sec(30 + 121), memory)
    (row,) = rows()
    assert (row.outcome, row.staff_reply_masked, row.desk_manager_id) == ("direct", None, MANAGER)  # 코드만
    assert row.masked_question == QUESTION  # 가림 검사를 넘은 손님 글만
    assert (result_.cases["direct"], result_.cases["no_text"]) == (1, 1)
    assert "가림 검사" in caplog.text and STAFF not in caplog.text and "가상로" not in caplog.text


# ── ⑤ 보낸 글 id 는 '직접 답'이 아님 ────────────────────────────────────
def test_our_own_sent_message_coming_back_is_not_a_direct_reply(channel):
    switch_on()
    memory = realtime.TickMemory()
    ours, theirs = Talk(channel, "uc-1"), Talk(channel, "uc-2")
    for talk in (ours, theirs):
        talk.say(f"m-{talk.chat}", sec(0), text=QUESTION)
    tick(channel, sec(16), memory)
    db_session.execute(update(CsAgentTurn).where(CsAgentTurn.chat_id == "uc-1").values(sent_message_id="s-ours"))
    db_session.commit()  # 2주차 [보내기]가 적은 보낸 글 id(사례는 아직 없음)
    staff(ours, "s-ours", sec(30), DRAFT)  # 그 글이 웹훅 · Open API 로 돌아옴
    staff(theirs, "s-theirs", sec(30), DRAFT)  # 음성 대조군: 같은 글이어도 직원이 데스크에서 쓴 것
    channel.calls.clear()
    first = tick(channel, sec(30 + 121), memory)
    assert (rows("uc-1")[0].outcome, rows("uc-2")[0].outcome) == (None, "copied")
    assert first.cases["pending"] == 2 and first.cases["ready"] == 1
    assert not [call for call in channel.calls if call.startswith("user-chats/uc-1")]  # 상태 표에서 걸러 읽지도 않는다
    staff(ours, "s-more", sec(200), f"{STAFF} 덧붙여 안내드립니다")  # 우리 글 뒤 직원이 직접 더 씀
    tick(channel, sec(200 + 121), memory)
    (row,) = rows("uc-1")
    assert (row.outcome, row.staff_reply_masked) == ("direct", f"{STAFF} 덧붙여 안내드립니다")  # 우리 글은 뺐다


# ── ⑥ 사례 속 금액 · 날짜는 새 초안에 못 옮김 ───────────────────────────
def test_amounts_and_dates_from_a_case_are_blocked_in_a_new_draft(channel):
    case_row("c-1", answer="합성 선반 깊이는 350mm, 설치비 포함 123,000원 이고 11월 9일 실측입니다")
    for chat in ("uc-1", "uc-2", "uc-3"):
        customer(channel, chat, text=QUESTION)
    drafts = ("안녕하세요 고객님, 설치비 포함 123,000원 입니다.", "안녕하세요 고객님, 11월 9일 실측 가능합니다.", DRAFT)
    client = FakeAnthropic(*({"intent": "hours", "draft": draft, "evidence_ids": ["shelf-depth"], "handoff": False,
                              "handoff_reason": "none", "staff_note": "합성 참고"} for draft in drafts))
    summary = run(channel, brain_fn=functools.partial(brain.draft_reply, client=client))
    sent = json.dumps(client.params[0]["messages"], ensure_ascii=False)
    assert brain_cases.CASES_HEAD in sent and "123,000원" in sent  # 양성 대조: 사례는 두뇌에 갔다
    (amount,), (date,), (clean,) = rows("uc-1"), rows("uc-2"), rows("uc-3")
    assert (amount.state, amount.error_code, "number_not_allowed" in amount.check_codes) == (
        "skipped", "check_failed", True)
    assert (date.state, date.error_code, "date_not_confirmed" in date.check_codes) == ("skipped", "check_failed", True)
    assert (clean.state, summary.stored) == ("stored", 1)  # 음성 대조군: 사례 숫자를 안 쓴 초안은 통과


def test_a_case_that_fails_the_mask_check_never_reaches_the_brain(app):
    case_row("c-1", answer="합성 답 가상로 12 로 오세요")  # 가림이 구멍 난 채 쌓인 사례(가정)
    case_row("c-2", answer="합성 답 깨끗함")
    assert case_material.similar_cases(db_session, "LAHOM", _lines(QUESTION)) == (("선반 깊이 문의드려요", "합성 답 깨끗함"),)
    with pytest.raises(MaskLeak) as caught:  # 두뇌가 실을 때 한 번 더 — 칸별 숫자만
        brain_cases.case_lines((("선반 깊이 문의드려요", "합성 답 가상로 12 로 오세요"),))
    assert caught.value.counts == {"도로": 1} and "가상로" not in str(caught.value)


# ── ⑦ 직원 글 · 이름이 로그에 없음 ──────────────────────────────────────
def test_staff_text_name_and_desk_id_stay_out_of_logs_and_summaries(channel, caplog):
    caplog.set_level(logging.DEBUG, logger="foms.services.cs_agent")
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0), text=QUESTION)
    tick(channel, sec(16), memory)
    staff(talk, "s-1", sec(30), f"{STAFF} 담당 {STAFF_NAME} 드림")
    result_ = tick(channel, sec(30 + 121), memory)
    assert rows()[0].outcome == "direct" and "[CS 사례]" in caplog.text  # 양성 대조: 로그는 남았다
    summary = json.dumps(result_.summary(), ensure_ascii=False)
    for mark in (STAFF, STAFF_NAME, PROFILE_NAME, MANAGER, CUSTOMER):
        assert mark not in caplog.text and mark not in summary
    stored = db_session.execute(select(CsAgentTurn.__table__)).mappings().one()
    cells = {key: str(value) for key, value in stored.items() if value is not None}
    assert [key for key, value in cells.items() if STAFF_NAME in value] == ["staff_reply_masked"]  # 직원 글 안에만
    assert not [key for key, value in cells.items() if PROFILE_NAME in value]  # 프로필 칸은 읽지 않는다
    assert cells["desk_manager_id"] == MANAGER  # 상담원 id 는 칸에만(ADMIN DB — 로그 · 요약 없음)


# ── ⑧ 마이그레이션 꼴 ────────────────────────────────────────────────────
def test_csagent_03_chains_onto_csagent_02_and_matches_the_model():
    module = load(MIGRATION, "csagent_03_mig_unit")
    assert (module.revision, module.down_revision) == ("csagent_03", "csagent_02")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source  # 상수 동결
    assert module.OUTCOMES == case_memory.OUTCOMES and module.EDIT_REASONS == case_memory.EDIT_REASONS
    checks = {c.name: str(c.sqltext) for c in CsAgentTurn.__table__.constraints if isinstance(c, CheckConstraint)}
    assert checks[module.OUTCOME_CHECK] == module.in_check("outcome", module.OUTCOMES)
    assert checks[module.EDIT_REASON_CHECK] == module.in_check("edit_reason", module.EDIT_REASONS)
    assert checks[module.EDIT_RATIO_CHECK] == module.EDIT_RATIO_SQL
    columns = CsAgentTurn.__table__.c
    for name, type_, nullable, default in module.COLUMNS:
        column = columns[name]
        assert column.nullable is nullable and type(column.type).__name__ == type(type_).__name__, name
        assert getattr(column.type, "length", None) == getattr(type_, "length", None), name
    assert (columns.edit_ratio.type.precision, columns.edit_ratio.type.scale) == (4, 3)
    assert str(columns.held_out.server_default.arg) == "false" and columns.held_out.default.arg is False
    (index,) = [i for i in CsAgentTurn.__table__.indexes if i.name == module.INDEX_NAME]
    model_ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert model_ddl == module.CREATE_INDEX_SQL.replace("IF NOT EXISTS ", "")  # 이름 · 식 · gin_trgm_ops 글자까지 같다
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1 and "csagent_03" in {rev.revision for rev in script.walk_revisions("base", heads[0])}


def test_the_migration_gates_the_trgm_index_to_postgresql_and_downgrades_in_reverse():
    source = MIGRATION.read_text(encoding="utf-8")
    up, down = source.split("def upgrade", 1)[1].split("def downgrade", 1)
    assert up.index("add_column") < up.index("create_check_constraint") < up.index("dialect.name == 'postgresql'")
    assert up.index("dialect.name == 'postgresql'") < up.index("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    assert down.index("DROP_INDEX_SQL") < down.index("drop_constraint") < down.index("drop_column")
    assert down.index("dialect.name == 'postgresql'") < down.index("DROP_INDEX_SQL")
    module = load(MIGRATION, "csagent_03_mig_cols")
    assert [name for name, *_ in module.COLUMNS] == ["masked_question", "outcome", "edit_ratio", "edit_reason",
                                                     "sent_by_user_id", "desk_manager_id", "sent_message_id",
                                                     "quote_lines", "held_out"]


# ── ⑨ 15분 바퀴만으로도 붙음 ─────────────────────────────────────────────
def test_the_quarter_hour_pass_alone_attaches_direct_replies(channel, monkeypatch):
    switch_on(realtime_enabled=False)  # 빠른 길 처음 값(꺼짐)
    monkeypatch.setattr(loop, "run_drafting", functools.partial(drafting.run_drafting, brain=FakeBrain(),
                                                                poster=FakePoster()))
    talk = Talk(channel)
    talk.say("m-1", sec(0), text=QUESTION)
    first = _loop_pass(channel, sec(60))
    assert rows()[0].state == "stored" and first.summary()["cases"]["pending"] == 0
    staff(talk, "s-1", sec(120), f"{STAFF} 직접 답입니다")
    assert tick(channel, sec(400), realtime.TickMemory()).outcome == "idle"  # 빠른 길은 꺼져 일 0
    later = _loop_pass(channel, sec(400))
    (row,) = rows()
    assert (row.outcome, row.staff_reply_masked, row.desk_manager_id) == ("direct", f"{STAFF} 직접 답입니다", MANAGER)
    assert later.summary()["cases"]["direct"] == 1


def test_with_the_fast_path_on_the_quarter_hour_pass_leaves_cases_to_it(channel, monkeypatch):
    switch_on()  # 빠른 길 켬 — 15분 바퀴는 보정 · 아침 보고만
    monkeypatch.setattr(loop, "attach_staff_replies", lambda *a, **k: pytest.fail("빠른 길이 도는데 15분 바퀴가 붙였다"))
    assert "cases" not in _loop_pass(channel, sec(60)).summary()


def _loop_pass(channel, now):
    return loop.run_pass(db_session, config=loop.LoopConfig(), stop=loop.StopFlag(),
                         reader=make_reader(channel, FakeClock()), now=now, clock=lambda: 0.0,
                         is_business_day=weekdays_only)


# ── 둘레: 읽기 상한 · 직원 정보 ─────────────────────────────────────────
def test_each_tick_reads_at_most_its_cap_and_the_rest_wait_for_the_next(channel):
    switch_on()
    memory = realtime.TickMemory()
    talks = [Talk(channel, f"uc-{n}") for n in range(1, 4)]
    for talk in talks:
        talk.say(f"m-{talk.chat}", sec(0), text=QUESTION)
    tick(channel, sec(16), memory)
    for talk in talks:
        staff(talk, f"s-{talk.chat}", sec(30), EDITED)
    first = tick(channel, sec(30 + 121), memory)
    assert (first.cases["reads"], first.cases["edited"], first.cases["halted"]) == (
        case_memory.TICK_LIMITS.max_reads, 2, "read_cap")
    second = tick(channel, sec(30 + 126), memory)
    assert (second.cases["reads"], second.cases["edited"]) == (1, 1)
    assert [rows(talk.chat)[0].outcome for talk in talks] == ["edited"] * 3


def test_staff_ids_are_not_shown_or_counted_on_screens_or_reports():
    """R10-28 — 보낸 직원 번호 · 상담원 id 를 보여 주거나 직원별로 세는 화면 · 패널 · 보고가 없다(ADMIN DB 만)."""
    agent = ROOT / "foms" / "services" / "cs_agent"
    surfaces = [*(ROOT / "templates").rglob("*.html"), *(ROOT / "static").rglob("*.js"), agent / "panel.py",
                agent / "report.py", ROOT / "foms" / "web" / "admin" / "cs_agent.py"]
    assert len(surfaces) > 10
    hits = [path.name for path in surfaces if any(name in path.read_text(encoding="utf-8", errors="replace")
                                                  for name in ("sent_by_user_id", "desk_manager_id"))]
    assert hits == []
