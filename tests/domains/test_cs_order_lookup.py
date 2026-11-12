"""주문 확인해 답하기(설계서 2026-11-12 온톨로지 5.6 · 사장님 D189 · D190) — 주문 문의 때만 본인을 확인해 ERP 주문 세부를 초안에.

완료 기준: 끄면 글자까지 그대로(두뇌 재료 · 표 쓰기 0) · 주문 문의 아니면 ERP 를 읽지 않음 · 못 찾으면 성함 · 휴대폰을 **한 번만**
물음(톡톡은 묻지 않고 넘김) · 답이 오면 두뇌 전에 찾아 한 번만 부름 · 넘긴 뒤 찾으면 한 번 더 부르고 쓰임을 더함 · 이름이 다른
주문 · 다른 번호 · 휴지통 · 초안 · 끝난 주문은 절대 싣지 않음 · 허용 목록 밖 칸(금액 · 주소 · 전화 · 이름) 0 · 초안 날짜는 그
주문 날짜만 통과 · 감사 줄에 값 · 글 없음. 합성 글 · 합성 주문 · 가짜 채널톡 · 가짜 두뇌(네트워크 0). 전화 꼴은 실행 때 만든다.
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace

from db import db_session
from foms.services.cs_agent import order_find, order_step
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_cases import QUOTE
from foms.services.cs_agent.onto_settings import ONTO_ORDER_FIELD
from foms.services.cs_agent.order_block import FIELDS, ORDER_RULES, order_block, order_facts
from foms.services.cs_agent.order_find import Lookup
from foms.services.cs_agent.order_step import ASK_MORE_TEXT, ASK_TEXT, LOG_KEY, NOTE_TEXTS
from models import Order, SystemSetting
from tests.domains.test_cs_drafting import NOW, FakeBrain, channel, customer, result, run, turn  # noqa: F401
from tests.support.cs_agent_fakes import at, keys  # noqa: F401 — keys 는 fixture

PHONE = "01" + "0" + "5550" + "1234"  # 합성 휴대폰(실행 때 만든다)
OTHER = "01" + "0" + "5550" + "9876"
NAME = "합성고객"
ADDRESS = "합성시 가상구 시험로 1"
AMOUNT = 4321987
ASK = "실측 언제 오시나요"
DATED = "실측은 11월 20일로 잡혀 있어요."  # 확인된 주문의 실측 날만 쓴 초안


def order_switch(on=True):
    value = {**st.DEFAULTS, ONTO_ORDER_FIELD: on}
    row = db_session.get(SystemSetting, st.SETTINGS_KEY)
    if row is None:
        db_session.add(SystemSetting(setting_key=st.SETTINGS_KEY, version=1, setting_value=value))
    else:
        row.setting_value = value
    db_session.commit()


def add_order(*, name=NAME, phone=PHONE, stage="MEASURE", erp=True, deleted=False, as_status=None, product="합성 붙박이장",
              measurement="2026-11-20"):
    data = {"schedule": {"measurement": {"date": measurement, "time": "10:00~12:00"}},
            "items": [{"product_name": product}, {"product_name": f"합성 수납장 {PHONE}"}],  # 전화 든 품목 이름은 빠진다
            "payment": {"total": AMOUNT}, "parties": {"customer": {"name": name, "phone": phone}}}
    order = Order(received_date="2026-11-01", customer_name=name, phone=phone, address=ADDRESS, product=product,
                  status="RECEIVED", is_erp_order=erp, erp_stage_code=stage, erp_measurement_date=measurement,
                  erp_phone_digits=phone, structured_data=data, as_axis_status=as_status, erp_owner_team_code="SALES",
                  deleted_at="2026-11-01 10:00:00" if deleted else None)
    db_session.add(order)
    db_session.commit()
    return order


def log_rows():
    db_session.expire_all()
    row = db_session.get(SystemSetting, LOG_KEY)
    return row.setting_value["rows"] if row is not None else []


def asked_before(chat="uc-1", act="asked", when=at(2, 8, 30)):
    when_utc = when.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    rows = [{"chat": chat, "turn": 0, "act": act, "basis": "", "order": None, "fields": [], "candidates": 0,
             "at": when_utc.isoformat(timespec="seconds")}]
    db_session.add(SystemSetting(setting_key=LOG_KEY, setting_value={"rows": rows}))
    db_session.commit()


def replied(channel, text=f"{NAME} {PHONE[:3]}-{PHONE[3:7]}-{PHONE[7:]}", medium="native"):
    """손님 물음 → 직원(공개)이 성함 · 휴대폰을 물음 → 손님 답."""
    customer(channel, text=ASK, when=at(2, 8, 20), medium=medium,
             more=[("m-ask", at(2, 8, 30), "manager", ASK_TEXT, {}), ("m-uc-1-2", at(2, 8, 50), "user", text, {})])


def handoff(reason="schedule"):
    return result(draft="", evidence_ids=(), handoff=True, handoff_reason=reason, staff_note="일정 문의")


# ── 찾기(서버 코드 · 원문) ───────────────────────────────────────────────
def test_mobiles_read_any_separator_and_country_code():
    texts = [f"{NAME} {PHONE[:3]}-{PHONE[3:7]}-{PHONE[7:]}", f"+82 {PHONE[1:3]} {PHONE[3:7]} {PHONE[7:]}", "치수 1200 x 600"]
    assert order_find.mobiles(texts) == (PHONE,)
    assert order_find.name_key("★합성 고객") == NAME


def test_contact_finds_only_the_open_order_with_the_same_name(app):
    mine = add_order()
    add_order(name="다른손님")  # 같은 번호 · 다른 이름
    add_order(phone=OTHER)  # 같은 이름 · 다른 번호
    for closed in (dict(deleted=True), dict(stage="COMPLETED"), dict(erp=False)):
        add_order(**closed)
    found = order_find.by_contact(db_session, [f"{NAME} {PHONE}"])
    assert (found.status, found.basis, found.order.id) == ("one", "contact", mine.id)
    assert order_find.by_contact(db_session, [f"다른이름 {PHONE}"]).status == "none"
    assert order_find.by_contact(db_session, [NAME]).status == "none"  # 휴대폰 없으면 찾지 않는다


def test_a_finished_order_counts_only_while_its_as_is_open(app):
    as_open = add_order(stage="COMPLETED", as_status="RECEIVED")
    assert order_find.by_contact(db_session, [f"{NAME} {PHONE}"]).order.id == as_open.id


def test_several_orders_are_narrowed_by_a_product_word_or_stay_several(app):
    add_order(product="합성 붙박이장")
    wanted = add_order(product="합성 신발장")
    several = order_find.by_contact(db_session, [f"{NAME} {PHONE}"])
    assert several.status == "several" and len(several.candidates) == 2
    assert order_find.narrow(several, [f"{NAME} {PHONE}", "신발장 문의예요"]).order.id == wanted.id
    assert order_find.narrow(several, ["그냥 문의"]).status == "several"


def test_order_number_needs_the_last_four_digits(app):
    order = add_order()
    hit = order_find.by_number(db_session, [f"주문번호 {order.id} 끝자리 {PHONE[-4:]}"])
    assert (hit.status, hit.basis, hit.order.id) == ("one", "number", order.id)
    assert order_find.by_number(db_session, [f"주문번호 {order.id} 끝자리 {OTHER[-4:]}"]).status == "mismatch"
    assert order_find.by_number(db_session, ["주문 문의예요"]).status == "none"


def test_profile_needs_the_exact_name_and_reads_only_the_user_field(app):
    order = add_order()
    assert order_find.by_profile(db_session, (NAME, PHONE)).order.id == order.id
    assert order_find.by_profile(db_session, (NAME + "님", PHONE)).status == "none"
    data = {"userChat": {"id": "uc-1"}, "user": {"profile": {"name": NAME, "mobileNumber": f"+82{PHONE[1:]}"}}}
    assert order_find.read_profile(None, "LAHOM", "uc-1", lambda *_a: data) == (NAME, PHONE)
    assert order_find.read_profile(None, "LAHOM", "uc-1", lambda *_a: {"userChat": {}}) is None


# ── 주문 칸(허용 목록만) ─────────────────────────────────────────────────
def test_the_block_carries_only_allowed_fields_and_no_money_address_phone_or_name(app):
    facts = order_facts(add_order(), "contact")
    lines = order_block(facts)
    text = "\n".join(lines)
    assert set(facts.fields()) <= set(FIELDS) and "products" in facts.fields()
    assert all(rule in lines for rule in ORDER_RULES)
    assert "단계: 실측" in text and "실측 날: 2026-11-20(금)" in text and f"{QUOTE}합성 붙박이장" in text
    for secret in (PHONE, PHONE[-4:], NAME, ADDRESS, str(AMOUNT), "SALES"):
        assert secret not in text, secret
    assert facts.dates() == (datetime.date(2026, 11, 20),)
    assert f"#{facts.order_id}" in facts.staff_line() and "SALES" in facts.staff_line()  # 주문 번호 · 팀은 직원 참고에만
    assert order_block(None) == []


# ── 초안 차례 ────────────────────────────────────────────────────────────
def test_off_keeps_the_old_handoff_and_writes_nothing(channel):
    order_switch(False)
    add_order()
    replied(channel)
    brain_fn = FakeBrain(handoff())
    run(channel, brain_fn=brain_fn)
    (request,) = brain_fn.requests
    assert request.order_lines == () and log_rows() == []
    assert (turn().state, turn().error_code, turn().handoff_reason) == ("skipped", "handoff", "schedule")


def test_other_handoffs_never_read_the_erp(channel):
    order_switch()
    add_order()
    replied(channel)
    brain_fn = FakeBrain(handoff("complaint"))
    run(channel, brain_fn=brain_fn)
    assert len(brain_fn.requests) == 1 and log_rows() == [] and turn().error_code == "handoff"


def test_unknown_customer_is_asked_for_name_and_phone_once(channel):
    order_switch()
    customer(channel, text=ASK)
    brain_fn = FakeBrain(handoff())
    run(channel, brain_fn=brain_fn)
    assert len(brain_fn.requests) == 1
    row = turn()
    assert (row.state, row.masked_draft, row.handoff) == ("stored", ASK_TEXT, False)
    assert [r["act"] for r in log_rows()] == ["asked"]


def test_talktalk_is_never_asked_for_a_number(channel):
    order_switch()
    customer(channel, text=ASK, medium="appNaverTalk")
    run(channel, brain_fn=FakeBrain(handoff()))
    assert (turn().state, turn().error_code) == ("skipped", "handoff")
    assert [r["act"] for r in log_rows()] == ["talktalk"]


def test_the_answer_is_found_before_the_brain_and_the_dated_draft_passes(channel):
    order_switch()
    order = add_order()
    asked_before()
    replied(channel)
    brain_fn = FakeBrain(result(draft=DATED, evidence_ids=()))
    run(channel, brain_fn=brain_fn)
    (request,) = brain_fn.requests  # 두뇌는 한 번
    assert request.order_lines and "실측 날: 2026-11-20(금)" in request.order_lines
    assert (turn().state, turn().masked_draft) == ("stored", DATED)
    (entry,) = log_rows()[1:]
    assert (entry["act"], entry["basis"], entry["order"]) == ("found", "contact", order.id)
    dumped = json.dumps(log_rows(), ensure_ascii=False)
    assert PHONE not in dumped and NAME not in dumped and ADDRESS not in dumped


def test_a_date_that_is_not_the_orders_date_is_blocked(channel):
    order_switch()
    add_order()
    asked_before()
    replied(channel)
    run(channel, brain_fn=FakeBrain(result(draft="실측은 11월 21일로 잡혀 있어요.", evidence_ids=())))
    assert (turn().state, turn().error_code) == ("skipped", "check_failed")
    assert "date_not_confirmed" in turn().check_codes


def test_a_handoff_with_contact_in_the_chat_calls_the_brain_again_and_adds_usage(channel):
    order_switch()
    add_order()
    customer(channel, text=f"{ASK} {NAME} {PHONE}")
    brain_fn = FakeBrain(handoff(), result(draft=DATED, evidence_ids=()))
    run(channel, brain_fn=brain_fn)
    first, again = brain_fn.requests
    assert first.order_lines == () and again.order_lines
    assert turn().masked_draft == DATED and turn().input_tokens == 1800
    assert [r["act"] for r in log_rows()] == ["found"]


def test_a_second_miss_hands_off_instead_of_asking_again(channel):
    order_switch()
    add_order(name="다른손님")  # 이름이 다른 주문은 절대 싣지 않는다
    asked_before()
    replied(channel)
    brain_fn = FakeBrain(handoff())
    run(channel, brain_fn=brain_fn)
    assert len(brain_fn.requests) == 1 and all(not r.order_lines for r in brain_fn.requests)
    assert (turn().state, turn().error_code) == ("skipped", "handoff")
    assert [r["act"] for r in log_rows()] == ["asked", "none"]


def test_several_matches_ask_for_a_product_once_then_hand_off(channel):
    order_switch()
    add_order(product="합성 붙박이장")
    add_order(product="합성 신발장")
    asked_before()
    replied(channel)
    run(channel, brain_fn=FakeBrain(handoff()))
    assert turn().masked_draft == ASK_MORE_TEXT and log_rows()[-1]["act"] == "asked_more"
    assert NOTE_TEXTS["several"] and order_step.pending_ask(db_session, "uc-1", NOW) == "asked_more"


def test_pending_ask_expires_and_reads_only_its_own_chat(app):
    asked_before(chat="uc-2")
    assert order_step.pending_ask(db_session, "uc-1", NOW) is None
    assert order_step.pending_ask(db_session, "uc-2", NOW) == "asked"
    assert order_step.pending_ask(db_session, "uc-2", NOW + order_step.ASK_WINDOW + datetime.timedelta(hours=1)) is None


def test_a_mismatched_order_number_tells_the_customer_nothing(app):
    order = add_order()
    turn_row = SimpleNamespace(id=7, chat_id="uc-9", brand="LAHOM")
    ctx = SimpleNamespace(session=db_session, now=NOW, stop=SimpleNamespace(check=lambda: None), order_turns={},
                          reader=SimpleNamespace(_get=lambda *_a: {"userChat": {}}),  # 손님 정보 칸 없음
                          summary=SimpleNamespace(brain_calls=0))
    order_switch()
    lines = [SimpleNamespace(text=f"주문번호 {order.id} 끝자리 {OTHER[-4:]}",
                             meta=SimpleNamespace(is_customer_signal=True, is_private=False))]
    out = order_step.lookup_after(ctx, turn_row, None, handoff("order_lookup"), lines, "native")
    assert out.handoff and NOTE_TEXTS["mismatch"] in out.staff_note and out.draft == ""
    assert isinstance(ctx.order_turns[7], order_step.OrderTurn) and Lookup("none").status == "none"
    (entry,) = log_rows()
    assert entry["act"] == "mismatch" and order_step.number_locked(db_session, "uc-9", NOW)
    right = [SimpleNamespace(text=f"주문번호 {order.id} 끝자리 {PHONE[-4:]}", meta=lines[0].meta)]
    again = order_step.lookup_after(SimpleNamespace(**{**vars(ctx), "order_turns": {}}), turn_row, None,
                                    handoff("order_lookup"), right, "native")
    assert again.draft == ASK_TEXT and not ctx.summary.brain_calls  # 잠긴 상담은 맞는 번호여도 번호 길로 찾지 않고 성함 · 휴대폰을 묻는다
