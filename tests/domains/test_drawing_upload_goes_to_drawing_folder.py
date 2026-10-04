"""M10 — 전달 창에서 직접 올린 도면이 전달에서 빠지지 않는다(2c-1, 설계서 §4.7).

배경(원장 `docs/plans/2026-09-29-drawing-defects-verification-ledger.md` M10):
    작업실 전달 창·ERP 대시보드 전달 창은 도면을 ``POST /api/orders/<id>/attachments``
    (category=drawing)로 올린다. 서버 multipart 폴더가 category 와 관계없이
    ``orders/<id>/attachments`` 였고, 전달 필터(``drawing_transfer._is_drawing_key``)는
    ``drawing_wizard/``·``drawing/``·``drawing_gateway/`` 만 통과시켜 직접 올린 도면이
    소리 없이 빠졌다(첫 전달 400 "전달할 도면이 없습니다", 재전달 400).

고친 방식:
    category=drawing 업로드는 어느 길이든 ``orders/<id>/drawing/`` 에 저장한다 — multipart
    폴더 분기, direct 세션(단건·일괄)의 폴더 재작성(캐시된 옛 JS 도 고쳐진다), JS 기본 폴더.
    전달 필터·시공 카드 deny-list(``/attachments/``)·고객 링크 allow-list 는 바꾸지 않는다.

음성 대조:
    수정 전 코드에서 multipart·direct 테스트가 빨간 것을 확인했다(보고서 negative_control).
    category=measurement 업로드가 여전히 ``attachments/`` 로 가는 것은 대조군이다.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as drawing_routes
import foms.api.files.order_routes as order_routes
import foms.services.storage as storage_module
from db import db_session
from foms.services.construction_dashboard_display import _collect_preview_items
from models import Order, OrderAttachment, User

ROOT = Path(__file__).resolve().parents[2]


class _Storage:
    """multipart 업로드·direct 세션·complete 를 함께 받는 r2 대역."""

    storage_type = "r2"

    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.thumb_folders: list[str] = []

    # multipart
    def upload_file(self, file_obj, filename, folder="uploads"):
        key = f"{folder}/u{len(self.uploaded) + 1}_{filename}"
        self.uploaded.append(key)
        return {"success": True, "key": key, "url": f"/fake/{key}", "filename": key.rsplit("/", 1)[-1]}

    def get_file_type(self, filename):
        return "image" if filename.lower().endswith((".png", ".jpg", ".jpeg")) else "file"

    def _generate_thumbnail(self, file_obj, unique_filename, folder, file_type, storage_key=None):
        self.thumb_folders.append(folder)
        return None

    # direct
    def generate_direct_upload_key(self, filename, folder):
        key = f"{folder}/d{len(self.uploaded) + 1}_{filename}"
        self.uploaded.append(key)
        return key

    def _get_content_type(self, filename):
        return "image/png"

    def generate_presigned_put_url(self, key, ct, expires_in=900):
        return f"https://r2.example.test/{key}"

    def object_exists(self, key):
        return key in self.uploaded

    def delete_file(self, key):
        return True


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(storage_module, "_storage_instance", fake)
    monkeypatch.setattr(order_routes, "ASYNC_ATTACHMENT_THUMBNAIL", False)
    monkeypatch.setattr(drawing_routes, "emit_erp_notification_to_users", lambda *a, **k: None)
    return fake


def _user(name: str, *, role: str = "STAFF", team: str = "DRAWING") -> SimpleNamespace:
    u = User(username=name, password=generate_password_hash("pw"), role=role, team=team, name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return SimpleNamespace(id=u.id, username=u.username, role=u.role, name=u.name)


def _as(client, u: SimpleNamespace) -> None:
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role


def _order(drafter: SimpleNamespace) -> int:
    o = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="M10고객", phone="010-1010-1010",
        address="Seoul", product="붙박이장", status="DRAWING", manager_name="영업M10", is_erp_order=True,
        erp_stage_code="DRAWING",
        structured_data={
            "parties": {"customer": {"name": "M10고객"}, "manager": {"name": "영업M10"}},
            "workflow": {"stage": "DRAWING"}, "drawing_status": "PENDING",
            "assignments": {"drawing_assignee_user_ids": [drafter.id]},
        },
    )
    db_session.add(o)
    db_session.commit()
    return o.id


def _sd(oid: int) -> dict:
    db_session.expire_all()
    return dict(db_session.get(Order, oid).structured_data or {})


def _multipart(client, oid: int, category: str, name: str = "plan.png"):
    return client.post(
        f"/api/orders/{oid}/attachments",
        data={"file": (io.BytesIO(b"\x89PNG fake"), name), "category": category, "note": "[도면 전달 첨부] "},
        content_type="multipart/form-data",
    )


# ── multipart ────────────────────────────────────────────────────────────────
def test_multipart_drawing_upload_is_stored_under_drawing_and_transfers(client, storage):
    """프로브 P3 옮김: 전달 창 multipart 업로드 key 가 drawing/ 이고 전달 200·현재본 포함."""
    dr = _user("m10_mp_d")
    oid = _order(dr)
    _as(client, dr)
    up = _multipart(client, oid, "drawing")
    assert up.status_code == 200, up.get_json()
    key = up.get_json()["attachment"]["storage_key"]
    assert key.startswith(f"orders/{oid}/drawing/"), key
    # 썸네일도 같은 폴더 변수를 쓴다.
    assert storage.thumb_folders == [f"orders/{oid}/drawing"]
    row = db_session.query(OrderAttachment).filter_by(order_id=oid, storage_key=key).one()
    assert row.category == "drawing"
    assert row.thumbnail_key.startswith(f"orders/{oid}/drawing/thumb_")

    t = client.post(f"/api/orders/{oid}/transfer-drawing", json={"files": [{"key": key, "filename": "plan.png"}]})
    assert t.status_code == 200, t.get_json()
    sd = _sd(oid)
    assert sd["drawing_status"] == "TRANSFERRED"
    assert [f["key"] for f in sd["drawing_current_files"]] == [key]


def test_multipart_non_drawing_upload_stays_under_attachments(client, storage):
    """대조군: 실측 사진은 지금처럼 attachments/ — 전달 필터에 걸려 도면으로 새지 않는다."""
    dr = _user("m10_mp_m")
    oid = _order(dr)
    _as(client, dr)
    up = _multipart(client, oid, "measurement", "site.jpg")
    assert up.status_code == 200, up.get_json()
    key = up.get_json()["attachment"]["storage_key"]
    assert key.startswith(f"orders/{oid}/attachments/"), key
    t = client.post(f"/api/orders/{oid}/transfer-drawing", json={"files": [{"key": key}]})
    assert t.status_code == 400


def test_mixed_with_wizard_pending_direct_upload_is_not_dropped(client, storage):
    """마법사 도면과 섞어 보내도 직접 올린 도면이 소리 없이 빠지지 않는다."""
    dr = _user("m10_mix_d")
    oid = _order(dr)
    _as(client, dr)
    key = _multipart(client, oid, "drawing").get_json()["attachment"]["storage_key"]
    wiz = f"orders/{oid}/drawing_wizard/exports/s1.png"
    t = client.post(f"/api/orders/{oid}/transfer-drawing", json={"files": [{"key": wiz}, {"key": key}]})
    assert t.status_code == 200, t.get_json()
    assert {f["key"] for f in _sd(oid)["drawing_current_files"]} == {wiz, key}


# ── direct 세션 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("endpoint", ["single", "batch"])
def test_direct_session_rewrites_attachments_folder_for_drawing(client, storage, endpoint):
    """folder=attachments + category=drawing → 발급 key 가 drawing/ (캐시된 옛 JS 도 고쳐진다)."""
    dr = _user(f"m10_ds_{endpoint}")
    oid = _order(dr)
    _as(client, dr)
    folder = f"orders/{oid}/attachments"
    if endpoint == "single":
        res = client.post("/api/upload/session",
                          json={"filename": "plan.png", "size": 10, "folder": folder, "category": "drawing"})
        keys = [res.get_json().get("key")]
    else:
        res = client.post("/api/upload/session/batch",
                          json={"folder": folder, "category": "drawing",
                                "files": [{"filename": "plan.png", "size": 10, "client_id": "0"}]})
        keys = [s["key"] for s in res.get_json().get("sessions") or []]
    assert res.status_code == 200, res.get_json()
    assert keys and all(k.startswith(f"orders/{oid}/drawing/") for k in keys), keys


@pytest.mark.parametrize("endpoint", ["single", "batch"])
@pytest.mark.parametrize("category", ["measurement", None])
def test_direct_session_keeps_attachments_folder_for_other_categories(client, storage, endpoint, category):
    """대조군: category 가 drawing 이 아니거나 없으면 폴더는 그대로 attachments/."""
    dr = _user(f"m10_dk_{endpoint}_{category}")
    oid = _order(dr)
    _as(client, dr)
    body = {"folder": f"orders/{oid}/attachments"}
    if category:
        body["category"] = category
    if endpoint == "single":
        res = client.post("/api/upload/session", json={**body, "filename": "a.png", "size": 10})
        keys = [res.get_json().get("key")]
    else:
        res = client.post("/api/upload/session/batch", json={**body, "files": [{"filename": "a.png", "size": 10}]})
        keys = [s["key"] for s in res.get_json().get("sessions") or []]
    assert res.status_code == 200, res.get_json()
    assert keys and all(k.startswith(f"orders/{oid}/attachments/") for k in keys), keys


def test_direct_session_other_subfolders_are_not_rewritten(client, storage):
    """drawing_gateway/revisions 처럼 이미 도면 폴더인 요청은 손대지 않는다."""
    dr = _user("m10_gw")
    oid = _order(dr)
    _as(client, dr)
    folder = f"orders/{oid}/drawing_gateway/revisions"
    res = client.post("/api/upload/session",
                      json={"filename": "g.png", "size": 10, "folder": folder, "category": "drawing"})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["key"].startswith(folder + "/")


def test_direct_session_rewritten_folder_uses_drawing_upload_permission(client, storage):
    """권한 판정은 바뀐 폴더 기준 — 도면 업로드 권한이 없는 시공팀 STAFF 는 403."""
    dr = _user("m10_perm_d")
    oid = _order(dr)
    cons = _user("m10_perm_c", team="CONSTRUCTION")
    _as(client, cons)
    res = client.post("/api/upload/session", json={
        "filename": "plan.png", "size": 10, "folder": f"orders/{oid}/attachments", "category": "drawing"})
    assert res.status_code == 403, res.get_json()
    # multipart 도 같은 판정(원래부터) — 두 길이 같은 답을 낸다.
    assert _multipart(client, oid, "drawing").status_code == 403


def test_direct_full_flow_session_put_complete_then_transfer(client, storage):
    """세션 → (PUT) → complete → 전달: 행 category=drawing, 전달 200."""
    dr = _user("m10_full")
    oid = _order(dr)
    _as(client, dr)
    sess = client.post("/api/upload/session", json={
        "filename": "plan.png", "size": 10, "folder": f"orders/{oid}/attachments", "category": "drawing"}).get_json()
    key = sess["key"]
    done = client.post(f"/api/orders/{oid}/attachments/complete",
                       json={"key": key, "filename": "plan.png", "category": "drawing", "size": 10})
    assert done.status_code == 200, done.get_json()
    assert done.get_json()["attachment"]["category"] == "drawing"
    t = client.post(f"/api/orders/{oid}/transfer-drawing", json={"files": [{"key": key, "filename": "plan.png"}]})
    assert t.status_code == 200, t.get_json()
    assert [f["key"] for f in _sd(oid)["drawing_current_files"]] == [key]


# ── 전달 뒤 보이는 곳(시공 카드) ─────────────────────────────────────────────
def test_transferred_upload_shows_on_construction_card(client, storage):
    """drawing/ 업로드를 전달하면 시공 카드(drawing_only deny-list)를 통과한다."""
    dr = _user("m10_cons")
    oid = _order(dr)
    _as(client, dr)
    key = _multipart(client, oid, "drawing").get_json()["attachment"]["storage_key"]
    assert client.post(f"/api/orders/{oid}/transfer-drawing", json={"files": [{"key": key}]}).status_code == 200
    row = {"structured_data": _sd(oid)}  # id 없음 → sd 경로만(deny-list 판정 대상)
    views = [i["view"] for i in _collect_preview_items(row, MagicMock(), drawing_only=True)]
    assert any(key in v for v in views), views


# ── JS 폴더(작업실 전달 창 direct · 공용 도우미 기본 폴더) ──────────────────
def test_workbench_transfer_modal_direct_folder_is_drawing():
    src = (ROOT / "templates/drawing/partials/workbench_detail_body.html").read_text(encoding="utf-8")
    assert "const folder = `orders/${orderId}/drawing`;" in src
    assert "const folder = `orders/${orderId}/attachments`;" not in src


def test_upload_progress_default_folder_follows_drawing_category_and_pin():
    src = (ROOT / "static/js/runtime/upload-progress.js").read_text(encoding="utf-8")
    assert re.search(r"category === 'drawing' \? 'drawing' : 'attachments'", src), "기본 폴더가 category 를 모른다"
    layout = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    assert "js/runtime/upload-progress.js') }}?v=20261004a" in layout
