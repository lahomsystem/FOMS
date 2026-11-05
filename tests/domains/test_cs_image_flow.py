"""그림 읽기 이어짐(설계서 17.11 (d) · (h) 4 ~ 8) — 앞 단계 '되묻지 않기'(ec3872e26)에 끼우기 · 저장 0 · 상한 · 같은 그림 ·
선점 · 미리 읽기 · 마이그레이션.

합성 상담(가린 꼴 글) · 합성 도면(Pillow) · 가짜 채널톡(파일 서명 주소 · 내려받기) · 가짜 모델(구조화 출력)만 쓴다 —
네트워크 · 금액 숫자 · 손님 그림 없음. 금액이 든 계산 줄은 서버 계산이 그 자리에서 낸 값과 견준다.
"""

from __future__ import annotations

import datetime
import functools
import importlib.util
import logging
import tempfile
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, select

from db import db_session
from foms.services.cs_agent import image_prep, image_read, image_store, quote_calc as qc
from foms.services.cs_agent import quote_record as qrec
from foms.services.cs_agent import realtime, settings as st
from foms.services.cs_agent.drafting_pass import DraftPass
from foms.services.cs_agent.drafting_read import MEMO_IMAGE_HEAD, MEMO_NOTE_HEAD
from foms.services.cs_agent.image_files import FileRef
from foms.services.cs_agent.image_preread import PrereadMemory, run_preread_tick
from foms.services.cs_agent.image_step import DRAWING_HEAD
from foms.services.cs_agent.turns import LEGACY_CLAIM_AFTER
from models import CsAgentImageRead
from tests.domains.test_cs_drafting import (  # noqa: F401 — channel 은 fixture
    FakeBrain, FakePoster, channel, customer, result, run, set_switch, turn,
)
from tests.domains.test_cs_quote_drawing import DRAWING_TEXT, _width_asks
from tests.support.cs_agent_fakes import FakeAnthropic, FakeClock, at, keys, make_reader  # noqa: F401
from tests.support.cs_image_support import (
    FILE_HOST, FakeDownload, FileStore, ImageChannel, answer, encoded, file_item, image_switch, plan_image, room, wall,
)
from tests.support.cs_quote_support import FakeQuoter, ask, catalog, confirm_prices, space

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "csagent_06_image_reads.py"
GOOD = answer(room("안방", wall(2700, 3000), target="named"))
DRAWING_DRAFT = "고객님, 보내 주신 도면을 보고 크기 확인해 견적 안내드리겠습니다."
KEY = "pub-file/synthetic/plan-a.jpg"


@pytest.fixture
def chan(channel):
    """그림 받기가 되는 가짜 채널톡(파일 key → 바이트)."""
    return ImageChannel(FileStore())


def drawing_chat(chan, chat="uc-1", *, keys=(KEY,), text=DRAWING_TEXT, data=None):
    """손님이 그림(들)을 먼저 보내고 견적 · 규격 모름(도면 참고) 글을 쓴 상담."""
    payload = data or encoded(plan_image())
    files = [file_item(chan.store.put(key, payload), payload) for key in keys]
    customer(chan, chat, text="", extra={"files": files}, when=at(2, 8, 40),
             more=[(f"m-{chat}-2", at(2, 8, 50), "user", text, {})])


def passing(client, chan, quote=None):
    """초안 차례 꼴 — 가짜 뽑기(가로 모름 + 도면 참고) · 가짜 그림 모델 · 가짜 내려받기."""
    quoter = FakeQuoter(quote or ask(space(width=0), unknown=("width",), size_in_attachment=True))
    return functools.partial(DraftPass, quoter=quoter, catalog_reader=lambda: catalog(), image_client=client,
                             image_transport=FakeDownload(chan.store), image_sleep=lambda _s: None)


def drafted(chan, client, *, mode="memo", draft=DRAWING_DRAFT, quote=None):
    brain_fn, poster = FakeBrain(result(draft=draft)), FakePoster()
    summary = run(chan, mode, brain_fn=brain_fn, poster=poster, pass_type=passing(client, chan, quote))
    return brain_fn, poster, summary


def note_lines(poster):
    (call,) = poster.calls
    return call.text.split(MEMO_NOTE_HEAD, 1)[1].strip().splitlines()


def image_rows():
    db_session.expire_all()
    return list(db_session.scalars(select(CsAgentImageRead).order_by(CsAgentImageRead.id)))


# ── 끔 · 직원 참고만 · 초안에 씀 ────────────────────────────────────────
def test_switch_off_calls_no_model_and_keeps_the_no_reask_step_byte_for_byte(chan):
    image_switch("off")
    drawing_chat(chan)
    client = FakeAnthropic(GOOD)
    brain_fn, poster, summary = drafted(chan, client)
    (request,) = brain_fn.requests
    assert client.params == [] and chan.store.signed == [] and image_rows() == []  # 모델 0번 · 받기 0번
    assert request.calculator_lines == (qc.DRAWING_LINE,) and note_lines(poster)[-1] == qc.DRAWING_NOTE
    assert turn().quote_lines == qrec.record_value(qrec.STATUS_DRAWING, lines=(qc.DRAWING_LINE,),
                                                   code=qc.SIZE_IN_DRAWING)  # 앞 단계(ec3872e26)와 같은 기록


def test_note_mode_reads_once_and_adds_only_a_staff_line(chan):
    image_switch("note")
    drawing_chat(chan)
    client = FakeAnthropic(GOOD)
    brain_fn, poster, summary = drafted(chan, client)
    (params,) = client.params
    assert params["model"] == "claude-sonnet-5-5" and [b["type"] for b in params["messages"][0]["content"]][:2] == [
        "text", "image"]
    (request,) = brain_fn.requests
    assert request.calculator_lines == (qc.DRAWING_LINE,) and _width_asks(request.calculator_lines) == []
    assert note_lines(poster)[-2:] == [qc.DRAWING_NOTE, f"{MEMO_IMAGE_HEAD}] 평면도 · 안방(글) · 벽 1 · 범위 "
                                       "2,400~2,700mm(벽 포함 300 뺌) · 확신 보통 — 직원 확인"]
    assert qrec.allowed_from(turn().quote_lines) == ()  # 금액 허용 0 — 직원 참고만
    (row,) = image_rows()
    assert (row.state, row.model, row.turn_id, row.input_tokens) == ("done", "claude-sonnet-5-5", turn().id, 1000)
    assert turn().input_tokens == 900 + 300 + 1000 and summary.brain_calls >= 3  # 초안 + 뽑기 + 그림 읽기 돈이 차례에


def test_draft_mode_puts_the_range_into_the_calculator(chan):
    image_switch("draft")
    confirm_prices()
    drawing_chat(chan)
    brain_fn, poster, _ = drafted(chan, FakeAnthropic(GOOD))
    (request,) = brain_fn.requests
    head, drawing_head, wording, *priced = request.calculator_lines
    assert head.startswith("라홈 견적 계산기 값") and drawing_head == DRAWING_HEAD
    assert "보내 주신 도면 기준으로 안방 자리를 2,400~2,700mm" in wording
    expected = qc.evaluate(ask(space(width=2400, width_max_mm=2700)), catalog(), (), check=_check(), now=_now())
    assert tuple(priced) == expected.lines[1:] and len(priced) == 2  # 두 끝을 지금 계산 그대로(새 계산 길 없음)
    assert qrec.allowed_from(turn().quote_lines) == tuple(priced) and turn().quote_lines["status"] == qrec.STATUS_OK
    assert note_lines(poster)[-1].endswith("— 초안에 씀")


def _check():
    from foms.services.cs_agent.quote_check import observe
    return observe(db_session, catalog(), now=_now())


def _now():
    return at(2, 9)


@pytest.mark.parametrize("bad", [
    answer(room("안방", wall(2700, 3000)), confidence="low"),
    answer(room("안방", wall(2700, 3000)), reasons=("wall_unclear",)),
    answer(room("드레스룸", wall(2700)), room("거실", wall(2900))),  # 공간 짝 실패
    answer(room("안방", wall(2700, 3000)), personal=("face",)),
])
def test_unusable_reads_fall_back_to_the_no_reask_step_with_a_staff_line(chan, bad):
    image_switch("draft")
    confirm_prices()
    drawing_chat(chan)
    brain_fn, poster, _ = drafted(chan, FakeAnthropic(bad))
    (request,) = brain_fn.requests
    assert request.calculator_lines == (qc.DRAWING_LINE,) and _width_asks(request.calculator_lines) == []
    assert note_lines(poster)[-1].startswith(MEMO_IMAGE_HEAD) and note_lines(poster)[-1].endswith("직원 확인")
    assert qrec.allowed_from(turn().quote_lines) == ()


def test_a_model_failure_or_broken_answer_is_the_old_behaviour(chan):
    image_switch("draft")
    drawing_chat(chan)
    brain_fn, poster, _ = drafted(chan, FakeAnthropic({"images": "broken"}))
    (request,) = brain_fn.requests
    assert request.calculator_lines == (qc.DRAWING_LINE,)
    assert note_lines(poster)[-1] == f"{MEMO_IMAGE_HEAD}] 읽지 못함(bad_response) — 직원 확인"
    assert [(r.state, r.skip_code) for r in image_rows()] == [("failed", "bad_response")]


def test_a_face_found_by_the_server_filter_is_never_sent(chan, monkeypatch):
    image_switch("draft")
    drawing_chat(chan)
    monkeypatch.setattr(image_prep, "count_faces", lambda _pixels: 1)
    client = FakeAnthropic(GOOD)
    brain_fn, poster, _ = drafted(chan, client)
    assert client.params == []  # 모델 0번
    assert note_lines(poster)[-1] == f"{MEMO_IMAGE_HEAD}] 읽지 못함(skipped_face) — 직원 확인"
    assert [(r.state, r.skip_code, r.model) for r in image_rows()] == [("skipped", "skipped_face", None)]


def test_haud_goes_to_a_person_before_any_image_read(chan):
    image_switch("draft")
    drawing_chat(chan)
    client = FakeAnthropic(GOOD)
    brain_fn, poster, _ = drafted(chan, client, quote=ask(space(width=0), brand="HAUD", size_in_attachment=True))
    assert client.params == [] and brain_fn.requests == [] and poster.calls == []  # 하우드는 사람에게(그림 읽기 전)
    assert (turn().state, turn().handoff_reason) == ("skipped", qc.HUMAN_BRAND)


def test_the_daily_money_cap_stops_the_image_call_before_sending(chan, monkeypatch):
    from foms.services.cs_agent import brain

    monkeypatch.setenv(brain.DAILY_CAP_ENV, "0.2")  # 초안 한 번은 되지만 그림 읽기 최악값 예약은 상한을 넘는다
    image_switch("draft", draft_max_tokens=2000, image_max_tokens=16000)
    drawing_chat(chan)
    client = FakeAnthropic(GOOD)
    brain_fn, poster, _ = drafted(chan, client)
    assert client.params == [] and brain_fn.requests[0].calculator_lines == (qc.DRAWING_LINE,)
    assert note_lines(poster)[-1] == f"{MEMO_IMAGE_HEAD}] 읽지 못함(daily_cap_reached) — 직원 확인"


# ── 저장 0(D89) ──────────────────────────────────────────────────────────
def test_no_bytes_keys_or_urls_reach_temp_files_rows_or_logs(chan, monkeypatch, caplog):
    for name in ("mkstemp", "NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile", "mkdtemp"):
        monkeypatch.setattr(tempfile, name, lambda *a, **k: pytest.fail("임시 파일을 만들었다"))
    caplog.set_level(logging.DEBUG, logger="foms.services.cs_agent")
    image_switch("note")
    drawing_chat(chan)
    client = FakeAnthropic(GOOD)
    drafted(chan, client)
    data = client.params[0]["messages"][0]["content"][1]["source"]["data"]
    (row,) = image_rows()
    stored = repr({column.name: getattr(row, column.name) for column in CsAgentImageRead.__table__.columns})
    for secret in (KEY, FILE_HOST, data[:40], "synthetic.bin"):
        assert secret not in stored and secret not in caplog.text
    assert len(row.sha256) == 64 and row.result["batch"] == [row.sha256]


# ── 고르기 · 상한 · 같은 그림 ────────────────────────────────────────────
def test_only_four_newest_customer_files_per_turn_and_never_staff_files(chan):
    image_switch("note", image_per_turn=4)
    keys = [f"pub-file/synthetic/{i}.jpg" for i in range(5)]
    drawing_chat(chan, keys=keys)
    staff = file_item(chan.store.put("staff/calc.png", b"x"), b"x", content_type="image/png")
    chan.messages["uc-1"].append({"id": "m-memo", "personType": "manager", "createdAt": "2026-11-01T23:45:00.000Z",
                                  "plainText": "", "files": [staff], "options": ["private"]})
    drafted(chan, FakeAnthropic(GOOD))
    assert sorted(chan.store.signed) == sorted(keys[:4]) and "staff/calc.png" not in chan.store.signed


def _sent_rows(count, chat="uc-other"):
    for index in range(count):
        db_session.add(CsAgentImageRead(brand="LAHOM", chat_id=chat, message_id=f"m-{index}", file_index=0,
                                        state="done", model="claude-sonnet-5-5", read_at=datetime.datetime(2026, 11, 2, 0, 5)))
    db_session.commit()


@pytest.mark.parametrize("settings,sent,chat", [({"image_per_day": 10}, 10, "uc-other"),
                                                ({"image_per_chat_day": 1}, 1, "uc-1")])
def test_daily_caps_skip_the_read_without_calling_the_model(chan, settings, sent, chat):
    image_switch("note", **settings)
    _sent_rows(sent, chat=chat)
    drawing_chat(chan)
    client = FakeAnthropic(GOOD)
    _, poster, _ = drafted(chan, client)
    assert client.params == [] and note_lines(poster)[-1] == f"{MEMO_IMAGE_HEAD}] 읽지 못함(skipped_cap) — 직원 확인"


def test_the_same_image_sent_again_reuses_the_earlier_result(chan, keys):
    image_switch("note")
    payload = encoded(plan_image())
    drawing_chat(chan, data=payload)
    client = FakeAnthropic(GOOD)
    reader = make_reader(chan, FakeClock())
    refs_a = [FileRef("m-uc-1", 0, "image/jpeg", len(payload), 1600, 1200, key=KEY)]
    common = dict(reader=reader, brand="LAHOM", chat_id="uc-1", turns=[("user", DRAWING_TEXT)],
                  cfg=st.read_settings(db_session), now=at(2, 9), deadline_s=30, still_on=lambda: True,
                  client=client, transport=FakeDownload(chan.store), sleep=lambda _s: None)
    first = image_read.read_batch(db_session, refs=refs_a, owner="test:a", **common)
    again = FileRef("m-uc-1-again", 0, "image/jpeg", len(payload), 1600, 1200, key=chan.store.put("pub-file/again", payload))
    second = image_read.read_batch(db_session, refs=[again], owner="test:b", **common)
    assert len(client.params) == 1 and second.reused and second.read == first.read  # 같은 바이트 → 앞 결과
    assert [r.model for r in image_rows()] == ["claude-sonnet-5-5", None]  # 다시 쓴 줄은 보낸 장수에 안 든다


# ── 시간 · 선점 ──────────────────────────────────────────────────────────
def test_claim_ttl_adds_the_inline_read_worst_time_only_when_it_is_on():
    def cfg(**values):
        return st.PanelSettings({**st.DEFAULTS, "quote_calc_enabled": True, **values})

    assert realtime.claim_ttl(cfg(image_read_mode="off")) == datetime.timedelta(seconds=45 + 20 + 45)
    assert realtime.claim_ttl(cfg(image_read_mode="note")) == datetime.timedelta(seconds=45 + 20 + 35 + 45)  # 145초
    assert realtime.claim_ttl(cfg(image_read_mode="draft", quote_calc_enabled=False)) == datetime.timedelta(seconds=90)
    assert LEGACY_CLAIM_AFTER > realtime.claim_ttl(cfg(image_read_mode="draft", image_inline_timeout_s=60))


def test_a_read_in_progress_elsewhere_is_waited_for_then_reused_or_given_up(chan, keys):
    image_switch("note")
    drawing_chat(chan)
    ref = FileRef("m-uc-1", 0, "image/jpeg", 10, 1600, 1200, key=KEY)
    (row,) = image_store.ensure_rows(db_session, "LAHOM", "uc-1", [ref], at(2, 9))
    row.state, row.claim_owner = "reading", "image:other:1"
    row.claim_expires_at = datetime.datetime(2026, 11, 2, 1, 0)  # 미리 읽기 길이 쥐고 있다(만료 전)
    db_session.commit()
    clock, client = FakeClock(), FakeAnthropic(GOOD)
    common = dict(reader=make_reader(chan, clock), brand="LAHOM", chat_id="uc-1", refs=[ref],
                  turns=[("user", DRAWING_TEXT)], cfg=st.read_settings(db_session), now=at(2, 9), owner="realtime:x",
                  deadline_s=5, still_on=lambda: True, client=client, transport=FakeDownload(chan.store), clock=clock)
    assert image_read.read_batch(db_session, sleep=clock.sleep, **common) is None  # 상한을 넘기면 그림 없이
    assert client.params == [] and chan.store.signed == []  # 두 길이 같은 그림을 두 번 읽지 않는다

    def finished_elsewhere(seconds):
        clock.sleep(seconds)
        other = db_session.get(CsAgentImageRead, row.id)
        other.state, other.sha256, other.claim_owner = "done", "a" * 64, None
        other.result = {**GOOD, "batch": ["a" * 64], "rules_version": image_read.RULES_VERSION,
                        "ranges": [{"room": "안방", "target": "named", "low": 2400, "high": 2700, "walls": 1,
                                    "deducted": [300]}]}
        db_session.commit()

    got = image_read.read_batch(db_session, sleep=finished_elsewhere, **common)
    assert got.reused and got.read.spaces[0].room == "안방" and client.params == []  # 미리 읽은 결과를 기다려 쓴다


# ── 미리 읽기 길 ─────────────────────────────────────────────────────────
def preread(chan, client, now=at(2, 9)):
    return run_preread_tick(db_session, memory=PrereadMemory(), reader=make_reader(chan, FakeClock()), now=now,
                            client=client, transport=FakeDownload(chan.store), sleep=lambda _s: None)


def test_preread_reads_quote_chats_and_the_turn_then_reuses_it(chan):
    image_switch("note")
    set_switch({"draft": "memo"})
    drawing_chat(chan)
    client = FakeAnthropic(GOOD)
    got = preread(chan, client)
    assert (got.outcome, got.read) == ("ok", 1) and len(client.params) == 1
    assert [r.state for r in image_rows()] == ["done"]
    _, poster, _ = drafted(chan, client)
    assert len(client.params) == 1  # 초안 차례는 미리 읽은 결과를 쓴다 — 두 번 읽지 않는다
    assert note_lines(poster)[-1].startswith(f"{MEMO_IMAGE_HEAD}] 평면도 · 안방")
    assert preread(chan, client).chats == 0  # 줄이 있는 그림은 다시 보지 않는다


def test_preread_no_longer_needs_quote_calc_and_reads_non_quote_photos_too(chan):
    image_switch("note", quote_calc_enabled=False)  # 17.11.1 의 1 — 견적 계산 넣기 · 견적 말 조건을 뗐다
    set_switch({"draft": "memo"})
    payload = encoded(plan_image())
    customer(chan, "uc-2", text="배송 문의드려요", when=at(2, 8, 0),
             more=[("m-uc-2-a", at(2, 8, 10), "manager", "합성 직원 답", {}),
                   ("m-uc-2-b", at(2, 8, 40), "user", "",
                    {"files": [file_item(chan.store.put("pub-file/defect.jpg", payload), payload)]})])
    client = FakeAnthropic(GOOD)
    got = preread(chan, client)
    assert (got.read, got.not_preread, len(client.params)) == (1, 0, 1)  # 하자 · 배송 사진도 질문과 같이 본다
    assert [(r.state, r.skip_code) for r in image_rows()] == [("done", None)]


def test_preread_is_idle_when_switched_off(chan):
    image_switch("off")
    set_switch({"draft": "memo"})
    drawing_chat(chan)
    assert preread(chan, FakeAnthropic(GOOD)).outcome == "idle"
    image_switch("note")
    set_switch({"draft": "off"})
    assert preread(chan, FakeAnthropic(GOOD)).outcome == "idle"  # 초안 끔이면 그림 읽기도 멈춘다


# ── 배선(WORKER 자식) ────────────────────────────────────────────────────
def test_the_preread_child_only_starts_with_its_own_env_and_has_a_heartbeat_kind():
    from foms.services.sidefx_worker import WORKER_KIND_CS_IMAGE_READ, WORKER_KIND_SPECS
    from tests.support.worker_jobs import jobs

    assert "cs_image_read" not in [j.name for j in jobs({"FOMS_CS_LOOP_ENABLED": "1"})]  # 처음 끔 — 메모리 그대로
    (child,) = [j for j in jobs({"FOMS_CS_IMAGE_READ_ENABLED": "1"}) if j.name == "cs_image_read"]
    assert child.argv[1:] == ("scripts/maintenance/run_cs_image_read.py", "--loop", "--json") and child.deferred
    spec = importlib.util.spec_from_file_location("run_cs_image_read_ut",
                                                  ROOT / "scripts" / "maintenance" / "run_cs_image_read.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.HEARTBEAT_WORKER_KIND == WORKER_KIND_CS_IMAGE_READ and WORKER_KIND_CS_IMAGE_READ in WORKER_KIND_SPECS


# ── 마이그레이션 ─────────────────────────────────────────────────────────
def test_csagent_06_chains_onto_the_head_and_matches_the_model():
    spec = importlib.util.spec_from_file_location("csagent_06_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == ("csagent_06", "notice_00")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    assert module.STATES == image_store.STATES
    table = CsAgentImageRead.__table__
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks[module.STATE_CHECK] == module.in_check("state", module.STATES)
    assert [c.name for c in table.columns] == ["id", *(name for name, *_ in module.COLUMNS)]
    for name, type_, nullable, _default in module.COLUMNS:
        column = table.c[name]
        assert column.nullable is nullable, name
        assert getattr(column.type, "length", None) == getattr(type_, "length", None), name
    indexes = {i.name: tuple(c.name for c in i.columns) for i in table.indexes}
    assert all(indexes[name] == columns for name, columns in module.INDEXES)
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1 and "csagent_06" in {rev.revision for rev in script.walk_revisions("base", heads[0])}
