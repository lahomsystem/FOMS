"""P2 — 칸반 옆 시트(F2 ①②③④⑤)·브리핑 60vh 보정(F1 ②)·레일 화면 크기 단추(F1 ①)·실패 문구(D5). 2026-11-09 설계서.

옆 시트 fragment 에 전화·주소·상세 링크, 도면 전달본 전부(이미지 + 파일 열기), 공정 4칸 + 불량 칩 4(전체 화면 시트와
같은 루트 data-foms-prod-sheet-page, id 없음), 단추 글 "제작 완료". 칸반 body 가 시트 공통 CSS·JS 를 싣는다.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.domains.test_production_sheet_page import _make_user, _seed_order

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_옆_시트에_연락처_도면_전부_공정_블록이_있다(client) -> None:
    _make_user(client, "p2_prod_side", "PRODUCTION")
    order = _seed_order()
    resp = client.get(f"/erp/production/tablet-sheet/{order.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # 연락처·주소·일정·상세
    assert "010-1234-5678" in html and 'href="tel:01012345678"' in html
    assert "map.kakao.com" in html and "시공팀 박성민, 최우진" in html
    assert f"/erp/orders/{order.id}/mobile" in html and ">상세</a>" in html
    # 도면 전달본: 이미지 2 + 파일 열기 1, 장수
    assert html.count("data-foms-erp-attachment-view-url=") == 2
    assert "상세.pdf 열기" in html and "3장" in html
    # 공정 블록: 루트 1, 공정 4, 불량 칩 4, id 없음(세로 오프캔버스와 안 겹침)
    assert html.count("data-foms-prod-sheet-page") == 1
    assert html.count("data-foms-sheet-step=") == 4 and html.count("data-foms-sheet-defect-reason=") == 4
    assert 'data-foms-sheet-step="cut" aria-pressed="true"' in html and ">1/4<" in html
    assert 'id="foms-production-steps-sheet"' not in html and "foms-prod-steps__list" not in html
    # 단추 글
    assert ">제작 완료<" in html and "생산 완료" not in html
    # 금액 없음(D7)
    assert "1234000" not in html and "1,234,000" not in html


def test_칸반_body_가_시트_공통_CSS_JS_를_싣고_핀이_같다() -> None:
    body = _read("templates/production/partials/tablet_kanban_body.html")
    assert "css/contexts/production/sheet.css') }}?v=20261111a" in body
    assert "js/production/foms-production-sheet-page.js') }}?v=20261110a" in body
    page = _read("templates/production/sheet.html")
    assert "css/contexts/production/sheet.css') }}?v=20261111a" in page
    assert "js/production/foms-production-sheet-page.js') }}?v=20261110a" in page
    js = _read("static/js/production/foms-production-sheet-page.js")
    assert "foms:erp-shell-fragment-swapped" in js and "data-foms-sheet-init" in js
    # 도메인 시트 핀 lockstep(칸반 = 시트 페이지 = 홈 = 출고 CHAIN)
    pin = body.split("tablet-domain-sheets.js') }}?v=")[1].split('"')[0]
    for rel in ("templates/production/sheet.html", "templates/production/home.html"):
        assert f"tablet-domain-sheets.js') }}}}?v={pin}" in _read(rel), rel
    assert f"'/static/js/foms/tablet-domain-sheets.js?v={pin}'" in _read("static/js/shipment/shipment-entry.js")


def test_브리핑_목록_60vh_보정과_번들_핀() -> None:
    css = " ".join(_read("static/css/foundation/foms-tablet-production-kanban.css").split())
    assert "max-height: calc(60vh / var(--foms-ui-zoom, 1))" in css
    bundle = _read("static/css/foundation/foms-tablet-bundle.css")
    assert 'foms-tablet-production-kanban.css?v=20261109b' in bundle and 'foms-tablet-rail.css?v=20261109g' in bundle
    assert "foms-tablet-bundle.css') }}?v=20261111b" in _read("templates/partials/shared/layout_head.html")


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
    steps = _read("static/js/production/foms-production-steps.js")
    assert steps.count(text) == 2
    assert "foms-production-steps.js') }}?v=20261109a" in _read("templates/production/partials/dashboard_body.html")
    for rel in ("static/js/production/foms-production-sheet-page.js", "static/js/production/foms-production-home.js"):
        assert text in _read(rel), rel


def test_옆_시트_템플릿은_인라인_style_이_없다() -> None:
    sheet = _read("templates/production/partials/tablet_sheet.html")
    assert 'style="' not in sheet
    # 뷰어 폴백 인라인 스크립트는 원래 있던 것 하나뿐
    assert sheet.count("<script>") == 1
