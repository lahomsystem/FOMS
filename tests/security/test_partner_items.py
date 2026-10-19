"""PARTNER-FOMS 1단계: 협력사 제품 항목 입력 확장 · 제품별 실측 사진 계약.

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.4 · §4.3 · §4.5 · §8.
- 제품마다 규격 여러 줄, 복합 폭(긴 치수), 제품 속성 다섯 칸 + 추가 입력 — 우리 주문 화면과 같은 키.
- 옛 화면 스크립트(하루 캐시)가 보내는 옛 모양(width/depth/height/memo)도 그대로 받는다.
- 제품 실측 사진은 우리 직원 업로드와 같은 item_index(+ 안정 item_id)로 묶는다.
"""
from __future__ import annotations

import io

from db import db_session
from foms.services.orders.item_identity import resolve_active_item_id
from foms.services.partners import orders as partner_orders
from models import Order, OrderAttachment, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    fake_storage,
    world,
)

_COMPOSITE_W = "5700(2402+1864+1434)"
_RICH_ITEMS = [
    {
        "product_name": "드레스룸 ㄷ자",
        "spec_rows": [
            {"spec_width": _COMPOSITE_W, "spec_depth": "600", "spec_height": "2350"},
            {"spec_width": "2352+2100+2860", "spec_depth": "450", "spec_height": "2350"},
            {"spec_width": "", "spec_depth": "", "spec_height": ""},  # 빈 줄은 버린다
        ],
        "internal": "선반 + 행거 2단 + 서랍 3",
        "color": "화이트 오크",
        "option_detail": "LED 바",
        "handle": "상담",
        "misc": "드레스룸 · 천장 몰딩 있음",
        "extra_input": "문 쪽 벽은 비움",
    },
    {"product_name": "", "spec_rows": [{"spec_width": "999"}]},  # 이름 없는 품목은 버린다
    {"product_name": "현관 신발장", "spec_rows": [{"spec_width": "1200", "spec_depth": "350", "spec_height": "2300"}]},
]


def _rich_order(app, partner_id) -> int:
    """풍부한 품목 주문을 만들고 주문 번호를 돌려준다(요청 뒤 세션이 바뀌어 객체 대신 번호)."""
    resp = _create(app, partner_id, {**_PAYLOAD, "items": _RICH_ITEMS})
    body = resp.get_json()
    assert resp.status_code == 200 and body["success"] is True, body
    assert body["data"]["item_count"] == 2
    return body["data"]["order_id"]


def _upload_item(client, order_id, filename, kind="photo", item_index=None):
    data = {"kind": kind, "file": (io.BytesIO(b"x" * 10), filename)}
    if item_index is not None:
        data["item_index"] = str(item_index)
    return client.post(f"/api/partner/orders/{order_id}/files", data=data, content_type="multipart/form-data")


# --------------------------------------------------------------------------
# 제품 항목 입력
# --------------------------------------------------------------------------
def test_rich_items_keep_multi_spec_rows_attributes_and_extra_input(app, world):
    order = db_session.get(Order, _rich_order(app, world["partner_a"]))
    items = order.structured_data["items"]
    assert [it["product_name"] for it in items] == ["드레스룸 ㄷ자", "현관 신발장"]
    first = items[0]
    assert first["spec_rows"] == [
        {"spec_width": _COMPOSITE_W, "spec_depth": "600", "spec_height": "2350"},
        {"spec_width": "2352+2100+2860", "spec_depth": "450", "spec_height": "2350"},
    ]
    assert {k: first[k] for k in partner_orders.ATTRIBUTE_KEYS} == {
        "internal": "선반 + 행거 2단 + 서랍 3", "color": "화이트 오크", "option_detail": "LED 바",
        "handle": "상담", "misc": "드레스룸 · 천장 몰딩 있음",
    }
    assert first["extra_input"] == "문 쪽 벽은 비움"
    # 원문 사본도 같은 모양으로 남는다(실측 책임 근거). 작업본에만 붙는 품목 uid(주문 생성 때 발급)는 뺀다.
    working = [{k: v for k, v in it.items() if k != "uid"} for it in items]
    assert all(it.get("uid") for it in items)
    assert order.structured_data["partner_intake"]["items"] == working
    # 빈 속성 칸은 키를 만들지 않는다(우리 화면이 "상담" 기본값을 그대로 보여 주게).
    assert "internal" not in items[1] and "extra_input" not in items[1]


def test_legacy_flat_payload_still_accepted(app, world):
    # 옛 화면 스크립트(하루 캐시)가 보내는 모양 — 대조군: 지금까지와 같은 결과.
    legacy = {**_PAYLOAD, "items": [{"product_name": "붙박이장", "width": "2400", "depth": "600",
                                      "height": "2300", "quantity": "1", "memo": "몰딩 있음"}]}
    resp = _create(app, world["partner_a"], legacy)
    assert resp.status_code == 200
    item = db_session.get(Order, resp.get_json()["data"]["order_id"]).structured_data["items"][0]
    assert item["spec_rows"] == [{"spec_width": "2400", "spec_depth": "600", "spec_height": "2300"}]
    assert item["misc"] == "몰딩 있음" and item["quantity"] == "1"


def test_dimension_and_row_limits(app, world):
    long_w = "+".join(["1234"] * 30)  # 149자 — 예전 20자 제한이면 잘렸다
    rows = [{"spec_width": str(1000 + i)} for i in range(partner_orders.MAX_SPEC_ROWS + 5)]
    payload = {**_PAYLOAD, "items": [
        {"product_name": "긴 치수", "spec_rows": [{"spec_width": long_w}]},
        {"product_name": "줄 많음", "spec_rows": rows},
    ]}
    resp = _create(app, world["partner_a"], payload)
    assert resp.status_code == 200
    items = db_session.get(Order, resp.get_json()["data"]["order_id"]).structured_data["items"]
    assert items[0]["spec_rows"][0]["spec_width"] == long_w[: partner_orders.DIM_LIMIT]
    assert len(items[0]["spec_rows"][0]["spec_width"]) == partner_orders.DIM_LIMIT
    assert len(items[1]["spec_rows"]) == partner_orders.MAX_SPEC_ROWS


def test_item_with_only_empty_spec_rows_keeps_one_blank_row(app, world):
    payload = {**_PAYLOAD, "items": [{"product_name": "치수 나중에", "spec_rows": [{}, {"spec_width": " "}]}]}
    resp = _create(app, world["partner_a"], payload)
    item = db_session.get(Order, resp.get_json()["data"]["order_id"]).structured_data["items"][0]
    assert item["spec_rows"] == [{"spec_width": "", "spec_depth": "", "spec_height": ""}]


# --------------------------------------------------------------------------
# 제품별 실측 사진
# --------------------------------------------------------------------------
def test_item_photo_links_item_index_and_stable_item_id(app, world, fake_storage):
    order_id = _rich_order(app, world["partner_a"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _upload_item(client, order_id, "wall.jpg", item_index=1).status_code == 200
    assert _upload_item(client, order_id, "site.jpg").status_code == 200  # 대조군: 공통 사진
    rows = db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).order_by(OrderAttachment.id).all()
    assert [(r.category, r.item_index) for r in rows] == [("measurement", 1), ("measurement", None)]
    assert rows[0].item_id == resolve_active_item_id(db_session, order_id, 1) and rows[0].item_id
    assert rows[1].item_id is None
    assert all(r.storage_key.split("/")[2] == "partner_measurement" for r in rows)


def test_item_photo_rejects_bad_index_or_draft_kind(app, world, fake_storage):
    order_id = _rich_order(app, world["partner_a"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _upload_item(client, order_id, "a.jpg", item_index=2).status_code == 400  # 품목은 2개(0·1)
    assert _upload_item(client, order_id, "a.jpg", item_index="x").status_code == 400
    assert _upload_item(client, order_id, "a.jpg", item_index=-1).status_code == 400
    assert _upload_item(client, order_id, "d.pdf", kind="draft", item_index=0).status_code == 400
    assert fake_storage.calls == []


def test_item_photo_on_other_company_order_is_hidden(app, world, fake_storage):
    other_id = _rich_order(app, world["partner_b"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _upload_item(client, other_id, "a.jpg", item_index=0).status_code == 404
    assert fake_storage.calls == []


def test_detail_page_shows_every_spec_row_attributes_and_item_photo_label(app, world, fake_storage):
    order_id = _rich_order(app, world["partner_a"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _upload_item(client, order_id, "wall.jpg", item_index=0).status_code == 200
    html = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert _COMPOSITE_W in html and "2352+2100+2860" in html
    assert "규격 2" in html and "화이트 오크" in html and "문 쪽 벽은 비움" in html
    assert "실측 사진 · 드레스룸 ㄷ자" in html
