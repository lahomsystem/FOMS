"""푸시 가드·커밋 원장이 '명령이 실제로 도는 저장소'로 판정하는지(설계서 2026-11-02 F1·F2).

2026-11-02 계측: 훅은 메인 체크아웃에서 돌고 세션은 `cd <워크트리> && git push` 로 일한다.
가드가 메인(10-21 에 멈춘 로컬 deploy, 앞선 rebase 사본 8개)을 보고 판정해 30일 동안
deploy 푸시 승인 요청이 468번 떴고, 원장에는 메인 HEAD(남의 커밋)가 적혔다.

임시 git 저장소로 그 모양을 그대로 만든다 — 메인(origin/deploy 보다 앞선 남의 커밋 1개),
세션 워크트리 `foms-s-x`(자기 커밋 1개 + 원장), 다른 origin 의 저장소.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "tools" / "harness"
HOOKS = REPO_ROOT / ".claude" / "hooks"
SID = "sess-effective-repo-test"


def _load(name: str, path: Path):
    """모듈을 파일 경로로 로드한다. 훅(.claude/hooks)은 로드 동안만 sys.path 에 두고
    `shared_utils` 캐시를 되돌린다 — 남기면 뒤 테스트의 Cursor 훅이 Claude 판을 집는다."""
    if str(HARNESS) not in sys.path:
        sys.path.insert(0, str(HARNESS))
    is_hook = path.parent == HOOKS
    saved = sys.modules.get("shared_utils")
    if is_hook:
        sys.path.insert(0, str(HOOKS))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    finally:
        if is_hook:
            sys.path.remove(str(HOOKS))
            if saved is None:
                sys.modules.pop("shared_utils", None)
            else:
                sys.modules["shared_utils"] = saved
    return mod


GUARD = _load("guard_policy_effective_ut", HARNESS / "guard_policy.py")
LEDGER = _load("session_commit_ledger_effective_ut", HARNESS / "session_commit_ledger.py")
EFFECTIVE = _load("effective_repo_ut", HARNESS / "effective_repo.py")


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return proc.stdout.strip()


def _commit(cwd: Path, name: str) -> str:
    (cwd / name).write_text(name, encoding="utf-8")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", name)
    return _git(cwd, "rev-parse", "HEAD")


def _build(tmp_path: Path) -> dict[str, Path | str]:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "deploy")
    _git(main, "remote", "add", "origin", str(origin))
    _commit(main, "base.txt")
    _git(main, "push", "-q", "origin", "deploy")
    _git(main, "fetch", "-q", "origin")
    foreign = _commit(main, "foreign.txt")  # 메인 로컬 deploy 에만 있는 남의 커밋
    wt = tmp_path / "foms-s-x"
    _git(main, "worktree", "add", "-q", "-b", "session/x", str(wt), "origin/deploy")
    own = _commit(wt, "own.txt")
    LEDGER.append_commit(str(wt), SID, own)
    LEDGER.append_commit(str(main), SID, own)  # F2: 워크트리 커밋은 메인 원장에도 적힌다
    other_origin = tmp_path / "other.git"
    _git(tmp_path, "init", "-q", "--bare", str(other_origin))
    other = tmp_path / "foms-s-other"
    other.mkdir()
    _git(other, "init", "-q", "-b", "deploy")
    _git(other, "remote", "add", "origin", str(other_origin))
    _commit(other, "o.txt")
    _git(other, "push", "-q", "origin", "deploy")
    _git(other, "fetch", "-q", "origin")
    _commit(other, "o2.txt")
    return {"tmp": tmp_path, "main": main, "wt": wt, "other": other, "own": own, "foreign": foreign}


@pytest.fixture(scope="module")
def repos(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path | str]:
    """판정만 하는 시험이 함께 쓰는 저장소 묶음(만드는 데 git 호출이 많아 모듈에 한 번)."""
    return _build(tmp_path_factory.mktemp("effective"))


@pytest.fixture()
def fresh_repos(tmp_path: Path) -> dict[str, Path | str]:
    """커밋을 더하는 원장 시험 전용 — 공유 묶음을 바꾸지 않는다."""
    return _build(tmp_path)


def _classify(command: str, repos, cwd: Path | None = None) -> tuple[str, str]:
    return GUARD.classify_command(
        command, project_root=str(repos["main"]), session_id=SID, cwd=str(cwd) if cwd else None
    )


def _posix(path: Path) -> str:
    return path.as_posix()


def test_push_from_worktree_via_cd_is_judged_on_worktree(repos) -> None:
    assert _classify(f"cd {_posix(repos['wt'])} && git push origin HEAD:deploy", repos) == ("allow", "")


def test_push_with_payload_cwd_worktree_is_allowed(repos) -> None:
    assert _classify("git push origin HEAD:deploy", repos, cwd=repos["wt"]) == ("allow", "")


def test_relative_cd_is_resolved_against_payload_cwd(repos) -> None:
    assert _classify("cd foms-s-x && git push origin HEAD:deploy", repos, cwd=repos["tmp"]) == ("allow", "")


def test_push_from_main_still_asks_for_foreign_commit(repos) -> None:
    decision, label = _classify("git push origin HEAD:deploy", repos, cwd=repos["main"])
    assert decision == "ask" and "타 세션" in label and repos["foreign"][:8] in label


def test_git_dash_c_overrides_cd(repos) -> None:
    command = f"cd {_posix(repos['wt'])} && git -C {_posix(repos['main'])} push origin HEAD:deploy"
    assert _classify(command, repos)[0] == "ask"


@pytest.mark.parametrize(
    "prefix",
    ['cd "$WT"', "cd -", "cd ~/x", "popd", "cd /definitely/not/here"],
)
def test_unresolvable_directory_fails_closed(repos, prefix: str) -> None:
    decision, label = _classify(f"{prefix} && git push origin HEAD:deploy", repos, cwd=repos["wt"])
    assert decision == "ask", (prefix, label)


def test_other_origin_repository_is_not_judged_by_foms_ledger(repos) -> None:
    decision, label = _classify(f"cd {_posix(repos['other'])} && git push origin HEAD:deploy", repos)
    assert decision == "ask" and "실효 저장소 판정 불가" in label


def test_production_push_still_asks_from_worktree(repos) -> None:
    decision, label = _classify(f"cd {_posix(repos['wt'])} && git push origin HEAD:production", repos)
    assert decision == "ask" and "production" in label


def test_subshell_cd_does_not_leak_to_outer_push(repos) -> None:
    command = f"bash -c 'cd {_posix(repos['wt'])}' ; git push origin HEAD:deploy"
    assert _classify(command, repos, cwd=repos["main"])[0] == "ask"


def test_git_command_dir_reads_cd_and_dash_c() -> None:
    assert GUARD.git_command_dir("cd /c/tmp/foms-s-a && git commit -F m -- x", "commit") == "/c/tmp/foms-s-a"
    assert GUARD.git_command_dir("git -C /c/tmp/b commit -m x", "commit") == "/c/tmp/b"
    assert GUARD.git_command_dir("cd /c/tmp/a && git -C /c/tmp/b commit -m x", "commit") == "/c/tmp/b"
    assert GUARD.git_command_dir("GIT_X=1 git commit -m x", "commit") is None
    assert GUARD.git_command_dir("cd /c/tmp/a && git push", "commit") is None


@pytest.mark.skipif(os.name != "nt", reason="Git Bash 경로 표기는 Windows 전용")
def test_git_bash_drive_path_is_converted() -> None:
    assert EFFECTIVE.native_path("/c/tmp/foms-s-x") == "c:/tmp/foms-s-x"
    assert EFFECTIVE.native_path("C:/tmp/x") == "C:/tmp/x"


def _ledger_shas(root: Path) -> list[str]:
    path = Path(LEDGER.ledger_path(str(root)))
    if not path.is_file():
        return []
    return LEDGER.session_shas(str(root), SID + "-ledger")


def test_commit_ledger_hook_records_worktree_head_in_both_ledgers(fresh_repos, monkeypatch) -> None:
    repos = fresh_repos
    hook = _load("record_commit_ledger_effective_ut", HOOKS / "record_commit_ledger.py")
    monkeypatch.setattr(hook, "get_project_root", lambda: str(repos["main"]))
    sha = _commit(repos["wt"], "own2.txt")
    payload = {
        "session_id": SID + "-ledger",
        "cwd": str(repos["main"]),
        "tool_input": {"command": f"cd {_posix(repos['wt'])} && git commit -q -m own2"},
        "tool_response": {"stdout": f"[session/x {sha[:7]}] own2\n 1 file changed"},
    }
    hook.process(payload)
    assert _ledger_shas(repos["wt"]) == [sha]
    assert _ledger_shas(repos["main"]) == [sha]
    main_head = _git(repos["main"], "rev-parse", "HEAD")
    assert main_head not in json.dumps(LEDGER.load_ledger(str(repos["main"])))


def test_commit_ledger_hook_main_commit_stays_in_main_ledger(fresh_repos, monkeypatch) -> None:
    repos = fresh_repos
    hook = _load("record_commit_ledger_effective_ut2", HOOKS / "record_commit_ledger.py")
    monkeypatch.setattr(hook, "get_project_root", lambda: str(repos["main"]))
    sha = _commit(repos["main"], "main2.txt")
    payload = {
        "session_id": SID + "-ledger",
        "cwd": str(repos["main"]),
        "tool_input": {"command": "git commit -q -m main2"},
        "tool_response": {"stdout": f"[deploy {sha[:7]}] main2\n 1 file changed"},
    }
    hook.process(payload)
    assert _ledger_shas(repos["main"]) == [sha]
    assert _ledger_shas(repos["wt"]) == []


def test_quiet_commit_is_recorded_from_fresh_reflog(fresh_repos, monkeypatch) -> None:
    """`git commit -q` 는 성공 출력이 없다 — 방금 생긴 reflog commit 으로 인정한다(2026-11-03)."""
    repos = fresh_repos
    hook = _load("record_commit_ledger_effective_ut3", HOOKS / "record_commit_ledger.py")
    monkeypatch.setattr(hook, "get_project_root", lambda: str(repos["main"]))
    sha = _commit(repos["wt"], "quiet.txt")
    payload = {
        "session_id": SID + "-ledger",
        "cwd": str(repos["main"]),
        "tool_input": {"command": f"cd {_posix(repos['wt'])} && git commit -q -F msg.txt -- quiet.txt"},
        "tool_response": {"stdout": "", "stderr": ""},
    }
    hook.process(payload)
    assert _ledger_shas(repos["wt"]) == [sha]


def test_failed_commit_output_is_not_recorded_even_with_fresh_reflog(fresh_repos, monkeypatch) -> None:
    repos = fresh_repos
    hook = _load("record_commit_ledger_effective_ut4", HOOKS / "record_commit_ledger.py")
    monkeypatch.setattr(hook, "get_project_root", lambda: str(repos["main"]))
    _commit(repos["wt"], "earlier.txt")
    payload = {
        "session_id": SID + "-ledger",
        "cwd": str(repos["wt"]),
        "tool_input": {"command": "git commit -q -m again"},
        "tool_response": {"stdout": "nothing to commit, working tree clean"},
    }
    hook.process(payload)
    assert _ledger_shas(repos["wt"]) == []


def test_stale_reflog_commit_is_not_taken_as_just_committed(repos) -> None:
    rec = _load("record_git_commit_ledger_effective_ut", HARNESS / "record_git_commit_ledger.py")
    assert rec.just_committed(str(repos["wt"]))
    assert not rec.just_committed(str(repos["wt"]), now=10**10)
