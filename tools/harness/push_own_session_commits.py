"""자기 세션 커밋만 deploy 로 푸시 (임시 worktree + cherry-pick).

사용:
  python tools/harness/push_own_session_commits.py --session-id <id>
  python tools/harness/push_own_session_commits.py --shas <sha1,sha2>

공유 워킹트리에서 `git push origin deploy` 로 HEAD 전체를 올리지 않고,
origin/deploy 기반 임시 worktree 에서 지정 SHA 만 cherry-pick 한 뒤
`git push origin HEAD:deploy` 한다. cherry-pick 충돌 시 중단·worktree 보존.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from typing import Sequence

from session_commit_ledger import session_shas, sha_in_list


def _run(cwd: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """git/기타 명령 실행."""
    return subprocess.run(
        list(args),
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _ordered_own_shas(project_root: str, own: Sequence[str]) -> list[str]:
    """origin/deploy..HEAD 중 own 에 속하는 SHA 를 오래된 순으로."""
    proc = _run(
        project_root,
        "git",
        "log",
        "--reverse",
        "--format=%H",
        "origin/deploy..HEAD",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "git log failed")
    range_shas = [ln.strip().lower() for ln in proc.stdout.splitlines() if ln.strip()]
    return [s for s in range_shas if sha_in_list(s, list(own))]


def push_own_commits(
    project_root: str,
    shas: Sequence[str],
    *,
    worktree_parent: str | None = None,
    keep_on_error: bool = True,
) -> int:
    """자기 SHA 만 cherry-pick 해 deploy 에 푸시한다.

    파라미터:
        project_root: 메인 저장소 루트.
        shas: 푸시할 커밋 해시 목록(순서 무관 — 범위 순으로 정렬).
        worktree_parent: 임시 worktree 부모 (기본 c:/tmp).
        keep_on_error: 실패 시 worktree 보존.
    반환:
        프로세스 exit code (0=성공).
    """
    if not shas:
        print("푸시할 자기 세션 커밋이 없습니다.", file=sys.stderr)
        return 2

    fetch = _run(project_root, "git", "fetch", "origin", "deploy", check=False)
    if fetch.returncode != 0:
        print(fetch.stderr or "git fetch failed", file=sys.stderr)
        return 1

    ordered = _ordered_own_shas(project_root, shas)
    if not ordered:
        print(
            "origin/deploy..HEAD 안에 자기 SHA 가 없습니다. 이미 푸시됐거나 레저가 어긋났습니다.",
            file=sys.stderr,
        )
        return 2

    parent = worktree_parent or ("c:/tmp" if os.name == "nt" else "/tmp")
    os.makedirs(parent, exist_ok=True)
    stamp = f"{int(time.time())}-{os.getpid()}"
    branch = f"tmp/own-deploy-{stamp}"
    wt = os.path.join(parent, f"foms-deploy-own-{stamp}")

    add = _run(
        project_root,
        "git",
        "worktree",
        "add",
        "-B",
        branch,
        wt,
        "origin/deploy",
        check=False,
    )
    if add.returncode != 0:
        print(add.stderr or "worktree add failed", file=sys.stderr)
        return 1

    try:
        for sha in ordered:
            cp = _run(
                wt,
                "git",
                "-c",
                "user.email=deploy-push@foms.local",
                "-c",
                "user.name=FOMS Deploy Push",
                "cherry-pick",
                sha,
                check=False,
            )
            if cp.returncode != 0:
                print(
                    f"cherry-pick 충돌: {sha[:8]}\n{cp.stderr}\n"
                    "의존 커밋 포함 여부를 사용자에게 확인하세요. "
                    f"worktree 보존: {wt}",
                    file=sys.stderr,
                )
                if not keep_on_error:
                    _cleanup(project_root, wt, branch)
                return 3

        push = _run(wt, "git", "push", "origin", f"HEAD:deploy", check=False)
        if push.returncode != 0:
            print(push.stderr or "push failed", file=sys.stderr)
            if not keep_on_error:
                _cleanup(project_root, wt, branch)
            return 1

        _cleanup(project_root, wt, branch)
        print(f"OK: pushed {len(ordered)} commit(s) to origin/deploy")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"own-only push 실패: {exc}\nworktree: {wt}", file=sys.stderr)
        return 1


def _cleanup(project_root: str, wt: str, branch: str) -> None:
    """worktree 및 임시 브랜치 제거."""
    _run(project_root, "git", "worktree", "remove", "--force", wt, check=False)
    _run(project_root, "git", "branch", "-D", branch, check=False)
    if os.path.isdir(wt):
        shutil.rmtree(wt, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default=os.getcwd(),
        help="저장소 루트 (기본: cwd)",
    )
    parser.add_argument("--session-id", default="", help="레저에서 SHA 로드")
    parser.add_argument(
        "--shas",
        default="",
        help="쉼표 구분 SHA (session-id 대신 직접 지정)",
    )
    parser.add_argument(
        "--worktree-parent",
        default="",
        help="임시 worktree 부모 디렉터리",
    )
    args = parser.parse_args(argv)
    root = os.path.abspath(args.project_root)
    if args.shas.strip():
        shas = [s.strip().lower() for s in args.shas.split(",") if s.strip()]
    else:
        shas = session_shas(root, args.session_id or "unknown")
    return push_own_commits(
        root,
        shas,
        worktree_parent=args.worktree_parent or None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
