"""주문 변경 사유 저장 경로 계약 (ORDER-REASON-00 T4).

여기서 고정하는 것: 저장이 **막히지 않는다**, 사유 요구 판정이 응답으로 내려간다(화면이
서버 판정을 그대로 쓴다), 그리고 그 표식이 ``security_logs.detail`` 예산을 깨지 않는다.

정본: docs/specs/2026-08-13-order-change-reason_SPEC.md
"""

import copy
import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.audit_message_display import ACTION_LABELS
from foms.services.audit_writer import SECURITY_DETAIL_LIMIT
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.change_reason import REASON_ATTACH_WINDOW, REASON_CODES
from models import Order, OrderChangeReason, OrderFieldChange, SecurityLog, User


def _login_as_admin(client, username="reason-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Reason Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_order(items=None) -> Order:
    order = Order(
        received_date="2026-08-13",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "RECEIVED"},
            "shipment": {},
            "schedule": {"measurement": {"date": "2026-08-14"}},
            "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
            "totals": {"final_amount": "1,300,000"},
            "items": items if items is not None else [{"product_name": "붙박이장", "price": "500000"}],
            "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123",
                     "address_detail": ""},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _save(client, order_id: int, mutate):
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    mutate(sd)
    response = client.put(f"/api/orders/{order_id}/structured",
                          json={"structured_data": sd, "structured_schema_version": 1})
    assert response.status_code == 200, response.get_data(as_text=True)[:200]
    db_session.expire_all()
    return response


def _last_header(order_id: int) -> SecurityLog:
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ORDER_STRUCTURED_SAVED", SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.desc())
        .first()
    )


def test_amount_save_asks_for_reason(client):
    """금액이 바뀐 저장은 사유 요구 표식을 응답과 감사 헤더 양쪽에 남긴다.

    바꾸는 값은 **입력**인 품목 단가다 — ``totals`` 로 보내봐야 서버가 재계산으로 덮는다.
    """
    _login_as_admin(client)
    order = _create_order()

    response = _save(client, order.id, lambda sd: sd["items"][0].update({"price": "620000"}))
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["change_reason_required"] is True
    assert payload["change_set"]

    header = _last_header(order.id)
    assert header.detail["reason_required"] is True
    assert header.detail["change_set"] == payload["change_set"]


def test_non_sensitive_save_does_not_ask(client):
    """연락처만 바뀐 저장은 묻지 않는다 — 매번 물으면 직원이 아무 값이나 고른다."""
    _login_as_admin(client, "reason-admin-2")
    order = _create_order()

    response = _save(client, order.id,
                     lambda sd: sd["parties"]["customer"].update({"phone": "010-9999-0000"}))
    payload = response.get_json()

    assert payload["change_reason_required"] is False
    header = _last_header(order.id)
    assert "reason_required" not in header.detail


def test_save_succeeds_without_any_reason(client):
    """사유는 저장을 막지 않는다 — 사유 때문에 주문 저장이 실패하면 영업이 멈춘다."""
    _login_as_admin(client, "reason-admin-3")
    order = _create_order()

    response = _save(client, order.id,
                     lambda sd: sd["schedule"]["measurement"].update({"date": "2026-08-20"}))

    assert response.status_code == 200
    assert response.get_json()["change_reason_required"] is True
    db_session.expire_all()
    assert db_session.get(Order, order.id).structured_data["schedule"]["measurement"]["date"] == "2026-08-20"


def test_reason_flag_does_not_blow_detail_budget(client):
    """품목 대량 변경 + 사유 표식이 함께 와도 detail 이 통째 표식으로 바뀌지 않는다.

    ``normalize_security_detail`` 은 4,000자를 넘는 detail 을 ``{'truncated':True,'size':N}``
    로 바꾼다 — 그러면 변경 목록만이 아니라 ``mode``·주문 맥락까지 사라진다.
    """
    _login_as_admin(client, "reason-admin-4")
    items = [{"product_name": f"품목{i}", "price": str(100000 + i)} for i in range(46)]
    order = _create_order(items=items)

    def mutate(sd):
        for index, item in enumerate(sd["items"]):
            item["price"] = str(900000 + index)

    response = _save(client, order.id, mutate)
    assert response.get_json()["change_reason_required"] is True

    header = _last_header(order.id)
    assert header.detail.get("mode") == "full"          # 맥락이 살아 있다
    assert header.detail["reason_required"] is True
    # 46개 단가 + 서버가 재계산한 파생 totals — 원장은 전량, detail 은 상한·예산 안에서만.
    assert header.detail["change_count"] >= 46
    assert len(str(header.detail)) < SECURITY_DETAIL_LIMIT


def test_inline_save_reports_reason_requirement(client, monkeypatch):
    """인라인(blur 자동저장)도 같은 판정을 응답에 싣는다 — 화면은 모달 대신 배너를 띄운다."""
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "1")
    _login_as_admin(client, "reason-admin-5")
    order = _create_order()

    response = client.patch(
        f"/api/orders/{order.id}/structured/fields",
        json={"field": "schedule.measurement.date", "value": "2026-08-25"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    payload = response.get_json()

    assert payload["change_reason_required"] is True
    assert payload["change_set"]


# ---------------------------------------------------------------------------
# T5: 사유 첨부 API — 저장은 이미 끝났고, 여기서 "왜"를 붙인다.
# ---------------------------------------------------------------------------

def _login_as_staff(client, username="reason-staff"):
    user = User(
        username=username,
        password=generate_password_hash("staff"),
        role="STAFF",
        team="CS",
        name="Reason Staff",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _attach(client, order_id, change_set, code="customer_request", note=""):
    return client.post(
        f"/api/orders/{order_id}/change-reason",
        json={"change_set": change_set, "code": code, "note": note},
    )


def _sensitive_save(client, order_id):
    """사유를 물어야 하는 저장 1회(품목 단가 변경)."""
    response = _save(client, order_id, lambda sd: sd["items"][0].update({"price": "777000"}))
    payload = response.get_json()
    assert payload["change_reason_required"] is True
    return payload["change_set"]


def test_attach_reason_records_ledger_row_and_audit(client):
    """사유가 원장에 남고, 그 행위 자체도 감사 로그가 된다."""
    _login_as_admin(client, "reason-attach-1")
    order = _create_order()
    change_set = _sensitive_save(client, order.id)

    response = _attach(client, order.id, change_set, code="input_correction")
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert response.get_json()["data"]["reason"]["label"] == "입력 오류 정정"

    db_session.expire_all()
    row = (
        db_session.query(OrderChangeReason)
        .filter(OrderChangeReason.change_set_id == change_set)
        .one()
    )
    assert (row.order_id, row.reason_code, row.reason_note) == (order.id, "input_correction", None)

    audit = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ORDER_CHANGE_REASON_SET", SecurityLog.target_id == order.id)
        .one()
    )
    assert audit.detail["change_set"] == change_set
    assert audit.detail["reason_code"] == "input_correction"
    # 새 action 은 표시 SSOT 에 등재돼 있어야 감사 화면이 코드가 아니라 라벨을 보여준다.
    assert ACTION_LABELS["ORDER_CHANGE_REASON_SET"] == "변경 사유 입력"


def test_reason_cannot_be_overwritten(client):
    """감사 원장은 덮어쓰지 않는다 — 두 번째 첨부는 409."""
    _login_as_admin(client, "reason-attach-2")
    order = _create_order()
    change_set = _sensitive_save(client, order.id)

    assert _attach(client, order.id, change_set).status_code == 200
    second = _attach(client, order.id, change_set, code="site_condition")
    assert second.status_code == 409
    assert "이미" in second.get_json()["error"]


def test_other_code_requires_note(client):
    """`기타` 는 메모가 있어야 집계에서 "그 밖"이 뭉개지지 않는다."""
    _login_as_admin(client, "reason-attach-3")
    order = _create_order()
    change_set = _sensitive_save(client, order.id)

    assert _attach(client, order.id, change_set, code="other").status_code == 400
    assert _attach(client, order.id, change_set, code="unknown_code").status_code == 400
    assert _attach(client, order.id, change_set, code="other", note="현장 요청").status_code == 200


def test_change_set_of_another_order_is_rejected(client):
    """다른 주문의 저장 묶음에 사유를 심을 수 없다."""
    _login_as_admin(client, "reason-attach-4")
    order_id = _create_order().id
    other_id = _create_order().id
    change_set = _sensitive_save(client, order_id)

    assert _attach(client, other_id, change_set).status_code == 404
    assert _attach(client, order_id, "not-a-real-change-set").status_code == 404


def test_staff_cannot_attach_reason_to_someone_elses_save(client):
    """본인이 한 저장에만 — 남의 저장에 사유를 붙이면 기록이 거짓이 된다(ADMIN 은 대리 가능)."""
    _login_as_admin(client, "reason-attach-5")
    order = _create_order()
    change_set = _sensitive_save(client, order.id)

    _login_as_staff(client, "reason-staff-1")
    refused = _attach(client, order.id, change_set)
    assert refused.status_code == 403

    db_session.expire_all()
    assert db_session.query(OrderChangeReason).filter(
        OrderChangeReason.change_set_id == change_set).first() is None


def test_reason_window_expires(client):
    """24시간이 지난 저장에는 못 붙인다 — 한참 뒤에 적는 사유는 기억이 아니라 재구성이다."""
    _login_as_admin(client, "reason-attach-6")
    order = _create_order()
    change_set = _sensitive_save(client, order.id)

    stale = now_utc_naive() - REASON_ATTACH_WINDOW - datetime.timedelta(minutes=1)
    for row in db_session.query(OrderFieldChange).filter(
            OrderFieldChange.change_set_id == change_set).all():
        row.created_at = stale
    db_session.commit()

    expired = _attach(client, order.id, change_set)
    assert expired.status_code == 410


# ---------------------------------------------------------------------------
# T6~T7: 화면 표면 — 이력 탭이 "왜"를 보여주고, 사유 입력 자산이 실려 있다.
# ---------------------------------------------------------------------------

def test_history_tab_exposes_reason(client):
    """이력 탭 응답이 저장 묶음마다 사유를 함께 준다(없으면 명시적으로 null)."""
    _login_as_admin(client, "reason-tab-1")
    order = _create_order()
    order_id = order.id
    with_reason = _sensitive_save(client, order_id)
    assert _attach(client, order_id, with_reason, code="site_condition").status_code == 200

    # 사유를 붙이지 않은 저장도 한 건 만든다.
    _save(client, order_id, lambda sd: sd["items"][0].update({"price": "888000"}))

    response = client.get(f"/api/orders/{order_id}/field-changes")
    assert response.status_code == 200
    sets = {entry["change_set"]: entry for entry in response.get_json()["data"]["change_sets"]}

    assert sets[with_reason]["reason"]["label"] == "현장 사정"
    assert sets[with_reason]["reason"]["code"] == "site_condition"
    others = [entry for key, entry in sets.items() if key != with_reason]
    assert others and all(entry["reason"] is None for entry in others)


def test_reason_codes_endpoint_is_the_single_source(client):
    """화면은 사유 목록을 서버에서 받는다 — JS 에 복사본을 두지 않는다."""
    _login_as_admin(client, "reason-tab-2")

    payload = client.get("/api/orders/change-reason-codes").get_json()
    codes = payload["data"]["codes"]

    assert [entry["code"] for entry in codes] == list(REASON_CODES)
    assert [entry for entry in codes if entry["note_required"]] == [
        {"code": "other", "label": "기타", "note_required": True}
    ]


def test_edit_page_loads_reason_surface(client):
    """사유 입력 자산이 주문 편집 화면에 실려야 화면이 실제로 뜬다."""
    _login_as_admin(client, "reason-tab-3")
    order = _create_order()

    body = client.get(f"/edit/{order.id}").get_data(as_text=True)

    assert "js/orders/order-change-reason.js" in body


# ---------------------------------------------------------------------------
# 사유 집계 — "입력 오류 정정 이번 달 몇 건" + 우회율
# ---------------------------------------------------------------------------

def test_stats_counts_by_code_and_skipped(client):
    """붙은 사유는 코드별로 세고, 물었는데 안 붙은 저장은 미입력으로 센다."""
    _login_as_admin(client, "reason-stats-1")
    order_id = _create_order().id

    attached_set = _sensitive_save(client, order_id)
    assert _attach(client, order_id, attached_set, code="input_correction").status_code == 200
    _save(client, order_id, lambda sd: sd["items"][0].update({"price": "999000"}))  # 사유 미입력

    data = client.get("/api/orders/change-reason-stats?days=30").get_json()["data"]
    by_code = {entry["code"]: entry["count"] for entry in data["by_code"]}

    assert by_code["input_correction"] == 1
    assert by_code["customer_request"] == 0
    assert data["attached"] == 1
    assert data["required"] == 2
    assert data["skipped"] == 1


def test_stats_is_admin_only(client):
    """사유 집계는 감사 지표라 ADMIN 전용이다."""
    _login_as_staff(client, "reason-stats-staff")
    assert client.get("/api/orders/change-reason-stats").status_code in (302, 403)


def test_stats_page_renders(client):
    """관리자 화면이 뜨고 집계 스크립트를 싣는다."""
    _login_as_admin(client, "reason-stats-2")
    body = client.get("/admin/change-reasons").get_data(as_text=True)
    assert "변경 사유 집계" in body
    assert "js/orders/change-reason-stats.js" in body
