"""휴대폰 퀘스트 이름 — 버튼은 approve_label 만, 팀은 한글 이름으로."""
from __future__ import annotations

from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, User

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
