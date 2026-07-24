"""cutover CLI 공용 지원 (scope 빌드 + approval 토큰 소비).

3 개 token-consuming CLI(mark/begin/abort)가 공유하는 얇은 헬퍼. OPS-APPROVAL-00 의
``consume_same_db`` (SAME db_mode) 를 재사용해 fence/marker 전이를 approval 소비와 한
transaction 에 commit 한다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import consume_same_db, read_secret_from_token_file

PACKET_ID = "CUTOVER-MODE-01"


def sha256_file(path: "str | Path") -> str:
    """readiness artifact 파일의 sha256 hex(스트리밍)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_scope(
    operation_id: str, family: str, phase: str, artifact_sha256: str,
    expected_version: int, expected_generation: int,
) -> dict[str, Any]:
    """approval scope object(RFC 8785 JCS exact fields)를 구성.

    ``target_ids_or_family`` 에 family literal 을 넣는다(§2.1 owner 표: family+readiness
    artifact+fence version+generation).
    """
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "packet_id": PACKET_ID,
        "target_ids_or_family": family,
        "phase": phase,
        "artifact_sha256": artifact_sha256,
        "expected_version": expected_version,
        "expected_generation": expected_generation,
    }


def consume_cutover_operation(
    session: Session, *,
    operation_id: str,
    control_root: Path,
    token_path: "str | Path",
    scope: dict[str, Any],
    target_mutation: Callable[[Session], bytes],
) -> str:
    """approval 토큰을 소비하며 ``target_mutation`` 을 같은 tx 에 적용(미commit).

    호출자가 session 을 commit 한다(원자성). 검증 실패 시 예외가 나고 mutation 은
    실행되지 않는다.

    :returns: consume 의 result_sha256.
    """
    raw_secret = read_secret_from_token_file(
        token_path, control_root, expected_operation_id=operation_id
    )
    return consume_same_db(
        session,
        operation_id=operation_id,
        scope_obj=scope,
        artifact_sha256=scope["artifact_sha256"],
        expected_version=scope["expected_version"],
        expected_generation=scope["expected_generation"],
        raw_secret=raw_secret,
        target_mutation=target_mutation,
    )
