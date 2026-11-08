"""FCOMM-01 11-08 점검(에이전트 5기)에서 나온 프리랜서 화면 결함 고침.

* 태블릿 가로 대시보드 주문 창(``/erp/dashboard/tablet-sheet/<id>``) — 허용 목록에 빠져 302 로 대시보드가 통째로 창에
  들어갔다. 내 주문 200, 남의 · 없는 주문 404(같은 답).
* 태블릿 레일 강조 — 도면 · 견적 계산기 · 내 수수료 화면에서 어느 칸도 강조되지 않았다(메뉴 id 와 판정 id 가 다름).
* 휴대폰 아래 탭 JS 경로표에 내 수수료가 없어 화면을 읽은 뒤 강조가 지워졌다.
* 견적 계산기 "제품 설정" 단추 — 프리랜서에게는 막힌 화면이라 숨긴다(회사 직원은 그대로).
* 실측 · 출고 판이 막힌 설정 API 를 불러 콘솔 403 — 프리랜서면 부르지 않는다.
* 내 수수료 어두운 테마 — 흰 상자 셋은 글자색도 고정한다.
"""
from __future__ import annotations

from pathlib import Path

from flask import g

from foms.services.foms_split_view import build_split_side_items, resolve_tablet_rail_active_id
from tests.domains.test_auth_finance import _make_user
from tests.security.test_freelancer_own_order_rights import _client, _freelancer, _link, _order

_ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_tablet_dashboard_sheet_own_order_only(app):
    fl = _freelancer()
    own, other = _order(fl.match_name), _order("남의담당")
    _link(own, fl)
    client = _client(app, fl)
    mine = client.get(f"/erp/dashboard/tablet-sheet/{own}")
    assert mine.status_code == 200 and mine.headers.get("X-FOMS-Fragment") == "1"
    theirs = client.get(f"/erp/dashboard/tablet-sheet/{other}")
    missing = client.get("/erp/dashboard/tablet-sheet/99999999")
    assert theirs.status_code == missing.status_code == 404
    # 음성 대조군: 회사 영업 직원은 남의 주문 창도 연다.
    staff = _client(app, _make_user("STAFF", "SALES"))
    assert staff.get(f"/erp/dashboard/tablet-sheet/{other}").status_code == 200


def test_tablet_rail_highlights_every_freelancer_screen(app):
    fl = _freelancer()
    for path, expected in (("/erp/drawing-workbench", "drawing"), ("/wdcalculator", "wdcalculator"),
                           ("/erp/my-commission", "my_commission"), ("/erp/measurement", "measurement")):
        with app.test_request_context(path):
            g.current_user = fl
            items = build_split_side_items(fl, active_id=resolve_tablet_rail_active_id(path))
        assert [i["id"] for i in items if i["active"]] == [expected], path


def test_bottom_nav_js_knows_my_commission_path():
    js = _read("static/js/foms/bottom-nav-shell.js")
    assert '{ id: "my_commission", prefix: "/erp/my-commission" }' in js
    assert 'my_commission: "내 수수료"' in js


def test_calculator_product_settings_button_hidden_for_freelancer_only(app):
    fl = _freelancer()
    html = _client(app, fl).get("/wdcalculator").get_data(as_text=True)
    assert "/wdcalculator/product-settings" not in html
    staff_html = _client(app, _make_user("STAFF", "SALES")).get("/wdcalculator").get_data(as_text=True)
    assert "/wdcalculator/product-settings" in staff_html  # 음성 대조군


def test_blocked_settings_api_is_not_called_by_freelancer_boards():
    for rel in ("static/js/measurement/dashboard.js", "static/js/shipment/shipment-dashboard.js"):
        js = _read(rel)
        assert "document.querySelector('script[data-foms-prefetch-allow]')" in js, rel
        assert js.count("fetch('/api/erp/shipment-settings')") == 1, rel
    # 표식은 켜진 프리랜서에게만 그린다(셸 미리 받기 좁히기 — layout_scripts.html).
    assert "if (current_user and is_sales_freelancer()) else ''" in _read("templates/partials/shared/layout_scripts.html")


def test_my_commission_white_boxes_fix_text_color():
    css = _read("static/css/contexts/sales_commission/my-commission.css")
    for selector in (".foms-mc__total{", ".foms-mc__list{", ".foms-mc__recent-list{"):
        rule = css[css.index(selector):css.index("}", css.index(selector))]
        assert "background:#fff" in rule and "color:#1f2937" in rule, selector
