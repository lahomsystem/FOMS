"""auth-rate key 상태기계 전이 (AUTH-ACCOUNT-01, SESSION-SIGNING-STATE-00 동형).

5 개 OPS-APPROVAL operation 의 상태 전이를 제공한다:

* ``AUTH_RATE_BOOTSTRAP_PREPARE``  — EMPTY → READY (첫 pending key stage).
* ``AUTH_RATE_BOOTSTRAP_ACTIVATE`` — READY → ACTIVE (pending → active, 첫 키 활성).
* ``AUTH_RATE_ROTATION_PREPARE``   — ACTIVE → ROTATION_READY (다음 generation pending).
* ``AUTH_RATE_ROTATION_ACTIVATE``  — ROTATION_READY → ROTATING (previous=구 active,
  active=새 키, ``previous_not_after`` grace 동안 dual accept).
* ``AUTH_RATE_ROTATION_FINALIZE``  — ROTATING → ACTIVE (grace 경과 후 구 키 폐기).

각 전이는 singleton(id=1)을 ``FOR UPDATE`` 로 잠그고 ``version`` 낙관 검증 후 요청 mode
에서만 전이한다. 잘못된 mode 는 :class:`AuthRateStateError` 로 STOP(non-state-aware
rollback 방지). ``version`` 은 매 전이 증가(scope expected_version + concurrency guard),
``generation`` 은 각 prepare 에서 증가(key 세대·scope expected_generation).

OPS-APPROVAL 토큰 소비는 signing 과 동일하게 ``ops_approval.consume_same_db`` 가 담당한다
— 이 모듈은 approval 인프라를 재구현하지 않고 순수 상태 전이(mutation)만 제공하며, 호출자
(CLI/consume 래퍼)가 approval 검증과 한 tx 로 묶어 commit 한다. key material 은 암호화된
envelope(JSON text)로만 받아 저장하고 raw 는 다루지 않는다(fingerprint 만 기록).
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import AuthRateKeyState

PACKET_ID = "AUTH-ACCOUNT-01"
# singleton 은 family 개념이 없으므로 scope 의 target 은 고정 literal.
SCOPE_TARGET = "AUTH_RATE_KEY_STATE"

MODES = ("EMPTY", "READY", "ACTIVE", "ROTATION_READY", "ROTATING")


class AuthRateStateError(RuntimeError):
    """전이 전 조건/mode/version 위반(호출자는 mutation 0 으로 처리)."""


def build_scope(
    operation_id: str, phase: str, artifact_sha256: str,
    expected_version: int, expected_generation: int,
) -> "dict[str, Any]":
    """OPS-APPROVAL scope object(exact fields) — signing build_scope 와 동형.

    scope source = encrypted key artifact sha + state version/generation.
    singleton 이므로 ``target_ids_or_family`` 는 고정 literal.
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


def load_singleton_for_update(session: Session) -> AuthRateKeyState:
    """auth-rate state singleton(id=1)을 ``FOR UPDATE`` 로 잠가 반환.

    :raises AuthRateStateError: singleton 행 부재(미seed).
    """
    row = (
        session.query(AuthRateKeyState)
        .filter(AuthRateKeyState.id == 1)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise AuthRateStateError("auth_rate_key_state singleton (id=1) is missing (unseeded).")
    return row


def read_state(session: Session) -> AuthRateKeyState:
    """singleton 을 잠금 없이 읽는다(operator 가 expected version/generation 확인용)."""
    row = session.query(AuthRateKeyState).filter(AuthRateKeyState.id == 1).one_or_none()
    if row is None:
        raise AuthRateStateError("auth_rate_key_state singleton (id=1) is missing (unseeded).")
    return row


def _check_version(row: AuthRateKeyState, expected_version: int) -> None:
    if row.version != expected_version:
        raise AuthRateStateError(
            f"state version {row.version} != expected {expected_version} (concurrent change)."
        )


def _bump(row: AuthRateKeyState, now: Any, updated_by_admin_user_id: Optional[int]) -> None:
    """매 전이 공통: version++·updated_at/by."""
    row.version = (row.version or 1) + 1
    row.updated_at = now
    row.updated_by_admin_user_id = updated_by_admin_user_id


def _validate_envelope(pending_key_ciphertext: str, pending_key_id: str) -> None:
    """pending ciphertext 가 JSON envelope 이고 key_id 가 일치하는지(raw/오배치 거부)."""
    try:
        env = json.loads(pending_key_ciphertext)
    except (ValueError, TypeError) as exc:
        raise AuthRateStateError("pending_key_ciphertext must be a JSON envelope.") from exc
    if not isinstance(env, dict) or env.get("key_id") != pending_key_id:
        raise AuthRateStateError("pending_key_ciphertext envelope key_id must match pending_key_id.")


def _canonical(operation_id: str, row: AuthRateKeyState) -> bytes:
    """approval result_sha256 용 canonical 결과 bytes(fingerprint 만; raw 없음)."""
    return json.dumps(
        {
            "operation": operation_id,
            "mode": row.mode,
            "version": row.version,
            "generation": row.generation,
            "active_key_id": row.active_key_id,
            "previous_key_id": row.previous_key_id,
            "pending_key_id": row.pending_key_id,
        },
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


# --------------------------------------------------------------------------- #
# 1. bootstrap prepare — EMPTY → READY
# --------------------------------------------------------------------------- #
def bootstrap_prepare(
    session: Session, *,
    pending_key_id: str,
    pending_key_ciphertext: str,
    prepared_key_artifact_sha256: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """EMPTY→READY: 첫 pending key(암호화 envelope + fingerprint) stage. generation→1."""
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode != "EMPTY":
        raise AuthRateStateError(f"bootstrap prepare requires mode EMPTY (got {row.mode}).")
    if not pending_key_id:
        raise AuthRateStateError("pending_key_id must be non-empty.")
    _validate_envelope(pending_key_ciphertext, pending_key_id)

    row.mode = "READY"
    row.pending_key_id = pending_key_id
    row.pending_key_ciphertext = pending_key_ciphertext
    row.prepared_key_artifact_sha256 = prepared_key_artifact_sha256
    row.generation = 1
    row.prepared_at = now
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("AUTH_RATE_BOOTSTRAP_PREPARE", row)


# --------------------------------------------------------------------------- #
# 2. bootstrap activate — READY → ACTIVE
# --------------------------------------------------------------------------- #
def bootstrap_activate(
    session: Session, *,
    prepared_rollout_artifact_sha256: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """READY→ACTIVE: pending 을 active 로 승격(첫 rate key 활성)."""
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode != "READY":
        raise AuthRateStateError(f"bootstrap activate requires mode READY (got {row.mode}).")
    if not row.pending_key_id or not row.pending_key_ciphertext:
        raise AuthRateStateError("READY state has no pending key to activate.")

    row.active_key_id = row.pending_key_id
    row.active_key_ciphertext = row.pending_key_ciphertext
    row.pending_key_id = None
    row.pending_key_ciphertext = None
    row.mode = "ACTIVE"
    row.activated_at = now
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("AUTH_RATE_BOOTSTRAP_ACTIVATE", row)


# --------------------------------------------------------------------------- #
# 3. rotation prepare — ACTIVE → ROTATION_READY
# --------------------------------------------------------------------------- #
def rotation_prepare(
    session: Session, *,
    pending_key_id: str,
    pending_key_ciphertext: str,
    prepared_key_artifact_sha256: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """ACTIVE→ROTATION_READY: 새 pending key(다음 generation) stage. generation++."""
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode != "ACTIVE":
        raise AuthRateStateError(f"rotation prepare requires mode ACTIVE (got {row.mode}).")
    if row.previous_key_id is not None or row.pending_key_id is not None:
        raise AuthRateStateError("rotation prepare requires empty previous/pending key slots.")
    if not pending_key_id:
        raise AuthRateStateError("pending_key_id must be non-empty.")
    _validate_envelope(pending_key_ciphertext, pending_key_id)

    row.mode = "ROTATION_READY"
    row.pending_key_id = pending_key_id
    row.pending_key_ciphertext = pending_key_ciphertext
    row.prepared_key_artifact_sha256 = prepared_key_artifact_sha256
    row.generation = (row.generation or 0) + 1
    row.prepared_at = now
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("AUTH_RATE_ROTATION_PREPARE", row)


# --------------------------------------------------------------------------- #
# 4. rotation activate — ROTATION_READY → ROTATING (dual accept)
# --------------------------------------------------------------------------- #
def rotation_activate(
    session: Session, *,
    grace_seconds: int,
    prepared_rollout_artifact_sha256: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """ROTATION_READY→ROTATING: previous=구 active, active=새 키, previous_not_after=now+grace.

    grace 동안 previous·active 둘 다 유효(dual accept) — 기존 bucket 을 강제 무효화하지 않고
    신·구 키를 함께 accept 한다.
    """
    now = now or now_utc_naive()
    if grace_seconds < 0:
        raise AuthRateStateError("grace_seconds must be non-negative.")
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode != "ROTATION_READY":
        raise AuthRateStateError(f"rotation activate requires ROTATION_READY (got {row.mode}).")
    if not row.pending_key_id or not row.active_key_id:
        raise AuthRateStateError("rotation activate requires both active and pending keys.")

    row.previous_key_id = row.active_key_id
    row.previous_key_ciphertext = row.active_key_ciphertext
    row.active_key_id = row.pending_key_id
    row.active_key_ciphertext = row.pending_key_ciphertext
    row.pending_key_id = None
    row.pending_key_ciphertext = None
    row.previous_not_after = now + timedelta(seconds=int(grace_seconds))
    row.mode = "ROTATING"
    row.activated_at = now
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("AUTH_RATE_ROTATION_ACTIVATE", row)


# --------------------------------------------------------------------------- #
# 5. rotation finalize — ROTATING → ACTIVE (구 키 폐기)
# --------------------------------------------------------------------------- #
def rotation_finalize(
    session: Session, *,
    prepared_rollout_artifact_sha256: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """ROTATING→ACTIVE: previous grace 경과 확인 후 구 키(previous slot) 폐기."""
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode != "ROTATING":
        raise AuthRateStateError(f"rotation finalize requires mode ROTATING (got {row.mode}).")
    if row.previous_not_after is None or row.previous_not_after > now:
        raise AuthRateStateError("rotation finalize requires the previous deadline to have passed.")

    row.previous_key_id = None
    row.previous_key_ciphertext = None
    row.previous_not_after = None
    row.mode = "ACTIVE"
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("AUTH_RATE_ROTATION_FINALIZE", row)
