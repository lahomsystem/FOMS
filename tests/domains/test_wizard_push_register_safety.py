"""마법사 "PUSH 했는데 주문 없음" 막기 (2026-10-20 설계서
docs/plans/2026-10-20-wizard-push-register-safety-spec.md).

- 실측 PUSH 는 "등록하고 PUSH" — 등록 성공 뒤 주문 기준 ``push-manual`` 을 text 없이 부르면
  서버가 저장된 주문으로 본문을 만든다.
- 발송 후 미등록 초안은 작성자 30분·관리자 2시간 뒤 1회 알림, 만료돼도 지우지 않는다.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash

import foms.api.channel.channel_integration as channel_integration
from db import db_session
from foms.services.channel_measure_message import build_measure_push_text
from foms.services.notifications import draft_send_reminder as reminder
from foms.services.order_draft_service import list_open_drafts
from models import Notification, Order, OrderDraft, User
from tools.cron.cleanup_order_drafts import run as run_cleanup

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime.datetime(2026, 10, 20, 5, 0, 0)


def _user(username: str, role: str = "STAFF", name: str = "작성자") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pass"),
        role=role,
        name=name,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _draft(user: User, key: str, *, history=None, expired: bool = False,
           order_id=None) -> OrderDraft:
    draft = OrderDraft(
        user_id=user.id,
        order_id=order_id,
        draft_key=key,
        step=4,
        payload={"schema_version": 1, "step": 4,
                 "data": {"customer_name": "박미영", "phone": "010-0000-0000",
                          "address": "송파 성내천로 50"}},
        expires_at=NOW + datetime.timedelta(days=-1 if expired else 7),
        send_history=history,
    )
    db_session.add(draft)
    db_session.commit()
    return draft


def _pushed(minutes_ago: int) -> dict:
    sent_at = (NOW - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return {"channeltalk_push_measure_room": {"pushed": True, "sent_at": sent_at,
                                              "message_id": "m1", "group_id": "g"}}


def _notifications(user_id: int) -> list[Notification]:
    return (
        db_session.query(Notification)
        .filter(Notification.target_user_id == user_id,
                Notification.notification_type == reminder.NOTIFICATION_TYPE)
        .all()
    )


# ---------------------------------------------------------------------------
# push-manual: measure_room 은 text 가 비면 서버가 조립한다
# ---------------------------------------------------------------------------


def _login_admin(client) -> User:
    user = _user("push-admin", role="ADMIN", name="관리자")
    response = client.post("/login", data={"username": "push-admin", "password": "pass"})
    assert response.status_code == 302
    return user


class _FakeStorage:
    def get_download_url(self, storage_key, expires_in=3600, **_kw):
        return f"https://cdn.example.com/{storage_key}"


def _push_setup(client, monkeypatch) -> dict:
    _login_admin(client)
    monkeypatch.setenv("CHANNEL_GROUP_MEASURE_ROOM", "group-room")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())
    captured: dict = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["data"] = data
        captured["count"] = captured.get("count", 0) + 1
        return {"success": True, "message_id": f"msg-room-{captured['count']}"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)
    return captured


def _order() -> int:
    order = Order(
        received_date="2026-10-20",
        customer_name="박미영",
        phone="010-4417-9114",
        address="송파 성내천로 50",
        product="여닫이 붙박이장",
        structured_data={
            "parties": {"customer": {"name": "박미영", "phone": "010-4417-9114"}},
            "site": {"address_full": "송파 성내천로 50"},
            "items": [{"product_name": "여닫이 붙박이장", "spec": "3300"}],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def test_measure_room_without_text_uses_server_composed_body(client, monkeypatch):
    captured = _push_setup(client, monkeypatch)
    order_id = _order()
    expected = build_measure_push_text(db_session.get(Order, order_id).structured_data)

    response = client.post("/api/channel/push-manual",
                           json={"order_id": order_id, "push_kind": "measure_room"})

    assert response.status_code == 200, response.get_json()
    assert captured["data"]["text"] == expected
    assert "박미영" in captured["data"]["text"]
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["channeltalk_push_measure_room"]["pushed"] is True


def test_measure_room_with_text_keeps_pc_form_text(client, monkeypatch):
    """PC 폼은 저장 전 화면 값을 보낸다 — text 가 오면 그대로 쓴다(동작 불변)."""
    captured = _push_setup(client, monkeypatch)
    order_id = _order()

    response = client.post("/api/channel/push-manual",
                           json={"order_id": order_id, "push_kind": "measure_room",
                                 "text": "PC 화면 글"})

    assert response.status_code == 200
    assert captured["data"]["text"] == "PC 화면 글"


def test_other_kinds_still_require_text(client, monkeypatch):
    _push_setup(client, monkeypatch)
    order_id = _order()

    response = client.post("/api/channel/push-manual",
                           json={"order_id": order_id, "push_kind": "measurement"})

    assert response.status_code == 400


def test_resend_after_change_needs_change_note(client, monkeypatch):
    """등록 뒤 정보가 바뀌어 다시 보내면 변경 내용이 필수이고 change_log 에 쌓인다."""
    captured = _push_setup(client, monkeypatch)
    order_id = _order()
    first = client.post("/api/channel/push-manual",
                        json={"order_id": order_id, "push_kind": "measure_room"})
    assert first.status_code == 200

    missing = client.post("/api/channel/push-manual",
                          json={"order_id": order_id, "push_kind": "measure_room"})
    assert missing.status_code == 400

    again = client.post("/api/channel/push-manual",
                        json={"order_id": order_id, "push_kind": "measure_room",
                              "change_note": "실측 시간 14시로 변경"})
    assert again.status_code == 200
    assert captured["data"]["is_retry"] is True
    db_session.expire_all()
    log = db_session.get(Order, order_id).structured_data[
        "channeltalk_push_measure_room"]["change_log"]
    assert log[-1]["note"] == "실측 시간 14시로 변경"


# ---------------------------------------------------------------------------
# 미등록 알림 스윕
# ---------------------------------------------------------------------------


def test_owner_reminded_once_after_30_minutes(app):
    owner = _user("draft-owner")
    draft = _draft(owner, "new.r1", history=_pushed(31))
    before_updated = draft.updated_at

    first = reminder.remind_unregistered_sent_drafts(db_session, now=NOW)
    db_session.commit()
    second = reminder.remind_unregistered_sent_drafts(db_session, now=NOW)
    db_session.commit()

    assert first["owner_reminded"] == 1
    assert second["owner_reminded"] == 0
    notes = _notifications(owner.id)
    assert len(notes) == 1
    assert "박미영" in notes[0].message and "실측 PUSH" in notes[0].message
    db_session.expire_all()
    saved = db_session.get(OrderDraft, draft.id)
    # 서버 쓰기가 If-Match 토큰(updated_at)을 흔들면 다음 autosave 가 409 로 튕긴다.
    assert saved.updated_at == before_updated
    assert saved.send_history[reminder.REMINDER_KEY]["owner_at"]
    assert saved.send_history["channeltalk_push_measure_room"]["pushed"] is True


def test_not_reminded_before_30_minutes_or_when_registered(app):
    owner = _user("draft-owner2")
    _draft(owner, "new.r2", history=_pushed(10))
    _draft(owner, "edit.r2", history=_pushed(90), order_id=_order())

    result = reminder.remind_unregistered_sent_drafts(db_session, now=NOW)

    assert result["owner_reminded"] == 0
    assert _notifications(owner.id) == []


def test_failed_send_only_is_not_reminded(app):
    owner = _user("draft-owner3")
    history = {"alimtalk_measurement": {"sent_at": None, "message_id": None,
                                        "error": "balance"}}
    _draft(owner, "new.r3", history=history)

    result = reminder.remind_unregistered_sent_drafts(db_session, now=NOW)

    assert result["owner_reminded"] == 0


def test_admin_reminded_after_two_hours(app):
    owner = _user("draft-owner4", name="하우드")
    admin = _user("draft-admin4", role="ADMIN", name="관리자")
    _draft(owner, "new.r4", history=_pushed(121))

    result = reminder.remind_unregistered_sent_drafts(db_session, now=NOW)
    db_session.commit()

    assert result["owner_reminded"] == 1
    assert result["admin_reminded"] == 1
    admin_notes = _notifications(admin.id)
    assert len(admin_notes) == 1
    assert "하우드" in admin_notes[0].message


def test_resend_after_reminder_reminds_again(app):
    owner = _user("draft-owner5")
    draft = _draft(owner, "new.r5", history=_pushed(40))
    reminder.remind_unregistered_sent_drafts(db_session, now=NOW)
    db_session.commit()

    history = dict(db_session.get(OrderDraft, draft.id).send_history)
    history["alimtalk_measurement"] = {"sent_at": NOW.isoformat(), "message_id": "a1",
                                       "error": None}
    draft.send_history = history
    db_session.commit()
    later = NOW + datetime.timedelta(minutes=31)
    result = reminder.remind_unregistered_sent_drafts(db_session, now=later)

    assert result["owner_reminded"] == 1


def test_reminder_type_is_pushed_to_phone():
    from foms.services.notifications.push_sender import _DEFAULT_P1_TYPES

    assert reminder.NOTIFICATION_TYPE in _DEFAULT_P1_TYPES


# ---------------------------------------------------------------------------
# 만료 보호: 지우지 않고, 작성 중 목록에 남긴다
# ---------------------------------------------------------------------------


def test_cleanup_keeps_expired_sent_draft(app):
    owner = _user("draft-owner6")
    sent_id = _draft(owner, "new.sent-expired", history=_pushed(60 * 24 * 8), expired=True).id
    plain_id = _draft(owner, "new.plain-expired", expired=True).id

    scanned, deleted = run_cleanup(execute=True, session=db_session)

    assert (scanned, deleted) == (1, 1)
    db_session.expire_all()
    remaining = {r.id for r in db_session.query(OrderDraft.id).all()}
    assert sent_id in remaining
    assert plain_id not in remaining


def test_open_draft_list_includes_expired_sent_draft(app):
    owner = _user("draft-owner7")
    sent = _draft(owner, "new.sent-list", history=_pushed(60), expired=True)
    _draft(owner, "new.plain-list", expired=True)

    rows = list_open_drafts(db_session, owner.id, now=NOW)

    assert [r.id for r in rows] == [sent.id]


# ---------------------------------------------------------------------------
# 관리자 화면
# ---------------------------------------------------------------------------


def test_admin_page_lists_and_discards(client):
    owner = _user("draft-owner8", name="하우드")
    sent_id = _draft(owner, "new.admin-list", history=_pushed(200)).id
    _draft(owner, "new.admin-failed",
           history={"alimtalk_measurement": {"error": "balance", "message_id": None}})
    _login_admin(client)

    page = client.get("/admin/sent-unregistered-drafts")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "박미영" in html and "하우드" in html
    assert html.count("버리기</button>") == 1

    response = client.post(f"/admin/sent-unregistered-drafts/{sent_id}/discard")
    assert response.status_code == 302
    db_session.expire_all()
    assert db_session.get(OrderDraft, sent_id) is None


def test_admin_page_is_admin_only(client):
    _user("draft-staff9", role="STAFF")
    client.post("/login", data={"username": "draft-staff9", "password": "pass"})

    response = client.get("/admin/sent-unregistered-drafts")

    assert response.status_code in (302, 403)


# ---------------------------------------------------------------------------
# 마법사 화면 계약
# ---------------------------------------------------------------------------


def test_wizard_channel_button_registers_then_pushes():
    js = (ROOT / "static/js/foms/wizard-send.js").read_text(encoding="utf-8")
    tpl = (ROOT / "templates/orders/wizard/step4_confirm.html").read_text(encoding="utf-8")
    shell = (ROOT / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")

    wizard = (ROOT / "static/js/foms/wizard.js").read_text(encoding="utf-8")
    # 4단계 큰 버튼 하나가 "등록하고 실측 PUSH" 를 맡는다(위 버튼은 2026-10-27 에 합쳤다).
    assert 'data-wizard-send="channel"' not in tpl
    assert '"등록하고 실측 PUSH"' in wizard
    assert "window.FomsWizardRegisterWithPush()" in wizard
    assert "window.FomsWizardRegisterWithPush = function" in js
    assert 'send: "/api/channel/push-manual"' in js
    # 등록 먼저 → 성공해야만 PUSH. 본문(text)은 보내지 않는다(서버 조립).
    register_at = js.index("client\n      .submitOrder()")
    push_at = js.index("fetch(ENDPOINTS.channel.send")
    assert register_at < push_at
    assert 'push_kind: "measure_room"' in js
    assert "payload.text" not in js
    assert "wizard-send.js') }}?v=20261027a" in shell


def test_wizard_register_and_push_success_goes_to_dashboard():
    """등록하고 PUSH 가 다 성공하면 대시보드로 간다(주문 수정 화면은 PUSH 실패 때만)."""
    js = (ROOT / "static/js/foms/wizard-send.js").read_text(encoding="utf-8")

    success_at = js.index("등록하고 실측 PUSH 완료")
    success_block = js[success_at:js.index("return;", success_at)]
    assert "goToDashboard(REDIRECT_DELAY_MS)" in success_block
    assert "goToOrder" not in success_block
    assert 'getAttribute("data-exit-href")' in js
    # PUSH 실패는 재전송이 필요하므로 주문 화면으로 간다.
    assert js.count("goToOrder(orderId, 0)") == 2


def test_single_button_always_registers_with_push():
    """4단계 등록 버튼은 모든 주문에서 "등록하고 실측 PUSH" 다(2026-10-27 — 지방 협력사 예외도 두지 않기로)."""
    wizard = (ROOT / "static/js/foms/wizard.js").read_text(encoding="utf-8")

    assert 'next.textContent = step < MAX_STEP ? "다음 →" : "등록하고 실측 PUSH";' in wizard
    assert "needsMeasurePush" not in wizard
    assert '"주문 등록"' not in wizard


def test_emergency_register_only_opens_when_push_cannot_go():
    """채널톡 PUSH 는 백업이다 — 못 보낼 때(미설정·본문 없음·미리보기 실패)도 ERP 등록은 할 수 있다."""
    js = (ROOT / "static/js/foms/wizard-send.js").read_text(encoding="utf-8")
    wizard = (ROOT / "static/js/foms/wizard.js").read_text(encoding="utf-8")

    assert 'showRegisterOnly(kind === "channel" && !!blocked);' in js
    assert js.count('showRegisterOnly(kind === "channel");') == 3, "flush 실패·미리보기 실패·통신 실패"
    assert "window.FomsWizardSubmitOnly();" in js
    assert "window.FomsWizardSubmitOnly = function" in wizard
