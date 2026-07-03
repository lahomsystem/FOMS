"""모바일 알림 센터 Phase 1A — 마크업/배선 계약.

벨은 홈 링크가 아니라 알림 시트를 여는 button 이어야 하고, unread badge span 과
bottom-sheet 패널 타깃이 존재해야 한다. read/read-all/archive(Phase 1B)는 범위 밖.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]


def _login_admin(client) -> User:
    user = User(
        username="mobile_notif_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Mobile Notif Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_shell_header_bell_is_notification_button_not_home_link() -> None:
    """벨은 홈 링크(<a href=_home_href>)가 아니라 알림 시트 opener button 이다."""
    header = (
        ROOT / "templates/partials/shared/erp_mobile_shell_header.html"
    ).read_text(encoding="utf-8")
    # 홈 링크로 쓰이던 벨이 제거되어야 한다.
    assert 'href="{{ _home_href }}"' not in header
    assert 'aria-label="ERP 홈"' not in header
    # button + a11y 속성 + 시트 타깃 연결.
    assert "data-foms-notif-open" in header
    assert 'aria-controls="erp-mobile-notification-sheet"' in header
    assert 'aria-expanded="false"' in header
    assert 'aria-label="알림"' in header
    # unread badge span (기본 숨김).
    assert "data-foms-notif-badge" in header
    assert "erp-mobile-shell-header__notify-badge" in header
    # 벨은 button 요소여야 한다: notify 클래스 바로 앞 여는 태그가 <button.
    prefix = header.split('class="erp-mobile-shell-header__notify', 1)[0]
    assert prefix.rstrip().endswith("<button"), "notify bell must be a <button> element"


def test_notification_panel_partial_structure() -> None:
    """알림 시트 partial 은 offcanvas + 리스트/긴급/placeholder 훅을 노출한다."""
    panel = (
        ROOT / "templates/partials/shared/erp_mobile_notification_panel.html"
    ).read_text(encoding="utf-8")
    for token in (
        'id="erp-mobile-notification-sheet"',
        "offcanvas offcanvas-bottom",
        "erp-mobile-notif-sheet",
        "data-foms-notif-sheet",
        "data-foms-notif-urgent",
        "data-foms-notif-list",
        "data-foms-notif-placeholder",
        'data-bs-dismiss="offcanvas"',
    ):
        assert token in panel, token
    # Phase 1A: 시트에는 닫기 버튼 하나뿐 — read/read-all/archive 액션 버튼 없음.
    assert panel.count("<button") == 1
    assert "onclick" not in panel
    # 인라인 <script> 금지(perf: replay 체인 amplifier 회피).
    assert "<script" not in panel


def test_app_shell_wires_panel_and_deferred_script() -> None:
    """foms_app_shell 이 알림 시트 include + defer 스크립트를 로드한다."""
    shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(
        encoding="utf-8"
    )
    assert "erp_mobile_notification_panel.html" in shell
    assert "js/foms/mobile-notification.js" in shell
    # 신규 <script> 는 defer (render-block 금지 / perf guard G1).
    for line in shell.splitlines():
        if "mobile-notification.js" in line:
            assert "defer" in line, line
            break
    else:  # pragma: no cover
        pytest.fail("mobile-notification.js script tag missing")


def test_notification_js_is_fragment_replay_safe_and_shares_badge() -> None:
    """모바일 알림 JS: singleton 가드 + 배지 fetch 미중복(공유 pub/sub 구독) + CDN 금지."""
    js = (ROOT / "static/js/foms/mobile-notification.js").read_text(encoding="utf-8")
    # G4: window.__*_BOUND singleton 가드 (fragment 재실행 idempotent).
    assert "window.__FOMS_MOBILE_NOTIF_BOUND" in js
    # 배지는 공유 pub/sub 구독만 — badge endpoint 를 fetch 하지 않는다.
    assert "FOMSNotificationBadge" in js
    assert "fetch('/erp/api/notifications/badge" not in js
    assert 'fetch("/erp/api/notifications/badge' not in js
    # 목록은 기존 GET API 재사용.
    assert "'/erp/api/notifications?limit='" in js
    # 백엔드 수정 금지 범위(Phase 1B): write 액션 없음 → POST 요청을 발생시키지 않는다.
    assert "method: 'POST'" not in js
    assert 'method: "POST"' not in js
    # 외부 CDN fetch/import 금지.
    assert "fetch('http" not in js
    assert 'fetch("http' not in js
    # fetch 에러 처리 + success 검증.
    assert ".catch(" in js
    assert "data.success" in js


def test_cohort_dashboard_renders_notification_bell_and_sheet(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort 모바일 대시보드 HTML 이 알림 button + 시트 + badge 훅을 렌더한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    for token in (
        "data-foms-notif-open",
        'id="erp-mobile-notification-sheet"',
        "data-foms-notif-badge",
        "data-foms-notif-list",
        "js/foms/mobile-notification.js",
    ):
        assert token in html, token
    # 벨이 홈 링크로 회귀하지 않았는지.
    assert 'aria-label="ERP 홈"' not in html
