"""order 상태 다축 전이 정본 엔진 (STATE-CORE-00, SSOT §2.2·§2.2.1·§2.3).

order 의 상태 변경은 지금까지 erp route 곳곳에서 ``order.status`` / ``structured_data``
를 직접 건드리며 흩어져 있었다. 이 모듈은 그 전이를 **단일 경로**로 모은다: 각 command
가 자기 axis 의 expected-from 을 검증하고, actual-before 를 snapshot 하고, row lock +
version bump + receipt 로 원자 전이하고, legacy ``OrderEvent`` parity 를 남기며, 필요한
side-effect 를 **같은 transaction 안** outbox 에 enqueue 하는 하나의 엔진이다.

세 helper 를 **조립만** 한다(재구현 금지):

* :func:`foms.services.orders.revision.execute_order_mutation` — FOR UPDATE row lock +
  If-Match(mutation_version) + idempotency replay + receipt. 실제 전이는 이 helper 의
  ``mutation`` 콜러블 안에서 수행한다.
* :mod:`foms.services.orders.state_axes` — 전이 전/후 canonical 축 read model
  (``read_state_axes``) 와 legacy ``order.status`` projection(``legacy_status_projection``).
* :func:`foms.services.sidefx_outbox.enqueue_side_effect` — side-effect 를 전이 tx 안에서
  outbox 에 enqueue(원자성: 전이 rollback 시 outbox 도 rollback).

STATE-CORE-00 은 **엔진 + command registry + 계약 fixture** 만 소유한다. 실제 route 가
이 서비스를 호출하도록 바꾸는 endpoint 이관은 하류(STATE-PROD-01·STATE-DRAWING-01 등)
몫이다. models.py·마이그레이션·worker 는 건드리지 않고 import 만 한다.
"""
from __future__ import annotations

import copy
import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.revision import MutationResult, execute_order_mutation
from foms.services.orders.state_axes import (
    AXIS_CONSTRUCTION,
    AXIS_DELETE,
    AXIS_HOLD,
    AXIS_LOGISTICS,
    AXIS_MAIN,
    AXIS_AS,
    LOGISTICS_VALUES,
    OrderStateAxes,
    legacy_status_projection,
    read_state_axes,
)
from foms.services.sidefx_outbox import enqueue_side_effect
from models import Order, OrderEvent

# 전이가 outbox 에 넣는 side-effect 는 Order command notification/cache/geocode 이므로
# source_domain 은 ORDER_EVENT 다(§2.3: "Order command notification/cache/geocode→ORDER_EVENT").
# 전이가 만든 OrderEvent row 를 source 로 참조해 one-of FK 매트릭스를 만족한다.
_SIDEFX_SOURCE_DOMAIN = "ORDER_EVENT"


# --------------------------------------------------------------------------- #
# 예외 (호출자는 status_code 로 HTTP 매핑; RevisionConflictError 는 helper 가 던진다)
# --------------------------------------------------------------------------- #
class TransitionError(RuntimeError):
    """전이 계약 위반의 베이스(호출자는 ``status_code`` 로 HTTP 매핑)."""

    status_code = 409
    error_code = "TRANSITION_ERROR"


class UnknownTransitionCommandError(TransitionError):
    """registry 에 없는 command_id. silent no-op 금지 — 명시적 거부(422)."""

    status_code = 422
    error_code = "UNKNOWN_TRANSITION_COMMAND"


class InvalidTransitionError(TransitionError):
    """command 이 이 from/to 를 허용하지 않음(비인접 전이·잘못된 target). 409."""

    status_code = 409
    error_code = "INVALID_TRANSITION"


class StageConflictError(TransitionError):
    """actual axis 값이 caller 의 expected-from 과 불일치. 409(상태 불변)."""

    status_code = 409
    error_code = "STAGE_CONFLICT"

    def __init__(self, axis: str, expected: Optional[str], actual: Optional[str]):
        super().__init__(
            f"{axis} expected-from {expected!r} but actual is {actual!r}."
        )
        self.axis = axis
        self.expected = expected
        self.actual = actual


# --------------------------------------------------------------------------- #
# axis writer — 각 축의 canonical path 만 쓰고 나머지 orthogonal 축은 건드리지 않는다.
# (§2.3 step 6: main 은 workflow.stage/erp_stage_code/mirror, orthogonal 은 자기 path만)
# --------------------------------------------------------------------------- #
def _apply_main(
    sd: Dict[str, Any], order: Order, value: str, *,
    actor_user_id: int, now: datetime.datetime, reason: Optional[str],
) -> None:
    """main stage: ``workflow.stage`` + indexed mirror ``erp_stage_code`` 를 함께 쓴다."""
    workflow = sd.setdefault("workflow", {})
    workflow["stage"] = value
    workflow["stage_updated_at"] = now.isoformat()
    order.erp_stage_code = value
    order.erp_stage_updated_at = now


def _apply_logistics(
    sd: Dict[str, Any], order: Order, value: str, *,
    actor_user_id: int, now: datetime.datetime, reason: Optional[str],
) -> None:
    """logistics: ``shipment.logistics_status`` 만 쓴다(main stage 불변)."""
    shipment = sd.setdefault("shipment", {})
    shipment["logistics_status"] = value


def _apply_hold(
    sd: Dict[str, Any], order: Order, value: str, *,
    actor_user_id: int, now: datetime.datetime, reason: Optional[str],
) -> None:
    """hold: ``workflow.hold.{active,held_at,held_by,reason}`` 만 쓴다(main stage 불변)."""
    workflow = sd.setdefault("workflow", {})
    if value == "HELD":
        workflow["hold"] = {
            "active": True,
            "held_at": now.isoformat(),
            "held_by": actor_user_id,
            "reason": reason,
        }
    else:
        workflow["hold"] = {"active": False, "released_at": now.isoformat()}


# axis → (writer, 유효 값 enum). AS/construction/delete 는 cycle/attempt/soft-delete 하위
# 상태기계라 하류(STATE-AS-01·STATE-CONST-CS-01·DELETE-CORE-00)가 소유한다 — 엔진에
# writer 를 두지 않고, registry 가 그 축 command 를 등록하면 그때 추가한다.
_AXIS_WRITERS: Dict[str, Callable[..., None]] = {
    AXIS_MAIN: _apply_main,
    AXIS_LOGISTICS: _apply_logistics,
    AXIS_HOLD: _apply_hold,
}


# --------------------------------------------------------------------------- #
# command registry (데이터 주도: command_id → axis 전이 + side-effect kind)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TransitionCommand:
    """전이 command 정의(registry 행).

    Attributes:
        command_id: command 식별자(예: ``REQUEST_MEASUREMENT``).
        policy_id: mutation 정책 식별자(receipt idempotency scope 구성요소).
        axis: 이 command 이 소유하는 canonical 축(``AXIS_MAIN`` 등).
        from_values: 허용 source 값(expected-from 도메인). actual 이 여기에 없으면 거부.
        to_values: 허용 target 값. caller 의 target 이 여기에 없으면 거부.
        event_type: legacy ``OrderEvent.event_type`` (parity).
        effect_type: 전이 tx 내 outbox 행의 ``effect_type``.
        extra_families: registry.extras cache family(§2.3 line 407).
    """

    command_id: str
    policy_id: str
    axis: str
    from_values: Tuple[str, ...]
    to_values: Tuple[str, ...]
    event_type: str
    effect_type: str
    extra_families: Tuple[str, ...] = field(default_factory=tuple)


def _cmd(**kw: Any) -> TransitionCommand:
    return TransitionCommand(**kw)


# 대표 command — 세 orthogonal 축(main handoff / logistics overlay / hold)을 덮어 전이
# 계약(expected-from·actual-before·event parity·tx내 outbox·orthogonality)을 고정한다.
# AS/construction/production/drawing command 는 자기 하위 상태기계를 소유한 하류 packet 이
# 이 registry 에 additive 로 등록한다.
COMMAND_REGISTRY: Dict[str, TransitionCommand] = {
    c.command_id: c
    for c in (
        _cmd(
            command_id="REQUEST_MEASUREMENT", policy_id="STATE_REQUEST_MEASUREMENT",
            axis=AXIS_MAIN, from_values=("RECEIVED",), to_values=("MEASURE",),
            event_type="MEASUREMENT_REQUESTED", effect_type="STAGE_NOTIFICATION",
        ),
        _cmd(
            command_id="COMPLETE_MEASUREMENT", policy_id="STATE_COMPLETE_MEASUREMENT",
            axis=AXIS_MAIN, from_values=("MEASURE",), to_values=("DRAWING",),
            event_type="MEASUREMENT_COMPLETED", effect_type="STAGE_NOTIFICATION",
        ),
        _cmd(
            command_id="SET_LOGISTICS_STATUS", policy_id="STATE_SET_LOGISTICS_STATUS",
            axis=AXIS_LOGISTICS, from_values=LOGISTICS_VALUES, to_values=LOGISTICS_VALUES,
            event_type="LOGISTICS_STATUS_CHANGED", effect_type="LOGISTICS_NOTIFICATION",
        ),
        _cmd(
            command_id="HOLD_ORDER", policy_id="STATE_HOLD_ORDER",
            axis=AXIS_HOLD, from_values=("NONE",), to_values=("HELD",),
            event_type="ORDER_HELD", effect_type="HOLD_NOTIFICATION",
        ),
        _cmd(
            command_id="RELEASE_HOLD", policy_id="STATE_RELEASE_HOLD",
            axis=AXIS_HOLD, from_values=("HELD",), to_values=("NONE",),
            event_type="ORDER_HOLD_RELEASED", effect_type="HOLD_NOTIFICATION",
        ),
    )
}


def get_command(command_id: str) -> TransitionCommand:
    """registry 에서 command 를 조회한다. 미등록이면 명시적 거부(silent no-op 금지).

    Args:
        command_id: 전이 command 식별자.

    Returns:
        등록된 :class:`TransitionCommand`.

    Raises:
        UnknownTransitionCommandError: registry 에 없는 command_id.
    """
    command = COMMAND_REGISTRY.get(command_id)
    if command is None:
        raise UnknownTransitionCommandError(
            f"transition command {command_id!r} is not registered; "
            f"known={sorted(COMMAND_REGISTRY)}."
        )
    return command


_AXIS_ATTR: Dict[str, str] = {
    AXIS_MAIN: "main",
    AXIS_LOGISTICS: "logistics",
    AXIS_HOLD: "hold",
    AXIS_AS: "as_status",
    AXIS_DELETE: "deleted",
    AXIS_CONSTRUCTION: "construction",
}


def _axis_value(axes: OrderStateAxes, axis: str) -> Optional[str]:
    """canonical read model 에서 지정 축의 현재 값을 뽑는다."""
    return getattr(axes, _AXIS_ATTR[axis])


def _changed_families(order_id: int, axis: str, before: Optional[str],
                      after: str, extras: Tuple[str, ...]) -> List[str]:
    """§2.3 line 407: ``{ORDER_DETAIL,ORDERS_INDEX,STAGE:before,STAGE:after} ∪ extras``.

    main 축 전이만 STAGE family 를 포함한다(orthogonal 축은 stage 를 바꾸지 않으므로 생략).
    """
    families = [f"ORDER_DETAIL:{order_id}", "ORDERS_INDEX"]
    if axis == AXIS_MAIN:
        if before:
            families.append(f"STAGE:{before}")
        families.append(f"STAGE:{after}")
    families.extend(extras)
    return families


@dataclass(frozen=True)
class TransitionResult:
    """:func:`transition_order` 반환값.

    Attributes:
        mutation: 하위 :class:`~foms.services.orders.revision.MutationResult`
            (body/headers/read_receipt_id/replayed).
        axes_before: 전이 직전 canonical 축 snapshot(replay 면 None).
        axes_after: 전이 직후 canonical 축(replay 면 None).
        event_type: 기록된 legacy ``OrderEvent`` type(replay 면 None).
        event_id: 기록된 ``OrderEvent.id`` (replay 면 None).
        outbox_id: enqueue 된 outbox 행 id(replay 면 None).
        replayed: idempotency replay(전이/event/outbox 미수행)면 True.
    """

    mutation: MutationResult
    axes_before: Optional[OrderStateAxes]
    axes_after: Optional[OrderStateAxes]
    event_type: Optional[str]
    event_id: Optional[int]
    outbox_id: Optional[int]
    replayed: bool


def transition_order(
    session: Session,
    *,
    command_id: str,
    order_id: int,
    actor_user_id: int,
    expected_from: str,
    target_value: str,
    scope_hash: str,
    request_hash: str,
    expected_version: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    reason: Optional[str] = None,
    source_screen: Optional[str] = None,
    emergency_override: bool = False,
    now: Optional[datetime.datetime] = None,
) -> TransitionResult:
    """order 를 registry command 로 원자 전이한다(상태 변경의 유일한 경로).

    한 transaction 안에서 (1) registry 조회, (2) target/expected-from 정합 검증,
    (3) row lock 아래 actual-before snapshot + expected-from 재확인, (4) axis canonical
    write + legacy projection 재계산, (5) legacy ``OrderEvent`` parity 기록, (6) 같은 tx
    outbox enqueue, (7) version bump + receipt 를 수행한다. ``session.commit()`` 은
    **호출자가 소유**한다(REV-00 규약) — 어떤 단계라도 실패하면 호출자 rollback 으로 전이·
    event·outbox 가 함께 사라진다(원자성).

    Args:
        session: business transaction 세션(호출자 소유, 커밋 미수행).
        command_id: registry command 식별자. 미등록이면 거부.
        order_id: 전이 대상 Order id(단건 FOR UPDATE lock).
        actor_user_id: 요청 actor(receipt 소유자·event/outbox author).
        expected_from: caller 가 본 현재 axis 값(actual 과 불일치 시 STAGE_CONFLICT).
        target_value: 목표 axis 값(command.to_values 안이어야 함).
        scope_hash: 요청 scope sha256 hex(receipt 저장).
        request_hash: 요청 payload sha256 hex(same-key/different-hash 감지).
        expected_version: If-Match mutation_version. None 이면 precondition 없음.
        idempotency_key: UUID 문자열(≤64자) 또는 None. 같은 key replay 는 전이/event/
            outbox 없이 저장된 응답을 돌려준다.
        reason: 전이 사유(hold/emergency override 등 payload 에 보존).
        source_screen: 요청 화면(event payload 에 보존, 선택).
        emergency_override: True 면 from_values 인접성 검사를 건너뛴다(비인접 전이).
            reason 필수. role(ADMIN/MANAGER) 검증은 하류 endpoint 몫이다.
        now: 테스트용 시각 주입(기본 now_utc_naive()).

    Returns:
        :class:`TransitionResult`.

    Raises:
        UnknownTransitionCommandError: 미등록 command_id(422).
        InvalidTransitionError: target 이 to_values 밖·비인접인데 override 아님·override
            인데 reason 누락(409).
        StageConflictError: actual axis 값이 expected_from 과 불일치(409, 상태 불변).
        RevisionConflictError: If-Match(mutation_version) 불일치(409, helper 가 던짐).
    """
    command = get_command(command_id)
    now = now or now_utc_naive()

    if target_value not in command.to_values:
        raise InvalidTransitionError(
            f"{command_id}: target {target_value!r} not in {command.to_values}."
        )
    if emergency_override:
        if not reason:
            raise InvalidTransitionError(
                f"{command_id}: emergency_override requires a reason."
            )
    elif expected_from not in command.from_values:
        raise InvalidTransitionError(
            f"{command_id}: not allowed from {expected_from!r} "
            f"(allowed={command.from_values}); use emergency_override for non-adjacent."
        )

    writer = _AXIS_WRITERS[command.axis]
    captured: Dict[str, Any] = {}

    def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
        """row lock 아래에서 전이 본체를 수행하고 changed cache family 를 돌려준다."""
        order = orders[0]

        # 1) actual-before snapshot + expected-from 재확인(lock 아래라 race-free).
        axes_before = read_state_axes(order)
        actual_from = _axis_value(axes_before, command.axis)
        if actual_from != expected_from:
            raise StageConflictError(command.axis, expected_from, actual_from)

        # 2) axis canonical write(copy.deepcopy + flag_modified) + legacy projection 재계산.
        sd = copy.deepcopy(order.structured_data or {})
        writer(sd, order, target_value, actor_user_id=actor_user_id, now=now, reason=reason)
        order.structured_data = sd
        flag_modified(order, "structured_data")
        axes_after = read_state_axes(order)
        projection = legacy_status_projection(axes_after)
        if projection:
            order.status = projection

        # 3) legacy OrderEvent parity — before/after 로 registry 지정 event 를 append.
        event = OrderEvent(
            order_id=order.id,
            event_type=command.event_type,
            payload={
                "command": command_id,
                "axis": command.axis,
                "from": actual_from,
                "to": target_value,
                "reason": reason,
                "source_screen": source_screen,
                "emergency_override": emergency_override,
            },
            created_by_user_id=actor_user_id,
            created_at=now,
        )
        sess.add(event)
        sess.flush()  # event.id 확보(outbox FK 참조)

        # 4) 같은 tx outbox enqueue — ORDER_EVENT source 로 one-of FK 매트릭스 만족.
        outbox_row = enqueue_side_effect(
            sess,
            source_domain=_SIDEFX_SOURCE_DOMAIN,
            source_id=event.id,
            effect_type=command.effect_type,
            payload={
                "order_id": order.id,
                "command": command_id,
                "axis": command.axis,
                "from": actual_from,
                "to": target_value,
            },
            dedupe_key=f"{command.effect_type}:{event.id}",
            now=now,
        )

        captured["axes_before"] = axes_before
        captured["axes_after"] = axes_after
        captured["event_id"] = event.id
        captured["outbox_id"] = outbox_row.id
        return {
            order.id: _changed_families(
                order.id, command.axis, actual_from, target_value, command.extra_families
            )
        }

    result = execute_order_mutation(
        session,
        actor_user_id=actor_user_id,
        policy_id=command.policy_id,
        order_ids=[order_id],
        expected_versions=({order_id: expected_version} if expected_version is not None else None),
        scope_hash=scope_hash,
        request_hash=request_hash,
        mutation=_mutate,
        idempotency_key=idempotency_key,
        now=now,
    )

    return TransitionResult(
        mutation=result,
        axes_before=captured.get("axes_before"),
        axes_after=captured.get("axes_after"),
        event_type=None if result.replayed else command.event_type,
        event_id=captured.get("event_id"),
        outbox_id=captured.get("outbox_id"),
        replayed=result.replayed,
    )


__all__ = [
    "TransitionError",
    "UnknownTransitionCommandError",
    "InvalidTransitionError",
    "StageConflictError",
    "TransitionCommand",
    "TransitionResult",
    "COMMAND_REGISTRY",
    "get_command",
    "transition_order",
]
