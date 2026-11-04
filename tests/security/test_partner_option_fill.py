"""단가표 전 협력사 주문 — 우리 CS 옵션 채우기(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md 결정 12).

단가표가 생기기 전에 들어온 주문은 옵션 줄이 없어 발행 대기에 뜨지 않는다. CS 가 품목마다 단가표 제품 · 옵션을 고르면
생산 뒤 주문은 확정본(CONFIRMED)까지 써서 바로 발행 대기에 뜨고, 그 전 주문은 원문 · 지금 값만 써서 협력사 도면 확인이
확정한다. 이미 옵션이 있는 품목(협력사가 고른 것)은 덮지 않는다. 대조군: 영업팀 · 협력사는 403, CS 는 200. 단가 · 이름은 가짜다.
"""
from __future__ import annotations

from db import db_session
from foms.services.partners.item_options import ItemOptionsError, confirm_partner_options
from foms.services.partners.price_list import save_price_list
from models import Order, OrderItemOption, SecurityLog, User
from tests.security.partner_fixtures import _PAYLOAD, _client, _create, world  # noqa: F401 — pytest fixture 재노출
from tests.security.test_partner_item_options import PRICES, SHEET, _item, _rows
from tests.security.test_partner_statement_portal import _partner
from tests.security.test_partner_statements import API, _cs

import pytest


def _old_order(app, w, *, stage="PRODUCTION", names=("슬라이딩", "붙박이장")):
    """단가표 저장 전에 들어온 주문(옵션 줄 없음) → 단가표 저장 → 단계."""
    items = [{"product_name": n, "spec_rows": [{"spec_width": "3700", "spec_depth": "620", "spec_height": "2290"}]}
             for n in names]
    resp = _create(app, w["partner_a"], {**_PAYLOAD, "items": items})
    assert resp.status_code == 200, resp.get_json()
    oid = resp.get_json()["data"]["order_id"]
    assert _rows(oid) == []
    save_price_list(db_session, w["org_a"], SHEET, label="11월판", effective_from="2026-11-01", base_id=None, user_id=None)
    order = db_session.get(Order, oid)
    order.erp_stage_code = stage
    db_session.commit()
    return oid


def _uids(oid):
    db_session.expire_all()
    return [it["uid"] for it in db_session.get(Order, oid).structured_data["items"]]


def _body(oid, *entries):
    return {"items": {uid: entry for uid, entry in zip(_uids(oid), entries)}}


def test_list_view_then_fill_after_confirm_goes_to_pending(app, world):
    oid = _old_order(app, world)
    cs = _cs(app)
    rows = cs.get(f"{API}/fill").get_json()["data"]["rows"]
    assert [(r["order_id"], r["missing"], r["items"], r["confirmed"]) for r in rows] == [(oid, 2, 2, True)]
    view = cs.get(f"{API}/orders/{oid}/options").get_json()["data"]
    assert [(i["no"], i["title"], i["base"], i["spec"], i["filled"]) for i in view["items"]] == [
        (1, "슬라이딩", "슬라이딩", "3700*620*2290", False), (2, "붙박이장", "", "3700*620*2290", False)]
    assert not any(price in repr(view) for price in PRICES)  # 목록은 이름만
    assert [g["label"] for g in view["tree"]] == ["기타"]  # 3단 고르기 창 목록(분류 없는 판 = 기타 — 2026-11-04)
    body = _body(oid, {"base": "슬라이딩", "lines": [{"key": "r4", "name": "슬라이딩 거울 도어", "qty": 2}]},
                 {"base": "침대 붙박이장", "lines": [{"key": "r7", "qty": 1}], "customs": [{"text": "선반 하나"}]})
    resp = cs.post(f"{API}/orders/{oid}/options", json=body)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"] == {"items": 2, "stages": ["PARTNER", "CURRENT", "CONFIRMED"], "confirmed": True}
    confirmed = _rows(oid, "CONFIRMED")
    assert [(r.base_key, r.lines[0]["key"]) for r in confirmed] == [("r2", "r4"), ("r3", "r7")]
    assert len(_rows(oid)) == 6
    assert [r["order_id"] for r in cs.get(f"{API}/pending").get_json()["data"]["rows"]] == [oid]
    assert cs.get(f"{API}/fill").get_json()["data"]["rows"] == []
    again = cs.post(f"{API}/orders/{oid}/options", json=body)
    assert again.status_code == 409 and "채울 품목이 없습니다" in again.get_json()["error"]
    log = db_session.query(SecurityLog).filter(SecurityLog.action == "PARTNER_OPTIONS_FILLED").one()
    assert log.target_id == oid and log.detail["confirmed"] is True


def test_fill_before_confirm_writes_current_only_and_partner_confirms(app, world):
    oid = _old_order(app, world, stage="DRAWING", names=("슬라이딩",))
    cs = _cs(app)
    resp = cs.post(f"{API}/orders/{oid}/options", json=_body(oid, {"base": "슬라이딩", "state": "later"}))
    assert resp.status_code == 200, resp.get_json()
    assert sorted(r.stage for r in _rows(oid)) == ["CURRENT", "PARTNER"]
    assert cs.get(f"{API}/pending").get_json()["data"]["rows"] == []  # 확정은 협력사가
    order = db_session.get(Order, oid)
    with pytest.raises(ItemOptionsError):  # "상담 후 정함"은 협력사가 도면 확인 때 고른다
        confirm_partner_options(db_session, order, {}, None)
    db_session.rollback()
    uid = _uids(oid)[0]
    confirm_partner_options(db_session, db_session.get(Order, oid), {uid: {"state": "none"}}, None)
    db_session.commit()
    assert [(r.state, r.base_key) for r in _rows(oid, "CONFIRMED")] == [("none", "r2")]


def test_fill_rejects_missing_base_wrong_product_option_later_after_confirm(app, world):
    oid = _old_order(app, world, names=("슬라이딩",))
    cs = _cs(app)
    url = f"{API}/orders/{oid}/options"
    cases = [({"state": "none"}, "단가표 제품"),
             ({"base": "슬라이딩", "lines": [{"key": "r7", "qty": 1}]}, "침대 붙박이장에만"),
             ({"base": "슬라이딩", "state": "later"}, "상담 후 정함"),
             ({"base": "슬라이딩", "lines": [{"key": "r9", "qty": 1}]}, "고를 수 없는 옵션"),
             ({"base": "슬라이딩"}, "옵션을 골라 주세요")]
    for entry, message in cases:
        resp = cs.post(url, json=_body(oid, entry))
        assert resp.status_code == 409 and message in resp.get_json()["error"], (entry, resp.get_json())
    stray = cs.post(url, json={"items": {**_body(oid, {"base": "슬라이딩", "state": "none"})["items"], "nope": {}}})
    assert stray.status_code == 409
    assert _rows(oid) == [] and db_session.query(SecurityLog).filter(
        SecurityLog.action == "PARTNER_OPTIONS_FILLED").count() == 0


def test_partner_chosen_items_are_not_listed_or_overwritten(app, world):
    save_price_list(db_session, world["org_a"], SHEET, label="11월판", effective_from="2026-11-01", base_id=None, user_id=None)
    db_session.commit()
    resp = _create(app, world["partner_a"], {**_PAYLOAD, "items": [_item(lines=[{"key": "r4", "qty": 1}])]})
    oid = resp.get_json()["data"]["order_id"]
    cs = _cs(app)
    assert cs.get(f"{API}/fill").get_json()["data"]["rows"] == []
    assert cs.get(f"{API}/orders/{oid}/options").get_json()["data"]["items"][0]["filled"] is True
    blocked = cs.post(f"{API}/orders/{oid}/options", json=_body(oid, {"base": "슬라이딩", "state": "none"}))
    assert blocked.status_code == 409
    assert [r.lines[0]["key"] for r in _rows(oid, "CURRENT")] == ["r4"]  # 협력사가 고른 값 그대로


def test_only_cs_and_admin(app, world):
    oid = _old_order(app, world, names=("슬라이딩",))
    body = _body(oid, {"base": "슬라이딩", "state": "none"})
    sales = _client(app, db_session.get(User, world["sales"]))
    assert sales.get(f"{API}/fill").status_code == 403
    assert sales.get(f"{API}/orders/{oid}/options").status_code == 403
    assert sales.post(f"{API}/orders/{oid}/options", json=body).status_code == 403
    assert sales.get(f"/erp/partner-statements/orders/{oid}/options").status_code == 403
    partner = _partner(app, world)
    assert partner.post(f"{API}/orders/{oid}/options", json=body).status_code == 403
    assert _rows(oid) == []
    cs = _cs(app)
    assert cs.get(f"/erp/partner-statements/orders/{oid}/options").status_code == 200
    assert cs.post(f"{API}/orders/{oid}/options", json=body).status_code == 200  # 대조군
    assert db_session.query(OrderItemOption).filter(OrderItemOption.order_id == oid).count() == 3
