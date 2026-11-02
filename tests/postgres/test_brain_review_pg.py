"""제안함 · 다시 확인 · 판 되돌리기 PostgreSQL 레인(설계서 7.5 화면 4 · 5 · 6 · ⑤-3) — SQLite 메인 레인과 같은 답인지 진짜
PostgreSQL(JSONB 경로 ``#>>`` 로 새 보기 범위 거르기 · 창 함수 이웃 · 줄 잠금 · 감사 JSON)에서 본다.

- 제안함: 보기 범위 · 결정 가능 거르기(음성 대조군 — 같은 상담 층의 숨긴 제안) · 항목당 카드 하나 · 새 항목 제안의 새 보기
  범위(JSONB 안 값)로 거르기.
- 결정: 등급 B 확인 · 고쳐 넣기 · 거절 까닭 · 같은 제안 막기.
- 다시 확인 '아직 맞음' · 판 되돌리기 · 결정 숫자(감사 JSONB).
``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다. 합성 항목만.
"""

from __future__ import annotations

import datetime

import pytest

from foms.services.brain.decide import apply_decision, reject_decision
from foms.services.brain.errors import BrainPermissionError, BrainRejectedError
from foms.services.brain.inbox import inbox, inbox_counts
from foms.services.brain.metrics import decision_metrics
from foms.services.brain.proposals import Proposer, propose_create, propose_update
from foms.services.brain.recheck import confirm_still_true, recheck_list
from foms.services.brain.rollback import rollback_release
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from tests.support.brain_review_support import review_world
from tests.support.brain_screen_support import TODAY
from tests.support.brain_support import NOW, REASON, create, link, values

LATER = NOW + datetime.timedelta(minutes=5)


def test_inbox_filters_by_scope_and_new_visibility_on_postgres(pg_session):
    world = review_world(pg_session)
    who, ch = world["people"], world["changes"]
    admin = who["admin"]
    create(pg_session, admin, "obs/case/photo", item_type="case", layer="cs", name="사진 먼저 받은 사례",
           confidence="observed")
    create(pg_session, admin, "obs/case/hidden", item_type="case", layer="cs", name="숨은 사례", confidence="observed",
           visibility="admin")
    link(pg_session, admin, "evidence_of", "obs/case/photo", "cs/lesson/photo")
    link(pg_session, admin, "evidence_of", "obs/case/hidden", "cs/lesson/photo")
    hidden_new = propose_create(pg_session, key="cs/lesson/new-hidden", brand="COMMON", layer="cs", item_type="lesson",
                                values=values("새 숨은 배운 점", visibility="team:DRAWING"), reason=REASON,
                                proposer=Proposer.user(admin.id), now=NOW, known="")
    shown_new = propose_create(pg_session, key="cs/lesson/new-shown", brand="COMMON", layer="cs", item_type="lesson",
                               values=values("새 보이는 배운 점"), reason=REASON, proposer=Proposer.user(admin.id),
                               now=NOW, known="")
    ai = propose_update(pg_session, key="cs/lesson/photo", base_version=1, after={"text": "사진 먼저"},
                        reason="AI 일반화", proposer=Proposer.agent_named("cs_agent"), now=NOW, known="")
    pg_session.commit()
    cs = inbox(pg_session, viewer_of(who["cs_mgr"]), now=LATER)
    assert sorted(c["main"]["id"] for c in cs["cards"]) == sorted([ch["cs"], shown_new.id])
    photo = next(c for c in cs["cards"] if c["key"] == "cs/lesson/photo")
    assert [p["id"] for p in photo["attached"]] == [ai.id]  # 항목당 카드 하나
    assert photo["similar"] == {"count": 1, "first": "2026-11-02", "last": "2026-11-02"}  # 숨은 사례는 수에도 0
    assert photo["touches"]["total"] == 1 and [t["key"] for t in photo["touches"]["items"]] == ["obs/case/photo"]
    admin_photo = next(c for c in inbox(pg_session, viewer_of(admin), now=LATER)["cards"] if c["key"] == "cs/lesson/photo")
    assert admin_photo["similar"]["count"] == 2 and admin_photo["touches"]["total"] == 2  # 대조군
    assert inbox_counts(pg_session, viewer_of(who["cs_mgr"]), LATER) == {"open": 3, "cards": 2, "ai_waiting": 0}
    admin_ids = {c["main"]["id"] for c in inbox(pg_session, viewer_of(admin), now=LATER)["cards"]}
    assert {hidden_new.id, ch["hidden"], ch["price"]} <= admin_ids  # 대조군: 숨긴 것도 ADMIN 에게는 있다
    with pytest.raises(BrainPermissionError):
        apply_decision(pg_session, hidden_new.id, actor=who["cs_mgr"], base_version=None, now=LATER)


def test_decisions_recheck_rollback_and_metrics_on_postgres(pg_session):
    world = review_world(pg_session)
    who, ch = world["people"], world["changes"]
    admin = who["admin"]
    apply_decision(pg_session, ch["price"], actor=admin, base_version=1, view_ms=1500, now=LATER,
                   confirm={"field": "text", "value": "지역별 운임 새 기준"})
    apply_decision(pg_session, ch["cs"], actor=who["cs_mgr"], base_version=1, edits={"name": "사진부터 받기"},
                   view_ms=9000, now=LATER)
    reject_decision(pg_session, ch["drawing"], actor=who["dr_mgr"], code="not_policy", view_ms=3000, now=LATER)
    pg_session.commit()
    assert current_object(pg_session, "cs/lesson/photo").name == "사진부터 받기"
    with pytest.raises(BrainRejectedError):
        propose_update(pg_session, key="drawing/rule/final", base_version=1, after={"text": "최종 도면만 올린다"},
                       reason="다시", proposer=Proposer.agent_named("drawing_agent"), now=LATER, known="")
    listed = recheck_list(pg_session, viewer_of(admin), today=TODAY)
    assert [(i["key"], i["overdue"], i["open"]) for i in listed["items"]] == [
        ("common/fit", True, False), ("common/shipping", False, False)]  # 글 고침 승인은 확인 날을 옮기지 않는다
    assert listed["counts"]["overdue"] == 1 and listed["counts"]["soon"] == 1
    done = confirm_still_true(pg_session, "common/fit", actor=admin, version=1, now=LATER)
    assert current_object(pg_session, "common/fit").stale_after.isoformat() == "2027-01-31" and done.version == 2
    pg_session.commit()
    data = decision_metrics(pg_session, now=LATER, days=30)
    assert data["decisions"]["timed"] == 3 and data["decisions"]["fast"] == 2 and data["rechecks"] == 1
    assert {r["code"]: r["count"] for r in data["reject_reasons"]}["not_policy"] == 1
    rolled = rollback_release(pg_session, 1, "drawing", actor=admin, confirm_number=1, now=LATER)
    assert rolled["steps"] == 1 and current_object(pg_session, "drawing/rule/final") is None
    pg_session.commit()


def test_d104_actions_schema_visibility_flags_and_confidence_on_postgres(pg_session):
    from foms.persistence.brain.models import BrainChange
    from foms.services.brain.action_runner import perform
    from foms.services.brain.apply import apply_change
    from foms.services.brain.decide import flag_stale_bases

    world = review_world(pg_session)
    who, ch = world["people"], world["changes"]
    admin, cs = who["admin"], who["cs_mgr"]
    create(pg_session, admin, "common/depth", item_type="spec", name="몸통 깊이",
           payload={"value": 600, "unit": "mm", "low": 300, "high": 900})
    _a, made = perform(pg_session, "propose_edit", actor=admin, now=NOW,
                       body={"key": "common/depth", "base_version": 1, "after": {"payload.value": 650}, "reason": "r"})
    sibling = propose_update(pg_session, key="common/depth", base_version=1, after={"text": "같은 항목 둘째 제안"},
                             reason=REASON, proposer=Proposer.agent_named("cs_agent"), now=NOW, known="")
    view = next(c for c in inbox(pg_session, viewer_of(admin), now=LATER)["cards"] if c["key"] == "common/depth")
    assert [(r["field"], r["before"], r["after"]) for r in view["main"]["fields"]] == [("payload.value", 600, 650)]
    perform(pg_session, "edit_apply", actor=admin, now=LATER,
            body={"change_id": made["change_id"], "base_version": 1, "edits": {"payload.value": 640}})
    row = current_object(pg_session, "common/depth")
    assert row.payload == {"value": 640, "unit": "mm", "low": 300, "high": 900} and row.confidence == "confirmed"
    assert pg_session.get(BrainChange, sibling.id).base_changed_at == LATER  # 넣는 순간 형제 제안에 표시
    assert pg_session.get(BrainChange, made["change_id"]).decided_action == "edit_apply"
    assert flag_stale_bases(pg_session, now=LATER) == 0
    with pytest.raises(BrainPermissionError):  # 엔진이 보기 범위를 본다(같은 상담 층 · 도면팀만)
        apply_change(pg_session, ch["hidden"], actor=cs, now=LATER)
    pg_session.rollback()
