"""넘긴 상담 배우기 — 되풀이 문턱 · 기다리는 말(사장님 2026-11-23 '여러 번 나온 것만 바로 반영' · 설계서
``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 3절 · 7절).

상담 1곳 → 기다림(지식 · 카드 없음 — 바로 반영이 켜져 있든 꺼져 있든). 다른 상담에서 ``repeat`` → 지식 하나 · 근거 둘(지금 지식
기준으로 한 번 더 물음). 같은 상담 ``repeat`` → 그대로 기다림. 60일 → ``dropped``. 부딪침은 1곳이어도 카드. 다시 물은 답이 같음이면
버림 · 판정을 못 하면 기다린 채. 기다리는 말은 판정자에게 회사 지식과 따로 보이고 뜻으로도 찾힌다. 마이그레이션 ``csagent_08`` —
사슬 · 모델 · 빈 SQLite 올림 · 내림.

합성 놓을 자리 판정자 · 가짜 벡터 · 가짜 두뇌만(네트워크 0). 손님 글 · 직원 이름 · 금액 없음.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, create_engine, inspect, select

from db import db_session
from foms.persistence.brain.vectors import SOURCE_KINDS, brain_embeddings, vector_metadata
from foms.services.brain import embeddings as emb
from foms.services.brain.ai_gates import judge_source
from foms.services.brain.chat_settings import EMBED_FIELD
from foms.services.brain.embeddings import embedder_source
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import handoff_learning_held as held
from foms.services.cs_agent import handoff_learning_place as place
from foms.services.cs_agent import handoff_learning_route as route
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from foms.services.cs_agent.handoff_learning_place import placer_source
from models import CsAgentLearnHeld
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_handoff_learning import NOW, admin, ask, changes, handed, on  # noqa: F401 — admin 은 fixture
from tests.domains.test_cs_learn_everything import SAID, TARGET, differs
from tests.support.brain_chat_support import axis, chat_on, fake_embedder
from tests.support.brain_support import no_conflict
from tests.support.cs_agent_fakes import FakeAnthropic, FakePlacer, at, clash_placer, keys, naive  # noqa: F401 — keys 는 fixture

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "csagent_08_learn_held.py"
OPEN_REPLY = "합성 직원 답 — 문은 양쪽으로 열 수 있어요"
OPEN_TEXT = "합성 문은 양쪽으로 열 수 있어요"
OPEN_AGAIN = "합성 문은 양쪽 어느 쪽으로도 열 수 있어요"  # 말만 바꾼 되풀이
MEANING = {"여닫이": axis(7), "열림 방향": axis(7)}  # 가짜 뜻 — 글자가 안 겹치는 같은 말


def _night(proposals, placer, *, now=NOW):
    with judge_source(no_conflict), placer_source(placer):
        return hl.run_handoff_learning(db_session, now=now, client=FakeAnthropic({"proposals": proposals}))


DIFF_TEXT = "합성 선반 깊이는 400mm 로 짠다고 안내한다"
DIFF_AGAIN = "합성 선반 깊이는 400mm 로 짜 드린다고 안내한다"


def _said(chat, text=OPEN_TEXT, when=None, **fields):
    """한 상담에서 들은 새 말 하나."""
    return ask([handed(chat, reply=OPEN_REPLY, when=when)], **{"title": "합성 열림 방향", "text": text, **fields})


def _differs(chat, text=DIFF_TEXT):
    """한 상담에서 들은 다른 말 하나(두뇌가 그 항목을 짚었다 — 후보 맨 앞)."""
    return differs([handed(chat, reply=SAID)], title="합성 선반 깊이", text=text)


def rows():
    db_session.expire_all()
    return list(db_session.scalars(select(CsAgentLearnHeld).order_by(CsAgentLearnHeld.id)))


def repeat_placer(then=None):
    """기다리는 말이 보이면 ``repeat``(맨 앞 줄), 다시 물으면(기다리는 말 없음) ``then``(처음 값 새 지식)."""
    return FakePlacer(lambda request: {"verdict": "repeat", "target": request["held"][0]["key"]} if request["held"]
                      else dict(then or {"verdict": "new"}))


# ── 상담 1곳 → 기다림 ────────────────────────────────────────────────────
@pytest.mark.parametrize("auto, said, answer, title, text", [
    (True, lambda: _said("uc-1"), {"verdict": "new"}, "합성 열림 방향", OPEN_TEXT),
    (False, lambda: _said("uc-1"), {"verdict": "new"}, "합성 열림 방향", OPEN_TEXT),  # 바로 반영이 꺼져 있어도 같다
    (True, lambda: _differs("uc-1"), {"verdict": "adds", "target": TARGET, "added": "깊은 선반은 400mm 로 짠다"},
     "합성 선반 깊이", DIFF_TEXT),
])
def test_a_saying_from_one_chat_waits_and_is_neither_knowledge_nor_a_card(admin, auto, said, answer, title, text):
    on(**{AUTO_FIELD: auto})
    before = current_object(db_session, TARGET)
    counts = _night([said()], FakePlacer(answer))
    assert (counts["held"], counts["filed"], counts["applied"], counts["new"], counts["added"], counts["cards"]) == (
        1, 0, 0, 0, 0, 0)
    assert changes() == [] and current_object(db_session, TARGET).version == before.version
    (row,) = rows()
    assert (row.brand, row.title, row.text, row.state, row.chat_ids) == ("LAHOM", title, text, "waiting", ["uc-1"])
    assert row.first_seen == row.last_seen == naive(NOW)


def test_a_repeat_from_another_chat_becomes_one_knowledge_item_with_both_evidences(admin):
    on(**{AUTO_FIELD: True})
    first = handed("uc-1", reply=OPEN_REPLY)
    _night([ask([first], title="합성 열림 방향", text=OPEN_TEXT)], FakePlacer())
    placer = repeat_placer()
    second = handed("uc-2", reply=OPEN_REPLY)
    counts = _night([ask([second], title="합성 열림 방향", text=OPEN_AGAIN)], placer, now=at(12, 1))
    assert (counts["promoted"], counts["filed"], counts["applied"], counts["held"], counts["new"]) == (1, 1, 1, 0, 0)
    (change,) = changes()
    assert change.op == "create" and current_object(db_session, change.item_key).text == OPEN_AGAIN
    assert change.evidence == [f"case:{first}", f"case:{second}", "staff:mgr-1"]  # 두 상담의 근거를 합쳤다
    assert "근거 상담 2곳 · 기다리던 말" in change.reason
    (row,) = rows()
    assert (row.state, row.chat_ids, len(row.turn_ids)) == ("promoted", ["uc-1", "uc-2"], 2)
    first_ask, second_ask = placer.requests
    assert first_ask["held"] == [{"key": f"held:{row.id}", "title": "합성 열림 방향", "text": OPEN_TEXT}]
    assert second_ask["held"] == []  # 올릴 때는 지금 지식 기준으로만 한 번 더 묻는다


def test_a_repeat_from_the_same_chat_only_adds_the_turn_and_keeps_waiting(admin):
    on(**{AUTO_FIELD: True})
    _night([_said("uc-1")], FakePlacer())
    placer = repeat_placer()
    counts = _night([_said("uc-1", text=OPEN_AGAIN)], placer, now=at(12, 1))
    assert (counts["held"], counts["promoted"], counts["filed"]) == (1, 0, 0) and changes() == []
    (row,) = rows()
    assert (row.state, row.chat_ids, len(row.turn_ids), len(placer.requests)) == ("waiting", ["uc-1"], 2, 1)
    assert row.last_seen == naive(at(12, 1)) and row.first_seen == naive(NOW)


@pytest.mark.parametrize("then, code, state", [
    ({"verdict": "same", "target": TARGET}, "same", "dropped"),  # 그사이 지식이 같은 말을 한다 — 버림
    ({"verdict": "not_rule"}, "not_rule", "dropped"),
    ({"verdict": "contradicts", "target": TARGET, "clash": {"knowledge": "합성 지식", "staff": "합성 직원"}},
     "cards", "promoted"),  # 사장님 카드로 올라갔다
])
def test_the_second_ask_decides_what_becomes_of_the_held_saying(admin, then, code, state):
    on(**{AUTO_FIELD: True})
    _night([_differs("uc-1")], FakePlacer())
    counts = _night([_differs("uc-2", text=DIFF_AGAIN)], repeat_placer(then), now=at(12, 1))
    assert (counts[code], counts["promoted"], counts["applied"]) == (1, 0, 0)
    assert rows()[0].state == state
    assert [c.item_type for c in changes()] == (["conflict"] if code == "cards" else [])


def test_a_judge_that_is_down_on_the_second_ask_keeps_the_merged_saying_waiting(admin):
    on(**{AUTO_FIELD: True})
    _night([_said("uc-1")], FakePlacer())
    answers = iter([None, "down"])

    def flaky(_session, request):
        if next(answers) == "down":
            from foms.services.brain.ai_gates import JudgeUnavailable
            raise JudgeUnavailable("place_off")
        return {"verdict": "repeat", "target": request["held"][0]["key"]}

    counts = _night([_said("uc-2", text=OPEN_AGAIN)], flaky, now=at(12, 1))
    assert (counts["blocked"], counts["promoted"], changes()) == ({"place_unavailable": 1}, 0, [])
    (row,) = rows()
    assert (row.state, row.chat_ids) == ("waiting", ["uc-1", "uc-2"])  # 다음 되풀이에 다시 올린다


def test_a_contradiction_from_one_chat_is_a_card_at_once_even_beside_a_held_saying(admin):
    on(**{AUTO_FIELD: True})
    _night([_differs("uc-4")], FakePlacer())
    assert len(rows()) == 1 and changes() == []  # 한 상담 — 기다리는 말
    placer = clash_placer(TARGET)
    counts = _night([differs([handed("uc-5", reply=SAID)])], placer, now=at(12, 1))
    assert (counts["cards"], counts["held"]) == (1, 0)
    assert placer.requests[0]["held"] != []  # 기다리는 말이 보였어도 부딪침이 먼저(사장님이 고른다)
    assert [c.item_type for c in changes()] == ["conflict"] and rows()[0].state == "waiting"


def test_a_saying_not_heard_again_for_sixty_days_is_dropped(admin):
    on(**{AUTO_FIELD: True})
    _night([_said("uc-1")], FakePlacer())
    route.file_proposals(db_session, [], [], now=NOW + datetime.timedelta(days=59), known="", approved=[])
    assert rows()[0].state == "waiting"
    route.file_proposals(db_session, [], [], now=NOW + datetime.timedelta(days=61), known="", approved=[])
    assert rows()[0].state == "dropped"
    placer, later = repeat_placer(), at(12, 1) + datetime.timedelta(days=61)
    _night([_said("uc-2", text=OPEN_AGAIN, when=later - datetime.timedelta(hours=2))], placer, now=later)
    assert placer.requests[0]["held"] == []  # 버린 말은 판정자에게 다시 보이지 않는다


# ── 판정자에게 보이는 꼴 · 뜻으로 찾기 ───────────────────────────────────
def test_the_held_block_is_labelled_apart_from_knowledge_and_repeat_needs_a_shown_key(admin):
    from foms.services.cs_agent.settings import read_settings
    on(**{AUTO_FIELD: True})
    shown = [{"key": "held:7", "title": "합성 열림 방향", "text": OPEN_TEXT}]
    answer = {"verdict": "repeat", "target": "held:7", "added": "", "clash": {"knowledge": "", "staff": ""}, "why": "합성"}
    client = FakeAnthropic(answer)
    cfg = read_settings(db_session, log=False)
    got = place.place(db_session, key=None, title="합성 열림", text=OPEN_AGAIN, cfg=cfg, now=NOW, client=client, held=shown)
    assert (got.verdict, got.target) == ("repeat", "held:7")
    user = client.params[0]["messages"][0]["content"]
    assert user.index("[사장님이 이미 정한 것]") < user.index("[기다리는 말](회사 지식이 아니다") < user.index("[새 말]")
    assert f"[held:7] 합성 열림 방향: {OPEN_TEXT}" in user and "repeat" in place.SCHEMA["properties"]["verdict"]["enum"]
    assert "repeat:" in place.SYSTEM and "decided 가 가장 먼저" in place.SYSTEM
    alone = FakeAnthropic(answer)
    assert place.place(db_session, key=None, title="합성 열림", text=OPEN_AGAIN, cfg=cfg, now=NOW,
                       client=alone).verdict == place.UNKNOWN  # 보이지 않은 기다리는 말은 대상이 못 된다
    assert "[기다리는 말]" not in alone.params[0]["messages"][0]["content"]


@pytest.fixture
def vec(admin):
    """'의미 찾기' 켬 + SQLite 벡터 표(시험 끝에 지운다)."""
    engine = db_session.get_bind()
    vector_metadata.create_all(engine)
    chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00"})
    yield admin
    db_session.remove()
    vector_metadata.drop_all(engine)


def _held_vectors():
    return set(db_session.execute(select(brain_embeddings.c.source_key).where(
        brain_embeddings.c.source_kind == emb.SOURCE_HELD)).scalars())


def test_a_held_saying_is_found_by_meaning_without_shared_words_and_its_vector_goes_when_promoted(vec):
    on(**{AUTO_FIELD: True})
    with embedder_source(fake_embedder(MEANING)):
        _night([_said("uc-1", title="여닫이 문", text="여닫이 문짝은 좌우 모두 된다")], FakePlacer())
    (row,) = rows()
    assert _held_vectors() == {str(row.id)}  # 판정에 만든 벡터를 그 자리에서 남긴다(돈 더 안 듦)
    other = "손잡이 쪽을 바꿔 달 수 있다고 안내한다"  # 글자는 안 겹친다
    assert held.near(db_session, brand="LAHOM", text=other) == []  # 벡터가 없으면 글자로만 — 못 찾는다
    placer = repeat_placer()
    with embedder_source(fake_embedder(MEANING)):
        counts = _night([_said("uc-2", title="열림 방향 바꾸기", text=other)], placer, now=at(12, 1))
    assert placer.requests[0]["held"][0]["key"] == f"held:{row.id}"
    assert (counts["promoted"], counts["applied"]) == (1, 1)
    assert rows()[0].state == "promoted" and _held_vectors() == set()  # 기다리는 동안만 둔다


# ── 마이그레이션 csagent_08 ──────────────────────────────────────────────
def _load():
    spec = importlib.util.spec_from_file_location("csagent_08_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_csagent_08_chains_onto_brain_03_keeps_one_head_and_matches_the_model():
    module = _load()
    assert (module.revision, module.down_revision) == ("csagent_08", "brain_03")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    table = CsAgentLearnHeld.__table__
    assert [c.name for c in table.columns] == ["id", *(name for name, *_ in module.COLUMNS)]
    assert not table.foreign_keys
    for name, type_, nullable, default in module.COLUMNS:
        column = table.c[name]
        assert column.nullable is nullable and getattr(column.type, "length", None) == getattr(type_, "length", None), name
        assert (column.server_default is not None) == (default is not None), name
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {module.STATE_CHECK: module.in_check("state", module.STATES)}
    assert module.STATES == held.STATES
    assert {i.name: tuple(c.name for c in i.columns) for i in table.indexes} == dict(module.INDEXES)
    assert module.EMBED_SOURCES == SOURCE_KINDS and module.EMBED_SOURCES_BEFORE == SOURCE_KINDS[:3]
    vector_checks = {c.name: str(c.sqltext) for c in brain_embeddings.constraints if isinstance(c, CheckConstraint)}
    assert vector_checks[module.EMBED_CHECK] == module.in_check("source_kind", SOURCE_KINDS)
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1 and "csagent_08" in {rev.revision for rev in script.walk_revisions("base", heads[0])}


def test_csagent_08_upgrade_then_downgrade_runs_on_an_empty_sqlite():
    """빈 SQLite 에서 실제로 돌린다 — 벡터 표가 없는 DB 는 제약을 건드리지 않고 지나간다."""
    module = _load()
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.upgrade()
        assert module.TABLE in set(inspect(conn).get_table_names())
        assert {i["name"] for i in inspect(conn).get_indexes(module.TABLE)} == {n for n, _c in module.INDEXES}
        module.downgrade()
        assert module.TABLE not in set(inspect(conn).get_table_names())
