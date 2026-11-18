"""빈 재료 채우기 3판 E '공정 단계 · 제약 · 상황도 따라가기'(설계서 2026-11-13 3절 E · 사장님 D205 — 처음 끔).

완료 기준: 칸을 끄면(켜기 전 · 끈 뒤) 두뇌에 가는 묶음 글이 바이트까지 같다 · 공정 단계 이름표 찾기와 그리로 오는 ``at_step`` ·
꼭 같이 · 같이 못 함(방향 없음) 줄 · 상황의 ``applies_to`` · ``at_step`` · ``answers`` · 보기 범위 · 은퇴 · 다른 브랜드 빠짐 ·
상한(물건당 줄 · 쓰인 횟수 순 · 2,000자) · 키 · 금액 없음 · 제약 넘김(막지 않고 넘김 까닭 ``constraint``) · 넘김 까닭 말.
합성 값만(꾸민 이름 · 수).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import update

from db import db_session
from foms.persistence.brain.models import BrainObject
from foms.services.brain.apply import apply_change
from foms.services.brain.proposals import Proposer, propose_retire
from foms.services.brain.store import current_object
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_cases import QUOTE
from foms.services.cs_agent.brain_prompt import HANDOFF_REASONS
from foms.services.cs_agent.handoff_learning_prompt import REASON_WORDS
from foms.services.cs_agent.handoff_memo import HANDOFF_TEXTS, reason_text
from foms.services.cs_agent.onto_block import FOLLOW_HEAD, MAX_CHARS, ONTO_BLOCK_HEAD, TIE_RULE, onto_block
from foms.services.cs_agent.onto_find import MAX_RULES, OntoRule, find_items
from foms.services.cs_agent.onto_follow import HANDOFF_CONSTRAINT, clashes, constraint_handoff, follow_items
from foms.services.cs_agent.onto_settings import ONTO_FOLLOW_FIELD, ONTO_GRAPH_FIELD, onto_follow_on
from models import SystemSetting
from tests.domains.test_cs_drafting import FakeBrain, channel, customer, result, run, turn  # noqa: F401
from tests.domains.test_cs_onto_graph import DAY, DOC, _products
from tests.support.brain_support import NOW, create, link, person
from tests.support.cs_agent_fakes import keys  # noqa: F401 — fixture

ASK = "합성장 합성 손잡이 문의요"
BOTH = "합성 손잡이랑 합성 유리문 같이 할게요"


def _doc(doc_id):
    return {**DOC, "doc_id": doc_id}


def _retire(admin, key):
    row = current_object(db_session, key)
    change = propose_retire(db_session, key=key, base_version=row.version, reason="합성 은퇴",
                            proposer=Proposer.user(admin.id), now=NOW)
    apply_change(db_session, change.id, actor=admin, now=NOW)


def _base(admin, *, docs=True):
    """지금 길 재료(3판 전) — 제품 · 옵션 + 걸린 규칙 하나(초안 길 시험은 채널 준비물의 지식 문서와 맞추지 않게 규격으로)."""
    _products(admin)
    if docs:
        create(db_session, admin, "common/pol-door", item_type="policy", name="합성 문 정책", checked_at="2026-10-20",
               payload=_doc("pol-door"))
        link(db_session, admin, "applies_to", "common/pol-door", "product_line/lahom-1")
    else:
        create(db_session, admin, "common/spec-door", item_type="spec", name="합성 문 규격", payload={"value": 18, "unit": "mm"})
        link(db_session, admin, "applies_to", "common/spec-door", "product_line/lahom-1")


def _follow_world(admin, *, docs=True):
    """3판 재료 — 공정 단계 · 상황 · 꼭 같이 · 같이 못 함(보기 범위 · 은퇴 · 브랜드 막는 짝 포함). ``docs`` = 지식 문서 유형
    (정책 · 기준 답)도 만들기."""
    create(db_session, admin, "option/3-7", name="합성 유리문", item_type="option")
    create(db_session, admin, "option/3-8", name="합성 조명", item_type="option", payload={"pref_label": "합성 조명 대표"})
    create(db_session, admin, "option/3-6", name="합성 옛옵션", item_type="option")
    create(db_session, admin, "option/9-1", name="하우드 합성옵션", item_type="option", brand="HAUD")
    link(db_session, admin, "excludes", "option/3-5", "option/3-7")
    link(db_session, admin, "requires", "product_line/lahom-1", "option/3-8")
    link(db_session, admin, "excludes", "product_line/lahom-1", "option/3-9")  # 관리자 범위 끝 — 빠진다
    link(db_session, admin, "excludes", "option/3-6", "product_line/lahom-1")  # 은퇴할 끝 — 빠진다
    link(db_session, admin, "excludes", "product_line/lahom-1", "option/9-1")  # 다른 브랜드 끝 — 빠진다
    create(db_session, admin, "process_step/measure", item_type="process_step", name="합성 실측 방문",
           payload={"erp_stage": "MEASURE", "aliases": ["실측"]})
    create(db_session, admin, "cs/situation/lift", item_type="situation", layer="cs", name="합성 승강기 없음",
           text="합성 상황 글.", payload={"aliases": ["승강기가 없"]})
    link(db_session, admin, "applies_to", "cs/situation/lift", "product_line/lahom-1")
    link(db_session, admin, "at_step", "cs/situation/lift", "process_step/measure")
    if docs:
        create(db_session, admin, "common/pol-measure", item_type="policy", name="합성 실측 정책",
               payload=_doc("pol-measure"))
        create(db_session, admin, "common/pol-hidden", item_type="policy", name="합성 숨은 정책", visibility="admin",
               payload=_doc("pol-hidden"))
        link(db_session, admin, "at_step", "common/pol-measure", "process_step/measure")
        link(db_session, admin, "at_step", "common/pol-hidden", "process_step/measure")
        create(db_session, admin, "cs/tpl-lift", item_type="template", layer="cs", name="합성 승강기 기준 답",
               payload={**_doc("tpl-lift"), "intents": ["hours"]})
        link(db_session, admin, "answers", "cs/tpl-lift", "cs/situation/lift")
    _retire(admin, "option/3-6")


@pytest.fixture
def world(app):
    admin = person(db_session, "onto_follow_admin")
    _base(admin)
    _follow_world(admin)
    db_session.commit()
    return admin


def _text(hits):
    return "\n".join(onto_block(hits, follow=True))


def test_follow_reads_steps_situations_and_ties_but_no_keys_or_amounts(world):
    hits = follow_items(db_session, ["합성장 실측 언제 와요 승강기가 없어요"], brand="LAHOM", day=DAY)
    assert [h.key for h in hits] == ["product_line/lahom-1", "process_step/measure", "cs/situation/lift"]
    product, step, place = hits
    assert [(r.role, r.name) for r in product.rules] == [("", "합성 문 정책"), ("requires", "합성 조명 대표")]
    assert product.clash_keys == frozenset()  # 관리자 범위 · 은퇴 · 다른 브랜드 끝은 같이 못 함에도 안 든다
    assert sorted((r.item_type, r.doc_id, r.name) for r in step.rules) == [
        ("policy", "pol-measure", "합성 실측 정책"), ("situation", "", "합성 승강기 없음")]  # 숨은 정책 빠짐
    assert sorted((r.role, r.item_type, r.doc_id) for r in place.rules) == [
        ("", "template", "tpl-lift"), ("to", "process_step", ""), ("to", "product_line", "")]
    text = _text(hits)
    assert text.startswith(FOLLOW_HEAD) and TIE_RULE in text
    assert f"꼭 같이(옵션):\n{QUOTE}합성 조명 대표" in text
    assert f"공정 단계:\n{QUOTE}합성 실측 방문\n걸린 정책 [pol-measure]:\n{QUOTE}합성 실측 정책" in text
    assert f"상황:\n{QUOTE}합성 승강기 없음" in text and "걸린 기준 답 [tpl-lift]:" in text
    assert f"걸린 공정 단계:\n{QUOTE}합성 실측 방문" in text and f"걸린 제품:\n{QUOTE}합성장" in text
    assert not any(head in text for head in ("product_line/", "option/", "process_step/", "situation/", "common/"))
    assert "합성 상황 글" not in text and "원" not in text.replace("원문", "")  # 상황 글 · 금액 없음
    assert follow_items(db_session, [""], brand="LAHOM", day=DAY) == []


def test_excludes_has_no_direction_and_only_a_chosen_pair_clashes(world):
    hits = follow_items(db_session, [BOTH], brand="LAHOM", day=DAY)
    assert [h.key for h in hits] == ["option/3-5", "option/3-7"]
    assert [(r.role, r.name) for r in hits[0].rules] == [("excludes", "합성 유리문")]
    assert [(r.role, r.name) for r in hits[1].rules] == [("excludes", "합성 손잡이")]  # 거꾸로 걸려 있어도 같은 뜻
    assert clashes(hits) is True
    one = follow_items(db_session, ["합성 손잡이만요"], brand="LAHOM", day=DAY)
    assert clashes(one) is False and f"같이 못 함(옵션):\n{QUOTE}합성 유리문" in _text(one)
    guessed = [SimpleNamespace(**{**vars(h), "by_meaning": True}) for h in hits]
    assert clashes(guessed) is False  # 뜻으로 찾은 물건은 손님이 고른 조합이 아니다


def test_lines_are_capped_by_usage_and_the_block_by_length(world):
    admin = world
    for i in range(MAX_RULES + 2):
        create(db_session, admin, f"option/7-{i}", name=f"합성 짝 {i}", item_type="option")
        link(db_session, admin, "excludes", "option/3-7", f"option/7-{i}")
        db_session.execute(update(BrainObject).where(BrainObject.item_key == f"option/7-{i}",
                                                     BrainObject.superseded_at.is_(None)).values(usage_count=i))
    db_session.commit()
    (hit,) = follow_items(db_session, ["합성 유리문"], brand="LAHOM", day=DAY)
    assert len(hit.rules) == MAX_RULES
    assert [r.name for r in hit.rules][:2] == [f"합성 짝 {MAX_RULES + 1}", f"합성 짝 {MAX_RULES}"]  # 쓰인 횟수 많은 순
    assert len(hit.clash_keys) == MAX_RULES + 3  # 넘김 판정은 상한 없이(손잡이 + 짝 여덟)
    rules = tuple(OntoRule(f"k{i}", "", "option", "합성" * 40, role="excludes") for i in range(MAX_RULES))
    big = [SimpleNamespace(key=f"o{i}", item_type="option", name=f"합성 물건 {i}", payload={}, rules=rules)
           for i in range(8)]
    lines = onto_block(big, follow=True)
    assert sum(len(line) + 1 for line in lines) <= MAX_CHARS
    assert f"{QUOTE}합성 물건 0" in lines and lines.count("같이 못 함(옵션):") < MAX_RULES * 8  # 뒤 줄부터 잘림
    leaky = SimpleNamespace(key="x", item_type="situation", name="합성 " + "01" + "0" + "5550" + "1234", payload={},
                            rules=())
    assert onto_block([leaky], follow=True) == []  # 가림 검사에 걸린 이름은 뺀다


def _settings(**values):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, version=1, setting_value={**st.DEFAULTS, **values}))
    db_session.commit()


def _draft(channel, chat, text, brain_fn=None):
    customer(channel, chat, text=text)
    brain_fn = brain_fn or FakeBrain(result())
    run(channel, brain_fn=brain_fn)
    (request,) = brain_fn.requests
    return request


def test_off_keeps_the_block_byte_for_byte_before_and_after(channel):
    admin = person(db_session, "onto_follow_off_admin")
    _base(admin, docs=False)
    db_session.commit()
    _settings(**{ONTO_GRAPH_FIELD: True})
    before = _draft(channel, "uc-1", ASK).onto_lines  # 3판 재료 · 칸 둘 다 없음
    assert before[0] == ONTO_BLOCK_HEAD and f"{QUOTE}합성장" in before
    _follow_world(admin, docs=False)
    db_session.commit()
    assert _draft(channel, "uc-2", ASK).onto_lines == before  # 재료가 생겨도 칸이 없으면(처음 값) 그대로
    _settings(**{ONTO_GRAPH_FIELD: True, ONTO_FOLLOW_FIELD: True})
    on = _draft(channel, "uc-3", ASK).onto_lines
    assert on != before and "꼭 같이(옵션):" in on
    _settings(**{ONTO_GRAPH_FIELD: True, ONTO_FOLLOW_FIELD: False})
    after = _draft(channel, "uc-4", ASK).onto_lines
    assert "\n".join(after).encode("utf-8") == "\n".join(before).encode("utf-8")  # 끈 뒤 — 바이트까지 같다
    assert list(after) == onto_block(find_items(db_session, [ASK], brand="LAHOM", day=DAY))
    _settings(**{ONTO_FOLLOW_FIELD: True})  # '물건 찾아 따라가기'가 꺼져 있으면 이 칸도 보지 않는다
    assert _draft(channel, "uc-5", ASK).onto_lines == ()
    assert HANDOFF_CONSTRAINT not in HANDOFF_REASONS  # 두뇌 출력 스키마(enum)는 칸과 무관하게 그대로


@pytest.mark.parametrize("follow, text, reason", [
    (True, BOTH, HANDOFF_CONSTRAINT), (True, "합성 손잡이만 할게요", None), (False, BOTH, None)])
def test_a_chosen_excluded_pair_hands_off_without_saying_no(channel, follow, text, reason):
    admin = person(db_session, "onto_follow_draft_admin")
    _base(admin, docs=False)
    _follow_world(admin, docs=False)
    db_session.commit()
    _settings(**{ONTO_GRAPH_FIELD: True, ONTO_FOLLOW_FIELD: follow})
    _draft(channel, "uc-1", text)
    row = turn()
    if reason is None:
        assert (row.state, row.handoff_reason) == ("stored", "none")
    else:
        assert (row.state, row.error_code, row.handoff_reason, row.masked_draft) == ("skipped", "handoff", reason, None)


def test_constraint_handoff_keeps_refusals_and_clear_reasons():
    assert constraint_handoff(result()).handoff_reason == HANDOFF_CONSTRAINT
    assert constraint_handoff(result()).handoff is True
    assert constraint_handoff(result(handoff=True, handoff_reason="unsure")).handoff_reason == HANDOFF_CONSTRAINT
    assert constraint_handoff(result(handoff=True, handoff_reason="complaint")).handoff_reason == "complaint"
    refused = result(refused=True, handoff_reason="refused")
    assert constraint_handoff(refused) is refused


def test_the_constraint_reason_has_plain_words_everywhere():
    assert reason_text("handoff", handoff_reason=HANDOFF_CONSTRAINT) == HANDOFF_TEXTS[HANDOFF_CONSTRAINT] == (
        "제작 조건을 확인해야 해요")
    assert REASON_WORDS[HANDOFF_CONSTRAINT] == "제작 조건 확인"
    assert onto_follow_on({ONTO_FOLLOW_FIELD: True}) and not onto_follow_on({ONTO_FOLLOW_FIELD: "yes"})
    assert st.DEFAULTS[ONTO_FOLLOW_FIELD] is False and st.FIELD_BY_NAME[ONTO_FOLLOW_FIELD].group == st.FIELD_BY_NAME[
        ONTO_GRAPH_FIELD].group
