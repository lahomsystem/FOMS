"""PARTNER-03: 협력사 3단계 — 로고 · 도면 OK(→생산) · 수정 요청 · AS 접수 계약.

스펙 docs/specs/2026-10-08-partner-portal_SPEC.md §13 · §14. 공용 준비물은 partner_fixtures.py.
"""
from __future__ import annotations

import io

import pytest

from db import db_session
from models import Order, OrderAttachment, PartnerOrg, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_confirm,
    _to_stage,
    fake_storage,
    logo_storage,
    quiet_push,
    world,
)
# --------------------------------------------------------------------------
# 3단계 — 협력사 로고
# --------------------------------------------------------------------------
def test_wizard_logo_partner_none_and_ours_unchanged(app, world, logo_storage):
    from foms.services.drawing_wizard_defaults import build_wizard_defaults

    partner_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    partner_order = db_session.get(Order, partner_id)
    assert build_wizard_defaults(partner_order, partner_order.structured_data, None)["logo"] == "none"

    admin = _client(app, db_session.get(User, world["admin"]))
    resp = admin.post(f"/admin/partners/{world['org_a']}/logo",
                      data={"logo": (io.BytesIO(b"\x89PNG-logo"), "logo.png")},
                      content_type="multipart/form-data")
    assert resp.status_code == 302
    db_session.expire_all()
    partner_order = db_session.get(Order, partner_id)
    assert build_wizard_defaults(partner_order, partner_order.structured_data, None)["logo"] == "partner"
    # 대조군: 우리 주문은 예전 규칙 그대로(하우드).
    ours = Order(received_date="2026-10-08", customer_name="c", phone="0", address="a", product="p",
                 structured_data={"parties": {"manager": {"name": "영업김"}}})
    db_session.add(ours)
    db_session.commit()
    assert build_wizard_defaults(ours, ours.structured_data, None)["logo"] == "haud"

    staff = _client(app, db_session.get(User, world["staff"]))
    got = staff.get(f"/api/partner/orders/{partner_order.id}/logo")
    assert got.status_code == 200 and got.data == b"\x89PNG-logo" and got.mimetype == "image/png"
    assert staff.get(f"/api/partner/orders/{ours.id}/logo").status_code == 404
    assert admin.get(f"/admin/partners/{world['org_a']}/logo").status_code == 200


def test_admin_logo_rejects_non_images(app, world, logo_storage):
    admin = _client(app, db_session.get(User, world["admin"]))
    admin.post(f"/admin/partners/{world['org_a']}/logo",
               data={"logo": (io.BytesIO(b"x"), "logo.exe")}, content_type="multipart/form-data")
    assert db_session.get(PartnerOrg, world["org_a"]).logo_storage_key is None
    assert logo_storage.files == {}


# --------------------------------------------------------------------------
# 3단계 — 협력사 도면 확인(이대로 제작) → 생산
# --------------------------------------------------------------------------
def test_partner_approves_drawing_and_order_moves_to_production(app, world):
    from models import SecurityLog

    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _to_confirm(order_id)
    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "final.pdf" in page and "이대로 만들어 주세요" in page

    resp = client.post(f"/api/partner/orders/{order_id}/approve-drawing", json={"idempotency_key": "k1"})
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = order.structured_data
    assert order.erp_stage_code == "PRODUCTION"
    assert sd["blueprint"]["customer_confirmed"] is True
    quest = next(q for q in sd["quests"] if q.get("stage") in ("고객컨펌", "CONFIRM"))
    assert quest["status"] == "COMPLETED" and quest["assignee_approval"]["approved_by"] == world["partner_a"]
    log = db_session.query(SecurityLog).filter(SecurityLog.action == "PARTNER_DRAWING_APPROVED").one()
    assert log.target_id == order_id and log.detail["final_drawing_keys"] == [f"orders/{order_id}/drawing/final.pdf"]
    assert "생산 중" in client.get(f"/partner/orders/{order_id}").get_data(as_text=True)


def test_partner_approve_refused_when_not_ready_or_not_own(app, world):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    a = _client(app, db_session.get(User, world["partner_a"]))
    b = _client(app, db_session.get(User, world["partner_b"]))
    # 아직 실측 단계
    assert a.post(f"/api/partner/orders/{order_id}/approve-drawing", json={}).status_code == 409
    # 도면 확인 단계지만 도면이 확정 전(수정 요청됨)
    _to_confirm(order_id, drawing_status="RETURNED")
    assert "이대로 만들어 주세요" not in a.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert a.post(f"/api/partner/orders/{order_id}/approve-drawing", json={}).status_code == 409
    # 다른 협력사
    _to_confirm(order_id)
    assert b.post(f"/api/partner/orders/{order_id}/approve-drawing", json={}).status_code == 404
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "CONFIRM"


# --------------------------------------------------------------------------
# 3단계 — 협력사 수정 요청 · AS 접수
# --------------------------------------------------------------------------
def test_partner_revision_request_returns_drawing_to_drawing_team(app, world, fake_storage, quiet_push):
    from models import Notification

    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _to_confirm(order_id)
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert "수정 요청 보내기" in client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    resp = client.post(f"/api/partner/orders/{order_id}/revision",
                       data={"note": "문 손잡이 위치 변경", "photos": (io.BytesIO(b"img"), "ref.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    last = sd["drawing_transfer_history"][-1]
    assert sd["drawing_status"] == "RETURNED"
    assert last["action"] == "REQUEST_REVISION" and "(협력사)" in last["by_user_name"]
    assert last["files_count"] == 1 and last["files"][0]["key"].startswith(f"orders/{order_id}/drawing_gateway/revisions/")
    assert last["target_drawing_keys"] == [f"orders/{order_id}/drawing/final.pdf"]
    note = db_session.query(Notification).filter(Notification.notification_type == "DRAWING_REVISION").one()
    assert note.target_team == "DRAWING" and "문 손잡이" in note.message
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "이대로 만들어 주세요" not in page and "수정 요청 보내기" not in page


def test_partner_revision_refusals(app, world, fake_storage, quiet_push):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    a = _client(app, db_session.get(User, world["partner_a"]))
    b = _client(app, db_session.get(User, world["partner_b"]))
    assert a.post(f"/api/partner/orders/{order_id}/revision", data={"note": "x"}).status_code == 409  # 도면 전 단계
    _to_confirm(order_id)
    assert a.post(f"/api/partner/orders/{order_id}/revision", data={"note": " "}).status_code == 400
    assert b.post(f"/api/partner/orders/{order_id}/revision", data={"note": "x"}).status_code == 404
    db_session.expire_all()
    assert db_session.get(Order, order_id).structured_data["drawing_status"] == "CONFIRMED"


def test_partner_as_register_opens_cycle_with_photo(app, world, fake_storage):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert client.post(f"/api/partner/orders/{order_id}/as", data={"content": "x"}).status_code == 409  # 시공 전
    _to_stage(order_id, "COMPLETED")
    assert "AS 접수하기" in client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    resp = client.post(f"/api/partner/orders/{order_id}/as",
                       data={"content": "문짝 처짐", "photos": (io.BytesIO(b"img"), "as.jpg")},
                       content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200 and body["data"]["photos"] == 1, body
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    assert order.as_axis_status == "RECEIVED"
    logs = order.structured_data["shipment"]["as_log"]
    reception = next(e for e in logs if e.get("type") == "reception")
    assert reception["text"] == "문짝 처짐" and "(협력사)" in reception["by"]
    att = db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id,
                                                   OrderAttachment.category == "as").one()
    assert att.as_log_id == reception["id"] and att.storage_key.startswith(f"orders/{order_id}/as/")
    # 진행 중인 AS 가 있으면 새로 열지 않는다.
    again = client.post(f"/api/partner/orders/{order_id}/as", data={"content": "또"})
    assert again.status_code == 409
    detail = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "진행 중인 AS" in detail and '<span class="pp-stage">AS 진행 중' in detail
    assert "AS 진행 중" in client.get("/partner").get_data(as_text=True)


def test_partner_as_other_org_refused(app, world, fake_storage):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _to_stage(order_id, "COMPLETED")
    b = _client(app, db_session.get(User, world["partner_b"]))
    assert b.post(f"/api/partner/orders/{order_id}/as", data={"content": "x"}).status_code == 404
    db_session.expire_all()
    assert db_session.get(Order, order_id).as_axis_status is None
