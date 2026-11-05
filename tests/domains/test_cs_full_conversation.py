"""상담 전체 대화(설계서 17.11.2 · 사장님 D173) — 쪽 넘김 · 글 수 · 자 수 상한 · 줄임 표시 · 가림 검사 · 사진 표시 자리 · 읽기
실패면 예전 재료 · 끔이면 글자까지 지금과 같음 · 초안 때 그림 읽기에 전체 대화(초안 두뇌는 그대로 30줄).

합성 글('합성 글 N') · 합성 도면(Pillow) · 쪽을 넘기는 가짜 채널톡 · 가짜 모델만(네트워크 0). 전화 꼴은 실행 때 만든다.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.cs_agent import full_conversation as fc
from foms.services.cs_agent import image_read
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.drafting_read import CONVERSATION_LIMIT, FILE_NOTE, conversation, read_lines
from foms.services.cs_agent.image_brain import FULL_HEAD
from foms.services.cs_agent.image_fetch import pending_files
from foms.services.cs_agent.masking import mask
from tests.domains.test_cs_drafting import channel, customer  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_image_flow import drafted
from tests.domains.test_cs_photo_read import PHONE, photo, with_photos
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    CODE_TEXT, FakeAnthropic, FakeClock, api_message, at, keys, make_reader,
)
from tests.support.cs_image_support import FakeDownload, encoded, file_item, image_switch, plan_image
from tests.support.cs_talk_support import START, PagedChannel, cfg, long_chat

OLD_HEAD = "상담 글(가린 글 · 오래된 것부터):"
PICTURE = "▶ 그림 0 (이번에 보낸 그림)"


def talk_of(chan, chat="uc-1", **values):
    return fc.read_talk(make_reader(chan, FakeClock()), "LAHOM", chat, cfg(**values))


# ── 쪽 넘김 · 글 수 상한 ─────────────────────────────────────────────────
@pytest.mark.parametrize("style, token", [("cursor", "cursor"), ("since", "since")])
def test_pages_are_read_newest_first_to_the_start_and_returned_oldest_first(keys, style, token):
    chan = PagedChannel(style=style)
    chan.chat("uc-1", *long_chat(120))
    talk = talk_of(chan)
    assert [text for _, text in talk.turns] == [f"합성 글 {i:03d}" for i in range(120)] and talk.more is False
    assert [role for role, _ in talk.turns[:2]] == ["user", "manager"] and talk.ids[0] == "m-000"
    assert chan.asks == [{"limit": 50, "sortOrder": "desc"}, {"limit": 50, "sortOrder": "desc", token: "50"},
                         {"limit": 50, "sortOrder": "desc", token: "100"}]


def test_the_message_cap_stops_paging_keeps_the_newest_and_marks_the_front(keys):
    chan = PagedChannel()
    chan.chat("uc-1", *long_chat(120))
    talk = talk_of(chan, full_talk_messages=70)
    assert [ask["limit"] for ask in chan.asks] == [50, 20] and len(talk.turns) == 70 and talk.more is True
    assert talk.turns[0][1] == "합성 글 050"
    assert fc.talk_text(talk, limit=100_000).split("\n")[0] == "(앞 대화 줄임)"


def test_odd_page_shapes_end_after_one_page():
    params = {"limit": 50, "sortOrder": "desc"}
    assert fc.next_page({"nextCursor": "c2", "hasNext": False}, params) is None
    assert fc.next_page({"nextCursor": "c2"}, {**params, "cursor": "c2"}) is None  # 같은 표지 — 끝없이 돌지 않는다
    assert fc.next_page({"next": 17300}, params) == {**params, "since": "17300"}
    assert fc.next_page({"messages": []}, params) is None and fc.next_page({"nextCursor": " "}, params) is None


# ── 거르기 · 가림 ────────────────────────────────────────────────────────
def test_lines_follow_the_draft_material_rules_and_are_masked(keys):
    chan = PagedChannel()
    file_msg = api_message("m-file", at(2, 8, 5), "user", "합성 사진이에요", files=[{"key": "pub-file/a.jpg"}])
    chan.chat("uc-1", api_message("m-a", at(2, 8), "user", f"합성 연락처 {PHONE}"),
              api_message("m-memo", at(2, 8, 1), "manager", "합성 내부 메모", options=["private"]),
              api_message("m-log", at(2, 8, 2), "bot", "합성 기록", log={"action": "open"}),
              api_message("m-bot", at(2, 8, 3), "bot", "합성 자동 안내"),
              api_message("m-code", at(2, 8, 4), "user", CODE_TEXT), file_msg,
              api_message("m-b", at(2, 8, 6), "manager", "합성 직원 답"))
    talk = talk_of(chan)
    expected = [(role, mask(text).strip()) for role, text in conversation(read_lines(make_reader(chan, FakeClock()),
                                                                                     "LAHOM", "uc-1"))]
    assert list(talk.turns) == expected and talk.ids == ("m-a", "m-file", "m-b")
    assert PHONE not in str(talk.turns) and talk.turns[1][1] == f"합성 사진이에요\n{FILE_NOTE}"


def test_a_mask_leak_anywhere_drops_the_whole_talk(keys, monkeypatch):
    chan = PagedChannel()
    chan.chat("uc-1", api_message("m-old", START, "user", f"합성 연락처 {PHONE}"), *long_chat(60, prefix="n"))
    monkeypatch.setattr(fc, "mask", lambda text: text)  # 가림 규칙 구멍을 꾸민다 — 검사가 막아야 한다
    assert talk_of(chan) is None
    monkeypatch.undo()
    talk = fc.Talk((("user", "합성 글"),), ("m-1",))
    assert fc.talk_text(talk, limit=1000, marks={"m-1": [f"▶ 사진 1 (손님) 연락처 {PHONE}"]}) is None


# ── 실패는 예전 재료로 ───────────────────────────────────────────────────
def test_a_failed_first_page_is_none_and_a_failed_later_page_keeps_what_was_read(keys):
    first = PagedChannel(fail=1)
    first.chat("uc-1", *long_chat(120))
    assert talk_of(first) is None
    later = PagedChannel(fail=2)
    later.chat("uc-1", *long_chat(120))
    talk = talk_of(later)
    assert len(talk.turns) == 50 and talk.more is True and talk.turns[-1][1] == "합성 글 119"


def test_off_reads_nothing(keys):
    chan = PagedChannel()
    chan.chat("uc-1", *long_chat(10))
    reader = make_reader(chan, FakeClock())
    off = cfg(full_talk_messages=0)
    assert fc.read_talk(reader, "LAHOM", "uc-1", off) is None and fc.picture_talk(reader, "LAHOM", "uc-1", off) is None
    assert fc.case_talks(reader, off, [{"turn_id": 1, "chat_id": "uc-1"}], brand="LAHOM") == {}
    assert fc.case_talks(None, cfg(), [{"turn_id": 1, "chat_id": "uc-1"}], brand="LAHOM") == {}  # 읽기 도우미 없음
    assert chan.asks == []
    assert fc.read_talk(reader, "LAHOM", "uc-1", cfg(), left=lambda: 0) is None and chan.asks == []  # 시간이 없으면 읽지 않음


# ── 자 수 상한 · 줄임 표시 · 사진 표시 자리 ───────────────────────────────
def test_the_char_cap_drops_from_the_front_with_one_cut_line():
    talk = fc.Talk(tuple(("user", f"합성 글 {i}") for i in range(10)), tuple(f"m-{i}" for i in range(10)))
    lines = fc.talk_text(talk, limit=len("합성 글 0") * 4).split("\n")
    assert lines == ["(앞 대화 6줄 줄임)", "[손님] 합성 글 6", "[손님] 합성 글 7", "[손님] 합성 글 8", "[손님] 합성 글 9"]
    assert fc.talk_text(talk, limit=100_000).split("\n")[0] == "[손님] 합성 글 0"  # 줄인 것이 없으면 표시 없음
    short = fc.Talk(talk.turns, talk.ids, more=True)
    assert fc.talk_text(short, limit=len("합성 글 0") * 4).split("\n")[0] == "(앞 대화 6줄 넘게 줄임)"
    huge = fc.Talk((("user", "가" * 50),), ("m-0",))
    assert fc.talk_text(huge, limit=20) == "[손님] " + "가" * 20  # 마지막 글 하나가 넘으면 그 글을 자른다


def test_photo_marks_sit_after_their_message_else_after_the_anchor_else_at_the_end():
    talk = fc.Talk((("user", "합성 질문"), ("user", f"합성 사진\n{FILE_NOTE}"), ("manager", "합성 답")),
                   ("m-q", "m-p", "m-a"))
    marks = {"m-p": ["▶ 사진 1 (손님) 현장 사진: 합성"], "m-gone": ["▶ 사진 2 (손님) 예시 사진: 합성"]}
    lines = fc.talk_text(talk, limit=1000, marks=marks, anchor="m-q").split("\n")
    assert lines == ["[손님] 합성 질문", "▶ 사진 2 (손님) 예시 사진: 합성", "[손님] 합성 사진", f"    {FILE_NOTE}",
                     "▶ 사진 1 (손님) 현장 사진: 합성", "[직원] 합성 답"]
    tail = fc.talk_text(talk, limit=1000, marks=marks, anchor="m-unknown").split("\n")
    assert tail[-1] == "▶ 사진 2 (손님) 예시 사진: 합성"
    assert fc.case_limit(cfg(), 1) == 12000 and fc.case_limit(cfg(), 30) == 4000 and fc.case_limit(cfg(), 200) == 2000


# ── 초안 때 그림 읽기 ────────────────────────────────────────────────────
@pytest.fixture
def paged(channel):  # noqa: F811
    return PagedChannel()


def photo_chat(chan, chat="uc-1", count=60):
    """긴 상담(합성 글 ``count`` 개) 끝에 손님이 사진과 글을 보냄 — 상태 표 · 가짜 채널톡에 같은 글."""
    payload = encoded(plan_image())
    item = file_item(chan.store.put(f"pub-file/{chat}.jpg", payload), payload)
    more = [(f"m-{i:03d}", START + datetime.timedelta(minutes=i), "user" if i % 2 == 0 else "manager",
             f"합성 글 {i:03d}", {}) for i in range(1, count)]
    more += [("m-photo", at(2, 8, 45), "user", "합성 사진 보내요", {"files": [item]}),
             ("m-ask", at(2, 8, 50), "user", "합성 문이 기울었어요 고칠 수 있나요", {})]
    customer(chan, chat, text="합성 글 000", when=START, more=more)


def batch(chan, client, settings, chat="uc-1"):
    """초안 차례처럼 — 최근 글 한 쪽을 읽고 그림 묶음 읽기(전체 대화 읽기 함수는 패널 값대로)."""
    reader = make_reader(chan, FakeClock())
    lines = read_lines(reader, "LAHOM", chat)
    return image_read.read_batch(db_session, reader=reader, brand="LAHOM", chat_id=chat,
                                 refs=pending_files(lines, limit=4), turns=conversation(lines), cfg=settings,
                                 now=at(2, 9), owner="test:talk", deadline_s=60, still_on=lambda: True, client=client,
                                 transport=FakeDownload(chan.store), sleep=lambda _s: None,
                                 full_talk=fc.picture_talk(reader, "LAHOM", chat, settings))


def task_of(client):
    return client.params[0]["messages"][0]["content"][-1]["text"]


def test_the_image_reader_gets_the_whole_chat_with_the_picture_in_place(paged):
    image_switch("note", quote_calc_enabled=False)
    photo_chat(paged)
    client = FakeAnthropic(with_photos(photo(0)))
    got = batch(paged, client, st.read_settings(db_session))
    task = task_of(client)
    lines = task.split("\n")
    at_photo = lines.index("[손님] 합성 사진 보내요", lines.index(FULL_HEAD))  # 질문 칸 말고 전체 대화 속 자리
    assert got.read is not None and FULL_HEAD in task and OLD_HEAD not in task
    assert lines[at_photo + 1:at_photo + 3] == [f"    {FILE_NOTE}", PICTURE]
    assert "[손님] 합성 글 000" in lines and lines[-1] == "[손님] 합성 문이 기울었어요 고칠 수 있나요"
    assert "손님 최근 질문(가린 글 — 마지막 직원 답 뒤):\n[손님] 합성 사진 보내요" in task  # 질문 칸은 그대로
    assert [ask.get("cursor") for ask in paged.asks] == [None, None, "50"]  # 초안 글 한 쪽 + 전체 대화 두 쪽


@pytest.mark.parametrize("why", ["off", "read_error", "mask_hole"])
def test_off_failure_or_a_mask_hole_falls_back_to_the_recent_thirty_lines(paged, monkeypatch, why):
    image_switch("note", quote_calc_enabled=False, full_talk_messages=0 if why == "off" else 300)
    photo_chat(paged)
    if why == "mask_hole":  # 가장 오래된 글에 가림 구멍(꾸밈) — 최근 30줄 밖이라 예전 재료는 멀쩡하다
        paged.messages["uc-1"].insert(0, api_message("m-hole", START - datetime.timedelta(hours=1), "user",
                                                     f"합성 연락처 {PHONE}"))
        monkeypatch.setattr(fc, "mask", lambda text: text)
    paged.fail = 2 if why == "read_error" else None  # 초안 글 한 쪽은 되고 전체 대화 첫 쪽이 실패
    client = FakeAnthropic(with_photos(photo(0)))
    got = batch(paged, client, st.read_settings(db_session))
    task = task_of(client)
    assert got.read is not None and OLD_HEAD in task and FULL_HEAD not in task and PHONE not in task
    assert "합성 글 031" not in task and "[손님] 합성 글 032" in task and PICTURE not in task
    assert len(paged.asks) == {"off": 1, "read_error": 2, "mask_hole": 3}[why]


def test_the_draft_brain_keeps_thirty_lines_while_the_image_reader_sees_the_whole_chat(paged):
    image_switch("draft", quote_calc_enabled=False)
    photo_chat(paged)
    client = FakeAnthropic(with_photos(photo(0)))
    brain_fn, _poster, _ = drafted(paged, client)
    (request,) = brain_fn.requests
    assert len(request.messages) == CONVERSATION_LIMIT and "합성 글 000" not in str(request.messages)
    assert FULL_HEAD in task_of(client) and "[손님] 합성 글 000" in task_of(client).split("\n")
