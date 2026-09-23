"""기존 결함 ② — 긴급 멘션 outbox ``NOTIFICATION`` 행의 실제 소비자.

긴급 멘션 라우트는 ``effect_type="NOTIFICATION"`` 행을 넣지만 그 타입의 handler 가 등록돼
있지 않았다. OS 푸시는 한 번도 나가지 않았고 행은 NoHandler 로 10회 재시도 뒤 DEAD 가 됐다.

여기서 고정하는 것:

* 러너가 ``NOTIFICATION`` 을 :func:`handle_notification_push` 로 등록한다.
* 새 알림이면 SIDEFX 세션으로 ``send_push_for_notification`` 을 1회 부르고 행은 DONE.
* 알림이 30분 넘게 지났으면 보내지 않고 DONE(배포 직후 밀린 행이 한꺼번에 울리지 않게).
* 웹 푸시 꺼짐(flag_off)은 재시도해도 같으므로 DONE.

실제 웹 푸시는 보내지 않는다(발송 함수 가짜 · 플래그 기본 꺼짐).
"""

from __future__ import annotations

import datetime as _dt
import uuid

import pytest
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import now_utc_naive
from foms.services.notifications import push_sender
from foms.services.notifications.notification_push_delivery import handle_notification_push
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.sidefx_worker import run_delivery_once
from models import (
    DomainSideEffectOutbox,
    Notification,
    NotificationEvent,
    NotificationEventType,
    User,
)
from tests.domains.test_sidefx_record_only_effects import _registered_effect_types


@pytest.fixture
def push_calls(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []

    def _send(nid, db=None, *, skip_attempted=False):
        calls.append((int(nid), db, skip_attempted))
        return {"sent": 1, "failed": 0, "revoked": 0, "reason": None}

    monkeypatch.setattr(push_sender, "send_push_for_notification", _send)
    return calls


def _urgent_mention(*, age: _dt.timedelta = _dt.timedelta(0)) -> tuple[int, int]:
    """긴급 멘션 라우트와 같은 모양으로 알림 + state + outbox 행을 만든다."""
    user = User(
        username=f"um_{uuid.uuid4().hex[:6]}",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="멘션 대상",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    notif = Notification(
        notification_type="URGENT_MENTION",
        target_type="USER",
        target_user_id=user.id,
        is_urgent=True,
        title="긴급 호출",
        created_at=now_utc_naive() - age,
    )
    db_session.add(notif)
    db_session.flush()
    fan_out_new_notification(db_session, notif)
    created_event = (
        db_session.query(NotificationEvent)
        .filter(
            NotificationEvent.notification_id == notif.id,
            NotificationEvent.event_type == NotificationEventType.CREATED,
        )
        .one()
    )
    row = enqueue_side_effect(
        db_session,
        source_domain="NOTIFICATION_EVENT",
        source_id=created_event.id,
        effect_type="NOTIFICATION",
        payload={"notification_id": notif.id, "recipient_user_id": user.id, "kind": "URGENT_MENTION"},
        dedupe_key=f"urgent_mention:{notif.id}",
    )
    db_session.commit()
    return notif.id, row.id


def _deliver() -> dict:
    handler = _registered_effect_types()["NOTIFICATION"]
    return run_delivery_once(
        engine,
        owner_hash="n" * 64,
        lease_token_fn=lambda: str(uuid.uuid4()),
        dispatch_fn=handler,
    )


def _status(row_id: int) -> str:
    db_session.expire_all()
    return db_session.get(DomainSideEffectOutbox, row_id).status


def test_runner_registers_real_notification_consumer():
    assert _registered_effect_types()["NOTIFICATION"] is handle_notification_push


def test_fresh_notification_sends_push_once_and_done(app, push_calls):
    nid, row_id = _urgent_mention()
    db_session.remove()
    result = _deliver()
    assert result["done"] == 1 and result["retried"] == 0 and result["dead"] == 0
    assert [c[0] for c in push_calls] == [nid]
    assert push_calls[0][1] is not None  # SIDEFX 세션을 그대로 넘긴다(rq 를 거치지 않음)
    assert push_calls[0][2] is True  # 재시도 때 이미 받은 사람은 건너뛴다
    assert _status(row_id) == "DONE"


def test_stale_notification_is_not_pushed(app, push_calls):
    _nid, row_id = _urgent_mention(age=_dt.timedelta(minutes=31))
    db_session.remove()
    assert _deliver()["done"] == 1
    assert push_calls == []
    assert _status(row_id) == "DONE"


def test_flag_off_finishes_without_retry(app, monkeypatch):
    """웹 푸시 꺼짐은 영구 사유 — 재시도하지 않고 DONE(실제 발송 함수, 플래그 off)."""
    monkeypatch.delenv("FOMS_WEB_PUSH_ENABLED", raising=False)
    _nid, row_id = _urgent_mention()
    db_session.remove()
    result = _deliver()
    assert result["done"] == 1 and result["retried"] == 0
    assert _status(row_id) == "DONE"


def test_missing_notification_id_is_noop(app, push_calls):
    _nid, row_id = _urgent_mention()
    row = db_session.get(DomainSideEffectOutbox, row_id)
    row.payload = {"kind": "URGENT_MENTION"}
    db_session.commit()
    db_session.remove()
    assert _deliver()["done"] == 1
    assert push_calls == []


def test_missing_sidefx_push_env_warns_once(app, push_calls, monkeypatch, caplog):
    from foms.services.notifications import notification_push_delivery as npd

    monkeypatch.setattr(npd, "_ENV_WARNED", False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("FOMS_WEB_PUSH_ENABLED", "1")
    monkeypatch.setenv("VAPID_CLAIMS_SUB", "mailto:ops@example.com")
    caplog.set_level("WARNING", logger="sidefx_notification_push")
    for _ in range(2):
        _urgent_mention()
    db_session.remove()
    assert _deliver()["done"] == 2
    warnings = [r for r in caplog.records if "VAPID_PRIVATE_KEY" in r.getMessage()]
    assert len(warnings) == 1
