"""AUDIT-LOG P4 B1: 주문 변경 3경로의 구조화 감사 기록 계약.

스펙: ``docs/specs/2026-08-08-audit-log-readability-coverage-design.md`` §3-2.

운영 실측이 드러낸 구멍을 막는다:

* ``as_completed_date`` 를 빈 값으로 바꾼 97건이 **원래 언제였는지 없이** 남았다
  (되돌릴 수도, 따질 수도 없다) → ``before`` 를 반드시 함께 기록한다.
* 로그가 주문번호만 담아 "누구 건인지"를 알려면 매번 주문을 열어야 했다
  → 고객명·주문 성격을 기록 시점에 스냅샷한다.
* 그러나 감사 원장에 PII 를 늘리지는 않는다 → **연락처·주소는 담지 않는다**.
"""

from __future__ import annotations

import itertools

from db import db_session
from models import Order, SecurityLog, User

_counter = itertools.count(1)
_PHONE = "010-3333-4444"
_ADDRESS = "서울시 감사구 원장로 12"


def _make_user(role: str = "ADMIN") -> int:
    n = next(_counter)
    user = User(username=f"p4-write-{n}", password="x", role=role,
                name=f"작업자{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def _make_order(**kwargs) -> Order:
    order = Order(
        received_date="2026-08-08",
        customer_name=kwargs.pop("customer_name", "홍길동"),
        phone=_PHONE,
        address=_ADDRESS,
        product="붙박이장",
        status=kwargs.pop("status", "RECEIVED"),
        **kwargs,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _client(app, user_id: int):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _latest_log(action: str) -> SecurityLog:
    db_session.expire_all()
    row = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == action)
        .order_by(SecurityLog.id.desc())
        .first()
    )
    assert row is not None, f"{action} 기록이 없다"
    return row


def _assert_no_pii(row: SecurityLog) -> None:
    """감사 행에 연락처·주소가 실려서는 안 된다(원장 PII 최소화)."""
    blob = f"{row.message or ''} {row.detail or ''}"
    assert _PHONE not in blob, "연락처가 감사 행에 실렸다"
    assert _ADDRESS not in blob, "주소가 감사 행에 실렸다"


# --------------------------------------------------------------------------
# 1. 필드 수정 경로 (field_update)
# --------------------------------------------------------------------------
def test_field_update_records_before_and_after(app):
    """필드 수정이 '이전 → 이후'와 대상 주문을 구조화로 남긴다."""
    with app.app_context():
        user_id = _make_user()
        order = _make_order(customer_name="이영희", measurement_date="2026-07-02")
        order_id = order.id
        client = _client(app, user_id)

        resp = client.post(
            "/api/update_order_field",
            json={"order_id": order_id, "field": "measurement_date", "value": "2026-08-20"},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        row = _latest_log("ORDER_FIELD_UPDATED")
        assert row.target_type == "order" and row.target_id == order_id
        assert row.detail["field"] == "measurement_date"
        assert row.detail["before"] == "2026-07-02"
        assert row.detail["after"] == "2026-08-20"
        assert row.detail["customer_name"] == "이영희"
        assert "실측일: 2026-07-02 → 2026-08-20" in row.message
        assert f"주문 #{order_id} (이영희)" in row.message
        _assert_no_pii(row)


def test_field_cleared_keeps_the_value_that_was_erased(app):
    """값을 지운 기록이 '무엇을 지웠는지'를 남긴다(운영 97건이 잃어버린 정보)."""
    with app.app_context():
        user_id = _make_user()
        order = _make_order(customer_name="박민수", measurement_date="2026-07-15")
        order_id = order.id
        client = _client(app, user_id)

        resp = client.post(
            "/api/update_order_field",
            json={"order_id": order_id, "field": "measurement_date", "value": ""},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        row = _latest_log("ORDER_FIELD_UPDATED")
        assert row.detail["before"] == "2026-07-15"
        assert row.detail["after"] == ""
        assert "실측일: 2026-07-15 → (지움)" in row.message


def test_status_field_update_uses_status_action_and_korean_stage(app):
    """상태 변경은 별도 action 으로 구분되고 단계 이름으로 읽힌다."""
    with app.app_context():
        user_id = _make_user()
        order = _make_order(customer_name="최영수", status="RECEIVED", is_self_measurement=True)
        order_id = order.id
        client = _client(app, user_id)

        resp = client.post(
            "/api/update_order_field",
            json={"order_id": order_id, "field": "status", "value": "MEASURE"},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        row = _latest_log("ORDER_STATUS_CHANGED")
        assert row.detail["before"] == "RECEIVED"
        assert row.detail["after"] == "MEASURE"
        assert "상태: 접수 → 실측" in row.message
        assert "자가실측 주문" in row.message


# --------------------------------------------------------------------------
# 2. 지방 체크리스트 경로 (regional)
# --------------------------------------------------------------------------
def test_regional_checklist_records_previous_state(app):
    """체크리스트 토글이 이전 상태까지 남긴다(해제인지 최초 체크인지 구분)."""
    with app.app_context():
        user_id = _make_user()
        order = _make_order(customer_name="김철수", is_regional=True,
                            regional_blueprint_sent=True)
        order_id = order.id
        client = _client(app, user_id)

        resp = client.post(
            "/api/update_regional_status",
            json={"order_id": order_id, "field": "regional_blueprint_sent", "value": False},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        row = _latest_log("ORDER_CHECKLIST_UPDATED")
        assert row.target_id == order_id
        assert row.detail["field"] == "regional_blueprint_sent"
        assert row.detail["before"] is True
        assert row.detail["after"] is False
        assert "도면 발송: 완료 → 해제" in row.message
        assert f"지방 주문 #{order_id} (김철수)" in row.message
        _assert_no_pii(row)


# --------------------------------------------------------------------------
# 3. 상태 변경 경로 (status)
# --------------------------------------------------------------------------
def test_status_route_records_structured_transition(app):
    """상태 변경 API 도 구조화 전이를 남긴다."""
    with app.app_context():
        user_id = _make_user()
        order = _make_order(customer_name="한지민", status="RECEIVED")
        order_id = order.id
        client = _client(app, user_id)

        resp = client.post(
            "/api/update_order_status",
            json={"order_id": order_id, "status": "MEASURE"},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        row = _latest_log("ORDER_STATUS_CHANGED")
        assert row.target_id == order_id
        assert row.detail["before"] == "RECEIVED"
        assert row.detail["after"] == "MEASURE"
        assert "상태: 접수 → 실측" in row.message
        _assert_no_pii(row)


# --------------------------------------------------------------------------
# 4. 지방 메모 경로 — 내용 기록 + 무변경 중복 차단
# --------------------------------------------------------------------------
def test_regional_memo_records_content_change(app):
    """메모 변경이 '무엇에서 무엇으로'를 남긴다(운영 지적: 내용 표기 없음)."""
    with app.app_context():
        user_id = _make_user()
        order = _make_order(customer_name="김재민", is_regional=True)
        order_id = order.id
        client = _client(app, user_id)

        resp = client.post(
            "/api/update_regional_memo",
            json={"order_id": order_id, "memo": "7/22 해피콜 완료, 8/1 시공 예정"},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        row = _latest_log("ORDER_MEMO_UPDATED")
        assert row.target_id == order_id
        assert row.detail["after"] == "7/22 해피콜 완료, 8/1 시공 예정"
        assert row.detail["before"] == ""
        assert "메모: (없음) → 7/22 해피콜 완료, 8/1 시공 예정" in row.message
        assert f"지방 주문 #{order_id} (김재민)" in row.message
        _assert_no_pii(row)


def test_regional_memo_unchanged_save_writes_nothing(app):
    """같은 메모 재저장은 원장에 남기지 않는다.

    대시보드 자동저장이 디바운스(1초)와 blur 즉시저장으로 **두 번** 발사한다
    (운영 실측: 09:34:35·09:34:36 동일 내용 2건). 무변경 쓰기를 막아 원장 중복을 끊는다.
    """
    with app.app_context():
        user_id = _make_user()
        order = _make_order(customer_name="김재민", is_regional=True)
        order_id = order.id
        client = _client(app, user_id)

        first = client.post("/api/update_regional_memo",
                            json={"order_id": order_id, "memo": "중복 검증 메모"})
        assert first.status_code == 200

        db_session.expire_all()
        before_count = (
            db_session.query(SecurityLog)
            .filter(SecurityLog.action == "ORDER_MEMO_UPDATED")
            .count()
        )

        second = client.post("/api/update_regional_memo",
                             json={"order_id": order_id, "memo": "중복 검증 메모"})
        assert second.status_code == 200
        assert second.get_json().get("unchanged") is True

        db_session.expire_all()
        after_count = (
            db_session.query(SecurityLog)
            .filter(SecurityLog.action == "ORDER_MEMO_UPDATED")
            .count()
        )

    assert after_count == before_count, "무변경 재저장이 감사 원장에 또 쌓였다"


def test_regional_memo_audit_detail_is_capped(app):
    """긴 메모 원문 전량을 원장에 담지 않는다(원장은 본문 저장소가 아니다)."""
    with app.app_context():
        user_id = _make_user()
        order = _make_order(customer_name="김재민", is_regional=True)
        order_id = order.id
        client = _client(app, user_id)

        long_memo = "가" * 900
        resp = client.post("/api/update_regional_memo",
                           json={"order_id": order_id, "memo": long_memo})
        assert resp.status_code == 200

        row = _latest_log("ORDER_MEMO_UPDATED")
        assert len(row.detail["after"]) <= 200
        assert row.detail["after_len"] == 900
