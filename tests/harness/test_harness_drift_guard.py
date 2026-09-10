"""하네스 드리프트 가드 (ablation v2 적용, 2026-09-10).

ablation 판정이 플러그인 업데이트·메모리 증식·규칙 복제·유령 경로로 되돌아가는 것을
코드로 막는다. 기준값(상한·ratchet)은 적용 시점 실측으로 고정한다.
`~/.claude` 를 읽는 테스트는 그 파일이 없는 환경(CI)에서는 통과한다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_SEARCH_DIRS = ("tools", "scripts", ".claude", "docs", "foms", "tests")


def _read(p: Path) -> str:
    """UTF-8 로 읽는다(cp949 함정 회피)."""
    return p.read_text(encoding="utf-8")


def _path_exists(raw: str) -> bool:
    """백틱 경로가 실존하는지 — 디렉토리 경로는 루트 기준, 파일명만 있으면 주요 디렉토리를 찾는다."""
    if (REPO / raw).exists():
        return True
    if "/" in raw:
        return False
    return any(next((REPO / d).rglob(raw), None) is not None for d in _SEARCH_DIRS if (REPO / d).is_dir())


def test_claude_md_paths_exist() -> None:
    """CLAUDE.md 가 가리키는 경로가 실존해야 한다 — `apps/api/` 류 유령 경로 재발 방지."""
    text = _read(REPO / "CLAUDE.md")
    missing = []
    for m in re.finditer(r"`((?:[\w.-]+/)+[\w.-]*|[\w-]+\.(?:py|md|json|ps1|css|js))`", text):
        raw = m.group(1).rstrip("/")
        if raw.startswith(("http", "~", "<", "_")) or "*" in raw or "<" in raw:
            continue
        if not _path_exists(raw):
            missing.append(raw)
    assert not missing, f"CLAUDE.md 가 가리키는 없는 경로: {missing}"


def test_mcp_servers_match_claude_md() -> None:
    """CLAUDE.md 의 MCP 정본 서술과 .mcp.json 실제 서버 집합이 같아야 한다."""
    servers = set(json.loads(_read(REPO / ".mcp.json"))["mcpServers"].keys())
    text = _read(REPO / "CLAUDE.md")
    m = re.search(r"\.mcp\.json`\(([^)]*)\)", text)
    assert m, "CLAUDE.md 에 `.mcp.json`(서버 목록) 서술이 없다"
    stated = {s.strip() for s in re.split(r"[·,]", m.group(1)) if s.strip()}
    assert stated == servers, f"CLAUDE.md {stated} != .mcp.json {servers}"


CLAUDE_MD_MAX_LINES = 45
DUP_MIN_CHARS = 40
_DUP_ALLOW = ("APP_OK", "claude_master")


def test_project_claude_md_line_budget() -> None:
    """프로젝트 CLAUDE.md 줄 수 상한 — 상시 로드 텍스트 재증식 방지(2026-09-10 적용 시 33줄)."""
    n = _read(REPO / "CLAUDE.md").count("\n") + 1
    assert n <= CLAUDE_MD_MAX_LINES, f"CLAUDE.md {n}줄 > {CLAUDE_MD_MAX_LINES} — 절차·복제본은 AGENTS.md 로"


def _policy_lines(p: Path) -> set[str]:
    """정책 문장 집합 — 40자 이상, 불릿·공백 정규화, 자구 동일 허용 토큰이 든 줄은 제외."""
    out: set[str] = set()
    for ln in _read(p).splitlines():
        s = re.sub(r"\s+", " ", ln.strip("-* \t"))
        if len(s) >= DUP_MIN_CHARS and not any(k in s for k in _DUP_ALLOW):
            out.add(s)
    return out


def test_no_duplicate_policy_lines_between_claude_and_agents() -> None:
    """같은 정책 문장이 CLAUDE.md 와 AGENTS.md 양쪽에 있으면 red — 두 벌 유지가 준수율을 못 올린 것이 감사 결론."""
    dup = _policy_lines(REPO / "CLAUDE.md") & _policy_lines(REPO / "AGENTS.md")
    assert not dup, "CLAUDE.md↔AGENTS.md 중복 문장:\n" + "\n".join(sorted(dup))


def test_atomic_facts_identical_in_both_files() -> None:
    """두 소비자(Claude / Codex·Cursor)가 각각 읽는 원자 사실은 양쪽에 같은 토큰으로 있어야 한다."""
    c = _read(REPO / "CLAUDE.md")
    a = _read(REPO / "AGENTS.md")
    for token in ("APP_OK", "claude_master", "CLAUDE-TEST-", "python -c \"import app; print('APP_OK')\""):
        assert token in c and token in a, f"원자 사실 {token!r} 이 한쪽 파일에 없다"


def test_task_grade_marker_ssot_is_guide() -> None:
    """등급 마커 정의 본문은 LONG_TASK_PROMPTS.md 가 정본이고 CLAUDE.md 는 포인터 1줄만 둔다."""
    guide = _read(REPO / "docs" / "guides" / "LONG_TASK_PROMPTS.md")
    assert "### 마커 규칙 정본" in guide
    for marker in ("`**A` 소형", "`**B` 하루", "`**C` 릴레이", "`**D` 최고 안전등급"):
        assert marker in guide, f"가이드에 {marker} 정의가 없다"
    claude = _read(REPO / "CLAUDE.md")
    assert "docs/guides/LONG_TASK_PROMPTS.md" in claude
    assert "`**B` 하루" not in claude, "마커 상세가 CLAUDE.md 에 다시 들어왔다"


INLINE_STYLE_RATCHET = 828  # 2026-09-10 실측: templates+static 의 .html/.js 안 `style="` 개수. 줄어들면 값을 낮춘다


def count_inline_styles() -> int:
    """templates/·static/ 의 .html/.js 파일에서 `style="` 개수를 센다(ratchet 기준값 재측정용)."""
    count = 0
    for base in ("templates", "static"):
        for p in (REPO / base).rglob("*"):
            if p.suffix in {".html", ".js"} and p.is_file():
                count += _read(p).count('style="')
    return count


def test_inline_style_ratchet() -> None:
    """인라인 style 개수는 기준값보다 늘 수 없다 — 규칙 두 벌(CLAUDE.md·AGENTS.md)이 5주간 76행 추가를 못 막았다(MOVE-TO-CODE)."""
    count = count_inline_styles()
    assert count <= INLINE_STYLE_RATCHET, (
        f"inline style {count} > 기준 {INLINE_STYLE_RATCHET} — erp-pro.css 로 옮겨라"
        "(기준값은 tests/harness/test_harness_drift_guard.py::INLINE_STYLE_RATCHET)"
    )


_LIVE_GUARD_LOG = REPO / "docs" / "harness" / "logs" / "SHELL_GUARD_LOG.md"
_LIVE_HOOK_LOG = REPO / "docs" / "harness" / "logs" / "CLAUDE_HOOK_LOG.md"


def _snapshot(p: Path) -> bytes:
    return p.read_bytes() if p.exists() else b""


def test_guard_hooks_do_not_write_live_log(tmp_path: Path) -> None:
    """가드 훅 2종(Claude·Cursor)이 FOMS_HARNESS_LOG_DIR 를 존중해야 한다.

    2026-09-09 감사: 실 SHELL_GUARD_LOG 300행 중 164행(55%)이 테스트 오염이었다 — 로그가
    실제 발화를 대표하지 못해 가드 실효 판정이 불가능했다(원장 §3).
    """
    before_guard, before_hook = _snapshot(_LIVE_GUARD_LOG), _snapshot(_LIVE_HOOK_LOG)
    env = dict(os.environ, FOMS_HARNESS_LOG_DIR=str(tmp_path))
    danger = "git push --force origin production"
    subprocess.run(
        [sys.executable, str(REPO / ".claude" / "hooks" / "guard_shell.py")],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": danger}}).encode(),
        capture_output=True, env=env, cwd=REPO, timeout=60,
    )
    cursor_env = dict(env, CURSOR_PAYLOAD=json.dumps({"command": danger, "workspace_roots": [str(REPO)]}))
    cursor_env.pop("PYTHONPATH", None)
    subprocess.run(
        [sys.executable, str(REPO / ".cursor" / "hooks" / "guard_shell.py")],
        stdin=subprocess.DEVNULL, capture_output=True, env=cursor_env, cwd=REPO, timeout=60,
    )
    assert _snapshot(_LIVE_GUARD_LOG) == before_guard, "가드 훅이 env 로그 경로를 무시하고 실 로그에 썼다"
    assert _snapshot(_LIVE_HOOK_LOG) == before_hook, "훅이 실 CLAUDE_HOOK_LOG 에 썼다"
    isolated = tmp_path / "SHELL_GUARD_LOG.md"
    assert isolated.exists(), "가드 훅이 주입된 로그 경로에 아무것도 쓰지 않았다"
    rows = [ln for ln in _read(isolated).splitlines() if ln.startswith("| 20")]
    assert len(rows) == 2, rows


def test_hook_log_utils_warn_honors_log_dir_env(tmp_path: Path, monkeypatch) -> None:
    """공용 유틸의 내부 경고 로그도 env 경로를 쓴다 — 테스트가 `id='unknown'` 27행을 실 로그에 남긴 사고."""
    monkeypatch.setenv("FOMS_HARNESS_LOG_DIR", str(tmp_path))
    before = _snapshot(_LIVE_HOOK_LOG)
    import importlib.util
    spec = importlib.util.spec_from_file_location("hlu_env_test", REPO / "tools" / "harness" / "hook_log_utils.py")
    assert spec and spec.loader
    hlu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hlu)
    hlu._warn("드리프트 가드 테스트 경고")
    assert _snapshot(_LIVE_HOOK_LOG) == before
    assert "드리프트 가드 테스트 경고" in _read(tmp_path / "CLAUDE_HOOK_LOG.md")
