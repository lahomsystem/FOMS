"""fence/marker 상태 전이 연산 (§8.2 line 1518-1522).

begin_drain / abort_drain / mark_cutover 의 **순수 DB 연산**. 호출자(CLI)가 이를
``ops_approval.consume_same_db`` 의 ``target_mutation`` 으로 감싸 approval 소비와 한
transaction 에 commit 하거나, PG 테스트가 직접 호출한다. 각 연산은:

* fence 를 ``FOR UPDATE`` 로 잠가 in-flight business tx(``FOR KEY SHARE`` 보유자)를
  drain 한 뒤 상태를 전이하고,
* optimistic ``row_version`` 을 재확인하며,
* consume 계약대로 canonical result **bytes** 를 반환한다(미commit — 호출자 commit).

marker 는 최초 1회만 insert 한다(update/delete 는 DB trigger 가 거부). 실제 business
mutation 적용은 각 family packet 몫이며 여기서는 fence/marker 만 다룬다.
"""
from __future__ import annotations

import datetime
import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from foms.services.security.cutover.families import FEATURE_CUTOVER_FAMILIES, is_drain_family
from foms.services.datetime_kst import now_utc_naive


class CutoverMarkError(RuntimeError):
    """fence/marker 전이 전제(family/mode/row_version/marker)가 위반될 때(변화 0)."""


def _assert_family(family: str) -> None:
    if family not in FEATURE_CUTOVER_FAMILIES:
        raise CutoverMarkError(f"unknown family {family!r} (not one of the 15 cutover families).")


def _lock_fence_for_update(session: Session, family: str):
    """fence 를 ``FOR UPDATE`` 로 잠가 in-flight business tx 를 drain(부재면 예외)."""
    row = session.execute(
        text(
            "SELECT mode, generation, row_version "
            "FROM feature_cutover_fences WHERE family = :family "
            "FOR UPDATE"
        ),
        {"family": family},
    ).first()
    if row is None:
        raise CutoverMarkError(f"feature_cutover_fences has no row for family {family!r}.")
    return row


def _marker_exists(session: Session, family: str) -> bool:
    return session.execute(
        text("SELECT 1 FROM feature_cutover_markers WHERE family = :family"),
        {"family": family},
    ).first() is not None


def _canonical(payload: dict) -> bytes:
    """연산 결과를 결정적 JSON bytes 로 직렬화(consume result_sha256 용)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def begin_drain(
    session: Session, family: str, expected_version: int, *,
    now: Optional[datetime.datetime] = None,
) -> bytes:
    """DRAIN family fence 를 ``OPEN→DRAINING`` 전이(FOR UPDATE drain, 미commit).

    :raises CutoverMarkError: 비 DRAIN family, marker 존재, mode!=OPEN, row_version 불일치.
    """
    _assert_family(family)
    if not is_drain_family(family):
        raise CutoverMarkError(f"family {family!r} is not a DRAIN family (begin_drain not applicable).")
    now = now or now_utc_naive()
    fence = _lock_fence_for_update(session, family)
    if _marker_exists(session, family):
        raise CutoverMarkError(f"family {family!r} already has a cutover marker (irreversible).")
    if fence[0] != "OPEN":
        raise CutoverMarkError(f"family {family!r} fence mode must be OPEN to begin drain (got {fence[0]!r}).")
    if fence[2] != expected_version:
        raise CutoverMarkError(f"fence row_version mismatch (expected {expected_version}, got {fence[2]}).")

    new_version = fence[2] + 1
    session.execute(
        text(
            "UPDATE feature_cutover_fences "
            "SET mode='DRAINING', row_version=:nv, updated_at=:now WHERE family=:family"
        ),
        {"nv": new_version, "now": now, "family": family},
    )
    return _canonical({"op": "begin_drain", "family": family, "mode": "DRAINING", "row_version": new_version})


def abort_drain(
    session: Session, family: str, expected_version: int, *,
    now: Optional[datetime.datetime] = None,
) -> bytes:
    """DRAINING fence 를 ``DRAINING→OPEN`` 복구(marker0 검증, 미commit).

    :raises CutoverMarkError: marker 존재, mode!=DRAINING, row_version 불일치.
    """
    _assert_family(family)
    now = now or now_utc_naive()
    fence = _lock_fence_for_update(session, family)
    if _marker_exists(session, family):
        raise CutoverMarkError(f"family {family!r} has a cutover marker; cannot abort after cutover.")
    if fence[0] != "DRAINING":
        raise CutoverMarkError(f"family {family!r} fence mode must be DRAINING to abort (got {fence[0]!r}).")
    if fence[2] != expected_version:
        raise CutoverMarkError(f"fence row_version mismatch (expected {expected_version}, got {fence[2]}).")

    new_version = fence[2] + 1
    session.execute(
        text(
            "UPDATE feature_cutover_fences "
            "SET mode='OPEN', row_version=:nv, updated_at=:now WHERE family=:family"
        ),
        {"nv": new_version, "now": now, "family": family},
    )
    return _canonical({"op": "abort_drain", "family": family, "mode": "OPEN", "row_version": new_version})


def mark_cutover(
    session: Session, family: str, expected_version: int, *,
    cutover_sha: str,
    cutover_generation: int,
    minimum_compatibility_generation: int,
    readiness_artifact_sha256: str,
    ops_approval_id: str,
    approved_by_admin_user_id: int,
    now: Optional[datetime.datetime] = None,
) -> bytes:
    """fence 를 drain 한 뒤 marker insert + ``fence→CUTOVER`` 를 한 tx 에 수행(미commit).

    COMPATIBLE family 는 fence mode OPEN 에서, DRAIN family 는 DRAINING 에서만 mark 한다.
    marker 는 최초 1회만 insert 하며 ``approved_by_admin_user_id`` 는 호출자가 소비된
    approval row 에서 복사해 전달한다(CLI 입력 아님).

    :raises CutoverMarkError: 잘못된 fence mode, 기존 marker, row_version 불일치.
    """
    _assert_family(family)
    now = now or now_utc_naive()
    fence = _lock_fence_for_update(session, family)
    if _marker_exists(session, family):
        raise CutoverMarkError(f"family {family!r} already marked (marker is irreversible; no re-mark).")

    required_mode = "DRAINING" if is_drain_family(family) else "OPEN"
    if fence[0] != required_mode:
        raise CutoverMarkError(
            f"family {family!r} ({'DRAIN' if is_drain_family(family) else 'COMPATIBLE'}) "
            f"fence mode must be {required_mode} to mark (got {fence[0]!r})."
        )
    if fence[2] != expected_version:
        raise CutoverMarkError(f"fence row_version mismatch (expected {expected_version}, got {fence[2]}).")

    session.execute(
        text(
            "INSERT INTO feature_cutover_markers "
            "(family, cutover_at, cutover_sha, cutover_generation, "
            " minimum_compatibility_generation, readiness_artifact_sha256, "
            " ops_approval_id, approved_by_admin_user_id, row_version, created_at) "
            "VALUES (:family, :now, :sha, :gen, :min_gen, :art, :aid, :admin, 1, :now)"
        ),
        {
            "family": family, "now": now, "sha": cutover_sha, "gen": cutover_generation,
            "min_gen": minimum_compatibility_generation, "art": readiness_artifact_sha256,
            "aid": ops_approval_id, "admin": approved_by_admin_user_id,
        },
    )
    new_version = fence[2] + 1
    session.execute(
        text(
            "UPDATE feature_cutover_fences "
            "SET mode='CUTOVER', generation=:gen, row_version=:nv, updated_at=:now "
            "WHERE family=:family"
        ),
        {"gen": cutover_generation, "nv": new_version, "now": now, "family": family},
    )
    return _canonical({
        "op": "mark_cutover", "family": family, "mode": "CUTOVER",
        "cutover_generation": cutover_generation, "row_version": new_version,
    })
