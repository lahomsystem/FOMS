"""주문 상세 최상단 AS 기준 일정 드리프트 배너 렌더 회귀.

스펙: docs/specs/2026-07-30-as-schedule-link-drift-design.md §4·§5.2.

목록(행 배지, test_as_dashboard_drift_render.py)만 있던 표시를 **주문을 연 사람**에게도
내는 표면이다 — 판정은 같은 서비스(`build_schedule_link_drift`)를 거치고, 시드도 목록
테스트와 같은 방식(링크 API 를 거치지 않고 `write_link()` 출력 형태 dict 를 직접 심음)이다.

정적 계약도 함께 잠근다: 신규 자산 2종의 `?v=` 핀이 저장소 전역에서 하나로 일치해야
서비스워커가 실기기에서 구버전 CSS/JS 를 계속 실행하지 않는다
(project_sw_stale_js_version_bump).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

_ROOT = Path(__file__).resolve().parents[2]
_TODAY = date.today().strftime("%Y-%m-%d")

_BANNER_ASSETS = (
    "css/components/foms-as-drift-banner.css",
    "js/orders/as-drift-banner.js",
)


def _login_as_admin(client, username: str = "drift-banner-admin") -> None:
    """관리자 로그인 — /edit/<id> 는 ADMIN/MANAGER/STAFF 만 접근한다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="드리프트 배너 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id


def _create_ref_order(*, construction_date: str, customer_name: str = "노현정") -> int:
    """기준 주문(시공일 보유) 시드. `erp_construction_date` 만 채운다(스펙 §3.3)."""
    order = Order(
        received_date=_TODAY,
        customer_name=customer_name,
        phone="010-0000-3333",
        address="Seoul",
        product="붙박이장",
        status="CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        erp_construction_date=construction_date,
        structured_data={"shipment": {}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _create_as_order(
    *, visit_date: str, ref_order_id: int | None = None, ref_date: str | None = None
) -> int:
    """AS 주문 시드. ref_order_id 가 없으면 링크 없는 주문(드리프트 `none`)."""
    as_visit: dict = {"date": visit_date}
    if ref_order_id is not None:
        as_visit["schedule_link"] = {
            "ref_order_id": ref_order_id,
            "ref_kind": "construction",
            "ref_date": ref_date,
            "linked_at": "2026-07-30T00:00:00",
            "linked_by_user_id": None,
            "linked_by": "테스트",
            "source": "as_nearby_modal",
            "ack_ref_date": None,
        }
    order = Order(
        received_date=_TODAY,
        customer_name="배너 AS 고객",
        phone="010-6666-7777",
        address="Seoul",
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="Alice",
        as_received_date=_TODAY,
        is_erp_order=True,
        structured_data={
            "shipment": {"as_content": "<div>내용</div>"},
            "schedule": {"as_visit": as_visit},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def test_ref_moved_order_detail_shows_loud_banner(client):
    """기준 시공일이 움직인 AS 주문을 열면 상단에 빨강 배너 + 고객명 + 옛/새 날짜가 뜬다."""
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-12")
    as_id = _create_as_order(visit_date="2026-08-11", ref_order_id=ref_id, ref_date="2026-08-11")

    resp = client.get(f"/edit/{as_id}")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="fomsAsDriftBanner"' in body
    assert "foms-as-drift-banner--ref_moved" in body
    # 기준 주문 고객명 + 옛 날짜 → 새 날짜 ("기준 노현정 8/11 → 8/12").
    assert "기준 노현정" in body
    assert '<s class="foms-as-drift-banner__old">8/11</s>' in body
    assert '<strong class="foms-as-drift-banner__new">8/12</strong>' in body
    assert "fa-triangle-exclamation foms-as-drift-banner__icon" in body
    # 액션 3종 + 새 일정 전달값(서버 정규화된 Ds).
    for hook in ("js-as-banner-drift-relink", "js-as-banner-drift-ack", "js-as-banner-drift-unlink"):
        assert hook in body, hook
    assert f'data-as-order-id="{as_id}"' in body
    assert 'data-ref-current-date="2026-08-12"' in body
    # 자산은 배너와 함께 실린다(fragment 표면엔 layout head 가 없다).
    for asset in _BANNER_ASSETS:
        assert asset in body, asset


def test_order_without_link_shows_no_banner(client):
    """링크가 없는 주문(state='none')은 배너도 배너 자산도 렌더하지 않는다."""
    _login_as_admin(client)
    as_id = _create_as_order(visit_date="2026-08-11")

    resp = client.get(f"/edit/{as_id}")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "foms-as-drift-banner" not in body
    for asset in _BANNER_ASSETS:
        assert asset not in body, asset


def test_matched_order_shows_quiet_banner_without_actions(client):
    """기준일과 일치(ok)면 파란 한 줄 확인 표기만 — 액션 버튼도 JS 도 싣지 않는다."""
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-11")
    as_id = _create_as_order(visit_date="2026-08-11", ref_order_id=ref_id, ref_date="2026-08-11")

    resp = client.get(f"/edit/{as_id}")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "foms-as-drift-banner--ok" in body
    assert "조치 불필요" in body
    assert "foms-as-drift-banner--ref_moved" not in body
    assert "js-as-banner-drift-relink" not in body
    assert "js/orders/as-drift-banner.js" not in body


def test_mobile_detail_shows_same_banner(client):
    """모바일 주문 상세(/erp/orders/<id>/mobile)도 같은 배너를 낸다(표면별 분기 없음)."""
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-12")
    as_id = _create_as_order(visit_date="2026-08-11", ref_order_id=ref_id, ref_date="2026-08-11")

    resp = client.get(f"/erp/orders/{as_id}/mobile")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "foms-as-drift-banner--ref_moved" in body
    assert "기준 노현정" in body


def test_banner_js_uses_existing_endpoints_and_singleton_guard():
    """배너 JS 는 기존 두 엔드포인트만 쓰고, fragment 재실행 대비 싱글톤 가드를 갖는다."""
    js = (_ROOT / "static/js/orders/as-drift-banner.js").read_text(encoding="utf-8")

    assert "window.__FOMS_AS_DRIFT_BANNER_BOUND" in js  # perf G4
    assert "'/api/update_order_field'" in js
    assert "'/as/schedule-link'" in js
    # 세 번째 엔드포인트 금지 — 위 두 개 외에 fetch 대상이 없어야 한다.
    assert len(re.findall(r"fetch\(", js)) == 1
    # 무음 실패 금지: 방어적 파싱 + .catch + 화면 메시지.
    assert "function parseJsonResponse(r)" in js
    assert "'서버 응답 오류 ('" in js
    assert ".catch(function (err)" in js
    assert "showMessage(banner," in js


def test_banner_script_tag_is_deferred():
    """신규 <script> 는 defer(perf G1) — 렌더 차단 금지."""
    tpl = (_ROOT / "templates/orders/partials/as_drift_banner.html").read_text(encoding="utf-8")

    tag = re.search(r"<script[^>]*as-drift-banner\.js[^>]*>", tpl)
    assert tag is not None, tpl
    assert re.search(r"\bdefer\b", tag.group(0)), tag.group(0)


def test_banner_asset_cache_pins_are_in_sync():
    """신규 CSS/JS 의 `?v=` 핀이 저장소 전역에서 하나로 일치한다(서비스워커 stale 가드)."""
    sources = [
        p
        for ext in ("*.html", "*.js", "*.py")
        for p in _ROOT.glob(f"**/{ext}")
        if not any(part in {".git", "node_modules", ".superpowers", "docs"} for part in p.parts)
    ]
    for asset in _BANNER_ASSETS:
        pattern = re.compile(re.escape(asset) + r"['\"\s\}\)]*\?v=([A-Za-z0-9._-]+)")
        pins = {
            pin
            for path in sources
            for pin in pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))
        }
        assert len(pins) == 1, f"{asset}: 핀 불일치/부재 {sorted(pins)}"
