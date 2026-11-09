"""생산팀 P1 — 403 문구·문서 진입 302(F7 ②), 세로 하단 탭 생산 첫 칸(F6), 금액 가리기(D7). 2026-11-09 설계서.

생산팀은 컨트롤타워 시트 fragment 가 403 이고(그대로), 주소창으로 열면 edit 가 아니라 모바일 상세로 간다.
세로(폰 화면) 하단 탭은 생산팀이면 생산이 첫 칸이고 생산 홈으로 간다. 완료 보드·모바일 상세의 금액은 생산팀에겐 없다.
"""

from __future__ import annotations

from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_permissions import can_view_order_amounts
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]


def _make_user(client, username: str, team: str | None, role: str = "STAFF") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _enable_v2(monkeypatch, user_id: int) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user_id))


def _order(stage: str = "PRODUCTION", *, status: str | None = None, price: int = 1234567) -> Order:
    today = get_today_kst().isoformat()
    sd = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": "금액시험", "phone": "010-0000-0000"}},
        "site": {"address_full": "서울 어딘가 1"},
        "schedule": {"construction": {"date": today}},
        "items": [{"product_name": "거실장", "name": "거실장", "spec_width": "3100", "quantity": 1, "price": price}],
    }
    order = Order(
        received_date=today, customer_name="금액시험", phone="010-0000-0000", address="서울 어딘가 1", product="거실장",
        manager_name="관리", status=status or stage, is_erp_order=True, structured_data=sd, erp_stage_code=stage,
        erp_construction_date=today,
    )
    db_session.add(order)
    db_session.commit()
    return order


# ── F7 ②: 403 문구 + 문서 진입 302 ──

def test_생산팀_컨트롤타워_시트는_403이고_주소창으로_열면_모바일_상세로(client) -> None:
    _make_user(client, "p1_prod_sheet", "PRODUCTION")
    order = _order()
    assert client.get(f"/erp/dashboard/tablet-sheet/{order.id}").status_code == 403
    resp = client.get(f"/erp/dashboard/tablet-sheet/{order.id}", headers={"Sec-Fetch-Dest": "document"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/erp/orders/{order.id}/mobile")


def test_관리자는_주소창으로_열면_편집_페이지로(client) -> None:
    _make_user(client, "p1_admin_sheet", "CS", role="ADMIN")
    order = _order()
    resp = client.get(f"/erp/dashboard/tablet-sheet/{order.id}", headers={"Sec-Fetch-Dest": "document"})
    assert resp.status_code == 302 and "/edit/" in resp.headers["Location"]


def test_fragment_loader_403_문구와_상세_링크_핀() -> None:
    js = (ROOT / "static/js/foms/fragment-loader.js").read_text(encoding="utf-8")
    assert "이 주문은 보기만 할 수 있어요." in js
    assert "/erp/orders/' + m[1] + '/mobile" in js
    assert "httpErr.status = res.status" in js and "err && err.status" in js
    scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    assert "js/foms/fragment-loader.js') }}?v=20261109a" in scripts


# ── F6: 세로 하단 탭 ──

def _bottom_nav(html: str) -> tuple[list[str], list[str]]:
    """하단 탭(erp_mobile_bottom_nav.html)의 id 와 href 를 순서대로."""
    import re

    start = html.index('<nav class="erp-mobile-bottom-nav"')
    block = html[start:html.index("</nav>", start)]
    return re.findall(r'data-foms-nav-id="([^"]+)"', block), re.findall(r'href="([^"]+)"', block)


def test_생산팀_세로_하단_탭은_생산이_첫_칸이고_생산_홈으로_간다(client, monkeypatch) -> None:
    user = _make_user(client, "p1_prod_tabs", "PRODUCTION")
    _enable_v2(monkeypatch, user.id)
    html = client.get("/erp/production/home").get_data(as_text=True)
    ids, hrefs = _bottom_nav(html)
    assert ids == ["production", "shipment", "construction", "dashboard"]
    assert hrefs[0].endswith("/erp/production/home")


def test_CS_세로_하단_탭은_그대로(client, monkeypatch) -> None:
    user = _make_user(client, "p1_cs_tabs", "CS")
    _enable_v2(monkeypatch, user.id)
    html = client.get("/erp/production/dashboard").get_data(as_text=True)
    ids, hrefs = _bottom_nav(html)
    assert ids[0] == "dashboard" and "production" not in ids
    assert not any(h.endswith("/erp/production/home") for h in hrefs)


# ── D7: 금액 가리기 ──

def test_금액_술어() -> None:
    class _U:
        def __init__(self, team, partner=None):
            self.team = team
            self.partner_org_id = partner

    assert can_view_order_amounts(_U("PRODUCTION")) is False
    assert can_view_order_amounts(_U("production ")) is False
    assert can_view_order_amounts(_U("CS")) is True and can_view_order_amounts(_U(None)) is True
    assert can_view_order_amounts(_U("PRODUCTION", partner=3)) is True
    assert can_view_order_amounts(None) is True  # 사용자 없음(내부 호출) = 가리지 않음, 접근은 login_required 몫


def test_생산팀_모바일_상세에는_금액이_없다(client) -> None:
    _make_user(client, "p1_prod_detail", "PRODUCTION")
    order = _order()
    html = client.get(f"/erp/orders/{order.id}/mobile").get_data(as_text=True)
    assert "1,234,567" not in html and "1234567" not in html
    assert "품목 금액" not in html and "foms-detail-amount-title" not in html
    assert "거실장" in html


def test_CS_모바일_상세에는_금액이_있다(client) -> None:
    _make_user(client, "p1_cs_detail", "CS")
    order = _order()
    html = client.get(f"/erp/orders/{order.id}/mobile").get_data(as_text=True)
    assert "1,234,567" in html and "품목 금액" in html and "foms-detail-amount-title" in html


def test_생산팀_완료_보드는_금액_열_없이_CS_는_그대로(client, monkeypatch) -> None:
    _order("COMPLETED", status="COMPLETED")
    prod = _make_user(client, "p1_prod_done", "PRODUCTION")
    _enable_v2(monkeypatch, prod.id)
    client.set_cookie("foms_ptr", "coarse", domain="localhost")
    html = client.get("/erp/completion").get_data(as_text=True)
    assert "foms-completion-grid" in html, "태블릿 그리드가 안 그려졌다(v2 코호트·coarse 쿠키 확인)"
    grid = html[html.find("foms-completion-grid"):]
    assert "미수 합계" not in grid and ">출고가<" not in grid and ">예약금<" not in grid and ">잔금<" not in grid
    csv_text = client.get("/erp/completion/export.csv").get_data(as_text=True)
    assert "출고가" not in csv_text and "완료일,고객,제품,현금영수증,정산상태" in csv_text

    cs = _make_user(client, "p1_cs_done", "CS")
    _enable_v2(monkeypatch, cs.id)
    html_cs = client.get("/erp/completion").get_data(as_text=True)
    grid_cs = html_cs[html_cs.find("foms-completion-grid"):]
    assert "미수 합계" in grid_cs and ">출고가<" in grid_cs
    assert "출고가,예약금,잔금" in client.get("/erp/completion/export.csv").get_data(as_text=True)


def test_생산팀_완료_시트에는_금액_절이_없다(client) -> None:
    order = _order("COMPLETED", status="COMPLETED")
    _make_user(client, "p1_prod_csheet", "PRODUCTION")
    html = client.get(f"/erp/completion/tablet-sheet/{order.id}").get_data(as_text=True)
    assert "foms-completion-sheet__amounts" not in html and "출고가" not in html
    _make_user(client, "p1_cs_csheet", "CS")
    html_cs = client.get(f"/erp/completion/tablet-sheet/{order.id}").get_data(as_text=True)
    assert "foms-completion-sheet__amounts" in html_cs and "출고가" in html_cs
