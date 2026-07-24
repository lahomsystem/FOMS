"""signing-state prepare 전이 + scope/artifact 지원 (SESSION-SIGNING-STATE-00).

3 개 owner operation(``SIGNING_CUTOVER_PREPARE``/``SIGNING_ROTATION_PREPARE``/
``SIGNING_RECOVERY_PREPARE``)의 **준비-only** 상태 전이를 제공한다. 모든 전이는
deadline-null 이며 active=pending·deadline 기록·READY→ACTIVE 같은 **activation 은 하지
않는다**(그건 SESSION-SIGNING-SECRET-01). 각 전이는 singleton(id=1)을 ``FOR UPDATE`` 로
잠그고 ``row_version`` 낙관 검증 후 pending key-ID/artifact hash/expected consumer SHA 등
증거만 기록한다.

OPS-APPROVAL 토큰 소비(``consume_same_db``)는 CLI 가 이 mutation 을 ``target_mutation``
으로 넘겨 한 tx 에 commit 한다. 여기서는 approval 인프라를 재구현하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import OpsApprovalRequest, SecuritySigningState
from foms.services.security.ops_approval import (
    consume_same_db,
    nonce_hash_from_secret,
    read_secret_from_token_file,
)

PACKET_ID = "SESSION-SIGNING-STATE-00"
# singleton 은 family 개념이 없으므로 scope 의 target 은 고정 literal.
SCOPE_TARGET = "SESSION_SIGNING_STATE"

_LEGACY_MODES = ("BRIDGE", "FORCE_REAUTH")


class SigningPrepareError(RuntimeError):
    """prepare 전 조건 위반(호출자는 mutation 0 으로 처리)."""


def sha256_file(path: "str | Path") -> str:
    """artifact 파일의 sha256 hex(스트리밍)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_scope(
    operation_id: str, phase: str, artifact_sha256: str,
    expected_version: int, expected_generation: int,
) -> "dict[str, Any]":
    """approval scope object(RFC 8785 JCS exact fields)를 구성.

    owner 표(§2.1 line 215) scope source = key-ID artifact + consumer SHA + state
    version/generation. singleton 이므로 ``target_ids_or_family`` 는 고정 literal.
    """
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "packet_id": PACKET_ID,
        "target_ids_or_family": SCOPE_TARGET,
        "phase": phase,
        "artifact_sha256": artifact_sha256,
        "expected_version": expected_version,
        "expected_generation": expected_generation,
    }


# inspect artifact(key-ID/encoding only)의 필수 필드 — raw/subkey 는 존재해선 안 된다.
_ARTIFACT_REQUIRED = ("schema_version", "slot", "key_id", "encoding", "byte_length")
_ARTIFACT_FORBIDDEN = ("root", "root_b64url", "secret", "raw", "subkey", "derived", "derived_hex")


def read_key_artifact(path: "str | Path") -> "dict[str, Any]":
    """inspect artifact(key-ID/encoding only)를 로드/검증.

    :raises SigningPrepareError: 필수 필드 누락 또는 secret/raw 필드 혼입.
    """
    with open(path, encoding="utf-8") as fh:
        art = json.load(fh)
    if not isinstance(art, dict):
        raise SigningPrepareError("key artifact must be a JSON object.")
    missing = [k for k in _ARTIFACT_REQUIRED if k not in art]
    if missing:
        raise SigningPrepareError(f"key artifact missing fields: {missing}.")
    leaked = [k for k in _ARTIFACT_FORBIDDEN if k in art]
    if leaked:
        raise SigningPrepareError(f"key artifact must not carry secret material: {leaked}.")
    if not isinstance(art["key_id"], str) or not art["key_id"]:
        raise SigningPrepareError("key artifact key_id must be a non-empty string.")
    return art


def consume_prepare_operation(
    session: Session, *,
    operation_id: str,
    control_root: Path,
    token_path: "str | Path",
    scope: "dict[str, Any]",
    mutation_builder: Callable[[Session, Optional[int]], bytes],
) -> str:
    """approval 토큰을 소비하며 approver 를 조회해 prepare mutation 을 한 tx 에 적용(미commit).

    ``updated_by_admin_user_id`` 는 CLI 입력이 아니라 소비된 approval row 의
    ``approved_by_user_id`` 에서 취한다(cutover marker 의 approver 복사와 동일 규약).
    호출자가 session 을 commit 한다(원자성).

    :param mutation_builder: ``(session, approved_by_admin_user_id) -> bytes`` — 실제 전이.
    :returns: consume 의 result_sha256.
    """
    raw_secret = read_secret_from_token_file(
        token_path, control_root, expected_operation_id=operation_id
    )
    nonce = nonce_hash_from_secret(raw_secret)

    def _mut(s: Session) -> bytes:
        approval = s.query(OpsApprovalRequest).filter_by(nonce_hash=nonce).one()
        return mutation_builder(s, approval.approved_by_user_id)

    return consume_same_db(
        session,
        operation_id=operation_id,
        scope_obj=scope,
        artifact_sha256=scope["artifact_sha256"],
        expected_version=scope["expected_version"],
        expected_generation=scope["expected_generation"],
        raw_secret=raw_secret,
        target_mutation=_mut,
    )


def load_singleton_for_update(session: Session) -> SecuritySigningState:
    """signing state singleton(id=1)을 ``FOR UPDATE`` 로 잠가 반환.

    :raises SigningPrepareError: singleton 행 부재(미seed).
    """
    row = (
        session.query(SecuritySigningState)
        .filter(SecuritySigningState.id == 1)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise SigningPrepareError("security_signing_state singleton (id=1) is missing (unseeded).")
    return row


def read_state(session: Session) -> SecuritySigningState:
    """singleton 을 잠금 없이 읽는다(operator 가 expected version/generation 확인용)."""
    row = session.query(SecuritySigningState).filter(SecuritySigningState.id == 1).one_or_none()
    if row is None:
        raise SigningPrepareError("security_signing_state singleton (id=1) is missing (unseeded).")
    return row


def _assert_no_deadlines(row: SecuritySigningState) -> None:
    """prepare 는 deadline 을 절대 기록하지 않는다 — 이미 설정돼 있으면 준비 대상이 아님."""
    if (row.legacy_flask_not_after is not None or row.legacy_wam_not_after is not None
            or row.previous_not_after is not None or row.activated_at is not None):
        raise SigningPrepareError(
            "state already carries deadlines/activation; prepare only runs on a clean pre-activation row."
        )


def _canonical_result(operation_id: str, row: SecuritySigningState) -> bytes:
    """approval result_sha256 용 canonical 결과 bytes(key ID 만; raw 없음)."""
    return json.dumps(
        {
            "operation": operation_id,
            "mode": row.mode,
            "generation": row.generation,
            "pending_key_id": row.pending_key_id,
            "legacy_cutover_mode": row.legacy_cutover_mode,
            "grace_seconds": row.grace_seconds,
            "row_version": row.row_version,
        },
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _check_version(row: SecuritySigningState, expected_version: int) -> None:
    if row.row_version != expected_version:
        raise SigningPrepareError(
            f"state row_version {row.row_version} != expected {expected_version} (concurrent change)."
        )


def prepare_cutover(
    session: Session, *,
    pending_key_id: str,
    prepared_key_artifact_sha256: str,
    legacy_cutover_mode: str,
    grace_seconds: int,
    prepared_consumer_sha: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """EMPTY→READY 준비: pending key ID/artifact/global mode/grace/consumer SHA 기록.

    deadline·active 는 기록하지 않는다(READY bridge 는 여전히 legacy raw 로만 sign/verify).
    """
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode != "EMPTY":
        raise SigningPrepareError(f"cutover prepare requires mode EMPTY (got {row.mode}).")
    _assert_no_deadlines(row)
    if legacy_cutover_mode not in _LEGACY_MODES:
        raise SigningPrepareError(f"legacy_cutover_mode must be one of {_LEGACY_MODES}.")
    if legacy_cutover_mode == "FORCE_REAUTH" and grace_seconds != 0:
        raise SigningPrepareError("FORCE_REAUTH requires grace_seconds == 0.")
    if grace_seconds < 0:
        raise SigningPrepareError("grace_seconds must be non-negative.")
    if not pending_key_id:
        raise SigningPrepareError("pending_key_id must be non-empty.")

    row.mode = "READY"
    row.pending_key_id = pending_key_id
    row.prepared_key_artifact_sha256 = prepared_key_artifact_sha256
    row.legacy_cutover_mode = legacy_cutover_mode
    row.grace_seconds = grace_seconds
    row.prepared_consumer_sha = prepared_consumer_sha
    row.prepared_at = now
    row.updated_at = now
    row.updated_by_admin_user_id = updated_by_admin_user_id
    row.row_version = (row.row_version or 1) + 1
    session.flush()
    return _canonical_result("SIGNING_CUTOVER_PREPARE", row)


def prepare_rotation(
    session: Session, *,
    pending_key_id: str,
    prepared_key_artifact_sha256: str,
    prepared_consumer_sha: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """CURRENT_ONLY→ROTATION_READY 준비: pending(NEXT) key ID 기록 + generation+1.

    previous/pending slot 이 비어 있어야 한다(정상 rotation 진입 조건).
    """
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode != "CURRENT_ONLY":
        raise SigningPrepareError(f"rotation prepare requires mode CURRENT_ONLY (got {row.mode}).")
    if row.previous_key_id is not None or row.pending_key_id is not None:
        raise SigningPrepareError("rotation prepare requires empty previous/pending key slots.")
    if not pending_key_id:
        raise SigningPrepareError("pending_key_id must be non-empty.")

    row.mode = "ROTATION_READY"
    row.pending_key_id = pending_key_id
    row.prepared_key_artifact_sha256 = prepared_key_artifact_sha256
    row.prepared_consumer_sha = prepared_consumer_sha
    row.generation = (row.generation or 0) + 1
    row.prepared_at = now
    row.updated_at = now
    row.updated_by_admin_user_id = updated_by_admin_user_id
    row.row_version = (row.row_version or 1) + 1
    session.flush()
    return _canonical_result("SIGNING_ROTATION_PREPARE", row)


def prepare_recovery(
    session: Session, *,
    pending_key_id: str,
    prepared_key_artifact_sha256: str,
    rescue_deployment_sha: str,
    prepared_consumer_sha: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """emergency recovery 준비: fresh NEXT rescue key 자료를 stage(mode 불변).

    compromise 는 어느 live 상태에서든 일어날 수 있으므로 EMPTY 를 제외한 mode 에서 실행
    가능하다. pending(NEXT) key ID·artifact·rescue deployment SHA 만 기록하고 mode 전이·
    activation 은 하지 않는다(SESSION-SIGNING-SECRET-01 의 activate_compromised_* 몫).

    ponytail: recovery 는 mode 를 바꾸지 않는 stage-only 준비다 — 정확한 activation 상태기계
              (active=new/deadlines=now/epoch+1)는 SECRET-01 이 소유한다.
    """
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode == "EMPTY":
        raise SigningPrepareError("recovery prepare cannot run from EMPTY (nothing to recover).")
    if not pending_key_id:
        raise SigningPrepareError("pending_key_id must be non-empty.")

    row.pending_key_id = pending_key_id
    row.prepared_key_artifact_sha256 = prepared_key_artifact_sha256
    row.rescue_deployment_sha = rescue_deployment_sha
    row.prepared_consumer_sha = prepared_consumer_sha
    row.prepared_at = now
    row.updated_at = now
    row.updated_by_admin_user_id = updated_by_admin_user_id
    row.row_version = (row.row_version or 1) + 1
    session.flush()
    return _canonical_result("SIGNING_RECOVERY_PREPARE", row)
