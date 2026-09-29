"""주문 상세 펼침 — 제품 여러 건 목록+상세(erporder 와 같은 모양) 배선 계약.

주문·생산·시공 대시보드가 공용 도우미 static/js/foms/order-items-md.js 와
static/css/components/foms-order-items-md.css 를 함께 싣고, 상세 렌더러가 2건 이상일 때
FomsOrderItemsMD.render 로 목록+상세를 그린다. 하나라도 빠지면 예전처럼 세로로 쌓인다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

HELPER_JS = "static/js/foms/order-items-md.js"
HELPER_CSS = "static/css/components/foms-order-items-md.css"
PIN = "?v=20260929a"

RENDERERS = (
    "static/js/orders/dashboard/erp-dashboard-detail-dom.js",
    "templates/production/partials/scripts.html",
    "static/js/construction/dashboard.js",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_helper_files_exist_and_expose_api() -> None:
    js = _read(HELPER_JS)
    assert "window.FomsOrderItemsMD = { render: render, nav: nav }" in js
    # 프래그먼트 교체로 다시 돌아도 문서 클릭 위임은 한 번만 건다.
    assert "window.__fomsOrderItemsMdBound" in js
    assert ".erp-order-detail .dw-items-md" in _read(HELPER_CSS)


def test_every_surface_loads_helper_js_and_css() -> None:
    # 도우미 JS 는 /erp/ 공통 레이아웃에서 페이지당 한 번 — 조각(fragment)에 두면 탭 전환마다
    # 다시 읽혀 성능 가드(fragment-multi-script)에 걸린다. 세 대시보드 모두 /erp/ 아래다.
    layout = _read("templates/partials/shared/layout_scripts.html")
    erp_block = layout[layout.index("{% if request.path.startswith('/erp/') %}"):]
    assert f"js/foms/order-items-md.js') }}}}{PIN}" in erp_block.split("{% endif %}", 1)[0]
    for rel in (
        "templates/production/partials/scripts.html",
        "templates/construction/partials/scripts.html",
    ):
        assert "filename='js/foms/order-items-md.js'" not in _read(rel), f"{rel}: 조각에 도우미 script 를 다시 넣지 말 것"

    css_tag = f"css/components/foms-order-items-md.css') }}}}{PIN}"
    for rel in (
        "templates/orders/partials/dashboard_styles.html",
        "templates/production/partials/styles.html",
        "templates/construction/partials/styles.html",
    ):
        assert css_tag in _read(rel), f"{rel} 에 목록+상세 CSS 링크가 없다"


def test_renderers_use_helper_for_multiple_items_only() -> None:
    for rel in RENDERERS:
        body = _read(rel)
        assert "items.length > 1 && !!itemsMd" in body, f"{rel}: 2건 이상 + 도우미 있을 때만 목록+상세"
        assert "itemsMd.render(items, cards)" in body, f"{rel}: 목록+상세 렌더 호출 없음"
        assert "itemsMd.nav(idx, items.length)" in body, f"{rel}: 카드 머리 이전/다음 없음"


def test_orders_detail_amount_block_rendered_once() -> None:
    """출고가·예약금·잔금은 주문 합계다 — 제품마다 반복하면 제품 가격으로 오해된다."""
    body = _read("static/js/orders/dashboard/erp-dashboard-detail-dom.js")
    assert "erp-items-total-${orderId}-${idx}" not in body
    assert "erp-items-total-${orderId}-${i}" not in body
    assert 'id="erp-items-total-${orderId}"' in body
