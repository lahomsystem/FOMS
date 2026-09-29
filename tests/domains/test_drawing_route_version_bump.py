"""2a-1② — 도면 라우트가 주문을 바꾸면 ``mutation_version`` 이 정확히 1 오른다.

도면 API 는 지금까지 버전을 올리지 않아(전달 취소의 outbox 경로 한 곳만 예외), 그 전에 연
주문 폼이 ``If-Match`` 를 보내도 409 로 걸러지지 않았다(설계서 §4.1 문제 4번째 줄).
여기서는 라우트 7개(전달·작업실 대기 전달·전달 취소·수정요청·반영 체크·수정요청 취소·
수령 확정 단계 유지)와 단계가 옮겨지는 수령 확정(전이 엔진이 한 번만 올린다)을 실제 HTTP
로 부르고, 각 호출 뒤

* 버전이 정확히 +1 이고,
* 호출 **전** 버전으로 ``PUT /api/orders/<id>/structured`` 에 ``If-Match`` 를 보내면 409
  ``VERSION_CONFLICT`` 인지

를 확인한다. 잠금 순서(첫 조회를 행 잠금 아래에서)는 SQLite 로는 볼 수 없어서
``tests/postgres/test_drawing_route_row_lock_pg.py`` 가 따로 본다.
"""

from __future__ import annotations

from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
import foms.api.drawing.wizard as wizard_api
from db import db_session
from models import Order, User


class _Storage:
    """삭제·업로드를 기록만 하는 가짜 스토리지(실제 R2 접근 없음)."""

    def __init__(self):
        self.deleted: list[str] = []

    def delete_file(self, key):
        self.deleted.append(key)
        return True

    def upload_file(self, file_obj, filename, folder="uploads"):
        return {"success": True, "key": f"{folder}/{filename}"}


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(revision_api, "get_storage", lambda: fake)
    monkeypatch.setattr(wizard_api, "get_storage", lambda: fake)
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)
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


def _order(sales_id, drafter_id, *, stage="DRAWING", drawing_status="PENDING", extra=None):
    sd = {
        "parties": {"customer": {"name": "버전고객", "phone": "010-1111-2222"},
                    "manager": {"name": "영업"}},
        "site": {"address_main": "서울 강남구", "address_full": "서울 강남구"},
        "items": [{"product_name": "붙박이장"}],
        "workflow": {"stage": stage},
        "drawing_status": drawing_status,
        "assignments": {"sales_assignee_user_ids": [sales_id],
                        "drawing_assignee_user_ids": [drafter_id]},
    }
    sd.update(extra or {})
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="버전고객",
                  phone="010-1111-2222", address="서울", product="붙박이장", status=stage,
                  manager_name="영업", is_erp_order=True, erp_stage_code=stage,
                  structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order.id


def _key(oid, name):
    return f"orders/{oid}/drawing_wizard/exports/{name}"


def _state(oid):
    db_session.expire_all()
    order = db_session.get(Order, oid)
    return int(order.mutation_version or 0), dict(order.structured_data or {})


def _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, resp):
    """라우트 성공 → 버전 +1 → 그 전 버전 If-Match 로 폼 PUT 은 409."""
    assert resp.status_code == 200, resp.get_json()
    after, sd = _state(oid)
    assert after == before + 1, f"mutation_version {before} -> {after} (+1 이어야 한다)"
    _as(client, admin)
    snap = client.get(f"/api/orders/{oid}/structured").get_json()
    put = client.put(f"/api/orders/{oid}/structured",
                     json={"structured_data": snap["structured_data"]},
                     headers={"If-Match": str(before)})
    assert put.status_code == 409, put.get_json()
    assert (put.get_json() or {}).get("error") == "VERSION_CONFLICT"
    return sd


def test_transfer_cancel_revision_check_cancel_each_bump_version(client, storage):
    """전달 → 전달 취소 → 재전달 → 수정요청 → 반영 체크 → 수정요청 취소: 매번 +1·오래된 폼 409."""
    admin = _user("vb_admin", "ADMIN", "CS")
    sales = _user("vb_sales", "STAFF", "SALES")
    drafter = _user("vb_draw", "STAFF", "DRAWING")
    oid = _order(sales[0], drafter[0], stage="CONFIRM", drawing_status="PENDING")

    # 1) 전달
    before, _ = _state(oid)
    _as(client, drafter)
    r = client.post(f"/api/orders/{oid}/transfer-drawing",
                    json={"files": [{"key": _key(oid, "v1.png"), "filename": "v1.png"}]})
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert sd["drawing_status"] == "TRANSFERRED"

    # 2) 전달 취소(회수 파일이 있는 경로)
    before, _ = _state(oid)
    _as(client, drafter)
    r = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert sd["drawing_status"] == "PENDING"

    # 3) 재전달
    before, _ = _state(oid)
    _as(client, drafter)
    r = client.post(f"/api/orders/{oid}/transfer-drawing",
                    json={"files": [{"key": _key(oid, "v2.png"), "filename": "v2.png"}]})
    _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)

    # 4) 수정요청
    before, _ = _state(oid)
    _as(client, sales)
    r = client.post(f"/api/orders/{oid}/request-revision", json={"note": "색 변경"})
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert sd["drawing_status"] == "RETURNED"
    req = [h for h in sd["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"][-1]

    # 5) 반영 체크
    before, _ = _state(oid)
    _as(client, drafter)
    r = client.post(f"/api/orders/{oid}/request-revision-check",
                    json={"request_at": req["at"], "by_user_id": req["by_user_id"], "checked": True})
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    checked = [h for h in sd["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"][-1]
    assert checked["review_check"]["checked"] is True

    # 6) 수정요청 취소
    before, _ = _state(oid)
    _as(client, sales)
    r = client.post(f"/api/orders/{oid}/cancel-revision-request", json={})
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert sd["drawing_status"] == "TRANSFERRED"


def test_cancel_transfer_without_new_files_still_bumps(client, storage):
    """새 파일 없이 한 전달(기존 현재본 유지)을 취소해도 버전이 오른다(예전엔 outbox 경로만 올렸다)."""
    admin = _user("vb2_admin", "ADMIN", "CS")
    sales = _user("vb2_sales", "STAFF", "SALES")
    drafter = _user("vb2_draw", "STAFF", "DRAWING")
    current = [{"key": _key(0, "old.png"), "filename": "old.png"}]
    oid = _order(sales[0], drafter[0], stage="CONFIRM", drawing_status="PENDING",
                 extra={"drawing_current_files": current})
    _as(client, drafter)
    assert client.post(f"/api/orders/{oid}/transfer-drawing", json={}).status_code == 200

    before, _ = _state(oid)
    _as(client, drafter)
    r = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert sd["drawing_status"] == "PENDING"


def test_receipt_stage_kept_bumps_once(client, storage):
    """단계 밖(CONFIRM)에서 확정 = 단계 유지 경로 — 전이 엔진 없이도 +1."""
    admin = _user("vb3_admin", "ADMIN", "CS")
    sales = _user("vb3_sales", "STAFF", "SALES")
    drafter = _user("vb3_draw", "STAFF", "DRAWING")
    oid = _order(sales[0], drafter[0], stage="CONFIRM")
    _as(client, drafter)
    assert client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": _key(oid, "a.png")}]}).status_code == 200

    before, _ = _state(oid)
    _as(client, sales)
    r = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert (r.get_json() or {}).get("stage_moved") is False, r.get_json()
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert sd["drawing_status"] == "CONFIRMED"
    assert sd["drawing_transfer_history"][-1]["action"] == "CONFIRM_RECEIPT"
    assert sd["workflow"]["history"][-1]["note"] == "도면 수령 확인(단계 유지)"


def test_receipt_stage_moving_bumps_exactly_once(client, storage):
    """도면 단계에서 확정 = 전이 엔진이 버전을 올린다 — 라우트가 한 번 더 올리지 않는다."""
    admin = _user("vb4_admin", "ADMIN", "CS")
    sales = _user("vb4_sales", "STAFF", "SALES")
    drafter = _user("vb4_draw", "STAFF", "DRAWING")
    oid = _order(sales[0], drafter[0], stage="DRAWING")
    _as(client, drafter)
    assert client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": _key(oid, "a.png")}]}).status_code == 200

    before, _ = _state(oid)
    _as(client, sales)
    r = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert (r.get_json() or {}).get("stage_moved") is True, r.get_json()
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert sd["drawing_status"] == "CONFIRMED"
    assert sd["workflow"]["stage"] == "CONFIRM"


def test_wizard_transfer_pending_bumps_version(client, storage):
    """작업실 대기 도면 전달(transfer-pending)도 공용 전달 처리를 타서 +1."""
    admin = _user("vb5_admin", "ADMIN", "CS")
    sales = _user("vb5_sales", "STAFF", "SALES")
    drafter = _user("vb5_draw", "STAFF", "DRAWING")
    oid = _order(sales[0], drafter[0], stage="CONFIRM")
    _as(client, admin)
    order = db_session.get(Order, oid)
    import copy

    from sqlalchemy.orm.attributes import flag_modified
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"] = {"pending": {"s-1": {"key": _key(oid, "p1.png"), "filename": "p1.png"}}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()

    before, _ = _state(oid)
    _as(client, drafter)
    r = client.post(f"/api/orders/{oid}/drawing-wizard/transfer-pending", json={})
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert sd["drawing_status"] == "TRANSFERRED"
    assert [f["key"] for f in sd["drawing_current_files"]] == [_key(oid, "p1.png")]


def _seed_wizard_pending(oid, *, versions=None):
    """작업실 대기 시트 1장(s-1)과 선택적 기존 버전 포인터를 직접 심는다(버전 불변)."""
    import copy

    from sqlalchemy.orm.attributes import flag_modified
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"] = {
        "sheets": [{"id": "s-1", "name": "시트1", "objects": []}],
        "pending": {"s-1": {"key": _key(oid, "p1.png"), "filename": "p1.png",
                            "sheet_name": "시트1"}},
        "versions": list(versions or []),
    }
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def test_transfer_pending_snapshot_is_part_of_transfer_write(client, storage, monkeypatch):
    """리뷰 P2 — 대기 시트 스냅샷(R2 업로드)이 전달 쓰기 **안에서**(커밋 전) 일어난다.

    예전에는 전달이 커밋(잠금 해제)된 뒤 잠금 없이 다시 읽고 업로드한 다음 structured_data
    를 통째로 되써서, 그 사이 커밋된 남의 쓰기를 지웠다. 업로드 순간 주문이 아직 전달 전
    상태(PENDING)여야 스냅샷과 전달이 한 트랜잭션 한 번의 +1 이다.
    """
    admin = _user("vb6_admin", "ADMIN", "CS")
    sales = _user("vb6_sales", "STAFF", "SALES")
    drafter = _user("vb6_draw", "STAFF", "DRAWING")
    oid = _order(sales[0], drafter[0], stage="CONFIRM", drawing_status="PENDING")
    _seed_wizard_pending(oid)
    seen = []
    orig_upload = storage.upload_file

    def _upload(file_obj, filename, folder="uploads"):
        seen.append((db_session.get(Order, oid).structured_data or {}).get("drawing_status"))
        return orig_upload(file_obj, filename, folder)

    monkeypatch.setattr(storage, "upload_file", _upload)

    before, _ = _state(oid)
    _as(client, drafter)
    r = client.post(f"/api/orders/{oid}/drawing-wizard/transfer-pending", json={})
    sd = _assert_bumped_and_stale_put_conflicts(client, admin, oid, before, r)
    assert seen == ["PENDING"], f"스냅샷 업로드가 전달 커밋 뒤에 일어났다: {seen}"
    dw = sd["drawing_wizard"]
    assert dw["pending"] == {}
    assert [v["sheet_id"] for v in dw["versions"]] == ["s-1"]
    assert sd["drawing_status"] == "TRANSFERRED"


def test_transfer_pending_prunes_stale_version_files_after_commit(client, storage, monkeypatch):
    """버전 30개 초과분의 R2 삭제는 커밋 **뒤**에 한다(롤백되면 포인터만 남고 파일이 사라지지 않게)."""
    sales = _user("vb7_sales", "STAFF", "SALES")
    drafter = _user("vb7_draw", "STAFF", "DRAWING")
    oid = _order(sales[0], drafter[0], stage="CONFIRM", drawing_status="PENDING")
    old = [{"v": i, "sheet_id": "s-1", "sheet_name": "시트1",
            "key": f"orders/{oid}/drawing_wizard/versions/v{i}_s-1.json"} for i in range(1, 31)]
    _seed_wizard_pending(oid, versions=old)
    at_delete = []
    orig_delete = storage.delete_file

    def _delete(key):
        db_session.expire_all()
        at_delete.append((db_session.get(Order, oid).structured_data or {}).get("drawing_status"))
        return orig_delete(key)

    monkeypatch.setattr(storage, "delete_file", _delete)
    _as(client, drafter)
    r = client.post(f"/api/orders/{oid}/drawing-wizard/transfer-pending", json={})
    assert r.status_code == 200, r.get_json()
    assert storage.deleted == [old[0]["key"]]
    assert at_delete == ["TRANSFERRED"]
    _, sd = _state(oid)
    versions = sd["drawing_wizard"]["versions"]
    assert len(versions) == 30 and versions[0]["v"] == 2 and versions[-1]["v"] == 31
