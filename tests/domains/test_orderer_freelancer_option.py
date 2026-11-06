"""FCOMM-01 T7 — 발주사 선택지의 프리랜서 이름(D3) · 모바일 서랍 "내 수수료" 링크 · 브랜드 회귀(D14).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §1(D3 · D14) · §2.2 · §11.3.
이름은 모두 가짜 값이다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from flask import g, render_template

from db import db_session
from foms.services.kakao_alimtalk import resolve_brand
from foms.services.sales_commission.settings import load_settings, save_freelancer
from foms.services.settlement_aggregation import BRAND_GENERAL, brand_channel_of
from models import Order
from tests.domains.test_auth_finance import _login, _make_user

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = "가짜프리"
SLEEPING = "쉬는가짜"
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
DRAWER = 'id="erp-mobile-menu-drawer"'
DRAWER_LINK = 'href="/erp/my-commission"'


def _freelancer(match_name: str, *, active: bool = True):
    user = _make_user("STAFF", "SALES")
    save_freelancer(db_session, user.id,
                    {"match_name": match_name, "start_month": "2030-01", "tax_type": "NONE", "active": active},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    return user


def _order(orderer: str = "라홈") -> int:
    order = Order(
        received_date="2030-01-01", customer_name="가짜고객", phone="010-0000-0000", address="가짜시",
        product="가짜장", status="RECEIVED", is_erp_order=True, erp_stage_code="RECEIVED",
        structured_data={"workflow": {"stage": "RECEIVED"},
                         "parties": {"customer": {"name": "가짜고객"}, "orderer": {"name": orderer}},
                         "items": [{"product_name": "가짜장"}]},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _mobile_v2(monkeypatch, user_id: int) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user_id))


def _options(html: str, select_id: str) -> list[list[str]]:
    """``<select id=…>`` 마다 option value 목록(PC · 모바일이 같은 id 를 쓰므로 여러 개)."""
    found = re.findall(rf'<select[^>]*id="{select_id}"[^>]*>(.*?)</select>', html, re.S)
    return [re.findall(r'<option value="([^"]*)"', block) for block in found]


# --------------------------------------------------------------------------
# 발주사 선택지
# --------------------------------------------------------------------------
def test_order_tab_pc_and_mobile_list_active_freelancer_names(app, monkeypatch):
    _freelancer(ACTIVE)
    _freelancer(SLEEPING, active=False)
    viewer = _make_user("ADMIN", None)
    _mobile_v2(monkeypatch, viewer.id)
    client = app.test_client()
    _login(client, viewer)

    html = client.get(f"/edit/{_order()}").get_data(as_text=True)

    selects = _options(html, "erp-orderer-select")
    assert len(selects) == 2, "PC 와 모바일 주문 탭 둘 다 그려져야 한다"
    for values in selects:
        assert values == ["라홈", "하우드", "숨고", ACTIVE]
    assert SLEEPING not in html


def test_order_tab_without_freelancers_keeps_three_options(app):
    viewer = _make_user("ADMIN", None)
    client = app.test_client()
    _login(client, viewer)

    html = client.get(f"/edit/{_order()}").get_data(as_text=True)

    selects = _options(html, "erp-orderer-select")
    assert selects and all(values == ["라홈", "하우드", "숨고"] for values in selects)


def test_wizard_step1_lists_active_freelancer_before_custom(app):
    _freelancer(ACTIVE)
    _freelancer(SLEEPING, active=False)
    with app.test_request_context("/"):
        g.current_user = None
        html = render_template("orders/wizard/step1_basic.html", today="2030-01-01")

    assert _options(html, "wiz-orderer-mode") == [["라홈", "하우드", "숨고", ACTIVE, "__custom__"]]


def test_load_path_matches_any_existing_option():
    """불러오기는 선택지에 있는 값이면 고른다(이름을 코드에 박지 않는다) — 프리랜서 이름도 직접 입력으로 빠지지 않게."""
    js = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    block = js[js.index("const ordererName = (sd?.parties?.orderer?.name"):]
    block = block[:block.index("toggleOrdererUI();")]
    assert "selectEl.options" in block
    assert "'숨고'" not in block


# --------------------------------------------------------------------------
# 서랍 링크
# --------------------------------------------------------------------------
def _drawer(app, monkeypatch, user) -> str:
    _mobile_v2(monkeypatch, user.id)
    client = app.test_client()
    _login(client, user)
    body = client.get("/erp/dashboard", headers={"User-Agent": MOBILE_UA}).get_data(as_text=True)
    start = body.index(DRAWER)
    return body[start:start + 20000]


def test_drawer_link_only_for_active_freelancer(app, monkeypatch):
    fl = _freelancer(ACTIVE)
    drawer = _drawer(app, monkeypatch, fl)
    assert DRAWER_LINK in drawer
    assert "내 수수료" in drawer


@pytest.mark.parametrize("who", ["sleeping", "sales", "admin"])
def test_drawer_link_hidden_for_others(app, monkeypatch, who):
    _freelancer(ACTIVE)
    if who == "sleeping":
        user = _freelancer(SLEEPING, active=False)
    else:
        user = _make_user("STAFF", "SALES") if who == "sales" else _make_user("ADMIN", None)
    drawer = _drawer(app, monkeypatch, user)
    assert DRAWER in drawer
    assert DRAWER_LINK not in drawer


# --------------------------------------------------------------------------
# D14 회귀 — 발주사가 프리랜서 이름이어도 브랜드 판정은 지금 그대로
# --------------------------------------------------------------------------
def test_freelancer_orderer_keeps_brand_behaviour():
    sd = {"parties": {"orderer": {"name": ACTIVE}}}
    assert resolve_brand(sd) == "HAUD"
    assert brand_channel_of(sd, "일반") == BRAND_GENERAL
