"""AS overlay 보호 + 상태 이전값 감사 — 2026-08-14 일괄 완료처리 사고 회귀 가드.

사고: 「단계 강제 변경」·주문 일괄 상태변경이 AS 접수/완료 주문의 ``status`` 를
``COMPLETED`` 로 덮어써 AS 대시보드에서 55건이 사라졌다(기록은 남고 목록 술어만 status).
게다가 ``STAGE_OVERRIDE`` payload 의 ``from`` 은 workflow.stage 라 status 이전값이 남지
않아 복구 근거가 부족했다.

가드 3종:
1. 일괄 경로는 AS overlay 주문을 기본 제외하고 경고를 돌려준다.
2. ``include_as: true`` 명시 opt-in 이면 통과한다(사람이 알고 누른 경우).
3. 단계 강제 변경은 status 이전값을 payload + security_logs 로 남긴다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, SecurityLog, User
from foms.services.orders.stage_override import AS_OVERLAY_STATUSES, as_overlay_status


def _login(client, username: str, role: str = "ADMIN") -> User:
    """테스트 사용자 생성 + 세션 로그인."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_order(*, status: str, stage: str = "MEASURE", is_erp: bool = True) -> Order:
    """AS overlay status + 메인 stage 를 동시에 가진 ERP 주문(사고 재현 형태).

    ``is_erp=False`` 는 메인 파이프라인 밖 레거시 주문 — 완료 경로 일원화(C-B2)의
    거부 술어에 들어가지 않아 일괄 변경이 그대로 통한다(대조군용).
    """
    order = Order(
        received_date="2026-08-01",
        customer_name="AS-고객",
        phone="010-3333-4444",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Mgr",
        is_erp_order=is_erp,
        as_received_date="2026-08-14" if status in AS_OVERLAY_STATUSES else None,
        structured_data={"workflow": {"stage": stage}} if is_erp else None,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_overlay_status_unit(client):
    """status 기준 판정 — workflow.stage 가 메인 코드여도 AS 를 놓치지 않는다."""
    assert as_overlay_status(_make_order(status="AS_RECEIVED")) == "AS_RECEIVED"
    assert as_overlay_status(_make_order(status="AS_COMPLETED")) == "AS_COMPLETED"
    assert as_overlay_status(_make_order(status="DRAWING", stage="DRAWING")) == ""


def test_bulk_stage_override_excludes_as_orders(client):
    """일괄 단계 강제 변경: AS 주문은 제외되고 경고가 온다.

    2026-09-21(ADMIN-OVERRIDE-01)부터 COMPLETED 목표는 CS 완료 경로 소관이라, AS 제외
    가드 자체를 재는 이 테스트는 메인 단계(시공)로 목표를 옮겼다. 사고 재현 차단이 핵심이다.
    """
    _login(client, "as_guard_mgr", role="MANAGER")
    as_order = _make_order(status="AS_RECEIVED")
    plain = _make_order(status="DRAWING", stage="DRAWING")
    as_id, plain_id = as_order.id, plain.id

    # 목표는 메인 단계(시공)다 — COMPLETED 목표는 2026-09-21(ADMIN-OVERRIDE-01)부터 CS 완료
    # 경로로 가므로, AS 제외 가드 자체를 재려면 완료가 아닌 메인 목표로 재야 한다.
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [as_id, plain_id],
            "to_stage": "CONSTRUCTION",
            "reason": "시공 단계로 정리",
            "confirm": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["updated"] == 1
    assert [item["order_id"] for item in data["skipped_as"]] == [as_id]
    assert "AS" in data["warning"]

    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "AS_RECEIVED"  # 사고 재현 차단
    assert db_session.get(Order, plain_id).status == "CONSTRUCTION"


def test_bulk_stage_override_all_as_returns_400(client):
    """대상이 전부 AS 면 아무것도 바꾸지 않고 400 으로 알린다."""
    _login(client, "as_guard_mgr2", role="MANAGER")
    as_id = _make_order(status="AS_COMPLETED").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={"order_ids": [as_id], "to_stage": "COMPLETED", "reason": "완료", "confirm": True},
    )
    assert resp.status_code == 400
    assert "AS" in resp.get_json()["error"]
    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "AS_COMPLETED"


def test_bulk_stage_override_include_as_opt_in(client):
    """include_as: true 는 명시 opt-in — 그때만 AS 주문의 단계도 바뀐다.

    2026-11-20(설계서 multi-item-split-schedule §4.3, M6): 열린 AS(접수 · 처리 중)는 단계만 옮기고 주문 상태의
    AS 표시는 그대로 둔다. 닫힌 AS(완료)는 지금처럼 상태 글까지 덮인다(대조군).
    """
    _login(client, "as_guard_mgr3", role="MANAGER")
    as_id = _make_order(status="AS_RECEIVED").id
    done_id = _make_order(status="AS_COMPLETED").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [as_id, done_id], "to_stage": "CONSTRUCTION", "reason": "정말 시공으로",
            "confirm": True, "include_as": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["updated"] == 2
    kept = {item["order_id"]: item.get("as_overlay_kept") for item in data["results"]}
    assert kept == {as_id: "AS_RECEIVED", done_id: None}
    db_session.expire_all()
    opened, closed = db_session.get(Order, as_id), db_session.get(Order, done_id)
    assert opened.status == "AS_RECEIVED" and opened.structured_data["workflow"]["stage"] == "CONSTRUCTION"
    assert closed.status == "CONSTRUCTION" and closed.structured_data["workflow"]["stage"] == "CONSTRUCTION"


def test_stage_override_records_previous_status(client):
    """단건 강제 변경이 status 이전값을 이벤트 payload + 감사행에 남긴다.

    열린 AS 는 상태 글이 그대로라 ``as_overlay_kept`` 로 남기고, 닫힌 AS(완료)를 덮은 흔적은 ``from_status`` 가 남긴다.
    """
    _login(client, "as_guard_mgr4", role="MANAGER")
    as_id = _make_order(status="AS_RECEIVED").id
    done_id = _make_order(status="AS_COMPLETED").id

    for oid in (as_id, done_id):
        resp = client.post(
            f"/api/orders/{oid}/workflow/stage-override",
            json={"to_stage": "CONSTRUCTION", "reason": "AS 종결 후 시공 복귀", "confirm": True},
        )
        assert resp.status_code == 200, resp.get_json()

    def _event(oid: int) -> OrderEvent:
        return (db_session.query(OrderEvent)
                .filter(OrderEvent.order_id == oid, OrderEvent.event_type == "STAGE_OVERRIDE").one())

    def _log(oid: int) -> SecurityLog:
        return (db_session.query(SecurityLog)
                .filter(SecurityLog.target_id == oid, SecurityLog.action == "ORDER_STATUS_CHANGED").one())

    ev = _event(as_id)
    assert ev.payload["from_status"] == "AS_RECEIVED" and ev.payload["to"] == "CONSTRUCTION"
    assert ev.payload["as_overlay_kept"] == "AS_RECEIVED" and "as_overlay_cleared" not in ev.payload
    log = _log(as_id)
    assert log.detail["before"] == "AS_RECEIVED" and log.detail["after"] == "AS_RECEIVED"
    assert log.detail["as_overlay_kept"] == "AS_RECEIVED" and log.detail["stage_override"] is True

    closed = _event(done_id)  # 대조군: 닫힌 AS 는 덮이고, 이전 상태는 from_status 에 남는다
    assert closed.payload["from_status"] == "AS_COMPLETED" and "as_overlay_kept" not in closed.payload
    assert _log(done_id).detail["before"] == "AS_COMPLETED" and _log(done_id).detail["after"] == "CONSTRUCTION"


def test_bulk_status_api_excludes_as_orders(client):
    """주문 일괄 상태변경(status API)도 AS 주문을 제외하고 사유를 알려준다.

    2026-09-20(C-B2)부터 메인 파이프라인 ERP 주문의 COMPLETED 직접 저장은 따로 막히므로
    (``blocked_use_cs_complete``), 이 테스트의 '통과하는 주문' 은 메인 축 밖 레거시 주문이다.
    AS 제외 가드 자체는 그대로다 — 사고 재현 차단이 이 테스트의 핵심이다.
    """
    _login(client, "as_guard_admin", role="ADMIN")
    as_id = _make_order(status="AS_RECEIVED").id
    cs_id = _make_order(status="CS", stage="CS").id  # 메인 파이프라인 → CS 완료 경로 소관
    legacy_id = _make_order(status="SCHEDULED", is_erp=False).id

    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [as_id, cs_id, legacy_id], "status": "COMPLETED"},
    )
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert [item["order_id"] for item in payload["blocked_as_orders"]] == [as_id]
    assert payload["blocked_use_cs_complete"] == [cs_id]
    assert payload["updated"] == 1
    assert "AS" in payload["message"]

    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "AS_RECEIVED"
    assert db_session.get(Order, cs_id).status == "CS"
    assert db_session.get(Order, legacy_id).status == "COMPLETED"


def test_bulk_status_api_allows_as_target(client):
    """AS 상태로 바꾸는 일괄 작업은 막지 않는다(AS 대시보드 안에서의 이동)."""
    _login(client, "as_guard_admin2", role="ADMIN")
    as_id = _make_order(status="AS_RECEIVED").id
    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [as_id], "status": "AS_COMPLETED"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["updated"] == 1
    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "AS_COMPLETED"


def test_split_keeps_as_orders_for_as_targets(client):
    """AS 3종 목표의 일괄 변경은 include_as 없이도 AS overlay 주문을 대상에 넣는다.

    제외 근거가 "AS 표시가 사라진다" 인데 AS 목표는 AS 축 자체를 다루므로 그 사고가
    성립하지 않는다. 메인 목표에서는 그대로 제외된다(같은 입력으로 재는 음성 대조군).
    """
    from foms.api.orders.stage_override_targets import (
        KIND_AS,
        KIND_MAIN,
        split_override_targets,
    )

    as_order = _make_order(status="AS_COMPLETED")
    plain = _make_order(status="DRAWING", stage="DRAWING")

    change, skipped, skipped_as = split_override_targets(
        [as_order, plain], "AS_RECEIVED", KIND_AS,
    )
    assert [int(o.id) for o in change] == [int(as_order.id), int(plain.id)]
    assert skipped == [] and skipped_as == []

    change_main, _, skipped_as_main = split_override_targets(
        [as_order, plain], "CONSTRUCTION", KIND_MAIN,
    )
    assert [int(o.id) for o in change_main] == [int(plain.id)]
    assert [item["order_id"] for item in skipped_as_main] == [int(as_order.id)]
