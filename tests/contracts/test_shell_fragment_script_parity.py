"""SHELL-JS-PARITY-01: 셸 대상 화면의 화면 전용 JS 는 온전한 페이지와 셸 조각 길에 함께 실려야 한다.

2026-11-18 스테이징 실측: 폰 출고 화면(``/erp/shipment``)에 다른 탭에서 **셸 스왑으로** 들어오면 카드의
[패킹] 단추(``[data-foms-packing-trigger]``)가 안 열렸다(콘솔 오류 없음). 새로고침으로 들어오면 열렸다.
``foms-packing.js`` 를 온전한 페이지 템플릿의 ``scripts`` 블록에만 실었기 때문이다 — 셸은 ``#main-content``
안 조각(``*_fragment.html``)만 갈아 끼우므로 그 블록은 스왑 진입 문서에 영영 없다. 같은 병으로 시공 탭의
[완료 준비] 게이트 · 출발 전 자재 확인 · 태블릿 작업 모드, 홈의 [부재중] 칩 · 단계 강제 변경, 출고 셸
(``shipment/layout.html``)의 관리자 강제 진행 사유 시트가 스왑 진입에서 죽어 있었다(로컬 재현 확인).

이 계약은 정적 감사다(HTTP 없음). 셸 대상 화면마다

* **온전한 페이지** = 쪽 템플릿 + 그 도메인 레이아웃(공용 ``partials/shared/layout_*`` 는 모든 문서에 늘 있으므로 뺀다)
* **셸 조각** = 라우트가 셸 요청에 돌려주는 조각 템플릿

에서 include · extends · import 를 따라가며 ``<script src>`` 를 모으고(``*-entry.js`` 는 안의 ``CHAIN`` 문자열까지
펼친다), 온전한 페이지에만 있는 스크립트가 있으면 실패한다. 의도된 예외는 :data:`ALLOWED_FULL_ONLY` 에
**이유와 함께** 적는다. Jinja 조건(``{% if %}``)은 무시한다 — 양쪽을 같게 과대 근사하므로 차이만 본다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import pytest

from foms.services.common.erp_navigation_contract import ERP_FRAGMENT_READY_PATHS

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
ERP_SHELL_JS = STATIC / "js" / "runtime" / "erp-shell.js"

#: 셸 경로 → (온전한 페이지 템플릿, 셸 조각 템플릿, 둘을 고르는 라우트 소스). 셸이 스왑하는 경로는
#: FRAGMENT_READY 9개 + erp-shell.js isSubordinateShellFragmentPath 의 하위 경로.
SHELL_SCREENS: dict[str, tuple[str, str, str]] = {
    "/erp/dashboard": ("orders/dashboard.html", "orders/partials/dashboard_main.html", "foms/web/orders/dashboard.py"),
    "/erp/measurement": ("measurement/dashboard.html", "measurement/partials/dashboard_fragment.html",
                         "foms/web/measurement/dashboard.py"),
    "/erp/drawing-workbench": ("drawing/workbench_dashboard.html", "drawing/partials/workbench_dashboard_fragment.html",
                               "foms/web/drawing/workbench.py"),
    "/erp/drawing-workbench/<id>": ("drawing/workbench_detail.html", "drawing/workbench_detail_fragment.html",
                                    "foms/web/drawing/workbench.py"),
    "/erp/production/dashboard": ("production/dashboard.html", "production/partials/dashboard_fragment.html",
                                  "foms/web/production/dashboard.py"),
    "/erp/production/home": ("production/home.html", "production/partials/home_fragment.html",
                             "foms/web/production/home.py"),
    "/erp/shipment": ("shipment/dashboard.html", "shipment/partials/dashboard_fragment.html",
                      "foms/web/shipment/dashboard.py"),
    "/erp/shipment-settings": ("shipment/settings.html", "shipment/settings_fragment.html",
                               "foms/api/shipment/settings.py"),
    "/erp/as": ("cs/as_dashboard.html", "cs/partials/as_dashboard_fragment.html", "foms/web/cs/as_dashboard.py"),
    "/erp/construction/dashboard": ("construction/dashboard.html", "construction/partials/dashboard_fragment.html",
                                    "foms/web/construction/dashboard.py"),
    "/erp/completion": ("cs/completion_dashboard.html", "cs/partials/completion_dashboard_fragment.html",
                        "foms/web/cs/completion_dashboard.py"),
    "/erp/history/": ("orders/history_dashboard.html", "orders/partials/history_dashboard_fragment.html",
                      "foms/web/orders/history.py"),
}

#: 의도된 예외 — {셸 경로: {static 기준 스크립트 경로: 이유}}. 이유 없는 등재는 금지.
#: (2026-11-18 현재 0건. 넣기 전에 "스왑 진입에서 그 기능이 정말 필요 없는가"를 실화면으로 확인하라.)
ALLOWED_FULL_ONLY: dict[str, dict[str, str]] = {}

#: 모든 셸 문서에 늘 있는 공용 레이아웃 조각(스왑으로 바뀌지 않는다).
SHARED_LAYOUT_PARTS = (
    "partials/shared/layout_head.html",
    "partials/shared/layout_scripts.html",
    "partials/shared/layout_nav.html",
    "partials/shared/layout_flash.html",
)

_COMMENT_RE = re.compile(r"\{#.*?#\}", re.S)
_REF_RE = re.compile(r"\{%-?\s*(?:include|extends|import|from)\s+['\"]([^'\"]+)['\"]")
_SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*\"([^\"]+)\"", re.I)
_URL_FOR_RE = re.compile(r"filename\s*=\s*['\"]([^'\"]+)['\"]")
_CHAIN_LIT_RE = re.compile(r"['\"]/static/(js/[^'\"?]+\.js)")

Loader = Callable[[str], "str | None"]


def _disk_loader(name: str) -> str | None:
    path = TEMPLATES / name
    return path.read_text(encoding="utf-8") if path.exists() else None


def _disk_js(rel: str) -> str | None:
    path = STATIC / rel
    return path.read_text(encoding="utf-8") if path.exists() else None


def _script_name(src: str) -> str:
    m = _URL_FOR_RE.search(src)
    if m:
        return m.group(1)
    src = src.split("?", 1)[0]
    return src[len("/static/"):] if src.startswith("/static/") else src


def collect_scripts(name: str, load: Loader = _disk_loader, load_js: Loader = _disk_js,
                    skip: tuple[str, ...] = ()) -> dict[str, str]:
    """``name`` 에서 닿는 ``<script src>`` → 처음 본 템플릿. ``*-entry.js`` 는 CHAIN 문자열까지 펼친다."""
    found: dict[str, str] = {}
    seen: set[str] = set(skip)

    def walk(tpl: str) -> None:
        if tpl in seen:
            return
        seen.add(tpl)
        text = load(tpl)
        if text is None:
            return
        text = _COMMENT_RE.sub("", text)
        for m in _SCRIPT_SRC_RE.finditer(text):
            js = _script_name(m.group(1))
            found.setdefault(js, tpl)
            if js.endswith("-entry.js"):
                for chained in _CHAIN_LIT_RE.findall(load_js(js) or ""):
                    found.setdefault(chained, f"{tpl} → {js}")
        for m in _REF_RE.finditer(text):
            walk(m.group(1))

    walk(name)
    return found


def full_only_scripts(full: str, frag: str, load: Loader = _disk_loader, load_js: Loader = _disk_js) -> dict[str, str]:
    """온전한 페이지(공용 레이아웃 제외)에만 있고 셸 조각 길에 없는 스크립트."""
    base: dict[str, str] = {}
    for part in SHARED_LAYOUT_PARTS:
        base.update(collect_scripts(part, load, load_js))
    full_set = collect_scripts(full, load, load_js, skip=SHARED_LAYOUT_PARTS)
    frag_set = collect_scripts(frag, load, load_js, skip=SHARED_LAYOUT_PARTS)
    return {js: where for js, where in full_set.items() if js not in frag_set and js not in base}


def _subordinate_shell_paths() -> set[str]:
    """erp-shell.js 가 FRAGMENT_READY 밖에서 스왑하는 하위 경로(문자열 그대로 읽는다)."""
    src = ERP_SHELL_JS.read_text(encoding="utf-8")
    body = src.split("function isSubordinateShellFragmentPath", 1)[1].split("\n  }\n", 1)[0]
    paths = set(re.findall(r"p === '([^']+)'", body))
    linked = re.search(r"var LINKED_FRESH_PATHS = \[([^\]]*)\]", src)
    assert linked and "LINKED_FRESH_PATHS.indexOf(p)" in body, "erp-shell.js 하위 경로 판정 모양이 바뀌었다 — 이 시험을 맞춰라"
    paths |= set(re.findall(r"'([^']+)'", linked.group(1)))
    if "drawing-workbench\\/\\d+" in body:
        paths.add("/erp/drawing-workbench/<id>")
    return paths


def test_shell_screen_map_covers_every_swapped_path():
    """셸이 스왑하는 경로(FRAGMENT_READY + 하위)는 전부 이 감사 표에 있어야 한다."""
    expected = set(ERP_FRAGMENT_READY_PATHS) | _subordinate_shell_paths()
    assert expected == set(SHELL_SCREENS), f"감사 표 누락/잉여: {sorted(expected ^ set(SHELL_SCREENS))}"


@pytest.mark.parametrize("path", sorted(SHELL_SCREENS))
def test_route_still_renders_the_mapped_templates(path: str):
    """표가 라우트와 어긋나면(템플릿 이름 변경) 감사가 엉뚱한 파일을 본다 — 라우트 소스에 두 이름이 있어야 한다."""
    full, frag, route = SHELL_SCREENS[path]
    src = (ROOT / route).read_text(encoding="utf-8")
    assert full in src and frag in src, f"{path}: {route} 가 {full} / {frag} 를 고르지 않는다"


@pytest.mark.parametrize("path", sorted(SHELL_SCREENS))
def test_full_page_scripts_also_ride_the_shell_fragment(path: str):
    """온전한 페이지에만 있는 화면 JS = 다른 탭에서 셸 스왑으로 들어오면 그 기능이 무음으로 죽는다."""
    full, frag, _route = SHELL_SCREENS[path]
    missing = full_only_scripts(full, frag)
    allowed = ALLOWED_FULL_ONLY.get(path, {})
    for js, reason in allowed.items():
        assert reason.strip(), f"{path}: 예외 {js} 에 이유가 없다"
    leftover = {js: where for js, where in missing.items() if js not in allowed}
    assert not leftover, (
        f"{path}: 온전한 페이지에만 실리는 스크립트 → 셸 스왑 진입에서 죽는다. {leftover}\n"
        f"고치는 길: 그 화면의 본문 파샬(온전한 페이지와 조각이 함께 include)에 data-foms-run-once 로 두거나, "
        f"entry CHAIN(예 static/js/shipment/shipment-entry.js)에 넣는다. 조각 {frag}"
    )


def test_audit_flags_a_script_that_lives_only_in_the_full_page():
    """음성 대조군: 블록에만 있는 스크립트 · 도메인 레이아웃에만 있는 스크립트는 잡고, 본문 · CHAIN 것은 통과시킨다."""
    tpls = {
        "x/layout.html": "{% include 'partials/shared/layout_scripts.html' %}<script src=\"{{ url_for('static', "
                         "filename='js/x/layout-only.js') }}\"></script>{% block scripts %}{% endblock %}",
        "partials/shared/layout_scripts.html": "<script src=\"{{ url_for('static', filename='js/shared.js') }}\"></script>",
        "x/page.html": "{% extends 'x/layout.html' %}{% block content %}{% include 'x/body.html' %}{% endblock %}"
                       "{% block scripts %}<script defer src=\"{{ url_for('static', filename='js/x/block-only.js') }}"
                       "?v=1\"></script>{# <script src=\"{{ url_for('static', filename='js/x/commented.js') }}\"> #}"
                       "{% endblock %}",
        "x/body.html": "<script data-foms-run-once src=\"{{ url_for('static', filename='js/x/body.js') }}\"></script>"
                       "<script src=\"{{ url_for('static', filename='js/x/x-entry.js') }}\"></script>",
        "x/frag.html": "{% include 'x/body.html' %}",
    }
    js = {"js/x/x-entry.js": "var CHAIN = ['/static/js/x/chained.js?v=' + V];"}
    missing = full_only_scripts("x/page.html", "x/frag.html", tpls.get, js.get)
    assert set(missing) == {"js/x/block-only.js", "js/x/layout-only.js"}
    frag = collect_scripts("x/frag.html", tpls.get, js.get)
    assert {"js/x/body.js", "js/x/x-entry.js", "js/x/chained.js"} <= set(frag)


def test_audit_sees_the_real_fixed_scripts_on_the_fragment_path():
    """양성 대조군(실제 파일): 2026-11-18 에 고친 스크립트가 조각 길에서 실제로 보인다 — 수집기가 눈을 감지 않았다."""
    ship = collect_scripts("shipment/partials/dashboard_fragment.html")
    assert "js/shipment/foms-packing.js" in ship and "js/foms/foms-reason-sheet.js" in ship
    cons = collect_scripts("construction/partials/dashboard_fragment.html")
    for name in ("js/construction/foms-complete-gate.js", "js/foms/tablet-construction-workmode.js",
                 "js/shipment/foms-packing.js"):
        assert name in cons, name
    home = collect_scripts("orders/partials/dashboard_main.html")
    for name in ("js/orders/foms-call-filter.js", "js/orders/erp-stage-override.js", "js/foms/foms-admin-override.js"):
        assert name in home, name
