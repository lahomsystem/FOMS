"""signing-state activation 전이 (SESSION-SIGNING-SECRET-01, §2.1 line 231-245).

STATE-00 의 deadline-null prepare 를 이어받아 **실제 activation** 상태 전이를 수행한다.
owner 표의 8 operation(cutover activate / legacy finalize / rotation activate·finalize /
compromise activate / force enter·exit / rescue rollforward)을 담당하며, 각 전이는
singleton(id=1)을 ``FOR UPDATE`` 로 잠그고 ``row_version`` 낙관 검증 후 요청 모드에서만
전이한다. 잘못된 mode 에서의 전이 시도는 예외로 **STOP**(non-state-aware rollback 방지).

OPS-APPROVAL 토큰 소비는 :func:`consume_activation` 이 STATE-00 prepare 와 동일 규약으로
approver identity 를 복사한다(입력 승인 아님). key ID(fingerprint)만 다루고 root/subkey raw
는 절대 저장·로그하지 않는다.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.signing.prepare_ops import (
    SigningPrepareError,
    build_scope,
    consume_prepare_operation,
    load_singleton_for_update,
    read_key_artifact,
    sha256_file,
)
from models import SecuritySigningState

# 재수출(activation CLI 가 prepare_ops 를 직접 알 필요 없게).
build_scope = build_scope
read_key_artifact = read_key_artifact
sha256_file = sha256_file

_LIVE_MODES = ("READY", "ACTIVE", "CURRENT_ONLY", "ROTATION_READY", "ROTATING")


class SigningActivationError(RuntimeError):
    """activation 전 조건/mode 위반(호출자는 mutation 0 으로 처리, non-state-aware rollback STOP)."""


def consume_activation(
    session: Session, *, operation_id: str, control_root, token_path, scope: "dict[str, Any]",
    mutation_builder,
) -> str:
    """OPS-APPROVAL 토큰을 소비하며 approver 를 복사해 activation mutation 을 한 tx 에 적용(미commit).

    STATE-00 prepare 와 동일한 generic consume(approver identity 는 소비된 approval row 에서
    취한다). 호출자가 session 을 commit 한다(원자성).
    """
    return consume_prepare_operation(
        session, operation_id=operation_id, control_root=control_root,
        token_path=token_path, scope=scope, mutation_builder=mutation_builder,
    )


def _lock_checked(session: Session, expected_version: int) -> SecuritySigningState:
    """singleton 을 잠그고 row_version 낙관 검증."""
    row = load_singleton_for_update(session)
    if row.row_version != expected_version:
        raise SigningActivationError(
            f"state row_version {row.row_version} != expected {expected_version} (concurrent change)."
        )
    return row


def _canonical(operation_id: str, row: SecuritySigningState) -> bytes:
    """approval result_sha256 용 canonical 결과 bytes(key ID 만; raw 없음)."""
    return json.dumps(
        {
            "operation": operation_id,
            "mode": row.mode,
            "maintenance_mode": row.maintenance_mode,
            "generation": row.generation,
            "session_epoch": row.session_epoch,
            "active_key_id": row.active_key_id,
            "previous_key_id": row.previous_key_id,
            "pending_key_id": row.pending_key_id,
            "row_version": row.row_version,
        },
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _bump(row: SecuritySigningState, now, updated_by_admin_user_id: Optional[int]) -> None:
    row.updated_at = now
    row.updated_by_admin_user_id = updated_by_admin_user_id
    row.row_version = (row.row_version or 1) + 1


# --------------------------------------------------------------------------- #
# 1. cutover activate — READY → ACTIVE (§2.1 line 231/235)
# --------------------------------------------------------------------------- #
def activate_cutover(
    session: Session, *, mode: str, prepared_rollout_artifact_sha256: str,
    expected_version: int, updated_by_admin_user_id: Optional[int], now: Optional[Any] = None,
) -> bytes:
    """READY→ACTIVE: active=pending, legacy deadline 기록. BRIDGE 는 grace 만큼 legacy verify-only,
    FORCE_REAUTH 는 즉시 cutoff+epoch+1+wam_not_before=now."""
    now = now or now_utc_naive()
    row = _lock_checked(session, expected_version)
    if row.mode != "READY":
        raise SigningActivationError(f"cutover activate requires mode READY (got {row.mode}).")
    want = "BRIDGE" if mode == "bridge" else "FORCE_REAUTH" if mode == "force-reauth" else None
    if want is None:
        raise SigningActivationError("mode must be 'bridge' or 'force-reauth'.")
    if row.legacy_cutover_mode != want:
        raise SigningActivationError(
            f"prepared legacy_cutover_mode {row.legacy_cutover_mode!r} != requested {want!r}."
        )
    if not row.pending_key_id:
        raise SigningActivationError("READY state has no pending key ID to activate.")

    deadline = now + timedelta(seconds=int(row.grace_seconds or 0))
    row.active_key_id = row.pending_key_id
    row.pending_key_id = None
    row.legacy_flask_not_after = deadline
    row.legacy_wam_not_after = deadline
    if want == "FORCE_REAUTH":
        row.session_epoch = (row.session_epoch or 0) + 1
        row.wam_not_before = now
    row.mode = "ACTIVE"
    row.activated_at = now
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("SIGNING_CUTOVER_ACTIVATE", row)


# --------------------------------------------------------------------------- #
# 2. legacy finalize — ACTIVE → CURRENT_ONLY (§2.1 line 243)
# --------------------------------------------------------------------------- #
def finalize_legacy(
    session: Session, *, prepared_rollout_artifact_sha256: str,
    expected_version: int, updated_by_admin_user_id: Optional[int], now: Optional[Any] = None,
) -> bytes:
    """ACTIVE→CURRENT_ONLY: 두 legacy deadline 경과 확인 후 legacy env 제거(deadline null)."""
    now = now or now_utc_naive()
    row = _lock_checked(session, expected_version)
    if row.mode != "ACTIVE":
        raise SigningActivationError(f"legacy finalize requires mode ACTIVE (got {row.mode}).")
    for deadline in (row.legacy_flask_not_after, row.legacy_wam_not_after):
        if deadline is None or deadline > now:
            raise SigningActivationError(
                "legacy finalize requires both legacy deadlines to have passed (grace ended)."
            )
    row.mode = "CURRENT_ONLY"
    row.legacy_flask_not_after = None
    row.legacy_wam_not_after = None
    row.legacy_cutover_mode = None
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("SIGNING_LEGACY_FINALIZE", row)


# --------------------------------------------------------------------------- #
# 3. rotation activate — ROTATION_READY → ROTATING (§2.1 line 243)
# --------------------------------------------------------------------------- #
def activate_rotation(
    session: Session, *, prepared_rollout_artifact_sha256: str,
    expected_version: int, updated_by_admin_user_id: Optional[int], now: Optional[Any] = None,
) -> bytes:
    """ROTATION_READY→ROTATING: previous=old active, active=new(pending), previous deadline=now+grace."""
    now = now or now_utc_naive()
    row = _lock_checked(session, expected_version)
    if row.mode != "ROTATION_READY":
        raise SigningActivationError(f"rotation activate requires ROTATION_READY (got {row.mode}).")
    if not row.pending_key_id or not row.active_key_id:
        raise SigningActivationError("rotation activate requires both active and pending key IDs.")
    row.previous_key_id = row.active_key_id
    row.active_key_id = row.pending_key_id
    row.pending_key_id = None
    row.previous_not_after = now + timedelta(seconds=int(row.grace_seconds or 0))
    row.mode = "ROTATING"
    row.activated_at = now
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("SIGNING_ROTATION_ACTIVATE", row)


# --------------------------------------------------------------------------- #
# 4. rotation finalize — ROTATING → CURRENT_ONLY (§2.1 line 243)
# --------------------------------------------------------------------------- #
def finalize_rotation(
    session: Session, *, prepared_rollout_artifact_sha256: str,
    expected_version: int, updated_by_admin_user_id: Optional[int], now: Optional[Any] = None,
) -> bytes:
    """ROTATING→CURRENT_ONLY: previous deadline 경과 확인 후 previous slot 제거."""
    now = now or now_utc_naive()
    row = _lock_checked(session, expected_version)
    if row.mode != "ROTATING":
        raise SigningActivationError(f"rotation finalize requires mode ROTATING (got {row.mode}).")
    if row.previous_not_after is None or row.previous_not_after > now:
        raise SigningActivationError("rotation finalize requires the previous deadline to have passed.")
    row.previous_key_id = None
    row.previous_not_after = None
    row.mode = "CURRENT_ONLY"
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("SIGNING_ROTATION_FINALIZE", row)


# --------------------------------------------------------------------------- #
# 5. compromise activate — live → CURRENT_ONLY (fresh key, epoch+1, cutoff) (§2.1 line 245)
# --------------------------------------------------------------------------- #
def activate_compromise(
    session: Session, *, prepared_rollout_artifact_sha256: str, quiescence_artifact_sha256: str,
    expected_version: int, updated_by_admin_user_id: Optional[int], now: Optional[Any] = None,
) -> bytes:
    """compromise: active=new(pending), previous/pending null, 모든 legacy/old deadline=now,
    epoch+1, WAM cutoff=now. maintenance 는 유지(exit 는 별도)."""
    now = now or now_utc_naive()
    row = _lock_checked(session, expected_version)
    if row.mode not in ("ACTIVE", "CURRENT_ONLY", "ROTATION_READY", "ROTATING"):
        raise SigningActivationError(
            f"compromise activate requires a live mode with a fresh pending key (got {row.mode})."
        )
    if not row.pending_key_id:
        raise SigningActivationError("compromise activate requires a fresh NEXT pending key ID.")
    if quiescence_artifact_sha256 is None:
        raise SigningActivationError("compromise activate requires a quiescence artifact SHA.")
    row.active_key_id = row.pending_key_id
    row.previous_key_id = None
    row.pending_key_id = None
    row.previous_not_after = None
    row.legacy_flask_not_after = now
    row.legacy_wam_not_after = now
    row.legacy_cutover_mode = None
    row.session_epoch = (row.session_epoch or 0) + 1
    row.wam_not_before = now
    row.mode = "CURRENT_ONLY"
    row.activated_at = now
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("SIGNING_COMPROMISE_ACTIVATE", row)


# --------------------------------------------------------------------------- #
# 6/7. force maintenance enter/exit — maintenance_mode OFF<->AUTH_ONLY (§2.1 line 235)
# --------------------------------------------------------------------------- #
def enter_force_maintenance(
    session: Session, *, rescue_deployment_sha: str,
    expected_version: int, updated_by_admin_user_id: Optional[int], now: Optional[Any] = None,
) -> bytes:
    """maintenance_mode OFF→AUTH_ONLY(공개 auth/session/WAM 503, health/maintenance 페이지만)."""
    now = now or now_utc_naive()
    row = _lock_checked(session, expected_version)
    if row.maintenance_mode != "OFF":
        raise SigningActivationError(
            f"force enter requires maintenance_mode OFF (got {row.maintenance_mode})."
        )
    row.maintenance_mode = "AUTH_ONLY"
    row.maintenance_started_at = now
    row.rescue_deployment_sha = rescue_deployment_sha
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("SIGNING_FORCE_ENTER", row)


def exit_force_maintenance(
    session: Session, *, smoke_artifact_sha256: str,
    expected_version: int, updated_by_admin_user_id: Optional[int], now: Optional[Any] = None,
) -> bytes:
    """maintenance_mode AUTH_ONLY→OFF(current-key smoke green 뒤 정상 업무 복구)."""
    now = now or now_utc_naive()
    row = _lock_checked(session, expected_version)
    if row.maintenance_mode != "AUTH_ONLY":
        raise SigningActivationError(
            f"force exit requires maintenance_mode AUTH_ONLY (got {row.maintenance_mode})."
        )
    if not smoke_artifact_sha256:
        raise SigningActivationError("force exit requires a private current-key smoke artifact SHA.")
    row.maintenance_mode = "OFF"
    row.maintenance_started_at = None
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("SIGNING_FORCE_EXIT", row)


# --------------------------------------------------------------------------- #
# 8. rescue rollforward — failed-smoke roll-forward staging (§2.1 line 237)
# --------------------------------------------------------------------------- #
def rescue_rollforward(
    session: Session, *, rescue_deployment_sha: str, prepared_rollout_artifact_sha256: str,
    expected_version: int, updated_by_admin_user_id: Optional[int], now: Optional[Any] = None,
) -> bytes:
    """failed post-activation smoke 뒤 roll-forward: rescue deployment/rollout 증거만 기록.

    mode 는 바꾸지 않는다(재-activation 은 compromise/cutover activate 로). known/legacy key 나
    old image 로 되돌리지 않는다(roll-forward only).
    """
    now = now or now_utc_naive()
    row = _lock_checked(session, expected_version)
    if row.mode == "EMPTY":
        raise SigningActivationError("rescue rollforward cannot run from EMPTY (nothing to recover).")
    if not rescue_deployment_sha:
        raise SigningActivationError("rescue rollforward requires a rescue deployment SHA.")
    row.rescue_deployment_sha = rescue_deployment_sha
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("SIGNING_RESCUE_ROLLFORWARD", row)
