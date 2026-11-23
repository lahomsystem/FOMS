"""한글 낱말 찾기(형태소 + BM25 — :mod:`foms.services.brain.word_search`)와 놓을 자리 후보 고르기(설계서
``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 5.2).

- 낱말: 조사 · 어미는 떼고 숫자 · 영문은 남긴다.
- 줄 세우기: 조사 · 끝만 다른 같은 말이 합성 항목 열두 개 가운데 맨 앞, 상관없는 항목은 앞에 오지 않는다.
- 후보: 낱말 찾기를 켜면 글자 찾기가 놓친 항목이 후보에 든다. 쓸 수 없으면 예전과 똑같다. 짚은 항목은 늘 맨 앞, 빈 설명 칸 ·
  다른 브랜드 · 판정자에게 못 보내는 글은 어느 길로도 안 든다.
- ``import app`` 은 형태소 꾸러미를 불러오지 않는다(웹 · gevent 프로세스가 모델 메모리를 지지 않게).

합성 글만(손님 글 · 직원 이름 · 금액 없음 · 네트워크 0).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from db import db_session
from foms.services.brain import ai_gates, word_search
from foms.services.brain.word_search import WordSearchUnavailable
from tests.support.brain_support import NOW, create, person

ROOT = Path(__file__).resolve().parents[2]


# ── 낱말 ─────────────────────────────────────────────────────────────────
def test_particles_and_endings_are_stripped_and_numbers_and_latin_are_kept():
    assert "도면" in word_search.tokens("도면을") and "도면" in word_search.tokens("도면이")
    assert word_search.tokens("도면을") == word_search.tokens("도면이") == ["도면"]
    got = word_search.tokens("선반 깊이는 350mm 이고 LED 조명")
    assert {"선반", "깊이", "350", "mm", "led", "조명"} <= set(got)
    assert not {"는", "을", "이고"} & set(got)
    assert word_search.tokens("") == [] and word_search.tokens(None) == []


# ── 줄 세우기 ────────────────────────────────────────────────────────────
DOCS = [
    ("synth/hinge", "경첩 소리 경첩이 삐걱거리면 기름칠해 드립니다"),
    ("synth/parking", "주차 안내 방문 기사님 차는 건물 뒤편에 댑니다"),
    ("synth/rail", "서랍 레일 서랍 레일은 저소음 부품을 씁니다"),
    ("synth/depth", "선반 깊이 선반 깊이는 350mm 로 짭니다"),
    ("synth/led", "조명 LED 조명은 붙박이장 위쪽에 답니다"),
    ("synth/mirror", "거울 문 거울은 안전 필름을 붙여 둡니다"),
    ("synth/paint", "도장 색 도장 색은 견본 판으로 고릅니다"),
    ("synth/handle", "손잡이 손잡이는 매립형과 돌출형이 있습니다"),
    ("synth/visit", "실측 방문 실측은 평일 낮에 갑니다"),
    ("synth/drawing", "도면 확인 도면은 실측 뒤 사흘 안에 보내 드립니다"),
    ("synth/glass", "유리 선반 유리는 강화 유리를 씁니다"),
    ("synth/wood", "합판 두께 몸통 합판은 18mm 를 씁니다"),
]


def test_a_paraphrase_finds_its_partner_first_and_an_unrelated_item_stays_out():
    got = word_search.rank("경첩에서 삐걱거리는 소리가 나면 기름칠을 해요", DOCS, limit=6)
    assert got[0] == "synth/hinge"
    assert "synth/parking" not in got[:3]
    drawing = word_search.rank("도면이 언제 보내지나요 실측하고 사흘이면 되나요", DOCS, limit=6)
    assert drawing[0] == "synth/drawing" and "synth/mirror" not in drawing[:3]
    assert word_search.rank("", DOCS, limit=6) == [] and word_search.rank("경첩", [], limit=6) == []


def test_tokens_are_remembered_by_key_and_version():
    word_search._reset_for_tests()
    first = word_search.item_tokens("synth/hinge", 1, "경첩이 삐걱거린다")
    assert word_search.item_tokens("synth/hinge", 1, "다른 글") == first  # 같은 판은 다시 나누지 않는다
    assert word_search.item_tokens("synth/hinge", 2, "선반 깊이") != first  # 판이 바뀌면 다시 나눈다


def test_interleave_puts_words_first_and_skips_repeats():
    assert word_search.interleave(["a", "b", "c"], ["b", "x"], 4) == ["a", "b", "x", "c"]
    assert word_search.interleave([], ["x", "y"], 1) == ["x"]


# ── 놓을 자리 후보 ──────────────────────────────────────────────────────
QUERY = ["삐걱거리는 경첩", "경첩에서 삐걱거리는 소리가 나면 기름칠한다"]
PARTNER, POINTED, NAMED = "lahom/synth-hinge", "lahom/synth-parking", "lahom/synth-hinge-name"


@pytest.fixture
def items(app):
    """합성 지식 — 짝(글자 찾기 점수는 하한 밑) · 짚을 항목 · 늘 빠져야 할 넷(빈 설명 칸 · 다른 브랜드 · 관리 글 · 낮은 확신)."""
    word_search._reset_for_tests()
    admin = person(db_session, "word_search_admin")
    rule = dict(item_type="situation", layer="cs", brand="LAHOM")
    create(db_session, admin, PARTNER, name="도어 마감", text="경첩이 삐걱거리면 기름칠해 드립니다", **rule)
    create(db_session, admin, POINTED, name="주차 안내", text="방문 기사님 차는 건물 뒤편에 댑니다", **rule)
    create(db_session, admin, NAMED, name="경첩 소리", text="문 닫힘 소리는 조정으로 줄입니다", **rule)  # 글자 찾기가 이름으로 찾는다
    create(db_session, admin, "common/synth-hinge-stub", item_type="product_line", name="경첩 부품",
           text="경첩 삐걱거리 기름칠 경첩")
    create(db_session, admin, "haud/synth-hinge", item_type="situation", layer="cs", brand="HAUD", name="경첩 기름",
           text="경첩이 삐걱거리면 기름칠합니다")
    create(db_session, admin, "lahom/synth-hinge-admin", name="경첩 관리", text="경첩이 삐걱거리면 기름칠", visibility="admin",
           **rule)
    seen = create(db_session, admin, "lahom/synth-hinge-seen", name="경첩 관찰", text="경첩이 삐걱거리면 기름칠", **rule)
    seen.confidence = "observed"  # 사람이 반영하면 확정이 된다 — 관찰 단계 줄을 흉내 낸다
    db_session.commit()
    return admin


def _related(**extra):
    common = dict(key=None, texts=QUERY, today=NOW.date(), brand="LAHOM", limit=6)
    return [item["key"] for item in ai_gates.related_items(db_session, **{**common, **extra})]


NEVER = {"common/synth-hinge-stub", "haud/synth-hinge", "lahom/synth-hinge-admin", "lahom/synth-hinge-seen"}


def test_word_search_brings_in_a_partner_that_character_matching_misses(items):
    today = _related()
    assert today == [NAMED]  # 짝은 글자 찾기 점수(글 낱말 둘)가 하한 밑이다
    words = _related(words=True)
    assert words[0] == PARTNER and NAMED in words
    assert not NEVER & set(words) and not NEVER & set(today)
    assert "haud/synth-hinge" in _related(words=True, brand=None)  # 대조군 — 브랜드를 안 거르면 낱말 찾기가 찾는 줄이다


def test_unavailable_word_search_gives_exactly_todays_list(items, monkeypatch):
    def broken(_text):
        raise WordSearchUnavailable("model_load")

    today = _related()
    assert _related(words=True) != today  # 켜져 있으면 다르다(아래 같음이 우연이 아니게)
    monkeypatch.setattr(word_search, "tokens", broken)
    assert _related(words=True) == today == [NAMED]
    assert _related(words=True, key=POINTED) == _related(key=POINTED)


def test_the_pointed_item_stays_first_and_appears_once(items):
    got = _related(words=True, key=POINTED)
    assert got[0] == POINTED and got.count(POINTED) == 1 and PARTNER in got
    assert not NEVER & set(got)
    assert _related(words=True, key="common/synth-hinge-stub")[:1] == [PARTNER]  # 짚은 칸이 빈 설명 칸이면 빼고 고른다


# ── 불러오기 ────────────────────────────────────────────────────────────
def test_importing_app_does_not_load_the_morpheme_packages():
    """``import app``(웹 · gevent) 이 형태소 꾸러미 · BM25 를 불러오지 않는다 — 모델은 놓을 자리 판정이 처음 쓸 때만 읽힌다."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    probe = "import sys\nimport app\nprint('kiwi=%s bm25=%s' % ('kiwipiepy' in sys.modules, 'bm25s' in sys.modules))\n"
    done = subprocess.run([sys.executable, "-c", probe], cwd=str(ROOT), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    assert "kiwi=False bm25=False" in done.stdout, done.stdout[-2000:]
