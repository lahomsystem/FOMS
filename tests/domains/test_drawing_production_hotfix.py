"""생산·시공 단계 도면 — 도면팀 바로 반영 · 사본 지우기 · 생산팀 알림.

설계서 docs/specs/2026-10-27-drawing-team-production-fix_SPEC.md (주문 5690).

- B: 생산·시공 단계에서 지정 도면 담당이 보내면 영업 확인 없이 바로 CONFIRMED(단계 유지).
  도면·고객컨펌 단계는 지금처럼 TRANSFERRED(음성 대조).
- C: 확정 도면이 한 장이고 방식이 없으면 교체, 두 장 이상이면 추가(태블릿 회귀 방지).
- D: 생산팀 활성 계정 전원에게 알림 + 폰 알림, 앞 알림과 합치지 않는다.
- A: 도면팀(담당 아님 포함)이 도면 칸 사본을 지우고 되살린다. 실측 사진·협력사 원본·최종 도면은 안 된다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as drawing_routes
from db import db_session
from foms.services.notifications.production_change import NOTIFICATION_TYPE
from foms.services.orders.confirm_drawing_gate import revision_in_flight_block
from foms.services.production_change_alerts import _build_change_lists
from models import Notification, NotificationUserState, Order, OrderAttachment, OrderEvent, User


@pytest.fixture
def pushes(monkeypatch):
    """폰 알림 줄 넣기를 기록한다(실제 발송 없음). 실시간 알림도 끈다."""
    sent: list[int] = []
    monkeypatch.setattr(drawing_routes, "emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr(
        "foms.services.notifications.realtime_notifications.emit_erp_notification_to_users",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "foms.services.notifications.push_sender.enqueue_push_for_notification",
        lambda notification_id, **k: sent.append(int(notification_id)),
    )
    return sent


def _user(name, *, team, role="STAFF", active=True):
    u = User(username=name, password=generate_password_hash("pw"), role=role, team=team,
             name=f"{name}이름", is_active=active)
    db_session.add(u)
    db_session.commit()
    return SimpleNamespace(id=u.id, username=u.username, role=u.role, name=u.name, team=team)


def _login(client, u):
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role


def _order(drawer_id, sales_id, *, stage="PRODUCTION", status="CONFIRMED", current=1, history=None):
    o = Order(
        received_date="2026-10-01", customer_name="핫픽스고객", phone="010-0000-0000",
        address="Seoul", product="붙박이장", status=stage, manager_name="영업핫픽스",
        is_erp_order=True, erp_stage_code=stage, structured_data={},
    )
    db_session.add(o)
    db_session.commit()
    files = [{"key": f"orders/{o.id}/drawing_gateway/final{i}.png", "filename": f"final{i}.png"}
             for i in range(1, current + 1)]
    o.structured_data = {
        "parties": {"customer": {"name": "핫픽스고객"}, "manager": {"name": "영업핫픽스"}},
        "workflow": {"stage": stage},
        "drawing_status": status,
        "assignments": {"drawing_assignee_user_ids": [drawer_id], "sales_assignee_user_ids": [sales_id]},
        "drawing_current_files": files,
        "drawing_transfer_history": history if history is not None else [
            {"action": "TRANSFER", "by_user_id": drawer_id, "transferred_at": "2026-10-01 00:00:00",
             "files": files},
            {"action": "CONFIRM_RECEIPT", "by_user_id": sales_id, "at": "2026-10-01 01:00:00", "files": files},
        ],
    }
    db_session.commit()
    for f in files:
        db_session.add(OrderAttachment(order_id=o.id, filename=f["filename"], file_type="image",
                                       category="drawing", storage_key=f["key"], user_id=drawer_id,
                                       file_size=1))
    db_session.commit()
    return o.id


def _send(client, oid, name="fix.png", **body):
    payload = {"files": [{"key": f"orders/{oid}/drawing_wizard/exports/{name}", "filename": name}]}
    payload.update(body)
    return client.post(f"/api/orders/{oid}/transfer-drawing", json=payload)


def _sd(oid):
    db_session.expire_all()
    o = db_session.get(Order, oid)
    return o, o.structured_data


def _prod_notifs(oid):
    return (db_session.query(Notification)
            .filter(Notification.order_id == oid, Notification.notification_type == NOTIFICATION_TYPE)
            .order_by(Notification.id).all())


@pytest.fixture
def people():
    return SimpleNamespace(
        drawer=_user("hf_drawer", team="DRAWING"),
        drawer2=_user("hf_drawer2", team="DRAWING"),
        sales=_user("hf_sales", team="SALES"),
        prod1=_user("hf_prod1", team="PRODUCTION"),
        prod2=_user("hf_prod2", team="PRODUCTION"),
        prod_off=_user("hf_prod_off", team="PRODUCTION", active=False),
    )


# --- B·C: 바로 반영 ----------------------------------------------------------


@pytest.mark.parametrize("stage", ["PRODUCTION", "CONSTRUCTION"])
def test_hotfix_confirms_immediately_and_replaces_single(client, people, pushes, stage):
    oid = _order(people.drawer.id, people.sales.id, stage=stage)
    _login(client, people.drawer)
    res = _send(client, oid)
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["hotfix"] is True and "바로 반영" in body["message"]

    order, sd = _sd(oid)
    assert sd["drawing_status"] == "CONFIRMED"
    assert order.erp_stage_code == stage and sd["workflow"]["stage"] == stage
    assert [f["key"].rsplit("/", 1)[-1] for f in sd["drawing_current_files"]] == ["fix.png"]
    last_two = sd["drawing_transfer_history"][-2:]
    assert last_two[0]["action"] == "TRANSFER" and last_two[0]["hotfix"] is True
    assert last_two[1]["action"] == "CONFIRM_RECEIPT"
    assert last_two[1]["auto_confirm"] == "DRAWING_HOTFIX"
    assert [f["key"] for f in last_two[1]["files"]] == [f["key"] for f in sd["drawing_current_files"]]
    assert sd["drawing_confirmed_by"] == people.drawer.name
    assert revision_in_flight_block(sd) is None  # 생산 [제작 시작] 도면 게이트 통과

    event = (db_session.query(OrderEvent)
             .filter(OrderEvent.order_id == oid, OrderEvent.event_type == "DRAWING_STATUS_CHANGED")
             .order_by(OrderEvent.id.desc()).first())
    assert event is not None and event.payload["after"] == "CONFIRMED"
    assert event.payload["auto_confirm"] == "DRAWING_HOTFIX"

    sales_notif = (db_session.query(Notification)
                   .filter(Notification.order_id == oid, Notification.notification_type == "DRAWING_TRANSFERRED")
                   .one())
    assert sales_notif.title == "도면 바로 반영됨"


def test_hotfix_cannot_be_cancelled_by_cancel_transfer(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id)
    _login(client, people.drawer)
    assert _send(client, oid).status_code == 200
    res = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    assert res.status_code == 400
    _order_row, sd = _sd(oid)
    assert sd["drawing_status"] == "CONFIRMED"


@pytest.mark.parametrize("stage", ["DRAWING", "CONFIRM"])
def test_negative_control_drawing_and_confirm_stage_keep_sales_confirm(client, people, pushes, stage):
    oid = _order(people.drawer.id, people.sales.id, stage=stage)
    _login(client, people.drawer)
    res = _send(client, oid)
    assert res.status_code == 200, res.get_json()
    assert not res.get_json().get("hotfix")
    _order_row, sd = _sd(oid)
    assert sd["drawing_status"] == "TRANSFERRED"
    assert sd["drawing_transfer_history"][-1]["action"] == "TRANSFER"
    assert "hotfix" not in sd["drawing_transfer_history"][-1]


def test_two_current_drawings_without_mode_append(client, people, pushes):
    """태블릿 시트 전달은 방식을 고르지 않는다 — 어느 장인지 모르면 400 대신 지금처럼 더한다."""
    oid = _order(people.drawer.id, people.sales.id, current=2)
    _login(client, people.drawer)
    assert _send(client, oid).status_code == 200
    _order_row, sd = _sd(oid)
    names = [f["key"].rsplit("/", 1)[-1] for f in sd["drawing_current_files"]]
    assert names == ["final1.png", "final2.png", "fix.png"]
    assert sd["drawing_status"] == "CONFIRMED"


def test_explicit_append_keeps_old_drawing(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id)
    _login(client, people.drawer)
    assert _send(client, oid, mode="APPEND").status_code == 200
    _order_row, sd = _sd(oid)
    assert [f["key"].rsplit("/", 1)[-1] for f in sd["drawing_current_files"]] == ["final1.png", "fix.png"]


def test_returned_with_unchecked_request_still_blocked(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id, status="RETURNED")
    o = db_session.get(Order, oid)
    sd = dict(o.structured_data)
    sd["drawing_transfer_history"] = list(sd["drawing_transfer_history"]) + [
        {"action": "REQUEST_REVISION", "by_user_id": people.sales.id, "at": "2026-10-02 00:00:00",
         "note": "치수 수정", "files": []},
    ]
    o.structured_data = sd
    db_session.commit()
    _login(client, people.drawer)
    res = _send(client, oid)
    assert res.status_code == 400
    assert "반영 완료" in res.get_json()["message"]


def test_non_assignee_drawer_cannot_send(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id)
    _login(client, people.drawer2)
    assert _send(client, oid).status_code == 403


# --- D: 생산팀 알림 ----------------------------------------------------------


def test_production_team_all_active_members_notified_with_push(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id)
    _login(client, people.drawer)
    assert _send(client, oid).status_code == 200

    notifs = _prod_notifs(oid)
    prod = [n for n in notifs if n.target_team == "PRODUCTION"]
    assert len(prod) == 1
    n = prod[0]
    assert n.title.startswith("[생산] 도면 바뀜")
    assert f"도면팀 {people.drawer.name} 님이 고쳐" in n.message
    reached = {uid for (uid,) in db_session.query(NotificationUserState.user_id)
               .filter(NotificationUserState.notification_id == n.id)}
    assert reached == {people.prod1.id, people.prod2.id}  # 비활성 계정은 빠진다
    assert n.id in pushes
    assert {x.target_team for x in notifs} == {"CS", "SALES", "PRODUCTION"}


def test_answer_to_sales_revision_says_so(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id, status="RETURNED")
    _login(client, people.drawer)
    assert _send(client, oid).status_code == 200
    prod = [n for n in _prod_notifs(oid) if n.target_team == "PRODUCTION"]
    assert len(prod) == 1
    assert f"영업 수정 요청을 도면팀 {people.drawer.name} 님이 반영해" in prod[0].message
    _order_row, sd = _sd(oid)
    assert sd["drawing_status"] == "CONFIRMED"


def test_revision_request_then_fix_within_60s_both_push(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id)
    _login(client, people.sales)
    res = client.post(f"/api/orders/{oid}/request-revision", json={"note": "문 손잡이 위치"})
    assert res.status_code == 200, res.get_json()
    # 수정요청 알림도 생산팀이 받는다(곧 도면이 바뀐다).
    assert [n.target_team for n in _prod_notifs(oid)].count("PRODUCTION") == 1

    _order_row, sd = _sd(oid)
    o = db_session.get(Order, oid)
    sd = dict(sd)
    sd["drawing_transfer_history"] = [
        dict(h, review_check={"checked": True}) if h.get("action") == "REQUEST_REVISION" else h
        for h in sd["drawing_transfer_history"]
    ]
    o.structured_data = sd
    db_session.commit()

    _login(client, people.drawer)
    assert _send(client, oid).status_code == 200, "수정요청 반영 완료 표시 뒤 전달"
    prod = [n for n in _prod_notifs(oid) if n.target_team == "PRODUCTION"]
    assert len(prod) == 2, "바로 반영 알림은 앞 수정요청 알림과 합치지 않는다"
    assert prod[1].id in pushes


def test_no_production_alert_in_drawing_stage(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id, stage="DRAWING")
    _login(client, people.drawer)
    assert _send(client, oid).status_code == 200
    assert _prod_notifs(oid) == []


def test_production_board_labels_hotfix_transfer():
    import datetime as dt

    sd = {"drawing_transfer_history": [
        {"action": "TRANSFER", "transferred_at": "2026-10-27 01:00:00", "hotfix": True, "note": ""},
        {"action": "CONFIRM_RECEIPT", "at": "2026-10-27 01:00:00", "auto_confirm": "DRAWING_HOTFIX"},
        {"action": "TRANSFER", "transferred_at": "2026-10-27 02:00:00", "note": ""},
    ]}
    alerts, _history = _build_change_lists([], sd, dt.datetime(2026, 10, 1), dt.datetime(2026, 10, 1))
    assert [a["label"] for a in alerts] == ["도면 바뀜(바로 반영)", "도면 재전달"]


# --- A: 사본 지우기 ----------------------------------------------------------


def _manual_copy(oid, uploader_id, *, category="drawing", folder="drawing"):
    a = OrderAttachment(order_id=oid, filename="사본.png", file_type="image", category=category,
                        storage_key=f"orders/{oid}/{folder}/copy-{category}.png", user_id=uploader_id,
                        file_size=1)
    db_session.add(a)
    db_session.commit()
    return a.id


def test_drawing_team_deletes_and_restores_copy(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id)
    copy_id = _manual_copy(oid, people.sales.id)
    _login(client, people.drawer2)  # 담당 아닌 도면팀도 된다
    listed = {a["id"]: a for a in client.get(f"/api/orders/{oid}/attachments").get_json()["attachments"]}
    assert listed[copy_id]["can_delete"] is True
    final_id = next(i for i, a in listed.items() if a.get("drawing_final_rank"))
    assert listed[final_id]["can_delete"] is False  # 최종 도면은 휴지통 버튼 없음

    assert client.delete(f"/api/orders/{oid}/attachments/{copy_id}").status_code == 200
    assert client.post(f"/api/orders/{oid}/attachments/{copy_id}/restore").status_code == 200
    assert client.delete(f"/api/orders/{oid}/attachments/{final_id}").status_code == 409


def test_drawing_team_cannot_delete_measurement_or_partner_original(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id)
    photo_id = _manual_copy(oid, people.sales.id, category="measurement", folder="measurement")
    partner_id = _manual_copy(oid, people.sales.id, folder="partner_draft")
    _login(client, people.drawer)
    assert client.delete(f"/api/orders/{oid}/attachments/{photo_id}").status_code == 403
    assert client.delete(f"/api/orders/{oid}/attachments/{partner_id}").status_code == 403


def test_drawing_team_cannot_change_item_link_of_copy(client, people, pushes):
    """도면팀 정리 규칙은 삭제·되살리기만 — 제품 연결 바꾸기는 옛 규칙."""
    from foms.services.order_attachment_permissions import (
        can_delete_order_attachment,
        can_modify_order_attachment,
    )

    oid = _order(people.drawer.id, people.sales.id)
    copy_id = _manual_copy(oid, people.sales.id)
    order = db_session.get(Order, oid)
    att = db_session.get(OrderAttachment, copy_id)
    drawer = db_session.get(User, people.drawer2.id)
    assert can_delete_order_attachment(drawer, order, att) is True
    assert can_modify_order_attachment(drawer, order, att) is False


def test_workbench_shows_copy_card_and_hides_attachment_link(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id)
    copy_id = _manual_copy(oid, people.sales.id)
    _login(client, people.drawer)
    page = client.get(f"/erp/drawing-workbench/{oid}")
    assert page.status_code == 200
    soup = BeautifulSoup(page.get_data(as_text=True), "html.parser")
    card = soup.select_one("#dw-stray-drawing-card")
    assert card is not None
    ids = [b["data-attachment-id"] for b in card.select("[data-dw-stray-delete]")]
    assert ids == [str(copy_id)]  # 사본만, 최종 도면은 없다
    assert "첨부 파일 열기" not in soup.get_text()
    # 생산 단계 + 확정 도면 1장 → 전달 창 기본 '교체' + 바로 반영 안내
    assert soup.select_one("#dw-transfer-mode option[selected]")["value"] == "REPLACE"
    assert soup.select_one("#dwTransferModal .dw-transfer-hotfix-notice") is not None


def test_workbench_no_copy_card_when_only_final(client, people, pushes):
    oid = _order(people.drawer.id, people.sales.id, stage="DRAWING")
    _login(client, people.drawer)
    soup = BeautifulSoup(client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True), "html.parser")
    assert soup.select_one("#dw-stray-drawing-card") is None
    assert soup.select_one("#dwTransferModal .dw-transfer-hotfix-notice") is None
