"""휴대폰 퀘스트 이름 — 버튼은 approve_label 만, 팀은 한글 이름으로."""
from __future__ import annotations

from pathlib import Path

from flask import render_template_string
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, ProductionRun, User

ROOT = Path(__file__).resolve().parents[2]
DETAIL = "templates/orders/partials/order_detail_mobile_v2.html"
QUEUE_CARD = "templates/partials/shared/erp_mobile_queue_card_v2.html"
APPROVE_JS = "static/js/foms/erp-quest-approve.js"

DETAIL_BANNED = (" 전달{% endif %}", "{{ team }} {{ quest_approve_label }}", "팀 승인으로")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _banned_hits(text: str, banned) -> list[str]:
    return [s for s in banned if s in text]


def test_detail_template_uses_approve_label_only():
    text = _read(DETAIL)
    assert _banned_hits(text, DETAIL_BANNED) == []
    assert "{{ team|team_label }} 대기" in text
    assert "{{ team|team_label }} 완료" in text


def test_detail_banned_check_catches_old_tail():
    old = "{{ quest_approve_label }}{% if x %} → {{ order.current_quest.next_stage_label }} 전달{% endif %}"
    assert _banned_hits(old, DETAIL_BANNED) == [" 전달{% endif %}"]


def test_queue_card_aria_labels_are_plain():
    assert "단계로 넘김" not in _read(QUEUE_CARD)


def test_approve_toast_texts():
    js = _read(APPROVE_JS)
    assert "기록 완료" not in js
    assert "승인 완료 —" not in js
    assert "단계로 넘겼습니다." in js


def test_mobile_detail_renders_team_button_names(client, monkeypatch):
    user = User(
        username="mqn_cs", password=generate_password_hash("pw"), role="ADMIN",
        team="CS", name="mqn_cs 이름", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    order = Order(
        received_date=get_today_kst().isoformat(),
        customer_name="이름 고객", phone="010-1234-5678", address="서울 테헤란로 123",
        product="붙박이장", status="RECEIVED", manager_name="Bob", is_erp_order=True,
        structured_data={
            "workflow": {"stage": "RECEIVED"},
            "parties": {"customer": {"name": "이름 고객", "phone": "010-1234-5678"}},
            "quests": [{
                "stage": "RECEIVED", "title": "주문 정보 확인", "description": "", "owner_team": "CS",
                "owner_person": "", "status": "OPEN", "required_approvals": ["CS"],
                "team_approvals": {}, "approval_mode": "team",
                "created_at": "2026-09-30T00:00:00", "updated_at": "2026-09-30T00:00:00",
            }],
        },
        erp_stage_code="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(f"/erp/orders/{order.id}/mobile")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-approve-label="실측 단계로 넘기기"' in html
    assert "CS팀으로 진행합니다." in html


def _login_mobile(client, monkeypatch, username: str) -> User:
    user = User(
        username=username, password=generate_password_hash("pw"), role="ADMIN",
        team="CS", name=f"{username} 이름", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    return user


def _stage_order(stage: str, team: str, *, stored_quest: bool = True) -> Order:
    quests = [{
        "stage": stage, "title": stage, "description": "", "owner_team": team,
        "owner_person": "", "status": "OPEN", "required_approvals": [team],
        "team_approvals": {}, "approval_mode": "team",
        "created_at": "2026-09-30T00:00:00", "updated_at": "2026-09-30T00:00:00",
    }] if stored_quest else []
    order = Order(
        received_date=get_today_kst().isoformat(),
        customer_name="보드 고객", phone="010-2222-3333", address="서울 테헤란로 1",
        product="붙박이장", status=stage, manager_name="Bob", is_erp_order=True,
        structured_data={
            "workflow": {"stage": stage},
            "parties": {"customer": {"name": "보드 고객", "phone": "010-2222-3333"}},
            "quests": quests,
        },
        erp_stage_code=stage,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _quest_section(client, order_id: int) -> tuple[str, str]:
    resp = client.get(f"/erp/orders/{order_id}/mobile")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="foms-detail-quest"' in html
    section = html.split('id="foms-detail-quest"', 1)[1].split("</section>", 1)[0]
    return html, section


def test_mobile_detail_production_board_state(client, monkeypatch):
    _login_mobile(client, monkeypatch, "mqn_prod")
    order = _stage_order("PRODUCTION", "PRODUCTION", stored_quest=False)

    html, section = _quest_section(client, order.id)
    assert '<p class="mb-0">제작대기</p>' in section
    assert f'href="/erp/production/dashboard?focus_order={order.id}"' in section
    assert "생산 보드 열기" in section
    assert "erp-mobile-quest-approve" not in html

    db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    _, section = _quest_section(client, order.id)
    assert '<p class="mb-0">제작중</p>' in section
    assert "제작대기" not in section


def test_mobile_detail_production_stored_open_quest_keeps_approve(client, monkeypatch):
    _login_mobile(client, monkeypatch, "mqn_prod_open")
    order = _stage_order("PRODUCTION", "PRODUCTION")

    _, section = _quest_section(client, order.id)
    assert "생산 보드 열기" not in section
    assert "erp-mobile-quest-approve" in section


def test_mobile_detail_construction_board_state(client, monkeypatch):
    _login_mobile(client, monkeypatch, "mqn_cons")
    order = _stage_order("CONSTRUCTION", "CONSTRUCTION")

    _, section = _quest_section(client, order.id)
    assert '<p class="mb-0">시공대기</p>' in section
    assert f'href="/erp/construction/dashboard?focus_order={order.id}"' in section
    assert "시공 보드 열기" in section


def test_mobile_detail_completed_board_state(client, monkeypatch):
    _login_mobile(client, monkeypatch, "mqn_done")
    order = _stage_order("COMPLETED", "CS")

    html, section = _quest_section(client, order.id)
    assert '<p class="mb-0">완료</p>' in section
    assert "href=" not in section
    assert "erp-mobile-quest-approve" not in html


def test_mobile_detail_as_board_state(client, monkeypatch):
    _login_mobile(client, monkeypatch, "mqn_as")
    order = _stage_order("AS", "CS")

    html, section = _quest_section(client, order.id)
    assert '<p class="mb-0">AS 확인</p>' in section
    assert f'href="/erp/as?focus_order={order.id}"' in section
    assert "AS 화면 열기" in section
    assert "erp-mobile-quest-approve" not in html


def test_queue_card_quest_actionable_skips_board_state(app):
    text = _read(QUEUE_CARD)
    expr = text.split("{% set quest_actionable =", 1)[1].split("%}", 1)[0]
    assert "(not order.board_state)" in expr

    src = ("{% from 'partials/shared/erp_mobile_queue_card_v2.html' import render_queue_card_v2 %}"
           "{{ render_queue_card_v2(o) }}")
    quest = {
        "title": "제작", "approve_label": "시공 단계로 넘기기", "approve_confirm": "",
        "all_approved": False, "is_done": False, "can_assignee_approve": False,
        "approvable_teams": ["PRODUCTION"], "approval_mode": "team", "advances_stage": True,
    }
    board_state = {
        "kind": "production", "label": "제작대기", "tone": "soft", "title": "",
        "link_label": "생산 보드 열기",
        "link_endpoint": "erp_production_page.erp_production_dashboard", "link_params": {},
    }
    base = {"id": 7, "customer_name": "고객", "address": "주소 1", "phone": "010-1", "alerts": {},
            "structured_data": {}, "stage_code": "PRODUCTION", "current_quest": quest}
    with app.test_request_context("/"):
        plain = render_template_string(src, o=base)
        guarded = render_template_string(src, o={**base, "board_state": board_state})
    assert "erp-queue-card__quest-approve" in plain
    assert "erp-queue-card__quest-approve" not in guarded

def test_queue_card_done_chip_hidden_under_board_state(app):
    src = ("{% from 'partials/shared/erp_mobile_queue_card_v2.html' import render_queue_card_v2 %}"
           "{{ render_queue_card_v2(o) }}")
    quest = {"title": "생산 확인", "is_done": True, "done_label": "생산 확인 완료",
             "can_retransition": False, "all_approved": True}
    board_state = {
        "kind": "completed", "label": "완료", "tone": "ok", "title": "",
        "link_label": "", "link_endpoint": "", "link_params": {},
    }
    base = {"id": 7, "customer_name": "고객", "address": "주소 1", "phone": "010-1", "alerts": {},
            "structured_data": {}, "stage_code": "COMPLETED", "current_quest": quest}
    with app.test_request_context("/"):
        plain = render_template_string(src, o=base)
        guarded = render_template_string(src, o={**base, "board_state": board_state})
    assert "생산 확인 완료" in plain
    assert "erp-queue-card__quest-done" in plain
    assert "생산 확인 완료" not in guarded
    assert "erp-queue-card__quest-done" not in guarded
