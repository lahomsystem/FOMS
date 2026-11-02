"""'회사 지식' 화면 파일 규칙(설계서 7.5 '라이브러리' · '앱 코드' · AGENTS.md 프런트 규칙 · 성능 가드).

- 그림 라이브러리 두 파일: SHA-256 이 적은 값과 같고(한 바이트도 안 고침) · MIT · 지도 탭에서만 import()(화면 <script> 없음).
- 유형 색 하나: CSS 클래스(.brain-type--*) · 링크 색이 display.py 표와 같다(모든 화면 같은 색).
- 템플릿: 인라인 style · onclick · 인라인 스크립트 없음, 스크립트는 defer + asset_url(내용 해시 ?v=), Jinja → JS 는 data-*.
- JS: 파일마다 300줄 이하 · innerHTML · jQuery · .style 없음 · fetch 는 try/catch + data.success 확인 · import() 는 지도 파일만.
- 파이썬 파일 500줄 이하.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from foms.services.brain.display import LINK_DISPLAY, TYPE_DISPLAY

ROOT = Path(__file__).resolve().parents[2]
VENDOR = {
    "static/vendor/cytoscape-3.34.4.esm.min.js": "0d7e373a706f0f01d6fb7a6ccf04988c01307cee1c2f9bcc7b068e9f6b431e3f",
    "static/vendor/cytoscape-dagre-4.0.1.esm.min.js": "fe9ea1bf0804655e9daf8f201a5e72f6133c85d1a9fb3ab706d22c192e228871",
}
JS = sorted((ROOT / "static/js/brain").glob("*.js"))
TEMPLATES = sorted((ROOT / "templates/brain").rglob("*.html"))
CSS = ROOT / "static/css/contexts/brain/brain.css"
PY = [ROOT / "foms/api/brain.py", ROOT / "foms/api/brain_review.py", ROOT / "foms/web/brain.py",
      *[ROOT / "foms/services/brain" / n for n in ("access.py", "browse.py", "card.py", "display.py", "read.py",
                                                   "release_view.py", "inbox.py", "decide.py", "recheck.py",
                                                   "rollback.py", "metrics.py", "review_rules.py", "proposals.py",
                                                   "apply.py", "actions.py", "action_runner.py", "schemas.py")]]
#: 화면 스크립트 — 읽기(⑤-2) 여섯 + 제안함 · 다시 확인 · 카드 제안(⑤-3) 다섯 + 이웃 지도 · 뇌 보기(⑤-4) 아홉.
SCRIPT_NAMES = {"brain-view.js", "brain-dom.js", "brain-page.js", "brain-table.js", "brain-releases.js", "brain-map.js",
                "brain-review-view.js", "brain-inbox-card.js", "brain-inbox.js", "brain-recheck.js",
                "brain-item-actions.js", "brain-graph-view.js", "brain-neighbours.js", "brain3d-core.js",
                "brain3d-layout.js", "brain3d-shell.js", "brain3d-nodes.js", "brain3d-labels.js", "brain3d-scene.js",
                "brain3d-tab.js"}
#: 그림 라이브러리를 import() 하는 화면 파일 — 유형 지도 · 이웃 지도(Cytoscape) · 뇌 보기(three.js · 그리기 파일).
IMPORTERS = ["brain-map.js", "brain-neighbours.js", "brain3d-tab.js"]


def _code(path: Path) -> str:
    """주석 줄(``*`` · ``//`` 로 시작)을 뺀 코드."""
    return chr(10).join(line for line in _text(path).splitlines()
                        if not line.strip().startswith(("*", "//", "/**")))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_vendor_files_are_the_published_bytes_and_mit():
    notice = _text(ROOT / "static/vendor/cytoscape-NOTICE.txt")
    for rel, digest in VENDOR.items():
        data = (ROOT / rel).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, rel
        assert digest in notice and rel in notice
        assert b"\nimport " not in data and not data.startswith(b"import ")  # 의존 없는 ESM 한 파일
        assert b"export{" in data  # ESM default export
    assert notice.count("MIT License") == 3 and "Chris Pettitt" in notice  # cytoscape · cytoscape-dagre · 묶인 dagre
    # Windows(core.autocrlf)가 꺼낼 때 줄 끝을 바꾸면 받은 바이트가 아니다 — 두 파일은 글로 다루지 않는다
    assert "static/vendor/cytoscape*.esm.min.js -text" in _text(ROOT / ".gitattributes")


def test_vendor_files_load_only_through_import_in_the_map_tab():
    index = _text(ROOT / "templates/brain/index.html")
    assert "data-cytoscape-url=\"{{ asset_url('vendor/cytoscape-3.34.4.esm.min.js') }}\"" in index
    assert "data-dagre-url=\"{{ asset_url('vendor/cytoscape-dagre-4.0.1.esm.min.js') }}\"" in index
    tags = [t for p in ROOT.joinpath("templates").rglob("*.html") for t in re.findall(r"<(?:script|link)[^>]*>", _text(p))]
    assert not [t for t in tags if "vendor/cytoscape" in t]  # <script> · <link> 로 싣지 않는다 — 지도 탭 import() 만
    assert index.count("vendor/cytoscape") == 2
    users = [p.name for p in JS if "import(" in _code(p)]
    assert sorted(users) == sorted(IMPORTERS)  # 그 밖의 화면 파일은 import() 하지 않는다
    assert "import(ctx.urls.cytoscape)" in _text(ROOT / "static/js/brain/brain-map.js")
    assert "import(root.getAttribute('data-cytoscape-url'))" in _text(ROOT / "static/js/brain/brain-neighbours.js")
    neighbours = _text(ROOT / "templates/brain/partials/card_neighbours.html")
    assert "data-cytoscape-url=\"{{ asset_url('vendor/cytoscape-3.34.4.esm.min.js') }}\"" in neighbours


def test_one_colour_per_type_in_css_matches_the_display_table():
    css = _text(CSS)
    css_types = dict(re.findall(r"\.brain-type--([a-z_]+) \{ --brain-type: (#[0-9a-f]{6}); \}", css))
    assert css_types == {t: color for t, (_label, color, _icon) in TYPE_DISPLAY.items()}
    css_links = dict(re.findall(r"\.brain-link--([a-z_]+) \{ --brain-link: (#[0-9a-f]{6}); \}", css))
    assert css_links == {k: v[1] for k, v in LINK_DISPLAY.items()}
    colors = [color for _label, color, _icon in TYPE_DISPLAY.values()]
    assert len(set(colors)) == len(colors)  # 유형마다 다른 색
    for state in (".brain-state--draft", ".brain-state--retired", ".brain-state--stale"):
        assert state in css
    assert "dashed" in css and "--brain-stale: #ea580c" in css and "--brain-retired: #9ca3af" in css


def test_templates_have_no_inline_style_or_script_and_pin_assets():
    for path in TEMPLATES:
        html = _text(path)
        assert 'style="' not in html and "onclick" not in html and "<script>" not in html, path.name
        for tag in re.findall(r"<script[^>]*>", html):
            assert " defer" in tag and "asset_url(" in tag, (path.name, tag)
    index = _text(ROOT / "templates/brain/index.html")
    assert "data-display=\"{{ display|tojson|forceescape }}\"" in index
    assert "asset_url('css/contexts/brain/brain.css')" in index
    item = _text(ROOT / "templates/brain/item.html")
    assert 'data-brain-slot-tab' not in item and "준비 중" not in item  # ⑤-4 — 이웃 지도 · 뇌 보기 탭이 열렸다
    assert 'data-bs-target="#brain-card-neighbours"' in item and 'data-bs-target="#brain-card-brain3d"' in item
    assert '<li class="nav-item" role="presentation" hidden data-brain3d-tab-item>' in item  # 뇌 보기는 숨겨 그린다
    assert 'data-current="{{ current|tojson|forceescape }}"' in item
    assert 'data-display="{{ display|tojson|forceescape }}"' in item


def test_scripts_follow_the_frontend_rules():
    assert {p.name for p in JS} == SCRIPT_NAMES
    for path in JS:
        js = _text(path)
        lines = len(js.splitlines())
        assert lines <= 300, (path.name, lines)
        for banned in (".innerHTML", "outerHTML", "insertAdjacentHTML", "jQuery", "$(", ".style.", "eval(",
                       "document.write"):
            assert banned not in js, (path.name, banned)
    dom = _text(ROOT / "static/js/brain/brain-dom.js")
    assert dom.count("fetch(") == 1 and "try {" in dom and "payload.success !== true" in dom
    assert "function postJson(" in dom and "method: 'POST'" in dom  # 쓰기도 같은 한 곳(CSRF 는 공용 부트스트랩)
    assert "safeJsonParse" in dom and "textContent" in dom
    others = [p.name for p in JS if p.name != "brain-dom.js" and "fetch(" in _text(p)]
    assert others == []  # 모든 읽기 · 쓰기는 requestJson 한 곳(try/catch + success 확인)으로
    for name in ("brain-inbox.js", "brain-recheck.js", "brain-item-actions.js"):
        assert "__FOMS_BRAIN_" in _text(ROOT / "static/js/brain" / name), name  # 다시 실행해도 한 번만 묶는다
    actions = _text(ROOT / "static/js/brain/brain-item-actions.js")
    assert "dom.safeJsonParse(root.getAttribute('data-current')" in actions
    page = _text(ROOT / "static/js/brain/brain-page.js")
    assert "dom.safeJsonParse(root.getAttribute('data-display')" in page and "__FOMS_BRAIN_PAGE_BOUND" in page


def test_python_files_stay_under_five_hundred_lines():
    for path in PY:
        assert len(_text(path).splitlines()) <= 500, path.name
