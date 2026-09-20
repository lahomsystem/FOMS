"""고객컨펌 승인 CTA·완료 배지 3표면 렌더(2026-09-17) — 실제 라우트로 그린다(합성 DOM 주입 금지).

* 모바일 큐 카드: CONFIRM 미승인 → ``<button … erp-queue-card__quest-approve data-approve-label="고객 컨펌 완료">``,
  옛 상세 링크 ``erp-queue-card__confirm-open`` 없음. 완료 quest → ``erp-queue-card__quest-done`` + "고객 컨펌 완료".
* 모바일 상세: 완료 quest → ``erp-quest-done`` 배지.
* PC 그리드: 완료 quest → ``erp-quest-done`` 배지.
"""
from __future__ import annotations

import pytest

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, User


def _make_user(username: str, *, team: str = "SALES") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
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


def _enable_mobile_v2(monkeypatch, user: User) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))


def _open_confirm_quest() -> dict:
    return {
        "stage": "CONFIRM", "title": "고객 컨펌", "description": "", "owner_team": "SALES",
        "owner_person": "", "status": "OPEN", "required_approvals": ["CS", "SALES"],
        "team_approvals": {}, "approval_mode": "assignee",
        "assignee_approval": {"approved": False, "approved_by": None, "approved_by_name": None, "approved_at": None},
        "created_at": "2026-09-16T00:00:00", "updated_at": "2026-09-16T00:00:00",
    }


def _done_confirm_quest() -> dict:
    return {
        "stage": "고객컨펌", "title": "고객 컨펌", "status": "COMPLETED", "approval_mode": "assignee",
        "required_approvals": ["CS", "SALES"], "team_approvals": {},
        "assignee_approval": {
            "approved": True, "approved_by": 12, "approved_by_name": "이다은담당", "approved_at": "2026-09-16T10:00:00",
        },
        "completed_at": "2026-09-16T10:00:00", "updated_at": "2026-09-16T10:00:00",
    }


def _create_order(*, quests: list[dict], customer_name: str = "표면 고객") -> Order:
    order = Order(
        received_date=get_today_kst().isoformat(),
        customer_name=customer_name,
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="CONFIRM",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "CONFIRM"},
            "parties": {"customer": {"name": customer_name, "phone": "010-1234-5678"}},
            "quests": quests,
        },
        erp_stage_code="CONFIRM",
    )
    db_session.add(order)
    db_session.commit()
    return order


def _queue_html(client) -> str:
    resp = client.get("/erp/dashboard", query_string={"stage": "고객컨펌", "view": "queue"})
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 1. 모바일 큐 카드
# --------------------------------------------------------------------------- #
def test_queue_card_renders_confirm_approve_button(client, monkeypatch):
    user = _make_user("disp_card_open")
    _login(client, user)
    _enable_mobile_v2(monkeypatch, user)
    order = _create_order(quests=[_open_confirm_quest()])

    html = _queue_html(client)
    assert f'data-order-id="{order.id}"' in html
    assert 'data-erp-mobile-v2="true"' in html
    assert "erp-queue-card__quest-approve" in html
    assert 'data-approve-label="고객 컨펌 완료"' in html
    assert "erp-queue-card__confirm-open" not in html
    # 승인 CTA 는 <a> 가 아니라 <button> 이어야 erp-quest-approve.js 가 잡는다.
    btn_at = html.index("erp-queue-card__quest-approve")
    tag_start = html.rfind("<", 0, btn_at)
    assert html[tag_start:tag_start + 7] == "<button", html[tag_start:tag_start + 40]
    assert "erp-queue-card__quest-done" not in html


def test_queue_card_renders_done_badge_for_completed_quest(client, monkeypatch):
    user = _make_user("disp_card_done")
    _login(client, user)
    _enable_mobile_v2(monkeypatch, user)
    order = _create_order(quests=[_done_confirm_quest()], customer_name="이다은")

    html = _queue_html(client)
    assert f'data-order-id="{order.id}"' in html or "이다은" in html
    assert "erp-queue-card__quest-done" in html
    assert "고객 컨펌 완료" in html
    assert "erp-queue-card__quest-approve" not in html
    assert "erp-queue-card__confirm-open" not in html


# --------------------------------------------------------------------------- #
# 2. 모바일 상세
# --------------------------------------------------------------------------- #
def test_mobile_detail_renders_done_badge(client, monkeypatch):
    user = _make_user("disp_detail_done")
    _login(client, user)
    _enable_mobile_v2(monkeypatch, user)
    order = _create_order(quests=[_done_confirm_quest()])

    resp = client.get(f"/erp/orders/{order.id}/mobile")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "erp-quest-done" in html
    assert "고객 컨펌 완료" in html
    assert "erp-mobile-quest-approve-assignee" not in html


def test_mobile_detail_renders_approve_button_for_open_quest(client, monkeypatch):
    """음성 대조군 — 미승인이면 배지 대신 승인 버튼(고객 컨펌 완료)."""
    user = _make_user("disp_detail_open")
    _login(client, user)
    _enable_mobile_v2(monkeypatch, user)
    order = _create_order(quests=[_open_confirm_quest()])

    html = client.get(f"/erp/orders/{order.id}/mobile").get_data(as_text=True)
    assert "erp-quest-done" not in html
    assert 'data-approve-label="고객 컨펌 완료"' in html


# --------------------------------------------------------------------------- #
# 3. PC 그리드
# --------------------------------------------------------------------------- #
def test_pc_grid_renders_done_badge(client):
    user = _make_user("disp_grid_done")
    _login(client, user)
    order = _create_order(quests=[_done_confirm_quest()], customer_name="그리드 완료")

    resp = client.get("/erp/dashboard", query_string={"stage": "고객컨펌"})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f'quest-collapse-{order.id}' in html
    assert "erp-quest-done" in html
    assert "고객 컨펌 완료" in html


def test_pc_grid_open_quest_has_no_done_badge(client):
    user = _make_user("disp_grid_open")
    _login(client, user)
    order = _create_order(quests=[_open_confirm_quest()], customer_name="그리드 진행")

    html = client.get("/erp/dashboard", query_string={"stage": "고객컨펌"}).get_data(as_text=True)
    assert f'quest-collapse-{order.id}' in html
    assert "erp-quest-done" not in html


# --------------------------------------------------------------------------- #
# 모바일 승인 버튼 노출 == 서버 팀 규칙 (2026-09-20 스테이징 페르소나 검수 P1)
# --------------------------------------------------------------------------- #
def _confirm_sd_for_display() -> dict:
    return {
        "workflow": {"stage": "CONFIRM"},
        "parties": {"manager": {"name": "다른 사람"}},
        "assignments": {},
        "quests": [{
            "stage": "CONFIRM", "title": "고객 컨펌", "status": "OPEN", "approval_mode": "assignee",
            "owner_team": "SALES", "required_approvals": ["CS", "SALES"],
            "assignee_approval": {"approved": False},
        }],
    }


@pytest.mark.parametrize("team,expected", [("CS", True), ("SALES", True), ("PRODUCTION", False), ("DRAWING", False)])
def test_confirm_mobile_button_follows_server_team_rule(team, expected):
    """담당자 이름이 비었거나 다른 사람이어도 CS·SALES 면 모바일에 [고객 컨펌 완료] 가 뜬다 — 서버가 200 을 주는 조합.
    PRODUCTION·DRAWING 은 서버가 403 이므로 버튼도 없다."""
    from types import SimpleNamespace
    from foms.services.erp_quest_display import build_current_quest_payload

    sd = _confirm_sd_for_display()
    user = SimpleNamespace(id=5, role="STAFF", team=team, name="검수자", username="auditor")
    order = SimpleNamespace(id=1, customer_name="고객", manager_name="다른 사람", structured_data=sd, is_erp_order=True)
    payload = build_current_quest_payload(sd=sd, stage="고객컨펌", stage_code="CONFIRM", order=order, current_user=user, user_map={})
    assert payload is not None
    assert payload["can_assignee_approve"] is expected
    assert payload["approve_label"] == "고객 컨펌 완료"
