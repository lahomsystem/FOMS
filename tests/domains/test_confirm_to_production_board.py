"""생산 보드 run 축(2026-09-17) — 제작중 = PRODUCTION + current ProductionRun.

고객컨펌 승인이 주문을 PRODUCTION 으로 옮기므로 '제작대기/제작중' 은 단계만으로 가를 수 없다.
버킷 SQL·f_stage·KPI 라벨·시트 버튼·묘비가 모두 ``production_runs`` 의 current 행 유무를 본다.
run 의 생애: 시작이 발급, 완료가 COMPLETED 로 닫고, 완료 취소가 다시 열며, 취소는 SUPERSEDED,
수정 제작은 새 회차를 발급한다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from foms.services.production_change_alerts import collect_production_tombstones
from foms.services.production_read_model import (
    build_production_orders_query,
    empty_production_step_stats,
    fetch_production_current_run_ids,
    fill_production_step_counts,
    production_stage_bucket_expr,
)
from models import Order, ProductionRun, User


def _make_user(username: str, *, team: str = "PRODUCTION") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _confirm_quest(*, approved: bool) -> dict:
    return {
        "stage": "고객컨펌", "title": "고객 컨펌", "status": "COMPLETED" if approved else "OPEN",
        "approval_mode": "assignee", "required_approvals": ["CS", "SALES"], "team_approvals": {},
        "assignee_approval": {"approved": approved, "approved_by": 1 if approved else None},
    }


def _make_order(stage_code: str, *, sd: dict | None = None, status: str | None = None,
                deleted_at: str | None = None) -> Order:
    base = {"workflow": {"stage": stage_code}}
    if sd:
        base = {**base, **sd}
    order = Order(
        received_date=get_today_kst().isoformat(),
        customer_name="보드 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=status or stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data=base,
        erp_stage_code=stage_code,
        deleted_at=deleted_at,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _mint_run(order_id: int, *, status: str = "IN_PROGRESS", is_current: bool = True) -> ProductionRun:
    run = ProductionRun(order_id=order_id, status=status, steps=[], defects=[], is_current=is_current)
    db_session.add(run)
    db_session.commit()
    return run


def _runs(order_id: int) -> list[ProductionRun]:
    return (
        db_session.query(ProductionRun)
        .filter(ProductionRun.order_id == order_id)
        .order_by(ProductionRun.created_at.asc())
        .all()
    )


# --------------------------------------------------------------------------- #
# 1. 버킷 SQL 4조합 + 카운트 일치 + f_stage 3분기 + run id 조회
# --------------------------------------------------------------------------- #
def test_bucket_sql_four_combinations_and_counts(app):
    with app.app_context():
        user = _make_user("board_bucket")
        prod_run = _make_order("PRODUCTION")
        _mint_run(prod_run.id)
        prod_norun = _make_order("PRODUCTION")
        confirm_ok = _make_order("CONFIRM", sd={"quests": [_confirm_quest(approved=True)]})
        confirm_no = _make_order("CONFIRM", sd={"quests": [_confirm_quest(approved=False)]})
        done = _make_order("CONSTRUCTION")

        _q = build_production_orders_query(db_session, user, f_stage="", f_q="", erp_mine_only=False)
        bucket_by_id = {
            row.id: row.bucket
            for row in _q.order_by(None)
            .with_entities(Order.id, production_stage_bucket_expr().label("bucket"))
            .all()
        }
        assert bucket_by_id[prod_run.id] == "제작중"
        assert bucket_by_id[prod_norun.id] == "제작대기"
        assert bucket_by_id[confirm_ok.id] == "제작대기"
        assert bucket_by_id[confirm_no.id] == "제작대기"
        assert bucket_by_id[done.id] == "제작완료"

        step_stats = empty_production_step_stats()
        fill_production_step_counts(_q, production_stage_bucket_expr(), step_stats)
        assert step_stats["제작대기"]["count"] == 3
        assert step_stats["제작중"]["count"] == 1
        assert step_stats["제작완료"]["count"] == 1

        def ids_for(f_stage: str) -> set[int]:
            q = build_production_orders_query(db_session, user, f_stage=f_stage, f_q="", erp_mine_only=False)
            return {o.id for o in q.all()}

        assert ids_for("제작대기") == {prod_norun.id, confirm_ok.id, confirm_no.id}
        assert ids_for("제작중") == {prod_run.id}
        assert ids_for("제작완료") == {done.id}

        rows = [prod_run, prod_norun, confirm_ok, confirm_no, done]
        assert fetch_production_current_run_ids(db_session, rows) == {prod_run.id}
        assert fetch_production_current_run_ids(db_session, []) == set()


def test_superseded_run_does_not_count_as_running(app):
    """종결된 run(is_current=False)만 있는 PRODUCTION 은 제작대기다."""
    with app.app_context():
        user = _make_user("board_superseded")
        order = _make_order("PRODUCTION")
        _mint_run(order.id, status="SUPERSEDED", is_current=False)
        _q = build_production_orders_query(db_session, user, f_stage="제작대기", f_q="", erp_mine_only=False)
        assert {o.id for o in _q.all()} == {order.id}
        assert fetch_production_current_run_ids(db_session, [order]) == set()


# --------------------------------------------------------------------------- #
# 2. run 생애 — 완료 취소가 run 을 다시 열고, 수정 제작이 새 회차를 발급한다
# --------------------------------------------------------------------------- #
def test_uncomplete_reopens_the_completed_run(client):
    _login(client, _make_user("board_uncomplete"))
    order_id = _make_order("PRODUCTION").id
    run_id = _mint_run(order_id).id

    assert client.post(f"/api/orders/{order_id}/production/complete", json={}).status_code == 200
    db_session.expire_all()
    closed = db_session.get(ProductionRun, run_id)
    assert closed.status == "COMPLETED" and closed.is_current is False

    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    reopened = db_session.get(ProductionRun, run_id)
    assert reopened.status == "IN_PROGRESS" and reopened.is_current is True
    assert len(_runs(order_id)) == 1
    assert db_session.get(Order, order_id).erp_stage_code == "PRODUCTION"


def test_rework_mints_a_new_run_round(client):
    _login(client, _make_user("board_rework"))
    order_id = _make_order("CONSTRUCTION").id
    first_id = _mint_run(order_id, status="COMPLETED", is_current=False).id

    resp = client.post(f"/api/orders/{order_id}/production/rework", json={"reason": "치수"})
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    runs = _runs(order_id)
    assert len(runs) == 2
    current = [r for r in runs if r.is_current]
    assert len(current) == 1 and current[0].status == "IN_PROGRESS" and current[0].id != first_id
    assert db_session.get(ProductionRun, first_id).status == "COMPLETED"


# --------------------------------------------------------------------------- #
# 3. 시트 — run 유무로 [제작 시작]/[제작 취소] 를 가른다
# --------------------------------------------------------------------------- #
def test_sheet_buttons_follow_run_presence(client):
    _login(client, _make_user("board_sheet"))
    waiting_id = _make_order("PRODUCTION").id
    running_id = _make_order("PRODUCTION").id
    _mint_run(running_id)

    waiting = client.get(f"/erp/production/tablet-sheet/{waiting_id}")
    assert waiting.status_code == 200
    html = waiting.get_data(as_text=True)
    assert 'data-tablet-sheet-action="production-start"' in html
    assert 'data-tablet-sheet-action="production-cancel"' not in html
    assert "고객 컨펌 전" not in html  # PRODUCTION 은 이미 컨펌된 주문이다

    running = client.get(f"/erp/production/tablet-sheet/{running_id}")
    assert running.status_code == 200
    html = running.get_data(as_text=True)
    assert 'data-tablet-sheet-action="production-cancel"' in html
    assert 'data-tablet-sheet-action="production-complete"' in html
    assert 'data-tablet-sheet-action="production-start"' not in html


def test_sheet_unapproved_confirm_shows_muted_label(client):
    """호환 경로: 단계 CONFIRM + quest 미승인이면 시트는 '고객 컨펌 전'(시작 버튼 없음)."""
    _login(client, _make_user("board_sheet_confirm"))
    order_id = _make_order("CONFIRM", sd={"quests": [_confirm_quest(approved=False)]}).id
    html = client.get(f"/erp/production/tablet-sheet/{order_id}").get_data(as_text=True)
    assert "고객 컨펌 전" in html
    assert 'data-tablet-sheet-action="production-start"' not in html


# --------------------------------------------------------------------------- #
# 4. 묘비 bucket — 삭제된 주문도 run 유무로 라벨을 단다
# --------------------------------------------------------------------------- #
def test_tombstone_bucket_follows_run_presence(app):
    with app.app_context():
        deleted_at = get_today_kst().strftime("%Y-%m-%d 12:00:00")
        waiting = _make_order("PRODUCTION", status="DELETED", deleted_at=deleted_at)
        running = _make_order("PRODUCTION", status="DELETED", deleted_at=deleted_at)
        _mint_run(running.id)

        by_id = {t["id"]: t["bucket"] for t in collect_production_tombstones(db_session, None, False)}
        assert by_id[waiting.id] == "제작대기"
        assert by_id[running.id] == "제작중"
