"""per-order 출고 설정 writer 계약 테스트 (SHIPMENT-WRITER-01, sqlite domains lane).

``api_erp_shipment_update`` canonical화(UPDATE_SHIPMENT_SETTINGS)를 고정한다:

* exact non-assignment schema(site_extra/construction_time/vehicle/trip)만 저장하고,
  site_extra color 는 고정 enum 으로 정규화한다(임의 색은 persist 하지 않음 = 거부).
* ``construction_workers`` 등 assignment/crew 이름 배열은 저장하지 않는다(name-array
  direct write 거부 — crew IDs via command).
* If-Match(settings_version) stale → 409(blind overwrite 방지), version bump + receipt.

PG DSN 불필요(sqlite ``client``/``db_session``). pure normalizer 는 함수 단위로도 고정.
"""
from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User
from foms.services.shipment.writer import (
    DEFAULT_SITE_EXTRA_COLOR,
    SITE_EXTRA_COLORS,
    SITE_EXTRA_MAX,
    apply_shipment_settings,
    build_shipment_settings_patch,
)


# --------------------------------------------------------------------------- #
# pure normalizer 계약(session 불필요)
# --------------------------------------------------------------------------- #
def test_patch_keeps_only_exact_non_assignment_keys() -> None:
    patch = build_shipment_settings_patch(
        {
            "site_extra": [], "construction_time": "  오전 10시 ", "vehicle": "1톤",
            "trip": "왕복", "construction_workers": ["철수", "영희"],
            "drawing_managers": ["김도면"], "measurement_manager": ["박실측"],
            "unknown_field": "x",
        }
    )
    assert set(patch.keys()) == {"site_extra", "construction_time", "vehicle", "trip"}
    assert patch["construction_time"] == "오전 10시"  # trim


def test_site_extra_color_coerced_to_enum() -> None:
    patch = build_shipment_settings_patch(
        {"site_extra": [{"text": "정문 앞 하차", "color": "#334155"},
                        {"text": "노랑", "color": "orange"},
                        {"text": "빈색", "color": ""}]}
    )
    assert patch["site_extra"] == [
        {"text": "정문 앞 하차", "color": DEFAULT_SITE_EXTRA_COLOR},  # hex → 기본색
        {"text": "노랑", "color": "orange"},  # enum 통과
        {"text": "빈색", "color": DEFAULT_SITE_EXTRA_COLOR},
    ]
    assert all(item["color"] in SITE_EXTRA_COLORS for item in patch["site_extra"])


def test_site_extra_cap_and_plain_strings() -> None:
    raw = [f"메모{i}" for i in range(SITE_EXTRA_MAX + 5)]
    patch = build_shipment_settings_patch({"site_extra": raw})
    assert len(patch["site_extra"]) == SITE_EXTRA_MAX
    assert patch["site_extra"][0] == {"text": "메모0", "color": DEFAULT_SITE_EXTRA_COLOR}


def test_apply_preserves_existing_crew_projection() -> None:
    sd = {"shipment": {"construction_workers": ["기존작업자"], "vehicle": "old"}}
    out = apply_shipment_settings(sd, {"vehicle": "1톤", "construction_workers": ["새이름배열"]})
    assert out["shipment"]["vehicle"] == "1톤"
    # name-array direct write 거부: construction_workers 는 그대로 보존(덮어쓰지 않음)
    assert out["shipment"]["construction_workers"] == ["기존작업자"]
    assert sd["shipment"]["vehicle"] == "old"  # 원본 미변경(deepcopy)


# --------------------------------------------------------------------------- #
# endpoint 계약(sqlite client)
# --------------------------------------------------------------------------- #
def _login_cs_staff(client, username: str) -> User:
    user = User(
        username=username, password=generate_password_hash("secret"),
        role="STAFF", team="CS", name="Shipment Writer", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_order() -> Order:
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today, customer_name="출고 설정 대상", phone="010-2222-3333",
        address="Seoul", product="장", status="IN_CONSTRUCTION", is_erp_order=True,
        structured_data={"shipment": {"construction_workers": ["기존작업자"]}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_update_writes_exact_schema_and_bumps_version(client) -> None:
    _login_cs_staff(client, "shipment-writer-ok")
    order = _make_order()
    oid, base_version = order.id, order.mutation_version
    resp = client.post(
        f"/api/erp/shipment/update/{oid}",
        json={"construction_time": "오전 10시", "vehicle": "1톤", "trip": "왕복",
              "site_extra": [{"text": "정문 앞", "color": "#abcdef"}]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["version"] == base_version + 1
    assert data["data"]["mutation_receipt"]

    db_session.expire_all()
    sd = db_session.get(Order, oid).structured_data["shipment"]
    assert sd["construction_time"] == "오전 10시"
    assert sd["vehicle"] == "1톤"
    assert sd["site_extra"] == [{"text": "정문 앞", "color": DEFAULT_SITE_EXTRA_COLOR}]
    events = [e.event_type for e in db_session.query(OrderEvent).filter_by(order_id=oid).all()]
    assert "SHIPMENT_SETTINGS_UPDATED" in events


def test_update_refuses_name_array_construction_workers(client) -> None:
    _login_cs_staff(client, "shipment-writer-crew")
    order = _make_order()
    oid = order.id
    resp = client.post(
        f"/api/erp/shipment/update/{oid}",
        json={"construction_workers": ["침입이름1", "침입이름2"], "vehicle": "2.5톤"},
    )
    assert resp.status_code == 200
    db_session.expire_all()
    sd = db_session.get(Order, oid).structured_data["shipment"]
    assert sd["vehicle"] == "2.5톤"
    # crew IDs via SET_INSTALLATION_CREW command — name-array 는 저장되지 않음(기존 보존)
    assert sd["construction_workers"] == ["기존작업자"]


def test_update_if_match_stale_returns_409(client) -> None:
    _login_cs_staff(client, "shipment-writer-ifmatch")
    order = _make_order()
    oid = order.id
    resp = client.post(
        f"/api/erp/shipment/update/{oid}",
        json={"vehicle": "1톤", "settings_version": 999},
    )
    assert resp.status_code == 409
    assert resp.get_json()["success"] is False


def test_update_construction_team_forbidden(client) -> None:
    user = User(
        username="shipment-writer-constr", password=generate_password_hash("secret"),
        role="ADMIN", team="CONSTRUCTION", name="Constr", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    order = _make_order()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["role"] = user.role
    resp = client.post(f"/api/erp/shipment/update/{order.id}", json={"vehicle": "1톤"})
    assert resp.status_code == 403
    assert "시공팀" in resp.get_json().get("message", "")
