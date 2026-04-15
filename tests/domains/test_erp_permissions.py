from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from flask import Flask, session, template_rendered
from sqlalchemy import or_
from sqlalchemy.dialects import postgresql
from werkzeug.security import generate_password_hash

import foms.services.erp_permissions as erp_permissions
from db import db_session
from models import Order, User


def test_can_edit_erp_allows_admin_and_sales_teams() -> None:
    assert erp_permissions.can_edit_erp(SimpleNamespace(role="ADMIN", team="WHATEVER"))
    assert erp_permissions.can_edit_erp(SimpleNamespace(role="USER", team="CS"))
    assert erp_permissions.can_edit_erp(SimpleNamespace(role="USER", team="SALES"))
    assert not erp_permissions.can_edit_erp(SimpleNamespace(role="USER", team="CONSTRUCTION"))


def test_build_mine_sql_filter_escapes_like_pattern_and_adds_all_condition_groups() -> None:
    user = SimpleNamespace(id=7, name="홍%_길", username="hong")

    conds = erp_permissions.build_mine_sql_filter(user)

    assert len(conds) == 12
    compiled = str(
        conds[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "\\%" in compiled
    assert "\\_" in compiled


def test_build_mine_sql_filter_skips_duplicate_username_match_group() -> None:
    user = SimpleNamespace(id=None, name="same", username="same")

    conds = erp_permissions.build_mine_sql_filter(user)

    assert len(conds) == 5


def test_erp_edit_required_returns_401_when_user_lookup_fails(monkeypatch) -> None:
    app = Flask(__name__)
    app.secret_key = "test-secret"
    monkeypatch.setattr(erp_permissions, "get_user_by_id", lambda _user_id: None)

    @erp_permissions.erp_edit_required
    def protected_endpoint():
        return {"success": True}, 200

    with app.test_request_context("/erp/edit"):
        session["user_id"] = 1
        response, status = protected_endpoint()

    assert status == 401
    assert response.get_json() == {"success": False, "message": "로그인이 필요합니다."}


def test_erp_construction_edit_required_allows_construction_team(monkeypatch) -> None:
    app = Flask(__name__)
    app.secret_key = "test-secret"
    user = SimpleNamespace(role="USER", team="CONSTRUCTION")
    monkeypatch.setattr(erp_permissions, "get_user_by_id", lambda _user_id: user)

    @erp_permissions.erp_construction_edit_required
    def protected_endpoint():
        return {"success": True}, 200

    with app.test_request_context("/erp/construction"):
        session["user_id"] = 1
        payload, status = protected_endpoint()

    assert status == 200
    assert payload == {"success": True}


@contextmanager
def _captured_templates(app: Flask):
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append((template, context))

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)


def test_build_mine_sql_filter_matches_sqlite_json_worker_names(app) -> None:
    user = User(
        username="worker1",
        password=generate_password_hash("pw"),
        name="시공1",
        role="USER",
        team="CONSTRUCTION",
    )
    mine_order = Order(
        received_date="2026-04-11",
        customer_name="내 작업",
        phone="010-1111-1111",
        address="서울시 송파구 올림픽로 1",
        product="주방장",
        status="IN_CONSTRUCTION",
        is_erp_beta=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": "내 작업"}, "manager": {"name": "망고"}},
            "shipment": {"construction_workers": ["시공1"]},
        },
    )
    other_order = Order(
        received_date="2026-04-11",
        customer_name="다른 작업",
        phone="010-2222-2222",
        address="서울시 송파구 올림픽로 2",
        product="주방장",
        status="IN_CONSTRUCTION",
        is_erp_beta=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": "다른 작업"}, "manager": {"name": "망고"}},
            "shipment": {"construction_workers": ["다른시공"]},
        },
    )
    db_session.add_all([user, mine_order, other_order])
    db_session.commit()

    conds = erp_permissions.build_mine_sql_filter(user)
    rows = (
        db_session.query(Order.id)
        .filter(Order.id.in_([mine_order.id, other_order.id]))
        .filter(or_(*conds))
        .order_by(Order.id)
        .all()
    )

    assert [row.id for row in rows] == [mine_order.id]


def test_construction_dashboard_applies_mine_filter_for_construction_team(app, client) -> None:
    user = User(
        username="worker1",
        password=generate_password_hash("pw"),
        name="시공1",
        role="USER",
        team="CONSTRUCTION",
    )
    mine_order = Order(
        received_date="2026-04-11",
        customer_name="내 작업",
        phone="010-1111-1111",
        address="서울시 송파구 올림픽로 1",
        product="주방장",
        status="IN_CONSTRUCTION",
        is_erp_beta=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": "내 작업"}, "manager": {"name": "망고"}},
            "site": {"address_full": "서울시 송파구 올림픽로 1"},
            "schedule": {"construction": {"date": "2026-04-11"}},
            "shipment": {"construction_workers": ["시공1"]},
        },
    )
    other_order = Order(
        received_date="2026-04-11",
        customer_name="다른 작업",
        phone="010-2222-2222",
        address="서울시 송파구 올림픽로 2",
        product="주방장",
        status="IN_CONSTRUCTION",
        is_erp_beta=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": "다른 작업"}, "manager": {"name": "망고"}},
            "site": {"address_full": "서울시 송파구 올림픽로 2"},
            "schedule": {"construction": {"date": "2026-04-11"}},
            "shipment": {"construction_workers": ["다른시공"]},
        },
    )
    db_session.add_all([user, mine_order, other_order])
    db_session.commit()
    mine_order_id = mine_order.id

    login_response = client.post(
        "/login",
        data={"username": "worker1", "password": "pw"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    with _captured_templates(app) as templates:
        response = client.get("/erp/construction/dashboard", follow_redirects=False)

    assert response.status_code == 200
    assert len(templates) == 1
    _, context = templates[0]
    assert context["erp_mine_only"] is True
    assert context["total_orders"] == 1
    assert [item["id"] for item in context["orders"]] == [mine_order_id]
