"""정산 대시보드 · 탭 "영업 수수료" **화면** 계약 테스트 (FCOMM-01 §2.1 · 플랜 T6).

API 숫자 · 권한은 `test_sales_commission_api.py`(서버 쪽)가 잡는다. 이 파일은 화면이 **놓치면 조용히
망가지는 것**만 잠근다:

1. 탭 ↔ pane 배선(id · aria · hidden)과 자리(맨 끝), 파셜 include 1회. 회계팀 밖은 화면째 403.
2. 루트 훅(`data-foms-settlement-commission` · `data-settlement-cm-*-api`) — JS 가 화면과 API 를 찾는 길.
3. 자산 핀 — 수수료 사슬(CSS 1 + JS 6)은 한 값, 셸 안 1번, 저장소 전역 1값(서비스워커 cache-first).
4. JS 가 API 경로 · 본문 칸 이름을 맞게 쓰고, 탭 활성화 속성을 관찰하며, fetch 를 try/catch +
   `success === true` 로 감싼다(무음 실패 금지). 주문마다 저장 줄을 세운다(빠른 입력 경합).
5. 위생 — 인라인 style · jQuery · innerHTML 없음, CSS 는 `.foms-settle` 아래만, 파일당 300줄 미만.

헬퍼는 요약 탭 렌더 계약에서 import 한다(복제하면 프래그먼트 헤더 · 핀 추출 규칙이 갈린다).
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
    _full_html,
    _login_allowed,
    _pins_for,
    _read,
    _read_code,
    _repo_pin_scan_sources,
    _tab_buttons,
    _tab_panels,
)

SHELL_TEMPLATE = "templates/cs/partials/settlement_dashboard_body.html"
PARTIAL_TEMPLATE = "templates/cs/partials/settlement_commission_body.html"
PARTIAL_NAME = "cs/partials/settlement_commission_body.html"
CSS_ASSET = "css/settlement/settlement-commission.css"
#: 로드 순서대로(조각 4개 → 진입점). 파일당 300줄 래칫 때문에 나눴다.
JS_ASSETS = (
    "js/settlement/commission-core.js",
    "js/settlement/commission-table.js",
    "js/settlement/commission-edit.js",
    "js/settlement/commission-deduct.js",
    "js/settlement/commission-close.js",
    "js/settlement/commission.js",
)
ALL_ASSETS = (CSS_ASSET,) + JS_ASSETS

TAB_ID = "foms-settle-tab-commission"
PANE_ID = "foms-settle-pane-commission"

#: 파셜이 서버 렌더 시점에 갖고 있어야 하는 훅 — JS `collectEls()` 가 이 이름으로 찾는다.
PARTIAL_HOOKS = (
    "data-foms-settlement-commission",
    'data-settlement-cm-freelancers-api="/api/sales-commission/freelancers"',
    'data-settlement-cm-rows-api="/api/sales-commission/rows"',
    'data-settlement-cm-input-api="/api/sales-commission/inputs/"',
    'data-settlement-cm-order-api="/api/orders/"',
    "data-settlement-cm-user",
    "data-settlement-cm-month",
    'data-settlement-cm-basis="completion"',
    'data-settlement-cm-basis="measurement"',
    "data-settlement-cm-forecast-note",
    "data-settlement-cm-near",
    "data-settlement-cm-msg",
    "data-settlement-cm-loading",
    "data-settlement-cm-empty",
    "data-settlement-cm-gridwrap",
    "data-settlement-cm-total",
    "data-settlement-cm-rows",
    "data-settlement-cm-dialog",
    "data-settlement-cm-ded-amount",
    "data-settlement-cm-ded-reason",
    "data-settlement-cm-ded-add",
    # T10 달 마감 · 마감 기록
    'data-settlement-cm-closings-api="/api/sales-commission/closings"',
    'data-settlement-cm-export-api="/api/sales-commission/export.csv"',
    "data-settlement-cm-close-open",
    "data-settlement-cm-closings",
    "data-settlement-cm-closings-rows",
    "data-settlement-cm-closings-empty",
    "data-settlement-cm-close-dialog",
    "data-settlement-cm-close-sum",
    "data-settlement-cm-close-waiting",
    "data-settlement-cm-close-msg",
    "data-settlement-cm-close-confirm",
)

#: 표 머리 — 회계팀 엑셀과 같은 순서(설계서 §2.1-2).
COLUMNS = ("시공일", "고객명", "품목", "거래구분", "출고가", "시공비", "차감", "요율", "수수료")

_TH_RE = re.compile(r"<th\b[^>]*>(.*?)</th>", re.S)
_STYLE_ATTR_RE = re.compile(r"\bstyle\s*=\s*['\"]")


def _js(rel: str) -> str:
    return _read_code(f"static/{rel}")


def _all_js() -> str:
    return "\n".join(_js(rel) for rel in JS_ASSETS)


def _pane_html(html: str) -> str:
    """수수료 pane 시작부터 마지막 창(마감 확인 창)이 닫힐 때까지."""
    start = html.index(f'id="{PANE_ID}"')
    end = html.index("</dialog>", html.index("data-settlement-cm-close-dialog", start))
    return html[start:end]


# ==========================================================================
# 1 — 탭 · pane · 권한
# ==========================================================================
def test_accounting_user_sees_commission_tab_and_pane(client, app):
    """회계팀(STAFF + ACCOUNTING)에게 탭 버튼과 pane 이 짝을 맞춰 나온다 — 탭은 맨 끝, 기본은 닫힘."""
    _login_allowed(client, role="STAFF", team="ACCOUNTING")

    html = _fragment_html(client)

    tabs = _tab_buttons(html)
    keys = [_attr(tag, "data-settlement-tab") for tag, _ in tabs]
    assert keys[-1] == "commission", keys
    tag, inner = tabs[-1]
    assert _attr(tag, "id") == TAB_ID
    assert _attr(tag, "aria-controls") == PANE_ID
    assert _attr(tag, "aria-selected") == "false"
    assert "영업 수수료" in inner

    panels = [p for p in _tab_panels(html) if _attr(p, "id") == PANE_ID]
    assert len(panels) == 1, panels
    assert _attr(panels[0], "aria-labelledby") == TAB_ID
    assert _attr(panels[0], "data-settlement-pane") == "commission"
    assert _HIDDEN_ATTR_RE.search(panels[0]), "수수료 pane 이 기본으로 열려 있다"


@pytest.mark.parametrize("hook", PARTIAL_HOOKS)
def test_partial_renders_every_data_hook(client, app, hook):
    """파셜 훅이 실제 렌더에 실린다(조건부 include 로 꺼지는 회귀를 잡는다)."""
    _login_allowed(client)

    assert hook in _pane_html(_fragment_html(client)), hook


def test_table_columns_follow_the_spreadsheet_order(client, app):
    """표 머리가 엑셀과 같은 순서다 — 회계팀이 엑셀을 옆에 두고 칸을 맞춰 본다."""
    _login_allowed(client)

    pane = _pane_html(_fragment_html(client))
    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in _TH_RE.findall(pane)]
    assert tuple(heads[: len(COLUMNS)]) == COLUMNS, heads


def test_settings_link_points_to_the_freelancer_page(client, app):
    """요율 · 시작 달은 설정 화면에서 바꾼다 — 위 줄에 그 링크 하나."""
    _login_allowed(client)

    pane = _pane_html(_fragment_html(client))
    assert 'href="/admin/sales-freelancers"' in pane
    assert "요율 · 시작 달 설정" in pane


def test_close_button_and_closing_list_markup(client, app):
    """[마감]은 위 줄 한 개, 확인 창의 [마감하기]는 미리 보기 전까지 꺼져 있고, 마감 기록은 처음엔 숨는다."""
    _login_allowed(client)

    pane = _pane_html(_fragment_html(client))
    assert pane.count("data-settlement-cm-close-open") == 1
    assert re.search(r"<button[^>]*data-settlement-cm-close-confirm[^>]*\sdisabled[\s>]", pane)
    tag = re.search(r"<section[^>]*data-settlement-cm-closings\s[^>]*>", pane).group(0)
    assert _HIDDEN_ATTR_RE.search(tag), "마감 기록이 기본으로 열려 있다"
    assert "마감 기록" in pane
    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in _TH_RE.findall(pane)]
    assert ["달", "줄 수", "합계", "실지급", "상태"] == heads[len(COLUMNS) + 1:len(COLUMNS) + 6], heads


def test_shell_includes_the_partial_once():
    shell = _read_code(SHELL_TEMPLATE)
    assert shell.count(PARTIAL_NAME) == 1, "include 가 없거나 중복이다"


def test_non_accounting_staff_cannot_open_the_page(client, app):
    """회계팀 밖(STAFF + SALES — 프리랜서와 같은 권한 축)은 정산 화면째 403 이고 수수료 마크업도 없다."""
    _login_allowed(client, role="STAFF", team="SALES")

    resp = client.get("/erp/settlement?view=fragment", headers={"X-FOMS-ERP-SHELL": "1"})

    assert resp.status_code == 403, resp.status_code
    body = resp.get_data(as_text=True)
    for needle in (TAB_ID, "data-foms-settlement-commission", "settlement/commission.js"):
        assert needle not in body, needle


# ==========================================================================
# 2 — 자산 핀
# ==========================================================================
@pytest.mark.parametrize("asset", ALL_ASSETS)
def test_asset_is_linked_once_with_the_commission_pin(asset):
    shell = _read(SHELL_TEMPLATE)
    hits = re.compile(re.escape(asset) + _PIN_SUFFIX).findall(shell)
    assert len(hits) == 1, f"{asset}: 셸 안 링크 {len(hits)}개"


def test_commission_chain_shares_one_pin():
    """수수료 사슬 6개는 한 값 — 한 파일만 범프하면 다른 조각과 버전이 갈린다."""
    shell = _read(SHELL_TEMPLATE)
    pins = set().union(*(_pins_for(asset, shell) for asset in ALL_ASSETS))
    assert len(pins) == 1, sorted(pins)


@pytest.mark.parametrize("asset", ALL_ASSETS)
def test_asset_pin_is_single_repo_wide(asset):
    pattern = re.compile(re.escape(asset) + _PIN_SUFFIX)
    pins = {pin for path in _repo_pin_scan_sources()
            for pin in pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))}
    assert len(pins) == 1, f"{asset}: 핀 {sorted(pins)}"


def test_rendered_page_carries_pinned_deferred_assets(client, app):
    """프래그먼트 · 전체 문서 둘 다 핀 붙은 링크를 싣고, 스크립트는 defer 다(perf G1)."""
    _login_allowed(client, role="STAFF", team="ACCOUNTING")

    for html in (_fragment_html(client), _full_html(client)):
        for asset in ALL_ASSETS:
            assert _pins_for(asset, html), f"{asset} 링크에 ?v= 핀이 없다"
        for asset in JS_ASSETS:
            tag = re.search(r"<script\b[^>]*" + re.escape(asset) + r"[^>]*>", html)
            assert tag and "defer" in tag.group(0), asset


def test_scripts_load_parts_before_the_entry_point():
    shell = _read(SHELL_TEMPLATE)
    positions = [shell.index(asset) for asset in JS_ASSETS]
    assert positions == sorted(positions), "조각 → 진입점 순서가 아니다"


# ==========================================================================
# 3 — JS 계약
# ==========================================================================
def test_js_uses_the_api_contract():
    js = _all_js()
    for needle in ("'PUT'", "install_cost", "rate_override_bp", "version", "input_version",
                   "/settlement/issue", "/settlement/deductions/", "/void",
                   "department: 'SALES'", "charge_to_user_id", "default_month", "near_misses",
                   "self_edits", "data.current", "data.row"):
        assert needle in js, needle


def test_close_js_uses_the_closing_contract():
    """마감 조각이 미리 보기 · 마감 · 지급 완료 · 마감 취소 · 내려받기 경로와 서버 판정(can_close)을 쓴다."""
    close = _js("js/settlement/commission-close.js")
    for needle in ("'/preview?'", "can_close", "block_reason", "waiting_counts", "WAIT_COST",
                   "'/paid'", "'DELETE'", "reason: reason", "ctx.urls.exportCsv", "window.confirm(",
                   "window.prompt(", "WITHHOLD_3_3", "VAT_10", "tax_income", "tax_local", "vat", "net",
                   "다음 마감으로 넘어가요", "C.loadClosings", "C.syncClose", "basis !== 'completion'"):
        assert needle in close, needle
    main = _js("js/settlement/commission.js")
    for needle in ("C.closing", "C.bindClose(ctx)", "C.syncClose(ctx)", "C.loadClosings(ctx)",
                   "data-settlement-cm-closings-api", "data-settlement-cm-export-api"):
        assert needle in main, needle


def test_cancel_is_offered_only_on_the_latest_open_closing():
    """[마감 취소]는 가장 최근 마감(목록 첫 줄)이 아직 지급 전일 때만 — 서버도 같은 규칙으로 막는다."""
    close = _js("js/settlement/commission-close.js")
    assert "closingRow(ctx, item, i === 0)" in close
    assert "if (!paid && isLatest)" in close


def test_js_watches_the_tab_attribute_and_mounts_once():
    main = _js("js/settlement/commission.js")
    assert "data-settlement-active-tab" in main
    assert "MutationObserver" in main
    assert "__FOMS_SETTLEMENT_COMMISSION_BOUND" in main
    assert "foms:erp-shell-fragment-swapped" in main


def test_fetch_is_guarded_by_try_catch_and_success_check():
    core = _js("js/settlement/commission-core.js")
    assert core.index("try {") < core.index("await fetch(") < core.index("catch (networkError)")
    assert "body.success !== true" in core


def test_saves_are_queued_per_order():
    """같은 주문의 저장은 하나씩 — 앞 요청이 끝나면 모아 둔 값을 새 version 으로 이어 보낸다."""
    edit = _js("js/settlement/commission-edit.js")
    assert "q.pending" in edit and "q.next" in edit
    assert "err.status === 409" in edit
    assert "focusNext" in edit and "'Enter'" in edit


def test_ui_words_cover_states_and_deal_types():
    core = _js("js/settlement/commission-core.js")
    for word in ("라홈", "하우드", "개인영업", "회계팀 지정", "시공비 기다림", "요율 정해 주세요", "예상",
                 "발주사를", "실측일을", "시공일을", "출고가를"):
        assert word in core, word


# ==========================================================================
# 4 — 위생
# ==========================================================================
@pytest.mark.parametrize("rel", (PARTIAL_TEMPLATE,) + tuple(f"static/{a}" for a in JS_ASSETS))
def test_no_inline_style_or_innerhtml_or_jquery(rel):
    code = _read_code(rel)
    assert not _STYLE_ATTR_RE.search(code), f"{rel}: 인라인 style"
    assert "innerHTML" not in code, f"{rel}: innerHTML"
    assert "jQuery" not in code and "$(" not in code, f"{rel}: jQuery"


@pytest.mark.parametrize("rel", (PARTIAL_TEMPLATE, f"static/{CSS_ASSET}") + tuple(f"static/{a}" for a in JS_ASSETS))
def test_no_mockup_leftover_words(rel):
    text = _read(rel)
    for phrase in _MOCKUP_LEFTOVERS:
        assert phrase not in text, f"{rel}: 목업 잔재 '{phrase}'"


def test_css_rules_stay_under_the_settlement_root():
    css = re.sub(r"/\*.*?\*/", " ", _read(f"static/{CSS_ASSET}"), flags=re.S)
    selectors = [s.strip() for block in re.findall(r"([^{}]+)\{", css) for s in block.split(",")]
    assert selectors
    for selector in selectors:
        assert selector.startswith(".foms-settle"), selector


@pytest.mark.parametrize("rel", tuple(f"static/{a}" for a in JS_ASSETS))
def test_js_files_stay_under_300_lines(rel):
    assert len(_read(rel).splitlines()) < 300, rel
