"""주문 목록·휴대폰 '현재 작업' 칸의 보드 단계 표시(board_state) 계약."""
from __future__ import annotations

import pytest
from flask import template_rendered
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services import construction_dashboard_display
from foms.services.erp_display import get_today_kst
from foms.services.orders import board_state_display
from foms.services.orders.board_state_display import (
    build_board_state,
    production_run_ids_for,
)
from foms.services.orders.dashboard_dto import build_orders_row_dtos
from foms.services.production_dashboard_display import _production_stage_label_from_stage
from foms.services.production_read_model import _kpi_stage_label_from_erp_stage
from models import Order, ProductionRun, User

_KEYS = {"kind", "label", "tone", "title", "link_label", "link_endpoint", "link_params"}


class _O:
    def __init__(self, oid: int):
        self.id = oid


def _sd(stage: str, history: list | None = None) -> dict:
    wf = {"stage": stage}
    if history is not None:
        wf["history"] = history
    return {"workflow": wf}


def _make_order(stage_code: str) -> Order:
    order = Order(
        received_date=get_today_kst().isoformat(),
        customer_name="보드 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage_code}},
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _mint_run(order_id: int, *, status: str = "IN_PROGRESS", is_current: bool = True) -> None:
    db_session.add(
        ProductionRun(order_id=order_id, status=status, steps=[], defects=[], is_current=is_current)
    )
    db_session.commit()


def _count_queries(fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


# ① 단계 표 전수
@pytest.mark.parametrize(
    "stage_code, sd, has_run, expected",
    [
        ("PRODUCTION", _sd("PRODUCTION"), True, {
            "kind": "production", "label": "제작중", "tone": "soft", "title": "",
            "link_label": "생산 보드 열기",
            "link_endpoint": "erp_production_page.erp_production_dashboard",
            "link_params": {"focus_order": 7},
        }),
        ("PRODUCTION", _sd("PRODUCTION"), False, {
            "kind": "production", "label": "제작대기", "tone": "soft", "title": "",
            "link_label": "생산 보드 열기",
            "link_endpoint": "erp_production_page.erp_production_dashboard",
            "link_params": {"focus_order": 7},
        }),
        ("CONSTRUCTION", _sd("CONSTRUCTION", [{"note": "시공 시작"}]), False, {
            "kind": "construction", "label": "시공중", "tone": "soft", "title": "",
            "link_label": "시공 보드 열기",
            "link_endpoint": "erp_construction_page.erp_construction_dashboard",
            "link_params": {"focus_order": 7},
        }),
        ("CONSTRUCTION", _sd("CONSTRUCTION", [{"note": "다른 기록"}]), False, {
            "kind": "construction", "label": "시공대기", "tone": "soft", "title": "",
            "link_label": "시공 보드 열기",
            "link_endpoint": "erp_construction_page.erp_construction_dashboard",
            "link_params": {"focus_order": 7},
        }),
        ("COMPLETED", _sd("COMPLETED"), False, {
            "kind": "completed", "label": "완료", "tone": "ok", "title": "",
            "link_label": "", "link_endpoint": "", "link_params": {},
        }),
        ("AS_COMPLETED", _sd("AS_COMPLETED"), False, {
            "kind": "completed", "label": "완료", "tone": "ok", "title": "",
            "link_label": "", "link_endpoint": "", "link_params": {},
        }),
        ("AS", _sd("AS"), False, {
            "kind": "as", "label": "할 일", "tone": "warn", "title": "AS 확인",
            "link_label": "AS 화면 열기", "link_endpoint": "erp_as_page.erp_as_dashboard",
            "link_params": {"focus_order": 7},
        }),
        ("AS_RECEIVED", _sd("AS_RECEIVED"), False, {
            "kind": "as", "label": "할 일", "tone": "warn", "title": "AS 확인",
            "link_label": "AS 화면 열기", "link_endpoint": "erp_as_page.erp_as_dashboard",
            "link_params": {"focus_order": 7},
        }),
    ],
)
def test_board_state_table(stage_code, sd, has_run, expected):
    state = build_board_state(_O(7), sd, stage_code, has_current_run=has_run)
    assert set(state) == _KEYS
    assert state == expected


# ② 음성 대조군
@pytest.mark.parametrize("stage_code", ["RECEIVED", "MEASURE", "DRAWING", "CONFIRM", "CS", "UNKNOWN", ""])
def test_board_state_none_for_other_stages(stage_code):
    assert build_board_state(_O(7), _sd(stage_code), stage_code, has_current_run=True) is None


@pytest.mark.parametrize(
    "quest, expected",
    [
        ({"status": "OPEN"}, None),
        ({"status": "OPEN", "is_synthesized": True}, "제작대기"),
        ({"status": "COMPLETED", "is_done": True}, "제작대기"),
        (None, "제작대기"),
    ],
)
def test_production_board_state_yields_to_stored_open_quest(quest, expected):
    state = build_board_state(_O(7), _sd("PRODUCTION"), "PRODUCTION", current_quest=quest)
    assert (state and state["label"]) == expected


@pytest.mark.parametrize("stage", ["PRODUCTION", "생산"])
@pytest.mark.parametrize("has_run", [True, False])
def test_production_label_matches_board_rule(stage, has_run):
    assert _kpi_stage_label_from_erp_stage(stage, has_run) == _production_stage_label_from_stage(stage, has_run)


def test_construction_stage_skips_malformed_history():
    sd = _sd("CONSTRUCTION", ["시공 시작", None, {"note": "시공 시작"}])
    assert board_state_display.construction_display_stage(_O(7), sd) == "시공중"
    assert board_state_display.construction_display_stage(_O(7), {"workflow": "CONSTRUCTION"}) is None


# ③ 위치 고정 계약
def test_construction_stage_rule_lives_in_board_state_module():
    assert (
        construction_dashboard_display._display_stage_for_order
        is board_state_display.construction_display_stage
    )


# ④ 생산 run id 모아 읽기
def test_production_run_ids_zero_queries_without_production_orders(app):
    with app.app_context():
        orders = [_make_order("CONSTRUCTION"), _make_order("COMPLETED"), _make_order("AS")]
        sds = {o.id: dict(o.structured_data) for o in orders}
        result, n = _count_queries(lambda: production_run_ids_for(db_session, orders, sds))
        assert result == set()
        assert n == 0


def test_production_run_ids_one_query_current_only(app):
    with app.app_context():
        a, b, c = (_make_order("PRODUCTION") for _ in range(3))
        _mint_run(a.id)
        _mint_run(b.id, status="SUPERSEDED", is_current=False)
        other = _make_order("CONSTRUCTION")
        orders = [a, b, c, other]
        sds = {o.id: dict(o.structured_data) for o in orders}
        result, n = _count_queries(lambda: production_run_ids_for(db_session, orders, sds))
        assert result == {a.id}
        assert n == 1


# ⑤ PC 행 DTO
def test_orders_row_dto_carries_board_state_and_keeps_current_quest(app):
    with app.app_context():
        order = _make_order("PRODUCTION")
        sds = {order.id: dict(order.structured_data)}
        rows = build_orders_row_dtos(
            [order], sds, {}, {}, None, production_run_ids={order.id}
        )
        row = rows[0]
        assert row["board_state"]["kind"] == "production"
        assert row["board_state"]["label"] == "제작중"
        assert "current_quest" in row
        assert row["current_quest"] is not None

        rows = build_orders_row_dtos([order], sds, {}, {}, None)
        assert rows[0]["board_state"]["label"] == "제작대기"


# ⑥ 휴대폰 상세 행
def test_mobile_detail_row_shows_in_production_label(app):
    with app.app_context():
        user = User(
            username="board_state_mobile",
            password=generate_password_hash("pw"),
            role="ADMIN",
            team="PRODUCTION",
            name="보드 관리자",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        order = _make_order("PRODUCTION")
        _mint_run(order.id)
        order_id = order.id

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
            sess["username"] = user.username
            sess["role"] = user.role

        captured: list[dict] = []

        def _capture(sender, template, context, **extra):
            if template.name == "orders/mobile_order_detail.html":
                captured.append(context["order"])

        template_rendered.connect(_capture, app)
        try:
            resp = client.get(f"/erp/orders/{order_id}/mobile")
        finally:
            template_rendered.disconnect(_capture, app)

        assert resp.status_code == 200
        assert captured, "mobile_order_detail.html was not rendered"
        assert captured[0]["board_state"]["label"] == "제작중"
        assert captured[0]["current_quest"] is not None


def test_orders_dashboard_reports_board_phases(app):
    with app.app_context():
        user = User(
            username="board_state_phases",
            password=generate_password_hash("pw"),
            role="ADMIN",
            team="CS",
            name="구간 관리자",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        _mint_run(_make_order("PRODUCTION").id)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
            sess["username"] = user.username
            sess["role"] = user.role

        resp = client.get("/erp/dashboard")
        assert resp.status_code == 200
        phases = resp.headers.get("X-FOMS-EPT-B7-PHASES", "")
        assert "board_run_ids" in phases
        assert "row_dtos" in phases


def test_orders_dashboard_board_rows_no_n_plus_one(app, monkeypatch):
    """생산(run 있음·없음)·시공·완료·AS 섞인 줄을 4→12건으로 늘려도 쿼리 수가 같다."""
    from foms.services.common import dashboard_cache as dc

    monkeypatch.delenv("REDIS_URL", raising=False)
    mix = ("PRODUCTION", "PRODUCTION", "CONSTRUCTION", "COMPLETED", "AS_RECEIVED", "PRODUCTION")

    def seed(n: int) -> None:
        for i in range(n):
            order = _make_order(mix[i % len(mix)])
            if i % 3 == 0:
                _mint_run(order.id)

    def fetch(client):
        dc.reset_dashboard_cache_runtime_for_tests()
        return client.get("/erp/dashboard?view=fragment", headers={"X-FOMS-ERP-SHELL": "1"})

    with app.app_context():
        user = User(
            username="board_state_nplus1",
            password=generate_password_hash("pw"),
            role="ADMIN",
            team="CS",
            name="예산 관리자",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
            sess["username"] = user.username
            sess["role"] = user.role

        seed(4)
        fetch(client)
        resp_small, q_small = _count_queries(lambda: fetch(client))
        seed(8)
        resp_big, q_big = _count_queries(lambda: fetch(client))
        dc.reset_dashboard_cache_runtime_for_tests()

    assert resp_small.status_code == 200 and resp_big.status_code == 200
    assert "생산 보드 열기" in resp_big.get_data(as_text=True)
    assert q_big - q_small == 0, (q_small, q_big)
    assert q_big <= 12, q_big
