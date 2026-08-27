"""AUDIT-GAP-01: 구조화 저장(PUT) 밖의 세 화면이 변경 원장을 부르는지 고정한다.

``record_field_changes`` 호출부는 2026-08-26 이전에 전 저장소에 **3곳(2파일)** 뿐이었다.
그래서 ``structured_diff.SCALAR_PATHS`` 화이트리스트에 이미 등재된 값조차, 아래 화면에서
바꾸면 ``order_field_changes`` 에 아무것도 남지 않았다(운영 실측 2026-08-26).

* ``/api/update_order_field`` — ``schedule.as_visit.date`` 원장 **7행** vs
  ``ORDER_FIELD_UPDATED`` 보안로그 **126행**(18배 차)
* ``/api/erp/shipment/update`` — ``shipment.construction_time``·``construction_workers`` 는
  화이트리스트인데 출고 대시보드 경로만 원장 미기록
* ``/api/storage_dashboard/order/<id>/field`` — ``detail`` 에 ``after`` 만 있고 **before 가
  없었다**. 배송비는 돈이라 이전 금액이 없으면 분쟁에서 따질 근거가 없다.

여기서 고정하는 것 3가지.

* **경로 정합**: 라우트의 필드명(``as_visit_date``)이 아니라 값이 실제로 사는 sd 점 경로
  (``schedule.as_visit.date``)로 남는다 — 화면마다 경로가 갈리면 한 축으로 못 읽는다.
  평면 컬럼(``shipping_fee``)은 점 없는 컬럼명 그대로다.
* **안 바뀌면 안 남는다**: 같은 값 재저장은 행을 만들지 않는다.
* **조인 열쇠**: 원장 행을 쓴 저장은 보안로그 ``detail['change_set']`` 로 이어진다
  (관리자 감사 화면이 ``detail->>'change_set'`` 으로 조인한다).

라벨(``path_label``) 단언은 여기 없다 — 라벨 등재는 별도 task 소유다.
``shipment.site_extra`` 도 단언하지 않는다(요약 처리 설계가 별도 task 진행 중).
"""

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderFieldChange, SecurityLog, User


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


# --------------------------------------------------------------------------
# T4-1 /api/update_order_field — AS 방문일
# --------------------------------------------------------------------------
def test_as_visit_date_lands_on_structured_path(client, app):
    """AS 방문일 변경이 sd 점 경로로 원장에 남는다(필드명 as_visit_date 가 아니다)."""
    _login(client, "gap-asvisit")
    oid = _create_order(
        structured_data=_valid_sd(schedule={"as_visit": {"date": "2026-09-01"}})
    )

    resp = client.post("/api/update_order_field", json={
        "order_id": oid, "field": "as_visit_date", "value": "2026-09-10",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    rows = _ledger(oid, "schedule.as_visit.date")
    assert len(rows) == 1, [(r.path, r.before_value, r.after_value) for r in _ledger(oid)]
    assert rows[0].before_value == "2026-09-01"
    assert rows[0].after_value == "2026-09-10"
    # 라우트 필드명으로는 남지 않는다 — 경로가 갈리면 한 축으로 못 읽는다.
    assert _ledger(oid, "as_visit_date") == []


def test_as_visit_date_change_joins_security_log_by_change_set(client, app):
    """원장 행을 쓴 저장은 보안로그 detail['change_set'] 으로 이어진다."""
    _login(client, "gap-asvisit-join")
    oid = _create_order(
        structured_data=_valid_sd(schedule={"as_visit": {"date": "2026-09-01"}})
    )

    resp = client.post("/api/update_order_field", json={
        "order_id": oid, "field": "as_visit_date", "value": "2026-09-11",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    row = _ledger(oid, "schedule.as_visit.date")[0]
    log = _latest_log("ORDER_FIELD_UPDATED")
    assert log is not None and log.target_id == oid
    assert log.detail.get("change_set") == row.change_set_id


def test_as_visit_date_unchanged_save_writes_no_row(client, app):
    """같은 방문일 재저장은 원장에 행을 만들지 않는다."""
    _login(client, "gap-asvisit-noop")
    oid = _create_order(
        structured_data=_valid_sd(schedule={"as_visit": {"date": "2026-09-01"}})
    )

    resp = client.post("/api/update_order_field", json={
        "order_id": oid, "field": "as_visit_date", "value": "2026-09-01",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _ledger(oid) == []


def test_flat_only_field_uses_bare_column_name(client, app):
    """평면 컬럼만 바꾸는 필드는 점 없는 컬럼명으로 남는다(AS 접수일)."""
    _login(client, "gap-asrecv")
    oid = _create_order(as_received_date="2026-08-01")

    resp = client.post("/api/update_order_field", json={
        "order_id": oid, "field": "as_received_date", "value": "2026-08-20",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    rows = _ledger(oid, "as_received_date")
    assert len(rows) == 1
    assert rows[0].before_value == "2026-08-01"
    assert rows[0].after_value == "2026-08-20"


def test_flat_only_field_unchanged_save_writes_no_row(client, app):
    """같은 값 재저장은 평면 경로에도 행을 만들지 않는다."""
    _login(client, "gap-asrecv-noop")
    oid = _create_order(as_received_date="2026-08-01")

    resp = client.post("/api/update_order_field", json={
        "order_id": oid, "field": "as_received_date", "value": "2026-08-01",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _ledger(oid) == []


def test_as_completed_date_bridge_keeps_the_value_that_was_erased(client, app):
    """AS 완료일은 canonical 브리지를 타지만 원장·헤더에 이전값이 남아야 한다.

    이 경로의 감사 헤더는 ``after`` 만 담고 있었다 — 완료일을 지운 운영 97건이 '원래 언제
    였는지' 없이 남은 것과 같은 구멍이다.
    """
    _login(client, "gap-ascomplete")
    oid = _create_order(status="AS", erp_stage_code="AS",
                        structured_data={"workflow": {"stage": "AS"}, "shipment": {}})

    first = client.post("/api/update_order_field", json={
        "order_id": oid, "field": "as_completed_date", "value": "2026-08-05",
    })
    assert first.status_code == 200, first.get_data(as_text=True)

    rows = _ledger(oid, "as_completed_date")
    assert len(rows) == 1
    assert rows[0].before_value is None
    assert rows[0].after_value == "2026-08-05"

    log = _latest_log("ORDER_FIELD_UPDATED")
    assert log.detail["field"] == "as_completed_date"
    assert log.detail.get("change_set") == rows[0].change_set_id

    # 같은 값 재저장은 행을 만들지 않는다(append-only 타임라인 중복 금지와 같은 게이트).
    again = client.post("/api/update_order_field", json={
        "order_id": oid, "field": "as_completed_date", "value": "2026-08-05",
    })
    assert again.status_code == 200, again.get_data(as_text=True)
    assert len(_ledger(oid, "as_completed_date")) == 1


def test_status_change_is_recorded_on_the_status_axis(client, app):
    """상태 변경은 **``status`` 경로**로 남는다 (2026-08-26 CEO 판정).

    ``order.status`` 와 ``workflow.stage`` 는 일부러 분리된 두 축이다 — AS 접수 주문은
    status 가 AS 로 바뀌어도 workflow.stage 는 MEASURE 로 남는다
    (``stage_override.as_overlay_status`` docstring 이 SSOT). 그래서 status 를
    ``workflow.stage`` 쌍둥이로 묶어 억제하면 **함께 바뀐 두 값 중 하나가 사라진다.**

    경로를 집합(``in ("status","workflow.stage")``)으로 느슨하게 받으면 어느 축에 실렸는지
    고정하지 못해 축이 갈라져도 green 이다 — 그래서 여기서는 정확히 못 박는다.
    """
    _login(client, "gap-status")
    oid = _create_order(status="RECEIVED")

    resp = client.post("/api/update_order_field", json={
        "order_id": oid, "field": "status", "value": "MEASURED",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    # 저장이 실제로 반영됐는지 먼저 본다 — 요청이 죽어도 "행 없음"은 공짜로 통과한다.
    db_session.expire_all()
    assert db_session.get(Order, oid).status == "MEASURED"

    status_rows = _ledger(oid, "status")
    assert len(status_rows) == 1, "상태 변경이 status 축에 안 남았다"
    assert status_rows[0].before_value == "RECEIVED"
    assert status_rows[0].after_value == "MEASURED"


# --------------------------------------------------------------------------
# T4-2 /api/erp/shipment/update — 출고 대시보드 저장
# --------------------------------------------------------------------------
def test_shipment_dashboard_records_construction_workers(client, app):
    """출고 대시보드 시공인원 변경이 원장에 남는다(화이트리스트인데 미기록이었다)."""
    _login(client, "gap-shipworkers", role="STAFF", team="CS")
    oid = _create_order(
        structured_data=_valid_sd(shipment={"construction_workers": ["김시공"]})
    )

    resp = client.post(f"/api/erp/shipment/update/{oid}", json={
        "construction_workers": ["김시공", "박시공"],
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    rows = _ledger(oid, "shipment.construction_workers")
    assert len(rows) == 1, [(r.path, r.before_value, r.after_value) for r in _ledger(oid)]
    assert "박시공" in (rows[0].after_value or "")
    assert "박시공" not in (rows[0].before_value or "")

    log = _latest_log("SHIPMENT_UPDATED")
    assert log is not None and log.detail.get("change_set") == rows[0].change_set_id


def test_shipment_dashboard_records_construction_time(client, app):
    """시공 시간도 sd 점 경로로 남는다."""
    _login(client, "gap-shiptime", role="STAFF", team="CS")
    oid = _create_order(structured_data=_valid_sd(shipment={"construction_time": "오전 10시"}))

    resp = client.post(f"/api/erp/shipment/update/{oid}", json={
        "construction_time": "오후 2시",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)

    rows = _ledger(oid, "shipment.construction_time")
    assert len(rows) == 1
    assert rows[0].before_value == "오전 10시"
    assert rows[0].after_value == "오후 2시"


def test_shipment_dashboard_unchanged_save_writes_no_row(client, app):
    """같은 출고 설정 재저장은 행을 만들지 않는다."""
    _login(client, "gap-ship-noop", role="STAFF", team="CS")
    oid = _create_order(
        structured_data=_valid_sd(shipment={"construction_time": "오전 10시",
                                            "construction_workers": ["김시공"]})
    )

    resp = client.post(f"/api/erp/shipment/update/{oid}", json={
        "construction_time": "오전 10시", "construction_workers": ["김시공"],
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    # site_extra 는 요약 처리 설계가 별도 task 소유라 판정에서 제외한다.
    rows = [r for r in _ledger(oid) if r.path != "shipment.site_extra"]
    assert rows == [], [(r.path, r.before_value, r.after_value) for r in rows]


# --------------------------------------------------------------------------
# T4-3 /api/storage_dashboard/order/<id>/field — 배송비·수납장 상태
# --------------------------------------------------------------------------
def _storage_post(client, oid, field, value):
    return client.post(
        f"/api/storage_dashboard/order/{oid}/field", json={"field": field, "value": value}
    )


def test_shipping_fee_records_before_and_after(client, app):
    """배송비 변경이 이전 금액과 함께 남는다(돈은 before 없으면 따질 수 없다)."""
    _login(client, "gap-fee", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=15000)

    resp = _storage_post(client, oid, "shipping_fee", 20000)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    rows = _ledger(oid, "shipping_fee")
    assert len(rows) == 1
    assert rows[0].before_value == "15000"
    assert rows[0].after_value == "20000"

    log = _latest_log("STORAGE_SETTING_UPDATED")
    assert log is not None and log.target_id == oid
    assert log.detail["before"] == 15000
    assert log.detail["after"] == 20000
    assert log.detail.get("change_set") == rows[0].change_set_id


def test_cabinet_status_records_before_and_after(client, app):
    """수납장 상태도 이전 상태와 함께 남는다."""
    _login(client, "gap-cabinet", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=0)

    resp = _storage_post(client, oid, "cabinet_status", "IN_PRODUCTION")
    assert resp.status_code == 200, resp.get_data(as_text=True)

    rows = _ledger(oid, "cabinet_status")
    assert len(rows) == 1
    assert rows[0].before_value == "RECEIVED"
    assert rows[0].after_value == "IN_PRODUCTION"

    log = _latest_log("STORAGE_SETTING_UPDATED")
    assert log.detail["before"] == "RECEIVED"


def test_storage_unchanged_save_writes_no_row(client, app):
    """같은 배송비 재저장은 행을 만들지 않는다."""
    _login(client, "gap-fee-noop", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=15000)

    resp = _storage_post(client, oid, "shipping_fee", 15000)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _ledger(oid) == []


def test_shipping_fee_zero_is_a_value_not_a_blank(client, app):
    """0원은 '값 없음'이 아니라 무료 배송이라는 값이다(clear 로 접히면 안 된다)."""
    _login(client, "gap-fee-zero", role="STAFF", team="CS")
    oid = _create_order(is_cabinet=True, cabinet_status="RECEIVED", shipping_fee=15000)

    resp = _storage_post(client, oid, "shipping_fee", 0)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    rows = _ledger(oid, "shipping_fee")
    assert len(rows) == 1
    assert rows[0].after_value == "0"
    assert rows[0].op == "set"
