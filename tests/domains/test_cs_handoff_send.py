"""넘김 메모 [배우기] · [흘리기](사장님 11-11) — 직원이 작은 창에서 쓴 답을 한 번만 손님께 · '직접 답'으로 적어 그날 밤 배움 ·
흘리면 배우지 않음 · 되돌리기. 초안 [보내기] 길(``cs.draft.*``)과 서로의 차례를 열지 못한다.

여기서 보는 것: 창 재료(까닭 · 가린 AI 메모 힌트 · 본 마지막 손님 글) · 한 번 → 한 글 · 직원이 먼저 답했으면 막음 · 손님이 더
썼으면 한 번 더 · 확실한 위험은 막고 경고는 확인표 · 스위치 · 'AI 냐' 차례는 안 엶 · 흘리기 · 되돌리기 · 같은 상담 다른 차례가
보내는 중이면 '확인 중' · 결과 맞추기가 '직접 답'으로 · 단추는 작은 창 길만 · 글은 로그 · 결과에 없음.

채널톡 · 보내기는 가짜(네트워크 없음), 손으로 꾸민 합성 글만. 시각은 2026-11 KST.
"""

from __future__ import annotations

import datetime
import json
import logging

from types import SimpleNamespace

import pytest
from sqlalchemy import update

from db import db_session
from foms.services.cs_agent import handoff_memo, handoff_send, metrics, send, send_record, turns, wam_functions
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.masking import mask
from models import CsAgentTurn, SecurityLog, SystemSetting
from tests.domains.test_cs_drafting import channel, customer  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_send import ACCOUNT, NOW, FakeSender, fresh, posted, switches
from tests.support.cs_agent_fakes import FakeClock, api_message, at, keys, make_reader  # noqa: F401 — keys 는 fixture

APP_ID = "app0public0wam01"
NOTE = "배송 일정은 주문 내역에서 출고일을 먼저 확인한 뒤 안내해 주세요"
REPLY = "안녕하세요 고객님, 주문 내역 확인해서 다시 안내드리겠습니다."
MARK = "청록고래배우기글표지"


def on(*, handoff_buttons=True, buttons=True):
    switches(buttons=buttons)
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, "send_buttons_enabled": buttons, "realtime_enabled": True,
        "handoff_buttons_enabled": handoff_buttons}))
    db_session.commit()


@pytest.fixture
def ready(channel):  # noqa: F811
    on()
    return channel


def handed(channel, chat="uc-1", *, reason="order_lookup", code="handoff", note=NOTE, check_codes=()):  # noqa: F811
    """넘김 메모가 붙은 건너뜀 차례 — 상태 표 · 가짜 채널톡에 손님 글, 가짜 채널톡에 우리 넘김 메모(비공개)."""
    customer(channel, chat)
    row = turns.claim_turn(db_session, "LAHOM", chat, f"m-{chat}", now=at(2, 8, 51))
    if code == "handoff":
        turns.record_handoff(row, reason=reason)
    turns.mark_skipped(row, reason=code, check_codes=check_codes, now=at(2, 8, 51))
    db_session.commit()
    turns.record_note_memo(row, memo_message_id=f"hmemo-{chat}", now=at(2, 8, 52))
    db_session.commit()
    body = handoff_memo.memo_body(code, handoff_reason=reason, check_codes=check_codes, staff_note=note)
    channel.messages[chat].append(api_message(f"hmemo-{chat}", at(2, 8, 52), "bot", body, options=["private"]))
    return row.id


def call(app, transport, method, params, manager="mgr-7", sender=None):
    return wam_functions.handle(method, params, manager, session=db_session, secret_key=app.secret_key, now=NOW,
                                reader=make_reader(transport, FakeClock()), sender=sender)["result"]


def audits(action):
    return db_session.query(SecurityLog).filter_by(action=action).order_by(SecurityLog.id).all()


# ── 창 재료 · 한 번 → 한 글 ──────────────────────────────────────────────
def test_the_learn_window_shows_reason_hint_and_sends_once_as_a_direct_reply(app, ready):
    turn_id = handed(ready)
    got = call(app, ready, "cs.handoff.get", {"turn": turn_id, "chat": "uc-1"})
    assert (got["code"], got["ok"], got["seen"], got["note"]) == ("write", True, "m-uc-1", None)
    assert got["reason"] == handoff_memo.HANDOFF_TEXTS["order_lookup"] and got["hint"] == mask(NOTE)
    assert got["message"] == handoff_send.HANDOFF_MESSAGES["write"] and got["max_text"] == 1000
    sender = FakeSender(ready)
    params = {"turn": turn_id, "chat": "uc-1", "text": REPLY, "seen": got["seen"], "shown_ms": 41000}
    first = call(app, ready, "cs.handoff.send", params, sender=sender)
    assert (first["code"], first["message"]) == ("sent", handoff_send.HANDOFF_MESSAGES["sent"])
    assert [(c.chat_id, c.text, c.turn_id) for c in sender.calls] == [("uc-1", REPLY, turn_id)]
    row = fresh(turn_id)
    assert (row.state, row.send_state, row.outcome, row.edit_ratio, row.edit_reason) == (
        "skipped", "sent", "direct", None, None)
    assert (row.staff_reply_masked, row.desk_manager_id, row.click_ms) == (mask(REPLY), "mgr-7", 41000)
    again = call(app, ready, "cs.handoff.send", params, sender=sender)
    assert again["code"] == "learn_sent" and len(sender.calls) == 1  # 두 번 눌러도 손님 쪽은 한 글
    assert call(app, ready, "cs.handoff.get", {"turn": turn_id, "chat": "uc-1"})["code"] == "learn_sent"
    assert [(a.detail["code"], a.detail["kind"], a.detail["via"], a.detail["channel_manager"])
            for a in audits("CS_AGENT_SEND")] == [("sent", "handoff", "wam", "mgr-7"),
                                                  ("learn_sent", "handoff", "wam", "mgr-7")]


def test_the_draft_path_and_the_learn_path_never_open_each_others_turns(app, ready):
    handoff_id = handed(ready)
    sender = FakeSender(ready)
    assert call(app, ready, "cs.draft.send", {"turn": handoff_id, "chat": "uc-1"}, sender=sender)["code"] == "not_open"
    draft_id = posted(ready, chat="uc-2")
    assert call(app, ready, "cs.handoff.send", {"turn": draft_id, "chat": "uc-2", "text": REPLY},
                sender=sender)["code"] == "not_open"
    assert call(app, ready, "cs.handoff.get", {"turn": draft_id, "chat": "uc-2"})["code"] == "not_open"
    assert call(app, ready, "cs.handoff.skip", {"turn": draft_id, "chat": "uc-2"})["code"] == "not_open"
    assert not sender.calls and fresh(draft_id).outcome is None and fresh(handoff_id).send_state is None


def test_an_asked_if_ai_turn_and_another_chat_are_never_opened(app, ready):
    ai_id = handed(ready, reason="asked_if_ai")
    assert call(app, ready, "cs.handoff.get", {"turn": ai_id, "chat": "uc-1"})["code"] == "not_open"
    other = handed(ready, chat="uc-3")
    assert call(app, ready, "cs.handoff.get", {"turn": other, "chat": "uc-1"})["code"] == "not_found"
    assert call(app, ready, "cs.handoff.send", {"turn": other, "chat": "uc-1", "text": REPLY},
                sender=FakeSender(ready))["code"] == "not_found"


# ── 최신인가 — 답이 나갔으면 막음 · 손님이 더 썼으면 한 번 더 ────────────────
def test_a_staff_reply_already_sent_blocks_the_learn_send(app, ready):
    turn_id = handed(ready)
    ready.messages["uc-1"].append(api_message("m-staff", at(2, 8, 55), "manager", "합성 직원 답"))
    assert call(app, ready, "cs.handoff.get", {"turn": turn_id, "chat": "uc-1"})["code"] == "answered"
    sender = FakeSender(ready)
    result = call(app, ready, "cs.handoff.send", {"turn": turn_id, "chat": "uc-1", "text": REPLY}, sender=sender)
    assert result["code"] == "answered" and not sender.calls
    row = fresh(turn_id)
    assert (row.send_state, row.desk_manager_id, row.outcome) == (None, None, None)


def test_a_new_customer_message_asks_once_more_and_the_second_press_sends(app, ready):
    turn_id = handed(ready)
    seen = call(app, ready, "cs.handoff.get", {"turn": turn_id, "chat": "uc-1"})["seen"]
    ready.messages["uc-1"].append(api_message("m-more", at(2, 8, 58), "user", "합성 손님 덧글"))
    sender = FakeSender(ready)
    params = {"turn": turn_id, "chat": "uc-1", "text": REPLY, "seen": seen}
    first = call(app, ready, "cs.handoff.send", params, sender=sender)
    assert (first["code"], first["seen"]) == ("new_message", "m-more") and not sender.calls
    assert first["message"] == handoff_send.HANDOFF_MESSAGES["new_message"] and fresh(turn_id).send_state is None
    second = call(app, ready, "cs.handoff.send", {**params, "seen": first["seen"]}, sender=sender)
    assert second["code"] == "sent" and len(sender.calls) == 1


def test_more_customer_words_before_opening_are_noted_but_do_not_block(app, ready):
    turn_id = handed(ready)
    ready.messages["uc-1"].append(api_message("m-more", at(2, 8, 54), "user", "합성 손님 덧글"))
    got = call(app, ready, "cs.handoff.get", {"turn": turn_id, "chat": "uc-1"})
    assert (got["code"], got["seen"], got["note"]) == ("write", "m-more", handoff_send.MORE_NOTE)
    result = call(app, ready, "cs.handoff.send", {"turn": turn_id, "chat": "uc-1", "text": REPLY, "seen": got["seen"]},
                  sender=FakeSender(ready))
    assert result["code"] == "sent"


# ── 검사 · 스위치 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("text, code", [
    (f"입금은 {ACCOUNT} 계좌로 부탁드립니다.", "account_number"),
    (f"안녕하세요 고객님, {NOTE}.", "private_memo_leak"),  # 힌트(AI 메모 직원 참고)를 그대로 베낌
    ("저는 AI 상담원이라 확인이 어려워요.", "ai_mention"),
])
def test_hard_risks_are_blocked_and_nothing_is_sent(app, ready, text, code):
    turn_id = handed(ready)
    sender = FakeSender(ready)
    result = call(app, ready, "cs.handoff.send", {"turn": turn_id, "chat": "uc-1", "text": text}, sender=sender)
    assert result["code"] == "blocked" and code in [p["code"] for p in result["problems"]] and not sender.calls
    assert fresh(turn_id).send_state is None


def test_a_warning_needs_the_confirm_stamp_of_the_same_manager(app, ready):
    turn_id = handed(ready)
    sender = FakeSender(ready)
    text = "안녕하세요 고객님, 맞춤 선반은 123,000원으로 진행 가능합니다."
    params = {"turn": turn_id, "chat": "uc-1", "text": text}
    first = call(app, ready, "cs.handoff.send", params, sender=sender)
    assert first["code"] == "needs_confirm" and isinstance(first["confirm"], str) and not sender.calls
    other = call(app, ready, "cs.handoff.send", {**params, "confirm": first["confirm"]}, manager="mgr-x",
                 sender=sender)
    assert other["code"] == "needs_confirm" and not sender.calls
    second = call(app, ready, "cs.handoff.send", {**params, "confirm": first["confirm"]}, sender=sender)
    assert second["code"] == "sent" and [c.text for c in sender.calls] == [text]


def test_switches_off_never_send_but_skip_still_works(app, ready):
    turn_id = handed(ready)
    sender = FakeSender(ready)
    params = {"turn": turn_id, "chat": "uc-1", "text": REPLY}
    on(handoff_buttons=False)
    assert call(app, ready, "cs.handoff.get", {"turn": turn_id, "chat": "uc-1"})["code"] == "buttons_off"
    assert call(app, ready, "cs.handoff.send", params, sender=sender)["code"] == "buttons_off"
    on(buttons=False)
    assert call(app, ready, "cs.handoff.send", params, sender=sender)["code"] == "switch_off"
    assert not sender.calls
    assert call(app, ready, "cs.handoff.skip", {"turn": turn_id, "chat": "uc-1"})["code"] == "skipped"


def test_unsigned_callers_and_bad_params_are_refused(app, ready):
    turn_id = handed(ready)
    out = wam_functions.handle("cs.handoff.send", {"turn": turn_id, "chat": "uc-1", "text": REPLY}, None,
                               session=db_session, secret_key=app.secret_key, now=NOW)
    assert out["error"]["type"] == "unauthorized"
    out = wam_functions.handle("cs.handoff.get", {"turn": turn_id}, "mgr-7", session=db_session,
                               secret_key=app.secret_key, now=NOW)
    assert out["error"]["type"] == "invalidParams"
    assert call(app, ready, "cs.handoff.send", {"turn": turn_id, "chat": "uc-1", "text": " "})["code"] == (
        "bad_request")
    assert {schema["name"] for schema in wam_functions.FUNCTION_SCHEMAS} >= {
        "cs.handoff.get", "cs.handoff.send", "cs.handoff.skip", "cs.handoff.unskip"}


# ── [흘리기] · [배우기로 바꾸기] ─────────────────────────────────────────
def test_skip_then_unskip_an_open_turn_and_then_teach_it(app, ready):
    turn_id = handed(ready)
    skipped = call(app, ready, "cs.handoff.skip", {"turn": turn_id, "chat": "uc-1"})
    assert (skipped["code"], fresh(turn_id).outcome) == ("skipped", "discarded")
    assert call(app, ready, "cs.handoff.get", {"turn": turn_id, "chat": "uc-1"})["code"] == "is_skipped"
    sender = FakeSender(ready)
    params = {"turn": turn_id, "chat": "uc-1", "text": REPLY}
    assert call(app, ready, "cs.handoff.send", params, sender=sender)["code"] == "is_skipped" and not sender.calls
    back = call(app, ready, "cs.handoff.unskip", {"turn": turn_id, "chat": "uc-1"})
    assert (back["code"], fresh(turn_id).outcome) == ("unskipped_open", None)
    assert call(app, ready, "cs.handoff.unskip", {"turn": turn_id, "chat": "uc-1"})["code"] == "not_skipped"
    assert call(app, ready, "cs.handoff.send", params, sender=sender)["code"] == "sent"
    assert [a.detail["code"] for a in audits("CS_AGENT_HANDOFF_SKIP")] == ["skipped"]
    assert [a.detail["code"] for a in audits("CS_AGENT_HANDOFF_UNSKIP")] == ["unskipped_open", "not_skipped"]


def test_skipping_a_sent_turn_and_undoing_it_restores_the_direct_reply(app, ready):
    turn_id = handed(ready)
    call(app, ready, "cs.handoff.send", {"turn": turn_id, "chat": "uc-1", "text": REPLY}, sender=FakeSender(ready))
    assert call(app, ready, "cs.handoff.skip", {"turn": turn_id, "chat": "uc-1"})["code"] == "skipped"
    assert (fresh(turn_id).send_state, fresh(turn_id).outcome) == ("sent", "discarded")
    assert call(app, ready, "cs.handoff.unskip", {"turn": turn_id, "chat": "uc-1"})["code"] == "unskipped_sent"
    assert fresh(turn_id).outcome == "direct"


def test_skipping_a_turn_already_learned_says_so(app, ready, monkeypatch):
    turn_id = handed(ready)
    monkeypatch.setattr(handoff_send, "used_ids", lambda _session: frozenset({turn_id}))
    result = call(app, ready, "cs.handoff.skip", {"turn": turn_id, "chat": "uc-1"})
    assert result["code"] == "skipped_learned" and "거절" in result["message"]


def test_skip_while_sending_waits(app, ready):
    turn_id = handed(ready)
    db_session.execute(update(CsAgentTurn).where(CsAgentTurn.id == turn_id).values(send_state="sending"))
    db_session.commit()
    assert call(app, ready, "cs.handoff.skip", {"turn": turn_id, "chat": "uc-1"})["code"] == "checking"
    assert fresh(turn_id).outcome is None


# ── 같은 상담 다른 차례 · 결과 맞추기 ─────────────────────────────────────
def test_another_turn_of_the_same_chat_sending_makes_both_paths_wait(app, ready):
    turn_id = handed(ready)
    ready.messages["uc-1"].append(api_message("m-2", at(2, 8, 56), "user", "합성 손님 덧글"))
    other = CsAgentTurn(brand="LAHOM", chat_id="uc-1", last_user_message_id="m-2", state="posted",
                        memo_message_id="memo-2", send_state="sending")
    db_session.add(other)
    db_session.commit()
    other_id = other.id
    sender = FakeSender(ready)
    assert call(app, ready, "cs.handoff.send", {"turn": turn_id, "chat": "uc-1", "text": REPLY},
                sender=sender)["code"] == "checking"
    db_session.execute(update(CsAgentTurn).where(CsAgentTurn.id == other_id).values(send_state=None))
    db_session.execute(update(CsAgentTurn).where(CsAgentTurn.id == turn_id).values(send_state="unknown"))
    db_session.commit()
    assert call(app, ready, "cs.draft.send", {"turn": other_id, "chat": "uc-1"}, sender=sender)["code"] == "checking"
    assert not sender.calls


def test_a_dead_sender_is_reconciled_as_a_direct_reply(app, ready):
    turn_id = handed(ready)
    old = datetime.datetime(2026, 11, 1, 23, 0)  # UTC naive — '보내는 중'이 오래 남음(보내던 web 이 죽음)
    db_session.execute(update(CsAgentTurn).where(CsAgentTurn.id == turn_id).values(
        send_state="sending", send_started_at=old, desk_manager_id="mgr-7"))
    db_session.commit()
    ready.messages["uc-1"].append(api_message("sent-x", at(2, 8, 59), "bot", REPLY,
                                              requestId=send.request_id_for(turn_id)))
    verdict = send_record.reconcile_turn(db_session, fresh(turn_id), now=NOW, reader=make_reader(ready, FakeClock()))
    row = fresh(turn_id)
    assert (verdict, row.send_state, row.outcome, row.staff_reply_masked) == ("sent", "sent", "direct", mask(REPLY))


# ── 단추 · 글 ─────────────────────────────────────────────────────────────
def test_buttons_go_on_the_window_path_only(monkeypatch):
    monkeypatch.setenv(send.WAM_APP_ENV, APP_ID)
    wam = send.handoff_buttons(5, "uc-1", path="wam")
    assert [(title, target["args"]) for title, target in wam] == [
        ("배우기", {"turn": 5, "mode": "learn"}), ("흘리기", {"turn": 5, "mode": "skip"})]
    assert send.handoff_buttons(5, "uc-1", path="link") == ()  # 링크로 대신 달지 않는다
    assert send.handoff_buttons(5, "uc 1", path="wam") == ()
    monkeypatch.delenv(send.WAM_APP_ENV)
    assert send.handoff_buttons(5, "uc-1", path="wam") == ()
    assert send_record.HANDOFF_CODES == handoff_memo.MEMO_CODES


def test_the_reply_text_never_reaches_logs_or_results(app, ready, caplog):
    turn_id = handed(ready)
    text = f"안녕하세요 고객님, {MARK} 안내드리겠습니다."
    with caplog.at_level(logging.DEBUG):
        result = call(app, ready, "cs.handoff.send", {"turn": turn_id, "chat": "uc-1", "text": text},
                      sender=FakeSender(ready))
    assert result["code"] == "sent"
    assert MARK not in caplog.text and MARK not in json.dumps(result, ensure_ascii=False)
    assert all(MARK not in json.dumps(a.detail, ensure_ascii=False) for a in audits("CS_AGENT_SEND"))


def test_metrics_count_only_draft_sends_not_learn_sends():
    when = datetime.datetime(2026, 11, 2, 1, 0)

    def row(state, send_state, outcome):
        return SimpleNamespace(state=state, send_state=send_state, outcome=outcome, placed_at=None, latency_ms=None,
                               asked_at=when, sent_at=when + datetime.timedelta(seconds=30), click_ms=900,
                               error_code="handoff" if state == "skipped" else None)

    result = metrics._brand("LAHOM", [row("posted", "sent", "as_is"), row("skipped", "sent", "direct")],
                            lambda _day: True)
    assert (result.as_is.hits, result.as_is.total, result.button.total) == (1, 1, 1)

