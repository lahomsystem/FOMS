"""check_deploy_drift · ci_watch 가 낡은 로컬 ref 로 거짓 판정하지 않는지(설계서 2026-11-02 F3).

2026-11-02: 운영 반영은 50초 만에 끝났는데, 로컬 origin/production 이 낡아 이미 더 새 배포로
덮인(REMOVED) 옛 머리를 "[누락] … 0커밋 뒤"로 판정해 21분을 헛기다렸다.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    harness = str(REPO_ROOT / "tools" / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


DRIFT = _load("check_deploy_drift_ut", REPO_ROOT / "tools" / "ops" / "check_deploy_drift.py")
CI_WATCH = _load("ci_watch_drift_ut", REPO_ROOT / "tools" / "harness" / "ci_watch.py")
TARGET = DRIFT.TARGETS[0]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


@pytest.fixture()
def chain(tmp_path: Path, monkeypatch) -> tuple[str, str, str]:
    """old → new 두 커밋과, new 의 후손이 아닌 곁가지 side."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "old")
    old = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "new")
    new = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", "-q", "-b", "side", old)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "side")
    side = _git(tmp_path, "rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    return old, new, side


def _run_check(monkeypatch, head: str, deployments: list[dict]):
    monkeypatch.setattr(DRIFT, "_resolve", lambda token, pid, target: ("env", "svc"))
    monkeypatch.setattr(DRIFT, "_deployments", lambda *a: deployments)
    real_git = DRIFT._git
    monkeypatch.setattr(
        DRIFT, "_git", lambda *args: head if args[:1] == ("rev-parse",) else real_git(*args)
    )
    return DRIFT.check(TARGET, "token", {TARGET.project: "pid"})


def _dep(sha: str, status: str) -> dict:
    return {"id": sha[:6], "status": status, "createdAt": "2026-11-02T11:48:48Z", "meta": {"commitHash": sha}}


def test_superseded_head_with_live_descendant_is_ok(chain, monkeypatch) -> None:
    old, new, _side = chain
    result = _run_check(monkeypatch, old, [_dep(new, "SUCCESS"), _dep(old, "REMOVED")])
    assert result.ok and result.deployed == new and "덮음" in result.note


def test_superseded_head_without_live_descendant_is_missing(chain, monkeypatch) -> None:
    old, _new, side = chain
    result = _run_check(monkeypatch, side, [_dep(old, "SUCCESS"), _dep(side, "REMOVED")])
    assert not result.ok


def test_live_head_is_ok(chain, monkeypatch) -> None:
    _old, new, _side = chain
    assert _run_check(monkeypatch, new, [_dep(new, "SUCCESS")]).ok


def test_fetch_failure_is_undetermined(monkeypatch) -> None:
    def failing_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 128, "", "fatal: unable to access")

    monkeypatch.setattr(DRIFT.subprocess, "run", failing_run)
    with pytest.raises(DRIFT.Undetermined):
        DRIFT._fetch(list(DRIFT.TARGETS))
    assert DRIFT.main(["--target", "production"]) == 2


def test_ci_watch_fetches_once_when_sha_is_not_local(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(CI_WATCH, "resolve_ref", lambda ref: "f" * 40 if calls else "")
    monkeypatch.setattr(
        CI_WATCH.subprocess, "run",
        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    assert CI_WATCH._fetch_and_resolve("ed31031f8", "production") == "f" * 40
    assert calls == [["git", "fetch", "-q", "origin", "production"]]
    source = (REPO_ROOT / "tools" / "harness" / "ci_watch.py").read_text(encoding="utf-8")
    assert "resolve_ref(args.sha) or _fetch_and_resolve(args.sha, args.branch)" in source
