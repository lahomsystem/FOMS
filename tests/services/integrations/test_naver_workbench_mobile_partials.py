# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 — 재감사 '부분' 판정 마무리(2026-09-29) 계약.

N-06 목록 `맨 위로` · N-16/N-39 `미입력` · N-19 원본 창 12px·제목 18px · N-21/N-26 원본 창 주문 단위 한 줄 ·
N-29 취소·반품 창 상품 줄 순서 · N-43 층 머리 합계 금액·발송기한.

음성 대조군: 각 시나리오 안에 둔다(FOMS 주문이 붙은 집 · 데스크톱 · 폰이 아닐 때 · 기한 배지 없음 등).
HEAD(b30145a3d) 코드로 돌리면 이 파일이 빨갛다.
"""

from __future__ import annotations

import re

from db import db_session
from models import Order
from tests.services.integrations.test_naver_dock_width_live import _needs_node
from tests.services.integrations.test_naver_workbench import _collected
from tests.services.integrations.test_naver_workbench_mobile import TEMPLATE, TRIAGE_PATH, _empty_strips, _rule
from tests.services.integrations.test_naver_workbench_mobile_p1 import PANE, _css, _js, _node
from tests.services.integrations.test_naver_workbench_v3_contract import (  # noqa: F401
    _login,
    workbench_on,
)

DETAIL_PATH = "/admin/naver-ingest/triage/detail"


def _tail() -> str:
    """폰 미디어 쿼리 안 '일부 항목 마무리' 절."""
    phone, _ = _css()
    assert "══ 일부 항목 마무리" in phone, "마무리 절이 폰 미디어 쿼리 안에 없다"
    return phone.split("══ 일부 항목 마무리", 1)[1]


# --------------------------------------------------------------------------- #
# N-21 · N-26 이력 원본 창 주문 단위 · N-19 글자
# --------------------------------------------------------------------------- #

def test_history_original_shows_naver_value_only_where_foms_has_none(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    fresh = _collected(order_no="N-PT-NEW", product="새 집", amount=100000, place_status="")
    frag = client.get(DETAIL_PATH, query_string={"link_id": fresh.id}).get_data(as_text=True)
    household = frag.split('data-cmp-section="household"')[1].split("</table>")[0]
    assert '<span class="wb-cmp__nofoms">FOMS 주문이 아직 없어 네이버 값만 보여요.</span>' in household
    assert household.count('class="wb-cmp__row--nofoms"') == 4, "주문자·수취인·연락처·주소"

    # 대조군: FOMS 주문이 붙은 집은 안내가 없고, 값이 있는 칸은 두 줄 비교 그대로.
    linked = _collected(order_no="N-PT-LNK", product="붙은 집", amount=100000, place_status="")
    order = Order(received_date="2026-09-28", customer_name="박도윤", phone="010-3333-4444",
                  address="서울 강남구 1 101호", product="서랍장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    linked.order_id = order.id
    linked.sync_status = "LINKED"
    db_session.commit()
    frag = client.get(DETAIL_PATH, query_string={"link_id": linked.id}).get_data(as_text=True)
    household = frag.split('data-cmp-section="household"')[1].split("</table>")[0]
    assert "wb-cmp__nofoms" not in household
    assert household.count('class="wb-cmp__row--nofoms"') == 1, "주문자 줄(FOMS 칸이 늘 –)만"

    tail = _tail()
    assert "display: none;" in _rule(tail, "    #wb-detail-body .wb-cmp__row--nofoms td:nth-child(3),\n"
                                           "    #wb-detail-body [data-cmp-section=\"household\"] + .wb-cmp tr.wb-cmp__row--nofoms td:nth-child(2)::before")
    assert "display: block;" in _rule(tail, "    #wb-detail-body .wb-cmp__nofoms")
    # N-19: 원본 창에 남던 11.5·10.5px → 12px, 폰 블록 17px 0개.
    assert "font-size: calc(12px * var(--wb-fs, 1));" in _rule(
        tail, "    #wb-detail-body .wb-cmp__option,\n    #wb-detail-body .wb-cmp__coupon,\n    #wb-detail-body .wb-coupon span")
    phone, everywhere = _css()
    assert "calc(17px" not in phone
    assert ".wb-ph,\n.wb-reread,\n.wb-find__clear,\n.wb-cmp__nofoms { display: none; }" in everywhere, "데스크톱은 안내를 숨긴다"


# --------------------------------------------------------------------------- #
# N-29 취소·반품 창 상품 줄 · N-16/N-39 미입력
# --------------------------------------------------------------------------- #

def test_scope_rows_lead_with_product_and_amount_on_phone():
    pane = PANE.read_text(encoding="utf-8")
    assert pane.count('<span class="fw-semibold wb-scope__no">{{ row.external_id }}</span>') == 2, "취소·반품 두 창"
    assert pane.count('<span class="wb-scope__main"><span class="wb-scope__lead">· </span>') == 2
    tail = _tail()
    assert "display: flex;" in _rule(tail, "    .naver-workbench .wb-scope__row .form-check-label")
    assert "order: 1;" in _rule(tail, "    .naver-workbench .wb-scope__main")
    assert "display: none;" in _rule(tail, "    .naver-workbench .wb-scope__lead")
    no = _rule(tail, "    .naver-workbench .wb-scope__no")
    assert "order: 3;" in no and "font-size: calc(12px * var(--wb-fs, 1));" in no
    _, everywhere = _css()
    assert "wb-scope__lead" not in everywhere, "데스크톱은 한 줄 그대로(대조군)"


def test_expiry_unset_says_not_entered_on_phone(client, workbench_on, monkeypatch):
    page = TEMPLATE.read_text(encoding="utf-8")
    assert '{% else %}<span class="wb-dk">미등록</span><span class="wb-ph">미입력</span>{% endif %}</span>' in page
    assert ('<div class="wb-ingest__v text-warning wb-expiry-unset"><span class="wb-dk">미등록</span>'
            '<span class="wb-ph">미입력</span></div>') in page
    assert ">미등록<" not in page.replace('<span class="wb-dk">미등록</span>', ""), "맨 `미등록` 이 남지 않는다"


# --------------------------------------------------------------------------- #
# N-43 층 머리 · N-06 맨 위로
# --------------------------------------------------------------------------- #

@_needs_node
def test_layer_meta_reads_total_and_due_badge_only():
    result = _node(("layerMeta",), """
var b = JSON.stringify([{text: '2건 묶음', cls: 'x'}, {text: '발송기한 10-21', cls: 'y'}]);
process.stdout.write(JSON.stringify({
  both: layerMeta('1284000', b),
  noDue: layerMeta('1284000', JSON.stringify([{text: '주문 #7'}])),
  unknown: layerMeta('', b),
  broken: layerMeta('12,000', '{oops'),
  none: layerMeta(null, null)}));""")
    assert result["both"] == "1,284,000원 · 발송기한 10-21"
    assert result["noDue"] == "1,284,000원", "기한 배지가 없으면(잠김·발송 끝) 금액만"
    assert result["unknown"] == "발송기한 10-21", "금액을 못 읽었으면 싣지 않는다"
    assert result["broken"] == "" and result["none"] == ""


def test_layer_meta_is_wired_and_pane_carries_the_total(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    link = _collected(order_no="N-PT-META", product="금액 집", amount=1284000, place_status="")
    body = client.get(TRIAGE_PATH, query_string={"tab": "work", "link_id": link.id}).get_data(as_text=True)
    assert re.search(r'<div id="wb-pane"[^>]* data-amount-total="1284000"', body)
    assert '<p class="wb-layer__meta" id="wb-layer-meta"></p>' in body
    js = _js()
    assert "setText('wb-layer-meta', pane ? layerMeta(pane.getAttribute('data-amount-total')," in js
    tail = _tail()
    assert "    .wb-layer__meta:empty { display: none; }" in tail
    assert "    .wb-layer__bar { flex-shrink: 0; }" in tail


@_needs_node
def test_to_top_shows_only_on_phone_after_a_screen_and_a_half():
    result = _node(("toTopVisible",), """
process.stdout.write(JSON.stringify([toTopVisible(true, 1267, 844), toTopVisible(true, 1266, 844),
  toTopVisible(false, 5000, 844), toTopVisible(true, 100, 0)]));""")
    assert result == [True, False, False, False]


def test_to_top_button_is_wired_hidden_by_default_and_desktop_never_shows_it():
    page = TEMPLATE.read_text(encoding="utf-8")
    assert '<button type="button" class="wb-totop" id="wb-totop" aria-label="목록 맨 위로" hidden>' in page
    js = _js()
    assert "'wb-totop': function () { window.scrollTo({ top: 0, behavior: 'smooth' }); }" in js
    assert "window.addEventListener('scroll', onToTopScroll, { passive: true });" in js
    phone, everywhere = _css()
    assert ".wb-totop { display: none; }" in everywhere
    shown = _rule(_tail(), "    .wb-totop:not([hidden])")
    assert "position: fixed;" in shown and "width: 48px;" in shown and "height: 48px;" in shown
    assert "    body.wb-detail-open .wb-totop { display: none; }" in phone
    assert page.count("?v=20260930h") == 2 and "?v=20260930d" not in page
