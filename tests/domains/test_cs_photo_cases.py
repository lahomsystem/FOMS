"""읽은 손님 사진 설명을 사례 재료 · 주간 고침 안 재료로 묶기(설계서 17.11.1 의 6 · 사장님 D172).

새 칸 없이 그림 읽기 표(``cs_agent_image_reads``)의 차례 번호(``turn_id``)로 잇는다 — '고침' · '직접 답' 사례에 사진 설명 두 줄까지
(직원 사진 설명 칸과 같은 자리 · 상한) · 그대로 사례 · 옛 판 · 얼굴 · 빈 글 · 새는 글은 빠짐 · 패널이 끔이면 예전 꼴 그대로.

합성 차례 · 합성 그림 읽기 결과(가린 꼴 글)만 — 손님 글 · 그림 · 금액 없음. 전화 꼴은 실행 때 만든다.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.cs_agent import brain_cases, case_material, weekly_fix
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_cases import CASES_PHOTO_HEAD, QUOTE, CaseItem
from foms.services.cs_agent.image_read import RULES_VERSION
from foms.services.cs_agent.image_summaries import summaries_by_turn
from foms.services.cs_agent.knowledge import load_approved
from models import CsAgentImageRead
from tests.domains.test_cs_case_memory import QUESTION, _lines, case_row
from tests.domains.test_cs_drafting import FakeBrain, channel, customer, run  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_edit_learning import edited_case, task
from tests.domains.test_cs_photo_read import PHONE
from tests.domains.test_cs_weekly_fix import NOW as MONDAY, edited, panel
from tests.support.cs_agent_fakes import FakeAnthropic, keys  # noqa: F401 — fixture
from tests.support.cs_image_support import image_switch

SEEN = "합성 현장 사진 — 붙박이장 문 한 짝이 기울어 있음"
ABOUT = "손님이 물은 문 처짐과 같은 자리"


def read_row(turn_id, *, index=0, chat="uc-photo", summary=SEEN, about=ABOUT, kind="site_photo", version=RULES_VERSION,
             state="done", seq=None):
    """차례가 읽은 그림 줄 하나(합성 결과 — 가린 꼴 글)."""
    seq = seq if seq is not None else index
    sha = f"{turn_id:032d}{seq:032d}"
    images = [{"index": i, "kind": kind, "confidence": "medium"} for i in range(index)]
    images.append({"index": index, "kind": kind, "confidence": "medium", "summary": summary, "about_question": about})
    result = {"images": images, "is_drawing": False, "spaces": [], "confidence": "medium", "reasons": [],
              "personal_seen": ["none"], "other_question": False,
              "batch": [f"{turn_id:032d}{i:032d}" for i in range(index)] + [sha], "rules_version": version}
    db_session.add(CsAgentImageRead(brand="LAHOM", chat_id=chat, message_id=f"m-{turn_id}-{seq}", file_index=0,
                                    state=state, sha256=sha, result=result, turn_id=turn_id,
                                    model="claude-sonnet-5-5", read_at=datetime.datetime(2026, 11, 1, 1, 0)))
    db_session.commit()


# ── 읽기(차례 번호로) ─────────────────────────────────────────────────────
def test_summaries_are_current_done_rows_with_text_only(app):
    read_row(1, index=0)
    read_row(1, index=1, kind="example_photo", summary="합성 예시 사진 — 흰색 여닫이 문", about="")
    read_row(2, version=1)  # 옛 판 — 설명이 있는 것처럼 쓰지 않는다
    read_row(3, state="discarded")
    read_row(4, summary="", about="")
    read_row(5, summary=f"연락처 {PHONE}")  # 가림 검사 — 새는 줄은 빈 칸이 된다(다른 칸은 남는다)
    got = summaries_by_turn(db_session, [1, 2, 3, 4, 5, 6])
    assert sorted(got) == [1, 5]
    assert [line.text for line in got[1]] == [f"현장 사진: {SEEN} — {ABOUT}", "예시 사진: 합성 예시 사진 — 흰색 여닫이 문"]
    assert [line.kind for line in got[1]] == ["site_photo", "example_photo"] and got[5][0].text == f"현장 사진: {ABOUT}"
    assert summaries_by_turn(db_session, [1], per_turn=1)[1][0].kind == "site_photo"
    assert summaries_by_turn(db_session, []) == {}


# ── 사례 재료 ────────────────────────────────────────────────────────────
def test_edited_and_direct_cases_carry_up_to_two_photo_lines_and_as_is_cases_do_not(app):
    direct = case_row("c-direct", answer="합성 직접 답")
    plain = case_row("c-plain", answer="합성 그대로 답", outcome="as_is")
    edit = edited_case("c-edit", notes=())
    for row in (direct, plain, edit):
        for index in range(3):
            read_row(row.id, index=index, chat=row.chat_id)
    before = case_material.similar_cases(db_session, "LAHOM", _lines(QUESTION))
    got = case_material.similar_cases(db_session, "LAHOM", _lines(QUESTION), with_photos=True)
    assert [item[:2] for item in got] == [item[:2] for item in before]  # 고르기 · 순서는 같다
    by_answer = {item[1]: item for item in got}
    assert by_answer["합성 그대로 답"] == ("선반 깊이 문의드려요", "합성 그대로 답")  # 그대로 사례는 예전 짝
    for answer in ("합성 직접 답", "합성 고친 답"):
        assert len(by_answer[answer].customer_photos) == brain_cases.MAX_PHOTO_NOTES == 2
        assert by_answer[answer].customer_photos[0] == f"현장 사진: {SEEN} — {ABOUT}"
    assert all(type(item) is tuple for item in before)  # 끄면 예전 꼴 그대로
    brain_cases.case_pairs(got)


def test_photo_lines_render_behind_the_quote_mark_with_their_own_head():
    item = CaseItem("합성 질문", "합성 직접 답", customer_photos=(f"현장 사진: {SEEN}", "상담 글(가린 글 · 오래된 것부터):"))
    lines = task((("다른 질문", "다른 답"), item)).split("\n")
    assert lines[lines.index(brain_cases.CASES_HEAD) + 1] == CASES_PHOTO_HEAD
    assert "사례 2 사람 답:" in lines and "고쳐 보냄" not in "\n".join(lines)  # 직접 답은 '고침' 머리표가 아니다
    head = lines.index("사례 2 손님이 보낸 사진(읽은 것):")
    assert lines[head + 1:head + 3] == [f"{QUOTE}현장 사진: {SEEN}", f"{QUOTE}상담 글(가린 글 · 오래된 것부터):"]
    assert [line for line in lines if line.startswith("상담 글(")] == ["상담 글(가린 글 · 오래된 것부터):"]
    assert CASES_PHOTO_HEAD not in task((("다른 질문", "다른 답"),))


@pytest.mark.parametrize("bad", [
    (CaseItem("q", "a", customer_photos=("가",) * 3),), (CaseItem("q", "a", customer_photos=("가" * 121,)),),
    (CaseItem("q", "a", reason="tone", detail="가" * 200, photo_notes=("나" * 120, "다" * 120),
              customer_photos=("라" * 120, "마" * 120)),) * 3,  # 덧붙은 글 합 상한을 사진 줄도 같이 쓴다
])
def test_photo_lines_share_the_extra_cap_and_bad_shapes_are_refused(bad):
    assert brain_cases.photo_chars(bad[0]) == sum(len(n) for n in bad[0].customer_photos)
    with pytest.raises(ValueError):
        brain_cases.case_pairs(bad)


def test_the_drafting_pass_adds_photo_lines_only_when_the_panel_is_not_off(channel):
    edited_case("c-edit", notes=())
    row = case_row("c-direct", answer="합성 직접 답")
    read_row(row.id, chat="c-direct")
    customer(channel)
    brain_fn = FakeBrain()
    run(channel, brain_fn=brain_fn)
    assert not any(isinstance(item, CaseItem) and item.customer_photos for item in brain_fn.requests[0].cases)
    image_switch("note", quote_calc_enabled=False)
    customer(channel, "uc-2")
    brain_fn = FakeBrain()
    run(channel, brain_fn=brain_fn)
    (request,) = brain_fn.requests
    assert any(isinstance(item, CaseItem) and item.customer_photos for item in request.cases)


# ── 주간 고침 안 재료 ───────────────────────────────────────────────────
def test_weekly_fix_material_carries_the_turn_photo_lines_when_the_panel_is_on(channel):
    panel()
    first, second = edited(1, chat="uc-1", staff=11), edited(2, chat="uc-2", staff=12)
    read_row(first, chat="uc-1")
    (group,) = weekly_fix.collect_groups(db_session, MONDAY)
    assert all(case["customer_photos"] == [] for case in group.cases)  # 끔(처음 값) — 예전 재료 그대로
    (group,) = weekly_fix.collect_groups(db_session, MONDAY, with_photos=True)
    assert [case["customer_photos"] for case in group.cases] == [[f"현장 사진: {SEEN} — {ABOUT}"], []]
    params = weekly_fix.build_params([group], load_approved(db_session, "LAHOM"), cfg=st.read_settings(db_session))
    body = params["messages"][0]["content"][0]["text"].split("\n")
    head = body.index(f"사례 {first} 손님이 보낸 사진(읽은 것):")
    assert body[head + 1] == f"| 현장 사진: {SEEN} — {ABOUT}" and f"사례 {second} 손님이 보낸 사진" not in body
    panel(image_read_mode="note")
    client = FakeAnthropic({"proposals": []})
    counts = weekly_fix.run_weekly_fix(db_session, now=MONDAY, client=client)
    assert counts["evidence_ok"] == 1 and f"| 현장 사진: {SEEN}" in client.params[0]["messages"][0]["content"][0]["text"]

