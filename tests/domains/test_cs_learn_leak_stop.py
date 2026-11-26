"""넘긴 상담 배우기 새는 곳 막기 — 판정 규칙 · '더함' 대상(설계서 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 4.1).

- 다. '○ 당' 값 × 수량으로 맞는 금액은 부딪침이 아니다(그 고객 한 사람의 수량이면 규칙 아님) — 두 판정자(다른 말 · 놓을 자리)가
  같은 글을 쓰고, 그 글이 모델 요청에 실린다. 모델은 부르지 않는다(가짜 두뇌).
- 라. '더함' 대상이 유형만 고칠 수 없는 항목(가격 규칙 · 용어)이면 새 사실을 만들지 않고 그 항목 고침 제안(열린 채 — 사람 승인)을
  올린다. 바로 반영이 켜져 있어도 반영하지 않는다(음성 대조군 — 막는 줄을 빼면 반영된다). 같은 대상에 열린 제안이 있으면 또 올리지
  않고, 가림 · 숫자 관문에 걸리면 새 지식으로도 넣지 않는다. 공통 항목처럼 다른 까닭으로 못 고치는 대상은 예전처럼 새 지식.

합성 글만(손님 글 · 직원 이름 · 금액 · 회사 지식 글 없음 · 네트워크 0).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain.ai_gates import judge_source
from foms.services.brain.apply import AutoLearn, apply_change
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning_judge as judge
from foms.services.cs_agent import handoff_learning_place as place
from foms.services.cs_agent import handoff_learning_propose as propose
from foms.services.cs_agent import handoff_learning_route as route
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from foms.services.cs_agent.handoff_learning_place import placer_source
from foms.services.cs_agent.settings import read_settings
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_handoff_learning import NOW, admin, changes, handed, on  # noqa: F401 — admin 은 fixture
from tests.domains.test_cs_learn_everything import TARGET
from tests.support.brain_support import create, no_conflict
from tests.support.cs_agent_fakes import FakeAnthropic, FakePlacer, keys, naive  # noqa: F401 — keys 는 fixture

TITLE, SAID = "합성 깊이 줄임 셈", "합성 깊이 줄임은 그 고객 통 수만큼 셈해 안내한다"
REPLY = "합성 직원 답 — 깊이 줄임은 통 수만큼 셈해요"
ADDED = "합성 깊이 줄임은 통마다 따로 셈한다"


# ── 다. '○ 당' 값의 배수는 부딪침이 아니다 ───────────────────────────────
def _line(system: str, head: str) -> str:
    return next(line for line in system.split("\n") if line.startswith(head))


def test_the_per_unit_rule_reads_the_same_in_both_judges():
    rule = f"단, {judge.PER_UNIT_AMOUNT}은 부딪침이 아니다(그 고객 한 사람의 수량에 따른 금액이면 규칙이 아닌 말이다)"
    assert judge.PER_UNIT_AMOUNT == "지식의 '○ 당' 값(통 당 · 개 당 · 30cm 당 등)에 수량을 곱해 맞아떨어지는 금액"
    assert judge.CONTRADICTS_RULES.endswith(rule)
    assert f"contradicts: {judge.CONTRADICTS_RULES}." in judge.SYSTEM  # 다른 말 판정자
    assert judge.CONTRADICTS_RULES in _line(place.SYSTEM, "contradicts:")  # 놓을 자리 판정자 — 같은 글
    assert judge.PER_UNIT_AMOUNT in _line(place.SYSTEM, "not_rule:") and place.NOT_RULE in place.VERDICTS  # 규칙 아님 쪽


def test_the_rule_rides_in_both_model_requests(admin):
    on(**{AUTO_FIELD: True})
    cfg = read_settings(db_session, log=False)
    answer = {"verdict": "not_rule", "target": "", "added": "", "clash": {"knowledge": "", "staff": ""}, "why": "합성"}
    placing = FakeAnthropic(answer)
    got = place.place(db_session, key=TARGET, title=TITLE, text=SAID, cfg=cfg, now=NOW, client=placing)
    assert got.verdict == place.NOT_RULE
    assert placing.params[0]["system"][0]["text"].count(judge.PER_UNIT_AMOUNT) == 2  # 부딪침 줄 · 규칙 아님 줄
    differing = FakeAnthropic({"verdict": "adds", "why": "합성"})
    assert judge.differs_verdict(db_session, target_key=TARGET, title=TITLE, text=SAID, cfg=cfg, now=NOW,
                                 client=differing) == judge.ADDS
    assert judge.PER_UNIT_AMOUNT in differing.params[0]["system"][0]["text"]


# ── 라. '더함' 대상이 고칠 수 없는 유형 ──────────────────────────────────
PRICE, TERM, SHARED = "lahom/synth-cut-rule", "lahom/synth-tong", "common/synth-cut-shared"
PRICE_PAYLOAD = {"approved_by": "합성", "approved_at": "2026-10-20"}


@pytest.fixture
def targets(admin):
    """라홈 가격 규칙 · 라홈 용어(유형만 못 고친다) · 공통 가격 규칙(브랜드 까닭 — 예전 길)."""
    rule = dict(item_type="price_rule", checked_at="2026-10-20")
    create(db_session, admin, PRICE, brand="LAHOM", name="합성 깊이 줄임 규칙", text="합성 깊이 줄임은 따로 셈한다",
           payload={"doc_id": "synth-cut-rule", **PRICE_PAYLOAD}, **rule)
    create(db_session, admin, TERM, item_type="term", brand="LAHOM", name="합성 통", text="합성 통은 문짝 묶음 하나를 센다")
    create(db_session, admin, SHARED, name="합성 공통 깊이 줄임 규칙", text="합성 공통 깊이 줄임은 따로 셈한다",
           payload={"doc_id": "synth-cut-shared", **PRICE_PAYLOAD}, **rule)
    db_session.commit()
    return admin


def _night(key, added=ADDED, *, auto=None, chats=("uc-5", "uc-6")):
    """두 상담에서 들은 다른 말(두뇌가 ``key`` 를 짚음 · 바로 고칠 글 없음) → 놓을 자리 판정 '더함'(그 항목)."""
    turns = [handed(chat, reply=REPLY) for chat in chats]
    cases = [{"turn_id": t, "chat_id": c, "reply": REPLY, "reason": "unsure", "staff": "mgr-1"} for t, c in zip(turns, chats)]
    raw = [{"op": "differs", "item_type": "fact", "key": key, "title": TITLE, "text": SAID, "fixed_text": "", "repeats": [],
            "why": "합성 — 두 손님에게 같은 셈을 안내했다", "evidence_turn_ids": turns}]
    with judge_source(no_conflict), placer_source(FakePlacer({"verdict": "adds", "target": key, "added": added})):
        return route.file_proposals(db_session, raw, cases, now=NOW, known="", approved=[], auto=auto, cfg=None)


@pytest.mark.parametrize("key, item_type", [(PRICE, "price_rule"), (TERM, "term")])
def test_adds_to_a_kind_learning_cannot_edit_opens_a_proposal_on_that_item_instead_of_a_new_fact(targets, key, item_type):
    before = current_object(db_session, key)
    counts = _night(key, auto=AutoLearn(targets.id))  # 바로 반영이 켜져 있어도
    assert counts == {"filed": 1, propose.PROPOSED: 1}  # 새 지식 · 바로 반영 없음
    (change,) = changes()
    assert (change.op, change.item_key, change.item_type, change.status) == ("update", key, item_type, "open")
    assert change.fields["text"] == {"before": before.text, "after": f"{before.text} {ADDED}"}
    assert "지금 지식에 더할 말 · 사람 승인" in change.reason and change.gates["conflict"] == "pass"
    assert current_object(db_session, key).version == before.version  # 사람이 보기 전에는 그대로
    apply_change(db_session, change.id, actor=targets, now=naive(NOW))  # 사람 승인 길
    assert current_object(db_session, key).text == f"{before.text} {ADDED}"


def test_the_auto_hold_is_what_keeps_a_term_proposal_open(targets, monkeypatch):
    """음성 대조군 — 막는 줄(사실 · 정책 밖 유형은 사람 승인)을 빼면 용어 고침은 그 자리에서 반영된다(가격 규칙은 반영 동작이 따로 막는다)."""
    monkeypatch.setattr(route, "human_only", lambda _change: False)
    counts = _night(TERM, auto=AutoLearn(targets.id))
    assert (counts[propose.PROPOSED], counts["applied"]) == (1, 1) and changes()[0].status == "applied"


def test_an_open_proposal_on_the_same_item_is_not_raised_again(targets):
    row = current_object(db_session, PRICE)
    propose_update(db_session, key=PRICE, base_version=row.version, after={"text": f"{row.text} 합성 사람이 고치는 중"},
                   reason="합성", proposer=Proposer.user(targets.id), now=naive(NOW))
    db_session.commit()
    assert _night(PRICE) == {"filed": 0, "open_proposal": 1} and changes() == []


@pytest.mark.parametrize("added, code", [
    ("합성 깊이 줄임은 통마다 37 을 더한다", "numbers"),  # 직원 답 · 지식에 없는 숫자
    (f"합성 깊이 줄임은 {chr(0x901A)} 마다 셈한다", "mask"),  # 한자 한 글자(글자 그대로 적지 않으려고 번호로 만든다)
], ids=["numbers", "mask"])
def test_a_text_gate_failure_files_nothing_not_even_a_new_fact(targets, added, code):
    assert _night(PRICE, added) == {"filed": 0, code: 1} and changes() == []


def test_a_target_blocked_for_another_reason_still_becomes_new_knowledge(targets):
    """공통 항목(하우드 문서에도 들어간다)은 유형이 아니라 브랜드 까닭 — 예전 그대로 새 지식."""
    counts = _night(SHARED)
    assert (counts["filed"], counts.get("placed_new"), counts.get(propose.PROPOSED)) == (1, 1, None)
    (change,) = changes()
    assert change.op == "create" and current_object(db_session, SHARED).version == 1


def test_the_proposal_kinds_and_skipped_gates():
    """고침 제안은 공통 바탕 유형만 — 기준 답(주간 고침 안 몫 · :mod:`tests.domains.test_cs_handoff_learning`) · 상황(온톨로지 안
    길)은 예전 그대로. 막지 않는 관문은 넣기 길과 같다."""
    assert propose.PROPOSE_TYPES == {"brand", "spec", "build_rule", "price_rule", "owner_decision", "term"}
    assert propose.SKIP == route.SKIP
