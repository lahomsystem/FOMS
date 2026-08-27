"""AUDIT-GAP-01 후속: 출고 대시보드·수납장 저장의 **유령 원장 행** 창을 닫는다.

두 화면(``/api/erp/shipment/update/<id>``, ``/api/storage_dashboard/order/<id>/field``)은
원장 쓰기를 ``execute_order_mutation`` 이 **반환한 뒤**(바깥)에서 했다. 정상 replay 는
``captured`` 패턴 덕에 안전했지만, receipt insert 의 **IntegrityError backstop** 은 다르다:
그 경로는 ``mutation`` 을 **이미 실행한 뒤** ``session.rollback()`` 하고 replay 를 반환한다
(``revision.py`` 의 ``session.add(receipt)`` → ``flush()`` except 블록). 그러면 값 변경은
롤백됐는데 바깥의 원장 쓰기 + ``db.commit()`` 은 그대로 살아남아 **컬럼은 안 바뀌었는데
원장 행만 남는다.** 감사 화면에서는 "누가 배송비를 바꿨다"로 읽히지만 실제 금액은 그대로다.

수정은 ``foms/api/orders/regional.py`` 가 이미 택한 방식과 같다 — 원장 쓰기를 ``_mutate``
**안**으로 옮겨 값 변경과 운명을 같이하게 한다(같은 tx·FOR UPDATE 락 안이라 rollback 이
원장 행도 함께 지운다).

여기서 고정하는 것.

* **유령 행 0**: backstop rollback 경로에서 컬럼이 안 바뀌면 원장 행도 없다.
* **회귀 방지**: 값이 바뀌면 여전히 행이 생기고, 무변경이면 여전히 0행이다.
* **조인 키는 무조건**: 감사 헤더 ``detail['change_set']`` 은 **무변경 저장에서도** 있다.
  헤더만 있고 행이 0인 상태는 "변경 없음"을 뜻하는 정상 상태이고, 조인 키가 늘 있어야
  감사 화면에서 원장으로 넘어가는 길이 항상 열린다(``edit.py``·``regional.py`` 와 같은 규약).

라벨(``path_label``) 단언은 여기 없다 — 라벨 등재는 별도 task 소유다.
"""

import datetime
import uuid

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders import revision as revision_mod
from models import (
    Order,
    OrderFieldChange,
    OrderMutationReceipt,
    SecurityLog,
    User,
)


# --------------------------------------------------------------------------
# 픽스처
# --------------------------------------------------------------------------
def _login(client, username, role="ADMIN", team="CS"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = username
        sess["role"] = role
    return user.id


def _valid_sd(**overrides):
    sd = {
        "entity_type": "order_structured",
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 1", "address_main": "서울 테헤란로 1"},
        "items": [{"product_name": "붙박이장", "price": 0}],
        "flags": {"urgent": False, "urgent_reason": "", "factory2": False},
    }
    sd.update(overrides)
    return sd


def _create_order(**cols):
    sd = cols.pop("structured_data", None)
    order = Order(
        received_date="2026-08-26",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=sd if sd is not None else _valid_sd(),
    )
    for key, value in cols.items():
        setattr(order, key, value)
    db_session.add(order)
    db_session.commit()
    return order.id


def _ledger(oid, path=None):
    db_session.expire_all()
    query = db_session.query(OrderFieldChange).filter(OrderFieldChange.order_id == oid)
    if path is not None:
        query = query.filter(OrderFieldChange.path == path)
    return query.order_by(OrderFieldChange.id).all()


def _latest_log(action):
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == action)
        .order_by(SecurityLog.id.desc())
        .first()
    )


def _reload(oid):
    db_session.expire_all()
    return db_session.get(Order, oid)


def _storage_post(client, oid, field, value, **kwargs):
    return client.post(
        f"/api/storage_dashboard/order/{oid}/field",
        json={"field": field, "value": value},
        **kwargs,
    )


# --------------------------------------------------------------------------
# backstop 시뮬레이션
# --------------------------------------------------------------------------
def _plant_conflicting_receipt(actor_user_id, policy_id, idempotency_key):
    """``(actor, policy, key)`` unique 를 이미 점유한 receipt 를 커밋해 둔다.

    ``revision.execute_order_mutation`` 이 자기 receipt 를 ``flush()`` 할 때 이 행과
    충돌해 ``IntegrityError`` 를 내도록 만드는 미끼다. 실제 운영에서는 다른 order 를
    같은 key 로 동시에 요청한 cross-order 경합이 이 자리를 만든다.
    """
    now = datetime.datetime(2026, 8, 26, 0, 0, 0)
    receipt = OrderMutationReceipt(
        read_receipt_id=str(uuid.uuid4()),
        actor_user_id=actor_user_id,
        policy_id=policy_id,
        idempotency_key=idempotency_key,
        scope_hash="0" * 64,
        request_hash="0" * 64,
        response_status=200,
        response_body={"mutation_receipt": "winner", "resources": []},
        resulting_versions={},
        read_expires_at=now + datetime.timedelta(days=365),
        expires_at=now + datetime.timedelta(days=365),
    )
    db_session.add(receipt)
    db_session.commit()
    return receipt.read_receipt_id


@pytest.fixture
def integrity_backstop(monkeypatch):
    """첫 조회만 "없음"으로 속여 backstop(rollback→replay) 경로를 실제로 태운다.

    ``execute_order_mutation`` 은 lock 직후 한 번(step 2, mutation 실행 전), 그리고
    ``IntegrityError`` 를 받은 뒤 한 번(step 5 except) ``_lookup_receipt`` 를 부른다.
    첫 호출에 ``None`` 을 돌려주면 mutation 이 실행되고, ``flush()`` 가 미끼 receipt 와
    충돌해 ``session.rollback()`` → 두 번째 조회(진짜) → ``_replay`` 로 간다.
    """
    real_lookup = revision_mod._lookup_receipt
    state = {"calls": 0}

    def _fake_lookup(session, actor_user_id, policy_id, idempotency_key):
        state["calls"] += 1
        if state["calls"] == 1:
            return None
        return real_lookup(session, actor_user_id, policy_id, idempotency_key)

    monkeypatch.setattr(revision_mod, "_lookup_receipt", _fake_lookup)
    return state


# --------------------------------------------------------------------------
# 출고 대시보드 — /api/erp/shipment/update/<id>
# --------------------------------------------------------------------------
def test_shipment_changed_save_still_records_ledger_row(client, app):
    """회귀 확인: 값이 바뀐 저장은 여전히 원장 행을 만든다(원장 쓰기를 옮겨도 유지)."""
    _login(client, "ghost-ship-changed", role="STAFF", team="CS")
    oid = _create_order(structured_data=_valid_sd(shipment={"construction_time": "오전 10시"}))

    resp = client.post(f"/api/erp/shipment/update/{oid}", json={"construction_time": "오후 2시"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    # 저장이 실제로 반영됐는지 먼저 본다 — 요청이 죽어도 "행 없음"은 공짜로 통과한다.
    sd = (_reload(oid).structured_data or {}).get("shipment") or {}
    assert sd.get("construction_time") == "오후 2시"

    rows = _ledger(oid, "shipment.construction_time")
    assert len(rows) == 1, [(r.path, r.before_value, r.after_value) for r in _ledger(oid)]
    assert rows[0].before_value == "오전 10시"
    assert rows[0].after_value == "오후 2시"


def test_shipment_unchanged_save_writes_no_ledger_row(client, app):
    """회귀 확인: 같은 값 재저장은 여전히 0행이다."""
    _login(client, "ghost-ship-noop", role="STAFF", team="CS")
    oid = _create_order(
        structured_data=_valid_sd(shipment={"construction_time": "오전 10시",
                                            "construction_workers": ["김시공"]})
    )

    resp = client.post(f"/api/erp/shipment/update/{oid}", json={
        "construction_time": "오전 10시", "construction_workers": ["김시공"],
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    sd = (_reload(oid).structured_data or {}).get("shipment") or {}
    assert sd.get("construction_time") == "오전 10시"
    rows = _ledger(oid)
    assert rows == [], [(r.path, r.before_value, r.after_value) for r in rows]


def test_shipment_header_carries_change_set_even_when_nothing_changed(client, app):
    """무변경 저장에도 감사 헤더 ``detail['change_set']`` 이 있다(무조건 넣기 계약).

    행이 0인 상태는 "저장은 했는데 바뀐 값이 없다"는 정상 상태다. 조인 키를 조건부로
    빼면 감사 화면에서 원장으로 넘어가는 길이 저장마다 있었다 없었다 한다.
    """
    _login(client, "ghost-ship-header", role="STAFF", team="CS")
    oid = _create_order(structured_data=_valid_sd(shipment={"construction_time": "오전 10시"}))

    resp = client.post(f"/api/erp/shipment/update/{oid}", json={"construction_time": "오전 10시"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _ledger(oid) == []

    log = _latest_log("SHIPMENT_UPDATED")
    assert log is not None and log.target_id == oid
    assert log.detail.get("change_set"), "무변경 저장인데 조인 키가 빠졌다"
    assert log.detail.get("change_count") == 0


def test_shipment_header_change_set_matches_ledger_rows(client, app):
    """값이 바뀐 저장은 헤더 ``change_set`` 과 원장 ``change_set_id`` 가 같다."""
    _login(client, "ghost-ship-join", role="STAFF", team="CS")
    oid = _create_order(structured_data=_valid_sd(shipment={"construction_workers": ["김시공"]}))

    resp = client.post(f"/api/erp/shipment/update/{oid}", json={
        "construction_workers": ["김시공", "박시공"],
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    rows = _ledger(oid, "shipment.construction_workers")
    assert len(rows) == 1
    log = _latest_log("SHIPMENT_UPDATED")
    assert log is not None
    assert log.detail.get("change_set") == rows[0].change_set_id
    assert log.detail.get("change_count") == 1


def test_shipment_integrity_backstop_leaves_no_ghost_row(client, app, integrity_backstop):
    """backstop rollback 경로: sd 가 안 바뀌었으면 원장 행도 없어야 한다.

    원장 쓰기가 ``_mutate`` 바깥에 있으면 이 저장은 sd 는 그대로인데 원장에
    ``오전 10시 → 오후 2시`` 행을 남긴다 — 감사 화면이 없는 변경을 말하게 된다.
    """
    user_id = _login(client, "ghost-ship-backstop", role="STAFF", team="CS")
    oid = _create_order(structured_data=_valid_sd(shipment={"construction_time": "오전 10시"}))
    _plant_conflicting_receipt(user_id, "SHIPMENT_EDIT", "ghost-ship-key")

    resp = client.post(
        f"/api/erp/shipment/update/{oid}",
        json={"construction_time": "오후 2시"},
        headers={"Idempotency-Key": "ghost-ship-key"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert integrity_backstop["calls"] >= 2, "backstop 경로를 안 탔다 — 시뮬레이션이 무의미"

    # sd 는 rollback 으로 되돌아가 있다.
    sd = (_reload(oid).structured_data or {}).get("shipment") or {}
    assert sd.get("construction_time") == "오전 10시"
    rows = _ledger(oid)
    assert rows == [], [(r.path, r.before_value, r.after_value) for r in rows]


# --------------------------------------------------------------------------
# 수납장 대시보드 — /api/storage_dashboard/order/<id>/field
# --------------------------------------------------------------------------
def test_storage_changed_save_still_records_ledger_row(client, app):
    """회귀 확인: 배송비 변경은 여전히 이전 금액과 함께 남는다."""
    _login(client, "ghost-fee-changed", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=15000)

    resp = _storage_post(client, oid, "shipping_fee", 20000)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _reload(oid).shipping_fee == 20000

    rows = _ledger(oid, "shipping_fee")
    assert len(rows) == 1
    assert rows[0].before_value == "15000"
    assert rows[0].after_value == "20000"


def test_storage_zero_fee_is_still_a_value_not_a_blank(client, app):
    """회귀 확인: 0원은 '값 없음'이 아니라 무료 배송이라는 값이다(``clear`` 로 접히면 안 된다)."""
    _login(client, "ghost-fee-zero", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=15000)

    resp = _storage_post(client, oid, "shipping_fee", 0)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _reload(oid).shipping_fee == 0

    rows = _ledger(oid, "shipping_fee")
    assert len(rows) == 1
    assert rows[0].after_value == "0"
    assert rows[0].op == "set"


def test_storage_unchanged_save_writes_no_ledger_row(client, app):
    """회귀 확인: 같은 배송비 재저장은 여전히 0행이다."""
    _login(client, "ghost-fee-noop", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=15000)

    resp = _storage_post(client, oid, "shipping_fee", 15000)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _reload(oid).shipping_fee == 15000
    assert _ledger(oid) == []


def test_storage_header_carries_change_set_even_when_nothing_changed(client, app):
    """무변경 저장에도 감사 헤더 ``detail['change_set']`` 이 있다(무조건 넣기 계약)."""
    _login(client, "ghost-storage-header", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=15000)

    resp = _storage_post(client, oid, "cabinet_status", "RECEIVED")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _reload(oid).cabinet_status == "RECEIVED"
    assert _ledger(oid) == []

    log = _latest_log("STORAGE_SETTING_UPDATED")
    assert log is not None and log.target_id == oid
    assert log.detail.get("change_set"), "무변경 저장인데 조인 키가 빠졌다"
    # before 복원 계약은 그대로다 — 배송비는 돈이라 이전값이 없으면 따질 근거가 없다.
    assert log.detail["before"] == "RECEIVED"
    assert log.detail["after"] == "RECEIVED"


def test_storage_header_change_set_matches_ledger_rows(client, app):
    """값이 바뀐 저장은 헤더 ``change_set`` 과 원장 ``change_set_id`` 가 같다."""
    _login(client, "ghost-storage-join", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=0)

    resp = _storage_post(client, oid, "cabinet_status", "IN_PRODUCTION")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _reload(oid).cabinet_status == "IN_PRODUCTION"

    rows = _ledger(oid, "cabinet_status")
    assert len(rows) == 1
    log = _latest_log("STORAGE_SETTING_UPDATED")
    assert log is not None
    assert log.detail.get("change_set") == rows[0].change_set_id
    assert log.detail["before"] == "RECEIVED"
    assert log.detail["after"] == "IN_PRODUCTION"


def test_storage_integrity_backstop_leaves_no_ghost_row(client, app, integrity_backstop):
    """backstop rollback 경로: 배송비가 안 바뀌었으면 원장 행도 없어야 한다.

    돈이 걸린 축이라 유령 행의 대가가 가장 크다 — "누가 15,000 을 20,000 으로 바꿨다"고
    원장이 말하는데 실제 금액은 15,000 그대로다.
    """
    user_id = _login(client, "ghost-fee-backstop", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=15000)
    _plant_conflicting_receipt(user_id, "SHIPPING_FEE_CHANGED", "ghost-fee-key")

    resp = _storage_post(
        client, oid, "shipping_fee", 20000,
        headers={"Idempotency-Key": "ghost-fee-key"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert integrity_backstop["calls"] >= 2, "backstop 경로를 안 탔다 — 시뮬레이션이 무의미"

    assert _reload(oid).shipping_fee == 15000
    rows = _ledger(oid)
    assert rows == [], [(r.path, r.before_value, r.after_value) for r in rows]
