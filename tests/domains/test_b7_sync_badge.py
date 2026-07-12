"""B7 sync 배지 + 재시도 큐 계약.

정적 파일(신규 공용 쓰기 래퍼/배지 CSS/헤더 마커/Wave1 스왑)과 셸 렌더 스모크
(헤더 배지 마커 + foms-write.js/foms-sync-badge.css 로드)를 검증한다.
서버 API 무변경이므로 JS 계약은 정적 텍스트 + 렌더 스모크로 확인한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_b7_foms_write_wrapper_surface() -> None:
    """foms-write.js: 공용 래퍼 + 큐 카운트 + 싱글톤 가드(G4) + 배지 3상태."""
    js = _read("static/js/foms/foms-write.js")
    # 공용 API 표면.
    assert "window.fomsWriteFetch" in js
    assert "window.fomsSyncPendingCount" in js
    # 오프라인 큐 폴백은 sync.js helper 경유(중복 구현 금지).
    assert "fomsOfflineEnqueueRequest" in js
    assert "fomsOfflineEnabled" in js
    assert "queued: true" in js
    # sync.js 와 동일한 IndexedDB 큐(DB/STORE 일치).
    assert "foms-offline-v1" in js
    assert "pending-writes" in js
    # fragment 재실행 대비 싱글톤 가드(perf guard G4 skip 조건).
    assert "window.__FOMS_WRITE_BOUND" in js
    # 배지 갱신 트리거 + 3상태.
    assert "foms:sync-changed" in js
    assert "visibilitychange" in js
    assert "foms-sync-badge--warn" in js
    assert "foms-sync-badge--danger" in js


def test_b7_sync_js_dispatches_flush_event() -> None:
    """sync.js flushQueue 는 결과를 foms:sync-changed 로 발행한다(SW 등록 SSOT 무변경)."""
    sync = _read("static/js/foms/sync.js")
    assert "foms:sync-changed" in sync
    assert 'detail: { source: "flush"' in sync
    # SW 등록 호출은 여전히 정확히 1회(등록 SSOT 회귀 방지).
    assert sync.count('register("/static/sw.js"') == 1


def test_b7_badge_css_component_exists() -> None:
    """배지 CSS 는 별도 컴포넌트 파일 + v2 스코프(헤더 그리드 무변경)."""
    css = _read("static/css/components/foms-sync-badge.css")
    assert ".foms-sync-badge" in css
    assert ".foms-sync-badge--warn" in css
    assert ".foms-sync-badge--danger" in css
    assert "body.erp-mobile-v2-layout" in css
    # 그리드 칼럼 선언을 건드리지 않는다(프로즈 언급은 허용, 실제 선언 금지).
    assert "grid-template-columns:" not in css


def test_b7_header_badge_marker_and_grid_untouched() -> None:
    """헤더는 __context 안 인라인 배지만 추가하고 그리드 칼럼 마크업은 무변경."""
    header = _read("templates/partials/shared/erp_mobile_shell_header.html")
    assert "data-foms-sync-badge" in header
    assert "foms-sync-badge" in header
    # 배지는 context 영역 안(그리드 칼럼 신설 아님).
    ctx = header.split("erp-mobile-shell-header__context", 1)[1]
    assert "data-foms-sync-badge" in ctx.split("</div>", 1)[0]


def test_b7_app_shell_loads_write_js_and_badge_css() -> None:
    """foms_app_shell 이 write.js(defer) + sync-badge.css 를 로드한다."""
    shell = _read("templates/partials/shared/foms_app_shell.html")
    assert "js/foms/foms-write.js" in shell
    assert "css/components/foms-sync-badge.css" in shell
    for line in shell.splitlines():
        if "foms-write.js" in line:
            assert "defer" in line, line
            break
    else:  # pragma: no cover
        raise AssertionError("foms-write.js script tag missing")


def test_b7_wave1_writes_use_wrapper() -> None:
    """Wave1 쓰기 fetch 는 fomsWriteFetch(있으면) 경유로 스왑됐다(폴백 유지)."""
    call_log = _read("static/js/orders/foms-call-log.js")
    prod = _read("static/js/production/foms-production-steps.js")
    packing = _read("static/js/shipment/foms-packing.js")
    for src in (call_log, prod):
        assert "window.fomsWriteFetch || fetch" in src
        assert "writeFetch(" in src
    assert "window.fomsWriteFetch" in packing
    # call-log 의 POST 는 writeFetch 로 전송.
    assert "writeFetch('/api/orders/" in call_log


def _login_admin(client) -> User:
    user = User(
        username="b7_sync_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="B7 Sync Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_b7_dashboard_renders_sync_badge_and_write_js(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v2 셸 렌더 스모크: 헤더 배지 마커 + write.js/배지 CSS 로드가 HTML 에 존재한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    assert "data-foms-sync-badge" in html
    assert "js/foms/foms-write.js" in html
    assert "css/components/foms-sync-badge.css" in html
