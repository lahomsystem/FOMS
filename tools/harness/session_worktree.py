"""세션별 worktree 격리 (Phase 1) 수명주기 CLI.

create : origin/deploy 기반 세션 worktree + session/<name> 브랜치 생성
list   : 세션 worktree 현황(브랜치·ahead·dirty·locked·detached)
sync   : rebase origin/deploy (소유 검증 후, ledger 승계는 post-rewrite 훅)
cleanup: 기본 dry-run 보고, --remove 시 clean+merged만 제거

설계 정본: docs/plans/2026-07-27-session-worktree-isolation-phase1.md
소유 판정은 deploy_push_scope의 세션 worktree union 규칙과 한 쌍이다.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
import types
import os
from pathlib import Path

WT_PREFIX = "foms-s-"
BRANCH_PREFIX = "session/"
DEFAULT_PARENT = "c:/tmp" if os.name == "nt" else "/tmp"
SOFT_LIMIT = 3  # ponytail: 스펙 §2.6 동시 상한 2-3, 초과는 경고만
USAGE_LOG = os.path.join("docs", "harness", "runtime", "session_worktree_usage.log")

# F1-v4: post-rewrite 훅 — rebase가 재작성한 SHA를 ledger에 자동 승계한다.
# 훅은 worktree마다가 아니라 공유 git-common-dir(모든 worktree가 공유)에 설치되므로
# 세션 worktree 어느 것을 만들 때 처음 설치되든 이후 전부에 적용된다.
POST_REWRITE_HOOK_SENTINEL = "# foms-session-worktree post-rewrite v1"

#: --name 허용 문자 — 단일 경로 컴포넌트이자 안전한 git ref 조각.
#: 경로 구분자·`..`·공백·git ref 금지문자(~^:?*[\)를 전부 배제한다.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

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
    except (OSError, ValueError) as exc:
        print(f"[warn] usage log 기록 실패: {exc}", file=sys.stderr)


def _range_shas(wt: Path, end_ref: str = "HEAD") -> list[str]:
    """origin/deploy..<end_ref> SHA 목록(오래된 순, 소문자).

    파라미터:
        wt: 대상 worktree 경로.
        end_ref: 범위 종점(기본 HEAD).
    """
    _, out = _git(wt, "log", "--reverse", "--format=%H", f"origin/deploy..{end_ref}")
    return [s.strip().lower() for s in out.splitlines() if s.strip()]


def _ledger() -> types.ModuleType:
    """session_commit_ledger 모듈 지연 로드 (harness 디렉터리 sys.path 주입, 중복 삽입 방지)."""
    harness_dir = str(Path(__file__).resolve().parent)
    if harness_dir not in sys.path:
        sys.path.insert(0, harness_dir)
    import session_commit_ledger
    return session_commit_ledger


def _post_rewrite_hook_content() -> str:
    """post-rewrite 훅 셸 스크립트 내용을 만든다.

    `record_rewrite_ledger.py`의 **절대경로를 프로비저닝 시점에 고정**해 굽는다.
    훅 실행 시점에 `git rev-parse --show-toplevel`로 다시 찾으면, 재작성이
    일어난 worktree 자신의 체크아웃에는 그 파일이 없을 수 있다 — 예를 들어
    이 harness 파일이 추가되기 이전 커밋 기반으로 만들어진 worktree, 또는
    이 스크립트만 격리해 실행하는 테스트 fixture. 실측: 이 문제로 훅이
    "No such file or directory"로 조용히 실패하는 것을 확인했다(F1-v4 초판).
    이 CLI(`session_worktree.py`) 자신은 항상 실제 harness 디렉터리에서
    실행되므로, 그 `__file__` 기준 절대경로를 쓰면 어느 worktree에서 rebase가
    일어나든 동일한 실제 스크립트를 가리킨다. `POST_REWRITE_HOOK_SENTINEL`은
    이 훅이 우리 것임을 표시해 자가치유(§`_ensure_post_rewrite_hook`)를 가능케
    하고, `|| { ... }`는 python 실행 자체가 실패해도(예: python 미설치) 무로그
    swallow 없이 harness 로그에 남기고 fail-open한다(FOMS 훅 규칙). 로그 줄에는
    재작성이 일어난 worktree(`$PWD`)를 함께 적어 어느 창의 rebase였는지 추적한다
    — 훅은 메인 트리를 포함한 전 worktree가 공유하므로 출처가 없으면 무의미하다.
    """
    script = Path(__file__).resolve().parent / "record_rewrite_ledger.py"
    main_tree = Path(__file__).resolve().parents[2]
    log_dir = (main_tree / "docs" / "harness" / "runtime").as_posix()
    log_path = f"{log_dir}/record_rewrite_ledger.log"
    return (
        "#!/bin/sh\n"
        f"{POST_REWRITE_HOOK_SENTINEL}\n"
        f'python "{script.as_posix()}" "$@" || {{ '
        f'mkdir -p "{log_dir}" 2>/dev/null; '
        f'echo "$(date) [$PWD] post-rewrite ledger 승계 실패 (record_rewrite_ledger 실행 불가)" >> "{log_path}" 2>/dev/null; '
        "exit 0; }\n"
    )


def _post_rewrite_hook_path(wt: Path) -> Path | None:
    """공유 post-rewrite 훅 파일 경로(git-common-dir 기준). 조회 실패 시 None."""
    code, common_dir = _git(wt, "rev-parse", "--git-common-dir", check=False)
    if code != 0 or not common_dir:
        return None
    hooks_dir = Path(common_dir)
    if not hooks_dir.is_absolute():
        hooks_dir = wt / hooks_dir
    return hooks_dir / "hooks" / "post-rewrite"


def _ensure_post_rewrite_hook(root: Path) -> None:
    """공유 post-rewrite 훅을 프로비저닝한다(없으면 생성, sentinel 있으면 자가치유).

    훅은 `git rev-parse --git-common-dir`가 가리키는 모든 worktree 공유 위치에
    설치한다 — 어느 worktree를 만들 때든 한 번만 설치되면 이후 모든 rebase에
    적용된다. 파일이 없으면 새로 만들고, 있고 내용이 다르면 두 갈래로
    나뉜다: **sentinel이 있으면**(=우리가 이전에 설치한 훅, 예를 들어 메인
    트리 브랜치 체크아웃으로 스크립트가 사라졌다가 돌아온 경우) 최신 내용으로
    **자가치유(재작성)**하고, **sentinel이 없으면**(타 도구가 설치한 훅일 수
    있음) **덮어쓰지 않고 경고만** 남긴다.

    파라미터:
        root: 훅 위치를 조회할 기준 저장소/worktree 경로.
    반환:
        없음(부작용: 훅 파일 생성/자가치유 + 실행권한 부여, 필요 시 stderr 경고).
    """
    hook_path = _post_rewrite_hook_path(root)
    if hook_path is None:
        print("[warn] git-common-dir 조회 실패 — post-rewrite 훅 설치 생략", file=sys.stderr)
        return
    hook_content = _post_rewrite_hook_content()
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8", errors="replace")
        if existing == hook_content:
            return
        if POST_REWRITE_HOOK_SENTINEL not in existing:
            print(
                f"[warn] 기존 post-rewrite 훅 발견({hook_path}) — 덮어쓰지 않음. "
                "ledger 자동 승계가 필요하면 내용을 수동 병합하세요.",
                file=sys.stderr,
            )
            return
        # sentinel 있음 = 우리 훅인데 내용이 최신과 다름 — 자가치유(아래 write로 재작성)
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(hook_content, encoding="utf-8", newline="\n")
    try:
        hook_path.chmod(hook_path.stat().st_mode | 0o111)  # Windows Git은 셔뱅으로 실행하나 실행비트도 부여
    except OSError:
        pass


def _is_safe_name(name: str) -> bool:
    """`--name` 이 단일 안전 경로 컴포넌트인지 검사한다.

    `nested/demo` 같은 이름은 worktree 를 `<parent>/foms-s-nested/demo` 에 만들어
    basename 을 `demo` 로 바꾼다 — `foms-s-` 프리픽스에 의존하는 list/sync/cleanup·
    union 소유 판정·`run.py`/`migrations/env.py` DDL 차단이 전부 무력화된다.
    그래서 경로 구분자·`..`·절대경로·공백·git ref 금지문자를 아예 거부한다.

    파라미터:
        name: 사용자가 준 worktree/브랜치 이름.
    반환:
        영숫자로 시작하고 `[A-Za-z0-9._-]` 만 쓰며 `..`/`.lock` 이 없으면 True.
    """
    return bool(_SAFE_NAME_RE.match(name)) and ".." not in name and not name.endswith(".lock")


def cmd_create(args: argparse.Namespace) -> int:
    """origin/deploy 기반 세션 worktree 생성. 기존 브랜치 재사용 금지(-b)."""
    name = args.name or time.strftime("s%m%d-%H%M%S")
    if not _is_safe_name(name):
        print(
            f"[refuse] --name 부적합: {name!r} — 영숫자로 시작하는 단일 이름만 허용"
            " (`/`·`\\`·`..`·공백·절대경로·git ref 금지문자 불가)",
            file=sys.stderr,
        )
        return EXIT_REFUSE
    root = repo_root()
    _git(root, "fetch", "origin", "deploy", check=False)  # 오프라인 허용
    if _git(root, "rev-parse", "--verify", "origin/deploy", check=False)[0] != 0:
        print("[error] origin/deploy ref 없음 — 네트워크 연결 후 재시도", file=sys.stderr)
        return EXIT_GIT
    _ensure_post_rewrite_hook(root)
    existing = session_worktrees(root)
    if len(existing) >= SOFT_LIMIT:
        print(f"[warn] 세션 worktree {len(existing)}개 활성 — 권장 상한 {SOFT_LIMIT}. cleanup 권장.")
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
        _, dirty = _status_porcelain(wt)
        flags = ("locked " if it["locked"] else "") + ("dirty" if dirty else "clean")
        print(f"{wt}  {branch}  ahead={ahead if code == 0 else '?'}  {flags}")
    return EXIT_OK


# harness 자체 부기 파일(SSOT: session_commit_ledger.py / 본 파일 USAGE_LOG) —
# 사용자 미커밋 변경과 혼동하지 않도록 dirty 판정에서 제외한다. 디렉터리 전체가
# 아니라 알려진 파일 2개(+ledger의 .tmp)로 좁혀, 향후 그 경로에 추가될 다른
# 파일까지 조용히 가려버리는 일을 막는다(F4).
_LEDGER_STATUS_EXCLUDES = (
    ":!docs/harness/runtime/session_commit_ledger.json*",
    ":!docs/harness/runtime/session_worktree_usage.log",
)


def _status_porcelain(wt: Path) -> tuple[int, str]:
    """worktree dirty 판정. harness 자체 부기 파일(ledger·usage log)은 제외한다."""
    return _git(wt, "status", "--porcelain", "--", ".", *_LEDGER_STATUS_EXCLUDES, check=False)


def _rebase_in_progress(wt: Path) -> bool:
    """rebase-merge/rebase-apply 디렉터리 존재 여부 (worktree는 .git이 파일이라 --git-path 필수)."""
    for sub in ("rebase-merge", "rebase-apply"):
        _, p = _git(wt, "rev-parse", "--git-path", sub)
        pp = Path(p) if os.path.isabs(p) else wt / p
        if pp.exists():
            return True
    return False


def cmd_sync(args: argparse.Namespace) -> int:
    """fetch + rebase origin/deploy. 세션 worktree 전용(ledger 승계는 post-rewrite 훅).

    소유 검증(F1-v4 — post-rewrite 훅 ledger 승계): 매 호출마다 동일하게
    `origin/deploy..HEAD`가 ledger union의 부분집합인지만 확인한다. 마커나
    patch-id 회계 같은 특수 분기가 없다 — rebase가 커밋 SHA를 재작성해도
    `cmd_create`가 설치한 공유 post-rewrite 훅(`record_rewrite_ledger.py`)이
    그 순간 old→new 승계를 ledger에 이미 반영해두므로, `--ledger-only` 복구
    호출도 표준 검증을 그대로 통과한다(v1~v3의 신뢰 창·회계 기계를 전부
    제거했다). 훅이 설치되지 않은 환경(수동 git 조작 등)에서 rebase하면
    ledger가 승계되지 않아 refuse가 나는 것이 안전한 기본값이다.
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
        hook_path = _post_rewrite_hook_path(wt)
        where = str(hook_path) if hook_path else "경로 조회 실패(git-common-dir)"
        print(
            f"  post-rewrite 훅({where}) 미설치/손상이 원인일 수 있음 — "
            "session_worktree.py create가 sentinel 훅을 자가치유합니다.",
            file=sys.stderr,
        )
        return EXIT_REFUSE
    if unknown:  # --allow-foreign 우회는 무흔적이면 안 된다 — 감사 1줄
        _usage_log(wt, f"sync --allow-foreign 승인 {len(unknown)}커밋: " + ", ".join(s[:8] for s in unknown[:10]))

    if not args.ledger_only:
        _git(wt, "fetch", "origin", "deploy")
        r = subprocess.run(["git", "rebase", "origin/deploy"], cwd=str(wt))
        if r.returncode != 0:
            print("[conflict] rebase 충돌 — 임의 해결 금지. 해결 → `git rebase --continue` → `sync --ledger-only`", file=sys.stderr)
            return EXIT_CONFLICT

    # ledger 갱신은 하지 않는다: rebase가 재작성한 SHA는 공유 post-rewrite 훅이
    # **세션별로** 승계한다. 여기서 `origin/deploy..HEAD` 전체를 한 세션 키로
    # set_session_shas 하면 여러 세션이 함께 쓴 worktree에서 마지막 세션이 남의
    # 커밋까지 소유하게 되고, 그 ledger를 단일 세션 기준으로 읽는
    # push_own_session_commits/promote 헬퍼가 타 세션 커밋을 실어 나른다.
    post = _range_shas(wt)
    print(f"[ok] sync 완료 — origin/deploy..HEAD {len(post)}커밋 (ledger 승계는 post-rewrite 훅 담당)")
    return EXIT_OK


def cmd_cleanup(args: argparse.Namespace) -> int:
    """세션 worktree 정리. 기본 dry-run 보고, --remove 시 clean+merged만 제거."""
    root = repo_root()
    if _git(root, "fetch", "origin", "deploy", check=False)[0] != 0:
        print("[warn] fetch origin deploy 실패 — merged 판정이 stale할 수 있음(오프라인?)", file=sys.stderr)
    rows = session_worktrees(root)
    force_target = Path(args.force_path).resolve() if args.force_path else None
    if force_target is not None and not any(it["path"] == force_target for it in rows):
        print(f"[refuse] --force-path 대상이 세션 worktree 목록에 없음: {force_target}", file=sys.stderr)
        return EXIT_REFUSE
    cwd = Path.cwd().resolve()
    for it in rows:
        wt, branch, locked = it["path"], it["branch"], it["locked"]
        force_this = force_target is not None and force_target == wt
        if cwd == wt or wt in cwd.parents:
            if force_this:
                print(f"[refuse] --force-path 대상이 현재 셸 cwd 내부: {wt} (다른 창/폴더에서 실행)", file=sys.stderr)
                return EXIT_REFUSE
            print(f"[keep] {wt} — 현재 셸 cwd 내부 (다른 창에서 실행)")
            continue
        if force_this:
            if not args.yes:
                print("[refuse] --force-path는 --yes 동반 필수 (미커밋 변경 영구 소실 경고)", file=sys.stderr)
                return EXIT_REFUSE
            rc = _force_remove(root, wt, branch)
            if rc != EXIT_OK:
                return rc
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
    if _git(root, "worktree", "prune", check=False)[0] != 0:
        print("[warn] worktree prune 실패 — 잔여 worktree 메타데이터 수동 확인 필요", file=sys.stderr)
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


def _untracked_files(wt: Path) -> list[str]:
    """미추적 파일 목록(harness 부기 파일 제외) — stash create 미커버 확인용."""
    _, out = _git(wt, "status", "--porcelain", "--untracked-files=all", "--", ".", *_LEDGER_STATUS_EXCLUDES, check=False)
    return [line[3:] for line in out.splitlines() if line.startswith("??")]


def _backup_ref(root: Path, wt: Path, branch: str | None) -> bool:
    """제거 전 백업 ref를 만든다. detached HEAD면 커밋 소실 방지의 유일한 안전장치다.

    브랜치가 있으면 원 브랜치가 그대로 보존되므로 백업 ref 실패는 경고로 끝내고,
    detached면 백업 ref가 없는 순간 HEAD 커밋이 dangling 되므로 실패 시 False를
    돌려 제거 자체를 중단시킨다.

    파라미터:
        root: 메인 저장소 루트(ref 생성 대상).
        wt: 제거 대상 worktree.
        branch: worktree 체크아웃 브랜치. None이면 detached HEAD.
    반환:
        제거를 진행해도 되면 True, 중단해야 하면 False.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if branch:
        backup = f"backup/{branch.replace('/', '-')}-{stamp}"
        if _git(root, "branch", backup, branch, check=False)[0] != 0:
            print(f"[warn] 백업 ref 생성 실패({backup}) — 원 브랜치({branch})는 보존됨", file=sys.stderr)
            return True
        print(f"[backup] 브랜치 백업 ref: {backup}")
        return True
    code, head = _git(wt, "rev-parse", "HEAD", check=False)
    if code != 0 or not head:
        print("[refuse] detached HEAD SHA 조회 실패 — 백업 불가, 강제 제거 중단", file=sys.stderr)
        return False
    backup = f"backup/detached-{stamp}"
    if _git(root, "branch", backup, head, check=False)[0] != 0:
        print(f"[refuse] detached HEAD 백업 ref 생성 실패({backup}) — 커밋 소실 위험, 강제 제거 중단", file=sys.stderr)
        return False
    print(f"[backup] detached HEAD({head[:10]}) 백업 ref: {backup}")
    return True


def _force_remove(root: Path, wt: Path, branch: str | None) -> int:
    """dirty/unmerged 강제 제거 — dirty는 stash create로 dangling 백업, 브랜치는 보존+백업 ref.

    반환:
        EXIT_OK 제거 성공, EXIT_REFUSE 백업 ref 확보 실패로 중단(제거 안 함),
        EXIT_GIT 제거 시도 후에도 worktree가 남음(파일 잠금 등, F5).
    """
    if not _backup_ref(root, wt, branch):
        return EXIT_REFUSE
    _, stash_sha = _git(wt, "stash", "create", check=False)
    if stash_sha:
        print(f"[backup] 미커밋 변경 dangling 커밋 {stash_sha} — 복구: git stash store {stash_sha}")
    else:
        print("[warn] stash create 결과 없음 — 추적 변경 없음(미추적 신규 파일은 아래 별도 확인)")
    untracked = _untracked_files(wt)
    if untracked:
        preview = ", ".join(untracked[:10])
        more = f" 외 {len(untracked) - 10}개" if len(untracked) > 10 else ""
        print(f"[warn] 미추적 파일 {len(untracked)}개는 stash에 포함되지 않아 백업되지 않음: {preview}{more}")
        # ponytail: stash create는 untracked 미포함. `git stash push -u`로 별도 백업 가능하나
        # 공유 stash 오염 금지 규칙상 자동 실행하지 않는다 — 필요하면 --force-path 전 수동 백업.
    _git(root, "worktree", "unlock", str(wt), check=False)
    code, _ = _git(root, "worktree", "remove", "--force", str(wt), check=False)
    if code != 0 and wt.exists():
        shutil.rmtree(wt, ignore_errors=True)  # push_own_session_commits._cleanup과 동일 폴백
        _git(root, "worktree", "prune", check=False)
    if wt.exists():
        print(f"[warn] {wt} — 강제 제거 미완료(파일 잠금 추정), 수동 확인 필요. 브랜치는 보존됨({branch})", file=sys.stderr)
        return EXIT_GIT
    _usage_log(root, f"force-remove {wt}")
    print(f"[removed:force] {wt} — 브랜치 보존({branch})")
    return EXIT_OK


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
    s = sub.add_parser("sync", help="rebase origin/deploy (ledger 승계는 post-rewrite 훅)")
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
