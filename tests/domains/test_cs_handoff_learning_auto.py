"""넘긴 상담 배우기 — 배운 것 바로 반영(사장님 2026-11-19 '매번 승인 대신 … 즉시 반영, 내가 확인하고 추후 수정 및 삭제').

패널 '배운 것 바로 반영'이 켜져 있으면 관문을 지난 안을 그 밤에 반영한다 — 사람 승인자 칸은 비고(아직 안 봄) 확신은 '근거
있음'. 켜진 ADMIN 이 없거나 칸이 꺼져 있으면 승인 대기로만. 사람 · 다른 에이전트 제안, 모두가 보지 않는 지식 · 값 규칙은 이
길로 못 넣는다. 한 밤에 여러 번 불러도 지식 번호가 겹치지 않는다. 상황 · 다른 이름 같은 온톨로지 안도 같은 밤에 넣는다.

준비물 · 도우미는 :mod:`tests.domains.test_cs_handoff_learning` 것 그대로(합성 차례 · 합성 지식 · 가짜 학습 모델 · 가짜 판정자).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain.apply import AutoLearn, apply_change
from foms.services.brain.errors import BrainPermissionError
from foms.services.brain.inbox import open_rows
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD, CASES_FIELD
from foms.services.cs_agent.handoff_learning_gates import AGENT
from foms.services.cs_agent.knowledge import load_approved
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_handoff_learning import (  # noqa: F401 — admin · two 는 fixture
    FACT, NOW, admin, ask, changes, handed, on, run, two,
)
from tests.support.brain_support import agent_judge, create
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys, naive  # noqa: F401 — keys 는 fixture


# ── 배운 것 바로 반영(사장님 11-19) ──────────────────────────────────────
def test_auto_apply_puts_learned_knowledge_in_at_once_marked_as_not_yet_seen_by_a_person(two, admin):
    on(**{AUTO_FIELD: True})
    rule = "합성 상판은 18mm 한 가지로만 만든다"
    counts = run(FakeAnthropic({"proposals": [ask(two), ask(two, item_type="policy", title="합성 상판 규칙", text=rule)]}))
    assert (counts["filed"], counts["applied"], counts["blocked"]) == (2, 2, {})
    fact, policy = changes()
    assert (fact.status, fact.decided_by, fact.decided_action) == ("applied", None, "auto_learn")
    assert (policy.status, policy.decided_by, policy.grade) == ("applied", None, "B")  # 사장님 몫 유형도 켜 둔 동안은 바로
    row = current_object(db_session, fact.item_key)
    assert (row.text, row.human_approver_id, row.confidence, row.created_by) == (FACT, None, "evidenced", f"agent:{AGENT}")
    texts = [item.text for item in load_approved(db_session, "LAHOM").items]
    assert FACT in texts and rule in texts  # 다음 초안이 바로 쓴다
    assert fact.id not in [c.id for c, _row, _end in open_rows(db_session, viewer_of(admin), naive(NOW))]


def test_auto_apply_needs_the_switch_and_an_active_admin_and_never_takes_other_proposals(two, admin):
    on()
    assert hl.auto_learn(db_session, {AUTO_FIELD: False}) is None
    assert hl.auto_learn(db_session, {AUTO_FIELD: True}).on_behalf == admin.id
    counts = run(FakeAnthropic({"proposals": [ask(two)]}))
    (change,) = changes()
    assert (counts["applied"], change.status) == (0, "open")  # 칸이 꺼져 있으면 승인 대기로만
    mine = propose_update(db_session, key="lahom/shelf-depth", base_version=1, after={"text": "합성 사람이 낸 고침"},
                          reason="합성", proposer=Proposer.user(admin.id), now=naive(NOW))
    with pytest.raises(BrainPermissionError):  # 사람 · 다른 에이전트 제안은 바로 반영 길로 못 넣는다
        apply_change(db_session, mine.id, actor=None, now=naive(NOW), auto=AutoLearn(admin.id))
    db_session.rollback()
    admin.is_active = False
    db_session.commit()
    assert hl.auto_learn(db_session, {AUTO_FIELD: True}) is None  # 켜진 ADMIN 이 없으면 승인 대기로만


def test_a_second_run_the_same_night_files_under_its_own_key(two, admin):
    """한 밤에 여러 번 부른다 — 뒤 바퀴의 지식이 앞 바퀴와 같은 번호라 빠지면 안 된다(그 사례는 이미 '읽음')."""
    on(**{AUTO_FIELD: True, CASES_FIELD: 2})
    later = [handed("uc-3", reply="합성 직원 답 — 양쪽으로 열 수 있어요"), handed("uc-4", reply="합성 직원 답 — 양쪽으로 열 수 있어요")]
    first = run(FakeAnthropic({"proposals": [ask(later, title="합성 열림 방향", text="합성 문은 양쪽으로 열 수 있어요")]}))
    second = run(FakeAnthropic({"proposals": [ask(two)]}), now=at(11, 2, 15))
    assert (first["applied"], second["applied"], second["blocked"]) == (1, 1, {})
    assert [c.item_key for c in changes()] == ["lahom/handoff-20261111-h02m00-1", "lahom/handoff-20261111-h02m15-1"]


def test_auto_apply_holds_knowledge_not_everyone_sees_and_owner_only_kinds(two, admin):
    hidden = create(db_session, admin, "lahom/sit-hidden", item_type="situation", layer="cs", brand="LAHOM",
                    name="합성 숨은 상황", visibility="admin")
    price = create(db_session, admin, "common/price-synth", item_type="price_rule", name="합성 값 규칙", text="합성 값 기준",
                   checked_at="2026-10-20", payload={"doc_id": "price-synth", "approved_by": "합성", "approved_at": "2026-10-20"})
    db_session.commit()
    agent = Proposer.agent_named(AGENT)
    for row, after in ((hidden, {"text": "합성 숨은 상황 고친 글"}), (price, {"text": "합성 값 기준 고친 글"})):
        with agent_judge():
            made = propose_update(db_session, key=row.item_key, base_version=row.version, after=after, reason="합성",
                                  proposer=agent, evidence=["case:1", "staff:mgr-1"], now=naive(NOW), known="")
        with pytest.raises(BrainPermissionError):
            apply_change(db_session, made.id, actor=None, now=naive(NOW), auto=AutoLearn(admin.id))
        db_session.rollback()


def test_ontology_ideas_from_the_same_call_are_filed_and_applied(two, admin):
    """사장님 11-19 '온톨로지 만들고 계속 업그레이드' — 상황 · 비슷한 말 · 잇기도 같은 밤에."""
    create(db_session, admin, "common/door-hinged", item_type="product_line", layer="common", brand="COMMON",
           name="합성 여닫이")
    db_session.commit()
    on(**{AUTO_FIELD: True})
    idea = {"kind": "new_situation", "key": "", "target_key": "", "name": "합성 상판 두께 문의",
            "text": "손님이 상판 두께를 물으면 규격을 안내한다", "aliases": [], "why": "합성 — 두 손님이 같은 것을 물었다",
            "evidence_turn_ids": list(two)}
    alias = {**idea, "kind": "alias", "key": "common/door-hinged", "name": "", "text": "", "aliases": ["합성 문짝"]}
    bad = {**idea, "text": idea["text"] + " 보증 37개월"}  # 지식에 없는 숫자 — 세탁 막기
    counts = run(FakeAnthropic({"proposals": [], "ontology": [idea, alias, bad, {**idea, "evidence_turn_ids": [999]}]}))
    assert (counts["proposed"], counts["filed"], counts["applied"]) == (4, 2, 2)
    assert counts["blocked"] == {"evidence": 1, "mask": 1}
    made, renamed = changes()
    assert (made.op, made.item_type, made.layer, made.status) == ("create", "situation", "cs", "applied")
    assert made.item_key.startswith("lahom/handoff-onto-20261111-") and made.evidence == [
        *(f"case:{i}" for i in two), "staff:mgr-1"]
    assert current_object(db_session, "common/door-hinged").payload["aliases"] == ["합성 문짝"]
    assert renamed.decided_action == "auto_learn"
