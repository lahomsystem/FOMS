"""긴급(P0) 전체화면 빨간 창 공용 모듈 계약 (SPEC 2026-10-02-urgent-alert-everywhere §A·§D).

인라인 오버레이(layout_head)를 static/js/foms/foms-urgent-alert.js 하나로 옮겼다.
standalone 화면 브리지가 공개 이름을 부르므로 이름이 바뀌면 여기서 깨진다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "static/js/foms/foms-urgent-alert.js"
CSS = ROOT / "static/css/components/foms-urgent-alert.css"
LAYOUT_HEAD = ROOT / "templates/partials/shared/layout_head.html"
HEAD_INIT = ROOT / "static/js/runtime/layout-head-init.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_module_exposes_public_contract() -> None:
    js = _read(MODULE)
    assert "if (window.FOMSUrgentAlert) return;" in js  # 싱글톤 가드
    for name in ("show: show", "handle: handle", "bindSocket: bindSocket", "resync: resync", "openFromPush: openFromPush"):
        assert name in js, name
    assert "window.triggerUrgentBriefingAlert = function" in js  # 호환 별칭
    assert "data.urgent !== true" in js


def test_module_resync_and_ack_wiring() -> None:
    js = _read(MODULE)
    assert "'/erp/api/notifications/pending-urgent'" in js
    assert "credentials: 'same-origin'" in js
    assert "data.success" in js
    assert "MIN_INTERVAL_MS = 30000" in js
    assert "'socket-connect': 1" in js and "'sw-click': 1" in js
    assert "'/ack'" in js
    assert "window.FOMSNotificationWrite.fetch" in js
    assert "'X-FOMS-Notification-Write': '1'" in js
    assert "FOMSNotificationBadge.refresh({ force: true })" in js


def test_module_socket_binding_is_idempotent() -> None:
    js = _read(MODULE)
    assert "socket.__fomsUrgentBound" in js
    assert "socket.on('erp_notification', handle)" in js
    assert "resync('socket-connect')" in js


def test_module_cross_tab_push_and_visibility() -> None:
    js = _read(MODULE)
    assert "CHANNEL_NAME = 'foms-urgent'" in js
    assert "typeof window.BroadcastChannel === 'function'" in js  # 미지원 가드
    assert "type: 'ack', notification_id" in js
    assert "navigator.serviceWorker" in js
    assert "'foms-urgent-open'" in js
    assert "visibilitychange" in js
    assert "resync('load')" in js


def test_module_close_rules_and_safety() -> None:
    """확인 버튼 하나로만 닫힌다: confirm()·인라인 스타일·innerHTML 없음, 키는 캡처 단계에서 가둔다."""
    js = _read(MODULE)
    assert "confirm(" not in js
    assert "style.cssText" not in js
    assert ".style." not in js
    assert "innerHTML" not in js
    assert "textContent" in js
    assert "stopImmediatePropagation" in js
    assert "onKey, true" in js  # 캡처 단계 등록
    assert "'Escape'" not in js  # Esc 로 닫는 경로가 없어야 한다
    # 새 JS 300줄 래칫(tests/harness/test_file_size_ratchet.py)
    assert len(js.splitlines()) < 300


def test_css_file_has_overlay_layer() -> None:
    css = _read(CSS)
    m = re.search(r"\.foms-urgent-alert\s*\{[^}]*z-index:\s*(\d+)", css)
    assert m and int(m.group(1)) >= 106000
    assert "white-space: pre-line" in css


def test_layout_head_delegates_to_module() -> None:
    head = _read(LAYOUT_HEAD)
    init_js = _read(HEAD_INIT)
    for text in (head, init_js):
        assert "urgent-fullscreen-overlay" not in text
        assert "window.triggerUrgentBriefingAlert = function" not in text
        assert "window.FOMSUrgentAlert.handle(data)" in text
        assert "window.FOMSUrgentAlert.resync('socket-connect')" in text
        # layout 은 bindSocket 을 부르지 않는다(이중 바인딩 방지).
        assert "FOMSUrgentAlert.bindSocket" not in text
        assert "window.FOMSDrawingAlert.handle(data)" in text


def test_layout_head_loads_module_deferred_before_socket_loader() -> None:
    head = _read(LAYOUT_HEAD)
    tag = re.search(r"<script[^>]*js/foms/foms-urgent-alert\.js[^>]*>", head)
    assert tag and re.search(r"\bdefer\b", tag.group(0))
    assert "css/components/foms-urgent-alert.css" in head
    assert head.index("js/foms/foms-urgent-alert.js") < head.index('id="global-socketio-loader"')
