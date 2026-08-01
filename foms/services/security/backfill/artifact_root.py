"""``FOMS_REMEDIATION_ARTIFACT_ROOT`` 위치/ACL/OS 가드 (§7.3 line 1249).

암호화 backfill artifact 가 존재할 수 있는 유일한 위치를 강제한다. root 는 **필수
absolute path** 이며 다음 하위면 fail-closed 한다: repo/worktree, user profile,
OneDrive/Dropbox/Google Drive 등 동기화·클라우드 폴더, network share, reparse-point.
Windows 는 inheritance off + operator SID/SYSTEM 만 접근하는 ACL 을 요구한다.

이 plan 의 exact provider 는 **Windows DPAPI CurrentUser v1** 뿐이므로 Linux/Railway/
다른 host 는 별도 KEK spec 이 정의되기 전까지 fail-closed 한다. weak ACL/위치 위반이면
audit 자체를 시작하지 않는다.

reparse-point 판정·broad-ACL(icacls) 판정은 :mod:`~foms.services.security.ops_control_root`
의 검증된 헬퍼를 재사용한다(control root 와 동일한 위협 모델).
"""
from __future__ import annotations

import os
from pathlib import Path

from foms.services.security.ops_control_root import (
    _FORBIDDEN_PATH_MARKERS,
    _is_reparse_point,
    _repo_root,
    _windows_acl_ok,
)

ENV_VAR = "FOMS_REMEDIATION_ARTIFACT_ROOT"


class ArtifactRootError(RuntimeError):
    """artifact root 이 위치/ACL/OS 계약을 위반할 때(호출자는 audit 시작 0)."""


def _assert_outside_repo_profile_sync(root: Path) -> None:
    """root 이 repo/user-profile/sync-cloud/network/reparse **밖**인지 검증(위반 시 예외)."""
    resolved = root.resolve()

    repo = _repo_root()
    try:
        resolved.relative_to(repo)
        raise ArtifactRootError(f"{ENV_VAR} must be outside the repository tree ({repo}).")
    except ValueError:
        pass  # not under repo → good

    profile = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    if profile:
        try:
            resolved.relative_to(Path(profile).resolve())
            raise ArtifactRootError(
                f"{ENV_VAR} must live outside the user profile ({profile}); "
                "profile subtrees (incl. OneDrive known folders, Temp) are refused."
            )
        except ValueError:
            pass  # not under profile → good

    lowered = str(resolved).lower().replace("/", "\\")
    for marker in _FORBIDDEN_PATH_MARKERS:
        if marker in lowered:
            raise ArtifactRootError(
                f"{ENV_VAR} must not live under a sync/cloud folder (matched marker {marker!r})."
            )

    if str(resolved).startswith("\\\\"):
        raise ArtifactRootError(f"{ENV_VAR} must not be a network share.")

    if _is_reparse_point(resolved):
        raise ArtifactRootError(f"{ENV_VAR} must not be a reparse point.")


def resolve_artifact_root(require_acl: bool = True) -> Path:
    """``FOMS_REMEDIATION_ARTIFACT_ROOT`` 을 검증해 절대 경로로 반환.

    :param require_acl: Windows ACL 잠금 검증 여부. 기본 True(운영 경로). fail-closed
        가드 자체는 ACL 검증 이전에 위치/OS 위반을 먼저 거부한다.
    :returns: 검증된 artifact root 절대 경로.
    :raises ArtifactRootError: 미설정/비 Windows/상대경로/부재/비디렉터리/repo·profile·
        sync·network·reparse 내부/ACL 미잠금.
    """
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        raise ArtifactRootError(f"{ENV_VAR} is not set.")
    if os.name != "nt":
        raise ArtifactRootError(
            f"{ENV_VAR} is only supported on Windows (DPAPI CurrentUser v1); "
            "Linux/Railway/other host fail-closed until a separate KEK spec is defined."
        )
    root = Path(raw)
    if not root.is_absolute():
        raise ArtifactRootError(f"{ENV_VAR} must be an absolute path.")
    if not root.exists() or not root.is_dir():
        raise ArtifactRootError(f"{ENV_VAR} must be an existing directory.")
    _assert_outside_repo_profile_sync(root)
    if require_acl and not _windows_acl_ok(root):
        raise ArtifactRootError(
            f"{ENV_VAR} ACL is not locked down "
            "(inheritance must be off and broad principals removed)."
        )
    return root.resolve()


def logical_artifact_dir(root: Path, report_baseline_sha: str, domain: str) -> Path:
    """``<root>/<report-baseline-sha>/<domain>`` 논리 artifact dir 경로(§7.3 line 1251).

    경로 조립만 한다(생성/검증은 호출자). ``domain`` 은 packet 정의 literal 이다.
    """
    return root / report_baseline_sha / domain
