"""도면팀 최신본 우선(시트별 교체) + 영업 '도면' 업로드 확인 — 계약(2026-10-04).

운영 주문 5407: 영업이 수령 확정(CONFIRMED)한 뒤 도면팀이 같은 마법사 시트의 2판을 보냈고,
09-30 수정(확정 전 재전달 = 전체 교체)은 TRANSFERRED 에서만 켜져 APPEND 로 쌓였다. 그 사이
영업이 같은 도면을 주문 화면에서 직접 올려 도면 칸이 3장이 됐다. SPEC:
``docs/specs/2026-10-04-drawing-latest-per-sheet_SPEC.md``.
"""
from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

import foms.api.files.order_routes as order_routes
import foms.services.storage as storage_module
from db import db_session
from foms.api.drawing.erp_orders_drawing import perform_drawing_transfer
from foms.services.drawing_confirm_cleanup import (
    resolve_final_drawing_files,
    superseded_drawing_keys,
)
from foms.services.orders.drawing_transfer import replace_same_sheet_files
from foms.web.drawing.tablet_sheet import _sheet_transfer_replaced_count
from models import Order, User


def _exp(order_id, name):
    return f"orders/{order_id}/drawing_wizard/exports/{name}"


def _entry(key, sheet_id=None):
    out = {"key": key, "filename": key.rsplit("/", 1)[-1]}
    if sheet_id:
        out["sheet_id"] = sheet_id
    return out


def _sheets(*ids):
    return {"drawing_wizard": {"sheets": [{"id": i} for i in ids]}}


# ---------------------------------------------------------------------------
# 순수 계산 — replace_same_sheet_files
# ---------------------------------------------------------------------------


def test_same_sheet_replaced_in_place_other_sheet_kept():
    old = [_entry("o/a1", "s-a"), _entry("o/b1", "s-b")]
    base, rest, numbers = replace_same_sheet_files(old, [_entry("o/b2", "s-b")], _sheets("s-a", "s-b"))
    assert [f["key"] for f in base] == ["o/a1", "o/b2"]
    assert rest == [] and numbers == [2]


def test_untagged_legacy_entries_count_as_sole_sheet():
    """5407 모양: sheet_id 없는 옛 판 2장(1판·2판) + 시트 1개 → 새 판 1장으로."""
    old = [_entry(_exp(1, "v1.png")), _entry(_exp(1, "v2.png"))]
    base, rest, numbers = replace_same_sheet_files(
        old, [_entry(_exp(1, "v3.png"), "s-1")], _sheets("s-1"))
    assert [f["key"] for f in base] == [_exp(1, "v3.png")]
    assert rest == [] and numbers == [1, 2]


def test_untagged_legacy_not_guessed_with_two_sheets():
    old = [_entry(_exp(1, "v1.png"))]
    base, rest, numbers = replace_same_sheet_files(
        old, [_entry(_exp(1, "v2.png"), "s-1")], _sheets("s-1", "s-2"))
    assert base == old and numbers == []
    assert [f["key"] for f in rest] == [_exp(1, "v2.png")]


def test_untagged_manual_upload_never_guessed():
    """마법사 산출물이 아닌 옛 도면(직접 올린 파일)은 시트로 추정하지 않는다."""
    old = [_entry("orders/1/drawing/manual.png")]
    base, rest, numbers = replace_same_sheet_files(
        old, [_entry(_exp(1, "v2.png"), "s-1")], _sheets("s-1"))
    assert base == old and numbers == [] and len(rest) == 1


def test_new_file_without_sheet_goes_to_rest():
    old = [_entry(_exp(1, "v1.png"), "s-1")]
    base, rest, numbers = replace_same_sheet_files(
        old, [_entry("orders/1/drawing/extra.png")], _sheets("s-1"))
    assert base == old and numbers == [] and len(rest) == 1


# ---------------------------------------------------------------------------
# 전달 — perform_drawing_transfer
# ---------------------------------------------------------------------------


def _make_user(username, *, team="DRAWING", role="ADMIN"):
    user = User(username=username, password=generate_password_hash("pw"), name=username,
                role=role, team=team, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _make_order(assignee_id, extra=None):
    sd = {
        "workflow": {"stage": "DRAWING"},
        "parties": {"customer": {"name": "홍"}, "manager": {"name": "영업 김"}},
        "assignments": {"drawing_assignee_user_ids": [assignee_id]},
    }
    sd.update(extra or {})
    order = Order(received_date="2026-10-04", customer_name="시트 고객", phone="010-0000-0000",
                  address="Seoul", product="붙박이장", status="DRAWING", manager_name="담당",
                  is_erp_order=True, erp_stage_code="DRAWING", structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def _send(app, order, user, files, **kwargs):
    with app.test_request_context():
        return perform_drawing_transfer(db_session, order, order.id, user, user.id,
                                        files=files, **kwargs)


def _set_status(order_id, status):
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["drawing_status"] = status
    order.structured_data = sd
    db_session.commit()
    return order


def _current(order_id):
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data


@pytest.mark.parametrize("mode", ["", "APPEND"])
def test_retransfer_after_confirm_replaces_same_sheet(app, mode):
    """확정 뒤 같은 시트 새 판(방식 미지정·APPEND 모두) → 현재본은 새 판 1장, 옛 판은 숨김."""
    user = _make_user(f"dws_sheet_confirmed_{mode or 'none'}")
    order = _make_order(user.id, _sheets("s-1"))
    oid = order.id
    v1, v2 = _exp(oid, "v1.png"), _exp(oid, "v2.png")
    assert _send(app, order, user, [_entry(v1, "s-1")])[1] == 200
    order = _set_status(oid, "CONFIRMED")

    payload, status = _send(app, order, user, [_entry(v2, "s-1")], mode=mode)

    assert status == 200, payload
    sd = _current(oid)
    assert [f["key"] for f in sd["drawing_current_files"]] == [v2]
    assert sd["drawing_current_files"][0]["sheet_id"] == "s-1"
    assert v1 in superseded_drawing_keys(sd)
    last = sd["drawing_transfer_history"][-1]
    assert last["mode"] == "REPLACE" and last["replace_target_numbers"] == [1]
    assert sd["drawing_status"] == "TRANSFERRED", "영업이 다시 수령 확정해야 한다"


def test_retransfer_one_of_two_sheets_keeps_other(app):
    user = _make_user("dws_sheet_two")
    order = _make_order(user.id, _sheets("s-1", "s-2"))
    oid = order.id
    a1, b1, b2 = _exp(oid, "a1.png"), _exp(oid, "b1.png"), _exp(oid, "b2.png")
    assert _send(app, order, user, [_entry(a1, "s-1"), _entry(b1, "s-2")])[1] == 200
    order = _set_status(oid, "CONFIRMED")

    assert _send(app, order, user, [_entry(b2, "s-2")])[1] == 200

    assert [f["key"] for f in _current(oid)["drawing_current_files"]] == [a1, b2]


def test_legacy_5407_shape_collapses_to_latest(app):
    """sheet_id 없이 쌓인 1판·2판(5407) + 시트 1개 → 다음 전달에서 새 판 1장."""
    user = _make_user("dws_sheet_5407")
    order = _make_order(user.id, _sheets("s-1"))
    oid = order.id
    v1, v2, v3 = _exp(oid, "v1.png"), _exp(oid, "v2.png"), _exp(oid, "v3.png")
    assert _send(app, order, user, [_entry(v1)])[1] == 200
    order = _set_status(oid, "CONFIRMED")
    assert _send(app, order, user, [_entry(v2)], mode="APPEND")[1] == 200
    order = _set_status(oid, "CONFIRMED")
    assert [f["key"] for f in _current(oid)["drawing_current_files"]] == [v1, v2]

    assert _send(app, order, user, [_entry(v3, "s-1")])[1] == 200

    sd = _current(oid)
    assert [f["key"] for f in sd["drawing_current_files"]] == [v3]
    assert {v1, v2} <= superseded_drawing_keys(sd)


def test_history_previous_files_keep_sheet_for_cancel_restore(app):
    """전달 취소는 previous_current_files 를 그대로 되돌린다 — 그 안에 시트 신원이 남아 있어야 한다."""
    user = _make_user("dws_sheet_cancel")
    order = _make_order(user.id, _sheets("s-1"))
    oid = order.id
    v1, v2 = _exp(oid, "v1.png"), _exp(oid, "v2.png")
    assert _send(app, order, user, [_entry(v1, "s-1")])[1] == 200
    order = _set_status(oid, "TRANSFERRED")
    assert _send(app, order, user, [_entry(v2, "s-1")])[1] == 200
    prev = _current(oid)["drawing_transfer_history"][-1]["previous_current_files"]
    assert [(f["key"], f.get("sheet_id")) for f in prev] == [(v1, "s-1")]


def test_confirm_normalize_keeps_sheet_id():
    sd = {"drawing_current_files": [_entry("orders/1/drawing_wizard/exports/a.png", "s-1")]}
    assert resolve_final_drawing_files(sd)[0]["sheet_id"] == "s-1"


def test_order_push_marked_stale_when_drawing_changes(app):
    user = _make_user("dws_sheet_push")
    order = _make_order(user.id, _sheets("s-1"))
    oid = order.id
    v1, v2 = _exp(oid, "v1.png"), _exp(oid, "v2.png")
    assert _send(app, order, user, [_entry(v1, "s-1")])[1] == 200
    db_session.expire_all()
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["drawing_status"] = "CONFIRMED"
    sd["channeltalk_push_drawing"] = {"pushed": True, "sent_at": "2026-10-02T03:18:06Z"}
    order.structured_data = sd
    db_session.commit()

    assert _send(app, order, user, [_entry(v2, "s-1")])[1] == 200

    push = _current(oid)["channeltalk_push_drawing"]
    assert push["pushed"] is True and push.get("stale_drawing_at")


def test_tablet_notice_counts_same_sheet_after_confirm():
    sd = {
        "drawing_status": "CONFIRMED",
        "drawing_current_files": [_entry(_exp(1, "v1.png"), "s-1"), _entry(_exp(1, "x.png"), "s-2")],
        "drawing_wizard": {"sheets": [{"id": "s-1"}, {"id": "s-2"}],
                           "pending": {"s-1": {"key": _exp(1, "v2.png")}}},
    }
    assert _sheet_transfer_replaced_count(sd) == 1


# ---------------------------------------------------------------------------
# 영업 '도면' 업로드 확인 — drawing_upload_guard (실제 라우트)
# ---------------------------------------------------------------------------


class _Storage:
    storage_type = "r2"

    def __init__(self):
        self.uploaded = []

    def upload_file(self, file_obj, filename, folder="uploads"):
        key = f"{folder}/g_{len(self.uploaded)}_{filename}"
        self.uploaded.append(key)
        return {"success": True, "key": key, "url": f"/fake/{key}", "filename": filename}

    def get_file_type(self, filename):
        return "image"

    def object_exists(self, key):
        return key in self.uploaded

    def delete_file(self, key):
        return True


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(storage_module, "_storage_instance", fake)
    monkeypatch.setattr(order_routes, "ASYNC_ATTACHMENT_THUMBNAIL", False)
    return fake


def _client_user(username, *, team, role="STAFF"):
    """요청 사이 세션 분리에 안전한 값 묶음(라우트 teardown 이 ORM 객체를 떼어 낸다)."""
    user = _make_user(username, team=team, role=role)
    return SimpleNamespace(id=user.id, username=user.username, role=user.role)


def _act_as(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _guard_order(sales, drafter, *, final=True):
    extra = {"assignments": {"sales_assignee_user_ids": [sales.id],
                             "drawing_assignee_user_ids": [drafter.id]}}
    order = _make_order(drafter.id, extra)
    if final:
        sd = dict(order.structured_data)
        sd["drawing_current_files"] = [_entry(_exp(order.id, "v1.png"), "s-1")]
        sd["drawing_status"] = "CONFIRMED"
        order.structured_data = sd
        db_session.commit()
    return SimpleNamespace(id=order.id)


def _post_drawing(client, order_id, **extra):
    data = {"file": (io.BytesIO(b"\x89PNG drawing"), "dup.png"), "category": "drawing"}
    data.update(extra)
    return client.post(f"/api/orders/{order_id}/attachments", data=data,
                       content_type="multipart/form-data")


def test_sales_drawing_upload_needs_ack_when_final_exists(client, storage):
    sales = _client_user("dws_guard_sales", team="SALES")
    drafter = _client_user("dws_guard_drafter", team="DRAWING")
    order = _guard_order(sales, drafter)
    _act_as(client, sales)

    res = _post_drawing(client, order.id)
    assert res.status_code == 409
    body = res.get_json()
    assert body["success"] is False and body["error"] == "DRAWING_FINAL_EXISTS"
    assert body["data"]["count"] == 1
    assert storage.uploaded == [], "확인 전에 스토리지에 올렸다"

    res = _post_drawing(client, order.id, ack_drawing_final="1")
    assert res.status_code == 200, res.get_json()


def test_drawing_upload_without_final_needs_no_ack(client, storage):
    sales = _client_user("dws_guard_sales2", team="SALES")
    drafter = _client_user("dws_guard_drafter2", team="DRAWING")
    order = _guard_order(sales, drafter, final=False)
    _act_as(client, sales)
    assert _post_drawing(client, order.id).status_code == 200


def test_drawing_team_upload_exempt(client, storage):
    sales = _client_user("dws_guard_sales3", team="SALES")
    drafter = _client_user("dws_guard_drafter3", team="DRAWING")
    order = _guard_order(sales, drafter)
    _act_as(client, drafter)
    assert _post_drawing(client, order.id).status_code == 200


def test_measurement_upload_not_guarded(client, storage):
    sales = _client_user("dws_guard_sales4", team="SALES")
    drafter = _client_user("dws_guard_drafter4", team="DRAWING")
    order = _guard_order(sales, drafter)
    _act_as(client, sales)
    res = client.post(f"/api/orders/{order.id}/attachments",
                      data={"file": (io.BytesIO(b"\xff\xd8\xff photo"), "a.jpg"),
                            "category": "measurement"},
                      content_type="multipart/form-data")
    assert res.status_code == 200, res.get_json()


def test_direct_session_and_ticket_need_ack(client, storage):
    sales = _client_user("dws_guard_sales5", team="SALES")
    drafter = _client_user("dws_guard_drafter5", team="DRAWING")
    order = _guard_order(sales, drafter)
    _act_as(client, sales)

    res = client.post("/api/upload/session", json={
        "filename": "dup.png", "size": 10, "folder": f"orders/{order.id}/drawing",
        "category": "drawing"})
    assert res.status_code == 409 and res.get_json()["error"] == "DRAWING_FINAL_EXISTS"

    res = client.post("/api/upload/session/batch", json={
        "files": [{"filename": "dup.png", "size": 10}], "folder": f"orders/{order.id}/drawing",
        "category": "drawing"})
    assert res.status_code == 409

    res = client.post(f"/api/orders/{order.id}/upload-tickets", json={
        "filename": "dup.png", "size": 10, "category": "drawing"})
    assert res.status_code == 409


def test_list_marks_final_rank_and_manual_rows(client, storage):
    sales = _client_user("dws_guard_sales6", team="SALES")
    drafter = _client_user("dws_guard_drafter6", team="DRAWING")
    order = _guard_order(sales, drafter, final=False)
    _act_as(client, drafter)
    manual = _post_drawing(client, order.id).get_json()["attachment"]["storage_key"]
    v1 = _exp(order.id, "v1.png")
    _act_as(client, drafter)
    res = client.post(f"/api/orders/{order.id}/transfer-drawing",
                      json={"note": "", "files": [_entry(v1, "s-1")]})
    assert res.status_code == 200, res.get_json()

    _act_as(client, sales)
    items = client.get(f"/api/orders/{order.id}/attachments").get_json()["attachments"]
    by_key = {i["storage_key"]: i for i in items}
    assert by_key[v1]["drawing_final_rank"] == 1
    assert by_key[v1]["drawing_final_total"] == 1
    assert "drawing_final_rank" not in by_key[manual]
    assert by_key[manual]["drawing_final_total"] == 1
