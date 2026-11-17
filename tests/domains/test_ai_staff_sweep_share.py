"""훑기 상한 나누기(D243) — 켜진 규칙마다 제 몫 먼저, 남은 자리는 내일 일 규칙부터.

운영 첫 밤(11-16)에 도면 담당 맡기기가 상한 30개 가운데 24개를 먼저 써 시공 잡기 11개가 다음 밤으로 밀렸다.
합성 주문 · 합성 협력사만. 바깥 호출 없음.
"""

from __future__ import annotations

from db import db_session
from foms.persistence.graft.models import AiAgentRun, ErpActionProposal
from foms.services.ai_staff import sweeps
from tests.domains.test_ai_staff_sweeps import (  # noqa: F401 - 픽스처도 함께 가져온다
    _construction_ready, _day, _levels, _order, _site, _sweep, proposers,
)


def test_each_rule_gets_its_share_before_a_backlog_takes_the_cap(proposers):
    """운영 첫 밤 — 앞 규칙(도면 담당 24개)이 상한을 먼저 써 시공 잡기 11개가 다음 밤으로 밀렸다. 규칙마다 제 몫이 먼저다."""
    _levels({"ops": {"send_measure_alimtalk": 0}})  # 켜진 규칙 둘(S1 · O3) — 운영과 같다
    for _ in range(5):
        _order("DRAWING", stage_days=3)
    for day in range(3):
        _order("PRODUCTION", partner=True, partner_intake={"requested_construction": {"date": _day(5 + day)}})
    first = _sweep(limit=4)
    assert (first.created, first.by_rule["O3"], first.by_rule["S1"]) == (4, 2, 2)
    second = _sweep(limit=4)  # 남은 자리는 후보가 남은 규칙이 쓴다 — 자리를 비워 두지 않는다
    assert (second.created, second.by_rule["O3"], second.by_rule["S1"]) == (4, 3, 1)
    runs = db_session.query(AiAgentRun).order_by(AiAgentRun.id).all()
    assert [(run.agent, run.proposals) for run in runs] == [("ops", 2), ("schedule", 2), ("ops", 3), ("schedule", 1)]
    assert {row.source_ref for row in db_session.query(ErpActionProposal)} == {str(run.id) for run in runs}


def test_leftover_room_goes_to_tomorrow_rules_first(proposers):
    """남은 자리는 오늘 밤을 놓치면 소용없는 규칙(내일 시공 안내)부터 — 밀린 일(도면 담당)은 다음 밤에도 만들 수 있다."""
    _construction_ready(proposers)
    _levels({"ops": {"send_measure_alimtalk": 0, "send_construction_alimtalk": 1}})
    # 켜진 규칙 셋(O3 · O4 · S1 — 몫 둘씩), S1 은 후보가 없어 두 자리가 남는다. 차례는 O3 이 O4 보다 앞이다
    for _ in range(6):
        _order("DRAWING", stage_days=3)
    for _ in range(4):
        _order("PRODUCTION", **_site(_day(1)))
    result = _sweep(limit=6)
    assert (result.created, result.by_rule["O4"], result.by_rule["O3"]) == (6, 4, 2)
    assert [rule.key for rule in sweeps.RULES.values() if rule.due] == ["O1", "O4"]


def test_a_rule_without_room_does_not_even_pick(proposers):
    """상한이 켜진 규칙 수보다 작으면 뒤 규칙은 후보도 고르지 않는다(실행 기록에 '건너뜀')."""
    _levels({"ops": {"send_measure_alimtalk": 0}})
    _order("DRAWING", stage_days=3)
    _order("PRODUCTION", partner=True, partner_intake={"requested_construction": {"date": _day(5)}})
    result = _sweep(limit=1)
    assert (result.created, result.by_rule["O3"], result.by_rule["S1"]) == (1, 1, 0)
    run = db_session.query(AiAgentRun).filter(AiAgentRun.agent == "schedule").one()
    assert [step["detail"] for step in run.steps] == ["한 번에 1개까지"] and run.outcome == "done"
