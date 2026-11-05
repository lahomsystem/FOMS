"""손님 사진을 질문과 같이 읽기 — 읽기 넓히기(설계서 17.11.1 의 1 · 2 · 사장님 D172).

사진마다 가린 짧은 설명 두 칸(가림 검사 0 이 아니면 그 칸만 비움) · 손님 최근 질문을 같이 보냄 · 미리 읽기가 견적 없이 돎 · 옛 판
(도면만) 결과를 설명이 있는 것처럼 다시 쓰지 않음 · 얼굴로 버린 결과는 판과 상관없이 다시 씀. 미리 읽기가 견적 없이 도는
것은 ``test_cs_image_flow`` 에 있다.

합성 글 · 합성 도면(Pillow) · 가짜 채널톡 · 가짜 모델만(네트워크 0). 전화 꼴은 실행 때 만든다(저장소에 두지 않는다).
"""

from __future__ import annotations

import json

from sqlalchemy import select

from db import db_session
from foms.services.cs_agent import image_brain, image_read
from foms.services.cs_agent import image_rules as ir
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.image_files import FileRef
from foms.services.cs_agent.image_notes import ABOUT_LIMIT, SUMMARY_LIMIT, clean_text
from models import CsAgentImageRead
from tests.domains.test_cs_drafting import channel, customer  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_image_flow import KEY, chan, drawing_chat  # noqa: F401 — chan 은 fixture
from tests.support.cs_agent_fakes import FakeAnthropic, FakeClock, at, keys, make_reader  # noqa: F401
from tests.support.cs_image_support import (
    FakeDownload, answer, encoded, file_item, image_switch, plan_image, room, wall,
)

#: 실행 때 만든 전화 꼴(저장소 글에 번호를 두지 않는다).
PHONE = "0" + "10" + "-" + "4" * 4 + "-" + "7" * 4


def photo(index=0, kind="site_photo", summary="합성 현장 사진 — 붙박이장 문 한 짝이 기울어 있음",
          about="손님이 물은 문 처짐과 같은 자리", confidence="medium"):
    """사진 하나(구조화 출력 ``images[]`` 칸 — 합성 글)."""
    return {"index": index, "kind": kind, "confidence": confidence, "summary": summary, "about_question": about}


def with_photos(*images, **kw):
    """사진 칸이 있는 그림 읽기 답(설치 자리 없음 — 하자 사진 같은 것)."""
    return {**answer(drawing=False, kinds=(), **kw), "images": list(images)}


def rows():
    db_session.expire_all()
    return list(db_session.scalars(select(CsAgentImageRead).order_by(CsAgentImageRead.id)))


# ── 스키마 · 읽기 ────────────────────────────────────────────────────────
def test_each_image_carries_a_confidence_and_two_short_text_fields_and_nothing_else_is_free_text():
    item = ir.image_schema()["properties"]["images"]["items"]
    assert item["required"] == ["index", "kind", "confidence", "summary", "about_question"]
    assert item["additionalProperties"] is False and item["properties"]["summary"] == {"type": "string"}
    assert "maxLength" not in json.dumps(ir.image_schema())  # 구조화 출력이 받지 않는 제약 — 자르기는 코드가


def test_text_fields_are_masked_one_line_capped_and_a_leak_empties_only_that_field():
    got = ir.read_result(json.dumps(with_photos(
        photo(0, summary=f"합성 견적 화면 — 연락처 {PHONE} 가 보임", about="견적 금액을\n다시 물음"),
        photo(1, kind="example_photo", summary="가" * (SUMMARY_LIMIT + 30), about="나" * (ABOUT_LIMIT + 30)))))
    first, second = got.notes
    assert (first.summary, first.about) == ("", "견적 금액을 다시 물음")  # 개인정보 꼴 → 그 칸만 비움 · 한 줄로
    assert (len(second.summary), len(second.about)) == (SUMMARY_LIMIT, ABOUT_LIMIT)
    assert (first.kind, first.confidence, second.index) == ("site_photo", "medium", 1)
    assert PHONE not in json.dumps(ir.result_json(got), ensure_ascii=False)
    assert clean_text(None, 10) == "" and clean_text("  ", 10) == ""


def test_stored_results_round_trip_and_old_drawing_only_results_read_without_text():
    read = ir.read_result(json.dumps(with_photos(photo(0), photo(1, kind="product_screen", about=""))))
    stored = ir.result_json(read)
    assert ir.read_result(json.dumps(stored)) == read  # 가린 글을 다시 가려도 그대로
    assert "about_question" not in stored["images"][1]  # 빈 칸은 싣지 않는다
    old = ir.read_result(json.dumps(answer(room("안방", wall(2700)))))  # 판 1 — 설명 칸 없음
    (note,) = old.notes
    assert (note.kind, note.confidence, note.summary, note.about, note.has_text) == ("floor_plan", "", "", "", False)


def test_the_reader_gets_the_masked_recent_question_and_the_wider_instructions(chan):
    image_switch("note", quote_calc_enabled=False)
    payload = encoded(plan_image())
    customer(chan, "uc-9", text="합성 직원 답 전 첫 글", when=at(2, 8, 0),
             more=[("m-uc-9-a", at(2, 8, 10), "manager", "합성 직원 답", {}),
                   ("m-uc-9-b", at(2, 8, 40), "user", f"문이 이렇게 됐어요 연락은 {PHONE}",
                    {"files": [file_item(chan.store.put("pub-file/door.jpg", payload), payload)]})])
    client = FakeAnthropic(with_photos(photo(0)))
    ref = FileRef("m-uc-9-b", 0, "image/jpeg", len(payload), 1600, 1200, key="pub-file/door.jpg")
    got = image_read.read_batch(db_session, reader=make_reader(chan, FakeClock()), brand="LAHOM", chat_id="uc-9",
                                refs=[ref], turns=[("user", "합성 직원 답 전 첫 글"), ("manager", "합성 직원 답"),
                                                   ("user", f"문이 이렇게 됐어요 연락은 {PHONE}")],
                                cfg=st.read_settings(db_session), now=at(2, 9), owner="test:q", deadline_s=30,
                                still_on=lambda: True, client=client, transport=FakeDownload(chan.store),
                                sleep=lambda _s: None)
    (params,) = client.params
    task = params["messages"][0]["content"][-1]["text"]
    question = task.split("손님 최근 질문(가린 글 — 마지막 직원 답 뒤):\n", 1)[1].split("\n상담 글(", 1)[0]
    assert question.startswith("[손님] 문이 이렇게 됐어요") and PHONE not in task  # 마지막 직원 답 뒤 손님 글만 · 가림
    assert "첫 글" not in question
    assert "summary" in image_brain.INSTRUCTIONS and "about_question" in image_brain.INSTRUCTIONS
    assert got.read.notes[0].summary.startswith("합성 현장 사진")
    (row,) = rows()
    assert row.result["rules_version"] == image_read.RULES_VERSION == 2
    assert row.result["images"][0]["summary"].startswith("합성 현장 사진")


# ── 판 번호 · 다시 쓰기 ──────────────────────────────────────────────────
def _common(chan, client):
    return dict(reader=make_reader(chan, FakeClock()), brand="LAHOM", chat_id="uc-1", turns=[("user", "합성 문의")],
                cfg=st.read_settings(db_session), now=at(2, 9), deadline_s=30, still_on=lambda: True, client=client,
                transport=FakeDownload(chan.store), sleep=lambda _s: None)


def _age(state="done"):
    """줄을 판 1(옛 결과)로 되돌린다 — 설명 칸이 없던 때의 결과."""
    for row in rows():
        row.state, row.result = state, {**{k: v for k, v in row.result.items() if k != "rules_version"},
                                        "rules_version": 1}
    db_session.commit()


def test_a_version_one_result_is_read_again_instead_of_reused(chan):
    image_switch("note")
    drawing_chat(chan)
    client = FakeAnthropic(answer(room("안방", wall(2700))), with_photos(photo(0, kind="floor_plan")))
    ref = FileRef("m-uc-1", 0, "image/jpeg", 10, 1600, 1200, key=KEY)
    image_read.read_batch(db_session, refs=[ref], owner="test:a", **_common(chan, client))
    _age()
    again = image_read.read_batch(db_session, refs=[ref], owner="test:b", **_common(chan, client))
    assert len(client.params) == 2 and not again.reused and again.read.notes[0].has_text
    same_bytes = FileRef("m-uc-1-b", 0, "image/jpeg", 10, 1600, 1200, key=chan.store.put("pub-file/b", chan.store.files[KEY]))
    _age()
    image_read.read_batch(db_session, refs=[same_bytes], owner="test:c", **_common(chan, client))
    assert len(client.params) == 3  # 같은 sha256 다시 쓰기도 옛 판은 쓰지 않는다


def test_a_face_discarded_result_is_reused_whatever_its_version(chan):
    image_switch("note")
    drawing_chat(chan)
    client = FakeAnthropic(answer(personal=("face",)))
    ref = FileRef("m-uc-1", 0, "image/jpeg", 10, 1600, 1200, key=KEY)
    first = image_read.read_batch(db_session, refs=[ref], owner="test:a", **_common(chan, client))
    assert first.discarded
    _age(state="discarded")
    again = image_read.read_batch(db_session, refs=[ref], owner="test:b", **_common(chan, client))
    assert again.reused and again.discarded and len(client.params) == 1  # 얼굴이 보인 사진을 다시 보내지 않는다
