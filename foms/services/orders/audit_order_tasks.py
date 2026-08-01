"""flat order_tasks → UUID identity 매핑 audit/분류 (TASK-BACKFILL-00, §5.2).

기존 :class:`~models.OrderTask` (auto-increment ``id`` 로만 식별되는 flat task)를 안정
UUID identity 로 정본화하기 전에 **read-only 로 분류**한다. 핵심 계약은 **자동 매핑 0** —
사람이 봐야 하는 task 는 절대 자동 backfill 하지 않는다:

* :func:`audit_order_tasks` 는 아무 것도 쓰지 않는다(순수 조회).
* **SAFE**: 6개 축(orphan/status/date/team/user/auto_key)이 모두 깨끗한 task →
  UUID/version/LEGACY provenance seed 대상.
* **AMBIGUOUS**: 아래 이상이 하나라도 있으면 quarantine(수동 CSV) — 자동 identity 발급
  금지:

  * :data:`ORPHAN` — 주문이 없거나 soft-delete(``status='DELETED'``/``deleted_at``)된 task.
  * :data:`BAD_STATUS` — status ∉ :data:`KNOWN_STATUSES`.
  * :data:`BAD_DATE` — ``due_date`` 가 있는데 ``YYYY-MM-DD`` 로 파싱 불가.
  * :data:`BAD_TEAM` — ``owner_team`` 이 있는데 정규화 후 canonical 팀이 아님.
  * :data:`BAD_USER` — ``owner_user_id`` 가 있는데 활성(``is_active``) User 아님(부재/비활성).
  * :data:`AUTO_COLLISION` — 같은 ``(order_id, meta.auto_key)`` 를 가진 **활성**(OPEN/
    IN_PROGRESS) task 가 2개 이상(auto 업서트 불변식 위반 → 어느 것이 정본인지 자동
    선택 금지).

**MEASURE→SALES safe mapping**: legacy pseudo-team ``MEASURE`` 는
:func:`~foms.services.orders.order_mutation_policy.normalize_team` 로 canonical ``SALES``
로 정규화되므로 team-clean 이다(BAD_TEAM 아님) — 이 정규화는 SSOT(AUTH-01) 를 재사용하며
기존 ``owner_team`` 컬럼을 **재작성하지 않는다**(expand 단계·근본은 하류 정규화 소관).

**creator 추정 금지**: task 를 누가 만들었는지는 추론하지 않는다. provenance 는 항상
``'LEGACY'`` 표식일 뿐이고(backfill), owner_user_id 는 **존재 검증만** 한다(추정/보정 없음).
전이(create/complete)·active task collision enforcement 는 하류 TASK-01 소관이다.

ponytail: 이 audit 은 flat→UUID 분류라 형제 ``audit_as_cycles`` /
``audit_order_item_identities`` 와 동일한 lite 패턴을 쓴다 — 무거운 run state machine
(lease/checkpoint/OPS-APPROVAL)까지 끌어오지 않는다.
"""
from __future__ import annotations

import csv
import datetime
import io
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from foms.services.orders.order_mutation_policy import normalize_team
from foms.web.auth import TEAMS

# canonical 팀 SSOT(auth 사용자관리·notifications 와 동일). MEASURE 는 여기 없고
# normalize_team 이 SALES 로 매핑하므로 team-clean 이 된다.
CANONICAL_TEAMS: FrozenSet[str] = frozenset(TEAMS.keys())

# task.status 정본 값(app/tasks.py·erp_automation 과 동일 vocabulary).
KNOWN_STATUSES: FrozenSet[str] = frozenset({"OPEN", "IN_PROGRESS", "DONE", "CANCELLED"})
# 활성(미종결) status — auto_key collision·enforcement coverage 는 이 집합만 본다.
ACTIVE_STATUSES: FrozenSet[str] = frozenset({"OPEN", "IN_PROGRESS"})

# ambiguous 사유 코드(분리 분류 — 한 task 가 여러 사유를 동시에 가질 수 있다).
ORPHAN = "ORPHAN"                  # 주문 없음/soft-delete
BAD_STATUS = "BAD_STATUS"          # 알 수 없는 status
BAD_DATE = "BAD_DATE"              # due_date 파싱 불가
BAD_TEAM = "BAD_TEAM"              # canonical 아닌 owner_team
BAD_USER = "BAD_USER"              # dangling owner_user_id
AUTO_COLLISION = "AUTO_COLLISION"  # 활성 (order_id, auto_key) 중복


@dataclass(frozen=True)
class TaskRow:
    """audit 대상 task 의 결정적 스냅샷(read-only 조회 결과).

    Attributes:
        task_id: ``order_tasks.id``.
        order_id: 소속 주문 id.
        status: 원문 status 문자열.
        owner_team: 원문 owner_team(정규화 전).
        owner_user_id: owner_user_id(없으면 None).
        due_date: 원문 due_date 문자열(없으면 None).
        auto_key: ``meta['auto_key']`` (비어있으면 None).
    """

    task_id: int
    order_id: int
    status: Optional[str]
    owner_team: Optional[str]
    owner_user_id: Optional[int]
    due_date: Optional[str]
    auto_key: Optional[str]


@dataclass(frozen=True)
class SafeTask:
    """6축 모두 깨끗한 task(UUID/version/LEGACY provenance seed 대상).

    Attributes:
        task_id: ``order_tasks.id``.
        order_id: 소속 주문 id.
    """

    task_id: int
    order_id: int


@dataclass(frozen=True)
class AmbiguousTask:
    """자동 매핑 불가한 task 1건(수동 CSV 대상·read-only·quarantine).

    Attributes:
        task_id: ``order_tasks.id``.
        order_id: 소속 주문 id.
        status: 발견 시점 status(참고).
        owner_team: 발견 시점 owner_team(참고).
        owner_user_id: 발견 시점 owner_user_id(참고).
        due_date: 발견 시점 due_date(참고).
        auto_key: 발견 시점 auto_key(참고).
        reasons: 감지된 사유 코드들(정렬·중복 제거) — 분리 분류.
    """

    task_id: int
    order_id: int
    status: Optional[str]
    owner_team: Optional[str]
    owner_user_id: Optional[int]
    due_date: Optional[str]
    auto_key: Optional[str]
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class TaskAudit:
    """분류 결과(read-only).

    Attributes:
        safe: SAFE task 목록(task_id 오름차순).
        ambiguous: quarantine 대상 목록(task_id 오름차순).
        active_ids: 활성(OPEN/IN_PROGRESS) task id 집합(enforcement coverage 기준).
    """

    safe: Tuple[SafeTask, ...]
    ambiguous: Tuple[AmbiguousTask, ...]
    active_ids: FrozenSet[int]

    def safe_ids(self) -> FrozenSet[int]:
        """SAFE task id 집합(backfill coverage 판정)."""
        return frozenset(s.task_id for s in self.safe)


def _auto_key(meta: Any) -> Optional[str]:
    """``meta['auto_key']`` 를 비어있지 않은 문자열로 반환(없으면 None)."""
    if not isinstance(meta, dict):
        return None
    raw = meta.get("auto_key")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _valid_iso_date(value: Optional[str]) -> bool:
    """``YYYY-MM-DD`` 로 파싱 가능한지(빈 값은 due_date 없음으로 취급되어 여기 안 옴)."""
    try:
        datetime.date.fromisoformat(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _field_reasons(
    row: TaskRow, *, active_order_ids: Set[int], active_user_ids: Set[int]
) -> List[str]:
    """collision 을 제외한 per-task 필드 이상 사유를 계산한다(read-only).

    Args:
        row: audit 대상 task 스냅샷.
        active_order_ids: soft-delete 되지 않은(활성) 주문 id 집합.
        active_user_ids: 활성(``is_active``) User id 집합.

    Returns:
        감지된 사유 코드 리스트(collision 은 별도 pass 에서 추가).
    """
    reasons: List[str] = []
    if row.order_id not in active_order_ids:
        reasons.append(ORPHAN)
    if (row.status or "") not in KNOWN_STATUSES:
        reasons.append(BAD_STATUS)
    if row.due_date not in (None, "") and not _valid_iso_date(row.due_date):
        reasons.append(BAD_DATE)
    if row.owner_team not in (None, ""):
        # normalize_team: trim·upper·MEASURE→SALES(AUTH-01 SSOT 재사용).
        if normalize_team(row.owner_team) not in CANONICAL_TEAMS:
            reasons.append(BAD_TEAM)
    if row.owner_user_id is not None and row.owner_user_id not in active_user_ids:
        reasons.append(BAD_USER)
    return reasons


def _load_task_rows(session: Session) -> List[TaskRow]:
    """모든 order_tasks 를 스냅샷 리스트로 읽는다(read-only)."""
    from models import OrderTask

    rows: List[TaskRow] = []
    for tid, oid, status, team, uid, due, meta in (
        session.query(
            OrderTask.id, OrderTask.order_id, OrderTask.status,
            OrderTask.owner_team, OrderTask.owner_user_id, OrderTask.due_date,
            OrderTask.meta,
        ).order_by(OrderTask.id).all()
    ):
        rows.append(TaskRow(
            task_id=tid, order_id=oid, status=status, owner_team=team,
            owner_user_id=uid, due_date=due, auto_key=_auto_key(meta),
        ))
    return rows


def _active_order_ids(session: Session, order_ids: Set[int]) -> Set[int]:
    """참조된 주문 중 soft-delete 되지 않은(활성) id 집합(배치 in_ 조회, N+1 금지)."""
    from models import Order

    if not order_ids:
        return set()
    return {
        oid for (oid,) in (
            session.query(Order.id)
            .filter(Order.id.in_(order_ids), Order.not_deleted_filter())
            .all()
        )
    }


def _active_user_ids(session: Session, user_ids: Set[int]) -> Set[int]:
    """참조된 owner_user_id 중 존재하고 활성(``is_active``)인 User id 집합(배치 in_ 조회)."""
    from models import User

    if not user_ids:
        return set()
    return {
        uid for (uid,) in (
            session.query(User.id)
            .filter(User.id.in_(user_ids), User.is_active.is_(True))
            .all()
        )
    }


def _collision_ids(rows: List[TaskRow]) -> Set[int]:
    """활성 (order_id, auto_key) 가 2개 이상인 task id 집합(auto 업서트 불변식 위반).

    auto_key 가 없는 task·종결(DONE/CANCELLED) task 는 collision 대상이 아니다
    (auto 업서트 dedup 은 ``status IN ('OPEN','IN_PROGRESS')`` 활성만 본다).
    """
    groups: Dict[Tuple[int, str], List[int]] = defaultdict(list)
    for row in rows:
        if row.auto_key and (row.status or "") in ACTIVE_STATUSES:
            groups[(row.order_id, row.auto_key)].append(row.task_id)
    collided: Set[int] = set()
    for _key, ids in groups.items():
        if len(ids) > 1:
            collided.update(ids)
    return collided


def audit_order_tasks(session: Session) -> TaskAudit:
    """전체 order_tasks 를 SAFE/ambiguous 로 분류한다(mutation 0).

    Args:
        session: SQLAlchemy Session(read-only 로만 사용).

    Returns:
        :class:`TaskAudit`.
    """
    rows = _load_task_rows(session)
    active_orders = _active_order_ids(session, {r.order_id for r in rows})
    active_users = _active_user_ids(
        session, {r.owner_user_id for r in rows if r.owner_user_id is not None}
    )
    collided = _collision_ids(rows)

    safe: List[SafeTask] = []
    ambiguous: List[AmbiguousTask] = []
    active_ids: Set[int] = set()
    for row in rows:
        if (row.status or "") in ACTIVE_STATUSES:
            active_ids.add(row.task_id)
        reasons = _field_reasons(
            row, active_order_ids=active_orders, active_user_ids=active_users
        )
        if row.task_id in collided:
            reasons.append(AUTO_COLLISION)
        if reasons:
            ambiguous.append(AmbiguousTask(
                task_id=row.task_id, order_id=row.order_id, status=row.status,
                owner_team=row.owner_team, owner_user_id=row.owner_user_id,
                due_date=row.due_date, auto_key=row.auto_key,
                reasons=tuple(sorted(set(reasons))),
            ))
        else:
            safe.append(SafeTask(task_id=row.task_id, order_id=row.order_id))

    safe.sort(key=lambda s: s.task_id)
    ambiguous.sort(key=lambda a: a.task_id)
    return TaskAudit(tuple(safe), tuple(ambiguous), frozenset(active_ids))


def to_manual_csv(audit: TaskAudit) -> str:
    """ambiguous task 를 수동 검토용 CSV 문자열로 내보낸다(header 포함).

    Args:
        audit: :func:`audit_order_tasks` 결과.

    Returns:
        ``task_id,order_id,status,owner_team,owner_user_id,due_date,auto_key,reasons,
        decision,approved_by_user_id`` CSV(ambiguous 행만·자동 매핑 0·decision=MANUAL).
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "task_id", "order_id", "status", "owner_team", "owner_user_id",
        "due_date", "auto_key", "reasons", "decision", "approved_by_user_id",
    ])
    for row in audit.ambiguous:
        writer.writerow([
            row.task_id, row.order_id, row.status or "", row.owner_team or "",
            "" if row.owner_user_id is None else row.owner_user_id,
            row.due_date or "", row.auto_key or "", "|".join(row.reasons),
            "MANUAL",   # decision: 사람이 결정(자동 identity 발급/보정 금지).
            "",         # approved_by_user_id: 승인 전.
        ])
    return buf.getvalue()


__all__ = [
    "CANONICAL_TEAMS",
    "KNOWN_STATUSES",
    "ACTIVE_STATUSES",
    "ORPHAN",
    "BAD_STATUS",
    "BAD_DATE",
    "BAD_TEAM",
    "BAD_USER",
    "AUTO_COLLISION",
    "TaskRow",
    "SafeTask",
    "AmbiguousTask",
    "TaskAudit",
    "audit_order_tasks",
    "to_manual_csv",
]
