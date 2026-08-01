"""signing activation CLI 공용 러너 (SESSION-SIGNING-SECRET-01).

8 개 activation CLI(tools/ops/*)가 공유하는 소비 러너. control root 해석 → scope 구성 →
OPS-APPROVAL 토큰 소비(approver 복사) → ``--apply`` 시에만 commit → key ID/결과 요약 출력.
이 모듈은 ``tools/ops`` 밖에 있어 ops manifest AST inventory 대상이 아니다(CLI 규약 없음).
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session, sessionmaker


def run_activation(
    *,
    operation_id: str,
    phase: str,
    artifact_path: str,
    expected_version: int,
    expected_generation: int,
    token_path: str,
    apply: bool,
    mutation_builder: Callable[[Session, Optional[int]], bytes],
    result_extra: "Optional[dict[str, Any]]" = None,
) -> int:
    """activation 전이를 OPS-APPROVAL 토큰 소비로 한 tx 에 적용(기본 dry-run).

    :param operation_id: 소비할 OPS operation.
    :param phase: approval scope 의 phase.
    :param artifact_path: scope artifact_sha256 를 계산할 주 rollout/smoke artifact.
    :param mutation_builder: ``(session, approver_id) -> bytes`` 실제 상태 전이.
    :returns: 0(성공). 검증 실패는 예외로 전파(mutation 0).
    """
    from db import engine
    from foms.services.security import ops_control_root as root_store
    from foms.services.security.signing import activate_ops

    try:
        control_root = root_store.resolve_control_root()
    except root_store.OpsControlRootError as exc:
        raise SystemExit(f"control root error: {exc}")

    artifact_sha = activate_ops.sha256_file(artifact_path)
    scope = activate_ops.build_scope(
        operation_id, phase, artifact_sha, expected_version, expected_generation
    )

    session = sessionmaker(bind=engine)()
    try:
        result_sha = activate_ops.consume_activation(
            session, operation_id=operation_id, control_root=control_root,
            token_path=token_path, scope=scope, mutation_builder=mutation_builder,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()

    out = {"operation": operation_id, "applied": bool(apply), "result_sha256": result_sha}
    out.update(result_extra or {})
    print(json.dumps(out, ensure_ascii=False))
    return 0
