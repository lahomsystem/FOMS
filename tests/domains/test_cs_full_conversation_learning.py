"""주간 학습에 상담 전체 대화(설계서 17.11.2 · 사장님 D173) — 주간 고침 안은 6줄 대신 전체 대화(읽기 실패면 6줄) · 사진 학습은
전체 대화 속 사진 자리에 ``▶ 사진 N`` 표시 줄(모르면 질문 뒤) · 묶음당 사례 수 상한(최근부터) · 끔이거나 읽기 도우미가 없으면
모델에 가는 글이 글자까지 지금과 같음.

합성 차례 · 합성 그림 읽기 결과 · 쪽을 넘기는 가짜 채널톡 · 가짜 학습 모델만(네트워크 0). 손님 글 · 직원 이름 · 금액 없음.
"""

from __future__ import annotations

from db import db_session
from foms.services.cs_agent import photo_learning, weekly_fix
from foms.services.cs_agent.drafting_read import FILE_NOTE
from foms.services.cs_agent.photo_learning_prompt import TALK_HEAD as PHOTO_TALK_HEAD
from models import CsAgentTurn
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_photo_cases import ABOUT, SEEN
from tests.domains.test_cs_photo_learning import (  # noqa: F401 — evidence · world 는 fixture
    done_turn, evidence, on, world,
)
from tests.domains.test_cs_weekly_fix import NOW, panel, ready, two_by_two  # noqa: F401 — ready · two_by_two 는 fixture
from tests.support.cs_agent_fakes import FakeAnthropic, FakeClock, api_message, at, keys, make_reader  # noqa: F401
from tests.support.cs_talk_support import PagedChannel, long_chat

PHOTO_LINE = f"▶ 사진 1 (손님) 현장 사진: {SEEN} — {ABOUT}"


def body(client, index=0):
    return client.params[index]["messages"][0]["content"][0]["text"].split("\n")


def with_context(ids):
    """차례마다 예전 재료(질문 앞 6줄 — 가린 글)를 적어 둔다."""
    for turn_id in ids:
        db_session.get(CsAgentTurn, turn_id).masked_context = f"[손님] 합성 앞 대화 {turn_id}"
    db_session.commit()


# ── 주간 고침 안 ─────────────────────────────────────────────────────────
def test_weekly_fix_cases_carry_the_whole_chat_and_a_failed_read_keeps_the_six_lines(two_by_two):
    first, second = two_by_two
    with_context(two_by_two)
    chan = PagedChannel(fail=2)  # 첫 상담은 한 쪽에 다 읽고, 둘째 상담 첫 쪽이 실패
    chan.chat("uc-1", *long_chat(40))
    client = FakeAnthropic({"proposals": []})
    counts = weekly_fix.run_weekly_fix(db_session, now=NOW, client=client, reader=make_reader(chan, FakeClock()))
    lines = body(client)
    assert counts["evidence_ok"] == 1 and len(chan.asks) == 2
    assert f"사례 {first} {weekly_fix.TALK_HEAD}" in lines and "| [손님] 합성 글 000" in lines
    assert "| [직원] 합성 글 039" in lines and f"사례 {first} 앞 대화(그 손님과 이미 나눈 말):" not in lines
    assert f"사례 {second} 앞 대화(그 손님과 이미 나눈 말):" in lines and f"| [손님] 합성 앞 대화 {second}" in lines
    assert f"사례 {second} {weekly_fix.TALK_HEAD}" not in lines


def test_weekly_fix_text_is_unchanged_when_off_or_without_a_reader(two_by_two, monkeypatch):
    monkeypatch.setattr(weekly_fix, "claim_week", lambda *_a: True)
    with_context(two_by_two)
    chan = PagedChannel()
    for chat in ("uc-1", "uc-2"):
        chan.chat(chat, *long_chat(40))
    before = FakeAnthropic({"proposals": []})
    weekly_fix.run_weekly_fix(db_session, now=NOW, client=before)  # 읽기 도우미 없음 — 예전 재료
    panel(full_talk_messages=0)
    off = FakeAnthropic({"proposals": []})
    weekly_fix.run_weekly_fix(db_session, now=NOW, client=off, reader=make_reader(chan, FakeClock()))
    assert off.params == before.params and chan.asks == []
    assert f"| [손님] 합성 앞 대화 {two_by_two[0]}" in body(off)


# ── 사진 학습 ────────────────────────────────────────────────────────────
def photo_chats(chan, first, second):
    """첫 상담은 사진이 온 글이 대화 속에 있고, 둘째 상담은 없다(질문 뒤에 놓인다)."""
    chan.chat("uc-1", *long_chat(6, prefix="a"),
              api_message(f"m-{first}-0", at(1, 9, 30), "user", "합성 사진", files=[{"key": "pub-file/a.jpg"}]),
              api_message("m-uc-1-11", at(1, 9, 31), "user", "합성 질문 하나"),
              api_message("m-uc-1-ans", at(1, 9, 40), "manager", "합성 경첩 안내"))
    chan.chat("uc-2", *long_chat(6, prefix="b"), api_message("m-uc-2-12", at(1, 9, 31), "user", "합성 질문 둘"),
              api_message("m-uc-2-ans", at(1, 9, 40), "manager", "합성 경첩 안내"))


def test_photo_learning_puts_each_photo_where_it_came_in_the_whole_chat(evidence):
    on()
    first, second = evidence
    chan = PagedChannel()
    photo_chats(chan, first, second)
    client = FakeAnthropic({"proposals": []})
    reader = make_reader(chan, FakeClock())
    counts = photo_learning.run_photo_learning(db_session, now=NOW, client=client, reader=reader)
    lines = body(client)
    assert counts["evidence_ok"] == 1 and f"사례 {first} {PHOTO_TALK_HEAD}" in lines
    at_photo = lines.index("| [손님] 합성 사진")
    assert lines[at_photo + 1:at_photo + 3] == [f"|     {FILE_NOTE}", f"| {PHOTO_LINE}"]
    at_question = lines.index("| [손님] 합성 질문 둘")
    assert lines[at_question + 1] == f"| {PHOTO_LINE}"  # 사진이 온 글을 모르면 질문 뒤
    assert not any(line.endswith("손님이 보낸 사진(읽은 것):") for line in lines)  # 전체 대화 속 표시 줄로 옮겼다
    assert lines.index(f"사례 {first} {PHOTO_TALK_HEAD}") < lines.index(f"사례 {first} 손님 글:")


def test_photo_learning_keeps_only_the_newest_cases_per_group(world):
    on(photo_learn_cases=2)
    ids = [done_turn("uc-1", 11), done_turn("uc-2", 12), done_turn("uc-3", 13)]
    (group,) = photo_learning.collect_photo_groups(db_session, NOW, cases_cap=2)
    assert [case["turn_id"] for case in group.cases] == ids[1:]
    client = FakeAnthropic({"proposals": []})
    counts = photo_learning.run_photo_learning(db_session, now=NOW, client=client,
                                               reader=make_reader(PagedChannel(), FakeClock()))
    lines = body(client)
    assert counts["evidence_ok"] == 1 and f"사례 {ids[0]} 손님 글:" not in lines
    assert all(f"사례 {turn_id} 손님 글:" in lines for turn_id in ids[1:])
    assert f"사례 {ids[1]} 손님이 보낸 사진(읽은 것):" in lines  # 대화를 못 읽은 사례는 예전 재료


def test_photo_learning_text_is_unchanged_when_off_or_without_a_reader(world, monkeypatch):
    monkeypatch.setattr(photo_learning, "claim_week", lambda *_a: True)
    on()
    ids = [done_turn("uc-1", 11), done_turn("uc-2", 12), done_turn("uc-3", 13), done_turn("uc-4", 14),
           done_turn("uc-5", 15)]
    chan = PagedChannel()
    photo_chats(chan, *ids[:2])
    before = FakeAnthropic({"proposals": []})
    photo_learning.run_photo_learning(db_session, now=NOW, client=before)  # 읽기 도우미 없음 — 예전 재료 · 다섯 사례 모두
    on(full_talk_messages=0)
    off = FakeAnthropic({"proposals": []})
    photo_learning.run_photo_learning(db_session, now=NOW, client=off, reader=make_reader(chan, FakeClock()))
    assert off.params == before.params and chan.asks == []
    assert all(f"사례 {turn_id} 손님 글:" in body(off) for turn_id in ids)
