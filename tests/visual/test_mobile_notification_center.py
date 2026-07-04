"""모바일 알림 센터 Phase 1A + 1B + 2 — 마크업/배선 계약.

벨은 홈 링크가 아니라 알림 시트를 여는 button 이어야 하고, unread badge span 과
bottom-sheet 패널 타깃이 존재해야 한다. Phase 1B(모두읽음/모두보관/항목보관/read),
Phase 2(긴급 pinned ack + 모바일 긴급 호출 진입점/시트) 계약을 함께 검증한다.
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
        # Phase 1B: 헤더 모두읽음 / 모두보관 액션 훅.
        "data-foms-notif-read-all",
        "data-foms-notif-archive-all",
    ):
        assert token in panel, token
    # Phase 1B: 헤더에 모두읽음 + 모두보관 + 닫기 = 버튼 3개.
    assert panel.count("<button") == 3
    # 액션은 여전히 위임 JS 가 처리 — 인라인 onclick 금지.
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
    # Phase 1B/2: 모든 write 는 same-origin write 헤더가 붙는 공용 helper 를 경유한다
    # (직접 window.fetch(..., {method:'POST'}) 로 상태 변경 금지).
    assert "FOMSNotificationWrite" in js
    assert "window.fetch(" not in js
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


# --- Phase 1B: 시트 write 액션 계약 -----------------------------------------


def test_notification_js_wires_read_archive_ack_write_actions() -> None:
    """모바일 알림 JS: read/archive/ack/read-all/archive-all POST 를 helper 로 배선한다."""
    js = (ROOT / "static/js/foms/mobile-notification.js").read_text(encoding="utf-8")
    # 항목 tap → read (미읽음일 때), 항목 보관, 긴급 ack, 헤더 모두읽음/모두보관 엔드포인트.
    assert "/read'" in js
    assert "/archive'" in js
    assert "/ack'" in js
    assert "/notifications/read-all" in js
    assert "/notifications/archive-all" in js
    # 위임 이벤트 훅.
    for hook in (
        "data-foms-notif-ack",
        "data-foms-notif-archive-item",
        "data-foms-notif-read-all",
        "data-foms-notif-archive-all",
        "data-foms-notif-item",
    ):
        assert hook in js, hook
    # 배지 재동기화 + 공용 write helper 경유.
    assert "FOMSNotificationBadge" in js and "refresh" in js
    assert "FOMSNotificationWrite" in js
    # Pinned 긴급 기준이 ack_at 로 갱신됨(is_read 기준 아님).
    assert "ack_at" in js


def test_notification_js_pins_urgent_by_ack_not_read() -> None:
    """긴급 pinned 필터: is_urgent && !ack_at (ack 하면 일반 목록으로 내려간다)."""
    js = (ROOT / "static/js/foms/mobile-notification.js").read_text(encoding="utf-8")
    assert "n.is_urgent && !n.ack_at" in js


# --- Phase 2: 긴급 호출 진입점 + 대상 picker 시트 + ack --------------------------


def test_urgent_call_panel_partial_structure() -> None:
    """긴급 호출 시트 partial: offcanvas + 대상/사유/전송 훅, 인라인 script/onclick 금지."""
    panel = (
        ROOT / "templates/partials/shared/erp_mobile_urgent_call_panel.html"
    ).read_text(encoding="utf-8")
    for token in (
        'id="erp-mobile-urgent-call-sheet"',
        "offcanvas offcanvas-bottom",
        "data-foms-urgent-sheet",
        "data-foms-urgent-targets",
        "data-foms-urgent-message",
        "data-foms-urgent-send",
        'maxlength="500"',
        'data-bs-dismiss="offcanvas"',
    ):
        assert token in panel, token
    assert "onclick" not in panel
    assert "<script" not in panel


def test_urgent_call_js_is_replay_safe_and_uses_write_helper() -> None:
    """긴급 호출 JS: singleton 가드 + urgent-targets GET + urgent-mention write helper."""
    js = (ROOT / "static/js/foms/urgent-call-sheet.js").read_text(encoding="utf-8")
    assert "window.__FOMS_URGENT_CALL_BOUND" in js
    assert "urgent-targets" in js
    assert "urgent-mention" in js
    assert "FOMSNotificationWrite" in js
    # 사유 500자 client-side 제한.
    assert "500" in js
    # 위임 진입점 훅.
    assert "data-foms-urgent-call" in js
    assert "data-foms-urgent-target" in js
    # 외부 CDN fetch 금지 + 에러 처리.
    assert "fetch('http" not in js
    assert 'fetch("http' not in js
    assert ".catch(" in js
    assert "data.success" in js


def test_app_shell_wires_urgent_call_panel_and_deferred_script() -> None:
    """foms_app_shell 이 긴급 호출 시트 include + defer 스크립트를 로드한다."""
    shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(
        encoding="utf-8"
    )
    assert "erp_mobile_urgent_call_panel.html" in shell
    assert "js/foms/urgent-call-sheet.js" in shell
    for line in shell.splitlines():
        if "urgent-call-sheet.js" in line:
            assert "defer" in line, line
            break
    else:  # pragma: no cover
        pytest.fail("urgent-call-sheet.js script tag missing")


def test_urgent_call_entry_points_exist_in_order_and_drawing_surfaces() -> None:
    """긴급 호출 진입점: 주문 상세 카드(모바일) + 도면 workbench 모바일 toolbar."""
    order_detail = (
        ROOT / "templates/orders/partials/dashboard_scripts_detail_dom.html"
    ).read_text(encoding="utf-8")
    order_detail_js = (
        ROOT / "static/js/orders/dashboard/erp-dashboard-detail-dom.js"
    ).read_text(encoding="utf-8")
    drawing = (
        ROOT / "templates/drawing/partials/workbench_mobile_handoff.html"
    ).read_text(encoding="utf-8")

    # 주문 상세: 모바일 전용(d-lg-none) 긴급 호출 버튼 + order 문맥.
    assert "data-foms-urgent-call" in order_detail
    assert 'data-order-id="${orderId}"' in order_detail
    # 동기화된 인라인 사본(JS)도 동일 진입점을 렌더한다.
    assert "data-foms-urgent-call" in order_detail_js
    # 도면 workbench 모바일 액션바: order.id 문맥.
    assert "data-foms-urgent-call" in drawing
    assert 'data-order-id="{{ order.id }}"' in drawing
