"""+ 버튼(.foms-shell-fab)이 아래에서 올라오는 창·팝업을 가리지 않는다(2026-09-24 사용자 제보: 실측 필터 날짜 칸을 가림).

+ 버튼 z-index(1050)가 Bootstrap offcanvas(1045)보다 위라, 창이 열린 동안에는 숨긴다.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_overlay_fab_script_toggles_html_class_on_bootstrap_events():
    js = _read("static/js/foms/foms-overlay-fab.js")
    for needle in ("show.bs.offcanvas", "show.bs.modal", "hidden.bs.offcanvas", "hidden.bs.modal",
                   "foms-overlay-open", ".offcanvas.show", "foms:erp-shell-fragment-swapped"):
        assert needle in js, needle
    assert "jQuery" not in js and "$(" not in js
    assert len(js.splitlines()) < 300


def test_shell_css_hides_fab_while_overlay_open_and_pins_bumped():
    css = _read("static/css/foundation/foms-shell.css")
    assert "html.foms-overlay-open body.erp-mobile-v2-layout .foms-shell-fab" in css
    assert "foms-shell.css?v=20260924a" in _read("static/css/foundation/foms-mobile-surfaces.css")
    assert "foms-mobile-surfaces.css') }}?v=20260924a" in _read("templates/partials/shared/layout_head.html")
    assert "js/foms/foms-overlay-fab.js') }}?v=" in _read("templates/partials/shared/layout_scripts.html")
