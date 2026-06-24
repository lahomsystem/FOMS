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

    assert len(conds) == 14
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

    assert len(conds) == 6


def test_resolve_mine_scope_for_user_uses_team_role() -> None:
    assert (
        erp_permissions.resolve_mine_scope_for_user(
            SimpleNamespace(role="ADMIN", team="DRAWING")
        )
        == "all"
    )
    assert erp_permissions.resolve_mine_scope_for_user(SimpleNamespace(team="DRAWING")) == "drawing"
    assert erp_permissions.resolve_mine_scope_for_user(SimpleNamespace(team="SALES")) == "sales"
    assert erp_permissions.resolve_mine_scope_for_user(SimpleNamespace(team="MEASURE")) == "sales"
    assert erp_permissions.resolve_mine_scope_for_user(SimpleNamespace(team="CONSTRUCTION")) == "construction"
    assert erp_permissions.resolve_mine_scope_for_user(SimpleNamespace(team=None)) == "all"


def test_is_order_related_to_user_uses_exact_role_assignments() -> None:
    user = SimpleNamespace(id=41, name="이시영", username="leeshiyoung", team="DRAWING")
    order = SimpleNamespace(
        manager_name="다른 영업",
        structured_data={
            "parties": {"manager": {"name": "다른 영업"}},
            "workflow": {"current_quest": {"owner_person": "다른 담당"}},
            "assignments": {
                "sales_assignee_user_ids": [77],
                "drawing_assignee_user_ids": [41],
            },
            "drawing_assignees": [{"user_id": 41, "name": "이시영"}],
            "shipment": {"construction_workers": ["다른 시공"]},
        },
    )

    assert erp_permissions.is_order_related_to_user(order, user, scope="drawing")
    assert not erp_permissions.is_order_related_to_user(order, user, scope="sales")
    assert not erp_permissions.is_order_related_to_user(order, user, scope="construction")


def test_is_order_related_to_user_supports_legacy_drawing_assignee_id() -> None:
    user = SimpleNamespace(id=41, name="변경된 이름", username="leeshiyoung", team="DRAWING")
    order = SimpleNamespace(
        manager_name="다른 영업",
        structured_data={
            "assignments": {},
            "drawing_assignees": [{"id": 41, "name": "이전 이름"}],
        },
    )

    assert erp_permissions.is_order_related_to_user(order, user, scope="drawing")


def test_is_order_related_to_user_does_not_use_admin_permission_as_ownership() -> None:
    admin = SimpleNamespace(id=5, name="이시영", username="admin", role="ADMIN", team=None)
    unrelated = SimpleNamespace(
        manager_name="안종훈",
        structured_data={
            "parties": {"manager": {"name": "안종훈"}},
            "workflow": {"current_quest": {"owner_person": "최상용"}},
            "assignments": {
                "sales_assignee_user_ids": [7],
                "drawing_assignee_user_ids": [8],
            },
            "drawing_assignees": [{"user_id": 8, "name": "최상용"}],
            "shipment": {"construction_workers": ["김시공"]},
        },
    )

    assert not erp_permissions.is_order_related_to_user(unrelated, admin)


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


def test_build_mine_sql_filter_scope_construction_owner_and_worker_not_other_roles(app) -> None:
    """시공 scope = 소유자(manager)+시공 작업자. 도면 배정으로만 잡힌 건은 제외(scope 좁힘)."""
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
        manager_name="다른매니저",
        structured_data={"shipment": {"construction_workers": ["시공담당고유"]}},
    )
    manager_order = Order(  # 소유자(manager) = 본인 → 포함 (시공팀은 manager로 배정됨)
        received_date="2026-04-12",
        customer_name="관리내건",
        phone="010-4444-4444",
        address="서울시 송파구 4",
        product="주방장",
        status="IN_CONSTRUCTION",
        is_erp_order=True,
        manager_name="시공담당고유",
        structured_data={"shipment": {"construction_workers": ["타인시공"]}},
    )
    drawing_only_order = Order(  # 도면 배정으로만 잡힘 → 시공 scope 제외
        received_date="2026-04-12",
        customer_name="도면만내건",
        phone="010-7777-7777",
        address="서울시 송파구 7",
        product="주방장",
        status="IN_CONSTRUCTION",
        is_erp_order=True,
        manager_name="딴사람",
        structured_data={"assignments": {"drawing_assignees": ["시공담당고유"]}},
    )
    db_session.add_all([user, worker_order, manager_order, drawing_only_order])
    db_session.commit()

    conds = erp_permissions.build_mine_sql_filter(user, scope="construction")
    ids = {
        row.id
        for row in db_session.query(Order.id)
        .filter(Order.id.in_([worker_order.id, manager_order.id, drawing_only_order.id]))
        .filter(or_(*conds))
        .all()
    }
    assert worker_order.id in ids  # 시공 작업자
    assert manager_order.id in ids  # 소유자(manager) — 시공팀 배정 방식
    assert drawing_only_order.id not in ids  # 도면 배정만으론 시공 scope 제외


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


def _login_construction_user(client, *, username="worker1", name="시공1"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        name=name,
        role="USER",
        team="CONSTRUCTION",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    login_response = client.post(
        "/login",
        data={"username": username, "password": "pw"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    return user


def test_construction_team_can_access_history_without_redirect(client) -> None:
    _login_construction_user(client)

    response = client.get("/erp/history/", follow_redirects=False)

    assert response.status_code == 200
    assert "/erp/shipment" not in (response.headers.get("Location") or "")


def test_history_applies_mine_filter_for_construction_team(app, client) -> None:
    user = _login_construction_user(client, username="hist_worker", name="시공이력")
    mine_order = Order(
        received_date="2026-04-11",
        customer_name="내 시공 이력",
        phone="010-1111-1111",
        address="서울",
        product="주방장",
        status="COMPLETED",
        is_erp_order=True,
        structured_data={
            "shipment": {"construction_workers": ["시공이력"]},
            "parties": {"customer": {"name": "내 시공 이력"}},
        },
    )
    other_order = Order(
        received_date="2026-04-11",
        customer_name="다른 사람 이력",
        phone="010-2222-2222",
        address="부산",
        product="주방장",
        status="COMPLETED",
        is_erp_order=True,
        structured_data={
            "shipment": {"construction_workers": ["다른시공"]},
            "parties": {"customer": {"name": "다른 사람 이력"}},
        },
    )
    db_session.add_all([mine_order, other_order])
    db_session.commit()
    mine_order_id = mine_order.id
    other_order_id = other_order.id

    with _captured_templates(app) as templates:
        response = client.get("/erp/history/", follow_redirects=False)

    assert response.status_code == 200
    assert len(templates) == 1
    _, context = templates[0]
    assert context["auto_browse_mine"] is True
    assert context["is_construction_team"] is True
    order_ids = [item["_order"].id for item in context["orders"]]
    assert mine_order_id in order_ids
    assert other_order_id not in order_ids


def test_completion_api_returns_only_mine_orders_for_construction_team(client) -> None:
    _login_construction_user(client, username="comp_worker", name="시공완료")
    mine_order = Order(
        received_date="2026-04-11",
        customer_name="내 완료",
        phone="010-3333-3333",
        address="서울",
        product="주방장",
        status="COMPLETED",
        is_erp_order=True,
        structured_data={
            "shipment": {"construction_workers": ["시공완료"]},
            "parties": {"customer": {"name": "내 완료"}},
        },
    )
    other_order = Order(
        received_date="2026-04-11",
        customer_name="남의 완료",
        phone="010-4444-4444",
        address="부산",
        product="주방장",
        status="COMPLETED",
        is_erp_order=True,
        structured_data={
            "shipment": {"construction_workers": ["다른시공"]},
            "parties": {"customer": {"name": "남의 완료"}},
        },
    )
    db_session.add_all([mine_order, other_order])
    db_session.commit()
    mine_order_id = mine_order.id
    other_order_id = other_order.id

    response = client.get("/api/orders/completion")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    ids = {row["id"] for row in payload["orders"]}
    assert mine_order_id in ids
    assert other_order_id not in ids


def test_settlement_issue_forbidden_for_construction_team(client) -> None:
    _login_construction_user(client, username="settle_worker", name="시공정산")
    order = Order(
        received_date="2026-04-11",
        customer_name="완료건",
        phone="010-5555-5555",
        address="서울",
        product="주방장",
        status="COMPLETED",
        is_erp_order=True,
        structured_data={"shipment": {"construction_workers": ["시공정산"]}},
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        f"/api/orders/{order.id}/settlement/issue",
        json={"department": "CONSTRUCTION", "amount": 10000, "reason": "테스트"},
    )
    payload = response.get_json()

    assert response.status_code == 403
    assert payload["success"] is False


def test_construction_team_mobile_bottom_nav_shows_four_tabs_only(client, monkeypatch) -> None:
    import re

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_construction_user(client, username="nav_worker", name="시공네비")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    response = client.get("/erp/completion")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    nav_match = re.search(r'<nav class="erp-mobile-bottom-nav".*?</nav>', body, re.S)
    assert nav_match, "bottom nav markup missing"
    nav_html = nav_match.group(0)
    assert 'data-bs-target="#erp-mobile-menu-drawer"' not in nav_html
    assert ">계산기</span>" not in nav_html
    assert ">출고</span>" in nav_html
    assert ">시공</span>" in nav_html
    assert ">완료</span>" in nav_html
    assert ">이력</span>" in nav_html
