"""승인 대기 ③(엇갈림 · 물어볼 것 만들기)은 ADMIN 만 보고 정한다(점검 F26 · 사장님 D167 '① 만 상담팀장, 나머지는 사장님' · D152).

판정은 :func:`foms.services.brain.access.approval_problem` 한 곳 — 반영 · 거절 · ③ 답(거절 까닭 셋) · 한꺼번에 승인이 모두 이 길이고,
승인 대기 목록 · 탭 수(:func:`.inbox.inbox_counts`)는 같은 규칙을 질의 조건으로 쓴다.

같은 모집단 음성 대조군: 층 승인자가 결정하던 상담 층 ③ 제안(전에는 상담팀장에게 보였다) 옆에 ② 상담 층 고침 · ① 이름표만 고침을
두고 ② · ① 은 그대로 보이고 되는지, ADMIN 에게는 ③ 이 보이고 되는지 같이 본다. 합성 항목 · 합성 계정만.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.access import approval_problem
from foms.services.brain.constants import AGENT_WORK_TYPES, ANSWER_CODES, LINK_OPS, OBJECT_OPS, TYPES
from foms.services.brain.decide import apply_decision, bulk_apply, reject_decision
from foms.services.brain.errors import BrainPermissionError
from foms.services.brain.inbox import inbox, inbox_counts
from foms.services.brain.inbox_bins import BIN_DECIDE, card_bin, owner_decides
from foms.services.brain.proposals import Proposer, propose_create, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from tests.support.brain_review_support import review_world
from tests.support.brain_support import NOW, REASON, agent_judge, values

LATER = NOW + datetime.timedelta(minutes=5)


@pytest.fixture(autouse=True)
def _agent_judge():
    with agent_judge():
        yield


def ask(admin, key, *, layer, item_type="conflict", about="cs/lesson/photo", visibility="all"):
    """③ 제안 하나(사람 제안 — AI 주 상한 밖) — 다루는 항목 근거를 단다."""
    return propose_create(db_session, key=key, brand="COMMON", layer=layer, item_type=item_type,
                          values=values("두 곳에 다르게 적혀 있어요", text="바깥 글과 회사 지식이 달라요", visibility=visibility),
                          reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="",
                          evidence=["plan:synth#perm", f"about:{about}"])


def label_change(admin, key, label):
    """① 이름표만 고침."""
    row = current_object(db_session, key)
    return propose_update(db_session, key=key, base_version=row.version,
                          after={"payload": {**(row.payload or {}), "pref_label": label}},
                          reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")


@pytest.fixture
def world(app):
    made = review_world(db_session)
    admin = made["people"]["admin"]
    made["cs_q"] = ask(admin, "conflict/perm-cs", layer="cs")
    made["dr_q"] = ask(admin, "question/perm-dr", layer="drawing", item_type="question", about="drawing/rule/final",
                       visibility="team:DRAWING")
    made["names"] = label_change(admin, "common/door", "여닫이 문")
    db_session.commit()
    return made


def _ids(viewer):
    return {c["main"]["id"] for c in inbox(db_session, viewer, now=LATER)["cards"]}


def test_owner_decides_is_exactly_the_decide_bin():
    for op in (*OBJECT_OPS, *LINK_OPS):
        for item_type in TYPES:
            assert owner_decides(op, item_type) is (card_bin(op, item_type, None, None) == BIN_DECIDE), (op, item_type)
    assert {t for t in TYPES if owner_decides("create", t)} == set(AGENT_WORK_TYPES)


def test_approval_problem_keeps_decide_bin_for_admin_only(world):
    who = {name: viewer_of(user) for name, user in world["people"].items()}
    for name in ("cs_mgr", "dr_mgr", "pr_mgr"):
        for layer in ("cs", "drawing", "production", "common"):
            for item_type in AGENT_WORK_TYPES:
                assert approval_problem(who[name], op="create", layer=layer, types=[item_type]) is not None
                assert approval_problem(who[name], op="create", layer=layer, types=[item_type],
                                        label_only=True) is not None  # 이름표 권한으로도 못 연다
    assert approval_problem(who["admin"], op="create", layer="cs", types=["conflict"]) is None  # 대조군
    # ③ 은 '만들기'만 — 이미 반영된 엇갈림 항목 고침은 그대로 ② 층 승인자 규칙(대조군)
    assert approval_problem(who["cs_mgr"], op="update", layer="cs", types=["conflict"]) is None
    assert approval_problem(who["cs_mgr"], op="update", layer="cs", types=["lesson"]) is None  # ② 그대로
    assert approval_problem(who["cs_mgr"], op="update", layer="common", types=["price_rule"],
                            label_only=True) is None  # ① 상담팀장 그대로(D167)
    assert approval_problem(who["cs_mgr"], op="create", layer="cs", types=iter(["conflict"])) is not None  # 한 번 도는 값


def test_layer_approvers_do_not_see_or_count_decide_cards_but_admin_does(world):
    who = {name: viewer_of(user) for name, user in world["people"].items()}
    cs_q, dr_q, names, cs_edit = world["cs_q"].id, world["dr_q"].id, world["names"].id, world["changes"]["cs"]
    cs = _ids(who["cs_mgr"])
    assert cs_q not in cs and {names, cs_edit} <= cs  # ① · ② 는 그대로(대조군)
    assert dr_q not in _ids(who["dr_mgr"]) and world["changes"]["drawing"] in _ids(who["dr_mgr"])
    for name in ("cs_mgr", "dr_mgr", "pr_mgr"):
        counts = inbox_counts(db_session, who[name], LATER)
        assert counts["cards"] == len(_ids(who[name])), name  # 탭 수 = 보이는 카드 수
    admin = inbox(db_session, who["admin"], now=LATER)
    bins = {c["main"]["id"]: c["bin"] for c in admin["cards"]}
    assert bins[cs_q] == bins[dr_q] == "decide"  # ADMIN 은 본다(같은 모집단 양성 대조)
    assert inbox_counts(db_session, who["admin"], LATER)["cards"] == len(admin["cards"])


@pytest.mark.parametrize("name", ["cs_mgr", "dr_mgr"])
def test_layer_approvers_cannot_apply_reject_answer_or_bulk_apply_decide_cards(world, name):
    actor = world["people"][name]
    change = world["cs_q"] if name == "cs_mgr" else world["dr_q"]
    with pytest.raises(BrainPermissionError):
        apply_decision(db_session, change.id, actor=actor, base_version=change.base_version, now=LATER)
    db_session.rollback()
    for code in ("other", *ANSWER_CODES):  # 보통 거절 · ③ 답 셋(회사 지식 · 바깥 글 · 둘 다)
        with pytest.raises(BrainPermissionError):
            reject_decision(db_session, change.id, actor=actor, code=code, now=LATER)
        db_session.rollback()
    out = bulk_apply(db_session, [change.id], actor=actor, now=LATER)  # 등급 A 라도 하나씩 판정에서 막힌다
    db_session.rollback()
    assert out["applied"] == [] and [f["id"] for f in out["failed"]] == [change.id]
    db_session.expire_all()
    assert db_session.get(BrainChange, change.id).status == "open"
    assert current_object(db_session, change.item_key) is None  # 정본에 아무것도 안 생겼다


def test_admin_still_answers_and_applies_and_cs_manager_still_approves_names(world):
    admin, cs_mgr = world["people"]["admin"], world["people"]["cs_mgr"]
    reject_decision(db_session, world["cs_q"].id, actor=admin, code="knowledge_right", now=LATER)
    apply_decision(db_session, world["dr_q"].id, actor=admin, base_version=world["dr_q"].base_version, now=LATER)
    apply_decision(db_session, world["names"].id, actor=cs_mgr, base_version=world["names"].base_version, now=LATER)
    db_session.commit()
    closed = db_session.get(BrainChange, world["cs_q"].id)
    assert (closed.status, closed.reject_code) == ("rejected", "knowledge_right")
    assert current_object(db_session, "question/perm-dr") is not None
    assert current_object(db_session, "common/door").payload["pref_label"] == "여닫이 문"  # D167 그대로
