"""마법사 부가 쓰기의 커밋 뒤 파일 삭제는 공통 판정(drawing_key_safety)을 거친다(2026-09-30).

* 시트 PNG 재저장: 같은 sheet_id 의 옛 대기 파일이 이미 전달돼 현재본(drawing_current_files)
  이 가리키고 있으면 지우지 않는다. 아무 곳도 안 쓰면 지운다(음성 대조군).
* 버전 스냅샷 30개 초과 가지치기: 빠진 가장 오래된 스냅샷 key 를 현재본·이력이 가리키면
  지우지 않는다. 아무 곳도 안 쓰면 지운다(음성 대조군).
"""

from __future__ import annotations

import copy
import io
from datetime import date

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.api.drawing.wizard as wizard_api
from db import db_session
from models import Order, User


class _Storage:
    """삭제·업로드를 기록만 하는 가짜 스토리지(실제 R2 접근 없음)."""

    def __init__(self):
        self.deleted: list[str] = []
        self.uploaded: list[str] = []

    def delete_file(self, key):
        self.deleted.append(key)
        return True

    def upload_file(self, file_obj, filename, folder="uploads"):
        key = f"{folder}/{filename}"
        self.uploaded.append(key)
        return {"success": True, "key": key}


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(wizard_api, "get_storage", lambda: fake)
    return fake


def _user(username, role, team):
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id, user.username, user.role


def _as(client, user):
    uid, username, role = user
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role


def _order(sales_id, drafter_id):
    sd = {
        "parties": {"customer": {"name": "키고객", "phone": "010-1111-2222"},
                    "manager": {"name": "영업"}},
        "site": {"address_main": "서울 강남구", "address_full": "서울 강남구"},
        "items": [{"product_name": "붙박이장"}],
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "IN_PROGRESS",
        "assignments": {"sales_assignee_user_ids": [sales_id],
                        "drawing_assignee_user_ids": [drafter_id]},
    }
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="키고객",
                  phone="010-1111-2222", address="서울", product="붙박이장", status="DRAWING",
                  manager_name="영업", is_erp_order=True, erp_stage_code="DRAWING",
                  structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order.id


def _patch_sd(oid, fn):
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    fn(sd)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _sd(oid):
    db_session.expire_all()
    return dict(db_session.get(Order, oid).structured_data or {})


def _export_key(oid, name):
    return f"orders/{oid}/drawing_wizard/exports/{name}"


def _version_key(oid, v):
    return f"orders/{oid}/drawing_wizard/versions/v{v}_s-1.json"


def _post_png(client, oid, name):
    return client.post(f"/api/orders/{oid}/drawing-wizard/sheet-png",
                       data={"file": (io.BytesIO(b"\x89PNG\r\n\x1a\nfake"), name),
                             "sheet_id": "s-1", "sheet_name": "시트1"},
                       content_type="multipart/form-data")


def _setup(prefix):
    sales = _user(f"{prefix}_sales", "STAFF", "SALES")
    drafter = _user(f"{prefix}_draw", "STAFF", "DRAWING")
    return drafter, _order(sales[0], drafter[0])


def _seed_pending(oid, old_key, *, transferred: bool):
    def _fn(sd):
        sd["drawing_wizard"] = {"pending": {"s-1": {"key": old_key, "filename": "old.png",
                                                    "sheet_name": "시트1"}}}
        if transferred:
            sd["drawing_current_files"] = [{"key": old_key, "filename": "old.png"}]
    _patch_sd(oid, _fn)


# ── 시트 PNG 재저장 ─────────────────────────────────────────────────────────


def test_sheet_png_resave_keeps_old_key_referenced_by_current_files(client, storage):
    """옛 대기 key 가 전달된 현재본에 있으면 재저장해도 지우지 않는다(새 key 는 pending 에)."""
    drafter, oid = _setup("ks1")
    old_key = _export_key(oid, "old.png")
    _seed_pending(oid, old_key, transferred=True)

    _as(client, drafter)
    r = _post_png(client, oid, "new.png")
    assert r.status_code == 200, r.get_json()
    new_key = _export_key(oid, "new.png")
    assert r.get_json()["data"]["key"] == new_key
    assert old_key not in storage.deleted
    assert storage.deleted == []
    sd = _sd(oid)
    assert sd["drawing_wizard"]["pending"]["s-1"]["key"] == new_key
    assert [f["key"] for f in sd["drawing_current_files"]] == [old_key]


def test_sheet_png_resave_deletes_unreferenced_old_key(client, storage):
    """음성 대조군 — 옛 대기 key 를 아무 기록도 안 쓰면 커밋 뒤 지운다."""
    drafter, oid = _setup("ks2")
    old_key = _export_key(oid, "old.png")
    _seed_pending(oid, old_key, transferred=False)

    _as(client, drafter)
    r = _post_png(client, oid, "new.png")
    assert r.status_code == 200, r.get_json()
    assert storage.deleted == [old_key]
    assert _sd(oid)["drawing_wizard"]["pending"]["s-1"]["key"] == _export_key(oid, "new.png")


# ── 버전 스냅샷 30개 초과 가지치기 ───────────────────────────────────────────


_SHEET = {"id": "s-1", "name": "시트1", "form": {}, "objects": []}


def _seed_versions(oid, *, oldest_ref: str | None):
    """버전 30개(v1~v30). ``oldest_ref`` = 'current' | 'history' | None(어디도 안 씀)."""
    def _fn(sd):
        sd["drawing_wizard"] = {"versions": [
            {"v": i, "sheet_id": "s-1", "sheet_name": "시트1", "key": _version_key(oid, i)}
            for i in range(1, 31)]}
        ref = [{"key": _version_key(oid, 1), "filename": "v1_s-1.json"}]
        if oldest_ref == "current":
            sd["drawing_current_files"] = ref
        elif oldest_ref == "history":
            sd["drawing_transfer_history"] = [{"action": "TRANSFER", "at": "2026-09-01 10:00:00",
                                               "files": ref}]
    _patch_sd(oid, _fn)


def _snapshot(client, oid):
    return client.post(f"/api/orders/{oid}/drawing-wizard/version-snapshot",
                       json={"sheet": _SHEET, "sheet_id": "s-1", "sheet_name": "시트1"})


@pytest.mark.parametrize("ref", ["current", "history"])
def test_snapshot_prune_keeps_key_still_referenced(client, storage, ref):
    """가지치기로 빠진 v1 key 를 현재본/전달 이력이 가리키면 지우지 않는다(포인터는 빠진다)."""
    drafter, oid = _setup(f"ks3{ref}")
    _seed_versions(oid, oldest_ref=ref)

    _as(client, drafter)
    r = _snapshot(client, oid)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["v"] == 31
    assert _version_key(oid, 1) not in storage.deleted
    assert storage.deleted == []
    versions = _sd(oid)["drawing_wizard"]["versions"]
    assert len(versions) == 30 and versions[0]["v"] == 2 and versions[-1]["v"] == 31


def test_snapshot_prune_deletes_unreferenced_key(client, storage):
    """음성 대조군 — v1 key 를 아무 기록도 안 쓰면 커밋 뒤 지운다."""
    drafter, oid = _setup("ks4")
    _seed_versions(oid, oldest_ref=None)

    _as(client, drafter)
    r = _snapshot(client, oid)
    assert r.status_code == 200, r.get_json()
    assert storage.deleted == [_version_key(oid, 1)]
    versions = _sd(oid)["drawing_wizard"]["versions"]
    assert len(versions) == 30 and versions[0]["v"] == 2
