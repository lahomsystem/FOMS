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
import json
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


def _conflict_marker_path(wt: Path) -> Path:
    """rebase 충돌 시 검증 통과한 pre 스냅샷을 적어두는 gitdir 내부 마커 경로.

    `_rebase_in_progress`와 동일 패턴(`--git-path`가 상대경로면 wt 기준 해석)을
    쓴다. gitdir 내부라 worktree status를 오염시키지 않는다.
    """
    _, p = _git(wt, "rev-parse", "--git-path", "foms_sync_conflict.json")
    return Path(p) if os.path.isabs(p) else wt / p


def _read_conflict_marker(marker: Path) -> dict[str, list[str]] | None:
    """마커의 pre SHA·patch-id 목록을 읽는다. 없거나 손상되면 None(=신뢰하지 않음)."""
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    pre, pre_patch_ids = data.get("pre"), data.get("pre_patch_ids")
    if not (isinstance(pre, list) and all(isinstance(s, str) for s in pre)):
        return None
    if not (isinstance(pre_patch_ids, list) and all(isinstance(s, str) for s in pre_patch_ids)):
        return None
    return {"pre": pre, "pre_patch_ids": pre_patch_ids}


def _write_conflict_marker(marker: Path, pre: list[str], pre_patch_ids: list[str]) -> None:
    """검증 통과한 pre SHA·patch-id 스냅샷을 마커에 기록한다."""
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"pre": pre, "pre_patch_ids": pre_patch_ids}), encoding="utf-8")


def _clear_conflict_marker(marker: Path) -> None:
    """마커 제거(있으면). 실패해도 다음 sync가 재정리하므로 무시."""
    try:
        marker.unlink(missing_ok=True)
    except OSError:
        pass


def _range_patch_ids(wt: Path, ref: str = "HEAD") -> dict[str, str]:
    """origin/deploy..<ref> 범위 각 커밋의 patch-id 사전 {sha: patch_id}(둘 다 소문자).

    `git log -p ... | git patch-id --stable` 파이프로 diff 내용 해시(patch-id)를
    얻는다. 충돌 해결로 파일 내용이 바뀌면 sha와 무관하게 patch-id도 달라진다
    — 이 성질로 재작성 슬롯과 진짜 foreign 커밋을 구분한다(F1-v3 전단사 회계).
    """
    log_proc = subprocess.run(
        ["git", "log", "-p", "--no-color", f"origin/deploy..{ref}"],
        cwd=str(wt), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    id_proc = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=str(wt), input=log_proc.stdout, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    out: dict[str, str] = {}
    for line in id_proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out[parts[1].lower()] = parts[0].lower()
    return out


def _recovery_accounting_passes(wt: Path, marker_data: dict[str, list[str]]) -> bool:
    """F1-v3 patch-id 전단사 회계 — 마커 기반 복구 검증의 핵심.

    post(origin/deploy..HEAD) 각 커밋의 patch-id가 마커의 pre patch-id 집합에
    있으면 "explained", 없으면 `unexplained_post`. pre patch-id 중 post 어디에도
    나타나지 않는 것은 충돌 해결로 재작성돼 사라진 "consumed_pre" 슬롯이다.
    `len(unexplained_post) <= len(consumed_pre)`일 때만 통과한다 — 충돌 해결로
    내용이 바뀐 커밋(정당한 재작성)은 슬롯 하나를 소비하고 슬롯 하나를 설명해
    통과하지만, merge/cherry-pick으로 유입된 진짜 foreign 커밋은 소비되지 않는
    unexplained 슬롯을 추가로 만들어 거부된다. ORIG_HEAD는 신뢰 신호로 쓰지
    않는다(merge/reset/pull/am도 갱신·영구 잔존해 round1·round2 모두 세탁 구멍이었다).
    """
    pre_patch_ids = set(marker_data["pre_patch_ids"])
    post_map = _range_patch_ids(wt)
    post_patch_ids = set(post_map.values())
    unexplained_post = [sha for sha, pid in post_map.items() if pid not in pre_patch_ids]
    consumed_pre = pre_patch_ids - post_patch_ids
    return len(unexplained_post) <= len(consumed_pre)


def cmd_sync(args: argparse.Namespace) -> int:
    """fetch + rebase origin/deploy + ledger 갱신. 세션 worktree 전용.

    소유 검증(F1-v3 — patch-id 전단사 회계): 원칙은 매 호출마다 **현재 HEAD**
    범위를 ledger union과 대조하는 것이다(최초 호출·마커 없는 `--ledger-only`
    모두 이 경로). 유일한 예외는 `--ledger-only`이고 직전 rebase 충돌 시 이
    worktree에 남긴 **마커**가 있을 때이며, 이때는 `_recovery_accounting_passes`
    (post 각 커밋의 patch-id를 마커의 pre patch-id와 전단사로 맞춰보는 회계)가
    통과해야만 재검증을 생략한다. ORIG_HEAD는 신뢰 신호로 전혀 쓰지 않는다 —
    round1(ORIG_HEAD 존재 시 신뢰)과 round2(마커+ORIG_HEAD 일치 시 신뢰) 둘 다
    `rebase --abort` 후 `merge`/`cherry-pick`으로 재현되는 세탁 구멍이었다(마커는
    남아있지만 그 시점 이후 상태 변화를 검증하지 않았기 때문). v3는 마커의
    "존재"가 아니라 마커가 설명하는 patch-id 회계로만 신뢰하므로, 마커가 아무리
    오래 남아있어도(A3) 그 사이 유입된 foreign 패치는 여전히 unexplained로
    잡힌다. `--allow-foreign`은 최후의 명시적 우회로 남긴다.
    """
    wt = Path(args.path).resolve() if args.path else repo_root()
    if not wt.name.lower().startswith(WT_PREFIX):
        print("[refuse] sync는 세션 worktree(foms-s-*) 안에서만 동작한다", file=sys.stderr)
        return EXIT_REFUSE
    scl = _ledger()
    marker = _conflict_marker_path(wt)

    if _rebase_in_progress(wt):
        print("[refuse] rebase 진행 중 — 해결 후 `git rebase --continue`, 그 다음 `sync --ledger-only`", file=sys.stderr)
        return EXIT_CONFLICT
    _, dirty = _status_porcelain(wt)
    if dirty and not args.ledger_only:
        print("[refuse] 미커밋 변경 존재 — 커밋 후 sync 재시도", file=sys.stderr)
        return EXIT_REFUSE

    # F1-v3 위생: 분기 앞에서 무조건 초기화 — 이후 사용 시점이 어느 분기를
    # 거쳤는지에 대한 암묵적 불변식에 의존하지 않는다(재리뷰 지적).
    pre: list[str] = []
    pre_patch_ids: list[str] = []

    marker_data = _read_conflict_marker(marker) if args.ledger_only else None
    recovered_via_marker = False
    if marker_data is not None:
        recovered_via_marker = _recovery_accounting_passes(wt, marker_data)
        if not recovered_via_marker and not args.allow_foreign:
            print(
                "[refuse] 복구 검증 실패 — 마커 이후 설명되지 않는 커밋이 있음"
                "(merge/cherry-pick 등 유입 의심). 임의 해결 금지.",
                file=sys.stderr,
            )
            print("  소유가 확실하면 --allow-foreign으로 명시 승인.", file=sys.stderr)
            return EXIT_REFUSE
        recovered_via_marker = True  # 회계 통과 또는 --allow-foreign 명시 우회

    if not recovered_via_marker:
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
            pre_patch_ids = list(_range_patch_ids(wt).values())

    if not args.ledger_only:
        _clear_conflict_marker(marker)  # 새 rebase 시도 전 잔존 마커 선삭제(A3 방어)
        _git(wt, "fetch", "origin", "deploy")
        r = subprocess.run(["git", "rebase", "origin/deploy"], cwd=str(wt))
        if r.returncode != 0:
            _write_conflict_marker(marker, pre, pre_patch_ids)
            print("[conflict] rebase 충돌 — 임의 해결 금지. 해결 → `git rebase --continue` → `sync --ledger-only`", file=sys.stderr)
            return EXIT_CONFLICT

    post = _range_shas(wt)
    sid = scl.latest_session_id(str(wt)) or "unknown"
    scl.set_session_shas(str(wt), sid, post)
    _clear_conflict_marker(marker)
    print(f"[ok] sync 완료 — ledger 갱신 session={sid}, {len(post)}커밋")
    return EXIT_OK


def cmd_cleanup(args: argparse.Namespace) -> int:
    """세션 worktree 정리. 기본 dry-run 보고, --remove 시 clean+merged만 제거."""
    root = repo_root()
    _git(root, "fetch", "origin", "deploy", check=False)
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
            if not _force_remove(root, wt, branch):
                return EXIT_GIT
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


def _untracked_files(wt: Path) -> list[str]:
    """미추적 파일 목록(harness 부기 파일 제외) — stash create 미커버 확인용."""
    _, out = _git(wt, "status", "--porcelain", "--untracked-files=all", "--", ".", *_LEDGER_STATUS_EXCLUDES, check=False)
    return [line[3:] for line in out.splitlines() if line.startswith("??")]


def _force_remove(root: Path, wt: Path, branch: str | None) -> bool:
    """dirty/unmerged 강제 제거 — dirty는 stash create로 dangling 백업, 브랜치는 보존+백업 ref.

    반환:
        최종 `wt.exists()` 재확인 기준 제거 성공 여부. False면 호출부
        (`cmd_cleanup`)가 거짓 성공을 보고하지 않고 EXIT_GIT으로 전파한다(F5).
    """
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
    if wt.exists():
        print(f"[warn] {wt} — 강제 제거 미완료(파일 잠금 추정), 수동 확인 필요. 브랜치는 보존됨({branch})", file=sys.stderr)
        return False
    _usage_log(root, f"force-remove {wt}")
    print(f"[removed:force] {wt} — 브랜치 보존({branch})")
    return True


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
