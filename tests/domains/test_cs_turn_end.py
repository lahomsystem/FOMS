"""말 끝남 판단(:mod:`foms.services.cs_agent.turn_end`) — 빠른 길 기다림을 판단으로 줄이고 늘림 · 기록만 · 끔 · 실패 · 가림 · 돈.

사장님 요청(11-11): 끝난 말은 바로, 이어질 말은 더 기다렸다 초안. 처음 값은 끔(예전 15초 그대로)이다.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from db import db_session
from foms.services.cs_agent import brain, realtime, turn_end
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_spend import SPEND_KEY
from foms.services.cs_agent.turn_end_settings import FAST_FIELD, MODE_FIELD, SLOW_FIELD
from models import SystemSetting
from tests.domains.test_cs_brain import PHONE  # 전화 꼴은 실행 중에 잇는다(공개 저장소 — R6-19)
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_realtime import Talk, rows, sec, switch_on, tick, turn_count
from tests.support.cs_image_support import file_item
from tests.support.cs_agent_fakes import FakeClock, api_message, keys, make_reader  # noqa: F401 — keys 는 fixture

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeJudge:
    """판단 대역 — 정한 답을 내고 부른 (상담, 글)을 남긴다."""

    def __init__(self, verdict=turn_end.DONE, error=None):
        self.verdict, self.error, self.calls = verdict, error, []

    def __call__(self, session, chat_id, message_id, **_kwargs):
        self.calls.append((chat_id, message_id))
        if self.error:
            raise self.error
        return self.verdict


class FakeClient:
    """Anthropic 클라이언트 대역(``with_options(...).messages.create``) — 받은 인자 · 옵션을 남긴다."""

    def __init__(self, text='{"done": true}', stop="end_turn", error=None):
        self.text, self.stop, self.error = text, stop, error
        self.calls, self.options = [], None
        self.messages = self

    def with_options(self, **options):
        self.options = options
        return self

    def create(self, **params):
        self.calls.append(params)
        if self.error is not None:
            raise self.error
        usage = SimpleNamespace(input_tokens=300, output_tokens=8, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0, iterations=None)
        return SimpleNamespace(stop_reason=self.stop, model=turn_end.MODEL, usage=usage,
                               content=[SimpleNamespace(type="text", text=self.text)])


def _on(mode="on", **extra):
    switch_on(**{MODE_FIELD: mode, **extra})


# ── 빠른 길에 붙은 모양 ────────────────────────────────────────────────────
def test_off_by_default_keeps_the_old_quiet_wait_and_never_asks(channel):
    switch_on()
    judge, memory, talk = FakeJudge(), realtime.TickMemory(), Talk(channel)
    talk.say("m-1", sec(0))
    assert tick(channel, sec(5), memory, turn_end=judge).picked == 0
    assert tick(channel, sec(15), memory, turn_end=judge).picked == 1
    assert judge.calls == [] and st.DEFAULTS[MODE_FIELD] == "off"


def test_a_finished_message_is_drafted_after_the_short_wait(channel):
    _on()
    judge, memory, talk = FakeJudge(turn_end.DONE), realtime.TickMemory(), Talk(channel)
    talk.say("m-1", sec(0))
    assert tick(channel, sec(3), memory, turn_end=judge).pending == 1  # 4초 전 — 아직 묻지 않는다
    assert judge.calls == []
    result = tick(channel, sec(5), memory, turn_end=judge)
    assert (result.picked, judge.calls, rows()[0].state) == (1, [("uc-1", "m-1")], "stored")


def test_an_unfinished_message_waits_longer_and_is_asked_once(channel):
    _on()
    judge, memory, talk = FakeJudge(turn_end.MORE), realtime.TickMemory(), Talk(channel)
    talk.say("m-1", sec(0), text="안녕하세요 문의드릴게요")
    for second in (5, 16, 39):  # 예전이면 15초에 집었다
        assert tick(channel, sec(second), memory, turn_end=judge).pending == 1
    assert tick(channel, sec(40), memory, turn_end=judge).picked == 1
    assert judge.calls == [("uc-1", "m-1")]


def test_the_max_wait_still_caps_an_unfinished_customer(channel):
    _on(**{SLOW_FIELD: 120})
    judge, memory, talk = FakeJudge(turn_end.MORE), realtime.TickMemory(), Talk(channel)
    talk.say("m-1", sec(0))
    talk.say("m-2", sec(30))
    assert tick(channel, sec(35), memory, turn_end=judge).pending == 1
    assert tick(channel, sec(60), memory, turn_end=judge).picked == 1  # 첫 미답 글부터 최대 기다림(60초)


def test_shadow_mode_asks_but_keeps_the_old_wait(channel):
    _on("shadow")
    judge, memory, talk = FakeJudge(turn_end.DONE), realtime.TickMemory(), Talk(channel)
    talk.say("m-1", sec(0))
    assert tick(channel, sec(5), memory, turn_end=judge).pending == 1
    assert tick(channel, sec(15), memory, turn_end=judge).picked == 1
    assert judge.calls == [("uc-1", "m-1")]


def test_a_new_customer_message_is_asked_again(channel):
    _on()
    judge, memory, talk = FakeJudge(turn_end.MORE), realtime.TickMemory(), Talk(channel)
    talk.say("m-1", sec(0), text="사진 보낼게요")
    tick(channel, sec(5), memory, turn_end=judge)
    talk.say("m-2", sec(10))
    judge.verdict = turn_end.DONE
    assert tick(channel, sec(15), memory, turn_end=judge).picked == 1
    assert judge.calls == [("uc-1", "m-1"), ("uc-1", "m-2")] and rows()[0].last_user_message_id == "m-2"


def test_a_broken_judge_falls_back_to_the_old_wait_and_is_not_asked_again(channel):
    _on()
    judge, memory, talk = FakeJudge(error=RuntimeError("합성")), realtime.TickMemory(), Talk(channel)
    talk.say("m-1", sec(0))
    assert tick(channel, sec(5), memory, turn_end=judge).pending == 1
    assert tick(channel, sec(10), memory, turn_end=judge).pending == 1
    assert tick(channel, sec(15), memory, turn_end=judge).picked == 1
    assert judge.calls == [("uc-1", "m-1")] and memory.turn_end[("uc-1", "m-1")] == turn_end.FAILED


def test_at_most_a_few_chats_are_asked_per_tick(channel):
    _on()
    judge, memory = FakeJudge(turn_end.MORE), realtime.TickMemory()
    for n in range(1, 6):
        Talk(channel, chat=f"uc-{n}").say(f"m-{n}", sec(0))
    tick(channel, sec(5), memory, turn_end=judge)
    assert len(judge.calls) == turn_end.MAX_PER_TICK and turn_count() == 0


@pytest.mark.parametrize(("mode", "verdict", "seconds"), [
    ("off", turn_end.DONE, 15), ("shadow", turn_end.DONE, 15), ("on", None, 15), ("on", turn_end.FAILED, 15),
    ("on", turn_end.DONE, 4), ("on", turn_end.MORE, 40),
])
def test_quiet_seconds(mode, verdict, seconds):
    cfg = {**st.DEFAULTS, MODE_FIELD: mode}
    assert turn_end.quiet_seconds(SimpleNamespace(get=cfg.get), verdict) == seconds


# ── 한 번 묻기(작은 모델) ──────────────────────────────────────────────────
def _ask(channel, client, *, message_id="m-2", now=None):
    channel.media.setdefault("uc-1", "native")
    cfg = st.read_settings(db_session, log=False)
    return turn_end.judge_one(db_session, "uc-1", message_id, reader=make_reader(channel, FakeClock()), cfg=cfg,
                              now=now or sec(6), client=client)


def _talk(channel, *texts):
    channel.messages["uc-1"] = [api_message("s-1", sec(-120), "manager", "네 고객님 어떤 제품 보시나요?"),
                                *(api_message(f"m-{i}", sec(i), "user", t) for i, t in enumerate(texts, start=1))]


def test_judge_one_sends_masked_recent_lines_to_haiku_and_records_ids_only(channel):
    _on("shadow")
    _talk(channel, "선반 깊이 문의요", f"연락은 {PHONE} 로 주세요")
    client = FakeClient()
    assert _ask(channel, client) == turn_end.DONE
    (params,) = client.calls
    content = params["messages"][0]["content"]
    assert params["model"] == "claude-haiku-5-5" and params["thinking"] == {"type": "disabled"}
    assert params["output_config"]["effort"] == "low" and params["output_config"]["format"]["schema"] == turn_end.SCHEMA
    assert PHONE not in content and PHONE.replace("-", "") not in content and "[전화]" in content and "[직원 · 2분 전]" in content and "[손님 · 4초 전]" in content
    assert client.options == {"timeout": turn_end.TIMEOUT_SECONDS, "max_retries": 0}
    db_session.expire_all()
    (entry,) = db_session.get(SystemSetting, turn_end.LOG_KEY).setting_value["rows"]
    assert set(entry) == {"chat", "message", "verdict", "mode", "ms", "at", "n", "len", "end", "file", "staff", "quiet"}
    assert (entry["chat"], entry["message"], entry["verdict"], entry["mode"]) == ("uc-1", "m-2", "done", "shadow")
    assert {k: entry[k] for k in ("n", "end", "file", "staff", "quiet")} == {
        "n": 2, "end": "yo", "file": False, "staff": True, "quiet": 4}  # 글 모양은 숫자 · 코드만(사장님 11-12)
    assert entry["len"] == len(f"연락은 {PHONE} 로 주세요") and PHONE not in json.dumps(entry, ensure_ascii=False)
    assert "선반" not in json.dumps(entry, ensure_ascii=False)
    spend = db_session.get(SystemSetting, SPEND_KEY).setting_value
    assert spend["calls"] == 1 and float(spend["reserved"]) == 0


@pytest.mark.parametrize("text, code", [
    ("", "empty"), ("  ", "empty"), ("배송 언제 와요?", "question"), ("그런데...", "trail"), ("그리고…", "trail"),
    ("음,", "comma"), ("문의드립니다.", "period"), ("감사해요!", "exclaim"), ("네~", "exclaim"), ("ㅠㅠ", "emoticon"),
    ("부탁드려요", "yo"), ("알겠습니다", "da"), ("화이트로 할게", "hangul"), ("가로 2400", "digit"), ("ok", "other"),
])
def test_end_codes_are_fixed_words_only(text, code):
    assert turn_end.end_code(text) == code and code in turn_end.END_CODES


def test_the_shape_marks_a_file_on_the_last_message_without_its_name(channel):
    _on()
    _talk(channel, "선반 문의요")
    item = file_item("pub-file/uc-1/0.jpg", b"x" * 10)
    channel.messages["uc-1"].append(api_message("m-2", sec(2), "user", "이렇게요", files=[item]))
    assert _ask(channel, FakeClient()) == turn_end.DONE
    db_session.expire_all()
    (entry,) = db_session.get(SystemSetting, turn_end.LOG_KEY).setting_value["rows"]
    assert (entry["n"], entry["file"], entry["end"], entry["len"]) == (2, True, "yo", 4)
    assert "synthetic" not in json.dumps(entry) and "pub-file" not in json.dumps(entry)


def test_not_done_is_more(channel):
    _on()
    _talk(channel, "안녕하세요", "사진 보낼게요")
    assert _ask(channel, FakeClient('{"done": false}')) == turn_end.MORE


def test_a_newer_message_is_not_asked(channel):
    _on()
    _talk(channel, "선반 문의요", "그리고", "깊이도요")
    client = FakeClient()
    assert _ask(channel, client, message_id="m-2") is None and client.calls == []


def test_a_name_left_after_masking_is_never_sent(channel):
    _on()
    _talk(channel, "선반 문의요", "김가나, 32평 견적 부탁드려요")
    client = FakeClient()
    assert _ask(channel, client) is None and client.calls == []


@pytest.mark.parametrize("client", [
    FakeClient(stop="max_tokens"), FakeClient(text="끝"), FakeClient(text='{"done": "yes"}'),
    FakeClient(error=anthropic.APIConnectionError(request=_REQUEST)),
])
def test_a_bad_answer_or_error_gives_no_verdict_and_settles_the_reservation(channel, client):
    _on()
    _talk(channel, "선반 문의요", "깊이 알려 주세요")
    assert _ask(channel, client) is None
    db_session.expire_all()
    assert float(db_session.get(SystemSetting, SPEND_KEY).setting_value["reserved"]) == 0
    assert db_session.get(SystemSetting, turn_end.LOG_KEY) is None


def test_without_a_daily_cap_nothing_is_sent(channel, monkeypatch):
    _on()
    monkeypatch.delenv(brain.DAILY_CAP_ENV)
    _talk(channel, "선반 문의요", "깊이 알려 주세요")
    client = FakeClient()
    assert _ask(channel, client) is None and client.calls == []


def test_the_record_keeps_only_the_latest_rows(channel, monkeypatch):
    _on()
    monkeypatch.setattr(turn_end, "LOG_LIMIT", 3)
    _talk(channel, "선반 문의요", "깊이 알려 주세요")
    for _ in range(5):
        _ask(channel, FakeClient())
    db_session.expire_all()
    assert len(db_session.get(SystemSetting, turn_end.LOG_KEY).setting_value["rows"]) == 3


def test_fields_are_in_the_panel_with_safe_defaults():
    names = {f.name for f in st.FIELDS}
    assert {MODE_FIELD, FAST_FIELD, SLOW_FIELD} <= names
    assert (st.DEFAULTS[MODE_FIELD], st.DEFAULTS[FAST_FIELD], st.DEFAULTS[SLOW_FIELD]) == ("off", 4, 40)
