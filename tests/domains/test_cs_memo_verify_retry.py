"""CS 초안 메모 다시 읽기 — 못 찾음 · 읽기 실패는 기다렸다 다시 읽는다(운영 11-06 사고).

올린 직후 채널톡 글 목록에 메모가 한 번 안 보여 막는 장치가 초안 스위치를 '저장만'으로 내렸고, 사흘 동안 AI 초안이
채널톡에 안 올라갔다. 이제 :data:`memo.VERIFY_RETRY_WAITS` 만큼 기다려 다시 읽고, 공개로 보이면 기다리지 않는다.
기다림은 ``tests/domains/conftest.py`` 의 ``_no_cs_memo_verify_sleep`` 가 건너뛰고 부른 초만 남긴다.
"""

from __future__ import annotations

import pytest

from foms.services import channel_memo
from foms.services.cs_agent import channel_read as cr
from foms.services.cs_agent import memo
from tests.support.cs_agent_fakes import FakeReader, at, derived

TEST_CHAT = "uc-test-1"
DRAFT = "합성 초안입니다. 담당자가 곧 확인합니다."


@pytest.fixture(autouse=True)
def only_test_chat(monkeypatch):
    for key in ("FOMS_ENV", "RAILWAY_PROJECT_NAME", "RAILWAY_ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    monkeypatch.setattr(channel_memo, "send_private_memo",
                        lambda *_a, **_k: {"success": True, "message_id": "memo-1", "error": None})


def bot_memo(*, private=True):
    extra = {"options": ["private"]} if private else {}
    return derived("memo-1", at(2, 9, 1), person="bot", chat=TEST_CHAT, **extra)


def post(reader):
    return memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", reader=reader)


def test_a_memo_missing_at_first_read_is_found_on_the_next_read(_no_cs_memo_verify_sleep):
    reader = FakeReader(messages={TEST_CHAT: []})
    reader.on_read = lambda chat: reader.messages[chat].append(bot_memo()) if len(reader.calls) == 2 else None
    assert post(reader) == memo.MemoResult(True, verified=True, message_id="memo-1")
    assert len(reader.calls) == 2 and _no_cs_memo_verify_sleep == [memo.VERIFY_RETRY_WAITS[0]]


def test_a_failed_read_is_tried_again(_no_cs_memo_verify_sleep):
    flaky = FakeReader(messages={TEST_CHAT: [bot_memo()]},
                       errors={TEST_CHAT: [cr.ChannelReadError("http_500", status=500)]})
    assert post(flaky).verified is True


def test_it_gives_up_after_the_last_wait(_no_cs_memo_verify_sleep):
    never = FakeReader(messages={TEST_CHAT: []})
    assert post(never).reason == memo.REASON_NOT_FOUND
    assert len(never.calls) == 1 + len(memo.VERIFY_RETRY_WAITS)
    assert _no_cs_memo_verify_sleep == list(memo.VERIFY_RETRY_WAITS)


def test_a_public_memo_is_not_read_again(_no_cs_memo_verify_sleep):
    reader = FakeReader(messages={TEST_CHAT: [bot_memo(private=False)]})
    assert post(reader).reason == memo.REASON_NOT_PRIVATE
    assert len(reader.calls) == 1 and _no_cs_memo_verify_sleep == []
