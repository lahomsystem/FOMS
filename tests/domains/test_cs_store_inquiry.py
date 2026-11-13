"""톡톡 상품 문의 줄 — 손님이 네이버 스토어 상품 화면에서 [문의하기]를 누르면 톡톡 봇이 '<상품 링크>에 대한 문의입니다.'를
먼저 보낸다. 예전엔 봇 글이라 통째로 빠져 초안이 "어떤 제품인지" 다시 물었다(사장님 11-13). 이제 상품 이름만
``[스토어 상품 문의]`` 줄로 초안 · 견적 뽑기 · 물건 찾기 재료에 들어간다 — 다른 봇 글 · 링크 · 상품 번호는 여전히 빠진다.

합성 값만(꾸민 상품 이름 · 상품 번호).
"""

from __future__ import annotations

import pytest

from foms.services.cs_agent import brain_prompt as prompt
from foms.services.cs_agent import drafting_read as dr
from foms.services.cs_agent.brain_instructions import INSTRUCTIONS
from foms.services.cs_agent.masking import require_masked
from foms.services.cs_agent.quote_brain import INSTRUCTIONS as QUOTE_INSTRUCTIONS
from tests.domains.test_cs_drafting import FakeBrain, channel, customer, result, run  # noqa: F401 — channel 은 fixture
from tests.support.cs_agent_fakes import api_message, at, keys  # noqa: F401 — keys 는 fixture

NAME = "합성 무몰딩 붙박이장 슬라이딩 30cm"
LINK = "https://smartstore.naver.com/inflow/outlink/product?p=12345&tr=tsf&frm=chat"


def store_blocks(name=NAME, url=LINK):
    return [{"type": "text", "value": f'<link type="url" value="{url}">{name}</link>에 대한 문의입니다.'}]


def bot_line(msg_id="b-1", when=None, *, name=NAME, blocks=None, text=None, **extra):
    """톡톡 상품 문의 봇 글(Open API 꼴)."""
    return api_message(msg_id, when or at(2, 8, 49), "bot", f"{name}에 대한 문의입니다." if text is None else text,
                       blocks=store_blocks(name) if blocks is None else blocks, options=["doNotSendApp"], **extra)


def lines_of(*items):
    return sorted(dr.parse_lines("LAHOM", "uc-1", list(items)), key=lambda line: line.key)


# ── 상품 이름 꺼내기 ────────────────────────────────────────────────────
def test_store_product_reads_the_name_from_the_store_link_block():
    assert dr.store_product(bot_line()) == NAME
    assert dr.store_product(bot_line(blocks=store_blocks(url=LINK.replace("smartstore", "m.smartstore")))) == NAME


@pytest.mark.parametrize("blocks,text", [
    ([{"type": "text", "value": f'<link type="url" value="https://example.com/x">{NAME}</link>에 대한 문의입니다.'}], None),
    ([{"type": "text", "value": "가구 호갱 방지 보안관 라홈 입니다. 무엇을 도와 드릴까요?"}], "가구 호갱 방지 보안관 라홈 입니다."),
    ([{"type": "text", "value": f"{NAME}에 대한 문의입니다."}], None),  # 덩어리가 있는데 스토어 링크가 없다
], ids=["other-host", "greeting", "no-link-in-blocks"])
def test_other_bot_lines_are_not_store_inquiries(blocks, text):
    assert dr.store_product(bot_line(blocks=blocks, text=text)) == ""


def test_plain_text_is_used_only_when_there_are_no_blocks():
    plain = api_message("b-2", at(2, 8, 49), "bot", f"{NAME}에 대한 문의입니다.")
    assert dr.store_product(plain) == NAME
    assert dr.store_product(api_message("b-3", at(2, 8, 49), "bot", f"{NAME} 문의 감사합니다.")) == ""


# ── 대화 재료 ───────────────────────────────────────────────────────────
def test_the_store_line_joins_the_conversation_but_other_bot_lines_do_not():
    lines = lines_of(bot_line(),
                     api_message("b-0", at(2, 8, 48), "bot", "가구 호갱 방지 보안관 라홈 입니다."),
                     api_message("u-1", at(2, 8, 50), "user", "견적을 어떻게 하는지 모르겠어요"),
                     api_message("u-2", at(2, 8, 51), "user", f"{NAME}에 대한 문의입니다."))  # 손님이 친 글은 손님 글
    assert dr.conversation(lines) == [(prompt.ROLE_STORE, NAME), ("user", "견적을 어떻게 하는지 모르겠어요"),
                                      ("user", f"{NAME}에 대한 문의입니다.")]
    assert [line.store_product for line in lines] == ["", NAME, "", ""]
    assert dr.customer_texts(lines)[0] == NAME  # 물건 찾기 · 같은 값 재료에도


@pytest.mark.parametrize("extra", [{"options": ["private"]}, {"log": {"action": "open"}}], ids=["private", "log"])
def test_private_or_log_bot_lines_stay_out(extra):
    item = {**bot_line(), **extra}
    (line,) = lines_of(item)
    assert line.store_product == "" and dr.public_turn(line) is None


def test_a_long_chat_keeps_the_last_store_line_up_front():
    talk = [api_message(f"u-{i}", at(2, 9, i), "user" if i % 2 else "manager", f"합성 글 {i}") for i in range(40)]
    lines = lines_of(bot_line(when=at(2, 8, 40)), *talk)
    turns = dr.conversation(lines)
    assert len(turns) == dr.CONVERSATION_LIMIT
    assert turns[0] == (prompt.ROLE_STORE, NAME) and turns[-1] == ("user", "합성 글 39")
    short = dr.conversation(lines_of(bot_line(when=at(2, 8, 40)), *talk[:5]))
    assert short[0] == (prompt.ROLE_STORE, NAME) and len(short) == 6  # 잘리지 않으면 제자리 그대로


def test_the_rendered_line_has_its_own_mark_and_passes_the_mask_check():
    text = prompt.render_conversation([(prompt.ROLE_STORE, NAME), ("user", "가로 3500 이에요")])
    assert text.splitlines()[0] == f"[스토어 상품 문의] {NAME}"
    require_masked(text)


def test_the_prompts_explain_the_mark():
    assert "[스토어 상품 문의] 줄은" in INSTRUCTIONS and "다시 묻지 않는다" in INSTRUCTIONS
    assert "[스토어 상품 문의] 줄은" in QUOTE_INSTRUCTIONS and "product_ids" in QUOTE_INSTRUCTIONS


def test_turn_end_ignores_the_store_line():
    from foms.services.cs_agent import turn_end
    lines = lines_of(bot_line(when=at(2, 8, 49)), api_message("u-1", at(2, 8, 50), "user", "가로 3500 이에요"))
    burst = turn_end._burst(lines, "u-1", at(2, 8, 51))
    assert [who for who, _, _ in burst] == ["user"]


# ── 초안 한 바퀴: 두뇌가 받은 재료 ──────────────────────────────────────
def test_the_draft_brain_gets_the_store_line_first(channel):
    customer(channel, text="견적을 어떻게 해야 하는지 모르겠어요",
             more=[("b-1", at(2, 8, 49), "bot", f"{NAME}에 대한 문의입니다.",
                    {"blocks": store_blocks(), "options": ["doNotSendApp"]})])
    brain_fn = FakeBrain(result())
    assert run(channel, brain_fn=brain_fn).stored == 1
    (request,) = brain_fn.requests
    assert request.messages[0] == (prompt.ROLE_STORE, NAME)
    assert request.messages[1] == ("user", "견적을 어떻게 해야 하는지 모르겠어요")
    assert "12345" not in repr(request.messages)  # 링크 · 상품 번호는 싣지 않는다
