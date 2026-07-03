"""W3-2: 생산 대시보드 단계 필터 flat 컬럼(erp_stage_code) 전환 계약 가드.

build_production_orders_query / production_stage_bucket_expr가 JSONB path cast 대신
flat 컬럼 ``Order.erp_stage_code``(index=True)로 단계를 필터/버킷한다. erp_stage_code는
workflow.stage 원문값(JSON 따옴표 없음)이므로 IN 목록에도 따옴표가 붙지 않아야 한다.

SQLite는 PG JSONB path 세만틱(``cast(sd['workflow']['stage'], String)``)을 신뢰성 있게
지원하지 않는다. 따라서 "구(JSONB) vs 신(flat) 동일 id 집합" 비교 대신 신 필터 단독의
stage별 포함/제외를 계약으로 검증한다. 구/신 동등은 게이트 실측(erp_stage_code ↔
structured_data#>>'{workflow,stage}' 정합 100%)으로 보증된다.

seed는 sync_erp_flat_columns(명시 호출 함수, event listener 아님)를 우회하고
erp_stage_code를 직접 세팅한다 — 게이트가 정합 100%를 보장하므로 이것이 운영 현실 반영.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.production_read_model import (
    build_production_orders_query,
    empty_production_step_stats,
    fill_production_step_counts,
    production_stage_bucket_expr,
)
from models import Order, User


def _make_user(username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="PRODUCTION",
        name="생산담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _seed(idx: int, stage_code: str | None) -> int:
    """erp_stage_code를 명시 세팅한 ERP 주문 1건 생성(sync 우회 — 게이트 정합 전제)."""
    order = Order(
        received_date="2026-06-01",
        customer_name=f"고객{idx}",
        phone=f"010-7000-{idx:04d}",
        address=f"서울시 스테이지 {idx}",
        product="싱크대",
        status="IN_PRODUCTION",
        manager_name="생산담당",
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage_code} if stage_code else {}},
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def test_base_stage_filter_includes_and_excludes(app):
    """base 필터: CONFIRM/PRODUCTION/CONSTRUCTION + 한글값만 포함, 그 외 제외."""
    with app.app_context():
        user = _make_user("prod_stage_base")
        ids = {
            "CONFIRM": _seed(1, "CONFIRM"),
            "PRODUCTION": _seed(2, "PRODUCTION"),
            "CONSTRUCTION": _seed(3, "CONSTRUCTION"),
            "생산_한글": _seed(4, "생산"),  # 미래 방어(한글) — 포함
            "MEASURE": _seed(5, "MEASURE"),  # 제외
            "COMPLETED": _seed(6, "COMPLETED"),  # 제외
            "None": _seed(7, None),  # 제외
        }

        _q = build_production_orders_query(
            db_session, user, f_stage="", f_q="", erp_mine_only=False
        )
        got = {o.id for o in _q.all()}

        expected = {ids["CONFIRM"], ids["PRODUCTION"], ids["CONSTRUCTION"], ids["생산_한글"]}
        assert got == expected, f"got={got} expected={expected}"
        assert ids["MEASURE"] not in got
        assert ids["COMPLETED"] not in got
        assert ids["None"] not in got


def test_f_stage_branch_filters(app):
    """f_stage 분기: 제작대기→CONFIRM/고객컨펌, 제작중→PRODUCTION/생산, 제작완료→CONSTRUCTION/시공."""
    with app.app_context():
        user = _make_user("prod_stage_branch")
        confirm_id = _seed(1, "CONFIRM")
        gcc_id = _seed(2, "고객컨펌")  # 한글 대기값
        prod_id = _seed(3, "PRODUCTION")
        prod_kr_id = _seed(4, "생산")
        cons_id = _seed(5, "CONSTRUCTION")
        cons_kr_id = _seed(6, "시공")

        def ids_for(f_stage: str) -> set[int]:
            _q = build_production_orders_query(
                db_session, user, f_stage=f_stage, f_q="", erp_mine_only=False
            )
            return {o.id for o in _q.all()}

        assert ids_for("제작대기") == {confirm_id, gcc_id}
        assert ids_for("제작중") == {prod_id, prod_kr_id}
        assert ids_for("제작완료") == {cons_id, cons_kr_id}


def test_stage_bucket_expr_labels(app):
    """production_stage_bucket_expr GROUP BY가 stage별 올바른 버킷 라벨로 카운트."""
    with app.app_context():
        user = _make_user("prod_stage_bucket")
        _seed(1, "CONFIRM")
        _seed(2, "고객컨펌")   # 제작대기 (총 2)
        _seed(3, "PRODUCTION")  # 제작중 (총 1)
        _seed(4, "CONSTRUCTION")
        _seed(5, "시공")        # 제작완료 (총 2)

        _q = build_production_orders_query(
            db_session, user, f_stage="", f_q="", erp_mine_only=False
        )
        step_stats = empty_production_step_stats()
        fill_production_step_counts(_q, production_stage_bucket_expr(), step_stats)

        assert step_stats["제작대기"]["count"] == 2
        assert step_stats["제작중"]["count"] == 1
        assert step_stats["제작완료"]["count"] == 2
