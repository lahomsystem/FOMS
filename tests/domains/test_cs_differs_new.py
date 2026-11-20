"""부딪치지 않는 다른 말은 새 지식(사장님 2026-11-21 '새 내용은 바로 넣기' · 상담 원장 D276).

- 밤 배우기: 바로 고치지 못한 한 번뿐인 다른 말 — 두뇌가 짚은 항목과 부딪치지 않으면 새 지식(바로 반영), 부딪치거나 · 판정을
  못 하거나 · 숫자가 직원 답에 없으면 예전처럼 엇갈림 카드.
- 쌓인 카드 다시 가르기(:mod:`foms.services.cs_agent.handoff_learning_resort`): 같은 판정으로 한 번 — 옮긴 카드는 '합쳐짐'으로
  닫고, 같은 말 카드는 합치고, 부딪침 · 숫자는 그대로 둔다. 판정을 못 하면 다음 바퀴에 다시. 다 하면 다시 안 한다.

합성 자료만(손님 글 · 직원 이름 · 금액 없음).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain.ai_gates import JudgeUnavailable, judge_source
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import handoff_learning_resort as resort
from foms.services.cs_agent import handoff_learning_gates as gates
from foms.services.cs_agent import learning_pass
from foms.services.brain.proposals import Proposer
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from foms.services.cs_agent.handoff_learning_gates import MERGED_ACTION
from models import SecurityLog
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_handoff_learning import NOW, admin, changes, handed, on  # noqa: F401 — admin 은 fixture
from tests.domains.test_cs_learn_everything import SAID, TARGET, differs, run_clash
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys, naive  # noqa: F401 — keys 는 fixture

NEW_TEXT = "합성 선반 뒤 콘센트 자리는 타공해 드린다고 안내한다"
NEW_SAID = "합성 직원 답 — 선반 뒤 콘센트 자리는 타공해 드려요"
LATER = at(11, 9)  # 밤 창 밖(바퀴는 시각과 상관없이 다시 가른다)


class Judge:
    """합성 판정자 — 부를 때마다 적고, ``clash`` 글이 든 묶음은 '부딪침', ``down`` 이면 부를 수 없음."""

    def __init__(self, clash: str = "\0", down: bool = False):
        self.calls: list[tuple[str, str]] = []
        self.clash, self.down = clash, down

    def __call__(self, _session, first: str, second: str) -> bool:
        if self.down:
            raise JudgeUnavailable("judge_off")
        self.calls.append((first, second))
        return self.clash in first or self.clash in second


def _night(judge, proposals, now=NOW):
    with judge_source(judge):
        return hl.run_handoff_learning(db_session, now=now, client=FakeAnthropic({"proposals": proposals}))


def _resort(judge, now=LATER):
    with judge_source(judge):
        return resort.resort_cards(db_session, now=now)


# ── 밤 배우기 ─────────────────────────────────────────────────────────────
def test_a_one_off_new_detail_that_does_not_clash_goes_in_as_new_knowledge_at_once(admin):
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, TARGET)
    judge = Judge()
    counts = _night(judge, [differs([handed("uc-5", reply=NEW_SAID)], title="합성 콘센트 자리 타공", text=NEW_TEXT)])
    assert (counts["new"], counts["applied"], counts["cards"], counts["fixed"]) == (1, 1, 0, 0)
    (change,) = changes()
    assert (change.op, change.status, change.decided_action, change.item_type) == ("create", "applied", "auto_learn", "fact")
    assert change.item_key.startswith("lahom/handoff-") and current_object(db_session, change.item_key).text == NEW_TEXT
    assert (current_object(db_session, TARGET).version, current_object(db_session, TARGET).text) == (before.version, before.text)
    assert judge.calls and all(before.text in pair[0] + pair[1] for pair in judge.calls)  # 두뇌가 짚은 항목과 견줬다
    assert change.gates["conflict"] == "skipped" or "conflict" in change.gates  # 제안 길은 같은 판정을 다시 막지 않는다


@pytest.mark.parametrize("judge, said, text", [
    (Judge(clash="400mm"), SAID, "합성 선반 깊이는 400mm 로 안내했어요"),  # 부딪침
    (Judge(down=True), NEW_SAID, NEW_TEXT),  # 판정을 못 함
    (Judge(), NEW_SAID, "합성 선반 뒤 콘센트 자리는 37곳 타공한다고 안내한다"),  # 직원 답에 없는 숫자
])
def test_a_clash_an_unjudged_detail_or_a_made_up_number_stays_a_card(admin, judge, said, text):
    on(**{AUTO_FIELD: True})
    counts = _night(judge, [differs([handed("uc-5", reply=said)], text=text)])
    assert (counts["new"], counts["applied"], counts["cards"]) == (0, 0, 1)
    assert [c.item_type for c in changes()] == ["conflict"]


def test_a_new_detail_also_closes_the_earlier_card_that_said_the_same(admin):
    on(**{AUTO_FIELD: True})
    run_clash(FakeAnthropic({"proposals": [differs([handed("uc-5", reply=NEW_SAID)], text=NEW_TEXT)]}))
    (card,) = changes()
    again = differs([handed("uc-6", reply=NEW_SAID)], text=NEW_TEXT, fixed_text="", repeats=[card.item_key])
    counts = _night(Judge(), [again], now=at(12, 1))
    assert (counts["new"], counts["cards"]) == (1, 0)
    db_session.refresh(card)
    assert (card.status, card.decided_action) == ("expired", MERGED_ACTION)


# ── 쌓인 카드 다시 가르기 ─────────────────────────────────────────────────
def _cards():
    """카드 넷 — 부딪침 · 새 내용 · 직원 답에 없는 숫자 · 새 내용과 같은 말(밤 배우기는 겹침 관문이 같은 카드를 또 만들지 않아
    운영의 여러 밤처럼 직접 넣는다)."""
    on(**{AUTO_FIELD: True})
    run_clash(FakeAnthropic({"proposals": [
        differs([handed("uc-5", reply=SAID)], text="합성 선반 깊이는 400mm 로 안내했어요"),
        differs([handed("uc-6", reply=NEW_SAID)], title="합성 콘센트 자리 타공", text=NEW_TEXT),
        differs([handed("uc-7", reply=NEW_SAID)], title="합성 받침 수", text="합성 선반 받침은 37개 들어간다"),
    ]}))
    turn = handed("uc-8", reply=NEW_SAID)
    common = dict(reason="합성 — 같은 말 카드", proposer=Proposer.agent_named(gates.AGENT), now=naive(NOW), known=NEW_SAID,
                  evidence=[f"case:{turn}", "staff:mgr-1"])
    assert gates._differs_card(db_session, TARGET, title="합성 콘센트 타공 같은 말", text=NEW_TEXT + ".", number=99,
                               common=common, now=at(12, 1), seen=[]) == "conflict_card"
    db_session.commit()
    cards = changes()
    assert [c.item_type for c in cards] == ["conflict"] * 4
    return cards


def test_resort_moves_the_cards_that_do_not_clash_and_keeps_the_rest_once(admin):
    clash, new, number, same = _cards()
    judge = Judge(clash="400mm")
    counts = _resort(judge)
    assert counts == {"checked": 4, "left": 0, "halted": None, "conflict": 1, "moved": 1, "numbers": 1, "merged": 1}
    db_session.expire_all()
    for card, status in ((clash, "open"), (new, "expired"), (number, "open"), (same, "expired")):
        db_session.refresh(card)
        assert card.status == status, card.id
    assert new.decided_action == same.decided_action == MERGED_ACTION
    made = [c for c in changes() if c.item_type != "conflict"]
    assert len(made) == 1 and (made[0].status, made[0].decided_action, made[0].item_type) == ("applied", "auto_learn", "policy")
    assert current_object(db_session, made[0].item_key).text in (NEW_TEXT, NEW_TEXT + ".")  # 새 카드부터 — 둘 가운데 하나만
    assert "엇갈림 카드에서 새 지식으로 옮김" in made[0].reason
    assert not any(e.startswith("about:") for e in made[0].evidence)
    assert db_session.query(SecurityLog).filter_by(action="BRAIN_MERGE").count() >= 2
    assert resort.card_resort_state(db_session)["done"] is True
    assert _resort(judge) == {"off": "done"}  # 한 번만


def test_resort_waits_when_the_judge_is_down_and_goes_a_few_cards_per_tick(admin, monkeypatch):
    cards = _cards()
    down = _resort(Judge(down=True))
    assert (down["checked"], down["halted"]) == (0, "judge_unavailable")
    assert all(c.status == "open" for c in changes() if c.item_type == "conflict")
    monkeypatch.setattr(resort, "PER_TICK", 2)
    first = _resort(Judge(clash="400mm"))
    assert (first["checked"], first["left"]) == (2, 2) and resort.card_resort_state(db_session)["done"] is False
    later = handed("uc-9", reply=SAID)  # 다시 가르기를 시작한 뒤 생긴 카드는 새 규칙이 이미 가른 것 — 건드리지 않는다
    run_clash(FakeAnthropic({"proposals": [differs([later], text="합성 선반 깊이는 400mm 가 맞다고 안내했어요")]}),
              now=at(12, 1))
    second = _resort(Judge(clash="400mm"))
    assert (second["checked"], second["left"]) == (2, 0) and resort.card_resort_state(db_session)["done"] is True
    newest = max((c for c in changes() if c.item_type == "conflict"), key=lambda c: c.id)
    assert newest.id > max(c.id for c in cards) and newest.status == "open"


def test_resort_needs_learning_on_and_auto_apply_on(admin):
    _cards()
    on(**{AUTO_FIELD: False})
    assert _resort(Judge()) == {"off": "no_auto"}
    assert all(c.status == "open" for c in changes())


def test_the_learning_share_runs_the_resort_at_any_hour(admin, monkeypatch):
    seen = []
    monkeypatch.setattr(learning_pass, "resort_cards", lambda session, now: seen.append(now) or {"checked": 1})
    out = learning_pass.run_learning(db_session, now=LATER, stop_check=lambda: None)
    assert seen == [LATER] and out["card_resort"] == {"checked": 1}
