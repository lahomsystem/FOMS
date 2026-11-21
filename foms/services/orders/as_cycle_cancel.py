"""AS 접수 취소 — 잘못 접수한 현재 건(접수 상태)을 걷어 내고 주문을 접수 전 모습으로 되돌린다.

설계서 ``docs/specs/2026-11-20-multi-item-split-schedule_SPEC.md`` §4.4 (결정 M9 ~ M12).

지금까지는 잘못 접수한 AS 를 지울 길이 없어 단계 강제 변경으로 주문 상태의 AS 표시만 덮었다 — AS 건은 열린 채
남았다(운영 5687). 이 명령은 그 건을 통째로 걷어 낸다.

* 현재 건이 **접수(RECEIVED)** 일 때만. 처리 중 · 완료는 취소가 아니다.
* 건은 ``as_lifecycle.cycles[]`` 에서 빼 ``cancelled_cycles[]`` 로 옮긴다. 순번 · 지난 건을 세는 곳이 모두
  ``cycles[]`` 자리 순서를 쓰므로, 남겨 두면 다음 접수가 "2번째 AS"가 되고 잘못 접수한 건이 지난 건으로 뜬다.
* 되돌리는 근거는 접수가 건에 남긴 **접수 전 값**(``pre_register`` — 상태 글 · AS 축 · 접수일 · 완료일 · 상차일 ·
  시공자 · 비용 판정 · 전달 배정)이다. 그 값이 없는 건(이 기능 전에 접수된 건)은 남은 건 · 본 흐름 단계로 되돌리고,
  그 건보다 앞선 AS 기록이 건 없이 남아 있으면 접수 전 상태를 알 수 없으므로 막는다.
* 그 건 번호가 찍힌 기록 줄은 지우지 않고 가림 표시만 한다(원문 · 첨부는 분쟁 근거로 남는다).
* 열린 AS 도면 요청(차수 상태 WAITING · IN_PROGRESS · TRANSFERRED · RETURNED)이 그 건에 걸려 있으면 막는다 —
  도면팀이 그리는 중인 요청이 주인 없는 차수로 남지 않게 먼저 닫게 한다.

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
    LEGACY_BRIDGE_ORIGIN,
    POLICY_AS_CANCEL,
    PRE_REGISTER_KEY,
    SALES_DELIVERY_KEYS,
    ASCycleError,
    _MAX_REASON,
    _append_transition,
    _apply_classification_projection,
    _apply_visit_projection,
    _lifecycle,
    _require_text,
    _run_as_command,
    current_cycle,
    cycle_status,
    restore_status_after_as_cancel,
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
#: 취소 사유 길이 한도(API 가 400 으로 먼저 거른다).
CANCEL_REASON_MAX = _MAX_REASON
NOT_RECEIVED_MESSAGE = "접수 상태인 AS 만 취소할 수 있습니다. 처리 중이거나 완료된 AS 는 취소할 수 없어요."
DRAWING_OPEN_MESSAGE = "열려 있는 AS 도면 요청이 있어 취소할 수 없습니다. 도면 요청을 먼저 닫아 주세요."
PRIOR_UNKNOWN_MESSAGE = (
    "이 접수보다 앞선 AS 기록이 남아 있어 접수 전 상태로 되돌릴 수 없습니다. 취소 대신 AS 완료로 닫아 주세요."
)


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


def _older_visible_log_exists(sd: Dict[str, Any], cycle: Dict[str, Any]) -> bool:
    """그 건보다 오래된, 가려지지 않은 AS 기록 줄이 있는가(건 번호가 다른 줄 · 옛 기록 줄).

    접수 전 값이 없는 건에서 남은 건도 없는데 이런 줄이 있으면, 건 기록 없이 끝난 옛 AS 가 있었다는 뜻이다 —
    접수 전 상태(상태 글 · AS 축 · 날짜)를 알 길이 없다.
    """
    cid = str(cycle.get("cycle_id") or "")
    opened_at = str(cycle.get("opened_at") or "")
    for entry in (sd.get("shipment") or {}).get("as_log") or []:
        if not isinstance(entry, dict) or entry.get("deleted") is True:
            continue
        if str(entry.get("cycle_id") or "") == cid:
            continue
        ts = str(entry.get("ts") or "")
        if entry.get("legacy") is True or not ts or ts < opened_at:
            return True
    return False


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


def _restore_billing(shipment: Dict[str, Any], cycle: Dict[str, Any], prev: Optional[Dict[str, Any]],
                     prior: Optional[Dict[str, Any]]) -> None:
    """주문당 한 칸인 비용 판정을 접수 전으로 — 취소한 건에서 내린 유 · 무상 판정이 정산에 남지 않게."""
    if prior is not None:
        before = prior.get("as_billing")
    else:
        before = (prev or {}).get("billing_snapshot")
        billing = shipment.get("as_billing")
        if not isinstance(before, dict) and isinstance(billing, dict):
            # 접수 전 값이 없는 건: 이 건을 연 뒤에 확정했거나 아직 미확정인 판정은 이 건의 것이라 걷는다.
            # 건 이전의 옛 확정 판정은 그대로 둔다.
            decided_in_cycle = str(billing.get("decided_at") or "") >= str(cycle.get("opened_at") or "")
            if billing.get("confirmed") and not decided_in_cycle:
                return
    if isinstance(before, dict):
        shipment["as_billing"] = copy.deepcopy(before)
    else:
        shipment.pop("as_billing", None)


def _restore_sales_delivery(shipment: Dict[str, Any], cycle: Dict[str, Any],
                            prior: Optional[Dict[str, Any]]) -> None:
    """전달 배정 칸(주문당 한 칸)을 접수 전으로 — 다음 접수 뒤에 취소한 건의 배정이 살아나지 않게.

    접수 전 배정은 남은(끝난) 건의 전달 기록이라 지우지 않고 그대로 되돌린다. 접수 전 값이 없는 건은 이 건을
    연 뒤에 생긴 배정 · 택배 기록만 치운다.
    """
    if prior is not None:
        before = prior.get("sales_delivery") if isinstance(prior.get("sales_delivery"), dict) else {}
        for key in SALES_DELIVERY_KEYS:
            if key in before:
                shipment[key] = copy.deepcopy(before[key])
            else:
                shipment.pop(key, None)
        return
    opened_at = str(cycle.get("opened_at") or "")
    link_key, _method_key, parcel_key = SALES_DELIVERY_KEYS
    for key, stamp in ((link_key, "assigned_at"), (parcel_key, "sent_at")):
        value = shipment.get(key)
        if isinstance(value, dict) and str(value.get(stamp) or opened_at) >= opened_at:
            shipment.pop(key, None)


def _restore_overwritten(sd: Dict[str, Any], order: Order, prior: Optional[Dict[str, Any]]) -> None:
    """접수가 덮은 시공자 칸 · 상차일을 되돌린다 — 접수 뒤에 누가 다시 고쳤으면(덮은 값과 다르면) 건드리지 않는다."""
    if prior is None:
        return
    shipment = sd.setdefault("shipment", {})
    workers = prior.get("construction_workers")
    if isinstance(workers, dict) and shipment.get("construction_workers") == workers.get("after"):
        if workers.get("before") is None:
            shipment.pop("construction_workers", None)
        else:
            shipment["construction_workers"] = copy.deepcopy(workers["before"])
    shipping = prior.get("shipping_scheduled_date")
    if isinstance(shipping, dict) and str(order.shipping_scheduled_date or "") == str(shipping.get("after") or ""):
        order.shipping_scheduled_date = shipping.get("before") or None


def _restore_shipment_projection(sd: Dict[str, Any], order: Order, cycle: Dict[str, Any],
                                 prev: Optional[Dict[str, Any]], prior: Optional[Dict[str, Any]]) -> None:
    """주문당 한 칸인 AS 투영을 남은 건(없으면 빈 값) · 접수 전 값으로 되돌린다."""
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
    _restore_billing(shipment, cycle, prev, prior)
    _restore_sales_delivery(shipment, cycle, prior)
    _restore_overwritten(sd, order, prior)


def cancel_as_cycle(
    session: Session, *, order_id: int, actor_user_id: int, reason: str, actor_name: str = "",
    cycle_id: Optional[str] = None, scope_hash: str, request_hash: str,
    now: Optional[datetime.datetime] = None, idempotency_key: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> MutationResult:
    """AS_CANCEL: 접수 상태인 현재 건을 ``cancelled_cycles[]`` 로 옮기고 주문을 접수 전 모습으로 되돌린다.

    접수 전 값(``pre_register``)이 있으면 그 값으로, 없으면 남은 건(완료면 ``AS_COMPLETED``) 또는 AS 축을 비운
    상태 글(물류 → 본 흐름)로 돌아간다. 건 기록이 없는 옛 AS 접수 주문은 같은 mutation 안에서 먼저 건을 세운 뒤
    취소한다(``legacy_bridge``).

    Args:
        session: 요청 세션(commit 은 호출자). order_id: 대상 주문. actor_user_id · actor_name: 취소한 사람.
        reason: 취소 사유(필수). cycle_id: 지정하면 현재 건과 같아야 한다.
        scope_hash · request_hash · idempotency_key · expected_version: REV-00 계약.

    Raises:
        ASCycleError: 사유 없음 · 취소할 건 없음 · 접수 상태가 아님 · 열린 AS 도면 요청 · 접수 전 상태를 알 수 없음.
    """
    now = now or now_utc_naive()
    reason_str = _require_text(reason, field="취소 사유", min_len=1, max_len=CANCEL_REASON_MAX)

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
        lifecycle = _lifecycle(sd)
        remaining = [c for c in lifecycle["cycles"] if c is not cycle]
        prev = next((c for c in reversed(remaining) if isinstance(c, dict)), None)
        prior = cycle.get(PRE_REGISTER_KEY) if isinstance(cycle.get(PRE_REGISTER_KEY), dict) else None
        # 접수 전 값도 남은 건도 없는데 앞선 AS 기록이 있다 = 건 기록 없이 끝난 옛 AS — 무엇으로 되돌릴지 모른다.
        # 옛 주문 끌어올리기 건은 그 옛 기록이 제 접수 글이라 해당하지 않는다.
        if (prior is None and prev is None and cycle.get("origin") != LEGACY_BRIDGE_ORIGIN
                and _older_visible_log_exists(sd, cycle)):
            raise ASCycleError(PRIOR_UNKNOWN_MESSAGE)

        _append_transition(cycle, command="AS_CANCEL", from_status=AS_RECEIVED, to_status=AS_NONE,
                           payload={"reason": reason_str}, actor_user_id=actor_user_id, now=now)
        cycle.update(cancelled_at=now.isoformat(), cancelled_by=actor_user_id,
                     cancelled_by_name=actor_name or "", cancel_reason=reason_str)
        lifecycle["cycles"] = remaining
        cancelled = lifecycle.get(CANCELLED_CYCLES_KEY)
        lifecycle[CANCELLED_CYCLES_KEY] = (cancelled if isinstance(cancelled, list) else []) + [cycle]
        lifecycle["current_cycle_id"] = prev.get("cycle_id") if prev else None
        if prev is None:
            # 남은 건이 없으면 상태 글 · AS 축 칸을 접수 전으로(남은 건이 있으면 뒤의 재계산이 그 건 상태로 맞춘다).
            restore_status_after_as_cancel(order, sd, prior)

        hidden = _hide_cycle_log_lines(sd, cid, actor_name=actor_name, now_iso=now.isoformat())
        _restore_shipment_projection(sd, order, cycle, prev, prior)
        before_dates = prior if prior is not None else {
            "as_received_date": (prev or {}).get("received_date"),
            "as_completed_date": (prev or {}).get("completed_date"),
        }
        order.as_received_date = before_dates.get("as_received_date") or None
        order.as_completed_date = before_dates.get("as_completed_date") or None
        # 취소 사실 한 줄 — 어느 건에도 묶지 않는다(남은 건의 기록으로 읽히지 않게).
        append_system_log(sd, text=f"AS 접수 취소됨 · {reason_str}").pop("cycle_id", None)
        return {"command": "AS_CANCEL", "cycle_id": cid, "reason": reason_str,
                "to": cycle_status(prev) if prev else AS_NONE,
                "restored_from": "pre_register" if prior is not None else ("previous_cycle" if prev else "stage"),
                "hidden_log_count": hidden, "remaining_cycles": len(remaining)}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_CANCEL,
        expected_version=expected_version, event_type=EVENT_AS_CANCELLED, apply=_apply,
        scope_hash=scope_hash, request_hash=request_hash, idempotency_key=idempotency_key, now=now,
        legacy_bridge=True,
    )


__all__ = [
    "CANCELLED_CYCLES_KEY",
    "CANCEL_REASON_MAX",
    "DRAWING_OPEN_MESSAGE",
    "EVENT_AS_CANCELLED",
    "NOT_RECEIVED_MESSAGE",
    "PRIOR_UNKNOWN_MESSAGE",
    "cancel_as_cycle",
    "open_drawing_round_blocks",
]
