"""출고 시공일 변경 확인(ack) API 계약 (POST /api/orders/<id>/shipment/change-ack — T3).

여기서 고정하는 계약:

* 미인증 401 · 시공팀 403 — 둘 다 JSON(redirect 0)이고 이벤트를 남기지 않는다.
* 성공 시 **Order 불변** + ``OrderEvent(SHIPMENT_CHANGE_ACK)`` **정확히 1건**.
* 응답에 in-place DOM 갱신용 ``remaining``(=0)·``banner_count_hint``(미확인이 있었으면 -1)
  가 실린다.
* 같은 ``Idempotency-Key`` 재요청은 event 를 더 만들지 않고 저장 응답을 replay 한다.
* ack 는 **개인별** — A 가 확인해도 B 의 alerts 는 그대로다.
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.shipment_change_alerts import collect_shipment_change_alerts
from models import Order, OrderEvent, User

_T0 = datetime.datetime(2026, 7, 1, 0, 0, 0)
_CHANGE = "CONSTRUCTION_DATE_CHANGED"
_ACK = "SHIPMENT_CHANGE_ACK"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_user(username: str, *, role: str = "STAFF", team: str = "SHIPMENT") -> User:
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


def _creds(user: User) -> tuple[int, str, str]:
    """세션 로그인용 primitive (id, username, role) — 요청 후 detach 대비 즉시 캡처."""
    return (user.id, user.username, user.role)


def _login(client, user_or_creds) -> None:
    """테스트 클라이언트 세션에 로그인 상태를 심는다(User 또는 :func:`_creds` 튜플)."""
    uid, username, role = (
        user_or_creds if isinstance(user_or_creds, tuple) else _creds(user_or_creds)
    )
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role


def _make_order(customer_name: str = "출고 고객") -> Order:
    """출고 대상 주문 1건 생성(커밋 포함)."""
    order = Order(
        received_date="2026-07-01",
        customer_name=customer_name,
        phone="010-5555-6666",
        address="서울 출고로 2",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="담당",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "SHIPMENT"},
            "parties": {"customer": {"name": customer_name}},
            "schedule": {"construction": {"date": "2026-07-20"}},
        },
        erp_stage_code="SHIPMENT",
    )
    db_session.add(order)
    db_session.commit()
    return order


def _seed_change(order_id: int, days: int = 2) -> None:
    """시공일 변경 이벤트 1건을 과거 시각으로 심는다(ack 대상)."""
    db_session.add(
        OrderEvent(
            order_id=order_id,
            event_type=_CHANGE,
            payload={"from": "2026-07-20", "to": "2026-07-28", "source": "test"},
            created_at=_T0 + datetime.timedelta(days=days),
        )
    )
    db_session.commit()


def _ack_events(order_id: int) -> list[OrderEvent]:
    """해당 주문의 ack 이벤트 목록(생성순)."""
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == _ACK)
        .order_by(OrderEvent.id.asc())
        .all()
    )


def _alerts(order: Order, user_id: int) -> list[dict]:
    """서비스가 보는 이 사용자의 미확인 목록."""
    db_session.expire_all()
    return collect_shipment_change_alerts(db_session, [order], user_id)[order.id]["alerts"]


def _url(order_id: int) -> str:
    return f"/api/orders/{order_id}/shipment/change-ack"


# --------------------------------------------------------------------------- #
# 1. 권한
# --------------------------------------------------------------------------- #
def test_unauthenticated_rejected(client):
    """비로그인 → 401 JSON, 이벤트 0건(redirect 아님)."""
    order_id = _make_order().id
    _seed_change(order_id)

    resp = client.post(_url(order_id), json={})

    assert resp.status_code == 401, resp.get_data(as_text=True)
    assert resp.is_json
    assert resp.get_json()["success"] is False
    assert "Location" not in resp.headers
    assert _ack_events(order_id) == []


def test_construction_team_rejected(client):
    """시공팀 → 403 JSON, 이벤트 0건(출고 데이터 수정 금지 규칙 재사용)."""
    _login(client, _make_user("ack_construction", team="CONSTRUCTION"))
    order_id = _make_order().id
    _seed_change(order_id)

    resp = client.post(_url(order_id), json={})

    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is False
    assert _ack_events(order_id) == []


def test_viewer_rejected(client):
    """조회 전용 계정 → 403 JSON, 이벤트 0건(SHIPMENT_EDIT hard deny)."""
    _login(client, _make_user("ack_viewer", role="VIEWER", team="SHIPMENT"))
    order_id = _make_order().id
    _seed_change(order_id)

    resp = client.post(_url(order_id), json={})

    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert _ack_events(order_id) == []


def test_missing_order_returns_404(client):
    """없는 주문 → 404 JSON."""
    _login(client, _make_user("ack_404"))

    resp = client.post(_url(99999999), json={})

    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


# --------------------------------------------------------------------------- #
# 2. 성공 — 이벤트 1건 + in-place 갱신용 응답
# --------------------------------------------------------------------------- #
def test_ack_writes_exactly_one_event_and_leaves_order_untouched(client):
    """ack 1회 → SHIPMENT_CHANGE_ACK 1건, Order(structured_data·version) 무변경."""
    user = _make_user("ack_ok")
    user_id = user.id
    _login(client, user)
    order = _make_order()
    order_id = order.id
    before_sd = dict(order.structured_data or {})
    before_version = getattr(order, "mutation_version", None)
    _seed_change(order_id)

    resp = client.post(_url(order_id), json={})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    assert body["remaining"] == 0
    assert body["banner_count_hint"] == -1  # 배너 카운트 1 감소
    assert body["data"] == {
        "order_id": order_id,
        "cleared": 1,
        "remaining": 0,
        "banner_count_hint": -1,
    }

    events = _ack_events(order_id)
    assert len(events) == 1
    assert events[0].created_by_user_id == user_id
    assert events[0].payload["source"] == "shipment_dashboard"

    saved = db_session.get(Order, order_id)
    assert dict(saved.structured_data or {}) == before_sd
    assert getattr(saved, "mutation_version", None) == before_version
    assert _alerts(saved, user_id) == []  # 내 화면에서 사라진다


def test_ack_without_pending_change_reports_zero_delta(client):
    """미확인 변경이 없으면 banner_count_hint 0(배너 카운트 그대로)."""
    user = _make_user("ack_nochange")
    _login(client, user)
    order_id = _make_order().id

    resp = client.post(_url(order_id), json={})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert (body["remaining"], body["banner_count_hint"], body["data"]["cleared"]) == (0, 0, 0)
    assert len(_ack_events(order_id)) == 1


# --------------------------------------------------------------------------- #
# 3. 멱등
# --------------------------------------------------------------------------- #
def test_second_ack_with_same_key_is_replayed(client):
    """같은 Idempotency-Key 재요청 → 이벤트 추가 0, 저장 응답 replay."""
    user = _make_user("ack_idem")
    _login(client, user)
    order_id = _make_order().id
    _seed_change(order_id)
    headers = {"Idempotency-Key": "ship-ack-key-1"}

    first = client.post(_url(order_id), json={}, headers=headers)
    second = client.post(_url(order_id), json={}, headers=headers)

    assert first.status_code == 200, first.get_data(as_text=True)
    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json() == first.get_json()
    assert len(_ack_events(order_id)) == 1


def test_repeated_ack_without_key_is_safe(client):
    """key 없는 연속 ack 는 오류 없이 수렴한다(추가 기록은 남되 상태는 동일)."""
    user = _make_user("ack_repeat")
    user_id = user.id
    _login(client, user)
    order = _make_order()
    order_id = order.id
    _seed_change(order_id)

    first = client.post(_url(order_id), json={})
    second = client.post(_url(order_id), json={})

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.get_json()["data"]["cleared"] == 1
    assert second.get_json()["data"]["cleared"] == 0  # 이미 확인 완료 → 지울 게 없다
    assert second.get_json()["banner_count_hint"] == 0
    assert len(_ack_events(order_id)) == 2  # 선례와 동일: key 없으면 dedupe 안 함
    assert _alerts(db_session.get(Order, order_id), user_id) == []


# --------------------------------------------------------------------------- #
# 4. 개인별 — A 의 ack 는 B 를 조용하게 만들지 않는다
# --------------------------------------------------------------------------- #
def test_ack_by_user_a_does_not_clear_user_b(client):
    """A 가 확인해도 B 의 alerts 는 그대로 남는다."""
    user_a = _make_user("ack_user_a")
    user_b = _make_user("ack_user_b")
    a_id, b_id = user_a.id, user_b.id
    b_creds = _creds(user_b)
    _login(client, user_a)
    order = _make_order()
    order_id = order.id
    _seed_change(order_id)

    resp = client.post(_url(order_id), json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    saved = db_session.get(Order, order_id)
    assert _alerts(saved, a_id) == []
    assert len(_alerts(saved, b_id)) == 1  # B 는 아직 시끄럽다

    # B 도 확인하면 B 만 조용해지고 이벤트는 사용자별로 1건씩 쌓인다.
    _login(client, b_creds)
    assert client.post(_url(order_id), json={}).status_code == 200
    assert _alerts(db_session.get(Order, order_id), b_id) == []
    assert {e.created_by_user_id for e in _ack_events(order_id)} == {a_id, b_id}
