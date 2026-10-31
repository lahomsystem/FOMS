"""[보내기] · [수정하기](플랜 C10-3) 둘레 — 화면 두 개 · '고칠 말' 다시 쓰기(빠른 길) · 메모 링크 버튼 · 채널 보내기 함수 ·
버리기 · 빠른 길 · 15분 바퀴 배선 · 마이그레이션 ``csagent_04`` · 화면 규칙. 완료 기준 ①~⑨ 는 ``test_cs_send.py``.

채널톡 · 두뇌는 가짜(네트워크 없음), 손으로 꾸민 합성 글만. 시각은 2026-11 KST(11-02 월).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import requests
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint

from db import db_session
from foms.services import channel_client, channel_send
from foms.services.cs_agent import loop, memo, realtime, rewrite, send, send_flow, send_record, send_view
from foms.services.cs_agent.masking import mask
from models import CsAgentTurn
from tests.domains.test_cs_drafting import DRAFT, FakeBrain, FakePoster, channel, customer, result, run  # noqa: F401
from tests.domains.test_cs_send import FakeSender, fresh, posted, press, switches, token, user
from tests.support.cs_agent_fakes import FakeClock, at, keys, make_reader  # noqa: F401 — keys 는 fixture

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "csagent_04_turn_send_state.py"
NOW = at(2, 9)
NEW_DRAFT = "안녕하세요 고객님, 합성 선반 깊이는 350mm 입니다. 더 궁금하시면 말씀 주세요."


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ready(channel, monkeypatch):
    switches()
    monkeypatch.setenv(send.BASE_URL_ENV, "https://foms.example")
    monkeypatch.setattr(send_view, "OpenApiReader", lambda *a, **k: make_reader(channel, FakeClock()))
    return channel


def login(client, row):
    with client.session_transaction() as sess:
        sess["user_id"] = row.id


# ── 화면 두 개(GET 은 보여 주기만) ───────────────────────────────────────
def test_the_edit_screen_shows_the_text_box_reasons_and_rewrite(client, ready):
    turn_id = posted(ready)
    login(client, user())
    html = client.get(f"/cs-agent/turns/{turn_id}/edit?c=uc-1").get_data(as_text=True)
    for needle in ("data-cs-send-text", "data-cs-send-reason", 'value="wrong_fact"', "틀린 사실", "data-cs-rewrite-go",
                   "남은 3번", 'data-mode="edit"', "js/cs-agent/send-screen.js", DRAFT, "csrf-token"):
        assert needle in html, needle
    assert fresh(turn_id).send_state is None


def test_a_link_for_another_chat_or_turn_is_not_found_and_other_teams_see_a_refusal(client, ready):
    turn_id = posted(ready)
    login(client, user())
    assert client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-9").status_code == 404  # 다른 환경 · 다른 상담 링크
    assert client.get(f"/cs-agent/turns/{turn_id}/send").status_code == 404
    assert client.get(f"/cs-agent/turns/{turn_id + 99}/send?c=uc-1").status_code == 404
    login(client, user(role="STAFF", team="SALES", name="sales"))
    denied = client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-1")
    assert denied.status_code == 403 and DRAFT not in denied.get_data(as_text=True)


def test_a_sent_or_switched_off_turn_shows_why_and_no_send_button(app, client, ready):
    staff = user()
    turn_id = posted(ready)
    login(client, staff)
    switches(buttons=False)
    html = client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-1").get_data(as_text=True)
    assert send_flow.MESSAGES["switch_off"] in html and "data-cs-send-go" not in html and 'data-token=""' in html
    switches()
    assert press(app, ready, turn_id, staff.id, FakeSender(ready)).code == "sent"
    html = client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-1").get_data(as_text=True)
    assert send_view.STATUS_LABELS["sent"] in html and "data-cs-send-go" not in html


# ── 버리기 ───────────────────────────────────────────────────────────────
def test_discard_marks_the_case_and_blocks_a_later_send(app, ready):
    staff = user()
    turn_id = posted(ready)
    done = send_flow.discard_turn(db_session, turn_id=turn_id, user_id=staff.id, token=token(app, turn_id, staff.id),
                                  secret_key=app.secret_key, now=NOW)
    assert done.code == "discarded" and fresh(turn_id).outcome == "discarded"
    sender = FakeSender(ready)
    assert press(app, ready, turn_id, staff.id, sender).code == "already" and not sender.calls


# ── '고칠 말' 다시 쓰기(빠른 길이 받는다) ─────────────────────────────────
def test_a_rewrite_request_becomes_a_new_memo_with_buttons_through_the_fast_path(app, ready):
    staff = user()
    turn_id = posted(ready)
    old_token = token(app, turn_id, staff.id)
    asked = send_flow.request_rewrite(db_session, turn_id=turn_id, user_id=staff.id, token=old_token,
                                      note="더 짧게 써 주세요", secret_key=app.secret_key, now=NOW)
    row = fresh(turn_id)
    assert asked.code == "rewrite_requested" and (row.rewrite_state, row.rewrite_note_masked) == (
        "requested", "더 짧게 써 주세요")
    brain_fn = FakeBrain(result(draft=NEW_DRAFT))
    calls = []

    def post(chat_id, text, *, brand, **kwargs):
        calls.append((chat_id, kwargs.get("buttons")))
        return memo.MemoResult(True, verified=True, message_id="memo-2")

    tick = realtime.run_tick(db_session, memory=realtime.TickMemory(), stop=loop.StopFlag(), now=NOW,
                             reader=make_reader(ready, FakeClock()), clock=lambda: 0.0, brain=brain_fn, poster=post,
                             is_business_day=lambda _d: True)
    (request,) = brain_fn.requests
    assert request.rewrite == (DRAFT, "더 짧게 써 주세요") and request.realtime is True
    assert tick.rewrites == {"done": 1}
    ((chat_id, buttons),) = calls
    assert chat_id == "uc-1" and [title for title, _ in buttons] == ["보내기", "수정하기"]
    assert buttons[0][1] == f"https://foms.example/cs-agent/turns/{turn_id}/send?c=uc-1"
    row = fresh(turn_id)
    assert (row.rewrite_state, row.memo_message_id, row.masked_draft, row.rewrite_count) == (
        "done", "memo-2", mask(NEW_DRAFT), 1)
    stale = send_flow.discard_turn(db_session, turn_id=turn_id, user_id=staff.id, token=old_token,
                                   secret_key=app.secret_key, now=NOW)
    assert (stale.code, stale.data["reason"]) == ("token", "token_stale")  # 옛 화면의 표는 새 메모에 안 맞는다


def test_rewrites_are_refused_when_the_fast_path_is_off_and_capped_per_turn(app, ready):
    staff = user()
    turn_id = posted(ready)

    def ask():
        return send_flow.request_rewrite(db_session, turn_id=turn_id, user_id=staff.id, token=token(app, turn_id, staff.id),
                                         note="합성 고칠 말", secret_key=app.secret_key, now=NOW).code

    switches(realtime=False)
    assert ask() == "rewrite_off" and fresh(turn_id).rewrite_state is None
    switches()
    db_session.query(CsAgentTurn).filter_by(id=turn_id).update({"rewrite_count": send_flow.MAX_REWRITES})
    db_session.commit()
    assert ask() == "already"


def test_a_rewrite_that_fails_the_check_posts_nothing(app, ready):
    staff = user()
    turn_id = posted(ready)
    send_flow.request_rewrite(db_session, turn_id=turn_id, user_id=staff.id, token=token(app, turn_id, staff.id),
                              note="할인 얘기 넣어 주세요", secret_key=app.secret_key, now=NOW)
    poster = FakePoster()
    counts = rewrite.run_rewrites(db_session, now=NOW, stop=loop.StopFlag(), reader=make_reader(ready, FakeClock()),
                                  brain=FakeBrain(result(draft="고객님 하우드 제품으로 10% 할인해 드립니다.")),
                                  poster=poster)
    row = fresh(turn_id)
    assert counts == {"check_failed": 1} and poster.calls == [] and (row.rewrite_state, row.memo_message_id) == (
        "failed", "memo-uc-1")


# ── 메모 링크 버튼(관리 화면 스위치 · 기본 주소) ──────────────────────────
@pytest.mark.parametrize("buttons_on,base,expected", [(True, "https://foms.example", 2), (False, "https://foms.example", 0),
                                                       (True, "", 0), (True, "http://foms.example", 0)])
def test_draft_memos_get_link_buttons_only_when_switched_on_with_an_https_base(channel, monkeypatch, buttons_on, base,
                                                                              expected):
    switches(buttons=buttons_on, realtime=False)
    monkeypatch.setenv(send.BASE_URL_ENV, base)
    customer(channel)
    poster = FakePoster()
    run(channel, "memo", poster=poster)
    (call,) = poster.calls
    buttons = call.kwargs.get("buttons", ())
    assert len(buttons) == expected
    if expected:
        turn_id = fresh_turn_id()
        assert buttons == ((send.BUTTON_SEND, f"{base}/cs-agent/turns/{turn_id}/send?c=uc-1"),
                           (send.BUTTON_EDIT, f"{base}/cs-agent/turns/{turn_id}/edit?c=uc-1"))
        assert "token" not in buttons[0][1]  # 주소에는 서명 표가 없다


def fresh_turn_id():
    db_session.expire_all()
    return db_session.query(CsAgentTurn.id).order_by(CsAgentTurn.id.desc()).first()[0]


# ── 채널 보내기 함수(손님이 보는 봇 공개 글 · requestId) ────────────────────
class Http:
    def __init__(self, status=200, body=None, raises=None):
        self.status, self.body, self.raises, self.calls = status, body, raises, []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.raises:
            raise self.raises
        fake = self

        class _Resp:
            status_code = fake.status

            @staticmethod
            def json():
                return fake.body if fake.body is not None else {"message": {"id": "sent-1",
                                                                            "createdAt": "2026-11-02T00:01:00Z"}}
        return _Resp()


@pytest.mark.parametrize("http,expected", [
    (Http(), {"success": True, "message_id": "sent-1", "created_at": "2026-11-02T00:01:00Z", "error": None}),
    (Http(status=422), {"success": False, "message_id": None, "created_at": None, "error": "provider_error"}),
    (Http(status=503), {"success": False, "message_id": None, "created_at": None, "error": "request_failed"}),
    (Http(raises=requests.Timeout("read timed out")),
     {"success": False, "message_id": None, "created_at": None, "error": "request_failed"}),
])
def test_the_channel_sender_posts_a_public_bot_message_with_the_request_id(monkeypatch, http, expected):
    monkeypatch.setattr(channel_client.requests, "post", http)
    monkeypatch.setattr(channel_client, "_open_api_headers", lambda brand: {"x-brand": brand})
    got = channel_send.send_public_bot_message("uc-1", "합성 답", brand="LAHOM", bot_name="라홈",
                                               request_id="foms-cs-send-7")
    assert got == expected
    (call,) = http.calls
    assert call["url"].endswith("/open/user-chats/uc-1/messages") and call["params"] == {"botName": "라홈"}
    assert call["json"] == {"plainText": "합성 답", "requestId": "foms-cs-send-7"}  # 옵션 칸이 없다 — 공개 글
    with pytest.raises(ValueError):
        channel_send.send_public_bot_message("x/../y", "합성", brand="LAHOM", bot_name="라홈", request_id="r")


def test_the_real_wrapper_reaches_the_channel_sender_with_the_turn_request_id(monkeypatch):
    http = Http()
    monkeypatch.setattr(channel_client.requests, "post", http)
    monkeypatch.setattr(channel_client, "_open_api_headers", lambda brand: {"x-brand": brand})
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, "uc-1")
    for env in ("FOMS_ENV", "RAILWAY_PROJECT_NAME"):
        monkeypatch.delenv(env, raising=False)
    sent = send.send_reply("uc-1", "  합성 답  ", brand="LAHOM", turn_id=42)
    assert (sent.posted, sent.message_id, sent.created_at.isoformat()) == (True, "sent-1", "2026-11-02T00:01:00+00:00")
    assert http.calls[0]["json"] == {"plainText": "합성 답", "requestId": "foms-cs-send-42"}
    assert http.calls[0]["params"] == {"botName": send.SEND_BOT_NAME} and "AI" not in send.SEND_BOT_NAME


# ── 15분 바퀴도 결과 모름을 맞춘다 ────────────────────────────────────────
def test_the_quarter_hour_pass_reconciles_unknown_sends(app, ready, monkeypatch):
    staff = user()
    turn_id = posted(ready)
    assert press(app, ready, turn_id, staff.id, FakeSender(ready, send.SendResult(False, reason=send.SEND_UNKNOWN))
                 ).code == "checking"
    monkeypatch.setattr(loop, "run_drafting", lambda *a, **k: None)  # 초안은 이 시험 밖
    result = loop.run_pass(db_session, config=loop.LoopConfig(), stop=loop.StopFlag(), now=at(2, 9, 2),
                           reader=make_reader(ready, FakeClock()), clock=lambda: 0.0, is_business_day=lambda _d: True)
    assert result.outcome == "ok" and result.summary()["sends"] == {"sent": 1} and fresh(turn_id).send_state == "sent"


# ── 마이그레이션 · 모델 ──────────────────────────────────────────────────
def test_csagent_04_chains_onto_csagent_03_and_matches_the_model():
    module = load(MIGRATION, "csagent_04_unit")
    assert (module.revision, module.down_revision) == ("csagent_04", "csagent_03")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    assert module.SEND_STATES == send_record.SEND_STATES and module.REWRITE_STATES == rewrite.REWRITE_STATES
    checks = {c.name: str(c.sqltext) for c in CsAgentTurn.__table__.constraints if isinstance(c, CheckConstraint)}
    assert checks[module.SEND_STATE_CHECK] == module.in_check("send_state", module.SEND_STATES)
    assert checks[module.REWRITE_STATE_CHECK] == module.in_check("rewrite_state", module.REWRITE_STATES)
    columns = CsAgentTurn.__table__.c
    for name, type_, nullable, _default in module.COLUMNS:
        column = columns[name]
        assert column.nullable is nullable and type(column.type).__name__ == type(type_).__name__, name
        assert getattr(column.type, "length", None) == getattr(type_, "length", None), name
    assert str(columns.rewrite_count.server_default.arg) == "0"
    indexes = {i.name: [c.name for c in i.columns] for i in CsAgentTurn.__table__.indexes}
    assert all(indexes[name] == [column] for name, column in module.INDEXES)
    up, down = source.split("def upgrade", 1)[1].split("def downgrade", 1)
    assert up.index("add_column") < up.index("create_check_constraint") < up.index("create_index")
    assert down.index("drop_index") < down.index("drop_constraint") < down.index("drop_column")
    heads = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads()
    assert heads == ["csagent_04"]


# ── 화면 규칙(인라인 스타일 · 스크립트 없음 · jQuery 없음 · fetch 검사) ──────
def test_the_screen_follows_the_frontend_rules():
    html = (ROOT / "templates/cs/cs_agent_send.html").read_text(encoding="utf-8")
    assert 'style="' not in html and "onclick" not in html and "<script>" not in html.replace(
        '{% include "partials/shared/csrf_bootstrap.html" %}', "")
    assert 'send-screen.js\') }}?v=' in html and "defer></script>" in html
    script = (ROOT / "static/js/cs-agent/send-screen.js").read_text(encoding="utf-8")
    assert ".innerHTML" not in script and "jQuery" not in script and "$(" not in script
    assert "__FOMS_CS_SEND_BOUND" in script and "payload.success === true" in script and "try {" in script
    assert len(script.splitlines()) < 300 and "shown_ms" in script
