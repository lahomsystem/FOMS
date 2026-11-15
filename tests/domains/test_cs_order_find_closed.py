"""상담 AI 주문 찾기 — 끝난 주문도 후보(사용자 결정 D220 · 접목판 원장 F-12).

완료 기준: 끝난 주문만 맞으면 확인됨(세 길 모두) · 진행 중 + 끝난 주문이 같이 맞으면 진행 중이 먼저 · 끝난 지
옛 끝난 주문도 찾음(기간 없음 — D225) · 휴지통 · 초안 · ERP 주문 아님은 끝난 주문이어도 그대로 빠짐 · 끝난 주문의
주문 칸에는 지난 실측 · 시간대(예정) · 배송 예정 칸이 없음(진행 중 주문 칸은 그대로) · 접목판 규칙 ①이 끝난 주문에서 AS 접수
제안을 만듦. 합성 주문 · 가짜 채널톡 · 가짜 두뇌(네트워크 0). 전화 꼴은 실행 때 만든다(:mod:`.test_cs_order_lookup`).
"""

from __future__ import annotations

import datetime

from db import db_session
from foms.services.cs_agent import order_find
from foms.services.cs_agent.order_block import ORDER_RULES, order_block, order_facts
from foms.services.datetime_kst import get_today_kst
from tests.domains.test_cs_drafting import FakeBrain, channel, result, run, turn  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_graft_step import chat, graft_env_off, proposals, seed_order, switches  # noqa: F401
from tests.domains.test_cs_order_lookup import NAME, PHONE, add_order
from tests.support.cs_agent_fakes import keys  # noqa: F401 — keys 는 fixture

WHO = [f"{NAME} {PHONE}"]


def closed(*, days_ago: int = 30, stage: str = "COMPLETED", **kwargs):
    """끝난 지 ``days_ago`` 날 된 합성 주문(열린 AS 없음) — 끝난 날은 단계 바뀐 때 칸, 만든 때도 같게 둔다."""
    order = add_order(stage=stage, **kwargs)
    when = datetime.datetime.combine(get_today_kst(), datetime.time(12)) - datetime.timedelta(days=days_ago)
    order.erp_stage_updated_at = when
    order.created_at = when
    db_session.commit()
    return order


# ── 찾기 ────────────────────────────────────────────────────────────────
def test_a_finished_order_alone_is_confirmed_on_every_path(app):
    done = closed()
    found = order_find.by_contact(db_session, WHO)
    assert (found.status, found.basis, found.order.id) == ("one", "contact", done.id)
    assert order_find.by_profile(db_session, (NAME, PHONE)).order.id == done.id
    hit = order_find.by_number(db_session, [f"주문번호 {done.id} 끝자리 {PHONE[-4:]}"])
    assert (hit.status, hit.order.id) == ("one", done.id)


def test_an_as_finished_order_is_a_candidate_too(app):
    done = closed(stage="AS_COMPLETED", as_status="COMPLETED")
    assert order_find.by_contact(db_session, WHO).order.id == done.id


def test_an_open_order_wins_over_finished_ones(app):
    closed(days_ago=10)
    live = add_order(stage="PRODUCTION")
    closed(days_ago=200, product="합성 신발장")
    found = order_find.by_contact(db_session, WHO)
    assert (found.status, found.order.id) == ("one", live.id)  # 열린 주문이 하나면 끝난 주문은 '여럿'을 만들지 않는다
    assert order_find.by_profile(db_session, (NAME, PHONE)).order.id == live.id


def test_several_finished_orders_without_an_open_one_stay_several(app):
    closed(days_ago=10)
    wanted = closed(days_ago=100, product="합성 신발장")
    several = order_find.by_contact(db_session, WHO)
    assert several.status == "several" and len(several.candidates) == 2
    assert order_find.narrow(several, [*WHO, "신발장 문의예요"]).order.id == wanted.id


def test_an_open_order_is_not_pushed_out_by_many_finished_ones(app):
    live = add_order(stage="MEASURE")
    for _ in range(order_find.MAX_CANDIDATES + 2):  # 열린 주문보다 새 번호인 끝난 주문이 상한보다 많아도
        closed(days_ago=5)
    assert order_find.by_contact(db_session, WHO).order.id == live.id


def test_old_finished_orders_are_found_with_no_window(app):
    """D225 — 끝난 주문은 기간 없이 찾는다(무상 AS 는 시공일로부터 1년이지만 찾기는 전체)."""
    old = closed(days_ago=3 * 365)
    assert order_find.by_contact(db_session, WHO).order.id == old.id
    assert order_find.by_number(db_session, [f"주문번호 {old.id} 끝자리 {PHONE[-4:]}"]).order.id == old.id


def test_deleted_draft_and_non_erp_finished_orders_stay_out(app):
    closed(deleted=True)
    closed(erp=False)
    draft = closed()
    draft.status = "DRAFT"
    db_session.commit()
    assert order_find.by_contact(db_session, WHO).status == "none"


# ── 주문 칸 ─────────────────────────────────────────────────────────────
def test_a_finished_order_block_drops_past_plan_fields(app):
    done = closed(stage="COMPLETED")
    done.erp_construction_date = "2026-01-15"
    done.shipping_scheduled_date = "2026-01-10"
    done.is_self_measurement = True
    db_session.commit()
    facts = order_facts(done, "contact")
    text = "\n".join(order_block(facts)[1 + len(ORDER_RULES):])  # 칸 줄만(머리말 · 규칙 글 빼고)
    assert facts.measurement is None and facts.measurement_time == "" and facts.shipping is None
    assert not facts.self_measure
    assert "실측 날" not in text and "실측 시간대" not in text and "배송 예정" not in text and "직접 재는" not in text
    assert "단계: 완료" in text and "시공 날: 2026-01-15(목)" in text and "합성 붙박이장" in text
    assert facts.dates() == (datetime.date(2026, 1, 15),)


def test_an_open_order_block_is_unchanged(app):
    as_open = add_order(stage="COMPLETED", as_status="RECEIVED")  # 끝난 단계 + 열린 AS = 예전부터 열린 주문
    for order in (add_order(), as_open):
        facts = order_facts(order, "contact")
        assert facts.measurement == datetime.date(2026, 11, 20) and facts.measurement_time == "10:00~12:00"


# ── 접목판 규칙 ① ───────────────────────────────────────────────────────
def test_as_words_on_a_finished_order_propose_an_as_intake(channel):
    switches(actions=True)
    order = seed_order("COMPLETED")
    chat(channel, "설치한 문짝이 처졌어요")
    brain_fn = FakeBrain(result())
    run(channel, brain_fn=brain_fn)
    (request,) = brain_fn.requests
    assert "단계: 완료" in "\n".join(request.order_lines)  # 끝난 주문이 확인돼 주문 칸이 실렸다
    (made,) = proposals()
    assert (made.action, made.status, made.order_id) == ("register_as", "open", order.id)
    assert "처졌어요" in made.params["as_content"] and PHONE not in made.params["as_content"]
    assert turn().state == "stored"
