"""주문 배정(order_assignments) command service (ASSIGNMENT-00, §2.1 line 172-179).

배정 authorization 정본을 JSONB 이름 배열이 아닌 ``order_assignments`` user-ID row 로
옮기기 위한 **mechanics + ID-only auth 판정 primitive** 를 제공한다. 모든 command 는
REV-00 :func:`~foms.services.orders.revision.execute_order_mutation` 를 재사용해
If-Match(mutation_version) + row lock + version bump + idempotency + receipt 를 얻는다.

경계(ASSIGNMENT-00):

* 이 service 는 배정 **mechanics**(claim/replace/release + event + version)와 배정 row
  기반 **structural validation**(count 1..20, claim 시 active 0, release 시 row 존재,
  batch all-or-none)만 수행한다.
* actor 의 role/team **AUTH enforcement 는 하지 않는다**(AUTH-01 몫). :func:`active_assignee_ids`
  · :func:`can_release_assignment` 는 AUTH-01 이 route guard 에서 호출할 **순수 판정
  함수**(ID-row 기반, JSONB 이름 미사용)이며, 여기서 route 에 배선하지 않는다.
* JSONB 표시 projection 은 갱신하지 않는다(server-owned projection 배선은 AUTH-01).

전형적 하류(AUTH-01) 사용:

    if not can_release_assignment(row, actor_user_id=u.id, actor_role=u.role,
                                  actor_team=u.team):
        abort(403)
    result = release_assignment(session, actor_user_id=u.id, order_id=o.id,
                                domain="DRAWING", user_id=t, reason=r,
                                expected_version=if_match, scope_hash=..., request_hash=...)
    session.commit()
"""
from __future__ import annotations

import datetime
from typing import Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.order_mutation_policy import team_has_capability
from foms.services.orders.revision import MutationResult, execute_order_mutation
from models import OrderAssignment, OrderEvent, User

# domain / source enum 은 models SSOT 를 재노출.
from models import ORDER_ASSIGNMENT_DOMAINS, ORDER_ASSIGNMENT_SOURCES  # noqa: F401

MAX_ASSIGNEES = 20
MIN_ASSIGNEES = 1
REASON_MAX = 500


# --------------------------------------------------------------------------- #
# errors (호출자가 status_code 로 HTTP 매핑; REV-00 error 계열과 함께 처리)
# --------------------------------------------------------------------------- #
class AssignmentError(RuntimeError):
    """ASSIGNMENT-00 계약 위반 베이스."""

    status_code = 409
    error_code = "ASSIGNMENT_ERROR"


class AssignmentValidationError(AssignmentError):
    """입력 검증 실패(count/reason/중복/비활성 target). 422."""

    status_code = 422
    error_code = "ASSIGNMENT_VALIDATION"


class ClaimConflictError(AssignmentError):
    """이미 active drawing 배정이 있는 주문을 새 key 로 재claim. 409."""

    status_code = 409
    error_code = "CLAIM_CONFLICT"

    def __init__(self, order_id: int):
        super().__init__(f"order {order_id} already has an active DRAWING assignment.")
        self.order_id = order_id


class AssignmentNotActiveError(AssignmentError):
    """release 대상 active 배정 row 가 없음(또는 이미 inactive). 409."""

    status_code = 409
    error_code = "ASSIGNMENT_NOT_ACTIVE"

    def __init__(self, order_id: int, domain: str, user_id: int):
        super().__init__(
            f"no active {domain} assignment for order {order_id}, user {user_id}."
        )
        self.order_id, self.domain, self.user_id = order_id, domain, user_id


# --------------------------------------------------------------------------- #
# 내부 helper
# --------------------------------------------------------------------------- #
def _validate_domain(domain: str) -> str:
    """domain 이 SALES|DRAWING|CONSTRUCTION 인지 검증."""
    if domain not in ORDER_ASSIGNMENT_DOMAINS:
        raise AssignmentValidationError(f"unknown domain {domain!r}.")
    return domain


def _clean_reason(reason: Optional[str], *, required: bool) -> Optional[str]:
    """reason 을 trim; required 면 1..500 강제, 아니면 있을 때만 상한 검증."""
    if reason is None or not reason.strip():
        if required:
            raise AssignmentValidationError("reason is required (1..500 chars).")
        return None
    trimmed = reason.strip()
    if len(trimmed) > REASON_MAX:
        raise AssignmentValidationError(f"reason exceeds {REASON_MAX} chars.")
    return trimmed


def _active_query(session: Session, order_id: int, domain: str):
    """(order, domain) 의 active 배정 row 쿼리."""
    return session.query(OrderAssignment).filter(
        OrderAssignment.order_id == order_id,
        OrderAssignment.domain == domain,
        OrderAssignment.active.is_(True),
    )


def resolve_assignee_ids(
    session: Session, user_ids: Iterable[int], *, min_n: int = MIN_ASSIGNEES,
    max_n: int = MAX_ASSIGNEES,
) -> List[int]:
    """ID picker resolve: 중복 없는 active user 1..N 임을 검증하고 정규화한다.

    Args:
        session: DB 세션.
        user_ids: 지정 대상 user_id 목록.
        min_n: 허용 최소 인원(기본 1).
        max_n: 허용 최대 인원(기본 20).

    Returns:
        정규화된 user_id 목록(입력 순서 보존).

    Raises:
        AssignmentValidationError: 개수 범위 밖·중복·존재하지 않거나 inactive 한 target.
    """
    try:
        ids = [int(u) for u in user_ids]
    except (TypeError, ValueError) as exc:
        raise AssignmentValidationError("assignee ids must be integers.") from exc
    if len(set(ids)) != len(ids):
        raise AssignmentValidationError("duplicate assignee ids.")
    if not (min_n <= len(ids) <= max_n):
        raise AssignmentValidationError(
            f"assignee count {len(ids)} out of range [{min_n}, {max_n}]."
        )
    active = {
        u.id
        for u in session.query(User).filter(User.id.in_(ids)).all()
        if u.is_active
    }
    missing = [i for i in ids if i not in active]
    if missing:
        raise AssignmentValidationError(f"unknown or inactive assignee ids: {missing}.")
    return ids


def _emit_event(
    session: Session, order_id: int, event_type: str, actor_user_id: int, payload: dict,
    now: datetime.datetime,
) -> None:
    """배정 command 당 OrderEvent 한 행 append."""
    session.add(
        OrderEvent(
            order_id=order_id,
            event_type=event_type,
            payload=payload,
            created_by_user_id=actor_user_id,
            created_at=now,
        )
    )


def _replace_active(
    session: Session, order_id: int, domain: str, target_ids: Sequence[int], *,
    actor_user_id: int, add_source: str, reason: Optional[str], now: datetime.datetime,
) -> None:
    """domain active 배정을 target_ids 로 replace: 빠진 row release + 추가 row assign.

    이미 배정된 user 는 그대로 두어 source/assigned_at 이력을 보존한다. release 는 hard
    delete 하지 않고 active=false + released_* 로 이력을 남긴다(한 tx).
    """
    current = {row.user_id: row for row in _active_query(session, order_id, domain).all()}
    target = set(target_ids)
    for uid, row in current.items():
        if uid not in target:
            row.active = False
            row.released_at = now
            row.released_by_user_id = actor_user_id
            row.release_reason = reason or "REPLACED"
    for uid in target_ids:
        if uid not in current:
            session.add(
                OrderAssignment(
                    order_id=order_id, domain=domain, user_id=uid, source=add_source,
                    active=True, assigned_at=now, assigned_by_user_id=actor_user_id,
                )
            )


def _families(order_id: int) -> dict:
    """REV-00 mutation 콜러블이 돌려줄 changed cache family."""
    return {order_id: ["ORDERS_INDEX", f"ORDER_DETAIL:{order_id}"]}


# --------------------------------------------------------------------------- #
# commands (전부 execute_order_mutation 재사용)
# --------------------------------------------------------------------------- #
def claim_drawing(
    session: Session, *, actor_user_id: int, order_id: int, scope_hash: str,
    request_hash: str, idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> MutationResult:
    """DRAWING active 배정 0건 주문을 actor 자기 ID 로 claim (event DRAWING_ASSIGNED).

    같은 idempotency key replay 는 저장된 응답을 돌려주고 재claim 하지 않는다. active
    배정이 이미 있으면(새 key) :class:`ClaimConflictError` 409. order row FOR UPDATE 가
    동시 claim 을 직렬화한다.
    """
    ts = now or now_utc_naive()

    def _mut(sess: Session, orders):
        order = orders[0]
        if _active_query(sess, order.id, "DRAWING").count() != 0:
            raise ClaimConflictError(order.id)
        sess.add(
            OrderAssignment(
                order_id=order.id, domain="DRAWING", user_id=actor_user_id,
                source="SELF_CLAIM", active=True, assigned_at=ts,
                assigned_by_user_id=actor_user_id,
            )
        )
        _emit_event(sess, order.id, "DRAWING_ASSIGNED", actor_user_id,
                    {"user_id": actor_user_id, "source": "SELF_CLAIM"}, ts)
        return _families(order.id)

    return execute_order_mutation(
        session, actor_user_id=actor_user_id, policy_id="CLAIM_DRAWING",
        order_ids=[order_id], scope_hash=scope_hash, request_hash=request_hash,
        idempotency_key=idempotency_key, mutation=_mut, now=ts,
    )


def set_sales_assignee(
    session: Session, *, actor_user_id: int, order_id: int, user_id: int,
    reason: Optional[str] = None, scope_hash: str, request_hash: str,
    expected_version: Optional[int] = None, idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> MutationResult:
    """SALES owner 1명 지정/교체 (event SALES_ASSIGNEE_SET).

    기존 owner 와 다른 사람으로 교체할 때는 reason 1..500 이 필수다(생성 시 불필요).
    SALES partial unique 가 주문당 active owner 1명을 DB 레벨에서 강제한다.
    """
    ts = now or now_utc_naive()
    resolve_assignee_ids(session, [user_id], min_n=1, max_n=1)

    def _mut(sess: Session, orders):
        order = orders[0]
        current = {r.user_id for r in _active_query(sess, order.id, "SALES").all()}
        replacing = bool(current) and current != {user_id}
        clean = _clean_reason(reason, required=replacing)
        _replace_active(
            sess, order.id, "SALES", [user_id], actor_user_id=actor_user_id,
            add_source="TEAM_REPLACE" if current else "INITIAL_OWNER",
            reason=clean, now=ts,
        )
        _emit_event(sess, order.id, "SALES_ASSIGNEE_SET", actor_user_id,
                    {"user_id": user_id, "reason": clean}, ts)
        return _families(order.id)

    return execute_order_mutation(
        session, actor_user_id=actor_user_id, policy_id="SET_SALES_ASSIGNEE",
        order_ids=[order_id],
        expected_versions=None if expected_version is None else {order_id: expected_version},
        scope_hash=scope_hash, request_hash=request_hash,
        idempotency_key=idempotency_key, mutation=_mut, now=ts,
    )


def replace_sales_owner_in_tx(
    session: Session, *, order_id: int, user_id: int, actor_user_id: int,
    reason: Optional[str], source: str = "TEAM_REPLACE",
    now: Optional[datetime.datetime] = None,
) -> None:
    """**이미 열린 트랜잭션 안에서** SALES owner 를 교체한다(event 포함, version bump 없음).

    :func:`set_sales_assignee` 와 같은 원장(active row replace + ``SALES_ASSIGNEE_SET``)을
    남기지만 REV-00 :func:`execute_order_mutation` 을 부르지 않는다 — 이미 mutation 안
    (FOR UPDATE 락·version bump 완료)에서 부수효과로 호출하는 자리 전용이다. 거기서
    execute_order_mutation 을 다시 부르면 같은 주문 락을 중첩으로 잡고 version 이 한 저장에
    두 번 올라간다(클라이언트 If-Match 가 즉시 stale).

    호출자 책임: 주문 행이 이 세션에서 이미 잠겨 있을 것, 커밋할 것, 대상 user 가 활성일 것.
    사람이 직접 지정하는 경로는 이 함수가 아니라 :func:`set_sales_assignee` 를 쓴다.

    Args:
        session: 열린 세션(커밋은 호출자).
        order_id: 대상 주문 id.
        user_id: 새 SALES owner user id.
        actor_user_id: 행위자 user id(감사 원장 author).
        reason: 교체 사유(1..500). 원장에 남는다.
        source: ``OrderAssignment.source`` 값.
        now: 시각 주입(테스트).
    """
    ts = now or now_utc_naive()
    clean = _clean_reason(reason, required=False)
    _replace_active(session, order_id, "SALES", [user_id], actor_user_id=actor_user_id,
                    add_source=source, reason=clean, now=ts)
    _emit_event(session, order_id, "SALES_ASSIGNEE_SET", actor_user_id,
                {"user_id": user_id, "reason": clean}, ts)


def _set_assignees(
    session: Session, *, domain: str, event_type: str, policy_id: str,
    actor_user_id: int, order_id: int, user_ids: Sequence[int], reason: Optional[str],
    scope_hash: str, request_hash: str, expected_version: Optional[int],
    idempotency_key: Optional[str], now: Optional[datetime.datetime],
) -> MutationResult:
    """DRAWING/CONSTRUCTION 1..20 replace 공용 구현."""
    ts = now or now_utc_naive()
    target_ids = resolve_assignee_ids(session, user_ids)
    clean = _clean_reason(reason, required=False)

    def _mut(sess: Session, orders):
        order = orders[0]
        _replace_active(sess, order.id, domain, target_ids, actor_user_id=actor_user_id,
                        add_source="TEAM_REPLACE", reason=clean, now=ts)
        _emit_event(sess, order.id, event_type, actor_user_id,
                    {"user_ids": target_ids, "reason": clean}, ts)
        return _families(order.id)

    return execute_order_mutation(
        session, actor_user_id=actor_user_id, policy_id=policy_id, order_ids=[order_id],
        expected_versions=None if expected_version is None else {order_id: expected_version},
        scope_hash=scope_hash, request_hash=request_hash,
        idempotency_key=idempotency_key, mutation=_mut, now=ts,
    )


def set_drawing_assignees(
    session: Session, *, actor_user_id: int, order_id: int, user_ids: Sequence[int],
    reason: Optional[str] = None, scope_hash: str, request_hash: str,
    expected_version: Optional[int] = None, idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> MutationResult:
    """DRAWING 배정을 active user 1..20 로 replace (event DRAWING_ASSIGNMENTS_REPLACED).

    빠진 row release + 추가 row assign 을 한 tx 로 처리한다.
    """
    return _set_assignees(
        session, domain="DRAWING", event_type="DRAWING_ASSIGNMENTS_REPLACED",
        policy_id="SET_DRAWING_ASSIGNEES", actor_user_id=actor_user_id,
        order_id=order_id, user_ids=user_ids, reason=reason, scope_hash=scope_hash,
        request_hash=request_hash, expected_version=expected_version,
        idempotency_key=idempotency_key, now=now,
    )


def set_construction_assignees(
    session: Session, *, actor_user_id: int, order_id: int, user_ids: Sequence[int],
    reason: Optional[str] = None, scope_hash: str, request_hash: str,
    expected_version: Optional[int] = None, idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> MutationResult:
    """CONSTRUCTION 배정을 active user 1..20 로 replace (event
    CONSTRUCTION_ASSIGNMENTS_REPLACED). 이 ID 만 authorization 에 사용한다."""
    return _set_assignees(
        session, domain="CONSTRUCTION", event_type="CONSTRUCTION_ASSIGNMENTS_REPLACED",
        policy_id="SET_CONSTRUCTION_ASSIGNEES", actor_user_id=actor_user_id,
        order_id=order_id, user_ids=user_ids, reason=reason, scope_hash=scope_hash,
        request_hash=request_hash, expected_version=expected_version,
        idempotency_key=idempotency_key, now=now,
    )


def batch_set_drawing_assignees(
    session: Session, *, actor_user_id: int, orders: Sequence[dict],
    user_ids: Sequence[int], reason: Optional[str] = None, scope_hash: str,
    request_hash: str, idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> MutationResult:
    """여러 주문의 DRAWING 배정을 한 번에 replace — **all-or-none**.

    ``orders`` = ``[{order_id, mutation_version}, ...]``. Order ID 정렬 lock(REV-00)
    으로 deadlock 0. 누락·stale·invalid 가 한 건이면 전체 abort(각각 OrderNotFound 404 /
    RevisionConflict 409 / Precondition 428 / Validation 422)이고 assignment·version·event
    변화 0이다. 콜러블은 try/except 없이 순차 처리 → row 별 예외를 삼키지 않는다.
    """
    ts = now or now_utc_naive()
    target_ids = resolve_assignee_ids(session, user_ids)
    clean = _clean_reason(reason, required=False)
    order_ids = [int(o["order_id"]) for o in orders]
    if len(set(order_ids)) != len(order_ids):
        raise AssignmentValidationError("duplicate order_id in batch.")
    # mutation_version 누락 order 는 expected 에서 빠지고, require_if_match=True 라 REV-00
    # 이 PreconditionRequiredError(428) 로 전체 abort 한다(row별 부분 처리 없음).
    expected = {
        int(o["order_id"]): int(o["mutation_version"])
        for o in orders
        if o.get("mutation_version") is not None
    }

    def _mut(sess: Session, locked):
        fams = {}
        for order in locked:  # locked 은 REV-00 이 ID 순으로 정렬·lock 함
            _replace_active(sess, order.id, "DRAWING", target_ids,
                            actor_user_id=actor_user_id, add_source="TEAM_REPLACE",
                            reason=clean, now=ts)
            _emit_event(sess, order.id, "DRAWING_ASSIGNMENTS_REPLACED", actor_user_id,
                        {"user_ids": target_ids, "reason": clean}, ts)
            fams.update(_families(order.id))
        return fams

    return execute_order_mutation(
        session, actor_user_id=actor_user_id, policy_id="BATCH_SET_DRAWING_ASSIGNEES",
        order_ids=order_ids, expected_versions=expected, require_if_match=True,
        scope_hash=scope_hash, request_hash=request_hash,
        idempotency_key=idempotency_key, mutation=_mut, now=ts,
    )


def release_assignment(
    session: Session, *, actor_user_id: int, order_id: int, domain: str, user_id: int,
    reason: str, scope_hash: str, request_hash: str,
    expected_version: Optional[int] = None, idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> MutationResult:
    """(order,domain,user) 의 active 배정 한 건을 release (event ASSIGNMENT_RELEASED).

    hard delete 하지 않고 active=false + released_* 로 이력을 보존한다. target User 가
    inactive 여도 active 배정 row 는 release 가능하다(user 활성 여부가 아니라 배정 row 를
    본다). active 배정이 없으면(또는 이미 inactive) :class:`AssignmentNotActiveError` 409.
    reason 1..500 필수. actor 자격(SELF_CLAIM/TEAM_REPLACE/role) enforcement 는 AUTH-01
    이 :func:`can_release_assignment` 로 수행한다(여기선 mechanics 만).
    """
    ts = now or now_utc_naive()
    _validate_domain(domain)
    clean = _clean_reason(reason, required=True)

    def _mut(sess: Session, orders):
        order = orders[0]
        row = (
            _active_query(sess, order.id, domain)
            .filter(OrderAssignment.user_id == user_id)
            .one_or_none()
        )
        if row is None:
            raise AssignmentNotActiveError(order.id, domain, user_id)
        row.active = False
        row.released_at = ts
        row.released_by_user_id = actor_user_id
        row.release_reason = clean
        _emit_event(sess, order.id, "ASSIGNMENT_RELEASED", actor_user_id,
                    {"domain": domain, "user_id": user_id, "reason": clean}, ts)
        return _families(order.id)

    return execute_order_mutation(
        session, actor_user_id=actor_user_id, policy_id="RELEASE_ASSIGNMENT",
        order_ids=[order_id],
        expected_versions=None if expected_version is None else {order_id: expected_version},
        scope_hash=scope_hash, request_hash=request_hash,
        idempotency_key=idempotency_key, mutation=_mut, now=ts,
    )


# --------------------------------------------------------------------------- #
# ID-only auth primitive (AUTH-01 이 enforce; 여기선 판정만·route 미배선)
# --------------------------------------------------------------------------- #
def active_assignee_ids(session: Session, order_id: int, domain: str) -> List[int]:
    """authorization SSOT: 주문·domain 의 현재 active 배정 user_id(정렬).

    JSONB 이름 배열 대신 이 함수만 권한 판정에 쓴다(get_assignee_ids 의 ID-row 대체).
    """
    _validate_domain(domain)
    rows = _active_query(session, order_id, domain).with_entities(OrderAssignment.user_id)
    return sorted(uid for (uid,) in rows)


def is_assignee(session: Session, order_id: int, domain: str, user_id: int) -> bool:
    """user 가 주문·domain 의 현재 active 배정 대상인가(ID-row 기반)."""
    return user_id in active_assignee_ids(session, order_id, domain)


def can_release_assignment(
    assignment: OrderAssignment, *, actor_user_id: int, actor_role: str,
    actor_team: Optional[str],
) -> bool:
    """release 자격 판정(순수·ID-row 기반, JSONB 이름 미사용; AUTH-01 이 enforce).

    §2.1 line 179 matrix:

    * ADMIN/MANAGER: 모든 domain release 가능(reason 은 별도 정책).
    * ``source=SELF_CLAIM``: 그 claim 의 owner(actor==user_id)만 release.
    * ``source=TEAM_REPLACE|INITIAL_OWNER|BACKFILL``: STAFF 는 domain team 기준 —
      DRAWING 은 DRAWING team, CONSTRUCTION 은 CS/SALES/CONSTRUCTION team, SALES 는
      CS/SALES team.

    이 함수는 판정만 하며 어떤 route 에도 배선되지 않는다(enforcement=AUTH-01).
    """
    if actor_role in ("ADMIN", "MANAGER"):
        return True
    if actor_role != "STAFF":
        return False
    if assignment.source == "SELF_CLAIM":
        return assignment.user_id == actor_user_id
    team = (actor_team or "").strip()
    if assignment.domain == "DRAWING":
        return team == "DRAWING"
    if assignment.domain == "CONSTRUCTION":
        return team_has_capability(team, ("CS", "SALES", "CONSTRUCTION"))
    if assignment.domain == "SALES":
        return team_has_capability(team, ("CS", "SALES"))
    return False


__all__ = [
    "MAX_ASSIGNEES", "MIN_ASSIGNEES", "REASON_MAX",
    "AssignmentError", "AssignmentValidationError", "ClaimConflictError",
    "AssignmentNotActiveError",
    "resolve_assignee_ids",
    "claim_drawing", "set_sales_assignee", "replace_sales_owner_in_tx",
    "set_drawing_assignees",
    "set_construction_assignees", "batch_set_drawing_assignees", "release_assignment",
    "active_assignee_ids", "is_assignee", "can_release_assignment",
]
