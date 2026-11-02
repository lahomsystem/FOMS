"""세션 시작 훅이 '메인 체크아웃 낡음'을 알리는지(설계서 2026-11-02 push-guard-effective-repo F6).

훅은 메인 체크아웃 파일로 돈다. 2026-10-21 ~ 11-03 메인이 304커밋 뒤처진 채 아무도 몰라
그 사이 deploy 에 올린 하네스 수정이 훅에 적용되지 않았다. 앱 코드만 다른 것은 알리지 않는다.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS = REPO_ROOT / ".claude" / "hooks"


def _load_session_start():
    saved = sys.modules.get("shared_utils")
    sys.path.insert(0, str(HOOKS))
    try:
        spec = importlib.util.spec_from_file_location("session_start_stale_ut", HOOKS / "session_start.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(HOOKS))
        if saved is None:
            sys.modules.pop("shared_utils", None)
        else:
            sys.modules["shared_utils"] = saved
    return mod


HOOK = _load_session_start()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _commit(cwd: Path, rel: str) -> None:
    path = cwd / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rel + str(len(list(cwd.rglob("*")))), encoding="utf-8")
    _git(cwd, "add", rel)
    _git(cwd, "commit", "-q", "-m", rel)


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path]:
    """origin(bare) 을 공유하는 메인 체크아웃과, 앞서 나가는 다른 클론."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "deploy")
    _git(main, "remote", "add", "origin", str(origin))
    _commit(main, "app.py")
    _git(main, "push", "-q", "origin", "deploy")
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", "-b", "deploy", str(origin), str(other))
    return main, other


def _advance(main: Path, other: Path, rel: str) -> None:
    _commit(other, rel)
    _git(other, "push", "-q", "origin", "deploy")
    _git(main, "fetch", "-q", "origin")


def test_up_to_date_main_is_silent(pair) -> None:
    main, _other = pair
    _git(main, "fetch", "-q", "origin")
    assert HOOK._main_checkout_stale_note(str(main)) == ("", "")


def test_behind_on_app_code_only_is_silent(pair) -> None:
    main, other = pair
    _advance(main, other, "foms/web/page.py")
    assert HOOK._main_checkout_stale_note(str(main)) == ("", "")


def test_behind_on_harness_files_warns_with_fast_forward(pair) -> None:
    main, other = pair
    _advance(main, other, "tools/harness/guard_policy.py")
    _advance(main, other, "foms/web/page.py")
    model, user = HOOK._main_checkout_stale_note(str(main))
    assert "[MAIN-STALE]" in model and "2커밋 뒤(앞섬 0)" in model and "1개가 다르다" in model
    assert "merge --ff-only origin/deploy" in model
    assert "메인 폴더" in user and "2커밋" in user


def test_diverged_main_asks_for_backup_first(pair) -> None:
    main, other = pair
    _commit(main, "local.txt")
    _advance(main, other, ".claude/hooks/guard_shell.py")
    model, _user = HOOK._main_checkout_stale_note(str(main))
    assert "앞섬 1" in model and "백업" in model and "ff-only" not in model


def test_non_repository_is_silent(tmp_path: Path) -> None:
    assert HOOK._main_checkout_stale_note(str(tmp_path)) == ("", "")


def test_session_start_emits_user_visible_system_message() -> None:
    source = (HOOKS / "session_start.py").read_text(encoding="utf-8")
    assert 'output["systemMessage"] = user_warning' in source
    assert source.index("drift = _deploy_drift_note()") < source.index("_main_checkout_stale_note(os.path")
