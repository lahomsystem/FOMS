"""flat AS 데이터 → UUID AS cycle 매핑 audit/분류 (AS-BACKFILL-00, §5.2).

주문의 flat ``structured_data['as_info']``(접수/방문일정/완료가 뭉친 entry 리스트)와 flat
``order.status`` 의 AS 축(:func:`~foms.services.orders.state_axes.read_as_status`)을 **read-only
로 분류**한다. 핵심 계약은 **자동 매핑 0** — 사람이 봐야 하는 주문은 절대 자동 backfill 하지
않는다:

* :func:`audit_as_cycles` 는 아무 것도 쓰지 않는다(순수 조회).
* **SAFE**: ``as_info`` entry 들이 well-formed 이고, 열린(OPEN) entry 가 **최대 1개**
  (current cycle 0/1)이며, 그 열림 상태가 flat AS 축(:func:`read_as_status`)과 **일치**하는
  주문 → entry 마다 cycle 로 정확 매핑한다(열린 entry=IN_PROGRESS current, 닫힌 entry=
  COMPLETED 이력). classification(사유/설명)·schedule(방문일)·completion(완료)은 entry
  스냅샷으로 복제된다.
* **AMBIGUOUS**: 열린 entry 가 복수(:data:`MULTIPLE_OPEN` — current cycle>1), flat AS 축과
  ``as_info`` 열림 상태가 불일치(:data:`STATUS_MISMATCH` — 예: flat ``AS_RECEIVED`` 인데
  as_info 열린 entry 0, 또는 flat 닫힘인데 열린 entry 잔존), ``as_info``/entry 구조 이상
  (:data:`MALFORMED`) → 수동 CSV 로 보낸다(자동 cycle 발급/선택 금지).
* AS 활동이 전혀 없는 주문(``as_info`` 없음·빈 리스트 + flat AS 축 NONE)은 대상에서 제외한다.

**전이(create/complete) 활성화는 하류 STATE-AS-01 소관** 이므로 이 audit 은 flat status/
history/stage 를 **재작성하지 않고**(inferred stage rewrite 금지), 열린 entry 가 여러 개일 때
어느 것이 current 인지 **자동 선택하지 않는다**(ambiguous cycle auto-select 금지).

**in-flight AS current 100%**: :attr:`ASCycleAudit.in_flight_ids`(flat AS 축이 열린 상태
``RECEIVED``/``IN_PROGRESS`` 인 주문)가 모두 SAFE(current cycle 보유)인지는
:meth:`ASCycleAudit.covers_all_in_flight` 로 검사한다 — ambiguous in-flight 주문이 있으면
coverage < 100% 이고 enforcement 는 게이트된다(:func:`backfill_as_cycles.can_enforce`).

ponytail: 이 audit 은 as_info→UUID cycle 분류라 형제 ``audit_production_runs`` /
``audit_order_item_identities`` 와 동일한 lite 패턴을 쓴다 — BACKFILL-ARTIFACT-00 의 암호화
run state machine(lease/checkpoint/OPS-APPROVAL)까지 끌어오지 않는다.
"""
from __future__ import annotations

import copy
import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from foms.services.orders.state_axes import read_as_status

# AS cycle status(§2.2 AS axis read-model; NONE 는 cycle 미발급이라 저장 안 함).
CYCLE_RECEIVED = "RECEIVED"
CYCLE_IN_PROGRESS = "IN_PROGRESS"
CYCLE_COMPLETED = "COMPLETED"

# flat AS 축의 "열린(current 요구)" 값(NONE·COMPLETED 는 current cycle 불필요).
_OPEN_AS_AXIS: FrozenSet[str] = frozenset({CYCLE_RECEIVED, CYCLE_IN_PROGRESS})

# as_info entry 의 flat status 값.
_ENTRY_OPEN = "OPEN"
_ENTRY_COMPLETED = "COMPLETED"

# ambiguous 사유 코드.
MULTIPLE_OPEN = "MULTIPLE_OPEN"        # 열린 entry 복수 → current cycle>1(자동 선택 금지)
STATUS_MISMATCH = "STATUS_MISMATCH"    # flat AS 축과 as_info 열림 상태 불일치
MALFORMED = "MALFORMED"                # as_info/entry 구조 이상


@dataclass(frozen=True)
class ASCycle:
    """AS cycle 1개의 결정적 스냅샷(flat as_info entry 복제).

    Attributes:
        legacy_as_id: 발급 근거 ``as_info`` entry id(provenance·멱등 키).
        status: cycle 상태(:data:`CYCLE_IN_PROGRESS`(열림) 또는 :data:`CYCLE_COMPLETED`).
        is_current: 현재 열린 cycle 여부(주문당 최대 1개).
        started_at: 시작 시각 ISO 문자열(transition — 없으면 None).
        started_by: 시작 담당(없으면 None).
        reason: AS 사유(classification — 없으면 None).
        description: AS 설명(classification — 없으면 None).
        visit_date: 방문일(schedule — 없으면 None).
        visit_time: 방문 시각(schedule — 없으면 None).
        completed_at: 완료 시각 ISO 문자열(completion — 없으면 None).
        completed_by: 완료 담당(없으면 None).
        completion_note: 완료 메모(없으면 None).
    """

    legacy_as_id: int
    status: str
    is_current: bool
    started_at: Optional[str]
    started_by: Optional[str]
    reason: Optional[str]
    description: Optional[str]
    visit_date: Optional[str]
    visit_time: Optional[str]
    completed_at: Optional[str]
    completed_by: Optional[str]
    completion_note: Optional[str]


@dataclass(frozen=True)
class ASCyclePlan:
    """SAFE 주문 1건의 결정적 backfill plan(cycle 목록·current 최대 1개).

    Attributes:
        order_id: 주문 id.
        cycles: 발급할 cycle 목록(legacy_as_id 오름차순, 열린 cycle 은 최대 1개).
    """

    order_id: int
    cycles: Tuple[ASCycle, ...]

    def has_current(self) -> bool:
        """열린(current) cycle 을 하나 가지고 있는가(coverage 판정)."""
        return any(c.is_current for c in self.cycles)


@dataclass(frozen=True)
class AmbiguousASCycle:
    """자동 매핑 불가한 주문 1건(수동 CSV 대상·read-only).

    Attributes:
        order_id: 주문 id.
        as_axis: 발견 시점 flat AS 축 값(참고).
        open_count: 열린 as_info entry 수.
        total_count: 전체 as_info entry 수.
        as_info: flat ``as_info`` 스냅샷(수동 검토용).
        reason: :data:`MULTIPLE_OPEN` | :data:`STATUS_MISMATCH` | :data:`MALFORMED`.
    """

    order_id: int
    as_axis: str
    open_count: int
    total_count: int
    as_info: Any
    reason: str


@dataclass(frozen=True)
class ASCycleAudit:
    """분류 결과(read-only).

    Attributes:
        safe: SAFE 주문의 backfill plan 목록(order_id 오름차순).
        ambiguous: 자동 매핑 불가 주문 목록(수동 CSV 대상).
        in_flight_ids: flat AS 축이 열린(``RECEIVED``/``IN_PROGRESS``) 주문 id 집합(coverage 기준).
    """

    safe: Tuple[ASCyclePlan, ...]
    ambiguous: Tuple[AmbiguousASCycle, ...]
    in_flight_ids: FrozenSet[int]

    def covers_all_in_flight(self) -> bool:
        """모든 in-flight AS 주문이 current cycle 을 갖는 SAFE plan 인가(100% 매핑)."""
        covered = {p.order_id for p in self.safe if p.has_current()}
        return self.in_flight_ids <= covered


def _as_info(sd: Any) -> Any:
    """``structured_data['as_info']`` 를 그대로 반환(부재 시 None)."""
    if not isinstance(sd, dict):
        return None
    return sd.get("as_info")


def _entry_state(entry: Dict[str, Any]) -> Optional[str]:
    """as_info entry 의 열림/닫힘 상태(:data:`_ENTRY_OPEN`/:data:`_ENTRY_COMPLETED`).

    status 필드가 정본. 알 수 없는 값이면 None(→ malformed 판정).
    """
    raw = str(entry.get("status") or "").strip().upper()
    if raw in (_ENTRY_OPEN, _ENTRY_COMPLETED):
        return raw
    return None


def _entries_wellformed(as_info: Any) -> bool:
    """as_info 가 dict 리스트이고 각 entry 가 정수 id·인식 가능한 status 를 갖는가."""
    if not isinstance(as_info, list):
        return False
    for entry in as_info:
        if not isinstance(entry, dict):
            return False
        if not isinstance(entry.get("id"), int):
            return False
        if _entry_state(entry) is None:
            return False
    return True


def _cycle_from_entry(entry: Dict[str, Any], *, is_current: bool) -> ASCycle:
    """well-formed as_info entry 를 cycle 스냅샷으로 변환한다(원문 복제·flat 보존)."""
    completed = _entry_state(entry) == _ENTRY_COMPLETED
    return ASCycle(
        legacy_as_id=int(entry["id"]),
        status=CYCLE_COMPLETED if completed else CYCLE_IN_PROGRESS,
        is_current=is_current,
        started_at=_opt_str(entry.get("started_at")),
        started_by=_opt_str(entry.get("started_by")),
        reason=_opt_str(entry.get("reason")),
        description=_opt_str(entry.get("description")),
        visit_date=_opt_str(entry.get("visit_date")),
        visit_time=_opt_str(entry.get("visit_time")),
        completed_at=_opt_str(entry.get("completed_at")),
        completed_by=_opt_str(entry.get("completed_by")),
        completion_note=_opt_str(entry.get("completion_note")),
    )


def _opt_str(value: Any) -> Optional[str]:
    """빈 값은 None, 그 외는 원문 문자열로(스냅샷 정규화)."""
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def classify_order(order: Any) -> Optional[object]:
    """한 주문을 SAFE plan / ambiguous / None(대상 제외)로 분류한다(read-only).

    Args:
        order: ``structured_data``·``status`` 속성을 가진 주문 row.

    Returns:
        :class:`ASCyclePlan` (SAFE) | :class:`AmbiguousASCycle` (수동 CSV)
        | ``None`` (AS 활동 없음 — cycle 미발급).
    """
    order_id = getattr(order, "id", None)
    sd = getattr(order, "structured_data", None)
    as_axis = read_as_status(order)
    as_info = _as_info(sd)
    entries = as_info if isinstance(as_info, list) else []

    # as_info 키가 있는데 리스트/entry 구조가 이상하면 malformed.
    if as_info is not None and not _entries_wellformed(as_info):
        return _ambiguous(order_id, as_axis, as_info, MALFORMED)

    open_entries = [e for e in entries if _entry_state(e) == _ENTRY_OPEN]
    open_count = len(open_entries)
    flat_open = as_axis in _OPEN_AS_AXIS

    if not entries:
        # as_info 없음/빈 리스트: flat 이 열린 AS 면 registry 누락(수동 검토), 아니면 대상 아님.
        if flat_open:
            return _ambiguous(order_id, as_axis, as_info, STATUS_MISMATCH)
        return None

    if open_count > 1:
        # 열린 cycle 이 복수 → current 를 자동 선택하지 않는다.
        return _ambiguous(order_id, as_axis, as_info, MULTIPLE_OPEN)

    # flat AS 축과 as_info 열림 상태가 어긋나면 수동 검토(자동 조정 금지).
    #   flat 열림인데 열린 entry 0  → registry 누락/불일치.
    #   flat 닫힘인데 열린 entry 1  → 잔존 열림 cycle.
    if flat_open != (open_count == 1):
        return _ambiguous(order_id, as_axis, as_info, STATUS_MISMATCH)

    open_id = id(open_entries[0]) if open_count == 1 else None
    cycles = tuple(
        _cycle_from_entry(e, is_current=(id(e) == open_id))
        for e in sorted(entries, key=lambda e: int(e["id"]))
    )
    return ASCyclePlan(order_id=order_id, cycles=cycles)


def _ambiguous(
    order_id: Any, as_axis: str, as_info: Any, reason: str
) -> AmbiguousASCycle:
    """ambiguous 레코드 구성(as_info 는 원문 그대로 스냅샷 — 수동 검토용)."""
    entries = as_info if isinstance(as_info, list) else []
    open_count = sum(
        1 for e in entries if isinstance(e, dict) and _entry_state(e) == _ENTRY_OPEN
    )
    return AmbiguousASCycle(
        order_id=order_id,
        as_axis=as_axis,
        open_count=open_count,
        total_count=len(entries),
        as_info=copy.deepcopy(as_info) if isinstance(as_info, (list, dict)) else as_info,
        reason=reason,
    )


def iter_orders(session: Session, *, batch_size: int = 1000) -> Iterable[Any]:
    """모든 주문 row 를 스트리밍(read-only, 전수 coverage)."""
    from models import Order

    for order in session.query(Order).order_by(Order.id).yield_per(batch_size):
        yield order


def audit_as_cycles(session: Session, *, batch_size: int = 1000) -> ASCycleAudit:
    """전체 주문을 분류해 SAFE plan·ambiguous·in-flight 집합을 만든다(mutation 0).

    Args:
        session: SQLAlchemy Session(read-only 로만 사용).
        batch_size: 스트리밍 yield_per 크기.

    Returns:
        :class:`ASCycleAudit`.
    """
    safe: List[ASCyclePlan] = []
    ambiguous: List[AmbiguousASCycle] = []
    in_flight: set[int] = set()
    for order in iter_orders(session, batch_size=batch_size):
        if read_as_status(order) in _OPEN_AS_AXIS:
            in_flight.add(order.id)
        result = classify_order(order)
        if isinstance(result, ASCyclePlan):
            safe.append(result)
        elif isinstance(result, AmbiguousASCycle):
            ambiguous.append(result)
    safe.sort(key=lambda p: p.order_id)
    ambiguous_sorted = tuple(sorted(ambiguous, key=lambda a: a.order_id))
    return ASCycleAudit(tuple(safe), ambiguous_sorted, frozenset(in_flight))


def to_manual_csv(audit: ASCycleAudit) -> str:
    """ambiguous 주문을 수동 매핑용 CSV 문자열로 내보낸다(header 포함).

    Args:
        audit: :func:`audit_as_cycles` 결과.

    Returns:
        ``order_id,as_axis,open_count,total_count,legacy_as_info_json,decision,reason,
        approved_by_user_id`` CSV(ambiguous 행만·자동 매핑 0·target 공란).
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "order_id", "as_axis", "open_count", "total_count", "legacy_as_info_json",
        "decision", "reason", "approved_by_user_id",
    ])
    for ref in audit.ambiguous:
        writer.writerow([
            ref.order_id,
            ref.as_axis,
            ref.open_count,
            ref.total_count,
            json.dumps(ref.as_info, ensure_ascii=False, default=str),
            "MANUAL",      # decision: 사람이 결정(자동 cycle 발급/선택 금지).
            ref.reason,
            "",            # approved_by_user_id: 승인 전.
        ])
    return buf.getvalue()


__all__ = [
    "CYCLE_RECEIVED",
    "CYCLE_IN_PROGRESS",
    "CYCLE_COMPLETED",
    "MULTIPLE_OPEN",
    "STATUS_MISMATCH",
    "MALFORMED",
    "ASCycle",
    "ASCyclePlan",
    "AmbiguousASCycle",
    "ASCycleAudit",
    "classify_order",
    "audit_as_cycles",
    "to_manual_csv",
]
