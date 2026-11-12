"""③ 비슷한 지난 상담을 뜻으로도 찾기(설계서 2026-11-12 온톨로지 10절 15 · D197 ③) — 끄면 글자 비슷함만 · 켜면 뜻이 가까운 같은
브랜드 사례를 섞는다 · 상담 사례 벡터 칸이 꺼져 있으면 부르지 않는다 · 두 순위에 다 든 사례가 위로.

합성 값만(꾸민 글).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.persistence.brain.vectors import vector_metadata
from foms.services.brain.chat_settings import CASE_FIELD, EMBED_FIELD, read_chat_settings
from foms.services.brain.embed_sources import run_embed
from foms.services.brain.embeddings import embedder_source
from foms.services.cs_agent import case_material
from foms.services.cs_agent.case_meaning import merge_ranks
from foms.services.cs_agent.drafting_read import ChatLine
from models import CsAgentTurn
from tests.support.brain_chat_support import NOW_KST, axis, chat_on, fake_embedder
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.support.cs_agent_fakes import at, derived, keys  # noqa: F401 — keys 는 fixture

MEANING = {"붙박이": axis(0), "장롱": axis(0), "선반": axis(1)}


def said(text):
    return [ChatLine(derived("q", at(2, 8, 9), "user", text), text)]


def _case(chat, question, *, brand="LAHOM"):
    db_session.add(CsAgentTurn(brand=brand, chat_id=chat, last_user_message_id=f"m-{chat}", state="stored", attempts=1,
                               masked_question=question, staff_reply_masked=f"합성 답 {chat}", outcome="edited"))
    db_session.commit()


@pytest.fixture
def cases(app):
    """SQLite 벡터 표 + 의미 찾기 · 상담 사례 벡터 켬 + 사례 넷(벡터까지 채움)."""
    engine = db_session.get_bind()
    vector_metadata.create_all(engine)
    chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00", CASE_FIELD: True})
    _case("c-wardrobe", "장롱 짜맞춤 견적 궁금해요")
    _case("c-shelf", "선반 깊이 문의드려요")
    _case("c-haud", "장롱 하우드 문의", brand="HAUD")
    _case("c-both", "붙박이 가격이요 장롱")
    with embedder_source(fake_embedder(MEANING)):
        run_embed(db_session, cfg=read_chat_settings(db_session), now=NOW_KST, apply=True, sources=("cs_case",))
    yield
    db_session.remove()
    vector_metadata.drop_all(engine)


def _answers(found):
    return [item[1] for item in found]


def test_rrf_puts_cases_in_both_ranks_first():
    assert merge_ranks([1, 2, 3], [3, 4], 3) == [3, 1, 2]
    assert merge_ranks([], [4, 5], 5) == [4, 5]
    assert merge_ranks([7, 8], [], 1) == [7]


def test_meaning_adds_close_same_brand_cases_only_when_on(cases):
    lines = said("붙박이 가격이요")
    off = case_material.similar_cases(db_session, "LAHOM", lines)
    assert _answers(off) == ["합성 답 c-both"]  # 글자로는 같은 글 하나만
    calls: list = []
    with embedder_source(fake_embedder(MEANING, calls)):
        on = case_material.similar_cases(db_session, "LAHOM", lines, meaning=True, now=NOW_KST)
        no_now = case_material.similar_cases(db_session, "LAHOM", lines, meaning=True)
    assert _answers(on) == ["합성 답 c-both", "합성 답 c-wardrobe"]  # 둘 다 든 사례가 위 · 하우드 · 선반은 빠짐
    assert _answers(no_now) == _answers(off)
    assert [call["input_type"] for call in calls] == ["query"]
    chat_on(db_session, **{EMBED_FIELD: True, "embed_daily_cap_usd": "1.00", CASE_FIELD: False})
    with embedder_source(fake_embedder(MEANING, calls)):
        assert _answers(case_material.similar_cases(db_session, "LAHOM", lines, meaning=True, now=NOW_KST)) == _answers(off)
    assert len(calls) == 1  # 상담 사례 벡터 칸이 꺼지면 부르지 않는다


@pytest.mark.parametrize("on", [False, True])
def test_the_draft_passes_the_panel_switch_and_its_clock(channel, monkeypatch, on):
    from foms.services.cs_agent import drafting
    from foms.services.cs_agent import settings as st
    from foms.services.cs_agent.onto_settings import ONTO_CASES_FIELD
    from models import SystemSetting
    from tests.domains.test_cs_drafting import FakeBrain, customer, result, run

    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, version=1,
                                   setting_value={**st.DEFAULTS, ONTO_CASES_FIELD: on}))
    db_session.commit()
    seen: list = []
    real = drafting.similar_cases
    monkeypatch.setattr(drafting, "similar_cases", lambda *a, **kw: seen.append(kw) or real(*a, **kw))
    customer(channel, text="합성 문의예요")
    run(channel, brain_fn=FakeBrain(result()))
    (kw,) = seen
    assert kw["meaning"] is on and kw["now"] is not None
