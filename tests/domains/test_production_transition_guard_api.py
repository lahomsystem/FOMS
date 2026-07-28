"""생산 전이 전제조건 가드 계약 (P1).

- 제작 시작(POST /api/orders/<id>/production/start): 제작대기(고객컨펌/CONFIRM)에서만 허용.
  그 외 stage → 409 + code=INVALID_STAGE, message 키, 상태 불변.
- 제작 완료(POST /api/orders/<id>/production/complete): 제작중(생산/PRODUCTION)에서만 허용.
- 레거시 한글 stage 값('생산' 등)도 허용 목록에 포함.
- 시트 풋터 조건 렌더: stage/is_sales_approved 분기(제작중 → 생산 완료, 제작대기 미승인 → 고객 컨펌 전).

fixture/클라이언트 패턴은 test_production_hold_api.py 를 준용한다.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _make_user(username: str, *, role: str = "ADMIN", team: str | None = None) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(stage_code: str) -> Order:
    """지정한 erp_stage_code 로 ERP 주문 1건 생성. workflow.stage 도 동기화."""
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="전이 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage_code}},
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _make_order_with_hold(stage_code: str, *, reason: str = "자재 입고 지연") -> Order:
    """보류(hold active) 상태의 ERP 주문 생성. workflow.stage 도 동기화."""
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="보류 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": stage_code},
            "production": {
                "hold": {
                    "active": True,
                    "reason": reason,
                    "at": "2026-07-24T00:00:00",
                    "by_name": "Bob",
                }
            },
        },
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


# --- 완료 가드 -----------------------------------------------------------------


def test_complete_blocked_when_not_production(client):
    """제작대기(CONFIRM) 주문 완료 시도 → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_c1"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"
    assert "message" in data  # 에러 키 = message (error 아님)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"
    assert saved.status == "CONFIRM"


def test_complete_succeeds_from_production(client):
    """제작중(PRODUCTION) 주문 완료 → success, CONSTRUCTION 전이."""
    _login(client, _make_user("guard_c2"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"
    assert saved.status == "CONSTRUCTION"


def test_complete_succeeds_from_legacy_korean_stage(client):
    """레거시 한글 stage('생산') 주문 완료 → success (한글 값 허용 목록 포함)."""
    _login(client, _make_user("guard_c3"))
    order_id = _make_order("생산").id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"


# --- 시작 가드 -----------------------------------------------------------------


def test_start_blocked_when_already_production(client):
    """제작중(PRODUCTION) 주문 시작 재시도 → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_s1"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"


def test_start_succeeds_from_confirm(client):
    """제작대기(CONFIRM) 주문 시작 → success, PRODUCTION 전이."""
    _login(client, _make_user("guard_s2"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.status == "PRODUCTION"


def test_start_succeeds_from_legacy_korean_stage(client):
    """레거시 한글 stage('고객컨펌') 주문 시작 → success (한글 값 허용 목록 포함)."""
    _login(client, _make_user("guard_s3"))
    order_id = _make_order("고객컨펌").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


# --- 시트 풋터 조건 렌더 (P1-c) ------------------------------------------------

_SHEET_TEMPLATE = "production/partials/tablet_sheet.html"


def _sheet_ctx(**over) -> dict:
    base = {
        "id": 1,
        "customer_name": "고객",
        "load_md": "-",
        "total_units_display": "0",
        "spec_rows_view": [],
        "notes_text": "",
        "drawing_thumb": None,
        "hold_active": False,
        "hold_reason": "",
        "rework_active": False,
        "rework_reason": "",
        "rework_count": 0,
        "stage": "제작중",
        "is_sales_approved": True,
        "change_alerts": [],
        "has_changes": False,
        "change_history": [],
        "has_change_history": False,
    }
    base.update(over)
    return base


def _render_sheet(app, **over) -> str:
    with app.test_request_context():
        return app.jinja_env.get_template(_SHEET_TEMPLATE).render(order=_sheet_ctx(**over))


def test_sheet_production_shows_complete_button(app):
    """제작중 시트 → '생산 완료' primary 버튼(production-complete)."""
    html = _render_sheet(app, stage="제작중")
    assert 'data-tablet-sheet-action="production-complete"' in html
    assert "생산 완료" in html
    assert 'data-tablet-sheet-action="production-start"' not in html


def test_sheet_waiting_approved_shows_start_button(app):
    """제작대기 + 승인 → '제작 시작' primary 버튼(production-start)."""
    html = _render_sheet(app, stage="제작대기", is_sales_approved=True)
    assert 'data-tablet-sheet-action="production-start"' in html
    assert "제작 시작" in html


def test_sheet_waiting_unapproved_shows_muted_label(app):
    """제작대기 + 미승인 → 무채 라벨 '고객 컨펌 전', primary 버튼 없음."""
    html = _render_sheet(app, stage="제작대기", is_sales_approved=False)
    assert "고객 컨펌 전" in html
    assert 'data-tablet-sheet-action="production-start"' not in html
    assert 'data-tablet-sheet-action="production-complete"' not in html


def test_sheet_done_shows_rework_button(app):
    """제작완료 시트 → '수정 제작' primary 버튼(production-rework), start/complete 없음."""
    html = _render_sheet(app, stage="제작완료")
    assert 'data-tablet-sheet-action="production-rework"' in html
    assert "수정 제작" in html
    assert 'data-tablet-sheet-action="production-start"' not in html
    assert 'data-tablet-sheet-action="production-complete"' not in html


def test_sheet_rework_active_shows_badge_and_reason(app):
    """rework_active 시트 → 재제작 배지 + 사유 1줄(보류 배지/사유와 동일 문법)."""
    html = _render_sheet(app, stage="제작중", rework_active=True, rework_reason="치수 오류")
    assert "foms-prod-sheet__rework-badge" in html
    assert "재제작" in html
    assert "foms-prod-sheet__rework-reason" in html
    assert "치수 오류" in html


def test_sheet_rework_badge_and_callout_show_count(app):
    """P5 A-3: rework_count 병기 — 헤더 배지·사유 콜아웃에 '재제작 N회', 사유 본문 볼드."""
    html = _render_sheet(
        app, stage="제작중", rework_active=True, rework_reason="치수 오류", rework_count=2
    )
    assert "재제작 2회" in html  # 회차 병기(배지/콜아웃)
    assert "foms-prod-sheet__reason-text" in html  # 사유 본문 볼드 승격


def test_sheet_hold_reason_callout_upgraded(app):
    """P5 A-3: 보류 사유 콜아웃 — 클래스 유지 + 사유 본문 볼드(__reason-text)."""
    html = _render_sheet(app, hold_active=True, hold_reason="자재 입고 지연")
    assert "foms-prod-sheet__hold-reason" in html  # 클래스 유지(계약)
    assert "자재 입고 지연" in html
    assert "foms-prod-sheet__reason-text" in html


# --- 칸반 카드 보류/재제작 사유 스트립 (P5 A-2) --------------------------------

_KANBAN_BODY_TEMPLATE = "production/partials/tablet_kanban_body.html"


def _card_row(**over) -> dict:
    """칸반 카드 렌더용 최소 enriched-row dict(제작중 버킷 기본)."""
    base = {
        "id": 1,
        "customer_name": "카드 고객",
        "stage": "제작중",
        "structured_data": {"production": {}},
        "construction_dday": None,
        "change_alerts": [],
        "has_changes": False,
        "has_change_history": False,
    }
    base.update(over)
    return base


def _render_kanban_body(app, rows: list[dict]) -> str:
    with app.test_request_context():
        return app.jinja_env.get_template(_KANBAN_BODY_TEMPLATE).render(
            kanban_orders=rows, orders=rows
        )


def test_kanban_card_hold_reason_strip(app):
    """보류 active 카드 상단 앰버 스트립(--hold) + 사유 텍스트 노출."""
    row = _card_row(
        structured_data={"production": {"hold": {"active": True, "reason": "자재 지연"}}}
    )
    html = _render_kanban_body(app, [row])
    assert "foms-kanban-card__alert-row--hold" in html
    assert "자재 지연" in html


def test_kanban_card_hold_no_reason_shows_placeholder(app):
    """보류 사유 미입력 시 스트립 detail = '사유 미입력'."""
    row = _card_row(structured_data={"production": {"hold": {"active": True}}})
    html = _render_kanban_body(app, [row])
    assert "foms-kanban-card__alert-row--hold" in html
    assert "사유 미입력" in html


def test_kanban_card_rework_reason_strip_with_count(app):
    """재제작 active 카드 상단 블루 스트립(--rework) + '재제작 N회' 회차 병기 + 사유."""
    row = _card_row(
        structured_data={
            "production": {"rework": {"active": True, "count": 2, "reason": "치수 오류"}}
        }
    )
    html = _render_kanban_body(app, [row])
    assert "foms-kanban-card__alert-row--rework" in html
    assert "재제작 2회" in html
    assert "치수 오류" in html


# --- 보류 게이트 (P2-c) --------------------------------------------------------


def test_start_blocked_when_hold_active(client):
    """보류(hold active) 주문 시작 → 409 HOLD_ACTIVE, 전이·hold 불변."""
    _login(client, _make_user("guard_h1"))
    order_id = _make_order_with_hold("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "HOLD_ACTIVE"
    assert "보류 중인 주문입니다" in data["message"]
    assert "자재 입고 지연" in data["message"]  # 사유 병기
    assert data["hold"]["active"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"  # 전이 미발생
    assert saved.structured_data["production"]["hold"]["active"] is True  # hold 불변


def test_start_with_release_hold_succeeds_and_clears_hold(client):
    """보류 주문 시작 + release_hold → success, PRODUCTION 전이, hold 해제, 토글 이벤트 기록."""
    _login(client, _make_user("guard_h2"))
    order_id = _make_order_with_hold("CONFIRM").id

    resp = client.post(
        f"/api/orders/{order_id}/production/start", json={"release_hold": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"  # 전이 발생
    assert saved.structured_data["production"]["hold"]["active"] is False  # hold 해제

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["active"] is False
    assert events[0].payload["via"] == "release_on_start"


def test_complete_blocked_when_hold_active(client):
    """보류(hold active) 주문 완료 → 409 HOLD_ACTIVE, 전이·hold 불변."""
    _login(client, _make_user("guard_h3"))
    order_id = _make_order_with_hold("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["code"] == "HOLD_ACTIVE"
    assert data["hold"]["active"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"  # 전이 미발생


def test_complete_with_release_hold_succeeds(client):
    """보류 주문 완료 + release_hold → success, CONSTRUCTION 전이, hold 해제, 이벤트 via 표기."""
    _login(client, _make_user("guard_h4"))
    order_id = _make_order_with_hold("PRODUCTION").id

    resp = client.post(
        f"/api/orders/{order_id}/production/complete", json={"release_hold": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"
    assert saved.structured_data["production"]["hold"]["active"] is False

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["via"] == "release_on_complete"


def test_release_hold_on_order_without_hold_is_harmless(client):
    """보류 없는 주문 + release_hold:true → 정상 전이(무해), 토글 이벤트 미기록."""
    _login(client, _make_user("guard_h5"))
    order_id = _make_order("CONFIRM").id  # hold 없음

    resp = client.post(
        f"/api/orders/{order_id}/production/start", json={"release_hold": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED",
        )
        .all()
    )
    assert len(events) == 0  # 보류 없으면 해제 이벤트 없음


# --- 수정 제작 (rework, P3-c) --------------------------------------------------


def test_rework_from_construction_succeeds(client):
    """제작완료(CONSTRUCTION) 주문 → rework → success, PRODUCTION 전이, rework active/count=1, 이벤트."""
    _login(client, _make_user("guard_r1"))
    order_id = _make_order("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/rework", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_status"] == "PRODUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.status == "PRODUCTION"
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is True
    assert rework["count"] == 1

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_REWORK_STARTED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["count"] == 1


def test_rework_then_complete_clears_active_preserves_count(client):
    """rework 후 complete → CONSTRUCTION, rework active False + count 보존, 재제작 history/이벤트."""
    _login(client, _make_user("guard_r2"))
    order_id = _make_order("CONSTRUCTION").id

    assert client.post(f"/api/orders/{order_id}/production/rework", json={}).status_code == 200
    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is False   # 완료 시 해제
    assert rework["count"] == 1        # count 보존
    # history 마지막 = 재제작 완료 note.
    hist = saved.structured_data["workflow"]["history"]
    assert hist[-1]["note"] == "제작 완료 (재제작)"

    completed = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_COMPLETED",
        )
        .all()
    )
    assert len(completed) == 1
    assert completed[0].payload.get("rework") is True


def test_rework_second_round_increments_count(client):
    """2회차 rework → count=2 (rework → complete → rework)."""
    _login(client, _make_user("guard_r3"))
    order_id = _make_order("CONSTRUCTION").id

    assert client.post(f"/api/orders/{order_id}/production/rework", json={}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/production/complete", json={}).status_code == 200
    resp = client.post(f"/api/orders/{order_id}/production/rework", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["production"]["rework"]["count"] == 2


def test_rework_blocked_when_not_construction(client):
    """제작대기(CONFIRM) 주문 → rework → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_r4"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/rework", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"


def test_rework_blocked_when_hold_active(client):
    """보류(hold active) 제작완료 주문 → rework → 409 HOLD_ACTIVE, 전이·hold 불변."""
    _login(client, _make_user("guard_r5"))
    order_id = _make_order_with_hold("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/rework", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["code"] == "HOLD_ACTIVE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"  # 전이 미발생


def test_rework_with_release_hold_succeeds_via_rework(client):
    """보류 제작완료 주문 → rework + release_hold → success, PRODUCTION 전이, via=release_on_rework."""
    _login(client, _make_user("guard_r6"))
    order_id = _make_order_with_hold("CONSTRUCTION").id

    resp = client.post(
        f"/api/orders/{order_id}/production/rework", json={"release_hold": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.structured_data["production"]["hold"]["active"] is False

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["via"] == "release_on_rework"


def test_rework_reason_is_trimmed(client):
    """rework reason 은 trim 되어 저장·이벤트에 반영된다."""
    _login(client, _make_user("guard_r7"))
    order_id = _make_order("CONSTRUCTION").id

    resp = client.post(
        f"/api/orders/{order_id}/production/rework", json={"reason": "  치수 오류  "}
    )
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["production"]["rework"]["reason"] == "치수 오류"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_REWORK_STARTED",
        )
        .all()
    )
    assert events[0].payload["reason"] == "치수 오류"


# --- 되돌리기 2종: 제작 취소 / 완료 취소 (B-3) --------------------------------


def test_cancel_from_production_succeeds(client):
    """제작중(PRODUCTION) 주문 → cancel → success, CONFIRM(제작대기) 복귀, 이벤트 기록."""
    _login(client, _make_user("guard_x1"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={"reason": "  오배정  "})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_status"] == "CONFIRM"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"
    assert saved.status == "CONFIRM"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_CANCELLED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["reason"] == "오배정"  # trim 반영


def test_cancel_blocked_when_not_production(client):
    """제작대기(CONFIRM) 주문 → cancel → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_x2"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"


def test_uncomplete_from_construction_succeeds(client):
    """제작완료(CONSTRUCTION) 주문 → uncomplete → success, PRODUCTION(제작중) 복귀, 이벤트."""
    _login(client, _make_user("guard_x3"))
    order_id = _make_order("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_status"] == "PRODUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.status == "PRODUCTION"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_COMPLETE_REVERTED",
        )
        .all()
    )
    assert len(events) == 1


def test_uncomplete_blocked_when_not_construction(client):
    """제작중(PRODUCTION) 주문 → uncomplete → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_x4"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"


def test_uncomplete_restores_rework_when_was_rework_completion(client):
    """재제작 완료(rework→complete) 후 uncomplete → rework active 복원 + completed_at 삭제, count 불변."""
    _login(client, _make_user("guard_x5"))
    order_id = _make_order("CONSTRUCTION").id

    # rework → complete (completed_at 기록, active False, count=1)
    assert client.post(f"/api/orders/{order_id}/production/rework", json={}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/production/complete", json={}).status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is False
    assert "completed_at" in rework  # complete 가 완료 시각 기록

    # uncomplete → 재제작 복원
    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is True         # 활성 복원
    assert "completed_at" not in rework     # 완료 시각 표식 삭제
    assert rework["count"] == 1             # 회차 불변

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_COMPLETE_REVERTED",
        )
        .all()
    )
    assert events[-1].payload["rework_restored"] is True


def test_uncomplete_leaves_non_rework_completion_untouched(client):
    """재제작 아닌 일반 완료 주문 → uncomplete → rework 무터치(생성 안 됨)."""
    _login(client, _make_user("guard_x6"))
    order_id = _make_order("CONSTRUCTION").id  # rework 없음

    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    production = saved.structured_data.get("production") or {}
    assert "rework" not in production  # 무터치 — rework 미생성

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_COMPLETE_REVERTED",
        )
        .all()
    )
    assert events[-1].payload["rework_restored"] is False


# --- 시트 되돌리기 버튼 조건 렌더 (B-3) ----------------------------------------


def test_sheet_production_shows_cancel_ghost_button(app):
    """제작중 시트 → '제작 취소' ghost 버튼(production-cancel) + '생산 완료' primary."""
    html = _render_sheet(app, stage="제작중")
    assert 'data-tablet-sheet-action="production-cancel"' in html
    assert "제작 취소" in html
    assert "foms-prod-sheet__btn--ghost" in html
    assert 'data-tablet-sheet-action="production-complete"' in html


def test_sheet_done_shows_uncomplete_ghost_button(app):
    """제작완료 시트 → '완료 취소' ghost 버튼(production-uncomplete) + '수정 제작' primary."""
    html = _render_sheet(app, stage="제작완료")
    assert 'data-tablet-sheet-action="production-uncomplete"' in html
    assert "완료 취소" in html
    assert "foms-prod-sheet__btn--ghost" in html
    assert 'data-tablet-sheet-action="production-rework"' in html


# --- 보류 운영 가시성: hold_days 파생 단위 (P7 C-1) ---------------------------


def test_production_hold_days_normal_none_and_parsefail():
    """hold_days = 오늘(KST) − 보류시작일(KST) 일수. None·파싱 실패는 None(bare except 아님)."""
    import datetime

    from foms.services.production_dashboard_display import _production_hold_days

    three_days_ago = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
    ).isoformat()
    assert _production_hold_days(three_days_ago) == 3  # 정상(UTC aware ISO → KST 일수차)
    assert _production_hold_days(None) is None          # 미입력
    assert _production_hold_days("not-a-date") is None  # 파싱 실패


def test_compute_tablet_prod_kpis_counts_hold():
    """KPI 'hold' = hold_active 행 수(신규 쿼리 없이 enriched 행 파생)."""
    from foms.web.production.dashboard import _compute_tablet_prod_kpis

    rows = [
        {"stage": "제작중", "hold_active": True, "construction_dday": None},
        {"stage": "제작대기", "hold_active": True, "construction_dday": None},
        {"stage": "제작중", "hold_active": False, "construction_dday": None},
    ]
    assert _compute_tablet_prod_kpis(rows)["hold"] == 2


# --- 보류 운영 가시성: 카드 D+n · is-held-imminent 렌더 (P7 C-2) ---------------


def test_kanban_card_hold_badge_shows_dday_plus(app):
    """보류 카드 우상단 배지 = '보류 D+{n}'(row hold_days 소비)."""
    row = _card_row(
        structured_data={"production": {"hold": {"active": True, "reason": "자재"}}},
        hold_days=5,
    )
    html = _render_kanban_body(app, [row])
    assert "foms-kanban-card__hold" in html
    assert "D+5" in html


def test_kanban_card_hold_badge_omits_dday_when_zero(app):
    """hold_days=0(당일 보류) 이면 D+ 미표기(그냥 '보류')."""
    row = _card_row(
        structured_data={"production": {"hold": {"active": True}}},
        hold_days=0,
        construction_dday=None,  # D-day 칩도 D+ 없음(미정)
    )
    html = _render_kanban_body(app, [row])
    assert "foms-kanban-card__hold" in html
    assert "D+" not in html


def test_kanban_card_held_imminent_class_when_hold_and_dday_le2(app):
    """보류 + 시공 D-2 이내(또는 지연) → is-held-imminent 강경고 클래스."""
    row = _card_row(
        structured_data={"production": {"hold": {"active": True}}},
        construction_dday=1,
    )
    html = _render_kanban_body(app, [row])
    assert "is-held-imminent" in html


def test_kanban_card_no_held_imminent_when_dday_far(app):
    """보류지만 시공일 여유(D-5) → is-held 만, is-held-imminent 없음."""
    row = _card_row(
        structured_data={"production": {"hold": {"active": True}}},
        construction_dday=5,
    )
    html = _render_kanban_body(app, [row])
    assert "is-held" in html
    assert "is-held-imminent" not in html


# --- PC 리스트 단계 셀 배지 (P8 C-4) -------------------------------------------

_GRID_TEMPLATE = "production/partials/filters_grid.html"


def _grid_row(**over) -> dict:
    """PC filters_grid 렌더용 최소 enriched-row dict."""
    base = {
        "id": 1,
        "alerts": {},
        "stage": "제작중",
        "is_sales_approved": True,
        "structured_data": {"production": {}},
        "customer_name": "고객",
        "orderer_name": "",
        "is_self_measurement": False,
        "phone": "-",
        "address": "-",
        "is_erp_order": True,
        "measurement_date": "",
        "construction_date": "",
        "manager_name": "-",
        "has_media": False,
        "attachments_count": 0,
        "hold_days": None,
    }
    base.update(over)
    return base


def _render_grid(app, rows: list[dict]) -> str:
    with app.test_request_context():
        return app.jinja_env.get_template(_GRID_TEMPLATE).render(orders=rows)


def test_pc_grid_hold_badge_renders(app):
    """PC 단계 셀: hold active → '보류 D+n' 배지 + title 사유."""
    row = _grid_row(
        structured_data={"production": {"hold": {"active": True, "reason": "자재 지연"}}},
        hold_days=4,
    )
    html = _render_grid(app, [row])
    assert "보류 D+4" in html
    assert "자재 지연" in html  # title 사유


def test_pc_grid_rework_badge_renders(app):
    """PC 단계 셀: rework active → '재제작 N회' 배지."""
    row = _grid_row(
        structured_data={
            "production": {"rework": {"active": True, "count": 2, "reason": "치수"}}
        },
    )
    html = _render_grid(app, [row])
    assert "재제작 2회" in html


def test_pc_grid_no_badges_when_inactive(app):
    """보류/재제작 비활성 → 배지 미렌더(단계 배지만)."""
    html = _render_grid(app, [_grid_row()])
    assert "보류 D+" not in html
    assert "재제작" not in html


# --- 완료 이력 (소실 방지 + 무채 배지, Phase E) --------------------------------


def test_release_hold_via_gate_appends_history(client):
    """전이 게이트 release(start + release_hold) 시 직전 active hold 를 hold_history 에 보존(E-a)."""
    user = _make_user("guard_e_hist")
    user_name = user.name
    _login(client, user)
    order_id = _make_order_with_hold("CONFIRM", reason="자재 입고 지연").id

    resp = client.post(
        f"/api/orders/{order_id}/production/start", json={"release_hold": True}
    )
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    history = saved.structured_data["production"]["hold_history"]
    assert len(history) == 1
    assert history[0]["reason"] == "자재 입고 지연"
    assert history[0]["at"]  # 보류 시작 시각 보존
    assert history[0]["released_at"]
    assert history[0]["released_by"] == user_name
    # hold 자체는 해제됨(이력은 별도 보존).
    assert saved.structured_data["production"]["hold"]["active"] is False


def test_enrich_row_derives_history_counts(client):
    """enriched 행에 rework_count(int)·hold_history_count(int) 파생(E-b) — 완료 후 이력 소비용."""
    from foms.services.production_dashboard_display import build_production_enriched_rows

    _login(client, _make_user("guard_e_enrich"))
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="이력 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "production": {
                "rework": {"active": False, "count": 3},
                "hold_history": [{"reason": "a"}, {"reason": "b"}],
            },
        },
        erp_stage_code="CONSTRUCTION",
    )
    db_session.add(order)
    db_session.commit()

    rows = build_production_enriched_rows([order], {})
    assert len(rows) == 1
    assert rows[0]["rework_count"] == 3
    assert rows[0]["hold_history_count"] == 2


def test_kanban_card_completed_history_badges(app):
    """완료 카드 무채 이력 배지(E-c): rework 완료(active 아님+count>0) → '재제작 N회'(hist) +
    hold_history_count>0 → '보류 이력'. 진행 배지(유채)와 구분되는 무채 __hist 클래스."""
    row = _card_row(
        stage="제작완료",
        structured_data={"production": {"rework": {"active": False, "count": 2}}},
        rework_count=2,
        hold_history_count=3,
    )
    html = _render_kanban_body(app, [row])
    assert "foms-kanban-card__hist" in html
    assert "재제작 2회" in html
    assert "보류 이력" in html


def test_kanban_card_no_history_badge_while_rework_active(app):
    """rework active 카드는 무채 이력 배지(__hist) 미렌더 — 진행 배지(유채)만."""
    row = _card_row(
        structured_data={"production": {"rework": {"active": True, "count": 1}}},
        rework_count=1,
    )
    html = _render_kanban_body(app, [row])
    assert "foms-kanban-card__hist" not in html


def test_sheet_completed_history_section(app):
    """완료 시트 무채 이력 섹션(E-d): rework 완료(active 아님+count>0) → '재제작 N회 · 최근 사유',
    hold_history → '보류 이력 N건'. 진행 콜아웃(유채)과 구분되는 __hist 섹션."""
    html = _render_sheet(
        app,
        stage="제작완료",
        rework_active=False,
        rework_count=2,
        rework_reason="치수 오류",
        hold_history=[{"reason": "a"}, {"reason": "b"}],
    )
    assert "foms-prod-sheet__hist" in html
    assert "재제작 2회" in html
    assert "최근 사유" in html
    assert "치수 오류" in html
    assert "보류 이력 2건" in html


def test_sheet_no_history_section_when_none(app):
    """이력 없음(rework_count=0, hold_history=[]) → 무채 이력 섹션 미렌더."""
    html = _render_sheet(app, stage="제작완료", rework_count=0, hold_history=[])
    assert "foms-prod-sheet__hist" not in html


def test_pc_grid_completed_rework_history_badge(app):
    """PC 단계 셀(E-e): 완료 건(rework active 아님+rework_count>0) → 무채 '재제작 N회' 이력 배지."""
    row = _grid_row(
        stage="제작완료",
        structured_data={"production": {"rework": {"active": False, "count": 2}}},
        rework_count=2,
    )
    html = _render_grid(app, [row])
    assert "재제작 2회" in html


# --- 제작 취소 깨끗한 되돌림 (F-1) --------------------------------------------


def test_quest_state_true_when_production_history_present():
    """F-1a: 제작대기 stage 라도 workflow.history 에 PRODUCTION 기록이 있으면
    is_sales_approved=True (제작 이력 = 컨펌·제작된 건 → 재시작 허용, 승인 퀘스트 없어도)."""
    from foms.services.production_dashboard_display import _production_quest_sales_state

    sd = {
        "workflow": {"history": [{"stage": "PRODUCTION"}, {"stage": "CONFIRM"}]},
        "quests": [],  # 승인 퀘스트 없음 — 이력 없었다면 False 였을 상태.
    }
    approved, quest = _production_quest_sales_state(sd, "제작대기")
    assert approved is True
    assert quest is None


def test_quest_state_true_with_legacy_korean_production_history():
    """F-1a: 레거시 한글 stage('생산') 이력도 제작 이력으로 인정."""
    from foms.services.production_dashboard_display import _production_quest_sales_state

    sd = {"workflow": {"history": [{"stage": "생산"}]}, "quests": []}
    approved, _ = _production_quest_sales_state(sd, "제작대기")
    assert approved is True


def test_quest_state_false_for_new_unapproved_without_production_history():
    """F-1a: 신규 미승인 건(history 무 PRODUCTION)은 여전히 False(고객 컨펌 전 유지)."""
    from foms.services.production_dashboard_display import _production_quest_sales_state

    sd = {"workflow": {"history": [{"stage": "CONFIRM"}]}, "quests": []}
    approved, _ = _production_quest_sales_state(sd, "제작대기")
    assert approved is False


def test_cancel_then_restart_available_via_production_history(client):
    """F-1a+b 통합: 미승인 CONFIRM 건도 제작 시작(history PRODUCTION 기록) 후 취소하면,
    제작대기 복귀에도 is_sales_approved=True (재시작 버튼) — '고객 컨펌 전' 미표시."""
    from foms.services.production_dashboard_display import build_production_enriched_rows

    _login(client, _make_user("guard_f1"))
    order_id = _make_order("CONFIRM").id

    # 제작 시작(history 에 PRODUCTION append) → 취소(제작대기 복귀)
    assert client.post(f"/api/orders/{order_id}/production/start", json={}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/production/cancel", json={}).status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"  # 제작대기 복귀

    rows = build_production_enriched_rows([saved], {})
    assert len(rows) == 1
    assert rows[0]["is_sales_approved"] is True  # 제작 이력 → 재시작 허용


def test_cancel_clears_rework_active_preserves_count(client):
    """F-1b: 제작 취소 시 rework active=False 정리(count·reason 보존)."""
    _login(client, _make_user("guard_f2"))
    order_id = _make_order("CONSTRUCTION").id

    # rework 로 제작중(PRODUCTION) + rework active=True, count=1 상태 진입.
    assert client.post(
        f"/api/orders/{order_id}/production/rework", json={"reason": "치수"}
    ).status_code == 200

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is False   # 취소 시 해제
    assert rework["count"] == 1        # count 보존
    assert rework["reason"] == "치수"  # reason 보존

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_CANCELLED",
        )
        .all()
    )
    assert events[-1].payload["rework_cleared"] is True


def test_cancel_releases_hold_and_appends_history(client):
    """F-1b: 제작 취소 시 active hold 해제 + hold_history 보존(released_by 기록)."""
    user = _make_user("guard_f3")
    user_name = user.name
    _login(client, user)
    order_id = _make_order_with_hold("PRODUCTION", reason="자재 지연").id

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    prod = saved.structured_data["production"]
    assert prod["hold"]["active"] is False   # 해제
    history = prod["hold_history"]
    assert len(history) == 1
    assert history[0]["reason"] == "자재 지연"
    assert history[0]["released_at"]
    assert history[0]["released_by"] == user_name

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_CANCELLED",
        )
        .all()
    )
    assert events[-1].payload["hold_released"] is True


def test_cancel_without_production_flags_is_harmless(client):
    """F-1b: production 플래그 없는 일반 제작중 주문 취소 → 정리 스킵(무해), 정상 복귀."""
    _login(client, _make_user("guard_f4"))
    order_id = _make_order("PRODUCTION").id  # production dict 없음

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_CANCELLED",
        )
        .all()
    )
    assert events[-1].payload["rework_cleared"] is False
    assert events[-1].payload["hold_released"] is False
