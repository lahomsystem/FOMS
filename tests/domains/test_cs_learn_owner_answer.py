"""넘긴 상담 배우기 × ③ 사장님 답(설계서 2026-11-26 온톨로지 잇기 3.2 · 카드 비평 S5 · S1).

- 판정자의 '사장님이 이미 정한 것' 줄: 사장님이 답과 함께 적은 글이 있으면 그 글(그때 직원 말 없이), 없으면 직원 말 → 답 이름.
  날짜 창 없이 대상 키로 찾고(두 달 지난 답도) 줄 수 상한은 그대로. 대조군: 다른 키.
- 사장님이 답으로 정한 지식은 사람 없는 길 둘을 타지 않는다 — 서로 다른 손님 둘의 다른 말은 바로 고치지 않고 판정자에게(멈춘 수
  ``owner_redo``), 판정이 '더함'이어도 바로 반영하지 않고 승인 대기에. 대조군: 되돌려 다시 연 카드면 예전처럼 바로 고친다.
합성 판정자(:class:`tests.support.cs_agent_fakes.FakePlacer`)와 가짜 두뇌만(네트워크 0). 손님 글 · 직원 이름 · 금액 없음.
"""

from __future__ import annotations

import datetime

from db import db_session
from foms.services.brain import question_answer as qa
from foms.services.brain.decide import reopen_decision
from foms.services.brain.proposals import Proposer, propose_create
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import handoff_learning_owner as owner
from foms.services.cs_agent import handoff_learning_place as place
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_handoff_learning import NOW, admin, changes, handed, on  # noqa: F401 — admin 은 fixture
from tests.domains.test_cs_learn_everything import FIXED, SAID, TARGET, differs, run_clash
from tests.domains.test_cs_learn_place import ADDED, _night, _one
from tests.support.brain_support import REASON, values
from tests.support.cs_agent_fakes import FakeAnthropic, FakePlacer, at, keys, naive  # noqa: F401 — keys 는 fixture

#: 직원이 같은 뜻을 다른 말로 한 것(글자 비슷함 관문을 비켜 가는 말 — S1 의 길).
PARAPHRASE = "합성 깊은 선반은 사백으로 짠다고 했다"
OWNER_TEXT = "합성 선반 깊이는 380mm 입니다"
ANSWERED_AT = at(11, 9)


def _card():
    """밤 배우기가 올린 엇갈림 카드 하나(대상 :data:`TARGET`)."""
    run_clash(FakeAnthropic({"proposals": [differs([handed("uc-5", reply=SAID)])]}))
    (card,) = changes()
    return card


def _answer(admin, card, code, text=None, when=ANSWERED_AT):  # noqa: F811
    got = qa.answer_question(db_session, card.id, actor=admin, code=code, text=text,
                             base_version=current_object(db_session, TARGET).version, now=naive(when))
    db_session.commit()
    return got


def _spy(monkeypatch):
    """넣기 결과(:func:`foms.services.cs_agent.handoff_learning_route.file_proposals`)를 밤 요약이 칸을 빼기 전에 받아 둔다."""
    got, real = {}, hl.file_proposals

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        got.update(out)
        return out

    monkeypatch.setattr(hl, "file_proposals", spy)
    return got


# ── 판정자에게 싣는 '사장님이 이미 정한 것'(S5) ──────────────────────────
def test_the_owners_own_words_reach_the_judge_instead_of_the_staffs_old_words(admin):  # noqa: F811
    on(**{AUTO_FIELD: True})
    card = _card()
    _answer(admin, card, "outside_right", OWNER_TEXT)
    assert current_object(db_session, TARGET).text == OWNER_TEXT
    placer = FakePlacer(lambda request: {"verdict": "decided" if request["decided"] else "new", "target": TARGET})
    counts = _night([differs([handed("uc-6", reply=SAID)], text=PARAPHRASE)], placer, now=at(12, 1))
    (line,) = placer.requests[0]["decided"]
    assert line == f"- [{TARGET}] 사장님이 적은 글: {OWNER_TEXT}"
    assert "400mm" not in line and "→" not in line  # 그때 직원 말 · 답 이름은 싣지 않는다
    assert counts["decided"] == 1


def test_decided_lines_find_old_answers_by_key_and_keep_the_line_cap(admin):  # noqa: F811
    on(**{AUTO_FIELD: True})
    target = current_object(db_session, TARGET)
    old = naive(at(12, 1)) - datetime.timedelta(days=60)  # 30일 창이었다면 빠졌을 답
    for n in range(place.MAX_DECIDED + 2):
        card = propose_create(db_session, key=f"conflict/lahom-synth-old-{n}", brand="LAHOM", layer=target.layer,
                              item_type="conflict", reason=REASON, proposer=Proposer.user(admin.id), now=old, known="",
                              values=values(f"합성 옛 엇갈림 {n}", text=f"승인된 규칙과 다름\n합성 옛 직원 말 {n}",
                                            payload={"target": TARGET, "target_version": target.version}),
                              evidence=["plan:synth#c1", f"about:{TARGET}"])
        qa.answer_question(db_session, card.id, actor=admin, code="knowledge_right",
                           now=old + datetime.timedelta(minutes=n + 1))
    db_session.commit()
    lines = place.decided_lines(db_session, [TARGET], at(12, 1))
    assert len(lines) == place.MAX_DECIDED  # 줄 수 상한은 그대로
    assert lines[0] == f"- [{TARGET}] 합성 옛 직원 말 {place.MAX_DECIDED + 1} → 회사 지식이 맞아요"  # 새 것부터
    assert place.decided_lines(db_session, ["lahom/synth-other"], at(12, 1)) == []  # 대조군 — 다른 지식


# ── 사장님이 정한 지식은 사람 없는 길로 다시 안 바꾼다(S1) ────────────────
def test_two_customers_do_not_fix_what_the_owner_decided_the_judge_sees_it(admin, monkeypatch):  # noqa: F811
    on(**{AUTO_FIELD: True})
    _answer(admin, _card(), "knowledge_right")
    before = current_object(db_session, TARGET)
    assert owner.owner_decided(db_session, TARGET) and not owner.owner_decided(db_session, "lahom/synth-other")
    got = _spy(monkeypatch)
    placer = FakePlacer(lambda request: {"verdict": "decided" if request["decided"] else "new", "target": TARGET})
    counts = _night([differs([handed("uc-6", reply=SAID), handed("uc-7", reply=SAID)], text=PARAPHRASE)], placer,
                    now=at(12, 1))
    assert (counts["fixed"], counts["applied"], counts["decided"]) == (0, 0, 1)
    assert current_object(db_session, TARGET).version == before.version and len(placer.requests) == 1
    assert got[owner.OWNER_REDO] == 1  # '사장님이 정한 대상이라 멈춤'을 가르는 칸


def test_a_reopened_answer_no_longer_holds_the_fix(admin, monkeypatch):  # noqa: F811
    """대조군 — 방금 정한 것 되돌리기로 다시 연 카드는 '사장님이 정한 것'이 아니다: 예전처럼 바로 고친다."""
    on(**{AUTO_FIELD: True})
    card = _card()
    _answer(admin, card, "knowledge_right")
    reopen_decision(db_session, card.id, actor=admin, now=naive(ANSWERED_AT) + datetime.timedelta(minutes=1))
    db_session.commit()
    assert not owner.owner_decided(db_session, TARGET)
    got = _spy(monkeypatch)
    placer = FakePlacer()
    counts = _night([differs([handed("uc-6", reply=SAID), handed("uc-7", reply=SAID)], text=PARAPHRASE)], placer,
                    now=at(12, 1))
    assert (counts["fixed"], counts["applied"]) == (1, 1) and current_object(db_session, TARGET).text == FIXED
    assert placer.requests == [] and owner.OWNER_REDO not in got


def test_adds_to_what_the_owner_decided_waits_for_a_person(admin, monkeypatch):  # noqa: F811
    on(**{AUTO_FIELD: True})
    _answer(admin, _card(), "both_right", "합성 벽이 약하면 받침을 한 줄 더 넣는다")
    before = current_object(db_session, TARGET)
    got = _spy(monkeypatch)
    placer = FakePlacer({"verdict": "adds", "target": TARGET, "added": ADDED})
    counts = _night([_one()], placer, judge=lambda *_a: True, now=at(12, 1))
    assert (counts["added"], counts["applied"]) == (1, 0)  # 넣되 바로 반영하지 않는다
    change = changes()[-1]
    assert (change.op, change.item_key, change.status) == ("update", TARGET, "open")  # 승인 대기 — 사람이 넣는다
    assert current_object(db_session, TARGET).version == before.version
    assert got[owner.OWNER_REDO] == 1


def test_auto_unless_owner_only_holds_edits_of_decided_knowledge(admin):  # noqa: F811
    on(**{AUTO_FIELD: True})
    _answer(admin, _card(), "knowledge_right")
    auto = object()

    class Change:
        def __init__(self, op, key):
            self.op, self.item_key = op, key

    assert owner.auto_unless_owner(db_session, Change("update", TARGET), auto) == (None, True)
    assert owner.auto_unless_owner(db_session, Change("update", "lahom/synth-other"), auto) == (auto, False)
    assert owner.auto_unless_owner(db_session, Change("create", TARGET), auto) == (auto, False)  # 새 지식은 막지 않는다
    assert owner.auto_unless_owner(db_session, Change("update", TARGET), None) == (None, False)  # 바로 반영 꺼짐
