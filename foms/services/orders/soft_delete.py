"""Order soft-delete/restore canonical 서비스 (DELETE-CORE-00, SSOT §5.2).

order 삭제/복구의 **정본 엔진**이다. 삭제는 legacy 처럼 ``order.status = 'DELETED'`` 로
main/overlay 축을 덮어쓰지 않고, delete 축의 canonical projection(``deleted_at`` 컬럼)만
set/clear 한다 — main/logistics/hold/AS/construction 축은 그대로 보존된다(§2.2·§2.2.1).
delete metadata(누가·언제·사유)는 ``structured_data['delete']`` JSONB projection + OrderEvent
스트림에 기록한다. 원자성(row lock + ``mutation_version`` bump + idempotency receipt)은
REV-00 :func:`execute_order_mutation` 을 재사용한다.

경계(DELETE-CORE-00):

* **hard delete 금지** — row 는 물리적으로 잔존한다(``deleted_at`` 만 세팅).
* **status string 직접 저장 금지** — ``order.status`` 는 절대 쓰지 않는다(projection 경유).
* **새 컬럼/마이그레이션 없음** — 이미 존재하는 ``deleted_at`` / ``structured_data`` 만 쓴다.
* **route 무이관** — 실제 delete/restore endpoint 이관은 DELETE-BULK-01 / DELETE-TRASH-01 하류.

이미 목표 delete 상태면 no-op(``None`` 반환) — version/event 폭주 없이 멱등하다.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.revision import (
    MutationResult,
    OrderNotFoundError,
    execute_order_mutation,
)
from foms.services.orders.state_axes import read_deleted
from models import Order, OrderEvent

# OrderEvent 이벤트 타입(delete/restore parity).
EVENT_SOFT_DELETED = "ORDER_SOFT_DELETED"
EVENT_RESTORED = "ORDER_RESTORED"

# revision policy id(idempotency unique key 구성요소).
POLICY_SOFT_DELETE = "ORDER_SOFT_DELETE"
POLICY_RESTORE = "ORDER_RESTORE"

# legacy 휴지통 리스트가 ``deleted_at`` 문자열을 desc 정렬하므로 고정폭 형식을 유지한다.
_DELETED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"

# delete/restore 로 무효화되는 cache family(대시보드·리스트·휴지통 + 상세는 order별로 추가).
_CACHE_FAMILIES = ("ORDERS_INDEX", "TRASH_INDEX")


def _digest(*parts: object) -> str:
    """결정적 sha256 hex(REV-00 scope/request hash 계약용)."""
    payload = json.dumps(list(parts), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_delete_projection(
    order: Order,
    *,
    deleted: bool,
    actor_user_id: int,
    reason: Optional[str],
    now: datetime.datetime,
) -> None:
    """delete 축 projection 만 set/clear 한다(``order.status`` 는 건드리지 않음).

    Args:
        order: 잠긴 Order row.
        deleted: True 면 삭제 projection set, False 면 clear(복구).
        actor_user_id: 삭제/복구 actor(metadata 기록용).
        reason: 삭제 사유(복구 시 무시). None 허용.
        now: UTC-naive 기준 시각.
    """
    stamp = now.strftime(_DELETED_AT_FORMAT)
    order.deleted_at = stamp if deleted else None

    sd = copy.deepcopy(order.structured_data) if isinstance(order.structured_data, dict) else {}
    if deleted:
        sd["delete"] = {
            "deleted_by": actor_user_id,
            "deleted_at": stamp,
            "reason": reason,
        }
    else:
        sd.pop("delete", None)
    order.structured_data = sd
    flag_modified(order, "structured_data")


def _transition(
    session: Session,
    *,
    order_id: int,
    actor_user_id: int,
    target_deleted: bool,
    reason: Optional[str],
    expected_version: Optional[int],
    idempotency_key: Optional[str],
    now: Optional[datetime.datetime],
) -> Optional[MutationResult]:
    """delete 축을 target 상태로 원자 전이한다(이미 target 이면 no-op).

    row 를 ``FOR UPDATE`` 로 먼저 잠근 뒤 현재 delete 상태를 읽어, 목표와 같으면 version
    bump/event 없이 ``None`` 을 돌려준다(멱등). 다르면 REV-00 helper 로 projection write +
    OrderEvent 기록 + version bump + receipt 를 원자 수행한다.

    Args:
        session: 호출자 소유 세션(commit 미수행).
        order_id: 대상 order id.
        actor_user_id: actor(receipt 소유자·event 작성자).
        target_deleted: True=soft delete, False=restore.
        reason: 삭제 사유(복구 시 무시).
        expected_version: If-Match ``mutation_version``. None 이면 precondition 없음.
        idempotency_key: 요청 dedupe key(None 이면 dedupe 안 함).
        now: 테스트용 시각 주입(기본 now_utc_naive()).

    Returns:
        MutationResult, 또는 이미 목표 상태면 None(멱등 no-op).

    Raises:
        OrderNotFoundError: order_id 미존재.
        RevisionConflictError: expected_version 불일치(state 불변).
    """
    now = now or now_utc_naive()

    # projection write 와 같은 FOR UPDATE 아래에서 멱등 판정 → 중복 bump/event 차단.
    order = (
        session.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .one_or_none()
    )
    if order is None:
        raise OrderNotFoundError(f"order not found: {order_id}")
    if (read_deleted(order) == "DELETED") == target_deleted:
        return None  # 이미 목표 delete 상태 → 멱등 no-op

    event_type = EVENT_SOFT_DELETED if target_deleted else EVENT_RESTORED

    def _mutation(sess: Session, locked: "list[Order]") -> "dict[int, list[str]]":
        families: "dict[int, list[str]]" = {}
        for target in locked:
            _write_delete_projection(
                target,
                deleted=target_deleted,
                actor_user_id=actor_user_id,
                reason=reason,
                now=now,
            )
            sess.add(
                OrderEvent(
                    order_id=target.id,
                    event_type=event_type,
                    payload={"actor_user_id": actor_user_id, "reason": reason},
                    created_by_user_id=actor_user_id,
                    created_at=now,
                )
            )
            families[target.id] = list(_CACHE_FAMILIES) + [f"ORDER_DETAIL:{target.id}"]
        return families

    return execute_order_mutation(
        session,
        actor_user_id=actor_user_id,
        policy_id=POLICY_SOFT_DELETE if target_deleted else POLICY_RESTORE,
        order_ids=[order_id],
        expected_versions=(
            {order_id: expected_version} if expected_version is not None else None
        ),
        idempotency_key=idempotency_key,
        scope_hash=_digest("scope", order_id),
        request_hash=_digest("request", order_id, target_deleted, reason),
        mutation=_mutation,
        now=now,
    )


def soft_delete_order(
    session: Session,
    *,
    order_id: int,
    actor_user_id: int,
    reason: Optional[str] = None,
    expected_version: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> Optional[MutationResult]:
    """order 를 soft-delete 한다(deleted projection set, 나머지 축 보존).

    ``deleted_at`` 만 세팅하고 ``order.status`` 는 보존하므로 main/overlay 축이 유지된다.
    hard delete 하지 않아 row 는 잔존한다. 호출자가 ``session.commit()`` 을 소유한다.

    Args:
        session: 호출자 소유 세션.
        order_id: 삭제할 order id.
        actor_user_id: 삭제 actor.
        reason: 삭제 사유(선택).
        expected_version: If-Match ``mutation_version``(선택).
        idempotency_key: 요청 dedupe key(선택).
        now: 테스트용 시각 주입(선택).

    Returns:
        MutationResult, 또는 이미 삭제 상태면 None(멱등 no-op).
    """
    return _transition(
        session,
        order_id=order_id,
        actor_user_id=actor_user_id,
        target_deleted=True,
        reason=reason,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        now=now,
    )


def restore_order(
    session: Session,
    *,
    order_id: int,
    actor_user_id: int,
    reason: Optional[str] = None,
    expected_version: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> Optional[MutationResult]:
    """soft-delete 된 order 를 복구한다(deleted projection clear, 나머지 축 보존).

    ``deleted_at`` 을 None 으로 되돌리고 ``structured_data['delete']`` metadata 를 제거한다.
    ``order.status`` 는 건드리지 않는다. 호출자가 ``session.commit()`` 을 소유한다.

    Args:
        session: 호출자 소유 세션.
        order_id: 복구할 order id.
        actor_user_id: 복구 actor.
        reason: 복구 메모(선택, event payload 기록).
        expected_version: If-Match ``mutation_version``(선택).
        idempotency_key: 요청 dedupe key(선택).
        now: 테스트용 시각 주입(선택).

    Returns:
        MutationResult, 또는 이미 non-deleted 상태면 None(멱등 no-op).
    """
    return _transition(
        session,
        order_id=order_id,
        actor_user_id=actor_user_id,
        target_deleted=False,
        reason=reason,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        now=now,
    )


__all__ = [
    "EVENT_SOFT_DELETED",
    "EVENT_RESTORED",
    "POLICY_SOFT_DELETE",
    "POLICY_RESTORE",
    "soft_delete_order",
    "restore_order",
]
