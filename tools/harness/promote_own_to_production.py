"""자기 세션 커밋만 production 승격 (worktree + cherry-pick + PR).

사용:
  python tools/harness/promote_own_to_production.py --session-id <id>
  python tools/harness/promote_own_to_production.py --shas <sha1,sha2>

origin/production 기반 임시 worktree 에서 지정 SHA 만 cherry-pick 한 뒤
promo 브랜치를 푸시하고 ``gh pr create --base production`` 한다.
``HEAD:production`` 직접 푸시는 하지 않는다.

기본: ``promote_completeness`` incomplete 이면 중단(exit 2).
``--allow-incomplete`` 로만 우회. cherry-pick 충돌 시 exit 3·worktree 보존.
단, 충돌 hunk 가 모두 자산 핀(``?v=<토큰>``)만 다르면 사전순 max 토큰으로 자동 해결.
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

from promote_completeness import PIN_RE, analyze_promote_completeness, normalize_pins
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


def _count_range(worktree: str, base_ref: str) -> int:
    """`base_ref..HEAD` 커밋 수 — cherry-pick 결과가 요청 SHA 수와 같은지 대조하는 데 쓴다.

    파라미터:
        worktree: 승격 worktree 경로.
        base_ref: production 정본 ref.
    반환: 커밋 수. 조회 실패는 -1(불일치로 취급돼 안전측 정지).
    """
    proc = _run(worktree, "git", "rev-list", "--count", f"{base_ref}..HEAD", check=False)
    if proc.returncode != 0:
        return -1
    try:
        return int((proc.stdout or "").strip() or "0")
    except ValueError:
        return -1


def _resolve_pin_hunks(text: str) -> str | None:
    """충돌 마커가 든 텍스트에서 hunk 마다 ours/theirs 가 핀 토큰만 다르면 max 토큰으로 해결.

    반환: 해결된 텍스트. 핀이 아닌 차이가 하나라도 있으면 None.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    found = False
    while i < len(lines):
        if not lines[i].startswith("<<<<<<<"):
            out.append(lines[i])
            i += 1
            continue
        found = True
        ours: list[str] = []
        theirs: list[str] = []
        section = "ours"
        i += 1
        while i < len(lines) and not lines[i].startswith(">>>>>>>"):
            ln = lines[i]
            if ln.startswith("|||||||"):
                section = "base"  # diff3 바탕 구간은 버린다
            elif ln.startswith("=======") and section in ("ours", "base"):
                section = "theirs"
            elif section == "ours":
                ours.append(ln)
            elif section == "theirs":
                theirs.append(ln)
            i += 1
        if i >= len(lines):
            return None  # 닫는 마커 없음
        i += 1
        if len(ours) != len(theirs):
            return None
        for a, b in zip(ours, theirs):
            if normalize_pins(a) != normalize_pins(b):
                return None
            ta = PIN_RE.findall(a)
            tb = PIN_RE.findall(b)
            tokens = iter(max(x, y) for x, y in zip(ta, tb))
            out.append(PIN_RE.sub(lambda _m: f"?v={next(tokens)}", a))
    return "".join(out) if found else None


def _try_resolve_pin_conflicts(wt: str) -> bool:
    """cherry-pick 충돌이 모두 핀 줄뿐이면 해결·add·continue 한다.

    "충돌 = 타 세션 의존 신호, 임의 해결 금지" 의 유일한 예외 — 자산 핀 토큰만.
    반환: 해결해 커밋까지 마쳤으면 True. 아니면 worktree 를 건드리지 않고 False.
    """
    proc = _run(wt, "git", "diff", "--name-only", "--diff-filter=U", check=False)
    if proc.returncode != 0:
        return False
    paths = [p.strip() for p in proc.stdout.splitlines() if p.strip()]
    if not paths:
        return False
    resolved: dict[str, str] = {}
    for rel in paths:
        full = os.path.join(wt, rel)
        try:
            with open(full, encoding="utf-8", newline="") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            return False
        fixed = _resolve_pin_hunks(text)
        if fixed is None:
            return False
        resolved[rel] = fixed
    for rel, fixed in resolved.items():
        with open(os.path.join(wt, rel), "w", encoding="utf-8", newline="") as fh:
            fh.write(fixed)
    add = _run(wt, "git", "add", "--", *resolved.keys(), check=False)
    if add.returncode != 0:
        return False
    # 편집기를 띄우지 않게 GIT_EDITOR=true (core.editor 는 환경변수에 밀린다).
    cont = subprocess.run(
        [
            "git",
            "-c",
            "user.email=promote@foms.local",
            "-c",
            "user.name=FOMS Promote",
            "cherry-pick",
            "--continue",
        ],
        cwd=wt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        env={**os.environ, "GIT_EDITOR": "true"},
        timeout=120,
    )
    return cont.returncode == 0


# 승격 판정을 하는 도구 파일. 이 폴더 내용이 origin/deploy 와 다르면 옛 도구다.
PROMOTE_TOOL_FILES = (
    "tools/harness/promote_own_to_production.py",
    "tools/harness/promote_completeness.py",
    "tools/harness/promote_file_compare.py",
)
STALE_TOOL_REF = "origin/deploy"
EXIT_STALE_TOOL = 4


def stale_promote_tool_files(project_root: str, ref: str = STALE_TOOL_REF) -> list[str]:
    """이 폴더의 승격 도구 파일 중 ``ref`` 와 내용이 다른 것을 돌려준다.

    2026-10-15: origin 보다 389커밋 뒤처진 메인 체크아웃에서 돌리자 파일 내용 판정
    (c0ef5f12d) 이전의 옛 판정이 돌아 "missing baseline deps=8" 오탐이 났다.
    ``ref`` 가 없으면(테스트용 임시 저장소 등) 판정할 수 없으니 빈 목록.
    """
    if _run(project_root, "git", "rev-parse", "--verify", "--quiet", ref, check=False).returncode != 0:
        return []
    diff = _run(
        project_root, "git", "diff", "--name-only", ref, "--", *PROMOTE_TOOL_FILES, check=False
    )
    if diff.returncode != 0:
        return []
    return [line.strip() for line in (diff.stdout or "").splitlines() if line.strip()]


def promote_own_commits(
    project_root: str,
    shas: Sequence[str],
    *,
    worktree_parent: str | None = None,
    keep_on_error: bool = True,
    allow_incomplete: bool = False,
    allow_stale_tool: bool = False,
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
        allow_stale_tool: 도구 파일이 origin/deploy 와 달라도 진행(도구를 고치는 중일 때만).
        base_ref: production 정본.
        gh_runner: 테스트용 gh 주입.
        title/body: PR 제목·본문.
    반환:
        exit code (0=성공, 1=오류, 2=incomplete/empty, 3=충돌, 4=옛 도구).
    """
    if not shas:
        print("승격할 자기 세션 커밋이 없습니다.", file=sys.stderr)
        return 2

    fetch = _run(project_root, "git", "fetch", "origin", "production", check=False)
    if fetch.returncode != 0:
        print(fetch.stderr or "git fetch failed", file=sys.stderr)
        return 1

    if not allow_stale_tool:
        _run(project_root, "git", "fetch", "origin", "deploy", check=False)
        stale = stale_promote_tool_files(project_root)
        if stale:
            print(
                "옛 승격 도구입니다(이 폴더가 origin/deploy 보다 뒤처졌거나 도구 파일이 바뀜): "
                + ", ".join(stale)
                + "\n최신 기준 작업 폴더에서 다시 실행하세요: "
                "git worktree add c:/tmp/foms-promote origin/deploy\n"
                "도구 자체를 고치는 중일 때만 --allow-stale-tool 로 우회.",
                file=sys.stderr,
            )
            return EXIT_STALE_TOOL

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
            if cp.returncode != 0 and _try_resolve_pin_conflicts(wt):
                print(f"핀 충돌 자동 해결(사전순 max): {sha[:8]}")
                continue
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

        # 승격 범위 대조(ablation v2 §6): worktree 에 얹힌 커밋 수가 요청 SHA 수와 다르면
        # 타 세션 커밋 혼입·누락 신호 — PR 을 열지 않고 충돌과 같은 등급으로 멈춘다.
        applied = _count_range(wt, base_ref)
        if applied != len(ordered):
            print(
                f"승격 범위 불일치: worktree 에 {applied}개 커밋, 요청 {len(ordered)}개 — "
                f"타 세션 커밋 혼입/누락 의심. worktree 보존: {wt}",
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
    parser.add_argument(
        "--allow-stale-tool",
        action="store_true",
        help="도구 파일이 origin/deploy 와 달라도 진행 (도구를 고치는 중일 때만)",
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
        allow_stale_tool=args.allow_stale_tool,
        base_ref=args.base_ref,
        title=args.title,
        body=args.body,
    )


if __name__ == "__main__":
    raise SystemExit(main())
