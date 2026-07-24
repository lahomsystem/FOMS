"""Order mutation revision · idempotency · read-after-write 공용 helper (REV-00).

초 단위 ``structured_updated_at`` 이 구분하지 못하는 동시 저장을, Order 별 단조 증가
``mutation_version`` (낙관적 concurrency) + ``FOR UPDATE`` 직렬화 + idempotency receipt
로 대체하기 위한 **기반 라이브러리**다. business mutation 자체는 구현하지 않는다 — 실제
Order row/scalar/JSONB/state 변경은 호출자가 넘기는 ``mutation`` 콜러블이 수행하고, 이
모듈은 오직 If-Match 검증 / row lock / version bump / idempotency replay / receipt·
read-resource 기록 / response 조립만 책임진다.

REV-00 은 이 helper 를 **실제 mutation route 에 적용하지 않는다**(STATE-CORE-00·DATA-01
등 하류 packet 몫). 여기서는 helper + 스키마 + PostgreSQL 계약 테스트만 확보한다.

전형적 하류 사용:

    def _mutate(session, orders):
        for o in orders:
            o.structured_data = ...        # 실제 업무 변경
        return {o.id: ["ORDERS_INDEX", f"ORDER_DETAIL:{o.id}"] for o in orders}

    result = execute_order_mutation(
        session,
        actor_user_id=user.id,
        policy_id="ORDER_STRUCTURED_PATCH",
        order_ids=[order.id],
        expected_versions={order.id: client_if_match},   # None 이면 precondition 없음
        idempotency_key=request_key,                      # None 이면 dedupe 안 함
        scope_hash=scope_sha256,
        request_hash=request_sha256,
        mutation=_mutate,
    )
    session.commit()
    return jsonify(result.body), result.headers   # {mutation_receipt, resources[]} + no-store
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import Order, OrderMutationReadResource, OrderMutationReceipt

# read-after-write window: initiator 가 X-FOMS-Mutation-Receipt 로 자기 write 를 확실히
# 보는 시간. cleanup 은 REV-CLEANUP-01.
READ_RECEIPT_TTL = datetime.timedelta(minutes=2)
# idempotency replay window: 같은 key 재요청은 저장된 response 를 돌려준다. 초과 후 같은
# key 는 IDEMPOTENCY_KEY_EXPIRED. row purge 는 REV-CLEANUP-01.
IDEMPOTENCY_REPLAY_WINDOW = datetime.timedelta(hours=24)
MAX_RESOURCES = 1000  # 단건/batch/copy/import 정규화 상한 (§2.4 line 405)
NO_STORE_HEADERS = {"Cache-Control": "private, no-store"}

# mutation 콜러블: 잠근 Order 목록을 받아 업무 변경을 수행하고, order_id → changed cache
# family 목록을 돌려준다(REV-00 은 family 를 계산하지 않고 보관만 한다). None/누락은 [].
MutationCallable = Callable[[Session, "list[Order]"], "Optional[Mapping[int, Sequence[str]]]"]


class RevisionError(RuntimeError):
    """REV-00 helper 계약 위반의 베이스(호출자는 status_code 로 HTTP 매핑)."""

    status_code = 409
    error_code = "REVISION_ERROR"


class RevisionConflictError(RevisionError):
    """If-Match(mutation_version) 불일치. stale → 409 + 최신 version 반환."""

    status_code = 409
    error_code = "REVISION_CONFLICT"

    def __init__(self, current_versions: Mapping[int, int]):
        super().__init__(f"mutation_version mismatch; current={dict(current_versions)}")
        self.current_versions = dict(current_versions)


class PreconditionRequiredError(RevisionError):
    """require_if_match 인데 해당 order 의 expected_version 누락. 428."""

    status_code = 428
    error_code = "PRECONDITION_REQUIRED"


class IdempotencyKeyExpiredError(RevisionError):
    """같은 idempotency key 가 24시간 replay window 를 넘김. 409."""

    status_code = 409
    error_code = "IDEMPOTENCY_KEY_EXPIRED"


class IdempotencyKeyConflictError(RevisionError):
    """같은 key 를 다른 request_hash 로 재사용(replay 아님). 409."""

    status_code = 409
    error_code = "IDEMPOTENCY_KEY_CONFLICT"


class OrderNotFoundError(RevisionError):
    """요청 order_id 중 존재하지 않는 것이 있음. 404."""

    status_code = 404
    error_code = "ORDER_NOT_FOUND"


@dataclass(frozen=True)
class MutationResult:
    """execute_order_mutation 반환값. 하류 route 가 HTTP 응답으로 변환한다.

    Attributes:
        body: ``{"mutation_receipt": <read_receipt_id>, "resources": [...]}``.
        headers: ``Cache-Control: private, no-store``.
        read_receipt_id: opaque 128-bit read-after-write 토큰.
        replayed: idempotency replay(저장된 응답 재사용, business write 미수행)면 True.
    """

    body: dict
    headers: dict
    read_receipt_id: str
    replayed: bool


def _lookup_receipt(
    session: Session, actor_user_id: int, policy_id: str, idempotency_key: str
) -> Optional[OrderMutationReceipt]:
    """(actor, policy, key) 로 기존 receipt 를 조회(없으면 None)."""
    return (
        session.query(OrderMutationReceipt)
        .filter(
            OrderMutationReceipt.actor_user_id == actor_user_id,
            OrderMutationReceipt.policy_id == policy_id,
            OrderMutationReceipt.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def _replay(receipt: OrderMutationReceipt) -> MutationResult:
    """저장된 receipt 를 replay 결과로 감싼다."""
    return MutationResult(
        body=receipt.response_body,
        headers=dict(NO_STORE_HEADERS),
        read_receipt_id=str(receipt.read_receipt_id),
        replayed=True,
    )


def execute_order_mutation(
    session: Session,
    *,
    actor_user_id: int,
    policy_id: str,
    order_ids: Sequence[int],
    scope_hash: str,
    request_hash: str,
    mutation: MutationCallable,
    expected_versions: Optional[Mapping[int, int]] = None,
    idempotency_key: Optional[str] = None,
    require_if_match: bool = False,
    response_status: int = 200,
    now: Optional[datetime.datetime] = None,
) -> MutationResult:
    """Order mutation 을 If-Match·row lock·version bump·idempotency·receipt 로 감싼다.

    호출자가 ``session.commit()`` 을 소유한다(이 함수는 replay 롤백 외에는 commit 하지
    않는다). ``mutation`` 콜러블 안에서 실제 업무 변경을 하고 order_id → changed cache
    family 목록을 반환한다.

    Args:
        session: business transaction 세션(호출자 소유, 커밋 미수행).
        actor_user_id: 요청 actor(receipt 소유자·idempotency scope).
        policy_id: mutation 정책 식별자(idempotency unique key 구성요소).
        order_ids: 잠글 Order id. ID 순으로 ``FOR UPDATE`` (§2.4 bulk 규칙). 최대 1000.
        scope_hash: 요청 scope 의 sha256 hex(receipt 저장).
        request_hash: 요청 payload 의 sha256 hex(같은 key/다른 hash 감지).
        mutation: ``(session, locked_orders) -> {order_id: [family, ...]}`` 콜러블.
        expected_versions: order_id → If-Match mutation_version. None 이면 precondition
            없음(신규 draft 흐름). 불일치 시 RevisionConflictError.
        idempotency_key: UUID 문자열(≤64자) 또는 None. 같은 key replay 는 저장된 응답을
            돌려주고 business write 0. None 이면 dedupe 하지 않는다.
        require_if_match: True 면 expected_versions 누락 order 에 PreconditionRequiredError
            (REV-99 전역 428 이관용). 기본 False.
        response_status: receipt 에 저장할 응답 status(기본 200).
        now: 테스트용 시각 주입(기본 now_utc_naive()).

    Returns:
        MutationResult(body/headers/read_receipt_id/replayed).

    Raises:
        RevisionConflictError: If-Match 불일치(현재 version 동봉).
        PreconditionRequiredError: require_if_match 인데 expected_version 누락.
        IdempotencyKeyExpiredError: 같은 key 가 24시간 window 초과.
        IdempotencyKeyConflictError: 같은 key 를 다른 request_hash 로 재사용.
        OrderNotFoundError: 존재하지 않는 order_id 포함.
        ValueError: order_ids 가 비었거나 1000 초과.
    """
    unique_ids = sorted(set(order_ids))
    if not unique_ids:
        raise ValueError("order_ids must not be empty.")
    if len(unique_ids) > MAX_RESOURCES:
        raise ValueError(f"order_ids exceeds MAX_RESOURCES ({MAX_RESOURCES}).")
    now = now or now_utc_naive()

    # 1) ID 순 FOR UPDATE — 같은 order 에 대한 동시 mutation 을 직렬화(lost update 차단)
    #    하고, 같은 key 동시 요청의 idempotency 조회를 커밋 순서대로 만든다.
    locked = (
        session.query(Order)
        .filter(Order.id.in_(unique_ids))
        .order_by(Order.id.asc())
        .with_for_update()
        .all()
    )
    if len(locked) != len(unique_ids):
        found = {o.id for o in locked}
        raise OrderNotFoundError(f"orders not found: {sorted(set(unique_ids) - found)}")

    # 2) lock 획득 뒤 idempotency 조회 — 앞선 동일-key 트랜잭션이 커밋했다면 여기서 보고
    #    replay 한다(같은 order 동시 same-key 는 이 경로로 수렴).
    if idempotency_key is not None:
        existing = _lookup_receipt(session, actor_user_id, policy_id, idempotency_key)
        if existing is not None:
            if now > existing.expires_at:
                raise IdempotencyKeyExpiredError(
                    f"idempotency key expired at {existing.expires_at.isoformat()}"
                )
            if existing.request_hash != request_hash:
                raise IdempotencyKeyConflictError(
                    "idempotency key reused with a different request hash."
                )
            return _replay(existing)

    # 3) If-Match(mutation_version) 검증.
    expected = dict(expected_versions or {})
    conflicts = False
    for order in locked:
        if order.id in expected:
            if order.mutation_version != expected[order.id]:
                conflicts = True
        elif require_if_match:
            raise PreconditionRequiredError(
                f"If-Match required for order {order.id} (mutation_version)."
            )
    if conflicts:
        raise RevisionConflictError({o.id: o.mutation_version for o in locked})

    # 4) 업무 변경 → family 수집 → version bump.
    families_raw = mutation(session, locked) or {}
    families = {oid: list(fams) for oid, fams in families_raw.items()}
    for order in locked:
        order.mutation_version = (order.mutation_version or 0) + 1

    resulting_versions = {o.id: o.mutation_version for o in locked}
    resources = [
        {
            "order_id": o.id,
            "resulting_version": o.mutation_version,
            "changed_cache_families": families.get(o.id, []),
        }
        for o in locked
    ]

    read_receipt_id = str(uuid.uuid4())
    body = {"mutation_receipt": read_receipt_id, "resources": resources}

    receipt = OrderMutationReceipt(
        read_receipt_id=read_receipt_id,
        actor_user_id=actor_user_id,
        policy_id=policy_id,
        idempotency_key=idempotency_key,
        scope_hash=scope_hash,
        request_hash=request_hash,
        response_status=response_status,
        response_body=body,
        resulting_versions={str(k): v for k, v in resulting_versions.items()},
        read_expires_at=now + READ_RECEIPT_TTL,
        expires_at=now + IDEMPOTENCY_REPLAY_WINDOW,
    )
    # 5) parent receipt insert. idempotency backstop: 서로 다른 order 를 같은 key 로
    #    동시 요청하면 FOR UPDATE 가 직렬화하지 못하므로(다른 row), unique
    #    (actor,policy,key) 제약이 두 번째 insert 를 여기서 막는다. 그 경우 이긴 쪽의
    #    저장 응답으로 replay 한다.
    #    ponytail: 같은-order 동시 same-key 는 위 lock+lookup 이 이미 처리하므로 이 경로는
    #    드문 cross-order 경합 backstop 이다.
    #    parent 를 먼저 flush 해야 child FK(read_receipt_id, 비-PK unique 참조)가 만족된다
    #    (두 매퍼 사이 relationship 이 없어 unit-of-work 가 순서를 보장하지 않음).
    session.add(receipt)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        if idempotency_key is None:
            raise
        winner = _lookup_receipt(session, actor_user_id, policy_id, idempotency_key)
        if winner is None:
            raise
        return _replay(winner)

    for res in resources:
        session.add(
            OrderMutationReadResource(
                read_receipt_id=read_receipt_id,
                order_id=res["order_id"],
                resulting_version=res["resulting_version"],
                changed_cache_families_json=res["changed_cache_families"],
            )
        )
    session.flush()

    return MutationResult(
        body=body,
        headers=dict(NO_STORE_HEADERS),
        read_receipt_id=read_receipt_id,
        replayed=False,
    )
