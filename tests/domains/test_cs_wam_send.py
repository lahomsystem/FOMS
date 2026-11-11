"""AI 초안 채널톡 안 작은 창(WAM) S2 · S3 — [보내기] · [수정하기] · [버리기]를 서명된 상담원으로(설계서 17.2.2).

작은 창은 앱 함수(``cs.draft.get`` · ``send`` · ``discard``)로만 서버를 부른다. 누른 사람은 채널톡이 서명한 상담원이고, 보내기 앞
확인 · 한 번만 · 최신인가 · 검사는 FOMS 화면 길과 같은 흐름을 탄다. 여기서 보는 것: 한 번 → 한 글 · 보낸 상담원이 차례 줄과
감사 원장에 남음(FOMS 짝이 있으면 직원 번호도) · 다른 상담의 차례는 없는 차례 · 확인표는 그 상담원에 묶임 · 화면 길은 여전히 표가
있어야 함 · 고치기 재료 · 버리기 · 관리 화면 칸이 단추를 작은 창으로 바꿈.

채널톡 · 보내기는 가짜(네트워크 없음), 손으로 꾸민 합성 글만. 시각은 2026-11 KST.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

from db import db_session
from foms.services import channel_memo
from foms.services.cs_agent import drafting_post, send, send_flow, send_view, wam_functions
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.masking import mask
from models import ChannelManagerLink, CsAgentTurn, SecurityLog, SystemSetting
from tests.domains.test_cs_drafting import DRAFT, channel  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_photo_read import PHONE
from tests.domains.test_cs_send import NOW, FakeSender, fresh, posted, ready, switches, user  # noqa: F401 — ready 는 fixture
from tests.support.cs_agent_fakes import FakeClock, api_message, at, keys, make_reader  # noqa: F401 — keys 는 fixture

APP_ID = "app0public0wam01"


def call(app, transport, method, params, manager="mgr-7", sender=None):
    """서명을 지난 함수 한 번(함수 받는 곳이 서명 · 채널을 본 뒤와 같은 자리)."""
    return wam_functions.handle(method, params, manager, session=db_session, secret_key=app.secret_key, now=NOW,
                                reader=make_reader(transport, FakeClock()), sender=sender)


def audits(action="CS_AGENT_SEND"):
    return db_session.query(SecurityLog).filter_by(action=action).order_by(SecurityLog.id).all()


# ── [보내기] 한 번 → 한 글 · 보낸 상담원 ─────────────────────────────────────
def test_the_send_window_sends_once_and_records_the_signed_manager(app, ready):
    turn_id = posted(ready)
    sender = FakeSender(ready)
    first = call(app, ready, "cs.draft.send", {"turn": turn_id, "chat": "uc-1"}, sender=sender)
    assert first["result"]["code"] == "sent" and first["result"]["ok"] is True
    assert [(c.chat_id, c.text) for c in sender.calls] == [("uc-1", DRAFT)]
    row = fresh(turn_id)
    assert (row.send_state, row.outcome, row.desk_manager_id, row.sent_by_user_id) == ("sent", "as_is", "mgr-7", None)
    again = call(app, ready, "cs.draft.send", {"turn": turn_id, "chat": "uc-1"}, sender=sender)
    assert again["result"]["code"] == "already" and len(sender.calls) == 1  # 두 번 눌러도 손님 쪽은 한 글
    assert [(a.user_id, a.detail["code"], a.detail["via"], a.detail["channel_manager"]) for a in audits()] == [
        (None, "sent", "wam", "mgr-7"), (None, "already", "wam", "mgr-7")]


def test_a_linked_foms_account_is_recorded_as_the_sender_too(app, ready):
    staff_id = user().id
    db_session.add(ChannelManagerLink(channel_manager_id="mgr-8", user_id=staff_id, is_active=True))
    db_session.commit()
    turn_id = posted(ready)
    result = call(app, ready, "cs.draft.send", {"turn": turn_id, "chat": "uc-1"}, manager="mgr-8",
                  sender=FakeSender(ready))
    assert result["result"]["code"] == "sent"
    row = fresh(turn_id)
    assert (row.desk_manager_id, row.sent_by_user_id) == ("mgr-8", staff_id)
    assert audits()[-1].user_id == staff_id


def test_a_turn_from_another_chat_is_not_found_and_nothing_is_sent(app, ready):
    turn_id = posted(ready)
    sender = FakeSender(ready)
    result = call(app, ready, "cs.draft.send", {"turn": turn_id, "chat": "uc-other"}, sender=sender)
    assert result["result"]["code"] == "not_found" and not sender.calls
    assert fresh(turn_id).send_state is None


def test_a_new_customer_message_reverts_and_clears_the_manager(app, ready):
    turn_id = posted(ready)
    ready.messages["uc-1"].append(api_message("m-new", at(2, 8, 58), "user", "합성 새 글"))
    sender = FakeSender(ready)
    result = call(app, ready, "cs.draft.send", {"turn": turn_id, "chat": "uc-1"}, sender=sender)
    assert result["result"]["code"] == "new_message" and not sender.calls
    row = fresh(turn_id)
    assert (row.send_state, row.desk_manager_id, row.sent_by_user_id) == (None, None, None)


def test_the_confirm_stamp_is_bound_to_the_manager_who_saw_the_warning(app, ready):
    turn_id = posted(ready)
    sender = FakeSender(ready)
    text = "안녕하세요 고객님, 맞춤 선반은 123,000원으로 진행 가능합니다."
    params = {"turn": turn_id, "chat": "uc-1", "mode": "edited", "text": text, "edit_reason": "missing"}
    first = call(app, ready, "cs.draft.send", params, sender=sender)["result"]
    assert first["code"] == "needs_confirm" and "number_not_allowed" in [w["code"] for w in first["warnings"]]
    assert isinstance(first["confirm"], str) and text not in json.dumps(first, ensure_ascii=False)
    other = call(app, ready, "cs.draft.send", {**params, "confirm": first["confirm"]}, manager="mgr-other",
                 sender=sender)["result"]
    assert other["code"] == "needs_confirm" and not sender.calls  # 다른 상담원에겐 그 확인표가 안 먹는다
    second = call(app, ready, "cs.draft.send", {**params, "confirm": first["confirm"]}, sender=sender)["result"]
    assert second["code"] == "sent" and [c.text for c in sender.calls] == [text]
    row = fresh(turn_id)
    assert (row.outcome, row.edit_reason, row.staff_reply_masked) == ("edited", "missing", mask(text))


def test_the_foms_screen_path_still_needs_its_token(app, ready):
    turn_id = posted(ready)
    sender = FakeSender(ready)
    for request in (send_flow.SendRequest(turn_id=turn_id, user_id=None),  # 사람 없는 화면 길
                    send_flow.SendRequest(turn_id=turn_id, user_id=user().id, token="bad")):
        result = send_flow.send_turn(db_session, request, secret_key=app.secret_key, now=NOW,
                                     reader=make_reader(ready, FakeClock()), sender=sender)
        assert result.code == "token" and not sender.calls


# ── [수정하기] 재료 · [버리기] ───────────────────────────────────────────────
def test_the_edit_window_gets_the_draft_and_the_reason_chips(app, ready):
    turn_id = posted(ready)
    got = call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})["result"]
    assert (got["code"], got["blocked"], got["draft"], got["checking"]) == ("ok", None, DRAFT, False)
    assert [code for code, _label in got["edit_reasons"]] == ["wrong_fact", "promise", "tone", "missing", "other"]
    assert call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-x"})["result"]["code"] == "not_found"
    switches(buttons=False)
    off = call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})["result"]
    assert off["blocked"] == send_flow.MESSAGES["switch_off"] and off["draft"] is None


def test_discard_from_the_window_closes_the_turn_without_sending(app, ready):
    turn_id = posted(ready)
    result = call(app, ready, "cs.draft.discard", {"turn": turn_id, "chat": "uc-1"})["result"]
    assert result["code"] == "discarded"
    assert fresh(turn_id).outcome == "discarded"
    assert [(a.detail["code"], a.detail["via"]) for a in audits("CS_AGENT_DISCARD")] == [("discarded", "wam")]
    assert call(app, ready, "cs.draft.discard", {"turn": turn_id, "chat": "uc-1"})["result"]["code"] == "already"


def test_bad_calls_are_refused_before_any_work(app, ready):
    turn_id = posted(ready)
    assert call(app, ready, "cs.draft.send", {"turn": turn_id, "chat": "uc-1"}, manager=None)["error"]["type"] == (
        "unauthorized")
    for params in ({"turn": turn_id}, {"chat": "uc-1"}, {"turn": turn_id, "chat": "uc 1"}, None):
        assert call(app, ready, "cs.draft.send", params)["error"]["type"] == "invalidParams"
    assert wam_functions.handle("cs.draft.get", {"turn": turn_id, "chat": "uc-1"}, "mgr-7")["error"]["type"] == (
        "invalidParams")  # 세션 없이 부르면(ping 밖) 일하지 않는다
    assert fresh(turn_id).send_state is None


# ── 함수 받는 곳(서명) 끝까지 ─────────────────────────────────────────────────
_KEY_HEX = "ab" * 32


def test_signed_function_calls_reach_the_window_functions(app, client, ready, monkeypatch):
    monkeypatch.setenv("CHANNEL_FUNCTION_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_FUNCTION_SIGNING_KEY", _KEY_HEX)
    monkeypatch.setenv("CHANNEL_FUNCTION_CHANNEL_ID", "201824")
    monkeypatch.setattr(send_view, "OpenApiReader", lambda: make_reader(ready, FakeClock()))
    turn_id = posted(ready)

    def put(method, params):
        body = json.dumps({"method": method, "params": params, "systemVersion": "v1", "context": {
            "channel": {"id": "201824"}, "caller": {"type": "manager", "id": "mgr-7"}}}).encode("utf-8")
        signature = base64.b64encode(hmac.new(bytes.fromhex(_KEY_HEX), body, hashlib.sha256).digest()).decode()
        return client.open("/api/channel/functions/v1", method="PUT", data=body,
                           headers={"x-signature": signature, "Content-Type": "application/json"})

    names = [f["name"] for f in put("extension.core.function.getFunctions", {}).get_json()["result"]["functions"]]
    assert {"cs.draft.get", "cs.draft.send", "cs.draft.discard"} <= set(names)
    got = put("cs.draft.get", {"turn": turn_id, "chat": "uc-1"})
    assert got.status_code == 200 and got.get_json()["result"]["draft"] == DRAFT
    gone = put("cs.draft.discard", {"turn": turn_id, "chat": "uc-1"})
    assert gone.get_json()["result"]["code"] == "discarded"


# ── 관리 화면 칸 → 메모 단추 ─────────────────────────────────────────────────
def test_the_button_path_setting_switches_memo_buttons_to_the_window(app, ready, monkeypatch):
    monkeypatch.setenv(send.BASE_URL_ENV, "https://foms.example")
    monkeypatch.setenv(send.WAM_APP_ENV, APP_ID)
    assert st.FIELD_BY_NAME["send_button_path"].default == "link"  # 처음 값은 링크(지금과 같다)
    links = send.memo_buttons(5, "uc-1")
    assert [title for title, _ in links] == ["보내기", "수정하기"] and all(isinstance(u, str) for _, u in links)
    wam = send.memo_buttons(5, "uc-1", path="wam")
    assert [target["args"] for _, target in wam] == [{"turn": 5, "mode": "send"}, {"turn": 5, "mode": "edit"}]
    actions = channel_memo._memo_buttons(wam)
    assert [a["action"]["attributes"] for a in actions] == [
        {"appId": APP_ID, "name": "cs-draft", "wamArgs": {"turn": 5, "mode": "send"}},
        {"appId": APP_ID, "name": "cs-draft", "wamArgs": {"turn": 5, "mode": "edit"}}]
    assert send.memo_buttons(5, "uc 1", path="wam") == ()  # 상담 id 꼴이 틀리면 단추 없음
    monkeypatch.delenv(send.WAM_APP_ENV)
    assert send.memo_buttons(5, "uc-1", path="wam") == links  # 앱 id 가 없으면 링크로(단추가 사라지지 않게)
    monkeypatch.setenv(send.WAM_APP_ENV, APP_ID)
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, "send_buttons_enabled": True, "send_button_path": "wam"}))
    db_session.commit()
    row = SimpleNamespace(id=9)
    assert drafting_post._buttons(SimpleNamespace(session=db_session), row, "uc-1")[0][1]["args"]["turn"] == 9


def test_a_sent_turn_row_keeps_no_text_beyond_masked_copies(app, ready):
    turn_id = posted(ready)
    call(app, ready, "cs.draft.send", {"turn": turn_id, "chat": "uc-1"}, sender=FakeSender(ready))
    row = db_session.get(CsAgentTurn, turn_id)
    assert row.staff_reply_masked == mask(DRAFT) and row.desk_manager_id == "mgr-7"


# ── '왜 고쳤나요' 칸(사장님 11-11 — 고친 답 + 까닭을 배우게) ──────────────────
WHY = "현금 결제는 안 되고 네이버 결제만 된다고 안내해야 해요"
EDITED = "안녕하세요 고객님, 현금 결제는 어렵고 네이버 결제로 가능합니다."


def detail_on(on=True):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, "send_buttons_enabled": True, "realtime_enabled": True, "edit_detail_enabled": on}))
    db_session.commit()


def test_the_edit_window_sends_the_written_reason_with_the_edited_reply(app, ready):
    detail_on()
    turn_id = posted(ready)
    got = call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})["result"]
    assert (got["detail"], got["max_detail"]) == (True, 1000)
    params = {"turn": turn_id, "chat": "uc-1", "mode": "edited", "text": EDITED, "edit_reason": "wrong_fact",
              "edit_detail": WHY}
    sent = call(app, ready, "cs.draft.send", params, sender=FakeSender(ready))["result"]
    assert sent["code"] == "sent" and WHY not in json.dumps(sent, ensure_ascii=False)
    row = fresh(turn_id)
    assert (row.outcome, row.edit_reason, row.edit_detail_masked, row.edit_detail_by) == (
        "edited", "wrong_fact", mask(WHY), None)  # FOMS 짝이 없는 상담원 — 직원 번호는 비움
    assert row.edit_detail_at is not None


def test_the_reason_is_dropped_when_the_detail_switch_is_off_or_the_text_was_not_changed(app, ready):
    detail_on(False)
    turn_id = posted(ready)
    assert call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})["result"]["detail"] is False
    params = {"turn": turn_id, "chat": "uc-1", "mode": "edited", "text": EDITED, "edit_detail": WHY}
    assert call(app, ready, "cs.draft.send", params, sender=FakeSender(ready))["result"]["code"] == "sent"
    assert fresh(turn_id).edit_detail_masked is None
    detail_on()
    same = posted(ready, chat="uc-2")
    params = {"turn": same, "chat": "uc-2", "mode": "edited", "text": DRAFT, "edit_detail": WHY}
    assert call(app, ready, "cs.draft.send", params, sender=FakeSender(ready))["result"]["code"] == "sent"
    assert (fresh(same).outcome, fresh(same).edit_detail_masked) == ("as_is", None)  # 안 고쳤으면 까닭도 없다


def test_customer_details_in_the_reason_block_the_send(app, ready):
    detail_on()
    turn_id = posted(ready)
    sender = FakeSender(ready)
    params = {"turn": turn_id, "chat": "uc-1", "mode": "edited", "text": EDITED, "edit_detail": f"손님 번호 {PHONE}"}
    result = call(app, ready, "cs.draft.send", params, sender=sender)["result"]
    assert (result["code"], result["field"]) == ("detail_private", "detail_private") and not sender.calls
    assert PHONE not in json.dumps(result, ensure_ascii=False) and fresh(turn_id).send_state is None

