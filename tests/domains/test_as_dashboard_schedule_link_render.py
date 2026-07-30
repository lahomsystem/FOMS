"""AS 기준 일정 매칭 UI 렌더/배선 회귀 (T3·T5).

스펙: docs/specs/2026-07-30-as-schedule-link-drift-design.md §5.
플랜: docs/plans/2026-07-30-as-schedule-link-drift-plan.md "T3"·"T5".

렌더 시드는 T4 테스트(test_as_dashboard_drift_render.py)와 같은 방식 — 링크 API를 거치지
않고 `write_link()` 출력 형태의 dict를 structured_data에 직접 심는다(§3.1 스키마 고정).

정적 계약 2종도 함께 잠근다:
- 모달 버튼 훅(`js-as-schedule-link`) 존재 — 리팩터에서 버튼이 통째로 사라지는 회귀 방지.
- 손댄 자산의 `?v=` 핀이 저장소 전역에서 하나로 일치 — 핀이 갈라지면 서비스워커가
  실기기에서 구버전 JS/CSS를 계속 실행한다(project_sw_stale_js_version_bump).
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

_ACTION_HOOKS = ("js-as-drift-relink", "js-as-drift-ack", "js-as-drift-unlink")


def _login_as_admin(client, username: str = "schedule-link-render-admin") -> None:
    """관리자 로그인 — 행 액션 버튼은 로그인 사용자 전원에게 보인다(쓰기는 API가 게이트)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="매칭 렌더 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id


def _create_ref_order(*, status: str = "CONSTRUCTION", construction_date: str | None) -> int:
    """기준 주문(시공일 보유) 시드. `erp_construction_date` 컬럼만 채운다(스펙 §3.3)."""
    order = Order(
        received_date=_TODAY,
        customer_name="기준 주문 고객",
        phone="010-0000-2222",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Bob",
        is_erp_order=True,
        erp_construction_date=construction_date,
        structured_data={"shipment": {}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _create_as_order(*, visit_date: str, ref_order_id: int | None = None,
                     ref_date: str | None = None) -> int:
    """AS 주문 시드. ref_order_id 가 없으면 링크 없는 행(드리프트 `none`)."""
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
        customer_name="매칭 AS 고객",
        phone="010-4444-5555",
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


def test_drifted_row_renders_three_actions_with_data_attributes(client):
    """ref_moved 행에는 재적용/무시/연결 해제 3개가 데이터 속성과 함께 렌더된다."""
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-12")
    as_id = _create_as_order(visit_date="2026-08-05", ref_order_id=ref_id, ref_date="2026-08-05")

    resp = client.get("/erp/as?tab=incomplete")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for hook in _ACTION_HOOKS:
        assert hook in body, hook
    assert f'data-as-order-id="{as_id}"' in body
    assert 'data-ref-current-date="2026-08-12"' in body
    assert 'data-drift-state="ref_moved"' in body
    for label in ("재적용", "무시", "연결 해제"):
        assert label in body, label


def test_non_drifted_row_renders_no_actions(client):
    """링크가 없는 행(드리프트 none)에는 액션 버튼이 하나도 없다."""
    _login_as_admin(client)
    _create_as_order(visit_date="2026-08-05")

    resp = client.get("/erp/as?tab=incomplete")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for hook in _ACTION_HOOKS:
        assert hook not in body, hook
    assert "erp-as-drift-actions" not in body


def test_ref_gone_row_renders_unlink_only(client):
    """기준 주문이 삭제된 ref_gone 은 재적용할 날짜가 없다 — '연결 해제'만 낸다."""
    _login_as_admin(client)
    ref_id = _create_ref_order(status="DELETED", construction_date="2026-08-05")
    _create_as_order(visit_date="2026-08-05", ref_order_id=ref_id, ref_date="2026-08-05")

    resp = client.get("/erp/as?tab=incomplete")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "js-as-drift-unlink" in body
    assert "js-as-drift-relink" not in body
    assert "js-as-drift-ack" not in body


def _find_schedule_buttons(body: str) -> list[str]:
    """렌더 본문에서 `.find-schedule-btn` 버튼 태그들만 잘라낸다(속성 검사용)."""
    return re.findall(r"<button[^>]*find-schedule-btn[^>]*>", body)


def test_find_schedule_btn_carries_linked_ref_order_id(client):
    """링크가 있으면 '일정찾기' 버튼이 현재 기준 주문 id 를 들고 렌더된다.

    한 응답에 PC 테이블 버튼과 모바일 카드 버튼이 함께 들어온다(as_dashboard_body 가
    두 표면을 같이 렌더하고 CSS 로 나눈다) — 두 경로 모두를 한 번에 잠근다.
    """
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-12")
    _create_as_order(visit_date="2026-08-05", ref_order_id=ref_id, ref_date="2026-08-05")

    body = client.get("/erp/as?tab=incomplete").get_data(as_text=True)

    buttons = _find_schedule_buttons(body)
    assert len(buttons) >= 2, buttons  # PC 테이블 + 모바일 카드
    assert all(f'data-linked-ref-order-id="{ref_id}"' in b for b in buttons)


def test_find_schedule_btn_has_no_ref_id_without_link(client):
    """링크가 없으면 같은 버튼의 `data-linked-ref-order-id` 는 빈 값이다(모달 = 미매칭 표시)."""
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-12")
    _create_as_order(visit_date="2026-08-05")

    body = client.get("/erp/as?tab=incomplete").get_data(as_text=True)

    buttons = _find_schedule_buttons(body)
    assert len(buttons) >= 2, buttons
    assert f'data-linked-ref-order-id="{ref_id}"' not in body
    assert all('data-linked-ref-order-id=""' in b for b in buttons)


def test_schedule_link_marking_is_a_single_shared_path():
    """모달 최초 렌더와 매칭 직후가 같은 표시 함수(markScheduleLinkApplied)를 쓴다.

    두 곳에서 라벨/비활성 상태를 따로 조립하면 재오픈 시 '매칭됨'이 소실되는 회귀가
    다시 난다(Defect 1). 호출 지점 2곳 + 상태를 실어 나르는 `linkedRefId` 를 잠근다.
    """
    js = (_ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")

    assert js.count("function markScheduleLinkApplied(") == 1
    assert js.count("markScheduleLinkApplied(") == 3  # 정의 1 + 호출 2(초기 렌더·매칭 직후)
    assert "_searchState.linkedRefId" in js
    assert "btn.dataset.linkedRefOrderId" in js


def test_match_writes_as_visit_date_through_existing_save_path():
    """매칭 성공 후 방문일 자동 기록이 기존 날짜 저장 경로를 그대로 탄다(Defect 2)."""
    js = (_ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")

    assert "writeAsVisitDateFromLink(" in js
    # 새 날짜 쓰기 fetch 를 만들지 않고 기존 헬퍼 체인을 재사용한다.
    assert "await applyRefDateToAsVisit(asOrderId, refDate)" in js
    assert "getDateInputsForOrder(asOrderId, 'as_visit_date')[0]" in js
    # 기존 값이 다를 때만 확인, 입력이 없으면 링크는 유지하고 안내만 남긴다(무음 실패 금지).
    assert "window.confirm('AS 방문일이 '" in js
    assert "매칭은 저장됐습니다." in js
    # 서버가 재조회한 기준일을 쓴다(클라 stale 금지, 스펙 §6).
    assert "res.data.link && res.data.link.ref_date" in js


def test_nearby_modal_match_button_hook_exists():
    """'이 일정에 매칭' 버튼 훅과 무음 실패 방지 배선이 JS 모듈에 살아 있어야 한다."""
    js = (_ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")

    assert "js-as-schedule-link" in js
    assert "data-ref-order-id=" in js
    assert "data-ref-date=" in js
    # 결과 행이 <a> 라 두 호출이 빠지면 편집 페이지로 이탈한다(스펙 §5.1).
    assert "e.stopPropagation();" in js and "e.preventDefault();" in js
    # 방어적 파싱 + .catch — 세션 만료 HTML 응답이 무음으로 삼켜지면 안 된다.
    assert "function parseJsonResponse(r)" in js
    assert "'서버 응답 오류 ('" in js
    # 재적용은 기존 날짜 저장 경로를 그대로 태운다(새 날짜 쓰기 코드 금지).
    assert "saveDateField(input, { silent: true })" in js
    assert "/api/update_order_field" in js


def test_touched_asset_cache_pins_are_in_sync():
    """손댄 JS/CSS 의 `?v=` 핀이 저장소 전역에서 하나로 일치한다(서비스워커 stale 가드)."""
    sources = [
        p
        for ext in ("*.html", "*.js", "*.py")
        for p in _ROOT.glob(f"**/{ext}")
        if not any(part in {".git", "node_modules", ".superpowers", "docs"} for part in p.parts)
    ]
    for asset in ("js/cs/as-dashboard.js", "css/contexts/cs/as-dashboard-body.css"):
        pattern = re.compile(re.escape(asset) + r"['\"\s\}\)]*\?v=([A-Za-z0-9._-]+)")
        pins = {
            pin
            for path in sources
            for pin in pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))
        }
        assert len(pins) == 1, f"{asset}: 핀 불일치/부재 {sorted(pins)}"
