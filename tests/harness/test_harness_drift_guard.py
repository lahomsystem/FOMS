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
