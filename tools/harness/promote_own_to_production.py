"""자기 세션 커밋만 production 승격 (worktree + cherry-pick + PR).

사용:
  python tools/harness/promote_own_to_production.py --session-id <id>
  python tools/harness/promote_own_to_production.py --shas <sha1,sha2>

origin/production 기반 임시 worktree 에서 지정 SHA 만 cherry-pick 한 뒤
promo 브랜치를 푸시하고 ``gh pr create --base production`` 한다.
``HEAD:production`` 직접 푸시는 하지 않는다.

기본: ``promote_completeness`` incomplete 이면 중단(exit 2).
``--allow-incomplete`` 로만 우회. cherry-pick 충돌 시 exit 3·worktree 보존.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Sequence

from promote_completeness import analyze_promote_completeness
from session_commit_ledger import session_shas, sha_in_list

GhRunner = Callable[[str, list[str]], subprocess.CompletedProcess[str]]


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


def _default_gh(cwd: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    """gh CLI 실행."""
    return _run(cwd, "gh", *args, check=False)


def _ordered_promote_shas(project_root: str, own: Sequence[str]) -> list[str]:
    """promote SHA 를 topo 오래된 순으로 정렬."""
    own_list = [s.strip().lower() for s in own if s and s.strip()]
    if not own_list:
        return []
    proc = _run(
        project_root,
        "git",
        "rev-list",
        "--reverse",
        "--topo-order",
        *own_list,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "git rev-list failed")
    range_shas = [ln.strip().lower() for ln in proc.stdout.splitlines() if ln.strip()]
    return [s for s in range_shas if sha_in_list(s, own_list)]


def promote_own_commits(
    project_root: str,
    shas: Sequence[str],
    *,
    worktree_parent: str | None = None,
    keep_on_error: bool = True,
    allow_incomplete: bool = False,
    base_ref: str = "origin/production",
    gh_runner: GhRunner | None = None,
    title: str = "",
    body: str = "",
) -> int:
    """자기 SHA 만 cherry-pick 해 production PR 을 연다.

    파라미터:
        project_root: 메인 저장소 루트.
        shas: 승격할 커밋 해시.
        worktree_parent: 임시 worktree 부모 (기본 c:/tmp).
        keep_on_error: 실패 시 worktree 보존.
        allow_incomplete: completeness 미통과 시에도 진행.
        base_ref: production 정본.
        gh_runner: 테스트용 gh 주입.
        title/body: PR 제목·본문.
    반환:
        exit code (0=성공, 1=오류, 2=incomplete/empty, 3=충돌).
    """
    if not shas:
        print("승격할 자기 세션 커밋이 없습니다.", file=sys.stderr)
        return 2

    fetch = _run(project_root, "git", "fetch", "origin", "production", check=False)
    if fetch.returncode != 0:
        print(fetch.stderr or "git fetch failed", file=sys.stderr)
        return 1

    completeness = analyze_promote_completeness(
        project_root, shas, base_ref=base_ref
    )
    if completeness.error:
        print(completeness.error, file=sys.stderr)
        return 1
    if not completeness.complete and not allow_incomplete:
        print(
            f"INCOMPLETE: missing baseline deps={len(completeness.missing)}. "
            "의존 포함·PC-only·중단을 사용자에게 확인하세요. "
            "우회는 --allow-incomplete 만.",
            file=sys.stderr,
        )
        for m in completeness.missing:
            print(f"  + {m.sha[:8]} {m.subject}", file=sys.stderr)
        return 2

    try:
        ordered = _ordered_promote_shas(project_root, shas)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not ordered:
        print("정렬된 승격 SHA 가 없습니다.", file=sys.stderr)
        return 2
    requested = {s.strip().lower() for s in shas if s and s.strip()}
    ordered_set = set(ordered)
    dropped = sorted(s for s in requested if not sha_in_list(s, list(ordered_set)))
    if dropped:
        print(
            "요청 SHA 중 rev-list에 안 잡힌 것(오타/리베이스/미존재): "
            + ", ".join(d[:8] for d in dropped),
            file=sys.stderr,
        )
        return 2

    parent = worktree_parent or ("c:/tmp" if os.name == "nt" else "/tmp")
    os.makedirs(parent, exist_ok=True)
    stamp = f"{int(time.time())}-{os.getpid()}"
    branch = f"promote/own-{stamp}"
    wt = os.path.join(parent, f"foms-prod-own-{stamp}")
    gh = gh_runner or _default_gh

    add = _run(
        project_root,
        "git",
        "worktree",
        "add",
        "-B",
        branch,
        wt,
        base_ref,
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
                "user.email=promote@foms.local",
                "-c",
                "user.name=FOMS Promote",
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

        push = _run(
            wt,
            "git",
            "push",
            "-u",
            "origin",
            f"HEAD:refs/heads/{branch}",
            check=False,
        )
        if push.returncode != 0:
            print(push.stderr or "push failed", file=sys.stderr)
            if not keep_on_error:
                _cleanup(project_root, wt, branch)
            return 1

        pr_title = title or f"promote: {len(ordered)} session commit(s)"
        pr_body = body or (
            "세션 own-only production 승격 (cherry-pick).\n\n"
            f"SHAs: {', '.join(s[:8] for s in ordered)}\n"
            "자동 생성: promote_own_to_production.py"
        )
        pr = gh(
            wt,
            [
                "pr",
                "create",
                "--base",
                "production",
                "--head",
                branch,
                "--title",
                pr_title,
                "--body",
                pr_body,
            ],
        )
        if pr.returncode != 0:
            print(pr.stderr or pr.stdout or "gh pr create failed", file=sys.stderr)
            print(
                f"원격 브랜치 잔존 가능: origin {branch} — 수동 삭제 또는 PR 재시도.",
                file=sys.stderr,
            )
            if not keep_on_error:
                _cleanup(project_root, wt, branch)
            return 1

        # 성공 시 로컬 worktree만 정리. remote promo 브랜치는 PR이 소유.
        _cleanup(project_root, wt, branch, delete_branch=True)
        url = (pr.stdout or "").strip()
        print(f"OK: opened PR for {len(ordered)} commit(s) → production")
        if url:
            print(url)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"own-only promote 실패: {exc}\nworktree: {wt}", file=sys.stderr)
        return 1


def _cleanup(
    project_root: str,
    wt: str,
    branch: str,
    *,
    delete_branch: bool = True,
) -> None:
    """worktree 및 로컬 임시 브랜치 제거."""
    rm = _run(
        project_root, "git", "worktree", "remove", "--force", wt, check=False
    )
    if rm.returncode != 0:
        print(
            f"worktree remove 실패({rm.returncode}): {rm.stderr or wt}",
            file=sys.stderr,
        )
    if delete_branch:
        br = _run(project_root, "git", "branch", "-D", branch, check=False)
        if br.returncode != 0:
            print(
                f"branch -D 실패({br.returncode}): {br.stderr or branch}",
                file=sys.stderr,
            )
    if os.path.isdir(wt):
        try:
            shutil.rmtree(wt)
        except OSError as exc:
            print(f"rmtree 실패: {wt}: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=os.getcwd())
    parser.add_argument("--session-id", default="")
    parser.add_argument("--shas", default="", help="쉼표 구분 SHA")
    parser.add_argument("--worktree-parent", default="")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="completeness incomplete 여도 진행 (사용자 승인 후만)",
    )
    parser.add_argument("--base-ref", default="origin/production")
    parser.add_argument("--title", default="")
    parser.add_argument("--body", default="")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.project_root)
    if args.shas.strip():
        shas = [s.strip().lower() for s in args.shas.split(",") if s.strip()]
    else:
        shas = session_shas(root, args.session_id or "unknown")
    return promote_own_commits(
        root,
        shas,
        worktree_parent=args.worktree_parent or None,
        allow_incomplete=args.allow_incomplete,
        base_ref=args.base_ref,
        title=args.title,
        body=args.body,
    )


if __name__ == "__main__":
    raise SystemExit(main())
