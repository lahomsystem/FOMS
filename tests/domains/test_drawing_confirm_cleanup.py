"""수령 확정 도면 목록 — 확정본은 전달 API 가 계산해 둔 현재본이고, 아무것도 지우지 않는다.

2026-09-29 정책 변경(사용자 결정): 이 파일의 옛 테스트는 "확정이 옛 도면을 지운다"와
"확정이 전달 이력으로 현재본을 다시 계산한다"를 단언했다. 둘 다 뒤집혔다.

* 지우기 → 안 지움: 전달 이력의 모든 files 를 지우던 정리가 수정요청 참고사진·첨부 탭 '도면'
  업로드까지 지웠고(C8·C8(a)), 커밋 전에 지워 롤백돼도 파일이 사라졌다(C8(b)).
* 재계산 → 현재본 그대로: 재계산(2026-06-24 ``589b5522e`` 가 확정 정리와 함께 들여옴)은 06-24
  이전 전달 API 가 수정 재전달을 [옛, 새] 로 **누적**하던 옛 데이터를 확정 때 고치려던 것이다.
  같은 커밋이 전달 API 자체를 고쳐 그 뒤로는 누적이 생기지 않는다. 대신 이력에는 전달 API 가
  판단에 쓴 입력(클라이언트 ``is_retransfer``, 전달 시점 상태)이 다 남지 않아 재계산이 전달 때와
  다른 답을 냈다(C8-X, CONFIRM_RECEIPT 너머 수정요청 — ``test_drawing_confirm_keeps_files.py``).
  확정은 영업이 화면에서 본 ``drawing_current_files`` 를 확정한다.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

import foms.services.drawing_confirm_cleanup as cleanup
import foms.services.storage as storage_module
from db import db_session
from models import Order, OrderAttachment, User


def _legacy_accumulated_sd(prefix: str) -> dict:
    """06-24 이전 전달 API 가 만든 누적 모양: 수정 재전달 APPEND 가 현재본을 [옛, 새] 로 남겼다."""
    old = {"key": f"{prefix}/old.pdf", "filename": "old.pdf"}
    new = {"key": f"{prefix}/new.pdf", "filename": "new.pdf"}
    return {
        "drawing_current_files": [old, new],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "mode": "APPEND", "files": [old], "previous_current_files": []},
            {"action": "REQUEST_REVISION", "files": []},
            {"action": "TRANSFER", "mode": "APPEND", "files": [new], "previous_current_files": [old]},
        ],
    }


def test_resolve_final_keeps_legacy_accumulated_current_files_as_shown():
    """옛 누적 데이터도 이력으로 다시 풀지 않는다 — 확정본은 화면에 보인 현재본 그대로다.

    옛 재계산은 이 모양을 [new] 로 줄였다. 06-24 이전 누적 주문이 아직 확정 전으로 남아 있다면
    [old, new] 로 확정된다 — 운영 잔존 여부는 읽기 전용 측정으로 따로 확인한다(브리프 보고).
    """
    final = cleanup.resolve_final_drawing_files(_legacy_accumulated_sd("orders/1"))

    assert [f["key"] for f in final] == ["orders/1/old.pdf", "orders/1/new.pdf"]


def test_resolve_final_drawing_files_multi_append_without_revision_keeps_all():
    """수정요청 없이 도면을 추가 전달하면 현재본 전부가 확정본이다."""
    structured_data = {
        "drawing_current_files": [
            {"key": "orders/2/a.pdf", "filename": "a.pdf"},
            {"key": "orders/2/b.pdf", "filename": "b.pdf"},
        ],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "mode": "APPEND",
             "files": [{"key": "orders/2/a.pdf", "filename": "a.pdf"}],
             "previous_current_files": []},
            {"action": "TRANSFER", "mode": "APPEND",
             "files": [{"key": "orders/2/b.pdf", "filename": "b.pdf"}],
             "previous_current_files": [{"key": "orders/2/a.pdf", "filename": "a.pdf"}]},
        ],
    }

    final = cleanup.resolve_final_drawing_files(structured_data)

    assert [f["key"] for f in final] == ["orders/2/a.pdf", "orders/2/b.pdf"]


def test_resolve_final_drawing_files_partial_replace_uses_transfer_result():
    """부분 교체 뒤 확정본 = 전달 API 가 계산해 둔 [a, b-v2](번호 순서 유지)."""
    structured_data = {
        "drawing_current_files": [
            {"key": "orders/3/a.pdf", "filename": "a.pdf"},
            {"key": "orders/3/b-v2.pdf", "filename": "b-v2.pdf"},
        ],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "mode": "APPEND",
             "files": [{"key": "orders/3/a.pdf", "filename": "a.pdf"},
                       {"key": "orders/3/b.pdf", "filename": "b.pdf"}],
             "previous_current_files": []},
            {"action": "REQUEST_REVISION", "files": []},
            {"action": "TRANSFER", "mode": "REPLACE", "replace_target_keys": ["orders/3/b.pdf"],
             "files": [{"key": "orders/3/b-v2.pdf", "filename": "b-v2.pdf"}],
             "previous_current_files": [{"key": "orders/3/a.pdf", "filename": "a.pdf"},
                                        {"key": "orders/3/b.pdf", "filename": "b.pdf"}]},
        ],
    }

    final = cleanup.resolve_final_drawing_files(structured_data)

    assert [f["key"] for f in final] == ["orders/3/a.pdf", "orders/3/b-v2.pdf"]
    assert final[1]["view_url"] == "/api/files/view/orders/3/b-v2.pdf"  # 정규화는 한다.
    assert cleanup.superseded_drawing_keys(structured_data) == frozenset({"orders/3/b.pdf"})


def test_superseded_keys_ignore_revision_photos_and_cancelled_transfers():
    """옛 도면 판정은 TRANSFER·CONFIRM_RECEIPT 만 본다 — 수정요청 참고사진은 도면이 아니다."""
    structured_data = {
        "drawing_current_files": [{"key": "orders/4/v2.png"}],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "files": [{"key": "orders/4/v1.png"}],
             "previous_current_files": []},
            {"action": "CONFIRM_RECEIPT", "files": [{"key": "orders/4/v1.png"}]},
            {"action": "REQUEST_REVISION",
             "files": [{"key": "orders/4/drawing_gateway/revisions/ref.jpg"}]},
            {"action": "TRANSFER", "files": [{"key": "orders/4/v2.png"}],
             "previous_current_files": [{"key": "orders/4/v1.png"}]},
            "깨진 항목",
        ],
    }

    assert cleanup.superseded_drawing_keys(structured_data) == frozenset({"orders/4/v1.png"})
    assert cleanup.superseded_drawing_keys(None) == frozenset()
    assert cleanup.superseded_drawing_keys({"drawing_current_files": [{"key": "x"}]}) == frozenset()


class _FailingDB:
    """확정 정리가 DB 를 조금이라도 건드리면 실패하는 대역."""

    def __getattr__(self, name):
        raise AssertionError(f"확정 정리가 DB 를 건드렸다: db.{name}")


def test_finalize_on_confirm_rewrites_current_files_without_touching_db():
    """옛 테스트는 여기서 옛 도면 행·파일 삭제를 단언했다 — 이제 DB·스토리지를 건드리지 않는다."""
    structured_data = _legacy_accumulated_sd("orders/9")

    final_files, deleted_count = cleanup.finalize_drawing_files_on_confirm(
        _FailingDB(), 9, structured_data)

    assert [f["key"] for f in final_files] == ["orders/9/old.pdf", "orders/9/new.pdf"]
    assert structured_data["drawing_current_files"] == final_files
    assert deleted_count == 0


def _login_sales_user(client):
    user = User(username="drawing_confirm_sales", password=generate_password_hash("pass"),
                role="ADMIN", team="SALES", name="영업담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


class _NoDeleteStorage:
    def __init__(self):
        self.deleted_keys: list[str] = []

    def delete_file(self, key):
        self.deleted_keys.append(key)
        return True


def test_confirm_drawing_receipt_api_keeps_replaced_drawing_row(client, monkeypatch):
    """API 확정: 현재본 [new] 확정, 교체된 old 행·파일은 남는다(옛 테스트는 삭제를 단언)."""
    storage = _NoDeleteStorage()
    monkeypatch.setattr(storage_module, "_storage_instance", storage)
    _login_sales_user(client)

    old = {"key": "orders/77/old.pdf", "filename": "old.pdf"}
    new = {"key": "orders/77/new.pdf", "filename": "new.pdf"}
    structured_data = {
        "parties": {"customer": {"name": "고객"}, "manager": {"name": "영업담당"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "TRANSFERRED",
        "assignments": {"sales_assignee_user_ids": []},
        "drawing_current_files": [new],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "mode": "APPEND", "files": [old], "previous_current_files": []},
            {"action": "REQUEST_REVISION", "files": []},
            {"action": "TRANSFER", "mode": "REPLACE", "replace_target_keys": [old["key"]],
             "files": [new], "previous_current_files": [old]},
        ],
    }
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="고객",
                  phone="010-0000-0000", address="Seoul", product="북박이", status="DRAWING",
                  manager_name="영업담당", is_erp_order=True, structured_data=structured_data)
    db_session.add(order)
    db_session.flush()
    for entry in (old, new):
        db_session.add(OrderAttachment(order_id=order.id, filename=entry["filename"],
                                       file_type="file", category="drawing",
                                       storage_key=entry["key"]))
    db_session.commit()
    order_id = order.id

    res = client.post(f"/api/orders/{order_id}/confirm-drawing-receipt", json={})
    assert res.status_code == 200
    assert res.get_json()["success"] is True

    db_session.expire_all()
    order = db_session.get(Order, order_id)
    assert [f["key"] for f in order.structured_data["drawing_current_files"]] == [new["key"]]
    # 도면 축 확정은 전이 뒤다 — 확정이 끝났다면 단계도 이미 CONFIRM 이다.
    assert order.structured_data["workflow"]["stage"] == "CONFIRM"
    remaining = {
        row.storage_key for row in db_session.query(OrderAttachment).filter(
            OrderAttachment.order_id == order_id, OrderAttachment.category == "drawing").all()
    }
    assert remaining == {old["key"], new["key"]}
    assert storage.deleted_keys == []
