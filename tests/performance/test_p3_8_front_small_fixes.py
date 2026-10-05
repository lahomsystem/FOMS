"""P3-8 작은 프런트 성능 4건 재발 방지(2026-10-01 성능 원장 P3-8).

1. 알림 종(.bell-active)은 안 읽은 알림이 있는 동안 계속 흔든다 — 사용자 결정(2026-10-05). 3번만 흔드는
   안(유휴 메인 스레드 AS 70→22ms · 대시보드 28→14ms)은 성능 이득을 알고도 택하지 않았으니, 다음 성능
   점검이 묻지 않고 다시 바꾸지 않게 잠근다.
2. erp-mobile-shell.js 는 광폭 마우스 PC 에서 하단 탭 높이(offsetHeight)를 읽지 않는다 — 그 화면에서
   하단 탭은 늘 숨어 있어 값이 0 이고, 읽기만 해도 레이아웃을 강제로 한 번 더 돌린다
   (같은 A/B: 이 파일의 로드 때 호출 34→1ms, 로드 스타일 계산 합 AS 133→108ms · 대시보드 146→108ms).
3. sync.js 는 layout_scripts.html 한 곳에서만 싣는다(셸 묶음에도 있어 셸 화면마다 두 번 실행됐다).
4. 아무도 싣지 않던 static/css/foundation/style.css 는 지웠다 — 되살아나지 않는다.

각 검사에는 음성 대조군을 둔다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
LAYOUT_SCRIPTS = TEMPLATES / "partials/shared/layout_scripts.html"
P2_BUNDLE = "partials/shared/foms_p2_surface_bundle.html"
SHELL_JS = ROOT / "static/js/runtime/erp-mobile-shell.js"
SHELL_CSS = ROOT / "static/css/foundation/erp-pro/10-erp-mobile-v2-shell.css"
_NODE = shutil.which("node")

_INCLUDE_RE = re.compile(r"{%-?\s*(?:include|extends)\s+['\"]([^'\"]+)['\"]")
_EXTENDS_RE = re.compile(r"{%-?\s*extends\s+['\"]")
_JINJA_COMMENT_RE = re.compile(r"{#.*?#}", re.S)
_SYNC_TAG_RE = re.compile(r"<script\b[^>]*js/foms/sync\.js[^>]*>", re.I)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- 1. 종 흔들기 ---------------------------------------------------------------------------


def _bell_animation(html: str) -> str:
    """``.bell-active { ... }`` 첫 블록의 animation 값."""
    block = html.split(".bell-active {", 1)[1].split("}", 1)[0]
    return re.search(r"animation:\s*([^;]+);", block).group(1).strip()


def _is_endless_shake(animation: str) -> bool:
    return "bell-shake" in animation and "infinite" in animation


def test_bell_keeps_shaking_by_user_decision() -> None:
    html = _read(LAYOUT_SCRIPTS)
    assert _is_endless_shake(_bell_animation(html)), _bell_animation(html)
    # 움직임 줄이기 설정이면 아예 흔들지 않는다(기존 규칙 유지).
    reduced = html.split("@media (prefers-reduced-motion: reduce)", 1)[1].split("</style>", 1)[0]
    assert ".bell-active" in reduced and "animation: none" in reduced


def test_bell_shake_checker_negative_control() -> None:
    assert _is_endless_shake("bell-shake 2.5s infinite")
    assert not _is_endless_shake("bell-shake 2.5s 3")
    assert not _is_endless_shake("none")
    assert _bell_animation(".bell-active {\n  animation: bell-shake 1s 3;\n}") == "bell-shake 1s 3"


# --- 2. 광폭 마우스 PC 에서 하단 탭 높이를 읽지 않기 ---------------------------------------------


def test_wide_mouse_pc_premise_chrome_is_hidden() -> None:
    """전제: 992+ 이면서 pointer fine/none 이면 하단 탭을 감싼 크롬이 display:none !important 다."""
    css = _read(SHELL_CSS)
    hide = css.split("((min-width: 992px) and (pointer: fine)),", 1)
    assert len(hide) == 2, "992+ fine 숨김 규칙이 사라졌다 — 높이 0 전제를 다시 확인할 것"
    block = hide[1].split("}", 1)[0]
    assert "((min-width: 992px) and (pointer: none))" in block
    assert ".erp-mobile-shell-chrome" in block and "display: none !important" in block
    shell = _read(TEMPLATES / "partials/shared/foms_app_shell.html")
    chrome_open = shell.index("erp-mobile-shell-chrome")
    assert chrome_open < shell.index("erp_mobile_bottom_nav.html") < shell.index("</div>", chrome_open)


_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const [src, coarse, wide] = process.argv.slice(1);
const listeners = {};
let reads = 0;
let writes = 0;
const rootProps = {};
const nav = { get offsetHeight() { reads += 1; return 64; } };
const document = {
  querySelector: (sel) => (sel === '.erp-mobile-bottom-nav' ? nav : null),
  querySelectorAll: () => [],
  getElementById: () => null,
  addEventListener: (n, fn) => { (listeners[n] = listeners[n] || []).push(fn); },
  documentElement: { style: {
    getPropertyValue: (k) => rootProps[k] || '',
    setProperty: (k, v) => { writes += 1; rootProps[k] = v; },
  } },
};
const window = {
  matchMedia: (q) => ({ matches: q === '(pointer: coarse)' ? coarse === '1' : (q === '(min-width: 992px)' ? wide === '1' : false) }),
  addEventListener: (n, fn) => { (listeners['win:' + n] = listeners['win:' + n] || []).push(fn); },
};
const ctx = vm.createContext({ window, document, console });
vm.runInContext(fs.readFileSync(src, 'utf8'), ctx);
(listeners.DOMContentLoaded || []).forEach((fn) => fn());
(listeners['foms:main-content-swapped'] || []).forEach((fn) => fn());
(listeners['win:resize'] || []).forEach((fn) => fn());
process.stdout.write(JSON.stringify({ reads, writes, value: rootProps['--erp-mobile-shell-nav-height'] || '' }));
"""


def _run_shell(*, coarse: bool, wide: bool) -> dict:
    proc = subprocess.run(
        [_NODE, "-e", _HARNESS, str(SHELL_JS), "1" if coarse else "0", "1" if wide else "0"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_wide_mouse_pc_writes_zero_without_reading_layout() -> None:
    # 세 번(첫 로드·스왑·리사이즈) 불려도 레이아웃을 읽지 않고, 같은 값은 한 번만 쓴다.
    assert _run_shell(coarse=False, wide=True) == {"reads": 0, "writes": 1, "value": "0px"}


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_phone_and_tablet_still_measure_nav_height() -> None:
    """음성 대조군: 좁은 창·터치 태블릿은 지금처럼 실제 높이를 잰다."""
    assert _run_shell(coarse=False, wide=False) == {"reads": 3, "writes": 1, "value": "64px"}
    assert _run_shell(coarse=True, wide=True) == {"reads": 3, "writes": 1, "value": "64px"}


# --- 3. sync.js 한 번만 ---------------------------------------------------------------------


def _template_graph() -> dict[str, tuple[set[str], bool]]:
    """템플릿 → (include·extends 대상, extends 하는 페이지인가). Jinja 주석은 뺀다."""
    graph: dict[str, tuple[set[str], bool]] = {}
    for path in TEMPLATES.rglob("*.html"):
        text = _JINJA_COMMENT_RE.sub("", path.read_text(encoding="utf-8", errors="ignore"))
        rel = path.relative_to(TEMPLATES).as_posix()
        graph[rel] = (set(_INCLUDE_RE.findall(text)), bool(_EXTENDS_RE.search(text)))
    return graph


def _closure(graph: dict[str, tuple[set[str], bool]], start: str) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        for child in graph.get(stack.pop(), (set(), False))[0]:
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def _pages_with_bundle_but_no_layout_scripts(graph: dict[str, tuple[set[str], bool]]) -> list[str]:
    layout = "partials/shared/layout_scripts.html"
    return sorted(
        rel
        for rel, (_, is_page) in graph.items()
        if is_page and P2_BUNDLE in (cl := _closure(graph, rel)) and layout not in cl
    )


def test_sync_js_loads_once_from_layout_scripts_only() -> None:
    layout_tags = _SYNC_TAG_RE.findall(_read(LAYOUT_SCRIPTS))
    assert len(layout_tags) == 1 and re.search(r"\bdefer\b", layout_tags[0]), layout_tags
    assert not _SYNC_TAG_RE.search(_read(TEMPLATES / P2_BUNDLE))
    # 셸 묶음을 싣는 페이지(extends)는 모두 layout_scripts 도 싣는다 — 묶음에서 빼도 sync.js 가 빠지는 화면이 없다.
    graph = _template_graph()
    pages = [rel for rel, (_, is_page) in graph.items() if is_page and P2_BUNDLE in _closure(graph, rel)]
    assert "orders/edit_order.html" in pages
    assert _pages_with_bundle_but_no_layout_scripts(graph) == []


def test_bundle_page_checker_negative_control() -> None:
    graph = {
        "x/layout.html": ({"partials/shared/layout_scripts.html"}, False),
        "x/good.html": ({"x/layout.html", P2_BUNDLE}, True),
        "x/bad.html": ({"y/plain.html", P2_BUNDLE}, True),
        "x/fragment.html": ({P2_BUNDLE}, False),
    }
    assert _pages_with_bundle_but_no_layout_scripts(graph) == ["x/bad.html"]


# --- 4. 죽은 style.css ----------------------------------------------------------------------


# 싣는 모양: filename='css/foundation/style.css' · "style.css" · /style.css · url(style.css).
# 다른 파일 안 주석 "(style.css," 이나 style-pro-max.css · el.style.cssText 는 해당 없다.
_STYLE_CSS_LOAD_RE = re.compile(r"(?:foundation/|['\"/]|url\(\s*)style\.css\b")


def test_dead_foundation_style_css_stays_removed() -> None:
    assert not (ROOT / "static/css/foundation/style.css").exists()
    offenders = [
        str(p.relative_to(ROOT))
        for base in ("templates", "static", "foms", "tools")
        for p in (ROOT / base).rglob("*")
        if p.suffix in {".html", ".css", ".js", ".py", ".json"}
        and _STYLE_CSS_LOAD_RE.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == [], offenders


def test_style_css_load_checker_negative_control() -> None:
    for hit in (
        "{{ url_for('static', filename='css/foundation/style.css') }}",
        '@import "style.css";',
        "@import url(style.css);",
        "<link href=\"/static/css/style.css\">",
    ):
        assert _STYLE_CSS_LOAD_RE.search(hit), hit
    for miss in ("css/foundation/style-pro-max.css", "el.style.cssText = ''", "(style.css, for wide tables)"):
        assert not _STYLE_CSS_LOAD_RE.search(miss), miss
