"""부딪치지 않는 다른 말은 새 지식(사장님 2026-11-21 '새 내용은 바로 넣기' · 상담 원장 D276 → 11-22 놓을 자리 판정).

- 밤 배우기: 바로 고치지 못한 다른 말 — 놓을 자리 판정이 '새 지식'이면 두 상담에서 들은 말은 새 지식(바로 반영 · 한 상담뿐이면
  기다리는 말 — 11-23), '부딪침'이면 엇갈림 카드(한 상담이어도), 판정을 못 하면 넣지도 카드도 없고, 직원 답에 없는 숫자는 새
  지식이 되지 못한다(``numbers``).
- 쌓인 카드 다시 가르기(판 3 — 놓을 자리 판정 · 되풀이 문턱)는 :mod:`tests.domains.test_cs_card_resort`.

합성 자료만(손님 글 · 직원 이름 · 금액 없음).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain.ai_gates import JudgeUnavailable, judge_source
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from foms.services.cs_agent.handoff_learning_gates import MERGED_ACTION
from foms.services.cs_agent.handoff_learning_place import placer_source
from models import SystemSetting
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_handoff_learning import NOW, admin, changes, handed, on  # noqa: F401 — admin 은 fixture
from tests.domains.test_cs_learn_everything import SAID, TARGET, differs, run_clash
from tests.support.cs_agent_fakes import FakeAnthropic, FakePlacer, at, clash_placer, keys  # noqa: F401 — keys 는 fixture

NEW_TEXT = "합성 선반 뒤 콘센트 자리는 타공해 드린다고 안내한다"
NEW_SAID = "합성 직원 답 — 선반 뒤 콘센트 자리는 타공해 드려요"


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


def _night(judge, proposals, now=NOW, placer=None):
    with judge_source(judge), placer_source(placer or FakePlacer()):
        return hl.run_handoff_learning(db_session, now=now, client=FakeAnthropic({"proposals": proposals}))


# ── 밤 배우기 ─────────────────────────────────────────────────────────────
def test_a_new_detail_from_two_chats_that_does_not_clash_goes_in_as_new_knowledge_at_once(admin):
    """한 상담뿐이면 기다리는 말(되풀이 문턱 11-23 — :mod:`tests.domains.test_cs_learn_held`), 두 상담이면 바로 새 지식."""
    on(**{AUTO_FIELD: True})
    before = current_object(db_session, TARGET)
    placer = FakePlacer()
    ids = [handed("uc-5", reply=NEW_SAID), handed("uc-6", reply=NEW_SAID)]
    counts = _night(Judge(), [differs(ids, title="합성 콘센트 자리 타공", text=NEW_TEXT, fixed_text="")], placer=placer)
    assert (counts["new"], counts["applied"], counts["cards"], counts["fixed"]) == (1, 1, 0, 0)
    (change,) = changes()
    assert (change.op, change.status, change.decided_action, change.item_type) == ("create", "applied", "auto_learn", "fact")
    assert change.item_key.startswith("lahom/handoff-") and current_object(db_session, change.item_key).text == NEW_TEXT
    assert (current_object(db_session, TARGET).version, current_object(db_session, TARGET).text) == (before.version, before.text)
    (request,) = placer.requests
    assert request["candidates"][0] == {"key": TARGET, "name": before.name, "type": before.item_type, "text": before.text}


@pytest.mark.parametrize("placer, said, text, cards, blocked", [
    (clash_placer(TARGET), SAID, "합성 선반 깊이는 400mm 로 안내했어요", 1, {}),  # 부딪침 — 카드
    (FakePlacer(down=True), NEW_SAID, NEW_TEXT, 0, {"place_unavailable": 1}),  # 판정을 못 함 — 넣지도 카드도 없다
    (FakePlacer({"verdict": "maybe"}), NEW_SAID, NEW_TEXT, 0, {"place_unknown": 1}),  # 꼴이 틀린 답
    (FakePlacer(), NEW_SAID, "합성 선반 뒤 콘센트 자리는 37곳 타공한다고 안내한다", 0, {"numbers": 1}),  # 직원 답에 없는 숫자
])
def test_a_clash_is_a_card_and_an_unjudged_or_made_up_number_is_never_filed(admin, placer, said, text, cards, blocked):
    on(**{AUTO_FIELD: True})
    counts = _night(Judge(), [differs([handed("uc-5", reply=said)], text=text)], placer=placer)
    assert (counts["new"], counts["applied"], counts["cards"], counts["blocked"]) == (0, 0, cards, blocked)
    assert [c.item_type for c in changes()] == ["conflict"] * cards


def test_a_new_detail_also_closes_the_earlier_card_that_said_the_same(admin):
    on(**{AUTO_FIELD: True})
    run_clash(FakeAnthropic({"proposals": [differs([handed("uc-5", reply=NEW_SAID)], text=NEW_TEXT)]}))
    (card,) = changes()
    again = differs([handed("uc-6", reply=NEW_SAID)], text=NEW_TEXT, fixed_text="", repeats=[card.item_key])
    counts = _night(Judge(), [again], now=at(12, 1))
    assert (counts["new"], counts["cards"]) == (1, 0)
    db_session.refresh(card)
    assert (card.status, card.decided_action) == ("expired", MERGED_ACTION)


# ── 다른 말 전용 판정자(모델 길 — 합성 판정자 없이 가짜 두뇌로) ───────────────
def _verdict(client, cfg=None, **kw):
    from foms.services.cs_agent.handoff_learning_judge import differs_verdict
    from foms.services.cs_agent.settings import read_settings
    return differs_verdict(db_session, target_key=TARGET, title="합성 콘센트 자리 타공", text=NEW_TEXT,
                           cfg=read_settings(db_session, log=False) if cfg is None else cfg, now=NOW, client=client, **kw)


@pytest.mark.parametrize("answer, want", [
    ({"verdict": "adds", "why": "합성"}, "adds"),
    ({"verdict": "contradicts", "why": "합성"}, "contradicts"),
    ({"verdict": "maybe", "why": "합성"}, "unknown"),  # 정한 꼴이 아닌 답 — 카드로 둔다
])
def test_the_differs_judge_asks_one_way_with_the_target_on_the_learning_line(admin, answer, want):
    from foms.services.cs_agent import handoff_learning_judge as judge
    on(**{AUTO_FIELD: True})
    client = FakeAnthropic(answer)
    assert _verdict(client) == want
    (params,) = client.params
    assert (params["model"], params["output_config"]["effort"]) == (judge.MODEL, judge.EFFORT) == ("claude-sonnet-5-5", "medium")
    user = params["messages"][0]["content"]
    assert current_object(db_session, TARGET).text in user and NEW_TEXT in user  # 두뇌가 짚은 항목과 직원 말
    assert user.index("[회사 지식]") < user.index("[직원 말]")  # 한 방향
    spend = db_session.get(SystemSetting, "cs_agent_learning_spend")
    assert spend is not None and spend.setting_value.get("calls", 0) >= 1  # 학습 돈 줄(챗봇 돈 줄 아님)


def test_the_differs_judge_is_unavailable_without_a_learning_cap(admin):
    from foms.services.cs_agent.settings import read_settings
    on(**{AUTO_FIELD: True, "learning_cap_usd_panel": None})
    client = FakeAnthropic({"verdict": "adds", "why": "합성"})
    assert _verdict(client, cfg=read_settings(db_session, log=False)) == "unavailable" and client.params == []
