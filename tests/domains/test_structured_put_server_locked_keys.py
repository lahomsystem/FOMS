"""주문 폼 전체 저장은 도면 축·도면 배정·퀘스트·고객확인을 바꾸지 못한다 — 도면 결함 2차 M1(2a-1①).

결함: 폼 JS 는 폼을 연 순간의 스냅샷에서 도면 키를 그대로 되실어 보냈고, 서버는 키가 **없을 때만**
서버값으로 되돌렸다. 그래서 폼을 연 뒤 도면팀·영업이 도면 API 로 바꾼 상태(수정요청·재전달·배정)를
한 번의 저장이 되돌렸다. 도면 API 는 ``mutation_version`` 을 올리지 않아 If-Match 도 못 걸렀고,
태블릿 폼은 If-Match 없이 보낸다. 1차(확정 때 재계산 제거) 뒤로는 되돌려진 현재 도면이 그대로
확정본·고객 링크·생산 탭이 된다(원장 순서 의존 7).

고침: ``structured_form_projection.lock_server_owned_keys`` 가 저장 순간의 서버값(행 잠금 아래
``old_sd``)으로 고정한다. 모든 테스트는 실제 Flask 라우트를 탄다.
"""

from __future__ import annotations

import copy
from datetime import date
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
import foms.services.storage as storage_module
from db import db_session
from foms.services.orders import structured_form_projection as projection
from models import Order, User


class _Storage:
    storage_type = "r2"

    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.deleted_keys: list[str] = []

    def upload_file(self, file_obj, filename, folder="uploads"):
        key = f"{folder}/m1_{len(self.uploaded)}_{filename}"
        self.uploaded.append(key)
        return {"success": True, "key": key, "url": f"/fake/{key}", "filename": filename}

    def object_exists(self, key: str) -> bool:
        return key in self.uploaded

    def delete_file(self, key: str) -> bool:
        self.deleted_keys.append(key)
        return True


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(storage_module, "_storage_instance", fake)
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)
    return fake


def _user(username: str, role: str, team: str) -> SimpleNamespace:
    u = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
             name=username, is_active=True)
    db_session.add(u)
    db_session.commit()
    return SimpleNamespace(id=u.id, username=u.username, role=u.role, name=u.name)


def _as(client, u: SimpleNamespace) -> None:
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role


def _order(sales: SimpleNamespace, drafter: SimpleNamespace) -> int:
    o = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="M1고객", phone="010-1",
        address="Seoul", product="붙박이장", status="DRAWING", manager_name=sales.name,
        is_erp_order=True, erp_stage_code="DRAWING",
        structured_data={
            "parties": {"customer": {"name": "M1고객", "phone": "010-1111-2222"},
                        "manager": {"name": sales.name}},
            "site": {"address_main": "서울 강남구", "address_full": "서울 강남구"},
            "items": [{"product_name": "붙박이장"}],
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "PENDING",
            "assignments": {"sales_assignee_user_ids": [sales.id],
                            "drawing_assignee_user_ids": [drafter.id]},
        },
    )
    db_session.add(o)
    db_session.commit()
    return o.id


def _sd(oid: int) -> dict:
    db_session.expire_all()
    return copy.deepcopy(db_session.get(Order, oid).structured_data or {})


def _key(oid: int, name: str) -> str:
    return f"orders/{oid}/drawing_wizard/exports/{name}"


def _transfer(client, oid: int, key: str, **extra) -> None:
    body = {"note": "전달", "files": [{"key": key, "filename": key.rsplit("/", 1)[-1]}], **extra}
    res = client.post(f"/api/orders/{oid}/transfer-drawing", json=body)
    assert res.status_code == 200, res.get_json()


def _confirm(client, oid: int) -> None:
    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert res.status_code == 200, res.get_json()


def _revise(client, oid: int) -> None:
    res = client.post(f"/api/orders/{oid}/request-revision", json={"note": "색 변경"})
    assert res.status_code == 200, res.get_json()


def _check_revision(client, oid: int) -> None:
    req = [h for h in _sd(oid)["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"][-1]
    res = client.post(f"/api/orders/{oid}/request-revision-check",
                      json={"request_at": req["at"], "by_user_id": req["by_user_id"], "checked": True})
    assert res.status_code == 200, res.get_json()


def _snapshot(client, oid: int) -> dict:
    """폼을 연 순간의 GET /structured 응답(폼 JS 가 되실어 보내는 원본)."""
    res = client.get(f"/api/orders/{oid}/structured")
    assert res.status_code == 200
    return res.get_json()


def _put(client, oid: int, sd: dict, if_match=None):
    headers = {"If-Match": str(if_match)} if if_match is not None else {}
    res = client.put(f"/api/orders/{oid}/structured", json={"structured_data": sd}, headers=headers)
    assert res.status_code == 200, res.get_json()
    return res


def _drawing_axis(sd: dict) -> tuple:
    return (sd.get("drawing_status"),
            [f.get("key") for f in sd.get("drawing_current_files") or []],
            [h.get("action") for h in sd.get("drawing_transfer_history") or []])


def _confirmed_then_snapshot(client, sales, drafter, oid):
    _as(client, drafter)
    _transfer(client, oid, _key(oid, "v1.png"))
    _as(client, sales)
    _confirm(client, oid)
    snap = _snapshot(client, oid)
    assert snap["structured_data"]["drawing_status"] == "CONFIRMED"
    return snap


def test_tablet_put_without_if_match_cannot_undo_revision_request(client, storage):
    """(a) 태블릿 경로: 확정 뒤 연 폼을 수정요청 뒤 If-Match 없이 저장해도 RETURNED 가 남는다."""
    sales, drafter = _user("m1a_s", "STAFF", "SALES"), _user("m1a_d", "STAFF", "DRAWING")
    oid = _order(sales, drafter)
    snap = _confirmed_then_snapshot(client, sales, drafter, oid)
    _revise(client, oid)
    before = _drawing_axis(_sd(oid))
    assert before[0] == "RETURNED"

    _put(client, oid, snap["structured_data"])

    assert _drawing_axis(_sd(oid)) == before


def test_latest_if_match_with_stale_body_cannot_undo_revision_request(client, storage):
    """(a') 버전을 새로 받아도(최신 If-Match) 본문이 옛 스냅샷이면 도면 축은 그대로다."""
    sales, drafter = _user("m1b_s", "STAFF", "SALES"), _user("m1b_d", "STAFF", "DRAWING")
    oid = _order(sales, drafter)
    snap = _confirmed_then_snapshot(client, sales, drafter, oid)
    _revise(client, oid)
    before = _drawing_axis(_sd(oid))
    latest_version = _snapshot(client, oid)["mutation_version"]

    _put(client, oid, snap["structured_data"], if_match=latest_version)

    assert _drawing_axis(_sd(oid)) == before


def test_stale_put_cannot_roll_back_a_retransfer(client, storage):
    """(b) 반대 방향: 수정본 재전달(TRANSFERRED·[v2]) 뒤 옛 폼이 RETURNED·[v1] 로 못 되돌린다."""
    sales, drafter = _user("m1c_s", "STAFF", "SALES"), _user("m1c_d", "STAFF", "DRAWING")
    oid = _order(sales, drafter)
    v1, v2 = _key(oid, "v1.png"), _key(oid, "v2.png")
    _as(client, drafter)
    _transfer(client, oid, v1)
    _as(client, sales)
    _revise(client, oid)
    snap = _snapshot(client, oid)
    assert snap["structured_data"]["drawing_status"] == "RETURNED"
    _as(client, drafter)
    _check_revision(client, oid)
    _transfer(client, oid, v2, mode="REPLACE", replace_target_keys=[v1])
    after_retransfer = _drawing_axis(_sd(oid))
    assert after_retransfer[:2] == ("TRANSFERRED", [v2])

    _as(client, sales)
    _put(client, oid, snap["structured_data"])

    assert _drawing_axis(_sd(oid)) == after_retransfer


def test_stale_put_cannot_roll_back_quests_or_customer_confirmation(client, storage):
    """(c) 퀘스트 상태·blueprint(고객확인·현재 도면)도 폼 스냅샷으로 되돌아가지 않는다."""
    sales, drafter = _user("m1d_s", "STAFF", "SALES"), _user("m1d_d", "STAFF", "DRAWING")
    oid = _order(sales, drafter)
    _as(client, sales)
    snap = _snapshot(client, oid)
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["quests"] = [{"stage": "DRAWING", "status": "COMPLETED"}]
    sd["blueprint"] = {"customer_confirmed": True, "current": {"key": _key(oid, "v1.png")}}
    order.structured_data = sd
    db_session.commit()
    stale = copy.deepcopy(snap["structured_data"])
    stale["quests"] = [{"stage": "DRAWING", "status": "OPEN"}]
    stale["blueprint"] = {"customer_confirmed": False}

    _put(client, oid, stale)

    now = _sd(oid)
    assert now["quests"] == [{"stage": "DRAWING", "status": "COMPLETED"}]
    assert now["blueprint"] == {"customer_confirmed": True, "current": {"key": _key(oid, "v1.png")}}


def test_stale_put_cannot_restore_previous_drawing_assignee(client, storage):
    """(f) 담당 지정 API 로 [d1]→[d2] 뒤 옛 폼 저장: [d2] 유지, 다른 배정 하위 키는 폼 값이 들어간다."""
    admin = _user("m1f_a", "ADMIN", "SALES")
    sales, d1 = _user("m1f_s", "STAFF", "SALES"), _user("m1f_d1", "STAFF", "DRAWING")
    d2 = _user("m1f_d2", "STAFF", "DRAWING")
    oid = _order(sales, d1)
    _as(client, admin)
    snap = _snapshot(client, oid)
    res = client.post(f"/api/orders/{oid}/assign-draftsman", json={"user_ids": [d2.id]})
    assert res.status_code == 200, res.get_json()
    assert _sd(oid)["assignments"]["drawing_assignee_user_ids"] == [d2.id]
    stale = copy.deepcopy(snap["structured_data"])
    stale["assignments"]["sales_assignee_user_ids"] = [sales.id, admin.id]

    _put(client, oid, stale)

    assignments = _sd(oid)["assignments"]
    assert assignments["drawing_assignee_user_ids"] == [d2.id]
    assert assignments["sales_assignee_user_ids"] == [sales.id, admin.id]


def test_client_cannot_create_drawing_status_the_server_never_had(client, storage):
    """(d) 기존 동작 유지: 서버에 없던 도면 상태를 폼이 새로 만들지 못한다."""
    sales, drafter = _user("m1g_s", "STAFF", "SALES"), _user("m1g_d", "STAFF", "DRAWING")
    oid = _order(sales, drafter)
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd.pop("drawing_status")
    order.structured_data = sd
    db_session.commit()
    _as(client, sales)
    body = copy.deepcopy(_snapshot(client, oid)["structured_data"])
    body["drawing_status"] = "CONFIRMED"
    body["drawing_current_files"] = [{"key": _key(oid, "forged.png")}]

    _put(client, oid, body)

    now = _sd(oid)
    assert "drawing_status" not in now
    assert "drawing_current_files" not in now


def test_order_change_entry_appended_by_the_same_save_survives_the_lock(client, storage):
    """(e) 같은 저장이 서버에서 붙이는 ERP_ORDER_CHANGED 도면 이력은 잠금이 지우지 않는다."""
    sales, drafter = _user("m1e_s", "STAFF", "SALES"), _user("m1e_d", "STAFF", "DRAWING")
    oid = _order(sales, drafter)
    _as(client, drafter)
    _transfer(client, oid, _key(oid, "v1.png"))
    _as(client, sales)
    body = copy.deepcopy(_snapshot(client, oid)["structured_data"])
    body["parties"]["customer"]["phone"] = "010-9999-8888"

    _put(client, oid, body)

    actions = [h.get("action") for h in _sd(oid)["drawing_transfer_history"]]
    assert actions[0] == "TRANSFER"
    assert "ERP_ORDER_CHANGED" in actions[1:]


def test_lock_reports_ignored_paths_and_keeps_server_values():
    """순수 함수: 폼이 다른 값을 보낸 경로만 돌려주고, 서버에 없는 키는 버린다."""
    old = {"drawing_status": "RETURNED", "quests": [1],
           "assignments": {"drawing_assignee_user_ids": [2], "sales_assignee_user_ids": [1]}}
    new = {"drawing_status": "CONFIRMED", "quests": [1], "drawing_current_files": [{"key": "x"}],
           "assignments": {"drawing_assignee_user_ids": [9], "sales_assignee_user_ids": [5]}}

    ignored = projection.lock_server_owned_keys(old, new)

    assert sorted(ignored) == ["assignments.drawing_assignee_user_ids", "drawing_current_files",
                               "drawing_status"]
    assert new == {"drawing_status": "RETURNED", "quests": [1],
                   "assignments": {"drawing_assignee_user_ids": [2], "sales_assignee_user_ids": [5]}}
