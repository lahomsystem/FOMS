"""M7 — 전달 취소가 아직 쓰는 파일을 지우지 않는다(2b, SPEC §4.5) + M2 취소 흐름 조합(§4.4).

전달 취소는 "이번 전달이 새로 들여온 key" 의 **행**은 복원된 현재본·남은 이력이 가리키지
않으면 지우고, **파일**은 취소 뒤에도 아무도 안 쓰는 것만 7일 유예로 회수 예약한다.
STORAGE_DELETE 핸들러는 7일 뒤 다시 확인해 그 사이 다시 쓰이게 된 key 는 지우지 않는다.

프로브 P6(같은 key 두 번 전달 → 취소가 복원된 현재본 파일을 예약)을 ``drawing/`` 판과
``drawing_wizard/exports/`` 판 두 벌로 옮겼다(두 판 모두 폴더 판정은 통과하는 key 라
폴더 판정 때문에 초록이 되는 일이 없다).
"""
from __future__ import annotations

import datetime
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
import foms.services.storage_delete_handler as handler_mod
from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.storage_delete_handler import handle_storage_delete
from models import DomainSideEffectOutbox, Order, OrderAttachment, User


class _Storage:
    def __init__(self):
        self.deleted_keys: list[str] = []

    def delete_file(self, key):
        self.deleted_keys.append(key)
        return True


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(handler_mod, "get_storage", lambda: fake)
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)
    return fake


def _user(name, role, team):
    u = User(username=name, password=generate_password_hash("pw"), role=role, team=team,
             name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return {"id": u.id, "username": u.username, "role": u.role}


def _as(client, who):
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = who["id"], who["username"], who["role"]


def _order(sales, drafter, extra_sd=None):
    sd = {
        "parties": {"customer": {"name": "M7고객"}, "manager": {"name": "m7s"}},
        "workflow": {"stage": "DRAWING"}, "drawing_status": "PENDING",
        "assignments": {"sales_assignee_user_ids": [sales["id"]],
                        "drawing_assignee_user_ids": [drafter["id"]]},
    }
    sd.update(extra_sd or {})
    o = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="M7고객",
              phone="010-7", address="서울", product="붙박이장", status="DRAWING",
              manager_name="m7s", is_erp_order=True, erp_stage_code="DRAWING", structured_data=sd)
    db_session.add(o)
    db_session.commit()
    return o.id


def _sd(oid):
    db_session.expire_all()
    return dict(db_session.get(Order, oid).structured_data or {})


def _outbox_keys():
    rows = db_session.query(DomainSideEffectOutbox).filter_by(effect_type="STORAGE_DELETE").all()
    return {r.payload.get("object_key"): r for r in rows}


def _rows(oid, key):
    return db_session.query(OrderAttachment).filter_by(order_id=oid, storage_key=key).count()


def _transfer(client, oid, key, **extra):
    res = client.post(f"/api/orders/{oid}/transfer-drawing", json={"files": [{"key": key}], **extra})
    assert res.status_code == 200, res.get_json()
    return res


def _people(prefix):
    return _user(f"{prefix}s", "STAFF", "SALES"), _user(f"{prefix}d", "STAFF", "DRAWING")


@pytest.mark.parametrize("folder", ["drawing", "drawing_wizard/exports"])
def test_cancel_same_key_twice_keeps_restored_current_file_and_row(client, storage, folder):
    """P6 — 같은 key 를 두 번 전달한 뒤 취소: 복원 현재본 key 는 행 유지·outbox 없음."""
    sales, dr = _people(f"p6{folder[:3]}")
    oid = _order(sales, dr)
    v1 = f"orders/{oid}/{folder}/v1.png"
    _as(client, dr)
    _transfer(client, oid, v1)
    _transfer(client, oid, v1)
    res = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    assert res.status_code == 200, res.get_json()
    sd = _sd(oid)
    assert [f["key"] for f in sd["drawing_current_files"]] == [v1]
    assert v1 not in _outbox_keys(), "복원된 현재본이 가리키는 key 를 STORAGE_DELETE 로 예약했다"
    assert _rows(oid, v1) == 1, "복원된 현재본의 첨부 행을 지웠다"
    assert "0개" in res.get_json()["message"]


def _drop_rows(oid, key):
    """첨부 행이 없는 옛 전달 이력 모양 — 그 key 의 첨부 행을 지운다(도면 기록 판정만 남긴다)."""
    db_session.query(OrderAttachment).filter_by(order_id=oid, storage_key=key).delete()
    db_session.commit()


@pytest.mark.parametrize("folder", ["drawing", "drawing_wizard/exports"])
def test_cancel_keeps_restored_current_file_by_record_alone(client, storage, folder):
    """P6 변형 — 첨부 행이 없어도 복원 현재본이 가리키는 key 는 도면 기록 판정만으로 보존된다.

    살아 있는 첨부 행 판정이 가리지 못하게 행을 지운 뒤 취소한다(2b 리뷰 P3: 두 벌 P6 는
    행 판정만으로도 초록이라 drawing_keys_in_use 가 따로 고정되지 않았다).
    """
    sales, dr = _people(f"p6r{folder[:3]}")
    oid = _order(sales, dr)
    v1 = f"orders/{oid}/{folder}/v1.png"
    _as(client, dr)
    _transfer(client, oid, v1)
    _transfer(client, oid, v1)
    _drop_rows(oid, v1)
    res = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    assert res.status_code == 200, res.get_json()
    assert [f["key"] for f in _sd(oid)["drawing_current_files"]] == [v1]
    assert v1 not in _outbox_keys(), "첨부 행이 없다고 복원 현재본 파일을 삭제 예약했다"


def test_cancel_reclaims_unused_new_drawing_after_seven_days(client, storage):
    """``drawing/`` 새 key 1개 보통 회수: 행 0 · 본체+썸네일 예약 · available_at ≥ 지금+7일."""
    sales, dr = _people("m7n")
    oid = _order(sales, dr)
    v1, v2 = f"orders/{oid}/drawing/v1.png", f"orders/{oid}/drawing/v2.png"
    thumb = f"orders/{oid}/drawing/thumb_v2.png"
    db_session.add(OrderAttachment(order_id=oid, filename="v2.png", file_type="image",
                                   category="drawing", storage_key=v2, thumbnail_key=thumb, file_size=1))
    db_session.commit()
    _as(client, dr)
    _transfer(client, oid, v1)
    _transfer(client, oid, v2)
    before = now_utc_naive()
    res = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    assert res.status_code == 200, res.get_json()
    assert [f["key"] for f in _sd(oid)["drawing_current_files"]] == [v1]
    assert _rows(oid, v2) == 0
    outbox = _outbox_keys()
    assert set(outbox) == {v2, thumb}
    for row in outbox.values():
        assert row.available_at >= before + datetime.timedelta(days=7) - datetime.timedelta(seconds=5)
        assert row.payload["order_id"] == oid
    assert "1개" in res.get_json()["message"]


@pytest.mark.parametrize("wizard_points", [True, False])
def test_wizard_key_cancel_hides_row_and_respects_wizard_use(client, storage, wizard_points):
    """마법사 산출 key 끝-끝: 취소 뒤 첨부 행 0(목록 API 에 안 보임), 파일은 마법사가 쓰면 보존."""
    sales, dr = _people(f"m7w{int(wizard_points)}")
    oid = _order(sales, dr)
    wkey = f"orders/{oid}/drawing_wizard/exports/sheet1.png"
    if wizard_points:
        o = db_session.get(Order, oid)
        o.structured_data = {**o.structured_data, "drawing_wizard": {
            "pending": {"s1": {"key": wkey, "filename": "sheet1.png"}}}}
        db_session.commit()
    _as(client, dr)
    _transfer(client, oid, wkey)
    assert _rows(oid, wkey) == 1
    res = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    assert res.status_code == 200, res.get_json()
    assert _rows(oid, wkey) == 0
    listing = client.get(f"/api/orders/{oid}/attachments").get_json()
    assert wkey not in str(listing)
    outbox = _outbox_keys()
    if wizard_points:
        assert wkey not in outbox, "마법사 대기 시트가 쓰는 파일을 회수 예약했다"
    else:
        assert set(outbox) == {wkey}


def test_handler_skips_key_that_became_current_again(client, storage):
    """예약 뒤 같은 key 가 다시 현재본이 되면 핸들러의 R2 삭제 호출 0. 대조군은 1."""
    sales, dr = _people("m7h")
    oid = _order(sales, dr)
    v1, v2 = f"orders/{oid}/drawing/v1.png", f"orders/{oid}/drawing/v2.png"
    _as(client, dr)
    _transfer(client, oid, v1)
    _transfer(client, oid, v2)
    assert client.post(f"/api/orders/{oid}/cancel-transfer", json={}).status_code == 200
    row_id = _outbox_keys()[v2].id

    handle_storage_delete(db_session.get(DomainSideEffectOutbox, row_id))  # 대조군: 아무도 안 쓰면 지운다
    assert storage.deleted_keys == [v2]

    storage.deleted_keys.clear()
    _transfer(client, oid, v2, mode="APPEND")  # 같은 key 가 다시 현재본이 됐다
    assert v2 in [f["key"] for f in _sd(oid)["drawing_current_files"]]
    handle_storage_delete(db_session.get(DomainSideEffectOutbox, row_id))
    assert storage.deleted_keys == [], "다시 현재본이 된 key 를 핸들러가 지웠다"


def test_handler_skips_by_record_alone_without_attachment_row(client, storage):
    """핸들러 재확인 변형 — 다시 현재본이 된 key 의 첨부 행이 없어도 기록 판정만으로 건너뛴다."""
    sales, dr = _people("m7r")
    oid = _order(sales, dr)
    v1, v2 = f"orders/{oid}/drawing/v1.png", f"orders/{oid}/drawing/v2.png"
    _as(client, dr)
    _transfer(client, oid, v1)
    _transfer(client, oid, v2)
    assert client.post(f"/api/orders/{oid}/cancel-transfer", json={}).status_code == 200
    row_id = _outbox_keys()[v2].id
    _transfer(client, oid, v2, mode="APPEND")
    _drop_rows(oid, v2)
    assert v2 in [f["key"] for f in _sd(oid)["drawing_current_files"]]
    handle_storage_delete(db_session.get(DomainSideEffectOutbox, row_id))
    assert storage.deleted_keys == [], "첨부 행이 없다고 다시 현재본이 된 key 를 지웠다"
    assert db_session.get(DomainSideEffectOutbox, row_id).payload.get(
        handler_mod.SKIPPED_STILL_REFERENCED) is True


def test_handler_deletes_when_order_is_gone(client, storage):
    """주문이 하드 삭제됐으면 지금처럼 지운다."""
    sales, dr = _people("m7g")
    oid = _order(sales, dr)
    v1, v2 = f"orders/{oid}/drawing/v1.png", f"orders/{oid}/drawing/v2.png"
    _as(client, dr)
    _transfer(client, oid, v1)
    _transfer(client, oid, v2)
    assert client.post(f"/api/orders/{oid}/cancel-transfer", json={}).status_code == 200
    row = _outbox_keys()[v2]
    row_id = row.id
    row.payload = {**row.payload, "order_id": 987654}
    db_session.commit()
    handle_storage_delete(db_session.get(DomainSideEffectOutbox, row_id))
    assert storage.deleted_keys == [v2]


# --------------------------------------------------------------------------- M2 흐름 조합


def _request(client, oid, note):
    res = client.post(f"/api/orders/{oid}/request-revision", json={"note": note})
    assert res.status_code == 200, res.get_json()


def _check_last_request(client, oid):
    req = [h for h in _sd(oid)["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"][-1]
    res = client.post(f"/api/orders/{oid}/request-revision-check",
                      json={"request_at": req["at"], "by_user_id": req["by_user_id"], "checked": True})
    assert res.status_code == 200, res.get_json()


def test_cancelled_unchecked_request_does_not_block_transfer_and_cancel_transfer_restores(client, storage):
    """취소된(미체크) 요청은 전달을 막지 않고, 취소→재요청→전달 취소 조합의 복원이 맞다."""
    sales, dr = _people("m2f")
    oid = _order(sales, dr)
    v1, v2 = f"orders/{oid}/drawing/v1.png", f"orders/{oid}/drawing/v2.png"
    _as(client, dr)
    _transfer(client, oid, v1)
    _as(client, sales)
    _request(client, oid, "첫 요청")
    assert client.post(f"/api/orders/{oid}/cancel-revision-request").status_code == 200
    assert _sd(oid)["drawing_status"] == "TRANSFERRED"
    _request(client, oid, "두 번째 요청")
    _as(client, dr)
    _check_last_request(client, oid)
    _transfer(client, oid, v2, is_retransfer=True)  # 취소된 첫 요청(미체크)이 막지 않는다
    assert _sd(oid)["drawing_status"] == "TRANSFERRED"

    assert client.post(f"/api/orders/{oid}/cancel-transfer", json={}).status_code == 200
    sd = _sd(oid)
    assert sd["drawing_status"] == "RETURNED"
    assert [f["key"] for f in sd["drawing_current_files"]] == [v1]
    actions = [h.get("action") for h in sd["drawing_transfer_history"]]
    assert actions == ["TRANSFER", "REVISION_CANCELLED", "REQUEST_REVISION"]
