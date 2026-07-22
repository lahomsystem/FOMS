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


def _init_repo_with_deploy(tmp_path: Path) -> Path:
    """bare remote + local clone on deploy with one base commit."""
    bare = tmp_path / "remote.git"
    local = tmp_path / "local"
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
