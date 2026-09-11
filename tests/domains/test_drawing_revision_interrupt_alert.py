"""도면 수정 요청 = ACTION-REQUIRED 등급(확인창) 계약.

왜: 수정 요청은 종 배지로만 왔고, 2026-09-11 운영 실측에서 90일 21건 중 8건이 미독이었다
(알림 열기까지 평균 최대 91.9시간). 서버가 realtime payload 에 `interrupt` 를 실어야
프런트가 확인창을 띄운다 — 등급 판정을 프런트로 내리지 않는다는 계약을 여기서 고정한다.
마법사는 standalone 문서라 확인창 자산을 직접 실어야 한다는 것도 함께 고정한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]


def _make_user(username, *, role, team, name):
    user = User(
        username=username,
        password=generate_password_hash("pass"),
        role=role,
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_transferred_order(manager_name):
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="고객",
        phone="010-0000-0000",
        address="서울",
        product="붙박이장",
        status="DRAWING",
        manager_name=manager_name,
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "고객"}, "manager": {"name": manager_name}},
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "TRANSFERRED",
            "assignments": {"sales_assignee_user_ids": []},
            "drawing_current_files": [{"key": "orders/1/drawing/a.pdf", "filename": "a.pdf"}],
            "drawing_transfer_history": [
                {"action": "TRANSFER", "by_user_name": "도면", "at": "2026-09-10 10:00:00"}
            ],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_revision_realtime_payload_carries_interrupt_grade(client, monkeypatch):
    """수정 요청 알림은 interrupt=True 로 나가고, 요청자 이름도 함께 실린다."""
    sent: list[dict] = []
    monkeypatch.setattr(
        revision_api,
        "emit_erp_notification_to_users",
        lambda user_ids, payload: sent.append(dict(payload or {})),
    )
    monkeypatch.setattr(
        revision_api, "enqueue_push_for_notification", lambda *a, **k: None, raising=False
    )

    sales = _make_user("rev_sales_grade", role="MANAGER", team="SALES", name="영업담당")
    order = _make_transferred_order("영업담당")
    order_id = order.id
    _login(client, sales)

    res = client.post(
        f"/api/orders/{order_id}/request-revision",
        json={
            "note": "상부장 높이 2385 → 2290",
            "target_drawing_keys": ["orders/1/drawing/a.pdf"],
        },
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["success"] is True

    revision_payloads = [p for p in sent if p.get("notification_type") == "DRAWING_REVISION"]
    assert len(revision_payloads) == 1
    payload = revision_payloads[0]
    assert payload["interrupt"] is True
    assert payload["order_id"] == order_id
    assert payload["created_by_name"] == "영업담당"
    # 긴급 호출(P0) 과는 다른 등급이다 — 전체화면 빨강을 타지 않아야 한다.
    assert payload.get("urgent") in (None, False)


def test_revision_cancel_is_not_an_interrupt(client, monkeypatch):
    """요청 취소는 작업을 멈출 일이 아니다 — 확인창 등급을 달지 않는다(쪽지 등급은 별도)."""
    source = (ROOT / "foms/api/drawing/erp_orders_revision.py").read_text(encoding="utf-8")
    cancel_block = source.split("DRAWING_REVISION_CANCELLED", 1)[1]
    assert "'interrupt': True" not in cancel_block


def test_shared_layout_routes_grades_to_dialog():
    """공용 레이아웃(인라인 + 외부 SSOT 사본) 둘 다 등급 분기를 모듈로 넘긴다."""
    head = (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    init_js = (ROOT / "static/js/runtime/layout-head-init.js").read_text(encoding="utf-8")
    scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    for text in (head, init_js):
        assert "window.FOMSDrawingAlert.handle(data)" in text
        # 긴급(P0)은 여전히 전체화면 오버레이가 먼저 잡는다.
        assert "triggerUrgentBriefingAlert(data)" in text
    assert "js/foms/foms-drawing-alert.js" in scripts
    assert "css/components/foms-drawing-alert.css" in scripts


def test_cancel_notice_grade_is_wired():
    """수정 요청 취소는 NOTICE 등급(쪽지)으로 나가고, 확인창 등급은 아니다."""
    source = (ROOT / "foms/api/drawing/erp_orders_revision.py").read_text(encoding="utf-8")
    cancel_block = source.split("DRAWING_REVISION_CANCELLED", 1)[1]
    assert "'notice': True" in cancel_block
    assert "'interrupt': True" not in cancel_block

    js = (ROOT / "static/js/foms/foms-drawing-alert.js").read_text(encoding="utf-8")
    # 등급 판정은 서버 몫 — 프런트는 두 플래그만 본다.
    assert "data.interrupt === true" in js
    assert "data.notice === true" in js
    # 쪽지는 스스로 닫아야 읽음이 된다(자동 닫힘 금지 — 못 본 채 사라짐 재발).
    assert "setTimeout" not in js.split("function notice(", 1)[1].split("function handle(", 1)[0]
    css = (ROOT / "static/css/components/foms-drawing-alert.css").read_text(encoding="utf-8")
    assert ".foms-drawing-notice" in css


def test_wizard_standalone_loads_alert_stack():
    """마법사는 standalone 이라 소켓·write helper·확인창을 직접 싣는다."""
    wizard = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
    for asset in (
        "cdn.socket.io",
        "js/foms/notification-write.js",
        "js/foms/foms-drawing-alert.js",
        "js/drawing/wizard-alert-bridge.js",
        "css/components/foms-drawing-alert.css",
    ):
        assert asset in wizard, asset
    # 상단바를 통째로 들이면 캔버스 단축키와 충돌한다 — include 하지 않는다.
    assert "layout_nav.html" not in wizard


def test_dialog_acks_before_closing():
    """확인 버튼은 ack + read 를 서버에 보내고, 닫기 X 는 두지 않는다."""
    js = (ROOT / "static/js/foms/foms-drawing-alert.js").read_text(encoding="utf-8")
    assert "'/erp/api/notifications/'" in js
    assert "['ack', 'read']" in js
    assert "FOMSNotificationWrite" in js
    # 서버가 등급을 정한다 — 프런트는 interrupt 플래그만 본다.
    assert "data.interrupt !== true" in js


def test_cancel_realtime_payload_carries_notice_grade(client, monkeypatch):
    """취소 라우트가 실제로 notice 등급 payload 를 쏜다(문자열 검사가 아니라 호출 결과로)."""
    sent: list[dict] = []
    monkeypatch.setattr(
        revision_api,
        "emit_erp_notification_to_users",
        lambda user_ids, payload: sent.append(dict(payload or {})),
    )
    monkeypatch.setattr(
        revision_api, "enqueue_push_for_notification", lambda *a, **k: None, raising=False
    )

    sales = _make_user("rev_sales_notice", role="MANAGER", team="SALES", name="영업취소")
    order = _make_transferred_order("영업취소")
    sd = dict(order.structured_data)
    sd["drawing_status"] = "RETURNED"
    sd["drawing_transfer_history"] = sd["drawing_transfer_history"] + [
        {"action": "REQUEST_REVISION", "by_user_name": "영업취소", "files": [],
         "at": "2026-09-11 09:00:00"}
    ]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    order_id = order.id
    _login(client, sales)

    res = client.post(f"/api/orders/{order_id}/cancel-revision-request")
    assert res.status_code == 200, res.get_data(as_text=True)

    cancels = [p for p in sent if p.get("notification_type") == "DRAWING_REVISION_CANCELLED"]
    assert len(cancels) == 1
    payload = cancels[0]
    assert payload["notice"] is True
    assert payload.get("interrupt") in (None, False)
    assert payload["created_by_name"] == "영업취소"
