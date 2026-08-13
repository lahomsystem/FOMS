"""카카오 알림톡 v1 — 자동 트리거 배선 테스트 (T3).

발송 계층은 T2 에서 이미 검증했으므로 여기서는 **쓰기 경로가 커밋 후 진입점을 부르는지**
만 본다(:func:`maybe_send_measure_alimtalk` 는 모듈 네임스페이스에서 스텁). draft autosave
경로는 호출 자체가 없어야 한다(스펙 H1).
"""
import copy

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api import erp_orders_structured
from foms.services import kakao_alimtalk
from models import Order, OrderEvent, User

_SD = {
    "workflow": {"stage": "RECEIVED"},
    "parties": {
        "customer": {"name": "임다슬", "phone": "010-2473-6730"},
        "orderer": {"name": "라홈시스템"},
    },
    "items": [{"product_name": "무몰딩 여닫이"}],
    "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123"},
    "schedule": {"measurement": {"date": "2026-08-14", "time": "3시 30분"}},
}


def _sd() -> dict:
    return copy.deepcopy(_SD)


def _login_as_admin(client, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="알림톡 트리거 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_order(structured_data=None) -> Order:
    order = Order(
        received_date="2026-07-04",
        customer_name="임다슬",
        phone="010-2473-6730",
        address="서울 테헤란로 123",
        product="무몰딩 여닫이",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else _sd(),
    )
    db_session.add(order)
    db_session.commit()
    return order


@pytest.fixture
def stub_maybe_send(monkeypatch):
    """세 쓰기 경로의 진입점을 전부 스텁하고 호출 order_id 를 모은다.

    erp_orders_structured 는 모듈 상단 import(=자기 네임스페이스 바인딩), field_update 는
    함수 로컬 import(=서비스 모듈에서 매번 조회)라 두 곳을 모두 패치해야 한다.
    """
    calls: list[int] = []
    monkeypatch.setattr(
        erp_orders_structured, "maybe_send_measure_alimtalk", lambda order_id: calls.append(order_id)
    )
    monkeypatch.setattr(
        kakao_alimtalk, "maybe_send_measure_alimtalk", lambda order_id: calls.append(order_id)
    )
    return calls


@pytest.fixture
def mute_put_side_effects(monkeypatch):
    """PUT 경로의 무관한 부수효과(알림/지오코딩/draft 승격)를 끈다."""
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)


def test_put_structured_with_measure_date_triggers_send(
    client, stub_maybe_send, mute_put_side_effects
):
    """실측일이 있는 저장은 커밋 후 자동 트리거를 1회 호출한다(diff 비교 없음)."""
    _login_as_admin(client, "alimtalk-put")
    order = _create_order()
    order_id = order.id

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _sd(), "structured_schema_version": 1},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert stub_maybe_send == [order_id]


def test_put_structured_failure_does_not_trigger(
    client, stub_maybe_send, mute_put_side_effects
):
    """저장이 400 으로 막히면(커밋 없음) 트리거도 없다."""
    _login_as_admin(client, "alimtalk-put-fail")
    order = _create_order()

    blank_address = _sd()
    blank_address["site"] = {"address_full": "", "address_main": "", "address_detail": ""}
    response = client.put(
        f"/api/orders/{order.id}/structured",
        json={"structured_data": blank_address, "structured_schema_version": 1},
    )

    assert response.status_code == 400
    assert stub_maybe_send == []


def test_patch_fields_triggers(client, stub_maybe_send, monkeypatch):
    """인라인 PATCH 저장도 커밋 후 트리거를 부른다."""
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "1")
    _login_as_admin(client, "alimtalk-patch")
    order = _create_order()
    order_id = order.id

    response = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        json={"field": "schedule.measurement.date", "value": "2026-08-20"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert stub_maybe_send == [order_id]


def test_field_update_quickedit_triggers(client, stub_maybe_send):
    """대시보드 퀵에디트(measurement_date)도 커밋 후 트리거를 부른다."""
    _login_as_admin(client, "alimtalk-quickedit")
    order = _create_order()
    order_id = order.id

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "measurement_date", "value": "2026-08-20"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert stub_maybe_send == [order_id]

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert (saved.structured_data["schedule"]["measurement"]["date"]) == "2026-08-20"


def test_field_update_unrelated_field_does_not_trigger(client, stub_maybe_send):
    """실측 일정과 무관한 필드 저장은 트리거를 부르지 않는다(불필요 DB 왕복 제거)."""
    _login_as_admin(client, "alimtalk-quickedit-other")
    order = _create_order()

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "manager_name", "value": "김담당"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert stub_maybe_send == []


def test_draft_autosave_does_not_trigger(client, stub_maybe_send):
    """draft 자동저장은 호출 자체가 없어야 한다(스펙 H1)."""
    _login_as_admin(client, "alimtalk-autosave")

    response = client.post(
        "/api/orders/erp/draft/autosave",
        json={"draft_token": "alimtalk-draft-token", "structured_data": _sd()},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["order_id"] is not None
    assert stub_maybe_send == []


def test_measurement_time_change_records_event(
    client, stub_maybe_send, mute_put_side_effects
):
    """실측 '시간'만 바뀌어도 타임라인 이벤트가 남는다(신설 비교)."""
    _login_as_admin(client, "alimtalk-time-event")
    order = _create_order()
    order_id = order.id

    changed = _sd()
    changed["schedule"]["measurement"]["time"] = "5시"
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": changed, "structured_schema_version": 1},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    db_session.expire_all()
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "MEASUREMENT_TIME_CHANGED")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload == {"from": "3시 30분", "to": "5시"}


def test_measurement_time_unchanged_records_no_event(
    client, stub_maybe_send, mute_put_side_effects
):
    """시간이 그대로면 이벤트를 남기지 않는다(저장마다 도배 금지)."""
    _login_as_admin(client, "alimtalk-time-noop")
    order = _create_order()
    order_id = order.id

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _sd(), "structured_schema_version": 1},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    db_session.expire_all()
    assert (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "MEASUREMENT_TIME_CHANGED")
        .count()
        == 0
    )


def test_measurement_time_label_is_registered():
    """타임라인 라벨 맵에 신규 이벤트가 등재돼 '기타 변경' 으로 떨어지지 않는다."""
    from foms.services.order_event_display import translate_event_type_to_korean

    assert translate_event_type_to_korean("MEASUREMENT_TIME_CHANGED") == "실측 시간 변경"
