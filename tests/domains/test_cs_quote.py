"""견적(라홈) — 견적 재료 뽑기 · 제작 조건 · 서버 계산 · 두뇌 재료 연결 · 허용 목록 · 끄고 켜기 · 14일 규칙(플랜 C10-6).

완료 기준(브리프): 계산기 값이 화면 계산과 원 단위로 같음(node — 큰 묶음은 계약 시험
``tests/contracts/wdcalculator/test_server_pricing_contract.py``) · 0원 · 모르는 가격 방식 · 계산 실패 · 안 되는 구성은
사람에게 · 모르는 칸은 한 가지만 묻기 · 계산기 값만 허용 목록에(손님 글 금액은 계속 막힘) · 끄면 예전 그대로 · 14일 확인 필요.
스토어 규칙 층(D73)은 ``test_cs_quote_rules.py``, 확인 날 기록(D74)은 ``test_cs_quote_check.py``, 검수 R17 은
``test_cs_quote_review.py``. 금액 숫자는 적지 않는다(재료는 ``tests/support/cs_quote_support.py``).
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.cs_agent import brain, quote_brain as qb, quote_calc as qc, quote_record as qrec, quote_step as qs
from foms.services.cs_agent import quote_check as qk
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_spend import BAD_RESPONSE, BrainUnavailable, SpendCapReached
from foms.services.cs_agent.checks import check_draft
from foms.services.cs_agent.drafting_read import MEMO_HEAD, MEMO_NOTE_HEAD, MEMO_QUOTE_HEAD, memo_snippets, memo_text
from foms.services.cs_agent.knowledge_doc import ApprovedKnowledge, KnowledgeItem
from foms.services.wdcalculator import pricing
from tests.contracts.wdcalculator.test_server_pricing_contract import _node
from tests.domains.test_cs_drafting import (  # noqa: F401 — channel 은 fixture
    CUSTOMER, FakeBrain, FakePoster, channel, customer, result, run, turn,
)
from tests.support.cs_agent_fakes import FakeAnthropic, keys  # noqa: F401 — keys 는 fixture
from tests.support.cs_quote_support import (
    CATEGORIES, HAUD, LAHOM, MOLD, NOW, OPTION, OTHER, QUOTE_TEXT, FakeQuoter, amount_draft, ask, catalog, checked,
    confirm_prices, evaluate, quoting, rule_item, space, switch, won,
)


# ── 계산 · 허용 목록 ─────────────────────────────────────────────────────
def test_calculator_line_equals_the_screen_amount_and_only_it_is_allowed():
    outcome = evaluate(ask(space(options=((OPTION, 2),))))
    rows = pricing.option_rows([(OPTION, 2)], CATEGORIES)
    (screen,) = _node([{"kind": "estimate", "products": LAHOM, "options": rows,
                        "components": [{"mode": "select", "productId": MOLD["id"], "widthMm": 2400}]}])
    amount = screen["won_total"]
    assert outcome.status == qc.STATUS_OK and amount == won(MOLD["id"], 2400, [(OPTION, 2)]) > 0
    head, line = outcome.lines
    assert f"{amount:,}원" in line and "가로 2,400mm" in line and "× 2" in line and f"{amount:,}" not in head
    assert outcome.allowed == (line,) and outcome.note.startswith(MEMO_QUOTE_HEAD) and outcome.code is None
    draft = f"고객님, 말씀하신 가로 2,400mm 기준 계산기 금액은 {amount:,}원입니다."
    knowledge_only = ("합성 선반 깊이는 350mm 입니다",)
    assert check_draft(draft, brand="LAHOM", medium="native", allowed_numbers=(*knowledge_only, *outcome.allowed)).ok
    blocked = check_draft(draft, brand="LAHOM", medium="native", allowed_numbers=knowledge_only)
    assert "number_not_allowed" in blocked.codes  # 계산기 줄이 없으면 그 금액은 막힌다
    budget = f"고객님, 예산 {amount + 10000:,}원에 맞춰 드릴게요."  # 손님이 쓴 금액 꼴 — 계산기 값이 아니다
    assert "number_not_allowed" in check_draft(budget, brand="LAHOM", medium="native",
                                               allowed_numbers=(*knowledge_only, *outcome.allowed)).codes


def test_several_spaces_get_a_total_and_a_width_range_gets_both_ends():
    two = evaluate(ask(space(), space(OTHER["id"], 1800, space="드레스룸")))
    total = won(MOLD["id"], 2400) + won(OTHER["id"], 1800)
    assert two.status == qc.STATUS_OK and two.allowed[-1] == f"합계(공간 2곳) {total:,}원"
    ranged = evaluate(ask(space(width=2400, width_max_mm=3005)))  # 위 끝은 10mm 단위로 올려 계산(D73)
    expected = (won(MOLD["id"], 2400), won(MOLD["id"], 3010))
    assert [f"{amount:,}원" in line for line, amount in zip(ranged.allowed, expected)] == [True, True]
    assert "계산 가로 3,010mm" in ranged.allowed[1] and not any(line.startswith("합계") for line in ranged.allowed)


def test_zero_unknown_pricing_type_failure_and_haud_go_to_a_human():
    zero = dict(MOLD, id=990001, price_30cm=0, price_1cm=0)
    odd = dict(MOLD, id=990002, pricing_type="2m")
    infinite = dict(MOLD, id=990003, price_30cm="Infinity")
    free = {"id": 990, "name": "합성", "options": [{"id": 1, "name": "영원", "price": 0}]}
    cases = {
        qc.HUMAN_ZERO: (ask(space(zero["id"])), catalog(extra=[zero])),
        qc.HUMAN_PRICING_TYPE: (ask(space(odd["id"])), catalog(extra=[odd])),
        qc.HUMAN_FAILED: (ask(space(options=(("0:0", 1),))), catalog()),
        qc.HUMAN_BRAND: (ask(brand="HAUD"), catalog()),
    }
    for code, (quote, catalog_) in cases.items():
        outcome = evaluate(quote, catalog_)
        assert (outcome.status, outcome.code, outcome.lines, outcome.allowed) == (qc.STATUS_HUMAN, code, (), ()), code
    zero_option = evaluate(ask(space(options=(("990:1", 1),))), catalog(categories=[free]))
    assert (zero_option.status, zero_option.code) == (qc.STATUS_HUMAN, qc.HUMAN_ZERO)  # 화면은 0원 옵션을 빼고 센다
    for pid, catalog_ in ((999999, catalog()), (infinite["id"], catalog(extra=[infinite]))):
        outcome = evaluate(ask(space(pid)), catalog_)
        assert outcome.status == qc.STATUS_HUMAN and outcome.code in (qc.HUMAN_FAILED, qc.HUMAN_ZERO), pid


def test_unknown_fields_ask_exactly_one_thing_in_order():
    rules = qc.build_rules([rule_item(f"검사: product={MOLD['id']} max_height=2400 door=hinged")])
    order = [
        (ask(space(None, 0)), (), "product"),
        (ask(space(width=0)), (), "width"),
        (ask(space(), unknown=("width",)), (), "width"),
        (ask(space(), unknown=("height", "door")), (), None),  # 규칙이 안 보는 칸은 묻지 않는다
        (ask(space()), rules, "height"),
        (ask(space(height_mm=2300)), rules, "door"),
    ]
    for quote, rules_, field in order:
        outcome = evaluate(quote, rules=rules_)
        if field is None:
            assert outcome.status == qc.STATUS_OK
            continue
        assert (outcome.status, outcome.code, outcome.allowed) == (qc.STATUS_ASK, field, ()), field
        (line,) = outcome.lines
        assert qc.ASK_ORDER[field] in line and line.count("모르는 칸") == 1 and "원" not in line.replace("원하", "")


def test_build_rules_block_configurations_that_cannot_be_made():
    rules = qc.build_rules([
        rule_item("슬라이딩은 ㄱ자에 안 된다\n검사: product=%s door=hinged" % MOLD["id"]),
        rule_item("검사: min_width=600 max_width=4800", item_id="rule-2"),
        rule_item("검사: product=999 max_height=10", item_id="rule-3"),  # 다른 제품 규칙은 걸리지 않는다
        rule_item("검사: max_height=10", kind="fact", item_id="fact-1"),  # build_rule 이 아니면 읽지 않는다
        rule_item("글로만 된 제작 조건", item_id="rule-4"),
    ])
    assert len(rules) == 3
    bad = [space(door="sliding"), space(door="hinged", width=500), space(door="hinged", width=4000, width_max_mm=5000)]
    for case in bad:
        assert (evaluate(ask(case), rules=rules).status, evaluate(ask(case), rules=rules).code) == (
            qc.STATUS_HUMAN, qc.HUMAN_RULE)
    assert evaluate(ask(space(door="hinged")), rules=rules).status == qc.STATUS_OK
    assert evaluate(ask(space(OTHER["id"], door="sliding")), rules=rules).status == qc.STATUS_OK
    for text in ("검사: colour=red", "검사: door=folding", "검사: max_height=abc", "검사:", "검사: product=",
                 "검사: max_width=１２"):
        with pytest.raises(qc.RuleUnreadable):
            qc.build_rules([rule_item(text)])


def test_fourteen_days_after_the_confirm_day_amounts_need_a_check():
    for days, status in ((13.9, qc.STATUS_OK), (14, qc.STATUS_OK), (14.01, qc.STATUS_CHECK)):
        assert evaluate(ask(), check=checked(days)).status == status, days  # 정확히 14일은 아직 확인됨
    stale = evaluate(ask(), check=checked(20))
    amount = f"{won(MOLD['id'], 2400):,}원"
    assert (stale.lines, stale.allowed) == ((qc.CHECK_LINE,), ())  # 두뇌 재료엔 금액 없이 한 줄만(R17-4)
    assert stale.note.startswith(f"{MEMO_QUOTE_HEAD} · 확인 필요") and amount in stale.note  # 직원 참고 줄에만
    for check in (qk.PriceCheck(), qk.PriceCheck(seed=True), checked(1, failed=True), checked(1, seed=True)):
        outcome = evaluate(ask(), check=check)
        assert (outcome.status, outcome.allowed) == (qc.STATUS_CHECK, ()), check


# ── 뽑기 두뇌 ────────────────────────────────────────────────────────────
def _request(**kw):
    knowledge = ApprovedKnowledge(brand="LAHOM", version=1, items=(
        KnowledgeItem(item_id="hours-day", kind="template", status="approved", text="평일 낮", intents=("hours",)),))
    values = dict(brand="LAHOM", chat_id="uc-1", medium="native", purpose="draft", daytime=True,
                  messages=[("user", QUOTE_TEXT)], customer_names=(), staff_names=(), knowledge=knowledge)
    return brain.DraftRequest(**{**values, **kw})


ANSWER = {"quote_request": True, "brand": "LAHOM", "unknown": ["height"], "spaces": [{
    "space": "안방", "product_ids": [str(MOLD["id"]), str(HAUD["id"]), "nope"], "width_mm": 2400, "width_max_mm": 0,
    "height_mm": 0, "door": "sliding", "handle": "push", "options": [{"id": OPTION, "qty": 120}]}]}


class Recording(FakeAnthropic):
    def __init__(self, *answers):
        super().__init__(*answers)
        self.options = []

    def with_options(self, **options):
        self.options.append(options)
        return self


@pytest.fixture
def brain_env(app, monkeypatch):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "5")


def test_extract_quote_sends_ids_not_prices_and_reads_the_answer(brain_env):
    client = Recording(ANSWER)
    got = qb.extract_quote(_request(realtime=True), catalog(), client=client, session=db_session, now=NOW)
    (params,) = client.params
    assert params["model"] == brain.MODEL and params["output_config"]["effort"] == "low"  # 의도 고르기 칸(처음 값)
    assert client.options == [{"timeout": float(qb.REALTIME_TIMEOUT_CAP), "max_retries": 0}]  # 뽑기 + 초안이 선점 안에
    schema = params["output_config"]["format"]["schema"]
    ids = schema["properties"]["spaces"]["items"]["properties"]["product_ids"]["items"]["enum"]
    assert str(MOLD["id"]) in ids and str(HAUD["id"]) not in ids  # 라홈 제품만 고를 수 있다
    system = "\n".join(block["text"] for block in params["system"])
    prices = {p[k] for p in LAHOM for k in ("price_1m", "price_30cm") if p.get(k)}
    assert all(f"{price:,}" not in system for price in prices) and MOLD["name"] in system  # 값은 두뇌에 주지 않는다
    assert CUSTOMER in params["messages"][0]["content"]
    assert (got.quote_request, got.brand, got.unknown) == (True, "LAHOM", ("height",))
    (only,) = got.spaces
    assert (only.product_ids, only.width_mm, only.door, only.options) == ((MOLD["id"],), 2400, "sliding", ((OPTION, 1),))
    assert got.cost_usd > 0 and brain.spent_today(db_session, now=NOW) == got.cost_usd  # 돈 줄에 바로잡혀 남는다
    batch = Recording(ANSWER)
    qb.extract_quote(_request(), catalog(), client=batch, session=db_session, now=NOW)
    assert batch.options[0]["timeout"] == float(st.DEFAULTS["batch_timeout_s"])  # 15분 루프 길은 그대로


def test_extract_quote_rejects_a_bad_shape(brain_env):
    for answer in ({"quote_request": "yes"}, {**ANSWER, "spaces": [{"space": "안방"}]}, {**ANSWER, "brand": "X"}):
        with pytest.raises(BrainUnavailable) as caught:
            qb.extract_quote(_request(), catalog(), client=FakeAnthropic(answer), session=db_session, now=NOW)
        assert caught.value.code == BAD_RESPONSE


# ── 초안 차례에 잇기 ─────────────────────────────────────────────────────
@pytest.mark.parametrize("row", [False, True])
def test_switched_off_is_exactly_as_before(channel, row):
    if row:
        switch(False)
    customer(channel, text=QUOTE_TEXT)
    quoter, brain_fn = FakeQuoter(ask()), FakeBrain(result(draft=amount_draft()))
    summary = run(channel, brain_fn=brain_fn, pass_type=quoting(quoter))
    (request,) = brain_fn.requests
    assert quoter.calls == [] and request.calculator_lines == () and summary.quotes == {} and summary.brain_calls == 1
    assert (turn().state, turn().error_code, turn().quote_lines) == ("skipped", "check_failed", None)  # 예전처럼 막힌다


def test_switched_on_fills_calculator_lines_allows_their_amounts_and_notes_them(channel):
    switch()
    confirm_prices()
    customer(channel, text=QUOTE_TEXT)
    quoter, brain_fn, poster = FakeQuoter(ask()), FakeBrain(result(draft=amount_draft())), FakePoster()
    summary = run(channel, "memo", brain_fn=brain_fn, poster=poster, pass_type=quoting(quoter))
    (request,) = brain_fn.requests
    expected = evaluate(ask(), check=checked(0))  # 버튼을 바퀴와 같은 때 눌렀다
    same_lines = request.calculator_lines == expected.lines  # 비교 결과만 단언한다(실패 글에 금액을 찍지 않게)
    assert same_lines and quoter.calls[0].calculator_lines == ()
    assert (summary.brain_calls, summary.quotes, summary.posted) == (2, {"ok": 1}, 1)
    (call,) = poster.calls
    assert call.text.split(MEMO_NOTE_HEAD, 1)[1].strip().splitlines()[-1] == expected.note
    row = turn()
    assert (row.state, row.cost_usd, row.input_tokens) == ("posted", Decimal("0.012"), 1200)  # 뽑기 돈까지
    assert row.quote_lines == qrec.record_value(qrec.STATUS_OK, lines=expected.lines, allowed=expected.allowed)
    assert qrec.allowed_from(row.quote_lines) == expected.allowed


def test_a_customer_budget_amount_is_still_blocked_when_switched_on(channel):
    switch()
    confirm_prices()
    customer(channel, text=QUOTE_TEXT)
    budget = f"고객님, 말씀하신 예산 {won(MOLD['id'], 2400) + 10000:,}원에 맞춰 드릴게요."
    run(channel, brain_fn=FakeBrain(result(draft=budget)), pass_type=quoting(FakeQuoter(ask())))
    assert (turn().state, turn().error_code) == ("skipped", "check_failed")


def test_a_quote_that_cannot_be_calculated_goes_to_a_human_without_a_draft(channel):
    switch()
    customer(channel, text=QUOTE_TEXT)
    zero = dict(MOLD, id=990001, price_30cm=0, price_1cm=0)
    poster = FakePoster()
    summary = run(channel, "memo", brain_fn=FakeBrain(max_calls=0), poster=poster,
                  pass_type=quoting(FakeQuoter(ask(space(zero["id"]))), catalog(extra=[zero])))
    row = turn()
    assert (row.state, row.error_code, row.handoff, row.handoff_reason, row.intent) == (
        "skipped", qc.HUMAN_ZERO, True, qc.HUMAN_ZERO, qb.QUOTE_INTENT)
    assert (row.cost_usd, poster.calls, summary.quotes, summary.brain_calls) == (Decimal("0.002"), [], {"human": 1}, 1)
    assert row.quote_lines["status"] == qrec.STATUS_HUMAN and qrec.allowed_from(row.quote_lines) == ()


def test_an_unknown_width_asks_one_thing_and_allows_no_amount(channel):
    switch()
    customer(channel, text=f"{CUSTOMER} 슬라이딩장 견적 부탁드려요")
    brain_fn = FakeBrain(result(draft="고객님, 설치하실 벽의 가로 길이를 알려 주시겠어요?"))
    summary = run(channel, brain_fn=brain_fn, pass_type=quoting(FakeQuoter(ask(space(width=0)))))
    (request,) = brain_fn.requests
    (line,) = request.calculator_lines
    assert qc.ASK_ORDER["width"] in line and summary.quotes == {"ask": 1} and turn().state == "stored"


def test_no_quote_words_or_not_a_quote_keeps_the_old_path(channel):
    switch()
    customer(channel)  # '선반 깊이 문의' — 견적 말이 없다
    quoter, brain_fn = FakeQuoter(ask()), FakeBrain()
    run(channel, brain_fn=brain_fn, pass_type=quoting(quoter))
    assert quoter.calls == [] and brain_fn.requests[0].calculator_lines == () and turn().quote_lines is None
    customer(channel, chat="uc-2", text=QUOTE_TEXT)
    other, brain_fn = FakeQuoter(dataclasses.replace(ask(), quote_request=False)), FakeBrain()
    summary = run(channel, brain_fn=brain_fn, pass_type=quoting(other))
    assert len(other.calls) == 1 and brain_fn.requests[0].calculator_lines == () and summary.quotes == {"not_quote": 1}


def test_extraction_errors_are_handled_like_the_draft_brain(channel):
    switch()
    customer(channel, text=QUOTE_TEXT)
    summary = run(channel, brain_fn=FakeBrain(max_calls=0),
                  pass_type=quoting(FakeQuoter(SpendCapReached(brain.DAILY_CAP_REACHED))))
    assert summary.halted == {"spend_cap": 1} and summary.released == 1 and turn().state == "failed"
    customer(channel, chat="uc-2", text=QUOTE_TEXT)
    summary = run(channel, brain_fn=FakeBrain(max_calls=0), pass_type=quoting(FakeQuoter(
        BrainUnavailable(BAD_RESPONSE))))
    assert (turn("uc-2").state, turn("uc-2").error_code, summary.halted) == ("failed", BAD_RESPONSE, {})


def test_quote_notes_in_old_memos_are_not_private_leak_material():
    old = memo_text("합성 초안", "직원끼리 확인할 합성 참고 문장입니다\n[견적 계산 — 확인 날 2026-10-30] 안방 · 긴합성제품이름 · 가로")
    lines = [SimpleNamespace(text=old, meta=SimpleNamespace(is_private=True, is_log=False))]
    (snippet,) = memo_snippets(lines)
    assert old.startswith(MEMO_HEAD) and "직원끼리" in snippet and MEMO_QUOTE_HEAD not in snippet


def test_the_panel_switch_starts_off():
    field = st.FIELD_BY_NAME[qs.SETTING]
    assert (field.kind, field.default, field.locked) == (st.KIND_BOOL, False, False)
    assert qs.looks_like_quote(["가로 2.4m 얼마예요"]) and not qs.looks_like_quote(["내일 배송 언제 와요"])


def test_the_turn_record_carries_no_customer_text_and_passes_the_mask_check():
    from foms.services.cs_agent.masking import leak_counts

    outcome = evaluate(ask(space(options=((OPTION, 2),), height_mm=2300, door="sliding"), space(OTHER["id"], 1800)))
    record = qrec.record_value(outcome.status, lines=outcome.lines, allowed=outcome.allowed)
    assert not any(leak_counts("\n".join([*record["lines"], *record["allowed"]])).values())
    assert qrec.allowed_from({**record, "status": qrec.STATUS_CHECK}) == () and qrec.allowed_from(None) == ()
    assert qrec.allowed_from({**record, "allowed": "한 글"}) == () and qrec.lines_from(record) == outcome.lines
    assert datetime.timedelta(days=qk.FRESH_DAYS) == datetime.timedelta(days=14)
