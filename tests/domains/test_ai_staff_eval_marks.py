"""'AI 시험' 사장님 채점(설계서 2026-11-23-brain-learning-upgrade 4.1 · 7절 '채점') — 표 · 남기기 · 90일 비우기 · 하루 10개 ·
관리자만 · 마이그레이션 ``aistaff_00``.

완료 기준:
- 시험이 '지난 상담' 차례마다(모델까지 간 것만) 한 줄을 남긴다 — 초안은 가린 글(가림 뒤 검사를 지난 글)이고, 넘김은 빈 글 · 넘긴
  까닭. 위험 문장 · 가림 검사 · 모델 못 받음 차례는 남기지 않는다. 결과 줄에는 여전히 글이 없다.
- 시험을 시작하면 90일 지난 초안을 빈 글로 비운다(사장님 답은 남는다).
- 채점할 차례: ADMIN 만 · 하루 10개에서 오늘(KST) 한 수를 뺀 만큼 · 새 시험부터 통과 · 실패 · 넘김을 번갈아 · 채점 코드는 싣지
  않는다 · 판정 못 받음 · 이미 채점함 · 90일 지남 · 차례 줄이 없는 줄은 뺀다.
- 채점 저장: 서버가 모두 다시 본다(꼴 · 갈래에 맞는 답 · '안 돼요'는 까닭 하나) · 이미 채점함 409 · 오늘 다 함 409 · 감사 줄
  (번호 · 코드만) · CSRF 가드 · 길 목록 ``ADMIN_OPS`` · ADMIN 아니면 404.
- 마이그레이션: 사슬(csagent_08 뒤) · 머리 하나 · 모델과 같은 칸 · 제약 · 색인 · 빈 SQLite 올림 · 내림.
합성 차례 · 합성 지식 · 가짜 두뇌 · 가짜 큐만(바깥 호출 없음). 손님 글 · 직원 이름 · 금액 없음.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import logging
import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from itsdangerous import URLSafeSerializer
from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, inspect, select
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError

from db import db_session
from foms.persistence.graft import models as graft_models
from foms.persistence.graft.models import AiStaffEvalMark
from foms.services.ai_staff import evals, evals_marks, evals_run
from foms.services.cs_agent.brain_spend import BrainUnavailable
from foms.services.cs_agent.masking import MaskLeak
from foms.services.datetime_kst import now_utc_naive
from foms.services.graft_flags import FLAGS
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from models import CsAgentTurn, SecurityLog, SystemSetting
from tests.domains.test_ai_staff_evals import (  # noqa: F401 — world 는 fixture
    ANSWERS, RAW, STAFF, FakeClient, _run, _settings, _turn, _world_turns, world,
)
from tests.support.brain_screen_support import people

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "aistaff_00_eval_marks.py"
BASE = "/api/ai-staff/evals/marks"
#: 화면에 가면 안 되는 채점 코드(갈래 ``kind`` 의 'handoff' 는 넘김 단추를 고르는 값이라 빼고 — 옳은 넘김 분류는 숨긴다).
CODES = ("copied", "pass", "fail_conflict", "fail_promise", "fail_unanswered", "judge_unknown", "right_handoff",
         "refused", "number_not_allowed")


def _rows():
    db_session.expire_all()
    return list(db_session.scalars(select(AiStaffEvalMark).order_by(AiStaffEvalMark.id)))


# ── 남기기 ───────────────────────────────────────────────────────────────
def test_a_run_keeps_one_masked_row_per_past_turn_that_reached_the_model(world, monkeypatch, caplog):
    ids = _world_turns()
    monkeypatch.setitem(ANSWERS, "합성 질문 전화", ("합성 안내 010-0000-0000 로 연락 주세요", ["hours-day"], False))
    phone = _turn(9, "합성 질문 전화", held_out=True, reply="합성 직원 답 아홉입니다")
    down = _turn(10, "합성 질문 못받음", held_out=True, reply="합성 직원 답 열입니다")
    leak = _turn(11, "합성 질문 가림", held_out=True, reply="합성 직원 답 열하나입니다")
    real = evals_run._draft

    def drafted(run, case, knowledge, left):
        if "못받음" in case.question:
            raise BrainUnavailable("timeout")
        if "가림" in case.question:
            raise MaskLeak({"전화": 1})
        return real(run, case, knowledge, left)

    monkeypatch.setattr(evals_run, "_draft", drafted)
    _settings(past=10, risk=3)
    with caplog.at_level(logging.INFO):
        assert _run(FakeClient())["status"] == evals.DONE
    rows = {row.turn_id: row for row in _rows()}
    assert set(rows) == {ids["same"], ids["diff"], ids["hand"], phone}  # 위험 문장 · 모델 못 받음 · 가림 검사는 없다
    assert {row.run_id for row in rows.values()} == {1} and {row.brand for row in rows.values()} == {"LAHOM"}
    assert (rows[ids["same"]].draft, rows[ids["same"]].judge_code) == (STAFF, "copied")
    assert (rows[ids["diff"]].judge_code, rows[ids["diff"]].handoff_reason) == ("fail_conflict", None)
    assert (rows[ids["hand"]].draft, rows[ids["hand"]].judge_code, rows[ids["hand"]].handoff_reason) == (
        "", "handoff", "unsure")
    assert rows[phone].draft == "합성 안내 [전화] 로 연락 주세요"  # 가린 글만 — 원래 번호는 없다
    assert rows[phone].judge_code == "phone_number"  # 보내기 전 검사가 막은 초안도 채점할 수 있다
    assert all(row.owner_answer is None and row.graded_at is None for row in rows.values())
    assert not any(RAW in row.draft for row in rows.values())
    stored = json.dumps(db_session.get(SystemSetting, evals.RESULTS_KEY).setting_value, ensure_ascii=False)
    for text in (STAFF, "합성 안내", "[전화]"):
        assert text not in stored and text not in caplog.text, text
    assert {down, leak}.isdisjoint(rows)


def test_a_draft_still_failing_the_mask_check_is_not_kept(world, monkeypatch, caplog):
    _turn(1, "합성 질문 다름", held_out=True, reply="합성 직원 답 둘입니다")
    _settings(past=1, risk=0)

    def leaks(_text):
        raise MaskLeak({"이름꼴": 1})

    monkeypatch.setattr(evals_marks, "require_masked", leaks)
    with caplog.at_level(logging.INFO):
        assert _run(FakeClient())["status"] == evals.DONE
    assert _rows() == [] and "다른 안내" not in caplog.text
    assert "채점 줄을 남기지 않음" in caplog.text


def test_drafts_older_than_ninety_days_are_blanked_when_a_run_starts(world):
    now = now_utc_naive()
    db_session.add_all([
        AiStaffEvalMark(run_id=1, turn_id=1, brand="LAHOM", draft="합성 옛 초안", judge_code="pass", owner_answer="ok",
                        graded_by=world.admin_id, graded_at=now - datetime.timedelta(days=91),
                        created_at=now - datetime.timedelta(days=91)),
        AiStaffEvalMark(run_id=1, turn_id=2, brand="LAHOM", draft="합성 덜 옛 초안", judge_code="pass",
                        created_at=now - datetime.timedelta(days=89))])
    db_session.commit()
    _settings(past=0, risk=1)
    assert _run(FakeClient())["status"] == evals.DONE
    old, recent = _rows()
    assert (old.draft, old.owner_answer, old.judge_code) == ("", "ok", "pass")  # 사장님 답 · 코드는 남는다
    assert recent.draft == "합성 덜 옛 초안"


# ── 채점할 차례 · 저장(API) ───────────────────────────────────────────────
@pytest.fixture
def who(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "1")
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", "all")
    return {name: user.id for name, user in people(db_session).items()}


def _client(app, user_id):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


def _body(resp, status):
    assert resp.status_code == status, resp.get_data(as_text=True)
    assert resp.headers["Cache-Control"] == "private, no-store"
    body = resp.get_json()
    assert set(body) == {"success", "data", "error"}
    return body


def _mark(run_id, code, n, *, days=0, reason=None, answer=None, by=None, turn=True):
    """채점 줄 하나(차례 줄도 — 가린 질문 · 직원 답). 번호를 돌려준다."""
    turn_id = 10_000 + n
    if turn:
        db_session.add(CsAgentTurn(id=turn_id, brand="LAHOM", chat_id=f"mk-chat-{n}", last_user_message_id=f"mk-m-{n}",
                                   state="posted", masked_question=f"합성 손님 글 {n}",
                                   staff_reply_masked=f"합성 직원 답 {n}", held_out=True))
    handed = code in evals_marks.HANDOFF_CODES
    row = AiStaffEvalMark(run_id=run_id, turn_id=turn_id, brand="LAHOM", draft="" if handed else f"합성 초안 {n}",
                          judge_code=code, handoff_reason=reason or ("unsure" if handed else None),
                          owner_answer=answer, graded_by=by, graded_at=now_utc_naive() if answer else None,
                          created_at=now_utc_naive() - datetime.timedelta(days=days))
    db_session.add(row)
    db_session.commit()
    return row.id


def test_the_queue_is_newest_run_first_mixed_and_blind(app, who):
    old = [_mark(1, "pass", n) for n in range(1, 5)]
    new_pass = [_mark(2, code, n) for n, code in ((11, "copied"), (12, "pass"), (13, "pass"))]
    new_fail = [_mark(2, code, n) for n, code in ((21, "fail_conflict"), (22, "number_not_allowed"),
                                                   (23, "fail_unanswered"))]
    new_hand = [_mark(2, "handoff", 31, reason="schedule"), _mark(2, "right_handoff", 32, reason="complaint")]
    skipped = [_mark(2, "judge_unknown", 41), _mark(2, "mask_leak", 42), _mark(2, "pass", 43, days=91),
               _mark(2, "pass", 44, answer="ok", by=who["admin"]), _mark(2, "pass", 45, turn=False)]
    data = _body(_client(app, who["admin"]).get(BASE), 200)["data"]
    assert (data["graded_today"], data["left"], data["limit"]) == (1, 9, 10)  # 오늘 하나 했다(대조군 44)
    expected = [new_pass[0], new_fail[0], new_hand[0], new_pass[1], new_fail[1], new_hand[1], new_pass[2], new_fail[2],
                old[0]]
    assert [item["id"] for item in data["items"]] == expected
    assert not set(skipped) & {item["id"] for item in data["items"]}
    first, hand = data["items"][0], data["items"][2]
    assert first == {"id": new_pass[0], "kind": "draft", "question": "합성 손님 글 11", "staff_reply": "합성 직원 답 11",
                     "draft": "합성 초안 11"}
    assert hand == {"id": new_hand[0], "kind": "handoff", "question": "합성 손님 글 31", "staff_reply": "합성 직원 답 31",
                    "handoff": "AI 가 사람에게 넘겼어요 — 날짜나 연락 약속이 필요하다고 봤어요"}
    sent = json.dumps(data, ensure_ascii=False)
    for code in CODES:
        assert f'"{code}"' not in sent, code  # 채점 코드는 화면에 가지 않는다
    assert data["fail_kinds"] == [{"code": "wrong_fact", "label": "사실이 틀림"}, {"code": "no_basis", "label": "없는 약속"},
                                  {"code": "tone", "label": "말투"}]


def test_every_handoff_reason_has_plain_words():
    from foms.services.cs_agent.brain_prompt import HANDOFF_REASONS

    assert set(HANDOFF_REASONS) | {"refused"} == set(evals_marks.HANDOFF_SAID)
    assert evals_marks.ANSWERS == graft_models.MARK_ANSWERS and evals_marks.FAIL_KINDS == tuple(evals_marks.FAIL_LABELS)


def test_saving_checks_everything_and_stops_at_ten_a_day(app, who):
    drafts = [_mark(1, "pass", n) for n in range(1, 12)]
    hand = _mark(1, "handoff", 50)
    client = _client(app, who["admin"])
    for payload in ({"mark": drafts[0], "answer": "handoff_right"}, {"mark": hand, "answer": "ok"},
                    {"mark": drafts[0], "answer": "bad"}, {"mark": drafts[0], "answer": "ok", "fail_kind": "tone"},
                    {"mark": drafts[0], "answer": "bad", "fail_kind": "nope"}, {"mark": True, "answer": "ok"},
                    {"mark": "1", "answer": "ok"}, {"mark": drafts[0], "answer": "ok", "judge": "pass"}, [], {}):
        body = _body(client.post(BASE, json=payload), 400)
        assert body["data"]["code"] == "EVAL_MARK_SHAPE" and body["error"] == "고른 답이 맞지 않아요 — 다시 골라 주세요."
    assert db_session.query(SecurityLog).filter(SecurityLog.action == evals_marks.AUDIT_MARK).count() == 0
    saved = _body(client.post(BASE, json={"mark": drafts[0], "answer": "bad", "fail_kind": "no_basis"}), 200)["data"]
    assert saved == {"graded_today": 1, "left": 9}
    row = db_session.get(AiStaffEvalMark, drafts[0], populate_existing=True)
    assert (row.owner_answer, row.fail_kind, row.graded_by) == ("bad", "no_basis", who["admin"]) and row.graded_at
    again = _body(client.post(BASE, json={"mark": drafts[0], "answer": "ok"}), 409)
    assert again["data"]["code"] == "EVAL_MARK_GONE" and again["error"] == "이미 채점했거나 없는 차례예요."
    assert _body(client.post(BASE, json={"mark": 999_999, "answer": "ok"}), 409)["data"]["code"] == "EVAL_MARK_GONE"
    assert _body(client.post(BASE, json={"mark": hand, "answer": "should_answer"}), 200)["data"]["left"] == 8
    log = db_session.query(SecurityLog).filter(SecurityLog.action == evals_marks.AUDIT_MARK).order_by(SecurityLog.id)
    assert [(entry.user_id, entry.target_type, entry.target_id, entry.detail) for entry in log][0] == (
        who["admin"], "ai_staff_eval_mark", drafts[0],
        {"run": 1, "turn": 10_001, "answer": "bad", "fail_kind": "no_basis"})  # 번호 · 코드만
    for mark in drafts[1:9]:
        _body(client.post(BASE, json={"mark": mark, "answer": "ok"}), 200)
    full = _body(client.post(BASE, json={"mark": drafts[9], "answer": "ok"}), 409)
    assert full["data"]["code"] == "EVAL_MARK_LIMIT" and full["error"] == "오늘 채점은 다 했어요."
    data = _body(client.get(BASE), 200)["data"]
    assert (data["items"], data["graded_today"], data["left"]) == ([], 10, 0)


def test_the_day_is_the_korean_day(world):
    """KST 11-22 23:30 · 11-23 00:30 · 11-23 08:30 에 채점 — KST 11-23 09:30 에 오늘은 둘이다(UTC 날로 세면 0 — 모두 UTC 11-22)."""
    utc = datetime.datetime(2026, 11, 22, 15, 30)  # KST 11-23 00:30
    for n, at in enumerate((utc - datetime.timedelta(hours=1), utc, utc + datetime.timedelta(hours=8)), start=1):
        db_session.add(AiStaffEvalMark(run_id=1, turn_id=n, brand="LAHOM", draft="합성 초안", judge_code="pass",
                                       owner_answer="ok", graded_by=world.admin_id, graded_at=at, created_at=at))
    db_session.commit()
    assert evals_marks.graded_today(db_session, world.admin_id, utc + datetime.timedelta(hours=9)) == 2
    aware = (utc + datetime.timedelta(hours=9)).replace(tzinfo=datetime.timezone.utc)
    assert evals_marks.graded_today(db_session, world.admin_id, aware) == 2  # 시간대 있는 값도 같다


@pytest.mark.parametrize("name,status", [("cs_mgr", 404), ("dr_mgr", 404), ("cs_staff", 404), ("viewer", 404),
                                         ("off_admin", 401), (None, 401)])
def test_only_admin_reads_and_grades(app, who, name, status):
    mark = _mark(1, "pass", 1)
    client = _client(app, who[name] if name else None)
    for resp in (client.get(BASE), client.post(BASE, json={"mark": mark, "answer": "ok"})):
        assert resp.status_code == status, (name, resp.status_code)
        assert "합성 초안" not in resp.get_data(as_text=True)
    assert db_session.get(AiStaffEvalMark, mark, populate_existing=True).owner_answer is None
    assert db_session.query(SecurityLog).filter(SecurityLog.action == evals_marks.AUDIT_MARK).count() == 0


def test_grading_needs_a_csrf_token(app, who):
    mark = _mark(1, "pass", 1)
    client = _client(app, who["admin"])
    app.config["WRITE_GUARD_ENABLED"] = True
    try:
        blocked = client.post(BASE, json={"mark": mark, "answer": "ok"})
        assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked"
        assert db_session.get(AiStaffEvalMark, mark, populate_existing=True).owner_answer is None
        seed = os.urandom(16).hex()
        with client.session_transaction() as sess:
            sess[_CSRF_SESSION_KEY] = seed
        token = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
        assert client.post(BASE, json={"mark": mark, "answer": "ok"}, headers={"X-CSRF-Token": token}).status_code == 200
    finally:
        app.config.pop("WRITE_GUARD_ENABLED", None)


def test_the_screen_gives_the_grading_place_to_admins_only(app, who):
    admin = _client(app, who["admin"]).get("/brain?tab=agents").get_data(as_text=True)
    assert 'data-ds-evals-marks data-marks-url="/api/ai-staff/evals/marks"' in admin and "ds-agents-marks.js" in admin
    manager = _client(app, who["cs_mgr"]).get("/brain?tab=agents").get_data(as_text=True)
    assert "data-ds-evals " in manager  # 대조군 — 칸은 그려졌다
    assert "data-marks-url" not in manager and "ds-agents-marks.js" not in manager and 'style="' not in admin


def test_the_grading_script_follows_the_screen_rules():
    text = (ROOT / "static" / "js" / "brain" / "ds" / "ds-agents-marks.js").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 300
    for banned in ("innerHTML", "fetch(", "style=", ".style.", "jQuery", "$("):
        assert banned not in text, banned
    assert "__FOMS_DS_EVAL_MARKS_BOUND" in text and "textContent" in text
    for label in ("보내도 돼요", "안 돼요", "넘기는 게 맞아요", "답했어야 해요"):
        assert label in text, label
    for answer in evals_marks.ANSWERS:
        assert f"'{answer}'" in text, answer  # 단추 답 = 서버가 받는 답


# ── 마이그레이션 aistaff_00 ─────────────────────────────────────────────
def _load():
    spec = importlib.util.spec_from_file_location("aistaff_00_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aistaff_00_chains_onto_csagent_08_keeps_one_head_and_matches_the_model():
    module = _load()
    assert (module.revision, module.down_revision) == ("aistaff_00", "csagent_08")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    table = AiStaffEvalMark.__table__
    assert table.name == module.TABLE
    assert [c.name for c in table.columns] == ["id", *(name for name, *_ in module.COLUMNS)]
    assert not table.foreign_keys
    for name, type_, nullable, default in module.COLUMNS:
        column = table.c[name]
        assert column.nullable is nullable and type(column.type) is type(type_), name
        assert getattr(column.type, "length", None) == getattr(type_, "length", None), name
        assert (column.server_default is not None) == (default is not None), name
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {name: module.in_check(column, values) for name, column, values in module.CHECKS}
    uniques = {c.name: tuple(col.name for col in c.columns) for c in table.constraints if isinstance(c, UniqueConstraint)}
    assert uniques == {module.UNIQUE[0]: module.UNIQUE[1]}
    assert {i.name: tuple(c.name for c in i.columns) for i in table.indexes} == dict(module.INDEXES)
    assert module.ANSWERS == graft_models.MARK_ANSWERS == evals_marks.ANSWERS
    assert module.FAIL_KINDS == graft_models.MARK_FAIL_KINDS == evals_marks.FAIL_KINDS
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1 and "aistaff_00" in {rev.revision for rev in script.walk_revisions("base", heads[0])}


def test_aistaff_00_upgrade_then_downgrade_runs_on_an_empty_sqlite():
    """빈 SQLite 에서 실제로 돌린다 — 유일 · 검사 제약이 살아 있고, 내리면 표가 없다."""
    module = _load()
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.upgrade()
        assert module.TABLE in set(inspect(conn).get_table_names())
        assert {i["name"] for i in inspect(conn).get_indexes(module.TABLE)} == {n for n, _c in module.INDEXES}
        insert = sql_text(f"INSERT INTO {module.TABLE} (run_id, turn_id, brand, judge_code, owner_answer) "
                          "VALUES (1, :turn, 'LAHOM', 'pass', :answer)")
        conn.execute(insert, {"turn": 1, "answer": None})
        assert conn.execute(sql_text(f"SELECT draft, created_at IS NOT NULL FROM {module.TABLE}")).one() == ("", 1)
        for params in ({"turn": 1, "answer": "ok"}, {"turn": 2, "answer": "maybe"}):  # 같은 차례 · 모르는 답
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(insert, params)
        module.downgrade()
        assert module.TABLE not in set(inspect(conn).get_table_names())
