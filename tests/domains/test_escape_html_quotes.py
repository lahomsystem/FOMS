"""화면 이스케이프 함수는 따옴표까지 바꾼다 (SPEC 2026-10-20-escape-html-quotes).

``div.textContent = x; return div.innerHTML`` 방식은 ``&``·``<``·``>`` 만 바꾸고 ``"``·``'``
는 그대로 둔다. 그 결과를 ``title="..."``·``data-*="..."`` 같은 속성값에 넣으면 파일 이름·
제품명·주소에 든 따옴표가 속성을 끝내 버린다. 정적 JS·템플릿의 이스케이프 함수 정의를
전부 찾아 몸통이 두 따옴표를 바꾸는지(또는 그런 함수에 맡기는지) 본다.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_DEF = re.compile(
    r"function\s+(?P<a>escapeHtml|escHtml|esc|escapeHTML|_esc|escapeAttr|htmlEscape)\s*\("
    r"|(?P<b>escapeHtml|escHtml|escapeHTML|htmlEscape|esc)\s*=\s*(?:function\b|\()"
)
_DQ = re.compile(r"&quot;|&#34;|&#x22;")
_SQ = re.compile(r"&#39;|&#039;|&apos;|&#x27;")
# 다른 (검사받는) 이스케이프 함수에 그대로 맡기는 몸통 — 예: esc(v) { return escapeHtml(v)... }
_DELEGATE = re.compile(r"\b(?:escapeHtml|escHtml|_escapeHtml)\s*\(")


def _sources():
    out = subprocess.run(
        ["git", "ls-files", "static/js", "templates"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.split()
    for rel in out:
        if not rel.endswith((".js", ".html")) or "/vendor/" in rel or ".min." in rel:
            continue
        yield rel, (ROOT / rel).read_text(encoding="utf-8")


def _body(text, start):
    """정의 시작 뒤 첫 ``{`` 부터 짝 ``}`` 까지(화살표 한 줄 함수는 줄 끝까지)."""
    brace = text.find("{", start)
    newline = text.find("\n", start)
    if brace == -1 or (newline != -1 and brace > newline and "=>" in text[start:newline]):
        return text[start:newline]
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace:i + 1]
    return text[brace:]


def _definitions():
    for rel, text in _sources():
        for m in _DEF.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            yield f"{rel}:{line}", _body(text, m.end())


def _quote_safe(body):
    if _DQ.search(body) and _SQ.search(body):
        return True
    return bool(_DELEGATE.search(body)) and not ("textContent" in body or "innerHTML" in body)


def test_finds_escape_definitions():
    defs = list(_definitions())
    # 2026-10-20 기준 40개 안팎 — 검색식이 깨져 0 이 되면 아래 검사가 거짓 통과한다.
    assert len(defs) >= 30, len(defs)


def test_every_escape_function_escapes_both_quotes():
    bad = [loc for loc, body in _definitions() if not _quote_safe(body)]
    assert not bad, "따옴표를 안 바꾸는 이스케이프 함수:\n" + "\n".join(bad)
