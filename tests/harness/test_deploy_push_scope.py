"""deploy_push_scope 단위 테스트 (오늘 사고 fixture 포함)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scope():
    harness = str(REPO_ROOT / "tools" / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    path = REPO_ROOT / "tools" / "harness" / "deploy_push_scope.py"
    name = "deploy_push_scope_ut"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_ledger():
    harness = str(REPO_ROOT / "tools" / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    path = REPO_ROOT / "tools" / "harness" / "session_commit_ledger.py"
    name = "session_commit_ledger_ut2"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo_with_deploy(tmp_path: Path, name: str = "local") -> Path:
    """bare remote + local clone on deploy with one base commit.

    name 으로 클론 디렉터리명을 바꿀 수 있다(세션 worktree `foms-s-*` 재현용).
    """
    bare = tmp_path / "remote.git"
    local = tmp_path / name
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(local))
    _git(local, "checkout", "-b", "deploy")
    (local / "README").write_text("base\n", encoding="utf-8")
    _git(local, "add", "README")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "base")
    _git(local, "push", "-u", "origin", "deploy")
    return local


def test_empty_scope(tmp_path: Path) -> None:
    """원격과 동기면 empty."""
    scope = _load_scope()
    local = _init_repo_with_deploy(tmp_path)
    result = scope.classify_deploy_scope(str(local), "sess-a")
    assert result.kind == "empty"


def test_own_only(tmp_path: Path) -> None:
    """레저에 있는 커밋만 있으면 own."""
    scope = _load_scope()
    ledger = _load_ledger()
    local = _init_repo_with_deploy(tmp_path)
    (local / "a.txt").write_text("a\n", encoding="utf-8")
    _git(local, "add", "a.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "own")
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=local, text=True
    ).strip()
    ledger.append_commit(str(local), "sess-a", sha)
    result = scope.classify_deploy_scope(str(local), "sess-a")
    assert result.kind == "own"
    assert sha.lower() in result.shas


def test_foreign_incident_pattern(tmp_path: Path) -> None:
    """오늘 사고: 타 세션 SHA + 내 SHA → foreign."""
    scope = _load_scope()
    ledger = _load_ledger()
    local = _init_repo_with_deploy(tmp_path)

    (local / "calc.txt").write_text("wd\n", encoding="utf-8")
    _git(local, "add", "calc.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "calc")
    calc_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=local, text=True
    ).strip()
    ledger.append_commit(str(local), "sess-calc", calc_sha)

    (local / "notif.txt").write_text("n\n", encoding="utf-8")
    _git(local, "add", "notif.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "notif")
    notif_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=local, text=True
    ).strip()
    ledger.append_commit(str(local), "sess-notif", notif_sha)

    result = scope.classify_deploy_scope(str(local), "sess-notif")
    assert result.kind == "foreign"
    assert any(s.startswith(calc_sha[:8].lower()) for s in result.foreign_shas)
    assert "타 세션" in result.label


def test_unknown_without_ledger(tmp_path: Path) -> None:
    """커밋은 있으나 레저 없으면 unknown."""
    scope = _load_scope()
    local = _init_repo_with_deploy(tmp_path)
    (local / "x.txt").write_text("x\n", encoding="utf-8")
    _git(local, "add", "x.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "x")
    result = scope.classify_deploy_scope(str(local), "sess-z")
    assert result.kind == "unknown"


def _commit_file(local: Path, name: str) -> str:
    """파일 1개 커밋 후 SHA 반환."""
    (local / name).write_text(name, encoding="utf-8")
    _git(local, "add", name)
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", name)
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=local, text=True, encoding="utf-8"
    ).strip()


def test_session_worktree_union_is_own(tmp_path: Path) -> None:
    """세션 worktree: 세션 키가 여러 개여도 union 이면 own(P3 거짓 문제 해법)."""
    scope = _load_scope()
    ledger = _load_ledger()
    wt = _init_repo_with_deploy(tmp_path, "foms-s-u1")
    ledger.append_commit(str(wt), "sid-day1", _commit_file(wt, "b.txt"))
    ledger.append_commit(str(wt), "sid-day2", _commit_file(wt, "c.txt"))
    # 오늘의 새 세션 id 로도 own
    assert scope.classify_deploy_scope(str(wt), "sid-day3").kind == "own"


def test_session_worktree_relative_root(tmp_path: Path, monkeypatch) -> None:
    """상대경로 root('.') 로도 세션 worktree 판정 — E2E 검증에서 적발된 결함 회귀."""
    scope = _load_scope()
    ledger = _load_ledger()
    wt = _init_repo_with_deploy(tmp_path, "foms-s-rel")
    ledger.append_commit(str(wt), "sid1", _commit_file(wt, "b.txt"))
    monkeypatch.chdir(wt)
    assert scope._is_session_worktree(".")
    assert scope.classify_deploy_scope(".", "other-sid").kind == "own"


def test_session_worktree_unledgered_is_foreign(tmp_path: Path) -> None:
    """세션 worktree: ledger 밖 커밋(cherry-pick 유입 재현)은 foreign 유지."""
    scope = _load_scope()
    ledger = _load_ledger()
    wt = _init_repo_with_deploy(tmp_path, "foms-s-u2")
    ledger.append_commit(str(wt), "sid1", _commit_file(wt, "b.txt"))
    _commit_file(wt, "d.txt")  # ledger 미기록
    result = scope.classify_deploy_scope(str(wt), "sid1")
    assert result.kind == "foreign"
    assert "ledger 밖" in result.label


def test_session_worktree_empty_ledger_falls_back(tmp_path: Path) -> None:
    """세션 worktree 라도 ledger 가 비면 기존 unknown 경로(=ask) 폴백."""
    scope = _load_scope()
    wt = _init_repo_with_deploy(tmp_path, "foms-s-u3")
    _commit_file(wt, "b.txt")
    assert scope.classify_deploy_scope(str(wt), "some-sid").kind == "unknown"
