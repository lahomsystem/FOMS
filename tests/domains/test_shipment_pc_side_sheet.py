"""PC 출고 탭 세부 창(서랍) 정적 계약 — 설계서 2026-11-23-pc-shipment-card-table §4.2.

static/js/shipment/pc-ship-sheet.js · static/css/contexts/shipment/pc-ship-sheet.css 를 글로 읽어 단언한다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/shipment/pc-ship-sheet.js"
CSS = ROOT / "static/css/contexts/shipment/pc-ship-sheet.css"
PC_QUERY = "(min-width: 992px) and (pointer: fine)"


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _css_no_comments() -> str:
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def test_pc_gate_and_singleton():
    src = _js()
    assert f"'{PC_QUERY}'" in src
    assert "window.matchMedia" in src
    assert "if (window.__FOMS_PC_SHIP_SHEET_BOUND) return;" in src
    assert "window.__FOMS_PC_SHIP_SHEET_BOUND = true;" in src


def test_never_sends_site_extra():
    src = _js()
    # 현장 메모는 PC 표가 여러 줄 · 색을 가진다 — 한 줄 덮어쓰기 금지.
    assert not re.search(r"site_extra\s*[:=]", src)
    assert not re.search(r"\[\s*['\"]site_extra['\"]\s*\]", src)
    assert "construction_time:" in src
    assert "/api/erp/shipment/update/" in src
    assert "data.success" in src


def test_row_click_skip_selectors_and_selection():
    src = _js()
    for sel in (
        "a, button, input, select, textarea, label",
        ".shipment-edit-list",
        ".shipment-site-extra-list",
        "[data-ship-worker-cell]",
        ".erp-ship-change",
        ".col-resize-handle",
    ):
        assert sel in src, sel
    assert "getSelection" in src


def test_no_jquery_no_alert_under_size_limit():
    src = _js()
    assert "jQuery" not in src and "$(" not in src
    assert "alert(" not in src
    assert len(src.splitlines()) < 300


def test_css_rules_all_inside_pc_gate():
    css = _css_no_comments().strip()
    head = f"@media {PC_QUERY} {{"
    assert css.startswith(head), "규칙은 PC 문지기 하나 안에만 둔다"
    assert css.count("@media") == 1
    assert css.endswith("}")
    # 바깥 블록 닫는 괄호가 맨 끝 한 번 — 문지기 밖 규칙 없음.
    depth = 0
    for i, ch in enumerate(css):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                assert i == len(css) - 1
    assert "style=" not in css


def test_css_font_sizes_scale_and_min_13px():
    css = _css_no_comments()
    for m in re.finditer(r"font-size:\s*([^;]+);", css):
        val = m.group(1).strip()
        mm = re.fullmatch(r"calc\((\d+)px \* var\(--foms-fs, 1\)\)", val)
        assert mm, val
        assert int(mm.group(1)) >= 13, val
