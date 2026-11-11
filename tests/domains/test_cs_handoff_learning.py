"""넘긴 상담 배우기 → 회사 지식 제안(사장님 11-11) — 처음 끔 · 하루 한 번 · 늘 사람 몫인 까닭 뺌 · 직원 답이 있는 사례만 ·
앞뒤 대화 창 · 가림에 걸린 사례만 뺌 · 숫자 · 근거 · 겹침 · 부딪침 관문 · 읽은 차례 다시 안 읽음 · 제안 길로만(승인 대기).

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
from foms.services.cs_agent.handoff_learn_settings import CASES_FIELD, HANDOFF_LEARN_FIELD
from foms.services.cs_agent.handoff_learning_gates import AGENT
from foms.services.cs_agent.handoff_learning_prompt import ANCHOR_MARK, INSTRUCTIONS, TALK_HEAD
from foms.services.cs_agent.knowledge import load_approved
from models import CsAgentTurn
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_photo_read import PHONE
from tests.domains.test_cs_weekly_fix import into_brain, panel
from tests.support.brain_support import agent_judge, person
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    FakeAnthropic, FakeClock, api_message, at, keys, make_reader, naive,
)
from tests.support.cs_talk_support import START, PagedChannel

NOW = at(11, 2)  # 수요일 KST 02:00
FACT = "합성 상판 두께는 18mm 로 만들어 드립니다"
REPLY = "합성 직원 답 — 상판 두께는 18mm 입니다"
_SEQ = itertools.count(1)


def handed(chat: str, *, reason="unsure", error="handoff", reply=REPLY, outcome="direct", state="skipped",
           held_out=False, codes=None, brand="LAHOM", when=None, anchor=None, context=None, staff="mgr-1") -> int:
    """넘긴 차례 하나(가린 질문 · 직원이 직접 한 가린 답)."""
    row = CsAgentTurn(brand=brand, chat_id=chat, last_user_message_id=anchor or f"m-{chat}-{next(_SEQ)}", state=state,
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


def run(client, now=NOW, reader=None):
    with agent_judge():
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


# ── 끄고 켜기 · 하루 한 번 ───────────────────────────────────────────────
def test_off_by_default_outside_the_window_and_once_a_day(two):
    client = FakeAnthropic({"proposals": []})
    panel()
    assert hl.run_handoff_learning(db_session, now=NOW, client=client) == {"off": "switch_off"}
    on()
    assert hl.run_handoff_learning(db_session, now=at(11, 4), client=client) == {"off": "not_window"}
    first = run(client)
    assert (first["cases"], first["sent"], first["filed"], first["halted"]) == (2, 2, 0, None)
    assert len(client.params) == 1
    assert run(client, now=at(11, 2, 45)) == {"off": "already_today"} and len(client.params) == 1
    assert hl.claim_day(db_session, "2026-11-12") and not hl.claim_day(db_session, "2026-11-12")  # 두 컨테이너도 한 번
    on(learning_cap_usd_panel=None)
    assert run(client, now=at(13, 1)) == {"off": "no_learning_cap"}


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
def test_only_learnable_handoffs_with_a_staff_reply_are_read(admin):
    on()
    wanted = [handed("uc-1", reason=r) for r in ("unsure", "photo", "schedule", "other")]
    wanted.append(handed("uc-2", error="check_failed", reason="none", codes=["date_promise"]))
    for reason in ("complaint", "order_lookup", "discount_refund", "human_only_amount", "asked_if_ai"):
        handed("uc-3", reason=reason)  # 늘 사람 몫 · 배울 까닭 밖
    handed("uc-3", error="check_failed", reason="complaint")
    handed("uc-3", error="check_failed", reason="none", codes=["refund_promise"])
    handed("uc-3", error="check_failed", reason="quote_zero")  # 견적 금액은 계산기 몫
    handed("uc-3", reply=None)  # 직원 답이 없는 사례
    handed("uc-3", held_out=True)
    handed("uc-3", outcome="copied")
    handed("uc-3", state="posted")
    handed("uc-3", brand="HAUD")
    handed("uc-3", when=at(3, 1))  # 7일 밖
    cases = hl.collect_cases(db_session, NOW, cap=20)
    assert [case["turn_id"] for case in cases] == wanted
    assert [case["reason"] for case in cases] == ["unsure", "photo", "schedule", "other", "check_failed"]
    assert [c["turn_id"] for c in hl.collect_cases(db_session, NOW, cap=2)] == wanted[:2]  # 오래된 것부터 상한만


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
    assert change.item_key == "lahom/handoff-20261111-1" and change.evidence == [*(f"case:{i}" for i in two), "staff:mgr-1"]
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
    counts = run(FakeAnthropic({"proposals": [ask(two, **bad)]}))
    assert counts["filed"] == 0 and counts["blocked"] == {code: 1} and changes() == []


def test_a_number_said_to_one_customer_only_is_not_learned(admin):
    on()
    ids = [handed("uc-1"), handed("uc-2", reply="합성 직원 답 — 상판은 두껍게 만들어요"), handed("uc-3")]
    raw = [ask(ids[:2], title="합성 상판 하나"),  # 18 은 첫 손님 답에만
           ask([ids[0], ids[2]], title="합성 상판 둘"),  # 두 손님 답 모두에 18
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


def test_conflict_with_approved_knowledge_is_never_filed(two):
    on()
    raw = [ask(two, op="update", key="lahom/shelf-depth", text="합성 선반 깊이는 350mm 아니고 상판 두께는 18mm 입니다")]
    with judge_source(lambda _s, _a, _b: True):  # 판정자: 승인 지식과 부딪침
        counts = hl.run_handoff_learning(db_session, now=NOW, client=FakeAnthropic({"proposals": raw}))
    assert counts["blocked"] == {"brain_conflict": 1} and changes() == []


def test_the_learning_pass_runs_handoff_learning_and_stays_quiet_when_off(two):
    panel()
    out = learning_pass.run_learning(db_session, now=NOW, stop_check=lambda: None, client=FakeAnthropic({}))
    assert out is None or "handoff_learning" not in out  # 꺼진 길은 요약에 싣지 않는다
    on(**{CASES_FIELD: 5})
    out = learning_pass.run_learning(db_session, now=NOW, stop_check=lambda: None,
                                     client=FakeAnthropic({"proposals": []}))
    assert out["handoff_learning"]["sent"] == 2
