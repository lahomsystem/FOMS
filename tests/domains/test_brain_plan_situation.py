"""자료 계획의 새 상황 항목 · 상황 연결(설계서 2026-11-13 빈 재료 채우기 3판 D · D201).

상담 층 · 보기 범위 모두 · 일반화한 한두 문장만(길이 · 문장 수) · 이름 · 다른 이름 · 글 가림 검사 · 외톨이 상황 0 · ``links[]`` 의
``applies_to`` · ``at_step`` · ``answers`` 는 허용 짝 틀 그대로(틀이 막는 짝은 not_allowed) · 상황이 승인 대기면 다음 차례 ·
``at_step`` 은 ⑥, ``answers`` 는 ② · 같은 계획 두 번 0. 합성 값만.
"""

from __future__ import annotations

from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.apply import apply_change
from foms.services.brain.inbox_bins import BIN_RULES, card_bin, change_ends
from foms.services.brain.plan_proposals import SITUATION_CHARS, situation_text
from foms.services.brain.store import current_object
from tests.domains.test_brain_plan_labels import PHONE, opened, run, world  # noqa: F401 — fixture
from tests.support.brain_support import NOW, create

LIFT = "situation/synth-lift"


def _plan():
    return {"new_items": [
        {"type": "situation", "key": LIFT, "pref_label": "합성 승강기 없음", "aliases": ["합성 승강기 없"],
         "text": "합성 사정이면 계단으로 옮겨요. 실측 때 같이 봐요.", "why": "D201 합성"},
        {"type": "situation", "key": "situation/synth-long", "pref_label": "합성 긴 글", "text": "하나. 둘. 셋."},
        {"type": "situation", "key": "situation/synth-notext", "pref_label": "합성 글 없음"},
        {"type": "situation", "key": "situation/synth-phone", "pref_label": "합성 손님 사정", "text": f"합성 {PHONE} 사정."},
        {"type": "situation", "key": "situation/synth-alone", "pref_label": "합성 외톨이", "text": "합성 글."},
        {"type": "situation", "key": "situation/synth-held", "pref_label": "합성 보류", "text": "합성 글.",
         "waiting": "합성"},
    ], "links": [
        {"from": LIFT, "to": "product_line/lahom-1", "kind": "applies_to"},
        {"from": LIFT, "to": "process_step/measure", "kind": "at_step"},
        {"from": LIFT, "to": "product_line/lahom-1", "kind": "requires"},  # 상황은 '꼭 같이'의 시작이 아니다
        {"from": "cs/tpl-lift", "to": LIFT, "kind": "answers"},
        {"from": "situation/synth-long", "to": "product_line/lahom-1"},
        {"from": "situation/synth-notext", "to": "process_step/measure", "kind": "at_step"},
        {"from": "situation/synth-phone", "to": "product_line/lahom-1"},
        {"from": "situation/synth-held", "to": "product_line/lahom-1"},
    ]}


def test_situation_text_is_one_or_two_short_sentences():
    assert situation_text("합성 한 문장.") == "합성 한 문장."
    assert situation_text("합성 하나. 합성 둘!") == "합성 하나. 합성 둘!"
    assert situation_text("하나. 둘. 셋.") is None
    assert situation_text("합" * (SITUATION_CHARS + 1)) is None and situation_text("두 줄\n글") is None
    assert situation_text("") is None and situation_text(None) is None


def test_situations_are_filed_in_the_cs_layer_and_their_links_follow(world):
    admin, _lead = world
    create(db_session, admin, "process_step/measure", item_type="process_step", name="합성 실측",
           payload={"erp_stage": "MEASURE"})
    create(db_session, admin, "cs/tpl-lift", item_type="template", layer="cs", name="합성 승강기 기준 답",
           payload={"doc_id": "tpl-lift", "approved_by": "합성", "approved_at": "2026-10-20", "intents": ["hours"]})
    db_session.commit()
    first = run(_plan())
    assert first["filed"] == {"create": 1}
    assert first["skipped"] == {"situation_text": 2, "masked": 1, "orphan_situation": 1, "waiting": 1,
                                "end_missing": 4}  # 넣지 않은 상황의 연결은 끝이 없다
    assert first["deferred"] == {"awaiting_create": 4}  # 상황이 승인 대기 — 연결은 다음 차례
    (change,) = opened("create")
    assert (change.item_key, change.item_type, change.layer) == (LIFT, "situation", "cs")
    after = change.fields
    assert after["visibility"]["after"] == "all" and after["text"]["after"] == "합성 사정이면 계단으로 옮겨요. 실측 때 같이 봐요."
    assert PHONE not in str(after)
    apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    second = run(_plan())
    assert second["filed"] == {"link_add:answers": 1, "link_add:applies_to": 1, "link_add:at_step": 1}
    assert second["skipped"]["not_allowed"] == 1  # 틀이 막는 짝(상황 → requires)
    links = {c.link_kind: c for c in db_session.execute(select(BrainChange).where(
        BrainChange.status == "open", BrainChange.op == "link_add")).scalars()}
    assert card_bin("link_add", None, None, "at_step", **change_ends(links["at_step"])) == BIN_RULES  # D202 — ⑥
    assert card_bin("link_add", None, None, "answers", **change_ends(links["answers"])) != BIN_RULES  # ② 한 장씩
    assert current_object(db_session, LIFT).payload == {"aliases": ["합성 승강기 없"]}
    assert run(_plan())["filed_total"] == 0  # 같은 계획 두 번 0
