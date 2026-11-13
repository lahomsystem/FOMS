"""스토어 상품 → 계산기 제품 정해 둔 짝(사장님 11-13) — 톡톡 상품 문의 줄의 상품이 표에 있으면 견적 뽑기가 짐작하지 않고 그 제품을
쓴다 · '계산기에 없음'이면 초안 없이 직원에게 · 손님 글이 다른 제품을 말하면 손님 글 · 표에 없는 상품은 예전 그대로.

계산기는 처음 채우기 파일 값(합성 시험 재료 — ``tests/support/cs_quote_support.py``). 금액 숫자는 적지 않는다.
"""

from __future__ import annotations

from foms.services.cs_agent import quote_brain as qb
from foms.services.cs_agent import quote_record as qrec
from foms.services.cs_agent import store_products as sp
from foms.services.cs_agent.brain_prompt import ROLE_STORE
from tests.domains.test_cs_drafting import FakeBrain, channel, customer, result, run, turn  # noqa: F401 — fixture
from tests.domains.test_cs_store_inquiry import store_blocks
from tests.support.cs_agent_fakes import at, keys  # noqa: F401 — keys 는 fixture
from tests.support.cs_quote_support import (
    MOLD, QUOTE_TEXT, FakeQuoter, amount_draft, ask, catalog, confirm_prices, quoting, space, switch,
)

HABAN = "라홈 하반 빌트인 침대 안방 무몰딩 붙박이장 30cm 친환경 E0"
BACH = "라홈 바흐 붙박이장 안방 작은방 슬라이딩 240cm"  # 사장님 11-13 '계산 없이 직원에게'
NEW = "라홈 합성 새 상품 붙박이장 30cm"  # 표에 없는 상품


def talk(name):
    return [(ROLE_STORE, name), ("user", QUOTE_TEXT)]


# ── 표 · 짝 찾기 ─────────────────────────────────────────────────────────
def test_the_table_holds_owner_decisions():
    assert sp.STORE_PRODUCTS["라홈 로라 붙박이장 안방 여닫이 푸쉬타입 30cm"] == 2  # 이름에 무몰딩이 없으면 몰딩(푸쉬)
    assert sp.STORE_PRODUCTS["라홈 무몰딩 붙박이장 로라 시리즈 30cm 푸쉬타입 친환경 E0"] == 5
    assert sp.STORE_PRODUCTS["라홈 무몰딩 붙박이장 아라 시리즈 30cm 친환경 E0"] == 33  # 아라는 원도어
    assert sp.STORE_PRODUCTS[BACH] is None and sp.STORE_PRODUCTS["라홈 모카 붙박이장 여닫이 스윙 안방 작은방 240cm"] is None
    assert all(value is None or isinstance(value, int) for value in sp.STORE_PRODUCTS.values())
    assert all(name == " ".join(name.split()) for name in sp.STORE_PRODUCTS)
    assert not any("화장대" in name for name in sp.STORE_PRODUCTS)  # 옵션을 같이 정해야 하는 상품은 표 밖(예전 그대로)


def test_store_choice_uses_the_last_store_line_and_the_catalog_value():
    cat_ = catalog()
    haban = sp.store_choice(talk(HABAN), cat_)
    assert haban.name == HABAN and str(haban.product_id) == "10"
    assert sp.store_choice([(ROLE_STORE, HABAN), ("user", "x"), (ROLE_STORE, BACH)], cat_) == sp.StoreChoice(BACH, None)
    assert sp.store_choice(talk("  라홈 하반 빌트인 침대   안방 무몰딩 붙박이장 30cm 친환경 E0 "), cat_).name == HABAN
    assert sp.store_choice(talk(NEW), cat_) is None and sp.store_choice([("user", QUOTE_TEXT)], cat_) is None
    assert sp.store_choice(talk(HABAN), catalog(products=[MOLD])) is None  # 계산기에서 지운 제품이면 짝을 쓰지 않는다


def test_apply_choice_fills_only_empty_spaces():
    choice = sp.StoreChoice(HABAN, 10)
    filled, human = sp.apply_choice(ask(space(None), unknown=("product", "door")), choice)
    assert ([s.product_ids for s in filled.spaces], filled.unknown, human) == ([(10,)], ("door",), False)
    kept, _ = sp.apply_choice(ask(space(MOLD["id"]), space(None)), choice)  # 손님이 말한 제품은 그대로
    assert [s.product_ids for s in kept.spaces] == [(MOLD["id"],), (10,)]
    made, _ = sp.apply_choice(qb.QuoteAsk(quote_request=True, spaces=(), unknown=("product",)), choice)  # 공간 없음
    assert [(s.space, s.product_ids, s.width_mm) for s in made.spaces] == [("기타", (10,), 0)] and made.unknown == ()


def test_apply_choice_sends_unknown_store_products_to_staff_unless_the_customer_named_one():
    none = sp.StoreChoice(BACH, None)
    assert sp.apply_choice(ask(space(None)), none)[1] is True
    assert sp.apply_choice(ask(space(MOLD["id"])), none)[1] is False


# ── 초안 한 바퀴 ─────────────────────────────────────────────────────────
def bot(name):
    return ("b-1", at(2, 8, 49), "bot", f"{name}에 대한 문의입니다.",
            {"blocks": store_blocks(name), "options": ["doNotSendApp"]})


def test_a_mapped_store_product_is_calculated_without_guessing(channel):
    switch()
    confirm_prices()
    customer(channel, text=QUOTE_TEXT, more=[bot(HABAN)])
    quoter, brain_fn = FakeQuoter(ask(space(None), unknown=("product",))), FakeBrain(result(draft=amount_draft()))
    summary = run(channel, brain_fn=brain_fn, pass_type=quoting(quoter))
    (sent,) = quoter.calls
    assert ROLE_STORE not in [role for role, _ in sent.messages]  # 뽑기는 상품 이름으로 짐작하지 않는다
    assert summary.quotes == {"ok": 1} and turn().quote_lines["status"] == qrec.STATUS_OK
    (request,) = brain_fn.requests
    assert request.messages[0] == (ROLE_STORE, HABAN) and request.calculator_lines  # 초안 두뇌는 상품 줄도 본다


def test_a_store_product_outside_the_calculator_goes_to_staff_without_a_draft(channel):
    switch()
    customer(channel, text=QUOTE_TEXT, more=[bot(BACH)])
    summary = run(channel, brain_fn=FakeBrain(max_calls=0), pass_type=quoting(FakeQuoter(ask(space(None)))))
    row = turn()
    assert (row.state, row.error_code, row.handoff_reason) == ("skipped", sp.HUMAN_STORE_PRODUCT, sp.HUMAN_STORE_PRODUCT)
    assert summary.quotes == {"human": 1} and summary.brain_calls == 1  # 뽑기 한 번 · 초안 두뇌는 부르지 않음


def test_the_customer_naming_a_product_wins_over_the_store_line(channel):
    switch()
    confirm_prices()
    customer(channel, text=QUOTE_TEXT, more=[bot(BACH)])
    summary = run(channel, brain_fn=FakeBrain(result(draft=amount_draft())), pass_type=quoting(FakeQuoter(ask())))
    assert summary.quotes == {"ok": 1} and turn().error_code != sp.HUMAN_STORE_PRODUCT


def test_an_unmapped_store_product_keeps_the_old_path(channel):
    switch()
    customer(channel, text=QUOTE_TEXT, more=[bot(NEW)])
    quoter = FakeQuoter(ask())
    run(channel, brain_fn=FakeBrain(result(draft=amount_draft())), pass_type=quoting(quoter))
    (sent,) = quoter.calls
    assert sent.messages[0] == (ROLE_STORE, NEW)  # 표에 없으면 뽑기가 상품 줄을 본다(예전 그대로)
