"""검수 R17(C10-6 견적 교차 검수) — 재현 16건을 옮긴 것 + 고친 길(R17-1 · 2 · 3 · 6 · 9)의 시험.

재현 시험은 검수 사본(``r17/fuzz/test_r17_quote_review.py``)의 기대 동작 그대로다. 바꾼 곳 하나: '확인 필요인데 두뇌가 금액을
써도 직원 참고가 남아야' 시험은 R17-4 고침(두뇌 재료에 금액 없음) 뒤의 모습으로 옮겼다 — 두뇌는 금액 없는 초안을 쓰고 메모의
직원 참고 줄에 계산기 값이 남는다. 그래도 두뇌가 금액을 쓰면 막힌다(안전한 쪽 — 따로 단언). 실패 글에 금액을 찍지 않는다.
"""

from __future__ import annotations

import datetime
import math
from decimal import Decimal

import pytest

from db import db_session
from foms.services.cs_agent import loop, memo, quote_brain as qb, quote_calc as qc, quote_record as qrec
from foms.services.cs_agent import quote_check as qk, quote_step as qs, rewrite, send_flow, turns
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_spend import API_ERROR, DAILY_CAP_REACHED, BrainUnavailable, SpendCapReached
from foms.services.cs_agent.drafting_read import MEMO_NOTE_HEAD, memo_text
from foms.services.cs_agent.drafting_summary import DraftSummary
from foms.services.cs_agent.knowledge_doc import ApprovedKnowledge
from foms.services.cs_agent.masking import mask
from foms.services.cs_agent.realtime import CLAIM_MARGIN, CLAIM_TTL, claim_ttl
from foms.services.cs_agent.settings import PanelSettings
from foms.services.wdcalculator import catalog as cat
from foms.services.wdcalculator import pricing
from tests.domains.test_cs_drafting import NOTE, FakeBrain, FakePoster, channel, customer, result, run, turn  # noqa: F401
from tests.domains.test_cs_quote import _request
from tests.domains.test_cs_send import FakeSender, posted, press, switches, token, user
from tests.domains.test_cs_send_parts import ready  # noqa: F401 — fixture
from tests.support.cs_agent_fakes import FakeClock, api_message, at, keys, make_reader  # noqa: F401
from tests.support.cs_quote_support import (
    CATEGORIES, HAUD, MOLD, NOW, QUOTE_TEXT, FakeQuoter, amount_draft, ask, catalog, checked, confirm_prices,
    evaluate, quoting, rule_item, switch, won,
)


def quote_turn(channel, *, poster=None, check=True):
    """15분 바퀴가 견적 계산을 넣어 메모로 올린 차례(가짜 채널톡에 그 메모를 붙인다) — 차례 id."""
    switch()
    if check:
        confirm_prices()
    customer(channel, text=QUOTE_TEXT)
    poster = poster or FakePoster()
    run(channel, "memo", brain_fn=FakeBrain(result(draft=amount_draft())), poster=poster,
        pass_type=quoting(FakeQuoter(ask())))
    row = turn()
    channel.messages["uc-1"].append(api_message(row.memo_message_id, at(2, 9, 1), "bot", poster.calls[-1].text,
                                                options=["private"]))
    return row.id


def recorded_turn(channel, record):
    """메모를 올린 차례 + 그 차례 견적 기록(``quote_lines``) — :func:`tests.domains.test_cs_send.posted` 꼴."""
    customer(channel, "uc-1")
    row = turns.claim_turn(db_session, "LAHOM", "uc-1", "m-uc-1", now=at(2, 8, 51))
    turns.record_quote(row, quote_lines=record)
    turns.mark_posting(row, masked_draft=mask(amount_draft()), now=at(2, 8, 51))
    turns.mark_posted(row, memo_message_id="memo-uc-1", now=at(2, 8, 52))
    db_session.commit()
    channel.messages["uc-1"].append(api_message("memo-uc-1", at(2, 8, 52), "bot", memo_text(amount_draft(), NOTE),
                                                options=["private"]))
    return row.id


def ok_record(**kw):
    outcome = evaluate(ask())
    return qrec.record_value(outcome.status, lines=outcome.lines, allowed=outcome.allowed, **kw)


# ── 높음 1: [보내기] 가 그 차례 계산기 값을 안다 ─────────────────────────────
def test_r17_send_button_accepts_an_unedited_quote_draft(app, channel):
    turn_id = quote_turn(channel)
    switches()
    result_ = press(app, channel, turn_id, user().id, FakeSender(channel))
    assert result_.code == "sent", result_.code


def test_r17_send_button_accepts_a_lightly_edited_quote_draft(app, channel):
    turn_id = quote_turn(channel)
    switches()
    text = amount_draft() + " 감사합니다."
    first = press(app, channel, turn_id, user().id, FakeSender(channel), mode="edited", text=text, edit_reason="missing")
    assert first.code in ("sent", "needs_confirm"), first.code


@pytest.mark.parametrize("record", [None, "needs_check"])
def test_the_send_button_still_blocks_amounts_without_a_confirmed_calculator_record(app, channel, record):
    if record is None:  # 음성 대조 — 견적 기록이 없는 예전 차례(검수 전 그대로 막힘)
        turn_id = posted(channel, draft=amount_draft())
    else:  # 확인 필요 기록은 허용 목록에 더하지 않는다
        turn_id = recorded_turn(channel, qrec.record_value(qrec.STATUS_CHECK, lines=(qc.CHECK_LINE,)))
    switches()
    assert press(app, channel, turn_id, user().id, FakeSender(channel)).code == "blocked"


def test_a_rewrite_reuses_the_turns_calculator_lines_and_amounts(app, ready):
    staff = user()
    turn_id = recorded_turn(ready, ok_record())
    send_flow.request_rewrite(db_session, turn_id=turn_id, user_id=staff.id,
                              token=token(app, turn_id, staff.id),
                              note="조금 더 짧게", secret_key=app.secret_key, now=NOW)
    brain_fn = FakeBrain(result(draft=amount_draft() + " 확인 부탁드립니다."))
    posted_texts = []

    def post(chat_id, text, *, brand, **kwargs):
        posted_texts.append(text)
        return memo.MemoResult(True, verified=True, message_id="memo-2")

    counts = rewrite.run_rewrites(db_session, now=NOW, stop=loop.StopFlag(), reader=make_reader(ready, FakeClock()),
                                  brain=brain_fn, poster=post)
    (request,) = brain_fn.requests
    same_lines = request.calculator_lines == evaluate(ask()).lines
    assert counts == {"done": 1} and same_lines and len(posted_texts) == 1


# ── 중간 2: 다시 올리기(메모 실패 뒤)도 그 차례 계산기 값을 안다 ─────────────
def test_r17_repost_of_a_quote_draft_is_not_blocked(channel):
    switch()
    confirm_prices()
    customer(channel, text=QUOTE_TEXT)
    run(channel, "memo", brain_fn=FakeBrain(result(draft=amount_draft())),
        poster=FakePoster(memo.MemoResult(False, reason="send_provider_error")), pass_type=quoting(FakeQuoter(ask())))
    assert (turn().state, turn().error_code) == ("failed", "send_provider_error")
    run(channel, "memo", brain_fn=FakeBrain(max_calls=0), poster=FakePoster(), now=at(2, 9, 15),
        pass_type=quoting(FakeQuoter(ask())))
    assert turn().state == "posted", (turn().state, turn().error_code, turn().check_codes)


# ── 중간 3: 초안 두뇌가 실패 · 놓아주기로 끝나도 뽑기 돈이 차례 줄에 남는다 ─────────
@pytest.mark.parametrize("failure", [BrainUnavailable(API_ERROR), SpendCapReached(DAILY_CAP_REACHED)])
def test_r17_extraction_cost_stays_on_the_turn_when_the_draft_brain_fails(channel, failure):
    switch()
    customer(channel, text=QUOTE_TEXT)
    run(channel, brain_fn=FakeBrain(failure), pass_type=quoting(FakeQuoter(ask())))
    row = turn()
    assert row.state == "failed"
    assert (row.cost_usd or Decimal(0)) >= ask().cost_usd and row.input_tokens == ask().input_tokens


# ── 중간 4: '확인 필요'면 금액은 두뇌 재료가 아니라 직원 참고 줄에만 ─────────────
def test_r17_needs_check_does_not_hand_amounts_to_the_draft_brain():
    stale = evaluate(ask(), check=checked(20))
    amount = f"{won(MOLD['id'], 2400):,}"
    assert stale.status == qc.STATUS_CHECK
    assert not any(amount in line for line in stale.lines), "확인 필요 금액이 두뇌 재료(calculator_lines)에 있다"


def test_r17_needs_check_leaves_the_amounts_in_the_staff_note(channel):
    switch()  # 버튼을 누른 적 없음 — 확인 날 없음 = 확인 필요
    customer(channel, text=QUOTE_TEXT)
    poster, brain_fn = FakePoster(), FakeBrain(result(draft="고객님, 실측 뒤 정확한 금액을 안내드리겠습니다."))
    run(channel, "memo", brain_fn=brain_fn, poster=poster, pass_type=quoting(FakeQuoter(ask())))
    assert brain_fn.requests[0].calculator_lines == (qc.CHECK_LINE,)
    assert poster.calls, (turn().state, turn().error_code)
    note = poster.calls[0].text.split(MEMO_NOTE_HEAD, 1)[1]
    assert f"{won(MOLD['id'], 2400):,}원" in note and "확인 필요" in note
    customer(channel, chat="uc-2", text=QUOTE_TEXT)  # 그래도 두뇌가 금액을 쓰면 막힌다(안전한 쪽)
    run(channel, brain_fn=FakeBrain(result(draft=amount_draft())), pass_type=quoting(FakeQuoter(ask())))
    assert (turn("uc-2").state, turn("uc-2").error_code) == ("skipped", "check_failed")


# ── 중간 5: 값과 무관한 저장은 확인 날을 새로 하지 않는다(D74) ─────────────────
def test_r17_unrelated_settings_save_does_not_refresh_the_price_check_day(app, wdcalculator_settings_env):
    import foms.api.wdcalculator.blueprint as wd

    with app.app_context():
        assert wd.save_products([dict(MOLD)])
    qk.observe(db_session, cat.read_catalog(), now=NOW)
    confirm_prices(cat.read_catalog(), when=NOW)
    first = qk.observe(db_session, cat.read_catalog(), now=NOW).confirmed_at
    with app.app_context():
        assert wd.save_spec_field_presets({f: [{"id": 1, "name": "합성"}] for f in wd.SPEC_PRESET_FIELDS})
    second = qk.observe(db_session, cat.read_catalog(), now=NOW + datetime.timedelta(hours=2)).confirmed_at
    assert second == first, "값을 안 바꾼 저장이 확인 날을 새로 했다"


# ── 중간 6: 빠른 길 선점 만료에 뽑기 상한을 더한다 ─────────────────────────────
def _cfg(**values):
    return PanelSettings({**st.DEFAULTS, **values})


def test_r17_realtime_worst_case_fits_the_claim():
    """처음 값(시간 상한 45초 · 다시 시도 0): 견적 전 초안 45 + 채널톡 4번 40 = 85 ≤ 선점 90 — 견적 뒤 뽑기 20 이 더 든다."""
    timeout = st.DEFAULTS["realtime_timeout_s"]
    assert st.DEFAULTS["realtime_retries"] == 0
    reads = 4 * 10.0  # 상담 읽기 둘 + 직전 다시 읽기 + 메모 올리기(채널톡 요청 하나 10초 상한)
    ttl = claim_ttl(_cfg(quote_calc_enabled=True)).total_seconds()
    assert timeout + reads <= (claim_ttl(_cfg()).total_seconds())  # 견적 끔 — 예전 그대로
    assert qb.REALTIME_TIMEOUT_CAP + timeout + reads <= ttl, (qb.REALTIME_TIMEOUT_CAP, timeout, reads, ttl)


@pytest.mark.parametrize(("retries", "extraction"), [(0, 20.0), (1, 42.0)])
def test_the_claim_adds_the_extraction_worst_case_only_when_quotes_are_on(retries, extraction):
    on, off = _cfg(quote_calc_enabled=True, realtime_retries=retries), _cfg(realtime_retries=retries)
    assert claim_ttl(off) == datetime.timedelta(seconds=st.DEFAULTS["realtime_timeout_s"]) + CLAIM_MARGIN == CLAIM_TTL
    assert qb.worst_seconds(on) == extraction  # 다시 시도 1 = 20초 두 번 + 쉼 2초
    assert claim_ttl(on).total_seconds() == st.DEFAULTS["realtime_timeout_s"] + extraction + CLAIM_MARGIN.total_seconds()
    short = _cfg(quote_calc_enabled=True, realtime_timeout_s=20, realtime_retries=retries)
    assert qb.worst_seconds(short) == (retries + 1) * 20 + retries * 2.0  # 시간 상한이 뽑기 상한보다 작으면 그 값


# ── 낮음 7: 서버 숫자 읽기 = JS Number() ─────────────────────────────────────
@pytest.mark.parametrize("text", ["１２", "١٢", "﻿12", "0b11", "0o17"])
def test_r17_js_number_matches_javascript(text):
    js = {"１２": math.nan, "١٢": math.nan, "﻿12": 12.0, "0b11": 3.0, "0o17": 15.0}[text]
    got = pricing.js_number(text)
    assert (math.isnan(got) and math.isnan(js)) or got == js, (text, got)


def test_r17_infinite_width_does_not_crash_the_server_calc():
    comp = {"mode": "select", "productId": MOLD["id"], "widthMm": "Infinity", "additionalFees": []}
    got = pricing.compute_estimate([comp], [MOLD], [])  # 화면은 Infinity 를 낸다 — 서버도 예외 없이
    assert not math.isfinite(got.total_price_collect)


# ── 낮음 8: 깨진 옵션 칸은 바퀴를 죽이지 않는다 ───────────────────────────────
def test_r17_corrupt_option_entry_goes_to_a_human_not_an_exception():
    broken = {"id": 991, "name": "합성", "options": ["깨진 칸"]}
    outcome = evaluate(ask(), catalog(categories=[broken]))
    assert outcome.status in (qc.STATUS_OK, qc.STATUS_HUMAN)


# ── 낮음 9: 라홈 후보는 같은 id 하우드 줄을 집지 않는다 ───────────────────────
def test_r17_lahom_candidate_never_prices_a_haud_row():
    twin = dict(HAUD, id=int(MOLD["id"]))
    lahom = dict(MOLD, id=str(MOLD["id"]))
    catalog_ = cat.Catalog((twin, lahom), tuple(CATEGORIES))
    asked = qb.read_ask('{"quote_request": true, "brand": "LAHOM", "unknown": [], "spaces": [{"space": "안방", '
                        f'"product_ids": ["{MOLD["id"]}"], "width_mm": 2400, "width_max_mm": 0, "height_mm": 0, '
                        '"door": "unknown", "handle": "unknown", "options": []}]}', catalog_)
    outcome = qc.evaluate(asked, catalog_, (), check=checked(), now=NOW)
    assert outcome.status == qc.STATUS_OK
    assert " ".join(str(HAUD["name"]).split()) not in outcome.lines[1], "라홈 후보 줄에 하우드 제품 이름이 있다"


# ── R17-9: 제작 조건 줄을 못 읽으면 빈 규칙이 아니라 사람에게(M23) ─────────────
def test_an_unreadable_build_rule_sends_a_quote_to_a_human(app):
    switch()
    request = _request()
    knowledge = ApprovedKnowledge(brand="LAHOM", version=1,
                                  items=(*request.knowledge.items, rule_item("검사: colour=red")))
    step = qs.prepare(session=db_session, knowledge=knowledge, request=request, texts=[QUOTE_TEXT], now=NOW,
                      stop=loop.StopFlag(), summary=DraftSummary(), quoter=FakeQuoter(ask()),
                      catalog_reader=catalog, price_check=lambda *_a, **_k: checked())
    assert (step.status, step.human, step.lines, step.allowed) == (qrec.STATUS_HUMAN, qc.HUMAN_RULE_UNREADABLE, (), ())
    readable = qs.prepare(session=db_session, knowledge=request.knowledge, request=request, texts=[QUOTE_TEXT],
                          now=NOW, stop=loop.StopFlag(), summary=DraftSummary(), quoter=FakeQuoter(ask()),
                          catalog_reader=catalog, price_check=lambda *_a, **_k: checked())
    assert readable.status == qrec.STATUS_OK  # 음성 대조 — 같은 재료에 제작 조건만 없으면 계산된다
