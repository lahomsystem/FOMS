"""AS(사후관리) cycle 상태전이 정본 서비스 (STATE-AS-01, SSOT §2.2.1 AS registry).

AS 는 지금까지 ``foms/api/cs/as_orders.py`` 와 ``field_update.py`` 곳곳에서 ``order.status``
/ ``workflow.stage`` 를 ``AS``/``AS_RECEIVED``/``AS_COMPLETED`` 로 **직접** 덮으며(=main stage
오염) flat ``as_info`` 리스트에 append 하는 식으로만 기록됐다. 이 모듈은 그 전이를 **단일
경로**로 모아 canonical ``structured_data['as_lifecycle']`` cycle 상태기계로 정본화한다:

* **immutable cycle core + append transition history**: cycle core(``cycle_id``/``opened_at``/
  ``opened_by``/``initial_content``/``initial_shipping_date``)는 불변이고, register/schedule/
  unschedule/start/complete/reopen/classification 은 ``{seq,command,from,to,payload,actor_id,at}``
  transition 을 **append** 한다(과거 transition mutate 금지).
* **current cycle projection**: 상태·방문·사유·완료는 마지막 유효 transition 에서 계산하는
  read projection 이다(:func:`~foms.services.orders.state_axes.read_as_status` 와 shape 정합).
* **AS main stage 복구 금지**: 전이는 orthogonal AS 축(``as_lifecycle``)만 쓰고 ``workflow.stage``
  는 건드리지 않는다. legacy ``order.status`` 는 :func:`legacy_status_projection` 으로 재계산한
  overlay projection 이다(AS_* > logistics > main).
* **classification main/lifecycle 불변**: classification(``as_pending``/``as_blueprint``/
  ``sales_delivery``) 토글은 cycle 상태·방문·main stage 를 바꾸지 않는다(implicit toggle 금지).

원자성(정책·이벤트·version·idempotency·row lock)은 REV-00
:func:`~foms.services.orders.revision.execute_order_mutation` 를 **조립**해 얻는다 —
``transition_order`` 엔진이 단일-값 axis writer(main/logistics/hold)만 소유하고 AS cycle
sub-state-machine(신규 cycle vs 같은 cycle reopen 은 하나의 target 값으로 표현 불가)은
소유하지 않으므로, STATE-CORE order_transition_service 엔진을 편집하지 않고 같은 REV-00
substrate 위에 AS 축을 세운다(STATE-CORE 조율 필요 여부는 packet report 참조). ``session.commit()``
은 **호출자 소유**(REV-00 규약). models·마이그레이션은 건드리지 않는다(import 만).
"""
from __future__ import annotations

import copy
import datetime
import uuid
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.as_log import append_system_log
from foms.services.orders.revision import MutationResult, execute_order_mutation
from foms.services.orders.state_axes import (
    AS_VALUES,
    legacy_status_projection,
    read_as_status,
    read_state_axes,
)
from models import Order, OrderEvent

# AS cycle 상태(§2.2 AS axis read-model). NONE 은 cycle 미보유.
AS_NONE = "NONE"
AS_RECEIVED = "RECEIVED"
AS_IN_PROGRESS = "IN_PROGRESS"
AS_COMPLETED = "COMPLETED"

# classification 필드(§line 515 SET_AS_CLASSIFICATION). shipment read projection + filter tab.
CLASSIFICATION_FIELDS = ("as_pending", "as_blueprint", "sales_delivery")

# 본문 길이 계약(§2.2.1 AS registry).
_MAX_CONTENT = 5000
_MAX_REASON = 500
_MAX_DESCRIPTION = 5000
_MAX_NOTE = 5000

# REV-00 receipt idempotency scope 문자열(POLICY_REGISTRY 와 무관, STATE-PROD/LEGACY 관례).
POLICY_AS_REGISTER = "STATE_AS_REGISTER"
POLICY_AS_SCHEDULE = "STATE_AS_SCHEDULE"
POLICY_AS_UNSCHEDULE = "STATE_AS_UNSCHEDULE"
POLICY_AS_START = "STATE_AS_START"
POLICY_AS_COMPLETE = "STATE_AS_COMPLETE"
POLICY_AS_REOPEN = "STATE_AS_REOPEN"
POLICY_AS_CLASSIFICATION = "STATE_AS_CLASSIFICATION"


class ASCycleError(ValueError):
    """AS cycle 전이 계약 위반(호출 endpoint 가 409 로 매핑). wrong cycle/stage 포함."""


# --------------------------------------------------------------------------- #
# 순수 cycle 헬퍼(DB 무관 — read projection / immutable core / append history)
# --------------------------------------------------------------------------- #
def _lifecycle(sd: Dict[str, Any]) -> Dict[str, Any]:
    """``as_lifecycle`` 블록을 dict 로 보장해 돌려준다(없으면 생성)."""
    lifecycle = sd.get("as_lifecycle")
    if not isinstance(lifecycle, dict):
        lifecycle = {"current_cycle_id": None, "cycles": []}
        sd["as_lifecycle"] = lifecycle
    if not isinstance(lifecycle.get("cycles"), list):
        lifecycle["cycles"] = []
    return lifecycle


def current_cycle(sd: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """``current_cycle_id`` 가 가리키는 현재 cycle dict(없으면 None)."""
    lifecycle = sd.get("as_lifecycle")
    if not isinstance(lifecycle, dict):
        return None
    current_id = lifecycle.get("current_cycle_id")
    cycles = lifecycle.get("cycles")
    if not current_id or not isinstance(cycles, list):
        return None
    return next(
        (c for c in cycles if isinstance(c, dict) and c.get("cycle_id") == current_id),
        None,
    )


def cycle_status(cycle: Optional[Dict[str, Any]]) -> str:
    """cycle 의 현재 상태 projection(마지막 transition ``to``, 없으면 RECEIVED, cycle 없으면 NONE)."""
    if not isinstance(cycle, dict):
        return AS_NONE
    transitions = cycle.get("transitions")
    if isinstance(transitions, list) and transitions:
        last = transitions[-1]
        if isinstance(last, dict):
            to = str(last.get("to") or "").strip()
            if to in AS_VALUES:
                return to
    return AS_RECEIVED


def _append_transition(
    cycle: Dict[str, Any], *, command: str, from_status: str, to_status: str,
    payload: Dict[str, Any], actor_user_id: int, now: datetime.datetime,
) -> None:
    """cycle 에 ``{seq,command,from,to,payload,actor_id,at}`` transition 을 append 한다(core 불변)."""
    transitions = cycle.get("transitions")
    if not isinstance(transitions, list):
        transitions = []
    transitions.append({
        "seq": len(transitions) + 1,
        "command": command,
        "from": from_status,
        "to": to_status,
        "payload": payload,
        "actor_id": actor_user_id,
        "at": now.isoformat(),
    })
    cycle["transitions"] = transitions


def _visit_projection(cycle: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """마지막 SCHEDULE/UNSCHEDULE transition 에서 방문 날짜/시각 projection(없으면 None)."""
    result: Dict[str, Optional[str]] = {"visit_date": None, "visit_time": None}
    for tr in reversed(cycle.get("transitions") or []):
        if not isinstance(tr, dict):
            continue
        if tr.get("command") in ("AS_SCHEDULE", "AS_UNSCHEDULE"):
            payload = tr.get("payload") or {}
            result["visit_date"] = payload.get("visit_date")
            result["visit_time"] = payload.get("visit_time")
            break
    return result


def project_current_as_cycle(order: Order) -> Optional[Dict[str, Any]]:
    """현재 AS cycle 의 read projection(상태·방문·분류·완료). cycle 없으면 None.

    Args:
        order: ``structured_data`` 를 가진 Order.

    Returns:
        ``{cycle_id,status,visit_date,visit_time,classification,opened_at}`` 또는 None.
    """
    sd = getattr(order, "structured_data", None)
    if not isinstance(sd, dict):
        return None
    cycle = current_cycle(sd)
    if cycle is None:
        return None
    visit = _visit_projection(cycle)
    return {
        "cycle_id": cycle.get("cycle_id"),
        "status": cycle_status(cycle),
        "visit_date": visit["visit_date"],
        "visit_time": visit["visit_time"],
        "classification": dict(cycle.get("classification") or {}),
        "opened_at": cycle.get("opened_at"),
    }


# --------------------------------------------------------------------------- #
# 검증 헬퍼
# --------------------------------------------------------------------------- #
def _require_text(value: Any, *, field: str, min_len: int, max_len: int) -> str:
    """문자열 길이 계약을 검증하고 trim 된 값을 돌려준다(위반 시 :class:`ASCycleError`)."""
    text = str(value or "").strip()
    if len(text) < min_len:
        raise ASCycleError(f"{field}은(는) 최소 {min_len}자 이상이어야 합니다.")
    if len(text) > max_len:
        raise ASCycleError(f"{field}은(는) 최대 {max_len}자까지 가능합니다.")
    return text


def _require_iso_date(value: Any, *, field: str) -> str:
    """``YYYY-MM-DD`` ISO 날짜를 검증하고 원문을 돌려준다(위반 시 :class:`ASCycleError`)."""
    text = str(value or "").strip()
    try:
        datetime.datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ASCycleError(f"{field} 형식이 올바르지 않습니다. (YYYY-MM-DD)") from exc
    return text


def _optional_visit_time(value: Any) -> Optional[str]:
    """``HH:MM`` 방문 시각(생략/빈 값이면 None). 위반 시 :class:`ASCycleError`."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        datetime.datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise ASCycleError("방문 시각 형식이 올바르지 않습니다. (HH:MM)") from exc
    return text


# --------------------------------------------------------------------------- #
# 레거시 전환 브리지(forward-only)
# --------------------------------------------------------------------------- #
# cycle.origin 값. canonical register 로 열린 cycle 과 레거시 전환으로 개시된 cycle 을
# 사후에 구분할 수 있어야 감사·재집계가 가능하다(태그 없으면 둘이 영구히 섞인다).
LEGACY_BRIDGE_ORIGIN = "LEGACY_BRIDGE"


def _open_legacy_bridge_cycle(
    sd: Dict[str, Any], order: Order, *, actor_user_id: int, now: datetime.datetime
) -> bool:
    """``as_lifecycle`` 이 없는 레거시 AS 주문에 **지금부터**의 cycle 을 개시한다.

    STATE-AS-01 이전에 접수된 주문은 cycle 이 없어 canonical 전이가 전부 409 로 막힌다
    (진행 중인 AS 의 방문일·완료 버튼 파손). 이 브리지는 그 주문을 canonical 축으로
    끌어올리되 **과거 이력은 재구성하지 않는다**(감사보고서 §296: as_info/history/방문일
    추정 금지). 옮기는 것은 canonical read-model 이 이미 노출하고 있는 **현재 축 값**
    하나뿐이다 — :func:`read_as_status` 가 legacy ``order.status`` 에서 파생하는 값 그대로
    cycle 을 열어, 읽기와 쓰기가 같은 상태를 보게 만든다.

    Args:
        sd: 잠긴 row 의 structured_data 사본(in-place 변경). order: 대상 주문.
        actor_user_id: 전환을 유발한 actor(provenance). now: 개시 시각.

    Returns:
        cycle 을 개시했으면 True. 이미 cycle 이 있거나 AS 상태가 아니면 False(무변경).
    """
    if current_cycle(sd) is not None:
        return False
    status = read_as_status(order)
    if status not in (AS_RECEIVED, AS_IN_PROGRESS, AS_COMPLETED):
        return False
    lifecycle = _lifecycle(sd)
    if lifecycle["cycles"]:
        # 과거 cycle 은 있는데 current 가 없다 = canonical 로 정상 종결된 주문. 레거시 아님.
        return False
    cycle_id = str(uuid.uuid4())
    cycle = {
        "cycle_id": cycle_id, "opened_at": now.isoformat(), "opened_by": actor_user_id,
        "initial_content": str((sd.get("shipment") or {}).get("as_content") or ""),
        "initial_shipping_date": None, "origin": LEGACY_BRIDGE_ORIGIN,
        "classification": {f: False for f in CLASSIFICATION_FIELDS}, "transitions": [],
    }
    _append_transition(
        cycle, command="AS_LEGACY_BRIDGE", from_status=AS_NONE, to_status=status,
        payload={
            "origin": LEGACY_BRIDGE_ORIGIN,
            "legacy_status": getattr(order, "status", None),
            "reason": "레거시 AS 주문의 canonical 전환 자동 개시(과거 이력 미복원)",
        },
        actor_user_id=actor_user_id, now=now,
    )
    lifecycle["cycles"].append(cycle)
    lifecycle["current_cycle_id"] = cycle_id
    append_system_log(sd, text="AS 접수됨(레거시 전환)")
    return True


# --------------------------------------------------------------------------- #
# execute_order_mutation 조립(정책·이벤트·version·idempotency·row lock)
# --------------------------------------------------------------------------- #
def _reproject_and_sync(order: Order, sd: Dict[str, Any]) -> None:
    """as_lifecycle overlay 반영 후 legacy ``order.status`` projection + flat 컬럼을 재계산한다."""
    from foms.services.erp_sync_columns import sync_erp_flat_columns

    projection = legacy_status_projection(read_state_axes(order))
    if projection:
        order.status = projection
    sync_erp_flat_columns(order, sd)


def _run_as_command(
    session: Session, *, order_id: int, actor_user_id: int, policy_id: str,
    event_type: str, apply: Callable[[Dict[str, Any], Order], Dict[str, Any]],
    scope_hash: str, request_hash: str, expected_version: Optional[int] = None,
    idempotency_key: Optional[str] = None, now: Optional[datetime.datetime] = None,
    sd_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    legacy_bridge: bool = False,
) -> MutationResult:
    """AS cycle 전이를 REV-00 원자 mutation 으로 감싼다(commit 은 호출자 소유).

    ``apply(sd, order)`` 는 row lock 아래 ``structured_data`` 사본을 mutate 하고 event
    payload 를 돌려준다(계약 위반 시 :class:`ASCycleError`). 이후 legacy status projection
    재계산 + version bump + receipt + ``OrderEvent`` parity 를 원자 기록한다.

    ``sd_hook`` 은 endpoint 가 **같은 tx·같은 sd 사본**에 남기는 부수 기록(AS 타임라인
    ``as_log`` append, ``as_billing`` 시드)이다. ``apply`` **직전**에 돌아야 한다 — register
    의 ``apply`` 가 ``shipment['as_content']`` 를 덮으므로, 뒤에 두면 legacy 영구화가 방금
    쓴 접수 원문을 "이전 기록"으로 중복 시드한다. 전이가 거부되면 부수 기록도 함께 롤백된다.

    ``legacy_bridge`` 는 cycle 이 없는 레거시 AS 주문을 같은 tx 안에서 canonical 축으로
    끌어올린 뒤 전이를 진행한다(:func:`_open_legacy_bridge_cycle`). 기본 off — 켠 endpoint
    만 적용된다.
    """
    now = now or now_utc_naive()

    def _mutate(sess: Session, orders: List[Order]) -> Dict[int, List[str]]:
        order = orders[0]
        sd = copy.deepcopy(order.structured_data or {})
        if legacy_bridge:
            _open_legacy_bridge_cycle(sd, order, actor_user_id=actor_user_id, now=now)
        if sd_hook is not None:
            sd_hook(sd)
        payload = apply(sd, order)
        order.structured_data = sd
        flag_modified(order, "structured_data")
        _reproject_and_sync(order, sd)
        sess.add(OrderEvent(
            order_id=order.id, event_type=event_type, payload=payload,
            created_by_user_id=actor_user_id, created_at=now,
        ))
        sess.flush()
        return {order.id: [f"ORDER_DETAIL:{order.id}", "ORDERS_INDEX"]}

    return execute_order_mutation(
        session, actor_user_id=actor_user_id, policy_id=policy_id,
        order_ids=[order_id], scope_hash=scope_hash, request_hash=request_hash,
        mutation=_mutate,
        expected_versions=({order_id: expected_version} if expected_version is not None else None),
        idempotency_key=idempotency_key, now=now,
    )


# --------------------------------------------------------------------------- #
# canonical AS command
# --------------------------------------------------------------------------- #
def register_as_cycle(
    session: Session, *, order_id: int, actor_user_id: int, as_content: str,
    shipping_scheduled_date: Optional[str] = None, source_screen: Optional[str] = None,
    received_date: Optional[str] = None, construction_worker_name: Optional[str] = None,
    scope_hash: str, request_hash: str, now: Optional[datetime.datetime] = None,
    idempotency_key: Optional[str] = None,
    sd_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> MutationResult:
    """AS_REGISTER: 새 RECEIVED cycle 을 발급하고 current 로 교체한다(과거 cycle 보존).

    current cycle 이 열려 있으면(RECEIVED/IN_PROGRESS) 중복 접수로 거부(409). 완료된 이전
    cycle 은 이력으로 남고 새 cycle 이 append 된다. main stage 는 건드리지 않는다.
    ``received_date`` 는 endpoint 가 KST 로 계산해 넘긴다(get_today_kst monkeypatch 존중);
    ``construction_worker_name`` 이 있으면 shipment 담당자 projection 에 반영한다.
    """
    now = now or now_utc_naive()
    content = _require_text(as_content, field="AS 내용", min_len=0, max_len=_MAX_CONTENT)
    shipping = _require_iso_date(shipping_scheduled_date, field="상차일") if shipping_scheduled_date else None

    def _apply(sd: Dict[str, Any], order: Order) -> Dict[str, Any]:
        lifecycle = _lifecycle(sd)
        existing = current_cycle(sd)
        if existing is not None and cycle_status(existing) in (AS_RECEIVED, AS_IN_PROGRESS):
            raise ASCycleError("이미 진행 중인 AS 접수가 있습니다.")
        cycle_id = str(uuid.uuid4())
        cycle = {
            "cycle_id": cycle_id, "opened_at": now.isoformat(), "opened_by": actor_user_id,
            "initial_content": content, "initial_shipping_date": shipping,
            "classification": {f: False for f in CLASSIFICATION_FIELDS}, "transitions": [],
        }
        _append_transition(cycle, command="AS_REGISTER", from_status=AS_NONE,
                            to_status=AS_RECEIVED, payload={"as_content_len": len(content)},
                            actor_user_id=actor_user_id, now=now)
        lifecycle["cycles"].append(cycle)
        lifecycle["current_cycle_id"] = cycle_id
        shipment = sd.setdefault("shipment", {})
        shipment["as_content"] = content
        if construction_worker_name:
            shipment["construction_workers"] = [construction_worker_name]
        _apply_classification_projection(sd, cycle)
        order.as_received_date = received_date or _today_str()
        if shipping:
            order.shipping_scheduled_date = shipping
        return {"command": "AS_REGISTER", "cycle_id": cycle_id, "to": AS_RECEIVED,
                "source_screen": source_screen}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_REGISTER,
        event_type="AS_REGISTERED", apply=_apply, scope_hash=scope_hash,
        request_hash=request_hash, idempotency_key=idempotency_key, now=now,
        sd_hook=sd_hook,
    )


def schedule_as_cycle(
    session: Session, *, order_id: int, actor_user_id: int, visit_date: str,
    visit_time: Optional[str] = None, cycle_id: Optional[str] = None,
    scope_hash: str, request_hash: str, now: Optional[datetime.datetime] = None,
    idempotency_key: Optional[str] = None,
    sd_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    legacy_bridge: bool = False,
) -> MutationResult:
    """AS_SCHEDULE: current RECEIVED/IN_PROGRESS cycle 에 방문일/시각을 기록한다(상태 불변)."""
    now = now or now_utc_naive()
    date_str = _require_iso_date(visit_date, field="방문일")
    time_str = _optional_visit_time(visit_time)

    def _apply(sd: Dict[str, Any], order: Order) -> Dict[str, Any]:
        cycle = _require_open_cycle(sd, cycle_id, allow=(AS_RECEIVED, AS_IN_PROGRESS))
        status = cycle_status(cycle)
        _append_transition(cycle, command="AS_SCHEDULE", from_status=status, to_status=status,
                            payload={"visit_date": date_str, "visit_time": time_str},
                            actor_user_id=actor_user_id, now=now)
        _apply_visit_projection(sd, order, date_str, time_str)
        return {"command": "AS_SCHEDULE", "cycle_id": cycle.get("cycle_id"),
                "visit_date": date_str, "visit_time": time_str}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_SCHEDULE,
        event_type="AS_SCHEDULED", apply=_apply, scope_hash=scope_hash,
        request_hash=request_hash, idempotency_key=idempotency_key, now=now,
        sd_hook=sd_hook, legacy_bridge=legacy_bridge,
    )


def unschedule_as_cycle(
    session: Session, *, order_id: int, actor_user_id: int, reason: str,
    cycle_id: Optional[str] = None, scope_hash: str, request_hash: str,
    now: Optional[datetime.datetime] = None, idempotency_key: Optional[str] = None,
    sd_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    legacy_bridge: bool = False,
) -> MutationResult:
    """AS_UNSCHEDULE: current cycle 방문 날짜/시각을 명시적 transition 으로 clear 한다(상태 불변)."""
    now = now or now_utc_naive()
    reason_str = _require_text(reason, field="사유", min_len=1, max_len=_MAX_REASON)

    def _apply(sd: Dict[str, Any], order: Order) -> Dict[str, Any]:
        cycle = _require_open_cycle(sd, cycle_id, allow=(AS_RECEIVED, AS_IN_PROGRESS))
        status = cycle_status(cycle)
        _append_transition(cycle, command="AS_UNSCHEDULE", from_status=status, to_status=status,
                            payload={"visit_date": None, "visit_time": None, "reason": reason_str},
                            actor_user_id=actor_user_id, now=now)
        _apply_visit_projection(sd, order, None, None)
        return {"command": "AS_UNSCHEDULE", "cycle_id": cycle.get("cycle_id"), "reason": reason_str}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_UNSCHEDULE,
        event_type="AS_UNSCHEDULED", apply=_apply, scope_hash=scope_hash,
        request_hash=request_hash, idempotency_key=idempotency_key, now=now,
        sd_hook=sd_hook, legacy_bridge=legacy_bridge,
    )


def start_as_cycle(
    session: Session, *, order_id: int, actor_user_id: int, reason: str, description: str,
    cycle_id: Optional[str] = None, scope_hash: str, request_hash: str,
    now: Optional[datetime.datetime] = None, idempotency_key: Optional[str] = None,
) -> MutationResult:
    """AS_START: current RECEIVED cycle 을 IN_PROGRESS 로 전이한다(사유/설명 기록)."""
    now = now or now_utc_naive()
    reason_str = _require_text(reason, field="사유", min_len=1, max_len=_MAX_REASON)
    desc_str = _require_text(description, field="설명", min_len=1, max_len=_MAX_DESCRIPTION)

    def _apply(sd: Dict[str, Any], order: Order) -> Dict[str, Any]:
        cycle = _require_open_cycle(sd, cycle_id, allow=(AS_RECEIVED,))
        _append_transition(cycle, command="AS_START", from_status=AS_RECEIVED,
                            to_status=AS_IN_PROGRESS,
                            payload={"reason": reason_str, "description": desc_str},
                            actor_user_id=actor_user_id, now=now)
        return {"command": "AS_START", "cycle_id": cycle.get("cycle_id"), "to": AS_IN_PROGRESS}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_START,
        event_type="AS_STARTED", apply=_apply, scope_hash=scope_hash,
        request_hash=request_hash, idempotency_key=idempotency_key, now=now,
    )


def complete_as_cycle(
    session: Session, *, order_id: int, actor_user_id: int, note: str = "",
    cycle_id: Optional[str] = None, scope_hash: str, request_hash: str,
    now: Optional[datetime.datetime] = None, idempotency_key: Optional[str] = None,
    completed_date: Optional[str] = None, allow_from: Any = (AS_IN_PROGRESS,),
    sd_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    legacy_bridge: bool = False,
) -> MutationResult:
    """AS_COMPLETE: current cycle 을 COMPLETED 로 종결한다(완료 메모·완료일).

    ``allow_from`` 은 종결을 허용하는 출발 상태다. 기본값은 ``/as/complete`` 라우트 계약인
    IN_PROGRESS 전용이고, AS 대시보드 완료 버튼(``field_update`` as_completed_date 브리지)은
    RECEIVED cycle 을 곧바로 종결하는 실제 동선이라 ``(RECEIVED, IN_PROGRESS)`` 를 넘긴다.
    ``completed_date`` 는 사용자가 고른 완료일(``YYYY-MM-DD``); 생략하면 오늘(KST)이다.
    """
    now = now or now_utc_naive()
    note_str = _require_text(note, field="완료 메모", min_len=0, max_len=_MAX_NOTE)
    done_date = _require_iso_date(completed_date, field="완료일") if completed_date else None

    def _apply(sd: Dict[str, Any], order: Order) -> Dict[str, Any]:
        cycle = _require_open_cycle(sd, cycle_id, allow=allow_from)
        _append_transition(cycle, command="AS_COMPLETE", from_status=cycle_status(cycle),
                            to_status=AS_COMPLETED, payload={"note": note_str},
                            actor_user_id=actor_user_id, now=now)
        order.as_completed_date = done_date or _today_str()
        return {"command": "AS_COMPLETE", "cycle_id": cycle.get("cycle_id"), "to": AS_COMPLETED}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_COMPLETE,
        event_type="AS_COMPLETED", apply=_apply, scope_hash=scope_hash,
        request_hash=request_hash, idempotency_key=idempotency_key, now=now,
        sd_hook=sd_hook, legacy_bridge=legacy_bridge,
    )


def reopen_as_cycle(
    session: Session, *, order_id: int, actor_user_id: int, reason: str,
    cycle_id: Optional[str] = None, scope_hash: str, request_hash: str,
    now: Optional[datetime.datetime] = None, idempotency_key: Optional[str] = None,
    sd_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    legacy_bridge: bool = False,
) -> MutationResult:
    """AS_REOPEN: 오완료된 current COMPLETED cycle 을 **같은 cycle** 로 RECEIVED 로 되돌린다."""
    now = now or now_utc_naive()
    reason_str = _require_text(reason, field="사유", min_len=1, max_len=_MAX_REASON)

    def _apply(sd: Dict[str, Any], order: Order) -> Dict[str, Any]:
        cycle = _require_open_cycle(sd, cycle_id, allow=(AS_COMPLETED,))
        _append_transition(cycle, command="AS_REOPEN", from_status=AS_COMPLETED,
                            to_status=AS_RECEIVED, payload={"reason": reason_str},
                            actor_user_id=actor_user_id, now=now)
        order.as_completed_date = None
        return {"command": "AS_REOPEN", "cycle_id": cycle.get("cycle_id"), "to": AS_RECEIVED}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_REOPEN,
        event_type="AS_REOPENED", apply=_apply, scope_hash=scope_hash,
        request_hash=request_hash, idempotency_key=idempotency_key, now=now,
        sd_hook=sd_hook, legacy_bridge=legacy_bridge,
    )


def set_as_classification(
    session: Session, *, order_id: int, actor_user_id: int, field: str, value: bool,
    cycle_id: Optional[str] = None, scope_hash: str, request_hash: str,
    now: Optional[datetime.datetime] = None, idempotency_key: Optional[str] = None,
) -> MutationResult:
    """SET_AS_CLASSIFICATION: current cycle 분류 플래그를 토글한다(main·lifecycle status·방문 불변).

    ``field`` 는 ``as_pending|as_blueprint|sales_delivery``, ``value`` 는 boolean. cycle
    classification + shipment read projection(filter tab)만 갱신하고 상태/방문/main 은 불변이다.
    """
    now = now or now_utc_naive()
    if field not in CLASSIFICATION_FIELDS:
        raise ASCycleError(f"허용되지 않은 분류 필드입니다: {field}")
    flag = bool(value)

    def _apply(sd: Dict[str, Any], order: Order) -> Dict[str, Any]:
        cycle = _require_open_cycle(sd, cycle_id, allow=AS_VALUES)
        status = cycle_status(cycle)
        classification = cycle.get("classification")
        if not isinstance(classification, dict):
            classification = {f: False for f in CLASSIFICATION_FIELDS}
        classification[field] = flag
        cycle["classification"] = classification
        _append_transition(cycle, command="SET_AS_CLASSIFICATION", from_status=status,
                            to_status=status, payload={"field": field, "value": flag},
                            actor_user_id=actor_user_id, now=now)
        _apply_classification_projection(sd, cycle)
        return {"command": "SET_AS_CLASSIFICATION", "cycle_id": cycle.get("cycle_id"),
                "field": field, "value": flag}

    return _run_as_command(
        session, order_id=order_id, actor_user_id=actor_user_id, policy_id=POLICY_AS_CLASSIFICATION,
        event_type="AS_CLASSIFICATION_CHANGED", apply=_apply, scope_hash=scope_hash,
        request_hash=request_hash, idempotency_key=idempotency_key, now=now,
    )


# --------------------------------------------------------------------------- #
# projection / lookup 보조
# --------------------------------------------------------------------------- #
def _require_open_cycle(
    sd: Dict[str, Any], cycle_id: Optional[str], *, allow: Any
) -> Dict[str, Any]:
    """current cycle 을 돌려주되, 지정 cycle_id 불일치나 허용 상태 밖이면 거부(409)."""
    cycle = current_cycle(sd)
    if cycle is None:
        raise ASCycleError("현재 진행 중인 AS cycle 이 없습니다.")
    if cycle_id is not None and str(cycle.get("cycle_id")) != str(cycle_id):
        raise ASCycleError("현재 AS cycle 과 일치하지 않습니다.")
    if cycle_status(cycle) not in allow:
        raise ASCycleError(
            f"현재 AS 상태({cycle_status(cycle)})에서 수행할 수 없는 작업입니다."
        )
    return cycle


def _apply_visit_projection(
    sd: Dict[str, Any], order: Order, visit_date: Optional[str], visit_time: Optional[str]
) -> None:
    """방문 날짜/시각을 legacy read projection(schedule.as_visit)으로 투영한다.

    ``as_visit_date`` 는 mapped 컬럼이 아니라 ``schedule.as_visit.date`` JSON 이 canonical
    이므로 그곳만 갱신한다(unschedule 은 None 으로 clear).
    """
    schedule = sd.setdefault("schedule", {})
    as_visit = schedule.get("as_visit")
    if not isinstance(as_visit, dict):
        as_visit = {}
    as_visit["date"] = visit_date
    as_visit["time"] = visit_time
    as_visit["type"] = "AS"
    schedule["as_visit"] = as_visit


def _apply_classification_projection(sd: Dict[str, Any], cycle: Dict[str, Any]) -> None:
    """cycle classification 을 shipment read projection(filter tab)으로 투영한다."""
    shipment = sd.setdefault("shipment", {})
    classification = cycle.get("classification") or {}
    for field in CLASSIFICATION_FIELDS:
        shipment[field] = bool(classification.get(field))


def _today_str() -> str:
    """오늘(KST) ``YYYY-MM-DD`` 문자열. get_today_kst 는 date 반환(.date() 금지)."""
    from foms.services.erp_display import get_today_kst

    return get_today_kst().strftime("%Y-%m-%d")


__all__ = [
    "ASCycleError",
    "LEGACY_BRIDGE_ORIGIN",
    "AS_NONE",
    "AS_RECEIVED",
    "AS_IN_PROGRESS",
    "AS_COMPLETED",
    "CLASSIFICATION_FIELDS",
    "current_cycle",
    "cycle_status",
    "project_current_as_cycle",
    "register_as_cycle",
    "schedule_as_cycle",
    "unschedule_as_cycle",
    "start_as_cycle",
    "complete_as_cycle",
    "reopen_as_cycle",
    "set_as_classification",
]
