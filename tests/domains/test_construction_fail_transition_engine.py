"""시공 불가(재작업)가 STATE-CORE 전이 엔진 한 경로만 탄다는 계약 (C-C2, 2026-09-20).

2026-09-20 까지 이 라우트는 ``execute_order_mutation`` 클로저 안에서 ``workflow.stage`` 와
``order.status`` 를 직접 썼고 changed-family 를 빈 리스트로 돌려 캐시 무효화가 없었으며,
expected-from 검사도 없어 시공중이 아닌 주문도 되돌렸다. 여기서 다음을 고정한다.

* 사유 4종이 각각 목표 단계에 닿고, 버전은 1회만 오르며 영수증도 1건뿐이다(이중 방지).
* 전이 이벤트 ``CONSTRUCTION_REWORKED`` 는 1건이다(엔진 것 하나 — 라우트 중복 발행 0).
* 시공중이 아니면 단계 충돌 409(``INVALID_STAGE``)이고 상태는 그대로다.
* attempt 봉인·시공 불가 이력·재예약은 전이 뒤 같은 tx 에서 그대로 남는다.
* 과거에 이미 REWORKED 된 attempt 는 불변이다(대조군).
"""

from __future__ import annotations

from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import (
    Order,
    OrderConstructionAttempt,
    OrderEvent,
    OrderMutationReceipt,
    User,
)


def _make_user(username: str, *, role: str = "STAFF", team: str = "CONSTRUCTION") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(stage: str = "CONSTRUCTION") -> Order:
    order = Order(received_date=date.today().isoformat(), customer_name="시공 고객",
                  phone="010-0000-0000", address="서울", product="붙박이장", status=stage,
                  manager_name="담당", is_erp_order=True,
                  structured_data={"workflow": {"stage": stage}}, erp_stage_code=stage)
    db_session.add(order)
    db_session.commit()
    return order


def _receipts(order_id: int) -> int:
    return (db_session.query(OrderMutationReceipt)
            .filter(OrderMutationReceipt.policy_id == "STATE_CONSTRUCTION_REWORK")
            .count())


@pytest.mark.parametrize("reason,target", [
    ("drawing_error", "DRAWING"),
    ("measurement_error", "MEASURE"),
    ("product_defect", "PRODUCTION"),
    ("site_issue", "CONSTRUCTION"),
])
def test_사유_4종이_각각_목표_단계에_닿고_버전과_영수증은_1회뿐이다(client, reason, target):
    _login(client, _make_user(f"cf_{reason}"))
    order = _make_order()
    oid = order.id
    base_version = order.mutation_version

    res = client.post(f"/api/orders/{oid}/construction/fail",
                      json={"reason": reason, "detail": "현장 사유"})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["new_status"] == target

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["workflow"]["stage"] == target
    assert saved.erp_stage_code == target
    assert saved.mutation_version == base_version + 1  # 이중 버전 증가 0
    assert _receipts(oid) == 1  # 이중 영수증 0(execute_order_mutation 중첩 없음)
    assert db_session.query(OrderEvent).filter_by(
        order_id=oid, event_type="CONSTRUCTION_REWORKED").count() == 1
    assert saved.structured_data["construction_fail_history"][0]["reason"] == reason


def test_시공중이_아니면_단계_충돌_409_이고_상태가_그대로다(client):
    _login(client, _make_user("cf_stage_guard"))
    order = _make_order("PRODUCTION")
    oid = order.id
    base_version = order.mutation_version

    res = client.post(f"/api/orders/{oid}/construction/fail",
                      json={"reason": "drawing_error", "detail": "치수"})
    assert res.status_code == 409
    assert res.get_json()["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["workflow"]["stage"] == "PRODUCTION"
    assert saved.mutation_version == base_version
    assert "construction_fail_history" not in saved.structured_data
    assert db_session.query(OrderEvent).filter_by(
        order_id=oid, event_type="CONSTRUCTION_REWORKED").count() == 0


def test_attempt_봉인과_재예약은_전이_뒤에도_그대로_남는다(client):
    _login(client, _make_user("cf_side_effects"))
    oid = _make_order().id
    assert client.post(f"/api/orders/{oid}/construction/start", json={}).status_code == 200
    db_session.expire_all()
    attempt_id = (db_session.query(OrderConstructionAttempt)
                  .filter_by(order_id=oid, is_current=True).first().id)

    res = client.post(f"/api/orders/{oid}/construction/fail",
                      json={"reason": "site_issue", "detail": "현장 재방문",
                            "reschedule_date": "2026-10-05"})
    assert res.status_code == 200, res.get_json()

    db_session.expire_all()
    sealed = db_session.get(OrderConstructionAttempt, attempt_id)
    assert sealed.status == "REWORKED" and sealed.is_current is False
    assert sealed.fail_reason == "site_issue" and sealed.fail_detail == "현장 재방문"

    saved = db_session.get(Order, oid)
    schedule = saved.structured_data["schedule"]["construction"]
    assert schedule["date"] == "2026-10-05" and schedule["rescheduled"] is True
    assert saved.structured_data["workflow"]["rework_reason"] == "site_issue"
    notes = [h.get("note", "") for h in saved.structured_data["workflow"]["history"]]
    assert any("시공 불가" in note for note in notes)


def test_대조군_이미_REWORKED_된_과거_attempt_는_불변이다(client):
    _login(client, _make_user("cf_past_attempt"))
    oid = _make_order().id
    past = OrderConstructionAttempt(order_id=oid, status="REWORKED", is_current=False,
                                    fail_reason="drawing_error", fail_detail="예전 사유",
                                    evidence={"before": [], "after": [11]})
    db_session.add(past)
    db_session.commit()
    past_id = past.id

    res = client.post(f"/api/orders/{oid}/construction/fail",
                      json={"reason": "product_defect", "detail": "새 사유"})
    assert res.status_code == 200, res.get_json()

    db_session.expire_all()
    untouched = db_session.get(OrderConstructionAttempt, past_id)
    assert untouched.fail_reason == "drawing_error"  # 과거 terminal attempt 덮어쓰기 0
    assert untouched.fail_detail == "예전 사유"
    assert untouched.evidence == {"before": [], "after": [11]}


def test_같은_키로_다시_보내도_이력과_attempt_는_한_번만_남는다(client):
    """멱등 replay — 같은 Idempotency-Key 재전송은 전이도 부수효과도 다시 쓰지 않는다."""
    _login(client, _make_user("cf_idem"))
    oid = _make_order().id
    assert client.post(f"/api/orders/{oid}/construction/start", json={}).status_code == 200

    headers = {"Idempotency-Key": "cf-replay-1"}
    body = {"reason": "product_defect", "detail": "문짝 파손"}
    first = client.post(f"/api/orders/{oid}/construction/fail", json=body, headers=headers)
    assert first.status_code == 200, first.get_json()
    second = client.post(f"/api/orders/{oid}/construction/fail", json=body, headers=headers)
    assert second.status_code == 200, second.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert len(saved.structured_data["construction_fail_history"]) == 1
    assert _receipts(oid) == 1
    attempts = (db_session.query(OrderConstructionAttempt)
                .filter_by(order_id=oid, status="REWORKED").all())
    assert len(attempts) == 1


def test_전이_이벤트에_사유_라벨과_상세가_함께_실린다(client):
    """타임라인이 '무엇 때문에 되돌렸는가' 를 이벤트 하나로 말할 수 있어야 한다."""
    from models import SecurityLog

    _login(client, _make_user("cf_payload"))
    oid = _make_order().id
    assert client.post(f"/api/orders/{oid}/construction/start", json={}).status_code == 200

    res = client.post(f"/api/orders/{oid}/construction/fail",
                      json={"reason": "measurement_error", "detail": "좌측 폭 20mm 오차"})
    assert res.status_code == 200, res.get_json()

    db_session.expire_all()
    event = (db_session.query(OrderEvent)
             .filter_by(order_id=oid, event_type="CONSTRUCTION_REWORKED").one())
    assert event.payload["reason"] == "실측 오류: 좌측 폭 20mm 오차"
    assert event.payload["to"] == "MEASURE"

    # 감사 detail 에는 봉인한 attempt id 가 남아 이력과 이어진다.
    sealed = (db_session.query(OrderConstructionAttempt)
              .filter_by(order_id=oid, status="REWORKED").one())
    log = (db_session.query(SecurityLog)
           .filter(SecurityLog.action == "CONSTRUCTION_REWORK_REQUESTED",
                   SecurityLog.target_id == oid)
           .one())
    assert log.detail["attempt_id"] == sealed.id


def test_타임라인_라벨에_시공_불가가_등재돼_있다():
    """라벨 미등재면 타임라인이 '기타 변경' 으로 뜬다(사람이 못 읽는다)."""
    from foms.services.order_event_display import translate_event_type_to_korean

    assert translate_event_type_to_korean("CONSTRUCTION_REWORKED") == "시공 불가"
