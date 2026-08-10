"""AUDIT-LOG P4 C1: 업무 행위 커버리지 감사 기록 계약.

스펙: ``docs/specs/2026-08-08-audit-log-readability-coverage-design.md`` §3-3.

운영 실측이 드러낸 구멍: 쓰기 라우트 172개 중 102개(59%)가 감사 기록 0이었고, 남은
기록도 ``db.add(SecurityLog(f"주문 #4109 시공 완료"))`` 처럼 자유 텍스트라 SQL 로 물을 수
없었다(``action``·``target_id``·``detail`` 전부 NULL). 여기서 고정하는 것:

1. **행위 1건 = 원장 1행** — 결제 확인·시공·생산·AS·도면·파일 업로드/삭제.
2. **행위자·대상이 구조화로 남는다** — ``user_id``·``action``·``target_type='order'``·
   ``target_id``·``detail``.
3. **문장은 표시 SSOT 가 만든다** — 고객명이 문장에 병기되고, 라우트가 f-string 으로
   직접 조립하지 않는다(회귀 시 즉시 red).
4. **PII 최소성** — 연락처·주소는 감사 행에 싣지 않는다.
"""

from __future__ import annotations

import itertools
import pathlib
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderAttachment, SecurityLog, User

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_counter = itertools.count(1)
_PHONE = "010-7777-8888"
_ADDRESS = "서울시 감사구 커버리지로 99"


def _make_user(*, role: str = "ADMIN", team: str | None = None) -> int:
    """행위자 1명을 만들고 id 만 돌려준다(요청 teardown 후 detach 회피)."""
    n = next(_counter)
    user = User(username=f"p4-c1-{n}", password=generate_password_hash("pw"), role=role,
                team=team, name=f"작업자{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _make_order(*, stage: str = "RECEIVED", customer_name: str = "홍길동",
                structured_data: dict | None = None) -> Order:
    sd = {"workflow": {"stage": stage}}
    if structured_data:
        sd = {**sd, **structured_data}
        sd.setdefault("workflow", {})["stage"] = stage
    order = Order(received_date=date.today().isoformat(), customer_name=customer_name,
                  phone=_PHONE, address=_ADDRESS, product="붙박이장", status=stage,
                  manager_name="Bob", is_erp_order=True, structured_data=sd,
                  erp_stage_code=stage)
    db_session.add(order)
    db_session.commit()
    return order


def _logs(action: str, order_id: int) -> list[SecurityLog]:
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == action, SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.asc())
        .all()
    )


def _only_log(action: str, order_id: int) -> SecurityLog:
    """행위 1건이 원장 1행으로만 남았는지 확인하고 그 행을 돌려준다."""
    rows = _logs(action, order_id)
    assert len(rows) == 1, f"{action}: 원장 {len(rows)}행(1행이어야 한다)"
    return rows[0]


def _assert_structured(row: SecurityLog, *, action: str, order_id: int, user_id: int,
                       customer_name: str) -> None:
    """구조화 4종 + 행위자 + 문장 안 고객명 + PII 부재를 한 번에 고정한다."""
    assert row.action == action
    assert row.target_type == "order" and row.target_id == order_id
    assert row.user_id == user_id, "행위자가 없으면 '누가 했나'를 물을 수 없다"
    assert isinstance(row.detail, dict) and row.detail.get("customer_name") == customer_name
    assert f"#{order_id} ({customer_name})" in (row.message or ""), row.message
    blob = f"{row.message or ''} {row.detail or ''}"
    assert _PHONE not in blob and _ADDRESS not in blob, "감사 행에 PII 가 실렸다"


# --------------------------------------------------------------------------- #
# 1. 결제 — 확인 토글은 돈이 오갔다는 판단의 근거다
# --------------------------------------------------------------------------- #
def test_payment_confirm_is_recorded_with_payment_type(client):
    """예약금/잔금 확인이 종류와 함께 남는다(지금까지 기록 0건이었다)."""
    user_id = _make_user()
    _login(client, user_id)
    order_id = _make_order(customer_name="이영희").id

    resp = client.post(f"/api/orders/{order_id}/payment-confirm",
                       json={"type": "deposit", "confirmed": True})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    row = _only_log("PAYMENT_CONFIRMED", order_id)
    _assert_structured(row, action="PAYMENT_CONFIRMED", order_id=order_id,
                       user_id=user_id, customer_name="이영희")
    assert row.detail["payment_type"] == "deposit"
    assert "결제 확인: 예약금" in row.message


def test_payment_unconfirm_uses_a_distinct_action(client):
    """확인 해제는 확인과 다른 action 이다(되돌린 사실이 묻히면 안 된다)."""
    user_id = _make_user()
    _login(client, user_id)
    order_id = _make_order(customer_name="박민수").id

    assert client.post(f"/api/orders/{order_id}/payment-confirm",
                       json={"type": "balance", "confirmed": True}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/payment-confirm",
                       json={"type": "balance", "confirmed": False}).status_code == 200

    row = _only_log("PAYMENT_CONFIRM_CLEARED", order_id)
    assert row.detail["payment_type"] == "balance" and row.detail["confirmed"] is False
    assert "결제 확인 해제: 잔금" in row.message


# --------------------------------------------------------------------------- #
# 2. 시공
# --------------------------------------------------------------------------- #
def test_construction_start_and_complete_are_recorded(client):
    """시공 시작·완료가 각각 1행씩, 고객명과 함께 남는다."""
    user_id = _make_user(role="STAFF", team="CONSTRUCTION")
    _login(client, user_id)
    order_id = _make_order(stage="CONSTRUCTION", customer_name="최영수").id

    assert client.post(f"/api/orders/{order_id}/construction/start", json={}).status_code == 200
    start = _only_log("CONSTRUCTION_STARTED", order_id)
    _assert_structured(start, action="CONSTRUCTION_STARTED", order_id=order_id,
                       user_id=user_id, customer_name="최영수")
    assert "시공 시작" in start.message

    resp = client.post(f"/api/orders/{order_id}/construction/complete",
                       json={"completion_note": "마감 확인"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    done = _only_log("CONSTRUCTION_COMPLETED", order_id)
    assert done.detail["new_stage"] == "CS"
    assert "시공 완료: 마감 확인" in done.message


def test_construction_rework_records_the_reason(client):
    """시공 불가는 사유가 남는다(무엇 때문에 되돌렸는지가 핵심 정보)."""
    user_id = _make_user(role="STAFF", team="CONSTRUCTION")
    _login(client, user_id)
    order_id = _make_order(stage="CONSTRUCTION", customer_name="김철수").id
    assert client.post(f"/api/orders/{order_id}/construction/start", json={}).status_code == 200

    resp = client.post(f"/api/orders/{order_id}/construction/fail",
                       json={"reason": "drawing_error", "detail": "치수 불일치"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    row = _only_log("CONSTRUCTION_REWORK_REQUESTED", order_id)
    _assert_structured(row, action="CONSTRUCTION_REWORK_REQUESTED", order_id=order_id,
                       user_id=user_id, customer_name="김철수")
    assert row.detail["reason"] == "drawing_error" and row.detail["new_stage"] == "DRAWING"
    assert "시공 불가(재작업 요청): 도면 오류" in row.message


# --------------------------------------------------------------------------- #
# 3. 생산
# --------------------------------------------------------------------------- #
def test_production_start_and_complete_are_recorded(client):
    """제작 시작·완료가 구조화로 남는다."""
    user_id = _make_user(role="STAFF", team="PRODUCTION")
    _login(client, user_id)
    order_id = _make_order(stage="CONFIRM", customer_name="조혜리").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    start = _only_log("PRODUCTION_STARTED", order_id)
    _assert_structured(start, action="PRODUCTION_STARTED", order_id=order_id,
                       user_id=user_id, customer_name="조혜리")
    assert "제작 시작" in start.message

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    done = _only_log("PRODUCTION_COMPLETED", order_id)
    assert done.detail["new_stage"] == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 4. AS
# --------------------------------------------------------------------------- #
def test_as_start_and_complete_are_recorded(client):
    """AS 시작·완료가 각각 남고, 완료 메모가 문장에 붙는다."""
    user_id = _make_user(role="ADMIN", team="CS")
    _login(client, user_id)
    order_id = _make_order(stage="CS", customer_name="문지훈",
                           structured_data={"shipment": {}}).id
    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "문 흠집"}).status_code == 200

    started = client.post(f"/api/orders/{order_id}/as/start",
                          json={"reason": "문 흠집", "description": "경첩 교체 필요"})
    assert started.status_code == 200, started.get_data(as_text=True)
    start = _only_log("AS_STARTED", order_id)
    _assert_structured(start, action="AS_STARTED", order_id=order_id,
                       user_id=user_id, customer_name="문지훈")
    assert "AS 시작: 문 흠집" in start.message

    assert client.post(f"/api/orders/{order_id}/as/complete",
                       json={"note": "도어 교체 완료"}).status_code == 200
    done = _only_log("AS_COMPLETED", order_id)
    assert "AS 완료: 도어 교체 완료" in done.message


def test_as_log_append_is_recorded(client):
    """AS 기록 추가도 원장에 남는다(타임라인만 보고 누가 썼는지 묻지 않게)."""
    user_id = _make_user(role="ADMIN", team="CS")
    _login(client, user_id)
    order_id = _make_order(stage="CS", customer_name="서지우",
                           structured_data={"shipment": {}}).id
    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "고객 문의"}).status_code == 200

    resp = client.post(f"/api/orders/{order_id}/as/log",
                       json={"log_type": "note", "text": "고객 통화 완료"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    row = _only_log("AS_LOG_ADDED", order_id)
    _assert_structured(row, action="AS_LOG_ADDED", order_id=order_id,
                       user_id=user_id, customer_name="서지우")


# --------------------------------------------------------------------------- #
# 5. 파일 — 사고가 나면 가장 먼저 묻는 대상이다
# --------------------------------------------------------------------------- #
def _attachment(order_id: int, filename: str = "도면.png") -> OrderAttachment:
    attachment = OrderAttachment(
        order_id=order_id, filename=filename, file_type="image", category="drawing",
        file_size=10, storage_key=f"orders/{order_id}/{filename}",
    )
    db_session.add(attachment)
    db_session.commit()
    return attachment


def test_attachment_upload_and_delete_are_recorded(app, client):
    """첨부 업로드·삭제가 파일명과 함께 남는다(``order_events`` 와 별개로 보안 원장에도)."""
    from foms.api.files import order_routes

    user_id = _make_user()
    _login(client, user_id)
    order_id = _make_order(customer_name="한지민").id
    attachment_id = _attachment(order_id).id
    storage_key = f"orders/{order_id}/도면.png"

    with app.test_request_context("/"):
        from flask import session as flask_session

        flask_session["user_id"] = user_id
        attachment = db_session.get(OrderAttachment, attachment_id)
        order_routes.emit_attachment_event(db_session, attachment, order_routes.ATTACHMENT_ADDED)
        order_routes.emit_attachment_event(db_session, attachment, order_routes.ATTACHMENT_DELETED)
        db_session.commit()

    added = _only_log("FILE_UPLOADED", order_id)
    _assert_structured(added, action="FILE_UPLOADED", order_id=order_id,
                       user_id=user_id, customer_name="한지민")
    assert added.detail["filename"] == "도면.png"
    assert "파일 업로드: 도면.png" in added.message

    removed = _only_log("FILE_DELETED", order_id)
    assert removed.detail["storage_key"] == storage_key


def test_attachment_meta_update_is_not_recorded(app, client):
    """항목 재배치(META_UPDATED)까지 보안 원장에 넣지 않는다(원장 도배 방지)."""
    from foms.api.files import order_routes

    user_id = _make_user()
    _login(client, user_id)
    order_id = _make_order(customer_name="유서준").id
    attachment_id = _attachment(order_id).id

    with app.test_request_context("/"):
        from flask import session as flask_session

        flask_session["user_id"] = user_id
        attachment = db_session.get(OrderAttachment, attachment_id)
        order_routes.emit_attachment_event(db_session, attachment, "ATTACHMENT_META_UPDATED")
        db_session.commit()

    assert _logs("ATTACHMENT_META_UPDATED", order_id) == []
    assert _logs("FILE_UPLOADED", order_id) == []


# --------------------------------------------------------------------------- #
# 6. 배선 계약 — 새 경로가 옛 방식으로 되돌아가는 것을 막는다
# --------------------------------------------------------------------------- #
#: C1 에서 배선한 파일. 여기에 raw ``SecurityLog`` 쓰기가 다시 생기면 구조화가 깨진다.
_WIRED_PATHS = (
    "foms/api/erp_orders_structured.py",
    "foms/api/construction/orders.py",
    "foms/api/production/orders.py",
    "foms/api/cs/as_orders.py",
    "foms/api/drawing/erp_orders_drawing.py",
    "foms/api/erp_orders_blueprint.py",
    "foms/api/files/order_routes.py",
)


def test_wired_paths_do_not_write_security_log_directly():
    """``db.add(SecurityLog(...))`` 직접 쓰기 금지 — 구조화 컬럼이 통째로 비게 된다."""
    offenders = [
        path for path in _WIRED_PATHS
        if "SecurityLog(" in (_REPO_ROOT / path).read_text(encoding="utf-8")
    ]
    assert not offenders, f"raw SecurityLog 쓰기가 남아 있다: {offenders}"


def test_wired_paths_build_sentences_with_the_display_ssot():
    """행위 문장은 표시 SSOT 가 만든다(라우트 f-string 조립 금지)."""
    missing = [
        path for path in _WIRED_PATHS
        if "describe_order_action" not in (_REPO_ROOT / path).read_text(encoding="utf-8")
    ]
    assert not missing, f"문장 SSOT 를 쓰지 않는 경로: {missing}"


def test_wired_paths_record_structured_target():
    """행위 기록은 대상(``target_type='order'``)을 함께 남긴다."""
    for path in _WIRED_PATHS:
        source = (_REPO_ROOT / path).read_text(encoding="utf-8")
        assert 'target_type="order"' in source or "target_type='order'" in source, (
            f"{path}: target_type 미기록"
        )
