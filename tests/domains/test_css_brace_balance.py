"""모든 정적 CSS 의 중괄호가 짝이 맞는다.

2026-10-01 발견: erp-pro.css 에서 `}` 하나가 빠져(6c0e669c7) 그 뒤 규칙 전부를 브라우저가 버렸다
(도면 게이트 막힌 이유 글자·경고 버튼 색·과거 이력 링크·긴급 호출 고른 사람 표시).
문자열 단언 테스트는 규칙이 파일에 '있는지'만 봐서 못 잡았다 — 파일이 파싱되는지를 본다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CSS_FILES = sorted((ROOT / "static" / "css").rglob("*.css"))


def _unbalanced_at(text: str) -> int | None:
    """주석·문자열을 건너뛰며 중괄호 깊이를 센다. 문제 없으면 None, 있으면 문제 위치(줄)."""
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        ch = text[i]
        if ch in ('"', "'"):
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return text.count("\n", 0, i) + 1
        i += 1
    return None if depth == 0 else text.count("\n") + 1


def test_css_files_found():
    assert len(CSS_FILES) > 50


@pytest.mark.parametrize("path", CSS_FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_css_braces_balanced(path: Path):
    line = _unbalanced_at(path.read_text(encoding="utf-8", errors="replace"))
    assert line is None, f"{path.relative_to(ROOT).as_posix()}: 중괄호 짝이 안 맞는다(~{line}줄)"


def test_checker_catches_missing_close():
    """음성 대조군: 실제 결함 모양(닫는 괄호 누락)을 잡는다."""
    assert _unbalanced_at(".a {\n  margin: 0;\n\n/* 주석 } */\n.b { color: red; }\n") is not None
    assert _unbalanced_at('.a { content: "}"; }\n') is None
