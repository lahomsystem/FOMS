"""협력사 도면 확인(받음) — FOMS 영업 "도면 수령 확인"과 같은 2단계(사용자 2026-10-28).

저희 도면팀이 보냄(TRANSFERRED) → 협력사 "도면 확인했어요"(→ 고객컨펌) 또는 수정 요청 → 고객과 확인 뒤
"이대로 만들어 주세요"(→ 생산). 직원 수령 확인과 같은 한 경로(``record_drawing_receipt``)를 탄다.
대조군: 다른 회사 404 · 보내기 전 409 · 우리 직원은 협력사 API 를 못 쓴다.
"""
from __future__ import annotations

import io

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Notification, Order, SecurityLog, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_stage,
    fake_storage,
    quiet_push,
    world,
)


def _send_drawing(order_id):
    """저희 도면팀이 도면을 보냄(도면 단계 · TRANSFERRED · 도면 key 파일 1개)."""
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    key = f"orders/{order_id}/drawing/final.png"
    sd["drawing_status"] = "TRANSFERRED"
    sd["drawing_current_files"] = [{"key": key, "filename": "final.png"}]
    sd["drawing_transfer_history"] = [{"action": "TRANSFER", "at": "2026-10-28 10:00:00", "files": [{"key": key}]}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _receipt(client, order_id):
    return client.post(f"/api/partner/orders/{order_id}/drawing-receipt", json={})


def test_partner_receipt_moves_to_confirm_then_approve_to_production(app, world, quiet_push):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _send_drawing(order_id)
    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    approve_btn = f'data-pp-approve-url="/api/partner/orders/{order_id}/approve-drawing"'
    receipt_btn = f'data-pp-approve-url="/api/partner/orders/{order_id}/drawing-receipt"'
    assert receipt_btn in page and approve_btn not in page and "수정 요청 보내기" in page
    board = client.get("/partner?turn=1").get_data(as_text=True)
    assert f'data-pp-order-id="{order_id}"' in board  # 보낸 도면은 협력사 차례

    resp = _receipt(client, order_id)
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = order.structured_data
    assert order.erp_stage_code == "CONFIRM" and sd["drawing_status"] == "CONFIRMED"
    receipt = sd["drawing_transfer_history"][-1]
    assert receipt["action"] == "CONFIRM_RECEIPT" and receipt["by_user_name"].endswith("(협력사)")
    assert db_session.query(SecurityLog).filter_by(action="PARTNER_DRAWING_RECEIVED", target_id=order_id).count() == 1

    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert approve_btn in page and receipt_btn not in page
    assert client.post(f"/api/partner/orders/{order_id}/approve-drawing", json={"idempotency_key": "r1"}).status_code == 200
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "PRODUCTION"


def test_partner_receipt_refused_before_send_other_company_and_staff(app, world, quiet_push):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    a = _client(app, db_session.get(User, world["partner_a"]))
    assert _receipt(a, order_id).status_code == 409  # 아직 보낸 도면이 없다
    assert "/drawing-receipt" not in a.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    _send_drawing(order_id)
    assert _receipt(_client(app, db_session.get(User, world["partner_b"])), order_id).status_code == 404
    assert _receipt(_client(app, db_session.get(User, world["staff"])), order_id).status_code in (302, 403)
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "DRAWING"
    assert _receipt(a, order_id).status_code == 200
    assert _receipt(a, order_id).status_code == 409  # 두 번 누르면 이미 고객컨펌


def test_drawing_sent_is_partner_turn_for_notice(app, world):
    from foms.services.partners.notify import partner_drawing_turn

    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    order = db_session.get(Order, order_id)
    assert partner_drawing_turn(order) is False  # 도면 작업 중 — 아직 협력사 차례 아님
    _send_drawing(order_id)
    db_session.expire_all()
    assert partner_drawing_turn(db_session.get(Order, order_id)) is True


def test_partner_as_register_notifies_cs(app, world, fake_storage):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _to_stage(order_id, "COMPLETED")
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/partner/orders/{order_id}/as",
                       data={"content": "문짝 처짐", "photos": (io.BytesIO(b"img"), "as.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    notes = db_session.query(Notification).filter_by(order_id=order_id, notification_type="PARTNER_AS_REGISTERED").all()
    assert [n.target_team for n in notes] == ["CS"] and "문짝 처짐" in notes[0].message
