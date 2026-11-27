"""글 고침 둘(사장님 2026-11-27 질문 창 답 그대로) — 사람이 읽는 글만, 동작 · 받는 사람 · 보내는 길은 그대로.

1. 주문 기록(타임라인)의 '생산' → '제작'("낱말만 '제작'으로"): 보여 줄 때 만드는 글이라 옛 기록도 새 글로 보인다.
2. 영업 · 협력사 도면 수정 요청 알림 글을 공장 요청 글과 맞춘다("공장 요청 글과 맞추기"):
   "… 도면 수정 요청이 접수됐어요. 대상: 도면 2. 메모: …" — 번호 꼴은 공장 글의 ``numbers_label``, "메모" 낱말은 그대로.

이름은 모두 가짜(정하늘 · 김도면 · 박반장).
"""

from __future__ import annotations

from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
import foms.services.notifications.push_sender as push_sender
import foms.services.partners.revision as partner_revision
from db import db_session
from foms.services.order_event_display import generate_change_description
from models import Notification, Order, User


# ── 1. 주문 기록 글 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("event_type", "text"),
    [
        ("PRODUCTION_STARTED", "제작을 시작했습니다"),
        ("PRODUCTION_COMPLETED", "제작을 완료 처리했습니다"),
        ("PRODUCTION_CANCELLED", "제작 시작을 취소했습니다 (제작 대기로 돌아감)"),
    ],
)
def test_timeline_production_lines_say_jejak(event_type, text):
    """세 줄 원문 — 말투 '~했습니다' 그대로, 낱말만 '제작'."""
    assert generate_change_description(event_type, "", "", "", {}) == text
    # 옛 기록(payload 에 무엇이 있든)도 보여 줄 때 같은 글이 된다 — 저장된 글을 읽지 않는다.
    assert generate_change_description(event_type, "", "", "", {"message": "생산을 시작했습니다"}) == text


# ── 2. 도면 수정 요청 알림 글 ─────────────────────────────────────────────────────


def _user(username, *, role, team, name, partner_org_id=None):
    user = User(username=username, password=generate_password_hash("pass"), role=role, team=team,
                name=name, is_active=True)
    if partner_org_id is not None:
        user.partner_org_id = partner_org_id
    db_session.add(user)
    db_session.commit()
    return user


def _order(manager_name, files):
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="정하늘", phone="010-0000-0000",
        address="서울", product="붙박이장", status="DRAWING", manager_name=manager_name, is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "정하늘"}, "manager": {"name": manager_name}},
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "TRANSFERRED",
            "assignments": {"sales_assignee_user_ids": []},
            "drawing_current_files": [{"key": f"orders/1/drawing/{i}.pdf", "filename": f"{i}.pdf"}
                                      for i in range(1, files + 1)],
            "drawing_transfer_history": [{"action": "TRANSFER", "by_user_name": "김도면", "at": "2026-11-27 10:00:00"}],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


@pytest.fixture
def quiet(monkeypatch):
    """실제 발송 없음 — 실시간 · 웹 푸시 대기열을 가짜로."""
    sent: list[dict] = []
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users",
                        lambda user_ids, payload: sent.append(dict(payload or {})))
    monkeypatch.setattr(push_sender, "enqueue_push_for_notification", lambda *a, **k: None)
    return sent


def _request(client, username, files, keys):
    sales = _user(username, role="MANAGER", team="SALES", name="박반장")
    order = _order("박반장", files)
    order_id = order.id
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = sales.id, sales.username, sales.role
    res = client.post(f"/api/orders/{order_id}/request-revision",
                      json={"note": "상부장 높이 2385 → 2290", "target_drawing_keys": keys})
    assert res.status_code == 200, res.get_data(as_text=True)
    return order_id


def _message(order_id):
    row = (db_session.query(Notification)
           .filter(Notification.order_id == order_id, Notification.notification_type == "DRAWING_REVISION")
           .one())
    return row.message


def test_staff_request_one_sheet(client, quiet):
    order_id = _request(client, "w1127_one", 2, ["orders/1/drawing/2.pdf"])
    expected = f"주문 #{order_id} (정하늘) 도면 수정 요청이 접수됐어요. 대상: 도면 2. 메모: 상부장 높이 2385 → 2290"
    assert _message(order_id) == expected
    assert [p["message"] for p in quiet if p.get("notification_type") == "DRAWING_REVISION"] == [expected]


def test_staff_request_many_sheets_has_no_count_tail(client, quiet):
    order_id = _request(client, "w1127_many", 3, ["orders/1/drawing/2.pdf", "orders/1/drawing/3.pdf"])
    message = _message(order_id)
    assert message == f"주문 #{order_id} (정하늘) 도면 수정 요청이 접수됐어요. 대상: 도면 2 · 3. 메모: 상부장 높이 2385 → 2290"
    assert "건)" not in message and "번 도면" not in message


def test_staff_request_without_numbers(client, quiet):
    order_id = _request(client, "w1127_none", 0, [])
    assert _message(order_id) == f"주문 #{order_id} (정하늘) 도면 수정 요청이 접수됐어요. 메모: 상부장 높이 2385 → 2290"


def test_partner_request_message(monkeypatch):
    """협력사 글 — 머리 "[협력사]" · "메모" · 꼬리 "(첨부 N건)" 그대로, 가운데 말투만."""
    monkeypatch.setattr(partner_revision, "partner_can_read_order", lambda user, order: True)
    monkeypatch.setattr(partner_revision, "normalize_revision_files",
                        lambda order_id, files: ([{"key": f"orders/{order_id}/drawing_gateway/revisions/a.jpg"}], []))
    user = _user("w1127_partner", role="STAFF", team="SALES", name="김도면")
    order = _order("박반장", 1)
    notification = partner_revision.request_partner_revision(db_session, user, order.id, "서랍 3단으로", [{}])
    assert notification.message == f"[협력사] 주문 #{order.id} (정하늘) 도면 수정 요청이 접수됐어요. 메모: 서랍 3단으로 (첨부 1건)"
    assert notification.title == "협력사 도면 수정 요청" and notification.target_team == "DRAWING"
    db_session.rollback()
