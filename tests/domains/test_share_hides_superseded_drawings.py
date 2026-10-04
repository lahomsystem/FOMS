"""고객 공유 링크는 교체된 옛 도면을 보여 주지 않는다(2026-09-29, C8 동반 수정 · 호환 점검표 C2).

수령 확정이 옛 도면을 지우지 않게 되면서(``test_drawing_confirm_keeps_files.py``) 옛 도면
첨부 행이 남는다. 고객 링크의 수집 함수(``foms/api/share.py`` ``_collect_drawing_files`` —
열람·ZIP·합본 PNG 공용)는 ``category='drawing'`` 첨부 전부를 모으므로, 규칙이 없으면 옛
도면이 고객에게 영원히 보인다. 규칙: 전달 이력(TRANSFER·CONFIRM_RECEIPT)에 올랐지만 지금
``drawing_current_files`` 에 없는 key 는 뺀다. 전달 이력에 한 번도 오르지 않은 첨부 탭 '도면'
업로드는 보인다. 같은 규칙으로 확정 전 재전달 직후 "1차·2차 섞여 보임"도 사라진다.

실제 라우트(전달·수정요청·확정·공유 열람)를 탄다. 스토리지는 전역 인스턴스를 대역으로 바꾼다.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from types import SimpleNamespace

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

import foms.api.files.order_routes as order_routes
import foms.api.share as share_routes
import foms.services.storage as storage_module
from db import db_session
from foms.services import audit_writer
from foms.services import order_share as osvc
from models import Order, OrderAttachment, User


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


class _ShareStorage:
    """전달 흐름(업로드)과 공유 열람(presign·원본 읽기)을 함께 받는 r2 대역."""

    storage_type = "r2"

    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.read_keys: list[str] = []
        self.deleted_keys: list[str] = []
        self._png = _png_bytes()

    def upload_file(self, file_obj, filename, folder="uploads"):
        key = f"{folder}/s{len(self.uploaded) + 1}_{filename}"
        self.uploaded.append(key)
        return {"success": True, "key": key, "url": f"/fake/{key}",
                "filename": key.rsplit("/", 1)[-1]}

    def get_file_type(self, filename: str) -> str:
        return "image" if filename.lower().endswith((".png", ".jpg", ".jpeg")) else "file"

    def object_exists(self, key: str) -> bool:
        return key in self.uploaded

    def delete_file(self, key: str) -> bool:
        self.deleted_keys.append(key)
        return True

    def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
        return f"https://r2.example/{key}?exp={expires_in}"

    def read_file_bytes(self, key: str) -> bytes:
        self.read_keys.append(key)
        return self._png


@pytest.fixture
def storage(monkeypatch):
    fake = _ShareStorage()
    monkeypatch.setattr(storage_module, "_storage_instance", fake)
    monkeypatch.setattr(order_routes, "ASYNC_ATTACHMENT_THUMBNAIL", False)
    audit_writer.reset_dedupe_cache()
    yield fake
    audit_writer.reset_dedupe_cache()


def _make_user(username: str, *, role: str, team: str) -> SimpleNamespace:
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
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="공유고객",
        phone="010-0000-0000", address="Seoul", product="붙박이장", status="DRAWING",
        manager_name=sales.name, is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "공유고객"}, "manager": {"name": sales.name}},
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


def _transfer(client, order_id: int, key: str, **extra) -> None:
    body = {"note": "전달", "files": [{"key": key, "filename": key.rsplit("/", 1)[-1]}], **extra}
    res = client.post(f"/api/orders/{order_id}/transfer-drawing", json=body)
    assert res.status_code == 200, res.get_json()


def _upload_attachment_tab_drawing(client, order_id: int) -> str:
    res = client.post(
        f"/api/orders/{order_id}/attachments",
        # 도면팀 최종본이 있으면 확인(ack)이 필요하다(drawing_upload_guard, 2026-10-04).
        data={"file": (io.BytesIO(b"\x89PNG sketch"), "site_sketch.png"), "category": "drawing",
              "ack_drawing_final": "1"},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()["attachment"]["storage_key"]


def _revision_then_retransfer(client, sales, drafter, order_id: int, v1: str, v2: str) -> None:
    _act_as(client, sales)
    res = client.post(f"/api/orders/{order_id}/request-revision",
                      json={"note": "문 손잡이 위치 변경", "files": []})
    assert res.status_code == 200, res.get_json()
    _act_as(client, drafter)
    req = [h for h in _sd(order_id)["drawing_transfer_history"]
           if h.get("action") == "REQUEST_REVISION"][-1]
    res = client.post(f"/api/orders/{order_id}/request-revision-check",
                      json={"request_at": req["at"], "by_user_id": req["by_user_id"],
                            "checked": True})
    assert res.status_code == 200, res.get_json()
    _transfer(client, order_id, v2, mode="REPLACE", replace_target_keys=[v1])


def _share_token(order_id: int) -> str:
    _row, token = osvc.create_share_token(db_session, order_id, "drawing")
    db_session.commit()
    return token


def _customer_sees(client, storage, token: str) -> tuple[str, set[str], set[str]]:
    """열람 본문 · ZIP 에 담긴 key · 합본 PNG 에 쓰인 key."""
    body = client.get(f"/s/{token}").get_data(as_text=True)
    storage.read_keys.clear()
    res = client.get(f"/s/{token}/drawings.zip")
    assert res.status_code == 200, res.get_data(as_text=True)[:200]
    zipfile.ZipFile(io.BytesIO(res.get_data()))  # 온전한 zip
    zip_keys = set(storage.read_keys)
    storage.read_keys.clear()
    res = client.get(f"/s/{token}/drawings-sheet.png")
    assert res.status_code == 200, res.get_data(as_text=True)[:200]
    return body, zip_keys, set(storage.read_keys)


def test_customer_link_hides_replaced_drawing_before_and_after_confirm(client, storage):
    """재전달 뒤 확정 전·확정 뒤 모두: 옛 도면은 안 보이고 수정본·첨부 탭 업로드는 보인다."""
    sales = _make_user("sh_sales", role="STAFF", team="SALES")
    drafter = _make_user("sh_drafter", role="STAFF", team="DRAWING")
    order_id = _make_order(sales, drafter)
    v1 = f"orders/{order_id}/drawing_wizard/exports/v1.png"
    v2 = f"orders/{order_id}/drawing_wizard/exports/v2.png"
    _act_as(client, drafter)
    _transfer(client, order_id, v1)
    _act_as(client, sales)
    sketch = _upload_attachment_tab_drawing(client, order_id)
    _revision_then_retransfer(client, sales, drafter, order_id, v1, v2)
    token = _share_token(order_id)

    # 확정 전(TRANSFERRED) — 예전에는 여기서 1차·2차가 섞여 보였다(C2).
    body, zip_keys, sheet_keys = _customer_sees(client, storage, token)
    assert v2 in body and sketch in body
    assert v1 not in body, "확정 전 고객 링크에 교체된 1차 도면이 보인다"
    assert zip_keys == {v2, sketch}
    assert sheet_keys == {v2, sketch}

    _act_as(client, sales)
    res = client.post(f"/api/orders/{order_id}/confirm-drawing-receipt", json={})
    assert res.status_code == 200, res.get_json()
    # 옛 도면 행은 지워지지 않았다 — 가린 것은 수집 규칙이다.
    assert db_session.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id, OrderAttachment.storage_key == v1).count() == 1

    body, zip_keys, sheet_keys = _customer_sees(client, storage, token)
    assert v2 in body and sketch in body
    assert v1 not in body, "확정 뒤 고객 링크에 교체된 1차 도면이 보인다"
    assert zip_keys == {v2, sketch}
    assert sheet_keys == {v2, sketch}
    assert storage.deleted_keys == []


def test_collect_drawing_files_ignores_other_order_keys_and_rows(app, storage):
    """다른 주문의 key(현재본에 끼어든 것)·다른 주문의 첨부 행은 수집되지 않는다."""
    mine = Order(received_date="2026-09-29", customer_name="내 주문", phone="010",
                 address="Seoul", product="장", is_erp_order=True, structured_data={})
    other = Order(received_date="2026-09-29", customer_name="남 주문", phone="010",
                  address="Seoul", product="장", is_erp_order=True, structured_data={})
    db_session.add_all([mine, other])
    db_session.flush()
    my_key = f"orders/{mine.id}/drawing_wizard/exports/now.png"
    their_key = f"orders/{other.id}/drawing_wizard/exports/theirs.png"
    their_row_key = f"orders/{other.id}/attachments/theirs_row.png"
    db_session.add(OrderAttachment(order_id=other.id, filename="theirs_row.png",
                                   file_type="image", category="drawing",
                                   storage_key=their_row_key))
    mine.structured_data = {
        "drawing_current_files": [{"key": my_key}, {"key": their_key}],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "files": [{"key": my_key}], "previous_current_files": []},
        ],
    }
    db_session.commit()

    keys = [f["key"] for f in share_routes._collect_drawing_files(mine)]

    assert keys == [my_key]


def test_end_to_end_photo_revision_untargeted_retransfer_confirm_then_customer_link(
    client, storage,
):
    """새 정책 끝-끝(통합 검증 2026-09-29): 한 주문으로 전 과정을 실제 라우트로 밟는다.

    전달(v1) → 수정요청(참고사진) → 반영 체크 → **대상 없는** 재전달(v2, 태블릿 시트 전달 모양 —
    서버 기록 ``mode='REPLACE'``·대상 None) → 수령 확정 → 고객 링크(열람·ZIP·합본 PNG).

    기대: 참고사진은 지워지지 않고 이력에 남는다 · 교체된 v1 은 행이 남지만 고객 링크에서 빠진다 ·
    현재본(=확정본)은 수정본 v2 하나뿐이다. C8(사진 삭제)·C8-X(옛 도면 부활)·C2(섞여 보임)가
    한 흐름에서 동시에 다시 나타나지 않는지 본다.
    """
    sales = _make_user("e2e_sales", role="STAFF", team="SALES")
    drafter = _make_user("e2e_drafter", role="STAFF", team="DRAWING")
    order_id = _make_order(sales, drafter)
    v1 = f"orders/{order_id}/drawing_wizard/exports/v1.png"
    v2 = f"orders/{order_id}/drawing_wizard/exports/v2.png"

    _act_as(client, drafter)
    _transfer(client, order_id, v1)

    _act_as(client, sales)
    res = client.post(
        f"/api/orders/{order_id}/drawing-gateway-upload",
        data={"file": (io.BytesIO(b"\xff\xd8\xff\xe0 ref"), "ref_photo.jpg")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200, res.get_json()
    ref = res.get_json()["file"]
    ref_key = ref["key"]
    assert ref_key.startswith(f"orders/{order_id}/drawing_gateway/revisions/")
    res = client.post(f"/api/orders/{order_id}/request-revision",
                      json={"note": "손잡이를 사진처럼", "files": [ref]})
    assert res.status_code == 200, res.get_json()
    assert _sd(order_id)["drawing_status"] == "RETURNED"

    _act_as(client, drafter)
    req = [h for h in _sd(order_id)["drawing_transfer_history"]
           if h.get("action") == "REQUEST_REVISION"][-1]
    res = client.post(f"/api/orders/{order_id}/request-revision-check",
                      json={"request_at": req["at"], "by_user_id": req["by_user_id"],
                            "checked": True})
    assert res.status_code == 200, res.get_json()
    _transfer(client, order_id, v2, mode="APPEND")  # 교체 대상 없음
    sd = _sd(order_id)
    last = sd["drawing_transfer_history"][-1]
    assert (last["action"], last["mode"], last["replace_target_keys"]) == ("TRANSFER", "REPLACE", None)
    assert [f["key"] for f in sd["drawing_current_files"]] == [v2]

    _act_as(client, sales)
    res = client.post(f"/api/orders/{order_id}/confirm-drawing-receipt", json={})
    assert res.status_code == 200, res.get_json()

    # 현재본 = 수정본만(확정본·CONFIRM_RECEIPT 기록 모두).
    sd = _sd(order_id)
    assert sd["drawing_status"] == "CONFIRMED"
    assert [f["key"] for f in sd["drawing_current_files"]] == [v2]
    confirm_entry = sd["drawing_transfer_history"][-1]
    assert confirm_entry["action"] == "CONFIRM_RECEIPT"
    assert [f["key"] for f in confirm_entry["files"]] == [v2]

    # 사진 남음 — 스토리지에서 아무것도 지우지 않았고, 수정요청 이력이 사진을 계속 가리킨다.
    assert storage.deleted_keys == []
    assert ref_key in storage.uploaded
    revision = [h for h in sd["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"]
    assert [f["key"] for f in revision[-1]["files"]] == [ref_key]

    # 옛 도면 v1 은 행이 남지만(타임라인·비교 탭 링크) 고객 링크 수집에서는 빠진다.
    db_session.expire_all()
    row_keys = {r.storage_key for r in db_session.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id).all()}
    assert {v1, v2} <= row_keys
    order = db_session.get(Order, order_id)
    assert [f["key"] for f in share_routes._collect_drawing_files(order)] == [v2]

    body, zip_keys, sheet_keys = _customer_sees(client, storage, _share_token(order_id))
    assert v2 in body
    assert v1 not in body, "확정 뒤 고객 링크에 교체된 1차 도면이 보인다"
    assert ref_key not in body, "영업 참고사진이 고객 링크에 섞였다"
    assert zip_keys == {v2}
    assert sheet_keys == {v2}
