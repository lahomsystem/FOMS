"""꺼진 규칙 거두기(D245) — 수준을 0 으로 내린 규칙이 훑기로 만든 열린 제안을 밤 훑기가 '낡은 것'으로 닫는다.

도면 담당은 도면팀이 스스로 나누고 협력사 시공일은 출고 담당이 출고 스케줄을 보고 조율한다 — 두 제안을 끈 날 운영에 열린 제안
43개가 남아 있었다(승인할 수 없는 카드가 기간이 끝날 때까지 보인다). 합성 주문 · 합성 협력사만. 바깥 호출 없음.
"""

from __future__ import annotations

from db import db_session
from foms.persistence.graft.models import AiAgentRun, ErpActionProposal
from models import SystemSetting
from tests.domains.test_ai_staff_sweeps import (  # noqa: F401 - 픽스처도 함께 가져온다
    _day, _levels, _order, _sweep, proposers,
)


def _status(order_id: int, action: str) -> list[str]:
    rows = db_session.query(ErpActionProposal).filter(ErpActionProposal.order_id == order_id,
                                                      ErpActionProposal.action == action)
    return sorted(row.status for row in rows)


def test_a_rule_turned_off_withdraws_only_its_own_open_sweep_proposals(proposers):
    open_one, from_chat, rejected = (_order("DRAWING", stage_days=3) for _ in range(3))
    partner = _order("PRODUCTION", partner=True, partner_intake={"requested_construction": {"date": _day(5)}})
    assert _sweep().created == 4
    rows = {row.order_id: row for row in db_session.query(ErpActionProposal)}
    rows[from_chat.id].source_kind = "cs_turn"  # 상담에서 나온 제안 — 훑기 것이 아니다
    rows[rejected.id].status = "rejected"  # 사람이 이미 결정한 것
    db_session.commit()

    _levels({"ops": {"assign_draftsman": 0}})
    result = _sweep()
    assert (result.created, result.withdrawn, result.by_rule["O3"]) == (0, {"O3": 1}, 0)
    assert _status(open_one.id, "assign_draftsman") == ["superseded"]
    assert _status(from_chat.id, "assign_draftsman") == ["open"]
    assert _status(rejected.id, "assign_draftsman") == ["rejected"]
    assert _status(partner.id, "schedule_construction") == ["open"]  # 켜진 규칙의 제안은 그대로
    run = db_session.query(AiAgentRun).filter(AiAgentRun.agent == "ops").order_by(AiAgentRun.id.desc()).first()
    assert ("열린 제안 닫기 — O3", "닫음 1개") in [(step["what"], step["detail"]) for step in run.steps]

    again = _sweep()  # 닫을 것이 없으면 단계도 없다
    assert again.withdrawn == {}
    run = db_session.query(AiAgentRun).filter(AiAgentRun.agent == "ops").order_by(AiAgentRun.id.desc()).first()
    assert not [step for step in run.steps if step["what"].startswith("열린 제안 닫기")]


def test_turning_the_rule_back_on_proposes_again(proposers):
    """거둔 것은 거절이 아니다 — 다시 켜면 그 밤부터 새로 만든다."""
    order = _order("DRAWING", stage_days=3)
    assert _sweep().by_rule["O3"] == 1
    _levels({"ops": {"assign_draftsman": 0}})
    assert _sweep().withdrawn == {"O3": 1}
    row = db_session.query(SystemSetting).one()
    row.setting_value = {"ops": {"assign_draftsman": 2}}
    db_session.commit()
    assert _sweep().by_rule["O3"] == 1
    assert _status(order.id, "assign_draftsman") == ["open", "superseded"]
