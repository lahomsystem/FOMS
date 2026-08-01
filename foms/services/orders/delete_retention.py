"""Soft-delete retention hard-purge under OPS-APPROVAL (DELETE-RETENTION-01, SSOT §5.2).

soft-delete(``deleted_at``)된 뒤 retention 기간이 지난 주문을, **OPS-APPROVAL 승인
(seq≥1 admin 재인증·one-time·control-root)** 하에서만 물리 삭제(hard purge)한다.
DELETE-CORE-00 이 delete 축 projection(``deleted_at``)만 세팅해 row 를 잔존시킨 것과
달리, 이 모듈은 그 잔존 row 를 **영구 제거**한다 — 그래서 파괴적이고, 삭제 전 다음
안전 검증을 **모두 통과**해야만 실행된다:

* **exact order-ID**: 대상은 계획 시점에 확정된 정확한 id 집합뿐(광역 ``WHERE ts<cutoff``
  삭제 아님, id 멤버십 삭제).
* **각 첨부 file hash**: 첨부의 storage 참조/메타데이터 해시(계획↔실행 사이 첨부 집합
  변동을 감지).
* **before snapshot(export 백업)**: 삭제 전 주문 row + 첨부 전체를 canonical 직렬화해
  계획 artifact 에 담는다(삭제 후 감사·복구 근거).
* **dependency artifact(참조 무결성)**: ``orders.id`` 를 참조하는 모든 FK 테이블의 대상
  참조 수. DB CASCADE/SET NULL 로 자동 정리 안 되는 참조는 nullable 이면 NULL 로 링크만
  끊고, NOT NULL ephemeral child 는 명시 allowlist 로만 삭제하며, 그 밖의 NOT NULL 참조자는
  :func:`_assert_fk_coverage` 로 fail-closed(임의 삭제 금지).
* **expected count hash**: 대상 수·id 집합을 사전 해시(``count_sha256``)하고, plan 전체를
  ``plan_sha256`` 로 커밋한다. 실행 시 live 상태로 재계산한 값이 승인된 값과 다르면
  **삭제 0 으로 중단**(count/set/snapshot drift).

OPS-APPROVAL 게이트는 ``foms.services.security.ops_approval.consume_same_db`` 를 재사용한다
(same-DB one-time consume, ``artifact_sha256=plan_sha256`` 바인딩). dry-run(기본)은 승인을
**소비하지 않고** 삭제 0 이다. ``apply`` 만이 승인 토큰을 소비하고, 검증을 전부 통과한
뒤에야 hard delete 를 실행한다 — consume+delete 는 호출자가 commit 하는 **한 tx** 라
실패 시 rollback 되어 토큰은 APPROVED 로 남고(재실행이 resume) 삭제 0 이다.

경계(DELETE-RETENTION-01): soft-delete 아닌 주문 삭제 금지(DELETE 술어 ``deleted_at IS
NOT NULL`` 재확인), 승인 없이 하드삭제 금지, 검증 미통과 삭제 금지, 새 스키마/마이그레이션
없음(기존 ``deleted_at``·FK cascade 재사용), ``models``·``order_mutation_policy`` 무변경.
"""
from __future__ import annotations

import datetime
import decimal
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from db import Base
from foms.services.datetime_kst import now_utc_naive
from foms.services.security.ops_approval import consume_same_db

OPERATION_ID = "DELETE_RETENTION_APPLY"
PACKET_ID = "DELETE-RETENTION-01"
DEFAULT_PHASE = "apply"

# DELETE-CORE 가 ``deleted_at`` 를 쓰는 고정폭 포맷(휴지통 desc 정렬 계약과 동일).
_DELETED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"

# 주문 물리 삭제는 되돌릴 수 없다 — 기본 retention 을 보수적으로 1년으로 둔다(운영자가
# 명시 override). ponytail: 안전 상한값. 더 짧게가 필요하면 인자로 낮춘다.
DEFAULT_RETENTION_DAYS = 365
DEFAULT_BATCH_SIZE = 500

# 전역 직렬화 락 — 동시 apply 를 한 번에 하나로 묶는다. xact 락이라 tx 종료 시 자동 해제.
# ponytail: global lock, retention purge 는 저빈도라 per-batch 락 불필요.
_ADVISORY_LOCK_KEY = "foms:delete_retention_apply"

# ``orders.id`` 를 참조하며 DB CASCADE/SET NULL 로 정리 안 되는 **NOT NULL** 참조 중, 주문과
# 함께 삭제해도 안전한 ephemeral child 만 여기 명시한다(이들은 하드 삭제 시 함께 지운다).
# nullable 참조자는 자동 NULL 처리되므로 allowlist 가 필요 없다. NOT NULL 참조자가 여기에
# 없으면 :func:`_assert_fk_coverage` 가 fail-closed 한다 — 알 수 없는 데이터의 묵시 삭제 금지.
# ponytail: 새 NOT NULL ephemeral child 참조자가 생기면 여기에만 추가한다.
_DELETE_CHILD_REFERRERS = frozenset({
    ("order_mutation_read_resources", "order_id"),  # ephemeral read-receipt child
})


class DeleteRetentionError(RuntimeError):
    """대상 선정/검증/삭제 계약 위반(호출자는 삭제 0 으로 처리)."""


class DeleteRetentionDriftError(DeleteRetentionError):
    """live 상태가 승인된 plan(id 집합·count·snapshot)과 달라 삭제를 중단."""


class DeleteRetentionFKError(DeleteRetentionError):
    """``orders.id`` 를 참조하는 미처리 non-cascade FK 존재(하드 삭제가 FK 를 깰 위험)."""


@dataclass(frozen=True)
class DeleteRetentionResult:
    """apply/dry-run 결과.

    Attributes:
        target_count: live 재계산으로 확정된 삭제 대상 주문 수.
        deleted: 실제 삭제된 주문 수(dry-run 은 0).
        applied: ``apply=True`` 로 삭제를 수행했으면 True.
        consumed: OPS-APPROVAL 토큰을 소비했으면 True(dry-run 은 False).
        plan_sha256: 실행 시 검증한 plan 해시(승인 artifact_sha256 과 일치).
        count_sha256: expected count hash(id 집합·수 커밋).
        result_sha256: consume 결과 해시(dry-run 은 None).
    """

    target_count: int
    deleted: int
    applied: bool
    consumed: bool
    plan_sha256: str
    count_sha256: str
    result_sha256: Optional[str] = None


# --------------------------------------------------------------------------- #
# canonical hashing (float 포함 임의 structured_data 를 결정적으로 해시)
# --------------------------------------------------------------------------- #
def _json_default(obj: Any) -> str:
    """datetime/date/Decimal/bytes 등 비-JSON 값을 결정적 문자열로."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return format(obj, "f")
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).hex()
    return str(obj)


def _canonical_bytes(obj: Any) -> bytes:
    """sorted-key compact JSON UTF-8 bytes(결정적). float 는 DB 값 그대로 직렬화."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default,
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# FK coverage (참조 무결성 fail-closed)
# --------------------------------------------------------------------------- #
def _referring_fks() -> list[tuple[str, str, str]]:
    """``orders.id`` 를 참조하는 모든 FK 를 ``(table, column, ondelete)`` 로 열거."""
    out: list[tuple[str, str, str]] = []
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table.name == "orders" and fk.column.name == "id":
                out.append((table.name, fk.parent.name, (fk.ondelete or "").upper()))
    return out


def _classify_referrers() -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """non-cascade 참조자를 ``(nullable, delete_children, notnull_unhandled)`` 로 분류.

    * nullable → 하드 삭제 시 NULL 로 링크만 끊는다(행 보존, 비파괴).
    * delete_children → NOT NULL 이며 allowlist 에 있는 ephemeral child(함께 삭제).
    * notnull_unhandled → NOT NULL 인데 allowlist 에 없음(fail-closed 대상).
    """
    nullable: list[tuple[str, str]] = []
    delete_children: list[tuple[str, str]] = []
    notnull_unhandled: list[tuple[str, str]] = []
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table.name != "orders" or fk.column.name != "id":
                continue
            if (fk.ondelete or "").upper() in ("CASCADE", "SET NULL"):
                continue
            key = (table.name, fk.parent.name)
            if fk.parent.nullable:
                nullable.append(key)
            elif key in _DELETE_CHILD_REFERRERS:
                delete_children.append(key)
            else:
                notnull_unhandled.append(key)
    return sorted(nullable), sorted(delete_children), sorted(notnull_unhandled)


def _assert_fk_coverage() -> None:
    """CASCADE/SET NULL 로 정리 안 되고 nullable 도 아니며 allowlist 에도 없는 NOT NULL
    참조자가 있으면 중단(알 수 없는 데이터의 묵시 삭제 금지 — fail-closed).

    :raises DeleteRetentionFKError: 미처리 NOT NULL non-cascade 참조자 존재.
    """
    _, _, unhandled = _classify_referrers()
    if unhandled:
        raise DeleteRetentionFKError(
            f"unhandled NOT NULL non-cascade referrers to orders.id: {unhandled}; "
            "hard delete would violate FK integrity and blind-deleting them is unsafe — "
            "add to _DELETE_CHILD_REFERRERS only after review."
        )


# --------------------------------------------------------------------------- #
# 대상 선정 + plan 조립
# --------------------------------------------------------------------------- #
def _parse_deleted_at(value: Optional[str]) -> Optional[datetime.datetime]:
    """``deleted_at`` 문자열을 canonical 포맷으로 파싱(실패 시 None → 대상 제외)."""
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, _DELETED_AT_FORMAT)
    except (ValueError, TypeError):
        return None


def select_retention_targets(
    session: Session,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: Optional[datetime.datetime] = None,
) -> list[int]:
    """soft-delete + retention 경과 주문 id(오름차순)를 반환.

    ``deleted_at`` 이 세팅되고 canonical 포맷으로 파싱되며 ``now - retention_days`` 이전인
    주문만 대상이다. 파싱 불가한 legacy 값은 안전하게 제외한다(날짜를 확신 못 하면 삭제 안 함).

    :raises DeleteRetentionError: retention_days<0.
    """
    if retention_days < 0:
        raise DeleteRetentionError("retention_days must be >= 0")
    cutoff = (now or now_utc_naive()) - datetime.timedelta(days=retention_days)
    rows = session.execute(
        text("SELECT id, deleted_at FROM orders WHERE deleted_at IS NOT NULL ORDER BY id")
    ).all()
    targets = []
    for oid, deleted_at in rows:
        parsed = _parse_deleted_at(deleted_at)
        if parsed is not None and parsed < cutoff:
            targets.append(int(oid))
    return targets


def _attachment_ref_sha256(row: dict[str, Any]) -> str:
    """첨부의 storage 참조/메타데이터 해시.

    ponytail: R2 실제 바이트를 안 받으므로 storage_key+메타데이터 identity 해시다(계획↔
    실행 사이 첨부 집합 변동을 감지하는 데 충분). 진짜 content hash 가 필요하면 R2 fetch 를
    붙여 이 함수만 교체한다.
    """
    ident = {
        "storage_key": row.get("storage_key"),
        "thumbnail_key": row.get("thumbnail_key"),
        "filename": row.get("filename"),
        "file_type": row.get("file_type"),
        "category": row.get("category"),
        "file_size": row.get("file_size"),
    }
    return _sha256_hex(_canonical_bytes(ident))


def _order_snapshot(session: Session, order_id: int) -> Optional[dict[str, Any]]:
    """주문 row + 첨부(해시 포함)를 before snapshot(export 백업)으로 직렬화."""
    order = session.execute(
        text("SELECT * FROM orders WHERE id = :id"), {"id": order_id}
    ).mappings().one_or_none()
    if order is None:
        return None
    attachments = session.execute(
        text(
            "SELECT id, storage_key, thumbnail_key, filename, file_type, category, "
            "file_size FROM order_attachments WHERE order_id = :id ORDER BY id"
        ),
        {"id": order_id},
    ).mappings().all()
    return {
        "order": dict(order),
        "attachments": [
            {**dict(a), "ref_sha256": _attachment_ref_sha256(dict(a))} for a in attachments
        ],
    }


def _dependency_totals(session: Session, order_ids: list[int]) -> dict[str, int]:
    """``orders.id`` 를 참조하는 각 FK 테이블의 대상 참조 수(참조 무결성 artifact)."""
    totals: dict[str, int] = {}
    if not order_ids:
        return totals
    for table, column, _ in sorted(_referring_fks()):
        # table/column 은 메타데이터 식별자(신뢰) — 값은 바인드 파라미터(주입 표면 0).
        n = session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {column} = ANY(:ids)"),
            {"ids": order_ids},
        ).scalar() or 0
        totals[f"{table}.{column}"] = int(n)
    return totals


def _build_plan_core(
    session: Session,
    order_ids: Iterable[int],
    *,
    retention_days: int,
    now: datetime.datetime,
    packet_id: str,
    phase: str,
) -> dict[str, Any]:
    """정확히 승인 대상 id 중 **여전히 soft-delete+retention 경과** 인 것만으로 plan core 조립.

    승인된 id 라도 복구되었거나(``deleted_at`` clear) 아직 미경과이면 탈락시킨다 — 이 탈락이
    곧 count/set drift 로 이어져 실행이 중단된다(soft-delete only·retention only 강제).
    """
    cutoff = now - datetime.timedelta(days=retention_days)
    kept: list[int] = []
    orders_snap: list[dict[str, Any]] = []
    for oid in sorted({int(x) for x in order_ids}):
        snap = _order_snapshot(session, oid)
        if snap is None:
            continue  # 이미 물리 삭제됨/미존재 → 탈락
        parsed = _parse_deleted_at(snap["order"].get("deleted_at"))
        if parsed is None or parsed >= cutoff:
            continue  # 복구됨 or 미경과 → 탈락(soft-delete only·retention only)
        kept.append(oid)
        orders_snap.append({"order_id": oid, **snap})

    core = {
        "schema_version": 1,
        "operation_id": OPERATION_ID,
        "packet_id": packet_id,
        "phase": phase,
        "retention_days": retention_days,
        "exact_order_ids": kept,
        "expected_count": len(kept),
        "dependency_totals": _dependency_totals(session, kept),
        "orders": orders_snap,
    }
    return core


def build_delete_plan(
    session: Session,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: Optional[datetime.datetime] = None,
    packet_id: str = PACKET_ID,
    phase: str = DEFAULT_PHASE,
    order_ids: Optional[Iterable[int]] = None,
) -> dict[str, Any]:
    """삭제 계획 artifact 를 조립(``plan_sha256``·``count_sha256`` 포함).

    ``order_ids`` 가 주어지면 그 id 로 한정(실행 시 live 재계산 경로), 없으면
    :func:`select_retention_targets` 로 대상을 선정한다(계획 단계).

    Returns:
        plan dict — ``plan_sha256`` 은 core 전체를, ``count_sha256`` 은 id 집합·수를 커밋한다.
        ``generated_at`` 은 core 밖(비결정 필드)이라 해시에 포함되지 않는다.
    """
    _assert_fk_coverage()
    now = now or now_utc_naive()
    if order_ids is None:
        order_ids = select_retention_targets(session, retention_days=retention_days, now=now)
    core = _build_plan_core(
        session, order_ids, retention_days=retention_days, now=now,
        packet_id=packet_id, phase=phase,
    )
    count_sha256 = _sha256_hex(_canonical_bytes(
        {"exact_order_ids": core["exact_order_ids"], "expected_count": core["expected_count"]}
    ))
    plan_sha256 = _sha256_hex(_canonical_bytes(core))
    return {
        **core,
        "count_sha256": count_sha256,
        "plan_sha256": plan_sha256,
        "generated_at": now.strftime(_DELETED_AT_FORMAT),
    }


def _ops_scope(plan: dict[str, Any]) -> dict[str, Any]:
    """plan → OPS-APPROVAL scope object(exact fields). artifact_sha256=plan_sha256."""
    return {
        "schema_version": 1,
        "operation_id": OPERATION_ID,
        "packet_id": plan["packet_id"],
        "target_ids_or_family": list(plan["exact_order_ids"]),
        "phase": plan["phase"],
        "artifact_sha256": plan["plan_sha256"],
        "expected_version": plan["expected_count"],
        "expected_generation": None,
    }


# --------------------------------------------------------------------------- #
# hard delete + apply(OPS-APPROVAL 게이트)
# --------------------------------------------------------------------------- #
def _chunks(items: list[int], size: int) -> Iterable[list[int]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _hard_delete(session: Session, order_ids: list[int], *, batch_size: int, plan_sha256: str) -> bytes:
    """정확히 ``order_ids`` 를 FK-safe 하게 배치 삭제(consume tx 안).

    non-CASCADE 참조자를 먼저 정리한 뒤 주문을 삭제한다: nullable 참조는 NULL 로 링크만 끊고,
    allowlist 의 NOT NULL ephemeral child 는 삭제하며, 나머지 FK 는 DB CASCADE/SET NULL 이
    맡는다. DELETE 술어는 ``deleted_at IS NOT NULL`` 을 재확인해 실행 직전 복구된 주문은 지우지
    않는다 — 그 경우 삭제수<대상수 → 예외 → 전체 rollback(토큰 미소비).

    식별자(table/column)는 SQLAlchemy 메타데이터에서만 오므로 f-string 보간에 주입 표면이
    없다(값은 바인드 파라미터).

    :returns: consume 결과 bytes(대상수·plan_sha256 커밋).
    :raises DeleteRetentionError: 실제 삭제 수가 대상 수와 다름(동시 변경 감지).
    """
    nullable, delete_children, _ = _classify_referrers()
    deleted = 0
    for chunk in _chunks(order_ids, max(1, batch_size)):
        for table, column in delete_children:
            session.execute(
                text(f"DELETE FROM {table} WHERE {column} = ANY(:ids)"), {"ids": chunk}
            )
        for table, column in nullable:
            session.execute(
                text(f"UPDATE {table} SET {column} = NULL WHERE {column} = ANY(:ids)"),
                {"ids": chunk},
            )
        n = session.execute(
            text("DELETE FROM orders WHERE id = ANY(:ids) AND deleted_at IS NOT NULL"),
            {"ids": chunk},
        ).rowcount or 0
        deleted += n
    if deleted != len(order_ids):
        raise DeleteRetentionError(
            f"expected to hard-delete {len(order_ids)} soft-deleted orders, "
            f"deleted {deleted} (concurrent restore/delete) — aborting, nothing committed."
        )
    return f"{OPERATION_ID}:{deleted}:{plan_sha256}".encode("utf-8")


def apply_delete_retention(
    session: Session,
    *,
    approved_plan: dict[str, Any],
    raw_secret: bytes,
    apply: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    now: Optional[datetime.datetime] = None,
) -> DeleteRetentionResult:
    """승인된 plan 을 live 상태로 재검증하고, ``apply`` 면 OPS-APPROVAL 소비 후 hard delete.

    호출자가 ``session`` 의 tx 를 소유한다: ``apply`` 성공 시 commit(consume+delete 원자),
    dry-run 이거나 검증 실패 시 rollback(삭제 0·토큰 미소비).

    Args:
        approved_plan: 승인 artifact 로 쓰인 plan(:func:`build_delete_plan` 산출).
        raw_secret: OPS-APPROVAL one-time secret raw bytes(control-root 토큰에서 디코드).
        apply: True 면 실제 소비·삭제, False(기본)면 dry-run(소비 0·삭제 0).
        batch_size: 한 배치 삭제 id 수(같은 tx 안 청크, ≥1).
        now: 테스트용 시각 주입.

    Returns:
        DeleteRetentionResult.

    Raises:
        DeleteRetentionDriftError: live plan 이 승인 plan 과 불일치(count/set/snapshot drift).
        DeleteRetentionFKError: 미처리 non-cascade 참조자.
        ApprovalConsumeError: 승인 검증 실패(만료/비ADMIN/version변경/재소비/scope 불일치).
    """
    _assert_fk_coverage()
    now = now or now_utc_naive()
    retention_days = int(approved_plan["retention_days"])
    approved_ids = list(approved_plan["exact_order_ids"])

    live = build_delete_plan(
        session,
        retention_days=retention_days,
        now=now,
        packet_id=approved_plan["packet_id"],
        phase=approved_plan["phase"],
        order_ids=approved_ids,
    )

    # 검증: count hash → set → plan 전체 해시. 하나라도 어긋나면 삭제 0.
    if live["count_sha256"] != approved_plan["count_sha256"]:
        raise DeleteRetentionDriftError(
            "expected count hash mismatch (target set/count drifted since approval)."
        )
    if live["exact_order_ids"] != sorted(int(x) for x in approved_ids):
        raise DeleteRetentionDriftError("exact order-ID set drifted since approval.")
    if live["plan_sha256"] != approved_plan["plan_sha256"]:
        raise DeleteRetentionDriftError(
            "plan artifact hash mismatch (order snapshot/attachment/dependency drift)."
        )

    order_ids = list(live["exact_order_ids"])
    result = DeleteRetentionResult(
        target_count=len(order_ids), deleted=0, applied=False, consumed=False,
        plan_sha256=live["plan_sha256"], count_sha256=live["count_sha256"],
    )
    if not apply:
        return result  # dry-run: 승인 미소비·삭제 0.

    # 동시 apply 직렬화(tx 종료 시 자동 해제).
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": _ADVISORY_LOCK_KEY})

    scope = _ops_scope(live)

    def _target_mutation(sess: Session) -> bytes:
        return _hard_delete(sess, order_ids, batch_size=batch_size, plan_sha256=live["plan_sha256"])

    result_sha = consume_same_db(
        session,
        operation_id=OPERATION_ID,
        scope_obj=scope,
        artifact_sha256=live["plan_sha256"],
        expected_version=live["expected_count"],
        expected_generation=None,
        raw_secret=raw_secret,
        target_mutation=_target_mutation,
        now=now,
    )
    return DeleteRetentionResult(
        target_count=len(order_ids), deleted=len(order_ids), applied=True, consumed=True,
        plan_sha256=live["plan_sha256"], count_sha256=live["count_sha256"],
        result_sha256=result_sha,
    )


__all__ = [
    "OPERATION_ID",
    "PACKET_ID",
    "DEFAULT_RETENTION_DAYS",
    "DeleteRetentionError",
    "DeleteRetentionDriftError",
    "DeleteRetentionFKError",
    "DeleteRetentionResult",
    "select_retention_targets",
    "build_delete_plan",
    "apply_delete_retention",
]
