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


def test_promote_range_mismatch_blocks_pr(tmp_path: Path, monkeypatch: Any) -> None:
    """cherry-pick 뒤 worktree 커밋 수가 요청 SHA 수와 다르면(타 세션 혼입·누락) PR 을 열지 않는다.

    ablation v2 §6 MOVE-TO-CODE 3순위 — 승격 PR 에 타 세션 커밋이 동반된 사고(`7357924c0`)의 코드 가드.
    """
    mod = _load()
    local, _bare, dep, feat = _setup(tmp_path)
    gh_calls: list[list[str]] = []

    def fake_gh(cwd: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        gh_calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "https://example/pr/9" + chr(10), "")

    real_run = mod._run

    def spy_run(cwd: str, *args: str, check: bool = True):
        result = real_run(cwd, *args, check=check)
        if args and args[0] == "git" and "cherry-pick" in args and result.returncode == 0:
            # 타 세션 커밋이 끼어든 상황을 흉내 낸다
            real_run(cwd, "git", "-c", "user.email=x@x", "-c", "user.name=x", "commit", "--allow-empty", "-m", "stray", check=False)
        return result

    monkeypatch.setattr(mod, "_run", spy_run)
    wt = tmp_path / "wts"
    wt.mkdir()
    code = mod.promote_own_commits(str(local), [dep, feat], worktree_parent=str(wt), gh_runner=fake_gh)
    assert code == 3, "범위 불일치는 충돌과 같은 등급으로 멈춰야 한다"
    assert gh_calls == [], "PR 을 열면 안 된다"


# ── 핀 충돌 자동 해결 (SPEC 2026-10-13-promote-completeness-content-aware §3.4) ──

_C = ("-c", "user.email=t@t", "-c", "user.name=t")
_FILLER = "".join(f"filler{i}\n" for i in range(10))


def _write_commit(local: Path, name: str, content: str, msg: str) -> str:
    (local / name).write_text(content, encoding="utf-8")
    _git(local, "add", name)
    _git(local, *_C, "commit", "-m", msg)
    return _sha(local)


def _setup_pages(
    tmp_path: Path, prod_line: str, dep_line: str, feat_line: str
) -> tuple[Path, Path, str]:
    """production·deploy 가 page.html 첫 줄에서 갈라진 저장소. feat 는 첫 줄과 끝 줄을 바꾼다."""
    bare = tmp_path / "remote.git"
    local = tmp_path / "local"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(local))
    _git(local, "checkout", "-b", "production")
    _write_commit(local, "page.html", "head ?v=20261011a\n" + _FILLER + "body1\n", "base")
    _git(local, "push", "-u", "origin", "production")
    _git(local, "checkout", "-b", "deploy")
    _write_commit(local, "page.html", dep_line + _FILLER + "body1\n", "dep")
    feat = _write_commit(local, "page.html", feat_line + _FILLER + "body2\n", "feat")
    _git(local, "checkout", "production")
    _write_commit(local, "page.html", prod_line + _FILLER + "body1\n", "prod")
    _git(local, "push", "origin", "production")
    _git(local, "checkout", "deploy")
    return local, bare, feat


def _ok_gh(cwd: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, 0, "https://example/pr/1\n", "")


def test_pin_only_conflict_auto_resolved_with_max_token(tmp_path: Path) -> None:
    """충돌이 핀 줄뿐이면 자동 해결 — 토큰은 사전순 max, 다른 변경은 그대로."""
    mod = _load()
    local, bare, feat = _setup_pages(
        tmp_path,
        "head ?v=20261012r\n",
        "head ?v=20261012d\n",
        "head ?v=20261012e\n",
    )
    wt = tmp_path / "wts"
    wt.mkdir()
    code = mod.promote_own_commits(
        str(local), [feat], worktree_parent=str(wt), gh_runner=_ok_gh
    )
    assert code == 0
    refs = subprocess.check_output(
        ["git", "for-each-ref", "--format=%(refname)", "refs/heads/promote/"],
        cwd=bare,
        text=True,
    ).split()
    assert len(refs) == 1
    content = subprocess.check_output(
        ["git", "show", f"{refs[0]}:page.html"], cwd=bare, text=True
    )
    assert content.splitlines()[0] == "head ?v=20261012r"
    assert content.splitlines()[-1] == "body2"
    assert "<<<<<<<" not in content


def test_non_pin_conflict_exits_3_and_keeps_worktree(tmp_path: Path) -> None:
    """핀이 아닌 줄의 충돌 → exit 3, worktree 보존."""
    mod = _load()
    local, _bare, feat = _setup_pages(
        tmp_path,
        "prod-head ?v=20261012r\n",
        "dep-head ?v=20261012d\n",
        "feat-head ?v=20261012e\n",
    )
    wt = tmp_path / "wts"
    wt.mkdir()
    code = mod.promote_own_commits(
        str(local),
        [feat],
        worktree_parent=str(wt),
        gh_runner=_ok_gh,
        allow_incomplete=True,
    )
    assert code == 3
    kept = [p for p in wt.iterdir() if p.name.startswith("foms-prod-own-")]
    assert len(kept) == 1
    assert "<<<<<<<" in (kept[0] / "page.html").read_text(encoding="utf-8")
