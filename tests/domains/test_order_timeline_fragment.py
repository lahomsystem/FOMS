"""C5: 주문 360° 타임라인 fragment 계약 테스트 (읽기 전용).

- 로그인 사용자는 유효 ERP 주문의 8단계 타임라인 fragment(200)를 받는다.
- 비로그인은 login_required로 로그인 리다이렉트(302).
- 존재하지 않는/비-ERP 주문은 404.
- 순수 빌더 build_order_timeline은 현재 단계 기준 done/current/pending을 채운다.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.order_timeline_v3 import STAGE_SEQUENCE, build_order_timeline
from models import Order, OrderEvent, User

_BASE = datetime.datetime(2026, 6, 1, 9, 0, 0)


def _login_admin(client) -> User:
    user = User(
        username="c5_timeline_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="C5 Timeline Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed_order(stage: str = "CONSTRUCTION", *, is_erp: bool = True) -> int:
    order = Order(
        received_date="2026-06-01",
        customer_name="타임라인고객",
        phone="010-1234-5678",
        address="서울시 성동구 1",
        product="붙박이장",
        status=stage,
        is_erp_order=is_erp,
        erp_stage_code=stage if is_erp else None,
        structured_data={
            "workflow": {"stage": stage},
            "parties": {"customer": {"name": "타임라인고객"}},
            "schedule": {
                "measurement": {"date": "2026-06-10"},
                "construction": {"date": "2026-06-28"},
            },
            "drawing_transfer_history": [{"round": 1}, {"round": 2}],
        },
    )
    db_session.add(order)
    db_session.flush()
    for i, to_stage in enumerate(["MEASURE", "DRAWING", "CONFIRM", "PRODUCTION", "CONSTRUCTION"]):
        db_session.add(
            OrderEvent(
                order_id=order.id,
                event_type="STAGE_CHANGED",
                payload={"to": to_stage},
                created_at=_BASE + datetime.timedelta(days=i + 1),
            )
        )
    db_session.commit()
    return order.id


def test_timeline_fragment_ok_for_logged_in(client) -> None:
    """로그인 사용자는 200 + 8단계 타임라인 마크업을 받는다."""
    _login_admin(client)
    order_id = _seed_order("CONSTRUCTION")

    res = client.get(f"/api/foms/fragment/order/{order_id}/timeline")

    assert res.status_code == 200
    assert res.headers.get("X-FOMS-Fragment") == "1"
    assert res.headers.get("Cache-Control") == "no-store"
    body = res.get_data(as_text=True)
    assert "fos-timeline" in body
    assert "실측" in body and "시공" in body and "완료" in body
    # 현재 단계(CONSTRUCTION)는 is-current, 이전 단계는 is-done.
    assert "is-current" in body
    assert "is-done" in body
    # 산출물 파생: 실측일 / 시공일 / 도면 전달 이력 수.
    assert "실측일 2026-06-10" in body
    assert "도면 전달 2회" in body


def test_timeline_fragment_requires_login(client) -> None:
    """비로그인은 login_required로 로그인 화면으로 리다이렉트(302)."""
    order_id = _seed_order("MEASURE")

    res = client.get(f"/api/foms/fragment/order/{order_id}/timeline")

    assert res.status_code == 302
    assert "/login" in res.headers.get("Location", "")


def test_timeline_fragment_404_for_missing(client) -> None:
    """존재하지 않는 주문은 404."""
    _login_admin(client)

    res = client.get("/api/foms/fragment/order/99999999/timeline")

    assert res.status_code == 404


def test_timeline_fragment_404_for_non_erp(client) -> None:
    """ERP 주문이 아니면 404(표시 대상 아님)."""
    _login_admin(client)
    order_id = _seed_order("RECEIVED", is_erp=False)

    res = client.get(f"/api/foms/fragment/order/{order_id}/timeline")

    assert res.status_code == 404


def test_build_order_timeline_states() -> None:
    """빌더는 현재 단계 기준으로 done/current/pending을 정확히 채운다."""
    order = SimpleNamespace(
        id=1,
        status="DRAWING",
        received_date="2026-06-01",
        customer_name="X",
        structured_data={"workflow": {"stage": "DRAWING"}},
    )
    result = build_order_timeline(order, [], {})

    assert len(result["stages"]) == len(STAGE_SEQUENCE) == 8
    assert result["current_code"] == "DRAWING"
    states = {s["code"]: s["state"] for s in result["stages"]}
    assert states["RECEIVED"] == "done"
    assert states["MEASURE"] == "done"
    assert states["DRAWING"] == "current"
    assert states["CONFIRM"] == "pending"
    assert states["COMPLETED"] == "pending"
