"""시공일 변경 이벤트 SSOT 계약 (T1).

``CONSTRUCTION_DATE_CHANGED`` OrderEvent 의 **유일한 emit 지점**은
``foms/services/order_date_sync.py`` 의 전역 ``before_flush`` 훅이다. 라우트/서비스별 emit 은
전부 제거됐다(구 emit 2곳: ``erp_orders_structured.py`` · ``orders/field_update.py``).

여기서 고정하는 계약:

* 시공일을 움직이는 **모든 쓰기 경로**가 이벤트를 정확히 **1건** 남긴다 —
  PUT 전체저장 / PATCH 필드 / ``update_order_field(scheduled_date)`` / 시공불가 재예약 /
  품목별 시공일 인라인 패치 / 레거시 편집 폼.
* payload 는 ``{"from", "to", "source"}`` 이고 날짜는 **정규화 + 안정 정렬 콤마 연결**이다.
* 허위 이벤트 0: 값 무변경 · 표기만 다름(``2026-07-20`` vs ``2026/07/20``) · 다중값 순서만
  바뀜 · 주문 생성(이전 값 없음)은 전부 0건.
* actor 는 요청 컨텍스트면 세션 사용자, 아니면 ``None``(부팅 백필·스크립트·워커).
"""

from __future__ import annotations

from typing import Any

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User

_EVENT = "CONSTRUCTION_DATE_CHANGED"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_user(username: str, *, role: str = "ADMIN", team: str | None = None) -> User:
    """테스트 사용자 1명 생성(커밋 포함)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    """테스트 클라이언트 세션에 로그인 상태를 심는다."""
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(
    *,
    sd: dict[str, Any] | None = None,
    is_erp_order: bool = True,
    status: str = "RECEIVED",
    stage: str = "RECEIVED",
    scheduled_date: str | None = None,
) -> Order:
    """주문 1건 생성(커밋 포함). 생성 flush 는 이벤트 대상이 아니다."""
    order = Order(
        received_date="2026-07-01",
        customer_name="시공일 고객",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status=status,
        manager_name="담당",
        is_erp_order=is_erp_order,
        structured_data=sd,
        erp_stage_code=stage if is_erp_order else None,
        scheduled_date=scheduled_date,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _erp_sd(construction_date: str, *, stage: str = "RECEIVED", items: list | None = None) -> dict:
    """필수값(고객/전화/주소/제품명)을 갖춘 최소 ERP structured_data."""
    return {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": "시공일 고객", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123"},
        "items": items if items is not None else [{"product_name": "붙박이장"}],
        "schedule": {"construction": {"date": construction_date}},
        "shipment": {},
    }


def _events(order_id: int) -> list[OrderEvent]:
    """해당 주문의 CONSTRUCTION_DATE_CHANGED 이벤트를 생성순으로 반환."""
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == _EVENT)
        .order_by(OrderEvent.id.asc())
        .all()
    )


def _from_to(order_id: int) -> list[tuple[str, str]]:
    """이벤트 payload 의 (from, to) 목록."""
    return [(e.payload["from"], e.payload["to"]) for e in _events(order_id)]


@pytest.fixture
def inline_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """PATCH /structured/fields 게이트(FOMS_INLINE_EDIT_ENABLED)를 연다."""
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "true")


# --------------------------------------------------------------------------- #
# 1. PUT 전체 저장 (실제 라우트)
# --------------------------------------------------------------------------- #
def test_put_full_structured_save_emits_single_event(client):
    """PUT /api/orders/<id>/structured 로 시공일을 바꾸면 이벤트 정확히 1건."""
    user = _make_user("cde_put", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order(sd=_erp_sd("2026-07-20")).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd("2026-07-28")},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True

    events = _events(order_id)
    assert len(events) == 1
    assert events[0].payload["from"] == "2026-07-20"
    assert events[0].payload["to"] == "2026-07-28"
    assert events[0].payload["source"]  # 쓰기 경로 힌트(Flask endpoint)
    assert events[0].created_by_user_id == user_id


def test_put_full_structured_save_item_only_change_emits_event(client):
    """PUT 이 품목별 시공일만 바꿔도 이벤트가 난다(구 emit 의 사각지대)."""
    _login(client, _make_user("cde_put_item", role="ADMIN"))
    order_id = _make_order(
        sd=_erp_sd("2026-07-20", items=[{"product_name": "붙박이장", "construction_date": "2026-07-22"}])
    ).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": _erp_sd(
                "2026-07-20",
                items=[{"product_name": "붙박이장", "construction_date": "2026-07-29"}],
            )
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _from_to(order_id) == [("2026-07-20,2026-07-22", "2026-07-20,2026-07-29")]


# --------------------------------------------------------------------------- #
# 2. PATCH /structured/fields (실제 라우트)
# --------------------------------------------------------------------------- #
def test_patch_structured_field_emits_single_event(client, inline_enabled):
    """PATCH schedule.construction.date → 이벤트 1건."""
    _login(client, _make_user("cde_patch", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd("2026-07-20")).id

    resp = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        json={"field": "schedule.construction.date", "value": "2026-08-03"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _from_to(order_id) == [("2026-07-20", "2026-08-03")]


# --------------------------------------------------------------------------- #
# 3. 품목별 시공일 인라인 패치 (실제 라우트 — erp_inline_patch.apply_field_patch 경유)
# --------------------------------------------------------------------------- #
def test_item_construction_date_inline_patch_emits_event(client, inline_enabled):
    """PATCH items.<n>.construction_date → 이벤트 1건(출고 대시보드가 쓰는 값)."""
    _login(client, _make_user("cde_item", role="ADMIN"))
    order_id = _make_order(
        sd=_erp_sd("2026-07-20", items=[{"product_name": "붙박이장", "construction_date": "2026-07-22"}])
    ).id

    resp = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        json={"field": "items.0.construction_date", "value": "2026-07-30"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _from_to(order_id) == [("2026-07-20,2026-07-22", "2026-07-20,2026-07-30")]


# --------------------------------------------------------------------------- #
# 4. POST /api/update_order_field (scheduled_date 빠른수정 — 실제 라우트)
# --------------------------------------------------------------------------- #
def test_update_order_field_scheduled_date_emits_single_event(client):
    """빠른수정 scheduled_date → 이벤트 정확히 1건(구 emit 제거 후에도 유실 0·중복 0)."""
    user = _make_user("cde_field", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order(sd=_erp_sd("2026-07-20", stage="생산"), stage="생산").id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "scheduled_date", "value": "2026-07-28"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True

    events = _events(order_id)
    assert len(events) == 1
    assert (events[0].payload["from"], events[0].payload["to"]) == ("2026-07-20", "2026-07-28")
    assert events[0].created_by_user_id == user_id


# --------------------------------------------------------------------------- #
# 5. 시공불가 재예약 (실제 라우트 — api_construction_fail)
# --------------------------------------------------------------------------- #
def test_construction_fail_reschedule_emits_event(client):
    """시공불가 재예약(가장 무거운 시공일 이동)도 이벤트를 남긴다 — 종전 완전 무음."""
    _login(client, _make_user("cde_fail", role="STAFF", team="CONSTRUCTION"))
    order_id = _make_order(
        sd=_erp_sd("2026-07-20", stage="CONSTRUCTION"),
        status="CONSTRUCTION",
        stage="CONSTRUCTION",
    ).id

    resp = client.post(
        f"/api/orders/{order_id}/construction/fail",
        json={"reason": "site_issue", "detail": "현장 재방문", "reschedule_date": "2026-08-05"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _from_to(order_id) == [("2026-07-20", "2026-08-05")]


# --------------------------------------------------------------------------- #
# 6. 레거시 편집 폼 (실제 라우트 — foms/web/orders/edit.py)
# --------------------------------------------------------------------------- #
def test_legacy_edit_form_emits_event(client):
    """레거시 주문수정 폼(POST /edit/<id>) 시공일 변경 → 이벤트 1건."""
    _login(client, _make_user("cde_legacy", role="ADMIN", team="CS"))
    order_id = _make_order(sd=_erp_sd("2026-07-20"), scheduled_date="2026-07-20").id

    resp = client.post(
        f"/edit/{order_id}",
        data={
            "received_date": "2026-07-01",
            "customer_name": "시공일 고객",
            "phone": "010-1234-5678",
            "address": "서울 테헤란로 123",
            "product": "붙박이장",
            "status": "RECEIVED",
            "manager_name": "담당",
            "scheduled_date": "2026-08-11",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]
    assert _from_to(order_id) == [("2026-07-20", "2026-08-11")]


# --------------------------------------------------------------------------- #
# 8. 허위 이벤트 0 (negative cases)
# --------------------------------------------------------------------------- #
def test_unchanged_save_emits_no_event(client):
    """같은 시공일로 다시 저장하면 이벤트 0건."""
    _login(client, _make_user("cde_same", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd("2026-07-20")).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd("2026-07-20")},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id) == []


def test_format_only_difference_emits_no_event(client):
    """`2026-07-20` → `2026/07/20` 은 같은 날짜다 — 이벤트 0건(구 emit 의 허위양성 정정)."""
    _login(client, _make_user("cde_fmt", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd("2026-07-20")).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd("2026/07/20")},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id) == []


def test_field_update_format_only_difference_emits_no_event(client):
    """빠른수정도 표기만 다르면 이벤트 0건(raw 비교였던 구 emit 과 대비)."""
    _login(client, _make_user("cde_fmt2", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd("2026-07-20", stage="생산"), stage="생산").id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "scheduled_date", "value": "2026/07/20"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id) == []


def test_multi_value_reorder_emits_no_event(client):
    """다중 시공일의 순서만 바뀐 저장은 이벤트 0건(집합 + 안정 정렬 비교)."""
    _login(client, _make_user("cde_order", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd("2026-07-20,2026-07-28")).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd("2026-07-28,2026-07-20")},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id) == []


def test_order_creation_emits_no_event(app):
    """주문 생성은 '이전 값'이 없으므로 이벤트 0건."""
    order_id = _make_order(sd=_erp_sd("2026-07-20")).id
    assert _events(order_id) == []


def test_legacy_column_write_outside_request_has_no_actor(app):
    """요청 컨텍스트 밖(스크립트·워커·백필) 쓰기도 죽지 않고 actor 는 None."""
    order = _make_order(sd=None, is_erp_order=False, scheduled_date="2026-07-20")
    order_id = order.id

    order.scheduled_date = "2026-09-09"
    db_session.commit()

    events = _events(order_id)
    assert len(events) == 1
    assert (events[0].payload["from"], events[0].payload["to"]) == ("2026-07-20", "2026-09-09")
    assert events[0].payload["source"] == "system"
    assert events[0].created_by_user_id is None
