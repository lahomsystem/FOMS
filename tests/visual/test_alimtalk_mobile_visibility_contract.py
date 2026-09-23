"""ERP 주문 화면 알림톡 발송 흔적 — 모바일 가시성 + 단독 공유 흔적 계약 (2026-09-23).

사용자 제보(2026-09-23): 모바일 주문 편집 화면에서 알림톡을 보냈는지 확인할 길이 없었다.
원인은 다섯 갈래였고 각각을 여기서 고정한다.

A. 미발송 칩이 있으면 흔적 줄을 **통째로** 감춰서 같은 줄의 공유 링크 칩까지 사라졌다.
B. 칩을 감춘 뒤 이력 패널로 가는 길이 없었다(CSS 주석이 말한 '시트의 발송 이력'이 없었다).
C. 발송 진행·실패·완료 문구를 PC 전용 상태 줄에만 써서 모바일에서는 조용히 사라졌다.
D. 저장 직후 화면 사본이 폼 수집본으로 바뀌며 발송 이력 키가 빠져 칩이 '아직 안 보냄'으로 되돌아갔다.
E. 도면 단독·계약서 단독 링크는 흔적을 아예 남기지 않았다(사용자 결정 2026-09-23 으로 뒤집음).

행동은 Node 로 실제 스크립트를 돌려 확인한다(문자열 계약만으로는 폴백 분기를 못 본다).
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

_needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _run_node(script: str) -> dict:
    """스크립트를 Node 로 돌려 마지막 stdout JSON 을 돌려준다."""
    node = shutil.which("node")
    assert node, "node 가 PATH 에 없다"
    with tempfile.TemporaryDirectory(prefix="alimtalk-vis-") as tmp:
        path = pathlib.Path(tmp) / "check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


# 최소 DOM 스텁 — createElement/appendChild/textContent/속성만 흉내 낸다.
_DOM_STUB = r"""
function makeEl(tag) {
    const el = {
        tagName: String(tag).toUpperCase(), children: [], attrs: {}, className: '',
        _text: '', title: '', type: '', dataset: {},
        appendChild(c) { this.children.push(c); return c; },
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
        get childElementCount() { return this.children.length; },
        get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
        set textContent(v) { this._text = String(v); this.children = []; },
        getClientRects() { return this._shown ? [1] : []; },
        classList: { toggle() {}, add() {}, remove() {} },
    };
    return el;
}
"""


# --- A. 모바일 흔적 줄: 미발송 칩만 감춘다 --------------------------------------------


def test_mobile_css_hides_only_none_chip_not_whole_row() -> None:
    """미발송 칩이 있다고 줄째 감추면 같은 줄의 공유 칩이 함께 사라진다."""
    css = _read("static/css/orders/erp-alimtalk-trace.css")
    # 옛 규칙(줄째 감춤)은 없어야 한다.
    assert ".erp-alimtalk-trace-slot--mobile:has(> .erp-alimtalk-trace--none) {" not in css
    # 미발송 칩 자신만 감춘다.
    assert re.search(
        r"\.erp-alimtalk-trace-slot--mobile > \.erp-alimtalk-trace--none \{\s*display: none;", css)
    # 줄은 '미발송 말고 다른 칩이 하나도 없을 때'만 감춘다(공유 칩이 있으면 남는다).
    assert re.search(
        r"\.erp-alimtalk-trace-slot--mobile:not\(:has\(> :not\(\.erp-alimtalk-trace--none\)\)\) "
        r"\{\s*display: none;", css)


# --- B. 모바일 시트에서 발송 이력 열기 --------------------------------------------------


def test_mobile_picker_sheet_offers_history_entry() -> None:
    """칩을 감춘 모바일에도 이력 패널로 가는 길이 시트에 있다(칩과 같은 위임 훅)."""
    sheet = _read("templates/orders/partials/erp_alimtalk_picker_modal.html")
    options = sheet[sheet.index("erp-channel-push-picker-options"):sheet.index("modal-footer")]
    assert "data-erp-alimtalk-trace-open" in options
    assert "발송 이력" in options
    # 시트 replay 흐름을 타려면 선택지와 같은 foms-btn 이어야 한다(겹친 모달 방지).
    button = options[options.index('id="erp-alimtalk-trace-open-btn-sheet"') - 200:]
    assert "foms-btn" in button[:400]
    assert "style=" not in sheet
    # 여는 쪽 위임 핸들러와 패널이 모바일 표면에 함께 있다.
    trace = _read("static/js/orders/erp-alimtalk-trace.js")
    assert "target.closest('[data-erp-alimtalk-trace-open]')" in trace
    mobile = _read("templates/orders/partials/erp_order_tab_mobile.html")
    assert "orders/partials/erp_alimtalk_picker_modal.html" in mobile
    assert "orders/partials/erp_alimtalk_trace_modal.html" in mobile


# --- C. 상태 줄 없는 표면의 결과 알림 ---------------------------------------------------


_SEND_HARNESS = _DOM_STUB + r"""
const alerts = [];
const toasts = [];
const scenario = __SCENARIO__;
const statusNodes = scenario.statusShown === null ? [] : [Object.assign(makeEl('span'), { _shown: scenario.statusShown })];
const notice = Object.assign(makeEl('div'), { _shown: scenario.noticeShown });
global.window = global;
global.CustomEvent = function (n, o) { this.type = n; this.detail = o && o.detail; };
global.document = {
    addEventListener() {},
    dispatchEvent() {},
    querySelectorAll(sel) { return sel === '.erp-alimtalk-status' ? statusNodes : []; },
    getElementById(id) {
        if (id === 'erp-alimtalk-notice') return notice;
        if (id === 'foms-alpine-toast-root') return scenario.toastHost ? makeEl('div') : null;
        return null;
    },
};
window.alert = (m) => alerts.push(m);
window.fomsShowToast = (m) => toasts.push(m);
window.Alpine = scenario.toastHost ? { store: () => ({}) } : undefined;
window.fomsErpAutosave = { isDirty: () => true };
window.ORDER_ID = 7;
__SOURCE__
(async () => {
    const ok = await window.fomsErpEnsureSavedForSend();
    process.stdout.write(JSON.stringify({ ok, alerts, toasts,
        status: statusNodes.map(n => n.textContent) }) + '\n');
})();
"""


def _run_send(scenario: dict) -> dict:
    source = _read("static/js/orders/erp-alimtalk-send.js")
    script = _SEND_HARNESS.replace("__SCENARIO__", json.dumps(scenario)).replace(
        "__SOURCE__", source)
    return _run_node(script)


@_needs_node
def test_error_without_status_line_is_alerted_on_mobile() -> None:
    """모바일(상태 줄 없음): 발송 전 저장 실패 같은 오류가 조용히 사라지지 않는다."""
    out = _run_send({"statusShown": None, "noticeShown": False, "toastHost": False})
    assert out["ok"] is False
    assert out["alerts"] == ["저장되지 않은 변경이 있습니다. 저장 후 발송해주세요."]


@_needs_node
def test_error_with_visible_status_line_is_not_alerted() -> None:
    """대조군(PC): 상태 줄이 보이면 거기에만 쓰고 창을 띄우지 않는다."""
    out = _run_send({"statusShown": True, "noticeShown": False, "toastHost": False})
    assert out["ok"] is False and out["alerts"] == []
    assert out["status"] == ["저장되지 않은 변경이 있습니다. 저장 후 발송해주세요."]


@_needs_node
def test_error_with_visible_modal_notice_is_not_alerted() -> None:
    """발송 모달 안내 줄이 이미 실패를 보여 주면 alert 를 겹쳐 띄우지 않는다."""
    out = _run_send({"statusShown": None, "noticeShown": True, "toastHost": False})
    assert out["alerts"] == []


def test_send_js_reports_done_and_failure_with_levels() -> None:
    """완료는 'done'(토스트, 호스트 없으면 alert), 실패는 'error' 등급으로 넘긴다."""
    js = _read("static/js/orders/erp-alimtalk-send.js")
    assert "erpAlimtalkSetStatus('알림톡 발송 완료', 'done');" in js
    assert js.count("'알림톡 발송 실패 · ' + erpAlimtalkReasonLabel(") == 2
    assert js.count("erpAlimtalkReasonLabel(code), 'error');") >= 2
    # 토스트 판정은 AS 접수 선례와 같은 함수 — 호스트가 있어도 숨은 영역(PC)이면 alert 로 간다.
    assert "window.erpToastVisibleHere()" in js
    # 진행 문구는 창을 띄우지 않는다(등급 없이 호출).
    assert "erpAlimtalkSetStatus('알림톡 발송 중…');" in js


# --- D. 저장 직후 화면 사본이 발송 이력을 잃지 않는다 ------------------------------------


def _extract_block(source: str, start: str, end: str) -> str:
    i = source.index(start)
    return source[i:source.index(end, i)]


@_needs_node
def test_save_keeps_alimtalk_trace_keys_in_client_copy() -> None:
    """폼 수집본으로 화면 사본을 바꿔도 alimtalk_measurement·alimtalk_share 는 남는다."""
    shared = _read("static/js/orders/erp-order-shared.js")
    block = _extract_block(shared, "var ERP_LOCAL_ONLY_TRACE_KEYS", "window.erpCarryLocalOnlyKeys")
    script = "global.window = global;\n" + block + r"""
const prev = { alimtalk_measurement: { sent_at: 'x' }, alimtalk_share: { kind: 'drawing' },
               channeltalk_push: { a: 1 } };
const next = { items: [] };
erpCarryLocalOnlyKeys(next, prev);
const own = { alimtalk_share: { kind: 'bundle' } };
erpCarryLocalOnlyKeys(own, prev);
erpCarryLocalOnlyKeys(null, prev);
process.stdout.write(JSON.stringify({ next, own }) + '\n');
"""
    out = _run_node(script)
    assert out["next"]["alimtalk_measurement"] == {"sent_at": "x"}
    assert out["next"]["alimtalk_share"] == {"kind": "drawing"}
    assert "channeltalk_push" not in out["next"], "옮기는 키는 발송 이력 둘뿐이다"
    assert out["own"]["alimtalk_share"] == {"kind": "bundle"}, "수집본에 이미 있으면 덮지 않는다"


def test_save_carries_trace_keys_but_never_sends_them() -> None:
    """PUT 에는 싣지 않는다 — 서버는 폼 값을 받으므로 낡은 사본이 새 이력(멱등 키)을 덮는다."""
    shared = _read("static/js/orders/erp-order-shared.js")
    preserved = _extract_block(shared, "const preservedTopLevelKeys = [", "];")
    assert "alimtalk_measurement" not in preserved
    assert "alimtalk_share" not in preserved
    assert ("erpCarryLocalOnlyKeys(structured_data, window.__erpLastStructuredData);\n"
            "            window.__erpLastStructuredData = structured_data;") in shared
    # 서버는 폼이 빠뜨린 두 키를 옛 값으로 되살린다.
    server = _read("foms/api/erp_orders_structured.py")
    ops = _extract_block(server, "_OPERATIONAL_TOP_LEVEL_KEYS = (", "\n)\n")
    assert "'alimtalk_measurement'," in ops and "'alimtalk_share'," in ops


# --- E. 도면 단독·계약서 단독 흔적 + 이력 패널 --------------------------------------------


_TRACE_HARNESS = _DOM_STUB + r"""
const scenario = __SCENARIO__;
const listeners = {};
const log = makeEl('ul');
const count = makeEl('span');
const slot = makeEl('div');
slot.setAttribute('data-erp-alimtalk-trace', 'compact');
let fetched = '';
global.window = global;
global.document = {
    readyState: 'complete',
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    createElement: makeEl,
    querySelector() { return null; },
    querySelectorAll(sel) { return sel === '[data-erp-alimtalk-trace]' ? [slot] : []; },
    getElementById(id) {
        if (id === 'erpAlimtalkTraceModal') return makeEl('div');
        if (id === 'erp-alimtalk-trace-log') return log;
        if (id === 'erp-alimtalk-trace-count') return count;
        return null;
    },
};
window.ORDER_ID = 11;
window.bootstrap = { Modal: { getOrCreateInstance: () => ({ show() {} }) } };
window.fetch = (url) => { fetched = url; return Promise.resolve({ json: () => Promise.resolve(
    { success: true, events: scenario.events }) }); };
window.__erpLastStructuredData = { alimtalk_share: scenario.share };
__SOURCE__
listeners.click[0]({ target: { closest: (s) => s === '[data-erp-alimtalk-trace-open]' ? {} : null },
                     preventDefault() {} });
setTimeout(() => {
    const items = log.children.map(li => ({
        text: li.textContent,
        bad: !!li.children[0] && li.children[0].className.indexOf('--bad') !== -1,
    }));
    const chips = slot.children.map(c => ({ tag: c.tagName, text: c.textContent,
        open: c.getAttribute('data-erp-alimtalk-trace-open') }));
    process.stdout.write(JSON.stringify({ fetched, items, chips }) + '\n');
}, 20);
"""


def _run_trace(scenario: dict) -> dict:
    source = _read("static/js/orders/erp-alimtalk-trace.js")
    script = _TRACE_HARNESS.replace("__SCENARIO__", json.dumps(scenario)).replace(
        "__SOURCE__", source)
    return _run_node(script)


@_needs_node
def test_history_panel_lists_share_sends_with_korean_labels() -> None:
    """이력 패널이 공유 링크 발송(알림톡·문자)까지 받아 와 종류를 한글로 적는다."""
    events = [
        {"event_type": "SHARE_ALIMTALK", "payload": {"kind": "drawing", "status": "sent"},
         "created_at": "2026-09-23T01:00:00", "created_by_name": "홍길동"},
        {"event_type": "SHARE_SMS", "payload": {"kind": "estimate", "status": "failed",
                                                "error": "network"},
         "created_at": "2026-09-23T00:30:00", "created_by_name": "홍길동"},
        {"event_type": "SHARE_ALIMTALK", "payload": {"kind": "bundle", "status": "in_flight"},
         "created_at": "2026-09-23T00:10:00", "created_by_name": "홍길동"},
        {"event_type": "ALIMTALK_SENT", "payload": {},
         "created_at": "2026-09-22T00:00:00", "created_by_name": None},
    ]
    out = _run_trace({"events": events, "share": None})
    assert "event_type=ALIMTALK_SENT,ALIMTALK_FAILED,SHARE_ALIMTALK,SHARE_SMS" in out["fetched"]
    items = out["items"]
    assert "도면 링크 · 알림톡" in items[0]["text"] and items[0]["bad"] is False
    assert "계약서 링크 · 문자" in items[1]["text"] and items[1]["bad"] is True
    # 결과를 모르는 선점 행은 성공으로 그리지 않는다.
    assert "도면·계약서 링크 · 알림톡" in items[2]["text"] and items[2]["bad"] is True
    assert "발송 진행 중 기록" in items[2]["text"]
    # 대조군: 예약 안내 이벤트는 종전 그대로.
    assert "실측 예약 안내" in items[3]["text"] and items[3]["bad"] is False


@pytest.mark.parametrize("kind,label", [("drawing", "도면 링크"), ("estimate", "계약서 링크"),
                                        ("bundle", "도면·계약서 링크")])
@_needs_node
def test_share_chip_labels_single_kinds_and_opens_history(kind: str, label: str) -> None:
    """단독 공유도 칩이 생기고 '무엇의 링크'인지 적힌다. 누르면 이력 패널이 열린다."""
    share = {"sent_at": "2026-09-23T01:00:00", "kind": kind, "channel": "alimtalk",
             "share_id": 3, "error": None, "sent_by": 1, "sent_by_name": "홍길동"}
    out = _run_trace({"events": [], "share": share})
    chips = out["chips"]
    assert len(chips) == 2, "예약 안내 칩 + 공유 칩"
    assert chips[1]["text"].startswith("✓" + label + " 알림톡 보냄")
    assert chips[1]["tag"] == "BUTTON" and chips[1]["open"] == "1"


def test_share_tracked_kinds_decision_recorded() -> None:
    """결정 변경(2026-09-23)이 서버 상수 옆에 남아 있다."""
    src = _read("foms/services/kakao_alimtalk.py")
    assert 'SHARE_TRACKED_KINDS = ("drawing", "estimate", "bundle")' in src
    assert "2026-09-23" in src[src.index("SHARE_TRACKED_KINDS = (") - 600:
                              src.index("SHARE_TRACKED_KINDS = (")]


def test_share_tracked_kinds_cover_every_share_kind() -> None:
    """추적 종류 = 공유 종류 전부. 새 종류가 생기면 흔적 여부를 명시적으로 정하게 한다."""
    from foms.services import kakao_alimtalk as ka
    from foms.services import order_share as osvc

    assert set(ka.SHARE_TRACKED_KINDS) == set(osvc.SHARE_KINDS)
