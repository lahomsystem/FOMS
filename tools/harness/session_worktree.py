"""세션별 worktree 격리 (Phase 1) 수명주기 CLI.

create : origin/deploy 기반 세션 worktree + session/<name> 브랜치 생성
list   : 세션 worktree 현황(브랜치·ahead·dirty·locked·detached)
sync   : rebase origin/deploy + ledger 갱신 (소유 검증 후)
cleanup: 기본 dry-run 보고, --remove 시 clean+merged만 제거

설계 정본: docs/plans/2026-07-27-session-worktree-isolation-phase1.md
소유 판정은 deploy_push_scope의 세션 worktree union 규칙과 한 쌍이다.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import os
from pathlib import Path

WT_PREFIX = "foms-s-"
BRANCH_PREFIX = "session/"
DEFAULT_PARENT = "c:/tmp" if os.name == "nt" else "/tmp"
SOFT_LIMIT = 3  # ponytail: 스펙 §2.6 동시 상한 2-3, 초과는 경고만
USAGE_LOG = os.path.join("docs", "harness", "runtime", "session_worktree_usage.log")

EXIT_OK = 0
EXIT_REFUSE = 2
EXIT_CONFLICT = 3
EXIT_GIT = 4


def _utf8_stdio() -> None:
    """Windows cp949 콘솔에서 한글 출력 깨짐/UnicodeDecodeError 차단."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _git(cwd: Path | str, *args: str, check: bool = True) -> tuple[int, str]:
    """git 실행. (returncode, stdout). check=True면 실패 시 사람이 읽는 에러 + SystemExit(EXIT_GIT)."""
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        print(f"[git-error] git {' '.join(args)}\n{(proc.stderr or '').strip()}", file=sys.stderr)
        raise SystemExit(EXIT_GIT)
    return proc.returncode, (proc.stdout or "").strip()


def repo_root() -> Path:
    """현재 cwd가 속한 저장소(또는 worktree)의 최상위 경로."""
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel")[1]).resolve()


def session_worktrees(root: Path) -> list[dict]:
    """foms-s-* worktree 목록. 각 항목 {'path','branch'(None=detached),'locked'}."""
    _, out = _git(root, "worktree", "list", "--porcelain")
    items: list[dict] = []
    cur: dict | None = None
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            cur = {"path": Path(line[len("worktree "):]).resolve(), "branch": None, "locked": False}
        elif line.startswith("branch ") and cur is not None:
            cur["branch"] = line[len("branch refs/heads/"):]
        elif line.startswith("locked") and cur is not None:
            cur["locked"] = True
        elif line == "" and cur is not None:
            if cur["path"].name.lower().startswith(WT_PREFIX):
                items.append(cur)
            cur = None
    return items


def _usage_log(root: Path, msg: str) -> None:
    """kill criteria 측정용 사용 로그 1줄 append. 실패는 경고만(기능 무영향)."""
    try:
        p = root / USAGE_LOG
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    except OSError as exc:
        print(f"[warn] usage log 기록 실패: {exc}", file=sys.stderr)


def _range_shas(wt: Path) -> list[str]:
    """origin/deploy..HEAD SHA 목록(오래된 순, 소문자)."""
    _, out = _git(wt, "log", "--reverse", "--format=%H", "origin/deploy..HEAD")
    return [s.strip().lower() for s in out.splitlines() if s.strip()]


def _ledger():
    """session_commit_ledger 모듈 지연 로드 (harness 디렉터리 sys.path 주입)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import session_commit_ledger
    return session_commit_ledger


def cmd_create(args: argparse.Namespace) -> int:
    """origin/deploy 기반 세션 worktree 생성. 기존 브랜치 재사용 금지(-b)."""
    root = repo_root()
    _git(root, "fetch", "origin", "deploy", check=False)  # 오프라인 허용
    if _git(root, "rev-parse", "--verify", "origin/deploy", check=False)[0] != 0:
        print("[error] origin/deploy ref 없음 — 네트워크 연결 후 재시도", file=sys.stderr)
        return EXIT_GIT
    existing = session_worktrees(root)
    if len(existing) >= SOFT_LIMIT:
        print(f"[warn] 세션 worktree {len(existing)}개 활성 — 권장 상한 {SOFT_LIMIT}. cleanup 권장.")
    name = args.name or time.strftime("s%m%d-%H%M%S")
    branch = f"{BRANCH_PREFIX}{name}"
    if _git(root, "rev-parse", "--verify", f"refs/heads/{branch}", check=False)[0] == 0:
        print(f"[refuse] 브랜치 {branch} 이미 존재 — 다른 이름 사용 또는 cleanup 후 재시도", file=sys.stderr)
        return EXIT_REFUSE
    parent = Path(args.parent)
    parent.mkdir(parents=True, exist_ok=True)
    wt = parent / f"{WT_PREFIX}{name}"
    _git(root, "worktree", "add", "-b", branch, str(wt), "origin/deploy")
    env_src = root / ".env"
    if env_src.is_file():
        shutil.copy2(env_src, wt / ".env")
        print("[warn] .env 사본 복사됨 — c:/tmp 시크릿 잔존 주의(cleanup이 함께 삭제)")
    _usage_log(root, f"create {wt}")
    print(f"[ok] worktree: {wt}")
    print(f"[ok] branch  : {branch} (base origin/deploy)")
    print("주의: 메인 트리의 미커밋/미추적 변경은 이 worktree로 넘어오지 않는다.")
    print(f"다음: cd {wt}  →  claude / Cursor 폴더 열기 / codex exec")
    print("dev 서버: PORT=5001 python run.py (세션 worktree는 startup DDL 자동 생략)")
    return EXIT_OK


def cmd_list(_args: argparse.Namespace) -> int:
    """세션 worktree 현황 출력."""
    root = repo_root()
    rows = session_worktrees(root)
    if not rows:
        print("(세션 worktree 없음)")
        return EXIT_OK
    for it in rows:
        wt, branch = it["path"], it["branch"] or "(detached)"
        code, ahead = _git(wt, "rev-list", "--count", "origin/deploy..HEAD", check=False)
        _, dirty = _git(wt, "status", "--porcelain", check=False)
        flags = ("locked " if it["locked"] else "") + ("dirty" if dirty else "clean")
        print(f"{wt}  {branch}  ahead={ahead if code == 0 else '?'}  {flags}")
    return EXIT_OK


def _status_porcelain(wt: Path) -> tuple[int, str]:
    """worktree dirty 판정. harness 자체 부기 경로(docs/harness/runtime)는 제외한다.

    append_commit(session_commit_ledger)이 worktree 내부에 자체 ledger 파일을
    쓰므로(정상 repo는 .gitignore로 걸러지나, 옛 커밋 기반 worktree는 그 항목이
    없을 수 있다) 사용자 미커밋 변경과 혼동하지 않도록 pathspec으로 제외한다.
    """
    return _git(wt, "status", "--porcelain", "--", ".", ":!docs/harness/runtime", check=False)


def _rebase_in_progress(wt: Path) -> bool:
    """rebase-merge/rebase-apply 디렉터리 존재 여부 (worktree는 .git이 파일이라 --git-path 필수)."""
    for sub in ("rebase-merge", "rebase-apply"):
        _, p = _git(wt, "rev-parse", "--git-path", sub)
        pp = Path(p) if os.path.isabs(p) else wt / p
        if pp.exists():
            return True
    return False


def cmd_sync(args: argparse.Namespace) -> int:
    """fetch + rebase origin/deploy + ledger 갱신. 세션 worktree 전용.

    소유 검증: rebase 전 범위가 이 worktree ledger union의 부분집합일 때만
    진행한다 — cherry-pick/merge로 유입된 타 세션 커밋의 세탁 차단.
    """
    wt = Path(args.path).resolve() if args.path else repo_root()
    if not wt.name.lower().startswith(WT_PREFIX):
        print("[refuse] sync는 세션 worktree(foms-s-*) 안에서만 동작한다", file=sys.stderr)
        return EXIT_REFUSE
    scl = _ledger()

    if _rebase_in_progress(wt):
        print("[refuse] rebase 진행 중 — 해결 후 `git rebase --continue`, 그 다음 `sync --ledger-only`", file=sys.stderr)
        return EXIT_CONFLICT
    _, dirty = _status_porcelain(wt)
    if dirty and not args.ledger_only:
        print("[refuse] 미커밋 변경 존재 — 커밋 후 sync 재시도", file=sys.stderr)
        return EXIT_REFUSE

    pre = _range_shas(wt)
    union = scl.all_known_shas(str(wt))
    unknown = [s for s in pre if not scl.sha_in_list(s, union)]
    if unknown and not args.allow_foreign:
        print(f"[refuse] ledger 밖 커밋 {len(unknown)}개 — 이 worktree에서 만든 커밋이 아님(cherry-pick/merge 유입?):", file=sys.stderr)
        for s in unknown[:10]:
            print(f"  {s[:10]}", file=sys.stderr)
        print("  소유가 확실하면 --allow-foreign으로 명시 승인.", file=sys.stderr)
        return EXIT_REFUSE

    if not args.ledger_only:
        _git(wt, "fetch", "origin", "deploy")
        r = subprocess.run(["git", "rebase", "origin/deploy"], cwd=str(wt))
        if r.returncode != 0:
            print("[conflict] rebase 충돌 — 임의 해결 금지. 해결 → `git rebase --continue` → `sync --ledger-only`", file=sys.stderr)
            return EXIT_CONFLICT

    post = _range_shas(wt)
    sid = scl.latest_session_id(str(wt)) or "unknown"
    scl.set_session_shas(str(wt), sid, post)
    print(f"[ok] sync 완료 — ledger 갱신 session={sid}, {len(post)}커밋")
    return EXIT_OK


def cmd_cleanup(args: argparse.Namespace) -> int:
    """세션 worktree 정리. 기본 dry-run 보고, --remove 시 clean+merged만 제거."""
    root = repo_root()
    _git(root, "fetch", "origin", "deploy", check=False)
    cwd = Path.cwd().resolve()
    for it in session_worktrees(root):
        wt, branch, locked = it["path"], it["branch"], it["locked"]
        force_this = bool(args.force_path) and Path(args.force_path).resolve() == wt
        if cwd == wt or wt in cwd.parents:
            print(f"[keep] {wt} — 현재 셸 cwd 내부 (다른 창에서 실행)")
            continue
        if force_this:
            if not args.yes:
                print("[refuse] --force-path는 --yes 동반 필수 (미커밋 변경 영구 소실 경고)", file=sys.stderr)
                return EXIT_REFUSE
            _force_remove(root, wt, branch)
            continue
        if locked:
            print(f"[keep] {wt} — locked. 해제: git worktree unlock \"{wt}\"")
            continue
        if branch is None:
            print(f"[keep] {wt} — detached HEAD, 수동 확인 필요")
            continue
        if not branch.startswith(BRANCH_PREFIX):
            print(f"[keep] {wt} — 비세션 브랜치({branch}), 불가침")
            continue
        code, dirty = _status_porcelain(wt)
        if code != 0:
            print(f"[keep] {wt} — 상태 조회 실패")
            continue
        merged = _git(root, "merge-base", "--is-ancestor", branch, "origin/deploy", check=False)[0] == 0
        if dirty:
            print(f"[keep] {wt} — dirty (미커밋 변경 존재)")
        elif not merged:
            print(f"[keep] {wt} — unmerged (origin/deploy 미반영 커밋)")
        elif not args.remove:
            print(f"[removable] {wt} ({branch}) — 실제 제거: cleanup --remove")
        else:
            _safe_remove(root, wt, branch)
    _git(root, "worktree", "prune", check=False)
    return EXIT_OK


def _safe_remove(root: Path, wt: Path, branch: str) -> None:
    """clean+merged worktree 무-force 제거 + branch -d. 실패는 keep 보고(전파 금지)."""
    code, _ = _git(root, "worktree", "remove", str(wt), check=False)
    if code != 0:
        print(f"[keep] {wt} — remove 실패(파일 락 추정), 다음 cleanup에서 재시도")
        return
    _git(root, "branch", "-d", branch, check=False)
    _usage_log(root, f"remove {wt}")
    print(f"[removed] {wt} ({branch})")


def _force_remove(root: Path, wt: Path, branch: str | None) -> None:
    """dirty/unmerged 강제 제거 — dirty는 stash create로 dangling 백업, 브랜치는 보존+백업 ref."""
    _, stash_sha = _git(wt, "stash", "create", check=False)
    if stash_sha:
        print(f"[backup] 미커밋 변경 dangling 커밋 {stash_sha} — 복구: git stash store {stash_sha}")
    else:
        print("[warn] stash create 결과 없음 — 미추적 신규 파일은 백업되지 않는다")
    if branch:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = f"backup/{branch.replace('/', '-')}-{stamp}"
        _git(root, "branch", backup, branch, check=False)
        print(f"[backup] 브랜치 백업 ref: {backup}")
    _git(root, "worktree", "unlock", str(wt), check=False)
    code, _ = _git(root, "worktree", "remove", "--force", str(wt), check=False)
    if code != 0 and wt.exists():
        shutil.rmtree(wt, ignore_errors=True)  # push_own_session_commits._cleanup과 동일 폴백
        _git(root, "worktree", "prune", check=False)
    _usage_log(root, f"force-remove {wt}")
    print(f"[removed:force] {wt} — 브랜치 보존({branch})")


def main(argv: list[str] | None = None) -> int:
    """CLI 엔트리포인트."""
    _utf8_stdio()
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="세션 worktree 생성")
    c.add_argument("--name", default=None)
    c.add_argument("--parent", default=DEFAULT_PARENT)
    c.set_defaults(fn=cmd_create)
    ls = sub.add_parser("list", help="세션 worktree 현황")
    ls.set_defaults(fn=cmd_list)
    s = sub.add_parser("sync", help="rebase origin/deploy + ledger 갱신")
    s.add_argument("--path", default=None)
    s.add_argument("--ledger-only", action="store_true")
    s.add_argument("--allow-foreign", action="store_true")
    s.set_defaults(fn=cmd_sync)
    cl = sub.add_parser("cleanup", help="세션 worktree 정리 (기본 dry-run)")
    cl.add_argument("--remove", action="store_true")
    cl.add_argument("--force-path", default=None)
    cl.add_argument("--yes", action="store_true")
    cl.set_defaults(fn=cmd_cleanup)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
