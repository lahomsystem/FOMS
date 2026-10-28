"""CS 상담 상태 재료(플랜 C1-2) — 수신 기록 뒤돌아 읽기 · 상태 표 · Open API 읽기 · 수신 누락 경보.

완료 기준 목록(429 · cursor · 빈 응답 · 브랜드 짝 · 우리 봇 메모 제외 · 확인코드 글 제외 · 수신 누락 경보 ·
늦게 온 옛 글 · 늦은 커밋 줄 · 있으면 무시)을 여기서 본다. 가장자리 경우는 ``test_cs_channel_read_edges``.
손으로 꾸민 합성 글만 쓴다(재료 · 가짜는 ``tests.support.cs_agent_fakes``).
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.cs_agent import channel_read as cr
from foms.services.cs_agent import read_budget as rb
from foms.services.cs_agent import state
from foms.services.cs_agent import state_store as ss
from models import CsAgentMessage
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    CODE_TEXT,
    HAUD_CHANNEL,
    LAHOM_CHANNEL,
    FakeClock,
    FakeRedis,
    FakeResponse,
    FakeTransport,
    api_message,
    at,
    chat_row,
    derived,
    entity,
    inbound,
    keys,
    make_reader,
    message_count,
    msg_row,
    naive,
    snap,
    state_of,
)


# ── 브랜드 짝 ───────────────────────────────────────────────────────────


def test_brand_mapping_lives_in_one_place():
    assert cr.brand_for_channel(LAHOM_CHANNEL) == "LAHOM"
    assert cr.brand_for_channel(int(HAUD_CHANNEL)) == "HAUD"
    assert cr.brand_for_channel("999") is None and cr.brand_for_channel(None) is None
    assert cr.channel_for_brand("HAUD") == HAUD_CHANNEL
    with pytest.raises(ValueError):
        cr.channel_for_brand("OTHER")
    # 짝의 브랜드 이름은 운영 시간 표 · Open API 키 이름과 같다.
    assert set(cr.CHANNEL_BRANDS.values()) == set(state.BRAND_HOURS)
    # 모르는 채널 글 · Open API 로 읽은 브랜드와 다른 채널 글은 거른다.
    assert cr.derive_message(entity("m1", at(2, 10), channel="999"))[1] == "unknown_channel"
    haud = entity("m1", at(2, 10), channel=HAUD_CHANNEL)
    assert cr.derive_message(haud, expected_brand="LAHOM")[1] == "unknown_channel"
    assert cr.derive_message(haud)[0].brand == "HAUD"


# ── 수신 기록 뒤돌아 읽기 · 있으면 무시 ─────────────────────────────────


def test_ingest_stores_derived_fields_only(app):
    inbound(1, entity("m1", at(2, 10), text="색상 문의요", files=[{"name": "a.jpg"}]))
    inbound(2, entity("m2", at(2, 10, 10), person="manager", text="내일 다시 연락드리겠습니다"))
    result = ss.ingest_inbound(db_session)

    assert (result.examined, result.inserted, result.duplicates) == (2, 2, 0)
    customer, staff = msg_row("m1"), msg_row("m2")
    assert customer.has_file and customer.is_closing is False and customer.source == "webhook"
    assert customer.created_at == naive(at(2, 10)) and customer.inbound_log_id == 1
    assert (staff.promise_kind, staff.promise_rule, staff.promise_due_at) == ("chat", "내일", naive(at(3, 17)))
    # 표에도 원문 칸이 없고, 어느 값에도 글이 들어가지 않았다.
    assert not {"text", "plain_text", "plainText"} & set(CsAgentMessage.__table__.c.keys())
    for row in (customer, staff):
        assert not any("문의" in str(value) or "연락" in str(value) for value in row)
    chat = chat_row()
    assert (chat.brand, chat.channel_id, chat.last_user_message_id, chat.last_answer_message_id) == (
        "LAHOM", LAHOM_CHANNEL, "m1", "m2")


def test_insert_or_ignore_is_idempotent(app):
    inbound(1, entity("m1", at(2, 10), text="문의요"))
    first = ss.ingest_inbound(db_session)
    second = ss.ingest_inbound(db_session)
    assert first.inserted == 1
    # 이미 넣은 수신 줄은 원본을 다시 열지 않는다.
    assert (second.examined, second.inserted) == (0, 0)

    again = ss.store_messages(db_session, [derived("m1", at(2, 10)), derived("m1", at(2, 10))], source="openapi")
    db_session.commit()
    assert (again.inserted, again.duplicates) == (0, 1)
    # 같은 글이 두 번째 수신 줄로 또 와도 한 줄이고, 첫 수신 줄 id 가 남는다.
    inbound(2, entity("m1", at(2, 10), text="문의요"))
    third = ss.ingest_inbound(db_session)
    assert (third.inserted, third.duplicates) == (0, 1)
    assert message_count() == 1
    row = msg_row("m1")
    assert (row.source, row.inbound_log_id) == ("webhook", 1)


def test_row_committed_late_with_lower_id_is_still_ingested(app):
    """id 를 먼저 받고 늦게 커밋한 줄(웹 gevent 2 프로세스, R4-1) — 커서였다면 건너뛴다."""
    inbound(102, entity("m2", at(2, 10, 1), text="두 번째 글"))
    assert ss.ingest_inbound(db_session).inserted == 1
    inbound(101, entity("m1", at(2, 10, 0), text="첫 번째 글"))

    result = ss.ingest_inbound(db_session)
    assert (result.examined, result.inserted) == (1, 1)
    assert {msg_row("m1").inbound_log_id, msg_row("m2").inbound_log_id} == {101, 102}


def test_late_older_message_never_overwrites_newer_state(app):
    inbound(1, entity("m2", at(2, 10, 30), text="새 글"))
    inbound(2, entity("a2", at(2, 10, 40), person="manager", text="네 확인했습니다"))
    ss.ingest_inbound(db_session)
    # 옛 글이 늦게 온다(웹훅 재전송 · Open API 보정).
    inbound(3, entity("m1", at(2, 10, 0), text="옛 글"))
    inbound(4, entity("a1", at(2, 10, 20), person="manager", text="안녕하세요"))
    ss.ingest_inbound(db_session)
    ss.store_messages(db_session, [derived("m0", at(2, 9), text="더 옛 글")], source="openapi")
    db_session.commit()

    chat = chat_row()
    assert (chat.last_user_message_id, chat.last_user_at) == ("m2", naive(at(2, 10, 30)))
    assert (chat.last_answer_message_id, chat.last_answer_at) == ("a2", naive(at(2, 10, 40)))
    assert not state_of().needs_reply  # 마지막 손님 글(m2) 뒤에 공개 답(a2)


def test_older_chat_list_snapshot_does_not_change_newer_state(app):
    assert ss.apply_chat_snapshots(db_session, [snap("closed", at(2, 12))]) == 1
    assert ss.apply_chat_snapshots(db_session, [snap("opened", at(2, 11))]) == 0
    assert chat_row().chat_state == "closed"
    assert ss.apply_chat_snapshots(db_session, [snap("opened", at(2, 13))]) == 1
    assert chat_row().chat_state == "opened"


# ── '답'의 정의 · 확인코드 글 ───────────────────────────────────────────


def test_our_bot_memo_and_auto_notice_are_not_answers(app):
    """음성 대조군: 우리 AI 메모(비공개 봇) · 자동 안내(공개 봇) · 직원 내부 메모는 답이 아니다(R1-6)."""
    inbound(1, entity("m1", at(2, 10), text="식탁 견적 부탁드려요"))
    inbound(2, entity("m2", at(2, 10, 5), person="bot", text="AI 초안", options=["MESSAGE_OPTION_PRIVATE"]))
    inbound(3, entity("m3", at(2, 10, 6), person="bot", text="지금은 운영 시간이 아닙니다"))
    inbound(4, entity("m4", at(2, 10, 7), person="manager", text="샘플 확인 필요", private=True))
    ss.ingest_inbound(db_session)

    s = state_of()
    assert s.needs_reply and s.waiting_since == at(2, 10)
    assert chat_row().last_answer_message_id is None
    # 공개 상담원 글이 오면 그때 답이다.
    inbound(5, entity("m5", at(2, 10, 20), person="manager", text="네 고객님 사이즈 알려 주세요"))
    ss.ingest_inbound(db_session)
    assert not state_of().needs_reply and chat_row().last_answer_message_id == "m5"


def test_code_message_does_not_create_needs_reply(app):
    """확인코드('문서 받기') 글은 share_consult 가 링크로 답한다 — 답 필요 · 시작 신호가 아니다(R4-2)."""
    inbound(1, entity("m1", at(2, 10), text=CODE_TEXT))
    ss.ingest_inbound(db_session)
    assert msg_row("m1").is_code_message is True
    s = state_of()
    assert not s.needs_reply and not s.closing_only
    assert chat_row().last_user_message_id is None

    inbound(2, entity("m2", at(2, 10, 30), text="설치 날짜는 언제쯤인가요"))
    ss.ingest_inbound(db_session)
    s = state_of()
    assert s.needs_reply and s.waiting_since == at(2, 10, 30)


# ── Open API 읽기 · 공유 양동이 ─────────────────────────────────────────


def test_list_follows_cursor_until_last_page(keys):
    clock = FakeClock()
    page1 = {"userChats": [{"id": "c1", "channelId": LAHOM_CHANNEL, "state": "opened",
                            "updatedAt": int(at(2, 9).timestamp() * 1000)},
                           {"id": "c2", "state": "closed"}], "next": "cur-2"}
    page2 = {"userChats": [{"id": "c3", "state": "snoozed"},
                           {"id": "c4", "channelId": HAUD_CHANNEL, "state": "opened"}]}
    transport = FakeTransport(FakeResponse(200, page1), FakeResponse(200, page2))

    chats = list(make_reader(transport, clock).iter_user_chats("LAHOM", changed_from=at(1, 0), changed_to=at(3, 0)))
    assert [(c.chat_id, c.state) for c in chats] == [("c1", "opened"), ("c2", "closed"), ("c3", "snoozed")]
    assert chats[0].updated_at == at(2, 9) and chats[1].updated_at is None
    first, second = transport.calls
    assert first["url"] == "https://api.channel.io/open/user-chats"
    assert first["params"]["from"] == int(at(1, 0).timestamp() * 1000)
    assert first["params"]["to"] == int(at(3, 0).timestamp() * 1000)
    assert "cursor" not in first["params"] and second["params"]["cursor"] == "cur-2"
    assert first["headers"]["x-access-key"] == "key-lahom"
    assert first["headers"]["Channel-Version"] == "2026-06-01"


def test_empty_responses_read_as_nothing(keys):
    clock = FakeClock()
    transport = FakeTransport(FakeResponse(200, raw=b""), FakeResponse(200, {}),
                              FakeResponse(200, {"messages": None}), FakeResponse(200, {"messages": []}))
    r = make_reader(transport, clock)
    assert r.list_user_chats("LAHOM", changed_from=at(1, 0), changed_to=at(2, 0)) == cr.ChatPage([], None)
    assert r.list_user_chats("LAHOM", changed_from=at(1, 0), changed_to=at(2, 0)).chats == []
    assert r.read_messages("LAHOM", "uc-1") == []
    assert r.read_messages("LAHOM", "uc-1") == []
    # 객체가 아닌 JSON 은 꼴이 바뀐 것 — 조용히 빈 값으로 넘기지 않는다.
    with pytest.raises(cr.ChannelReadError):
        make_reader(FakeTransport(FakeResponse(200, [1, 2])), clock).read_messages("LAHOM", "uc-1")


def test_429_waits_retry_after_then_reads(keys):
    clock = FakeClock()
    transport = FakeTransport(FakeResponse(429, headers={"Retry-After": "2"}), FakeResponse(200, {"messages": []}))
    assert make_reader(transport, clock).read_messages("LAHOM", "uc-1") == []
    assert clock.sleeps == [2.0] and len(transport.calls) == 2


def test_long_retry_after_stops_and_blocks_the_channel_for_others(keys):
    clock = FakeClock()
    budget = rb.LocalChannelBudget(clock=clock)
    first = FakeTransport(FakeResponse(429, headers={"Retry-After": "120"}))
    with pytest.raises(cr.ChannelRateLimited) as info:
        make_reader(first, clock, budget).read_messages("LAHOM", "uc-1")
    assert info.value.retry_after == 120 and clock.sleeps == []

    second = FakeTransport(FakeResponse(200, {"messages": []}))
    with pytest.raises(cr.ChannelRateLimited):
        make_reader(second, clock, budget).read_messages("LAHOM", "uc-2")
    assert second.calls == []  # 쉼 표시를 보고 채널톡에 요청을 보내지 않았다
    other = FakeTransport(FakeResponse(200, {"messages": []}))
    assert make_reader(other, clock, budget).read_messages("HAUD", "uc-3") == []  # 다른 채널은 막히지 않는다


def test_redis_budget_is_shared_across_processes_per_channel():
    clock = FakeClock(start=1000.2)
    redis = FakeRedis(clock)
    one = rb.RedisChannelBudget(redis, {"message": 3}, clock=clock)
    two = rb.RedisChannelBudget(redis, {"message": 3}, clock=clock)

    assert [one.acquire("LAHOM", "message"), two.acquire("LAHOM", "message"), one.acquire("LAHOM", "message")] == [0.0] * 3
    assert two.acquire("LAHOM", "message") == pytest.approx(0.8)  # 두 프로세스가 같은 몫을 나눠 쓴다
    assert one.acquire("HAUD", "message") == 0.0  # 채널마다 따로
    clock.now = 1001.0
    assert two.acquire("LAHOM", "message") == 0.0  # 다음 1초 칸
    one.block("LAHOM", 2.5)
    assert two.acquire("LAHOM", "message") == pytest.approx(2.5)
    assert two.acquire("HAUD", "message") == 0.0


# ── 수신 누락 경보 · 한 상담 보정 ───────────────────────────────────────


def test_missing_inbound_alarm_returns_only_real_gaps(app):
    inbound(1, entity("m1", at(2, 10), text="첫 글"))
    ss.ingest_inbound(db_session)
    inbound(9, entity("m5", at(2, 10, 25), text="수신 기록엔 있는데 아직 안 넣은 글"))
    api = [
        derived("m1", at(2, 10), text="첫 글"),
        derived("m2", at(2, 10, 10), text="웹훅이 빠뜨린 글"),
        derived("m3", at(2, 11, 58), text="아직 오는 중일 수 있는 글"),
        derived("m4", at(2, 10, 20), person="bot", text="AI 초안", options=["MESSAGE_OPTION_PRIVATE"]),
        derived("m5", at(2, 10, 25), text="수신 기록엔 있는데 아직 안 넣은 글"),
        derived("m0", datetime.datetime(2026, 10, 20, 15, tzinfo=state.KST), text="웹훅 전 글"),
    ]
    assert ss.find_missing_inbound(db_session, "uc-1", api, now=at(2, 12)) == ["m2"]
    # 창을 넘겨 못 넣은 수신 줄(m5)은 그 상담의 수신 기록을 다시 읽어 메웠다.
    assert msg_row("m5").inbound_log_id == 9
    # 음성 대조군: 빠진 글이 없으면 빈 목록.
    assert ss.find_missing_inbound(db_session, "uc-1", api[:1], now=at(2, 12)) == []


def test_reconcile_fills_message_the_webhook_missed(app, keys):
    inbound(1, entity("m1", at(2, 10), text="첫 글"))
    inbound(2, entity("a1", at(2, 10, 5), person="manager", text="네 안녕하세요"))
    ss.ingest_inbound(db_session)
    assert not state_of().needs_reply

    body = {"messages": [api_message("m2", at(2, 10, 30), "user", "그럼 색상은 어떤 게 있나요"),
                         api_message("a1", at(2, 10, 5), "manager", "네 안녕하세요"),
                         api_message("m1", at(2, 10), "user", "첫 글")]}
    reader = make_reader(FakeTransport(FakeResponse(200, body)), FakeClock())
    result = ss.reconcile_chat(db_session, reader, "LAHOM", "uc-1", now=at(2, 12))
    assert result == ss.ReconcileResult(inserted=1, missing_inbound=["m2"])
    assert (msg_row("m2").source, msg_row("m2").inbound_log_id) == ("openapi", None)
    assert state_of(now=at(2, 12)).needs_reply  # 웹훅이 빠뜨린 손님 글로 답 필요가 맞게 나온다

    # 늦게 온 웹훅 줄은 같은 글에 수신 줄 id 만 적는다(줄은 그대로 하나).
    inbound(3, entity("m2", at(2, 10, 30), text="그럼 색상은 어떤 게 있나요"))
    late = ss.ingest_inbound(db_session)
    assert (late.inserted, late.duplicates) == (0, 1)
    assert msg_row("m2").inbound_log_id == 3 and message_count() == 3
