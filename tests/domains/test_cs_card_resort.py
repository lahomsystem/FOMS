"""쌓인 엇갈림 카드 다시 가르기 판 3(사장님 2026-11-23 'AI 가 새 판정으로 다시 가르기' · 설계서
``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 2.1 · 3절 — :mod:`foms.services.cs_agent.handoff_learning_resort`).

- '지금 글 + 덧붙인 문장' 카드(옛 길): 한 상담 → 덧붙인 문장만 기다리는 말 · 카드 닫힘 · 지식 그대로. 두 상담 → 그 항목 끝에
  문장을 붙여 바로 반영 · 카드 닫힘. 다른 상담의 같은 카드 → 기다리는 말에 합쳐 올림.
- 같음 · 이미 정함 · 규칙 아님 → 카드 닫힘 · 기다리는 말 없음. 부딪침 → 카드는 열린 채 첫 줄에 두 구절.
- 두 구절이 이미 있는 카드는 손대지 않는다. 판정을 못 하면 멈추고 다음 바퀴에 다시. 다 하면 다시 안 한다. 판이 바뀌면 한 번 더.

합성 놓을 자리 판정자(:class:`tests.support.cs_agent_fakes.FakePlacer`)만(네트워크 0). 손님 글 · 직원 이름 · 금액 없음.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from db import db_session
from foms.services.brain.proposals import Proposer
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning_gates as gates
from foms.services.cs_agent import handoff_learning_resort as resort
from foms.services.cs_agent import learning_pass
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from foms.services.cs_agent.handoff_learning_gates import CLASH_HEAD, MERGED_ACTION
from foms.services.cs_agent.handoff_learning_place import placer_source
from models import CsAgentLearnHeld, SecurityLog, SystemSetting
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_handoff_learning import NOW, admin, changes, handed, on  # noqa: F401 — admin 은 fixture
from tests.support.cs_agent_fakes import FakePlacer, at, clash_placer, keys, naive  # noqa: F401 — keys 는 fixture

TARGET = "lahom/shelf-depth"
SAID = "합성 직원 답 — 선반 깊이는 350mm 이고 받침은 두 줄로 넣어 드려요"
ADDED = "선반 받침은 두 줄로 넣는다"
OTHER = "합성 선반 뒤 콘센트 자리는 타공해 드린다고 안내한다"
LATER = at(11, 9)  # 밤 창 밖(바퀴는 시각과 상관없이 다시 가른다)
ADDS = {"verdict": "adds", "target": TARGET, "added": ADDED}
_NUMBER = iter(range(100, 10_000))


def _resort(placer, now=LATER):
    with placer_source(placer):
        return resort.resort_cards(db_session, now=now)


def _whole() -> str:
    """짚은 항목의 지금 글을 그대로 품고 한 문장을 덧붙인 글(첫 밤 옛 길 카드 13장의 꼴)."""
    return f"{current_object(db_session, TARGET).text} {ADDED}"


def _card(chats=("uc-5",), text=None, clash=""):
    """넘김 학습 엇갈림 카드 한 장(근거 = 상담마다 차례 하나 + 답한 직원)."""
    turns = [handed(chat, reply=SAID) for chat in chats]
    common = dict(reason="합성 — 쌓인 카드", proposer=Proposer.agent_named(gates.AGENT), now=naive(NOW), known=SAID,
                  evidence=[*(f"case:{turn}" for turn in turns), "staff:mgr-1"])
    code = gates._differs_card(db_session, TARGET, title="합성 선반 깊이", text=text or _whole(), number=next(_NUMBER),
                               common=common, now=NOW, seen=[], clash=clash)
    assert code == "conflict_card"
    db_session.commit()
    return max(changes(), key=lambda change: change.id)


def _status(card):
    db_session.expire_all()
    db_session.refresh(card)
    return card.status, card.decided_action


def _held():
    db_session.expire_all()
    return list(db_session.scalars(select(CsAgentLearnHeld).order_by(CsAgentLearnHeld.id)))


def _made():
    return [change for change in changes() if change.item_type != "conflict"]


@pytest.fixture
def auto(admin):
    on(**{AUTO_FIELD: True})
    return admin


# ── '지금 글 + 덧붙인 문장' 카드 ─────────────────────────────────────────
def test_a_card_from_one_chat_waits_as_its_added_sentence_only_and_closes(auto):
    before = current_object(db_session, TARGET)
    card = _card()
    placer = FakePlacer(ADDS)
    counts = _resort(placer)
    assert (counts["checked"], counts["held"], counts["left"], counts["halted"]) == (1, 1, 0, None)
    assert _status(card) == ("expired", MERGED_ACTION)
    (row,) = _held()
    assert (row.text, row.state, len(row.chat_ids)) == (ADDED, "waiting", 1)  # 지금 글은 이미 지식이다
    assert _made() == [] and current_object(db_session, TARGET).version == before.version
    (request,) = placer.requests
    assert request["text"] == _whole() and request["candidates"][0]["key"] == TARGET
    assert not request["text"].startswith((CLASH_HEAD, gates.DIFFERS_LINE))  # 표시 줄은 빼고 묻는다
    assert db_session.query(SecurityLog).filter_by(action="BRAIN_MERGE").count() == 1


def test_a_card_from_two_chats_appends_the_sentence_to_the_item_and_closes(auto):
    before = current_object(db_session, TARGET)
    card = _card(chats=("uc-5", "uc-6"))
    counts = _resort(FakePlacer(ADDS))
    assert (counts["placed_added"], counts["checked"]) == (1, 1) and _held() == []
    assert _status(card) == ("expired", MERGED_ACTION)
    (change,) = _made()
    assert (change.op, change.item_key, change.status, change.decided_action) == ("update", TARGET, "applied", "auto_learn")
    assert current_object(db_session, TARGET).text == f"{before.text} {ADDED}"
    assert "쌓인 엇갈림 카드를 놓을 자리 판정으로 다시 가름" in change.reason
    assert not any(e.startswith("about:") for e in change.evidence)


def test_a_new_saying_from_two_chats_becomes_new_knowledge_and_closes(auto):
    card = _card(chats=("uc-5", "uc-6"), text=OTHER)
    counts = _resort(FakePlacer())
    assert counts["placed_new"] == 1 and _status(card) == ("expired", MERGED_ACTION)
    (change,) = _made()
    assert change.op == "create" and current_object(db_session, change.item_key).text == OTHER


def test_the_same_card_from_another_chat_joins_the_held_saying_and_goes_in(auto):
    before = current_object(db_session, TARGET)
    first, second = _card(chats=("uc-5",)), _card(chats=("uc-6",))
    placer = FakePlacer(lambda request: {"verdict": "repeat", "target": request["held"][0]["key"]} if request["held"]
                        else dict(ADDS))
    counts = _resort(placer)
    assert (counts["held"], counts["promoted"], counts["checked"]) == (1, 1, 2)
    assert _status(first) == _status(second) == ("expired", MERGED_ACTION)
    (row,) = _held()
    assert (row.state, row.chat_ids) == ("promoted", ["uc-5", "uc-6"])
    assert current_object(db_session, TARGET).text == f"{before.text} {ADDED}"


# ── 넣지 않음 · 부딪침 ──────────────────────────────────────────────────
def _owner_answered():
    """그 항목에 대해 사장님이 '회사 지식이 맞아요'로 닫은 카드 한 장(다시 가를 카드가 아니다)."""
    card = _card(chats=("uc-4",), text="합성 선반 깊이는 400mm 로 안내했어요")
    card.status, card.reject_code, card.decided_at = "rejected", "knowledge_right", naive(NOW)
    db_session.commit()


@pytest.mark.parametrize("answer, code", [
    ({"verdict": "same", "target": TARGET}, "same"),
    ({"verdict": "decided", "target": TARGET}, "decided_before"),
    ({"verdict": "not_rule"}, "not_rule"),
])
def test_a_card_the_placer_drops_is_closed_and_nothing_is_held(auto, answer, code):
    if answer["verdict"] == "decided":
        _owner_answered()
    before = current_object(db_session, TARGET)
    card = _card(chats=("uc-5", "uc-6"))
    counts = _resort(FakePlacer(answer))
    assert (counts[code], counts["checked"]) == (1, 1)
    assert _status(card) == ("expired", MERGED_ACTION)
    assert _held() == [] and _made() == [] and current_object(db_session, TARGET).version == before.version


def test_a_real_clash_stays_open_and_now_starts_with_the_two_phrases(auto):
    card = _card()
    counts = _resort(clash_placer(TARGET, "깊이는 350mm", "받침은 두 줄"))
    assert (counts["marked"], counts["checked"]) == (1, 1)
    assert _status(card) == ("open", None)
    assert card.fields["text"]["after"].split("\n") == [
        f"{CLASH_HEAD}회사 지식 「깊이는 350mm」 ↔ 직원 「받침은 두 줄」", gates.DIFFERS_LINE, _whole()]
    assert card.fields["payload"]["after"]["target"] == TARGET
    assert _held() == [] and _made() == []
    assert gates.open_cards(db_session) == [(card.item_key, TARGET, _whole())]  # 견주기는 예전 꼴 그대로


def test_a_card_the_placer_already_made_is_left_untouched(auto):
    card = _card(clash=f"{CLASH_HEAD}회사 지식 「합성 지식」 ↔ 직원 「합성 직원」")
    fields = card.fields
    placer = FakePlacer(ADDS)
    counts = _resort(placer)
    assert (counts["kept"], counts["checked"], placer.requests) == (1, 1, [])
    assert _status(card) == ("open", None) and card.fields == fields


def test_a_card_whose_item_is_gone_is_left_without_asking(auto, monkeypatch):
    card = _card()
    monkeypatch.setattr(resort, "current_object", lambda _session, _key: None)
    placer = FakePlacer(ADDS)
    counts = _resort(placer)
    assert (counts["target"], placer.requests) == (1, []) and _status(card) == ("open", None)


# ── 바퀴 · 판 ───────────────────────────────────────────────────────────
def test_the_pass_stops_when_the_placer_is_down_and_goes_on_next_tick(auto, monkeypatch):
    cards = [_card(chats=(chat,), text=f"{OTHER} — {word}") for chat, word in (("uc-5", "첫째"), ("uc-6", "둘째"),
                                                                                ("uc-7", "셋째"))]
    down = _resort(FakePlacer(down=True))
    assert (down["checked"], down["left"], down["halted"]) == (0, 3, "judge_unavailable")
    assert all(_status(card) == ("open", None) for card in cards) and _held() == []
    assert resort.card_resort_state(db_session)["done"] is False
    monkeypatch.setattr(resort, "PER_TICK", 2)
    first = _resort(FakePlacer())
    assert (first["checked"], first["left"], first["held"]) == (2, 1, 2)
    later = _card(chats=("uc-9",), text="합성 나중 카드는 새 규칙이 이미 가른 것이다")  # 시작한 뒤 생긴 카드 — 건드리지 않는다
    second = _resort(FakePlacer())
    assert (second["checked"], second["left"]) == (1, 0) and resort.card_resort_state(db_session)["done"] is True
    assert all(_status(card) == ("expired", MERGED_ACTION) for card in cards) and _status(later) == ("open", None)


def test_after_every_card_is_sorted_the_pass_never_runs_again(auto):
    _card()
    assert _resort(FakePlacer(ADDS))["checked"] == 1
    assert resort.card_resort_state(db_session)["done"] is True
    _card(chats=("uc-6",))
    placer = FakePlacer(ADDS)
    assert _resort(placer) == {"off": "done"} and placer.requests == []


def test_a_new_version_sorts_every_open_card_once_more_where_version_two_finished(auto):
    card = _card()
    db_session.add(SystemSetting(setting_key=resort.STORE_KEY, description="합성", setting_value={
        "policy": 2, "until": card.id, "checked": [card.id], "done": True}))
    db_session.commit()
    counts = _resort(FakePlacer(ADDS))
    assert (counts["checked"], counts["held"]) == (1, 1)  # 판 2 가 가른 표는 버리고 처음부터
    state = resort.card_resort_state(db_session)
    assert (resort.RESORT_POLICY, state["policy"], state["done"], state["checked"]) == (3, 3, True, [card.id])


def test_the_pass_needs_learning_on_and_auto_apply_on(admin):
    on(**{AUTO_FIELD: True})
    card = _card()
    on(**{AUTO_FIELD: False})
    placer = FakePlacer(ADDS)
    assert _resort(placer) == {"off": "no_auto"} and placer.requests == []
    assert _status(card) == ("open", None)


def test_the_learning_share_runs_the_resort_at_any_hour(admin, monkeypatch):
    seen = []
    monkeypatch.setattr(learning_pass, "resort_cards", lambda session, now: seen.append(now) or {"checked": 1})
    out = learning_pass.run_learning(db_session, now=LATER, stop_check=lambda: None)
    assert seen == [LATER] and out["card_resort"] == {"checked": 1}
