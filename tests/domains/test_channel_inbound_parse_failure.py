"""CH-LATENT-02: 인바운드 파싱 실패를 보이게 만드는 계약 테스트.

파싱 실패는 지금까지 ``parse_failed`` 행 하나만 남기고 끝났다 — 보낸 사람은 접수된 줄
알고, 운영자에게는 볼 표면이 없었다. 이 스위트가 고정하는 것:

* 그룹 채팅이면 같은 방으로 실패 사유(빠진 항목)를 회신한다.
* **고객 1:1 대화(userChat)에는 회신하지 않는다** — 자동 안내가 고객에게 나가면 안 된다.
* 채널톡 환경변수 미설정이면 조용히 건너뛴다(수신 처리를 깨뜨리지 않는다).
* 어떤 경우에도 운영 로그에는 ``parse_failed`` 가 남는다.
"""

import logging

import foms.services.channel_client as channel_client
import foms.services.channel_inbound as channel_inbound
from db import db_session
from models import ChannelInboundEventLog


class _FakeLog:
    """``_notify_parse_failure`` 가 읽는 필드만 가진 최소 대역."""

    def __init__(self, chat_type=None, source_chat_id=None, log_id=1):
        self.chat_type = chat_type
        self.source_chat_id = source_chat_id
        self.id = log_id


def _capture_sends(monkeypatch):
    sent = []

    def _fake_send(group_id, plain_text, blocks=None, files=None, bot_name="FOMS", raise_on_error=False):
        sent.append({"group_id": group_id, "plain_text": plain_text, "bot_name": bot_name})
        return {"success": True, "message_id": "notice-1"}

    monkeypatch.setattr(channel_client, "send_group_message", _fake_send)
    monkeypatch.setattr(channel_client, "is_configured", lambda: True)
    return sent


def test_group_chat_gets_failure_notice_with_missing_fields(monkeypatch):
    sent = _capture_sends(monkeypatch)

    channel_inbound._notify_parse_failure(
        _FakeLog(chat_type="group", source_chat_id="209990"), ["phone", "address"]
    )

    assert len(sent) == 1
    assert sent[0]["group_id"] == "209990"
    assert "phone, address" in sent[0]["plain_text"]
    assert "주문 자동 접수 실패" in sent[0]["plain_text"]


def test_user_chat_gets_no_automated_reply(monkeypatch):
    """고객 1:1 대화에는 자동 실패 안내를 보내지 않는다."""
    sent = _capture_sends(monkeypatch)

    channel_inbound._notify_parse_failure(
        _FakeLog(chat_type="userChat", source_chat_id="u-1"), ["phone"]
    )

    assert sent == []


def test_missing_chat_id_sends_nothing(monkeypatch):
    sent = _capture_sends(monkeypatch)

    channel_inbound._notify_parse_failure(_FakeLog(chat_type="group", source_chat_id=""), ["phone"])

    assert sent == []


def test_unconfigured_channel_skips_notice_without_raising(monkeypatch):
    sent = _capture_sends(monkeypatch)
    monkeypatch.setattr(channel_client, "is_configured", lambda: False)

    channel_inbound._notify_parse_failure(
        _FakeLog(chat_type="group", source_chat_id="209990"), ["phone"]
    )

    assert sent == []


def test_parse_failure_always_reaches_operator_log(monkeypatch, caplog):
    """회신을 못 보내는 경우에도 운영 로그에는 남아야 한다(무음 금지)."""
    _capture_sends(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="foms.services.channel_inbound"):
        channel_inbound._notify_parse_failure(
            _FakeLog(chat_type="userChat", source_chat_id="u-1", log_id=77), ["phone"]
        )

    messages = [r.getMessage() for r in caplog.records]
    assert any("parse_failed" in m and "log=77" in m and "phone" in m for m in messages)


def test_worker_notifies_when_text_cannot_be_parsed(app, monkeypatch):
    """process_inbound_job 이 parse_failed 로 끝날 때 안내 경로를 실제로 탄다(app=스키마)."""
    sent = _capture_sends(monkeypatch)

    log = ChannelInboundEventLog(
        dedupe_key="evt_parse_fail_1",
        payload_hash="h" * 64,
        chat_type="group",
        source_chat_id="209990",
        status="received",
        raw_payload={"entity": {"plainText": "안녕하세요 견적 문의합니다"}},
    )
    db_session.add(log)
    db_session.commit()
    log_id = log.id

    channel_inbound.process_inbound_job(log_id)

    db_session.expire_all()
    saved = db_session.get(ChannelInboundEventLog, log_id)
    assert saved.status == "parse_failed"
    assert len(sent) == 1
    assert sent[0]["group_id"] == "209990"
