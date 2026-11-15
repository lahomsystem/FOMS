"""새 회사 지식 화면의 디자인 시스템이 밖으로 새지 않는다(설계서 2026-11-14-foms-graft 5.1).

- ``foms-ds.css``: 모든 선택자가 ``.f-`` 로 시작(그래서 ``.f-app`` 아래거나 ``.f-`` class 에만 먹는다) · ``:root`` 없음 ·
  맨 태그 선택자 없음 · ``@import`` 없음. 설계서의 네 가지 고침(토큰 → ``.f-app`` · ``.f-tag.st-*`` 여덟 · ``.f-i.i-*`` 88 ·
  ``--fs: var(--foms-fs, 1)``)과 출처 줄.
- 틀 배치 ``brain-ds-shell.css``: 선택자가 ``.fb-`` · ``.f-`` 로 시작.
- 이 CSS 들을 가리키는 템플릿은 ``templates/brain/ds/`` 뿐, 공용 ``layout_head.html`` 에는 없다.
목업 파일(``docs/``)은 읽지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DS_CSS = ROOT / "static/css/contexts/brain/ds/foms-ds.css"
SHELL_CSS = ROOT / "static/css/contexts/brain/ds/brain-ds-shell.css"


def _selectors(css: str) -> list[str]:
    """주석을 뺀 CSS 의 모든 선택자(쉼표로 나눔). ``@media`` 머리는 빼고 안의 규칙은 센다."""
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    code = re.sub(r"\{[^{}]*\}", "{}", code)  # 선언 덩어리를 비운다(안쪽부터)
    out: list[str] = []
    for head in re.findall(r"([^{}]+)\{", code):
        head = head.strip()
        if not head or head.startswith("@"):
            continue
        out.extend(part.strip() for part in _split_top(head) if part.strip())
    return out


def _split_top(head: str) -> list[str]:
    """괄호 밖 쉼표로만 나눈다(``:where(h1, h2)`` 는 한 선택자)."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(head):
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(head[start:i])
            start = i + 1
    parts.append(head[start:])
    return parts


def test_selector_reader_catches_leaks():
    """음성 대조군: 새는 모양을 읽어 낸다."""
    found = _selectors(":root { --a:1; }\nbody, .f-x :where(h1, p) { margin:0 }\n"
                       "@media (max-width:640px) { .st-a { x:1 } }")
    assert found == [":root", "body", ".f-x :where(h1, p)", ".st-a"]


def test_every_design_system_selector_is_scoped():
    css = DS_CSS.read_text(encoding="utf-8")
    selectors = _selectors(css)
    assert len(selectors) > 300  # 아이콘 88 + 부품들 — 읽기가 비지 않았다
    leaks = [s for s in selectors if not s.startswith(".f-")]
    assert leaks == []
    assert ":root" not in re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert "@import" not in css


def test_the_four_spec_fixes_and_the_source_line():
    css = DS_CSS.read_text(encoding="utf-8")
    assert "Blueprint © Palantir Technologies, Apache License 2.0" in css
    assert re.search(r"^\.f-app \{\n  --black:#111418;", css, flags=re.M)  # ① 토큰이 .f-app 에
    assert len(re.findall(r"^\.f-tag\.st-[a-z]+ \{", css, flags=re.M)) == 8  # ②
    assert not re.search(r"^\.st-", css, flags=re.M)
    assert len(re.findall(r"^\.f-i\.i-[a-z0-9-]+\{--i:url\(", css, flags=re.M)) == 88  # ③
    assert not re.search(r"^\.i-", css, flags=re.M)
    assert "--fs:var(--foms-fs, 1);" in css and "--fs:1;" not in css  # ④


def test_shell_layout_selectors_are_prefixed():
    selectors = _selectors(SHELL_CSS.read_text(encoding="utf-8"))
    assert selectors and [s for s in selectors if not s.startswith((".fb-", ".f-"))] == []
    assert "@import" not in SHELL_CSS.read_text(encoding="utf-8")


def test_only_new_brain_templates_load_the_design_system():
    texts = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in (ROOT / "templates").rglob("*.html")}
    ds_users = sorted(rel for rel, text in texts.items() if "css/contexts/brain/ds/foms-ds.css'" in text)
    assert ds_users == ["templates/brain/ds/layout.html"]
    page_css_users = [rel for rel, text in texts.items() if "'css/contexts/brain/ds/" in text]
    assert page_css_users and all(rel.startswith("templates/brain/ds/") for rel in page_css_users)
    head = texts["templates/partials/shared/layout_head.html"]
    assert "brain/ds" not in head and "foms-ds.css" not in head
    layout = texts["templates/brain/ds/layout.html"]
    assert "asset_url('css/contexts/brain/ds/foms-ds.css')" in layout
    links = " ".join(re.findall(r"<link\b[^>]*>", layout))
    assert "bootstrap" not in links.lower() and "erp-pro" not in links and "font-awesome" not in links
    includes = re.findall(r"{%-?\s*(?:include|extends)\s+[\"']([^\"']+)[\"']", layout)
    assert includes == ["partials/shared/csrf_bootstrap.html", "partials/shared/notice_popup.html"]
