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
