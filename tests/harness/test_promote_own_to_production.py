"""promote_own_to_production TDD."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    harness = str(REPO_ROOT / "tools" / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    path = REPO_ROOT / "tools" / "harness" / "promote_own_to_production.py"
    name = "promote_own_ut"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


def _sha(cwd: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=cwd, text=True
    ).strip()


def _setup(tmp_path: Path) -> tuple[Path, Path, str, str]:
    bare = tmp_path / "remote.git"
    local = tmp_path / "local"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(local))
    _git(local, "checkout", "-b", "production")
    (local / "shared.txt").write_text("base\n", encoding="utf-8")
    _git(local, "add", "shared.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "base")
    _git(local, "push", "-u", "origin", "production")

    _git(local, "checkout", "-b", "deploy")
    (local / "shared.txt").write_text("dep\n", encoding="utf-8")
    _git(local, "add", "shared.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "dep")
    dep = _sha(local)
    (local / "shared.txt").write_text("feat\n", encoding="utf-8")
    _git(local, "add", "shared.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "feat")
    feat = _sha(local)
    _git(local, "push", "-u", "origin", "deploy")
    return local, bare, dep, feat


def test_incomplete_blocks_without_allow(tmp_path: Path) -> None:
    """feat만이면 completeness incomplete → exit 2, gh 미호출."""
    mod = _load()
    local, _bare, _dep, feat = _setup(tmp_path)
    calls: list[Any] = []

    def fake_gh(cwd: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append((cwd, list(args)))
        return subprocess.CompletedProcess(args, 0, "https://example/pr/1\n", "")

    wt = tmp_path / "wts"
    wt.mkdir()
    code = mod.promote_own_commits(
        str(local),
        [feat],
        worktree_parent=str(wt),
        gh_runner=fake_gh,
    )
    assert code == 2
    assert calls == []


def test_promote_creates_pr_not_direct_production_push(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """complete set → promo branch push + gh --base production, never HEAD:production."""
    mod = _load()
    local, bare, dep, feat = _setup(tmp_path)
    gh_calls: list[list[str]] = []
    push_cmds: list[list[str]] = []

    def fake_gh(cwd: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        gh_calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "https://example/pr/9\n", "")

    real_run = mod._run

    def spy_run(cwd: str, *args: str, check: bool = True):
        if len(args) >= 2 and args[0] == "git" and args[1] == "push":
            push_cmds.append(list(args))
        return real_run(cwd, *args, check=check)

    monkeypatch.setattr(mod, "_run", spy_run)

    wt = tmp_path / "wts"
    wt.mkdir()
    code = mod.promote_own_commits(
        str(local),
        [dep, feat],
        worktree_parent=str(wt),
        gh_runner=fake_gh,
    )
    assert code == 0
    assert gh_calls, "gh pr create must run"
    flat = " ".join(" ".join(c) for c in gh_calls)
    assert "--base" in flat and "production" in flat
    assert all("HEAD:production" not in " ".join(c) for c in push_cmds)

    # promo branch exists on remote (not production tip = feat message necessarily)
    branches = subprocess.check_output(
        ["git", "branch", "-a"], cwd=bare, text=True
    )
    assert "promote/own-" in branches or "tmp/own-prod-" in branches
