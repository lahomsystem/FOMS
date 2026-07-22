"""deploy push 범위 vs 세션 레저 분류.

`origin/deploy..HEAD` 의 SHA 가 현재 세션 ledger 에 모두 있으면 own,
하나라도 없으면 foreign, ledger/세션 불명이면 unknown.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Literal

from session_commit_ledger import normalize_session_id, session_shas, sha_in_list

ScopeKind = Literal["empty", "own", "foreign", "unknown"]


@dataclass(frozen=True)
class ScopeResult:
    """deploy push 범위 분류 결과."""

    kind: ScopeKind
    shas: tuple[str, ...]
    foreign_shas: tuple[str, ...]
    label: str


def _run_git(project_root: str, *args: str) -> tuple[int, str, str]:
    """git 서브프로세스 실행. (code, stdout, stderr)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def list_unpushed_deploy_shas(project_root: str) -> tuple[str, ...]:
    """`origin/deploy..HEAD` SHA 목록(오래된 순). remote 없으면 빈 튜플.

    fetch 는 호출하지 않는다(가드 경로 지연·네트워크 회피). 로컬
    `origin/deploy` ref 가 있으면 그걸 쓴다.
    """
    code, out, _err = _run_git(
        project_root, "rev-parse", "--verify", "origin/deploy"
    )
    if code != 0:
        return ()
    code, out, _err = _run_git(
        project_root, "log", "--reverse", "--format=%H", "origin/deploy..HEAD"
    )
    if code != 0 or not out:
        return ()
    return tuple(line.strip().lower() for line in out.splitlines() if line.strip())


def classify_deploy_scope(
    project_root: str,
    session_id: str | None,
) -> ScopeResult:
    """현재 세션 기준 deploy push 범위를 분류한다.

    파라미터:
        project_root: 저장소 루트.
        session_id: 현재 에이전트 세션 id (없으면 unknown 취급).
    반환:
        ScopeResult (empty/own/foreign/unknown).
    """
    shas = list_unpushed_deploy_shas(project_root)
    if not shas:
        return ScopeResult("empty", (), (), "")

    sid = normalize_session_id(session_id)
    if sid == "unknown":
        preview = ", ".join(s[:8] for s in shas[:5])
        return ScopeResult(
            "unknown",
            shas,
            shas,
            f"deploy 푸시 세션 불명({len(shas)}커밋: {preview})",
        )

    known = session_shas(project_root, sid)
    if not known:
        preview = ", ".join(s[:8] for s in shas[:5])
        return ScopeResult(
            "unknown",
            shas,
            shas,
            f"deploy 푸시 레저 없음({len(shas)}커밋: {preview})",
        )

    foreign = tuple(s for s in shas if not sha_in_list(s, known))
    if not foreign:
        return ScopeResult("own", shas, (), "")

    preview = ", ".join(s[:8] for s in foreign[:5])
    return ScopeResult(
        "foreign",
        shas,
        foreign,
        (
            f"deploy 푸시 타 세션 커밋 포함({len(foreign)}/{len(shas)}: {preview}) "
            f"— 전체 포함 승인 또는 자기 몫만(임시 WT cherry-pick)"
        ),
    )


def push_targets_deploy(targets: set[str], *, implicit_branch: str | None = None) -> bool:
    """refspec 대상 또는 암시 브랜치가 deploy 이면 True."""
    lowered = {t.lower() for t in targets if t}
    if "deploy" in lowered:
        return True
    if not lowered and (implicit_branch or "").lower() == "deploy":
        return True
    return False
