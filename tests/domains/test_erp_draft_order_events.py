"""ERP 주력 생성 경로의 생성 이력 계약 (T3).

ERP '새 주문'(draft POST → 자동저장 → 전체저장 승격)은 ``create_order()`` 를 경유하지
않아 운영 대부분 주문에 "누가 이 주문을 만들었나" 기록이 **0건**이었다. 여기서 고정하는
계약:

* draft 행이 **처음 만들어질 때**(``POST /api/orders/erp/draft`` · 자동저장이 만드는
  ``_create_session_draft``) ``ORDER_DRAFT_CREATED`` 1건 — actor 포함.
* **기존 draft 재저장(자동저장)은 이벤트 0건** — 초안은 수십 번 갱신되므로 생성 시점만
  기록한다(설계 결정 ②).
* draft → 실주문 **승격 시** ``ORDER_CREATED`` 1건(payload ``via="erp_draft"``, actor).
  전체 시나리오(생성 → 자동저장 N회 → 승격) = ``ORDER_DRAFT_CREATED`` 1 + ``ORDER_CREATED`` 1.
* 레거시 ``create_order()`` 경로(주문 추가 폼)와 **중복 0** — 그 경로는 erp draft 를 거치지
  않고, 이미 ``ORDER_CREATED`` 가 있는 주문이 승격 판정을 통과해도 2건이 되지 않는다.
* 타임라인 라벨: ``ORDER_DRAFT_CREATED`` · ``ORDER_CREATED`` 한글 라벨 반환.
* 금액 SSOT(T2) 상호작용: draft 생성·자동저장·승격 전 구간에서 ``PAYMENT_CHANGED`` 0건.
"""

from __future__ import annotations

from typing import Any

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User

_DRAFT_CREATED = "ORDER_DRAFT_CREATED"
_CREATED = "ORDER_CREATED"
_PAYMENT_CHANGED = "PAYMENT_CHANGED"


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


def _erp_sd(**extra: Any) -> dict:
    """필수값(고객/전화/주소/제품명)을 갖춘 최소 ERP structured_data."""
    sd: dict[str, Any] = {
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "생성이력 고객", "phone": "010-2222-3333"}},
        "site": {"address_full": "서울 역삼로 45", "address_main": "서울 역삼로 45"},
        "items": [{"product_name": "붙박이장", "price": 1000000}],
        "schedule": {},
        "shipment": {},
    }
    sd.update(extra)
    return sd


def _events(order_id: int, event_type: str) -> list[OrderEvent]:
    """해당 주문의 이벤트를 생성순으로 반환."""
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .order_by(OrderEvent.id.asc())
        .all()
    )


def _create_draft(client, token: str) -> int:
    """POST /api/orders/erp/draft 로 draft 를 만들고 order_id 를 돌려준다."""
    resp = client.post("/api/orders/erp/draft", json={"draft_token": token})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["reused"] is False
    return int(body["order_id"])


def _autosave(client, token: str, **sd_extra: Any):
    """자동저장 라우트 1회 호출."""
    return client.post(
        "/api/orders/erp/draft/autosave",
        json={"draft_token": token, "structured_data": _erp_sd(**sd_extra)},
    )


# --------------------------------------------------------------------------- #
# 1. draft 생성 — POST /api/orders/erp/draft
# --------------------------------------------------------------------------- #
def test_draft_post_emits_single_draft_created_event(client):
    """draft POST 1회 → ``ORDER_DRAFT_CREATED`` 정확히 1건(actor 기록)."""
    user = _make_user("t3_draft_post", role="ADMIN")
    user_id = user.id
    _login(client, user)

    order_id = _create_draft(client, "t3-draft-post")

    events = _events(order_id, _DRAFT_CREATED)
    assert len(events) == 1
    assert events[0].created_by_user_id == user_id
    assert events[0].payload["via"] == "erp_draft"
    assert events[0].payload["created_via"] == "ADD_ORDER"
    # 아직 승격 전이므로 생성 이벤트는 없다.
    assert _events(order_id, _CREATED) == []


def test_draft_post_reuse_emits_no_additional_event(client):
    """같은 세션이 draft POST 를 다시 불러 기존 draft 를 재사용하면 이벤트 0건 추가."""
    _login(client, _make_user("t3_draft_reuse", role="ADMIN"))
    order_id = _create_draft(client, "t3-draft-reuse")

    again = client.post("/api/orders/erp/draft", json={"draft_token": "t3-draft-reuse"})
    assert again.status_code == 200, again.get_data(as_text=True)
    assert again.get_json()["reused"] is True

    assert len(_events(order_id, _DRAFT_CREATED)) == 1


# --------------------------------------------------------------------------- #
# 2. 자동저장이 만드는 draft (_create_session_draft 경유)
# --------------------------------------------------------------------------- #
def test_autosave_created_draft_emits_single_draft_created_event(client):
    """draft POST 없이 자동저장이 draft 를 만들어도 ``ORDER_DRAFT_CREATED`` 1건."""
    user = _make_user("t3_autosave_create", role="ADMIN")
    user_id = user.id
    _login(client, user)

    resp = _autosave(client, "t3-autosave-create")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    order_id = resp.get_json()["order_id"]
    assert order_id is not None

    events = _events(order_id, _DRAFT_CREATED)
    assert len(events) == 1
    assert events[0].created_by_user_id == user_id
    assert events[0].payload["created_via"] == "ADD_ORDER_AUTOSAVE"
    assert _events(order_id, _CREATED) == []


# --------------------------------------------------------------------------- #
# 3. 기존 draft 재저장 — 이벤트 0건 추가
# --------------------------------------------------------------------------- #
def test_repeated_autosave_emits_no_additional_event(client):
    """같은 draft 를 3회 자동저장해도 이벤트는 생성 시점 1건 그대로다."""
    _login(client, _make_user("t3_autosave_repeat", role="ADMIN"))
    order_id = _create_draft(client, "t3-autosave-repeat")

    for index in range(3):
        resp = _autosave(
            client,
            "t3-autosave-repeat",
            notes_marker=f"자동저장 {index}",
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["order_id"] == order_id

    assert len(_events(order_id, _DRAFT_CREATED)) == 1
    assert _events(order_id, _CREATED) == []


# --------------------------------------------------------------------------- #
# 4. 승격 — ORDER_CREATED 1건 / 전 시나리오 DRAFT 1 + CREATED 1
# --------------------------------------------------------------------------- #
def test_draft_promotion_emits_single_order_created_event(client):
    """전체 시나리오(생성 → 자동저장 3회 → 승격) = DRAFT 1 + CREATED 1 정확히."""
    user = _make_user("t3_promote", role="ADMIN")
    user_id = user.id
    _login(client, user)

    order_id = _create_draft(client, "t3-promote")
    for _ in range(3):
        assert _autosave(client, "t3-promote").status_code == 200

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd()},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["draft_cleared"] is True

    draft_events = _events(order_id, _DRAFT_CREATED)
    created_events = _events(order_id, _CREATED)
    assert len(draft_events) == 1
    assert len(created_events) == 1
    assert created_events[0].payload["via"] == "erp_draft"
    assert created_events[0].payload["status"] == "RECEIVED"
    assert created_events[0].created_by_user_id == user_id

    # 승격이 실제로 일어났는지(draft 해제) 확인 — 이벤트만 남고 상태가 그대로면 무의미하다.
    db_session.expire_all()
    order = db_session.query(Order).filter(Order.id == order_id).one()
    assert (order.structured_data or {}).get("meta", {}).get("draft") is False
    assert order.status == "RECEIVED"


def test_second_save_after_promotion_emits_no_additional_created_event(client):
    """승격 후 재저장(일반 수정)은 ``ORDER_CREATED`` 를 더 남기지 않는다."""
    _login(client, _make_user("t3_resave", role="ADMIN"))
    order_id = _create_draft(client, "t3-resave")

    for _ in range(2):
        resp = client.put(
            f"/api/orders/{order_id}/structured",
            json={"structured_data": _erp_sd()},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

    assert len(_events(order_id, _CREATED)) == 1
    assert len(_events(order_id, _DRAFT_CREATED)) == 1


# --------------------------------------------------------------------------- #
# 5. 레거시 create_order 경로와 중복 0
# --------------------------------------------------------------------------- #
def test_legacy_add_form_emits_one_created_event_without_draft_event(client):
    """레거시 주문 추가 폼은 ``create_order()`` 경유 — CREATED 1 · DRAFT 0.

    이 경로는 erp draft 를 만들지 않으므로 T3 배선과 겹치지 않는다(중복 이벤트 0).
    """
    _login(client, _make_user("t3_legacy_form", role="STAFF", team="SALES"))

    resp = client.post(
        "/add",
        data={
            "create_mode": "LEGACY",
            "received_date": "2026-08-05",
            "received_time": "10:00",
            "customer_name": "레거시 고객",
            "phone": "010-4444-5555",
            "address": "서울 강남대로 1",
            "product": "레거시 제품",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (301, 302), resp.get_data(as_text=True)

    order = (
        db_session.query(Order)
        .filter(Order.customer_name == "레거시 고객")
        .order_by(Order.id.desc())
        .first()
    )
    assert order is not None

    created_events = _events(order.id, _CREATED)
    assert len(created_events) == 1
    # create_order 정본 payload — erp draft 표기가 붙지 않는다.
    assert "via" not in (created_events[0].payload or {})
    assert _events(order.id, _DRAFT_CREATED) == []


def test_promotion_does_not_duplicate_existing_created_event(client):
    """이미 ``ORDER_CREATED`` 가 있는 주문이 승격 판정을 통과해도 2건이 되지 않는다."""
    _login(client, _make_user("t3_dedupe", role="ADMIN"))

    order = Order(
        received_date="2026-08-05",
        customer_name="중복방지 고객",
        phone="010-6666-7777",
        address="서울 테헤란로 99",
        product="붙박이장",
        status="DRAFT",
        is_erp_order=True,
        structured_data=_erp_sd(meta={"draft": True}),
        erp_stage_code="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id
    # 레거시 경로가 이미 남긴 생성 이벤트를 모사한다.
    db_session.add(
        OrderEvent(
            order_id=order_id,
            event_type=_CREATED,
            payload={"owner_user_id": 1, "status": "RECEIVED"},
        )
    )
    db_session.commit()

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd()},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    created_events = _events(order_id, _CREATED)
    assert len(created_events) == 1
    assert created_events[0].payload.get("owner_user_id") == 1


# --------------------------------------------------------------------------- #
# 6. 라벨 노출
# --------------------------------------------------------------------------- #
def test_event_types_render_korean_labels() -> None:
    """무필터 소비자가 "기타 변경"으로 떨어지지 않도록 한글 라벨을 등록한다."""
    from foms.services.order_event_display import (
        generate_change_description,
        translate_event_type_to_korean,
    )

    assert translate_event_type_to_korean(_DRAFT_CREATED) == "임시 주문 생성"
    assert translate_event_type_to_korean(_CREATED) == "주문 생성"
    assert generate_change_description(
        _DRAFT_CREATED, "", "", "", {"via": "erp_draft"}
    ) == "임시 주문(초안)을 생성했습니다"
    assert generate_change_description(
        _CREATED, "", "", "", {"via": "erp_draft"}
    ) == "주문을 생성했습니다"


# --------------------------------------------------------------------------- #
# 7. 금액 SSOT(T2) 상호작용 — 전 구간 PAYMENT_CHANGED 0건
# --------------------------------------------------------------------------- #
def test_draft_lifecycle_emits_no_payment_changed_event(client):
    """draft 생성·자동저장·승격 어디에서도 금액 이벤트는 남지 않는다.

    draft 구간은 ``order_payment_sync`` 가 억제하고(승격 시점 값이 초기값), T3 이벤트가
    그 억제를 깨지 않는다는 것이 이 테스트의 요점이다.
    """
    _login(client, _make_user("t3_payment_mix", role="ADMIN"))
    order_id = _create_draft(client, "t3-payment-mix")

    for deposit in (100000, 250000):
        resp = _autosave(client, "t3-payment-mix", payment={"deposit": deposit})
        assert resp.status_code == 200, resp.get_data(as_text=True)

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd(payment={"deposit": 250000})},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    assert _events(order_id, _PAYMENT_CHANGED) == []
    assert len(_events(order_id, _DRAFT_CREATED)) == 1
    assert len(_events(order_id, _CREATED)) == 1
