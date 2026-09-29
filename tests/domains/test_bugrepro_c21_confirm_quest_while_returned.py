"""C21 재현 — 수령 확정 뒤 수정요청(RETURNED)인데 고객컨펌 승인이 생산으로 넘긴다.

실제 라우트 순서를 그대로 밟는다(합성 상태 주입 없음):

1. 도면 담당(STAFF/DRAWING)이 ``POST /api/orders/<id>/transfer-drawing`` → ``drawing_status=TRANSFERRED``
2. 영업 담당(STAFF/SALES)이 ``POST /api/orders/<id>/confirm-drawing-receipt`` → stage CONFIRM, CONFIRMED
3. 같은 영업이 ``POST /api/orders/<id>/request-revision`` → ``drawing_status=RETURNED``, stage CONFIRM 유지
   (``erp_orders_revision.py`` 가 CONFIRMED→RETURNED 를 허용하고 단계는 건드리지 않는다)
4. 이 상태에서 ``POST /api/orders/<id>/quest/approve`` (고객 컨펌 완료)

올바른 동작: 도면이 수정 중(RETURNED)이면 고객 컨펌 완료로 생산에 넘어가면 안 된다 — 4xx 로
거절하고 stage 는 CONFIRM, ``blueprint.customer_confirmed`` 미기록, ``CUSTOMER_CONFIRMED`` 이벤트 0.
지금 코드는 ``quest_approve_authz`` 도 ``quest_transition_service`` (CUSTOMER_CONFIRM) 도
``drawing_status`` 를 보지 않아 200 → PRODUCTION 이 된다(= 이 테스트가 빨갛다).

같은 구멍의 다른 입구(부가 주장)도 같은 방식으로 단언한다:

* 재전이(완료 quest + stage CONFIRM) — 승인 라우트 ``is_retransition`` 분기
* 생산 탭 [제작 시작] CONFIRM 호환 경로 — ``production/start`` (b)
* 일반 상태 쓰기(일괄 ``bulk_update_order_status`` · 단건 ``update_order_status`` ·
  ``update_order_field`` status)의 인접 전진 CONFIRM→PRODUCTION — 퀘스트 게이트도 안 본다
* 화면 CTA — ``build_current_quest_payload`` 가 RETURNED 에서도 [고객 컨펌 완료] 를 내민다

음성 대조군: 수정요청이 없는(CONFIRMED) 주문은 같은 승인으로 PRODUCTION 까지 간다(초록이어야 한다).

C21 은 2차 설계서 몫이다(1차 묶음 브리프 2026-09-29). 빨간 재현 테스트 7개는 고칠 때까지
``strict=True`` xfail 로 둔다 — 누가 먼저 고치면 XPASS 가 실패로 드러나 표시를 떼게 된다.
음성 대조군은 표시 없이 그대로 초록이어야 한다.
"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_quest_display import build_current_quest_payload
from models import Order, OrderEvent, User

_C21_PENDING = pytest.mark.xfail(
    strict=True,
    reason="2차 설계서: C21 — 원장 2026-09-29-drawing-defects-verification-ledger.md",
)


class _Actor:
    """요청 사이에 세션이 닫혀도(teardown) 안전한 사용자 식별값 묶음."""

    def __init__(self, user: User) -> None:
        self.id = int(user.id)
        self.username = user.username
        self.role = user.role
        self.name = user.name

    def load(self) -> User:
        return db_session.get(User, self.id)


def _make_user(username: str, *, role: str = "STAFF", team: str | None = None) -> _Actor:
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
    return _Actor(user)


def _login(client, user: _Actor) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _drawing_stage_order(sales: _Actor, drawer: _Actor) -> Order:
    """도면 단계 주문 — 영업·도면 담당이 명시 지정돼 있다(권한 폴백을 타지 않게)."""
    order = Order(
        received_date="2026-09-29",
        customer_name="C21 고객",
        phone="010-2121-2121",
        address="서울 테헤란로 21",
        product="붙박이장",
        status="DRAWING",
        manager_name=sales.name,
        is_erp_order=True,
        erp_stage_code="DRAWING",
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {"customer": {"name": "C21 고객"}, "manager": {"name": sales.name}},
            "assignments": {
                "sales_assignee_user_ids": [sales.id],
                "drawing_assignee_user_ids": [drawer.id],
            },
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _reload(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _events(order_id: int, event_type: str) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .all()
    )


def _walk_to_confirmed(client, tag: str) -> tuple[int, _Actor]:
    """전달 → 수령 확정을 실제 API 로 밟는다. (order_id, 영업 담당) 반환."""
    sales = _make_user(f"c21_sales_{tag}", team="SALES")
    drawer = _make_user(f"c21_drawer_{tag}", team="DRAWING")
    order_id = _drawing_stage_order(sales, drawer).id
    key = f"orders/{order_id}/drawing_wizard/exports/v1.png"

    _login(client, drawer)
    sent = client.post(
        f"/api/orders/{order_id}/transfer-drawing",
        json={"files": [{"key": key, "filename": "v1.png"}]},
    )
    assert sent.status_code == 200, sent.get_json()

    _login(client, sales)
    received = client.post(f"/api/orders/{order_id}/confirm-drawing-receipt", json={})
    assert received.status_code == 200, received.get_json()
    assert received.get_json()["stage_moved"] is True

    saved = _reload(order_id)
    assert saved.structured_data["drawing_status"] == "CONFIRMED"
    assert saved.erp_stage_code == "CONFIRM"
    return order_id, sales


def _request_revision(client, order_id: int) -> None:
    """(영업으로 로그인된 상태에서) 수령 확정 뒤 수정요청 → RETURNED, 단계는 CONFIRM 그대로."""
    asked = client.post(
        f"/api/orders/{order_id}/request-revision",
        json={"note": "고객이 손잡이 색 변경 요청"},
    )
    assert asked.status_code == 200, asked.get_json()
    saved = _reload(order_id)
    assert saved.structured_data["drawing_status"] == "RETURNED"
    assert saved.erp_stage_code == "CONFIRM"
    assert saved.structured_data["workflow"]["stage"] == "CONFIRM"


def _walk_to_returned(client, tag: str) -> tuple[int, _Actor]:
    order_id, sales = _walk_to_confirmed(client, tag)
    _request_revision(client, order_id)
    return order_id, sales


def _assert_still_confirm_and_unconfirmed(order_id: int, resp, entry: str) -> None:
    """RETURNED 에서의 전진 시도는 4xx 이고, 단계·고객확인·전이 이벤트가 그대로여야 한다."""
    saved = _reload(order_id)
    sd = saved.structured_data or {}
    observed = (
        f"[{entry}] HTTP {resp.status_code} body={resp.get_json()} → "
        f"stage={saved.erp_stage_code}/{(sd.get('workflow') or {}).get('stage')} "
        f"drawing_status={sd.get('drawing_status')}"
    )
    assert 400 <= resp.status_code < 500, (
        "도면이 수정 중(RETURNED)인데 생산으로 넘기는 요청이 거절되지 않았다 — " + observed
    )
    assert saved.erp_stage_code == "CONFIRM", observed
    assert (sd.get("workflow") or {}).get("stage") == "CONFIRM", observed
    assert sd.get("drawing_status") == "RETURNED", observed


# --------------------------------------------------------------------------- #
# C21 본 주장 — 고객컨펌 승인(PC·모바일 공용 라우트)
# --------------------------------------------------------------------------- #
@_C21_PENDING
def test_c21_confirm_approve_rejected_while_drawing_returned(client):
    order_id, _sales = _walk_to_returned(client, "main")

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    _assert_still_confirm_and_unconfirmed(order_id, resp, "quest/approve")
    sd = _reload(order_id).structured_data or {}
    assert not (sd.get("blueprint") or {}).get("customer_confirmed"), (
        "수정 중인 도면에 고객 확인이 기록됐다"
    )
    assert _events(order_id, "CUSTOMER_CONFIRMED") == []


# --------------------------------------------------------------------------- #
# 음성 대조군 — 수정요청이 없으면(CONFIRMED) 같은 승인은 생산으로 간다(초록)
# --------------------------------------------------------------------------- #
def test_c21_control_confirm_approve_passes_when_drawing_confirmed(client):
    order_id, _sales = _walk_to_confirmed(client, "ctrl")

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["auto_transitioned"] is True
    saved = _reload(order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert (saved.structured_data.get("blueprint") or {}).get("customer_confirmed") is True
    assert len(_events(order_id, "CUSTOMER_CONFIRMED")) == 1


# --------------------------------------------------------------------------- #
# 부가 주장 — 같은 구멍의 다른 입구
# --------------------------------------------------------------------------- #
def _walk_to_completed_confirm_quest_then_returned(client, tag: str) -> tuple[int, _Actor]:
    """stage CONFIRM + 완료(COMPLETED) CONFIRM quest + RETURNED 를 실제 API 로 만든다.

    2026-09-17 전 승인(단계 제자리)으로 운영에 남은 '이다은 류' 와 같은 모양이다. 오늘은
    quest 생성(POST quest) + 관리자 수동 완료(PUT quest/status, 사유 필수)로 도달한다 —
    수동 완료는 전이를 하지 않는다.
    """
    order_id, sales = _walk_to_confirmed(client, tag)
    created = client.post(f"/api/orders/{order_id}/quest", json={})
    assert created.status_code == 200, created.get_json()

    admin = _make_user(f"c21_admin_{tag}", role="ADMIN", team="SALES")
    _login(client, admin)
    done = client.put(
        f"/api/orders/{order_id}/quest/status",
        json={"status": "COMPLETED", "reason": "고객 전화로 컨펌 받음"},
    )
    assert done.status_code == 200, done.get_json()
    saved = _reload(order_id)
    assert saved.erp_stage_code == "CONFIRM"

    _login(client, sales)
    _request_revision(client, order_id)
    return order_id, sales


@_C21_PENDING
def test_c21_retransition_rejected_while_drawing_returned(client):
    """완료 quest + stage CONFIRM 의 [고객 컨펌 완료](재전이)도 RETURNED 면 막혀야 한다."""
    order_id, _sales = _walk_to_completed_confirm_quest_then_returned(client, "retr")

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    _assert_still_confirm_and_unconfirmed(order_id, resp, "quest/approve 재전이")
    assert _events(order_id, "CUSTOMER_CONFIRMED") == []


@_C21_PENDING
def test_c21_production_start_compat_rejected_while_drawing_returned(client):
    """생산 탭 [제작 시작] CONFIRM 호환 경로(b)도 RETURNED 면 막혀야 한다."""
    order_id, _sales = _walk_to_completed_confirm_quest_then_returned(client, "pstart")

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})

    _assert_still_confirm_and_unconfirmed(order_id, resp, "production/start")
    assert _events(order_id, "PRODUCTION_STARTED") == []


@pytest.mark.parametrize(
    ("entry", "path", "body_for"),
    [
        # ERP 대시보드 작업 큐 일괄 상태 바(dashboard_grid.html erp-grid-bulk-bar, can_edit_erp 노출)
        ("bulk", "/api/bulk_update_order_status",
         lambda oid: {"order_ids": [oid], "status": "PRODUCTION"}),
        ("single", "/api/update_order_status",
         lambda oid: {"order_id": oid, "status": "PRODUCTION"}),
        ("field", "/api/update_order_field",
         lambda oid: {"order_id": oid, "field": "status", "value": "PRODUCTION"}),
    ],
    ids=["bulk", "single", "field"],
)
@_C21_PENDING
def test_c21_generic_status_advance_keeps_confirm_while_drawing_returned(
    client, entry, path, body_for,
):
    """일반 상태 쓰기의 인접 전진(CONFIRM→PRODUCTION)도 RETURNED 면 단계를 옮기면 안 된다.

    응답 모양(4xx 인지, 200 + 차단 목록인지)은 경로마다 다를 수 있어 **상태 불변식만** 단언한다.
    """
    order_id, _sales = _walk_to_returned(client, f"gen_{entry}")

    resp = client.post(path, json=body_for(order_id))

    saved = _reload(order_id)
    sd = saved.structured_data or {}
    observed = (
        f"[{path}] HTTP {resp.status_code} → stage={saved.erp_stage_code}/"
        f"{(sd.get('workflow') or {}).get('stage')} drawing_status={sd.get('drawing_status')}"
    )
    assert saved.erp_stage_code == "CONFIRM", (
        "도면이 수정 중(RETURNED)인데 일반 상태 쓰기로 생산 단계가 됐다 — " + observed
    )
    assert (sd.get("workflow") or {}).get("stage") == "CONFIRM", observed


@_C21_PENDING
def test_c21_confirm_cta_not_offered_while_drawing_returned(client):
    """화면 SSOT(PC 그리드·모바일 큐 카드·모바일 상세가 읽는 payload)도 버튼을 내밀면 안 된다."""
    order_id, sales = _walk_to_returned(client, "cta")
    order = _reload(order_id)

    payload = build_current_quest_payload(
        sd=order.structured_data, stage="CONFIRM", stage_code="CONFIRM",
        order=order, current_user=sales.load(),
    )

    assert payload is not None
    offered = bool(payload.get("approve_label")) and bool(payload.get("can_assignee_approve"))
    assert not offered, (
        "RETURNED 인데 [고객 컨펌 완료] 버튼이 노출된다 — "
        f"approve_label={payload.get('approve_label')!r} "
        f"can_assignee_approve={payload.get('can_assignee_approve')!r} "
        f"advances_stage={payload.get('advances_stage')!r}"
    )
