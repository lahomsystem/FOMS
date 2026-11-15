"""시공일 승인 뒤 손님 시공일 안내가 못 나갔을 때 — 다시 보내기 제안 하나(점검 2차 w6-08 · 설계서 2026-11-14-foms-graft 3.13).

- 시공 잡기 · 방문 옮기기(시공) 승인에서 시공일 쓰기는 됐고 같이 보낸 손님 안내(결과 ``customer_notice``)만 실패하면, 그 주문에
  '알림톡 보내기(시공일 안내)' 제안 하나를 열어 둔다 — 사람이 다시 승인해야 나간다(**자동으로 다시 보내지 않는다**).
- 겹침 열쇠는 훑기 규칙 O4 와 같다(할 일 + 주문 + 지금 시공일 — :func:`.construction_notice.scope`). 같은 실패로 제안이 여러 개
  쌓이지 않고(이미 열린 같은 제안이 있으면 그것을 알린다), O4 도 같은 날 제안을 또 만들지 않는다.
- ``FOMS_GRAFT_CONSTRUCTION_ALIMTALK`` 가 꺼져 있으면 아무것도 하지 않는다(그때는 같이 보내 보지도 않는다 — 결과가 지금과 같다).
- 제안한 직원은 운영 AI(O4 의 주인), 출처는 ``proposal``(그 시공일 제안 번호). 사람이 이미 승인한 일의 뒷일이라 AI 직원 수준 표를
  보지 않는다(:func:`.lifecycle._level_check`).
- 승인한 사람에게는 '시공일은 잡았고 안내는 못 보냈어요 — 다시 보내기 제안을 남겼어요'. 만들기가 실패해도 승인 결과는 그대로(로그엔
  번호 · 예외 이름만).
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Callable, Optional

from foms.persistence.graft.models import ErpActionProposal
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_actions import preview as fns
from foms.services.erp_actions.registry import SOURCE_PROPOSAL, STATUS_FAILED, STATUS_OPEN, dedupe_key
from foms.services.erp_actions.runners import OUTCOME_EXECUTED, RunOutcome, RunRequest
from foms.services.erp_ontology.read import order_key
from foms.services.graft_flags import enabled_global
from models import Order

logger = logging.getLogger(__name__)

__all__ = ["ACTION", "PROPOSER", "REASON", "leave", "wanted"]

ACTION = "send_construction_alimtalk"
PROPOSER = "agent:ops"
REASON = "시공일을 승인했는데 손님 시공일 안내 알림톡이 못 나갔어요 — 승인하면 다시 보내요."
_LEFT = {"schedule_construction": "시공일은 잡았고 안내는 못 보냈어요 — 다시 보내기 제안을 남겼어요.",
         "move_construction": "시공일은 옮겼고 안내는 못 보냈어요 — 다시 보내기 제안을 남겼어요."}


def wanted(action: str, outcome: RunOutcome) -> bool:
    """시공일 두 할 일이 실행됐는데 같이 보낸 손님 안내가 못 나갔고 시공일 안내 스위치가 켜져 있나."""
    notice = outcome.result.get("customer_notice") if outcome.status == OUTCOME_EXECUTED else None
    return (action in _LEFT and isinstance(notice, dict) and notice.get("sent") is False
            and enabled_global("construction_alimtalk"))


def _open_one(session: Any, order: Any) -> Optional[int]:
    """같은 열쇠(지금 시공일)로 이미 열린 · 실패한 다시 보내기 제안 번호(없으면 ``None``)."""
    key = dedupe_key(ACTION, int(order.id), {}, fns.scope(ACTION, order))
    return session.query(ErpActionProposal.id).filter(
        ErpActionProposal.order_id == int(order.id), ErpActionProposal.dedupe_key == key,
        ErpActionProposal.status.in_((STATUS_OPEN, STATUS_FAILED))).scalar()


def leave(session: Any, request: RunRequest, outcome: RunOutcome, propose: Callable[..., Any]) -> RunOutcome:
    """다시 보내기 제안을 열어 두고(같은 것이 이미 열려 있으면 그것) 승인한 사람에게 보일 말을 바꾼다 — 스스로 커밋한다.

    Args:
        session: 승인 세션(시공일 쓰기는 이미 커밋됐다). request: 승인한 시공일 제안의 실행 재료.
        outcome: 실행기 결과(:func:`wanted` 가 참). propose: :func:`.lifecycle.propose`(층 순환을 피해 받는다).

    Returns:
        말 · 결과(``notice_retry`` — 다시 보내기 제안 번호)를 바꾼 결과. 남기지 못했으면 받은 결과 그대로.
    """
    try:
        order = session.get(Order, request.order_id)
        row = propose(session, action=ACTION, proposed_by=PROPOSER, order=order, params={}, reason=REASON,
                      evidence=[{"kind": "order", "ref": order_key(int(order.id)), "label": f"주문 #{order.id}"}],
                      source_kind=SOURCE_PROPOSAL, source_ref=str(request.proposal_id), level=1,
                      now=request.now or now_utc_naive())
        found = row.id if row is not None else _open_one(session, order)
        session.commit()
    except Exception as exc:  # noqa: BLE001 — 다시 보내기 제안이 못 생겨도 시공일 승인 결과는 그대로(로그엔 번호 · 예외 이름만)
        session.rollback()
        logger.warning("[ERP-ACTION] 시공일 안내 다시 보내기 제안 못 만듦 proposal=%s error=%s", request.proposal_id,
                       type(exc).__name__)
        return outcome
    if found is None:
        return outcome
    return dataclasses.replace(outcome, message=_LEFT[request.action], result={**outcome.result, "notice_retry": found})
