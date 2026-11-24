"""밤 배우기가 사진 그 자체를 같이 보기(설계서 9.2 · 9.8 — 사장님 11-24) — 손님 사진 · 직원 그림이 대화의 ``▶ 사진 N`` 줄과 같은
번호로 실린다 · 내부 메모 · 봇 파일은 안 받는다 · 얼굴 줄은 안 받는다 · 지문이 다르면 안 싣는다 · 상한(상담 · 묶음) · 같은 그림
한 번만 · 못 받으면 설명 줄로 남고 배우기는 돈다 · 끔(env · 그림 읽기 끔 · 읽기 도우미 없음)이면 모델에 가는 인자가 예전과 같다 ·
가림으로 빠진 사례의 사진은 안 나간다 · 낮 그림 읽기는 직원 파일을 보지 않는다 · 지시문 줄.

합성 그림(Pillow 로 그 자리에서) · 쪽을 넘기는 가짜 채널톡 · 가짜 내려받기 · 가짜 학습 모델만(네트워크 0). 손님 글 · 직원 이름 ·
금액 없음. 얼굴 거르기는 시험마다 '얼굴 없음'으로 바꿔 둔다(진짜 거르기는 :mod:`tests.domains.test_cs_image_prep`).
"""

from __future__ import annotations

import datetime
import hashlib
import io

import pytest
from PIL import Image

from db import db_session
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import handoff_learning_photos as lp
from foms.services.cs_agent import image_brain, image_fetch
from foms.services.cs_agent import image_prep as prep
from foms.services.cs_agent.drafting_read import parse_lines, read_lines
from foms.services.cs_agent.handoff_learning_photos import SEEN, BatchPhotos, batch_photos
from foms.services.cs_agent.handoff_learning_place import SYSTEM as PLACE_SYSTEM
from foms.services.cs_agent.handoff_learning_prompt import INSTRUCTIONS, build_params
from foms.services.cs_agent.image_fetch import pending_files
from foms.services.cs_agent.image_read import RULES_VERSION
from foms.services.cs_agent.settings import read_settings
from models import CsAgentImageRead
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_handoff_learning import admin, handed, on, run  # noqa: F401 — admin 은 fixture
from tests.domains.test_cs_photo_read import PHONE
from tests.support.cs_agent_fakes import FakeAnthropic, FakeClock, api_message, keys, make_reader  # noqa: F401
from tests.support.cs_image_support import FakeDownload, FileStore, encoded, file_item, plan_image
from tests.support.cs_talk_support import START, PagedChannel, cfg

SUMMARY = "합성 평면도 — 방 한쪽 코너에 기둥 자리 표시"


@pytest.fixture(autouse=True)
def no_faces(monkeypatch):
    """얼굴 거르기 '없음'(합성 도면) · env 끔 칸 지움."""
    monkeypatch.setattr(prep, "count_faces", lambda image: 0)
    monkeypatch.delenv(lp.ENV, raising=False)


@pytest.fixture
def world(admin, monkeypatch):  # noqa: F811
    """가짜 채널톡(파일 서명 주소 포함) · 가짜 내려받기."""
    store = FileStore()
    chan = PagedChannel(store)
    monkeypatch.setattr(image_fetch.requests, "get", FakeDownload(store))
    return store, chan


def picture(seed: int) -> bytes:
    """합성 도면 JPEG(씨앗마다 다른 바이트)."""
    return encoded(plan_image(1600 + seed * 8, 1200), "JPEG")


def when(minute: int) -> datetime.datetime:
    return START + datetime.timedelta(minutes=minute)


def photo_msg(store, msg_id, minute, person, key, data, **extra):
    """파일 하나가 붙은 글(가짜 채널톡 · 파일 저장소에 같이)."""
    store.put(key, data)
    return api_message(msg_id, when(minute), person, "합성 그림", files=[file_item(key, data)], **extra)


def image_row(chat, message_id, data=None, *, state="done", skip=None, sha=None, summary=SUMMARY):
    """그림 읽기 표 줄 하나(합성 결과 — 가린 꼴 글). 지문은 ``data`` 의 sha256(또는 ``sha``)."""
    digest = sha if sha is not None else hashlib.sha256(data).hexdigest() if data is not None else None
    result = None
    if state == "done":
        result = {"images": [{"index": 0, "kind": "floor_plan", "confidence": "medium", "summary": summary,
                              "about_question": ""}], "is_drawing": False, "spaces": [], "confidence": "medium",
                  "reasons": [], "personal_seen": ["none"], "other_question": False, "batch": [digest],
                  "rules_version": RULES_VERSION}
    db_session.add(CsAgentImageRead(brand="LAHOM", chat_id=chat, message_id=message_id, file_index=0, state=state,
                                    skip_code=skip, sha256=digest, result=result,
                                    read_at=datetime.datetime(2026, 11, 1, 1, 0)))
    db_session.commit()


def content(client, index=0):
    return client.params[index]["messages"][0]["content"]


def lines_of(client, index=0):
    return content(client, index)[-1]["text"].split("\n")


def labels(client, index=0):
    """사진 블록 앞 글(``사진 N``)들 — 그림 블록과 짝이 맞는지도 본다."""
    blocks = content(client, index)[:-1]
    assert [b["type"] for b in blocks[1::2]] == ["image"] * (len(blocks) // 2)
    assert all(b["source"]["type"] == "base64" and b["source"]["media_type"] == "image/jpeg" for b in blocks[1::2])
    return [b["text"] for b in blocks[0::2]]


def seen_line(number, who, summary=None):
    return f"| ▶ 사진 {number} ({who} · {SEEN})" + (f" 평면도: {summary}" if summary else "")


def mixed_chat(store, chan, chat="uc-1"):
    """손님 도면(읽은 줄 있음) · 직원이 선을 그은 그림 · 내부 메모 파일 · 봇 파일 · 손님 질문 · 직원 답."""
    customer = picture(1)
    chan.chat(chat,
              photo_msg(store, f"{chat}-000", 0, "user", f"{chat}/plan.jpg", customer),
              photo_msg(store, f"{chat}-001", 1, "manager", f"{chat}/marked.jpg", picture(2)),
              photo_msg(store, f"{chat}-002", 2, "manager", f"{chat}/memo.jpg", picture(3), private=True),
              photo_msg(store, f"{chat}-003", 3, "bot", f"{chat}/bot.jpg", picture(4)),
              api_message(f"{chat}-004", when(4), "user", "합성 질문 — 코너도 쓸 수 있나요"),
              api_message(f"{chat}-005", when(5), "manager", "합성 답 — 그 자리는 어렵습니다"))
    image_row(chat, f"{chat}-000", customer)
    return customer


# ── 싣기 · 번호 ──────────────────────────────────────────────────────────
def test_customer_and_staff_pictures_ride_in_order_with_the_numbers_of_the_talk_lines(world):
    store, chan = world
    on(image_read_mode="note")
    mixed_chat(store, chan)
    case = handed("uc-1", anchor="uc-1-004")
    client = FakeAnthropic({"proposals": [], "ontology": []})
    counts = run(client, reader=make_reader(chan, FakeClock()))
    lines = lines_of(client)
    assert labels(client) == ["사진 1", "사진 2"] and (counts["photos"], counts["photo_skipped"]) == (2, {})
    first = next(i for i, line in enumerate(lines) if line.startswith("| [손님] 합성 그림"))
    assert lines[first + 2] == seen_line(1, "손님", SUMMARY)  # 첨부 표시 줄 다음 — 그 사진이 온 글 자리
    staff = next(i for i, line in enumerate(lines) if line.startswith("| [직원] 합성 그림"))
    assert lines[staff + 2] == seen_line(2, "직원")
    assert sorted(store.signed) == ["uc-1/marked.jpg", "uc-1/plan.jpg"]  # 내부 메모 · 봇 파일은 받지 않는다
    assert len(chan.asks) == 1  # 사진 고르기와 전체 대화가 같은 쪽을 한 번만 읽는다
    assert counts["sent"] == 1 and f"사례 {case} 손님 글:" in lines


def test_face_rows_and_a_changed_fingerprint_never_ride(world):
    store, chan = world
    on(image_read_mode="note")
    ok, face, checked, changed = picture(1), picture(2), picture(3), picture(4)
    chan.chat("uc-1",
              photo_msg(store, "uc-1-000", 0, "user", "k/ok.jpg", ok),
              photo_msg(store, "uc-1-001", 1, "user", "k/face.jpg", face),
              photo_msg(store, "uc-1-002", 2, "user", "k/checked.jpg", checked),
              photo_msg(store, "uc-1-003", 3, "user", "k/changed.jpg", changed),
              api_message("uc-1-004", when(4), "user", "합성 질문"))
    image_row("uc-1", "uc-1-001", face, state="discarded", skip="discarded_face")
    image_row("uc-1", "uc-1-002", checked, state="skipped", skip="skipped_face_check")
    image_row("uc-1", "uc-1-003", sha="0" * 64)  # 표의 지문이 다시 받은 것과 다르다
    handed("uc-1", anchor="uc-1-004")
    client = FakeAnthropic({"proposals": [], "ontology": []})
    counts = run(client, reader=make_reader(chan, FakeClock()))
    assert labels(client) == ["사진 1"] and counts["photo_skipped"] == {"face": 2, "sha_mismatch": 1}
    assert "k/face.jpg" not in store.signed and "k/checked.jpg" not in store.signed  # 얼굴 줄은 받지도 않는다
    text = "\n".join(lines_of(client))
    assert text.count(SEEN) == 1 and "| ▶ 사진 2 (손님) 평면도: " + SUMMARY in text  # 지문이 다르면 설명 줄로만


def test_caps_per_chat_and_per_batch_keep_customer_pictures_first_and_the_newest(world, monkeypatch):
    store, chan = world
    monkeypatch.setattr(lp, "CUSTOMER_CAP", 2)
    monkeypatch.setattr(lp, "STAFF_CAP", 1)
    monkeypatch.setattr(lp, "BATCH_CAP", 3)
    chan.chat("uc-1", *(photo_msg(store, f"a-{i}", i, "user", f"a/{i}.jpg", picture(i)) for i in range(3)),
              photo_msg(store, "a-s1", 4, "manager", "a/s1.jpg", picture(10)),
              photo_msg(store, "a-s2", 5, "manager", "a/s2.jpg", picture(11)))
    chan.chat("uc-2", photo_msg(store, "b-0", 6, "user", "b/0.jpg", picture(20)),
              photo_msg(store, "b-s", 7, "manager", "b/s.jpg", picture(21)))
    got = batch_photos(db_session, make_reader(chan, FakeClock()), cfg(image_read_mode="note"),
                       [{"chat_id": "uc-1"}, {"chat_id": "uc-2"}], {}, brand="LAHOM", transport=FakeDownload(store))
    assert got.skipped == {"customer_cap": 1, "batch_cap": 3}  # 직원 그림은 손님 사진 3장 뒤라 묶음 상한
    assert sorted(store.signed) == ["a/1.jpg", "a/2.jpg", "b/0.jpg"]  # 새 사진부터
    assert got.marks == {"uc-1": {"a-1": [f"▶ 사진 1 (손님 · {SEEN})"], "a-2": [f"▶ 사진 2 (손님 · {SEEN})"]},
                         "uc-2": {"b-0": [f"▶ 사진 3 (손님 · {SEEN})"]}}  # 번호는 묶음 전체에서 하나 · 대화 순서
    monkeypatch.setattr(lp, "BATCH_CAP", 20)
    store.signed.clear()
    more = batch_photos(db_session, make_reader(chan, FakeClock()), cfg(image_read_mode="note"),
                        [{"chat_id": "uc-1"}], {}, brand="LAHOM", transport=FakeDownload(store))
    assert more.skipped == {"customer_cap": 1, "staff_cap": 1} and "a/s2.jpg" in store.signed  # 직원 그림도 새 것부터


def test_the_same_picture_rides_once_and_every_line_points_at_it(world, monkeypatch):
    store, chan = world
    shared = picture(5)  # 여러 손님에게 보낸 구성표
    for chat in ("uc-1", "uc-2"):
        chan.chat(chat, photo_msg(store, f"{chat}-s", 1, "manager", f"{chat}/table.jpg", shared),
                  api_message(f"{chat}-q", when(2), "user", "합성 질문"))
    got = batch_photos(db_session, make_reader(chan, FakeClock()), cfg(image_read_mode="note"),
                       [{"chat_id": "uc-1"}, {"chat_id": "uc-2"}], {}, brand="LAHOM", transport=FakeDownload(store))
    line = f"▶ 사진 1 (직원 · {SEEN})"
    assert got.marks == {"uc-1": {"uc-1-s": [line]}, "uc-2": {"uc-2-s": [line]}} and list(got.items) == [1]
    images, sent, skipped = got.pick([[f"| {line}"], [f"| {line}"]])
    assert (len(images), sent, skipped) == (2, 1, {})
    assert prep.LONG_EDGE == 2000 and max(Image.open(io.BytesIO(got.items[1].data)).size) == lp.LONG_EDGE
    monkeypatch.setattr(lp, "STAFF_CAP", 2)  # 같은 그림은 상한을 쓰지 않는다
    chan.chat("uc-1", photo_msg(store, "x-0", 0, "manager", "x/other.jpg", picture(6)),
              photo_msg(store, "x-1", 1, "manager", "x/a.jpg", shared), photo_msg(store, "x-2", 2, "manager", "x/b.jpg", shared))
    again = batch_photos(db_session, make_reader(chan, FakeClock()), cfg(image_read_mode="note"), [{"chat_id": "uc-1"}],
                         {}, brand="LAHOM", transport=FakeDownload(store))
    assert again.skipped == {} and sorted(again.items) == [1, 2]
    assert again.marks["uc-1"]["x-1"] == again.marks["uc-1"]["x-2"] == [f"▶ 사진 2 (직원 · {SEEN})"]


def test_a_failed_download_keeps_the_description_line_and_learning_goes_on(world):
    store, chan = world
    on(image_read_mode="note")
    lost = picture(1)
    chan.chat("uc-1", api_message("uc-1-000", when(0), "user", "합성 그림", files=[file_item("k/lost.jpg", lost)]),
              api_message("uc-1-001", when(1), "user", "합성 질문"))
    image_row("uc-1", "uc-1-000", lost)
    handed("uc-1", anchor="uc-1-001")
    client = FakeAnthropic({"proposals": [], "ontology": []})
    counts = run(client, reader=make_reader(chan, FakeClock()))
    assert len(content(client)) == 1 and counts["sent"] == 1 and counts["halted"] is None
    assert counts["photo_skipped"] == {"fetch_failed": 1} and counts["photos"] == 0
    assert f"| ▶ 사진 1 (손님) 평면도: {SUMMARY}" in lines_of(client)


def test_a_broken_picture_step_falls_back_to_the_old_lines(world, monkeypatch):
    store, chan = world
    mixed_chat(store, chan)
    monkeypatch.setattr(lp, "_gather", lambda *_a, **_k: 1 / 0)
    base = {"uc-1": {"uc-1-000": ["▶ 사진 1 (손님) 예전 줄"]}}
    reader = make_reader(chan, FakeClock())
    got = batch_photos(db_session, reader, cfg(image_read_mode="note"), [{"chat_id": "uc-1"}], base, brand="LAHOM")
    assert (got.marks, got.reader, got.items, got.skipped) == (base, reader, {}, {"error": 1})
    assert "uc-1" not in repr(got) and "plan.jpg" not in repr(got)


# ── 끄기 · 가림 ──────────────────────────────────────────────────────────
def test_switched_off_photos_leave_the_model_arguments_as_before(world, monkeypatch):
    store, chan = world
    mixed_chat(store, chan)
    handed("uc-1", anchor="uc-1-004")
    monkeypatch.setattr(hl, "used_ids", lambda _session: frozenset())  # 같은 사례를 여러 번 읽힌다
    monkeypatch.setattr(hl, "claim_day", lambda *_a, **_k: True)

    def once(**panel):
        on(**panel)
        client = FakeAnthropic({"proposals": [], "ontology": []})
        run(client, reader=make_reader(chan, FakeClock()))
        return client.params[0]

    with monkeypatch.context() as old:  # 예전 길 — 사진 모듈이 없던 때
        old.setattr(hl, "batch_photos", lambda _s, reader, _c, _cases, base, **_k: BatchPhotos(marks=base, reader=reader))
        before = once(image_read_mode="note")
    assert len(before["messages"][0]["content"]) == 1
    monkeypatch.setenv(lp.ENV, "0")
    assert once(image_read_mode="note") == before and store.signed == []
    monkeypatch.delenv(lp.ENV)
    assert once() == before and store.signed == []  # 패널 '그림 읽기' 끔(처음 값)
    on(image_read_mode="note")
    client = FakeAnthropic({"proposals": [], "ontology": []})
    run(client)  # 읽기 도우미 없음
    assert len(content(client)) == 1 and store.signed == []


def test_build_params_without_pictures_is_one_text_block_byte_for_byte(admin):  # noqa: F811
    settings = read_settings(db_session, log=False)
    plain = build_params([["사례 1 합성:"]], [], [], model="claude-sonnet-5-5", cfg=settings)
    assert build_params([["사례 1 합성:"]], [], [], model="claude-sonnet-5-5", cfg=settings, images=()) == plain
    assert [block["type"] for block in plain["messages"][0]["content"]] == ["text"]
    pics = [{"type": "text", "text": "사진 1"}, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                                          "data": "AAAA"}}]
    with_pics = build_params([["사례 1 합성:"]], [], [], model="claude-sonnet-5-5", cfg=settings, images=pics)
    assert with_pics["messages"][0]["content"] == [*pics, *plain["messages"][0]["content"]]
    assert {k: v for k, v in with_pics.items() if k != "messages"} == {k: v for k, v in plain.items() if k != "messages"}


def test_pictures_of_a_mask_dropped_case_never_leave(world):
    store, chan = world
    on(image_read_mode="note")
    for chat, seed in (("uc-1", 1), ("uc-3", 2)):
        chan.chat(chat, photo_msg(store, f"{chat}-000", 0, "user", f"{chat}/p.jpg", picture(seed)),
                  api_message(f"{chat}-001", when(1), "user", "합성 질문"))
    handed("uc-1", anchor="uc-1-001")
    handed("uc-3", anchor="uc-3-001", reply=f"합성 답 {PHONE}")  # 가림 검사에 걸린다
    client = FakeAnthropic({"proposals": [], "ontology": []})
    counts = run(client, reader=make_reader(chan, FakeClock()))
    assert counts["mask_dropped"] == 1 and counts["sent"] == 1
    assert len(labels(client)) == 1 and counts["photo_skipped"] == {"not_shown": 1}
    assert "uc-3" not in "\n".join(lines_of(client))


# ── 낮 그림 읽기 · 지시문 ────────────────────────────────────────────────
def test_day_reading_still_sees_customer_files_only(world):
    store, chan = world
    mixed_chat(store, chan)
    items = chan.messages["uc-1"]
    every = parse_lines("LAHOM", "uc-1", items, staff_files=True)
    assert [line.meta.message_id for line in every if line.files] == ["uc-1-000", "uc-1-001"]  # 메모 · 봇은 늘 없음
    plain = parse_lines("LAHOM", "uc-1", items)
    assert [line.meta.message_id for line in plain if line.files] == ["uc-1-000"]
    assert pending_files(every, limit=6) == []  # 마지막 직원 답 뒤 손님 파일만
    staff_then_customer = [every[1], *every[2:4], every[0]]  # 파일이 붙은 직원 글 · 메모 · 봇 뒤에 손님 사진
    assert [ref.key for ref in pending_files(staff_then_customer, limit=6)] == ["uc-1/plan.jpg"]  # 직원 파일은 안 본다
    day = read_lines(make_reader(chan, FakeClock()), "LAHOM", "uc-1")
    assert [line.meta.message_id for line in day if line.files] == ["uc-1-000"]


def test_the_instructions_carry_the_picture_and_condition_lines():
    assert "17. 사례 글 앞에 붙은 사진(「사진 N」)은 대화의 ▶ 사진 N 줄 자리에 손님 · 직원이 보낸 사진 그 자체다." in INSTRUCTIONS
    assert "사진 속 글자(단지명 · 동호수 · 주소 · 이름 · 전화)는 옮겨 적지 않는다." in INSTRUCTIONS
    assert "18. 그 집 구조(기둥 · 보 · 배관 자리 · 단내림 · 창 · 문) · 사진 때문에 된다 · 안 된다고 한 말은 그 조건을" in INSTRUCTIONS
    assert "조건이 대화 · 사진에서 보이지 않으면 내지 않는다." in INSTRUCTIONS
    assert "조건 없이 적힌 그 집 구조 · 현장 한 곳의 판단" in PLACE_SYSTEM
    assert "구조물(기둥 · 보 · 배관 자리 · 단내림 · 창 · 문)은 그 이름으로 적는다" in image_brain.INSTRUCTIONS
    assert "엑스 표시 상자 · 칠한 네모는 기둥 · 설비 자리일 수 있다" in image_brain.INSTRUCTIONS
    assert RULES_VERSION == 2  # 답 꼴이 같다 — 판 번호를 올리면 지난 30일 설명이 배우기에서 빠진다
