# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 배치(2026-09-28 모바일 2단계) 계약.

폰(≤767.98px)에서 쓸 수 있게 하되 **데스크톱 화면은 그대로**다. 여기서 무는 것:

* 알림 요약 띠 — 실제로 그려지는 띠만 세고(유령·부분 취소·옛 주문 정리·오늘 발송·실패),
  띠가 하나도 없으면 요약 띠도 없다. 띠 자체(버튼·data-*)는 요약 띠 **안**에 그대로 산다.
* 폰 CSS — 주문 단위 대조표 세로 쌓기·칩 한 줄 가로 스크롤·벌크 바 아래 붙기가
  `@media (max-width: 767.98px)` 안에 있고, 폰 전용 부품은 데스크톱에서 숨는다.
* ERP 로 돌아가는 길 — admin 레이아웃이라 v2 하단 탭이 없어서 머리줄에 `‹ ERP` 링크를 둔다.
* 핀 — CSS·JS 를 고쳤으므로 ``?v`` 가 함께 움직였다(SW staticCacheFirst).

폰 1·2단계(2026-09-29 목업)는 ``test_naver_workbench_mobile_phase12.py`` 가 문다(파일 크기 래칫
500줄 때문에 나눴다).
"""

from __future__ import annotations

import pathlib
import re

from flask import url_for

from foms.web.admin import naver_ingest
from tests.services.integrations.test_naver_workbench_v3_contract import (  # noqa: F401
    _login,
    workbench_on,
)

TRIAGE_PATH = "/admin/naver-ingest/triage"
ROOT = pathlib.Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "templates/admin/naver_workbench.html"
CSS = ROOT / "static/css/admin/naver-workbench.css"
JS = ROOT / "static/js/admin/naver-workbench.js"
PHONE_MEDIA = "@media (max-width: 767.98px)"


# --------------------------------------------------------------------------- #
# 보조
# --------------------------------------------------------------------------- #

def _empty_strips(monkeypatch) -> None:
    """띠 다섯 종을 전부 0 으로 — 테스트마다 필요한 띠만 다시 켠다."""
    monkeypatch.setattr(naver_ingest, "_ghost_view", lambda db: {"count": 0, "rows": []})
    monkeypatch.setattr(naver_ingest, "_partial_claim_view", lambda db: {"count": 0, "rows": []})
    monkeypatch.setattr(naver_ingest, "_origin_cleanup_view",
                        lambda db: {"count": 0, "rows": [], "truncated": False})
    monkeypatch.setattr(naver_ingest, "_bulk_dispatch_view",
                        lambda db: {"show": False, "date": "", "count": 0, "eligible": 0,
                                    "blocked": 0, "rows": []})
    monkeypatch.setattr(naver_ingest, "_failure_rows", lambda db: [])


def _failure_row() -> dict:
    """실패 띠 한 줄(재시도 불가 — 취소 실패 갈래)."""
    return {"customer_name": "실패고객", "external_order_no": "N-MOB-FAIL", "action": "cancel",
            "action_label": "취소", "reason": "네이버 거절", "at": "2026-09-28 10:00",
            "link_id": 1, "retryable": False}


def _media_block(css: str, query: str) -> str:
    """`query` 로 시작하는 미디어 블록들의 본문을 괄호 짝으로 잘라 이어 붙인다."""
    blocks = []
    start = css.find(query)
    while start != -1:
        depth = 0
        open_at = css.index("{", start)
        for index in range(open_at, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(css[open_at + 1:index])
                    break
        start = css.find(query, start + 1)
    return "\n".join(blocks)


def _banner(body: str) -> str:
    """요약 띠 버튼 마크업."""
    start = body.index('id="wb-alerts-toggle"')
    return body[start:body.index("</button>", start)]


# --------------------------------------------------------------------------- #
# 알림 요약 띠
# --------------------------------------------------------------------------- #

def test_summary_banner_counts_only_rendered_strips(client, workbench_on, monkeypatch):
    """유령 2 · 부분 취소 1 · 실패 1 → `확인 필요 4건`, 띠 3종. 없는 띠는 말하지 않는다."""
    _empty_strips(monkeypatch)
    monkeypatch.setattr(naver_ingest, "_ghost_view", lambda db: {"count": 2, "rows": []})
    monkeypatch.setattr(naver_ingest, "_partial_claim_view", lambda db: {"count": 1, "rows": []})
    monkeypatch.setattr(naver_ingest, "_failure_rows", lambda db: [_failure_row()])
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'data-wb-alert-sections="3"' in body
    assert 'data-wb-alert-total="4"' in body
    banner = _banner(body)
    assert 'aria-expanded="false"' in banner, "폰에서는 접힌 채로 시작한다"
    assert 'aria-controls="wb-alerts-body"' in banner
    assert re.search(r"확인할 주문 <b>4</b>건", banner)  # 2026-09-30 P2 N-15·N-16: `확인 필요` 는 이력 상태 이름과 겹쳤다
    parts = re.sub(r"\s+", " ", banner.split('class="wb-alerts__parts">')[1].split("</span>")[0])
    assert parts == "결제가 다 취소된 주문 2 · 부분 취소 1 · 처리 실패 1"
    assert "옛 주문 정리" not in banner and "오늘 발송" not in banner
    # 띠 자체는 요약 띠의 펼침 자리 **안**에 그대로 있다(데스크톱은 CSS 가 늘 펼친다).
    body_at = body.index('id="wb-alerts-body"')
    assert body_at < body.index('class="wb-ghost"') < body.index('id="wb-result"')
    assert 'style="' not in body[body.index('class="wb-alerts"'):body_at]


def test_summary_banner_names_countless_strip_without_inflating_total(client, workbench_on,
                                                                     monkeypatch):
    """발송 완료 띠는 숫자 없이 이름만 — 합계에 0 을 더한다(`확인할 주문` 대신 `알림`)."""
    _empty_strips(monkeypatch)
    monkeypatch.setattr(naver_ingest, "_bulk_dispatch_view",
                        lambda db: {"show": True, "state": "done", "date": "2026-09-28",
                                    "count": 0, "eligible": 0, "blocked": 0, "sent": 3,
                                    "day_rows": [], "rows": []})
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'data-wb-alert-sections="1"' in body
    assert 'data-wb-alert-total="0"' in body
    banner = _banner(body)
    assert "확인할 주문" not in banner
    assert "알림" in banner and "오늘 발송 완료" in banner


def test_summary_banner_is_absent_without_strips(client, workbench_on, monkeypatch):
    """띠가 하나도 없으면 요약 띠도 없다(빈 경고는 사람이 안 읽게 만든다)."""
    _empty_strips(monkeypatch)
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'id="wb-alerts-toggle"' not in body
    assert 'class="wb-alerts"' not in body
    assert 'class="wb-alerts__body"' not in body


# --------------------------------------------------------------------------- #
# ERP 로 돌아가는 길 · 핀
# --------------------------------------------------------------------------- #

def test_head_has_phone_back_link_to_erp_dashboard(client, workbench_on, monkeypatch):
    """admin 레이아웃이라 v2 하단 탭이 없다 — 머리줄의 `‹ ERP` 가 ERP 대시보드로 간다."""
    _empty_strips(monkeypatch)
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)
    with client.application.test_request_context():
        href = url_for("erp_dashboard.erp_dashboard")

    head = body[body.index('class="wb-bar wb-bar--head"'):body.index('class="wb-bar__title"')]
    assert f'class="wb-back" href="{href}"' in head
    assert 'aria-label="ERP 대시보드로 돌아가기"' in head
    # 셸(하단 탭)은 싣지 않았다 — HTMX 조각 교체가 /admin 화면을 통째로 갈아 끼운다.
    assert "erp-mobile-bottom-nav" not in body


def test_asset_pins_moved_together():
    """CSS·JS 를 고쳤으면 핀을 함께 올린다 — 서비스워커 캐시가 옛 파일을 준다."""
    markup = TEMPLATE.read_text(encoding="utf-8")

    assert markup.count("?v=20260930d") == 2
    assert "?v=20260929b" not in markup, "폰 3·4단계(2026-09-29)에서 CSS·JS 를 고쳤다 — 핀도 함께"
    assert "?v=20260929a" not in markup
    assert "?v=20260914b" not in markup


# --------------------------------------------------------------------------- #
# 폰 CSS · JS
# --------------------------------------------------------------------------- #

def test_phone_css_rules_live_in_the_phone_media_query():
    """폰 규칙은 폰 미디어 쿼리 안에 있고, 폰 전용 부품은 데스크톱에서 숨는다."""
    css = CSS.read_text(encoding="utf-8")
    phone = _media_block(css, PHONE_MEDIA)
    desktop = css.replace(phone, "")

    # 주문 단위 대조표(3열)만 세로로 쌓는다 — 네이버/FOMS 이름표를 CSS 가 붙인다.
    assert '[data-cmp-section="household"] + .wb-cmp thead { display: none; }' in phone
    assert '[data-cmp-section="household"] + .wb-cmp td { display: block; width: auto; }' in phone
    assert 'content: "네이버 원본"' in phone and 'content: "FOMS 현재 값"' in phone
    # 필터 칩은 한 줄 가로 스크롤, 칸마다 44px.
    chips = phone.split(".wb-chips {")[1].split("}")[0]
    assert "flex-wrap: nowrap" in chips and "overflow-x: auto" in chips
    assert "min-height: 44px" in phone.split(".wb-chips .wb-chip {")[1].split("}")[0]
    # 띠 안 표는 자기 칸 안에서만 민다 · 목록 칸은 0 하한(페이지 가로 스크롤 방지).
    assert ".wb-scroll { overflow-x: auto;" in phone
    assert "grid-template-columns: minmax(0, 1fr)" in phone
    # 벌크 바는 아래에 붙고, 주 조작은 남색 흰 글자.
    bulk = phone.split("#wb-bulk.on {")[1].split("}")[0]
    assert "position: fixed" in bulk and "bottom: 0" in bulk
    assert "safe-area-inset-bottom" in bulk
    # 색은 화면 전체 `.naver-workbench .btn-primary` 한 벌이 든다(2026-09-28) — 폰 규칙은 폭만.
    assert "flex: 1 1 auto" in phone.split("#wb-bulk-submit {")[1].split("}")[0]
    assert "#4a55b8" not in phone.split("#wb-bulk-submit {")[1].split("}")[0], "색이 두 벌이 된다"
    # 알림 요약 띠 · 글자 크기 조절 · ERP 링크.
    assert '.wb-alerts__toggle[aria-expanded="true"] + .wb-alerts__body { display: block; }' in phone
    assert ".wb-alerts__body { display: none;" in phone
    assert ".wb-fs { display: none; }" in phone
    # 데스크톱: 폰 전용 부품 둘은 숨고, 알림 띠 본문은 숨기지 않는다(예전 화면 그대로).
    assert ".wb-back { display: none; }" in desktop
    assert ".wb-alerts__toggle { display: none; }" in desktop
    assert ".wb-alerts__body" not in desktop


def test_phone_js_toggles_banner_and_reveals_pane():
    """JS 는 CSS 로 안 되는 둘만 한다 — 요약 띠 펼치기, 폰에서 상세로 내려가기."""
    js = JS.read_text(encoding="utf-8")

    assert "'wb-alerts-toggle': toggleAlerts" in js
    assert "var PHONE_QUERY = '(max-width: 767.98px)';" in js
    assert "revealPaneOnPhone();" in js
    # 전체 다시 그리기 너머로 펼침 상태를 지킨다.
    assert "var alertsOpen = readAlertsOpen();" in js
    assert "applyAlertsOpen(alertsOpen);" in js


def test_new_markup_adds_no_inline_style():
    """폰 배치로 더한 마크업(ERP 링크·요약 띠)에 인라인 스타일이 없다."""
    markup = TEMPLATE.read_text(encoding="utf-8")
    back = markup[markup.index('class="wb-back"'):markup.index('class="wb-bar__title"')]
    banner = markup[markup.index('class="wb-alerts"'):markup.index('id="wb-alerts-body"')]

    assert 'style="' not in back
    assert 'style="' not in banner


def test_phone_pane_has_back_to_list_outside_swapped_fragment(client, workbench_on, monkeypatch):
    """폰은 목록 아래에 상세가 붙는다 — 292줄이면 약 32,000px 아래라 '목록으로' 없이는
    돌아갈 길이 스크롤뿐이었다(2026-09-28 스테이징 390px 확인). 버튼은 응답으로 통째로
    갈아 끼우는 #wb-pane **바깥**(바로 앞)에 있어야 교체 뒤에도 남는다."""
    _empty_strips(monkeypatch)
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'id="wb-pane-back"' in body
    assert body.index('id="wb-pane-back"') < body.index('<div id="wb-pane"')
    js = JS.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "'wb-pane-back': backToList" in js
    # 2026-09-29 폰 3단계: 버튼은 층을 닫는다(leaveLayer) — 방금 연 행으로 돌아가는 규칙은 그대로.
    assert "a.wb-row[aria-current=\"true\"]" in js.split("function leaveLayer(")[1][:800]
    css = CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert ".wb-pane-back { display: none; }" in css
    assert ".wb-pane-back {" in _media_block(css, "@media (max-width: 767.98px)")


def test_row_product_line_is_block_so_ellipsis_applies():
    """제품명 줄은 span 이다 — inline 이면 text-overflow 가 먹지 않고 행 끝에서 글자가
    그냥 잘린다. 말줄임이 걸리려면 block 이어야 한다."""
    css = CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    rule = css.split(".wb-row__line2 {", 1)[1].split("}", 1)[0]
    assert "display: block;" in rule and "text-overflow: ellipsis;" in rule


def test_phone_back_button_lives_in_the_layer_bar():
    """2026-09-28 에는 목록 아래 상세 위에 붙은 sticky '목록으로' 였다(전역 nav 밑에 깔려 --wb-nav-h
    만큼 내렸다). 2026-09-29 폰 3단계부터 상세는 화면을 덮는 층이고 버튼은 층 위 막대(sticky)의
    첫 칸이다 — 층이 전역 nav 를 덮으므로 nav 높이만큼 내릴 일이 없다. 누르는 곳은 44px."""
    css = CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    phone = _media_block(css, "@media (max-width: 767.98px)")
    rule = phone.split(".wb-pane-back {", 1)[1].split("}", 1)[0]
    assert "--wb-nav-h" not in rule and "position: sticky" not in rule
    assert "min-height: 44px;" in rule and "min-width: 44px;" in rule
    assert "position: sticky;" in phone.split("    .wb-layer__bar {", 1)[1].split("}", 1)[0]


# --------------------------------------------------------------------------- #
# 주 조작 버튼 대비(2026-09-28) — 전역 #007AFF + 흰 글자 = 4.0:1 (AA 미달)
# --------------------------------------------------------------------------- #

def _contrast(fg: str, bg: str) -> float:
    """WCAG 2.x 대비율."""
    def lum(hex_color: str) -> float:
        hex_color = hex_color.lstrip("#")
        channels = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    high, low = sorted((lum(fg), lum(bg)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _outside_media(css: str) -> str:
    """미디어 쿼리 블록을 전부 걷어낸 나머지 — 모든 폭에 걸리는 규칙만 남는다."""
    out, index = [], 0
    while True:
        start = css.find("@media", index)
        if start == -1:
            out.append(css[index:])
            return "".join(out)
        out.append(css[index:start])
        depth = 0
        for cursor in range(css.index("{", start), len(css)):
            if css[cursor] == "{":
                depth += 1
            elif css[cursor] == "}":
                depth -= 1
                if depth == 0:
                    index = cursor + 1
                    break


def _rule(css: str, selector: str) -> str:
    """`selector {` 로 시작하는 첫 규칙 본문."""
    return css.split(selector + " {")[1].split("}")[0]


def _hex(body: str, prop: str) -> str:
    """규칙 본문에서 `prop: #rrggbb` 값을 꺼낸다."""
    found = re.search(prop + r":\s*(#[0-9a-fA-F]{6})", body)
    assert found, f"{prop} 가 6자리 색으로 적혀 있지 않다: {body}"
    return found.group(1)


def test_primary_buttons_meet_aa_contrast_on_every_viewport():
    """이 화면의 `.btn-primary` 는 폰·데스크톱 모두 흰 글자 대비 4.5:1 이상이다.

    전역 `.btn-primary`(style-pro-max.css, !important)는 #007AFF 라 4.0:1 이다. 상세
    액션 줄('+ 주문 만들기'·'발송처리')과 모달 확인 버튼이 그 색이었고, 폰 벌크 버튼만
    따로 칠해져 있었다. 규칙은 **미디어 쿼리 밖**(모든 폭)에 있고 이 화면 범위에만 건다.
    """
    css = CSS.read_text(encoding="utf-8")
    everywhere = _outside_media(css)

    base = _rule(everywhere, ".naver-workbench .btn-primary")
    assert "!important" in base, "전역 규칙이 !important 라 같은 무기가 아니면 진다"
    assert _contrast(_hex(base, "color"), _hex(base, "background")) >= 4.5

    hover = _rule(everywhere, ".naver-workbench .btn-primary:hover,\n"
                              ".naver-workbench .btn-primary:focus-visible")
    assert _contrast(_hex(hover, "color"), _hex(hover, "background")) >= 4.5
    active = _rule(everywhere, ".naver-workbench .btn-primary:active")
    assert _contrast(_hex(active, "color"), _hex(active, "background")) >= 4.5

    # 끈 상태 — 부트스트랩 opacity .65 로 흐리면 흰 글자가 3:1 아래로 떨어진다.
    disabled = _rule(everywhere, ".naver-workbench .btn-primary:disabled,\n"
                                 ".naver-workbench .btn-primary.disabled")
    assert "opacity: 1" in disabled
    assert _contrast(_hex(disabled, "color"), _hex(disabled, "background")) >= 4.5

    # 포커스 테두리는 흰 바탕과 3:1 이상(비텍스트 대비).
    # 첫 짝은 hover 와 묶인 색 규칙이다 — 테두리는 단독 규칙(마지막 짝)에 있다.
    focus = everywhere.split(".naver-workbench .btn-primary:focus-visible {")[-1].split("}")[0]
    ring = re.search(r"outline:\s*2px solid (#[0-9a-fA-F]{6})", focus)
    assert ring and _contrast(ring.group(1), "#ffffff") >= 3.0, focus


def test_primary_button_rule_never_touches_global_selector():
    """전역 `.btn-primary` 를 이 파일이 다시 쓰지 않는다 — 범위는 `.naver-workbench` 뿐."""
    css = CSS.read_text(encoding="utf-8")
    for line in css.splitlines():
        stripped = line.strip()
        if stripped.startswith(".btn-primary"):
            raise AssertionError(f"범위 없는 전역 규칙: {stripped}")


def test_pane_primary_actions_render_inside_the_scoped_root(client, workbench_on):
    """주 조작 버튼(상세 액션 줄·벌크)이 `.naver-workbench` 안에서 그려진다 — 범위 밖이면 색이 안 닿는다."""
    _login(client)
    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    root = body.index('class="container-fluid naver-workbench"')
    for marker in ('id="wb-bulk-submit"', 'id="wb-bulk-confirm"'):
        assert body.index(marker) > root, marker
