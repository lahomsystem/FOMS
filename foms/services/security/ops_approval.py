"""고위험 ops 승인 consume 라이브러리 (§2.1 line 205-207).

승인된 :class:`~models.OpsApprovalRequest` 를 고위험 CLI 가 ``--approval-token-file``
로 소비할 때 쓰는 공용 인프라. business operation 은 구현하지 않는다 — 실제 mutation 은
호출자가 넘기는 ``target_mutation`` 콜러블이 수행하고, 이 모듈은 오직 승인 검증/
one-time consume/reservation snapshot/audit/finalize 만 책임진다.

두 모드:

* **same-DB(SAME)**: approval row + principal row 를 ``FOR UPDATE`` 로 잠그고 active
  ADMIN·동일 principal version·exact operation/scope/artifact/version/generation 을
  확인한 뒤 target mutation + CONSUMED 를 **한 transaction** 에 commit. one-time.
* **cross-DB(TARGET_RESERVED)**: primary 에서 같은 검증 뒤 5분 **RESERVED**(취소 불가
  authorization snapshot)를 commit → target DB 에서 unique
  ``(approval_id,reservation_id,operation_scope_sha256)`` audit + mutation 을 한 tx 로
  commit → primary 를 CONSUMED 로 finalize. crash retry 는 target audit 이 있으면
  result hash 대조 후 finalize 만 한다.

RESERVED 는 사후 취소하지 않는다. 이후 role/deactivate/version 변경은 **신규**
reservation 만 막는다.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from typing import Any, Callable, Optional

from pathlib import Path

from sqlalchemy.orm import Session

from models import OpsApprovalRequest, OpsApprovalTargetAudit, SecurityPrincipalVersion, User
from foms.services.datetime_kst import now_utc_naive
from foms.services.security import ops_control_root as _root_store

RESERVATION_TTL_SECONDS = 300  # 5분 non-cancelable snapshot

# scope object 의 exact fields (§2.1 line 209).
_SCOPE_FIELDS = frozenset({
    "schema_version",
    "operation_id",
    "packet_id",
    "target_ids_or_family",
    "phase",
    "artifact_sha256",
    "expected_version",
    "expected_generation",
})


class ApprovalConsumeError(RuntimeError):
    """승인 검증/consume 이 계약을 위반할 때(호출자는 이 예외를 mutation 0 으로 처리)."""


def _utcnow() -> datetime.datetime:
    """naive UTC now(프로젝트 timestamp 규약 = now_utc_naive)."""
    return now_utc_naive()


def _sha256_hex(data: bytes) -> str:
    """bytes 의 sha256 hex."""
    return hashlib.sha256(data).hexdigest()


def canonical_scope_bytes(scope_obj: dict[str, Any]) -> bytes:
    """scope object 를 canonical JSON bytes 로 직렬화(RFC 8785 근사).

    exact fields 검증, identifier 배열 정렬·중복 거부 후 sorted-key/compact JSON 으로
    직렬화한다.

    :raises ApprovalConsumeError: 필드 불일치, 중복 identifier, 비직렬화 타입.
    """
    if not isinstance(scope_obj, dict):
        raise ApprovalConsumeError("scope must be a JSON object.")
    keys = set(scope_obj.keys())
    if keys != _SCOPE_FIELDS:
        raise ApprovalConsumeError(
            f"scope fields mismatch; expected exactly {sorted(_SCOPE_FIELDS)}, got {sorted(keys)}."
        )
    normalized = dict(scope_obj)
    ids = normalized.get("target_ids_or_family")
    if isinstance(ids, list):
        if any(not isinstance(x, (str, int)) for x in ids):
            raise ApprovalConsumeError("target_ids_or_family entries must be str/int.")
        if len(set(ids)) != len(ids):
            raise ApprovalConsumeError("target_ids_or_family must not contain duplicates.")
        normalized["target_ids_or_family"] = sorted(ids, key=lambda x: (str(type(x)), x))
    # ponytail: sorted-key compact JSON == RFC 8785 JCS for our str/int/array-only
    #           scopes; upgrade to a full JCS lib only if float/unicode-escape scopes appear.
    return json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_scope_sha256(scope_obj: dict[str, Any]) -> str:
    """scope object 의 canonical sha256 hex."""
    return _sha256_hex(canonical_scope_bytes(scope_obj))


def compute_operation_scope_sha256(operation_id: str, scope_sha256: str) -> str:
    """target audit unique 용 operation+scope 결합 해시."""
    return _sha256_hex(f"{operation_id}\0{scope_sha256}".encode("utf-8"))


def nonce_hash_from_secret(raw_secret: bytes) -> str:
    """one-time secret raw bytes 의 sha256 hex(= DB nonce_hash). raw 는 저장 금지."""
    return _sha256_hex(raw_secret)


def read_secret_from_token_file(
    token_path: "str | Path",
    control_root: "Path",
    *,
    expected_operation_id: Optional[str] = None,
) -> bytes:
    """``--approval-token-file`` 을 control root 안에서 읽어 raw one-time secret 을 얻는다.

    고위험 consumer CLI 가 소비 직전에 호출하는 공용 진입점. 토큰은 control root 아래여야
    하고(밖이면 거부), 지정 시 operation_id 도 대조한다. 실제 authorization 바인딩은
    secret→nonce_hash 로 이루어지므로 이 함수는 편의/조기 거부일 뿐이다.

    :returns: base64url secret 을 strict decode 한 raw bytes.
    :raises OpsControlRootError: 토큰이 root 밖이거나 스키마 위반.
    :raises ApprovalConsumeError: expected_operation_id 불일치.
    """
    token = _root_store.read_token(Path(token_path), control_root)
    if expected_operation_id is not None and token.get("operation_id") != expected_operation_id:
        raise ApprovalConsumeError("token operation_id does not match expected operation.")
    return _root_store.decode_secret_b64url(token["one_time_secret_b64url"])


def _verify_approved_row(
    session: Session,
    *,
    row: Optional[OpsApprovalRequest],
    operation_id: str,
    scope_sha256: str,
    artifact_sha256: Optional[str],
    expected_version: Optional[int],
    expected_generation: Optional[int],
    now: datetime.datetime,
) -> None:
    """APPROVED row 의 exact 승인 조건을 검증(위반 시 예외 → mutation 0).

    approval row 는 호출자가 이미 ``FOR UPDATE`` 로 잠근 상태여야 한다. approver 의
    active ADMIN·principal version 도 여기서 ``FOR UPDATE`` 로 재확인한다.
    """
    if row is None:
        raise ApprovalConsumeError("approval token does not match any request (unknown/replayed).")
    if row.state != "APPROVED":
        raise ApprovalConsumeError(f"approval is not in APPROVED state (state={row.state}).")
    if row.expires_at is None or row.expires_at <= now:
        raise ApprovalConsumeError("approval has expired.")
    if row.operation_type != operation_id:
        raise ApprovalConsumeError("operation mismatch.")
    if row.scope_sha256 != scope_sha256:
        raise ApprovalConsumeError("scope hash mismatch.")
    if (row.artifact_sha256 or None) != (artifact_sha256 or None):
        raise ApprovalConsumeError("artifact hash mismatch.")
    if row.expected_version != expected_version:
        raise ApprovalConsumeError("expected_version mismatch.")
    if row.expected_generation != expected_generation:
        raise ApprovalConsumeError("expected_generation mismatch.")

    if row.approved_by_user_id is None or row.approved_principal_version is None:
        raise ApprovalConsumeError("approval is missing approver identity/version.")

    approver = (
        session.query(User)
        .filter(User.id == row.approved_by_user_id)
        .with_for_update()
        .one_or_none()
    )
    if approver is None or not approver.is_active or approver.role != "ADMIN":
        raise ApprovalConsumeError("approver is not an active ADMIN.")

    pv = (
        session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == row.approved_by_user_id)
        .with_for_update()
        .one_or_none()
    )
    if pv is None or pv.version != row.approved_principal_version:
        raise ApprovalConsumeError("approver principal version changed since approval.")


def approve_request(
    session: Session,
    *,
    approval_id: str,
    approver_user_id: int,
    now: Optional[datetime.datetime] = None,
) -> OpsApprovalRequest:
    """PENDING → APPROVED 전이의 SSOT(재인증은 호출자/웹 라우트 책임).

    approval row 를 ``FOR UPDATE`` 로 잠그고 PENDING·미만료 재확인, approver 가 active
    ADMIN 인지, principal version 이 존재하는지 확인한 뒤 approver identity 와 그 시점
    principal version 을 snapshot 한다. approver identity 는 인자(세션에서 온 id)로만
    받는다 — 입력 승인 아님.

    :returns: 갱신된 row(미commit; 호출자가 commit).
    :raises ApprovalConsumeError: 부재/비 PENDING/만료/비 ADMIN/principal 부재.
    """
    now = now or _utcnow()
    row = (
        session.query(OpsApprovalRequest)
        .filter(OpsApprovalRequest.id == approval_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise ApprovalConsumeError("approval request not found.")
    if row.state != "PENDING":
        raise ApprovalConsumeError(f"approval is not PENDING (state={row.state}).")
    if row.expires_at is None or row.expires_at <= now:
        raise ApprovalConsumeError("approval has expired.")

    approver = (
        session.query(User)
        .filter(User.id == approver_user_id)
        .with_for_update()
        .one_or_none()
    )
    if approver is None or not approver.is_active or approver.role != "ADMIN":
        raise ApprovalConsumeError("approver is not an active ADMIN.")

    pv = (
        session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == approver_user_id)
        .with_for_update()
        .one_or_none()
    )
    if pv is None:
        raise ApprovalConsumeError("approver has no principal version row.")

    row.state = "APPROVED"
    row.approved_by_user_id = approver_user_id
    row.approved_principal_version = pv.version
    row.approved_at = now
    row.row_version = (row.row_version or 1) + 1
    session.flush()
    return row


def _lock_by_nonce(session: Session, nonce_hash: str) -> Optional[OpsApprovalRequest]:
    """nonce_hash 로 approval row 를 ``FOR UPDATE`` 잠금 조회."""
    return (
        session.query(OpsApprovalRequest)
        .filter(OpsApprovalRequest.nonce_hash == nonce_hash)
        .with_for_update()
        .one_or_none()
    )


def consume_same_db(
    session: Session,
    *,
    operation_id: str,
    scope_obj: dict[str, Any],
    artifact_sha256: Optional[str],
    expected_version: Optional[int],
    expected_generation: Optional[int],
    raw_secret: bytes,
    target_mutation: Callable[[Session], bytes],
    now: Optional[datetime.datetime] = None,
) -> str:
    """same-DB one-time consume. 검증→target mutation→CONSUMED 를 한 tx(미commit).

    호출자가 session 의 transaction 을 commit 한다(원자성). 검증 실패는 예외를 던지고
    이때 target mutation 은 실행되지 않았으므로 rollback 시 mutation 0 이다.

    :returns: ``result_sha256`` (target mutation 결과 bytes 의 sha256 hex).
    :raises ApprovalConsumeError: 승인 조건 위반(만료/비 ADMIN/version 변경/재소비/
        operation·scope·artifact·version·generation 불일치).
    """
    now = now or _utcnow()
    scope_sha256 = compute_scope_sha256(scope_obj)
    nonce_hash = nonce_hash_from_secret(raw_secret)

    row = _lock_by_nonce(session, nonce_hash)
    _verify_approved_row(
        session,
        row=row,
        operation_id=operation_id,
        scope_sha256=scope_sha256,
        artifact_sha256=artifact_sha256,
        expected_version=expected_version,
        expected_generation=expected_generation,
        now=now,
    )
    assert row is not None  # _verify_approved_row raises otherwise

    result = target_mutation(session)
    if not isinstance(result, (bytes, bytearray)):
        raise ApprovalConsumeError("target_mutation must return bytes (its canonical result).")
    result_sha256 = _sha256_hex(bytes(result))

    row.state = "CONSUMED"
    row.consumed_at = now
    row.result_sha256 = result_sha256
    row.row_version = (row.row_version or 1) + 1
    session.flush()
    return result_sha256


def reserve_primary(
    session: Session,
    *,
    operation_id: str,
    scope_obj: dict[str, Any],
    artifact_sha256: Optional[str],
    expected_version: Optional[int],
    expected_generation: Optional[int],
    raw_secret: bytes,
    reservation_ttl_seconds: int = RESERVATION_TTL_SECONDS,
    now: Optional[datetime.datetime] = None,
) -> str:
    """cross-DB 1단계: primary 검증 후 RESERVED snapshot 을 만든다(미commit).

    RESERVED 는 취소 불가 authorization snapshot 이다 — 호출자가 commit 하면 이후
    approver 의 role/version 변경은 **신규** reservation 만 막고 이 snapshot 은 유지된다.

    :returns: 새 ``reservation_id`` (UUID str).
    :raises ApprovalConsumeError: APPROVED 아님/만료/비 ADMIN/version 변경/불일치.
    """
    now = now or _utcnow()
    scope_sha256 = compute_scope_sha256(scope_obj)
    nonce_hash = nonce_hash_from_secret(raw_secret)

    row = _lock_by_nonce(session, nonce_hash)
    _verify_approved_row(
        session,
        row=row,
        operation_id=operation_id,
        scope_sha256=scope_sha256,
        artifact_sha256=artifact_sha256,
        expected_version=expected_version,
        expected_generation=expected_generation,
        now=now,
    )
    assert row is not None

    reservation_id = str(uuid.uuid4())
    row.state = "RESERVED"
    row.reservation_id = reservation_id
    row.reserved_at = now
    row.reservation_expires_at = now + datetime.timedelta(seconds=reservation_ttl_seconds)
    row.row_version = (row.row_version or 1) + 1
    session.flush()
    return reservation_id


def commit_target(
    target_session: Session,
    *,
    approval_id: str,
    reservation_id: str,
    operation_id: str,
    scope_sha256: str,
    target_mutation: Callable[[Session], bytes],
    now: Optional[datetime.datetime] = None,
) -> str:
    """cross-DB 2단계: target DB 에 unique audit + mutation 을 한 tx 로 commit(미commit).

    crash retry(같은 approval/reservation/scope)면 target audit 가 이미 있으므로 기존
    result hash 를 반환하고 mutation 을 재실행하지 않는다(idempotent).

    :returns: ``result_sha256``.
    """
    now = now or _utcnow()
    op_scope = compute_operation_scope_sha256(operation_id, scope_sha256)

    existing = (
        target_session.query(OpsApprovalTargetAudit)
        .filter(
            OpsApprovalTargetAudit.approval_id == approval_id,
            OpsApprovalTargetAudit.reservation_id == reservation_id,
            OpsApprovalTargetAudit.operation_scope_sha256 == op_scope,
        )
        .one_or_none()
    )
    if existing is not None:
        # crash retry: 이미 적용됨 — 재mutation 금지, 기존 result 반환.
        return existing.result_sha256 or ""

    result = target_mutation(target_session)
    if not isinstance(result, (bytes, bytearray)):
        raise ApprovalConsumeError("target_mutation must return bytes.")
    result_sha256 = _sha256_hex(bytes(result))

    target_session.add(
        OpsApprovalTargetAudit(
            approval_id=approval_id,
            reservation_id=reservation_id,
            operation_scope_sha256=op_scope,
            operation_id=operation_id,
            result_sha256=result_sha256,
            committed_at=now,
        )
    )
    target_session.flush()
    return result_sha256


def finalize_primary(
    session: Session,
    *,
    approval_id: str,
    result_sha256: str,
    now: Optional[datetime.datetime] = None,
) -> None:
    """cross-DB 3단계: primary reservation 을 CONSUMED 로 finalize(미commit, idempotent).

    RESERVED → CONSUMED. 이미 CONSUMED 면 no-op(crash-safe). RESERVED 를 취소하지
    않는다 — approver 의 사후 version 변경과 무관하게 finalize 한다.
    """
    now = now or _utcnow()
    row = (
        session.query(OpsApprovalRequest)
        .filter(OpsApprovalRequest.id == approval_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise ApprovalConsumeError("approval row not found for finalize.")
    if row.state == "CONSUMED":
        return  # idempotent
    if row.state != "RESERVED":
        raise ApprovalConsumeError(f"cannot finalize from state {row.state}.")
    row.state = "CONSUMED"
    row.consumed_at = now
    row.result_sha256 = result_sha256
    row.row_version = (row.row_version or 1) + 1
    session.flush()


def reconcile_reservations(
    primary_session: Session,
    target_session: Session,
    *,
    now: Optional[datetime.datetime] = None,
) -> dict[str, list[str]]:
    """양쪽 read-only 대조로 RESERVED 를 finalize 하거나 EXPIRED/alert 처리(미commit).

    * target audit 이 있으면 → primary finalize CONSUMED (RESERVED 를 rollback 하지
      않음).
    * reservation_expires_at 지났고 target audit 이 없으면 → EXPIRED (target commit 0).
    * 그 외(만료 전 미완료)는 pending 으로 보고만 한다.

    임의 rollback 은 하지 않는다(취소 불가 snapshot).

    :returns: ``{"finalized": [...], "expired": [...], "pending": [...]}`` (approval id).
    """
    now = now or _utcnow()
    out: dict[str, list[str]] = {"finalized": [], "expired": [], "pending": []}

    reserved = (
        primary_session.query(OpsApprovalRequest)
        .filter(OpsApprovalRequest.state == "RESERVED")
        .with_for_update()
        .all()
    )
    for row in reserved:
        audit = (
            target_session.query(OpsApprovalTargetAudit)
            .filter(
                OpsApprovalTargetAudit.approval_id == row.id,
                OpsApprovalTargetAudit.reservation_id == row.reservation_id,
            )
            .one_or_none()
        )
        if audit is not None:
            finalize_primary(
                primary_session,
                approval_id=row.id,
                result_sha256=audit.result_sha256 or "",
                now=now,
            )
            out["finalized"].append(str(row.id))
        elif row.reservation_expires_at is not None and row.reservation_expires_at <= now:
            row.state = "EXPIRED"
            row.row_version = (row.row_version or 1) + 1
            out["expired"].append(str(row.id))
        else:
            out["pending"].append(str(row.id))
    primary_session.flush()
    return out
