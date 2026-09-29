"""마법사로 저장하면 도면 담당자 자동 지정(2026-09-30 사용자 결정).

도면 담당이 한 명도 없는 주문을 도면팀(DRAWING) 활성 사용자가 마법사로 저장(PUT·sheet-png)
하면, 같은 잠금 쓰기(버전 +1 한 번) 안에서 그 사람이 담당으로 들어간다. 이미 담당이 있거나
도면팀이 아닌 관리자면 바뀌지 않는다. 음성 대조군: 저장 없이 전달하면 기존대로 담당 미지정 400.
"""

from __future__ import annotations

import copy
import io
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.api.drawing.wizard as wizard_api
from db import db_session
from models import Order, OrderEvent, User

_AUTO_NOTE_PREFIX = "도면 담당자 자동 지정:"


class _Storage:
    def upload_file(self, file_obj, filename, folder="uploads"):
        return {"success": True, "key": f"{folder}/{filename}"}

    def delete_file(self, key):
        return True


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(wizard_api, "get_storage", lambda: fake)
    return fake


def _user(username, role, team, *, is_active=True):
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username}-name", is_active=is_active)
    db_session.add(user)
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=user.role, name=user.name)


def _as(client, user):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _order(*, drawing_ids=None, stage="DRAWING"):
    assignments = {}
    if drawing_ids is not None:
        assignments["drawing_assignee_user_ids"] = list(drawing_ids)
    sd = {
        "parties": {"customer": {"name": "자동고객", "phone": "010-1111-2222"},
                    "manager": {"name": "영업"}},
        "site": {"address_main": "서울 강남구", "address_full": "서울 강남구"},
        "items": [{"product_name": "붙박이장"}],
        "workflow": {"stage": stage},
        "drawing_status": "PENDING",
        "assignments": assignments,
    }
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="자동고객",
                  phone="010-1111-2222", address="서울", product="붙박이장", status=stage,
                  manager_name="영업", is_erp_order=True, erp_stage_code=stage,
                  structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order.id


def _state(oid):
    db_session.expire_all()
    order = db_session.get(Order, oid)
    return int(order.mutation_version or 0), copy.deepcopy(order.structured_data or {})


def _auto_notes(sd):
    return [h for h in (sd.get("workflow") or {}).get("history") or []
            if str(h.get("note", "")).startswith(_AUTO_NOTE_PREFIX)]


def _auto_events(oid):
    return [e for e in db_session.query(OrderEvent).filter_by(
        order_id=oid, event_type="DRAWING_ASSIGNEE_SET").all()
        if (e.payload or {}).get("change_method") == "WIZARD_AUTO"]


def _wizard_state():
    return {"v": 1, "sheets": [{"id": "s-1", "name": "도면 1", "form": {}, "objects": []}]}


def _put(client, oid):
    return client.put(f"/api/orders/{oid}/drawing-wizard",
                      json={"state": _wizard_state(), "base_updated_at": None})


def _sheet_png(client, oid):
    return client.post(
        f"/api/orders/{oid}/drawing-wizard/sheet-png",
        data={"file": (io.BytesIO(b"\x89PNG\r\n\x1a\nFAKE"), "p1.png"),
              "sheet_id": "s-1", "sheet_name": "도면 1"},
        content_type="multipart/form-data",
    )


def test_put_by_drawing_user_auto_assigns_once(client):
    drafter = _user("aa1_draw", "STAFF", "DRAWING")
    oid = _order()
    before, _ = _state(oid)
    _as(client, drafter)

    r = _put(client, oid)

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["auto_assigned"] == {"user_id": drafter.id, "name": drafter.name}
    after, sd = _state(oid)
    assert after == before + 1  # 담당 지정과 저장이 한 번의 버전 +1
    assert sd["assignments"]["drawing_assignee_user_ids"] == [drafter.id]
    assert sd["drawing_assignees"] == [{"id": drafter.id, "name": drafter.name, "team": "DRAWING"}]
    assert sd["shipment"]["drawing_managers"] == [drafter.name]
    notes = _auto_notes(sd)
    assert len(notes) == 1 and notes[0]["note"] == f"도면 담당자 자동 지정: {drafter.name} (마법사 저장)"
    assert sd["drawing_wizard"]["sheets"][0]["id"] == "s-1"
    assert len(_auto_events(oid)) == 1

    # 두 번째 저장은 이미 담당이 있으므로 다시 지정하지 않는다.
    r2 = client.put(f"/api/orders/{oid}/drawing-wizard",
                    json={"state": _wizard_state(),
                          "base_updated_at": sd["drawing_wizard"]["updated_at"]})
    assert r2.status_code == 200, r2.get_json()
    assert r2.get_json()["data"]["auto_assigned"] is None
    after2, sd2 = _state(oid)
    assert after2 == after + 1
    assert len(_auto_notes(sd2)) == 1
    assert len(_auto_events(oid)) == 1


def test_sheet_png_by_drawing_user_auto_assigns_once(client, storage):
    drafter = _user("aa2_draw", "STAFF", "DRAWING")
    oid = _order()
    before, _ = _state(oid)
    _as(client, drafter)

    r = _sheet_png(client, oid)

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["auto_assigned"]["user_id"] == drafter.id
    after, sd = _state(oid)
    assert after == before + 1
    assert sd["assignments"]["drawing_assignee_user_ids"] == [drafter.id]
    assert len(_auto_notes(sd)) == 1
    assert "s-1" in sd["drawing_wizard"]["pending"]
    assert len(_auto_events(oid)) == 1


def test_already_assigned_is_unchanged(client, storage):
    owner = _user("aa3_owner", "STAFF", "DRAWING")
    other = _user("aa3_other", "STAFF", "DRAWING")
    oid = _order(drawing_ids=[owner.id])
    _as(client, other)

    assert _put(client, oid).status_code == 200
    assert _sheet_png(client, oid).status_code == 200

    _, sd = _state(oid)
    assert sd["assignments"]["drawing_assignee_user_ids"] == [owner.id]
    assert _auto_notes(sd) == []
    assert _auto_events(oid) == []


def test_admin_not_on_drawing_team_does_not_auto_assign(client, storage):
    admin = _user("aa4_admin", "ADMIN", "CS")
    oid = _order()
    before, _ = _state(oid)
    _as(client, admin)

    r = _put(client, oid)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["auto_assigned"] is None
    assert _sheet_png(client, oid).status_code == 200

    after, sd = _state(oid)
    assert after == before + 2
    assert not (sd.get("assignments") or {}).get("drawing_assignee_user_ids")
    assert _auto_notes(sd) == []


def test_non_participant_cannot_save_so_no_assign(client):
    sales = _user("aa5_sales", "STAFF", "SALES")
    oid = _order()
    _as(client, sales)

    assert _put(client, oid).status_code == 403
    _, sd = _state(oid)
    assert not (sd.get("assignments") or {}).get("drawing_assignee_user_ids")


def test_transfer_pending_works_after_auto_assign(client, storage):
    """음성 대조군(저장 없이 전달 → 400)과 같은 모집단에서, 저장 뒤 전달은 통과한다."""
    drafter = _user("aa6_draw", "STAFF", "DRAWING")
    control_oid = _order()
    oid = _order()
    _as(client, drafter)

    # 음성 대조군: 저장 없이 담당 미지정 주문에 대기 시트를 심고 전달 → 기존 게이트 400.
    order = db_session.get(Order, control_oid)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"] = {"pending": {"s-1": {
        "key": f"orders/{control_oid}/drawing_wizard/exports/p1.png", "filename": "p1.png"}}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    ctrl = client.post(f"/api/orders/{control_oid}/drawing-wizard/transfer-pending", json={})
    assert ctrl.status_code == 400, ctrl.get_json()

    assert _sheet_png(client, oid).status_code == 200
    r = client.post(f"/api/orders/{oid}/drawing-wizard/transfer-pending", json={})
    assert r.status_code == 200, r.get_json()
    _, sd = _state(oid)
    assert sd["drawing_status"] == "TRANSFERRED"
    assert sd["assignments"]["drawing_assignee_user_ids"] == [drafter.id]


def test_should_auto_assign_predicate_edges():
    """술어 경계: 팀 공백 제거·비활성·레거시 drawing_assignees 도 '담당 있음'."""
    from foms.services.orders.drawing_assignee_write import should_auto_assign_wizard_saver

    def u(team, active=True):
        return SimpleNamespace(id=7, name="n", team=team, is_active=active)

    assert should_auto_assign_wizard_saver({}, u(" DRAWING ")) is True
    assert should_auto_assign_wizard_saver({}, u("DRAWING", active=False)) is False
    assert should_auto_assign_wizard_saver({}, u("drawing")) is False
    assert should_auto_assign_wizard_saver({}, None) is False
    assert should_auto_assign_wizard_saver(
        {"drawing_assignees": [{"id": 3, "name": "x"}]}, u("DRAWING")) is False
    assert should_auto_assign_wizard_saver(
        {"assignments": {"drawing_assignee_user_ids": []}}, u("DRAWING")) is True
