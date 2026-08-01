"""Web Push(Phase 3B) client + Service Worker source 계약.

SW push/notificationclick/notificationclose 핸들러, deep link allowlist,
등록 SSOT(단일 navigator.serviceWorker.register), CTA 훅/구독 옵션을 텍스트/regex 로
검증한다. 기존 fetch handler 의 network-first timeout + cache fallback(perf guard G3)이
회귀하지 않았는지도 함께 확인한다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SW = ROOT / "static/sw.js"
SYNC_JS = ROOT / "static/js/foms/sync.js"
A2HS_JS = ROOT / "static/js/foms/a2hs-prompt.js"
PUSH_JS = ROOT / "static/js/foms/mobile-push.js"
PANEL = ROOT / "templates/partials/shared/erp_mobile_notification_panel.html"
APP_SHELL = ROOT / "templates/partials/shared/foms_app_shell.html"
LAYOUT_SCRIPTS = ROOT / "templates/partials/shared/layout_scripts.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- Service Worker push handlers -------------------------------------------


def test_sw_registers_push_lifecycle_handlers() -> None:
    """sw.js 는 push / notificationclick / notificationclose 핸들러와 showNotification 을 갖는다."""
    sw = _read(SW)
    assert re.search(r"addEventListener\(\s*['\"]push['\"]", sw)
    assert re.search(r"addEventListener\(\s*['\"]notificationclick['\"]", sw)
    assert re.search(r"addEventListener\(\s*['\"]notificationclose['\"]", sw)
    assert "showNotification" in sw
    # push payload 안전 파싱(try/catch) — 파싱 실패해도 generic 알림.
    assert "event.data.json()" in sw


def test_sw_notificationclick_deeplink_allowlist() -> None:
    """notificationclick deep link 는 same-origin '/erp/' 경로만 허용(오픈 리다이렉트 차단)."""
    sw = _read(SW)
    # allowlist 검증 로직: '/erp/' prefix + origin 비교 + 폴백 경로.
    assert 'indexOf("/erp/")' in sw
    assert "target.origin !== self.location.origin" in sw
    assert "/erp/dashboard" in sw  # 폴백 경로
    # 클릭/닫힘 서버 보고는 best-effort(엔드포인트 미존재해도 죽지 않음).
    assert "/erp/api/notifications/push/event" in sw
    assert "console.debug" in sw
    # SW 내부 write 는 헤더 직접 지정 + credentials include.
    assert "X-FOMS-Notification-Write" in sw
    assert 'credentials: "include"' in sw


def test_sw_fetch_networkfirst_timeout_cache_fallback_intact() -> None:
    """G3 회귀 방지: 기존 fetch handler 의 timeout + cache fallback 계약이 잔존한다."""
    sw = _read(SW)
    assert "NETWORK_FIRST_TIMEOUT_MS" in sw
    assert "setTimeout" in sw
    assert "staticCacheFirst(req, STATIC_CACHE)" in sw
    # 기존 install/activate/fetch 리스너 무변경.
    assert re.search(r"addEventListener\(\s*['\"]install['\"]", sw)
    assert re.search(r"addEventListener\(\s*['\"]activate['\"]", sw)
    assert re.search(r"addEventListener\(\s*['\"]fetch['\"]", sw)


def test_sw_cache_version_bumped() -> None:
    """푸시 핸들러 추가와 함께 CACHE_VERSION 이 bump 됐다(구 캐시 activate 시 purge)."""
    sw = _read(SW)
    assert 'CACHE_VERSION = "foms-p2-v10"' in sw


# --- 등록 SSOT: 단일 navigator.serviceWorker.register --------------------------


def test_service_worker_register_has_single_source_of_truth() -> None:
    """navigator.serviceWorker.register 직접 호출은 sync.js helper 한 곳뿐이다."""
    sync = _read(SYNC_JS)
    a2hs = _read(A2HS_JS)
    push = _read(PUSH_JS)

    # 실제 SW 등록 호출(register("/static/sw.js"))만 카운트 — prose 주석의 언급은 제외.
    call_re = re.compile(r"register\(\s*['\"]/static/sw\.js")
    assert len(call_re.findall(sync)) == 1, "sync.js 등록 SSOT 는 정확히 1회여야 한다"
    assert not call_re.search(a2hs), "a2hs-prompt.js 는 helper 경유여야 한다"
    assert not call_re.search(push), "mobile-push.js 는 helper 경유여야 한다"

    # helper 는 Promise<registration> SSOT — 진행 중 Promise 재사용(중복 register 방지).
    assert "window.fomsRegisterServiceWorker" in sync
    assert "window.__fomsSwRegistrationPromise" in sync
    # 소비자들은 helper 를 경유한다.
    assert "window.fomsRegisterServiceWorker" in a2hs
    assert "window.fomsRegisterServiceWorker" in push


# --- mobile-push.js client 계약 ---------------------------------------------


def test_mobile_push_js_is_replay_safe_and_uses_write_helper() -> None:
    """mobile-push.js: singleton 가드 + write helper 경유 + subscribe 옵션 + 에러 처리."""
    push = _read(PUSH_JS)
    # G4: singleton 가드.
    assert "window.__FOMS_MOBILE_PUSH_BOUND" in push
    # pushManager.subscribe 는 userVisibleOnly:true.
    assert "userVisibleOnly: true" in push
    assert "applicationServerKey" in push
    # 상태 판단 SSOT + VAPID key + 구독 write 엔드포인트.
    assert "/erp/api/notifications/mobile-state" in push
    assert "/erp/api/notifications/push/vapid-public-key" in push
    assert "/erp/api/notifications/push/subscribe" in push
    # 모든 write 는 공용 helper 경유(직접 window.fetch POST 금지).
    assert "FOMSNotificationWrite" in push
    # app icon badge feature detect + 공유 count 구독.
    assert "setAppBadge" in push
    assert "clearAppBadge" in push
    assert "FOMSNotificationBadge" in push
    # 외부 CDN fetch 금지 + fetch 에러 처리 + success 검증.
    assert "fetch('http" not in push
    assert 'fetch("http' not in push
    assert ".catch(" in push
    assert "data.success" in push


def test_mobile_push_js_denied_guide_and_no_deeplink() -> None:
    """차단(denied) 안내: 인라인 가이드 토글/패널 + 복귀 자동 재평가 + 딥링크 시도 금지."""
    push = _read(PUSH_JS)
    # '허용 방법 보기' 토글 + 인라인 가이드 패널 훅.
    assert "data-foms-push-guide-toggle" in push
    assert "data-foms-push-guide" in push
    # aria-expanded 관리(확장/접기 접근성).
    assert "aria-expanded" in push
    # OS 설정에서 켜고 복귀 시 자동 재평가.
    assert "visibilitychange" in push
    # 딥링크 시도 금지: 웹/PWA 는 OS 설정 화면을 프로그램적으로 열 수 없다.
    assert "intent://" not in push
    assert "app-prefs" not in push


def test_notification_panel_exposes_push_cta_hook() -> None:
    """알림 시트 partial 에 push CTA 훅(data-foms-push-cta)이 있고 인라인 script/onclick 금지."""
    panel = _read(PANEL)
    assert "data-foms-push-cta" in panel
    assert "onclick" not in panel
    assert "<script" not in panel
    # CTA 버튼은 JS 가 렌더 — 헤더 정적 버튼 수(모두읽음/모두보관/닫기=3)는 유지.
    assert panel.count("<button") == 3


def test_layout_scripts_wires_mobile_push_deferred_script() -> None:
    """알림 센터 승격: layout_scripts 가 mobile-push.js 를 defer 로드(PC·모바일 공통).

    foms_app_shell 에는 중복 로드 금지(단일 센터 SSOT).
    """
    layout = _read(LAYOUT_SCRIPTS)
    shell = _read(APP_SHELL)
    assert "js/foms/mobile-push.js" in layout
    assert "js/foms/mobile-push.js" not in shell
    for line in layout.splitlines():
        if "mobile-push.js" in line:
            assert "defer" in line, line
            break
    else:  # pragma: no cover
        raise AssertionError("mobile-push.js script tag missing in layout_scripts")
