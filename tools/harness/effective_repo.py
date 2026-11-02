"""셸 명령이 실제로 도는 저장소 루트(실효 저장소)를 찾는다.

훅은 언제나 메인 체크아웃(`${CLAUDE_PROJECT_DIR}`)에서 실행되지만, 세션은 메인 창에서
`cd /c/tmp/foms-s-… && git push …` 로 워크트리에 들어가 일한다. 푸시 가드·커밋 원장이
메인을 보고 판정하면 메인의 낡은 로컬 deploy 때문에 매 푸시가 사람 승인을 기다리고,
원장에는 남의 커밋이 적힌다(설계서 docs/specs/2026-11-02-push-guard-effective-repo_SPEC.md).

판정 순서: git `-C <dir>` → 같은 명령의 앞선 `cd`/`pushd` → 훅 입력 `cwd` → 메인.
해석이 애매하면(None) 호출부가 fail-closed(가드=ask) 또는 fail-open(원장=기록 안 함)으로 닫는다.
"""
from __future__ import annotations

import os
import re
import subprocess

#: 셸이 펼쳐야 값이 정해지는 경로 — 가드가 미리 알 수 없다.
_UNRESOLVABLE_RE = re.compile(r"[$`*?]")
#: Git Bash 표기 `/c/tmp/x` → `c:/tmp/x`.
_GIT_BASH_DRIVE_RE = re.compile(r"^/([A-Za-z])(/.*)?$")


def _git(cwd: str, *args: str) -> str | None:
    """`git -C cwd …` 의 stdout(앞뒤 공백 제거). 실패·빈 출력이면 None."""
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def native_path(raw: str) -> str:
    """Git Bash 경로(`/c/tmp/x`)를 Windows 경로(`c:/tmp/x`)로 바꾼다. 그 밖은 그대로."""
    if os.name == "nt":
        match = _GIT_BASH_DRIVE_RE.match(raw.replace("\\", "/"))
        if match:
            return f"{match.group(1)}:{match.group(2) or '/'}"
    return raw


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def resolve_repo_root(raw: str | None, *, base: str | None, reference_root: str | None) -> str | None:
    """실효 폴더 문자열을 저장소 루트로 바꾼다. 판정할 수 없으면 None.

    파라미터:
        raw: `-C`·`cd` 인자 또는 훅 입력 cwd(따옴표 제거된 것). None 이면 base 를 쓴다.
        base: 상대 경로의 기준(훅 입력 cwd, 없으면 메인 루트).
        reference_root: 메인 저장소 루트. 실효 루트의 origin 이 메인과 다르면 None
            (다른 저장소의 deploy 를 FOMS 원장으로 판정하지 않는다).
    반환: `git rev-parse --show-toplevel` 결과 또는 None.
    """
    target = raw if raw is not None else base
    if not target or target in ("-", "~") or target.startswith("~") or _UNRESOLVABLE_RE.search(target):
        return None
    path = native_path(target)
    if not os.path.isabs(path):
        if not base:
            return None
        path = os.path.join(native_path(base), path)
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return None
    top = _git(path, "rev-parse", "--show-toplevel")
    if top is None:
        return None
    if reference_root and not _same_path(top, reference_root):
        ref_url = _git(reference_root, "config", "--get", "remote.origin.url")
        if ref_url is None or _git(top, "config", "--get", "remote.origin.url") != ref_url:
            return None
    return top


def same_repo(a: str, b: str) -> bool:
    """두 루트가 같은 폴더인지(대소문자·구분자 무시)."""
    return _same_path(a, b)
