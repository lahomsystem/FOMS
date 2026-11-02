"""견적 — 손님이 규격 모름 · 도면 참고라 하고 그림을 보냈으면 가로를 다시 묻지 않는다(운영 11-02 지적 · 설계서 17.4 의 5).

운영 상담: 손님이 앞서 집 도면 그림을 보내고 '견적도 봐 주세요 / 규격 모름(도면 참고) / … / (다른 물음)'이라 썼는데, 초안이
'설치하실 벽의 가로 길이(mm)를 알려 주시면'이라고 다시 물었다. 고친 길: 뽑기 칸 ``size_in_attachment`` → 계산 결과
``size_in_drawing``(묻는 줄 없음 · 금액 허용 없음 · 직원 참고 줄) → 두뇌 기본 지시 11번(이미 준 · 모른다고 한 것을 다시 묻지
않는다). 대화는 그 상담을 가린 **합성 글**이다(실제 손님 글 · 금액 없음). 그림 읽기는 다음 일이다(모델은 그림을 못 본다).
"""

from __future__ import annotations

import functools
import json
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.cs_agent import brain_prompt as bp, quote_brain as qb, quote_calc as qc, quote_record as qrec
from foms.services.cs_agent import quote_step as qs
from foms.services.cs_agent.drafting_read import FILE_NOTE, MEMO_NOTE_HEAD, MEMO_QUOTE_HEAD, memo_snippets, memo_text
from tests.domains.test_cs_drafting import (  # noqa: F401 — channel 은 fixture
    CUSTOMER, FakeBrain, FakePoster, channel, customer, result, run, turn,
)
from tests.domains.test_cs_quote import _request, brain_env  # noqa: F401 — brain_env 는 fixture
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys  # noqa: F401 — keys 는 fixture
from tests.support.cs_quote_support import MOLD, NOW, FakeQuoter, ask, catalog, evaluate, quoting, space, switch, won

#: 그 상담을 가린 합성 글 — 견적 · 규격 모름(위 그림 참고) · 다른 물음 하나가 한 글에 있다.
DRAWING_TEXT = (f"{CUSTOMER} 작은방 붙박이장 견적도 같이 봐 주실 수 있을까요\n"
                "크기 - 잘 몰라요(위에 보낸 평면도 참고해 주세요)\n"
                "색상 - 밝은 색\n"
                "손잡이 없는 문은 어떤 종류가 있나요?")
#: 뽑기 모델의 합성 답 — 가로 모름(0 · unknown) + 크기는 손님 첨부에.
DRAWING_ANSWER = {"quote_request": True, "brand": "LAHOM", "unknown": ["width"], "size_in_attachment": True,
                  "spaces": [{"space": "작은방", "product_ids": [str(MOLD["id"])], "width_mm": 0, "width_max_mm": 0,
                              "height_mm": 0, "door": "unknown", "handle": "push", "options": []}]}
DRAWING_DRAFT = "고객님, 보내 주신 도면을 보고 크기 확인해 견적 안내드리겠습니다."
WIDTH_ASK = qc.ASK_ORDER["width"]  # '설치하실 벽의 가로 길이(mm)'


def _width_asks(lines):
    """두뇌 재료 가운데 가로를 묻게 하는 줄."""
    return [line for line in lines if WIDTH_ASK in line]


def _drawing_chat(channel, *, attached=True, chat="uc-1"):
    """손님이 먼저 그림(첨부만)을 보내고 이어 견적 · 규격 모름 글을 쓴 상담. ``attached=False`` 면 그림 없이 글만."""
    if not attached:
        customer(channel, chat, text=DRAWING_TEXT)
        return
    customer(channel, chat, text="", extra={"files": [{"id": "f-1"}]}, when=at(2, 8, 40),
             more=[(f"m-{chat}-2", at(2, 8, 50), "user", DRAWING_TEXT, {})])


def _private(text):
    """비공개 메모 글 하나(읽기 결과 꼴)."""
    return SimpleNamespace(text=text, meta=SimpleNamespace(is_private=True, is_log=False))


# ── 뽑기 ─────────────────────────────────────────────────────────────────
def test_the_extraction_schema_instructions_and_reader_carry_size_in_attachment():
    schema = qb.quote_schema(catalog())
    assert schema["properties"]["size_in_attachment"] == {"type": "boolean"}
    assert "size_in_attachment" in schema["required"]
    assert "size_in_attachment" in qb.INSTRUCTIONS and FILE_NOTE in qb.INSTRUCTIONS  # 첨부 표시 글자 그대로
    def read(answer):
        return qb.read_ask(json.dumps(answer), catalog()).size_in_attachment

    assert read(DRAWING_ANSWER) is True and read({**DRAWING_ANSWER, "size_in_attachment": False}) is False
    old = {key: value for key, value in DRAWING_ANSWER.items() if key != "size_in_attachment"}
    assert read(old) is False  # 칸이 없으면 예전처럼(묻는다)
    with pytest.raises(ValueError, match="size_in_attachment"):
        qb.read_ask(json.dumps({**DRAWING_ANSWER, "size_in_attachment": "yes"}), catalog())


def test_extract_quote_sees_the_attachment_mark_and_reads_the_flag(brain_env):
    client = FakeAnthropic(DRAWING_ANSWER)
    got = qb.extract_quote(_request(messages=[("user", FILE_NOTE), ("user", DRAWING_TEXT)]), catalog(), client=client,
                           session=db_session, now=NOW)
    (params,) = client.params
    assert FILE_NOTE in params["messages"][0]["content"]  # 뽑기 모델은 '첨부가 왔다'는 표시를 본다
    assert (got.size_in_attachment, got.unknown, got.spaces[0].width_mm) == (True, ("width",), 0)


def test_only_a_customer_attachment_counts():
    assert qs.customer_sent_file(_request(messages=[("user", FILE_NOTE), ("user", DRAWING_TEXT)]))
    assert qs.customer_sent_file(_request(messages=[("user", f"{DRAWING_TEXT}\n{FILE_NOTE}")]))
    assert not qs.customer_sent_file(_request(messages=[("manager", FILE_NOTE), ("user", DRAWING_TEXT)]))
    assert not qs.customer_sent_file(_request(messages=[("user", DRAWING_TEXT)]))


# ── 계산 ─────────────────────────────────────────────────────────────────
def test_an_unknown_width_with_a_customer_drawing_is_not_asked():
    cases = (ask(space(width=0), size_in_attachment=True),
             ask(space(), unknown=("width",), size_in_attachment=True),
             ask(space(None, 0), size_in_attachment=True))  # 제품도 모르면 — 가로는 그림에 있으니 묻는 줄 없이 직원에게
    for quote in cases:
        outcome = evaluate(quote)
        assert _width_asks(outcome.lines) == [] and outcome.allowed == ()  # 묻는 줄 0 · 금액 허용 0
        assert (outcome.status, outcome.code, outcome.lines, outcome.note) == (
            qrec.STATUS_DRAWING, qc.SIZE_IN_DRAWING, (qc.DRAWING_LINE,), qc.DRAWING_NOTE)
    assert "손님이 보낸 도면 · 사진에서 크기를 확인해 안내한다 — 가로 길이를 다시 묻지 말 것" in qc.DRAWING_LINE
    assert qc.DRAWING_NOTE == "[견적 계산] 손님 도면 · 사진에서 가로 확인 → 계산기"
    assert qc.DRAWING_NOTE.startswith(MEMO_QUOTE_HEAD)  # 다음 초안의 '비공개 메모 섞임' 재료에서 빠진다
    assert memo_snippets([_private(memo_text("합성 초안", qc.DRAWING_NOTE))]) == [""]
    record = qrec.record_value(qrec.STATUS_DRAWING, lines=(qc.DRAWING_LINE,), code=qc.SIZE_IN_DRAWING)
    assert (qrec.allowed_from(record), qrec.lines_from(record)) == ((), ())  # 다시 검사도 금액을 더하지 않는다


def test_the_flag_never_hides_a_known_width_or_the_brand_rule():
    assert evaluate(ask(space(), size_in_attachment=True)).status == qrec.STATUS_OK  # 가로를 알면 계산한다
    assert evaluate(ask(brand="HAUD", size_in_attachment=True)).code == qc.HUMAN_BRAND


def test_negative_control_without_a_drawing_still_asks_exactly_one_thing():
    outcome = evaluate(ask(space(width=0)))
    (line,) = outcome.lines
    assert (outcome.status, outcome.code, outcome.allowed) == (qc.STATUS_ASK, "width", ())
    assert _width_asks(outcome.lines) == [line] and line.count("모르는 칸") == 1


# ── 두뇌 기본 지시 ───────────────────────────────────────────────────────
def test_the_brain_instructions_forbid_asking_again():
    text = bp.instructions("LAHOM")
    assert "11. 손님이 이미 준 정보나 모른다고 한 것을 다시 묻지 않는다." in text
    assert "같은 글에서 함께 물은 것은 각각 답하거나 확인 뒤 안내한다고 쓴다." in text


# ── 그 상담 되풀이(합성 대화 · 가짜 두뇌) ────────────────────────────────
def test_replay_the_drawing_chat_gives_the_brain_no_width_question(channel):
    switch()
    _drawing_chat(channel)
    client = FakeAnthropic(DRAWING_ANSWER)
    brain_fn, poster = FakeBrain(result(draft=DRAWING_DRAFT)), FakePoster()
    summary = run(channel, "memo", brain_fn=brain_fn, poster=poster,
                  pass_type=quoting(functools.partial(qb.extract_quote, client=client)))  # 진짜 뽑기 길 · 가짜 모델
    assert FILE_NOTE in client.params[0]["messages"][0]["content"]
    (request,) = brain_fn.requests
    assert _width_asks(request.calculator_lines) == []  # 가로를 묻는 재료 0
    assert request.calculator_lines == (qc.DRAWING_LINE,) and summary.quotes == {qrec.STATUS_DRAWING: 1}
    (call,) = poster.calls
    note = call.text.split(MEMO_NOTE_HEAD, 1)[1].strip().splitlines()
    assert note[-1] == qc.DRAWING_NOTE and DRAWING_DRAFT in call.text  # 금액 없는 초안 + 직원 참고 줄로 직원에게
    row = turn()
    assert (row.state, row.handoff) == ("posted", False)
    assert row.quote_lines == qrec.record_value(qrec.STATUS_DRAWING, lines=(qc.DRAWING_LINE,), code=qc.SIZE_IN_DRAWING)
    assert qrec.allowed_from(row.quote_lines) == ()


def test_replay_an_amount_in_the_drawing_state_is_still_blocked(channel):
    switch()
    _drawing_chat(channel)
    amount = f"고객님, 보내 주신 도면 기준 {won(MOLD['id'], 2400):,}원입니다."  # 계산기 값이어도 허용 목록에 없다
    run(channel, brain_fn=FakeBrain(result(draft=amount)),
        pass_type=quoting(FakeQuoter(ask(space(width=0), size_in_attachment=True))))
    assert (turn().state, turn().error_code) == ("skipped", "check_failed")


def test_replay_negative_control_without_an_attachment_asks_the_width(channel):
    switch()
    _drawing_chat(channel, attached=False)
    client = FakeAnthropic(DRAWING_ANSWER)  # 모델이 첨부가 있다고 잘못 답해도
    brain_fn = FakeBrain(result(draft="고객님, 설치하실 벽의 가로 길이를 알려 주시겠어요?"))
    summary = run(channel, brain_fn=brain_fn, pass_type=quoting(functools.partial(qb.extract_quote, client=client)))
    (request,) = brain_fn.requests
    (line,) = request.calculator_lines
    assert _width_asks(request.calculator_lines) == [line] and summary.quotes == {qc.STATUS_ASK: 1}  # 예전처럼 한 가지
    assert turn().quote_lines["code"] == "width"
