# -*- coding: utf-8 -*-
"""NVCLAIM-PARTIAL-01 — 부분 취소·반품 화면(계약 §4): pane·목록 줄·JS·핀.

게이트가 켜지면 취소·반품 모달이 상품주문 목록과 체크박스를 내고, 우리가 이미 부분 취소한
줄은 잠긴다. 게이트가 꺼지면 옛 모달 그대로다(음성 대조군). 부분 취소한 형제가 섞인 집이
목록 줄·pane 에서 계속 열려 있는지, ``id="wb-…"`` 가 문서 안에서 유일한지, JS 블록과 ``?v``
핀이 계약대로인지도 여기서 본다.

서비스 계약은 ``test_naver_partial_claim``, 부분 취소 뒤 발송은
``test_naver_partial_claim_dispatch``, 큐·워커·라우트는 ``test_naver_partial_claim_routes``
가 본다. 픽스처·헬퍼는 ``naver_partial_claim_helpers`` 한 벌을 공유한다.
"""
from __future__ import annotations

import re
from collections import Counter

from tests.services.integrations._markup import has_attribute, is_disabled
from tests.services.integrations.naver_partial_claim_helpers import (  # noqa: F401
    JS_PATH,
    PANE_PATH,
    TRIAGE_PATH,
    WORKBENCH_TEMPLATE,
    _ext,
    _household_2354,
    _link,
    _login,
    _partial_off,
    partial_on,
    workbench_on,
)

# --------------------------------------------------------------------------- #
# 화면 — pane (계약 §4)
# --------------------------------------------------------------------------- #

def _pane_of(client, link_id: int) -> str:
    """pane 조각 HTML."""
    response = client.get(f"{PANE_PATH}?link_id={link_id}")
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def test_cancel_modal_lists_rows_with_checkboxes_when_the_gate_is_on(client, workbench_on,
                                                                     partial_on):
    """게이트 ON — 취소 모달이 집의 상품주문을 체크박스 목록으로 그리고, 이미 취소된 C1 은 잠긴다.

    기준 사례 #2354 그대로다(브리프 §2-1 ①). 형제 ``CANCEL_DONE``(판매자센터 취소)은
    ``household_claimed`` 로 발주확인·발송 축을 잠그지만, 계약 §4 개정(2026-09-11 CEO)으로
    ``can_cancel`` 은 ``household_claimed`` 를 안 본다 — ``cancel_sendable_count`` 와 서버
    ``_claim_guard(scope=todo)`` 가 형제 클레임을 행 단위로 거른다. 그래서 이 집에서도 취소
    모달이 렌더되고 C1 은 "취소 완료" 로 잠긴다(단언 유지).
    """
    _login(client)
    order_no = "N-PC-UI"
    ids = _household_2354(order_no)

    pane = _pane_of(client, ids["M"])

    assert 'id="wb-cancel-scope"' in pane
    assert 'class="form-check-input wb-scope-pick"' in pane
    assert 'name="po"' in pane
    assert f'value="{_ext(order_no, "A1")}"' in pane
    assert is_disabled(pane, f"wb-cancel-po-{ids['C1']}") is True
    assert is_disabled(pane, f"wb-cancel-po-{ids['A1']}") is False
    assert 'id="wb-cancel-selected-count"' in pane
    assert has_attribute(pane, "wb-cancel-scope-auto", "data-foms-no-autodismiss")


def test_cancel_modal_disables_our_partially_canceled_row(client, workbench_on, partial_on):
    """게이트 ON, 잠기지 않는 집 — 우리가 부분 취소한 라인은 체크 불가(``canceled_ours``), 나머지는 체크 가능.

    위 테스트가 집 잠금 결정에 걸려 있어, 계약 §3 그대로도 반드시 green 이어야 하는
    변형을 따로 둔다: 형제 표식이 partial 이면 ``cancel_lock`` 이 거짓이라 모달이 뜬다.
    """
    _login(client)
    order_no = "N-PC-UIP"
    main = _link("PO-PC-UIP-M", order_no=order_no, addon=False)
    a1 = _link("PO-PC-UIP-A1", order_no=order_no, addon=True)
    done = _link("PO-PC-UIP-A2", order_no=order_no, addon=True,
                 canceled=True, cancel_scope="partial")

    pane = _pane_of(client, main)

    assert 'id="wb-cancel-scope"' in pane
    assert is_disabled(pane, f"wb-cancel-po-{done}") is True
    assert is_disabled(pane, f"wb-cancel-po-{a1}") is False
    assert is_disabled(pane, f"wb-cancel-po-{main}") is False
    assert 'id="wb-cancel-selected-list"' in pane
    assert 'id="wb-cancel-scope-rest"' in pane
    assert has_attribute(pane, "wb-cancel-scope-auto", "data-foms-no-autodismiss")


def test_cancel_modal_is_the_old_one_when_the_gate_is_off(client, monkeypatch, workbench_on):
    """★ 음성 대조군 — 게이트 OFF 면 옛 모달 그대로: 목록 없음, "상품주문 1건을" 재진술(단건 집)."""
    _partial_off(monkeypatch)
    _login(client)
    main = _link("PO-PC-OLD-M", order_no="N-PC-OLD", addon=False)

    pane = _pane_of(client, main)

    assert 'id="wb-modal-cancel"' in pane
    assert "wb-cancel-scope" not in pane
    assert "상품주문 1건을" in pane


def test_members_table_shows_our_cancel_line(client, workbench_on):
    """멤버 표 클레임 칸에 취소 축 "우리 취소 {시각}" 줄이 생긴다 — 재수집 전엔 스냅샷에 없어서다."""
    _login(client)
    order_no = "N-PC-MEM"
    main = _link("PO-PC-MEM-M", order_no=order_no, addon=False)
    _link("PO-PC-MEM-A1", order_no=order_no, addon=True, canceled=True, cancel_scope="partial")

    pane = _pane_of(client, main)

    assert "우리 취소 " in pane


def test_partially_canceled_household_keeps_confirm_open(client, workbench_on):
    """결정 5 화면 — partial 표식 형제는 발주확인 버튼을 잠그지 않는다; household 표식은 잠근다(v3 :413)."""
    _login(client)
    open_main = _link("PO-PC-CF-M", order_no="N-PC-CF", addon=False, place="NOT_YET")
    _link("PO-PC-CF-A1", order_no="N-PC-CF", addon=True, place="NOT_YET",
          canceled=True, cancel_scope="partial")
    lock_main = _link("PO-PC-CFL-M", order_no="N-PC-CFL", addon=False, place="NOT_YET")
    _link("PO-PC-CFL-A1", order_no="N-PC-CFL", addon=True, place="NOT_YET",
          canceled=True, cancel_scope="household")

    open_pane = _pane_of(client, open_main)
    locked_pane = _pane_of(client, lock_main)

    assert is_disabled(open_pane, "wb-confirm") is False
    assert 'id="wb-modal-confirm"' in open_pane
    assert is_disabled(locked_pane, "wb-confirm") is True


def _list_row(client, order_no: str) -> str:
    """처리 목록(``tab=work``)에서 그 주문번호 집의 줄(``<a class="wb-row" …</a>``) 하나.

    test_naver_workbench._row_of 와 같은 규칙 — 줄을 먼저 나누고 그 안에서 찾는다. 주문번호는
    줄의 ``data-find`` 에 소문자로만 들어 있어 소문자로 맞춘다.
    """
    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)
    for chunk in body.split('<a class="wb-row')[1:]:
        row = '<a class="wb-row' + chunk.split("</a>")[0]
        if order_no.lower() in row:
            return row
    raise AssertionError(f"목록에 '{order_no}' 집의 줄이 없다")


def _pick_tag(row: str) -> str:
    """목록 줄 안의 벌크 체크박스(``class="wb-pick"``) 여는 태그."""
    at = row.find('class="wb-pick"')
    assert at >= 0, "목록 줄에 벌크 체크박스가 없다"
    return row[row.rfind("<", 0, at):row.find(">", at) + 1]


def _partial_sibling_household(order_no: str, *, cancel_scope: str) -> tuple[int, int]:
    """본품(NOT_YET) + 형제 1건(우리 취소 표식 + 재수집된 ``CANCEL_DONE``) 집 — (본품, 형제) link id.

    ``cancel_scope`` 가 ``partial`` 이면 결정 5 의 열린 집, ``household``·빈 값(옛 표식)이면
    집 전체 취소로 잠기는 집이다. 형제 스냅샷에 클레임을 함께 심는 이유는 다음 수집 뒤 모양
    (부분 취소가 형제 클레임으로 읽히는 자리)을 재현하기 위해서다.
    """
    main = _link(f"{order_no}-M", order_no=order_no, addon=False, place="NOT_YET")
    a1 = _link(f"{order_no}-A1", order_no=order_no, addon=True, canceled=True,
               cancel_scope=cancel_scope, claim="CANCEL_DONE", claim_type="CANCEL")
    return main, a1


def test_list_row_and_pane_stay_open_for_a_partially_canceled_sibling(client, workbench_on):
    """결정 5 목록 줄 — 우리가 일부 취소한 형제의 ``CANCEL_DONE`` 은 집을 잠그지 않는다.

    ``_attach_household_counts``(옛 경로)·``_build_sibling_index`` 가 ``_group_queue``·
    ``_household_has_claim`` 과 같은 규칙으로 partial 행을 건너뛰어야 목록 줄이 ``stop``/
    ``locked`` 로 그려지지 않고 벌크 체크가 열리며, pane 의 발주확인 버튼도 같은 말을 한다.
    음성 대조군: 같은 집에서 표식이 ``household`` 또는 키 없음(옛 표식)이면 stop/locked.
    """
    _login(client)
    open_main, _ = _partial_sibling_household("N-PC-LST", cancel_scope="partial")

    row = _list_row(client, "N-PC-LST")
    assert "wb-row--stop" not in row, row
    assert "wb-row--locked" not in row, row
    assert "disabled" not in _pick_tag(row), _pick_tag(row)
    pane = _pane_of(client, open_main)
    assert is_disabled(pane, "wb-confirm") is False
    assert 'id="wb-modal-confirm"' in pane

    for order_no, scope in (("N-PC-LSTH", "household"), ("N-PC-LSTO", "")):
        lock_main, _ = _partial_sibling_household(order_no, cancel_scope=scope)
        locked_row = _list_row(client, order_no)
        assert "wb-row--stop" in locked_row, (scope, locked_row)
        assert "wb-row--locked" in locked_row, (scope, locked_row)
        assert "disabled" in _pick_tag(locked_row), (scope, _pick_tag(locked_row))
        assert is_disabled(_pane_of(client, lock_main), "wb-confirm") is True, scope


def test_pane_buttons_do_not_depend_on_which_sibling_opened_it(client, workbench_on):
    """M-4 — pane 을 **부분 취소 행 자체**(A1)로 열어도 발주확인·발송 버튼은 본품(M)으로 열 때와 같다.

    A1 의 스냅샷은 ``CANCEL_DONE`` 이라 ``selected.claim.blocking`` 이 참이다. pane 이 그것을
    ``selected.partial_canceled`` 없이 ``household_claimed`` 로 읽으면 A1 로 연 화면만 잠긴다.
    발주확인 전 집(NOT_YET)은 ``wb-confirm`` 이, 발주확인이 끝난 집은 ``wb-dispatch`` 가
    두 화면에서 똑같이 열려 있어야 한다.
    """
    _login(client)
    confirm_main, confirm_a1 = _partial_sibling_household("N-PC-SIB", cancel_scope="partial")
    dispatch_main = _link("PO-PC-SIBD-M", order_no="N-PC-SIBD", addon=False)
    dispatch_a1 = _link("PO-PC-SIBD-A1", order_no="N-PC-SIBD", addon=True, canceled=True,
                        cancel_scope="partial", claim="CANCEL_DONE", claim_type="CANCEL")

    by_main, by_a1 = _pane_of(client, confirm_main), _pane_of(client, confirm_a1)
    assert is_disabled(by_main, "wb-confirm") is False
    assert is_disabled(by_a1, "wb-confirm") is is_disabled(by_main, "wb-confirm")
    assert is_disabled(by_a1, "wb-dispatch") is is_disabled(by_main, "wb-dispatch")

    by_main, by_a1 = _pane_of(client, dispatch_main), _pane_of(client, dispatch_a1)
    assert is_disabled(by_main, "wb-dispatch") is False
    assert is_disabled(by_a1, "wb-dispatch") is is_disabled(by_main, "wb-dispatch")
    assert is_disabled(by_a1, "wb-confirm") is is_disabled(by_main, "wb-confirm")


def test_no_duplicate_wb_ids_with_both_scope_modals(client, workbench_on, partial_on):
    """새 모달 목록이 붙어도 ``id="wb-…"`` 는 문서 안에서 유일하다(v3 절대 규칙 1).

    취소 모달(발송 0건 집)과 반품 모달(발송 집)은 한 pane 에 함께 뜰 수 없으므로 각각 렌더해
    센다 — 겹치면 5번째 행 취소가 1번째 집으로 나간다.
    """
    _login(client)
    cancel_main = _link("PO-PC-DUP-M", order_no="N-PC-DUP", addon=False)
    _link("PO-PC-DUP-A1", order_no="N-PC-DUP", addon=True)
    return_main = _link("PO-PC-DUPR-M", order_no="N-PC-DUPR", addon=False, dispatched=True)
    _link("PO-PC-DUPR-A1", order_no="N-PC-DUPR", addon=True, dispatched=True)

    for link_id in (cancel_main, return_main):
        pane = _pane_of(client, link_id)
        counts = Counter(re.findall(r'id="(wb-[^"]+)"', pane))
        dupes = {k: v for k, v in counts.items() if v > 1}
        assert not dupes, f"중복 id: {dupes}"


# --------------------------------------------------------------------------- #
# 정적 계약 — JS·핀
# --------------------------------------------------------------------------- #

def _js_block(js: str, first: str, last: str) -> str:
    """``first`` 함수 정의부터 ``last`` 함수 정의가 끝나는 곳(다음 함수 선언 직전)까지."""
    start = re.search(rf"(function\s+{first}\s*\(|{first}\s*=\s*(async\s*)?(function|\())", js)
    assert start, f"{first} 정의가 없다"
    tail = re.search(rf"(function\s+{last}\s*\(|{last}\s*=\s*(async\s*)?(function|\())", js)
    assert tail, f"{last} 정의가 없다"
    after = re.search(r"\n\s*(async\s+)?function\s+\w+\s*\(|\n\s*(const|let|var)\s+\w+\s*=\s*(async\s*)?\(",
                      js[tail.end():])
    end = tail.end() + after.start() if after else len(js)
    return js[start.start():end]


def test_js_sends_product_order_ids_and_locks_more_buttons():
    """JS 계약 — 본문에 ``product_order_ids``, 미리보기 함수 3종, 잠금 목록 확장, 새 블록에 innerHTML 없음."""
    js = JS_PATH.read_text(encoding="utf-8")

    for needle in ("product_order_ids", "scopeSelection", "refreshClaimPlan", "renderClaimPlan",
                   "/claim-plan", "'wb-return-reject'", "'wb-return-approve-btn'",
                   "대상 상품주문을 고르세요", "submitCancel", "submitReturn", "watchFulfillment("):
        assert needle in js, f"{needle} 가 JS 에 없다"

    block = _js_block(js, "scopeSelection", "renderClaimPlan")
    assert "innerHTML" not in block, "새 함수 블록이 innerHTML 을 쓴다(XSS) — textContent 만"


def test_workbench_pins_moved_to_20260911a():
    """CSS·JS 를 고쳤으면 ``?v`` 핀이 함께 움직인다(SW staticCacheFirst) — 2026-09-11 부분 취소·반품."""
    markup = WORKBENCH_TEMPLATE.read_text(encoding="utf-8")

    assert markup.count("?v=20260911a") == 2
    assert "?v=20260910a" not in markup
