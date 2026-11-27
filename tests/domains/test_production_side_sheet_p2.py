"""P2 — 브리핑 60vh 보정(F1 ②)·레일 화면 크기 단추(F1 ①)·실패 문구(D5). 2026-11-09 설계서.

칸반 옆 시트(F2 ①②③④⑤) 몫은 2026-11-27 옛 생산 보드와 함께 지웠다(옆 시트 라우트 · 템플릿 · 칸반 본문 없음).
남은 계약: 도메인 시트 JS 핀은 싣는 곳(작업 시트 · 첫 화면 · 출고 CHAIN)이 같은 값, 확인 창 목록 60vh 보정, 레일, 실패 문구.
"""

from __future__ import annotations

from pathlib import Path

from tests.domains.test_production_sheet_page import _make_user

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_시트_공통_JS_를_싣고_도메인_시트_핀이_같다() -> None:
    page = _read("templates/production/sheet.html")
    assert "js/production/foms-production-sheet-page.js') }}?v=" in page
    assert "css/contexts/production/sheet.css') }}?v=20261127u" in page
    js = _read("static/js/production/foms-production-sheet-page.js")
    assert "foms:erp-shell-fragment-swapped" in js and "data-foms-sheet-init" in js
    # 도메인 시트 핀 lockstep(첫 화면 = 작업 시트 = 출고 CHAIN — 옛 칸반 본문은 2026-11-27 지움)
    home = _read("templates/production/partials/home_body.html")
    pin = home.split("tablet-domain-sheets.js') }}?v=")[1].split('"')[0]
    for rel in ("templates/production/sheet.html", "templates/production/partials/home_body.html"):
        assert f"tablet-domain-sheets.js') }}}}?v={pin}" in _read(rel), rel
    assert f"'/static/js/foms/tablet-domain-sheets.js?v={pin}'" in _read("static/js/shipment/shipment-entry.js")


def test_브리핑_목록_60vh_보정과_번들_핀() -> None:
    css = " ".join(_read("static/css/foundation/foms-tablet-production-kanban.css").split())
    assert "max-height: calc(60vh / var(--foms-ui-zoom, 1))" in css
    bundle = _read("static/css/foundation/foms-tablet-bundle.css")
    assert 'foms-tablet-production-kanban.css?v=20261127p' in bundle and 'foms-tablet-rail.css?v=20261122t' in bundle
    assert "foms-tablet-bundle.css') }}?v=20261127p" in _read("templates/partials/shared/layout_head.html")


def test_레일_브랜드_아래_화면_크기_단추() -> None:
    rail = _read("templates/partials/shared/foms_tablet_rail.html")
    brand = rail.index('class="foms-tablet-rail__brand"')
    zoom = rail.index("foms_ui_zoom_control.html")
    first_item = rail.index("{% for item in foms_tablet_rail_items()")
    assert brand < zoom < first_item
    assert "foms_ui_zoom_variant = 'rail'" in rail
    css = _read("static/css/foundation/foms-tablet-rail.css")
    assert ".foms-tablet-rail .foms-ui-zoom--rail" in css and "flex-direction: column" in css


def test_레일_렌더에_화면_크기_단추가_들어간다(client, monkeypatch) -> None:
    user = _make_user(client, "p2_prod_rail", "PRODUCTION")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    html = client.get("/erp/production/home").get_data(as_text=True)
    rail = html[html.index('class="foms-tablet-rail"'):]
    rail = rail[: rail.index("</nav>")]
    assert 'class="foms-ui-zoom foms-ui-zoom--rail"' in rail
    assert rail.count("data-foms-ui-zoom-ctl") == 1


def test_실패_문구는_한_가지(client) -> None:
    text = "연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요."
    ds = _read("static/js/foms/tablet-domain-sheets.js")
    assert "처리 중 오류가 발생했습니다." not in ds and ds.count(text) == 4
    for rel in ("static/js/production/foms-production-sheet-page.js", "static/js/production/foms-production-home.js"):
        assert text in _read(rel), rel

