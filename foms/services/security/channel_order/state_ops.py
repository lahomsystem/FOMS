"""channel key 상태기계 전이 (CHANNEL-INBOUND-ORDER-01, AUTH-ACCOUNT-01 동형).

3 개 OPS-APPROVAL key operation 의 상태 전이를 제공한다(prepare/activate/finalize 가 현재
mode 에 따라 bootstrap 과 rotation 을 겸한다 — auth-rate 의 5 operation 을 3 으로 접었다):

* ``CHANNEL_KEY_ROTATION_PREPARE``  — EMPTY→READY(첫 키) 또는 ACTIVE→ROTATION_READY(다음
  generation pending). generation 증가.
* ``CHANNEL_KEY_ROTATION_ACTIVATE`` — READY→ACTIVE(첫 키 활성) 또는 ROTATION_READY→ROTATING
  (previous=구 active, active=새 키, ``previous_not_after`` grace 동안 dual accept).
* ``CHANNEL_KEY_ROTATION_FINALIZE`` — ROTATING→ACTIVE. grace 경과 **및 old-reference 0**
  (구 key 를 참조하는 봉인 secret 이 남아 있으면 거부 — rewrap 선행 강제)이어야 구 key 폐기.

각 전이는 singleton(id=1)을 ``FOR UPDATE`` 로 잠그고 ``version`` 낙관 검증 후 요청 mode 에서만
전이한다. OPS-APPROVAL 토큰 소비는 ``ops_approval.consume_same_db`` 가 담당한다 — 이 모듈은
순수 상태 전이(mutation)만 제공하고 호출자(CLI/consume 래퍼)가 approval 검증과 한 tx 로 묶는다.
key material 은 암호화된 envelope(JSON text)로만 받아 저장하고 raw 는 다루지 않는다.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import ChannelInboundKeyState

PACKET_ID = "CHANNEL-INBOUND-ORDER-01"
SCOPE_TARGET = "CHANNEL_INBOUND_KEY_STATE"

MODES = ("EMPTY", "READY", "ACTIVE", "ROTATION_READY", "ROTATING")


class ChannelKeyStateError(RuntimeError):
    """전이 전 조건/mode/version 위반, 또는 old-reference 잔존(호출자는 mutation 0)."""


def build_scope(
    operation_id: str, phase: str, artifact_sha256: str,
    expected_version: int, expected_generation: int,
) -> "dict[str, Any]":
    """OPS-APPROVAL scope object(exact fields) — auth-rate build_scope 와 동형.

    scope source = encrypted key artifact sha + state version/generation. singleton 이므로
    ``target_ids_or_family`` 는 고정 literal.
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


def load_singleton_for_update(session: Session) -> ChannelInboundKeyState:
    """channel key state singleton(id=1)을 ``FOR UPDATE`` 로 잠가 반환.

    :raises ChannelKeyStateError: singleton 행 부재(미seed).
    """
    row = (
        session.query(ChannelInboundKeyState)
        .filter(ChannelInboundKeyState.id == 1)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise ChannelKeyStateError("channel_inbound_key_state singleton (id=1) is missing.")
    return row


def read_state(session: Session) -> ChannelInboundKeyState:
    """singleton 을 잠금 없이 읽는다(operator 가 expected version/generation 확인용)."""
    row = (
        session.query(ChannelInboundKeyState)
        .filter(ChannelInboundKeyState.id == 1)
        .one_or_none()
    )
    if row is None:
        raise ChannelKeyStateError("channel_inbound_key_state singleton (id=1) is missing.")
    return row


def _check_version(row: ChannelInboundKeyState, expected_version: int) -> None:
    if row.version != expected_version:
        raise ChannelKeyStateError(
            f"state version {row.version} != expected {expected_version} (concurrent change)."
        )


def _bump(row: ChannelInboundKeyState, now: Any, updated_by_admin_user_id: Optional[int]) -> None:
    """매 전이 공통: version++·updated_at/by."""
    row.version = (row.version or 1) + 1
    row.updated_at = now
    row.updated_by_admin_user_id = updated_by_admin_user_id


def _validate_envelope(pending_key_ciphertext: str, pending_key_id: str) -> None:
    """pending ciphertext 가 JSON envelope 이고 key_id 가 일치하는지(raw/오배치 거부)."""
    try:
        env = json.loads(pending_key_ciphertext)
    except (ValueError, TypeError) as exc:
        raise ChannelKeyStateError("pending_key_ciphertext must be a JSON envelope.") from exc
    if not isinstance(env, dict) or env.get("key_id") != pending_key_id:
        raise ChannelKeyStateError(
            "pending_key_ciphertext envelope key_id must match pending_key_id."
        )


def _canonical(operation_id: str, row: ChannelInboundKeyState) -> bytes:
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


def key_rotation_prepare(
    session: Session, *,
    pending_key_id: str,
    pending_key_ciphertext: str,
    prepared_key_artifact_sha256: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """EMPTY→READY(첫 키) 또는 ACTIVE→ROTATION_READY(rotation). generation++·pending stage."""
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode not in ("EMPTY", "ACTIVE"):
        raise ChannelKeyStateError(f"key prepare requires mode EMPTY or ACTIVE (got {row.mode}).")
    if row.previous_key_id is not None or row.pending_key_id is not None:
        raise ChannelKeyStateError("key prepare requires empty previous/pending key slots.")
    if not pending_key_id:
        raise ChannelKeyStateError("pending_key_id must be non-empty.")
    _validate_envelope(pending_key_ciphertext, pending_key_id)

    row.mode = "READY" if row.mode == "EMPTY" else "ROTATION_READY"
    row.pending_key_id = pending_key_id
    row.pending_key_ciphertext = pending_key_ciphertext
    row.prepared_key_artifact_sha256 = prepared_key_artifact_sha256
    row.generation = (row.generation or 0) + 1
    row.prepared_at = now
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("CHANNEL_KEY_ROTATION_PREPARE", row)


def key_rotation_activate(
    session: Session, *,
    grace_seconds: int,
    prepared_rollout_artifact_sha256: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """READY→ACTIVE(첫 키) 또는 ROTATION_READY→ROTATING(dual accept·grace).

    rotation 활성 시 previous=구 active·active=새 키·previous_not_after=now+grace 로 grace 동안
    신·구 키를 함께 accept 한다(기존 봉인 secret 강제 무효화 0).
    """
    now = now or now_utc_naive()
    if grace_seconds < 0:
        raise ChannelKeyStateError("grace_seconds must be non-negative.")
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode not in ("READY", "ROTATION_READY"):
        raise ChannelKeyStateError(
            f"key activate requires mode READY or ROTATION_READY (got {row.mode})."
        )
    if not row.pending_key_id or not row.pending_key_ciphertext:
        raise ChannelKeyStateError("activate requires a pending key to promote.")

    if row.mode == "READY":
        row.active_key_id = row.pending_key_id
        row.active_key_ciphertext = row.pending_key_ciphertext
        row.mode = "ACTIVE"
    else:  # ROTATION_READY → ROTATING (dual accept)
        row.previous_key_id = row.active_key_id
        row.previous_key_ciphertext = row.active_key_ciphertext
        row.active_key_id = row.pending_key_id
        row.active_key_ciphertext = row.pending_key_ciphertext
        row.previous_not_after = now + timedelta(seconds=int(grace_seconds))
        row.mode = "ROTATING"
    row.pending_key_id = None
    row.pending_key_ciphertext = None
    row.activated_at = now
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("CHANNEL_KEY_ROTATION_ACTIVATE", row)


def key_rotation_finalize(
    session: Session, *,
    old_reference_count: int,
    prepared_rollout_artifact_sha256: str,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """ROTATING→ACTIVE: grace 경과 **및 old-reference 0** 확인 후 previous(구 key) 폐기.

    ``old_reference_count`` 는 구 key 로 여전히 봉인돼 있는 secret 수(호출자가
    :func:`key_state.count_previous_key_references` 로 산출). 0 이 아니면 rewrap 미완이므로
    거부한다(**old-reference 0 전 제거 0** — 참조 남은 키 삭제 금지).
    """
    now = now or now_utc_naive()
    row = load_singleton_for_update(session)
    _check_version(row, expected_version)
    if row.mode != "ROTATING":
        raise ChannelKeyStateError(f"key finalize requires mode ROTATING (got {row.mode}).")
    if row.previous_not_after is None or row.previous_not_after > now:
        raise ChannelKeyStateError("key finalize requires the previous grace deadline to pass.")
    if old_reference_count != 0:
        raise ChannelKeyStateError(
            f"key finalize blocked: {old_reference_count} secrets still reference the previous "
            "key (rewrap must complete first — old-reference 0 before removal)."
        )

    row.previous_key_id = None
    row.previous_key_ciphertext = None
    row.previous_not_after = None
    row.mode = "ACTIVE"
    row.prepared_rollout_artifact_sha256 = prepared_rollout_artifact_sha256
    _bump(row, now, updated_by_admin_user_id)
    session.flush()
    return _canonical("CHANNEL_KEY_ROTATION_FINALIZE", row)
