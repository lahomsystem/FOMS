"""화면 작은 둘(설계 글 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 7.4 · 차례 9).

- 지식 카드 '연결 없음' 줄 → "아직 아무 지식에도 안 이어졌어요 — 문장으로 잇기"(문장으로 고치기를 쓸 수 있는 사람만 링크 —
  ``?tab=inbox&fill=item:<키>``), 누르면 입력 칸이 그 지식 이름으로 미리 채워진다. 쓸 수 없으면(스위치 끔) 글만 · 링크 없음.
  볼 수 없는 지식 · 다른 머리 · 너무 긴 키는 미리 채우지 않는다. 시험지 길(``fill=E02``)은 예전처럼 채우지 않는다.
- 물어보기 근거 칩: 이웃 따라가기로 찾은 근거면 응답 칸 ``followed`` 가 참(칩 끝 '(이어서 찾음)' — ds-ask-turn.js).
합성 계정 · 합성 지식만.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from db import db_session
from foms.services.brain import chat_answer
from foms.services.brain.change_request_hints import fill_item, link_prefill
from foms.services.brain.chat_retrieve import VIA_NEIGHBOUR, VIA_SEARCH, Candidate, Retrieval
from foms.services.brain.scope import viewer_of
from models import User
from tests.domains.test_brain_ds_request import _body, _client, _flags, who  # noqa: F401 — who 는 fixture
from tests.support.brain_chat_support import NOW_KST
from tests.support.brain_support import create, link

ROOT = Path(__file__).resolve().parents[2]
TURN = ROOT / "static/js/brain/ds/ds-ask-turn.js"
LONE = "common/synth-lone"
UNLINKED = "아직 아무 지식에도 안 이어졌어요"


@pytest.fixture
def lone(who):
    create(db_session, db_session.get(User, who["admin"]), LONE, name="합성 외톨이 문짝")
    db_session.commit()
    return who


def _glance(body: str) -> str:
    at = body.index('aria-label="연결된 지식"')
    return body[at:body.index("</section>", at)]


def test_unlinked_card_line_links_to_the_input_prefilled_with_its_name(app, lone):
    admin = _client(app, lone["admin"])
    part = _glance(_body(admin.get(f"/brain/items/{LONE}")))
    found = re.search(r'<a href="([^"]+)">([^<]+)</a>', part)
    assert found and html.unescape(found.group(2)) == f"{UNLINKED} — 문장으로 잇기" and "연결 없음" not in part
    href = html.unescape(found.group(1))
    assert href == "/brain?tab=inbox&fill=item:common/synth-lone" or href == "/brain?tab=inbox&fill=item%3Acommon%2Fsynth-lone"
    box = re.search(r"<input [^>]*data-ds-req-text[^>]*>", _body(admin.get(href))).group(0)
    assert html.unescape(re.search(r'value="([^"]*)"', box).group(1)) == "'합성 외톨이 문짝'을 …에 이어 줘"
    link(db_session, db_session.get(User, lone["admin"]), "excludes", "common/door", "common/slide")
    db_session.commit()
    linked = _glance(_body(admin.get("/brain/items/common/door")))  # 대조군 — 이어진 지식에는 그 줄이 없다
    assert UNLINKED not in linked and "미닫이 문짝" in linked


def test_unlinked_line_is_plain_text_for_people_who_cannot_use_sentences(app, lone, monkeypatch):
    _flags(monkeypatch, change=False)
    part = _glance(_body(_client(app, lone["admin"]).get(f"/brain/items/{LONE}")))
    assert UNLINKED in part and "문장으로 잇기" not in part and "fill=item" not in part and "<a " not in part


def test_fill_item_only_for_visible_items_and_its_own_prefix(app, lone):
    admin = viewer_of(db_session.get(User, lone["admin"]))
    today = NOW_KST.date()
    assert fill_item(db_session, admin, f"item:{LONE}", today=today) == "'합성 외톨이 문짝'을 …에 이어 줘"
    hidden = viewer_of(db_session.get(User, lone["sales_mgr"]))
    assert fill_item(db_session, hidden, "item:cs/lesson/hidden", today=today) is None  # 도면팀만 보는 지식
    for raw in ("", None, LONE, "item:", "item:no/such", "item:" + "x" * 121, "E02"):
        assert fill_item(db_session, admin, raw, today=today) is None, raw
    assert link_prefill("합성 표") == "'합성 표'를 …에 이어 줘" and link_prefill("AB") == "'AB'을(를) …에 이어 줘"
    box = re.search(r"<input [^>]*data-ds-req-text[^>]*>", _body(_client(app, lone["admin"]).get("/brain?tab=inbox&fill=E02")))
    assert "value=" not in box.group(0)  # 시험지 길은 예전처럼 비운다


def _cand(key, via):
    return Candidate(key=key, name=f"합성 {key}", item_type="fact", layer="common", confidence="confirmed",
                     checked_at=None, via=via)


def test_chat_evidence_says_when_it_was_found_by_following_a_link():
    retrieval = Retrieval([_cand("a/one", VIA_SEARCH), _cand("a/two", VIA_NEIGHBOUR)])
    verified = chat_answer.Verified(answer="합성 답", evidence=["a/one", "a/two"], checks=[], unknown=False, ask_team=None,
                                    layer=None, certainty="high")
    chips = chat_answer._view(1, verified, retrieval, left=3, cards=True)["evidence"]
    assert [(c["key"], c["followed"]) for c in chips] == [("a/one", False), ("a/two", True)]
    assert set(chips[0]) == {"key", "name", "type", "confidence", "checked_at", "followed"}  # 칸 하나만 더


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_ask_turn_script_marks_followed_chips():
    subprocess.run(["node", "--check", str(TURN)], check=True, timeout=60)
    source = TURN.read_text(encoding="utf-8")
    assert "' (이어서 찾음)'" in source and ".followed" in source
