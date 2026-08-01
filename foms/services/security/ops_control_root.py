"""``FOMS_OPS_CONTROL_ROOT`` — 고위험 ops 승인 토큰의 보호 저장소 (§2.1 line 223).

raw one-time token 은 DB/artifact/git/log 에 남기지 않고 오직 이 control root 아래
random filename 으로 atomic 하게 존재하다가 consume/expire/revoke 뒤 제거된다.

control root 계약:

* repo/worktree/user profile/OneDrive·동기화·network share/reparse-point **밖**의
  absolute path.
* Windows: inheritance off + 운영자 SID/SYSTEM 만 접근(broad principal 금지).
* 다른 OS 는 **fail-closed** (지원하지 않음).

이 모듈은 raw secret 을 절대 로깅하지 않는다(예외 메시지에도 secret 값 미포함).
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

TOKEN_SCHEMA_VERSION = 1
_SECRET_BYTES = 32  # 256-bit one-time secret

# OneDrive/동기화/클라우드 폴더 표식(경로에 등장하면 거부).
_FORBIDDEN_PATH_MARKERS = (
    "onedrive",
    "dropbox",
    "google drive",
    "googledrive",
    "icloud",
    "nextcloud",
    "sync",
)

# 광범위 접근 principal — control root ACL 에 존재하면 거부.
_BROAD_ACL_PRINCIPALS = (
    "Everyone",
    "BUILTIN\\Users",
    "Authenticated Users",
    "NT AUTHORITY\\Authenticated Users",
    "Users",
)


class OpsControlRootError(RuntimeError):
    """control root 이 계약(위치/ACL/OS)을 위반할 때."""


def _repo_root() -> Path:
    """이 파일 기준 repo 루트(…/foms/services/security/ops_control_root.py → repo)."""
    return Path(__file__).resolve().parents[3]


def _is_reparse_point(path: Path) -> bool:
    """``path`` 가 reparse point(symlink/junction)인지 판정(Windows 우선)."""
    try:
        attrs = os.stat(path, follow_symlinks=False).st_file_attributes  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return path.is_symlink()
    FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def _assert_outside_repo_and_sync(root: Path) -> None:
    """control root 이 repo/profile/OneDrive/동기화/reparse 밖인지 검증."""
    resolved = root.resolve()

    repo = _repo_root()
    try:
        resolved.relative_to(repo)
        raise OpsControlRootError(
            f"FOMS_OPS_CONTROL_ROOT must be outside the repository tree ({repo})."
        )
    except ValueError:
        pass  # not under repo → good

    lowered = str(resolved).lower().replace("/", "\\")
    for marker in _FORBIDDEN_PATH_MARKERS:
        if marker in lowered:
            raise OpsControlRootError(
                f"FOMS_OPS_CONTROL_ROOT must not live under a sync/cloud folder "
                f"(matched marker {marker!r})."
            )

    # UNC/network share (\\server\share) 거부.
    if str(resolved).startswith("\\\\"):
        raise OpsControlRootError("FOMS_OPS_CONTROL_ROOT must not be a network share.")

    if _is_reparse_point(resolved):
        raise OpsControlRootError("FOMS_OPS_CONTROL_ROOT must not be a reparse point.")


def _windows_acl_ok(root: Path) -> bool:
    """Windows ACL 이 broad principal 없이 잠겨 있는지 icacls 로 판정.

    inheritance 가 켜져 있으면 상속된 broad principal(예: BUILTIN\\Users)이 나타나므로
    그 존재를 곧 실패 신호로 쓴다. icacls 미가용/오류는 fail-closed(False).
    """
    try:
        out = subprocess.run(
            ["icacls", str(root)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if out.returncode != 0:
        return False
    listing = out.stdout
    for principal in _BROAD_ACL_PRINCIPALS:
        if principal in listing:
            return False
    return True


def harden_control_root(root: Path) -> None:
    """control root 디렉터리 ACL 을 잠근다(상속 제거 + 현재 사용자/SYSTEM 만 Full).

    프로비저닝/테스트에서 1회 호출. 다른 OS 는 fail-closed.

    :param root: 이미 존재하는 control root 디렉터리.
    :raises OpsControlRootError: 비 Windows 이거나 icacls 실패.
    """
    if os.name != "nt":
        raise OpsControlRootError("control root hardening is Windows-only (other OS fail-closed).")
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    grants = ["icacls", str(root), "/inheritance:r", "/grant:r", "SYSTEM:(OI)(CI)F"]
    if user:
        grants += ["/grant:r", f"{user}:(OI)(CI)F"]
    result = subprocess.run(grants, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise OpsControlRootError(f"failed to harden control root ACL: {result.stderr.strip()}")


def resolve_control_root(require_acl: bool = True) -> Path:
    """``FOMS_OPS_CONTROL_ROOT`` 을 검증해 반환.

    :param require_acl: Windows ACL 잠금 검증 여부. 기본 True(운영 경로).
    :returns: 검증된 control root 절대 경로.
    :raises OpsControlRootError: 미설정/상대경로/부재/비디렉터리/repo·sync 내부/
        reparse/비 Windows/ACL 미잠금.
    """
    raw = os.environ.get("FOMS_OPS_CONTROL_ROOT", "").strip()
    if not raw:
        raise OpsControlRootError("FOMS_OPS_CONTROL_ROOT is not set.")
    if os.name != "nt":
        raise OpsControlRootError(
            "FOMS_OPS_CONTROL_ROOT is only supported on Windows; other OS fail-closed."
        )
    root = Path(raw)
    if not root.is_absolute():
        raise OpsControlRootError("FOMS_OPS_CONTROL_ROOT must be an absolute path.")
    if not root.exists() or not root.is_dir():
        raise OpsControlRootError("FOMS_OPS_CONTROL_ROOT must be an existing directory.")
    _assert_outside_repo_and_sync(root)
    if require_acl and not _windows_acl_ok(root):
        raise OpsControlRootError(
            "FOMS_OPS_CONTROL_ROOT ACL is not locked down "
            "(inheritance must be off and broad principals removed; run harden_control_root)."
        )
    return root.resolve()


def _assert_under_root(path: Path, root: Path) -> Path:
    """``path`` 가 control root 아래인지 검증(밖이면 거부)."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise OpsControlRootError(
            "token path is outside FOMS_OPS_CONTROL_ROOT (refused)."
        )
    return resolved


def new_one_time_secret() -> tuple[str, bytes]:
    """256-bit one-time secret 을 생성.

    :returns: ``(base64url-no-padding, raw-bytes)`` 튜플. base64url 은 토큰 파일에,
        raw bytes 의 sha256 은 DB ``nonce_hash`` 로 쓴다.
    """
    raw = secrets.token_bytes(_SECRET_BYTES)
    b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return b64, raw


def decode_secret_b64url(b64: str) -> bytes:
    """토큰의 base64url one-time secret 을 raw bytes 로 strict decode."""
    pad = "=" * (-len(b64) % 4)
    return base64.urlsafe_b64decode(b64 + pad)


def build_token(
    approval_id: str,
    one_time_secret_b64url: str,
    operation_id: str,
    scope_sha256: str,
    expires_at_iso: str,
) -> dict[str, Any]:
    """토큰 schema dict 를 생성(§2.1 line 223 exact fields)."""
    return {
        "schema_version": TOKEN_SCHEMA_VERSION,
        "approval_id": approval_id,
        "one_time_secret_b64url": one_time_secret_b64url,
        "operation_id": operation_id,
        "scope_sha256": scope_sha256,
        "expires_at": expires_at_iso,
    }


_REQUIRED_TOKEN_FIELDS = (
    "schema_version",
    "approval_id",
    "one_time_secret_b64url",
    "operation_id",
    "scope_sha256",
    "expires_at",
)


def atomic_write_token(root: Path, token: dict[str, Any]) -> Path:
    """control root 아래 random filename 으로 토큰을 atomic(O_EXCL) create.

    :param root: 검증된 control root.
    :param token: :func:`build_token` schema dict.
    :returns: 생성된 토큰 파일 경로.
    :raises OpsControlRootError: 스키마 위반.
    """
    missing = [f for f in _REQUIRED_TOKEN_FIELDS if f not in token]
    if missing:
        raise OpsControlRootError(f"token missing fields: {missing}")
    filename = f"ops-approval-{secrets.token_hex(16)}.json"
    path = _assert_under_root(root / filename, root)
    payload = json.dumps(token, ensure_ascii=False, sort_keys=True).encode("utf-8")
    # O_EXCL: 이미 존재하면 실패(충돌/재사용 방지).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    return path


def read_token(path: Path, root: Path) -> dict[str, Any]:
    """control root 아래 토큰 파일을 로드/검증.

    :raises OpsControlRootError: 경로가 root 밖이거나 스키마 위반.
    """
    resolved = _assert_under_root(Path(path), root)
    with open(resolved, encoding="utf-8") as fh:
        token = json.load(fh)
    if not isinstance(token, dict):
        raise OpsControlRootError("token file is not a JSON object.")
    missing = [f for f in _REQUIRED_TOKEN_FIELDS if f not in token]
    if missing:
        raise OpsControlRootError(f"token missing fields: {missing}")
    return token


def remove_token(path: Path) -> None:
    """consume/expire/revoke 뒤 토큰 파일 제거.

    삭제 실패는 access-deny quarantine(``.quarantine`` rename) + CRITICAL 표식으로
    남긴다. secure-erase 를 과장하지 않는다(단순 unlink/rename).
    """
    p = Path(path)
    try:
        os.remove(p)
    except FileNotFoundError:
        return
    except OSError:
        try:
            p.rename(p.with_suffix(p.suffix + ".quarantine"))
        except OSError as exc:  # noqa: BLE001 - 마지막 방어, 삼키지 않고 재발생
            raise OpsControlRootError(
                f"CRITICAL: token could not be removed or quarantined: {p}"
            ) from exc
