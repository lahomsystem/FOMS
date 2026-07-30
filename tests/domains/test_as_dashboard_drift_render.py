"""AS 대시보드 기준 일정 드리프트 렌더 회귀 (T4).

스펙: docs/specs/2026-07-30-as-schedule-link-drift-design.md §4·§8.
플랜: docs/plans/2026-07-30-as-schedule-link-drift-plan.md "T4".

시드는 링크 API(T2, 동시 편집 중)를 거치지 않고 `write_link()`와 같은 모양의 dict를
structured_data에 직접 심는다(§3.1 스키마 고정). 렌더 경로(`apply_as_dashboard_row_display_fields`
→ `apply_schedule_link_drift_fields`)만 검증 대상이다.
"""
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

_TODAY = date.today().strftime("%Y-%m-%d")


def _login_as_admin(client, username: str = "drift-render-admin") -> None:
    """관리자 로그인 — AS 대시보드는 로그인 사용자 전원에게 보인다(쓰기 아님)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="드리프트 렌더 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id


def _create_ref_order(
    *, status: str = "CONSTRUCTION", construction_date: str | None,
    customer_name: str = "기준 주문 고객",
) -> int:
    """기준 주문(시공일 보유) 시드. `erp_construction_date` 컬럼만 채운다(스펙 §3.3).

    customer_name 은 배지 표시명 폴백(#id) 검증을 위해 override 가능(기본값은 정상 케이스).
    """
    order = Order(
        received_date=_TODAY,
        customer_name=customer_name,
        phone="010-0000-1111",
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


def _create_as_order(*, visit_date: str, ref_order_id: int, ref_date: str) -> int:
    """AS 주문 시드 — `schedule.as_visit.schedule_link`을 직접 심는다(write_link 출력 형태)."""
    schedule_link = {
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
        customer_name="드리프트 AS 고객",
        phone="010-2222-3333",
        address="Seoul",
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="Alice",
        as_received_date=_TODAY,
        is_erp_order=True,
        structured_data={
            "shipment": {"as_content": "<div>내용</div>"},
            "schedule": {"as_visit": {"date": visit_date, "schedule_link": schedule_link}},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def test_ref_moved_shows_banner_and_red_badge(client):
    """기준 시공일이 바뀌고 AS 방문일은 옛 기준(D0)에 남아있으면 ref_moved — 배너+빨강 배지.

    2026-07-30 가독성 개선: 배지는 기준 주문 id 대신 고객명을 보여주고(요구사항 1),
    아이콘 + 옛 날짜 취소선/새 날짜 굵게로 눈에 띄게 렌더한다(요구사항 3).
    """
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-12")
    _create_as_order(visit_date="2026-08-05", ref_order_id=ref_id, ref_date="2026-08-05")

    resp = client.get("/erp/as?tab=incomplete")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "as-schedule-drift-banner" in body
    assert "현재 목록에서 기준 일정이 변경된 AS 1건" in body
    assert "erp-as-drift-badge--ref_moved" in body
    # id 가 아니라 기준 주문의 고객명이 뜬다 — 옛 "#id" 표기는 이름이 있으면 더 이상 안 나온다.
    assert "기준 기준 주문 고객" in body
    assert f"기준 #{ref_id}" not in body
    # 경고 아이콘 + 옛 날짜 취소선 / 새 날짜 굵게(요구사항 3).
    assert "fa-triangle-exclamation" in body
    assert '<s class="erp-as-drift-badge__old">8/5</s>' in body
    assert '<strong class="erp-as-drift-badge__new">8/12</strong>' in body


def test_ref_moved_with_missing_customer_name_falls_back_to_id(client):
    """기준 주문 고객명이 비어있으면 이름 대신 '#id' 로 폴백한다(빈칸 배지 방지)."""
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-12", customer_name="")
    _create_as_order(visit_date="2026-08-05", ref_order_id=ref_id, ref_date="2026-08-05")

    resp = client.get("/erp/as?tab=incomplete")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f"기준 #{ref_id}" in body


def test_ref_unchanged_shows_no_banner(client):
    """기준 시공일이 링크 시점(D0)과 같으면 ok — 배너가 뜨지 않는다."""
    _login_as_admin(client)
    ref_id = _create_ref_order(construction_date="2026-08-05")
    _create_as_order(visit_date="2026-08-05", ref_order_id=ref_id, ref_date="2026-08-05")

    resp = client.get("/erp/as?tab=incomplete")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "as-schedule-drift-banner" not in body
    assert "erp-as-drift-badge--ref_moved" not in body


def test_ref_deleted_shows_grey_badge_and_banner_excludes_it(client):
    """기준 주문이 삭제되면 ref_gone(회색) — 조치 불가 상태라 배너 카운트에서 제외한다."""
    _login_as_admin(client)
    ref_id = _create_ref_order(status="DELETED", construction_date="2026-08-05")
    _create_as_order(visit_date="2026-08-05", ref_order_id=ref_id, ref_date="2026-08-05")

    resp = client.get("/erp/as?tab=incomplete")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "erp-as-drift-badge--ref_gone" in body
    assert "as-schedule-drift-banner" not in body
