"""[보내기] 교차 검수 R15 반영(플랜 C10-3) — 검수가 실패하는 시험으로 보인 것을 고친 뒤 막는 시험 · 살아남은 변이를 잡는 시험.

R15-1 '확인 후 보내기'는 경고를 본 그 글에 묶인 확인표로만 · R15-2 보낸 답의 약속 칸 · R15-3 AI 초안에 있던 문제는 고친 글에서도 막음 ·
R15-4 결과를 못 적었거나 채널톡을 부르기 직전 '보내는 중'이 아니면 '보냈어요'라 하지 않음 · R15-5 '고칠 말' 처리 중엔 보내기 막음 ·
오래 남은 처리 중은 만료 · R15-6 토큰 공유 열쇠 · 프로세스 잠금 · 같은 토큰만 지움. 변이: '보내는 중' 조건부 쓰기 · 보내기 직전 스위치 ·
안 고친 글은 그대로 · 부르기 전 예외 되돌림 · 조회 전용 막기 · 버리기 조건 · 보냄 적기 조건 · 메모 비공개 · 잠금 뒤 다시 읽기.

채널톡 · 두뇌 · Redis 는 가짜, 손으로 꾸민 합성 글만. 시각은 2026-11 KST(11-02 월).
"""

from __future__ import annotations

import datetime
import hashlib
import json

import pytest
from sqlalchemy import select, update

from db import db_session
from foms.services import channel_client, channel_token_cache
from foms.services.cs_agent import loop, rewrite, send, send_auth, send_flow, send_record
from foms.services.cs_agent import state_store as ss
from foms.services.cs_agent.channel_read import derive_message
from models import CsAgentMessage, CsAgentTurn
from tests.domains.test_cs_drafting import FakeBrain, channel, result  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_send import (  # noqa: F401 — ready · token_env 는 fixture
    API, NOW, FakeSender, fresh, posted, press, ready, switches, token, token_env, user,
)
from tests.support.cs_agent_fakes import FakeClock, TokenRedis, api_message, at, entity, inbound, keys, make_reader  # noqa

AMOUNT = "안녕하세요 고객님, 맞춤 선반은 123,000원으로 진행 가능합니다."
LINK_DATE = "안녕하세요 고객님, 결제는 http://evil.example/pay 에서 해 주세요. 내일 꼭 설치해 드립니다."
PROMISE = "안녕하세요 고객님, 확인 후 안내드리겠습니다."


def edited(app, channel, turn_id, uid, sender, text, **kwargs):
    return press(app, channel, turn_id, uid, sender, mode="edited", text=text, edit_reason="missing", **kwargs)


def set_row(turn_id, **values):
    db_session.execute(update(CsAgentTurn).where(CsAgentTurn.id == turn_id).values(**values))
    db_session.commit()


# ── R15-1 확인표 ─────────────────────────────────────────────────────────
def test_a_bare_confirm_flag_never_skips_the_warning(app, ready):
    staff = user()
    turn_id = posted(ready)
    sender = FakeSender(ready)
    for confirm in (True, "x" * 32, ""):
        result_ = edited(app, ready, turn_id, staff.id, sender, AMOUNT + " http://evil.example/pay", confirm=confirm)
        assert result_.code == "needs_confirm" and result_.data["confirm"], confirm
    assert sender.calls == [] and fresh(turn_id).send_state is None


def test_the_confirm_stamp_belongs_to_the_text_it_warned_about(app, ready):
    staff, other = user(), user(name="b")
    turn_id = posted(ready)
    sender = FakeSender(ready)
    first = edited(app, ready, turn_id, staff.id, sender, AMOUNT)
    stamp = first.data["confirm"]
    swapped = edited(app, ready, turn_id, staff.id, sender, LINK_DATE, confirm=stamp)  # 다른 글에 앞 확인표
    assert swapped.code == "needs_confirm" and "link_not_allowed" in [w["code"] for w in swapped.data["warnings"]]
    assert edited(app, ready, turn_id, other.id, sender, AMOUNT, confirm=stamp).code == "needs_confirm"  # 다른 직원
    sent = edited(app, ready, turn_id, staff.id, sender, "  " + AMOUNT.replace(" ", "  ") + " ", confirm=stamp)
    assert sent.code == "sent" and len(sender.calls) == 1  # 빈칸만 다른 같은 글은 같은 확인표


def test_the_screen_resets_the_confirmation_when_the_text_changes():
    from pathlib import Path
    script = (Path(__file__).resolve().parents[2] / "static/js/cs-agent/send-screen.js").read_text(encoding="utf-8")
    assert "confirmStamp = null" in script and "addEventListener('input'" in script and "confirm: confirmStamp" in script


# ── R15-2 보낸 답의 약속 ─────────────────────────────────────────────────
def test_a_promise_in_a_sent_reply_is_watched_like_a_desk_reply(app, ready):
    staff = user()
    turn_id = posted(ready, draft=PROMISE)
    assert press(app, ready, turn_id, staff.id, FakeSender(ready)).code == "sent"
    expected = derive_message(entity("sent-1", at(2, 9, 1), "bot", PROMISE, requestId=send.request_id_for(turn_id)))[0]
    assert expected.promise_kind is not None
    inbound(1, entity("sent-1", at(2, 9, 1), "bot", PROMISE, chat="uc-1", requestId=send.request_id_for(turn_id)))
    ss.ingest_inbound(db_session, lookback=10, now=send_record.naive_utc(NOW))
    db_session.commit()
    row = db_session.execute(select(CsAgentMessage.person_type, CsAgentMessage.promise_kind,
                                    CsAgentMessage.promise_rule).where(CsAgentMessage.message_id == "sent-1")).one()
    assert tuple(row) == ("manager", expected.promise_kind, expected.promise_rule)


def test_a_bot_row_ingested_first_gets_the_promise_filled(app, ready):
    message = derive_message(entity("sent-7", at(2, 9, 1), "bot", PROMISE))[0]  # requestId 없는 웹훅 — 봇 글
    ss.store_messages(db_session, [message], source="webhook", now=send_record.naive_utc(NOW))
    send_record.record_answer(db_session, brand="LAHOM", chat_id="uc-1", message_id="sent-7", sent_at=at(2, 9, 1),
                              text=PROMISE, turn_id=7, now=NOW)
    db_session.commit()
    row = db_session.execute(select(CsAgentMessage.person_type, CsAgentMessage.promise_kind)
                             .where(CsAgentMessage.message_id == "sent-7")).one()
    assert row.person_type == "manager" and row.promise_kind is not None


# ── R15-3 AI 초안에 있던 문제는 고쳐도 막음 ───────────────────────────────
def test_problems_already_in_the_ai_draft_stay_blocked_after_a_tiny_edit(app, ready):
    staff = user()
    draft = "안녕하세요 고객님, 맞춤 선반은 123,000원입니다."
    turn_id = posted(ready, draft=draft)
    sender = FakeSender(ready)
    for text in (draft, draft + " ", draft + "."):
        outcome = edited(app, ready, turn_id, staff.id, sender, text)
        assert outcome.code == "blocked" and "number_not_allowed" in [p["code"] for p in outcome.data["problems"]]
    assert sender.calls == []


# ── R15-4 결과를 못 적으면 '확인 중' · 부르기 직전 다시 보기 ──────────────────
def test_a_row_moved_on_during_the_call_is_never_reported_sent(app, ready):
    staff = user()
    turn_id = posted(ready)

    def late():  # 보내는 동안 다른 쪽(5분 넘은 맞추기)이 '못 보냄'으로 바꿨다
        set_row(turn_id, send_state="failed", send_error="not_delivered")

    result_ = press(app, ready, turn_id, staff.id, FakeSender(ready, on_call=late))
    assert result_.code == "checking" and fresh(turn_id).send_state == "failed"


def test_the_sending_mark_is_checked_again_right_before_channel_talk(app, ready):
    staff = user()
    turn_id = posted(ready)
    original = ready.__call__.__func__

    class Moving(type(ready)):
        def __call__(self, url, **kwargs):
            if url.endswith("/messages"):
                set_row(turn_id, send_state="failed")  # 읽는 사이 '보내는 중'이 아니게 됐다
            return original(self, url, **kwargs)

    ready.__class__ = Moving
    sender = FakeSender(ready)
    result_ = press(app, ready, turn_id, staff.id, sender)
    assert result_.code == "checking" and sender.calls == []


# ── R15-5 고칠 말 처리 중 · 만료 ─────────────────────────────────────────
def test_sending_is_refused_while_the_ai_rewrites(app, ready):
    staff = user()
    turn_id = posted(ready)
    set_row(turn_id, rewrite_state="working", rewrite_count=1)
    sender = FakeSender(ready)
    assert press(app, ready, turn_id, staff.id, sender).code == "rewriting" and sender.calls == []
    row = db_session.get(CsAgentTurn, turn_id)
    assert send_record.start_sending(db_session, row, user_id=staff.id, click_ms=None, now=NOW) is False  # SQL 가드도


def test_a_stuck_rewrite_expires_and_can_be_asked_again(app, ready):
    staff = user()
    turn_id = posted(ready)
    set_row(turn_id, rewrite_state="working", rewrite_count=1,
            updated_at=send_record.naive_utc(NOW) - rewrite.WORKING_EXPIRES - datetime.timedelta(seconds=1))
    counts = rewrite.run_rewrites(db_session, now=NOW, stop=loop.StopFlag(), reader=make_reader(ready, FakeClock()),
                                  brain=FakeBrain(), poster=lambda *a, **k: pytest.fail("메모를 올렸다"))
    row = fresh(turn_id)
    assert counts.get("expired") == 1 and (row.rewrite_state, row.send_error) == ("failed", "rewrite_expired")
    asked = send_flow.request_rewrite(db_session, turn_id=turn_id, user_id=staff.id, token=token(app, turn_id, staff.id),
                                      note="합성 고칠 말", secret_key=app.secret_key, now=NOW)
    assert asked.code == "rewrite_requested"


# ── R15-6 토큰 공유 열쇠 · 잠금 · 같은 토큰만 지움 ─────────────────────────
def test_the_shared_key_carries_the_environment_and_an_app_fingerprint(token_env, monkeypatch):
    monkeypatch.setattr(channel_client, "_token_cache", {})
    channel_client._get_access_token()
    (key,) = [k for k in token_env.redis.values if not k.endswith(":lock")]
    fingerprint = hashlib.sha256(b"secret").hexdigest()[:12]
    assert key.endswith(":201824") and fingerprint in key and "secret" not in key.replace(fingerprint, "")
    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "other-app-secret")  # 다른 앱(비밀)이면 다른 열쇠
    monkeypatch.setattr(channel_client, "_token_cache", {})
    assert channel_client._get_access_token() == "token-2" and len(token_env.issued) == 2


def test_the_process_lock_is_free_while_waiting_on_redis(token_env, monkeypatch):
    monkeypatch.setattr(channel_client, "_token_cache", {})
    seen = []
    key = channel_token_cache.shared_key("201824", "secret")
    token_env.redis.set(f"{key}:lock", "other-process", nx=True, px=15_000)

    def sleep(seconds):
        seen.append(channel_client._token_lock.locked())
        token_env.clock.now += seconds
        token_env.redis.set(key, json.dumps({"token": "token-of-other", "expires_at": token_env.clock() + 900}),
                            px=900_000)

    monkeypatch.setattr(channel_token_cache.time, "sleep", sleep)
    assert channel_client._get_access_token() == "token-of-other" and seen == [False]


def test_dropping_a_dead_token_compares_and_deletes_in_one_step(token_env):
    key = channel_token_cache.shared_key("201824", "secret")
    token_env.redis.set(key, json.dumps({"token": "dead", "expires_at": 9e9}), px=900_000)

    class Racing(TokenRedis):
        def eval(self, script, numkeys, *args):  # 지우기 직전 다른 프로세스가 새 토큰을 넣었다
            token_env.redis.values[key] = json.dumps({"token": "fresh", "expires_at": 9e9}).encode()
            return token_env.redis.eval(script, numkeys, *args)

    racing = Racing(token_env.clock)
    racing.values, racing.expires = token_env.redis.values, token_env.redis.expires
    channel_token_cache.drop_shared_token("201824", "dead", secret="secret", client=racing)
    assert json.loads(token_env.redis.values[key])["token"] == "fresh"  # 새 토큰은 남는다
    channel_token_cache.drop_shared_token("201824", "fresh", secret="secret", client=token_env.redis)
    assert key not in token_env.redis.values  # 대조군: 같은 토큰이면 지운다


def test_a_token_stored_while_taking_the_lock_is_reused(token_env):
    key = channel_token_cache.shared_key("201824", "secret")

    class Late(TokenRedis):
        def set(self, name, value, nx=False, px=None):
            done = super().set(name, value, nx=nx, px=px)
            if nx and name.endswith(":lock"):  # 잠금을 잡는 사이 다른 프로세스가 넣었다
                super().set(key, json.dumps({"token": "token-of-other", "expires_at": self.clock() + 900}), px=900_000)
            return done

    got = channel_token_cache.shared_token("201824", lambda: pytest.fail("다시 읽지 않고 발급했다"), secret="secret",
                                           client=Late(token_env.clock), now=token_env.clock)
    assert got[0] == "token-of-other"


# ── 살아남은 변이를 잡는 시험 ────────────────────────────────────────────
@pytest.mark.parametrize("values", [{"send_state": "sending"}, {"send_state": "sent"}, {"send_state": "unknown"},
                                    {"outcome": "discarded"}, {"state": "superseded"}, {"memo_message_id": "memo-new"},
                                    {"rewrite_state": "working"}])
def test_the_sending_guard_itself_refuses_rows_that_moved_on(app, ready, values):
    staff = user()
    turn_id = posted(ready)
    row = db_session.get(CsAgentTurn, turn_id)  # 화면이 본 줄(앞 확인을 지났다)
    table = CsAgentTurn.__table__  # 표 수준 UPDATE — 화면이 본 ORM 줄은 그대로 둔다
    db_session.execute(update(table).where(table.c.id == turn_id).values(**values))  # 그사이 바뀜
    assert send_record.start_sending(db_session, row, user_id=staff.id, click_ms=None, now=NOW) is False
    db_session.rollback()
    fresh_row = db_session.get(CsAgentTurn, turn_id, populate_existing=True)
    assert send_record.start_sending(db_session, fresh_row, user_id=staff.id, click_ms=None, now=NOW) is True  # 대조군


def test_switching_off_between_the_first_mark_and_the_call_sends_nothing(app, ready):
    staff = user()
    turn_id = posted(ready)
    original = ready.__call__.__func__

    class Off(type(ready)):
        def __call__(self, url, **kwargs):
            switches(buttons=False)
            return original(self, url, **kwargs)

    ready.__class__ = Off
    sender = FakeSender(ready)
    assert press(app, ready, turn_id, staff.id, sender).code == "switch_off" and sender.calls == []
    assert fresh(turn_id).send_state is None


def test_an_edit_identical_to_the_draft_counts_as_sent_as_is(app, ready):
    from tests.domains.test_cs_drafting import DRAFT
    staff = user()
    turn_id = posted(ready)
    assert edited(app, ready, turn_id, staff.id, FakeSender(ready), f"  {DRAFT} ").code == "sent"
    row = fresh(turn_id)
    assert (row.outcome, row.edit_ratio, row.edit_reason) == ("as_is", 0, None)


def test_an_error_before_calling_channel_talk_puts_the_row_back(app, ready, monkeypatch):
    staff = user()
    turn_id = posted(ready)

    def boom(*_a, **_k):
        raise RuntimeError("합성 검사 고장")

    monkeypatch.setattr(send_flow, "check_draft", boom)
    with pytest.raises(RuntimeError):
        press(app, ready, turn_id, staff.id, FakeSender(ready))
    assert (fresh(turn_id).send_state, fresh(turn_id).sent_by_user_id) == (None, None)


def test_a_viewer_is_refused_before_the_token_is_even_read(app, client, ready):
    turn_id = posted(ready)
    viewer = user(role="VIEWER", team="CS", name="viewer")
    with client.session_transaction() as sess:
        sess["user_id"] = viewer.id
    denied = client.post(f"{API}/{turn_id}/send", json={"token": token(app, turn_id, viewer.id)})
    assert denied.status_code == 403 and denied.get_json()["error"] == "상담 직원 · 관리자만 쓸 수 있습니다."


def test_discard_itself_refuses_a_row_being_sent(app, ready, monkeypatch):
    staff = user()
    turn_id = posted(ready)
    tok = token(app, turn_id, staff.id)
    set_row(turn_id, send_state="sending")
    monkeypatch.setattr(send_flow, "_closed", lambda _row: None)  # 앞 확인을 지난 줄이 그사이 '보내는 중'이 됐다
    done = send_flow.discard_turn(db_session, turn_id=turn_id, user_id=staff.id, token=tok, secret_key=app.secret_key,
                                  now=NOW)
    assert done.code == "already" and fresh(turn_id).outcome is None


def test_finish_sent_only_writes_rows_that_are_being_sent(app, ready):
    turn_id = posted(ready)
    set_row(turn_id, send_state="failed")
    assert send_record.finish_sent(db_session, turn_id, message_id="sent-x", sent_at=NOW, case=None, now=NOW) is False
    assert fresh(turn_id).send_state == "failed"


def test_a_public_message_with_the_memo_id_is_not_the_draft(app, ready):
    staff = user()
    turn_id = posted(ready)
    for message in ready.messages["uc-1"]:
        if message["id"] == "memo-uc-1":
            message.pop("options")  # 같은 id 의 공개 글 — 우리 비공개 메모가 아니다
    sender = FakeSender(ready)
    assert press(app, ready, turn_id, staff.id, sender).code == "memo_missing" and sender.calls == []
