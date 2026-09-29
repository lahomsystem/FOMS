"""수령 확정은 파일을 지우지 않는다 — 회귀 테스트(C8·C8(a)·C8(b)·C8-X, 2026-09-29).

사용자 결정(2026-09-29): 확정할 때 첨부 탭 '도면' 업로드도, 교체된 옛 도면도, 수정요청
참고사진도 남긴다. 확정이 정하는 것은 ``drawing_current_files`` 와 ``CONFIRM_RECEIPT.files``
뿐이다(``foms/services/drawing_confirm_cleanup.py``).

지우던 시절의 결함(원장 ``docs/plans/2026-09-29-drawing-defects-verification-ledger.md``):

* C8: 확정 정리가 전달 이력의 **모든** 항목 files 를 삭제 후보로 모아 수정요청 참고사진
  (``orders/<id>/drawing_gateway/revisions/``, 첨부 행 없음)을 스토리지에서 지웠다.
* C8(a): 첨부 탭 '도면' 분류 업로드(``orders/<id>/attachments/``)를 행째·파일째 지웠다.
* C8(b): 스토리지 삭제가 라우트의 ``db.commit()`` 보다 먼저라, 커밋이 실패해도 파일만 사라졌다.
* C8-X: 확정이 현재본을 전달 이력으로 **다시 계산**하면서 대상 없는 재전달
  (``mode='REPLACE'``·대상 None)을 "맨 뒤에 추가"로 풀어 옛 도면을 되살렸다. 이제 확정은
  전달 API 가 계산해 둔 ``drawing_current_files`` 를 그대로 쓴다.

모든 테스트는 실제 Flask 라우트를 탄다. 스토리지는 전역 인스턴스를 기록용 대역으로 바꿔
**어느 모듈이 지우든** ``deleted_keys`` 에 잡히게 했다.
"""

from __future__ import annotations

import io
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

import foms.api.files.order_routes as order_routes
import foms.services.drawing_confirm_cleanup as cleanup
import foms.services.storage as storage_module
from db import db_session
from models import Order, OrderAttachment, User


class _RecordingStorage:
    """업로드 키를 만들어 주고, 지운 키를 기록하는 스토리지 대역."""

    storage_type = "r2"

    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.deleted_keys: list[str] = []
        self._seq = 0

    def upload_file(self, file_obj, filename, folder="uploads"):
        self._seq += 1
        key = f"{folder}/c8_{self._seq}_{filename}"
        self.uploaded.append(key)
        return {"success": True, "key": key, "url": f"/fake/{key}",
                "filename": key.rsplit("/", 1)[-1]}

    def get_file_type(self, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            return "image"
        if ext in ("mp4", "mov", "avi", "mkv", "webm"):
            return "video"
        return "file"

    def object_exists(self, key: str) -> bool:
        return key in self.uploaded

    def delete_file(self, key: str) -> bool:
        self.deleted_keys.append(key)
        return True


@pytest.fixture
def storage(monkeypatch):
    """모든 ``get_storage()`` 호출이 같은 기록용 대역을 돌려주게 한다."""
    fake = _RecordingStorage()
    monkeypatch.setattr(storage_module, "_storage_instance", fake)
    # 비동기 썸네일 스레드를 띄우지 않는다 — 결정성.
    monkeypatch.setattr(order_routes, "ASYNC_ATTACHMENT_THUMBNAIL", False)
    return fake


def _make_user(username: str, *, role: str, team: str) -> SimpleNamespace:
    """사용자를 만들고 요청 사이 세션 분리에 안전한 값 묶음을 돌려준다."""
    user = User(username=username, password=generate_password_hash("pass"), role=role,
                team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=user.role, name=user.name)


def _act_as(client, user: SimpleNamespace) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(sales: SimpleNamespace, drafter: SimpleNamespace) -> int:
    """도면 단계 ERP 주문(영업 담당·도면 담당 지정, 아직 전달 전)."""
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="C8고객",
        phone="010-0000-0000", address="Seoul", product="붙박이장", status="DRAWING",
        manager_name=sales.name, is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "C8고객"}, "manager": {"name": sales.name}},
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "PENDING",
            "assignments": {"sales_assignee_user_ids": [sales.id],
                            "drawing_assignee_user_ids": [drafter.id]},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _sd(order_id: int) -> dict:
    db_session.expire_all()
    return dict(db_session.get(Order, order_id).structured_data or {})


def _row_keys(order_id: int) -> set[str]:
    db_session.expire_all()
    return {row.storage_key for row in db_session.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id).all()}


def _wizard_key(order_id: int, name: str) -> str:
    """도면 마법사 산출물 경로(OrderAttachment 행 없음 — 전달이 행을 만든다)."""
    return f"orders/{order_id}/drawing_wizard/exports/{name}"


def _transfer(client, order_id: int, key: str, note: str, *,
              mode: str = "APPEND", replace_target_keys: list[str] | None = None) -> None:
    res = client.post(
        f"/api/orders/{order_id}/transfer-drawing",
        json={"note": note, "mode": mode, "replace_target_keys": replace_target_keys,
              "files": [{"key": key, "filename": key.rsplit("/", 1)[-1]}]},
    )
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["success"] is True


def _upload_revision_reference(client, order_id: int) -> dict:
    """영업이 수정요청 창에서 참고사진을 올린다(창구 업로드 — 첨부 행 없음)."""
    res = client.post(
        f"/api/orders/{order_id}/drawing-gateway-upload",
        data={"file": (io.BytesIO(b"\xff\xd8\xff\xe0 fake-jpeg"), "ref_photo.jpg")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()["file"]


def _request_revision(client, order_id: int, files: list[dict]) -> None:
    res = client.post(f"/api/orders/{order_id}/request-revision",
                      json={"note": "손잡이 위치를 사진처럼 바꿔 주세요", "files": files})
    assert res.status_code == 200, res.get_json()


def _check_latest_revision(client, order_id: int) -> None:
    """도면팀이 수정요청을 '반영 완료'로 체크한다(재전달 전제)."""
    req = [h for h in _sd(order_id)["drawing_transfer_history"]
           if h.get("action") == "REQUEST_REVISION"][-1]
    res = client.post(f"/api/orders/{order_id}/request-revision-check",
                      json={"request_at": req["at"], "by_user_id": req["by_user_id"],
                            "checked": True})
    assert res.status_code == 200, res.get_json()


def _confirm(client, order_id: int, body: dict | None = None):
    return client.post(f"/api/orders/{order_id}/confirm-drawing-receipt", json=body or {})


def _run_until_retransfer(client, sales, drafter, order_id: int, *, with_reference_photo: bool,
                          targeted: bool = True) -> tuple[str, str, str | None]:
    """TRANSFER(1차) → REQUEST_REVISION(참고사진) → 체크 → TRANSFER(수정본) — 전부 실제 라우트.

    targeted=True: 작업실·ERP 대시보드의 교체 대상 지정 경로(``replace_target_keys=[v1]``).
    targeted=False: 태블릿 '시트 전달'과 같은 대상 없는 APPEND — 서버가 ``mode='REPLACE'``·대상
    없음으로 기록하고 현재본을 [수정본] 으로 바꾼다.
    """
    v1 = _wizard_key(order_id, "v1.png")
    v2 = _wizard_key(order_id, "v2.png")
    _act_as(client, drafter)
    _transfer(client, order_id, v1, "1차 전달")
    _act_as(client, sales)
    ref_key = None
    files: list[dict] = []
    if with_reference_photo:
        ref = _upload_revision_reference(client, order_id)
        ref_key = ref["key"]
        files = [ref]
    _request_revision(client, order_id, files)
    _act_as(client, drafter)
    _check_latest_revision(client, order_id)
    if targeted:
        _transfer(client, order_id, v2, "수정본 전달", mode="REPLACE", replace_target_keys=[v1])
    else:
        _transfer(client, order_id, v2, "수정본 전달", mode="APPEND")
    assert [f["key"] for f in _sd(order_id)["drawing_current_files"]] == [v2]
    return v1, v2, ref_key


# ---------------------------------------------------------------------------
# C8 — 수정요청 참고사진·교체된 옛 도면을 지우지 않는다
# ---------------------------------------------------------------------------


def test_confirm_receipt_keeps_revision_photo_and_replaced_drawing(client, storage):
    """재전달 뒤 확정: 현재본은 수정본, 스토리지·첨부 행은 하나도 지우지 않는다."""
    sales = _make_user("c8_sales", role="STAFF", team="SALES")
    drafter = _make_user("c8_drafter", role="STAFF", team="DRAWING")
    order_id = _make_order(sales, drafter)
    v1, v2, ref_key = _run_until_retransfer(
        client, sales, drafter, order_id, with_reference_photo=True)
    assert ref_key and ref_key.startswith(f"orders/{order_id}/drawing_gateway/revisions/")

    _act_as(client, sales)
    res = _confirm(client, order_id)
    assert res.status_code == 200, res.get_json()

    sd = _sd(order_id)
    assert sd["drawing_status"] == "CONFIRMED"
    assert [f["key"] for f in sd["drawing_current_files"]] == [v2]
    confirm_entry = sd["drawing_transfer_history"][-1]
    assert confirm_entry["action"] == "CONFIRM_RECEIPT"
    assert [f["key"] for f in confirm_entry["files"]] == [v2]
    # 이력의 수정요청 항목은 확정 뒤에도 참고사진을 가리키고, 그 파일은 남아 있다.
    revision = [h for h in sd["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"]
    assert [f["key"] for f in revision[0]["files"]] == [ref_key]
    assert storage.deleted_keys == [], f"확정이 파일을 지웠다: {storage.deleted_keys}"
    # 교체된 1차 도면 행도 남는다(타임라인·비교 탭 링크가 계속 열린다 — M15).
    assert {v1, v2} <= _row_keys(order_id)


def test_admin_override_confirm_while_returned_keeps_revision_photo(client, storage):
    """관리자 강제 확정(수정요청 중): 현재본 1차 도면 그대로, 참고사진도 지우지 않는다."""
    admin = _make_user("c8o_admin", role="ADMIN", team="SALES")
    drafter = _make_user("c8o_drafter", role="STAFF", team="DRAWING")
    order_id = _make_order(admin, drafter)
    v1 = _wizard_key(order_id, "v1.png")
    _act_as(client, drafter)
    _transfer(client, order_id, v1, "1차 전달")
    _act_as(client, admin)
    ref = _upload_revision_reference(client, order_id)
    _request_revision(client, order_id, [ref])
    assert _sd(order_id)["drawing_status"] == "RETURNED"

    res = _confirm(client, order_id, {"admin_override": True,
                                      "override_reason": "현장 일정상 현재본으로 확정"})
    assert res.status_code == 200, res.get_json()
    assert [f["key"] for f in _sd(order_id)["drawing_current_files"]] == [v1]
    assert storage.deleted_keys == [], f"강제 확정이 파일을 지웠다: {storage.deleted_keys}"


def test_finalize_service_touches_no_db_row_or_storage(app, storage):
    """서비스 직접 호출: 확정본 = 현재본, 삭제 수 0, 첨부 행·스토리지 무변화."""
    order = Order(received_date="2026-09-29", customer_name="서비스", phone="010",
                  address="Seoul", product="장", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.flush()
    oid = order.id
    ref_key = f"orders/{oid}/drawing_gateway/revisions/20260929_ref.jpg"
    v1, v2 = _wizard_key(oid, "v1.png"), _wizard_key(oid, "v2.png")
    for key in (v1, v2):
        db_session.add(OrderAttachment(order_id=oid, filename=key.rsplit("/", 1)[-1],
                                       file_type="image", category="drawing", storage_key=key))
    db_session.commit()
    structured_data = {
        "drawing_current_files": [{"key": v2, "filename": "v2.png"}],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "mode": "APPEND",
             "files": [{"key": v1, "filename": "v1.png"}], "previous_current_files": []},
            {"action": "REQUEST_REVISION", "files": [{"key": ref_key, "filename": "ref.jpg"}]},
            {"action": "TRANSFER", "mode": "REPLACE", "replace_target_keys": [v1],
             "files": [{"key": v2, "filename": "v2.png"}],
             "previous_current_files": [{"key": v1, "filename": "v1.png"}]},
        ],
    }

    final_files, deleted_count = cleanup.finalize_drawing_files_on_confirm(
        db_session, oid, structured_data)
    db_session.commit()

    assert [f["key"] for f in final_files] == [v2]
    assert structured_data["drawing_current_files"] == final_files
    assert deleted_count == 0
    assert storage.deleted_keys == []
    assert _row_keys(oid) == {v1, v2}


# ---------------------------------------------------------------------------
# C8-X — 확정은 전달 API 가 계산해 둔 현재본을 그대로 확정한다
# ---------------------------------------------------------------------------


def test_confirm_after_untargeted_retransfer_keeps_only_revised_drawing(client, storage):
    """대상 없는 재전달(서버 기록 ``mode='REPLACE'``·대상 None) 뒤 확정 = [수정본]."""
    sales = _make_user("c8x_sales", role="STAFF", team="SALES")
    drafter = _make_user("c8x_drafter", role="STAFF", team="DRAWING")
    order_id = _make_order(sales, drafter)
    v1, v2, _ = _run_until_retransfer(
        client, sales, drafter, order_id, with_reference_photo=False, targeted=False)
    last = _sd(order_id)["drawing_transfer_history"][-1]
    assert (last["mode"], last["replace_target_keys"]) == ("REPLACE", None)  # 서버가 기록한 모양

    _act_as(client, sales)
    res = _confirm(client, order_id)
    assert res.status_code == 200, res.get_json()
    saved = [f["key"] for f in _sd(order_id)["drawing_current_files"]]
    assert saved == [v2], f"수령 확정이 교체된 옛 도면을 되살렸다: {saved}"


def test_confirm_after_append_transfer_past_earlier_confirm_keeps_both(client, storage):
    """이력 재계산이 틀리는 두 번째 모양: 수정요청 → 강제 확정 → '추가' 전달 → 확정.

    전달 API 는 상태가 CONFIRMED 라 재전달이 아니라고 보고 [v1, v2] 로 **추가**했다(영업도
    그 두 장을 보고 확정한다). 옛 재계산은 수정요청을 CONFIRM_RECEIPT 너머까지 거슬러 찾아
    재전달로 풀고 [v2] 만 남긴 뒤 v1 을 지웠다. 확정본은 화면에 보인 [v1, v2] 여야 한다.
    """
    admin = _make_user("c8y_admin", role="ADMIN", team="SALES")
    drafter = _make_user("c8y_drafter", role="STAFF", team="DRAWING")
    order_id = _make_order(admin, drafter)
    v1, v2 = _wizard_key(order_id, "v1.png"), _wizard_key(order_id, "v2.png")
    _act_as(client, drafter)
    _transfer(client, order_id, v1, "1차 전달")
    _act_as(client, admin)
    _request_revision(client, order_id, [])
    res = _confirm(client, order_id, {"admin_override": True, "override_reason": "일정상 확정"})
    assert res.status_code == 200, res.get_json()
    _act_as(client, drafter)
    _transfer(client, order_id, v2, "추가 도면", mode="APPEND")
    assert [f["key"] for f in _sd(order_id)["drawing_current_files"]] == [v1, v2]

    _act_as(client, admin)
    res = _confirm(client, order_id)
    assert res.status_code == 200, res.get_json()
    assert [f["key"] for f in _sd(order_id)["drawing_current_files"]] == [v1, v2]
    assert storage.deleted_keys == []


# ---------------------------------------------------------------------------
# C8(a) — 첨부 탭 '도면' 분류 업로드
# ---------------------------------------------------------------------------


def test_confirm_receipt_keeps_attachment_tab_drawing_upload(client, storage):
    """주문 첨부 탭에서 '도면' 분류로 올린 사진은 확정 뒤에도 행·파일 모두 남는다."""
    sales = _make_user("c8a_sales", role="STAFF", team="SALES")
    drafter = _make_user("c8a_drafter", role="STAFF", team="DRAWING")
    order_id = _make_order(sales, drafter)
    v1 = _wizard_key(order_id, "v1.png")
    _act_as(client, drafter)
    _transfer(client, order_id, v1, "1차 전달")

    _act_as(client, sales)
    res = client.post(
        f"/api/orders/{order_id}/attachments",
        data={"file": (io.BytesIO(b"\xff\xd8\xff\xe0 sketch"), "site_sketch.jpg"),
              "category": "drawing"},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200, res.get_json()
    sketch_key = res.get_json()["attachment"]["storage_key"]
    assert sketch_key.startswith(f"orders/{order_id}/attachments/")

    res = _confirm(client, order_id)
    assert res.status_code == 200, res.get_json()
    assert {v1, sketch_key} <= _row_keys(order_id)
    assert storage.deleted_keys == []


# ---------------------------------------------------------------------------
# C8(b) — 커밋이 실패해도 스토리지는 그대로
# ---------------------------------------------------------------------------


@pytest.fixture
def fail_confirm_commit():
    """도면 상태를 CONFIRMED 로 쓰는 flush(=라우트의 db.commit)를 실패시킨다."""
    fired: list[int] = []

    def _boom(session, flush_context, instances):
        for obj in session.dirty:
            sd = getattr(obj, "structured_data", None) if isinstance(obj, Order) else None
            if isinstance(sd, dict) and sd.get("drawing_status") == "CONFIRMED":
                fired.append(obj.id)
                raise RuntimeError("C8b: 커밋 실패 모사(DB 오류)")

    event.listen(db_session, "before_flush", _boom)
    try:
        yield fired
    finally:
        event.remove(db_session, "before_flush", _boom)


def test_commit_failure_on_confirm_leaves_storage_and_rows(client, storage, fail_confirm_commit):
    """확정 커밋이 실패하면 DB 가 되돌아가고, 스토리지는 처음부터 건드리지 않았다."""
    sales = _make_user("c8b_sales", role="STAFF", team="SALES")
    drafter = _make_user("c8b_drafter", role="STAFF", team="DRAWING")
    order_id = _make_order(sales, drafter)
    v1, v2, _ = _run_until_retransfer(
        client, sales, drafter, order_id, with_reference_photo=False)

    _act_as(client, sales)
    res = _confirm(client, order_id)
    assert res.status_code == 500, res.get_json()  # 전제: 커밋이 실패했다.
    assert fail_confirm_commit == [order_id]

    assert _sd(order_id)["drawing_status"] == "TRANSFERRED"  # DB 는 롤백됐다.
    assert {v1, v2} <= _row_keys(order_id)
    assert storage.deleted_keys == []
