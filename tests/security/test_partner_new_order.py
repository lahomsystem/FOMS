"""PARTNER-FOMS 5-1: 협력사 새 주문 화면 — 우리 새 주문 모양(목록 · 상세 틀 · 제품명 ▾ · 주소 찾기).

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.4 · §17.
"""
from __future__ import annotations

import html as html_lib
import json
import re

import pytest

import foms.web.partner as partner_web
from db import db_session
from models import User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_confirm,
    world,
)

_NAMES = re.compile(r"data-pp-product-names='([^']*)'")
_CATALOG = [
    {"name": " 몰딩(푸쉬) ", "price_30cm": 84400, "coupon_value": 7, "additional_options": [{"name": "LED", "price": 55000}]},
    {"name": "\t신발장", "price_1m": 123456},
    {"name": "몰딩(푸쉬)"},
    {"name": ""},
    "잘못된 행",
]


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(partner_web, "load_products", lambda: list(_CATALOG))


def _html(app, user_id, path) -> str:
    resp = _client(app, db_session.get(User, user_id)).get(path)
    assert resp.status_code == 200, path
    return resp.get_data(as_text=True)


def test_new_order_uses_our_item_frame_picker_and_address_window(app, world, catalog):
    html = _html(app, world["partner_a"], "/partner/orders/new")
    # 우리 새 주문 틀: 주문 정보 카드 → 왼쪽 목록 · 오른쪽 상세 → 아래 고정 줄 "보내기".
    assert 'class="card border-secondary pp-order pp-new"' in html
    assert "erp-items-master-detail-shell pp-items-md" in html and 'class="item-rail"' in html
    assert "data-pp-rail-summary" in html and "data-pp-rail-prev" in html and "data-pp-rail-next" in html
    assert re.search(r'class="pp-actions".*?type="submit"', html, re.S)
    # 항목 더하기: PC 왼쪽 목록 '+ 항목' + 휴대폰(목록이 숨을 때) 카드 아래 단추.
    assert html.count("data-pp-add-item") == 2 and "pp-items-md__add" in html
    # 꼭 넣을 칸은 지금과 같다.
    for name in ("customer_name", "customer_phone", "address"):
        assert re.search(rf'name="{name}"[^>]*required', html), name
    # 제품명 ▾ — 새 항목 틀(template)에 단추, 우리 고르기 창 모듈을 싣는다.
    template = re.search(r'<template id="ppItemRow">(.*?)</template>', html, re.S).group(1)
    assert "data-pp-product-pick" in template and "erp-calc-has-trigger" in template
    assert "js/orders/erp-spec-picker.js" in html and "css/wdcalculator/category-picker.css" in html
    # 주소 찾기 — 우리 PC 와 같은 칸, 우리 서버 주소 검색.
    assert 'data-pp-sheet-open="ppAddressModal"' in html
    assert 'data-pp-address-url="/api/address/search"' in html and 'data-pp-address-target="ppAddress"' in html
    for part in ("data-pp-address-query", "data-pp-address-detail", "data-pp-address-results", "data-pp-address-apply"):
        assert part in html, part


def test_product_list_carries_names_only(app, world, catalog):
    html = _html(app, world["partner_a"], "/partner/orders/new")
    names = json.loads(html_lib.unescape(_NAMES.search(html).group(1)))
    assert names == ["몰딩(푸쉬)", "신발장"]  # 앞뒤 공백 · 빈 이름 · 겹친 이름 · 잘못된 행은 뺀다
    for leak in ("84400", "123456", "55000", "price_", "coupon", "additional_options", "LED"):
        assert leak not in html, leak


def test_no_catalog_means_plain_name_field(app, world, monkeypatch):
    monkeypatch.setattr(partner_web, "load_products", lambda: [])
    html = _html(app, world["partner_a"], "/partner/orders/new")
    assert "data-pp-product-pick" not in html and "data-pp-product-names" not in html
    assert "erp-spec-picker.js" not in html
    assert 'data-k="product_name"' in html  # 직접 입력 칸은 그대로


def test_order_screen_picker_only_while_items_editable(app, world, catalog):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    editable = _html(app, world["partner_a"], f"/partner/orders/{order_id}")
    assert editable.count("data-pp-product-pick") == 2  # 서버가 그린 카드 1 + 새 항목 틀 1
    assert _NAMES.search(editable)
    _to_confirm(order_id)
    locked = _html(app, world["partner_a"], f"/partner/orders/{order_id}")
    assert "data-pp-product-pick" not in locked and "data-pp-product-names" not in locked


class _Resp:
    status_code = 200

    def __init__(self, docs):
        self._docs = docs

    def json(self):
        return {"documents": self._docs}


def test_partner_can_search_address_but_not_other_staff_apis(app, world, monkeypatch):
    doc = {"address_name": "서울 송파구 신천동 7-18", "road_address": {"address_name": "서울 송파구 송파대로 345", "x": "127.1", "y": "37.5"}}
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params["query"])
        return _Resp([doc] if "address.json" in url else [])

    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr("foms.api.address.requests.get", fake_get)
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.get("/api/address/search?q=송파대로 345&size=10")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True and body["results"][0]["road_address_name"] == "서울 송파구 송파대로 345"
    assert calls and calls[0] == "송파대로 345"
    # 단가가 든 우리 제품 목록 · 프리셋 API 는 여전히 막힌다(대조군).
    for path in ("/api/wdcalculator/products", "/api/wdcalculator/spec-field-presets"):
        denied = client.get(path)
        assert denied.status_code == 403, path


def test_staff_address_search_unchanged(app, world, monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr("foms.api.address.requests.get", lambda *a, **k: _Resp([]))
    resp = _client(app, db_session.get(User, world["staff"])).get("/api/address/search?q=없는 주소")
    assert resp.status_code == 200 and resp.get_json()["results"] == []
    anon = app.test_client().get("/api/address/search?q=x")
    assert anon.status_code in (302, 401)


def test_photo_zones_on_new_order_and_editable_order(app, world, catalog):
    """5-2: 사진 칸(즉시 추가 · 찍기 · 붙여넣기 · 끌어놓기) — 제품 칸 · 공통 실측 사진 · 초안 도면."""
    html = _html(app, world["partner_a"], "/partner/orders/new")
    template = re.search(r'<template id="ppItemRow">(.*?)</template>', html, re.S).group(1)
    assert 'data-pp-photo-zone="item"' in template and 'capture="environment"' in template
    assert 'data-pp-photo-zone="common"' in html and 'data-pp-photo-zone="draft"' in html
    draft = re.search(r'data-pp-photo-zone="draft".*?data-pp-photo-empty', html, re.S).group(0)
    assert "capture=" not in draft and 'accept="image/*,.pdf,.dwg,.dxf,.zip"' in draft
    assert 'name="photos"' not in html and 'name="drafts"' not in html  # 옛 파일 칸은 걷었다
    assert "js/partner/partner-photo-stage.js" in html

    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    editable = _html(app, world["partner_a"], f"/partner/orders/{order_id}")
    assert editable.count('data-pp-photo-zone="item"') == 2  # 서버가 그린 카드 1 + 새 항목 틀 1
    assert "js/partner/partner-photo-stage.js" in editable
    _to_confirm(order_id)
    locked = _html(app, world["partner_a"], f"/partner/orders/{order_id}")
    assert "data-pp-photo-zone" not in locked and "partner-photo-stage.js" not in locked
