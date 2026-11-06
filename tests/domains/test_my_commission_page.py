"""FCOMM-01 T7 — 프리랜서 "내 수수료" 화면 ``/erp/my-commission``(서버 렌더 · 스크립트 없음).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §2.2 · §9 · §11.2.
요율 · 금액 · 이름은 모두 가짜 값이다(저장소 공개 — 실제 요율은 설정에만 있다).
"""
from __future__ import annotations

import datetime
import re

import pytest

from db import db_session
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from models import Order, SalesCommissionInput
from tests.domains.test_auth_finance import _login, _make_user

PAGE = "/erp/my-commission"
MATCH = "가짜프리"
OTHER_MATCH = "다른가짜"
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}


# --------------------------------------------------------------------------
# 시드
# --------------------------------------------------------------------------
def _add_freelancer(match_name: str, *, tax_type: str = "NONE", active: bool = True):
    user = _make_user("STAFF", "SALES")
    version, _cfg, _changed = save_freelancer(
        db_session, user.id,
        {"match_name": match_name, "start_month": "2030-01", "tax_type": tax_type, "active": active},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return user


def _order(*, customer: str, manager: str = "", orderer: str = "", stage: str = "CS",
           construction: str | None = "2030-03-10", measurement: str | None = "2030-01-05",
           price: int = 2_500_000, install_cost: int | None = None, extra: dict | None = None) -> int:
    schedule: dict = {}
    if construction is not None:
        schedule["construction"] = {"date": construction}
    if measurement is not None:
        schedule["measurement"] = {"date": measurement}
    sd = {
        "parties": {"manager": {"name": manager}, "orderer": {"name": orderer}, "customer": {"name": customer}},
        "schedule": schedule,
        "items": [{"product_name": "가짜장", "price": price}],
        "workflow": {"stage": stage},
        **(extra or {}),
    }
    order = Order(
        received_date="2030-01-01", customer_name=customer, phone="010-0000-0000", address="가짜시",
        product="가짜장", status="COMPLETED", manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_stage_code=stage, erp_construction_date=construction, erp_measurement_date=measurement,
    )
    db_session.add(order)
    db_session.commit()
    if install_cost is not None:
        db_session.add(SalesCommissionInput(order_id=order.id, install_cost=install_cost, version=1))
        db_session.commit()
    return order.id


def _seed(tax_type: str = "NONE") -> dict:
    fl = _add_freelancer(MATCH, tax_type=tax_type)
    other = _add_freelancer(OTHER_MATCH)
    ded = {"settlement": {"deductions": [
        {"id": "d1", "department": "SALES", "charge_to_user_id": fl.id, "amount": -100_000, "reason": "가짜 재방문"},
    ]}}
    # 라홈: (2,500,000 − 1,000,000 − 100,000) × 4% = 56,000
    _order(customer="라홈고객", manager=MATCH, orderer="라홈 가짜점", install_cost=1_000_000, extra=ded)
    # 개인영업: (2,000,000 − 500,000 − 0) × 8% = 120,000
    _order(customer="개인고객", manager="아무개", orderer=MATCH, price=2_000_000, install_cost=500_000,
           construction="2030-03-01")
    _order(customer="숨고고객", manager=MATCH, orderer="숨고", install_cost=500_000)       # 요율 정하는 중
    _order(customer="하우드고객", manager=MATCH, orderer="하우드")                            # 시공비 기다림
    _order(customer="남의고객", manager=OTHER_MATCH, orderer="라홈", install_cost=1_000_000)
    # 실측일 기준 3월 · 시공 전(예상): (3,000,000 − 1,000,000) × 6% = 120,000
    _order(customer="예상고객", manager=MATCH, orderer="하우드", stage="PRODUCTION", construction=None,
           measurement="2030-03-05", price=3_000_000, install_cost=1_000_000)
    return {"fl": fl, "other": other}


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


def _html(client, query: str = "month=2030-03") -> str:
    resp = client.get(f"{PAGE}?{query}")
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def _content(html: str) -> str:
    """화면 본문(``<div class="foms-mc">`` … 짝 ``</div>``)만 — 공용 레이아웃의 스크립트 · 스타일은 빼고 본다."""
    start = html.index('<div class="foms-mc">')
    depth = 0
    for tag in re.finditer(r"<(/?)div\b", html[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return html[start:start + tag.end()]
    raise AssertionError("foms-mc 본문이 닫히지 않았다")


# --------------------------------------------------------------------------
# 프리랜서 본인
# --------------------------------------------------------------------------
def test_freelancer_sees_own_rows_and_formula(app):
    world = _seed()
    html = _html(_client(app, world["fl"]))

    assert "내 수수료" in html
    assert "3월 시공 완료분" in html
    assert "176,000원" in html  # 56,000 + 120,000 (계산된 줄만)
    for name in ("라홈고객", "개인고객", "숨고고객", "하우드고객"):
        assert name in html
    assert "남의고객" not in html
    assert "예상고객" not in html  # 시공 완료 기준에는 시공 전 줄이 없다
    assert "출고가 2,500,000 − 시공비 1,000,000 − 차감 100,000 = 1,400,000 × 4% = 56,000원" in html
    assert "출고가 2,000,000 − 시공비 500,000 − 차감 0 = 1,500,000 × 8% = 120,000원" in html
    assert "차감 · 가짜 재방문 100,000원" in html
    assert "요율 정하는 중" in html
    assert "시공비 기다림" in html
    for label in ("라홈", "개인영업", "회계팀 지정", "하우드"):
        assert label in html
    assert "3월 10일" in html
    assert "<details" in html


def test_freelancer_user_id_param_is_ignored(app):
    world = _seed()
    html = _html(_client(app, world["fl"]), f"month=2030-03&user_id={world['other'].id}")

    assert "라홈고객" in html
    assert "남의고객" not in html
    assert "님 화면을 보고 있어요" not in html
    assert "user_id=" not in _content(html)


def test_percent_with_fraction(app):
    fl = _make_user("STAFF", "SALES")
    version, _cfg, _changed = save_freelancer(
        db_session, fl.id, {"match_name": MATCH, "start_month": "2030-01", "tax_type": "NONE", "active": True},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, fl.id, {"effective_month": "2030-01", "lahom_bp": 450, "haud_bp": 425, "personal_bp": 800},
             base_version=version, actor_user_id=None)
    db_session.commit()
    _order(customer="반올림고객", manager=MATCH, orderer="라홈", price=2_000_000, install_cost=0)
    html = _html(_client(app, fl))
    assert "= 2,000,000 × 4.5% = 90,000원" in html


# --------------------------------------------------------------------------
# 세금 줄
# --------------------------------------------------------------------------
@pytest.mark.parametrize("tax_type, expected, absent", [
    ("WITHHOLD_3_3", "세금 빼고 170,200원", "부가세 더해"),   # 176,000 − 5,280 − 520
    ("VAT_10", "부가세 더해 193,600원", "세금 빼고"),         # 176,000 + 17,600
    ("NONE", None, None),
])
def test_tax_line_per_tax_type(app, tax_type, expected, absent):
    world = _seed(tax_type)
    html = _content(_html(_client(app, world["fl"])))
    if expected is None:
        assert "세금 빼고" not in html and "부가세 더해" not in html
    else:
        assert expected in html
        assert absent not in html


# --------------------------------------------------------------------------
# 달 · 기준
# --------------------------------------------------------------------------
def test_default_month_is_previous_kst_month(app, monkeypatch):
    import foms.web.sales_commission as page
    monkeypatch.setattr(page, "get_today_kst", lambda: datetime.date(2030, 4, 3))
    world = _seed()
    html = _html(_client(app, world["fl"]), "")

    assert "이번 10일 받을 돈" in html
    assert "2030년 3월" in html
    assert "176,000원" in html


def test_month_and_basis_links(app, monkeypatch):
    import foms.web.sales_commission as page
    monkeypatch.setattr(page, "get_today_kst", lambda: datetime.date(2030, 3, 20))
    world = _seed()
    content = _content(_html(_client(app, world["fl"])))

    assert 'href="/erp/my-commission?month=2030-02&amp;basis=completion"' in content
    assert 'href="/erp/my-commission?month=2030-03&amp;basis=measurement"' in content
    assert 'aria-current="page">시공 완료 기준' in content
    assert "month=2030-04" not in content  # 이번 달 다음은 링크가 없다


def test_measurement_basis_shows_forecast(app):
    world = _seed()
    html = _html(_client(app, world["fl"]), "month=2030-03&basis=measurement")

    assert "3월 실측 — 앞으로 들어올 돈 미리 보기" in html
    assert "예상고객" in html
    assert "예상 120,000원" in html
    assert "라홈고객" not in html  # 실측 1월 줄은 3월 실측 화면에 없다
    assert 'aria-current="page">실측일 기준' in html
    assert "3월 5일" in html


def test_empty_month_message(app):
    world = _seed()
    html = _html(_client(app, world["fl"]), "month=2030-01")
    assert "이 달에는 수수료 줄이 없어요" in html


def test_bad_params_fall_back(app):
    world = _seed()
    html = _html(_client(app, world["fl"]), "month=2030-13&basis=xx")
    assert 'aria-current="page">시공 완료 기준' in html


# --------------------------------------------------------------------------
# 권한
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role, team", [("ADMIN", None), ("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")])
def test_accounting_and_admin_view_with_user_id(app, role, team):
    world = _seed()
    client = _client(app, _make_user(role, team))
    html = _html(client, f"month=2030-03&user_id={world['fl'].id}")

    assert f"{MATCH} 님 화면을 보고 있어요." in html
    assert "라홈고객" in html
    assert "남의고객" not in html
    assert f"user_id={world['fl'].id}" in _content(html)  # 달 · 기준 링크가 대상을 잃지 않는다

    assert client.get(f"{PAGE}?month=2030-03").status_code == 404
    non_freelancer = _make_user("STAFF", "SALES")
    assert client.get(f"{PAGE}?month=2030-03&user_id={non_freelancer.id}").status_code == 404


@pytest.mark.parametrize("role, team", [("STAFF", "SALES"), ("MANAGER", "CS"), ("STAFF", "CS")])
def test_other_staff_denied(app, role, team):
    world = _seed()
    client = _client(app, _make_user(role, team))
    assert client.get(f"{PAGE}?user_id={world['fl'].id}").status_code == 403


def test_inactive_freelancer_denied(app):
    _seed()
    sleeping = _add_freelancer("쉬는가짜", active=False)
    assert _client(app, sleeping).get(PAGE).status_code == 403


def test_login_required(app):
    resp = app.test_client().get(PAGE)
    assert resp.status_code in (302, 401)


def test_allowed_with_policy_guard_on(app):
    world = _seed()
    prev = app.config.get("AUTH_POLICY_ENABLED")
    app.config["AUTH_POLICY_ENABLED"] = True
    try:
        assert _client(app, world["fl"]).get(f"{PAGE}?month=2030-03").status_code == 200
    finally:
        app.config["AUTH_POLICY_ENABLED"] = prev


# --------------------------------------------------------------------------
# 마크업 규약
# --------------------------------------------------------------------------
def test_no_inline_style_and_no_script(app):
    world = _seed()
    content = _content(_html(_client(app, world["fl"])))
    assert 'style="' not in content
    assert "<script" not in content
    src = open("templates/sales_commission/my_commission.html", encoding="utf-8").read()
    assert not re.search(r"\sstyle=", src)
    assert "<script" not in src
    assert "css/contexts/sales_commission/my-commission.css" in src
