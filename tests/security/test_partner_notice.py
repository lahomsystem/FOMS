"""협력사 공지 창(사용자 2026-11-02) — "확인"을 눌러야 닫힌다.

알림 표를 쓴다: 협력사 직원마다 PARTNER_NOTICE 한 건, 확인 = 그 직원 state.ack_at. 대조군: 다른 직원 공지 · 우리 직원 ·
꺼진 협력사 계정 · 같은 제목 다시 보내기.
"""
from __future__ import annotations

from pathlib import Path

from db import db_session
from foms.services.partners.notices import create_partner_notice, pending_partner_notices
from models import Notification, NotificationUserState, User
from tests.security.partner_fixtures import _client, world  # noqa: F401 — pytest fixture 재노출

ROOT = Path(__file__).resolve().parents[2]


def _send(title="실측 전 주문 안내", message="첫 줄\n둘째 줄") -> list[dict]:
    rows = create_partner_notice(db_session, title=title, message=message, actor_user_id=None,
                                 actor_name="라홈 본사", apply=True)
    db_session.commit()
    return rows


def test_notice_goes_to_partner_staff_only_once(app, world):
    off = db_session.get(User, world["partner_a2"])
    off.is_active = False
    db_session.commit()
    rows = _send()
    sent = {r["user_id"] for r in rows if r["verdict"] == "SENT"}
    assert sent == {world["partner_a"], world["partner_b"]}  # 우리 직원 · 꺼진 계정 없음
    again = _send()
    assert {r["verdict"] for r in again} == {"SKIP_ALREADY"}
    assert db_session.query(Notification).filter(Notification.notification_type == "PARTNER_NOTICE").count() == 2


def test_popup_shows_until_ok_then_next_notice(app, world):
    _send("첫 공지", "가\n나")
    _send("둘째 공지", "다")
    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get("/partner").get_data(as_text=True)
    assert "data-pp-notice" in page and "첫 공지" in page and "partner-notice.js" in page
    first = pending_partner_notices(db_session, db_session.get(User, world["partner_a"]))[0]["id"]

    resp = client.post(f"/api/partner/notices/{first}/ack")
    assert resp.status_code == 200
    assert [n["title"] for n in resp.get_json()["data"]["pending"]] == ["둘째 공지"]
    state = db_session.query(NotificationUserState).filter(NotificationUserState.notification_id == first).one()
    assert state.ack_at is not None and state.read_at is not None

    second = resp.get_json()["data"]["pending"][0]["id"]
    assert client.post(f"/api/partner/notices/{second}/ack").get_json()["data"]["pending"] == []
    page = client.get("/partner").get_data(as_text=True)
    assert "data-pp-notice" not in page and "partner-notice.js" not in page


def test_cannot_ack_someone_elses_notice(app, world):
    _send()
    mine = pending_partner_notices(db_session, db_session.get(User, world["partner_a"]))[0]["id"]
    other = _client(app, db_session.get(User, world["partner_b"]))
    assert other.post(f"/api/partner/notices/{mine}/ack").status_code == 404
    assert pending_partner_notices(db_session, db_session.get(User, world["partner_a"]))[0]["id"] == mine
    staff = _client(app, db_session.get(User, world["staff"]))
    assert staff.post(f"/api/partner/notices/{mine}/ack").status_code in (302, 403)


def test_popup_closes_only_with_ok_and_has_no_inline_style() -> None:
    js = (ROOT / "static/js/partner/partner-notice.js").read_text(encoding="utf-8")
    assert "Escape" in js and "preventDefault" in js
    modal = (ROOT / "templates/partner/partials/notice_modal.html").read_text(encoding="utf-8")
    assert "data-pp-notice-ok" in modal and 'style="' not in modal and "data-bs-dismiss" not in modal
    assert "pp-notice__backdrop" in modal
