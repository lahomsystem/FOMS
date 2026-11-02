"""회사 지식 의미 찾기(사장님 D114 — Voyage AI 벡터 · 처음 끔) — 가짜 벡터 시험.

1. RRF 순서 — 글자 · 다른 이름 · 벡터 세 줄을 섞는다(글자에 없던 뜻 비슷한 항목도 들어온다).
2. 꺼짐 · 열쇠 없음 · 실패 · 표 없음이면 지금의 글자 찾기 그대로(조용히 물러남).
3. 보기 범위는 SQL 에서 순위 앞에 — 볼 수 없는 항목은 벡터가 가장 가까워도 안 나온다(음성 대조군).
4. 질문은 가린 글만 벡터로 · 가격 재량 · 관리 항목과 개인정보 꼴 글은 넣지 않는다.
5. 의미 찾기 돈 상한(따로 줄) · 시간 상한 · 백필은 모의 실행이 처음 값 · 판이 바뀌면 다시 넣기.
6. 마이그레이션 ``brain_02`` 사슬(머리 하나) · 벡터 표는 ORM ``Base`` 밖 · pgvector 없으면 만들지 않음.
7. 근원 종류 셋(회사 지식 항목 · 물어보기 질문 · 상담 사례) — 질문 벡터는 물을 때 남고 1년 지우기에 같이 지워진다, 상담 사례는
   백필만(설정 처음 끔 · 사례 기억과 같은 가림 검사에 하나라도 걸리면 건너뜀 · 상담 초안 사례 고르기는 그대로).
합성 지식 · 합성 계정 · 가짜 벡터만(네트워크 없음).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select

import datetime

from db import Base, db_session
from foms.persistence.brain.models import BrainQuestion
from foms.persistence.main.models import CsAgentTurn
from foms.services.brain.chat_log import purge_questions
from foms.services.brain.chat_settings import CASE_FIELD
from foms.persistence.brain.vectors import DIMENSION, SOURCE_KINDS, brain_embeddings, vector_metadata
from foms.services.brain import embeddings as emb
from foms.services.brain.chat_answer import ask
from foms.services.brain.chat_settings import DEFAULTS, EMBED_FIELD, read_chat_settings
from foms.services.brain.chat_tools import rrf, search_objects
from foms.services.brain.embed_sources import run_embed
from foms.services.brain.embeddings import EmbedUnavailable, embedder_source, nearest, query_vector
from foms.services.brain.proposals import Proposer, propose_retire, propose_update
from foms.services.brain.apply import apply_change
from foms.services.brain.scope import viewer_of
from models import SystemSetting
from tests.support.brain_chat_support import NOW_KST, axis, chat_on, chat_world, fake_embedder, fixed, reply
from tests.support.brain_support import NOW, REASON

ROOT = Path(__file__).resolve().parents[2]
TODAY = NOW_KST.date()
TABLE = {"깊이": axis(0), "치수": axis(0), "경첩": axis(2), "재단": axis(3), "여유분": axis(3)}


@pytest.fixture
def vec(app):
    """사람 · 지식 · 설정(챗봇 · 의미 찾기 켬) + SQLite 벡터 표(시험 끝에 지운다)."""
    engine = db_session.get_bind()
    vector_metadata.create_all(engine)
    people = chat_world(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00"})
    yield people
    db_session.remove()
    vector_metadata.drop_all(engine)


def _cfg():
    return read_chat_settings(db_session)


def embed_pending(session, *, cfg, now, apply=False, limit=500):
    """회사 지식 항목 근원만(이 파일의 시험 꼴)."""
    return run_embed(session, cfg=cfg, now=now, apply=apply, limit=limit, sources=("brain_item",))["brain_item"]


def _fill(calls=None):
    with embedder_source(fake_embedder(TABLE, calls)):
        done = embed_pending(db_session, cfg=_cfg(), now=NOW_KST, apply=True)
    return done


# ── 1. RRF ───────────────────────────────────────────────────────────────
def test_rrf_fuses_ranks_and_semantic_hits_join(vec):
    fused = rrf([["a", "b", "c"], ["c"], ["c", "a"]])
    assert [k for k, _s in fused] == ["c", "a", "b"]
    assert fused[0][1] == pytest.approx(1 / 63 + 1 / 61 + 1 / 61)
    _fill()
    who = viewer_of(vec["admin"])
    assert search_objects(db_session, who, "장 안쪽 치수", today=TODAY) == []  # 글자로는 못 찾는다
    with embedder_source(fake_embedder(TABLE)):
        q = query_vector(db_session, "장 안쪽 치수", cfg=_cfg(), now=NOW_KST)
    assert [h["key"] for h in search_objects(db_session, who, "장 안쪽 치수", today=TODAY, vector=q)] == ["common/sliding"]
    with embedder_source(fake_embedder(TABLE)):
        q2 = query_vector(db_session, "경첩 치수", cfg=_cfg(), now=NOW_KST)
    hybrid = [h["key"] for h in search_objects(db_session, who, "경첩 치수", today=TODAY, vector=q2)]
    assert hybrid[:2] == ["common/hinge", "common/sliding"]  # 글자 + 벡터 둘 다 맞은 항목이 앞


# ── 2. 물러남 ────────────────────────────────────────────────────────────
def test_off_missing_key_failure_and_missing_table_fall_back_silently(vec, monkeypatch):
    _fill()
    who = viewer_of(vec["admin"])
    lexical = search_objects(db_session, who, "여닫이 경첩", today=TODAY)
    monkeypatch.delenv(emb.KEY_ENV, raising=False)
    assert emb.off_reason(db_session, _cfg()) == "no_key"  # 열쇠 env 없음 = 꺼짐
    assert query_vector(db_session, "여닫이 경첩", cfg=_cfg(), now=NOW_KST) is None
    calls = []
    with embedder_source(fake_embedder(TABLE, calls, fail=EmbedUnavailable("timeout"))):
        assert query_vector(db_session, "여닫이 경첩", cfg=_cfg(), now=NOW_KST) is None
        out = ask(db_session, vec["admin"], "여닫이 경첩", now=NOW_KST,
                  client=fixed(reply(answer="합성 조건", evidence_ids=["common/hinge"], unknown=False)))
    assert len(calls) == 2 and calls[0]["timeout"] == 8.0 and out["unknown"] is False  # 실패해도 글자 찾기로 답한다
    assert search_objects(db_session, who, "여닫이 경첩", today=TODAY, vector=None) == lexical
    chat_on(db_session, **{EMBED_FIELD: False, "embed_daily_cap_usd": "1.00"})
    assert emb.off_reason(db_session, _cfg()) == "off"
    assert DEFAULTS[EMBED_FIELD] is False and DEFAULTS["embed_daily_cap_usd"] is None  # 처음 끔 · 상한 비움


def test_no_vector_table_means_off(app):
    people = chat_world(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00"})
    with embedder_source(fake_embedder(TABLE)):
        assert emb.off_reason(db_session, read_chat_settings(db_session)) == "no_table"
        assert ask(db_session, people["admin"], "주차 요금", client=fixed(reply()), now=NOW_KST)["unknown"] is True


# ── 3. 보기 범위는 순위 앞에(SQL) ─────────────────────────────────────────
def test_scope_is_filtered_before_ranking_with_a_negative_control(vec):
    _fill()
    with embedder_source(fake_embedder(TABLE)):
        q = query_vector(db_session, "여유분 얼마나 둬요", cfg=_cfg(), now=NOW_KST)
    cs = [k for k, _s in nearest(db_session, viewer_of(vec["cs_mgr"]), q, today=TODAY, limit=3)]
    dr = [k for k, _s in nearest(db_session, viewer_of(vec["dr_mgr"]), q, today=TODAY, limit=3)]
    assert dr[0] == "drawing/bom" and "drawing/bom" not in cs  # 도면팀 범위 — 대조군은 본다
    assert len(cs) == 3  # 상한까지 볼 수 있는 다른 항목으로 채운다(볼 수 없는 것이 자리를 먹지 않는다)
    hits = [h["key"] for h in search_objects(db_session, viewer_of(vec["cs_mgr"]), "여유분 얼마나 둬요", today=TODAY,
                                             vector=q)]
    assert "drawing/bom" not in hits


# ── 4. 무엇을 보내나 ─────────────────────────────────────────────────────
def test_only_masked_questions_and_allowed_item_text_are_embedded(vec):
    calls = []
    _fill(calls)
    sent = "\n".join(t for c in calls for t in c["texts"])
    assert calls[0]["input_type"] == "document"
    assert "재량 할인 폭" not in sent  # 가격 재량 범위 항목은 새 바깥 처리자에게 보내지 않는다
    assert "빌트인장" in sent and "위 낱말: 가구" in sent  # 다른 이름 · 위 낱말도 같이
    stored = set(db_session.execute(select(brain_embeddings.c.source_key).where(
        brain_embeddings.c.source_kind == "brain_item")).scalars())
    assert "common/discount" not in stored and "common/sliding" in stored
    asked = []
    with embedder_source(fake_embedder(TABLE, asked)):
        ask(db_session, vec["admin"], "고객 010-2345-6789 님 슬라이딩 깊이", client=fixed(reply()), now=NOW_KST)
    query = asked[0]["texts"][0]
    assert asked[0]["input_type"] == "query" and "2345" not in query and "[전화]" in query


# ── 5. 돈 · 백필 · 다시 넣기 ──────────────────────────────────────────────
def test_embedding_cost_cap_and_separate_spend_line(vec):
    chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "0.00"})
    calls = []
    with embedder_source(fake_embedder(TABLE, calls)):
        assert query_vector(db_session, "슬라이딩 깊이", cfg=_cfg(), now=NOW_KST) is None
        assert embed_pending(db_session, cfg=_cfg(), now=NOW_KST, apply=False)["pending"] >= 5  # 모의 실행은 세기만
    assert calls == []
    chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00"})
    with embedder_source(fake_embedder(TABLE, calls)):
        assert query_vector(db_session, "슬라이딩 깊이", cfg=_cfg(), now=NOW_KST) is not None
    line = db_session.get(SystemSetting, emb.SPEND_KEY, populate_existing=True).setting_value
    assert line["calls"] == 1 and float(line["usd"]) > 0 and line["reserved"] == "0.000000"
    assert db_session.get(SystemSetting, "brain_chat_spend") is None  # 챗봇 돈 줄과 따로


def test_backfill_is_dry_run_by_default_and_reembeds_changed_versions(vec):
    calls = []
    with embedder_source(fake_embedder(TABLE, calls)):
        dry = embed_pending(db_session, cfg=_cfg(), now=NOW_KST)
        assert dry["applied"] is False and calls == [] and dry["pending"] >= 5
        first = embed_pending(db_session, cfg=_cfg(), now=NOW_KST, apply=True)
        assert first["embedded"] == dry["pending"]
        assert embed_pending(db_session, cfg=_cfg(), now=NOW_KST)["pending"] == 0  # 다시 돌려도 같은 것은 안 넣는다
        admin = vec["admin"]
        change = propose_update(db_session, key="common/hinge", base_version=1, after={"text": "여닫이 경첩 넷 합성"},
                                reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")
        apply_change(db_session, change.id, actor=admin, now=NOW)
        retire = propose_retire(db_session, key="common/old-rule", base_version=1, reason=REASON,
                                proposer=Proposer.user(admin.id), now=NOW)
        apply_change(db_session, retire.id, actor=admin, now=NOW)
        db_session.commit()
        again = embed_pending(db_session, cfg=_cfg(), now=NOW_KST, apply=True)
    assert again["embedded"] == 1 and again["removed"] == 1
    version = db_session.execute(select(brain_embeddings.c.source_version).where(
        brain_embeddings.c.source_key == "common/hinge")).scalar_one()
    assert version == 2
    from tools.cron import brain_embed
    nightly = brain_embed.run(apply=False, session=db_session, now=NOW_KST)  # 밤 단계 — 열쇠 env 없음 · 상담 사례는 안 다룸
    assert nightly == {"brain_item": {"off": "no_key"}, "chatbot_question": {"off": "no_key"}}


# ── 6. 마이그레이션 · 표 ─────────────────────────────────────────────────
def test_brain_02_chains_once_and_keeps_vectors_out_of_the_orm_base():
    path = ROOT / "migrations" / "versions" / "brain_02_chat_usage.py"
    spec = importlib.util.spec_from_file_location("brain_02_unit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == ("brain_02", "brain_01")
    source = path.read_text(encoding="utf-8")
    ddl = " ".join(module.EMBED_DDL).lower()
    assert "import models" not in source and "hnsw" not in ddl and "ivfflat" not in ddl  # 정확 찾기(벡터 색인 없음)
    assert f"vector({DIMENSION})" in " ".join(module.EMBED_DDL) and module.EMBED_DIM == DIMENSION == 1024
    assert "pg_available_extensions" in source  # pgvector 가 없으면 벡터 표만 건너뛴다
    for name, columns in module.COLUMNS.items():
        table = Base.metadata.tables[name]
        assert [c.name for c in table.columns] == ["id", *(n for n, *_ in columns)], name
        for col_name, type_, nullable, _default in columns:
            assert table.c[col_name].nullable is nullable, (name, col_name)
        assert {i.name for i in table.indexes} == {n for n, *_ in module.INDEXES[name]}, name
    assert "brain_embeddings" not in Base.metadata.tables and "brain_embeddings" in vector_metadata.tables
    assert [c.name for c in brain_embeddings.columns] == ["id", "source_kind", "source_key", "source_version", "model",
                                                           "dimension", "embedding", "text_hash", "created_at"]
    assert module.EMBED_SOURCES == SOURCE_KINDS == ("brain_item", "chatbot_question", "cs_case")
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1 and "brain_02" in {rev.revision for rev in script.walk_revisions("base", heads[0])}


def test_voyage_request_shape_without_network(monkeypatch):
    sent = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"object": "list", "data": [{"object": "embedding", "embedding": [0.5] * DIMENSION, "index": 0}],
                    "model": emb.MODEL, "usage": {"total_tokens": 7}}

    def post(url, **kwargs):
        sent.update(url=url, **kwargs)
        return Response()

    monkeypatch.setenv(emb.KEY_ENV, "synthetic-key")
    monkeypatch.setattr(emb.requests, "post", post)
    vectors, tokens = emb.voyage_embedder(["합성 글"], "query", 5.0)
    assert tokens == 7 and len(vectors[0]) == DIMENSION
    assert sent["url"] == "https://api.voyageai.com/v1/embeddings" and sent["timeout"] == 5.0
    assert sent["json"] == {"input": ["합성 글"], "model": "voyage-4", "input_type": "query", "output_dimension": 1024}
    assert sent["headers"] == {"Authorization": "Bearer synthetic-key"}
    monkeypatch.setattr(emb.requests, "post", lambda *a, **k: type("R", (), {"status_code": 429})())
    with pytest.raises(EmbedUnavailable) as caught:
        emb.voyage_embedder(["합성 글"], "query", 5.0)
    assert caught.value.code == "http_429"


# ── 7. 근원 종류 셋 ──────────────────────────────────────────────────────
def _rows(kind):
    return dict(db_session.execute(select(brain_embeddings.c.source_key, brain_embeddings.c.source_version)
                                   .where(brain_embeddings.c.source_kind == kind)).all())


def test_chatbot_question_vectors_are_kept_backfilled_and_purged(vec):
    calls = []
    with embedder_source(fake_embedder(TABLE, calls)):
        out = ask(db_session, vec["admin"], "고객 010-2345-6789 님 슬라이딩 깊이", client=fixed(reply()), now=NOW_KST)
    db_session.commit()
    assert set(_rows("chatbot_question")) == {str(out["id"])} and len(calls) == 1  # 찾기에 만든 벡터를 그대로(돈 더 안 듦)
    old = BrainQuestion(asker_id=vec["admin"].id, masked_question="경첩 몇 개 다나요", unknown=True,
                        asked_at=datetime.datetime(2025, 10, 1))
    leak = BrainQuestion(asker_id=vec["admin"].id, masked_question="연락처 010-2345-6789", unknown=True)
    db_session.add_all([old, leak])
    db_session.commit()
    assert db_session.get(BrainQuestion, out["id"]).masked_question.startswith("고객 [전화]")  # 질문 줄도 그대로 남는다
    with embedder_source(fake_embedder(TABLE, calls)):
        filled = run_embed(db_session, cfg=_cfg(), now=NOW_KST, apply=True, sources=("chatbot_question",))
    assert filled["chatbot_question"]["embedded"] == 1, filled  # 가림 검사에 걸리는 질문은 보내지 않는다
    assert "2345" not in "".join(t for c in calls for t in c["texts"]) and calls[-1]["input_type"] == "query"
    assert set(_rows("chatbot_question")) == {str(out["id"]), str(old.id)}
    gone = purge_questions(db_session, now_utc=NOW_KST.astimezone(datetime.timezone.utc).replace(tzinfo=None))
    db_session.commit()
    assert gone["questions"] == 1 and gone["vectors"] == 1 and set(_rows("chatbot_question")) == {str(out["id"])}


def _turn(question, answer, *, outcome="direct", held_out=False):
    row = CsAgentTurn(brand="LAHOM", chat_id=f"uc-{question[:4]}", last_user_message_id="m-1", state="stored", attempts=1,
                      masked_question=question, staff_reply_masked=answer, outcome=outcome, held_out=held_out)
    db_session.add(row)
    db_session.commit()
    return row


def test_cs_case_vectors_are_backfill_only_off_by_default_and_skip_leaks(vec):
    ok = _turn("선반 깊이 문의드려요", "안녕하세요\n선반 깊이는 합성 기준으로 안내드려요\n감사합니다")
    leaky = _turn("주소 서울시 합성구 합성로 12", "확인했어요")
    held = _turn("선반 색 문의", "합성 답", held_out=True)
    account = _turn("입금 어디로 해요", "계좌 110-123-456789 로 부탁드려요")
    calls = []
    with embedder_source(fake_embedder(TABLE, calls)):
        assert run_embed(db_session, cfg=_cfg(), now=NOW_KST, sources=("cs_case",)) == {"cs_case": {"off": "off"}}
        chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00", CASE_FIELD: True})
        dry = run_embed(db_session, cfg=_cfg(), now=NOW_KST, sources=("cs_case",))["cs_case"]
        assert dry["applied"] is False and dry["pending"] == 1 and calls == []  # 모의 실행이 처음 값 · 돈 0
        done = run_embed(db_session, cfg=_cfg(), now=NOW_KST, sources=("cs_case",), apply=True)["cs_case"]
    assert done["embedded"] == 1 and set(_rows("cs_case")) == {str(ok.id)}
    sent = calls[0]["texts"][0]
    assert sent.startswith("손님: 선반 깊이 문의드려요\n직원: 선반 깊이는") and "감사합니다" not in sent  # 사례 기억과 같은 다듬기
    assert str(leaky.id) not in _rows("cs_case") and str(held.id) not in _rows("cs_case")
    assert str(account.id) not in _rows("cs_case")  # 계좌 같은 번호(가림 검사)는 보내지 않는다
    from tools.cron import brain_embed
    with embedder_source(fake_embedder(TABLE)):
        assert "cs_case" not in brain_embed.run(apply=False, session=db_session, now=NOW_KST)  # 밤 단계는 상담 사례를 안 다룸
    from foms.services.cs_agent import case_material
    assert "embeddings" not in Path(case_material.__file__).read_text(encoding="utf-8")  # 상담 초안 사례 고르기는 그대로
    assert DEFAULTS[CASE_FIELD] is False
