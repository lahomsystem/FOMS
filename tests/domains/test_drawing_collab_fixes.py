"""도면 협업 수정 6건 — 백엔드(B) 계약.

- 수령확정 상태 가드(TRANSFERRED 외 400, 전원 적용).
- 전달·전달취소 알림(→ 담당 영업 본인만, 이름 불일치면 영업팀 폴백 + fan_out).
- 수정요청취소 알림(DRAWING_REVISION_CANCELLED → 도면팀 + fan_out).
- Blueprint V3 죽은 라우트 404.
- 워크벤치 include_confirmed 필터 + no_assignee 플래그.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

import foms.web.drawing.workbench as wb
from db import db_session
from models import Notification, NotificationUserState, Order, User


def _make_user(username, *, role="ADMIN", team=None, name=None):
    user = User(
        username=username,
        password=generate_password_hash("pass"),
        role=role,
        team=team,
        name=name or username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(*, sd, status="DRAWING", manager_name="담당", stage_code="DRAWING", customer="고객"):
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name=customer,
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name=manager_name,
        is_erp_order=True,
        structured_data=sd,
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


# --- 수령확정 상태 가드 ------------------------------------------------------


def test_confirm_receipt_blocked_when_not_transferred(client):
    admin = _make_user("recv_admin1", role="ADMIN")
    _login(client, admin)
    order = _make_order(sd={
        "parties": {"customer": {"name": "고객"}, "manager": {"name": "담당"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "RETURNED",
    })
    res = client.post(f"/api/orders/{order.id}/confirm-drawing-receipt")
    assert res.status_code == 400
    assert "전달된 도면" in res.get_json()["message"]
    # 상태 정합성 가드는 ADMIN 도 통과 못함 → drawing_status 불변.
    saved = db_session.get(Order, order.id)
    assert saved.structured_data["drawing_status"] == "RETURNED"
    # 가드에 막히면 단계 전이도 없다(엔진 경유 전후 동일).
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"


def test_confirm_receipt_allowed_when_transferred(client):
    admin = _make_user("recv_admin2", role="ADMIN")
    _login(client, admin)
    order = _make_order(sd={
        "parties": {"customer": {"name": "고객"}, "manager": {"name": "담당"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "TRANSFERRED",
        "drawing_current_files": [],
        "drawing_transfer_history": [{"action": "TRANSFER", "files": []}],
    })
    oid = order.id
    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt")
    assert res.status_code == 200
    assert res.get_json()["success"] is True
    assert res.get_json()["stage_moved"] is True
    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["drawing_status"] == "CONFIRMED"
    # 단계 전이는 STATE-CORE 엔진이 한다 — workflow.stage 와 색인 미러가 함께 움직인다.
    assert saved.structured_data["workflow"]["stage"] == "CONFIRM"
    assert saved.erp_stage_code == "CONFIRM"


# --- 전달취소 알림 (Alert A) -------------------------------------------------


def _transferred_order(manager_name):
    return _make_order(
        manager_name=manager_name,
        sd={
            "parties": {"customer": {"name": "홍길동"}, "manager": {"name": manager_name}},
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "TRANSFERRED",
            "drawing_current_files": [],
            "drawing_transfer_history": [
                {"action": "TRANSFER", "mode": "APPEND", "files": [], "previous_current_files": []},
            ],
        },
    )


def _state_user_ids(notif_id):
    return {
        uid
        for (uid,) in db_session.query(NotificationUserState.user_id).filter(
            NotificationUserState.notification_id == notif_id
        )
    }


def test_cancel_transfer_notifies_owner_sales_only(client):
    """담당 영업 본인만 받는다 — 같은 팀 다른 영업에게 퍼지지 않는다."""
    admin = _make_user("ct_admin1", role="ADMIN")
    owner = _make_user("ct_owner", role="STAFF", team="SALES", name="영업김")
    other = _make_user("ct_sales", role="STAFF", team="SALES", name="영업원")
    owner_id, other_id = owner.id, other.id
    _login(client, admin)
    order = _transferred_order("영업김")  # 라홈/하우드 아님 → 담당 영업
    oid = order.id

    res = client.post(f"/api/orders/{oid}/cancel-transfer")
    assert res.status_code == 200 and res.get_json()["success"] is True

    notifs = (
        db_session.query(Notification)
        .filter(Notification.order_id == oid, Notification.notification_type == "DRAWING_TRANSFER_CANCELLED")
        .all()
    )
    assert len(notifs) == 1
    n = notifs[0]
    assert n.target_team is None
    assert n.target_manager_name == "영업김"
    recipients = _state_user_ids(n.id)
    assert owner_id in recipients
    assert other_id not in recipients


def test_cancel_transfer_falls_back_to_sales_team_when_owner_unknown(client):
    """담당자 이름이 활성 사용자와 안 맞으면 알림이 사라지지 않게 영업팀 전체로."""
    admin = _make_user("ct_admin3", role="ADMIN")
    sales = _make_user("ct_sales3", role="STAFF", team="SALES", name="영업원3")
    sales_id = sales.id
    _login(client, admin)
    order = _transferred_order("퇴사한영업")
    oid = order.id

    res = client.post(f"/api/orders/{oid}/cancel-transfer")
    assert res.status_code == 200 and res.get_json()["success"] is True

    n = (
        db_session.query(Notification)
        .filter(Notification.order_id == oid, Notification.notification_type == "DRAWING_TRANSFER_CANCELLED")
        .one()
    )
    assert n.target_team == "SALES"
    assert n.target_manager_name is None
    assert sales_id in _state_user_ids(n.id)


def test_transfer_notifies_owner_sales_only(client):
    """도면 전달 알림도 담당 영업 본인만 받는다."""
    admin = _make_user("tr_admin", role="ADMIN")
    owner = _make_user("tr_owner", role="STAFF", team="SALES", name="영업박")
    other = _make_user("tr_sales", role="STAFF", team="SALES", name="영업최")
    owner_id, other_id = owner.id, other.id
    _login(client, admin)
    order = _make_order(
        manager_name="영업박",
        sd={
            "parties": {"customer": {"name": "홍길동"}, "manager": {"name": "영업박"}},
            "workflow": {"stage": "DRAWING"},
            "assignments": {"drawing_assignee_user_ids": [admin.id]},
        },
    )
    oid = order.id

    res = client.post(
        f"/api/orders/{oid}/transfer-drawing",
        json={"note": "", "mode": "APPEND",
              "files": [{"key": f"orders/{oid}/drawing_gateway/revisions/a.png", "filename": "a.png"}]},
    )
    assert res.status_code == 200, res.get_json()

    n = (
        db_session.query(Notification)
        .filter(Notification.order_id == oid, Notification.notification_type == "DRAWING_TRANSFERRED")
        .one()
    )
    assert n.target_team is None
    assert n.target_manager_name == "영업박"
    recipients = _state_user_ids(n.id)
    assert owner_id in recipients
    assert other_id not in recipients


def test_cancel_transfer_routes_cs_for_lahom_manager(client):
    admin = _make_user("ct_admin2", role="ADMIN")
    _login(client, admin)
    order = _transferred_order("라홈매니저")  # '라홈' 포함 → CS
    oid = order.id
    res = client.post(f"/api/orders/{oid}/cancel-transfer")
    assert res.status_code == 200
    n = (
        db_session.query(Notification)
        .filter(Notification.order_id == oid, Notification.notification_type == "DRAWING_TRANSFER_CANCELLED")
        .one()
    )
    assert n.target_team == "CS"
    assert n.target_manager_name is None


# --- 수정요청취소 알림 (Alert B) ---------------------------------------------


def test_cancel_revision_notifies_drawing_team(client):
    sales = _make_user("cr_sales", role="MANAGER", team="SALES", name="영업담당")
    drawer = _make_user("cr_drawer", role="STAFF", team="DRAWING", name="도면원")
    drawer_id = drawer.id
    _login(client, sales)
    order = _make_order(
        manager_name="영업담당",
        sd={
            "parties": {"customer": {"name": "홍길동"}, "manager": {"name": "영업담당"}},
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "RETURNED",
            "drawing_current_files": [],
            "drawing_transfer_history": [
                {"action": "TRANSFER", "mode": "APPEND", "files": []},
                {"action": "REQUEST_REVISION", "files": []},
            ],
        },
    )
    oid = order.id
    res = client.post(f"/api/orders/{oid}/cancel-revision-request")
    assert res.status_code == 200 and res.get_json()["success"] is True

    n = (
        db_session.query(Notification)
        .filter(Notification.order_id == oid, Notification.notification_type == "DRAWING_REVISION_CANCELLED")
        .one()
    )
    assert n.target_team == "DRAWING"
    states = db_session.query(NotificationUserState).filter(
        NotificationUserState.notification_id == n.id, NotificationUserState.user_id == drawer_id
    ).all()
    assert len(states) == 1


# --- 죽은 라우트 404 ---------------------------------------------------------


def test_dead_blueprint_v3_routes_are_404(client):
    admin = _make_user("dead_admin", role="ADMIN")
    _login(client, admin)
    assert client.post("/api/orders/1/drawing/request-revision", json={}).status_code == 404
    assert client.post("/api/orders/1/drawing/complete-revision", json={}).status_code == 404


# --- 워크벤치 include_confirmed + no_assignee -------------------------------


def _get_workbench_rows(client, monkeypatch, query=""):
    captured = {}

    def _fake_render(template_name, **ctx):
        captured["rows"] = ctx.get("rows")
        return ""

    monkeypatch.setattr(wb, "render_template", _fake_render)
    res = client.get("/erp/drawing-workbench" + query)
    assert res.status_code == 200
    return captured["rows"]


def test_workbench_include_confirmed_toggle(client, monkeypatch):
    admin = _make_user("wb_admin1", role="ADMIN")
    _login(client, admin)
    confirmed = _make_order(
        status="CONFIRM", stage_code="CONFIRM", customer="컨펌고객UNIQ",
        sd={
            "parties": {"customer": {"name": "컨펌고객UNIQ"}, "manager": {"name": "담당"}},
            "workflow": {"stage": "CONFIRM"},
            "drawing_status": "CONFIRMED",
        },
    )
    cid = confirmed.id

    # 기본: 컨펌 주문 제외.
    rows = _get_workbench_rows(client, monkeypatch)
    assert all(r["id"] != cid for r in rows)
    # include_confirmed=1: 컨펌 주문 포함.
    rows = _get_workbench_rows(client, monkeypatch, "?include_confirmed=1")
    assert any(r["id"] == cid for r in rows)


def test_workbench_no_assignee_flag(client, monkeypatch):
    admin = _make_user("wb_admin2", role="ADMIN")
    _login(client, admin)
    # 담당 미지정(DRAWING assignee 0명) DRAWING 단계 주문.
    order = _make_order(
        customer="미지정고객UNIQ",
        sd={
            "parties": {"customer": {"name": "미지정고객UNIQ"}, "manager": {"name": "담당"}},
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "PENDING",
            "assignments": {},
        },
    )
    oid = order.id
    rows = _get_workbench_rows(client, monkeypatch)
    row = next(r for r in rows if r["id"] == oid)
    assert row["no_assignee"] is True
