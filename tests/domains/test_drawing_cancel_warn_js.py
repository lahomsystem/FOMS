"""S2 — 전달 취소 경고 갈래(§3.4 · Q4 경고만 · Q5-④ · 리뷰 P2)와 시트 JS 누락 안내를 Node 로 실제로 돌린다.

- window.fomsDrawingCancelWarn(drawing-urgent-call-pc.js): 폭에 따라 PC·모바일 문구를 고르고 경고 시트를 연다(확인창 없음).
  문구·시트가 없으면 false — 인라인 cancelTransfer 가 기존 확인창 경로로 간다.
- 인라인 cancelTransfer 본문을 템플릿에서 그대로 떼어 실행한다: 새 JS 가 떴으면 시트, 안 떴으면 경고 문구 확인창.
- 인라인 warnIfSheetJsMissing: 시트 JS 가 안 떴으면 주 버튼을 누를 때 새로고침 안내.
"""

from __future__ import annotations

import pytest

from tests.support.drawing_customer_js_harness import ROOT, run_js

URGENT_JS = "static/js/foms/drawing-urgent-call-pc.js"


def _urls(result: dict) -> list[str]:
    return [c["url"] for c in result["calls"]]


WARN_DOM = r"""
const warn = makeEl({ id: 'dwCancelWarnModal', attrs: { 'data-order-id': '77' } });
const warnText = makeEl({});
warn._sel['[data-cancel-warn-text]'] = warnText;
const cancelBtn = makeEl({ id: 'btn-cancel-transfer', attrs: ATTRS });
window.matchMedia = function (q) { return { matches: NARROW && q === '(max-width: 991.98px)' }; };
"""


def _warn(attrs: dict, *, narrow: bool = False, with_modal: bool = True) -> dict:
    driver = (
        f"const ATTRS = {attrs!r}; const NARROW = {str(narrow).lower()};\n" + WARN_DOM
        + ("" if with_modal else "delete byId['dwCancelWarnModal'];\n")
        + "loadSources();\n"
        + "const handled = window.fomsDrawingCancelWarn(cancelBtn);\n"
        + "out({ handled: handled, text: warnText.textContent });"
    )
    return run_js([URGENT_JS], driver)


PC_TEXT = {"data-customer-sent-text-pc": "보냈어요(PC)", "data-customer-sent-text-mobile": "보냈어요(모바일)"}


@pytest.mark.parametrize("narrow,expect", [(False, "보냈어요(PC)"), (True, "보냈어요(모바일)")])
def test_cancel_warn_picks_text_by_width_and_opens_sheet_without_confirm(narrow, expect):
    r = _warn(PC_TEXT, narrow=narrow)
    assert r["handled"] is True and r["text"] == expect
    assert ["show", "dwCancelWarnModal"] in r["modalOps"]
    assert not [a for a in r["alerts"] if a.startswith("CONFIRM:")] and r["calls"] == []


def test_cancel_warn_without_text_leaves_plain_confirm_path():
    r = _warn({})
    assert r["handled"] is False and r["modalOps"] == []


def test_cancel_warn_without_sheet_falls_back():
    r = _warn(PC_TEXT, with_modal=False)
    assert r["handled"] is False and r["modalOps"] == []


def _inline_fn(signature: str) -> str:
    """작업실 인라인 스크립트의 함수 본문을 그대로 떼어 낸다(문자열 단언이 아니라 실행하려고)."""
    body = (ROOT / "templates/drawing/partials/workbench_detail_body.html").read_text(encoding="utf-8")
    start = body.index(signature)
    depth, i = 0, body.index("{", start)
    while True:
        ch = body[i]
        depth += 1 if ch == "{" else -1 if ch == "}" else 0
        i += 1
        if depth == 0:
            return body[start:i]


def _run_inline(attrs: dict, *, helper: str, confirm: bool = True) -> dict:
    driver = (
        f"const ATTRS = {attrs!r}; const NARROW = false;\n" + WARN_DOM
        + "const orderId = 77; const shown = [];\n"
        + "function showWorkbenchToast(m) { shown.push(m); }\n"
        + f"window.__confirmAnswer = {str(confirm).lower()};\n"
        + "route('/cancel-transfer', function () { return Resp(200, { success: true }); });\n"
        + helper + "\n"
        + _inline_fn("async function cancelTransfer() {") + "\n"
        + "await cancelTransfer(); await flush();\n"
        + "out({ helperCalls: window.__helperCalls || 0 });"
    )
    return run_js([], driver)


def test_inline_cancel_transfer_uses_warn_sheet_when_js_loaded():
    r = _run_inline(PC_TEXT, helper="window.__FOMS_DRAWING_URGENT_PC_BOUND = true;"
                    " window.fomsDrawingCancelWarn = function () { window.__helperCalls = (window.__helperCalls || 0) + 1;"
                    " return true; };")
    assert r["helperCalls"] == 1
    assert r["calls"] == [] and not [a for a in r["alerts"] if a.startswith("CONFIRM:")]


def test_inline_cancel_transfer_falls_back_to_confirm_with_warning_when_js_missing():
    """새 JS 가 핀·캐시 문제로 안 떴으면 경고 문구를 확인창으로 보이고, 예를 누르면 전달 취소가 된다(막히지 않는다)."""
    r = _run_inline(PC_TEXT, helper="")
    assert "CONFIRM:보냈어요(PC)" in r["alerts"]
    assert _urls(r) == ["/api/orders/77/cancel-transfer"] and r["href"] == "/erp/drawing-workbench/77?tab=timeline"


def test_inline_cancel_transfer_without_warning_keeps_old_confirm():
    r = _run_inline({}, helper="window.fomsDrawingCancelWarn = function () { return false; };", confirm=False)
    assert [a for a in r["alerts"] if a.startswith("CONFIRM:")] == [
        "CONFIRM:전달 취소 시 최신 전달본 파일과 이력이 함께 정리됩니다. 진행할까요?"]
    assert r["calls"] == []


@pytest.mark.parametrize("attr,flag,loaded", [
    ("data-ok-submit", "__FOMS_DRAWING_CUSTOMER_OK_BOUND", False),
    ("data-send-submit", "__FOMS_DRAWING_CUSTOMER_SEND_BOUND", False),
    ("data-edit-submit", "__FOMS_DRAWING_REVISION_EDIT_BOUND", False),
    ("data-ok-submit", "__FOMS_DRAWING_CUSTOMER_OK_BOUND", True),
])
def test_inline_warns_when_sheet_js_missing(attr, flag, loaded):
    """시트 JS 가 안 떴으면 주 버튼을 눌렀을 때 새로고침 안내가 뜬다. 떴으면(대조군) 아무 말도 안 한다."""
    driver = (
        "const shown = []; function showWorkbenchToast(m) { shown.push(m); }\n"
        + (f"window.{flag} = true;\n" if loaded else "")
        + _inline_fn("function warnIfSheetJsMissing(e) {") + "\n"
        + f"const b = makeEl({{ attrs: {{ {attr!r}: '' }} }});\n"
        + "b._closest['[data-ok-submit], [data-send-submit], [data-edit-submit]'] = b;\n"
        + "warnIfSheetJsMissing({ target: b });\n"
        + "out({ shown: shown });"
    )
    r = run_js([], driver)
    if loaded:
        assert r["shown"] == []
    else:
        assert len(r["shown"]) == 1 and "새로고침" in r["shown"][0]
