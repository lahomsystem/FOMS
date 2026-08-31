"""실측일 미정 — 템플릿/JS 소스 문자열 계약.

화면이 아니라 소스에서 판정한다(선례: tests/performance/test_page_local_defer_contract.py).
고정하는 회귀축:
- 버튼이 데스크톱 필터 액션줄 안, '동선' 버튼 뒤에 있을 것
- 모달이 `.erp-pro` 래퍼 밖(모바일 max-width:100vw 무력화 함정)일 것
- 상시 배너에 data-foms-no-autodismiss (.alert 5초 자동닫힘 함정)
- 렌더가 textContent 전용(XSS 싱크 금지), jQuery 부재
- SW staticCacheFirst 대비 ?v 핀 3곳 동기 + 범프
- dashboard_scripts.html 의 <script src> 는 정확히 1개(perf 가드 사각)
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

DASHBOARD_MAIN = REPO / "templates" / "measurement" / "partials" / "dashboard_main.html"
DASHBOARD_SCRIPTS = REPO / "templates" / "measurement" / "partials" / "dashboard_scripts.html"
DASHBOARD_PAGE = REPO / "templates" / "measurement" / "dashboard.html"
DASHBOARD_JS = REPO / "static" / "js" / "measurement" / "dashboard.js"
MEASUREMENT_ENTRY_JS = REPO / "static" / "js" / "measurement" / "measurement-entry.js"

BUTTON_ID = 'id="btn-undated-measurement"'
MODAL_ID = 'id="undatedMeasurementModal"'


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------ 1. 버튼 위치

def test_undated_button_exists():
    assert BUTTON_ID in _read(DASHBOARD_MAIN), "실측일 미정 버튼이 없다"


def test_undated_button_is_last_in_filter_actions():
    html = _read(DASHBOARD_MAIN)
    # 기준점은 액션줄의 마지막 지도 진입점(핀 지도 링크)이다. 2026-08-31 "동선 추천"
    # 버튼(`id="btn-route-plan"`) 폐지, 2026-09-01 "동선 지도" 링크 폐지로 기준점이
    # 두 번 밀렸다 — 삭제가 위치 계약을 깨뜨리는 자리라 남긴다.
    assert html.index('open_map=1') < html.index(BUTTON_ID), (
        "실측일 미정 버튼은 지도 링크 뒤(액션줄 오른쪽 끝)에 와야 한다"
    )


def test_undated_button_is_inside_desktop_filter_form():
    html = _read(DASHBOARD_MAIN)
    actions_at = html.index("erp-pro-filter-actions")
    button_at = html.index(BUTTON_ID)
    assert actions_at < button_at, "버튼이 erp-pro-filter-actions 블록 앞에 있다"
    assert "</form>" not in html[actions_at:button_at], (
        "버튼이 데스크톱 필터 폼 밖으로 빠져나갔다"
    )


# ------------------------------------------------------------ 2. 모달 계약

def test_undated_modal_exists():
    assert MODAL_ID in _read(DASHBOARD_MAIN), "실측일 미정 모달이 없다"


def test_undated_modal_dialog_is_extra_large_and_centered():
    html = _read(DASHBOARD_MAIN)
    modal_at = html.index(MODAL_ID)
    dialog_at = html.index("modal-dialog", modal_at)
    line_start = html.rfind("\n", 0, dialog_at) + 1
    line_end = html.find("\n", dialog_at)
    dialog_line = html[line_start: line_end if line_end != -1 else len(html)]
    assert "modal-xl" in dialog_line, dialog_line
    assert "modal-dialog-centered" in dialog_line, dialog_line


def test_undated_modal_is_outside_erp_pro_wrapper():
    """`.erp-pro .modal-dialog { max-width:100vw }` 가 992px 이하에서 크기를 무력화한다."""
    html = _read(DASHBOARD_MAIN)
    assert html.index("end erp-pro") < html.index(MODAL_ID), (
        "모달이 .erp-pro 래퍼 안에 있어 modal-xl 이 무력화된다"
    )


def test_undated_persistent_banners_opt_out_of_autodismiss():
    html = _read(DASHBOARD_MAIN)
    modal_at = html.index(MODAL_ID)
    modal_slice = html[modal_at:]
    for banner_id in ('id="undated-error"', 'id="undated-truncated"'):
        assert banner_id in modal_slice, f"{banner_id} 배너가 없다"
        banner_at = modal_slice.index(banner_id)
        window = modal_slice[max(0, banner_at - 400): banner_at + 400]
        assert "data-foms-no-autodismiss" in window, (
            f"{banner_id} 에 data-foms-no-autodismiss 가 없다 (.alert 5초 자동닫힘 무음 실패)"
        )


# ------------------------------------------------------------ 3. 인라인 스타일 금지

def test_undated_modal_has_no_inline_style():
    html = _read(DASHBOARD_MAIN)
    modal_at = html.index(MODAL_ID)
    next_comment = html.find("<!-- ", modal_at)
    modal_slice = html[modal_at: next_comment if next_comment != -1 else len(html)]
    assert 'style="' not in modal_slice, "모달에 인라인 스타일이 있다 (CSS 파일 사용)"


# ------------------------------------------------------------ 4. JS 계약

def _undated_js_slice(js: str) -> str:
    """dashboard.js 안의 '실측일 미정' 블록만 잘라낸다.

    'undated' 를 언급하는 첫 줄부터 마지막 줄까지 = 이 기능이 만든 코드 전부.
    (고정 바이트 슬라이스는 블록이 길어지면 뒷부분을 놓친다.)
    """
    lines = js.splitlines()
    hits = [i for i, line in enumerate(lines) if "undated" in line.lower()]
    assert hits, "dashboard.js 에 실측일 미정 블록이 없다"
    return "\n".join(lines[hits[0]: hits[-1] + 1])


def test_dashboard_js_calls_undated_api():
    assert "/api/erp/measurement/undated" in _read(DASHBOARD_JS)


def test_dashboard_js_validates_data_success():
    assert "data.success" in _read(DASHBOARD_JS), "fetch 응답 data.success 검증이 없다"


def test_dashboard_js_references_modal_and_new_tab():
    js = _read(DASHBOARD_JS)
    assert "undatedMeasurementModal" in js
    slice_ = _undated_js_slice(js)
    assert "_blank" in slice_, "수정 버튼이 새 탭(target=_blank)으로 열리지 않는다"
    assert "target" in slice_


def test_undated_js_block_uses_textcontent_only():
    js = _read(DASHBOARD_JS)
    slice_ = _undated_js_slice(js)
    assert ".innerHTML" not in slice_, "innerHTML 주입은 저장형 XSS 싱크다"
    assert "textContent" in slice_, "셀 값은 textContent 로 넣어야 한다"


def test_dashboard_js_has_no_jquery():
    js = _read(DASHBOARD_JS)
    assert "jQuery" not in js
    assert "$(" not in js


# ------------------------------------------------------------ 5. ?v 핀 동기 + 범프

def test_measurement_js_version_pins_are_synced_and_bumped():
    entry = _read(MEASUREMENT_ENTRY_JS)
    match = re.search(r"MEAS_JS_V\s*=\s*'([^']+)'", entry)
    assert match, "measurement-entry.js 에서 MEAS_JS_V 를 찾지 못했다"
    token = match.group(1)

    assert token != "20260810b", (
        "dashboard.js 를 고쳤으면 MEAS_JS_V 를 범프해야 한다(SW staticCacheFirst 가 옛 파일을 서빙)"
    )
    assert f"measurement_js_v = '{token}'" in _read(DASHBOARD_SCRIPTS), (
        "dashboard_scripts.html 의 measurement_js_v 가 MEAS_JS_V 와 다르다"
    )
    assert f"?v={token}" in _read(DASHBOARD_PAGE), (
        "dashboard.html 의 ?v 리터럴이 MEAS_JS_V 와 다르다"
    )


# ------------------------------------------------------------ 6. CHAIN 오염 금지

def test_dashboard_scripts_has_exactly_one_script_src():
    """perf 가드 _scan_fragment_multi_script 사각 방지 — entry 1개만 허용."""
    assert _read(DASHBOARD_SCRIPTS).count("<script src") == 1, (
        "dashboard_scripts.html 에 <script src> 를 추가하면 defer 계약·perf 스캔이 red 다"
    )
