"""8 OPS-APPROVAL operation 의 same-DB consume 헬퍼 (CHANNEL-INBOUND-ORDER-01).

CLI 가 ``--approval-token-file`` 을 소비하며 approver 를 조회해 실제 전이(mutation)를 한 tx 에
적용하는 공용 진입점. SESSION-SIGNING ``prepare_ops.consume_prepare_operation`` 과 동형이다.
``updated_by_admin_user_id`` 는 CLI 입력이 아니라 소비된 approval row 의 ``approved_by_user_id``
에서 취한다(**default Admin 금지** — 입력 승인 아님). 호출자가 session 을 commit 한다(원자성).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from foms.services.security.ops_approval import (
    consume_same_db,
    nonce_hash_from_secret,
    read_secret_from_token_file,
)
from models import OpsApprovalRequest


def sha256_file(path: "str | Path") -> str:
    """artifact 파일의 sha256 hex(scope artifact_sha256 산출용)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def consume_channel_operation(
    session: Session, *,
    operation_id: str,
    control_root: Path,
    token_path: "str | Path",
    scope: "dict[str, Any]",
    mutation_builder: Callable[[Session, Optional[int]], bytes],
) -> str:
    """approval 토큰을 소비하며 approver 를 조회해 mutation 을 한 tx 에 적용(미commit).

    Args:
        session: business tx 세션(호출자가 commit).
        operation_id: 8 CHANNEL operation 중 하나.
        control_root: FOMS_OPS_CONTROL_ROOT.
        token_path: ``--approval-token-file`` 경로(control root 아래).
        scope: exact fields scope object(operation 별 build_scope 결과).
        mutation_builder: ``(session, approved_by_admin_user_id) -> bytes`` — 실제 전이.

    Returns:
        consume 의 result_sha256.
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
