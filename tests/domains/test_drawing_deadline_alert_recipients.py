"""도면 마감 알림 — 받는 사람 · 허용 목록 · 루프 배선 · 실패 격리 · 하트비트(설계서 docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md
§9-3 · §9-8 · §10). 때 · 한 번만 · 글은 ``test_drawing_deadline_alert.py``, 종류 등록 ``…_kind.py``, 작업 시트 ``…_sheet.py``,
미리 보기 ``…_preview.py``. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import json

import pytest

from db import db_session
from foms.services.notifications import drawing_deadline_alert as alert
from models import NotificationUserState, OrderFreelancerLink
from tests.domains.test_loop_heartbeat_wiring import _REPO_ROOT, _load
from tests.support.drawing_deadline_seed import (
    at,
    enable,
    make_order,
    make_user,
    rows,
    run,
    seed_world,
    state,
    statements,
    to_ids,
)

MON = "2026-11-23"  # 시공 11/25 (수) 의 마감 날


@pytest.fixture
def world(app):
    return seed_world()


def _sent_to(world, oid):
    names = {v: k for k, v in world.items()}
    return sorted(names[uid] for uid in to_ids(oid))


def test_담당이_있으면_도면_담당과_영업_담당만(world, monkeypatch):
    enable(monkeypatch)
    oid = make_order("김가짜", "2026-11-25", assignees=((world["draw"], "장가짜"),))
    run(at(MON, 8, 2))
    assert _sent_to(world, oid) == ["draw", "sales"]  # 관리자 · 다른 도면팀 · 협력사 계정 없음


def test_담당이_없으면_도면팀_전원_영업_관리자_꺼진_계정은_빠진다(world, monkeypatch):
    """§14 답 1 — 사장님 "관리자도 같이"."""
    enable(monkeypatch)
    oid = make_order("나가짜", "2026-11-25", status="PENDING")
    run(at(MON, 8, 2))
    assert _sent_to(world, oid) == ["admin", "draw", "draw2", "sales"]


def test_담당_계정이_꺼졌으면_닿는_담당이_없어_도면팀_관리자로(world, monkeypatch):
    enable(monkeypatch)
    oid = make_order("다가짜", "2026-11-25", assignees=((world["draw_off"], "꺼진도면"),))
    run(at(MON, 8, 2))
    assert _sent_to(world, oid) == ["admin", "draw", "draw2", "sales"]
    assert "지금: 도면 고치는 중 · 도면 꺼진도면 · 영업 이가짜" in rows(oid)[0].message  # 글은 화면 그대로


def test_영업_쪽은_도면_전달_알림과_같은_규칙(world, monkeypatch):
    """협력사 주문 → CS · 라홈 → CS · 이름 안 맞음 → 영업팀 전원 · '양산' → + 관리자(그 규칙의 몫)."""
    enable(monkeypatch)
    one = ((world["draw"], "장가짜"),)
    partner = make_order("가가짜", "2026-11-25", assignees=one, partner=True, manager="이가짜")
    lahom = make_order("나가짜", "2026-11-25", assignees=one, manager="라홈 직원")
    nomatch = make_order("다가짜", "2026-11-25", assignees=one, manager="없는사람")
    yangsan = make_order("라가짜", "2026-11-25", assignees=one, manager="양산지사")
    run(at(MON, 8, 2))
    assert _sent_to(world, partner) == ["cs", "draw"] and _sent_to(world, lahom) == ["cs", "draw"]
    assert _sent_to(world, nomatch) == ["draw", "sales", "sales2"]
    assert _sent_to(world, yangsan) == ["admin", "draw"]


def test_한_사람이_여러_길에_걸려도_한_줄(world, monkeypatch):
    enable(monkeypatch)
    oid = make_order("마가짜", "2026-11-25", assignees=((world["sales"], "이가짜"), (world["draw"], "장가짜")))
    run(at(MON, 8, 2))
    assert to_ids(oid) == sorted([world["draw"], world["sales"]])
    states = db_session.query(NotificationUserState).filter(
        NotificationUserState.notification_id.in_([n.id for n in rows(oid)])).all()
    assert sorted(s.user_id for s in states) == to_ids(oid)  # 사람마다 줄 하나 · state 하나


def test_프리랜서_영업은_그_주문에_연결이_있을_때만(world, monkeypatch):
    from foms.services.sales_commission.settings import load_settings, save_freelancer

    enable(monkeypatch)
    fl = make_user("프가짜", "SALES")
    save_freelancer(db_session, fl, {"match_name": "프가짜", "start_month": "2020-01", "tax_type": "NONE", "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    one = ((world["draw"], "장가짜"),)
    linked = make_order("바가짜", "2026-11-25", assignees=one, manager="프가짜")
    unlinked = make_order("사가짜", "2026-11-25", assignees=one, manager="프가짜")
    db_session.query(OrderFreelancerLink).filter_by(order_id=unlinked).delete()
    db_session.commit()
    assert db_session.query(OrderFreelancerLink).filter_by(order_id=linked, user_id=fl).count() == 1
    run(at(MON, 8, 2))
    assert fl in to_ids(linked) and fl not in to_ids(unlinked)


def test_허용_목록이면_그_사람만_받고_나머지는_건너뜀_수만(world, monkeypatch):
    enable(monkeypatch, only=str(world["sales"]))
    oid = make_order("아가짜", "2026-11-25", status="PENDING")  # 담당 없음 → 4명 대상
    got = run(at(MON, 8, 2))
    assert to_ids(oid) == [world["sales"]] and got["skipped"] == 3
    assert state()[f"{oid}:2026-11-23:am"]["to"] == ["이가짜"] and state()[f"{oid}:2026-11-23:am"]["skipped"] == 3


def test_허용_목록에_번호가_없으면_아무도_안_받는다(world, monkeypatch):
    """'claude_master' 처럼 이름을 잘못 적어도 전원 발송이 되지 않는다(닫힌 쪽으로)."""
    enable(monkeypatch, only="claude_master")
    oid = make_order("자가짜", "2026-11-25", assignees=((world["draw"], "장가짜"),))
    got = run(at(MON, 8, 2))
    assert rows() == [] and got["skipped"] == 2 and got["sent"] == 1
    assert state()[f"{oid}:2026-11-23:am"]["to"] == []
    assert run(at(MON, 9, 0))["sent"] == 0  # 기록이 있어 다시 셈하지 않는다


# --------------------------------------------------------------------------- #
# 루프 배선 · 실패 격리 · 하트비트
# --------------------------------------------------------------------------- #
def test_루프가_부르고_실패해도_다른_알림을_막지_않는다(app, monkeypatch):
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_notification_escalation.py")
    calls = []
    monkeypatch.setattr(runner.drawing_deadline_alert, "run_drawing_deadline_alerts",
                        lambda db: calls.append(db) or (_ for _ in ()).throw(RuntimeError("deadline boom")))
    with app.app_context():
        result = runner._sweep_once(False)
    assert calls and result["drawing_deadline_alert"] == {"error": "sweep_failed"}
    assert "partner_statement_reminder" in result and "error" not in result["partner_statement_reminder"]
    assert runner._heartbeat_metadata(result, 60)["deadline_alerts"] == 0


def test_루프_한_바퀴_결과와_하트비트_수(world, app, monkeypatch):
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_notification_escalation.py")
    enable(monkeypatch)
    make_order("차가짜", "2026-11-25", assignees=((world["draw"], "장가짜"),))
    real = alert.run_drawing_deadline_alerts
    monkeypatch.setattr(runner.drawing_deadline_alert, "run_drawing_deadline_alerts",
                        lambda db: real(db, now=at(MON, 8, 2)))
    with app.app_context():
        got = runner._drawing_deadline_alert_once(db_session)
    assert got["sent"] == 1 and got["notifications"] == 2 and got["slot"] == "am"
    meta = runner._heartbeat_metadata({"drawing_deadline_alert": got}, 60)
    assert meta["deadline_alerts"] == 2 and "이가짜" not in json.dumps(meta, ensure_ascii=False)
    monkeypatch.delenv(alert.ENABLED_ENV)
    monkeypatch.setattr(runner.drawing_deadline_alert, "run_drawing_deadline_alerts", real)
    with app.app_context(), statements() as seen:
        assert runner._drawing_deadline_alert_once(db_session)["notifications"] == 0
    assert seen == []  # 끔 = 루프 단계 쿼리 0(커밋 · 배달 포함)
