"""넘긴 상담 배우기 → 회사 지식(사장님 11-11 · 11-19) — 처음 끔 · 밤마다 남은 사례가 없을 때까지 · 새 것부터 · 늘 사람 몫인 까닭
뺌 · 직원 답이 있는 사례만 · 전체 대화와 사진 줄 · 앞뒤 대화 창 · 가림에 걸린 사례만 뺌 · 숫자 · 근거 · 겹침 · 부딪침 관문 · 읽은
차례 다시 안 읽음 · 다른 말은 엇갈림 카드로 · '배운 것 바로 반영'이 꺼져 있으면 승인 대기로만, 켜면 그 자리에서 반영.

합성 차례 · 합성 승인 지식(:data:`tests.domains.test_cs_drafting.KNOWLEDGE`) · 쪽을 넘기는 가짜 채널톡 · 가짜 학습 모델 · 가짜
부딪침 판정자만(네트워크 0). 손님 글 · 직원 이름 · 금액 없음. 시각은 2026-11 KST(11-11 수 — 창 안은 02:00).
"""

from __future__ import annotations

import datetime
import itertools

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.ai_gates import judge_source
from foms.services.brain.apply import apply_change
from foms.services.brain.card import actor_label
from foms.services.brain.display import AGENT_LABELS
from foms.services.brain.inbox import open_rows
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import learning_pass
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD, CASES_FIELD, EDIT_LEARN_FIELD, HANDOFF_LEARN_FIELD
from foms.services.cs_agent.handoff_learning_gates import AGENT, CLASH_HEAD
from foms.services.cs_agent.handoff_learning_place import placer_source
from foms.services.cs_agent.handoff_learning_prompt import (
    ANCHOR_MARK, CHIP_WORDS, INSTRUCTIONS, TALK_HEAD, TAUGHT_MARK, WHOLE_HEAD, anchor_mark, case_lines,
)
from foms.services.cs_agent.send_view import EDIT_REASON_LABELS
from foms.services.cs_agent.knowledge import load_approved
from models import CsAgentImageRead, CsAgentTurn
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_photo_cases import read_row
from tests.domains.test_cs_photo_read import PHONE
from tests.domains.test_cs_weekly_fix import into_brain, panel
from tests.support.brain_support import agent_judge, person
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    FakeAnthropic, FakeClock, FakePlacer, api_message, at, clash_placer, keys, make_reader, naive,
)
from tests.support.cs_talk_support import START, PagedChannel

NOW = at(11, 2)  # 수요일 KST 02:00
FACT = "합성 상판 두께는 18mm 로 만들어 드립니다"
REPLY = "합성 직원 답 — 상판 두께는 18mm 입니다"
_SEQ = itertools.count(1)


def handed(chat: str, *, reason="unsure", error="handoff", reply=REPLY, outcome="direct", state="skipped",
           held_out=False, codes=None, brand="LAHOM", when=None, anchor=None, context=None, staff="mgr-1",
           send_state=None, **extra) -> int:
    """넘긴 차례 하나(가린 질문 · 직원이 직접 한 가린 답). ``send_state`` 'sent' = 넘김 메모 [배우기]로 보낸 차례."""
    row = CsAgentTurn(brand=brand, chat_id=chat, last_user_message_id=anchor or f"m-{chat}-{next(_SEQ)}", state=state,
                      send_state=send_state, **extra,
                      error_code=error, handoff=error == "handoff", handoff_reason=reason, check_codes=codes,
                      outcome=outcome, intent="spec", held_out=held_out, masked_question="합성 상판 두께가 어떻게 돼요?",
                      staff_reply_masked=reply, masked_context=context, desk_manager_id=staff,
                      updated_at=naive(when or at(10, 15)))
    db_session.add(row)
    db_session.commit()
    return row.id


def on(**extra):
    panel(**{HANDOFF_LEARN_FIELD: True, **extra})


def ask(ids, **fields):
    base = {"op": "create", "item_type": "fact", "key": "", "title": "합성 상판 두께", "text": FACT,
            "why": "합성 — 두 손님에게 직원이 같은 두께를 안내했다", "evidence_turn_ids": list(ids)}
    return {**base, **fields}


def body(client, index=0):
    return client.params[index]["messages"][0]["content"][0]["text"].split("\n")


def changes():
    db_session.expire_all()
    return list(db_session.scalars(select(BrainChange).where(BrainChange.proposed_by == f"agent:{AGENT}")
                                   .order_by(BrainChange.id)))


def run(client, now=NOW, reader=None, placer=None):
    """밤 한 번 — 합성 부딪침 판정자(부딪침 없음) + 합성 놓을 자리 판정자(처음 값 '새 지식')."""
    with agent_judge(), placer_source(placer or FakePlacer()):
        return hl.run_handoff_learning(db_session, now=now, client=client, reader=reader)


@pytest.fixture
def admin(channel):  # noqa: F811
    """회사 지식 표로 옮긴 승인 지식(운영처럼 — 표가 정본)."""
    owner = person(db_session, "handoff-learn-admin")
    into_brain(owner)
    return owner


@pytest.fixture
def two(admin):
    """서로 다른 손님 둘의 넘긴 사례(근거 관문을 넘는다)."""
    return [handed("uc-1"), handed("uc-2")]


# ── 끄고 켜기 · 밤마다 남은 사례가 없을 때까지 ───────────────────────────
def test_off_by_default_outside_the_window_and_every_tick_until_nothing_is_left(two):
    client = FakeAnthropic({"proposals": []})
    panel()
    assert hl.run_handoff_learning(db_session, now=NOW, client=client) == {"off": "switch_off"}
    on(**{CASES_FIELD: 2})
    assert hl.run_handoff_learning(db_session, now=at(11, 9), client=client) == {"off": "not_window"}
    third = handed("uc-3")
    first = run(client)
    assert (first["cases"], first["sent"], first["filed"], first["halted"]) == (2, 2, 0, None)
    second = run(client, now=at(11, 2, 15))  # 같은 밤 다음 바퀴 — 남은 사례를 읽는다
    assert (second["cases"], second["sent"]) == (1, 1) and len(client.params) == 2
    assert f"사례 {two[0]} 손님 글:" in body(client, 1) and f"사례 {third} 손님 글:" in body(client, 0)  # 새 것부터
    last = run(client, now=at(11, 2, 30))  # 남은 사례 없음 — 두뇌를 부르지 않고 그 밤을 닫는다
    assert (last["cases"], len(client.params)) == (0, 2)
    assert run(client, now=at(11, 2, 45)) == {"off": "already_today"} and len(client.params) == 2
    on(learning_cap_usd_panel=None)
    assert run(client, now=at(13, 1)) == {"off": "no_learning_cap"}


def test_an_overlapping_container_waits_and_a_night_stops_at_the_run_limit(admin):
    day, start = "2026-11-12", at(12, 1)
    assert hl.claim_day(db_session, day, start)
    assert not hl.claim_day(db_session, day, start + datetime.timedelta(minutes=5))  # 다른 부르기가 도는 중
    assert hl.claim_day(db_session, day, start + hl.LEASE + datetime.timedelta(seconds=1))  # 죽은 부르기의 잠금은 풀린다
    for _ in range(hl.MAX_RUNS - 2):
        hl.release(db_session)
        assert hl.claim_day(db_session, day, start)
    hl.release(db_session)
    assert not hl.claim_day(db_session, day, start)  # 한 밤 상한
    hl.close_day(db_session, "2026-11-13")
    assert not hl.claim_day(db_session, "2026-11-13", start)


def test_the_next_night_never_rereads_used_cases(two):
    on()
    client = FakeAnthropic({"proposals": []})
    run(client)
    fresh = [handed("uc-3"), handed("uc-4")]
    again = run(client, now=at(12, 1, 15))
    lines = body(client, 1)
    assert (again["cases"], again["sent"]) == (2, 2)
    assert all(f"사례 {i} 손님 글:" in lines for i in fresh)
    assert not any(f"사례 {i} 손님 글:" in lines for i in two)  # 이미 읽은 차례는 다시 안 보낸다
    assert hl.used_ids(db_session) == frozenset([*two, *fresh])


def test_a_failed_call_keeps_the_cases_for_the_next_night(two):
    on(learning_cap_usd_panel="0")  # 학습 돈 0 — 보내기 전에 막힌다
    counts = run(FakeAnthropic({"proposals": []}))
    assert counts["halted"] == "daily_cap_reached" and hl.used_ids(db_session) == frozenset()


# ── 읽기 ─────────────────────────────────────────────────────────────────
def test_every_staff_answered_turn_is_read_whatever_the_reason(admin):
    """사장님 11-20 '뭐든지 다 배워서' — 늘 사람 몫이던 까닭(불만 · 주문 조회 · 할인 환불 · 금액 · 견적) · 배우기만 차례도 읽는다."""
    on()
    wanted = [handed("uc-1", reason=r) for r in ("unsure", "photo", "schedule", "other", "complaint", "order_lookup",
                                                 "discount_refund", "human_only_amount")]
    wanted.append(handed("uc-2", error="check_failed", reason="none", codes=["refund_promise"]))
    wanted.append(handed("uc-2", error="quote_zero", reason="quote_zero"))
    wanted.append(handed("uc-2", error="learn_only", reason=None))  # 초안 스위치 '배우기만' 차례
    handed("uc-3", reason="asked_if_ai")  # 'AI 냐 사람이냐' — 배울 사실이 없다
    handed("uc-3", reply=None)  # 직원 답이 없는 사례
    handed("uc-3", held_out=True)
    handed("uc-3", outcome="copied")
    handed("uc-3", state="posted")  # 초안이 나간 차례는 패널 칸이 켜져 있을 때만
    handed("uc-3", brand="HAUD")
    handed("uc-3", when=NOW - hl.LEARN_LOOKBACK - datetime.timedelta(days=1))  # 읽는 창 밖
    cases = hl.collect_cases(db_session, NOW, cap=20)
    assert [case["turn_id"] for case in cases] == wanted[::-1]  # 새 것부터 — 오늘 상담을 오늘 밤 배운다
    assert [case["reason"] for case in cases] == ["learn_only", "other", "check_failed", "human_only_amount",
                                                  "discount_refund", "order_lookup", "complaint", "other", "schedule",
                                                  "photo", "unsure"]
    assert [c["turn_id"] for c in hl.collect_cases(db_session, NOW, cap=2)] == wanted[::-1][:2]  # 상한만
    assert "AI 초안 없이 직원이 답함" in case_lines({**cases[0], "talk": None})[0]


def test_no_case_never_reaches_the_model(admin):
    on()
    client = FakeAnthropic({"proposals": []})
    counts = run(client)
    assert (counts["sent"], client.params) == (0, [])


def test_one_customer_case_reaches_the_model_and_a_fact_without_numbers_is_filed(admin):
    """사장님 11-11 '넘긴 상담마다 배워 다음 상담에' — 한 손님 사례로도 안을 낸다(늘 사장님 승인)."""
    on()
    one = handed("uc-1", reply="합성 직원 답 — 양쪽으로 열 수 있어요")
    client = FakeAnthropic({"proposals": [ask([one], title="합성 열림 방향", text="합성 문은 양쪽으로 열 수 있어요")]})
    counts = run(client)
    assert (counts["sent"], counts["filed"], len(client.params)) == (1, 1, 1), counts
    assert [c.fields["payload"]["after"]["pref_label"] for c in changes()] == ["합성 열림 방향"]
    assert changes()[0].evidence == [f"case:{one}", "staff:mgr-1"]  # 손님 한 명 + 답한 직원 한 명


def test_one_customer_case_without_a_known_staff_is_held_by_the_knowledge_gate(admin):
    on()
    one = handed("uc-1", reply="합성 직원 답 — 양쪽으로 열 수 있어요", staff=None)
    counts = run(FakeAnthropic({"proposals": [ask([one], title="합성 열림 방향", text="합성 문은 양쪽으로 열 수 있어요")]}))
    assert counts["blocked"] == {"brain_evidence": 1} and changes() == []


# ── 재료 ─────────────────────────────────────────────────────────────────
def long_talk(chat: str, count: int = 40) -> list[dict]:
    """손님 · 직원이 번갈아 쓴 긴 합성 글(글마다 239자)."""
    return [api_message(f"{chat}-{i:03d}", START + datetime.timedelta(minutes=i), "user" if i % 2 == 0 else "manager",
                        f"합성 글 {i:03d} " + "합성 이야기 " * 33) for i in range(count)]


def test_the_material_is_a_window_around_the_question_with_the_reaction_after(admin):
    on(full_talk_chars=2000)
    first = handed("uc-1", anchor="uc-1-020")
    second = handed("uc-2", context="[손님] 합성 앞 대화")
    chan = PagedChannel()
    chan.chat("uc-1", *long_talk("uc-1"))
    client = FakeAnthropic({"proposals": []})
    counts = run(client, reader=make_reader(chan, FakeClock()))
    lines = body(client)
    text = "\n".join(lines)
    assert (counts["talks"], counts["sent"]) == (1, 2)
    assert f"사례 {first} {TALK_HEAD}" in lines and "| (앞 대화 16줄 줄임)" in lines and "| (뒤 대화 16줄 줄임)" in lines
    question = next(i for i, line in enumerate(lines) if line.startswith("| [손님] 합성 글 020"))
    assert lines[question + 1] == f"| {ANCHOR_MARK}" and lines[question + 2].startswith("| [직원] 합성 글 021")
    assert "합성 글 016" in text and "합성 글 023" in text and "합성 글 015" not in text and "합성 글 024" not in text
    assert f"사례 {second} 앞 대화(그 손님과 이미 나눈 말):" in lines and "| [손님] 합성 앞 대화" in lines  # 못 읽음 — 6줄
    assert lines.index(f"사례 {first} 직원이 직접 한 답:") > lines.index(f"사례 {first} 손님 글:")
    assert client.params[0]["system"][0]["text"] == INSTRUCTIONS and client.params[0]["model"] == "claude-sonnet-5-5"
    assert "[lahom/shelf-depth] 사실 shelf-depth (고칠 수 있음): 합성 선반 깊이는 350mm 입니다" in lines


def test_a_short_talk_is_sent_whole_once_with_photo_lines_and_case_marks(admin):
    """사장님 11-19 '대화 전체와 이미지까지' — 상한 안이면 전체 대화를 한 번만 싣고 같은 상담의 다른 사례는 그것을 가리킨다."""
    on()
    first = handed("uc-1", anchor="uc-1-002")
    second = handed("uc-1", anchor="uc-1-004")
    photo = handed("uc-1", reason="asked_if_ai", anchor="uc-1-000")  # 배우지 않는 차례가 읽은 사진도 그 상담 대화에 싣는다
    read_row(photo, chat="uc-1")
    db_session.execute(CsAgentImageRead.__table__.update().values(message_id="uc-1-000"))
    db_session.commit()
    chan = PagedChannel()
    chan.chat("uc-1", *long_talk("uc-1", count=6))
    client = FakeAnthropic({"proposals": []})
    counts = run(client, reader=make_reader(chan, FakeClock()))
    lines = body(client)
    assert (counts["talks"], counts["sent"]) == (2, 2)
    assert sum(line.endswith(WHOLE_HEAD) for line in lines) == 1 and f"사례 {second} {WHOLE_HEAD}" in lines  # 새 사례가 싣는다
    assert sum(line.startswith("| [손님] 합성 글 000") for line in lines) == 1  # 대화는 한 번만
    start = next(i for i, line in enumerate(lines) if line.startswith("| [손님] 합성 글 000"))
    assert lines[start + 1].startswith("| ▶ 사진 1 (손님) ")  # 그 사진이 온 글 바로 뒤
    assert f"| {anchor_mark(first)}" in lines and f"| {anchor_mark(second)}" in lines
    assert any(line.startswith(f"사례 {first} 상담 전체 대화: 사례 {second} 과 같은 상담") for line in lines)
    assert "온톨로지 목록(상황 · 제작 조건 · 제품 · 옵션 — 키는 대괄호 안):" in lines


def test_a_mask_leak_drops_only_that_case(admin):
    on()
    kept = [handed("uc-1"), handed("uc-2")]
    leaked = handed("uc-3", reply=f"합성 답 {PHONE}")
    client = FakeAnthropic({"proposals": []})
    counts = run(client)
    assert (counts["mask_dropped"], counts["sent"]) == (1, 2)
    assert PHONE not in "\n".join(body(client)) and f"사례 {leaked} 손님 글:" not in body(client)
    assert hl.used_ids(db_session) == frozenset([*kept, leaked])  # 다음 밤에 다시 읽지 않는다


# ── 관문 · 넣기 ──────────────────────────────────────────────────────────
def test_passing_ideas_land_in_the_inbox_as_open_agent_proposals_and_drafts_learn_only_after_approval(two, admin):
    on()
    counts = run(FakeAnthropic({"proposals": [ask(two)]}))
    assert (counts["proposed"], counts["filed"], counts["blocked"]) == (1, 1, {})
    (change,) = changes()
    assert (change.op, change.item_type, change.layer, change.brand, change.status) == (
        "create", "fact", "common", "LAHOM", "open")
    assert change.item_key == "lahom/handoff-20261111-h02m00-1" and change.evidence == [*(f"case:{i}" for i in two), "staff:mgr-1"]
    assert change.fields["payload"]["after"]["pref_label"] == "합성 상판 두께"
    assert "넘긴 상담 배우기 · 근거 상담 2곳 · 넘긴 까닭 모름" in change.reason
    assert actor_label(change.proposed_by, {}) == AGENT_LABELS[AGENT] == "AI(넘긴 상담 배우기)"
    assert change.id in [c.id for c, _row, _end in open_rows(db_session, viewer_of(admin), naive(NOW))]
    assert current_object(db_session, change.item_key) is None  # 승인 전엔 아무것도 바뀌지 않는다
    assert FACT not in [item.text for item in load_approved(db_session, "LAHOM").items]
    apply_change(db_session, change.id, actor=admin, now=naive(NOW))  # 사장님 승인 → 지식 문서 다시 씀
    db_session.commit()
    assert FACT in [item.text for item in load_approved(db_session, "LAHOM").items]


def test_a_policy_idea_is_a_knowledge_document_item_too(two, admin):
    on()
    rule = "합성 상판은 18mm 한 가지로만 만든다"
    counts = run(FakeAnthropic({"proposals": [ask(two, item_type="policy", title="합성 상판 규칙", text=rule)]}))
    (change,) = changes()
    assert (counts["filed"], change.item_type, change.layer, change.grade) == (1, "policy", "common", "B")
    apply_change(db_session, change.id, actor=admin, now=naive(NOW))
    db_session.commit()
    assert rule in [item.text for item in load_approved(db_session, "LAHOM").items]


def test_an_update_of_an_approved_fact_is_preferred_and_only_lahom_facts_are_targets(two):
    on()
    text = "합성 선반 깊이는 350mm 이고 상판 두께는 18mm 입니다"
    counts = run(FakeAnthropic({"proposals": [
        ask(two, op="update", key="lahom/shelf-depth", text=text),
        ask(two, op="update", key="lahom/hours-day", text=FACT),  # 기준 답은 주간 고침 안 몫
        ask(two, op="update", key="lahom/none", text=FACT),
    ]}))
    assert (counts["filed"], counts["blocked"]) == (1, {"target": 2})
    (change,) = changes()
    assert (change.op, change.item_key, change.fields["text"]["after"]) == ("update", "lahom/shelf-depth", text)


@pytest.mark.parametrize("bad, code", [
    ({"text": FACT + " 보증 37개월"}, "numbers"),  # 직원 답에도 지식에도 없는 숫자
    ({"why": f"연락처 {PHONE}"}, "mask"),
    ({"title": "합성\n두 줄"}, "form"),
    ({"op": "retire"}, "form"),
    ({"evidence_turn_ids": [999]}, "evidence"),
    ({"text": "합성 선반 깊이는 350mm 입니다"}, "same"),  # 반영된 지식과 같은 말
])
def test_blocked_ideas_are_counted_and_never_filed(two, bad, code):
    on()
    placer = FakePlacer()
    counts = run(FakeAnthropic({"proposals": [ask(two, **bad)]}), placer=placer)
    assert counts["filed"] == 0 and changes() == [] and placer.requests == []  # 싼 관문이 먼저 — 판정자를 부르지 않는다
    assert (counts["same"], counts["blocked"]) == (1, {}) if code == "same" else counts["blocked"] == {code: 1}


def test_a_number_must_be_in_a_cited_staff_reply_or_the_knowledge(admin):
    """사장님 11-20 '누구에게나 같은 숫자는 한 번만 말했어도' — 관문은 직원이 말하지 않은(두뇌가 지어낸) 숫자만 막는다."""
    on()
    ids = [handed("uc-1"), handed("uc-2", reply="합성 직원 답 — 상판은 두껍게 만들어요")]
    raw = [ask([ids[1]], title="합성 상판 하나"),  # 18 은 고른 직원 답에 없다
           ask([ids[0]], title="합성 상판 둘"),  # 한 손님 답에 18 — 넣는다
           ask(ids[:2], title="합성 선반", text="합성 선반은 350mm 깊이 기준으로 짜 드려요")]  # 지식에 있는 숫자
    counts = run(FakeAnthropic({"proposals": raw}))
    assert (counts["filed"], counts["blocked"]) == (2, {"numbers": 1})
    assert [c.fields["payload"]["after"]["pref_label"] for c in changes()] == ["합성 상판 둘", "합성 선반"]


def test_evidence_outside_this_run_is_blocked(admin):
    on()
    ids = [handed("uc-1"), handed("uc-2")]
    counts = run(FakeAnthropic({"proposals": [ask([ids[0], 999999]), ask([])]}))
    assert counts["blocked"] == {"evidence": 2} and changes() == []


def test_the_same_idea_is_not_filed_twice_across_nights(two):
    on()
    run(FakeAnthropic({"proposals": [ask(two)]}))
    fresh = [handed("uc-3"), handed("uc-4")]
    client = FakeAnthropic({"proposals": [ask(fresh, text=FACT + " 기본으로")]})
    counts = run(client, now=at(12, 1, 30))
    assert counts["blocked"] == {"open_proposal": 1} and len(changes()) == 1
    assert f"- 합성 상판 두께: {FACT}" in body(client)  # 이미 낸 제안을 지시문에 보인다
    db_session.get(BrainChange, changes()[0].id).status = "rejected"  # 사장님이 거절
    db_session.commit()
    later = [handed("uc-5"), handed("uc-6")]
    again = run(FakeAnthropic({"proposals": [ask(later)]}), now=at(13, 1, 30))
    assert (again["cases"], again["blocked"]) == (2, {"rejected_before": 1}) and len(changes()) == 1


def test_conflict_with_approved_knowledge_never_overwrites_and_becomes_a_card_for_the_owner(two, admin):
    """사장님 11-19 '따로 모아 보여 주기' — 지금 지식과 다른 말은 버리지도 덮어쓰지도 않고 승인 대기 ③ 엇갈림 카드로."""
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, "lahom/shelf-depth")
    said = "합성 선반 깊이는 350mm 아니고 상판 두께는 18mm 입니다"
    raw = [ask(two, op="update", key="lahom/shelf-depth", text=said),
           ask(two, op="differs", key="lahom/shelf-depth", title="합성 선반 깊이 다른 말", text="합성 선반 깊이는 400mm 로 안내했어요"),
           ask(two, op="differs", key="lahom/none", title="합성 없는 항목", text="합성 다른 말 — 대상이 없다")]
    placer = clash_placer("lahom/shelf-depth", knowledge="350mm", staff="400mm")  # 놓을 자리: 그 항목과 부딪침
    with judge_source(lambda _s, _a, _b: True), placer_source(placer):  # 고치기 안의 공용 판정자: 승인 지식과 부딪침
        counts = hl.run_handoff_learning(db_session, now=NOW, client=FakeAnthropic({"proposals": raw}))
    assert (counts["cards"], counts["applied"], counts["filed"], counts["blocked"]) == (2, 0, 0, {"target": 1})
    cards = changes()
    assert [(c.op, c.item_type, c.status) for c in cards] == [("create", "conflict", "open")] * 2  # 바로 반영하지 않는다
    assert [c.item_key for c in cards] == ["conflict/lahom-handoff-20261111-h02m00-1",
                                           "conflict/lahom-handoff-20261111-h02m00-2"]
    assert all("about:lahom/shelf-depth" in c.evidence for c in cards)
    assert cards[0].fields["text"]["after"] == f"승인된 규칙과 다름\n{said}"  # 두뇌의 고치기 안은 예전 그대로
    assert cards[1].fields["text"]["after"] == (f"{CLASH_HEAD}회사 지식 「350mm」 ↔ 직원 「400mm」\n승인된 규칙과 다름\n"
                                                "합성 선반 깊이는 400mm 로 안내했어요")  # 첫 줄에 어긋나는 두 구절
    assert cards[1].fields["payload"]["after"]["target"] == "lahom/shelf-depth"  # 한 손님 숫자도 카드로는 올린다
    assert len(placer.requests) == 1  # 없는 항목을 짚은 다른 말은 판정자를 부르지 않는다
    after = current_object(db_session, "lahom/shelf-depth")
    assert (after.version, after.text) == (before.version, before.text)  # 승인 지식 글은 그대로
    assert {c.id for c in cards} <= {c.id for c, _row, _end in open_rows(db_session, viewer_of(admin), naive(NOW))}


def test_the_learning_pass_runs_handoff_learning_and_stays_quiet_when_off(two):
    panel()
    out = learning_pass.run_learning(db_session, now=NOW, stop_check=lambda: None, client=FakeAnthropic({}))
    assert out is None or "handoff_learning" not in out  # 꺼진 길은 요약에 싣지 않는다
    on(**{CASES_FIELD: 5})
    out = learning_pass.run_learning(db_session, now=NOW, stop_check=lambda: None,
                                     client=FakeAnthropic({"proposals": []}))
    assert out["handoff_learning"]["sent"] == 2


# ── 넘김 메모 [배우기] · [흘리기](사장님 11-11) ─────────────────────────
def test_turns_taught_from_the_learn_window_are_read_even_for_human_only_reasons(channel):  # noqa: F811
    taught = handed("uc-t1", reason="order_lookup", send_state="sent")
    check = handed("uc-t2", error="check_failed", reason=None, codes=["refund_promise"], send_state="sent")
    plain = handed("uc-t3", reason="order_lookup")  # 데스크에서 직접 답한 주문 조회 — 11-20 부터 읽는다(표지는 없다)
    handed("uc-t4", reason="unsure", send_state="sent", outcome="discarded")  # [흘리기] — 늘 뺀다
    handed("uc-t5", reason="asked_if_ai", send_state="sent")  # 'AI 냐' — 배울 사실이 없다
    cases = hl.collect_cases(db_session, NOW, cap=20)
    assert [(case["turn_id"], case["taught"]) for case in cases] == [(plain, False), (check, True), (taught, True)]
    head = case_lines({**cases[2], "talk": None})[0]
    assert TAUGHT_MARK in head and "주문 조회" in head
    assert "9. 불만 · 주문 조회 · 할인 · 환불 · 사람이 정하는 금액 상담은 그 손님 사정" in INSTRUCTIONS


def test_drafted_turns_the_staff_edited_or_answered_themselves_are_read_only_when_switched_on(channel):  # noqa: F811
    why = "합성 까닭 — 상판 두께를 틀리게 썼어요"
    edited = handed("uc-e1", error=None, reason=None, state="posted", outcome="edited", send_state="sent",
                    staff=None, sent_by_user_id=7, masked_draft="합성 AI 초안 — 상판 두께는 15mm", edit_reason="wrong_fact",
                    edit_detail_masked=why)
    plain = handed("uc-e2", error=None, reason=None, state="posted", outcome="edited", send_state="sent")  # 까닭을 안 적음
    handed("uc-e3", error=None, reason=None, state="posted", outcome="as_is", send_state="sent",
           edit_detail_masked=why)  # 안 고침 — 안 읽음
    direct = handed("uc-e4", error=None, reason=None, state="posted", outcome="direct",
                    masked_draft="합성 AI 초안 — 상판 두께는 15mm")  # 초안을 안 쓰고 직접 답함(사장님 11-19 '모든 대화')
    handed("uc-e5", error=None, reason=None, state="superseded", outcome=None)  # 지난 초안 — 끝난 꼴 없음
    assert hl.collect_cases(db_session, NOW, cap=20) == []  # 패널 '초안이 나간 상담도 배우기' 끔(처음 값)
    got, mid, case = hl.collect_cases(db_session, NOW, cap=20, edits=True)
    assert (got["turn_id"], got["reason"], got["taught"], got["why"]) == (direct, "direct", False, None)
    told = case_lines({**got, "talk": None})
    assert "초안을 안 쓰고 직원이 직접 답함" in told[0] and any("AI 초안(직원이 쓰지 않음" in line for line in told)
    assert (mid["turn_id"], mid["reason"], mid["why"]) == (plain, "edited", None)
    assert (case["turn_id"], case["reason"], case["staff"], case["chip"], case["why"]) == (
        edited, "edited", "user-7", "wrong_fact", why)
    assert "11. 'AI 초안을 안 쓰고 직원이 직접 답함'" in INSTRUCTIONS and EDIT_LEARN_FIELD == "edit_learn_enabled"
    lines = case_lines({**case, "talk": None})
    assert "직원이 고쳐 보냄" in lines[0] and any("AI 초안(직원이 고치기 전" in line for line in lines)
    assert any(line.startswith(f"사례 {edited} 직원이 적은 고친 까닭(고른 칸: 틀린 사실)") for line in lines)
    assert f"| {why}" in lines and "10. 'AI 초안을 직원이 고쳐 보냄'" in INSTRUCTIONS
    assert CHIP_WORDS == dict(EDIT_REASON_LABELS)

