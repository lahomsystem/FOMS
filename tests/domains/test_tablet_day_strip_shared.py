"""날짜 버튼 띠 · 사람 색 공용 자산(설계서 tablet-production-ui §13 P13-1).

출고 탭 CSS 두 곳에 있던 규칙을 static/css/components/foms-tablet-day-strip.css 하나로 옮겼다.
출고 · 시공 두 화면이 같은 ?v= 핀으로 싣고, 날짜 띠 JS 도 같은 핀으로 싣는다(싱글턴이라 두 탭을 오가도 한 번만 묶인다).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRIP_CSS = "static/css/components/foms-tablet-day-strip.css"
CORE_MQ = "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
CSS_LINK = re.compile(r"css/components/foms-tablet-day-strip\.css'\) \}\}\?v=(\d{8}[a-z])\"")
JS_ENTRY = re.compile(r"'/static/js/shipment/tablet-ship-datebar\.js\?v=(\d{8}[a-z])'")
JS_TAG = re.compile(r"js/shipment/tablet-ship-datebar\.js'\) \}\}\?v=(\d{8}[a-z])\" defer>")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_strip_css_rules_only_inside_cohort_gate_and_scaled_fonts() -> None:
    css = re.sub(r"/\*.*?\*/", "", _read(STRIP_CSS), flags=re.S).strip()
    head = "@media " + CORE_MQ + " {"
    assert css.startswith(head) and css.endswith("}")
    inner = css[len(head):-1]
    assert "@media" not in inner
    blocks = list(re.finditer(r"([^{}]+)\{[^{}]*\}", inner))
    assert len(blocks) >= 20
    for block in blocks:
        for sel in block.group(1).split(","):
            assert sel.strip().startswith("body.erp-mobile-v2-layout"), sel
    for value in re.findall(r"font-size:\s*([^;]+);", css):
        m = re.fullmatch(r"calc\((\d+)px \* var\(--foms-fs, 1\)\)", value.strip())
        assert m and int(m.group(1)) >= 13, value
    for i in range(1, 11):
        assert f'[data-ship-color="{i}"] {{ --ship-pc: #' in css
    assert "background:" not in re.sub(r"\s+", " ", css).split(".foms-ship-day.is-selected {")[1].split("}")[0]


def test_moved_rules_live_in_one_place_only() -> None:
    cols = _read("static/css/contexts/shipment/shipment-dashboard-columns.css")
    sheet = _read("static/css/contexts/shipment/tablet-day-sheet.css")
    assert ".foms-ship-day {" not in cols and ".foms-ship-days__track {" not in cols
    assert "--ship-pc:" not in sheet and "var(--ship-pc" in sheet  # 칠하는 곳은 출고 CSS 에 남는다


def test_shipment_and_construction_load_same_pins() -> None:
    ship = _read("templates/shipment/partials/dashboard_main.html")
    cons_css = _read("templates/construction/partials/styles.html")
    cons_scripts = _read("templates/construction/partials/scripts.html")
    entry = _read("static/js/shipment/shipment-entry.js")
    ship_pin = CSS_LINK.findall(ship)
    cons_pin = CSS_LINK.findall(cons_css)
    assert len(ship_pin) == 1 and ship_pin == cons_pin
    # 시공 화면은 styles.html 을 dashboard_body 에서 싣는다 → 온전한 페이지 · 셸 조각 둘 다
    body = _read("templates/construction/partials/dashboard_body.html")
    assert "construction/partials/styles.html" in body and "construction/partials/scripts.html" in body
    # 시공 쪽은 dashboard_body.html(온전한 페이지 · 셸 조각 공통)에 defer 로 한 번, 출고 CHAIN 과 같은 핀.
    assert JS_ENTRY.findall(entry) == JS_TAG.findall(body) and len(JS_TAG.findall(body)) == 1
    assert "tablet-ship-datebar" not in cons_scripts  # 조각 scripts 묶음(perf_scan fragment-multi-script)은 늘리지 않는다
    assert "__FOMS_SHIP_DATEBAR_BOUND" in _read("static/js/shipment/tablet-ship-datebar.js")
    # 띠 CSS 는 출고 열 CSS 뒤 · 하루치 표 CSS 앞(옛 자리 순서 그대로)
    assert ship.index("shipment-dashboard-columns.css") < ship.index("foms-tablet-day-strip.css") < ship.index("tablet-day-sheet.css")
