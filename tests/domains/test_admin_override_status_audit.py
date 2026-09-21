"""일반 화면 경로(상태 변경·필드 변경)의 뚫기 감사와 전건 롤백 (ADMIN-OVERRIDE-01 W2).

두 가지를 본다.

1. **전건 롤백**: 일괄 강제 완료는 한 건이 실패하면 앞 건도 커밋되지 않는다. 전이 실패는
   세션 전체를 되감으므로, 실패 뒤 루프를 계속하면 앞 건의 변경이 사라진 채 ``updated``
   만 올라가 화면이 거짓말한다.
2. **감사 대칭**: 뚫어서 완료한 건도 평소 건과 **같은 감사행**을 남긴다. 한쪽만 남기면
   감사 원장이 실제 변경보다 적게 센다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, SecurityLog, User


def _login(client, username: str, role: str = "ADMIN") -> int:
    """테스트용 사용자를 만들고 세션에 로그인시킨 뒤 user id 를 돌려준다."""
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team="CS", name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    user_id = int(user.id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role
    return user_id


def _make_erp(*, status: str, stage: str) -> int:
    """메인 파이프라인 위에 깨끗이 올라와 있는 ERP 주문 1건의 id."""
    order = Order(
        received_date="2026-09-01", customer_name="강제진행-고객", phone="010-7777-8888",
        address="Seoul", product="붙박이장", status=status, manager_name="Mgr",
        is_erp_order=True, structured_data={"workflow": {"stage": stage}},
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _reload(order_id: int) -> Order:
    """현재 커밋된 주문 상태를 다시 읽는다."""
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _override_events(order_id: int) -> list:
    """주문에 남은 ``ADMIN_OVERRIDE_USED`` 이벤트 전부."""
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id,
                OrderEvent.event_type == "ADMIN_OVERRIDE_USED")
        .all()
    )


def _denied_logs(order_id: int) -> list:
    """거부된 뚫기 시도가 남긴 감사행(``ADMIN_OVERRIDE_DENIED``)."""
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ADMIN_OVERRIDE_DENIED",
                SecurityLog.target_id == order_id)
        .all()
    )


def _status_audit_logs(order_id: int) -> list:
    """상태 변경 감사행(``ORDER_STATUS_CHANGED``) — 뚫기 건도 평소 건과 같이 남아야 한다."""
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ORDER_STATUS_CHANGED",
                SecurityLog.target_id == order_id)
        .all()
    )


def test_일괄_강제_완료는_한_건이_실패하면_앞_건도_커밋되지_않는다(client, monkeypatch):
    """음성 대조군 — 부분 성공을 보고하지 않는다(전건 롤백 + 오류 응답)."""
    from flask import jsonify

    from foms.api.orders import status as status_module

    _login(client, "ov_bulk_cs_fail")
    first = _make_erp(status="CS", stage="CS")
    second = _make_erp(status="CS", stage="CS")

    real_complete = status_module.complete_order_as_cs
    calls = {"n": 0}

    def _flaky(db, order, **kwargs):
        """두 번째 주문에서만 전이 실패를 흉내 낸다(세션 전체를 되감는다)."""
        calls["n"] += 1
        if calls["n"] == 1:
            return real_complete(db, order, **kwargs)
        db.rollback()
        return jsonify({"success": False, "code": "INVALID_STAGE",
                        "message": "두 번째 건은 전이가 거부됐다"}), 409

    monkeypatch.setattr(status_module, "complete_order_as_cs", _flaky)

    resp = client.post(
        "/api/bulk_update_order_status",
        json={
            "order_ids": [first, second],
            "status": "COMPLETED",
            "admin_override": True,
            "override_reason": "일괄 강제 완료",
        },
    )

    assert calls["n"] == 2
    assert resp.status_code == 409, resp.get_json()
    assert "updated" not in resp.get_json()
    assert _reload(first).status == "CS"
    assert _reload(second).status == "CS"
    assert _override_events(first) == []
    assert _override_events(second) == []


def test_필드_변경의_거부된_뚫기도_감사_원장에_남는다(client):
    """음성 — STAFF 의 ``admin_override`` 는 403 이고, 그 시도가 원장에 1행 남는다."""
    _login(client, "ov_field_denied", role="STAFF")
    order_id = _make_erp(status="CS", stage="CS")

    resp = client.post(
        "/api/update_order_field",
        json={
            "order_id": order_id,
            "field": "status",
            "value": "COMPLETED",
            "admin_override": True,
            "override_reason": "내가 하고 싶다",
        },
    )

    assert resp.status_code == 403, resp.get_json()
    assert resp.get_json()["code"] == "ADMIN_ONLY"
    denied = _denied_logs(order_id)
    assert len(denied) == 1
    assert (denied[0].detail or {}).get("route") == "orders.update_order_field"
    assert _reload(order_id).status == "CS"


def test_필드_변경으로_강제_완료해도_평소와_같은_감사행이_남는다(client):
    """뚫기 건만 감사에서 빠지면 원장이 실제 변경보다 적게 센다."""
    _login(client, "ov_field_complete")
    order_id = _make_erp(status="CS", stage="CS")

    resp = client.post(
        "/api/update_order_field",
        json={
            "order_id": order_id,
            "field": "status",
            "value": "COMPLETED",
            "admin_override": True,
            "override_reason": "고객 요청으로 잔여 절차 생략",
        },
    )

    assert resp.status_code == 200, resp.get_json()
    assert _reload(order_id).status == "COMPLETED"
    assert len(_override_events(order_id)) == 1
    audits = _status_audit_logs(order_id)
    assert len(audits) == 1
    assert (audits[0].detail or {}).get("after") == "COMPLETED"


def test_단건_상태_변경으로_강제_완료해도_평소와_같은_감사행이_남는다(client):
    """단건 상태 경로의 뚫기 완료 분기도 일괄과 같은 감사 헬퍼를 쓴다."""
    _login(client, "ov_status_complete")
    order_id = _make_erp(status="CS", stage="CS")

    resp = client.post(
        "/api/update_order_status",
        json={
            "order_id": order_id,
            "status": "COMPLETED",
            "admin_override": True,
            "override_reason": "고객 요청으로 잔여 절차 생략",
        },
    )

    assert resp.status_code == 200, resp.get_json()
    assert _reload(order_id).status == "COMPLETED"
    assert len(_override_events(order_id)) == 1
    audits = _status_audit_logs(order_id)
    assert len(audits) == 1
    assert (audits[0].detail or {}).get("after") == "COMPLETED"
