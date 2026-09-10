"""하네스 드리프트 가드 (ablation v2 적용, 2026-09-10).

ablation 판정이 플러그인 업데이트·메모리 증식·규칙 복제·유령 경로로 되돌아가는 것을
코드로 막는다. 기준값(상한·ratchet)은 적용 시점 실측으로 고정한다.
`~/.claude` 를 읽는 테스트는 그 파일이 없는 환경(CI)에서는 통과한다.
"""
from __future__ import annotations

import json
import re
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
