"""정산 대시보드 · 탭 "제품별" **화면** 계약 테스트 (2026-10-07, 승인 목업 이식).

API 숫자·불변식은 `test_settlement_products.py`(서버 쪽)가 잡는다. 이 파일은 화면이 **놓치면 조용히
망가지는 것**만 잠근다:

1. 탭 ↔ pane 배선(id·aria·hidden)과 자리(분석 뒤 · 네이버 정산 앞), 파셜 include 1회.
2. 루트 훅(`data-foms-settlement-products` · `data-products-url`) — JS 가 화면과 API 를 찾는 길.
3. 자산 핀 — 셸 사슬과 같은 값, 셸 안 1번, 저장소 전역 1값(서비스워커 cache-first).
4. JS 가 API 최상위 키를 전부 읽고, 셸 공통 기간·탭 활성화 속성을 관찰하며, fetch 를
   try/catch + `success === true` 로 감싼다(무음 실패 금지).
5. 상태 4종(불러오는 중 · 실패 · 권한 없음 · 빈 기간)이 서로 다른 노드.
6. 위생 — 인라인 style·Jinja JSON·jQuery·innerHTML 없음, CSS 는 `.foms-settle` 아래 `s-pr`
   이름만, 글자 크기는 전부 `--s-fs` 배율.

헬퍼는 요약 탭 렌더 계약에서 import 한다(복제하면 프래그먼트 헤더·핀 추출 규칙이 갈린다).
문서 디렉토리는 읽지 않는다(CI-DOCSCOPE-01).
"""

from __future__ import annotations

import re

import pytest

from tests.domains.test_settlement_dashboard_render import (  # noqa: E402
    _HIDDEN_ATTR_RE,
    _MOCKUP_LEFTOVERS,
    _PIN_SUFFIX,
    _attr,
    _fragment_html,
    _js_function_body,
    _login_allowed,
    _pins_for,
    _read,
    _read_code,
    _repo_pin_scan_sources,
    _strip_comments,
    _tab_buttons,
    _tab_panels,
)
from tests.domains.test_settlement_dashboard_render import CSS_ASSET as SUMMARY_CSS  # noqa: E402

SHELL_TEMPLATE = "templates/cs/partials/settlement_dashboard_body.html"
PARTIAL_TEMPLATE = "templates/cs/partials/settlement_products_body.html"
CSS_ASSET = "css/settlement/settlement-products.css"
#: 로드 순서대로(조각 4개 → 진입점). 파일당 300줄 래칫 때문에 나눴다.
JS_ASSETS = (
    "js/settlement/products-core.js",
    "js/settlement/products-cards.js",
    "js/settlement/products-charts.js",
    "js/settlement/products-quality.js",
    "js/settlement/products.js",
)
ALL_ASSETS = (CSS_ASSET,) + JS_ASSETS

TAB_ID = "foms-settle-tab-products"
PANE_ID = "foms-settle-pane-products"
API_URL = "/api/settlement/products"

#: 서버 계약(C:/tmp 계약서 §API)의 data 최상위 키 — 화면이 하나라도 안 읽으면 그 카드가 빈다.
API_KEYS = (
    "range", "families", "series", "period", "trend", "selected_months",
    "top_names", "unmapped_top", "coverage", "allocation_check",
)
#: 상태 노드 4종(서로 다른 노드·문구).
STATE_HOOKS = ("data-products-loading", "data-products-error", "data-products-denied", "data-products-empty")

_SCALED_FONT_RE = re.compile(r"font-size:\s*calc\([\d.]+px \* var\(--s-fs, 1\)\)")
_ANY_FONT_RE = re.compile(r"font-size\s*:\s*([^;}]+)")
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _js_all() -> str:
    """제품별 탭 스크립트 전부(주석 제거)를 이어 붙인다 — 키·배선은 어느 조각에 있어도 된다."""
    return "\n".join(_read_code(f"static/{rel}") for rel in JS_ASSETS)


def _products_pane(html: str) -> str:
    """렌더 HTML 에서 제품별 pane 구간(pane 시작 ~ 다음 pane 또는 툴팁 전)을 잘라낸다."""
    start = html.index(f'id="{PANE_ID}"')
    nxt = [i for i in (html.find('role="tabpanel"', start + 1), html.find('id="foms-settle-tooltip"', start)) if i > 0]
    return html[start:min(nxt)] if nxt else html[start:]


# ==========================================================================
# 1 — 탭 ↔ pane 배선
# ==========================================================================
def test_products_tab_sits_between_analytics_and_channel(client, app):
    """제품별 탭 버튼이 분석 뒤 · 네이버 정산 앞에 있고 aria 배선이 pane 과 짝이다."""
    _login_allowed(client)
    html = _fragment_html(client)

    keys = [_attr(tag, "data-settlement-tab") for tag, _ in _tab_buttons(html)]
    assert "products" in keys, keys
    at = keys.index("products")
    assert keys[at - 1] == "analytics", keys
    assert at + 1 == len(keys) or keys[at + 1] == "channel", keys

    tag, inner = _tab_buttons(html)[at]
    assert _attr(tag, "id") == TAB_ID, tag
    assert _attr(tag, "aria-controls") == PANE_ID, tag
    assert _attr(tag, "aria-selected") == "false", tag
    assert _attr(tag, "tabindex") == "-1", tag
    assert "제품별" in inner, inner

    panes = {_attr(p, "data-settlement-pane"): p for p in _tab_panels(html)}
    pane = panes.get("products")
    assert pane, panes.keys()
    assert _attr(pane, "id") == PANE_ID, pane
    assert _attr(pane, "aria-labelledby") == TAB_ID, pane
    assert _HIDDEN_ATTR_RE.search(pane), "제품별 pane 이 첫 렌더에 열려 있다"


def test_partial_is_included_once_inside_the_products_pane(client, app):
    """셸이 파셜을 정확히 1번 include 하고, 렌더 결과에서 루트가 제품별 pane 안에 있다."""
    shell = _strip_comments(_read(SHELL_TEMPLATE))
    assert shell.count("cs/partials/settlement_products_body.html") == 1

    _login_allowed(client)
    html = _fragment_html(client)
    assert html.count('data-foms-settlement-products="1"') == 1
    assert 'data-foms-settlement-products="1"' in _products_pane(html), "루트가 제품별 pane 밖에 있다"


def test_root_carries_the_products_api_url(client, app):
    """루트가 `data-products-url` 로 API 경로를 싣는다(JS 하드코딩 대신 url_for)."""
    _login_allowed(client)
    root = re.search(r"<div\b[^>]*data-foms-settlement-products=\"1\"[^>]*>", _fragment_html(client))
    assert root, "제품별 루트가 렌더에 없다"
    assert _attr(root.group(0), "data-products-url") == API_URL, root.group(0)
    assert "url_for('settlement_api.api_settlement_products')" in _read(PARTIAL_TEMPLATE)


# ==========================================================================
# 2 — 자산 핀
# ==========================================================================
@pytest.mark.parametrize("asset", ALL_ASSETS)
def test_products_asset_is_linked_once_with_the_shell_pin(asset):
    """자산이 셸에 정확히 1번, 요약 CSS 와 같은 핀으로 실린다."""
    shell = _read_code(SHELL_TEMPLATE)
    hits = re.compile(re.escape(asset) + _PIN_SUFFIX).findall(shell)
    assert len(hits) == 1, f"{asset}: 셸 안 링크 {len(hits)}개"
    assert set(hits) == _pins_for(SUMMARY_CSS, shell), f"{asset}: 셸 사슬 핀과 다르다 {hits}"


@pytest.mark.parametrize("asset", ALL_ASSETS)
def test_products_asset_pin_is_single_repo_wide(asset):
    """자산 하나당 핀이 저장소 전역에서 한 값이다."""
    pattern = re.compile(re.escape(asset) + _PIN_SUFFIX)
    pins = {pin for path in _repo_pin_scan_sources()
            for pin in pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))}
    assert len(pins) == 1, f"{asset}: 핀 {sorted(pins)}"


def test_products_scripts_are_deferred_and_entry_loads_last(client, app):
    """스크립트 5개가 전부 defer 이고, 진입점(products.js)이 조각들 뒤에 실린다."""
    _login_allowed(client)
    html = _fragment_html(client)
    positions = []
    for asset in JS_ASSETS:
        tag = re.search(r"<script\b[^>]*%s[^>]*>" % re.escape(asset), html)
        assert tag, f"{asset} 스크립트가 렌더에 없다"
        assert re.search(r"\bdefer\b", tag.group(0)), tag.group(0)
        positions.append(tag.start())
    assert positions == sorted(positions), "로드 순서가 조각 → 진입점이 아니다"


# ==========================================================================
# 3 — JS 계약
# ==========================================================================
@pytest.mark.parametrize("key", API_KEYS)
def test_js_reads_every_top_level_api_key(key):
    """API data 최상위 키를 화면 코드가 읽는다(`.key` 또는 `'key'`)."""
    js = _js_all()
    assert re.search(r"(\.%s\b|['\"]%s['\"])" % (key, key), js), f"JS 가 '{key}' 를 읽지 않는다"


def test_js_follows_shell_range_and_tab_activation():
    """셸의 공통 기간 속성과 탭 활성화 속성을 MutationObserver 로 관찰한다(새 이벤트 발명 금지)."""
    js = _read_code("static/js/settlement/products.js")
    assert "MutationObserver" in js
    assert "attributeFilter: ['data-settlement-date-range']" in js
    assert "attributeFilter: ['data-settlement-active-tab']" in js
    assert "var PRODUCTS_TAB = 'products'" in js
    assert re.search(r"date_from=.*date_to=", js, re.S), "조회 URL 에 기간을 싣지 않는다"


def test_js_fetch_is_guarded_and_distinguishes_403():
    """fetch 가 try/catch 안이고 `success !== true` 를 실패로 보며, 403 은 권한 상태로 간다."""
    js = _read_code("static/js/settlement/products.js")
    body = _js_function_body(js, "load")
    assert body.index("try {") < body.index("await fetch(") < body.index("catch (err)"), body[:300]
    assert "body.success !== true" in body
    assert re.search(r"status === 403\)\s*\{\s*showState\(ctx, 'denied'\)", body), body
    assert "seq !== state.seq" in body, "늦게 온 응답이 최신 기간 화면을 덮는다"


def test_js_mount_is_idempotent_and_survives_fragment_swap():
    """싱글톤 가드 뒤 swap 리스너, 루트 표식, 떨어진 루트 정리가 있다(perf G4)."""
    js = _read_code("static/js/settlement/products.js")
    assert "window.__FOMS_SETTLEMENT_PRODUCTS_BOUND" in js
    assert "settlementProductsMounted" in js
    for ev in ("foms:main-content-swapped", "foms:erp-shell-fragment-swapped"):
        assert ev in js, ev
    assert "isConnected" in js and ".disconnect()" in js
    assert _js_all().count("document.addEventListener") == 3
    assert "window.addEventListener" not in _js_all(), "전역 window 리스너는 스왑마다 누적된다"


def test_js_has_no_jquery_or_html_injection():
    """jQuery·innerHTML·insertAdjacentHTML 없이 textContent 로만 그린다."""
    js = _js_all()
    for bad in ("innerHTML", "insertAdjacentHTML", "outerHTML", "jQuery", "$(", "document.write"):
        assert bad not in js, f"금지 패턴 '{bad}'"


# ==========================================================================
# 4 — 상태 4종 · 위생
# ==========================================================================
def test_four_states_are_distinct_server_rendered_nodes(client, app):
    """불러오는 중 · 실패 · 권한 없음 · 빈 기간이 각각 다른 노드로 pane 안에 렌더된다."""
    _login_allowed(client)
    pane = _products_pane(_fragment_html(client))
    texts = []
    for hook in STATE_HOOKS:
        m = re.search(r"<(\w+)\b[^>]*\b%s\b[^>]*>(.*?)</\1>" % re.escape(hook), pane, re.S)
        assert m, f"{hook} 노드가 없다"
        texts.append(re.sub(r"<[^>]+>|\s+", "", m.group(2)))
    assert len(set(texts)) == len(texts), "상태 문구가 겹친다"
    assert "data-products-retry" in pane, "실패 상태에 재시도 버튼이 없다"
    assert 'data-products-grid' in pane


def test_partial_has_no_inline_style_jinja_json_or_mockup_leftovers():
    """파셜에 인라인 style · Jinja JSON 주입 · 목업 잔재 낱말이 없다."""
    code = _read_code(PARTIAL_TEMPLATE)
    assert not re.search(r"\bstyle\s*=", code)
    assert "tojson" not in code and "JSON.parse" not in code
    for rel in (PARTIAL_TEMPLATE, *(f"static/{a}" for a in JS_ASSETS)):
        for phrase in _MOCKUP_LEFTOVERS:
            assert phrase not in _read_code(rel), f"{rel}: 목업 잔재 '{phrase}'"


def test_products_css_is_scoped_prefixed_and_font_scaled():
    """모든 선택자가 `.foms-settle` 아래 `s-pr` 이름을 물고, 글자 크기는 전부 `--s-fs` 배율이다."""
    css = _CSS_COMMENT_RE.sub(" ", _read(f"static/{CSS_ASSET}"))
    for rule in css.split("}"):
        if "{" not in rule:
            continue
        selector = rule.rsplit("{", 1)[0].split("{")[-1]
        for part in selector.split(","):
            part = part.strip()
            if not part or part.startswith(("from", "to")) or part.endswith("%"):
                continue
            assert part.startswith(".foms-settle"), f"스코프 밖 선택자: {part}"
            assert ".s-pr" in part, f"s-pr 이름이 아닌 선택자: {part}"
    for value in _ANY_FONT_RE.findall(css):
        assert re.fullmatch(r"calc\([\d.]+px \* var\(--s-fs, 1\)\)", value.strip()), value
    assert _SCALED_FONT_RE.search(css)
    assert "--s-fs:" not in css, "배율 토큰은 요약 CSS 루트 1곳에만 선언한다"


def test_chart_only_filter_controls_hide_on_the_products_tab():
    """제품별 탭에서는 그래프 단위 조작(`.s-fb-chart`)을 감춘다(기간 바 자체는 공유)."""
    css = _read_code(f"static/{SUMMARY_CSS}")
    assert re.search(
        r'\[data-settlement-active-tab="products"\]\s*\.s-fb-chart[^{]*\{[^}]*display\s*:\s*none', css
    ), "제품별 탭에서 그래프 조작을 감추는 규칙이 없다"
