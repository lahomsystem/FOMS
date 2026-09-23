"""발송 기록 칩 계약 (2026-09-23, 목업 제안 A).

알림톡(예약 안내·공유 링크)과 채널톡 PUSH 흔적을 한 가지 칩 문법으로 한 자리에 그린다.
예전엔 두 모듈이 따로 그려 이름("보냄" vs "실측 PUSH 보냄")·정렬(반반 칸)이 제각각이었다.

* PC(`wide`): 왼쪽부터 전부 나열, 예약 안내 미발송은 점선 칩.
* 모바일(`fold`): 요약 한 줄(칩과 같은 높이) → 누르면 두 칸 격자.
* 칩 시각은 짧게(오늘 14:05 · 어제 18:30 · 그 전 9/21), 다시 보냄은 ↻, 못 보낸 것 먼저.
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
JS = "static/js/orders/erp-send-trace.js"
CSS = "static/css/orders/erp-send-trace.css"
PIN = "?v=20260923a"

_needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --- 템플릿·자산 ---------------------------------------------------------------------


def test_pc_tab_has_one_wide_send_trace_slot() -> None:
    html = _read("templates/orders/partials/erp_order_tab.html")
    assert html.count('data-erp-send-trace="wide"') == 1
    # 예전 두 자리(알림톡·PUSH 따로)는 주문 화면에서 사라졌다.
    assert "data-erp-alimtalk-trace" not in html
    assert "data-erp-channel-push-trace" not in html


def test_mobile_action_bar_has_one_fold_send_trace_slot() -> None:
    html = _read("templates/orders/partials/erp_order_tab_mobile.html")
    footer = html[html.index("erp-mobile-sticky-action-bar"):]
    bar = footer[: footer.index("</footer>")]
    # :empty 로 접히려면 자리 안에 공백조차 없어야 한다.
    assert '<div class="erp-send-trace erp-send-trace--fold" data-erp-send-trace="fold"></div>' in bar
    assert bar.index('data-erp-send-trace="fold"') < bar.index('id="erp-save-btn"')
    assert "data-erp-alimtalk-trace" not in html
    assert "data-erp-channel-push-trace" not in html


def test_assets_loaded_once_and_old_push_trace_removed() -> None:
    order_js = _read("templates/orders/partials/erp_order_js.html")
    for asset in ("css/orders/erp-send-trace.css", "js/orders/erp-send-trace.js"):
        lines = [row for row in order_js.splitlines() if asset in row]
        assert len(lines) == 1, asset
        assert PIN in lines[0], asset
    assert "erp-channel-push-trace" not in order_js
    assert not (ROOT / "static/js/orders/erp-channel-push-trace.js").exists()
    assert not (ROOT / "static/css/orders/erp-channel-push-trace.css").exists()


def _login_admin(client, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Send Trace Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_edit_page_renders_send_trace_on_both_surfaces(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """실제 렌더: PC·모바일 두 표면에 자리 하나씩, 자산과 이력 창이 함께 실린다."""
    user = _login_admin(client, "send_trace_admin")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = Order(
        received_date=datetime.date.today().isoformat(),
        customer_name="발송 기록 고객",
        phone="010-0000-3334",
        address="서울",
        product="붙박이장",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(f"/edit/{order.id}?open=erp-order")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    legacy = html[html.index('id="erp-order-form-legacy"'):html.index('id="erp-order-form-mobile"')]
    mobile = html[html.index('id="erp-order-form-mobile"'):]
    assert 'data-erp-send-trace="wide"' in legacy
    assert 'data-erp-send-trace="fold"' in mobile
    assert "js/orders/erp-send-trace.js" + PIN in html
    assert "css/orders/erp-send-trace.css" + PIN in html
    assert 'id="erpAlimtalkTraceModal"' in html


# --- 모델(실제 스크립트를 Node 로 돌린다) ----------------------------------------------

_HARNESS = r"""
global.window = global;
global.CustomEvent = function (n) { this.type = n; };
global.document = {
    readyState: 'complete',
    addEventListener() {},
    querySelectorAll() { return []; },
    getElementById() { return null; },
};
__SOURCE__
const out = {};
const cases = __CASES__;
for (const name of Object.keys(cases)) {
    const c = cases[name];
    out[name] = window.erpSendTraceModel(c.sd, Date.parse(c.now));
}
process.stdout.write(JSON.stringify(out));
"""

# 기준 시각: 2026-09-23 15:00 KST = 06:00 UTC
NOW = "2026-09-23T06:00:00Z"


def _run(cases: dict) -> dict:
    script = _HARNESS.replace("__SOURCE__", _read(JS)).replace("__CASES__", json.dumps(cases, ensure_ascii=False))
    proc = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True,
                          encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@_needs_node
def test_short_time_today_yesterday_older() -> None:
    """칩 시각: 오늘 = 시:분, 어제 = '어제 시:분', 그 전 = 월/일 (KST 기준, naive 값은 UTC)."""
    out = _run({
        "today": {"now": NOW, "sd": {"channeltalk_push_measure_room": {"pushed": True, "sent_at": "2026-09-23T05:05:00+00:00"}}},
        "yesterday": {"now": NOW, "sd": {"channeltalk_push": {"pushed": True, "sent_at": "2026-09-22T09:30:00"}}},
        "older": {"now": NOW, "sd": {"channeltalk_push_as": {"pushed": True, "sent_at": "2026-09-20T06:45:00Z"}}},
        "kst_midnight": {"now": NOW, "sd": {"channeltalk_push": {"pushed": True, "sent_at": "2026-09-22T15:30:00Z"}}},
    })
    assert out["today"]["chips"][0]["meta"] == "14:05"
    assert out["today"]["chips"][0]["label"] == "실측 PUSH"
    assert out["yesterday"]["chips"][0]["meta"] == "어제 18:30"
    assert out["older"]["chips"][0]["meta"] == "9/20"
    # UTC 로는 22일이지만 KST 로는 23일 00:30 — 오늘이다.
    assert out["kst_midnight"]["chips"][0]["meta"] == "00:30"


@_needs_node
def test_every_chip_names_what_was_sent() -> None:
    """'보냄'만 있는 칩은 없다 — 예약 안내·링크 종류·PUSH 종류가 이름이다."""
    out = _run({"all": {"now": NOW, "sd": {
        "alimtalk_measurement": {"sent_at": "2026-09-23T00:10:00"},
        "alimtalk_share": {"kind": "bundle", "sent_at": "2026-09-23T04:40:00", "channel": "alimtalk"},
        "channeltalk_push_drawing": {"pushed": True, "sent_at": "2026-09-23T02:02:00", "is_modified": True},
    }}})
    chips = out["all"]["chips"]
    labels = [c["label"] for c in chips]
    assert labels == ["도면+계약 링크", "발주 PUSH", "예약 안내"]  # 최근 순
    assert [c["kind"] for c in chips] == ["alim", "push", "alim"]
    assert chips[1]["resent"] is True
    assert out["all"]["measurementSent"] is True
    assert all(c["label"] != "보냄" for c in chips)


@_needs_node
def test_failures_first_then_newest_and_text_channel() -> None:
    out = _run({"mix": {"now": NOW, "sd": {
        "alimtalk_measurement": {"sent_at": "2026-09-23T05:59:00", "channel": "LMS"},
        "alimtalk_share": {"kind": "drawing", "error": "invalid_phone", "sent_at": "2026-09-21T01:00:00"},
        "channeltalk_push": {"pushed": True, "sent_at": "2026-09-23T05:00:00"},
    }}})
    chips = out["mix"]["chips"]
    assert chips[0]["kind"] == "fail" and chips[0]["label"] == "도면 링크 실패"
    assert chips[0]["meta"]  # 사유가 시각 자리에 온다
    assert chips[1]["kind"] == "sms" and chips[1]["label"] == "예약 안내"
    assert chips[2]["label"] == "영발 PUSH"


@_needs_node
def test_nothing_sent_means_no_chips() -> None:
    out = _run({"none": {"now": NOW, "sd": {"workflow": {"stage": "RECEIVED"}}}, "null": {"now": NOW, "sd": None}})
    assert out["none"] == {"chips": [], "measurementSent": False}
    assert out["null"]["chips"] == []


# --- 렌더 규칙(소스 계약) -------------------------------------------------------------


def test_render_rules_in_source() -> None:
    js = _read(JS)
    # 서버 왕복 없이 화면 사본만 읽는다.
    assert "fetch(" not in js
    assert "window.__erpLastStructuredData" in js
    # PC 만 예약 안내 미발송 점선 칩, 모바일은 기록이 없으면 비운다.
    assert "if (!model.measurementSent) slot.appendChild(_noneChip(clickable));" in js
    assert "if (!chips.length) return;" in js
    # 칩을 누르면 기존 발송 이력 창이 열린다.
    assert "data-erp-alimtalk-trace-open" in js
    # 다른 모듈의 갱신 신호를 모두 듣는다.
    for name in ("foms:erp-structured-loaded", "foms:alimtalk-trace-update", "foms:share-trace-update",
                 "foms:channel-push-trace-update", "foms:send-trace-refresh"):
        assert name in js, name
    assert ".style." not in js


def test_summary_row_is_as_low_as_a_chip() -> None:
    """요약 줄은 칩과 같은 높이(26px)·테두리 없음 — 화면 차지 최소화(2026-09-23 사용자 요청)."""
    css = _read(CSS)
    summary = css.split(".erp-send-trace__summary {")[1].split("}")[0]
    assert "height: 26px;" in summary
    assert "border: 0;" in summary
    chip = css.split(".erp-send-chip {")[1].split("}")[0]
    assert "height: 26px;" in chip
    grid = css.split(".erp-send-trace__grid {")[1].split("}")[0]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in grid
    assert ".erp-send-trace--fold:empty {\n  display: none;" in css
    for kind in ("alim", "push", "sms", "fail", "none"):
        assert f".erp-send-chip--{kind}" in css, kind


def test_history_panel_includes_push_and_refreshes_send_trace() -> None:
    trace = _read("static/js/orders/erp-alimtalk-trace.js")
    assert "SHARE_SMS,CHANNELTALK_PUSH'" in trace
    assert "event.event_type === 'CHANNELTALK_PUSH'" in trace
    assert "document.dispatchEvent(new CustomEvent('foms:send-trace-refresh'));" in trace
    modal = _read("templates/orders/partials/erp_alimtalk_trace_modal.html")
    assert ">발송 이력</h5>" in modal
