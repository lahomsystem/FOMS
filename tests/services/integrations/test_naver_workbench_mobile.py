# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 배치(2026-09-28 모바일 2단계) 계약.

폰(≤767.98px)에서 쓸 수 있게 하되 **데스크톱 화면은 그대로**다. 여기서 무는 것:

* 알림 요약 띠 — 실제로 그려지는 띠만 세고(유령·부분 취소·옛 주문 정리·오늘 발송·실패),
  띠가 하나도 없으면 요약 띠도 없다. 띠 자체(버튼·data-*)는 요약 띠 **안**에 그대로 산다.
* 폰 CSS — 주문 단위 대조표 세로 쌓기·칩 한 줄 가로 스크롤·벌크 바 아래 붙기가
  `@media (max-width: 767.98px)` 안에 있고, 폰 전용 부품은 데스크톱에서 숨는다.
* ERP 로 돌아가는 길 — admin 레이아웃이라 v2 하단 탭이 없어서 머리줄에 `‹ ERP` 링크를 둔다.
* 핀 — CSS·JS 를 고쳤으므로 ``?v`` 가 함께 움직였다(SW staticCacheFirst).
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
    assert re.search(r"확인 필요 <b>4</b>건", banner)
    parts = re.sub(r"\s+", " ", banner.split('class="wb-alerts__parts">')[1].split("</span>")[0])
    assert parts == "유령 주문 2 · 부분 취소 1 · 처리 실패 1"
    assert "옛 주문 정리" not in banner and "오늘 발송" not in banner
    # 띠 자체는 요약 띠의 펼침 자리 **안**에 그대로 있다(데스크톱은 CSS 가 늘 펼친다).
    body_at = body.index('id="wb-alerts-body"')
    assert body_at < body.index('class="wb-ghost"') < body.index('id="wb-result"')
    assert 'style="' not in body[body.index('class="wb-alerts"'):body_at]


def test_summary_banner_names_countless_strip_without_inflating_total(client, workbench_on,
                                                                     monkeypatch):
    """발송 완료 띠는 숫자 없이 이름만 — 합계에 0 을 더한다(`확인 필요` 대신 `알림`)."""
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
    assert "확인 필요" not in banner
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

    assert markup.count("?v=20260928a") == 2
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
    assert "#4a55b8" in phone.split("#wb-bulk-submit {")[1].split("}")[0]
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
