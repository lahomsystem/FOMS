"""Batch 4: 생산 대시보드 KPI 전체스캔 slim 투영 동치 가드.

compute_production_kpis_and_badges는 전체 structured_data를 행마다 로드/파싱했다.
KPI/배지는 flags/schedule/workflow 서브트리만 읽으므로(_erp_alerts·_erp_get_stage)
해당 3개 JSON 경로만 SQL로 투영하도록 바꿨다. kpi_rows는 호출부에서 len()(총건수)으로만
쓰여 행 수는 불변이다.

slim 경로로 계산한 KPI/step 배지가 전체 structured_data 로드 reference와 정확히 동일한지
(동작 보존), 반환 kpi_rows 길이(=total_orders)가 보존되는지를 고정한다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import _ensure_dict, _erp_alerts, _erp_get_stage
from foms.services.production_read_model import (
    _kpi_stage_label_from_erp_stage,
    compute_production_kpis_and_badges,
    empty_production_step_stats,
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


def _big_extra() -> dict:
    return {
        "items": [{"name": f"i{i}", "spec": "x" * 40} for i in range(15)],
        "parties": {"customer": {"name": "고객", "memo": "y" * 150}},
    }


def _seed(idx: int, *, flags=None, schedule=None, workflow=None) -> int:
    sd = dict(_big_extra())
    if flags is not None:
        sd["flags"] = flags
    if schedule is not None:
        sd["schedule"] = schedule
    if workflow is not None:
        sd["workflow"] = workflow
    order = Order(
        received_date="2026-06-01",
        customer_name=f"고객{idx}",
        phone=f"010-6000-{idx:04d}",
        address=f"서울시 피구 {idx}",
        product="싱크대",
        status="IN_PRODUCTION",
        manager_name="생산담당",
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _reference(ids, step_stats) -> dict:
    """전체 structured_data 로드 경로로 동일 KPI/배지 계산(reference)."""
    kpis = {
        "urgent_count": 0,
        "production_d2_count": 0,
        "measurement_d4_count": 0,
        "construction_d3_count": 0,
    }
    rows = (
        db_session.query(Order)
        .filter(Order.id.in_(ids))
        .with_entities(Order.id, Order.structured_data)
        .all()
    )
    for r in rows:
        sd = _ensure_dict(r.structured_data)
        a = _erp_alerts(None, sd, 0)
        if a.get("urgent"):
            kpis["urgent_count"] += 1
        if a.get("production_d2"):
            kpis["production_d2_count"] += 1
        if a.get("measurement_d4"):
            kpis["measurement_d4_count"] += 1
        if a.get("construction_d3"):
            kpis["construction_d3_count"] += 1
        label = _kpi_stage_label_from_erp_stage(_erp_get_stage(None, sd) or "")
        if not label or label not in step_stats:
            continue
        if a.get("production_d2"):
            step_stats[label]["imminent"] += 1
        if a.get("drawing_overdue"):
            step_stats[label]["overdue"] += 1
    return kpis


def test_production_kpi_slim_equals_full(app):
    with app.app_context():
        _make_user("prod_kpi_slim")
        ids = [
            _seed(1, flags={"urgent": True}, workflow={"stage": "PRODUCTION"},
                  schedule={"construction": {"date": "2026-06-28"}}),
            _seed(2, workflow={"stage": "CONFIRM"},
                  schedule={"construction": {"date": "2099-01-01"}}),
            _seed(3, flags={"urgent": True}, workflow={"stage": "CONSTRUCTION"},
                  schedule={"measurement": {"date": "2026-06-29"}}),
            _seed(4, workflow={"stage": "PRODUCTION"},
                  schedule={"construction": {"date": "2026-06-29"}}),
            _seed(5, workflow={"stage": "CONFIRM"}, schedule={}),
        ]

        q = db_session.query(Order).filter(Order.id.in_(ids))
        slim_steps = empty_production_step_stats()
        kpi_rows, slim_kpis = compute_production_kpis_and_badges(q, slim_steps)

        ref_steps = empty_production_step_stats()
        ref_kpis = _reference(ids, ref_steps)

        assert slim_kpis == ref_kpis, f"slim={slim_kpis} ref={ref_kpis}"
        assert slim_steps == ref_steps, f"slim={slim_steps} ref={ref_steps}"
        # 호출부 total_orders = len(kpi_rows): 행 수 불변
        assert len(kpi_rows) == len(ids)
        assert ref_kpis["urgent_count"] == 2
