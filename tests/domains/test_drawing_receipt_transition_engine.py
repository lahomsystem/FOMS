"""도면 수령 확정이 STATE-CORE 전이 엔진 한 경로만 탄다는 계약 (C-C1, 2026-09-20).

2026-09-20 까지 이 라우트는 ``workflow.stage`` 와 ``order.status`` 를 직접 써서 버전·영수증·
전이 이벤트가 남지 않았고, 전달된 도면이 도면 단계 밖에서 확정되면 단계를 CONFIRM 으로
조용히 되돌렸다. 여기서 다음을 고정한다.

* 도면 단계 확정 = DRAWING→CONFIRM 전이(버전 증가·영수증 1건·이벤트 2종).
* 재요청은 기존 drawing_status 가드가 400 으로 잡는다(대조군 — 멱등 replay 분기 없음).
* 단계가 도면이 아니면 전이를 건너뛰고 도면 축만 확정한다(단계 역행 0).
* 전이가 실패하면 도면 파일 정리가 일어나지 않는다(순서 계약).
"""

from __future__ import annotations

from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, OrderMutationReceipt, SecurityLog, User

_TRANSFERRED_SD = {
    "parties": {"customer": {"name": "고객"}, "manager": {"name": "담당"}},
    "drawing_status": "TRANSFERRED",
    "drawing_current_files": [{"key": "orders/1/final.pdf", "name": "final.pdf"}],
    "drawing_transfer_history": [{"action": "TRANSFER", "files": []}],
}


def _make_user(username: str, *, role: str = "ADMIN", team: str | None = "SALES") -> User:
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


def _make_order(stage: str) -> Order:
    sd = {**{k: list(v) if isinstance(v, list) else v for k, v in _TRANSFERRED_SD.items()},
          "workflow": {"stage": stage}}
    order = Order(received_date=date.today().isoformat(), customer_name="도면 고객",
                  phone="010-0000-0000", address="서울", product="붙박이장", status=stage,
                  manager_name="담당", is_erp_order=True, structured_data=sd,
                  erp_stage_code=stage)
    db_session.add(order)
    db_session.commit()
    return order


def _events(order_id: int, event_type: str) -> int:
    return db_session.query(OrderEvent).filter_by(order_id=order_id, event_type=event_type).count()


def test_도면_단계_수령_확정은_엔진_전이로_CONFIRM_까지_간다(client):
    _login(client, _make_user("dr_engine_admin"))
    oid = _make_order("DRAWING").id

    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["success"] is True and body["stage_moved"] is True
    assert body["new_stage"] == "CONFIRM"

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["workflow"]["stage"] == "CONFIRM"
    assert saved.erp_stage_code == "CONFIRM"
    assert saved.structured_data["drawing_status"] == "CONFIRMED"
    assert saved.mutation_version == 2  # 신규 주문 기본 1 → 전이 1회 = 1회만 증가
    assert db_session.query(OrderMutationReceipt).filter_by(
        policy_id="STATE_DRAWING_RECEIPT_CONFIRM").count() == 1
    assert _events(oid, "DRAWING_RECEIPT_CONFIRMED") == 1
    assert _events(oid, "DRAWING_STATUS_CHANGED") == 1


def test_대조군_재요청은_기존_도면_가드가_400_으로_잡고_상태는_그대로다(client):
    _login(client, _make_user("dr_engine_admin2"))
    oid = _make_order("DRAWING").id
    assert client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={}).status_code == 200

    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert res.status_code == 400
    assert "전달된 도면" in res.get_json()["message"]

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["workflow"]["stage"] == "CONFIRM"
    assert saved.mutation_version == 2  # 두 번째 요청은 전이도 버전 증가도 없다
    assert _events(oid, "DRAWING_RECEIPT_CONFIRMED") == 1


def test_대조군_도면_단계가_아니면_단계를_되돌리지_않고_도면_축만_확정한다(client):
    """재전달된 도면이 생산 단계에서 확정되는 실제 경로 — 조용한 단계 역행 0."""
    _login(client, _make_user("dr_engine_admin3"))
    oid = _make_order("PRODUCTION").id

    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["stage_moved"] is False and body["new_stage"] == "PRODUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["workflow"]["stage"] == "PRODUCTION"  # 역행 0
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.structured_data["drawing_status"] == "CONFIRMED"
    assert saved.mutation_version == 1  # 전이 없음 = 버전 불변(기본 1)
    assert _events(oid, "DRAWING_RECEIPT_CONFIRMED") == 0
    assert _events(oid, "DRAWING_STATUS_CHANGED") == 1
    assert any("단계 유지" in (row.message or "")
               for row in db_session.query(SecurityLog).all())


def test_대조군_권한_없는_사용자는_403_이고_상태가_바뀌지_않는다(client):
    outsider = _make_user("dr_engine_outsider", role="STAFF", team="SALES")
    order = _make_order("DRAWING")
    order.manager_name = "다른담당"
    db_session.commit()
    oid = order.id

    _login(client, outsider)
    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert res.status_code == 403

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert saved.structured_data["drawing_status"] == "TRANSFERRED"
    assert saved.mutation_version == 1  # 거부 = 버전 불변(기본 1)


def test_전이가_실패하면_도면_파일_정리가_일어나지_않는다(client, monkeypatch):
    """파일 정리는 전이 뒤 — 전이 예외는 rollback 이라 drawing_current_files 가 보존된다."""
    import foms.api.drawing.erp_orders_draftsman as draftsman
    from foms.services.orders.order_transition_service import StageConflictError

    _login(client, _make_user("dr_engine_admin4"))
    oid = _make_order("DRAWING").id

    def _boom(*args, **kwargs):
        raise StageConflictError("main", "DRAWING", "PRODUCTION")

    monkeypatch.setattr(draftsman, "advance_receipt_stage", _boom)
    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert res.status_code == 409
    assert res.get_json()["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["drawing_current_files"] == [
        {"key": "orders/1/final.pdf", "name": "final.pdf"}]
    assert saved.structured_data["drawing_status"] == "TRANSFERRED"
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"


def test_단계_유지_경로의_이력_시각은_옛_전이_시각이_아니라_이번_요청_시각이다(client):
    """drift 경로(stage_moved False) 이력 행이 오래전 stage_updated_at 을 베끼면 안 된다.

    단계 축 타임스탬프는 전이 엔진만 쓴다 — 라우트는 읽기만 하고, 이력 행에는 이번
    요청 시각을 적는다. 그러지 않으면 "오늘 확정한 일" 이 몇 달 전 기록처럼 보인다.
    """
    from foms.services.datetime_kst import now_utc_naive

    _login(client, _make_user("dr_history_at"))
    order = _make_order("PRODUCTION")
    stale = "2020-01-01T00:00:00"
    sd = {**order.structured_data}
    sd["workflow"] = {"stage": "PRODUCTION", "stage_updated_at": stale}
    order.structured_data = sd
    db_session.commit()
    oid = order.id

    before = now_utc_naive().isoformat()
    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["stage_moved"] is False

    db_session.expire_all()
    wf = db_session.get(Order, oid).structured_data["workflow"]
    row = wf["history"][-1]
    assert row["updated_at"] != stale
    assert row["updated_at"] >= before
    # 단계 축 타임스탬프 자체는 라우트가 건드리지 않는다(전이 엔진 소유).
    assert wf["stage_updated_at"] == stale


def test_단계_이동_경로의_이력_시각은_전이가_넣은_시각과_같다(client):
    """대조군 — 실제로 단계가 옮겨 갔으면 이력 행과 단계 축이 같은 순간을 가리킨다."""
    _login(client, _make_user("dr_history_at_moved"))
    oid = _make_order("DRAWING").id

    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["stage_moved"] is True

    db_session.expire_all()
    wf = db_session.get(Order, oid).structured_data["workflow"]
    assert wf["history"][-1]["updated_at"] == wf["stage_updated_at"]
