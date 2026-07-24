"""Offline local recovery apply under OPS-APPROVAL (OFFLINE-01, SSOT §5.2).

브라우저/기기에 큐잉된 **미전송 order 변경(offline local queue)**을, OPS-APPROVAL 승인
(seq≥1 admin 재인증·one-time·control-root) 하에서, 그리고 큐 무결성이 검증된 뒤에만
적용한다. SW-01(``cfc27685``)이 offline mutation 을 OFF 로 유지하므로 자동 재생(background
replay)은 없다 — recovery 는 오직 **명시 승인 apply** 로만 이뤄진다.

apply 전 다음 3개 검증을 **모두 통과**해야 한다(하나라도 어긋나면 apply 0):

* **inventory hash**: 큐 전체(``schema_version`` + 정규화된 ``entries``)의 canonical
  sha256. 큐가 export↔apply 사이 변조되면 불일치. OPS-APPROVAL ``artifact_sha256`` 이 이
  해시에 바인딩돼, 승인된 것과 다른 큐는 consume 단계에서 거부된다.
* **schema(구조 정합·버전)**: ``schema_version`` 이 지원 버전과 일치하고, 각 entry 가
  허용된 op·정확한 필드 구조를 만족(fail-closed: 미지 op·결손/여분 필드는 거부).
* **order-ID hash**: 대상 order id 집합(정렬·중복 제거)의 canonical sha256. 승인된 대상과
  다른 주문으로 recovery 를 돌리는 변조를 감지.

OPS-APPROVAL 게이트는 :func:`foms.services.security.ops_approval.consume_same_db` 를
재사용한다(same-DB one-time consume, ``artifact_sha256=inventory_sha256``). dry-run(기본)은
승인을 **소비하지 않고** apply 0 이다. ``apply`` 만 승인 토큰을 소비하고, 검증을 전부 통과한
뒤에야 모든 entry 를 **한 tx(all-or-none)** 로 적용한다 — 어느 entry 라도(예: 대상 주문
부재) 실패하면 전체 rollback 되어 부분 적용 0·토큰 미소비(재실행이 resume)다.

경계(OFFLINE-01): 승인 없이 apply 금지, 검증 미통과 apply 금지, offline 자동 재생 금지
(SW-01 OFF 유지·명시 승인 apply 만), 부분 적용 금지, 새 스키마/마이그레이션 없음(기존
``orders.structured_data`` 재사용), ``models``·``order_mutation_policy`` 무변경.
"""
from __future__ import annotations

import copy
import datetime
import decimal
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.ops_approval import consume_same_db
from models import Order

OPERATION_ID = "OFFLINE_LOCAL_RECOVERY_APPROVE"
PACKET_ID = "OFFLINE-01"
DEFAULT_PHASE = "apply"
SCHEMA_VERSION = 1

# 각 queue entry 의 정확한 필드(exact). fail-closed — 결손/여분 필드는 schema 위반.
_ENTRY_FIELDS = frozenset({"order_id", "op", "patch"})

# 허용 op 화이트리스트(fail-closed). 미지 op 는 schema 검증에서 거부된다.
# ponytail: 지금 필요한 건 structured_data 병합 하나뿐. op 종류가 늘면 여기 +
#           :func:`_apply_entry` 에만 추가한다.
_ALLOWED_OPS = frozenset({"structured_data_merge"})


class OfflineRecoveryError(RuntimeError):
    """큐 검증/적용 계약 위반(호출자는 apply 0 으로 처리)."""


class OfflineRecoverySchemaError(OfflineRecoveryError):
    """큐 schema/version 부적합(미지 op·결손 필드·미지원 버전 — fail-closed)."""


class OfflineRecoveryDriftError(OfflineRecoveryError):
    """inventory/order-ID hash 불일치 또는 대상 주문 부재로 적용을 중단(all-or-none)."""


@dataclass(frozen=True)
class OfflineRecoveryResult:
    """apply/dry-run 결과.

    Attributes:
        entry_count: 큐에 담긴 미전송 변경 entry 수.
        applied_count: 실제 적용된 entry 수(dry-run 은 0).
        applied: ``apply=True`` 로 적용을 수행했으면 True.
        consumed: OPS-APPROVAL 토큰을 소비했으면 True(dry-run 은 False).
        inventory_sha256: 검증한 큐 무결성 해시(승인 ``artifact_sha256`` 과 일치).
        order_ids_sha256: 대상 order-ID 집합 해시.
        result_sha256: consume 결과 해시(dry-run 은 None).
    """

    entry_count: int
    applied_count: int
    applied: bool
    consumed: bool
    inventory_sha256: str
    order_ids_sha256: str
    result_sha256: Optional[str] = None


# --------------------------------------------------------------------------- #
# canonical hashing (float 포함 임의 patch 를 결정적으로 해시)
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
    """sorted-key compact JSON UTF-8 bytes(결정적)."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default,
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# schema 검증(fail-closed) + hash 파생
# --------------------------------------------------------------------------- #
def _validate_entry(entry: Any) -> tuple[int, str, dict[str, Any]]:
    """queue entry 하나를 검증하고 ``(order_id, op, patch)`` 로 정규화.

    Args:
        entry: 큐 export 의 개별 변경 항목(dict).

    Returns:
        (order_id, op, patch) — 검증을 통과한 정규화 튜플.

    Raises:
        OfflineRecoverySchemaError: 타입/필드/op 부적합(미지 op·결손·여분 필드 포함).
    """
    if not isinstance(entry, dict):
        raise OfflineRecoverySchemaError("queue entry must be an object.")
    keys = set(entry.keys())
    if keys != _ENTRY_FIELDS:
        raise OfflineRecoverySchemaError(
            f"entry fields mismatch; expected exactly {sorted(_ENTRY_FIELDS)}, got {sorted(keys)}."
        )
    oid = entry["order_id"]
    # bool 은 int 서브타입이므로 명시 배제(True/False 를 order_id 로 허용하지 않는다).
    if not isinstance(oid, int) or isinstance(oid, bool):
        raise OfflineRecoverySchemaError("entry.order_id must be an int.")
    op = entry["op"]
    if op not in _ALLOWED_OPS:
        raise OfflineRecoverySchemaError(f"entry.op {op!r} is not allowed (fail-closed).")
    patch = entry["patch"]
    if not isinstance(patch, dict):
        raise OfflineRecoverySchemaError("entry.patch must be an object.")
    return oid, op, patch


def _normalized_entries(entries: Any) -> list[dict[str, Any]]:
    """entries 리스트를 검증·정규화(정확한 필드 순서 무관 canonical 표현)."""
    if not isinstance(entries, list):
        raise OfflineRecoverySchemaError("queue.entries must be a list.")
    out: list[dict[str, Any]] = []
    for entry in entries:
        oid, op, patch = _validate_entry(entry)
        out.append({"order_id": oid, "op": op, "patch": patch})
    return out


def _inventory_sha256(normalized_entries: list[dict[str, Any]]) -> str:
    """큐 무결성 해시 = sha256(schema_version + 정규화된 entries)."""
    return _sha256_hex(_canonical_bytes(
        {"schema_version": SCHEMA_VERSION, "entries": normalized_entries}
    ))


def _order_ids_sha256(normalized_entries: list[dict[str, Any]]) -> tuple[str, list[int]]:
    """대상 order-ID 집합(정렬·중복제거) 해시와 그 id 리스트."""
    order_ids = sorted({e["order_id"] for e in normalized_entries})
    return _sha256_hex(_canonical_bytes(order_ids)), order_ids


def build_recovery_plan(
    entries: Iterable[dict[str, Any]],
    *,
    packet_id: str = PACKET_ID,
    phase: str = DEFAULT_PHASE,
    device_id: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> dict[str, Any]:
    """offline 큐 export 를 승인용 recovery plan artifact 로 조립(검증 + 해시 포함).

    admin 은 이 plan(특히 ``inventory_sha256``)을 검토·승인하고, apply 시점에 같은 plan 을
    :func:`apply_offline_recovery` 에 넘긴다. 조립 단계에서 이미 schema 를 검증하므로
    부적합 큐는 승인 artifact 자체가 만들어지지 않는다.

    Args:
        entries: 미전송 변경 항목들(각 ``{order_id, op, patch}``).
        packet_id: 승인 scope packet(기본 ``OFFLINE-01``).
        phase: 승인 scope phase(기본 ``apply``).
        device_id: 큐를 export 한 기기/브라우저 식별자(정보용, 해시 비포함).
        now: 테스트용 시각 주입.

    Returns:
        plan dict — ``inventory_sha256``·``order_ids_sha256``·``entry_count``·정규화
        ``entries``·``order_ids`` 를 담는다. ``generated_at``·``device_id`` 는 무결성
        해시에 포함되지 않는 비결정 필드다.

    Raises:
        OfflineRecoverySchemaError: entries 가 schema 를 위반.
    """
    now = now or now_utc_naive()
    normalized = _normalized_entries(entries)
    inventory_sha256 = _inventory_sha256(normalized)
    order_ids_sha256, order_ids = _order_ids_sha256(normalized)
    return {
        "schema_version": SCHEMA_VERSION,
        "operation_id": OPERATION_ID,
        "packet_id": packet_id,
        "phase": phase,
        "device_id": device_id,
        "entries": normalized,
        "order_ids": order_ids,
        "entry_count": len(normalized),
        "inventory_sha256": inventory_sha256,
        "order_ids_sha256": order_ids_sha256,
        "generated_at": now.isoformat(),
    }


def _ops_scope(plan: dict[str, Any]) -> dict[str, Any]:
    """plan → OPS-APPROVAL scope object(exact fields). artifact_sha256=inventory_sha256."""
    return {
        "schema_version": 1,  # OPS scope 포맷 버전(큐 schema_version 과 별개, 항상 1).
        "operation_id": OPERATION_ID,
        "packet_id": plan["packet_id"],
        "target_ids_or_family": list(plan["order_ids"]),
        "phase": plan["phase"],
        "artifact_sha256": plan["inventory_sha256"],
        "expected_version": plan["entry_count"],
        "expected_generation": None,
    }


# --------------------------------------------------------------------------- #
# 적용(all-or-none) + apply(OPS-APPROVAL 게이트)
# --------------------------------------------------------------------------- #
def _apply_entry(session: Session, order: Order, op: str, patch: dict[str, Any]) -> None:
    """단일 entry 를 대상 주문에 적용(현재 op: structured_data 상위 병합).

    JSONB 수정은 프로젝트 규약(copy.deepcopy + flag_modified)을 따른다.

    Raises:
        OfflineRecoverySchemaError: 미지 op(정상 경로에선 도달 불가 — 방어).
    """
    if op == "structured_data_merge":
        sd = copy.deepcopy(order.structured_data or {})
        # ponytail: 상위 키 shallow 병합. 중첩 offline patch 가 필요해지면 deep-merge 로
        #           이 한 줄만 승급한다.
        sd.update(patch)
        order.structured_data = sd
        flag_modified(order, "structured_data")
        return
    raise OfflineRecoverySchemaError(f"unknown op {op!r} at apply time (fail-closed).")


def _apply_entries(
    session: Session, entries: list[dict[str, Any]], *, inventory_sha256: str
) -> bytes:
    """모든 entry 를 순서대로 적용(consume tx 안). 대상 부재 등은 예외 → 전체 rollback.

    all-or-none: 어느 entry 라도 실패하면 예외를 던져 consume tx 전체가 rollback 되므로
    부분 적용이 발생하지 않는다.

    Returns:
        consume 결과 bytes(entry 수·inventory_sha256 커밋).

    Raises:
        OfflineRecoveryDriftError: 대상 주문이 존재하지 않음(부분 적용 방지 중단).
    """
    for entry in entries:
        oid, op, patch = _validate_entry(entry)  # 방어적 재검증(defense-in-depth).
        order = session.get(Order, oid)
        if order is None:
            raise OfflineRecoveryDriftError(
                f"target order {oid} not found; aborting all-or-none (nothing applied)."
            )
        _apply_entry(session, order, op, patch)
    session.flush()
    return f"{OPERATION_ID}:{len(entries)}:{inventory_sha256}".encode("utf-8")


def apply_offline_recovery(
    session: Session,
    *,
    approved_plan: dict[str, Any],
    raw_secret: bytes,
    apply: bool = False,
    now: Optional[datetime.datetime] = None,
) -> OfflineRecoveryResult:
    """승인된 recovery plan 을 검증하고, ``apply`` 면 OPS-APPROVAL 소비 후 all-or-none 적용.

    호출자가 ``session`` 의 tx 를 소유한다: ``apply`` 성공 시 commit(consume+적용 원자),
    dry-run 이거나 검증 실패 시 rollback(적용 0·토큰 미소비). offline 자동 재생 경로는
    없다 — 이 함수는 오직 명시 호출 + ``apply=True`` + 유효 승인 토큰일 때만 적용한다.

    Args:
        approved_plan: 승인 artifact 로 쓰인 plan(:func:`build_recovery_plan` 산출).
        raw_secret: OPS-APPROVAL one-time secret raw bytes(control-root 토큰에서 디코드).
        apply: True 면 실제 소비·적용, False(기본)면 dry-run(소비 0·적용 0).
        now: 테스트용 시각 주입.

    Returns:
        OfflineRecoveryResult.

    Raises:
        OfflineRecoverySchemaError: plan schema/version 부적합.
        OfflineRecoveryDriftError: inventory/order-ID hash 불일치 또는 대상 주문 부재.
        ApprovalConsumeError: 승인 검증 실패(만료/비ADMIN/version 변경/재소비/scope 불일치).
    """
    now = now or now_utc_naive()

    # 1. schema/version 검증(fail-closed).
    if approved_plan.get("operation_id") != OPERATION_ID:
        raise OfflineRecoverySchemaError(
            "approved_plan.operation_id must be OFFLINE_LOCAL_RECOVERY_APPROVE."
        )
    if approved_plan.get("schema_version") != SCHEMA_VERSION:
        raise OfflineRecoverySchemaError(
            f"unsupported queue schema_version {approved_plan.get('schema_version')!r} "
            f"(expected {SCHEMA_VERSION})."
        )
    normalized = _normalized_entries(approved_plan.get("entries"))

    # 2. inventory / order-ID hash 검증(승인 후 plan hand-edit 감지).
    inventory_sha256 = _inventory_sha256(normalized)
    order_ids_sha256, _order_ids = _order_ids_sha256(normalized)
    if inventory_sha256 != approved_plan.get("inventory_sha256"):
        raise OfflineRecoveryDriftError(
            "inventory hash mismatch (queue tampered since approval)."
        )
    if order_ids_sha256 != approved_plan.get("order_ids_sha256"):
        raise OfflineRecoveryDriftError(
            "order-ID hash mismatch (target set tampered since approval)."
        )

    result = OfflineRecoveryResult(
        entry_count=len(normalized), applied_count=0, applied=False, consumed=False,
        inventory_sha256=inventory_sha256, order_ids_sha256=order_ids_sha256,
    )
    if not apply:
        return result  # dry-run: 승인 미소비·적용 0(자동 재생 없음).

    scope = _ops_scope({**approved_plan, "order_ids": _order_ids, "entry_count": len(normalized)})

    def _target_mutation(sess: Session) -> bytes:
        return _apply_entries(sess, normalized, inventory_sha256=inventory_sha256)

    result_sha = consume_same_db(
        session,
        operation_id=OPERATION_ID,
        scope_obj=scope,
        artifact_sha256=inventory_sha256,
        expected_version=len(normalized),
        expected_generation=None,
        raw_secret=raw_secret,
        target_mutation=_target_mutation,
        now=now,
    )
    return OfflineRecoveryResult(
        entry_count=len(normalized), applied_count=len(normalized), applied=True, consumed=True,
        inventory_sha256=inventory_sha256, order_ids_sha256=order_ids_sha256,
        result_sha256=result_sha,
    )


__all__ = [
    "OPERATION_ID",
    "PACKET_ID",
    "SCHEMA_VERSION",
    "OfflineRecoveryError",
    "OfflineRecoverySchemaError",
    "OfflineRecoveryDriftError",
    "OfflineRecoveryResult",
    "build_recovery_plan",
    "apply_offline_recovery",
]
