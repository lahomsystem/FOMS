"""WDCalculator 태블릿 가로 표피(저장된 견적 접힘/오버레이) 정적 자산 계약.

계산 엔진·DOM id 무변경 표피이므로 페이지 렌더 대신 소스 자산을 직접 검증한다:
- calculator.html 이 tablet-skin.js 를 defer 로 배선한다.
- tablet-skin.js 가 singleton 가드 + coarse-landscape 게이트 + 접힘/펼침 클래스를 갖는다.
- tablet-skin.css 가 접힘(48px 레일)·오버레이·백드롭 규칙을 갖는다.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _ROOT / "templates" / "wdcalculator" / "calculator.html"
_JS = _ROOT / "static" / "js" / "wdcalculator" / "tablet-skin.js"
_CSS = _ROOT / "static" / "css" / "wdcalculator" / "tablet-skin.css"


def test_calculator_template_wires_tablet_skin_js() -> None:
    html = _TEMPLATE.read_text(encoding="utf-8")
    assert "js/wdcalculator/tablet-skin.js" in html
    # 렌더 차단 방지 — defer 필수(성능 가드 G1)
    line = next(ln for ln in html.splitlines() if "tablet-skin.js" in ln)
    assert "defer" in line


def test_tablet_skin_js_has_singleton_and_gate() -> None:
    js = _JS.read_text(encoding="utf-8")
    # G4 중복 바인딩 방지 singleton 가드
    assert "__WDC_TABLET_SKIN_BOUND" in js
    # coarse landscape ≥992 배타 게이트
    assert "min-width: 992px" in js
    assert "orientation: landscape" in js
    assert "pointer: coarse" in js
    # 임베디드 제외(erp-wdc-split 자체 오버레이 소유)
    assert "wdcalculator-container--embedded" in js
    # 접힘/펼침 상태 클래스 + 상태 기억
    assert "wdc-tablet-skin" in js
    assert "wdc-saved-open" in js
    assert "localStorage" in js


def test_tablet_skin_css_has_collapse_overlay_rules() -> None:
    css = _CSS.read_text(encoding="utf-8")
    # 게이트 미디어쿼리
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in css
    # 접힘 레일(48px) + 카드 숨김
    assert "wdc-tablet-skin" in css
    assert ".wdc-saved-rail" in css
    # 오버레이 펼침 + 백드롭
    assert "wdc-saved-open" in css
    assert ".wdc-saved-backdrop" in css
