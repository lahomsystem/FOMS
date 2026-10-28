"""CS 상담 상태 재료(플랜 C1-2) 가장자리 — 거른 글 · 파생 칸 · 30일 나눔 · 재시도 · 양동이 내려감 · 창 밖 줄.

완료 기준 목록은 ``test_cs_channel_read`` 에 있다. 손으로 꾸민 합성 글만 쓴다.
"""

from __future__ import annotations

import datetime
import email.utils
import logging

import pytest
import requests
from redis.exceptions import ConnectionError as RedisConnectionError

from db import db_session
from foms.services.cs_agent import channel_read as cr
from foms.services.cs_agent import read_budget as rb
from foms.services.cs_agent import state_store as ss
from foms.services.cs_agent.state import KST
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    HAUD_CHANNEL,
    FakeClock,
    FakeRedis,
    FakeResponse,
    FakeTransport,
    api_message,
    at,
    derived,
    entity,
    inbound,
    keys,
    make_reader,
    message_count,
    msg_row,
    snap,
    state_of,
)


def test_derive_skips_what_is_not_a_known_user_chat_message():
    assert cr.derive_message(entity("m1", at(2, 10), chatType="group"))[1] == "not_user_chat"
    assert cr.derive_message(entity("m1", at(2, 10), createdAt=None))[1] == "no_created_at"
    assert cr.derive_message(entity("", at(2, 10)))[1] == "no_ids"
    assert cr.derive_message(entity("x" * 65, at(2, 10)))[1] == "bad_ids"
    assert cr.derive_message(None)[1] == "no_entity"


def test_derived_fields_are_computed_once_and_text_is_dropped():
    customer = derived("m1", at(2, 10), text="네 감사합니다!")
    assert customer.is_closing is True and customer.is_code_message is False
    photo = derived("m2", at(2, 10), text="", files=[{"name": "a.jpg"}])
    assert photo.has_file is True and photo.is_closing is False
    staff = derived("m3", at(2, 10, 10), person="manager", text="내일 다시 연락드리겠습니다")
    assert (staff.promise_kind, staff.promise_rule) == ("chat", "내일")
    assert staff.promise_due_at == at(3, 17).astimezone(datetime.timezone.utc)
    memo = derived("m4", at(2, 10), person="manager", text="내일 연락드릴게요", options=["MESSAGE_OPTION_PRIVATE"])
    assert memo.is_private and memo.promise_kind is None
    assert derived("m5", at(2, 10), person="bot", text="배정", log={"action": "assign"}).is_log
    # 파생 칸 어디에도 글 원문 칸이 없다.
    assert not {"text", "plain_text", "plainText"} & set(vars(staff))


def test_ingest_counts_skipped_rows(app):
    inbound(1, entity("m1", at(2, 10), chatType="group", chat="grp-1"))
    inbound(2, entity("m2", at(2, 10), channel="999"))
    inbound(3, entity("m3", at(2, 10), text="문의요"))
    result = ss.ingest_inbound(db_session)
    assert result.inserted == 1 and result.skipped == {"not_user_chat": 1, "unknown_channel": 1}


def test_customer_message_after_closed_snapshot_reopens(app):
    inbound(1, entity("m1", at(2, 10), text="문의 하나 더요"))
    ss.ingest_inbound(db_session)
    ss.apply_chat_snapshots(db_session, [snap("closed", at(2, 9))])
    assert state_of().needs_reply  # 닫힘을 읽은 뒤 손님이 또 썼다
    ss.apply_chat_snapshots(db_session, [snap("closed", at(2, 10, 30))])
    assert not state_of().is_open


def test_row_outside_lookback_window_is_filled_by_chat_recheck(app):
    """뒤돌아 읽기 창(여기선 1줄)을 넘긴 늦은 줄은 바퀴가 못 본다 — 보정의 상담 다시 읽기가 메운다."""
    inbound(102, entity("m2", at(2, 10, 1), text="두 번째 글"))
    inbound(101, entity("m1", at(2, 10, 0), text="첫 번째 글"))
    ss.ingest_inbound(db_session, lookback=1)
    assert message_count() == 1
    api = [derived("m1", at(2, 10, 0)), derived("m2", at(2, 10, 1))]
    assert ss.find_missing_inbound(db_session, "uc-1", api, now=at(2, 12)) == []
    assert msg_row("m1").inbound_log_id == 101


def test_long_range_is_split_into_30_day_windows(keys):
    clock = FakeClock()
    transport = FakeTransport(*[FakeResponse(200, {"userChats": []}) for _ in range(3)])
    start = datetime.datetime(2026, 9, 1, tzinfo=KST)
    end = datetime.datetime(2026, 11, 1, tzinfo=KST)
    assert list(make_reader(transport, clock).iter_user_chats("LAHOM", changed_from=start, changed_to=end)) == []
    spans = [(call["params"]["from"], call["params"]["to"]) for call in transport.calls]
    assert spans[0][0] == int(start.timestamp() * 1000) and spans[-1][1] == int(end.timestamp() * 1000)
    assert all(b - a <= 30 * 86400 * 1000 for a, b in spans)
    assert all(spans[i][1] == spans[i + 1][0] for i in range(len(spans) - 1))
    with pytest.raises(ValueError):
        make_reader(FakeTransport(), clock).list_user_chats("LAHOM", changed_from=start, changed_to=end)


def test_read_messages_fills_chat_and_channel_and_keeps_brand(keys):
    body = {"messages": [api_message("m2", at(2, 10, 5), "manager", "네 안녕하세요"),
                         api_message("m1", at(2, 10), "user", "문의요"),
                         api_message("x1", at(2, 10, 6), "user", "다른 채널 글", channelId=HAUD_CHANNEL)]}
    transport = FakeTransport(FakeResponse(200, body))
    messages = make_reader(transport, FakeClock()).read_messages("LAHOM", "uc-1", limit=20)
    assert [(m.message_id, m.chat_id, m.brand) for m in messages] == [("m1", "uc-1", "LAHOM"), ("m2", "uc-1", "LAHOM")]
    (call,) = transport.calls
    assert call["url"] == "https://api.channel.io/open/user-chats/uc-1/messages"
    assert call["params"] == {"limit": 20, "sortOrder": "desc"}


def test_429_without_retry_after_backs_off(keys):
    clock = FakeClock()
    transport = FakeTransport(FakeResponse(429), FakeResponse(200, {"messages": []}))
    assert make_reader(transport, clock).read_messages("LAHOM", "uc-1") == []
    assert clock.sleeps == [1.0]


def test_odd_retry_after_values_are_bounded(keys):
    def header(value, name="Retry-After"):
        return rb.retry_after_seconds(FakeResponse(429, headers={name: value}))

    assert header("inf") is None and header("nan") is None and header("soon") is None
    assert header("99999") == rb.MAX_RETRY_AFTER_SECONDS
    assert header("1.5", name="retry-after") == 1.5
    later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
    assert 25 <= header(email.utils.format_datetime(later, usegmt=True)) <= 30
    # 못 읽는 값이면 지수 대기로 — 그 채널을 무한히 막지 않는다.
    clock = FakeClock()
    transport = FakeTransport(FakeResponse(429, headers={"Retry-After": "inf"}), FakeResponse(200, {"messages": []}))
    assert make_reader(transport, clock).read_messages("LAHOM", "uc-1") == []
    assert clock.sleeps == [1.0]


def test_server_error_and_network_error_retry_then_client_error_stops(keys):
    clock = FakeClock()
    transport = FakeTransport(FakeResponse(503), requests.ConnectionError("down"), FakeResponse(200, {"messages": []}))
    assert make_reader(transport, clock).read_messages("LAHOM", "uc-1") == []
    assert clock.sleeps == [1.0, 2.0]
    missing = FakeTransport(FakeResponse(404))
    with pytest.raises(cr.ChannelReadError) as info:
        make_reader(missing, clock).read_messages("LAHOM", "uc-1")
    assert info.value.status == 404 and len(missing.calls) == 1


def test_missing_keys_mean_not_configured(monkeypatch):
    monkeypatch.delenv("CHANNEL_OPENAPI_KEY_LAHOM", raising=False)
    monkeypatch.delenv("CHANNEL_OPENAPI_SECRET_LAHOM", raising=False)
    transport = FakeTransport()
    with pytest.raises(cr.OpenApiNotConfigured):
        make_reader(transport, FakeClock()).read_messages("LAHOM", "uc-1")
    assert transport.calls == []


def test_redis_budget_falls_back_to_local_with_one_warning(caplog):
    class BrokenRedis:
        def pttl(self, key):
            raise RedisConnectionError("down")

        def set(self, key, value, px=None):
            raise RedisConnectionError("down")

    budget = rb.RedisChannelBudget(BrokenRedis(), {"message": 1}, clock=FakeClock())
    with caplog.at_level(logging.WARNING, logger=rb.logger.name):
        assert budget.acquire("LAHOM", "message") == 0.0
        assert budget.acquire("LAHOM", "message") > 0  # 프로세스 안 몫(1)을 지킨다
        budget.block("HAUD", 3)
        assert budget.acquire("HAUD", "message") == pytest.approx(3)
    assert sum("내려감" in record.getMessage() for record in caplog.records) == 1


def test_default_budget_uses_shared_redis_when_present(monkeypatch, caplog):
    monkeypatch.setattr(rb, "get_dashboard_redis", lambda: None)
    with caplog.at_level(logging.WARNING, logger=rb.logger.name):
        assert isinstance(rb.default_budget(), rb.LocalChannelBudget)
    assert any("Redis 없음" in record.getMessage() for record in caplog.records)
    monkeypatch.setattr(rb, "get_dashboard_redis", lambda: FakeRedis(FakeClock()))
    assert isinstance(rb.default_budget(), rb.RedisChannelBudget)
