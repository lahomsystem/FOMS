"""QUEST-BACKFILL-00 — quest 단일성 audit/backfill 계약 테스트.

두 층을 검증한다:

* **순수 도메인**(PG 불필요): stage별 current quest 단일성 분류(SAFE/AMBIGUOUS/MANUAL/
  CLEAN), 정규화의 approval 삭제/변경 0, 모호 approval 자동 선택 0, lazy-create 0.
* **PG 통합**(``FOMS_TEST_DATABASE_URL`` 필요, conftest 가 미설정이면 lane skip): 전체
  주문 coverage 100%·미분류 0, BACKFILL 인프라(runs) wrap 으로 SAFE 만 정규화해 DONE,
  ambiguous/manual/clean 무변경, survivor approval 보존, 단일성 회복.

DSN 은 env 로만 주입한다(비밀번호 커밋 0).
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from foms.services.orders.audit_order_quests import (
    AMBIGUOUS,
    CLASSIFICATIONS,
    CLEAN,
    MANUAL,
    SAFE,
    audit_orders,
    classify_quests,
)
from foms.services.orders.backfill_order_quests import (
    SUPERSEDE_REASON,
    apply_resolutions_to_sd,
    run_backfill,
)

NOW = datetime.datetime(2026, 7, 24, 12, 0, 0)
NOW_ISO = NOW.isoformat()


# --------------------------------------------------------------------------- #
# quest builders
# --------------------------------------------------------------------------- #
def _quest(stage, *, status="OPEN", created_at="2026-01-01T00:00:00", approvals=None,
           assignee_approved=None, required=None, transitions=None):
    """단일 quest dict 를 만든다(테스트 fixture)."""
    quest = {
        "stage": stage,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "required_approvals": required if required is not None else [],
        "team_approvals": {},
    }
    for team, approved in (approvals or {}).items():
        quest["team_approvals"][team] = {"approved": approved, "approved_by": None, "approved_at": None}
    if assignee_approved is not None:
        quest["approval_mode"] = "assignee"
        quest["assignee_approval"] = {"approved": assignee_approved, "approved_by": None, "approved_at": None}
    if transitions is not None:
        quest["transitions"] = transitions
    return quest


def _sd(quests, **extra):
    sd = {"quests": quests}
    sd.update(extra)
    return sd


def _approved_marks(sd):
    """주문 전체에서 approved=True 인 (stage, kind, team?) 마크 집합(approval 보존 비교용)."""
    marks = set()
    for quest in (sd.get("quests") or []):
        if not isinstance(quest, dict):
            continue
        stage = str(quest.get("stage"))
        for team, value in (quest.get("team_approvals") or {}).items():
            ok = value.get("approved") if isinstance(value, dict) else bool(value)
            if ok:
                marks.add((stage, "team", str(team)))
        assignee = quest.get("assignee_approval")
        if isinstance(assignee, dict) and assignee.get("approved"):
            marks.add((stage, "assignee", ""))
    return marks


# --------------------------------------------------------------------------- #
# 1. 단일성 분류 (순수)
# --------------------------------------------------------------------------- #
def test_single_active_quest_is_clean():
    sd = _sd([_quest("MEASURE")])
    audit = classify_quests(1, sd)
    assert audit.classification == CLEAN
    assert audit.resolutions == ()


def test_missing_or_empty_quests_is_clean_no_lazy_create():
    assert classify_quests(1, {}).classification == CLEAN
    assert classify_quests(2, {"quests": []}).classification == CLEAN
    assert classify_quests(3, None).classification == CLEAN


def test_different_stages_active_is_clean():
    """서로 다른 stage 의 active quest 다수는 정상(단일성은 stage별)."""
    sd = _sd([_quest("RECEIVED", status="COMPLETED"), _quest("MEASURE"), _quest("CONFIRM")])
    assert classify_quests(1, sd).classification == CLEAN


def test_duplicate_active_no_approval_is_safe_survivor_newest():
    sd = _sd([
        _quest("MEASURE", created_at="2026-01-01T00:00:00"),
        _quest("MEASURE", created_at="2026-02-01T00:00:00"),
    ])
    audit = classify_quests(1, sd)
    assert audit.classification == SAFE
    assert len(audit.resolutions) == 1
    res = audit.resolutions[0]
    assert res.stage_code == "MEASURE"
    assert res.survivor_index == 1  # 최신
    assert res.superseded_indexes == (0,)


def test_duplicate_active_one_approval_is_safe_keeps_approved():
    sd = _sd([
        _quest("PRODUCTION", created_at="2026-02-01T00:00:00"),  # 최신, 미승인
        _quest("PRODUCTION", created_at="2026-01-01T00:00:00", approvals={"PRODUCTION": True}),
    ])
    audit = classify_quests(1, sd)
    assert audit.classification == SAFE
    res = audit.resolutions[0]
    assert res.survivor_index == 1  # 최신이 아니라 approval 보유분을 유지
    assert res.superseded_indexes == (0,)


def test_duplicate_active_labels_and_codes_collapse_same_stage():
    """한글 라벨('실측')과 코드('MEASURE')는 동일 stage 로 정규화된다."""
    sd = _sd([_quest("실측"), _quest("MEASURE")])
    audit = classify_quests(1, sd)
    assert audit.classification == SAFE
    assert audit.resolutions[0].stage_code == "MEASURE"


def test_duplicate_active_two_approvals_is_ambiguous_no_autoselect():
    sd = _sd([
        _quest("MEASURE", approvals={"SALES": True}),
        _quest("MEASURE", assignee_approved=True),
    ])
    audit = classify_quests(1, sd)
    assert audit.classification == AMBIGUOUS
    assert audit.ambiguous_stages == ("MEASURE",)
    assert audit.resolutions == ()  # 자동 선택 금지


def test_superseded_duplicate_does_not_count_as_active():
    """terminal(SUPERSEDED) quest 는 active 로 세지 않아 단일성 위반이 아니다."""
    sd = _sd([
        _quest("MEASURE"),
        _quest("MEASURE", status="SUPERSEDED",
               transitions=[{"to": "SUPERSEDED", "at": NOW_ISO}]),
    ])
    assert classify_quests(1, sd).classification == CLEAN


def test_malformed_quests_container_is_manual():
    assert classify_quests(1, {"quests": {"stage": "MEASURE"}}).classification == MANUAL


def test_malformed_quest_entry_is_manual():
    sd = _sd([_quest("MEASURE"), "not-a-dict"])
    audit = classify_quests(1, sd)
    assert audit.classification == MANUAL
    assert audit.manual_reasons


def test_ambiguous_precedes_manual_when_both_present():
    sd = _sd([
        _quest("MEASURE", approvals={"SALES": True}),
        _quest("MEASURE", assignee_approved=True),
        "malformed",
    ])
    assert classify_quests(1, sd).classification == AMBIGUOUS


def test_required_team_drift_reported_but_not_bucket_changing():
    """required_approvals 불일치는 report-only — 단일 active 는 여전히 CLEAN."""
    sd = _sd([_quest("MEASURE", required=["DRAWING"])])  # MEASURE 기대는 SALES
    audit = classify_quests(1, sd)
    assert audit.classification == CLEAN
    assert "MEASURE" in audit.required_team_drift


def test_lahom_orderer_expects_cs_required_team():
    """라홈 발주사면 MEASURE required team 이 CS 로 기대되어 SALES 선언은 drift."""
    sd = _sd(
        [_quest("MEASURE", required=["SALES"])],
        parties={"orderer": {"name": "라홈 강남"}},
    )
    assert "MEASURE" in classify_quests(1, sd).required_team_drift


def test_classification_always_in_closed_set():
    for sd in ({}, _sd([_quest("MEASURE")]), _sd([_quest("MEASURE"), _quest("MEASURE")])):
        assert classify_quests(1, sd).classification in CLASSIFICATIONS


# --------------------------------------------------------------------------- #
# 2. 정규화 (순수) — approval 보존·단일성 회복
# --------------------------------------------------------------------------- #
def test_apply_resolutions_supersedes_extra_preserves_approval():
    sd = _sd([
        _quest("PRODUCTION", created_at="2026-02-01T00:00:00"),
        _quest("PRODUCTION", created_at="2026-01-01T00:00:00", approvals={"PRODUCTION": True}),
    ])
    audit = classify_quests(1, sd)
    before = _approved_marks(sd)
    new_sd, superseded = apply_resolutions_to_sd(sd, audit.resolutions, now_iso=NOW_ISO)

    assert superseded == 1
    assert _approved_marks(new_sd) == before  # approval 삭제/변경 0
    # 원본 불변(deepcopy)
    assert sd["quests"][0]["status"] == "OPEN"
    # survivor(승인 보유) 무변경, 나머지만 terminal
    survivor = new_sd["quests"][1]
    superseded_q = new_sd["quests"][0]
    assert survivor["status"] == "OPEN"
    assert survivor["team_approvals"]["PRODUCTION"]["approved"] is True
    assert superseded_q["status"] == "SUPERSEDED"
    assert superseded_q["transitions"][-1]["reason"] == SUPERSEDE_REASON


def test_normalization_restores_single_ness():
    sd = _sd([_quest("MEASURE", created_at="a"), _quest("MEASURE", created_at="b")])
    audit = classify_quests(1, sd)
    new_sd, _ = apply_resolutions_to_sd(sd, audit.resolutions, now_iso=NOW_ISO)
    assert classify_quests(1, new_sd).classification == CLEAN


def test_apply_resolutions_noop_when_no_resolutions():
    sd = _sd([_quest("MEASURE")])
    new_sd, superseded = apply_resolutions_to_sd(sd, (), now_iso=NOW_ISO)
    assert superseded == 0
    assert new_sd == sd


# --------------------------------------------------------------------------- #
# 3. PG 통합 — coverage 100%, BACKFILL wrap, 무변경 격리
# --------------------------------------------------------------------------- #
def _make_order(**quests_kw):
    """orders 테이블 최소 필수 컬럼 + structured_data 를 채운 dict."""
    from models import Order

    return Order(
        received_date="2026-07-24",
        customer_name="테스트",
        phone="01000000000",
        address="서울",
        product="가구",
        structured_data=quests_kw.get("structured_data"),
    )


def _reset_tables(engine):
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM maintenance_backfill_checkpoints"))
        conn.execute(text("DELETE FROM maintenance_backfill_approvals"))
        conn.execute(text("DELETE FROM maintenance_backfill_runs"))
        conn.execute(text("DELETE FROM orders"))


@pytest.fixture
def clean_db(pg_engine):
    _reset_tables(pg_engine)
    yield pg_engine
    _reset_tables(pg_engine)


def test_pg_audit_coverage_and_backfill_singleness(clean_db):
    engine = clean_db
    session = sessionmaker(bind=engine)()
    try:
        # 5종: clean / no-quests / safe(dup no-approval) / safe(dup one-approval) /
        # ambiguous(dup two-approval) / manual(malformed)
        orders = {
            "clean": _make_order(structured_data=_sd([_quest("MEASURE")])),
            "empty": _make_order(structured_data={}),
            "safe_noappr": _make_order(structured_data=_sd([
                _quest("MEASURE", created_at="2026-01-01T00:00:00"),
                _quest("MEASURE", created_at="2026-02-01T00:00:00"),
            ])),
            "safe_oneappr": _make_order(structured_data=_sd([
                _quest("PRODUCTION", created_at="2026-02-01T00:00:00"),
                _quest("PRODUCTION", created_at="2026-01-01T00:00:00", approvals={"PRODUCTION": True}),
            ])),
            "ambiguous": _make_order(structured_data=_sd([
                _quest("CONSTRUCTION", approvals={"CONSTRUCTION": True}),
                _quest("CONSTRUCTION", assignee_approved=True),
            ])),
            "manual": _make_order(structured_data={"quests": {"stage": "CS"}}),
        }
        for order in orders.values():
            session.add(order)
        session.commit()
        ids = {name: o.id for name, o in orders.items()}
        appr_before = _approved_marks(orders["safe_oneappr"].structured_data)

        # --- audit: coverage 100%, 미분류 0 ---
        audit = audit_orders(session)
        assert audit.total == 6
        assert audit.unclassified == 0
        assert audit.counts[CLEAN] == 2   # clean + empty
        assert audit.counts[SAFE] == 2    # safe_noappr + safe_oneappr
        assert audit.counts[AMBIGUOUS] == 1
        assert audit.counts[MANUAL] == 1
        assert sum(audit.counts[c] for c in CLASSIFICATIONS) == audit.total

        # --- backfill: SAFE 만 정규화, DONE, coverage 100% ---
        report = run_backfill(
            session,
            db_instance_id="test-db",
            owner_identity="tester",
            audit=audit,
            now=NOW,
            activate_approval=lambda s, run: setattr(run, "current_approval_seq", 1),
        )
        assert report.state == "DONE"
        assert report.total_rows == 2
        assert report.completed_rows == 2
        assert report.superseded_quests == 2  # 각 safe 주문에서 1개씩

        # --- 재audit: SAFE 는 이제 CLEAN, ambiguous/manual 불변 ---
        session.expire_all()
        after = audit_orders(session)
        assert after.counts[SAFE] == 0
        assert after.counts[CLEAN] == 4
        assert after.counts[AMBIGUOUS] == 1
        assert after.counts[MANUAL] == 1

        # --- survivor approval 보존 + 단일 active ---
        from models import Order

        safe1 = session.get(Order, ids["safe_oneappr"])
        assert _approved_marks(safe1.structured_data) == appr_before
        actives = [q for q in safe1.structured_data["quests"]
                   if str(q.get("status")) in ("OPEN", "IN_PROGRESS")]
        assert len(actives) == 1 and actives[0]["team_approvals"]["PRODUCTION"]["approved"] is True

        # --- ambiguous 주문은 손대지 않음(자동 선택 0) ---
        amb = session.get(Order, ids["ambiguous"])
        amb_actives = [q for q in amb.structured_data["quests"]
                       if str(q.get("status")) in ("OPEN", "IN_PROGRESS")]
        assert len(amb_actives) == 2

        # --- no-quests 주문은 lazy-create 0 (여전히 quest 없음) ---
        empty = session.get(Order, ids["empty"])
        assert not (empty.structured_data or {}).get("quests")
    finally:
        session.close()
