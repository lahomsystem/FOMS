"""PARTNER-FOMS 2단계: 협력사 완공 사진 · 완공 사진으로 AS 접수 · AS 진행 상황 · 관리자 돌아가기.

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.1 · §3.6 · §4.6 · §4.7 · §8.
각 허용 경로에는 거부 대조군(시공 전 · 다른 회사 · 남의 사진 · 다른 분류)을 같이 둔다.
"""
from __future__ import annotations

import copy

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Order, OrderAttachment, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_stage,
    fake_storage,
    world,
)


def _order(app, partner_id) -> int:
    return _create(app, partner_id).get_json()["data"]["order_id"]


def _attach(order_id, filename, category="construction") -> int:
    att = OrderAttachment(order_id=order_id, filename=filename, file_type="image", category=category,
                          file_size=10, storage_key=f"orders/{order_id}/{category}/{filename}")
    db_session.add(att)
    db_session.commit()
    return att.id


def _reception(order_id):
    db_session.expire_all()
    logs = db_session.get(Order, order_id).structured_data["shipment"]["as_log"]
    return next(e for e in logs if e.get("type") == "reception")


# --------------------------------------------------------------------------
# 완공 사진 보기
# --------------------------------------------------------------------------
def test_completion_photos_show_only_after_construction(app, world):
    order_id = _order(app, world["partner_a"])
    _attach(order_id, "front.jpg")
    _attach(order_id, "measure.jpg", category="measurement")  # 대조군: 실측 사진은 완공 사진이 아니다
    client = _client(app, db_session.get(User, world["partner_a"]))
    before = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "완공 사진 · AS" not in before and "front.jpg" not in before  # 시공 전에는 탭이 없다
    _to_stage(order_id, "COMPLETED")
    html = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "완공 사진 · AS" in html and 'alt="front.jpg"' in html
    assert 'name="construction_photo_ids"' in html and "measure.jpg" not in html


def test_completion_section_without_photos_still_allows_as(app, world):
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "CS")
    html = _client(app, db_session.get(User, world["partner_a"])).get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "아직 완공 사진이 없습니다" in html and "AS 접수하기" in html


# --------------------------------------------------------------------------
# 완공 사진으로 AS 접수
# --------------------------------------------------------------------------
def test_as_with_picked_completion_photos_keeps_ids_without_copying(app, world, fake_storage):
    order_id = _order(app, world["partner_a"])
    first, second = _attach(order_id, "door.jpg"), _attach(order_id, "shelf.jpg")
    _to_stage(order_id, "COMPLETED")
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/partner/orders/{order_id}/as",
                       data={"content": "문짝 걸림", "construction_photo_ids": [str(second), str(first), str(second)]})
    assert resp.status_code == 200, resp.get_json()
    reception = _reception(order_id)
    assert reception["ref_attachment_ids"] == [second, first]  # 고른 순서, 중복 제거
    assert "문짝 걸림" in reception["text"] and "[완공 사진 참고] shelf.jpg, door.jpg" in reception["text"]
    # 첨부를 복제하지 않는다(AS 첨부를 지울 때 시공 사진 원본이 같이 지워지지 않게).
    assert db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).count() == 2


def test_as_without_picked_photos_keeps_plain_text(app, world):
    # 대조군: 고른 사진이 없으면 지금과 같은 원문(덧붙임 · 참조 키 없음).
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "COMPLETED")
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert client.post(f"/api/partner/orders/{order_id}/as", data={"content": "문짝 처짐"}).status_code == 200
    reception = _reception(order_id)
    assert reception["text"] == "문짝 처짐" and "ref_attachment_ids" not in reception


def test_as_refuses_photos_from_other_order_or_other_category(app, world):
    own = _order(app, world["partner_a"])
    other = _order(app, world["partner_a"])
    foreign = _attach(other, "other.jpg")  # 같은 회사라도 다른 주문의 사진
    measurement = _attach(own, "measure.jpg", category="measurement")
    _to_stage(own, "COMPLETED")
    client = _client(app, db_session.get(User, world["partner_a"]))
    for bad in (str(foreign), str(measurement), "x", "999999"):
        resp = client.post(f"/api/partner/orders/{own}/as", data={"content": "x", "construction_photo_ids": bad})
        assert resp.status_code == 400, bad
    db_session.expire_all()
    assert db_session.get(Order, own).as_axis_status is None  # 거부되면 AS 건도 열리지 않는다


def test_as_on_other_company_order_is_hidden_before_photo_check(app, world):
    order_id = _order(app, world["partner_a"])
    photo = _attach(order_id, "door.jpg")
    _to_stage(order_id, "COMPLETED")
    b = _client(app, db_session.get(User, world["partner_b"]))
    resp = b.post(f"/api/partner/orders/{order_id}/as", data={"content": "x", "construction_photo_ids": str(photo)})
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# AS 진행 상황
# --------------------------------------------------------------------------
def test_open_as_shows_progress_with_visit_and_as_photos(app, world, fake_storage):
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "COMPLETED")
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert client.post(f"/api/partner/orders/{order_id}/as", data={"content": "거울 흔들림"}).status_code == 200
    reception = _reception(order_id)
    db_session.add(OrderAttachment(order_id=order_id, filename="as-before.jpg", file_type="image", category="as",
                                   as_log_id=reception["id"], file_size=10,
                                   storage_key=f"orders/{order_id}/as/as-before.jpg"))
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    cycle = next(c for c in sd["as_lifecycle"]["cycles"] if c["cycle_id"] == sd["as_lifecycle"]["current_cycle_id"])
    cycle.setdefault("transitions", []).append(
        {"command": "AS_SCHEDULE", "payload": {"visit_date": "2026-10-21", "visit_time": "14:00"}})
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    html = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "진행 중인 AS" in html and "2026-10-21 14:00" in html and 'alt="as-before.jpg"' in html
    assert 'name="construction_photo_ids"' not in html  # 진행 중이면 새 접수 칸이 없다


# --------------------------------------------------------------------------
# 관리자 돌아가기
# --------------------------------------------------------------------------
def test_admin_back_button_only_when_impersonating(app, world):
    partner = db_session.get(User, world["partner_a"])
    plain = _client(app, partner).get("/partner").get_data(as_text=True)
    assert "관리자로 돌아가기" not in plain  # 대조군: 협력사 본인 로그인
    client = _client(app, partner)
    with client.session_transaction() as sess:
        sess["impersonating_from"] = world["admin"]
    html = client.get("/partner").get_data(as_text=True)
    assert "관리자로 돌아가기" in html and 'action="/switch-back"' in html
