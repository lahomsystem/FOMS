"""push_own_session_commits 통합 테스트."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    harness = str(REPO_ROOT / "tools" / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    path = REPO_ROOT / "tools" / "harness" / "push_own_session_commits.py"
    name = "push_own_ut"
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
    name = "ledger_ut3"
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


def test_own_only_push_excludes_foreign(tmp_path: Path) -> None:
    """자기 SHA 만 원격 tip 에 반영되고 타 세션 SHA 는 남는다."""
    runner = _load()
    ledger = _load_ledger()

    bare = tmp_path / "remote.git"
    local = tmp_path / "local"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(local))
    _git(local, "checkout", "-b", "deploy")
    (local / "README").write_text("base\n", encoding="utf-8")
    _git(local, "add", "README")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "base")
    _git(local, "push", "-u", "origin", "deploy")

    (local / "calc.txt").write_text("calc\n", encoding="utf-8")
    _git(local, "add", "calc.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "calc")
    calc = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=local, text=True
    ).strip()
    ledger.append_commit(str(local), "sess-calc", calc)

    (local / "notif.txt").write_text("notif\n", encoding="utf-8")
    _git(local, "add", "notif.txt")
    _git(local, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "notif")
    notif = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=local, text=True
    ).strip()
    ledger.append_commit(str(local), "sess-notif", notif)

    wt_parent = tmp_path / "wts"
    wt_parent.mkdir()
    code = runner.push_own_commits(
        str(local),
        [notif],
        worktree_parent=str(wt_parent),
    )
    assert code == 0

    remote_tip = subprocess.check_output(
        ["git", "rev-parse", "deploy"], cwd=bare, text=True
    ).strip()
    # tip should be cherry-picked notif equivalent — message notif, tree has notif.txt but not calc
    # After cherry-pick of notif only onto base, tip != notif sha (new sha) but parents from base
    show = subprocess.check_output(
        ["git", "log", "-1", "--format=%s", remote_tip],
        cwd=bare,
        text=True,
    ).strip()
    assert show == "notif"

    # calc file must not be on remote tip tree
    ls = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", remote_tip],
        cwd=bare,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "notif.txt" in ls
    assert "calc.txt" not in ls
