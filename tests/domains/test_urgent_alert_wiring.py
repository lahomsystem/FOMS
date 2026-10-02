"""긴급 알림 빨간 창 배선 계약 (SPEC 2026-10-02 urgent-alert-everywhere §B·§D).

왜: 긴급 멘션·공지의 전체화면 경고는 `layout_head` 안에만 있었다. standalone 화면인
도면 마법사·실측 지도에서는 뜨지 않았고, PC 팝업(OS 웹푸시)을 누르면 sw.js 가 열린 창을
navigate 해서 메모리에만 있던 빨간 창과 마법사 작업까지 지웠다. 여기서는 정적 배선을 고정한다:
- 마법사·지도가 모듈·CSS·브리지를 싣고 브리지가 `FOMSUrgentAlert.bindSocket` 을 부른다.
- 지도에 새로 실은 스크립트는 전부 defer(G1/G2 렌더 비차단).
- sw.js 긴급 클릭은 navigate 없이 focus + 'foms-urgent-open' postMessage, 비긴급은 현행 navigate.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WIZARD = ROOT / "templates" / "drawing" / "wizard.html"
WIZARD_BRIDGE = ROOT / "static" / "js" / "drawing" / "wizard-alert-bridge.js"
MAP_VIEW = ROOT / "templates" / "measurement" / "map_view.html"
MAP_BRIDGE = ROOT / "static" / "js" / "measurement" / "map-urgent-bridge.js"
SW = ROOT / "static" / "sw.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _script_tag(html: str, needle: str) -> str:
    for match in re.finditer(r"<script\b[^>]*>", html):
        if needle in match.group(0):
            return match.group(0)
    raise AssertionError(f"script tag not found: {needle}")


def _function_body(src: str, signature: str) -> str:
    """signature 부터 다음 최상위 `\n}` 까지(함수 본문)."""
    start = src.index(signature)
    end = src.index("\n}", start)
    return src[start:end]


def _listener_body(src: str, event_name: str) -> str:
    start = src.index(f'self.addEventListener("{event_name}"')
    end = src.index("\n});", start)
    return src[start:end]


# --- 도면 마법사 ---------------------------------------------------------------


def test_wizard_loads_urgent_module_and_css() -> None:
    html = _read(WIZARD)
    head = html[: html.index("</head>")]
    assert "css/components/foms-urgent-alert.css" in head
    module = _script_tag(html, "js/foms/foms-urgent-alert.js")
    bridge = _script_tag(html, "js/drawing/wizard-alert-bridge.js")
    assert " defer" in module and " defer" in bridge
    # 브리지가 모듈 존재를 기다리지만, 순서상 모듈이 먼저 실려야 첫 시도에 붙는다.
    assert html.index("js/foms/foms-urgent-alert.js") < html.index("js/drawing/wizard-alert-bridge.js")
    # 기존 수정 요청 확인창 배선은 그대로.
    assert "js/foms/foms-drawing-alert.js" in html
    assert "cdn.socket.io/4.5.4/socket.io.min.js" in html


def test_wizard_bridge_binds_urgent_alert_and_keeps_drawing_alert() -> None:
    js = _read(WIZARD_BRIDGE)
    assert "window.FOMSUrgentAlert.bindSocket(socket)" in js
    assert "window.FOMSDrawingAlert.bindSocket(socket)" in js
    # 대기 조건이 긴급 모듈만 있어도 소켓을 연다.
    assert "!window.FOMSUrgentAlert" in js
    # 소켓은 한 번만.
    assert "window.__wizardAlertSocket" in js


# --- 실측 지도 -----------------------------------------------------------------


def test_map_view_loads_socket_module_and_bridge_deferred() -> None:
    html = _read(MAP_VIEW)
    head = html[: html.index("</head>")]
    assert "css/components/foms-urgent-alert.css" in head
    needles = (
        "cdn.socket.io/4.5.4/socket.io.min.js",
        "js/foms/notification-write.js",
        "js/foms/foms-urgent-alert.js",
        "js/measurement/map-urgent-bridge.js",
    )
    positions = []
    for needle in needles:
        tag = _script_tag(html, needle)
        assert " defer" in tag, f"G1/G2: 렌더 차단 금지 — {needle}"
        assert " async" not in tag, needle
        positions.append(html.index(needle))
    # 실행 순서(defer = 문서 순서): socket.io → write helper → 모듈 → 브리지.
    assert positions == sorted(positions)
    # standalone CSRF 배선은 이미 있다(확인 ack POST 용).
    assert 'include "partials/shared/csrf_bootstrap.html"' in html


def test_map_urgent_bridge_shape() -> None:
    js = _read(MAP_BRIDGE)
    assert "typeof window.io === 'undefined' || !window.FOMSUrgentAlert" in js
    assert "window.__mapUrgentSocket" in js
    assert "window.FOMSUrgentAlert.bindSocket(socket)" in js
    assert "reconnectionAttempts: Infinity" in js
    # 줄 수 상한(작은 브리지).
    assert len(js.splitlines()) <= 80


# --- 서비스 워커 ---------------------------------------------------------------


def test_sw_push_handler_carries_urgent_flag() -> None:
    sw = _read(SW)
    push = _listener_body(sw, "push")
    assert "urgent: pushData.urgent === true" in push


def test_sw_urgent_click_posts_message_and_does_not_navigate() -> None:
    sw = _read(SW)
    detect = _function_body(sw, "function isUrgentPushNotification(")
    assert "data.urgent === true" in detect
    assert 'indexOf("foms-urgent-") === 0' in detect  # 구 payload(tag) 호환

    urgent = _function_body(sw, "function handleUrgentNotificationClick(")
    assert "navigate" not in urgent
    assert 'clients.matchAll({ type: "window", includeUncontrolled: true })' in urgent
    assert ".focused" in urgent
    assert 'visibilityState === "visible"' in urgent
    assert ".focus()" in urgent
    assert 'type: "foms-urgent-open"' in urgent
    assert "notification_id: data.notification_id" in urgent
    assert ".postMessage(message)" in urgent
    # 열린 창이 없을 때만 대시보드를 연다.
    assert "clients.openWindow(PUSH_FALLBACK_DEEP_LINK)" in urgent
    assert 'reportPushEvent(data.notification_id, "opened")' in urgent


def test_sw_click_branches_urgent_before_navigate_and_keeps_non_urgent_navigate() -> None:
    sw = _read(SW)
    click = _listener_body(sw, "notificationclick")
    branch = click.index("isUrgentPushNotification(notification, data)")
    urgent_call = click.index("handleUrgentNotificationClick(data)")
    navigate = click.index("client.navigate(url)")
    assert branch < urgent_call < navigate
    # 긴급 분기는 return 으로 빠져 아래 navigate 경로에 닿지 않는다.
    assert "return;" in click[urgent_call:navigate]
    # 비긴급은 현행: deep link allowlist → focus → navigate, 창 없으면 openWindow(url).
    assert "sanitizePushDeepLink(data.deep_link)" in click
    assert "clients.openWindow(url)" in click


def test_sw_cache_version_bumped_for_urgent_click() -> None:
    assert 'CACHE_VERSION = "foms-p2-v11"' in _read(SW)
