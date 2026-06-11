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
        is_erp_order=True,
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
        is_erp_order=True,
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


def test_build_mine_sql_filter_scope_construction_excludes_manager_only(app) -> None:
    """시공 scope는 시공 작업자만 — manager로만 잡힌 건은 제외(역할-정확)."""
    user = User(
        username="cons_scope",
        password=generate_password_hash("pw"),
        name="시공담당고유",
        role="USER",
        team="CONSTRUCTION",
    )
    worker_order = Order(  # 시공 작업자 = 본인 → 포함
        received_date="2026-04-12",
        customer_name="시공내건",
        phone="010-3333-3333",
        address="서울시 송파구 3",
        product="주방장",
        status="IN_CONSTRUCTION",
        is_erp_order=True,
        structured_data={"shipment": {"construction_workers": ["시공담당고유"]},
                         "parties": {"manager": {"name": "다른매니저"}}},
    )
    manager_only_order = Order(  # manager만 본인, 시공 작업자 타인 → 시공 scope 제외
        received_date="2026-04-12",
        customer_name="관리만내건",
        phone="010-4444-4444",
        address="서울시 송파구 4",
        product="주방장",
        status="IN_CONSTRUCTION",
        is_erp_order=True,
        manager_name="시공담당고유",
        structured_data={"shipment": {"construction_workers": ["타인시공"]}},
    )
    db_session.add_all([user, worker_order, manager_only_order])
    db_session.commit()

    conds = erp_permissions.build_mine_sql_filter(user, scope="construction")
    ids = {
        row.id
        for row in db_session.query(Order.id)
        .filter(Order.id.in_([worker_order.id, manager_only_order.id]))
        .filter(or_(*conds))
        .all()
    }
    assert worker_order.id in ids
    assert manager_only_order.id not in ids  # manager로만 잡힌 건은 시공 scope에서 제외


def test_build_mine_sql_filter_scope_sales_excludes_worker_only(app) -> None:
    """영업 scope는 manager/sales_assignee만 — 시공 작업자로만 잡힌 건은 제외."""
    user = User(
        username="sales_scope",
        password=generate_password_hash("pw"),
        name="영업담당고유",
        role="USER",
        team="SALES",
    )
    manager_order = Order(  # manager = 본인 → 영업 scope 포함
        received_date="2026-04-12",
        customer_name="영업내건",
        phone="010-5555-5555",
        address="서울시 송파구 5",
        product="주방장",
        status="MEASURE",
        is_erp_order=True,
        manager_name="영업담당고유",
        structured_data={},
    )
    worker_only_order = Order(  # 시공 작업자만 본인, manager 타인 → 영업 scope 제외
        received_date="2026-04-12",
        customer_name="시공만내건",
        phone="010-6666-6666",
        address="서울시 송파구 6",
        product="주방장",
        status="MEASURE",
        is_erp_order=True,
        manager_name="딴사람",
        structured_data={"shipment": {"construction_workers": ["영업담당고유"]}},
    )
    db_session.add_all([user, manager_order, worker_only_order])
    db_session.commit()

    conds = erp_permissions.build_mine_sql_filter(user, scope="sales")
    ids = {
        row.id
        for row in db_session.query(Order.id)
        .filter(Order.id.in_([manager_order.id, worker_only_order.id]))
        .filter(or_(*conds))
        .all()
    }
    assert manager_order.id in ids
    assert worker_only_order.id not in ids  # 시공 작업자로만 잡힌 건은 영업 scope에서 제외


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
        is_erp_order=True,
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
        is_erp_order=True,
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
