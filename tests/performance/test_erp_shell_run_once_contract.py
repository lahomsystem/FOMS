"""P2-3: ERP 셸 공용 스크립트 1회 실행 + 탭 스왑 메모리 누적 재발 방지 계약(정적 검사).

배경(2026-10-01 성능 검사 원장 P2-3, 2026-10-02 로컬 실측):
- 9탭 조각마다 셸(erp_mobile_shell.html → foms_app_shell.html)이 들어 있어 탭을 바꿀 때마다
  erp-shell.js activateScripts() 가 공용 스크립트 19개 + 인라인 1개를 다시 실행했다.
  Alpine·htmx 가 스왑마다 새 인스턴스를 띄웠다(45스왑에 alpine:init 46회).
- 완료↔이력 100스왑에 분리 DOM 노드 7,842개·document 리스너 142→338. 힙 스냅샷의 붙잡는 경로는
  Bootstrap 전역 Map(요소→인스턴스)이 쥔 셸 메뉴 서랍(.offcanvas)과 한 번 연 비용 청구 모달이었다.
  완료 탭 인라인 스크립트는 사진 목록이 커서 가장 크게 보였을 뿐 스스로 붙잡지는 않았다.

검사 대상은 문자열·순서다(CI 에 JS 런타임 없음). 각 검사 함수에는 음성 대조군을 둔다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ERP_SHELL_JS = ROOT / "static/js/runtime/erp-shell.js"
SHELL_ENTRY = "partials/shared/foms_app_shell.html"
RUN_ONCE = "data-foms-run-once"

_SCRIPT_OPEN_RE = re.compile(r"<script\b[^>]*>", re.I)
_INCLUDE_RE = re.compile(r"{%\s*include\s+['\"]([^'\"]+)['\"]")
_FILENAME_RE = re.compile(r"filename\s*=\s*['\"]([^'\"]+\.js)['\"]")

# 셸 공용 스크립트 정본 목록. 늘거나 줄면 이 목록과 아래 재연결 표를 같이 고친다.
EXPECTED_SHELL_SCRIPTS = {
    "js/vendor/htmx.min.js",
    "js/foms/alpine-store.js",
    "js/vendor/alpine.min.js",
    "js/foms/attachment-preview-zoom.js",
    "js/foms/erp-attachment-preview-open.js",
    "js/foms/lightbox.js",
    "js/foms/voice-input.js",
    "js/foms/haptic.js",
    "js/foms/sync.js",
    "js/foms/bottom-nav-shell.js",
    "js/foms/search.js",
    "js/foms/kv-copy.js",
    "js/foms/mobile-queue-scroll.js",
    "js/foms/mobile-queue-focus.js",
    "js/foms/mobile-tower.js",
    "js/runtime/erp-mobile-shell.js",
    "js/foms/foms-order-timeline-sheet.js",
    "js/foms/foms-write.js",
    "js/foms/foms-qr-scan.js",
}

# 셸 조각 DOM(스왑마다 새로 들어옴)에 직접 붙는 스크립트는 다시 실행되지 않으므로 스왑 이벤트에서
# 다시 연결해야 한다. 파일 → 그 연결을 증명하는 문자열.
SWAP_REBIND_TOKENS = {
    "js/foms/mobile-tower.js": "document.addEventListener('foms:main-content-swapped', initTower)",
    "js/foms/voice-input.js": 'document.addEventListener("foms:main-content-swapped", init)',
    "js/foms/foms-qr-scan.js": "document.addEventListener('foms:main-content-swapped', revealTriggers)",
    "js/runtime/erp-mobile-shell.js": "document.addEventListener('foms:main-content-swapped', initMobileShell)",
    "js/foms/mobile-queue-scroll.js": "document.addEventListener('foms:main-content-swapped', initMobileQueueScroll)",
    "js/foms/mobile-queue-focus.js": "document.addEventListener('foms:main-content-swapped', init)",
    "js/foms/erp-attachment-preview-open.js": 'document.addEventListener("foms:main-content-swapped"',
    "js/foms/bottom-nav-shell.js": 'document.addEventListener("foms:erp-shell-fragment-swapped", onFragmentSwapped)',
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _shell_templates(entry: str = SHELL_ENTRY) -> list[str]:
    """셸 진입 템플릿에서 include 를 따라간 템플릿 목록(진입 포함)."""
    seen: list[str] = []
    stack = [entry]
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.append(rel)
        stack.extend(_INCLUDE_RE.findall(_read(ROOT / "templates" / rel)))
    return seen


def _unmarked_script_tags(html: str) -> list[str]:
    """run-once 표식이 없는 <script> 여는 태그."""
    return [tag for tag in _SCRIPT_OPEN_RE.findall(html) if RUN_ONCE not in tag]


def _apply_fragment_body(js: str) -> str:
    return js.split("function applyFragmentToMain(html, swapUrl) {", 1)[1].split("\n  }\n", 1)[0]


def _order_ok(body: str, *tokens: str) -> bool:
    """tokens 가 body 안에 모두 있고 주어진 순서대로 나오는가."""
    idx = [body.find(t) for t in tokens]
    return all(i >= 0 for i in idx) and idx == sorted(idx)


def test_every_shell_script_is_marked_run_once() -> None:
    """셸 include 트리의 <script> 는 전부 run-once 표식을 단다(새 셸 스크립트도 자동 검사)."""
    templates = _shell_templates()
    assert "partials/shared/htmx_layout.html" in templates
    assert "partials/shared/alpine_layout.html" in templates
    violations = {
        rel: tags for rel in templates if (tags := _unmarked_script_tags(_read(ROOT / "templates" / rel)))
    }
    assert not violations, violations


def test_unmarked_script_checker_negative_control() -> None:
    """음성 대조군: 표식 없는 태그는 잡고, 있는 태그는 통과시킨다."""
    assert _unmarked_script_tags('<script src="a.js" defer></script>') == ['<script src="a.js" defer>']
    assert _unmarked_script_tags("<script defer>\nx()\n</script>") == ["<script defer>"]
    assert _unmarked_script_tags(f'<script {RUN_ONCE} src="a.js" defer></script>') == []
    assert _unmarked_script_tags(f'<script defer {RUN_ONCE}="htmx-config">x()</script>') == []


def test_shell_script_list_matches_ssot() -> None:
    """셸이 싣는 외부 스크립트 = 정본 목록. 인라인 htmx 설정은 고정 키로 1회만."""
    found: set[str] = set()
    for rel in _shell_templates():
        found.update(_FILENAME_RE.findall(_read(ROOT / "templates" / rel)))
    assert found == EXPECTED_SHELL_SCRIPTS
    htmx_layout = _read(ROOT / "templates/partials/shared/htmx_layout.html")
    assert f'<script defer {RUN_ONCE}="htmx-config">' in htmx_layout


def test_activate_scripts_skips_already_executed_run_once() -> None:
    """activateScripts 는 등록된 run-once 키면 새 <script> 를 만들기 전에 건너뛴다."""
    js = _read(ERP_SHELL_JS)
    assert f"var RUN_ONCE_ATTR = '{RUN_ONCE}';" in js
    body = js.split("function activateScripts(container) {", 1)[1].split("\n  }\n", 1)[0]
    assert _order_ok(
        body,
        "old.hasAttribute(RUN_ONCE_ATTR)",
        "executedScriptKeys[runOnceKey]",
        "return;",
        "document.createElement('script')",
        "executedScriptKeys[runOnceKey] = true;",
    ), body
    # 받기 실패한 스크립트는 다음 스왑에서 다시 시도한다.
    assert "delete executedScriptKeys[runOnceKey];" in body


def test_registry_is_built_before_innerhtml_and_htmx_processed_after() -> None:
    """첫 스왑에서도 건너뛰려면 innerHTML 이 옛 셸 <script> 를 지우기 전에 등록해야 한다.
    htmx 는 다시 실행되지 않으므로 새 조각의 hx-* 를 스왑 뒤 직접 연결한다."""
    body = _apply_fragment_body(_read(ERP_SHELL_JS))
    assert _order_ok(
        body,
        "teardownOpenOverlays(main);",
        "disposeBootstrapInstances(main);",
        "ensureExecutedScriptRegistry();",
        "main.innerHTML = html;",
        "activateScripts(main);",
        "processHtmxIn(main);",
        "finishErpShellFragmentSwap(swapUrl);",
    ), body


def test_order_checker_negative_control() -> None:
    """음성 대조군: 등록이 innerHTML 뒤면(옛 셸 <script> 가 이미 지워짐) 순서 검사가 실패한다."""
    bad = "main.innerHTML = html;\nensureExecutedScriptRegistry();\nactivateScripts(main);"
    assert not _order_ok(bad, "ensureExecutedScriptRegistry();", "main.innerHTML = html;")
    assert not _order_ok("activateScripts(main);", "ensureExecutedScriptRegistry();", "activateScripts(main);")


def test_swap_disposes_all_bootstrap_instances_not_only_open_ones() -> None:
    """누수 재발 방지: 닫힌 인스턴스도 정리해야 Bootstrap 전역 Map 이 옛 화면을 놓는다.
    셸 메뉴 서랍(.offcanvas)은 erp-mobile-shell.js 가 스왑마다 getOrCreateInstance 한다."""
    js = _read(ERP_SHELL_JS)
    sel = js.split("var BOOTSTRAP_DISPOSE_SELECTOR =", 1)[1].split(";", 1)[0]
    for needle in (".modal", ".offcanvas", ".collapse", ".toast", '[data-bs-toggle="dropdown"]'):
        assert needle in sel, needle
    assert ".show" not in sel  # 열린 것만 고르면 닫힌 인스턴스가 남는다(기존 teardownOpenOverlays 한계)
    comps = js.split("var BOOTSTRAP_DISPOSE_COMPONENTS =", 1)[1].split(";", 1)[0]
    for name in ("'Modal'", "'Offcanvas'", "'Collapse'", "'Toast'", "'Dropdown'"):
        assert name in comps, name
    body = js.split("function disposeBootstrapInstances(container) {", 1)[1].split("\n  }\n", 1)[0]
    assert "instance.dispose();" in body
    drawer = _read(ROOT / "templates/partials/shared/erp_mobile_menu_drawer.html")
    assert 'class="offcanvas ' in drawer
    assert "Offcanvas.getOrCreateInstance(drawer)" in _read(ROOT / "static/js/runtime/erp-mobile-shell.js")


def test_shell_dom_scripts_rebind_on_swap_instead_of_rerun() -> None:
    """다시 실행되지 않는 셸 스크립트 중 셸 조각 DOM 에 직접 붙는 것은 스왑 이벤트로 다시 연결한다."""
    missing = [
        rel for rel, token in SWAP_REBIND_TOKENS.items() if token not in _read(ROOT / "static" / rel)
    ]
    assert not missing, missing
    assert set(SWAP_REBIND_TOKENS) <= EXPECTED_SHELL_SCRIPTS
    nav = _read(ROOT / "static/js/foms/bottom-nav-shell.js")
    swapped = nav.split("function onFragmentSwapped(ev) {", 1)[1].split("\n  }\n", 1)[0]
    assert "initBottomNavTapFeedback();" in swapped


def test_mobile_tower_does_not_pin_old_dom() -> None:
    """타워 제어기는 타워 없는 화면으로 가면 비운다 — 모듈 변수가 옛 대시보드 DOM 을 붙잡지 않게."""
    js = _read(ROOT / "static/js/foms/mobile-tower.js")
    init = js.split("function initTower() {", 1)[1].split("\n  }\n", 1)[0]
    assert _order_ok(init, "if (!root) {", "activeTower = null;", "return;")
    assert "root.dataset.fomsTowerBound === '1'" in init
    # 파일 최상단에서 한 번 잡은 root 로 바인딩하던 옛 구조(재실행에 기대던 구조)로 돌아가지 않는다.
    assert not re.search(r"^  var root = document\.querySelector", js, re.M)
