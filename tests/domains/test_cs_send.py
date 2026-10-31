"""[보내기] · [수정하기](플랜 C10-3 · 설계서 17.2 · 17.2.1 · 원장 D68 · D69) — 완료 기준 ①~⑨ 와 권한 · CSRF · 표.

① 보내기 한 번 → 손님 쪽 한 글, 두 번 누름 · 두 사람 동시 → 한 글 ② 그사이 손님 새 글(Open API 기준) → 안 보내고 '새 글이 있어요'
③ 누른 직원이 차례 줄에 남음 ④ 사람이 고친 글의 계좌 · 다른 브랜드 · 가림 표시 → 막음, 맞춤 금액 → 경고만 ⑤ GET · 링크 미리 읽기만으로는
안 나가고 표도 그대로 ⑥ 10초 끊김 흉내 → 두 번 안 나감 · requestId 로 맞춤 ⑦ 보낸 글이 돌아와도 '직접 답'이 안 됨 ⑧ 프로세스
여럿이 토큰 하나를 같이 씀(Redis 가짜) ⑨ 하우드 · 허용 목록 밖 · 스위치 꺼짐 → 안 보냄. 더해 권한(로그인 안 함 · 다른 팀) · CSRF 없음 ·
만료 표 · 다른 차례 표 → 막음. 화면 · 다시 쓰기 · 메모 버튼 · 채널 보내기 함수 · 마이그레이션은 ``test_cs_send_parts.py``.

채널톡 · 두뇌 · Redis 는 가짜(네트워크 없음), 손으로 꾸민 합성 글만(전화 꼴 숫자 · 실제 가격 없음). 시각은 2026-11 KST(11-02 월).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import time
from types import SimpleNamespace

import pytest
from itsdangerous import URLSafeSerializer
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import channel_client, channel_token_cache
from foms.services.cs_agent import case_memory, loop, send, send_auth, send_flow, send_record, turns
from foms.services.cs_agent import settings as st
from foms.services.cs_agent import state_store as ss
from foms.services.cs_agent.drafting_read import memo_text
from foms.services.cs_agent.masking import mask
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from models import CsAgentChat, CsAgentMessage, CsAgentTurn, SecurityLog, SystemSetting, User
from tests.domains.test_cs_drafting import CUSTOMER, DRAFT, NOTE, channel, customer  # noqa: F401 — channel 은 fixture
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    HAUD_CHANNEL, FakeClock, TokenRedis, api_message, at, entity, inbound, keys, make_reader,
)

NOW = at(2, 9)
MARK = "남색고래보낼글표지"  # 보낼 글 표지 — 로그 · 요약 · 응답에 나오면 안 된다
API = "/api/cs-agent/turns"
ACCOUNT = "-".join(("3" * 3, "2" * 2, "4" * 7))  # 꾸민 계좌 꼴(실행 때 만든다 — 공개 저장소에 전화 꼴 숫자를 두지 않는다)


# ── 재료 ─────────────────────────────────────────────────────────────────
def user(role="STAFF", team="CS", name="cs"):
    row = User(username=f"send-{name}-{role.lower()}", password=generate_password_hash("pw"), role=role, team=team,
               name=f"합성 {name}", is_active=True)
    db_session.add(row)
    db_session.commit()
    return row


def switches(*, buttons=True, loop_on=True, mode="memo", realtime=True):
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY,
                                   setting_value={"loop": "on" if loop_on else "off", "draft": mode}))
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, "send_buttons_enabled": buttons, "realtime_enabled": realtime}))
    db_session.commit()


def posted(channel, chat="uc-1", *, draft=DRAFT, brand="LAHOM", memo_id=None):
    """메모를 올린 차례 — 상태 표 · 가짜 채널톡에 손님 글, 가짜 채널톡에 우리 비공개 메모(원문은 채널톡에만)."""
    customer(channel, chat, channel_id=HAUD_CHANNEL if brand == "HAUD" else "201824")
    row = turns.claim_turn(db_session, brand, chat, f"m-{chat}", now=at(2, 8, 51))
    turns.mark_posting(row, masked_draft=mask(draft), now=at(2, 8, 51))
    turns.mark_posted(row, memo_message_id=memo_id or f"memo-{chat}", now=at(2, 8, 52))
    db_session.commit()
    channel.messages[chat].append(api_message(memo_id or f"memo-{chat}", at(2, 8, 52), "bot", memo_text(draft, NOTE),
                                              options=["private"]))
    return row.id


def token(app, turn_id, uid, memo=None):
    row = db_session.get(CsAgentTurn, turn_id)
    return send_auth.issue_send_token(app.secret_key, turn_id=turn_id, user_id=uid,
                                      memo_id=memo if memo is not None else row.memo_message_id)


def fresh(turn_id):
    db_session.expire_all()
    return db_session.get(CsAgentTurn, turn_id)


class FakeSender:
    """보내기 감싸개 대역 — 부를 때 '보내는 중'이 **커밋**됐는지 보고, 받은 글은 가짜 채널톡 상담에 requestId 와 함께 붙인다."""

    def __init__(self, channel, *results, deliver=True, on_call=None):
        self.channel, self.results, self.deliver, self.on_call = channel, list(results), deliver, on_call
        self.calls = []

    def __call__(self, chat_id, text, *, brand, turn_id):
        db_session.rollback()
        state = db_session.scalar(select(CsAgentTurn.send_state).where(CsAgentTurn.id == turn_id))
        assert state == "sending", f"'보내는 중'을 커밋하기 전에 보냈다(지금 {state})"
        self.calls.append(SimpleNamespace(chat_id=chat_id, text=text, brand=brand, turn_id=turn_id))
        if self.on_call:
            self.on_call()
        result = self.results.pop(0) if self.results else send.SendResult(True, message_id=f"sent-{len(self.calls)}",
                                                                            created_at=at(2, 9, 1))
        if self.deliver:
            self.channel.messages[chat_id].append(api_message(result.message_id or f"sent-{len(self.calls)}",
                                                              at(2, 9, 1), "bot", text,
                                                              requestId=send.request_id_for(turn_id)))
        return result


def press(app, channel, turn_id, uid, sender, **kwargs):
    kwargs.setdefault("token", token(app, turn_id, uid))
    request = send_flow.SendRequest(turn_id=turn_id, user_id=uid, **kwargs)
    return send_flow.send_turn(db_session, request, secret_key=app.secret_key, now=NOW,
                               reader=make_reader(channel, FakeClock()), sender=sender)


@pytest.fixture
def ready(channel):
    switches()
    return channel


# ── ① 한 번 → 한 글 · 두 번 누름 · 두 사람 동시 → 한 글 · ③ 누른 직원 ──────
def test_one_press_sends_one_message_and_records_who_pressed(app, ready):
    staff = user()
    turn_id = posted(ready)
    sender = FakeSender(ready)
    result = press(app, ready, turn_id, staff.id, sender, shown_ms=7300)
    assert (result.code, result.status) == ("sent", 200)
    (call,) = sender.calls
    assert (call.chat_id, call.text, call.brand) == ("uc-1", DRAFT, "LAHOM")  # 정본 = 메모의 '손님께 보낼 답'
    row = fresh(turn_id)
    assert (row.send_state, row.sent_message_id, row.outcome, row.sent_by_user_id, row.click_ms) == (
        "sent", "sent-1", "as_is", staff.id, 7300)
    assert row.edit_ratio == 0 and row.state == "posted" and row.staff_reply_masked == mask(DRAFT)
    assert row.masked_question and CUSTOMER in row.masked_question and row.waiting_since is not None
    again = press(app, ready, turn_id, staff.id, sender)
    assert again.code == "already" and len(sender.calls) == 1  # 두 번 누름 — 손님 쪽은 한 글
    audit = db_session.query(SecurityLog).filter_by(action="CS_AGENT_SEND").order_by(SecurityLog.id).all()
    assert [(a.user_id, a.target_id, a.detail["code"]) for a in audit] == [(staff.id, turn_id, "sent"),
                                                                          (staff.id, turn_id, "already")]


def test_two_people_pressing_together_send_once(app, ready):
    first, second = user(name="a"), user(name="b")
    turn_id = posted(ready)
    seen = {}
    sender = FakeSender(ready, on_call=lambda: seen.setdefault(
        "second", press(app, ready, turn_id, second.id, FakeSender(ready))))
    assert press(app, ready, turn_id, first.id, sender).code == "sent"
    assert seen["second"].code == "checking" and len(sender.calls) == 1  # 앞 사람이 '보내는 중' — 뒤 사람은 안 보냄
    assert fresh(turn_id).sent_by_user_id == first.id


# ── ② 그사이 손님 새 글 · 직원 답 → 안 보냄 ──────────────────────────────
@pytest.mark.parametrize("person,reason", [("user", "stale"), ("manager", "human_replied")])
def test_a_new_message_on_channel_talk_blocks_the_send(app, ready, person, reason):
    staff = user()
    turn_id = posted(ready)
    ready.messages["uc-1"].append(api_message("m-new", at(2, 8, 58), person, "합성 새 글"))  # 채널톡에만(상태 표는 늦다)
    sender = FakeSender(ready)
    result = press(app, ready, turn_id, staff.id, sender)
    assert (result.code, result.data.get("reason"), sender.calls) == ("new_message", reason, [])
    row = fresh(turn_id)
    assert (row.send_state, row.sent_by_user_id, row.send_error, row.outcome) == (None, None, reason, None)


# ── ④ 사람이 고친 글: 확실한 위험은 막고 나머지는 '확인 후 보내기' ─────────────
@pytest.mark.parametrize("text,code", [
    ("안녕하세요 고객님, 하우드 제품으로 안내드립니다.", "other_brand"),
    (f"안녕하세요 고객님, 계좌 {ACCOUNT} 로 보내 주세요.", "account_number"),
    ("[이름] 고객님, 합성 선반 깊이는 350mm 입니다.", "mask_marker"),
    (f"안녕하세요 고객님 {NOTE}", "private_memo_leak"),  # 내부 메모(직원 참고) 글이 새는 꼴
    ("저는 AI 상담사입니다. 합성 선반 깊이는 350mm 입니다.", "ai_mention"),
    ("저는 진짜 상담사예요. 직원이 직접 답하고 있어요.", "human_claim"),
])
def test_hard_risks_in_an_edited_text_are_blocked(app, ready, text, code):
    staff = user()
    turn_id = posted(ready)
    sender = FakeSender(ready)
    result = press(app, ready, turn_id, staff.id, sender, mode="edited", text=text, edit_reason="tone", confirm=True)
    assert result.code == "blocked" and code in [p["code"] for p in result.data["problems"]] and not sender.calls
    assert fresh(turn_id).send_state is None


def test_a_custom_amount_is_a_warning_and_a_second_press_sends(app, ready):
    staff = user()
    turn_id = posted(ready)
    sender = FakeSender(ready)
    text = "안녕하세요 고객님, 맞춤 선반은 123,000원으로 진행 가능합니다."
    first = press(app, ready, turn_id, staff.id, sender, mode="edited", text=text, edit_reason="missing")
    assert first.code == "needs_confirm" and "number_not_allowed" in [w["code"] for w in first.data["warnings"]]
    assert not sender.calls and fresh(turn_id).send_state is None
    second = press(app, ready, turn_id, staff.id, sender, mode="edited", text=text, edit_reason="missing",
                   confirm=True)
    assert second.code == "sent" and [c.text for c in sender.calls] == [text]
    row = fresh(turn_id)
    assert (row.outcome, row.edit_reason) == ("edited", "missing") and 0 < row.edit_ratio <= 1
    assert row.staff_reply_masked == mask(text)  # 고친 글은 가린 사본만 — 다음 초안 재료(사례)가 된다


def test_the_ai_draft_as_is_gets_the_full_check(app, ready):
    staff = user()
    turn_id = posted(ready, draft="안녕하세요 고객님, 맞춤 선반은 123,000원입니다.")  # 승인 지식에 없는 금액
    sender = FakeSender(ready)
    result = press(app, ready, turn_id, staff.id, sender, confirm=True)
    assert result.code == "blocked" and not sender.calls  # 그대로 보내기엔 '확인 후' 가 없다


# ── ⑤ GET · 링크 미리 읽기는 안 보내고 표도 그대로 ────────────────────────
def test_opening_the_link_never_sends_and_the_page_token_still_works(app, client, ready):
    staff = user()
    turn_id = posted(ready)
    sender = FakeSender(ready)
    anonymous = client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-1")  # 메신저 미리 읽기 — 쿠키 없음
    assert anonymous.status_code == 302 and "/login" in anonymous.headers["Location"]
    with client.session_transaction() as sess:
        sess["user_id"] = staff.id
    reader = make_reader(ready, FakeClock())
    from foms.services.cs_agent import send_view
    original = send_view.OpenApiReader
    send_view.OpenApiReader = lambda *a, **k: reader
    try:
        page = client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-1")
        twice = client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-1")
    finally:
        send_view.OpenApiReader = original
    html = page.get_data(as_text=True)
    assert page.status_code == twice.status_code == 200 and DRAFT in html and page.headers["Cache-Control"] == (
        "private, no-store")
    row = fresh(turn_id)
    assert (row.send_state, row.sent_by_user_id, row.click_ms, row.updated_at) == (None, None, None,
                                                                                   at(2, 8, 52).astimezone(
                                                                                       datetime.timezone.utc)
                                                                                   .replace(tzinfo=None))
    page_token = html.split('data-token="', 1)[1].split('"', 1)[0]
    assert press(app, ready, turn_id, staff.id, sender, token=page_token).code == "sent"  # 열기가 표를 쓰지 않았다
    assert len(sender.calls) == 1


# ── ⑥ 10초 끊김 → 두 번 안 나감 · requestId 로 맞춤 ─────────────────────────
def test_a_timeout_is_never_resent_and_is_matched_by_request_id(app, ready):
    staff = user()
    turn_id = posted(ready)
    sender = FakeSender(ready, send.SendResult(False, reason=send.SEND_UNKNOWN))  # 채널톡엔 닿았다(가짜가 붙인다)
    first = press(app, ready, turn_id, staff.id, sender, mode="edited", text="합성 고친 답입니다.", edit_reason="tone")
    assert (first.code, first.status) == ("checking", 202) and fresh(turn_id).send_state == "unknown"
    assert press(app, ready, turn_id, staff.id, sender).code == "checking" and len(sender.calls) == 1
    matched = send_flow.reconcile_one(db_session, turn_id=turn_id, user_id=staff.id, token=token(app, turn_id, staff.id),
                                      secret_key=app.secret_key, now=at(2, 9, 2),
                                      reader=make_reader(ready, FakeClock()))
    row = fresh(turn_id)
    assert matched.code == "sent" and (row.send_state, row.sent_message_id, row.outcome) == ("sent", "sent-1", "edited")
    assert len(sender.calls) == 1


def test_an_unknown_send_that_never_arrived_becomes_retryable_only_after_the_wait(app, ready):
    staff = user()
    turn_id = posted(ready)
    lost = FakeSender(ready, send.SendResult(False, reason=send.SEND_UNKNOWN), deliver=False)
    assert press(app, ready, turn_id, staff.id, lost).code == "checking"
    reader = make_reader(ready, FakeClock())
    assert send_record.reconcile_sends(db_session, now=at(2, 9, 3), reader=reader) == {"waiting": 1}  # 아직 기다림
    assert fresh(turn_id).send_state == "unknown"
    assert send_record.reconcile_sends(db_session, now=at(2, 9, 6), reader=reader) == {"failed": 1}  # 5분 넘게 없음
    row = fresh(turn_id)
    assert (row.send_state, row.send_error, row.outcome, row.sent_by_user_id) == ("failed", "not_delivered", None, None)
    again = FakeSender(ready)
    assert press(app, ready, turn_id, staff.id, again).code == "sent" and len(again.calls) == 1


# ── ⑦ 보낸 글이 돌아와도 '직접 답'이 아니다(되먹임 막기) ──────────────────────
def test_our_sent_reply_coming_back_is_an_answer_but_never_a_direct_reply(app, ready):
    staff = user()
    turn_id = posted(ready)
    assert press(app, ready, turn_id, staff.id, FakeSender(ready)).code == "sent"
    chat = db_session.get(CsAgentChat, db_session.scalar(select(CsAgentChat.id).where(CsAgentChat.chat_id == "uc-1")))
    assert chat.last_answer_message_id == "sent-1"  # 상태 표에 '답' — 상담이 '답 필요'에서 빠진다
    inbound(1, entity("sent-1", at(2, 9, 1), "bot", "합성 보낸 글", chat="uc-1",
                      requestId=send.request_id_for(turn_id)))  # 웹훅으로 돌아온 우리 봇 공개 글
    ss.ingest_inbound(db_session, lookback=10, now=send_record.naive_utc(NOW))
    db_session.commit()
    rows = db_session.execute(select(CsAgentMessage.message_id, CsAgentMessage.person_type)
                              .where(CsAgentMessage.chat_id == "uc-1")).all()
    assert ("sent-1", "manager") in rows and len([r for r in rows if r[0] == "sent-1"]) == 1
    summary = case_memory.attach_staff_replies(db_session, now=at(2, 9, 10), stop=loop.StopFlag(),
                                               reader=make_reader(ready, FakeClock()))
    assert (summary.direct, summary.edited, summary.copied) == (0, 0, 0)
    row = fresh(turn_id)
    assert (row.outcome, row.sent_message_id) == ("as_is", "sent-1")  # 보낸 차례의 사례는 그대로
    _rows, sent = case_memory._chat_rows(db_session, [case_memory._Pending(turn_id, "uc-1", "LAHOM", "m-uc-1",
                                                                          at(2, 8, 50).replace(tzinfo=None))])
    assert sent["uc-1"] == {"sent-1"}  # C10-4 거름이 이 길로 채워졌다


def test_a_returned_bot_reply_is_read_as_staff_in_the_next_draft_material(ready):
    from foms.services.cs_agent.channel_read import derive_message
    ours = entity("sent-9", at(2, 9, 1), "bot", "합성", requestId=send.request_id_for(7))
    other_bot = entity("auto-1", at(2, 9, 1), "bot", "합성 자동 안내", requestId="other-app-1")
    memo = entity("memo-9", at(2, 9, 1), "bot", "합성", requestId=send.request_id_for(7), options=["private"])
    assert derive_message(ours)[0].is_answer is True  # 우리 [보내기] 글은 직원 답
    assert derive_message(other_bot)[0].is_answer is False and derive_message(memo)[0].is_answer is False  # 대조군


# ── ⑧ 프로세스 여럿이 토큰 하나(Redis 공유 캐시 + 잠금) ─────────────────────
@pytest.fixture
def token_env(monkeypatch):
    clock = FakeClock(start=1_000.0)
    redis = TokenRedis(clock)
    issued = []

    def issue(*_channel):
        issued.append(1)
        return f"token-{len(issued)}", clock() + 1500  # expiresIn 1560 − 60초 여유(발급 응답이 정한 만료)

    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "secret")
    monkeypatch.setattr(channel_client, "CHANNEL_ID", "201824")
    monkeypatch.setattr(channel_client, "_issue_token", issue)
    monkeypatch.setattr(channel_client.time, "time", clock)
    monkeypatch.setattr(channel_token_cache, "_client", lambda: redis)
    return SimpleNamespace(clock=clock, redis=redis, issued=issued, monkeypatch=monkeypatch)


def test_processes_share_one_token_through_redis(token_env):
    tokens = []
    for _process in range(3):  # 프로세스마다 자기 캐시가 비어 있다
        token_env.monkeypatch.setattr(channel_client, "_token_cache", {})
        tokens.append(channel_client._get_access_token())
    assert tokens == ["token-1"] * 3 and len(token_env.issued) == 1


def test_shared_token_keeps_the_issued_expiry(token_env):
    """R1 — 공유 값의 수명은 발급 응답(expiresIn)이 정한 만료 그대로다."""
    token_env.monkeypatch.setattr(channel_client, "_token_cache", {})
    channel_client._get_access_token()
    key = channel_token_cache.KEY_PREFIX + "201824"
    assert json.loads(token_env.redis.values[key])["expires_at"] == 1_000.0 + 1500
    assert token_env.redis.expires[key] == pytest.approx(1_000.0 + 1500)
    token_env.clock.now += 1500 - 1  # 남은 수명이 짧으면(5초 안) 쓰지 않고 새로 받는다
    token_env.monkeypatch.setattr(channel_client, "_token_cache", {})
    assert channel_client._get_access_token() == "token-2"


def test_a_dead_shared_token_is_dropped_and_reissued_once(token_env):
    """R2 — 401 이면 공유 값이 그 토큰일 때만 지우고 다시 받는다(다른 프로세스가 넣은 새 토큰은 그대로)."""
    token_env.monkeypatch.setattr(channel_client, "_token_cache", {})
    dead = channel_client._get_access_token()
    channel_client._invalidate_token(dead)
    token_env.monkeypatch.setattr(channel_client, "_token_cache", {})
    fresh_token = channel_client._get_access_token()
    assert (dead, fresh_token, len(token_env.issued)) == ("token-1", "token-2", 2)
    channel_client._invalidate_token(dead)  # 늦게 온 옛 401 — 새 공유 값은 지우지 않는다
    token_env.monkeypatch.setattr(channel_client, "_token_cache", {})
    assert channel_client._get_access_token() == "token-2" and len(token_env.issued) == 2


def test_a_waiting_process_uses_the_token_the_lock_holder_stored(token_env):
    lock = channel_token_cache.KEY_PREFIX + "201824:lock"
    token_env.redis.set(lock, "other-process", nx=True, px=15_000)  # 다른 프로세스가 발급 중

    def sleep(seconds):
        token_env.clock.now += seconds
        token_env.redis.set(channel_token_cache.KEY_PREFIX + "201824",
                            json.dumps({"token": "token-of-other", "expires_at": token_env.clock() + 900}), px=900_000)

    got = channel_token_cache.shared_token("201824", lambda: pytest.fail("잠금을 못 잡은 쪽이 발급했다"),
                                           client=token_env.redis, now=token_env.clock, sleep=sleep)
    assert got[0] == "token-of-other" and token_env.issued == []


def test_without_redis_or_when_it_fails_each_process_issues_as_before(token_env, monkeypatch):
    token_env.redis.fail = True
    monkeypatch.setattr(channel_client, "_token_cache", {})
    assert channel_client._get_access_token() == "token-1"  # Redis 실패 — 예전처럼 이 프로세스가 발급
    monkeypatch.setattr(channel_token_cache, "_client", lambda: None)
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setattr(channel_client, "_token_cache", {})
    assert channel_client._get_access_token() == "token-2" and len(token_env.issued) == 2


# ── ⑨ 하우드 · 허용 목록 밖 · 스위치 꺼짐 → 안 보냄 ──────────────────────────
@pytest.mark.parametrize("case,code", [("haud", "not_allowed"), ("outside", "not_allowed"), ("buttons_off", "switch_off"),
                                       ("emergency", "switch_off")])
def test_haud_outside_the_allow_list_and_switches_off_never_send(app, channel, monkeypatch, case, code):
    switches(buttons=case != "buttons_off", loop_on=case != "emergency")
    staff = user()
    if case == "outside":
        monkeypatch.setenv("FOMS_CS_MEMO_TEST_CHAT_IDS", "uc-2")
    turn_id = posted(channel, brand="HAUD" if case == "haud" else "LAHOM")
    sender = FakeSender(channel)
    result = press(app, channel, turn_id, staff.id, sender)
    assert result.code == code and not sender.calls and fresh(turn_id).send_state is None


def test_the_wrapper_itself_refuses_haud_and_chats_outside_the_list(monkeypatch):
    calls = []
    monkeypatch.setattr(send.channel_send, "send_public_bot_message", lambda *a, **k: calls.append(1))
    monkeypatch.setenv("FOMS_CS_MEMO_TEST_CHAT_IDS", "uc-1")
    for env in ("FOMS_ENV", "RAILWAY_PROJECT_NAME"):
        monkeypatch.delenv(env, raising=False)
    assert send.send_reply("uc-1", "합성", brand="HAUD", turn_id=1).reason == send.REASON_BRAND
    assert send.send_reply("uc-9", "합성", brand="LAHOM", turn_id=1).reason == send.REASON_STAGING
    assert send.send_reply("x/../y", "합성", brand="LAHOM", turn_id=1).reason == send.REASON_NO_CHAT
    assert calls == []


# ── 권한 · CSRF · 표 ─────────────────────────────────────────────────────
def test_only_cs_staff_and_admins_may_post(client, ready):
    turn_id = posted(ready)
    assert client.post(f"{API}/{turn_id}/send", json={}).status_code == 401  # 로그인 안 함
    for role, team in (("STAFF", "SALES"), ("VIEWER", "CS"), ("MANAGER", "DRAWING")):
        other = user(role=role, team=team, name=f"{role}{team}")
        with client.session_transaction() as sess:
            sess["user_id"] = other.id
        denied = client.post(f"{API}/{turn_id}/send", json={"token": "x"})
        assert denied.status_code == 403 and denied.get_json()["success"] is False, (role, team)
    for role, team in (("STAFF", "CS"), ("MANAGER", "CS"), ("STAFF", "ACCOUNTING"), ("ADMIN", None)):
        assert send_auth.can_use_send_screen(SimpleNamespace(role=role, team=team, is_active=True,
                                                             partner_org_id=None)), (role, team)
    assert fresh(turn_id).send_state is None


def test_writes_need_csrf_and_the_policy_gate(app, client, ready):
    staff = user()
    turn_id = posted(ready)
    with client.session_transaction() as sess:
        sess["user_id"] = staff.id
    app.config["WRITE_GUARD_ENABLED"] = True
    try:
        blocked = client.post(f"{API}/{turn_id}/discard", json={"token": token(app, turn_id, staff.id)})
        assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked"
        seed = os.urandom(16).hex()
        with client.session_transaction() as sess:
            sess[_CSRF_SESSION_KEY] = seed
        csrf = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
        passed = client.post(f"{API}/{turn_id}/discard", json={"token": token(app, turn_id, staff.id)},
                             headers={"X-CSRF-Token": csrf})
        assert passed.status_code == 200 and fresh(turn_id).outcome == "discarded"
    finally:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    app.config["AUTH_POLICY_ENABLED"] = True
    try:
        sales = user(role="MANAGER", team="SALES", name="mgr")
        with client.session_transaction() as sess:
            sess["user_id"] = sales.id
        denied = client.post(f"{API}/{turn_id}/send", json={})
        assert denied.status_code == 403 and denied.headers.get("X-Auth-Policy") == "denied"
    finally:
        app.config.pop("AUTH_POLICY_ENABLED", None)


def test_expired_foreign_and_stale_tokens_are_refused(app, ready, monkeypatch):
    staff, other = user(), user(name="b")
    turn_id = posted(ready)
    second = posted(ready, chat="uc-2")
    with monkeypatch.context() as patched:
        real = time.time()
        patched.setattr(time, "time", lambda: real - send_auth.TOKEN_MAX_AGE - 5)
        expired = token(app, turn_id, staff.id)
    sender = FakeSender(ready)
    for tok, reason in ((expired, "token_expired"), (token(app, second, staff.id), "token_other_turn"),
                        (token(app, turn_id, other.id), "token_other_user"),
                        (token(app, turn_id, staff.id, memo="memo-old"), "token_stale"), ("x.y.z", "token_bad")):
        result = press(app, ready, turn_id, staff.id, sender, token=tok)
        assert (result.code, result.data["reason"]) == ("token", reason)
    assert not sender.calls and fresh(turn_id).send_state is None


def test_the_send_text_never_reaches_logs_or_results(app, ready, caplog):
    caplog.set_level(logging.DEBUG)
    staff = user()
    turn_id = posted(ready)
    results = [press(app, ready, turn_id, staff.id, FakeSender(ready), mode="edited", text=f"{MARK} 123,000원",
                     edit_reason="tone"),
               press(app, ready, turn_id, staff.id, FakeSender(ready), mode="edited", text=f"하우드 {MARK}",
                     edit_reason="tone")]
    assert [r.code for r in results] == ["needs_confirm", "blocked"]
    assert MARK not in caplog.text and all(MARK not in json.dumps(r.data, ensure_ascii=False) for r in results)
    assert all(MARK not in f"{a.message}{a.detail}" for a in db_session.query(SecurityLog).all())  # 감사 원장에도 글 없음
    assert MARK not in repr(send_flow.SendRequest(turn_id=1, user_id=1, token="t", text=MARK))
