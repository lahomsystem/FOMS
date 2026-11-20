"""AS 접수 취소 — 잘못 접수한 현재 건(접수 상태)을 걷어 낸다.

설계서 ``docs/specs/2026-11-20-multi-item-split-schedule_SPEC.md`` §4.4 (결정 M9 ~ M12).

지금까지는 잘못 접수한 AS 를 지울 길이 없어 단계 강제 변경으로 주문 상태의 AS 표시만 덮었다 — AS 건은 열린 채
남았다(운영 5687). 이 명령은 그 건을 통째로 걷어 낸다.

* 현재 건이 **접수(RECEIVED)** 일 때만. 처리 중 · 완료는 취소가 아니다.
* 건은 ``as_lifecycle.cycles[]`` 에서 빼 ``cancelled_cycles[]`` 로 옮긴다. 순번 · 지난 건을 세는 곳이 모두
  ``cycles[]`` 자리 순서를 쓰므로, 남겨 두면 다음 접수가 "2번째 AS"가 되고 잘못 접수한 건이 지난 건으로 뜬다.
* 그 건 번호가 찍힌 기록 줄은 지우지 않고 가림 표시만 한다(원문 · 첨부는 분쟁 근거로 남는다).
* 열린 AS 도면 요청(차수 상태 WAITING · IN_PROGRESS · TRANSFERRED · RETURNED)이 그 건에 걸려 있으면 막는다 —
  도면팀이 그리는 중인 요청이 주인 없는 차수로 남지 않게 먼저 닫게 한다.
* 되돌리지 못하는 것: 접수가 덮은 시공자 칸(``shipment.construction_workers``)과 상차일. 스냅샷이 없다.

원자성 · 상태 글 재계산 · 이벤트는 다른 AS 명령과 같은 틀(``as_cycle_service._run_as_command``)을 탄다.
``session.commit()`` 은 호출자 소유.
"""
from __future__ import annotations

import copy
import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.as_cycle_service import (
    AS_NONE,
    AS_RECEIVED,
    CLASSIFICATION_FIELDS,
    POLICY_AS_CANCEL,
    ASCycleError,
    _MAX_REASON,
    _append_transition,
    _apply_classification_projection,
    _apply_visit_projection,
    _lifecycle,
    _require_text,
    _run_as_command,
    clear_as_status_text,
    current_cycle,
    cycle_status,
)
from foms.services.orders.as_drawing import current_round as current_drawing_round
from foms.services.orders.as_log import append_system_log, current_reception_entry
from foms.services.orders.as_schedule_link import clear_link
from foms.services.orders.revision import MutationResult
from models import Order

EVENT_AS_CANCELLED = "AS_CANCELLED"
#: 취소한 건을 옮겨 두는 자리(``as_lifecycle`` 아래).
CANCELLED_CYCLES_KEY = "cancelled_cycles"
#: 가림 표시한 기록 줄에 남기는 까닭.
LOG_HIDDEN_REASON = "AS_CANCEL"
NOT_RECEIVED_MESSAGE = "접수 상태인 AS 만 취소할 수 있습니다. 처리 중이거나 완료된 AS 는 취소할 수 없어요."
DRAWING_OPEN_MESSAGE = "열려 있는 AS 도면 요청이 있어 취소할 수 없습니다. 도면 요청을 먼저 닫아 주세요."


def open_drawing_round_blocks(sd: Dict[str, Any], cycle_id: str) -> bool:
    """그 AS 건에 열린 AS 도면 요청이 걸려 있는가.

    "열림" = ``as_drawing.current_round_id`` 가 가리키는 차수의 상태가 WAITING · IN_PROGRESS · TRANSFERRED ·
    RETURNED(``as_drawing.OPEN_STATUSES``). CONFIRMED · CANCELLED 는 닫힌 차수다. 차수가 어느 건에 묶였는지
    모르면(``cycle_id`` 없음) 이 건의 것으로 본다 — 다른 건에 묶인 것이 분명할 때만 막지 않는다.
    """
    rnd = current_drawing_round(sd)
    if rnd is None:
        return False
    return str(rnd.get("cycle_id") or cycle_id) == str(cycle_id)


def _hide_cycle_log_lines(sd: Dict[str, Any], cycle_id: str, *, actor_name: str, now_iso: str) -> int:
    """그 건 번호가 찍힌 기록 줄에 가림 표시를 한다(원문은 그대로). 가린 줄 수를 돌려준다."""
    hidden = 0
    for entry in (sd.get("shipment") or {}).get("as_log") or []:
        if not isinstance(entry, dict) or entry.get("deleted") is True:
            continue
        if str(entry.get("cycle_id") or "") != cycle_id:
            continue
        entry["deleted"] = True
        entry["deleted_at"] = now_iso
        entry["deleted_by"] = actor_name or "시스템"
        entry["deleted_reason"] = LOG_HIDDEN_REASON
        hidden += 1
    return hidden


def _restore_shipment_projection(sd: Dict[str, Any], order: Order, prev: Optional[Dict[str, Any]]) -> None:
    """주문당 한 칸인 AS 투영을 남은 건(없으면 빈 값)으로 되돌린다 — 접수 글 · 방문일 · 분류 · 비용."""
    shipment = sd.setdefault("shipment", {})
    reception = current_reception_entry(sd) if prev is not None else None
    shipment["as_content"] = str(
        (reception or {}).get("text") or (prev or {}).get("initial_content") or "")
    # 방문일 칸은 주문당 하나라 취소한 건의 값이다(새 건 접수가 직전 건 방문일을 이미 비웠다).
    clear_link(sd)
    _apply_visit_projection(sd, order, None, None)
    sd["schedule"]["as_visit"].pop("shipment_recommendation", None)
    if prev is not None:
        _apply_classification_projection(sd, prev)
    else:
        for field in CLASSIFICATION_FIELDS:
            shipment[field] = False
    # 비용 칸도 주문당 하나다. 남은 건이 있으면 그 건의 봉인값으로, 없으면 이번 접수가 심은 미확정 추정값을 걷는다
    # (남기면 다음 접수가 고른 유 · 무상이 심기지 않는다). 확정된 판정은 건드리지 않는다.
    snapshot = (prev or {}).get("billing_snapshot")
    billing = shipment.get("as_billing")
    if isinstance(snapshot, dict):
        shipment["as_billing"] = copy.deepcopy(snapshot)
    elif prev is None and isinstance(billing, dict) and not billing.get("confirmed"):
        shipment.pop("as_billing", None)


def cancel_as_cycle(
    session: Session, *, order_id: int, actor_user_id: int, reason: str, actor_name: str = "",
    cycle_id: Optional[str] = None, scope_hash: str, request_hash: str,
    now: Optional[datetime.datetime] = None, idempotency_key: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> MutationResult:
    """AS_CANCEL: 접수 상태인 현재 건을 ``cancelled_cycles[]`` 로 옮기고 주문을 접수 전 모습으로 되돌린다.

    남은 건이 없으면 AS 축을 비운 상태 글(물류 → 본 흐름)로, 남은 건이 완료면 ``AS_COMPLETED`` 로 돌아간다.
    건 기록이 없는 옛 AS 접수 주문은 같은 mutation 안에서 먼저 건을 세운 뒤 취소한다(``legacy_bridge``).

    Args:
        session: 요청 세션(commit 은 호출자). order_id: 대상 주문. actor_user_id · actor_name: 취소한 사람.
        reason: 취소 사유(필수). cycle_id: 지정하면 현재 건과 같아야 한다.
        scope_hash · request_hash · idempotency_key · expected_version: REV-00 계약.

    Raises:
        ASCycleError: 사유 없음 · 취소할 건 없음 · 접수 상태가 아님 · 열린 AS 도면 요청 · 본 흐름 단계를 읽을 수 없음.
    """
    now = now or now_utc_naive()
    reason_str = _require_text(reason, field="취소 사유", min_len=1, max_len=_MAX_REASON)

    def _apply(sd: Dict[str, Any], order: Order) -> Dict[str, Any]:
        cycle = current_cycle(sd)
        if cycle is None:
            raise ASCycleError("취소할 AS 접수가 없습니다.")
        cid = str(cycle.get("cycle_id") or "")
        if cycle_id is not None and cid != str(cycle_id):
            raise ASCycleError("현재 AS cycle 과 일치하지 않습니다.")
        if cycle_status(cycle) != AS_RECEIVED:
            raise ASCycleError(NOT_RECEIVED_MESSAGE)
        if open_drawing_round_blocks(sd, cid):
            raise ASCycleError(DRAWING_OPEN_MESSAGE)

        _append_transition(cycle, command="AS_CANCEL", from_status=AS_RECEIVED, to_status=AS_NONE,
                           payload={"reason": reason_str}, actor_user_id=actor_user_id, now=now)
        cycle.update(cancelled_at=now.isoformat(), cancelled_by=actor_user_id,
                     cancelled_by_name=actor_name or "", cancel_reason=reason_str)
        lifecycle = _lifecycle(sd)
        remaining = [c for c in lifecycle["cycles"] if c is not cycle]
        lifecycle["cycles"] = remaining
        cancelled = lifecycle.get(CANCELLED_CYCLES_KEY)
        lifecycle[CANCELLED_CYCLES_KEY] = (cancelled if isinstance(cancelled, list) else []) + [cycle]
        prev = next((c for c in reversed(remaining) if isinstance(c, dict)), None)
        lifecycle["current_cycle_id"] = prev.get("cycle_id") if prev else None
        if prev is None:
            # 남은 건이 없으면 상태 글에서 AS 를 걷는다(남은 건이 있으면 뒤의 재계산이 그 건 상태로 맞춘다).
            clear_as_status_text(order, sd)

        hidden = _hide_cycle_log_lines(sd, cid, actor_name=actor_name, now_iso=now.isoformat())
        _restore_shipment_projection(sd, order, prev)
        order.as_received_date = (prev or {}).get("received_date") or None
        order.as_completed_date = (prev or {}).get("completed_date") or None
        # 취소 사실 한 줄 — 어느 건에도 묶지 않는다(남은 건의 기록으로 읽히지 않게).
        append_system_log(sd, text=f"AS 접수 취소됨 · {reason_str}").pop("cycle_id", None)
        return {"command": "AS_CANCEL", "cycle_id": cid, "reason": reason_str,
                "to": cycle_status(prev) if prev else AS_NONE,
                "hidden_log_count": hidden, "remaining_cycles": len(remaining)}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_CANCEL,
        expected_version=expected_version, event_type=EVENT_AS_CANCELLED, apply=_apply,
        scope_hash=scope_hash, request_hash=request_hash, idempotency_key=idempotency_key, now=now,
        legacy_bridge=True,
    )


__all__ = [
    "CANCELLED_CYCLES_KEY",
    "DRAWING_OPEN_MESSAGE",
    "EVENT_AS_CANCELLED",
    "NOT_RECEIVED_MESSAGE",
    "cancel_as_cycle",
    "open_drawing_round_blocks",
]
