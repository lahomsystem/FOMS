"""PARTNER-FOMS 3-1: 협력사 주문 화면(우리 /edit 모양) · 협력사 투영 · 접수 확인 중 품목 고치기.

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.3 · §4-1 · §4-4 · §5-4 · §8 · §12.
각 허용 경로에는 거부 대조군(다른 회사 · 도면 단계 · 남의 uid)을 같이 둔다.
"""
from __future__ import annotations

import copy
import io
import json
import uuid

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.orders.item_identity import resolve_active_item_id
from foms.services.partners.view import build_partner_order_view
from foms.web.orders.edit import _build_erp_order_bootstrap
from models import Notification, Order, OrderAttachment, SecurityLog, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _to_stage,
    fake_storage,
    world,
)

_ITEMS = [
    {"product_name": "안방 붙박이장", "spec_rows": [{"spec_width": "5700(2402+1864+1434)", "spec_depth": "600",
                                                  "spec_height": "2350"}], "color": "화이트 오크"},
    {"product_name": "화장대", "spec_rows": [{"spec_width": "1200", "spec_depth": "450", "spec_height": "750"}]},
]
# 우리 직원만 보는 값 — 협력사 화면 원문에 하나도 나오면 안 된다.
_INTERNAL = ("7654321", "3456789", "9876543", "시공팀메모X", "긴급사유X", "내부비고X")


def _order(app, partner_id) -> int:
    resp = _create(app, partner_id, {**_PAYLOAD, "items": _ITEMS})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _patch_sd(order_id, fn) -> None:
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    fn(sd)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _seed_internal(sd) -> None:
    sd["items"][0]["price"] = 7654321
    sd["payment"] = {"deposit_amount": 3456789}
    sd["estimate_preview"] = {"total": 9876543}
    sd["notes"] = {"construction_note": "시공팀메모X", "phone_note": "저녁에만 전화"}
    sd["flags"] = {"urgent": True, "urgent_reason": "긴급사유X"}


def _uids(order_id) -> list[str]:
    db_session.expire_all()
    return [it["uid"] for it in db_session.get(Order, order_id).structured_data["items"]]


def _put(client, order_id, items):
    return client.put(f"/api/partner/orders/{order_id}/items", json={"items": items})


# --------------------------------------------------------------------------
# 협력사 투영 · 화면
# --------------------------------------------------------------------------
def test_partner_screen_carries_no_internal_values_but_staff_bootstrap_does(app, world):
    order_id = _order(app, world["partner_a"])
    _patch_sd(order_id, _seed_internal)
    db_session.get(Order, order_id).notes = "내부비고X"
    db_session.commit()
    html = _client(app, db_session.get(User, world["partner_a"])).get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert [marker for marker in _INTERNAL if marker in html] == []
    assert "저녁에만 전화" in html and "5700(2402+1864+1434)" in html and "화이트 오크" in html
    # 대조군: 같은 주문을 우리 직원 화면이 실으면 값이 다 있다(투영이 실제로 걸러 낸 것).
    staff = json.dumps(_build_erp_order_bootstrap(db_session.get(Order, order_id)), ensure_ascii=False)
    assert [marker for marker in _INTERNAL if marker not in staff] == []


def test_projection_keys_are_an_allowlist(app, world):
    order_id = _order(app, world["partner_a"])
    _patch_sd(order_id, _seed_internal)
    view = build_partner_order_view(db_session.get(Order, order_id))
    assert set(view) == {
        "id", "customer_name", "customer_phone", "phone_note", "received_by", "received_date", "received_time",
        "manager_user_id", "manager_name", "manager_phone", "stage_code", "stage_label", "steps", "address",
        "address_note", "measured_on", "measurement_note", "construction_date", "construction_time", "memo",
        "submitted_at", "items", "items_editable",
    }
    assert set(view["items"][0]) <= {"product_name", "spec_rows", "quantity", "internal", "color", "option_detail",
                                      "handle", "misc", "extra_input", "uid"}


def test_editable_only_while_intake_is_checked(app, world):
    order_id = _order(app, world["partner_a"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    measure = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "품목 저장" in measure and 'id="ppItemRow"' in measure and "partner-items.js" in measure
    _to_stage(order_id, "DRAWING")
    drawing = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "품목 저장" not in drawing and 'id="ppItemRow"' not in drawing
    assert 'data-k="product_name" maxlength="100" value="안방 붙박이장" placeholder="예: 드레스룸 ㄷ자" readonly' in drawing


# --------------------------------------------------------------------------
# 품목 고치기
# --------------------------------------------------------------------------
def test_edit_keeps_uid_and_staff_keys_and_records_original(app, world):
    order_id = _order(app, world["partner_a"])
    _patch_sd(order_id, lambda sd: sd["items"][0].update({"price": 1250000, "measurement_date": "2026-10-20"}))
    first, _ = _uids(order_id)
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = _put(client, order_id, [
        {"uid": first, "product_name": "안방 붙박이장 ㄱ자", "spec_rows": [
            {"spec_width": "5700", "spec_depth": "600", "spec_height": "2350"},
            {"spec_width": "2352+2100+2860", "spec_depth": "450", "spec_height": "2350"}], "handle": "푸시 오픈"},
        {"product_name": "현관 신발장", "spec_rows": [{"spec_width": "1200"}]},
    ])
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    items = order.structured_data["items"]
    assert items[0]["uid"] == first and items[0]["price"] == 1250000 and items[0]["measurement_date"] == "2026-10-20"
    assert items[0]["handle"] == "푸시 오픈" and "color" not in items[0]  # 비운 속성은 지운다
    assert len(items[0]["spec_rows"]) == 2 and items[1]["product_name"] == "현관 신발장"
    intake = order.structured_data["partner_intake"]
    assert [it["product_name"] for it in intake["items"]] == ["안방 붙박이장 ㄱ자", "현관 신발장"]
    assert all("uid" not in it and "price" not in it for it in intake["items"])
    edit = intake["item_edits"][-1]
    assert edit["by_user_id"] == world["partner_a"] and [it["product_name"] for it in edit["before"]] == ["안방 붙박이장", "화장대"]
    assert order.product == "안방 붙박이장 ㄱ자"
    assert db_session.query(SecurityLog).filter_by(action="PARTNER_ORDER_ITEMS_EDITED", target_id=order_id).count() == 1
    assert db_session.query(Notification).filter_by(
        order_id=order_id, notification_type="PARTNER_ORDER_ITEMS_EDITED", target_team="CS").count() == 1


def test_forged_uid_is_not_adopted(app, world):
    order_id = _order(app, world["partner_a"])
    before = set(_uids(order_id))
    forged = str(uuid.uuid4())
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _put(client, order_id, [{"uid": forged, "product_name": "x"}]).status_code == 200
    assert _uids(order_id)[0] != forged and _uids(order_id)[0] in before  # 위치로 물려받는다(새 uid 주입 금지)


def test_item_photos_follow_their_item_and_removed_item_photos_become_common(app, world, fake_storage):
    order_id = _order(app, world["partner_a"])
    first, second = _uids(order_id)
    client = _client(app, db_session.get(User, world["partner_a"]))
    for name, index in (("first.jpg", 0), ("second.jpg", 1)):
        resp = client.post(f"/api/partner/orders/{order_id}/files", content_type="multipart/form-data",
                           data={"kind": "photo", "item_index": str(index), "file": (io.BytesIO(b"x" * 10), name)})
        assert resp.status_code == 200
    # 첫 품목을 지우고 둘째를 맨 앞으로 — 둘째 사진은 0번 자리로, 첫 품목 사진은 공통 사진으로.
    assert _put(client, order_id, [{"uid": second, "product_name": "화장대"}, {"product_name": "새 품목"}]).status_code == 200
    db_session.expire_all()
    rows = {a.filename: a for a in db_session.query(OrderAttachment).filter_by(order_id=order_id)}
    assert rows["second.jpg"].item_index == 0
    assert rows["second.jpg"].item_id == resolve_active_item_id(db_session, order_id, 0)
    assert rows["first.jpg"].item_index is None and rows["first.jpg"].item_id is None
    assert resolve_active_item_id(db_session, order_id, 1) is not None  # 새 품목 자리도 사진을 받을 수 있다


def test_edit_refused_after_intake_or_for_other_company(app, world):
    order_id = _order(app, world["partner_a"])
    other = _client(app, db_session.get(User, world["partner_b"]))
    assert _put(other, order_id, [{"product_name": "x"}]).status_code == 404
    own = _client(app, db_session.get(User, world["partner_a"]))
    assert _put(own, order_id, [{"product_name": ""}]).status_code == 400
    _to_stage(order_id, "DRAWING")
    resp = _put(own, order_id, [{"product_name": "x"}])
    assert resp.status_code == 409 and "수정 요청" in resp.get_json()["error"]
    db_session.expire_all()
    assert [it["product_name"] for it in db_session.get(Order, order_id).structured_data["items"]] == ["안방 붙박이장", "화장대"]


def test_staff_cannot_call_partner_items_api(app, world):
    order_id = _order(app, world["partner_a"])
    staff = _client(app, db_session.get(User, world["staff"]))
    assert _put(staff, order_id, [{"product_name": "x"}]).status_code in (403, 404)
