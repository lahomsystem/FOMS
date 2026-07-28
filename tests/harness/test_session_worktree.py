"""세션 worktree 격리 Phase1 — scope 계약 + CLI 통합 테스트."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[2] / "tools" / "harness"
SW = HARNESS / "session_worktree.py"
sys.path.insert(0, str(HARNESS))

pytestmark = pytest.mark.skipif(
    not SW.exists(), reason="session_worktree.py 미구현 (Task 2에서 활성화)"
)


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """CLI 실행 — 자식은 PYTHONUTF8=1로 cp949 사고 차단."""
    env = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run(
        [sys.executable, str(SW), *args], cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )
    return r.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """bare origin + deploy 브랜치 작업 클론 (origin/deploy 추적 ref 포함)."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    (work / "a.txt").write_text("1", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-m", "init")
    _git(work, "branch", "-M", "deploy")
    _git(work, "push", "-u", "origin", "deploy")
    return work


def _make_wt(repo: Path, tmp_path: Path, name: str) -> Path:
    r = _run(repo, "create", "--name", name, "--parent", str(tmp_path / "wts"))
    assert r.returncode == 0, r.stderr
    wt = tmp_path / "wts" / f"foms-s-{name}"
    _git(wt, "config", "user.email", "t@t")
    _git(wt, "config", "user.name", "t")
    return wt


def _commit(wt: Path, fname: str, msg: str) -> str:
    (wt / fname).write_text(fname, encoding="utf-8")
    _git(wt, "add", fname)
    _git(wt, "commit", "-m", msg)
    return _git(wt, "rev-parse", "HEAD")


# ---- scope 계약 (Task 1) ----

def test_scope_union_own_across_sessions(repo: Path, tmp_path: Path) -> None:
    """세션 키가 여러 개 쌓여도 union이면 own — P3 거짓 문제의 해법 검증."""
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "u1")
    s1 = _commit(wt, "b.txt", "day1")
    scl.append_commit(str(wt), "sid-day1", s1)
    s2 = _commit(wt, "c.txt", "day2")
    scl.append_commit(str(wt), "sid-day2", s2)
    # 오늘의 새 세션 id로도 own (union 규칙)
    assert classify_deploy_scope(str(wt), "sid-day3").kind == "own"


def test_scope_flags_unledgered_as_foreign(repo: Path, tmp_path: Path) -> None:
    """ledger 밖 커밋(cherry-pick/merge 유입 재현)은 foreign — 세탁 경로 차단 검증."""
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "u2")
    s1 = _commit(wt, "b.txt", "mine")
    scl.append_commit(str(wt), "sid1", s1)
    _commit(wt, "d.txt", "foreign-like")  # ledger 미기록
    assert classify_deploy_scope(str(wt), "sid1").kind == "foreign"


def test_scope_empty_ledger_falls_back_to_unknown(repo: Path, tmp_path: Path) -> None:
    """훅 없는 창(Codex) 재현: ledger 없음 → 기존 unknown 경로(=ask) 유지."""
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "u3")
    _commit(wt, "b.txt", "no-hook")
    assert classify_deploy_scope(str(wt), "some-sid").kind == "unknown"


# ---- CLI (Task 2) ----

def test_create_makes_worktree_and_branch(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t1")
    assert wt.is_dir()
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "session/t1"


def test_create_refuses_existing_branch(repo: Path, tmp_path: Path) -> None:
    """-b + 사전 존재 검사 — 기존 세션 브랜치 리셋으로 커밋 유실 방지(-B 금지) 검증."""
    _make_wt(repo, tmp_path, "t2")
    r = _run(repo, "create", "--name", "t2", "--parent", str(tmp_path / "wts2"))
    assert r.returncode == 2
    assert "이미 존재" in (r.stdout + r.stderr)


def test_list_includes_detached(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t3")
    _git(wt, "checkout", "--detach")
    r = _run(repo, "list")
    assert r.returncode == 0
    assert "(detached)" in r.stdout


def test_sync_rebases_and_scope_is_own(repo: Path, tmp_path: Path) -> None:
    """핵심 계약: origin/deploy 전진 → sync → rebase 완료 + scope=own."""
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "t4")
    old = _commit(wt, "b.txt", "session work")
    scl.append_commit(str(wt), "sid1", old)
    # 타 세션의 deploy 전진 재현
    (repo / "a.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "other session")
    _git(repo, "push", "origin", "deploy")
    r = _run(wt, "sync")
    assert r.returncode == 0, r.stderr
    assert _git(wt, "rev-parse", "HEAD") != old
    assert classify_deploy_scope(str(wt), "sid1").kind == "own"


def test_sync_refuses_unledgered_commits(repo: Path, tmp_path: Path) -> None:
    """ledger 밖 커밋 포함 시 sync 거부 — 세탁 경로 차단."""
    wt = _make_wt(repo, tmp_path, "t5")
    _commit(wt, "b.txt", "unledgered")
    r = _run(wt, "sync")
    assert r.returncode == 2
    assert "ledger 밖" in (r.stdout + r.stderr)


def test_sync_refuses_outside_session_worktree(repo: Path) -> None:
    r = _run(repo, "sync")
    assert r.returncode == 2


def test_cleanup_default_is_dry_run(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t6")
    r = _run(repo, "cleanup")
    assert r.returncode == 0
    assert "[removable]" in r.stdout
    assert wt.exists()


def test_cleanup_remove_flag_removes_merged_clean(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t7")
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0, r.stderr
    assert not wt.exists()
    assert "session/t7" not in _git(repo, "branch", "--list", "session/t7")


def test_cleanup_keeps_dirty(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t8")
    (wt / "wip.txt").write_text("wip", encoding="utf-8")
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0
    assert wt.exists()
    assert "dirty" in r.stdout


def test_cleanup_keeps_unmerged(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t9")
    _commit(wt, "c.txt", "unmerged work")
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0
    assert wt.exists()
    assert "unmerged" in r.stdout


def test_cleanup_keeps_non_session_branch(repo: Path, tmp_path: Path) -> None:
    """디렉터리명이 foms-s-*여도 브랜치가 session/*이 아니면 불가침."""
    wt = _make_wt(repo, tmp_path, "t10")
    _git(wt, "checkout", "-b", "experiment/x")
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0
    assert wt.exists()


# ---- 리뷰 반영 (fix round 1) ----

def test_cleanup_force_path_backs_up_and_removes_dirty(repo: Path, tmp_path: Path) -> None:
    """--force-path: dirty worktree도 강제 제거하되 브랜치 백업 ref를 남기고 원 브랜치는 보존한다."""
    wt = _make_wt(repo, tmp_path, "t12")
    (wt / "wip.txt").write_text("wip", encoding="utf-8")
    r = _run(repo, "cleanup", "--force-path", str(wt), "--yes")
    assert r.returncode == 0, r.stderr
    assert not wt.exists()
    assert "session/t12" in _git(repo, "branch", "--list", "session/t12")
    assert "backup/session-t12-" in _git(repo, "branch", "--list", "backup/session-t12-*")


def test_cleanup_force_path_mismatch_refuses(repo: Path, tmp_path: Path) -> None:
    """--force-path 대상이 세션 worktree 목록에 없으면 exit 2로 거부한다(F2)."""
    _make_wt(repo, tmp_path, "t13")
    bogus = tmp_path / "wts" / "foms-s-does-not-exist"
    r = _run(repo, "cleanup", "--force-path", str(bogus), "--yes")
    assert r.returncode == 2


def test_sync_conflict_then_ledger_only_recovers_and_scope_is_own(repo: Path, tmp_path: Path) -> None:
    """F1 회귀: rebase 충돌 → 해결 → `sync --ledger-only`가 ORIG_HEAD 기준으로 own 판정을 유지한다."""
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "t14")
    (wt / "a.txt").write_text("session-side", encoding="utf-8")
    _git(wt, "add", "a.txt")
    _git(wt, "commit", "-m", "session edits a.txt")
    mine = _git(wt, "rev-parse", "HEAD")
    scl.append_commit(str(wt), "sid1", mine)

    # 타 세션이 동일 파일을 수정 후 deploy에 반영 — rebase 충돌 유도
    (repo / "a.txt").write_text("other-side", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "other session edits a.txt")
    _git(repo, "push", "origin", "deploy")

    r = _run(wt, "sync")
    assert r.returncode == 3, r.stdout + r.stderr  # EXIT_CONFLICT

    # 충돌 해결 후 계속
    (wt / "a.txt").write_text("resolved", encoding="utf-8")
    _git(wt, "add", "a.txt")
    _git(wt, "-c", "core.editor=true", "rebase", "--continue")

    r2 = _run(wt, "sync", "--ledger-only")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert classify_deploy_scope(str(wt), "sid1").kind == "own"


def test_cleanup_keeps_locked(repo: Path, tmp_path: Path) -> None:
    """locked worktree는 --remove에도 불가침이다."""
    wt = _make_wt(repo, tmp_path, "t15")
    _git(repo, "worktree", "lock", str(wt))
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0
    assert wt.exists()
    assert "locked" in r.stdout


# ---- 리뷰 반영 (fix round 2) — F1 재설계: ORIG_HEAD 신뢰 → 충돌 마커 신뢰 ----

def test_sync_ledger_only_refuses_after_merge_of_foreign_branch(repo: Path, tmp_path: Path) -> None:
    """F1 round2 필수 회귀: merge로 유입된 foreign 커밋은 ORIG_HEAD 잔존과 무관하게 거부된다.

    round1(ORIG_HEAD 존재 시 그 범위로 신뢰)은 `git merge` 후에도 ORIG_HEAD가
    갱신·잔존해 세탁 구멍이었다 — 마커가 없으면 현재 HEAD 범위로 검증해야 한다.
    """
    import session_commit_ledger as scl

    wt = _make_wt(repo, tmp_path, "t18")
    mine = _commit(wt, "b.txt", "session work")
    scl.append_commit(str(wt), "sid1", mine)

    (repo / "c.txt").write_text("other", encoding="utf-8")
    _git(repo, "add", "c.txt")
    _git(repo, "commit", "-m", "other session unrelated file")
    _git(repo, "push", "origin", "deploy")

    _git(wt, "fetch", "origin", "deploy")
    _git(wt, "-c", "core.editor=true", "merge", "origin/deploy", "-m", "merge foreign")

    r = _run(wt, "sync", "--ledger-only")
    assert r.returncode == 2, r.stdout + r.stderr


def test_sync_ledger_only_refuses_after_reset_and_foreign_cherry_pick(repo: Path, tmp_path: Path) -> None:
    """F1 round2 필수 회귀: reset --hard(ORIG_HEAD 갱신) 후 타 커밋 cherry-pick도 거부된다."""
    import session_commit_ledger as scl

    wt = _make_wt(repo, tmp_path, "t19")
    mine = _commit(wt, "b.txt", "session work")
    scl.append_commit(str(wt), "sid1", mine)

    foreign = _commit(repo, "d.txt", "foreign work")  # ledger 미기록

    _git(wt, "reset", "--hard", "HEAD")  # ORIG_HEAD 갱신 재현(round1이면 이후 신뢰됐을 값)
    _git(wt, "cherry-pick", foreign)

    r = _run(wt, "sync", "--ledger-only")
    assert r.returncode == 2, r.stdout + r.stderr


# ---- 리뷰 반영 (fix round 3) — F1-v3: patch-id 전단사 회계 (A1/A2/A3 실증 대응) ----

def test_sync_ledger_only_refuses_after_abort_then_merge_foreign(repo: Path, tmp_path: Path) -> None:
    """A1 재현: 충돌 → abort → merge foreign → ledger-only → exit 2, foreign 미등록.

    round1/round2는 ORIG_HEAD를 신뢰 신호로 썼는데, `rebase --abort` 후
    `merge`를 해도 ORIG_HEAD가 갱신·잔존해 두 라운드 모두 여기서 세탁됐다.
    v3는 마커의 patch-id 회계로만 판단하므로 abort 후 유입된 foreign은
    여전히 unexplained로 잡혀 거부된다.
    """
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    # a.txt와 무관한 foreign 브랜치를 분기 전 상태에서 미리 만들어 둔다 —
    # 나중에 병합할 때 a.txt 충돌이 재발하지 않도록(테스트 셋업 자체가
    # 충돌로 죽지 않게) 하기 위함.
    _git(repo, "branch", "foreign-branch")
    _git(repo, "checkout", "foreign-branch")
    (repo / "f.txt").write_text("foreign", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", "foreign work on separate branch")
    _git(repo, "checkout", "deploy")

    wt = _make_wt(repo, tmp_path, "t20")
    (wt / "a.txt").write_text("session-side", encoding="utf-8")
    _git(wt, "add", "a.txt")
    _git(wt, "commit", "-m", "session edits a.txt")
    mine = _git(wt, "rev-parse", "HEAD")
    scl.append_commit(str(wt), "sid1", mine)

    (repo / "a.txt").write_text("other-side", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "other session edits a.txt")
    _git(repo, "push", "origin", "deploy")

    r = _run(wt, "sync")
    assert r.returncode == 3, r.stdout + r.stderr  # 충돌, 마커 기록됨

    _git(wt, "rebase", "--abort")  # wt는 mine 상태로 복귀, 마커는 잔존(A1 조건)

    _git(wt, "fetch", str(repo), "foreign-branch")
    _git(wt, "-c", "core.editor=true", "merge", "FETCH_HEAD", "-m", "merge foreign after abort")

    r2 = _run(wt, "sync", "--ledger-only")
    assert r2.returncode == 2, r2.stdout + r2.stderr
    assert classify_deploy_scope(str(wt), "sid1").kind != "own"


def test_sync_ledger_only_refuses_after_continue_then_cherry_pick_foreign(repo: Path, tmp_path: Path) -> None:
    """A2 재현: 충돌 → resolve → continue → cherry-pick foreign → ledger-only → exit 2.

    복구 자체는(마커 회계로) 통과 가능한 상태이지만, continue 이후 추가로
    유입된 foreign 커밋은 전단사 회계에서 소비되지 않는 unexplained 슬롯을
    만들어 거부되어야 한다.
    """
    import session_commit_ledger as scl

    wt = _make_wt(repo, tmp_path, "t21")
    (wt / "a.txt").write_text("session-side", encoding="utf-8")
    _git(wt, "add", "a.txt")
    _git(wt, "commit", "-m", "session edits a.txt")
    mine = _git(wt, "rev-parse", "HEAD")
    scl.append_commit(str(wt), "sid1", mine)

    (repo / "a.txt").write_text("other-side", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "other session edits a.txt")
    _git(repo, "push", "origin", "deploy")

    r = _run(wt, "sync")
    assert r.returncode == 3, r.stdout + r.stderr

    (wt / "a.txt").write_text("resolved", encoding="utf-8")
    _git(wt, "add", "a.txt")
    _git(wt, "-c", "core.editor=true", "rebase", "--continue")

    foreign = _commit(repo, "g.txt", "foreign work2")  # ledger 미기록, worktree가 object store 공유라 fetch 불요
    _git(wt, "cherry-pick", foreign)

    r2 = _run(wt, "sync", "--ledger-only")
    assert r2.returncode == 2, r2.stdout + r2.stderr


def test_sync_ledger_only_recovers_when_resolution_rewrites_patch_content(repo: Path, tmp_path: Path) -> None:
    """F1-v3 필수: 충돌 해결로 patch 내용 자체가 바뀐 커밋도 exit 0 + own으로 복구된다.

    엄격 포함관계(post의 모든 patch-id가 pre 집합의 부분집합)였다면 이 케이스가
    거짓 거부(false refuse)였을 것이다 — 해결된 커밋은 diff 내용이 바뀌어
    patch-id도 달라지기 때문(F1 원증상 재발 지점). 전단사 회계
    (unexplained_post <= consumed_pre)는 이 슬롯 교체를 정확히 1:1로 허용한다.
    """
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "t22")
    (wt / "a.txt").write_text("session-side", encoding="utf-8")
    _git(wt, "add", "a.txt")
    _git(wt, "commit", "-m", "session edits a.txt")
    mine = _git(wt, "rev-parse", "HEAD")
    scl.append_commit(str(wt), "sid1", mine)

    (repo / "a.txt").write_text("other-side", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "other session edits a.txt")
    _git(repo, "push", "origin", "deploy")

    r = _run(wt, "sync")
    assert r.returncode == 3, r.stdout + r.stderr

    # 해결 시 patch 내용을 원본(session-side)과 다르게 재작성 — patch-id가 바뀐다.
    (wt / "a.txt").write_text("resolved-with-different-content", encoding="utf-8")
    _git(wt, "add", "a.txt")
    _git(wt, "-c", "core.editor=true", "rebase", "--continue")

    r2 = _run(wt, "sync", "--ledger-only")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert classify_deploy_scope(str(wt), "sid1").kind == "own"


def test_sync_ledger_only_refuses_new_foreign_merge_with_stale_marker(repo: Path, tmp_path: Path) -> None:
    """A3 재현: 마커가 잔존한 채(그 사이 정당한 추가 커밋까지 쌓인 뒤) 새로 유입된
    foreign 병합도 전단사 회계로 거부된다 — 마커의 '존재'가 아니라 그 순간의
    회계 결과만 신뢰함을 검증한다.
    """
    import session_commit_ledger as scl

    _git(repo, "branch", "foreign-branch2")
    _git(repo, "checkout", "foreign-branch2")
    (repo / "h.txt").write_text("foreign3", encoding="utf-8")
    _git(repo, "add", "h.txt")
    _git(repo, "commit", "-m", "foreign work on separate branch 2")
    _git(repo, "checkout", "deploy")

    wt = _make_wt(repo, tmp_path, "t23")
    (wt / "a.txt").write_text("session-side", encoding="utf-8")
    _git(wt, "add", "a.txt")
    _git(wt, "commit", "-m", "session edits a.txt")
    mine = _git(wt, "rev-parse", "HEAD")
    scl.append_commit(str(wt), "sid1", mine)

    (repo / "a.txt").write_text("other-side", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "other session edits a.txt")
    _git(repo, "push", "origin", "deploy")

    r = _run(wt, "sync")
    assert r.returncode == 3, r.stdout + r.stderr  # 마커 기록(pre=[mine] 시점)

    _git(wt, "rebase", "--abort")

    # "시간이 지나며" 세션이 정당한 커밋을 하나 더 쌓는다 — 마커는 그대로(A3).
    later = _commit(wt, "later.txt", "more session work")
    scl.append_commit(str(wt), "sid1", later)

    _git(wt, "fetch", str(repo), "foreign-branch2")
    _git(wt, "-c", "core.editor=true", "merge", "FETCH_HEAD", "-m", "merge foreign much later")

    r2 = _run(wt, "sync", "--ledger-only")
    assert r2.returncode == 2, r2.stdout + r2.stderr
