"""STATE-QUEST-01: quest 승인 → stage 전이 오케스트레이션.

quest 최종 승인이 stage 전이를 유발하는 **유일한 경로**를 정본화한다(§5.2·report §line 320,
330-331):

* RECEIVED/MEASURE/CONFIRM 최종 승인 → :mod:`order_transition_service` 로 다음 stage 전이
  (``REQUEST_MEASUREMENT``: RECEIVED→MEASURE, fresh MEASURE quest; ``COMPLETE_MEASUREMENT``:
  MEASURE→DRAWING, DRAWING quest 미생성; ``CUSTOMER_CONFIRM``: CONFIRM→PRODUCTION,
  PRODUCTION quest 미생성).
* DRAWING 은 전용 command(도면 transfer·수령 확정)로만 전이 — standalone quest 승인 전이는
  거부(``STAGE_COMMAND_REQUIRED`` 409).
* PRODUCTION/CONSTRUCTION/CS quest 승인은 prerequisite 만 기록하고 stage 를 쓰지 않는다(no-op).
* CONFIRM 이 PRODUCTION quest 를 만들지 않는 이유: 생산 quest 는 팀 승인(PRODUCTION) 모드라
  ``foms/api/production/orders.py`` 의 제작 완료 게이트(``_stage_quest_block(sd, "PRODUCTION")``)
  가 '생산팀 승인' 뒤로 잠기는데, 생산 보드에는 그 승인 버튼이 없다. 2026-09-17 전에는
  CONFIRM 이 command 전용 집합에 남아 "승인도 못 하고 생산으로도 못 가는" 막다른 골목이었다
  (운영 #5193) — 이제 CONFIRM 최종 승인이 곧 ``CUSTOMER_CONFIRM`` 전이다.

전이는 :func:`~foms.services.orders.order_transition_service.transition_order` 를 경유한다
(엔진 무편집·재구현 금지). ``session.commit()`` 은 **호출자 소유**(REV-00). 승인 **권한** 판정은
AUTH-QUEST-01(quest approve route) 몫이며 이 모듈은 **전이만** 한다 — models·마이그레이션·
order_mutation_policy 는 건드리지 않는다.
"""
from __future__ import annotations

import copy
import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE, STAGE_LABELS
from foms.services.orders.erp_policy_data_access import get_stage
from foms.services.orders.erp_policy_quests import (
    check_quest_approvals_complete,
    create_quest_from_template,
)
from foms.services.orders.order_transition_service import (
    TransitionError,
    TransitionResult,
    transition_order,
)
from models import Order


class StandaloneStageAdvanceError(TransitionError):
    """DRAWING 을 standalone quest 승인으로 전이하려는 시도 — 전용 command 필요(409)."""

    status_code = 409
    error_code = "STAGE_COMMAND_REQUIRED"


class QuestIncompleteError(TransitionError):
    """현 stage quest 가 존재하나 필수 승인이 미완 — 최종 승인 전이라 전이 거부(409)."""

    status_code = 409
    error_code = "QUEST_INCOMPLETE"


class OrderNotFoundError(TransitionError):
    """전이 대상 order 가 없음(404)."""

    status_code = 404
    error_code = "ORDER_NOT_FOUND"


# stage(영문 코드) → (transition command, expected_from, target_value, 다음 stage quest 생성 여부).
# RECEIVED/MEASURE/CONFIRM 최종 승인만 stage 전이를 유발한다. DRAWING 은 _COMMAND_REQUIRED_STAGES,
# 나머지(PRODUCTION/CONSTRUCTION/CS/…)는 이 map 에 없어 prerequisite-only(no-op)로 처리된다.
#   RECEIVED→MEASURE: fresh MEASURE quest 생성(report line 330).
#   MEASURE→DRAWING: DRAWING quest 미생성 — DRAWING 은 command 전용(report line 331).
#   CONFIRM→PRODUCTION: PRODUCTION quest 미생성 — 만들면 생산 보드의 제작 완료 게이트
#     (production/orders.py _stage_quest_block(sd, "PRODUCTION")) 가 없는 승인 버튼 뒤로 잠긴다.
_STAGE_ADVANCE: Dict[str, Tuple[str, str, str, bool]] = {
    "RECEIVED": ("REQUEST_MEASUREMENT", "RECEIVED", "MEASURE", True),
    "MEASURE": ("COMPLETE_MEASUREMENT", "MEASURE", "DRAWING", False),
    "CONFIRM": ("CUSTOMER_CONFIRM", "CONFIRM", "PRODUCTION", False),
}

# 전용 command(도면 transfer·수령 확정)로만 전이하는 stage — standalone 승인 전이 거부.
_COMMAND_REQUIRED_STAGES = frozenset({"DRAWING"})


def stage_advance_target(stage_code: Optional[str]) -> Optional[str]:
    """``stage_code`` 의 quest 최종 승인이 옮겨 갈 다음 stage 코드. 옮기지 않으면 None.

    표시 계층(승인 버튼 문구)이 "다음 단계로 넘어간다"를 약속해도 되는지 판정하는 SSOT.
    :data:`_STAGE_ADVANCE` 를 그대로 읽으므로 전이 규칙과 문구가 갈라지지 않는다.

    :param stage_code: 영문 stage 코드(``MEASURE`` 등). None/미등록이면 None.
    :returns: 다음 stage 코드 또는 None(prerequisite-only·command 전용·미등록).
    """
    advance = _STAGE_ADVANCE.get(stage_code) if stage_code else None
    return advance[2] if advance else None


def is_command_required_stage(stage_code: Optional[str]) -> bool:
    """``stage_code`` 가 전용 command 로만 전이하는 단계(DRAWING)면 True.

    이 단계에서 quest approve API 는 409 ``COMMAND_REQUIRED`` 로 거부한다 — 표시 계층은
    승인 버튼 자체를 그리지 않아야 막다른 길이 생기지 않는다.
    """
    return stage_code in _COMMAND_REQUIRED_STAGES


def _find_stage_quest(
    sd: Dict[str, Any], stage: Optional[str], stage_code: str
) -> Optional[Dict[str, Any]]:
    """현 stage 의 quest dict 를 찾는다(영문 코드/한글명 모두 매칭). 없으면 None."""
    quests = sd.get("quests")
    if not isinstance(quests, list):
        return None
    # SSOT(check_quest_approvals_complete)와 같은 별칭 집합 — 한글 저장형('고객컨펌')을
    # 코드('CONFIRM')로 찾을 때 놓치면 '없음 → True' 로 새어 나간다(2026-09-20 P2).
    aliases = {
        stage, stage_code, STAGE_LABELS.get(stage_code, ""),
        STAGE_NAME_TO_CODE.get(stage or "", ""), STAGE_NAME_TO_CODE.get(stage_code, ""),
    } - {"", None}
    for quest in quests:
        if isinstance(quest, dict) and quest.get("stage") in aliases:
            return quest
    return None


def find_stage_quest_for_approve(
    sd: Dict[str, Any], stage_name: Optional[str], stage_code: str
) -> Tuple[Optional[Dict[str, Any]], int]:
    """승인 라우트가 잡을 현 단계 quest 와 원본 ``quests`` 인덱스. 없으면 ``(None, -1)``.
    같은 단계 quest 가 여럿(강제 단계 변경 뒤 COMPLETED 옆에 새 OPEN 등)이면 표시 SSOT
    (``erp_quest_display.resolve_current_quest``)와 같은 규칙 — (1) OPEN/IN_PROGRESS 중 created_at·
    updated_at 최신, (2) 없으면 COMPLETED 중 completed_at·updated_at·created_at 최신, (3) 그 밖은 첫
    일치. 화면이 버튼을 그린 quest 를 서버도 잡아야 재전이로 잘못 빠지지 않는다(2026-09-20 리뷰 P2).
    """
    quests = sd.get("quests") if isinstance(sd.get("quests"), list) else []
    aliases = {
        stage_name, stage_code, STAGE_LABELS.get(stage_code, ""),
        STAGE_NAME_TO_CODE.get(stage_name or "", ""), STAGE_NAME_TO_CODE.get(stage_code, ""),
    } - {"", None}
    matched = [(i, q) for i, q in enumerate(quests) if isinstance(q, dict) and q.get("stage") in aliases]
    status_of = lambda q: str(q.get("status", "OPEN")).upper()
    active = [(i, q) for i, q in matched if status_of(q) in ("OPEN", "IN_PROGRESS")]
    done = [(i, q) for i, q in matched if status_of(q) == "COMPLETED"]
    if active:  # max 는 동률이면 앞선 것 — 표시 SSOT 의 안정 정렬(reverse=True)과 같은 답이다.
        i, q = max(active, key=lambda iq: iq[1].get("created_at") or iq[1].get("updated_at")
                   or "1970-01-01T00:00:00")
    elif done:
        i, q = max(done, key=lambda iq: iq[1].get("completed_at") or iq[1].get("updated_at")
                   or iq[1].get("created_at") or "1970-01-01T00:00:00")
    else:
        i, q = matched[0] if matched else (-1, None)
    return q, i


def _stage_quest_complete(sd: Dict[str, Any], stage: Optional[str], stage_code: str) -> bool:
    """현 stage quest 가 (a) 아예 없거나 (b) 최종 승인 완료면 True(전이 허용), 미완이면 False.

    quest 자체가 없으면 게이트하지 않는다(레거시/backfill 미완 lock-out 방지, STATE-PROD 선례).
    완료 판정은 :func:`check_quest_approvals_complete` (판정 SSOT — status COMPLETED·assignee·
    team 모드를 모두 안다) 한 곳에 위임한다. 여기서 모드를 다시 가르지 않는다.

    Args:
        sd: 대상 order 의 structured_data.
        stage: workflow.stage 원문(영문 코드 또는 한글명일 수 있음).
        stage_code: 정규화된 영문 stage 코드.

    Returns:
        전이해도 되면 True(quest 없음 또는 완료), 존재하나 미완이면 False.
    """
    quest = _find_stage_quest(sd, stage, stage_code)
    if quest is None:
        return True
    return check_quest_approvals_complete(sd, stage_code)[0]


def _append_next_stage_quest(
    order: Order, target_stage_code: str, actor_user_id: int
) -> None:
    """전이 직후 같은 tx 에서 다음 stage 의 fresh quest 를 structured_data 에 추가한다.

    ``create_quest_from_template`` 재사용(dynamic team 규칙 포함). 템플릿이 없으면 no-op.

    Args:
        order: 전이 완료된 order(structured_data 에 새 stage 반영됨).
        target_stage_code: 새 stage 영문 코드(예: ``MEASURE``).
        actor_user_id: 전이 actor(quest owner_person hint).
    """
    sd = copy.deepcopy(order.structured_data or {})
    new_quest = create_quest_from_template(target_stage_code, str(actor_user_id or ""), sd)
    if not new_quest:
        return
    quests = sd.get("quests")
    if not isinstance(quests, list):
        quests = []
    quests.append(new_quest)
    sd["quests"] = quests
    order.structured_data = sd
    flag_modified(order, "structured_data")


def advance_stage_on_quest_completion(
    session: Session,
    *,
    order_id: int,
    actor_user_id: int,
    scope_hash: str,
    request_hash: str,
    expected_version: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    reason: Optional[str] = None,
    source_screen: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> Optional[TransitionResult]:
    """현 stage quest 의 최종 승인이 stage 전이를 유발하면 :func:`transition_order` 로 전이한다.

    RECEIVED/MEASURE/CONFIRM 만 stage 를 advance 한다(다음 stage 로 canonical 전이 + 필요 시
    fresh quest). DRAWING 은 전용 command 전용이라 standalone 전이를 거부하고, 그 밖의 stage
    (PRODUCTION/CONSTRUCTION/CS/…)는 prerequisite-only 라 stage 를 쓰지 않는다(None). 전이는
    order_transition_service 경유이며 version bump·receipt·legacy OrderEvent·tx내 outbox 는
    엔진이 원자 보장한다. ``session.commit()`` 은 호출자 소유(REV-00).

    Args:
        session: business transaction 세션(호출자 소유, 커밋 미수행).
        order_id: 전이 대상 Order id.
        actor_user_id: 요청 actor(event/receipt author, fresh quest owner hint).
        scope_hash: 요청 scope sha256 hex(receipt 저장).
        request_hash: 요청 payload sha256 hex(same-key/different-hash 감지).
        expected_version: If-Match mutation_version. None 이면 precondition 없음.
        idempotency_key: UUID 문자열(≤64자) 또는 None(같은 key replay 는 전이/side-effect 없음).
        reason: 전이 사유(event payload 보존, 선택).
        source_screen: 요청 화면(event payload 보존, 선택).
        now: 테스트용 시각 주입(기본 now_utc_naive()).

    Returns:
        stage 를 advance 했으면 :class:`TransitionResult`, prerequisite-only stage 면 None.

    Raises:
        OrderNotFoundError: order_id 미존재(404).
        StandaloneStageAdvanceError: stage 가 DRAWING(전용 command 필요, 409).
        QuestIncompleteError: 현 stage quest 가 존재하나 미완(409).
        TransitionError/RevisionError: 전이 엔진/REV helper 예외 전파.
    """
    order = session.get(Order, order_id)
    if order is None:
        raise OrderNotFoundError(f"order {order_id} not found.")

    sd = order.structured_data or {}
    stage = get_stage(sd)
    stage_code = STAGE_NAME_TO_CODE.get(stage, stage) if stage else None

    if stage_code in _COMMAND_REQUIRED_STAGES:
        raise StandaloneStageAdvanceError(
            f"{stage_code} 단계는 standalone quest 승인이 아니라 전용 command 로만 전이합니다."
        )

    advance = _STAGE_ADVANCE.get(stage_code) if stage_code else None
    if advance is None:
        # prerequisite-only(PRODUCTION/CONSTRUCTION/CS/…): stage 를 쓰지 않는다.
        return None

    if not _stage_quest_complete(sd, stage, stage_code):
        raise QuestIncompleteError(
            f"{stage_code} 단계 quest 의 필수 승인이 완료되지 않아 전이할 수 없습니다."
        )

    command_id, expected_from, target_value, make_next_quest = advance
    result = transition_order(
        session,
        command_id=command_id,
        order_id=order_id,
        actor_user_id=actor_user_id,
        expected_from=expected_from,
        target_value=target_value,
        scope_hash=scope_hash,
        request_hash=request_hash,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        reason=reason,
        source_screen=source_screen,
        now=now,
    )
    if make_next_quest and not result.replayed:
        _append_next_stage_quest(order, target_value, actor_user_id)
    return result


__all__ = [
    "StandaloneStageAdvanceError",
    "QuestIncompleteError",
    "OrderNotFoundError",
    "advance_stage_on_quest_completion",
    "find_stage_quest_for_approve",
    "stage_advance_target",
    "is_command_required_stage",
]
