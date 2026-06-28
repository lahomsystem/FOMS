"""Batch 4: 시공 대시보드 KPI 전체스캔 slim 투영 동치 가드.

시공 KPI 스캔은 전체 structured_data(items/parties/quests 등 대용량)를 행마다
로드/파싱했다. KPI는 flags/schedule/workflow 서브트리만 읽으므로(_erp_alerts·
_display_stage_for_order) 해당 3개 JSON 경로만 SQL로 투영하도록 바꿨다.

이 테스트는 (1) SQLAlchemy JSON 서브패스 추출이 SQLite/PG 양쪽에서 dict로 환원되는지
(_ensure_dict가 dict·JSON문자열 모두 처리)와 (2) slim 투영으로 계산한 KPI가 전체
structured_data 로드 경로의 KPI와 정확히 동일한지(동작 보존)를 고정한다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.construction_dashboard_display import _display_stage_for_order
from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    self_measurement_four_checks_done,
)
from models import Order, User


def _make_user(username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CONSTRUCTION",
        name="시공담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _big_extra() -> dict:
    """KPI가 절대 읽지 않는 대용량 키들 — slim 투영에서 빠지는 부분."""
    return {
        "items": [{"name": f"품목{i}", "spec": "x" * 50} for i in range(20)],
        "parties": {"customer": {"name": "고객", "memo": "y" * 200}},
        "quests": [{"q": "z" * 100} for _ in range(10)],
        "assignments": {"drawing_assignee_user_ids": [1, 2, 3]},
    }


def _seed(idx: int, *, flags=None, schedule=None, workflow=None,
          is_self=False, status="IN_CONSTRUCTION") -> int:
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
        phone=f"010-7000-{idx:04d}",
        address=f"서울시 케이구 {idx}",
        product="싱크대",
        status=status,
        manager_name="시공담당",
        is_erp_order=True,
        is_self_measurement=is_self,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _kpis_from(rows, sd_getter) -> dict:
    """라우트 KPI 루프와 동일 로직. sd_getter(row)->structured_data dict."""
    step_stats = {
        "시공대기": {"count": 0, "imminent": 0},
        "시공중": {"count": 0, "imminent": 0},
        "시공완료": {"count": 0, "imminent": 0},
    }
    kpis = {
        "urgent_count": 0,
        "construction_d3_count": 0,
        "measurement_d4_count": 0,
        "production_d2_count": 0,
    }
    for row in rows:
        if row.is_self_measurement and not self_measurement_four_checks_done(row):
            continue
        sd = sd_getter(row)
        display_stage = _display_stage_for_order(row, sd)
        if not display_stage:
            continue
        alerts = _erp_alerts(row, sd, 0)
        if display_stage in step_stats:
            step_stats[display_stage]["count"] += 1
            if alerts.get("construction_d3"):
                step_stats[display_stage]["imminent"] += 1
        if alerts.get("urgent"):
            kpis["urgent_count"] += 1
        if alerts.get("construction_d3"):
            kpis["construction_d3_count"] += 1
        if alerts.get("measurement_d4"):
            kpis["measurement_d4_count"] += 1
        if alerts.get("production_d2"):
            kpis["production_d2_count"] += 1
    return {"kpis": kpis, "steps": step_stats}


def test_construction_kpi_slim_projection_equals_full(app):
    """slim(flags/schedule/workflow 3경로 SQL 투영) KPI == 전체 structured_data 로드 KPI."""
    with app.app_context():
        _make_user("kpi_slim_user")
        ids = []
        # 다양한 조합: 긴급/시공임박/시공중(history)/시공완료/자가실측 스킵/단계없음
        ids.append(_seed(1, flags={"urgent": True},
                         workflow={"stage": "CONSTRUCTION"},
                         schedule={"construction": {"date": "2099-01-01"}}))
        ids.append(_seed(2, flags={"urgent": False},
                         workflow={"stage": "CONSTRUCTION",
                                   "history": [{"note": "시공 시작"}]},
                         schedule={"construction": {"date": "2026-06-28"}}))
        ids.append(_seed(3, workflow={"stage": "COMPLETED"},
                         schedule={"construction": {"date": "2026-06-29"}}))
        ids.append(_seed(4, is_self=True, workflow={"stage": "CONSTRUCTION"},
                         schedule={"construction": {"date": "2026-06-28"}}))
        ids.append(_seed(5, workflow={"stage": "RECEIVED"},
                         schedule={"measurement": {"date": "2026-06-29"}}))
        ids.append(_seed(6, flags={"urgent": True},
                         workflow={"stage": "CONSTRUCTING"},
                         schedule={"construction": {"date": "2026-06-28"}}))

        sd_json = Order.structured_data
        base = db_session.query(Order).filter(Order.id.in_(ids))

        full_rows = base.with_entities(
            Order.id, Order.structured_data, Order.is_self_measurement
        ).all()
        slim_rows = base.with_entities(
            Order.id,
            sd_json["flags"].label("sd_flags"),
            sd_json["schedule"].label("sd_schedule"),
            sd_json["workflow"].label("sd_workflow"),
            Order.is_self_measurement,
        ).all()

        full = _kpis_from(full_rows, lambda r: _ensure_dict(r.structured_data))
        slim = _kpis_from(
            slim_rows,
            lambda r: {
                "flags": _ensure_dict(r.sd_flags),
                "schedule": _ensure_dict(r.sd_schedule),
                "workflow": _ensure_dict(r.sd_workflow),
            },
        )

        assert slim == full, f"slim KPI != full KPI\nslim={slim}\nfull={full}"
        # 동치 검증이 자명하지 않도록(전부 0이 아님) 최소 신호 확인
        assert full["kpis"]["urgent_count"] == 2


def test_construction_kpi_slim_subpaths_roundtrip_dict(app):
    """SQL JSON 서브패스가 _ensure_dict로 dict 환원(dict 또는 JSON문자열)."""
    with app.app_context():
        _make_user("kpi_slim_roundtrip")
        oid = _seed(
            42,
            flags={"urgent": True},
            schedule={"construction": {"date": "2026-07-01"}},
            workflow={"stage": "CONSTRUCTION", "history": [{"note": "시공 시작"}]},
        )
        sd_json = Order.structured_data
        row = (
            db_session.query(Order)
            .filter(Order.id == oid)
            .with_entities(
                sd_json["flags"].label("sd_flags"),
                sd_json["schedule"].label("sd_schedule"),
                sd_json["workflow"].label("sd_workflow"),
            )
            .one()
        )
        flags = _ensure_dict(row.sd_flags)
        schedule = _ensure_dict(row.sd_schedule)
        workflow = _ensure_dict(row.sd_workflow)
        assert flags.get("urgent") is True
        assert schedule["construction"]["date"] == "2026-07-01"
        assert workflow["stage"] == "CONSTRUCTION"
        assert workflow["history"][0]["note"] == "시공 시작"
