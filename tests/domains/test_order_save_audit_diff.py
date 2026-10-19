"""주문 저장 감사 로그의 변경 내역 배선 계약 (ORDER-DIFF-00).

2026-08-11 운영 실측에서 ``/security_logs`` 최근 50행의 ``before``/``after`` 가 0건이었다
(``ORDER_STRUCTURED_SAVED`` 는 "저장했다"까지만 남겼다). 저장 두 경로(전체 PUT·인라인 PATCH)가
실제로 바뀐 값을 남기는지, 그리고 감사 화면이 그것을 사람 문장으로 읽는지 여기서 고정한다.
"""

import copy

from werkzeug.security import generate_password_hash

from db import db_session
from foms.web.admin.audit import _security_log_row
from models import Order, SecurityLog, User


def _login_as_admin(client, username="diff-audit-admin"):
    """감사 로그를 남길 ADMIN 세션을 만든다."""
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Diff Audit Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _structured_payload():
    """저장 전 기준 문서."""
    return {
        "workflow": {"stage": "RECEIVED"},
        "shipment": {},
        "schedule": {"measurement": {"date": "2026-08-12"}},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "totals": {"final_amount": "1300000"},
        "items": [{"product_name": "붙박이장", "price": "500000"}],
        "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123", "address_detail": ""},
    }


def _create_order() -> Order:
    """감사 대상 ERP 주문 1건."""
    order = Order(
        received_date="2026-08-11",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=_structured_payload(),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _latest_save_log(order_id: int) -> SecurityLog:
    """해당 주문의 마지막 저장 감사 행."""
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ORDER_STRUCTURED_SAVED", SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.desc())
        .first()
    )


def test_full_save_records_field_level_changes(client):
    """전체 저장은 바뀐 필드의 이전값→새값을 detail 에 남긴다."""
    _login_as_admin(client)
    order = _create_order()
    order_id = order.id

    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = "2026-08-14"
    sd["items"][0]["price"] = "620000"

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )
    assert response.status_code == 200

    entry = _latest_save_log(order_id)
    assert entry is not None
    changes = {change["path"]: change for change in entry.detail["changes"]}

    assert changes["schedule.measurement.date"]["before"] == "2026-08-12"
    assert changes["schedule.measurement.date"]["after"] == "2026-08-14"
    assert changes["items.0.price"]["before"] == "500000"
    assert changes["items.0.price"]["after"] == "620000"
    assert changes["items.0.price"]["item"] == "붙박이장"
    assert entry.detail["change_count"] == len(entry.detail["changes"])
    assert entry.detail["truncated"] == 0
    # 문장만 봐도 무엇이 바뀌었는지 읽혀야 한다(CSV·grep 경로에는 표가 없다).
    assert "실측일" in entry.message


def test_save_without_changes_keeps_plain_sentence(client):
    """바뀐 게 없으면 없는 변경을 지어내지 않는다.

    첫 저장은 서버 금액 재계산(DATA-01 server pricing)이 걸려 ``totals`` 가 실제로 바뀐다 —
    그건 진짜 변경이므로 기록돼야 한다. 무변경 판정은 **그 다음 저장**에서 확인한다.
    """
    _login_as_admin(client, username="diff-audit-nochange")
    order = _create_order()
    order_id = order.id

    first = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": copy.deepcopy(order.structured_data), "structured_schema_version": 1},
    )
    assert first.status_code == 200

    db_session.expire_all()
    settled = db_session.get(Order, order_id)
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": copy.deepcopy(settled.structured_data), "structured_schema_version": 1},
    )
    assert response.status_code == 200

    entry = _latest_save_log(order_id)
    assert entry.detail["change_count"] == 0
    assert entry.detail["changes"] == []
    assert entry.message.endswith("전체 저장")


def test_inline_patch_records_before_and_after(client, monkeypatch):
    """인라인 저장은 경로만이 아니라 값까지 남긴다(기존에는 ``field`` 만 있었다)."""
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "1")
    _login_as_admin(client, username="diff-audit-inline")
    order = _create_order()
    order_id = order.id

    response = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        json={"field": "parties.customer.phone", "value": "010-9999-8888"},
    )
    assert response.status_code == 200

    entry = _latest_save_log(order_id)
    assert entry.detail["mode"] == "inline"
    assert entry.detail["field"] == "parties.customer.phone"
    assert entry.detail["changes"] == [{
        "path": "parties.customer.phone",
        "before": "010-1234-5678",
        "after": "010-9999-8888",
        "op": "set",
    }]


def test_audit_screen_renders_change_rows(client):
    """감사 화면은 경로가 아니라 업무 라벨로 변경을 읽는다(라벨은 읽기 시점에 붙는다)."""
    _login_as_admin(client, username="diff-audit-screen")
    order = _create_order()
    order_id = order.id

    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = "2026-08-20"
    client.put(f"/api/orders/{order_id}/structured",
               json={"structured_data": sd, "structured_schema_version": 1})

    row = _security_log_row(_latest_save_log(order_id), {})

    assert row["change_total"] >= 1
    labels = [change["label"] for change in row["changes"]]
    assert "실측일" in labels
    assert any("2026-08-12" in change["text"] and "2026-08-20" in change["text"] for change in row["changes"])


def test_legacy_field_only_detail_is_not_read_as_cleared(client):
    """값 없이 ``field`` 만 있는 구(舊) 인라인 기록을 "지웠다"로 읽지 않는다.

    ORDER-DIFF-00 이전 인라인 저장은 ``{'mode','field'}`` 만 남겼다. 읽기 경로가 그것을
    ``after=None`` 으로 재구성하면 **바꾼 적 없는 값을 지운 것으로** 보인다.
    """
    user = _login_as_admin(client, username="diff-audit-legacy")
    order = _create_order()

    legacy = SecurityLog(
        user_id=user.id,
        message="주문 #%d — 주문 저장: 인라인 수정" % order.id,
        action="ORDER_STRUCTURED_SAVED",
        target_type="order",
        target_id=order.id,
        detail={"mode": "inline", "field": "schedule.measurement.date", "order_type": "주문"},
    )
    db_session.add(legacy)
    db_session.commit()

    row = _security_log_row(legacy, {})

    assert "(지움)" not in row["display"]
    assert row["display"].endswith("인라인 수정")
