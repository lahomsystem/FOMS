"""제안함 · 결정 · 다시 확인 · 되돌리기(설계서 2026-11-02-haud-master-brain 6절 · 7.5 화면 4 · 5 · 6 · D101 · D103 · ⑤-3).

- 권한(D101): 상담 팀장은 가격 규칙을 못 넣고, 도면 팀장은 상담 층을 못 넣고, ADMIN 은 모두(대조군).
- 보기 범위: 같은 모집단(상담 층 배운 점)의 숨긴 제안은 상담 팀장 제안함 · 수에 0, ADMIN 에게는 보임(음성 대조군).
- 기준 판 충돌 · 고쳐 넣기 · 거절 까닭 남김 + 같은 제안 막기 · 항목당 카드 하나 · AI 주 상한 20 · 4주 닫힘 · 등급 A 만 한꺼번에 ·
  등급 B 핵심 값 확인 · '아직 맞음' 날 밀기 · 판(층) 되돌리기 · 항목 하나 되돌리기 = 새 제안 · 결정 숫자.
합성 항목 · 합성 계정만.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainRelease
from foms.services.brain import constants as c
from foms.services.brain.decide import apply_decision, bulk_apply, expire_ai_proposals, reject_decision
from foms.services.brain.errors import (
    BrainConfirmError, BrainConflictError, BrainOpenProposalError, BrainPermissionError, BrainRejectedError,
    BrainRollbackBlockedError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.inbox import inbox, inbox_counts
from foms.services.brain.metrics import decision_metrics
from foms.services.brain.proposals import Proposer, propose_rollback, propose_update
from foms.services.brain.recheck import confirm_still_true, recheck_counts, recheck_list
from foms.services.brain.release_view import release_page
from foms.services.brain.rollback import rollback_release
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_link, current_object
from models import SecurityLog
from tests.support.brain_review_support import review_world
from tests.support.brain_screen_support import TODAY
from tests.support.brain_support import NOW, REASON, TWO_SOURCES, agent_judge, create, link


@pytest.fixture(autouse=True)
def _agent_judge():
    """에이전트 제안의 관문 ②(부딪침 — 7.7 · D105)를 합성 판정자로 넘긴다(모델을 부르지 않는다)."""
    with agent_judge():
        yield


LATER = NOW + datetime.timedelta(minutes=5)


@pytest.fixture
def world(app):
    return review_world(db_session)


def _cards(person, now=LATER):
    return inbox(db_session, viewer_of(person), now=now)["cards"]


def _ids(cards):
    return sorted(card["main"]["id"] for card in cards)


def _confirm(change_id):
    card = next(cd for cd in _cards(_admin()) if cd["main"]["id"] == change_id)
    return card["main"]["confirm"]


def _admin():
    from models import User
    return db_session.query(User).filter_by(username="bs_admin").one()


# ── 범위 · 권한 ──────────────────────────────────────────────────────────
def test_inbox_shows_only_what_each_person_may_decide_and_see(world):
    who, ch = world["people"], world["changes"]
    assert _ids(_cards(who["admin"])) == sorted(ch.values())  # 대조군: ADMIN 은 넷 모두
    assert _ids(_cards(who["cs_mgr"])) == [ch["cs"]]  # 가격 규칙(사장님 몫) · 도면팀만 · 다른 층 빠짐
    assert _ids(_cards(who["dr_mgr"])) == [ch["drawing"]]  # 도면팀 범위 상담 항목도 층이 달라 빠짐
    assert _cards(who["pr_mgr"]) == []
    assert inbox_counts(db_session, viewer_of(who["cs_mgr"]), LATER) == {"open": 1, "cards": 1, "ai_waiting": 0}
    assert inbox_counts(db_session, viewer_of(who["admin"]), LATER)["open"] == 4
    # 같은 모집단(상담 층 배운 점)에서 숨긴 것만 빠진다 — 보기 범위가 거른 것이지 층이 거른 것이 아니다
    assert {cd["key"] for cd in _cards(who["admin"]) if cd["layer"] == "cs"} == {"cs/lesson/photo", "cs/lesson/hidden"}
    with pytest.raises(BrainPermissionError):
        apply_decision(db_session, ch["hidden"], actor=who["cs_mgr"], base_version=1, now=LATER)


def test_cs_manager_cannot_approve_a_price_rule_but_admin_can(world):
    who, ch = world["people"], world["changes"]
    with pytest.raises(BrainPermissionError):
        apply_decision(db_session, ch["price"], actor=who["cs_mgr"], base_version=1, now=LATER)
    with pytest.raises(BrainPermissionError):
        reject_decision(db_session, ch["price"], actor=who["cs_mgr"], code="wrong_number", now=LATER)
    confirm = _confirm(ch["price"])
    assert confirm == {"field": "text", "value": "지역별 운임 새 기준"}
    result = apply_decision(db_session, ch["price"], actor=who["admin"], base_version=1, confirm=confirm, now=LATER)
    assert result.version == 2 and current_object(db_session, "common/shipping").text == "지역별 운임 새 기준"


def test_drawing_manager_cannot_approve_the_cs_layer(world):
    who, ch = world["people"], world["changes"]
    with pytest.raises(BrainPermissionError):
        apply_decision(db_session, ch["cs"], actor=who["dr_mgr"], base_version=1, now=LATER)
    with pytest.raises(BrainPermissionError):
        apply_decision(db_session, ch["drawing"], actor=who["cs_mgr"], base_version=1, now=LATER)
    assert apply_decision(db_session, ch["cs"], actor=who["cs_mgr"], base_version=1, now=LATER).version == 2  # 대조군
    assert apply_decision(db_session, ch["drawing"], actor=who["dr_mgr"], base_version=1, now=LATER).version == 2
    for name in ("sales_mgr", "cs_staff", "viewer", "off_admin"):
        assert _cards(who[name]) == []


# ── 기준 판 · 고쳐 넣기 · 등급 B ─────────────────────────────────────────
def test_base_version_conflict_after_the_item_changed(world):
    who, ch = world["people"], world["changes"]
    second = propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"name": "사진 먼저 받기 둘"},
                            reason=REASON, proposer=Proposer.user(who["cs_mgr"].id), now=NOW, known="")
    with pytest.raises(BrainConflictError):  # 화면이 보낸 기준 판이 제안과 다르다
        apply_decision(db_session, ch["cs"], actor=who["cs_mgr"], base_version=7, now=LATER)
    apply_decision(db_session, ch["cs"], actor=who["cs_mgr"], base_version=1, now=LATER)
    card = next(cd for cd in _cards(who["cs_mgr"]) if cd["key"] == "cs/lesson/photo")
    assert card["main"]["id"] == second.id
    assert card["main"]["base"] == {"changed": True, "current": 2, "flagged_at": "2026-11-02 10:05"}  # 넣는 순간 표시
    assert db_session.get(BrainChange, second.id).base_changed_at == LATER
    with pytest.raises(BrainConflictError) as caught:
        apply_decision(db_session, second.id, actor=who["cs_mgr"], base_version=1, now=LATER)
    assert caught.value.current_version == 2
    assert db_session.get(BrainChange, second.id).status == c.CHANGE_OPEN  # 열린 채 — 거절은 된다
    reject_decision(db_session, second.id, actor=who["cs_mgr"], code="other", now=LATER)


def test_edit_then_apply_keeps_the_first_value_and_marks_the_audit(world):
    who, ch = world["people"], world["changes"]
    result = apply_decision(db_session, ch["cs"], actor=who["cs_mgr"], base_version=1,
                            edits={"name": "사진부터 받기", "text": "치수보다 사진을 먼저"}, view_ms=3200, now=LATER)
    row = current_object(db_session, "cs/lesson/photo")
    assert (result.version, row.name, row.text) == (2, "사진부터 받기", "치수보다 사진을 먼저")
    fields = db_session.get(BrainChange, ch["cs"]).fields
    assert fields["name"] == {"before": "사진 먼저 받기", "after": "사진부터 받기", "proposed": "사진 먼저 꼭 받기"}
    assert fields["text"]["proposed"] is None and fields["text"]["after"] == "치수보다 사진을 먼저"
    audit = db_session.execute(select(SecurityLog).where(SecurityLog.action == "BRAIN_APPLY",
                                                         SecurityLog.target_id == ch["cs"])).scalar_one()
    assert audit.detail["edited"] == 1 and audit.detail["ms"] == 3200 and audit.detail["age_s"] == 300
    assert "사진" not in audit.message  # 감사 줄은 코드 · 숫자만
    with pytest.raises(BrainShapeError):  # 고칠 수 없는 칸
        apply_decision(db_session, ch["drawing"], actor=who["dr_mgr"], base_version=1,
                       edits={"visibility": "all"}, now=LATER)


def test_grade_b_needs_the_key_value_confirmed(world):
    who, ch = world["people"], world["changes"]
    with pytest.raises(BrainConfirmError) as caught:
        apply_decision(db_session, ch["price"], actor=who["admin"], base_version=1, now=LATER)
    assert caught.value.field == "text"
    with pytest.raises(BrainConfirmError):
        apply_decision(db_session, ch["price"], actor=who["admin"], base_version=1,
                       confirm={"field": "text", "value": "옛 화면 값"}, now=LATER)
    # 고쳐 넣으면 확인 글도 고친 값이어야 한다
    result = apply_decision(db_session, ch["price"], actor=who["admin"], base_version=1,
                            edits={"text": "지역별 운임 고친 기준"},
                            confirm={"field": "text", "value": "지역별 운임 고친 기준"}, now=LATER)
    assert result.version == 2


# ── 거절 · 같은 제안 막기 · 항목당 카드 하나 ─────────────────────────────
def test_reject_reason_is_stored_and_the_same_proposal_cannot_come_back(world):
    who, ch = world["people"], world["changes"]
    rejected = reject_decision(db_session, ch["cs"], actor=who["cs_mgr"], code="one_customer", view_ms=1200, now=LATER)
    assert (rejected.status, rejected.reject_code, rejected.decided_by) == ("rejected", "one_customer", who["cs_mgr"].id)
    with pytest.raises(BrainRejectedError) as caught:
        propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"name": "사진 먼저 꼭 받기"},
                       reason="다시", proposer=Proposer.agent_named("cs_agent"),
                       evidence=TWO_SOURCES, now=LATER, known="")
    assert caught.value.reject_code == "one_customer"
    other = propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"name": "사진을 먼저 받기"},
                           reason="다른 값", proposer=Proposer.agent_named("cs_agent"),
                           evidence=TWO_SOURCES, now=LATER, known="")
    assert other.status == "open"  # 대조군: 다른 새 값은 받는다
    with pytest.raises(BrainShapeError):
        reject_decision(db_session, other.id, actor=who["cs_mgr"], code="no_such_chip", now=LATER)


def test_one_open_proposal_per_item_the_second_attaches_to_the_same_card(world):
    who, ch = world["people"], world["changes"]
    ai = propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"text": "사진을 먼저 받는다"},
                        reason="AI 일반화", proposer=Proposer.agent_named("cs_agent"),
                        evidence=TWO_SOURCES, now=NOW, known="")
    human = propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"text": "사진 먼저 그다음 치수"},
                           reason=REASON, proposer=Proposer.user(who["cs_mgr"].id), now=LATER, known="")
    cards = [cd for cd in _cards(who["cs_mgr"]) if cd["key"] == "cs/lesson/photo"]
    assert len(cards) == 1
    assert cards[0]["main"]["id"] == ch["cs"] and not cards[0]["main"]["ai"]  # 처음 사람 제안이 카드
    assert [p["id"] for p in cards[0]["attached"]] == [ai.id, human.id]
    assert inbox_counts(db_session, viewer_of(who["cs_mgr"]), LATER) == {"open": 3, "cards": 1, "ai_waiting": 0}


# ── AI 주 상한 · 4주 닫힘 ────────────────────────────────────────────────
def test_ai_proposals_are_capped_at_twenty_a_week_by_usage(world):
    from sqlalchemy import update
    from foms.persistence.brain.models import BrainObject
    who = world["people"]
    for n in range(22):
        key = f"cs/tone/t{n:02d}"
        create(db_session, who["admin"], key, item_type="tone", layer="cs", name=f"합성 말투 {chr(0xAC00 + n)}")
        db_session.execute(update(BrainObject).where(BrainObject.item_key == key).values(usage_count=n))
        propose_update(db_session, key=key, base_version=1, after={"text": "말투 고침 제안"}, reason="AI 일반화",
                       proposer=Proposer.agent_named("cs_agent"), evidence=TWO_SOURCES, now=NOW, known="")
    db_session.commit()
    cards = [cd for cd in _cards(who["cs_mgr"]) if cd["main"]["ai"]]
    assert len(cards) == c.AI_WEEKLY_CAP == 20
    assert [cd["usage_count"] for cd in cards] == list(range(21, 1, -1))  # 쓰인 횟수 많은 순, 적은 둘이 기다림
    assert inbox_counts(db_session, viewer_of(who["cs_mgr"]), LATER)["ai_waiting"] == 2
    for card in cards[:5]:
        reject_decision(db_session, card["main"]["id"], actor=who["cs_mgr"], code="other", now=LATER)
    data = inbox(db_session, viewer_of(who["cs_mgr"]), now=LATER)
    assert {k: data["ai"][k] for k in ("cap", "used", "left")} == {"cap": 20, "used": 5, "left": 15}  # 상담 층 자리(D106)
    assert data["ai"]["layers"] == {"cs": {"used": 5, "left": 15}}
    assert len([cd for cd in data["cards"] if cd["main"]["ai"]]) == 15  # 이번 주 남은 자리만
    next_week = LATER + datetime.timedelta(days=7)
    assert len([cd for cd in _cards(who["cs_mgr"], now=next_week) if cd["main"]["ai"]]) == 17  # 새 주 = 자리 20


def test_ai_proposals_close_after_four_weeks_but_human_ones_stay_open(world):
    who, ch = world["people"], world["changes"]
    old = NOW - datetime.timedelta(days=c.AI_EXPIRE_DAYS + 1)
    ai = propose_update(db_session, key="cs/tone/polite", base_version=1, after={"name": "오래된 AI 제안"},
                        reason="AI 일반화", proposer=Proposer.agent_named("cs_agent"),
                        evidence=TWO_SOURCES, now=old, known="")
    fresh = propose_update(db_session, key="cs/lesson/hidden", base_version=1, after={"text": "새 AI 제안"},
                           reason="AI 일반화", proposer=Proposer.agent_named("cs_agent"),
                           evidence=TWO_SOURCES, now=NOW, known="")
    db_session.get(BrainChange, ch["cs"]).created_at = old  # 사람 제안도 같은 나이(대조군)
    db_session.flush()
    assert ai.id not in _ids(_cards(who["admin"]))  # 닫기 전에도 제안함에 안 보인다
    assert expire_ai_proposals(db_session, now=LATER) == 1
    assert db_session.get(BrainChange, ai.id).status == c.CHANGE_EXPIRED
    assert db_session.get(BrainChange, ch["cs"]).status == c.CHANGE_OPEN
    assert db_session.get(BrainChange, fresh.id).status == c.CHANGE_OPEN
    with pytest.raises(BrainTargetError):
        apply_decision(db_session, ai.id, actor=who["admin"], base_version=1, now=LATER)


# ── 한꺼번에 넣기 ────────────────────────────────────────────────────────
def test_bulk_apply_takes_grade_a_only(world):
    who, ch = world["people"], world["changes"]
    tone = propose_update(db_session, key="cs/tone/polite", base_version=1, after={"text": "부드럽게 말한다"},
                          reason=REASON, proposer=Proposer.user(who["admin"].id), now=NOW, known="")
    door = propose_update(db_session, key="common/door", base_version=1, after={"text": "여닫이 문짝 설명"},
                          reason=REASON, proposer=Proposer.user(who["admin"].id), now=NOW, known="")
    assert [db_session.get(BrainChange, i).grade for i in (ch["cs"], tone.id, door.id)] == ["A", "A", "B_LIGHT"]
    with pytest.raises(BrainShapeError):
        bulk_apply(db_session, [ch["cs"], tone.id, door.id], actor=who["admin"], now=LATER)
    assert all(db_session.get(BrainChange, i).status == "open" for i in (ch["cs"], tone.id, door.id))
    result = bulk_apply(db_session, [ch["cs"], tone.id, ch["hidden"]], actor=who["cs_mgr"], now=LATER)
    assert [r["id"] for r in result["applied"]] == [ch["cs"], tone.id]
    assert result["failed"] == [{"id": ch["hidden"], "code": "BRAIN_FORBIDDEN"}]  # 볼 수 없는 것은 막힘
    bulk = db_session.execute(select(SecurityLog.detail).where(SecurityLog.action == "BRAIN_APPLY")).scalars().all()
    assert sum(1 for d in bulk if d.get("bulk")) == 2


# ── 다시 확인 ────────────────────────────────────────────────────────────
def test_still_true_bumps_checked_and_stale_dates_through_the_apply_action(world):
    who, ch = world["people"], world["changes"]
    admin_list = recheck_list(db_session, viewer_of(who["admin"]), today=TODAY)
    keys = [i["key"] for i in admin_list["items"]]
    assert keys == ["common/fit", "common/shipping"]  # 지남 · 7일 안(가격 규칙 열린 제안 있음)
    fit = admin_list["items"][0]
    assert (fit["overdue"], fit["stale_after"], fit["open"]) == (True, "2026-09-29", False)
    assert admin_list["counts"] == {"overdue": 1, "soon": 1, "total": 2,
                                    "line": "다시 볼 항목 2개 — 확인 날 지남 1개 · 7일 안 1개"}
    assert recheck_list(db_session, viewer_of(who["cs_mgr"]), today=TODAY)["items"] == []  # 공통 바탕은 ADMIN 몫
    result = confirm_still_true(db_session, "common/fit", actor=who["admin"], version=1, view_ms=900, now=LATER)
    row = current_object(db_session, "common/fit")
    assert (result.version, row.checked_at.isoformat(), row.stale_after.isoformat()) == (2, "2026-11-02", "2027-01-31")
    change = db_session.get(BrainChange, result.change_id)
    assert change.fields == {"checked_at": {"before": "2026-07-01", "after": "2026-11-02"}} and change.status == "applied"
    audit = db_session.execute(select(SecurityLog.detail).where(SecurityLog.target_id == result.change_id,
                                                                SecurityLog.action == "BRAIN_APPLY")).scalar_one()
    assert audit["recheck"] == 1 and audit["ms"] == 900
    assert confirm_still_true(db_session, "common/fit", actor=who["admin"], version=2, now=LATER) is None  # 오늘 이미
    with pytest.raises(BrainOpenProposalError):
        confirm_still_true(db_session, "common/shipping", actor=who["admin"], version=1, now=LATER)
    with pytest.raises(BrainConflictError):
        confirm_still_true(db_session, "common/fit", actor=who["admin"], version=1, now=LATER)
    assert recheck_counts(db_session, viewer_of(who["admin"]), today=TODAY)["total"] == 1
    with pytest.raises(BrainPermissionError):  # 볼 수 없는 항목은 없는 것과 같다
        confirm_still_true(db_session, "drawing/rule/final", actor=who["cs_mgr"], version=1, now=LATER)


# ── 되돌리기 ─────────────────────────────────────────────────────────────
def test_layer_rollback_restores_the_layer_and_keeps_the_release_in_history(world):
    who = world["people"]
    admin = who["admin"]
    day2 = NOW + datetime.timedelta(days=1)
    fix = propose_update(db_session, key="common/door", base_version=1, after={"text": "고친 문짝 설명"},
                         reason=REASON, proposer=Proposer.user(admin.id), now=day2, known="")
    apply_decision(db_session, fix.id, actor=admin, base_version=1, now=day2)
    create(db_session, admin, "common/new", name="새 제품", now=day2)
    link(db_session, admin, "requires", "common/fit", "common/door", now=day2)
    db_session.commit()
    number = current_object(db_session, "common/new").release_no
    assert number == 2
    with pytest.raises(BrainPermissionError):
        rollback_release(db_session, number, "common", actor=who["cs_mgr"], confirm_number=number, now=day2)
    with pytest.raises(BrainShapeError):
        rollback_release(db_session, number, "common", actor=admin, confirm_number=1, now=day2)
    with pytest.raises(BrainTargetError):
        rollback_release(db_session, 0, "common", actor=admin, confirm_number=0, now=day2)
    done = rollback_release(db_session, number, "common", actor=admin, confirm_number=number, now=day2)
    assert done == {"number": 2, "layer": "common", "into": 3, "steps": 3}
    assert current_object(db_session, "common/door").text == "합성 설명 여닫이 문짝"
    assert current_object(db_session, "common/new") is None
    assert current_link(db_session, "requires", "common/fit", "common/door") is None
    mark = db_session.execute(select(BrainRelease.diff).where(BrainRelease.number == 2,
                                                              BrainRelease.layer == "common")).scalar_one()["rollback"]
    assert mark["into"] == 3 and mark["by"] == admin.id
    page = release_page(db_session, viewer_of(admin))
    assert [r["number"] for r in page["items"]] == [3, 2, 1]  # 되돌린 판도 이력에 남는다
    layer2 = page["items"][1]["layers"][0]
    assert layer2["rollback"] == {"into": 3, "at": "2026-11-03"}
    with pytest.raises(BrainTargetError):  # 두 번은 못 한다
        rollback_release(db_session, number, "common", actor=admin, confirm_number=number, now=day2)
    assert db_session.execute(select(SecurityLog).where(SecurityLog.action == "BRAIN_RELEASE_ROLLBACK")).scalar_one()


def test_layer_rollback_is_blocked_when_a_later_release_touched_the_same_item(world):
    admin = world["people"]["admin"]
    day2, day3 = NOW + datetime.timedelta(days=1), NOW + datetime.timedelta(days=2)
    first = propose_update(db_session, key="common/door", base_version=1, after={"text": "판 둘 설명"},
                           reason=REASON, proposer=Proposer.user(admin.id), now=day2, known="")
    apply_decision(db_session, first.id, actor=admin, base_version=1, now=day2)
    later = propose_update(db_session, key="common/door", base_version=2, after={"text": "판 셋 설명"},
                           reason=REASON, proposer=Proposer.user(admin.id), now=day3, known="")
    apply_decision(db_session, later.id, actor=admin, base_version=2, now=day3)
    with pytest.raises(BrainRollbackBlockedError) as caught:
        rollback_release(db_session, 2, "common", actor=admin, confirm_number=2, now=day3)
    assert caught.value.count == 1
    assert current_object(db_session, "common/door").text == "판 셋 설명"


def test_single_item_rollback_is_a_new_proposal_with_the_old_values(world):
    admin = world["people"]["admin"]
    fix = propose_update(db_session, key="common/door", base_version=1, after={"name": "여닫이 문짝 새 이름"},
                         reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")
    apply_decision(db_session, fix.id, actor=admin, base_version=1, now=LATER)
    back = propose_rollback(db_session, key="common/door", to_version=1, reason="옛 이름으로",
                            proposer=Proposer.user(admin.id), now=LATER)
    assert (back.status, back.rollback_of_version, back.base_version) == ("open", 1, 2)
    assert back.fields == {"name": {"before": "여닫이 문짝 새 이름", "after": "여닫이 문짝"}}
    assert current_object(db_session, "common/door").name == "여닫이 문짝 새 이름"  # 제안일 뿐 — 바로 바뀌지 않는다
    card = next(cd for cd in _cards(admin) if cd["key"] == "common/door")
    assert card["main"]["rollback_of"] == 1
    apply_decision(db_session, back.id, actor=admin, base_version=2, now=LATER)
    assert current_object(db_session, "common/door").name == "여닫이 문짝"


# ── 결정 숫자 ────────────────────────────────────────────────────────────
def test_decision_metrics_count_time_rollbacks_and_reject_reasons(world):
    who, ch = world["people"], world["changes"]
    setup = decision_metrics(db_session, now=LATER, days=30)["decisions"]["apply"]  # 재료를 넣은 반영(만들기 일곱)
    assert setup == 7
    apply_decision(db_session, ch["cs"], actor=who["cs_mgr"], base_version=1, view_ms=2000, now=LATER)
    apply_decision(db_session, ch["drawing"], actor=who["dr_mgr"], base_version=1, view_ms=45_000, now=LATER)
    reject_decision(db_session, ch["hidden"], actor=who["admin"], code="needs_photo", view_ms=4000, now=LATER)
    back = propose_rollback(db_session, key="cs/lesson/photo", to_version=1, reason="옛 이름",
                            proposer=Proposer.user(who["admin"].id), now=LATER)
    apply_decision(db_session, back.id, actor=who["admin"], base_version=2, now=LATER)
    data = decision_metrics(db_session, now=LATER, days=30)
    dec = data["decisions"]
    assert (dec["apply"] - setup, dec["reject"], dec["timed"], dec["fast"], dec["fast_share"]) == (3, 1, 3, 2, 0.667)
    assert [b["count"] for b in dec["decide_time"]] == [2, 0, 1, 0, 0]
    assert dec["proposal_age"][0] == {"label": "1시간 안", "count": 4}
    assert data["rollbacks"]["applied_rollback_changes"] == 1
    reasons = {r["code"]: r["count"] for r in data["reject_reasons"]}
    assert reasons["needs_photo"] == 1 and list(reasons) == list(c.REJECT_CODES)


def test_card_shows_scoped_similar_cases_touches_meaning_and_phone_rule(world):
    who, ch = world["people"], world["changes"]
    admin = who["admin"]
    create(db_session, admin, "obs/case/photo", item_type="case", layer="cs", name="사진 먼저 받은 사례",
           confidence="observed")
    create(db_session, admin, "obs/case/hidden", item_type="case", layer="cs", name="숨은 사례", confidence="observed",
           visibility="admin")
    link(db_session, admin, "evidence_of", "obs/case/photo", "cs/lesson/photo")
    link(db_session, admin, "evidence_of", "obs/case/hidden", "cs/lesson/photo")
    card = next(cd for cd in _cards(who["cs_mgr"]) if cd["key"] == "cs/lesson/photo")
    assert card["similar"] == {"count": 1, "first": "2026-11-02", "last": "2026-11-02"}  # 숨은 사례는 수에도 0
    assert card["touches"] == {"total": 1, "items": [{"kind": "evidence_of", "direction": "in", "key": "obs/case/photo",
                                                      "name": "사진 먼저 받은 사례", "type": "case"}]}
    main = card["main"]
    assert main["phone_ok"] is True and main["bulk_ok"] is True and main["confirm"] is None
    assert main["meaning"].startswith("넣으면 이 항목의 새 판이 되고") and "명백한 문제가 없다" in main["meaning"]
    assert [g["name"] for g in main["gates"]] == ["form", "mask", "hanja", "numbers", "conflict", "evidence", "eval"]
    assert main["fields"] == [{"field": "name", "before": "사진 먼저 받기", "after": "사진 먼저 꼭 받기", "label": None,
                               "unit": None, "editable": True, "datatype": "text", "choices": []}]
    assert main["action"] == "propose_edit"
    admin_card = next(cd for cd in _cards(admin) if cd["key"] == "cs/lesson/photo")
    assert admin_card["similar"]["count"] == 2 and admin_card["touches"]["total"] == 2  # 대조군
    price = next(cd for cd in _cards(admin) if cd["main"]["id"] == ch["price"])["main"]
    assert price["phone_ok"] is True and price["confirm"] == {"field": "text", "value": "지역별 운임 새 기준"}
    assert "가격 규칙이라" in price["meaning"]
