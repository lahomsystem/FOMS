"""WD 계산기 태블릿 v2 스킨 구조 계약.

계산 엔진·DOM id 무변경 표면(신규 DOM + 은닉 엔진 위젯 양방향 미러)이므로 페이지 렌더
대신 소스 자산을 직접 검증한다:
- calculator.html 이 tablet-skin.js 를 defer + ?v= 로 배선한다.
- tablet-skin.js 가 singleton 가드 + coarse-landscape 게이트 + v2 섹션 DOM 을 갖는다.
- D/H 센티넬(구판)이 전면 삭제됐다.
- MINE 제품명·30cm/1m 방식·엔진 버튼 미러 셀렉터가 존재한다.
- tablet-skin.css 가 게이트 미디어쿼리 + 스코프 토큰을 갖는다.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/wdcalculator/tablet-skin.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/wdcalculator/tablet-skin.css").read_text(encoding="utf-8")
CAL = (ROOT / "templates/wdcalculator/calculator.html").read_text(encoding="utf-8")


def test_singleton_and_gate() -> None:
    assert "__WDC_TABLET_SKIN_BOUND" in JS
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in JS


def test_v2_dom_sections_present() -> None:
    for cls in [
        "wdc2-topbar",
        "wdc2-sheet",
        "wdc2-abar",
        "wdc2-panel",
        "wdc2-saved-overlay",
        "wdc-tablet-v2",
    ]:
        assert cls in JS, cls


def test_dh_sentinel_removed() -> None:
    assert "[규격]" not in JS
    assert "parseDH" not in JS and "encodeDH" not in JS


def test_mine_mirror_contract() -> None:
    assert "base-manual-name" in JS
    assert "base-manual-pricing-type" in JS


def test_engine_button_mirrors() -> None:
    for sel in [
        "addBaseComponentBtn",
        "addOptionBtn",
        "btnAddNote",
        "addEstimateBtn",
        "saveEstimateBtn",
        "wdUnitPriceMetaToggle",
    ]:
        assert sel in JS, sel


def test_calculate_btn_not_referenced() -> None:
    assert "calculateBtn" not in JS


def test_css_gate_and_tokens() -> None:
    assert "pointer: coarse" in CSS and "landscape" in CSS
    assert "--wdc2-accent" in CSS and "wdc-tablet-v2" in CSS


def test_calculator_template_wiring_defer() -> None:
    # calculator.html 은 url_for()로 배선하므로 `tablet-skin.js') }}?v=` 형태다.
    # 계약 본질(캐시버스트 ?v + 렌더차단 방지 defer)을 실제 배선 형태로 검증한다.
    line = next(ln for ln in CAL.splitlines() if "tablet-skin.js" in ln)
    assert "?v=" in line and "defer" in line
