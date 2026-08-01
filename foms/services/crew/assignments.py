"""주문↔설치 작업자 배정 registry + audit + backfill (CREW-00, §5.2).

:class:`~models.OrderInstallationAssignment` 배정 mechanics 를 제공한다:

* assign/replace/release, 주문당 활성 **0..20명** 상한, release history 보존.
* 동시성: 주문 행을 ``SELECT ... FOR UPDATE`` 로 잠가 배정 command 를 직렬화한다
  (cap 계산 race·중복 active 방지). partial unique ``uq_order_installation_active`` 가
  DB 레벨 backstop 이다.
* audit: 주문의 배정 이력(active+released) 조회.
* backfill: 기존 free-name(``structured_data.shipment.construction_workers``)을 마스터
  worker 로 **audit(분류)** 후 **명시 apply** 한다. 자동 승격 0 · free-name master write
  금지 — apply 는 이미 등록된 worker id 로만 배정한다.

경계(CREW-00): 배정 row 를 authorization 에 쓰지 않는다. route 실배선은 하류
(SHIPMENT-REFERENCE-01) — 여기선 라이브러리만.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.crew.workers import CrewError, CrewValidationError
from models import InstallationWorker, Order, OrderInstallationAssignment

MAX_INSTALLATION_WORKERS = 20
MIN_INSTALLATION_WORKERS = 0
REASON_MAX = 500


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #
class AssignmentCapExceededError(CrewError):
    """주문 활성 설치 작업자가 상한(20)을 넘음. 409."""

    status_code = 409
    error_code = "INSTALLATION_ASSIGNMENT_CAP"

    def __init__(self, order_id: int, requested: int):
        super().__init__(
            f"order {order_id} would have {requested} active installation workers "
            f"(max {MAX_INSTALLATION_WORKERS})."
        )
        self.order_id = order_id
        self.requested = requested


class WorkerAlreadyAssignedError(CrewError):
    """이미 활성 배정된 worker 를 같은 주문에 다시 배정. 409."""

    status_code = 409
    error_code = "WORKER_ALREADY_ASSIGNED"

    def __init__(self, order_id: int, worker_id: int):
        super().__init__(
            f"worker {worker_id} is already actively assigned to order {order_id}."
        )
        self.order_id = order_id
        self.worker_id = worker_id


class AssignmentNotActiveError(CrewError):
    """release 대상 active 배정 row 가 없음(또는 이미 released). 409."""

    status_code = 409
    error_code = "INSTALLATION_ASSIGNMENT_NOT_ACTIVE"

    def __init__(self, order_id: int, worker_id: int):
        super().__init__(
            f"no active installation assignment for order {order_id}, worker {worker_id}."
        )
        self.order_id = order_id
        self.worker_id = worker_id


class InactiveWorkerError(CrewValidationError):
    """비활성 worker 를 신규 배정하려 함. 422."""

    error_code = "INSTALLATION_WORKER_INACTIVE"

    def __init__(self, worker_id: int):
        super().__init__(f"installation worker {worker_id} is inactive or missing.")
        self.worker_id = worker_id


# --------------------------------------------------------------------------- #
# 내부 helper
# --------------------------------------------------------------------------- #
def _lock_order(session: Session, order_id: int) -> Order:
    """배정 mutation 직렬화용 주문 행 ``FOR UPDATE`` lock (없으면 검증 오류).

    주문 행 하나를 lock 해 (order 당) cap 계산·중복 검사 사이의 race 를 없앤다.
    """
    order = (
        session.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .one_or_none()
    )
    if order is None:
        raise CrewValidationError(f"order {order_id} not found.")
    return order


def _active_rows(session: Session, order_id: int) -> List[OrderInstallationAssignment]:
    """주문의 현재 active 배정 row(assigned_at→id 정렬)."""
    return (
        session.query(OrderInstallationAssignment)
        .filter(
            OrderInstallationAssignment.order_id == order_id,
            OrderInstallationAssignment.status == 'ACTIVE',
        )
        .order_by(
            OrderInstallationAssignment.assigned_at.asc(),
            OrderInstallationAssignment.id.asc(),
        )
        .all()
    )


def _assert_active_worker(session: Session, worker_id: int) -> None:
    """worker 가 실존·활성인지 검증(신규 배정 전)."""
    worker = session.get(InstallationWorker, worker_id)
    if worker is None or not worker.is_active:
        raise InactiveWorkerError(worker_id)


def _clean_reason(reason: Optional[str], *, required: bool) -> Optional[str]:
    """release/replace 사유 trim; required 면 1..500 강제."""
    trimmed = (reason or "").strip()
    if not trimmed:
        if required:
            raise CrewValidationError("reason is required (1..500 chars).")
        return None
    if len(trimmed) > REASON_MAX:
        raise CrewValidationError(f"reason exceeds {REASON_MAX} chars.")
    return trimmed


# --------------------------------------------------------------------------- #
# registry commands
# --------------------------------------------------------------------------- #
def assign_worker(
    session: Session, *, order_id: int, worker_id: int,
    actor_user_id: Optional[int] = None, now: Optional[datetime.datetime] = None,
) -> OrderInstallationAssignment:
    """설치 작업자 한 명을 주문에 활성 배정한다(상한 20·중복 방지).

    주문 행 ``FOR UPDATE`` lock 아래에서 cap(≤20)·중복 active 를 검사하고 삽입한다.
    이미 활성 배정된 worker 면 :class:`WorkerAlreadyAssignedError`(409). 상한 초과면
    :class:`AssignmentCapExceededError`(409). 비활성/미존재 worker 면
    :class:`InactiveWorkerError`(422). 호출자가 ``session.commit()`` 한다.

    Returns:
        flush 된 active :class:`OrderInstallationAssignment`.
    """
    ts = now or now_utc_naive()
    _lock_order(session, order_id)
    _assert_active_worker(session, worker_id)
    active = _active_rows(session, order_id)
    if any(r.worker_id == worker_id for r in active):
        raise WorkerAlreadyAssignedError(order_id, worker_id)
    if len(active) + 1 > MAX_INSTALLATION_WORKERS:
        raise AssignmentCapExceededError(order_id, len(active) + 1)
    row = OrderInstallationAssignment(
        order_id=order_id, worker_id=worker_id, status='ACTIVE',
        assigned_at=ts, assigned_by_user_id=actor_user_id,
    )
    session.add(row)
    session.flush()
    return row


def release_worker(
    session: Session, *, order_id: int, worker_id: int, reason: str,
    actor_user_id: Optional[int] = None, now: Optional[datetime.datetime] = None,
) -> OrderInstallationAssignment:
    """(order,worker) 의 active 배정 한 건을 release 한다(이력 보존).

    hard delete 하지 않고 ``status='RELEASED'`` + released_* 로 이력을 남긴다. active
    배정이 없으면 :class:`AssignmentNotActiveError`(409). reason 1..500 필수.

    Returns:
        released 된 row.
    """
    ts = now or now_utc_naive()
    clean = _clean_reason(reason, required=True)
    _lock_order(session, order_id)
    row = (
        session.query(OrderInstallationAssignment)
        .filter(
            OrderInstallationAssignment.order_id == order_id,
            OrderInstallationAssignment.worker_id == worker_id,
            OrderInstallationAssignment.status == 'ACTIVE',
        )
        .one_or_none()
    )
    if row is None:
        raise AssignmentNotActiveError(order_id, worker_id)
    row.status = 'RELEASED'
    row.released_at = ts
    row.released_by_user_id = actor_user_id
    row.release_reason = clean
    session.flush()
    return row


def replace_workers(
    session: Session, *, order_id: int, worker_ids: Sequence[int],
    reason: Optional[str] = None, actor_user_id: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> List[OrderInstallationAssignment]:
    """주문의 활성 설치 작업자 집합을 ``worker_ids`` 로 replace 한다(set 의미).

    빠진 worker 는 release(이력 보존), 추가 worker 는 assign 한다. 이미 배정된 worker 는
    그대로 두어 assigned_at 이력을 보존한다. 목표 집합 크기는 0..20 이어야 한다(초과면
    :class:`AssignmentCapExceededError`). 중복 worker_id 나 비활성 worker 는 거부한다.
    주문 행 ``FOR UPDATE`` lock 아래 한 tx 로 처리한다.

    Returns:
        replace 후 남은 active row 목록(assigned_at 정렬).
    """
    ts = now or now_utc_naive()
    ids = [int(w) for w in worker_ids]
    if len(set(ids)) != len(ids):
        raise CrewValidationError("duplicate worker_id in replace set.")
    if len(ids) > MAX_INSTALLATION_WORKERS:
        raise AssignmentCapExceededError(order_id, len(ids))
    clean = _clean_reason(reason, required=False)
    _lock_order(session, order_id)
    for wid in ids:
        _assert_active_worker(session, wid)
    current = {r.worker_id: r for r in _active_rows(session, order_id)}
    target = set(ids)
    for wid, row in current.items():
        if wid not in target:
            row.status = 'RELEASED'
            row.released_at = ts
            row.released_by_user_id = actor_user_id
            row.release_reason = clean or "REPLACED"
    for wid in ids:
        if wid not in current:
            session.add(OrderInstallationAssignment(
                order_id=order_id, worker_id=wid, status='ACTIVE',
                assigned_at=ts, assigned_by_user_id=actor_user_id,
            ))
    session.flush()
    return _active_rows(session, order_id)


# --------------------------------------------------------------------------- #
# audit (배정 이력 조회) + active projection
# --------------------------------------------------------------------------- #
def active_worker_ids(session: Session, order_id: int) -> List[int]:
    """주문의 현재 active 설치 작업자 worker_id(정렬). (표시·picker 용)."""
    rows = (
        session.query(OrderInstallationAssignment.worker_id)
        .filter(
            OrderInstallationAssignment.order_id == order_id,
            OrderInstallationAssignment.status == 'ACTIVE',
        )
    )
    return sorted(wid for (wid,) in rows)


def assignment_history(session: Session, order_id: int) -> List[dict]:
    """주문의 설치 작업자 배정 이력(active+released)을 시간순 projection.

    Returns:
        배정 row projection dict 목록(assigned_at→id 정렬). release 메타 포함.
    """
    rows = (
        session.query(OrderInstallationAssignment)
        .filter(OrderInstallationAssignment.order_id == order_id)
        .order_by(
            OrderInstallationAssignment.assigned_at.asc(),
            OrderInstallationAssignment.id.asc(),
        )
        .all()
    )
    return [
        {
            "id": r.id,
            "worker_id": r.worker_id,
            "status": r.status,
            "assigned_at": r.assigned_at,
            "assigned_by_user_id": r.assigned_by_user_id,
            "released_at": r.released_at,
            "released_by_user_id": r.released_by_user_id,
            "release_reason": r.release_reason,
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# backfill (free-name → 마스터 배정; 자동 승격 0)
# --------------------------------------------------------------------------- #
def _normalize_name(name) -> str:
    """free-name 정규화(shipment read-model 과 동일 규칙: trim+lower)."""
    return str(name or "").strip().lower()


@dataclass(frozen=True)
class FreeNameAudit:
    """free-name 배정 분류 결과(read-only).

    Attributes:
        matched: ``normalized_name -> worker_id`` (활성 마스터 display_name exact 매치).
        unmatched: 활성 마스터에 매치되지 않은 free-name(정규화) — 수동 마스터 등록 대상.
        occurrences: ``normalized_name -> [order_id, ...]`` (free-name 이 나타난 주문).
    """

    matched: Dict[str, int]
    unmatched: List[str]
    occurrences: Dict[str, List[int]]


def audit_free_names(session: Session) -> FreeNameAudit:
    """기존 free-name 설치 작업자를 활성 마스터로 분류한다(아무 것도 쓰지 않음).

    ``structured_data.shipment.construction_workers`` 의 이름들을 활성
    :class:`InstallationWorker.display_name`(정규화 exact) 로 매핑한다. 매치되지 않은
    이름은 수동 마스터 등록 대상으로 unmatched 에 남긴다(자동 마스터 생성 금지). 기존
    free-name 데이터가 없으면 빈 결과(no-op).

    Returns:
        :class:`FreeNameAudit`.
    """
    name_to_worker: Dict[str, int] = {}
    for w in (
        session.query(InstallationWorker)
        .filter(InstallationWorker.is_active.is_(True))
        .all()
    ):
        key = _normalize_name(w.display_name)
        if key and key not in name_to_worker:
            name_to_worker[key] = w.id

    occurrences: Dict[str, List[int]] = {}
    for order in session.query(Order).filter(Order.structured_data.isnot(None)).all():
        sd = order.structured_data
        if not isinstance(sd, dict):
            continue
        workers = (sd.get('shipment') or {}).get('construction_workers') or []
        if not isinstance(workers, (list, tuple)):
            continue
        for raw in workers:
            key = _normalize_name(raw)
            if key:
                occurrences.setdefault(key, [])
                if order.id not in occurrences[key]:
                    occurrences[key].append(order.id)

    matched = {k: name_to_worker[k] for k in occurrences if k in name_to_worker}
    unmatched = sorted(k for k in occurrences if k not in name_to_worker)
    return FreeNameAudit(matched=matched, unmatched=unmatched, occurrences=occurrences)


def apply_backfill(
    session: Session, pairs: Iterable[Tuple[int, int]], *,
    actor_user_id: Optional[int] = None, now: Optional[datetime.datetime] = None,
) -> int:
    """명시 승인된 (order_id, worker_id) 배정을 만든다(자동 승격 0).

    ``pairs`` 는 :func:`audit_free_names` 결과를 사람이 검토해 확정한 (order_id,
    worker_id) 목록이다 — free-name 이 아니라 **이미 등록된 마스터 worker id** 로만
    배정한다(free-name master write 금지). 각 배정은 :func:`assign_worker` 를 거쳐 cap·
    중복·활성 검증을 받으며, 이미 활성인 (order,worker) 는 조용히 건너뛴다(idempotent).
    빈 입력이면 no-op(0).

    Returns:
        새로 만든 active 배정 수.
    """
    created = 0
    for order_id, worker_id in pairs:
        if worker_id in active_worker_ids(session, order_id):
            continue  # 이미 활성 — idempotent skip.
        assign_worker(
            session, order_id=order_id, worker_id=worker_id,
            actor_user_id=actor_user_id, now=now,
        )
        created += 1
    return created


__all__ = [
    "MAX_INSTALLATION_WORKERS", "MIN_INSTALLATION_WORKERS", "REASON_MAX",
    "AssignmentCapExceededError", "WorkerAlreadyAssignedError",
    "AssignmentNotActiveError", "InactiveWorkerError",
    "assign_worker", "release_worker", "replace_workers",
    "active_worker_ids", "assignment_history",
    "FreeNameAudit", "audit_free_names", "apply_backfill",
]
