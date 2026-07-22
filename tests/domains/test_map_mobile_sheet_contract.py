"""실측 동선 지도(map_view) 모바일 재설계 계약 테스트.

지키는 계약:
  1. 모바일 게이트 문자열이 프로젝트 SSOT(foms-shell.css)와 바이트 동일 (CSS·JS 3곳)
  2. 신규 자원은 인라인이 아니라 별도 파일 + defer 로만 실린다 (성능 가드 G1)
  3. 시트/상세 승격 계약(3-스냅, body 승격, 배경 잠금, 뒤로가기)이 살아있다
  4. 카카오 엔진의 기존 전역 시그니처가 유지된다 (엔진 READ-ONLY)
"""
from pathlib import Path

TEMPLATE = Path("templates/measurement/map_view.html")
CSS = Path("static/css/measurement/map-mobile.css")
JS = Path("static/js/measurement/map-mobile-sheet.js")
KAKAO_JS = Path("static/js/measurement/map-view-kakao.js")
SHELL_CSS = Path("static/css/foundation/foms-shell.css")

GATE = (
    "(max-width: 991.98px), "
    "((min-width: 992px) and (pointer: coarse) and (orientation: portrait))"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mobile_gate_is_byte_identical_to_project_ssot():
    assert GATE in _read(SHELL_CSS), "SSOT(foms-shell.css) 게이트 문자열이 바뀌었다"
    assert GATE in _read(CSS)
    assert GATE in _read(JS)
    assert GATE in _read(KAKAO_JS)


def test_template_links_mobile_assets_with_defer():
    content = _read(TEMPLATE)
    assert "css/measurement/map-mobile.css" in content
    assert "js/measurement/map-mobile-sheet.js" in content
    # 신규 스크립트는 렌더 차단 금지(가드 G1)
    for line in content.splitlines():
        if "map-mobile-sheet.js" in line and "<script" in line:
            assert " defer" in line, "map-mobile-sheet.js 는 defer 필수"
            break
    else:  # pragma: no cover - 위 링크 assert 가 먼저 실패한다
        raise AssertionError("map-mobile-sheet.js <script> 태그를 찾지 못함")


def test_mobile_css_loads_after_inline_style_block():
    """인라인 <style> 뒤에 링크돼야 동일 특이성에서 신규 규칙이 이긴다."""
    content = _read(TEMPLATE)
    assert content.index("</style>") < content.index("css/measurement/map-mobile.css")


def test_legacy_media_arm_no_longer_pins_panel_height():
    """40% 고정 높이(카드 1건도 안 보이던 원인)가 제거되었는지."""
    content = _read(TEMPLATE)
    assert "flex: 0 0 40%;" not in content
    assert "flex: 0 0 60%;" not in content
    # 경계는 시트 게이트와 동일 — 992px 정확히는 PC 2-pane 유지
    assert "@media (max-width: 992px) {" not in content


def test_sheet_has_three_snaps_and_transform_only_animation():
    css = _read(CSS)
    for snap in ("fmm-snap-peek", "fmm-snap-half", "fmm-snap-full"):
        assert snap in css
    assert "transition: transform .28s cubic-bezier(.32, .72, 0, 1);" in css
    # 스냅 이동은 transform 만 — height/top 애니메이션(리플로우) 금지
    assert "transition: height" not in css
    assert "transition: all" not in css


def test_sheet_js_is_singleton_guarded_and_es5_iife():
    js = _read(JS)
    assert "window.__FOMS_MAP_MOBILE_BOUND" in js
    assert "'use strict';" in js
    for banned in ("=>", "const ", "let ", "`"):
        assert banned not in js, f"ES5 IIFE 규약 위반: {banned!r}"


def test_detail_sheet_promotion_contract():
    js = _read(JS)
    css = _read(CSS)
    # 시트의 transform 이 fixed 컨테이닝 블록이 되므로 body 직속 승격이 필수
    assert "document.body.appendChild(detailPanel);" in js
    assert "fmm-detail-sheet" in js and ".order-detail-panel.fmm-detail-sheet" in css
    assert "foms-map-detail-open" in js
    assert "body.foms-map-detail-open" in css
    assert "aria-modal" in js
    assert "window.history.pushState" in js
    assert "popstate" in js
    # 가로 스크롤은 표 안에서만 격리
    assert ".fmm-detail-sheet .table-responsive" in css


def test_existing_globals_are_wrapped_not_replaced():
    """기존 전역은 감싸기만 — 재정의/시그니처 변경 금지."""
    js = _read(JS)
    assert "origLoadDetail.apply(this, arguments)" in js
    assert "origCloseDetail.apply(this, arguments)" in js
    assert "window.FomsMapMobileSheet" in js
    # 시트 모듈이 카카오 엔진 내부를 직접 조작하지 않는다
    assert "FomsMapViewKakao" not in js


def test_kakao_popup_has_mobile_branch_and_sheet_hook():
    js = _read(KAKAO_JS)
    assert "function isMobileView()" in js
    assert "foms-kmap-popup__m-body" in js
    assert "foms-kmap-popup__actions--m" in js
    assert "window.FomsMapMobileSheet" in js
    # 훅이 없으면 기존 동작으로 폴백
    assert "if (typeof window.selectOrder === 'function') window.selectOrder(Number(orderId));" in js
    # PC 테이블 팝업(folium 파리티)은 그대로 남아있어야 한다
    assert "foms-kmap-popup__table" in js
    assert "<tr><th>접수일</th>" in js


def test_mobile_popup_width_is_viewport_bound():
    css = _read(CSS)
    assert "width: min(84vw, 300px);" in css


def test_no_inline_style_attributes_added_to_template_panel():
    """스킨은 CSS 파일 소유 — 템플릿 패널 마크업에 style= 를 늘리지 않는다."""
    content = _read(TEMPLATE)
    assert '<div class="map-right-panel">' in content
    assert '<div class="order-list-header">' in content
    # 상세 패널의 초기 숨김(display:none)만 기존대로 유지
    assert content.count('id="order-detail-panel" style="display: none;"') == 1
