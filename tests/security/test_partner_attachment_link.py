"""PARTNER-FOMS 5-3: 보낸 실측 사진 제품 연결 · 해제(PATCH /api/partner/orders/<id>/attachments/<aid>).

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §17.2. 허용 경로마다 거부 대조군(다른 회사 · 단계 · 우리 직원 파일 ·
초안 도면 · 범위 밖 · 우리 직원 호출)을 둔다.
"""
from __future__ import annotations

from db import db_session
from models import Order, OrderAttachment, OrderEvent, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _to_stage,
    _upload,
    fake_storage,
    world,
)

_ITEMS = [{"product_name": "안방장", "width": "2400"}, {"product_name": "신발장", "width": "1200"}]


def _order(app, partner_id) -> int:
    resp = _create(app, partner_id, {**_PAYLOAD, "items": _ITEMS})
    return resp.get_json()["data"]["order_id"]


def _patch(app, user_id, order_id, att_id, body):
    client = _client(app, db_session.get(User, user_id))
    return client.patch(f"/api/partner/orders/{order_id}/attachments/{att_id}", json=body)


def _att(order_id, filename) -> OrderAttachment:
    db_session.expire_all()
    return db_session.query(OrderAttachment).filter_by(order_id=order_id, filename=filename).one()


def test_link_and_unlink_partner_photo(app, world, fake_storage):
    order_id = _order(app, world["partner_a"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _upload(client, order_id, "wall.jpg", "photo").status_code == 200
    att = _att(order_id, "wall.jpg")
    assert att.item_index is None
    resp = _patch(app, world["partner_a"], order_id, att.id, {"item_index": 1})
    assert resp.status_code == 200, resp.get_json()
    att = _att(order_id, "wall.jpg")
    assert att.item_index == 1 and att.item_id is not None
    events = db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="ATTACHMENT_META_UPDATED").count()
    assert events == 1
    assert _patch(app, world["partner_a"], order_id, att.id, {"item_index": None}).status_code == 200
    att = _att(order_id, "wall.jpg")
    assert att.item_index is None and att.item_id is None


def test_link_rejects_wrong_company_stage_kind_range_and_staff(app, world, fake_storage):
    order_id = _order(app, world["partner_a"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    _upload(client, order_id, "wall.jpg", "photo")
    _upload(client, order_id, "draft.pdf", "draft")
    photo_id = _att(order_id, "wall.jpg").id
    draft_id = _att(order_id, "draft.pdf").id
    staff_file = OrderAttachment(order_id=order_id, filename="ours.jpg", file_type="image", category="measurement",
                                 storage_key=f"orders/{order_id}/measurement/ours.jpg", file_size=1)
    db_session.add(staff_file)
    db_session.commit()
    staff_id = staff_file.id
    assert _patch(app, world["partner_b"], order_id, photo_id, {"item_index": 0}).status_code == 404
    assert _patch(app, world["staff"], order_id, photo_id, {"item_index": 0}).status_code == 403
    assert _patch(app, world["partner_a"], order_id, draft_id, {"item_index": 0}).status_code == 400
    assert _patch(app, world["partner_a"], order_id, staff_id, {"item_index": 0}).status_code == 400
    assert _patch(app, world["partner_a"], order_id, photo_id, {"item_index": 5}).status_code == 400
    assert _patch(app, world["partner_a"], order_id, photo_id, {}).status_code == 400
    other = _order(app, world["partner_a"])
    assert _patch(app, world["partner_a"], other, photo_id, {"item_index": 0}).status_code == 404  # 다른 주문의 사진
    _to_stage(order_id, "DRAWING")
    assert _patch(app, world["partner_a"], order_id, photo_id, {"item_index": 0}).status_code == 409
    assert _att(order_id, "wall.jpg").item_index is None


def test_screen_shows_link_controls_only_while_intake_open(app, world, fake_storage):
    order_id = _order(app, world["partner_a"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    client.post(f"/api/partner/orders/{order_id}/files",
                data={"kind": "photo", "item_index": "0", "file": (__import__("io").BytesIO(b"x"), "item.jpg")},
                content_type="multipart/form-data")
    _upload(client, order_id, "wall.jpg", "photo")
    html = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert 'id="ppAttUrl"' in html
    assert f'data-pp-att-link="{_att(order_id, "wall.jpg").id}"' in html  # 공통 사진 → 제품 연결
    assert f'data-pp-att-unlink="{_att(order_id, "item.jpg").id}"' in html  # 제품 사진 → 공통으로
    assert 'data-pp-photo-zone="common"' in html and 'name="photos"' not in html  # 더 보내기도 사진 칸
    _to_stage(order_id, "DRAWING")
    locked = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "ppAttUrl" not in locked and "data-pp-att-unlink" not in locked
    assert db_session.get(Order, order_id) is not None
