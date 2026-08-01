"""operator 용 고위험 ops 승인 요청 생성 CLI (§2.1 line 205).

operator 가 PENDING ops approval request + random 256-bit one-time token 을 만든다.
**approver 를 지정할 수 없다** — 승인은 active ADMIN 이 화면 재인증으로만 한다.

    python tools/ops/create_ops_approval_request.py \
        --operation SIGNING_CUTOVER_PREPARE \
        --scope-file <canonical-redacted.json> \
        --expires-in-seconds 900 \
        [--output <under-control-root>.json]

token 은 ``FOMS_OPS_CONTROL_ROOT`` 아래 random filename 으로 atomic 하게 쓰인다(또는
``--output`` 이 control root 아래를 가리키면 그 이름으로). raw secret 은 stdout/DB/log 에
남기지 않고 오직 토큰 파일에만 존재한다. stdout 에는 approval_id 와 승인 URL 만 출력한다.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

# repo root 를 sys.path 에 (Railway SSH / 로컬 양쪽에서 실행 가능).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from models import OpsApprovalRequest  # noqa: E402
from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.security import ops_control_root as root_store  # noqa: E402
from foms.services.security.ops_approval import (  # noqa: E402
    canonical_scope_bytes,
    compute_scope_sha256,
    nonce_hash_from_secret,
)
from foms.services.security.ops_approval_manifest import (  # noqa: E402
    load_operations_manifest,
    OpsManifestError,
)


def _operator_identity_hash() -> str:
    """operator OS identity 의 sha256(원문 저장 금지 — PII0)."""
    who = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    return hashlib.sha256(f"ops-operator\0{who}".encode("utf-8")).hexdigest()


def _load_scope(path: str) -> dict:
    """scope 파일을 로드하고 canonical 직렬화가 가능한지(exact fields) 검증."""
    with open(path, encoding="utf-8") as fh:
        scope = json.load(fh)
    canonical_scope_bytes(scope)  # raises on field/dup violations
    return scope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a high-risk ops approval request (operator).")
    parser.add_argument("--operation", required=True, help="manifest 에 등록된 operation_id")
    parser.add_argument("--scope-file", required=True, help="canonical redacted scope JSON")
    parser.add_argument("--expires-in-seconds", type=int, default=900)
    parser.add_argument("--output", default=None, help="control root 아래 토큰 경로(선택)")
    args = parser.parse_args(argv)

    manifest = load_operations_manifest()
    if args.operation not in manifest.get("operations", {}):
        raise SystemExit(f"unknown operation {args.operation!r} (not in ops approval manifest).")

    try:
        control_root = root_store.resolve_control_root()
    except root_store.OpsControlRootError as exc:
        raise SystemExit(f"control root error: {exc}")

    scope = _load_scope(args.scope_file)
    if scope.get("operation_id") != args.operation:
        raise SystemExit("scope.operation_id must equal --operation.")
    scope_sha256 = compute_scope_sha256(scope)

    secret_b64, raw_secret = root_store.new_one_time_secret()
    nonce_hash = nonce_hash_from_secret(raw_secret)
    approval_id = str(uuid.uuid4())
    now = now_utc_naive()
    expires_at = now + datetime.timedelta(seconds=args.expires_in_seconds)

    session = sessionmaker(bind=engine)()
    try:
        session.add(
            OpsApprovalRequest(
                id=approval_id,
                operation_type=args.operation,
                scope_sha256=scope_sha256,
                artifact_sha256=scope.get("artifact_sha256"),
                expected_version=scope.get("expected_version"),
                expected_generation=scope.get("expected_generation"),
                nonce_hash=nonce_hash,
                expires_at=expires_at,
                state="PENDING",
                operator_identity_hash=_operator_identity_hash(),
                created_at=now,
            )
        )
        session.commit()
    finally:
        # 실패 시 미커밋 tx 는 close() 가 rollback 한다(광범위 except 로 삼키지 않음).
        session.close()

    token = root_store.build_token(
        approval_id=approval_id,
        one_time_secret_b64url=secret_b64,
        operation_id=args.operation,
        scope_sha256=scope_sha256,
        expires_at_iso=expires_at.isoformat() + "Z",
    )
    if args.output:
        target = Path(args.output)
        # --output 은 control root 아래여야 한다.
        root_store._assert_under_root(target, control_root)
        token_path = target
        payload = json.dumps(token, ensure_ascii=False, sort_keys=True).encode("utf-8")
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
    else:
        token_path = root_store.atomic_write_token(control_root, token)

    # stdout: secret 미포함. approval_id + 승인 URL + 토큰 경로만.
    print(json.dumps({
        "approval_id": approval_id,
        "operation": args.operation,
        "approval_url": f"/admin/ops/approvals/{approval_id}",
        "token_path": str(token_path),
        "expires_at": expires_at.isoformat() + "Z",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
