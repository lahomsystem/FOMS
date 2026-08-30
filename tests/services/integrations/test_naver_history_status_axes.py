"""네이버 이력 탭 **상태 칸** 축 계약 테스트 (레인 D).

계약 정본: `docs/plans/2026-08-30-naver-history-status-contract.md` §9.
어휘 정본: `docs/design/mockups/naver-triage-status-column--table.html`.

**왜 파일을 따로 두는가**: `test_naver_workbench.py` 는 이력 탭의 *옛* 어휘("수집됨(생성 전)"·
"발주확인 전")를 이미 물고 있는 공유 자산이고, 이번 개편은 그 자리에 **축별 줄**(FOMS ·
네이버 파이프 · 취소·반품)을 새로 세운다. 같은 파일에 섞으면 픽스처가 공유 자산이 되어
네 레인이 서로를 덮는다 — 계약 §6 이 그래서 이 파일을 새로 두라고 못 박았다.

여기서 잠그는 것은 **화면이 사실을 말하는가** 하나다:

1. 돈 관계(추가결제·재결제)와 **상대 주문번호**가 보인다 — 사용자 요구 1.
2. 발주확인·발송처리의 **완료**가 글자로 보인다(무표시 규칙 부활 방지) — 사용자 요구 3.
3. 부분 처리(1/2 · 2/3)가 전체 완료처럼 보이지 않는다.
4. 우리 기록과 네이버 기록의 **어긋남**이 화면에 남는다.
5. 이력 행은 끝까지 **읽기 전용**이다(절대 규칙 3).
6. 칩과 배지가 **한 낱말**을 쓴다 — 한 화면에서 같은 축을 두 이름으로 부르지 않는다.
7. 숫자는 전부 **집(묶음) 단위**다 — 부분이 전체보다 커 보이는 2026-08-19 사고 재발 방지.

`_login`·`_uid`·`workbench_on` 만 기존 파일에서 빌려 쓰고(계약 §6), 발주확인·발송·관계·
클레임을 세밀히 조작하는 픽스처는 이 파일이 스스로 만든다.
"""

from __future__ import annotations

import datetime
import html
import re
from typing import Any, Optional

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order
from tests.services.integrations.test_naver_workbench import (  # noqa: F401
    _login,
    _uid,
    workbench_on,
)

TRIAGE_PATH = "/admin/naver-ingest/triage"

#: 상태 칸 `td` 의 계약 클래스 (계약 §5).
STATUS_TD_CLASS = "wb-hist__status"

#: 이력 칩 질의값 → `HISTORY_FOMS_LABELS` 의 상태 키 (계약 §2.4 · §4.1).
#: 칩은 `sync_status` 로 거르고 배지는 `foms_state` 로 칠하므로 이름이 한 벌 어긋나 있다 —
#: "같은 낱말" 계약을 검증하려면 이 대응을 명시해야 한다.
CHIP_QUERY_TO_STATE = {
    "COLLECTED": "collected",
    "LINKED": "linked",
    "PENDING_REVIEW": "review",
    "FAILED": "failed",
}


# --------------------------------------------------------------------------- #
# 픽스처 — 링크 한 건을 원하는 축 상태로 만든다 (네이버 호출 0 · 저장값만)
# --------------------------------------------------------------------------- #

def _order(*, product: str = "붙박이장") -> Order:
    """관계 배지가 가리킬 ERP 주문 1건."""
    order = Order(received_date="2026-08-01", customer_name="이수취",
                  phone="010-3333-4444", address="서울 강남구 1 101호",
                  product=product, status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, product: str, amount: int = 100000,
          place_status: str = "OK", claim_status: str = "",
          send_date: str = "", dispatched_at: str = "",
          relation: str = "NEW", order_id: Optional[int] = None,
          sync_status: str = "", fail_reason: str = "",
          fail_action: str = "confirm", fail_at: str = "2026-08-27T11:20:00",
          shipping_due: str = "",
          return_block: Optional[dict[str, Any]] = None,
          cancel_block: Optional[dict[str, Any]] = None,
          reviewed: bool = False) -> ExternalOrderLink:
    """수집 링크 1건을 원하는 축 상태로 만든다.

    같은 ``order_no`` 로 만든 링크들은 수취인 전화·주소가 같으므로 **한 집**이 된다
    (``group_key_text`` 규칙). 부분 발송·부분 발주확인을 재현하려면 그렇게 여러 건을 만든다.

    Args:
        order_no: 네이버 주문번호(집 키의 첫 조각).
        product: 제품명 — 이력 행을 찾는 바늘로 쓴다(집마다 다르게 준다).
        amount: 결제금액. 집 대표(lead)는 **금액 최대** 링크다.
        place_status: ``placeOrderStatus``. ``"OK"`` 면 발주확인 완료, 빈 값이면 아직.
        claim_status: ``claimStatus`` 원문(예 ``"CANCEL_DONE"``). 빈 값이면 클레임 없음.
        send_date: 네이버가 돌려준 ``delivery.sendDate``. 빈 값이면 ``delivery`` 블록을
            아예 안 만든다 — 빈 문자열로 넣으면 '발송처리 남음' 술어의 모양이 실제와 달라진다.
        dispatched_at: 우리 쪽 발송 표식(``triage_state.fulfillment.dispatched_at``).
        relation: 관계 컬럼 값(``"NEW"``/``"ADDON"``/``"REPAY"``).
        order_id: 붙은 ERP 주문 id(없으면 미생성 링크).
        sync_status: 수집 상태. 안 주면 ``order_id`` 유무로 정한다.
        fail_reason: 워커가 남긴 마지막 실패 사유(``fulfillment.last_error``).
        fail_action: 그 실패가 난 작업(``confirm``/``dispatch``/``cancel``/``return``).
        fail_at: 그 실패 시각 원문.
        shipping_due: ``shippingDueDate`` 원문(발송기한).
        return_block: 네이버 반품·교환 상세 블록(``returnCompletedDate``·
            ``collectCompletedDate``·``refundExpectedDate``·``refundStandbyStatus``·
            ``returnReason``). 최상위 ``return`` 자리에 그대로 넣는다 —
            ``mapping.RETURN_BLOCK_KEYS`` 가 ``cancel`` 블록을 **일부러 빼므로**
            취소 블록에 넣으면 반품 축이 통째로 빈 값이 되어 픽스처가 조용히
            아무것도 안 만든다(취소 블록의 환불 필드가 반품 진행으로 새는 것을
            막는 규칙이다).
        reviewed: 사람이 이미 확인한 건인가(``reviewed_at`` 을 채운다). 확인된 건은
            처리 큐에서 빠지므로 **오른쪽 상세 pane 이 안 열린다** — pane 은 열릴 때
            자기 링크의 반품 축을 한 번 판다(:func:`_triage_pane`). 이력 표의 파싱
            횟수를 세는 테스트가 그 한 번을 이력 표의 몫으로 오해하지 않게 하는
            장치다. 이력 표 자체는 확인 여부와 무관하게 전 링크를 낸다.

    Returns:
        저장까지 끝난 :class:`ExternalOrderLink`.
    """
    external_id = f"PO-HSA-{_uid()}"
    snapshot: dict[str, Any] = {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": external_id, "productName": product,
            "productOption": "", "totalPaymentAmount": amount,
            "claimStatus": claim_status or None,
            "placeOrderStatus": place_status or None,
            "shippingDueDate": shipping_due or None,
            "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
        },
    }
    if send_date:
        # 네이버 응답 그대로의 자리(최상위 `delivery`) — 수집 파이프라인이 저장하는 모양이다.
        snapshot["delivery"] = {"sendDate": send_date,
                                "deliveryMethod": "DIRECT_DELIVERY",
                                "deliveryStatus": "NOT_TRACKING"}
    if return_block:
        snapshot["return"] = dict(return_block)
    if cancel_block:
        # 취소 축 전용 자리. `return` 에 넣으면 `mapping.RETURN_BLOCK_KEYS` 가 읽어 버려
        # 취소 건이 반품 진행으로 보이는 그 결함을 테스트가 스스로 만든다.
        snapshot["cancel"] = dict(cancel_block)
    fulfillment: dict[str, Any] = {}
    if dispatched_at:
        fulfillment["dispatched_at"] = dispatched_at
    if fail_reason:
        fulfillment.update({"last_error": fail_reason, "last_error_at": fail_at,
                            "last_error_action": fail_action})
    link = ExternalOrderLink(
        channel=CHANNEL, external_id=external_id,
        sync_status=sync_status or ("LINKED" if order_id else "COLLECTED"),
        external_order_no=order_no, raw_snapshot=snapshot,
        group_key=group_key_text(snapshot),
        place_order_status=place_status or None,
        relation=relation or "NEW", order_id=order_id,
        triage_state={"fulfillment": fulfillment} if fulfillment else None,
        reviewed_at=datetime.datetime(2026, 8, 27, 2, 0, 0) if reviewed else None,
    )
    db_session.add(link)
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 마크업 조각 뽑기
#
# **행을 통째로 자르고 그 다음에 고른다.** 낱말이 나온 자리에서 자르면 같은 낱말이 한 행에
# 두 번 나올 때(`data-find` 속성 + 본문) 그 사이만 잘려 뒤쪽 칸이 통째로 빠진 조각을
# 단언하게 된다 — "버튼이 없다" 류 단언이 없는 자리를 보며 조용히 green 이 된다.
# --------------------------------------------------------------------------- #

def _history_section(body: str) -> str:
    """이력 탭 영역만 — 처리 탭의 칩·행과 섞이지 않게 자른다."""
    assert "전체 이력" in body, "이력 탭이 화면에 없다(ADMIN 으로 ?tab=all 을 열었는가)"
    return body.split("전체 이력", 1)[1]


def _hist_rows(body: str) -> list[str]:
    """이력 표의 데이터 행 전부(``<tr>…</tr>``)."""
    tbody = body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]
    return ["<tr" + chunk.split("</tr>")[0] for chunk in tbody.split("<tr")[1:]]


def _row(body: str, order_no: str) -> str:
    """그 **집**(네이버 주문번호)의 이력 행을 통째로.

    제품명으로 찾지 않는다: 주문이 붙은 링크는 행의 제품 칸이 **ERP 주문의 제품명**으로
    덮이므로(`_link_rows` 는 `order.product` 를 먼저 쓴다) 스냅샷 제품명으로 찾으면
    "행이 없다"가 된다. 주문번호는 모든 행의 `data-find` 에 소문자로 들어 있어
    붙은 집·안 붙은 집을 같은 방법으로 집는다.
    """
    needle = order_no.lower()
    for row in _hist_rows(body):
        if needle in row.lower():
            return row
    raise AssertionError(f"이력 표에 집 '{order_no}' 의 행이 없다")


def _status_cell(row: str) -> str:
    """행에서 상태 칸(``td.wb-hist__status``)만 — 계약 §5 의 클래스로 찾는다.

    클래스로 찾는 이유: 열 순서로 세면 열이 하나 늘고 주는 순간 조용히 다른 칸을 본다.
    """
    for chunk in row.split("<td")[1:]:
        cell = "<td" + chunk.split("</td>", 1)[0]
        if STATUS_TD_CLASS in cell:
            return cell
    raise AssertionError(f"행에 상태 칸(class={STATUS_TD_CLASS})이 없다 — 계약 §5")


def _chips(body: str) -> str:
    """이력 탭 필터 칩 묶음(표 앞의 ``wb-filters`` 블록)."""
    section = _history_section(body)
    assert 'class="wb-filters"' in section, "이력 탭에 필터 칩 묶음이 없다"
    return section.split('class="wb-filters"', 1)[1].split('class="table-responsive"', 1)[0]


def _pager(body: str) -> str:
    """이력 탭 페이저(``wb-pager``)."""
    section = _history_section(body)
    assert 'class="wb-pager"' in section, "이력 탭에 페이저가 없다(쪽이 하나뿐인가)"
    return section.split('class="wb-pager"', 1)[1].split("</div>", 1)[0]


def _anchors(markup: str) -> list[tuple[str, str]]:
    """마크업 안 링크를 ``(href, 글자만 남긴 본문)`` 목록으로."""
    out: list[tuple[str, str]] = []
    for chunk in markup.split("<a ")[1:]:
        tag_body = chunk.split("</a>", 1)[0]
        match = re.search(r'href="([^"]*)"', tag_body)
        inner = tag_body.split(">", 1)[1] if ">" in tag_body else ""
        out.append((match.group(1) if match else "", _tight(inner)))
    return out


def _tight(markup: str) -> str:
    """마크업에서 **글자만** 남긴다(태그·공백 제거).

    배지가 한 ``<span>`` 이든 여러 조각이든 같은 낱말로 읽히게 하려는 것이다 —
    줄바꿈·들여쓰기·태그 경계에 단언이 묶이면 계약이 아니라 마크업 취향을 잠그게 된다.
    """
    text = re.sub(r"<[^>]*>", "", markup)
    return re.sub(r"\s+", "", html.unescape(text))


def _hash_numbers(markup: str) -> list[str]:
    """마크업 안 ``#숫자`` 를 등장 순서대로 — 관계 배지가 가리키는 주문번호."""
    return re.findall(r"#(\d+)", markup)


def _axis_row(cell: str, key: str) -> str:
    """상태 칸에서 축 한 줄(``FOMS``·``네이버``·``취소·반품``)의 **값 블록**만.

    칸 전체로 단언하면 옆 축의 낱말이 섞여 들어온다 — 취소 줄이 안 났는데 네이버 줄의
    시각을 보고 green 이 되는 식이다. 축 이름표(``.wb-st__k``)로 잘라 그 다음 값
    블록(``.wb-st__v``)만 돌려준다.

    Args:
        cell: :func:`_status_cell` 이 뽑은 상태 칸.
        key: 축 이름표 글자(``FOMS``·``네이버``·``취소·반품``).

    Returns:
        그 축의 ``.wb-st__v`` 안쪽 마크업.
    """
    marker = f'class="wb-st__k">{key}</div>'
    assert marker in cell, (f"상태 칸에 '{key}' 축 줄이 없다", cell)
    tail = cell.split(marker, 1)[1]
    assert 'class="wb-st__v"' in tail, (f"'{key}' 축에 값 블록이 없다", tail)
    return tail.split('class="wb-st__v"', 1)[1].split("</div>", 1)[0]


def _badges(markup: str) -> list[str]:
    """마크업 안 배지(``.wb-st__b``) 글자를 등장 순서대로."""
    return [_tight(chunk.split(">", 1)[1].split("</span>", 1)[0])
            for chunk in markup.split('class="wb-st__b')[1:]]


def _whens(markup: str) -> list[str]:
    """마크업 안 작은 글자(``.wb-st__when``)를 등장 순서대로.

    **목록으로** 돌려주는 이유: "값이 없으면 그 조각을 아예 안 낸다" 는 빈 문자열이
    아니라 **요소 부재**로만 증명된다(빈 칸이나 ``–`` 로 채우면 "값이 없다"와 "우리가
    모른다"가 화면에서 같은 모양이 된다 — 계약 §3).
    """
    return [_tight(chunk.split("</span>", 1)[0])
            for chunk in markup.split('class="wb-st__when">')[1:]]


def _warns(cell: str) -> list[str]:
    """상태 칸의 경고 줄(``.wb-st__warn``) 글자를 등장 순서대로."""
    return [_tight(chunk.split("</div>", 1)[0])
            for chunk in cell.split('class="wb-st__warn">')[1:]]


def _open(client, **params: Any) -> str:
    """이력 탭을 연다."""
    params.setdefault("tab", "all")
    return client.get(TRIAGE_PATH, query_string=params).get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 1. 관계 축 — 추가결제·재결제와 상대 주문번호 (계약 §2.2 · §3.1)
# --------------------------------------------------------------------------- #

def test_addon_household_shows_the_relation_badge_and_the_other_order_number(client, workbench_on):
    """추가결제 집은 배지와 **상대 주문번호**를 함께 낸다 — 사용자 요구 1.

    지금 이력 탭은 `ExternalOrderLink.relation` 을 행에 아예 싣지 않아, 돈이 어디로
    붙은 결제인지 이 화면에서 알 길이 없다. 배지만 있고 번호가 없으면 사람이 그 주문을
    찾으러 다른 화면을 열어야 하므로 **번호까지**가 한 계약이다.
    """
    _login(client)
    order = _order(product="붙박이장 본품")
    _link(order_no="N-HSA-ADDON", product="붙박이장 옵션 차액", amount=180000,
          relation="ADDON", order_id=int(order.id))

    cell = _status_cell(_row(_open(client), "N-HSA-ADDON"))

    assert "추가결제" in _tight(cell), cell
    assert _hash_numbers(cell) == [str(order.id)], cell
    assert "<a " in cell, "주문번호는 눌러서 그 주문으로 들어가는 **평범한 링크**여야 한다"


def test_repay_household_says_repay_not_addon(client, workbench_on):
    """재결제는 추가결제와 **다른 낱말**이다 — 돈의 성격이 다르다.

    한 배지로 뭉뜽그리면 "이미 받은 돈의 추가분"과 "취소된 주문을 다시 결제한 것"이
    같은 것으로 읽힌다.
    """
    _login(client)
    order = _order(product="중문 3연동")
    _link(order_no="N-HSA-REPAY", product="중문 3연동 (재주문)", amount=1690000,
          relation="REPAY", order_id=int(order.id))

    cell = _status_cell(_row(_open(client), "N-HSA-REPAY"))

    assert "재결제" in _tight(cell), cell
    assert "추가결제" not in _tight(cell), cell
    assert _hash_numbers(cell) == [str(order.id)], cell


def test_relation_number_comes_from_the_member_that_decided_the_relation(client, workbench_on):
    """관계를 정한 **그 멤버**의 주문번호를 적는다 — 대표(lead)의 것이 아니다.

    집의 관계는 "멤버 중 ADDON 이 하나라도 있으면 ADDON" 으로 정하는데(`_group_queue`
    와 같은 우선순위), 대표는 **금액 최대** 링크다. 둘은 서로 다른 링크일 수 있고
    실제로 섞인 집은 존재한다(백필 전 데이터는 형제 일부만 관계 값이 있다).
    대표에서 번호를 뽑으면 화면이 "추가결제 → #(엉뚱한 주문)" 을 찍고, 사람이 그것을
    눌러 남의 주문으로 들어간다.
    """
    _login(client)
    new_order = _order(product="시스템장 본품")
    addon_order = _order(product="시스템장 추가구성")
    # 대표(금액 최대)는 NEW, 관계를 정한 쪽은 금액이 작은 ADDON 형제다.
    _link(order_no="N-HSA-MIX", product="시스템장 8자", amount=3180000,
          relation="NEW", order_id=int(new_order.id))
    _link(order_no="N-HSA-MIX", product="시스템장 추가 선반", amount=120000,
          relation="ADDON", order_id=int(addon_order.id))

    cell = _status_cell(_row(_open(client), "N-HSA-MIX"))

    assert "추가결제" in _tight(cell), cell
    assert _hash_numbers(cell) == [str(addon_order.id)], (
        "관계를 정한 ADDON 형제가 아니라 대표(NEW)의 주문번호를 찍었다", cell)


def test_relation_badge_without_a_linked_order_shows_the_word_only(client, workbench_on):
    """가리킬 주문이 없으면 **화살표와 번호를 아예 안 낸다** — 배지 낱말만.

    `None` 을 그대로 찍으면 화면에 "추가결제 → #None" 이 뜬다. 없는 값을 자리표시자로
    채우면 "값이 없다"와 "우리가 모른다"가 같은 모양이 된다(계약 §3 의 규율).
    """
    _login(client)
    _link(order_no="N-HSA-ADDON-NOORDER", product="붙박이장 미붙임 추가분",
          amount=90000, relation="ADDON", order_id=None, sync_status="COLLECTED")

    cell = _status_cell(_row(_open(client), "N-HSA-ADDON-NOORDER"))

    assert "추가결제" in _tight(cell), cell
    assert "→" not in cell, "가리킬 주문이 없는데 화살표를 냈다"
    assert _hash_numbers(cell) == [], cell
    assert "None" not in cell, cell


# --------------------------------------------------------------------------- #
# 2. 네이버 축 — 완료를 글자로 (계약 §2.3-B·C · §3.2)
# --------------------------------------------------------------------------- #

def test_place_and_dispatch_done_are_spelled_out(client, workbench_on):
    """발주확인·발송처리의 **완료가 글자로** 나온다 — 무표시 규칙 부활 방지.

    지금 화면은 "발주확인 전" 배지만 달고 완료는 아무 표시가 없다. 그 규칙은 화면을
    외운 사람만 읽을 수 있고, 발송 축은 표시 자체가 통째로 없다(사용자 요구 2·3).
    빈 칸은 "끝났다"와 "우리가 모른다"를 같은 모양으로 만든다.
    """
    _login(client)
    order = _order()
    _link(order_no="N-HSA-DONE", product="중문 슬림 3연동", amount=1760000,
          place_status="OK", dispatched_at="2026-08-27T07:02:00",
          send_date="2026-08-28T12:03:00.000+09:00", order_id=int(order.id))

    cell = _tight(_status_cell(_row(_open(client), "N-HSA-DONE")))

    assert _tight("발주확인 완료") in cell, cell
    assert _tight("발송처리 완료") in cell, cell


def test_partial_dispatch_and_partial_place_show_the_fraction(client, workbench_on):
    """부분 처리는 **분수로** 나온다 — 전체 완료처럼 보이면 안 된다.

    발주확인·발송처리는 상품주문(링크)마다 찍힌다. 워커가 건별로 성공/실패해서 한 집이
    부분으로 남을 수 있는데, 집 줄이 "완료" 라고만 적으면 남은 형제가 화면에서 사라진다.
    """
    _login(client)
    order = _order()
    # 집 A — 발주확인 2/2, 발송 1/2 (나간 쪽은 네이버 기록도 있어 어긋남이 아니다).
    _link(order_no="N-HSA-PART-D", product="붙박이장 4자", amount=2200000,
          place_status="OK", dispatched_at="2026-08-27T07:02:00",
          send_date="2026-08-27T16:10:00.000+09:00", order_id=int(order.id))
    _link(order_no="N-HSA-PART-D", product="붙박이장 상부장", amount=800000,
          place_status="OK", order_id=int(order.id))
    # 집 B — 발주확인 2/3.
    _link(order_no="N-HSA-PART-P", product="시스템장 6자", amount=3000000, place_status="OK")
    _link(order_no="N-HSA-PART-P", product="시스템장 서랍", amount=500000, place_status="OK")
    _link(order_no="N-HSA-PART-P", product="시스템장 거울", amount=300000, place_status="")

    body = _open(client)
    dispatch_cell = _tight(_status_cell(_row(body, "N-HSA-PART-D")))
    place_cell = _tight(_status_cell(_row(body, "N-HSA-PART-P")))

    assert _tight("발송처리 1/2") in dispatch_cell, dispatch_cell
    assert _tight("발주확인 완료 2/2") in dispatch_cell, dispatch_cell
    assert _tight("발주확인 2/3") in place_cell, place_cell


def test_our_dispatch_without_naver_record_is_flagged(client, workbench_on):
    """우리만 보내고 네이버가 침묵하면 `네이버 기록 없음` 이 뜬다.

    발송처리는 **되돌릴 수 없는 호출**이다. 우리 표식만 있고 네이버 `sendDate` 가 없는
    집은 그 호출이 유실된 자리인데, 지금 이력 표는 두 축을 아예 안 읽어서 사람이
    판매자센터를 열어야만 알 수 있었다. 반대 방향(네이버에만 기록)은 판매자센터 직접
    발송이라 경고가 아니다 — 그래서 한 방향만 문다.
    """
    _login(client)
    order = _order()
    _link(order_no="N-HSA-MISMATCH", product="시스템장 8자 어긋남", amount=3180000,
          place_status="OK", dispatched_at="2026-08-27T07:02:00", send_date="",
          order_id=int(order.id))

    cell = _tight(_status_cell(_row(_open(client), "N-HSA-MISMATCH")))

    assert _tight("네이버 기록 없음") in cell, cell
    assert _tight("발송처리 완료") not in cell, "네이버가 침묵하는데 완료라고 적었다"


def test_settled_cancel_household_shows_one_cell_instead_of_the_pipe(client, workbench_on):
    """발주확인·발송 전에 취소가 **확정**된 집은 파이프 대신 `네이버 처리 없음` 한 칸.

    네이버에 아무것도 안 했고 앞으로도 안 한다. 여기에 `발송처리 할 차례`(주황)를 두면
    "지금 해라"라는 뜻이 되어 되돌릴 수 없는 호출을 부른다.
    """
    _login(client)
    _link(order_no="N-HSA-SKIP", product="중문 2연동 취소확정", amount=1120000,
          place_status="", claim_status="CANCEL_DONE")

    cell = _tight(_status_cell(_row(_open(client), "N-HSA-SKIP")))

    assert _tight("네이버 처리 없음") in cell, cell
    assert "발주확인" not in cell, "할 일이 없는 집에 발주확인 칸을 냈다"
    assert "발송처리" not in cell, "할 일이 없는 집에 발송 칸을 냈다"


# --------------------------------------------------------------------------- #
# 3. 취소·반품 축 — 확정 여부 (계약 §3.3)
# --------------------------------------------------------------------------- #

def test_claim_phase_splits_unsettled_from_settled(client, workbench_on):
    """`claim_phase` 가 **미확정과 확정을 가른다** — 라벨만으로는 안 갈린다.

    "취소 요청"과 "취소 완료"는 네이버가 확정했는지가 다른데, 이 축이 없던 시절 화면
    두 곳이 "claimStatus 가 비어 있지 않은가" 한 비트로 판정해 승인 전 취소가 `취소 완료`
    로 표기됐다. 그 판정은 주문 폐기(soft delete)의 허가증이기도 했다 —
    아직 살아 있을 수 있는 주문이 휴지통으로 갈 수 있었다(2026-08-28 운영 사고).
    """
    _login(client)
    _link(order_no="N-HSA-CLAIM-REQ", product="붙박이장 취소요청", amount=1000000,
          place_status="OK", claim_status="CANCEL_REQUEST")
    _link(order_no="N-HSA-CLAIM-DONE", product="붙박이장 취소완료", amount=1000000,
          place_status="OK", claim_status="CANCEL_DONE")

    body = _open(client)
    requested = _tight(_status_cell(_row(body, "N-HSA-CLAIM-REQ")))
    settled = _tight(_status_cell(_row(body, "N-HSA-CLAIM-DONE")))

    assert _tight("취소 요청 · 확정 전") in requested, requested
    assert _tight("취소 완료") in settled, settled
    assert "확정전" not in settled, "네이버가 확정한 건에 '확정 전' 꼬리를 달았다"


# --------------------------------------------------------------------------- #
# 4. 절대 규칙 3 — 이력 행은 끝까지 읽기 전용
# --------------------------------------------------------------------------- #

def test_history_rows_still_carry_no_mutation_surface(client, workbench_on):
    """상태 칸이 생겨도 이력 행에 **조작면이 없다**(절대 규칙 3).

    불가역 mutation 라우트(발주확인·발송처리·취소)는 전부 STAFF 까지 열려 있다.
    이력 행에 버튼이나 `data-link-id` 를 두면 그 자리가 곧 **과거 주문 전체**에 대한
    조작면이 된다. 그래서 잠그는 게 아니라 만들지 않는다 — 새 축이 그 규칙을 뚫지
    않는지 여기서 다시 문다(축마다 '지금 해라'라고 말하는 칸이 생겼기 때문이다).
    """
    _login(client)
    order = _order()
    _link(order_no="N-HSA-RO-1", product="읽기전용 추가결제", amount=180000,
          relation="ADDON", order_id=int(order.id))
    _link(order_no="N-HSA-RO-2", product="읽기전용 발송대기", amount=900000,
          place_status="OK", order_id=int(order.id))
    _link(order_no="N-HSA-RO-3", product="읽기전용 취소중", amount=500000,
          place_status="", claim_status="CANCEL_REQUEST")
    _link(order_no="N-HSA-RO-4", product="읽기전용 발송실패", amount=240000,
          place_status="OK", fail_reason="배송방법 코드 거부", fail_action="dispatch")

    rows = _hist_rows(_open(client))

    assert len(rows) >= 4, "이력 행이 안 떴다"
    for row in rows:
        assert "<button" not in row, row
        assert "data-link-id" not in row, row
        assert 'class="btn' not in row, row


def test_status_cell_markup_has_no_id_attribute(client, workbench_on):
    """상태 칸에 `id` 속성을 두지 않는다 — 행마다 반복되므로 하나만 넣어도 중복이다.

    문서 안 `id` 중복은 `test_naver_workbench_v3_contract.py` 가 이미 금지한다.
    상태 칸은 그 규칙이 가장 쉽게 깨지는 자리라(축 3줄 × 행 수) 여기서 따로 문다.
    """
    _login(client)
    order = _order()
    _link(order_no="N-HSA-NOID-1", product="아이디없음 하나", amount=100000,
          relation="ADDON", order_id=int(order.id))
    _link(order_no="N-HSA-NOID-2", product="아이디없음 둘", amount=200000,
          place_status="", claim_status="RETURN_REQUEST")

    for row in _hist_rows(_open(client)):
        cell = _status_cell(row)
        assert re.search(r"\sid\s*=", cell) is None, cell


# --------------------------------------------------------------------------- #
# 5. 어휘 — 칩과 배지가 한 낱말 (계약 §2.4 · §9-8)
# --------------------------------------------------------------------------- #

def test_chip_labels_start_with_the_badge_word(client, workbench_on):
    """모든 칩 라벨은 대응하는 **배지 낱말로 시작한다** — 한 화면 두 이름 금지.

    지금 화면은 칩이 `수집됨(생성 전)`·`생성됨` 인데 배지는 `수집됨`·`생성됨` 이라
    같은 축을 두 낱말로 부른다. 칩은 목록을 거르는 장치라 꼬리(`· 주문 전`)가 더 필요할
    수 있으므로 "같은 글자"가 아니라 "**배지 낱말로 시작**"을 계약으로 둔다 —
    그래야 검증 가능하면서 꼬리도 허용된다.

    상수를 테스트 함수 안에서 import 하는 것은 일부러다: 모듈 맨 위에서 읽으면 상수가
    아직 없을 때 이 파일 **전체**가 수집 단계에서 죽어, 다른 계약이 왜 깨졌는지 안 보인다.
    """
    from foms.web.admin.naver_ingest import HISTORY_FOMS_LABELS, HISTORY_STATUS_CHIPS

    for query, label in HISTORY_STATUS_CHIPS:
        state = CHIP_QUERY_TO_STATE[query]
        word = HISTORY_FOMS_LABELS[state]
        assert label.startswith(word), (
            f"칩 '{label}' 이 배지 낱말 '{word}' 로 시작하지 않는다", query)

    _login(client)
    order = _order()
    _link(order_no="N-HSA-W-COLLECTED", product="어휘 받아옴", amount=100000)
    _link(order_no="N-HSA-W-LINKED", product="어휘 주문만듦", amount=100000,
          order_id=int(order.id))
    _link(order_no="N-HSA-W-REVIEW", product="어휘 확인필요", amount=100000,
          sync_status="PENDING_REVIEW")
    _link(order_no="N-HSA-W-FAILED", product="어휘 받기실패", amount=100000,
          sync_status="FAILED")

    body = _open(client)
    chips = _tight(_chips(body))
    seen = {"COLLECTED": "N-HSA-W-COLLECTED", "LINKED": "N-HSA-W-LINKED",
            "PENDING_REVIEW": "N-HSA-W-REVIEW", "FAILED": "N-HSA-W-FAILED"}
    for query, label in HISTORY_STATUS_CHIPS:
        word = HISTORY_FOMS_LABELS[CHIP_QUERY_TO_STATE[query]]
        assert _tight(label) in chips, (f"칩 '{label}' 이 화면에 없다", chips)
        cell = _tight(_status_cell(_row(body, seen[query])))
        assert _tight(word) in cell, (f"행 배지가 '{word}' 가 아니다", cell)


# --------------------------------------------------------------------------- #
# 6. 숫자는 집 단위 · 필터는 안 풀린다 (계약 §4)
# --------------------------------------------------------------------------- #

def test_new_chip_numbers_count_households_not_links(client, workbench_on):
    """새 칩 두 개의 숫자는 **집 단위**다 — 링크 3건짜리 집 하나는 `1` 이다.

    링크 행으로 세면 "전체 36 · 발송처리 남음 102" 처럼 부분이 전체보다 커 보인다
    (2026-08-19 스테이징 실화면). 이 화면의 모든 숫자가 집 단위라는 규약을 새 칩이
    깨면 그 사고가 그대로 재발한다.
    """
    _login(client)
    order = _order()
    for idx, name in enumerate(("집단위 본품", "집단위 상부장", "집단위 서랍")):
        _link(order_no="N-HSA-GROUPCOUNT", product=name, amount=900000 - idx,
              place_status="OK", relation="ADDON", order_id=int(order.id))

    chips = _chips(_open(client))
    dispatch_chip = [text for href, text in _anchors(chips) if "dispatch=PENDING" in href]
    relation_chip = [text for href, text in _anchors(chips) if "rel=ADDON_REPAY" in href]

    assert dispatch_chip, ("`발송처리 남음` 칩이 없다", chips)
    assert relation_chip, ("`추가결제 · 재결제` 칩이 없다", chips)
    assert "1주문" in dispatch_chip[0], dispatch_chip
    assert "3주문" not in dispatch_chip[0], ("링크 수로 셌다", dispatch_chip)
    assert "1주문" in relation_chip[0], relation_chip
    assert "3주문" not in relation_chip[0], ("링크 수로 셌다", relation_chip)


def test_chips_and_pager_carry_all_four_filters(client, workbench_on, monkeypatch):
    """칩과 페이저가 `status`·`place`·`dispatch`·`rel` 을 **전부** 들고 간다.

    필터 파라미터가 4개가 됐다. 하나라도 안 실으면 그 링크를 누른 순간 사용자가 방금
    좁힌 목록이 조용히 풀린다(선행 결함 #8 과 같은 모양). 자기 축을 켜고 끄는 칩은
    그 축을 안 들고 가는 게 맞으므로, **나머지 세 개**를 들고 가는지를 문다.
    """
    from foms.web.admin import naver_ingest as mod
    from foms.web.admin.naver_ingest import HISTORY_STATUS_CHIPS

    monkeypatch.setattr(mod, "PAGE_SIZE", 1, raising=False)
    _login(client)
    order = _order()
    for order_no, product in (("N-HSA-F1", "필터 유지 하나"), ("N-HSA-F2", "필터 유지 둘")):
        _link(order_no=order_no, product=product, amount=100000, place_status="",
              relation="ADDON", order_id=int(order.id), sync_status="LINKED")

    body = _open(client, status="LINKED", place="PENDING",
                 dispatch="PENDING", rel="ADDON_REPAY")

    pager = _pager(body)
    for token in ("status=LINKED", "place=PENDING", "dispatch=PENDING",
                  "rel=ADDON_REPAY", "page=2"):
        assert token in pager, (f"페이저가 '{token}' 을 안 들고 간다", pager)

    chips = _anchors(_chips(body))
    axis_tokens = {"status": "status=LINKED", "place": "place=PENDING",
                   "dispatch": "dispatch=PENDING", "rel": "rel=ADDON_REPAY"}
    # (칩을 찾는 바늘, 그 칩이 **직접 토글하는** 축)
    targets = [(_tight(label), "status") for _query, label in HISTORY_STATUS_CHIPS]
    targets += [(_tight("발주확인 남음"), "place"),
                (_tight("발송처리 남음"), "dispatch"),
                (_tight("추가결제"), "rel")]
    for needle, own_axis in targets:
        found = [href for href, text in chips if needle in text]
        assert found, (f"칩 '{needle}' 이 화면에 없다", chips)
        for axis, token in axis_tokens.items():
            if axis == own_axis:
                continue
            assert token in found[0], (f"칩 '{needle}' 이 '{token}' 을 안 들고 간다", found[0])


def test_place_pending_matches_the_new_counters(app, workbench_on):
    """기존 `place_pending` 과 새 집계가 **갈리지 않는다**.

    `place_pending`(옛 필드)과 `place_done_count`/`place_total`(새 필드)이 같은 사실을
    두 벌로 말하게 됐다. 두 값이 어긋나면 같은 행이 "발주확인 완료"라고 적으면서 칩에는
    '발주확인 남음'으로 잡힌다 — 화면과 숫자가 갈리는 그 결함이 정확히 이 자리에서 난다.

    라우트가 아니라 `_link_rows` 를 직접 부른다. 템플릿(레인 C)이 아직 없어도 서버
    계약만은 스스로 판정된다.
    """
    from foms.web.admin.naver_ingest import _link_rows

    _link(order_no="N-HSA-PARITY-ALL", product="정합 전부완료", amount=100000,
          place_status="OK")
    _link(order_no="N-HSA-PARITY-PART", product="정합 일부완료 하나", amount=200000,
          place_status="OK")
    _link(order_no="N-HSA-PARITY-PART", product="정합 일부완료 둘", amount=100000,
          place_status="")
    _link(order_no="N-HSA-PARITY-NONE", product="정합 전부미완", amount=300000,
          place_status="")

    with app.test_request_context(f"{TRIAGE_PATH}?tab=all"):
        rows, total = _link_rows(db_session, status=None, page=1)

    assert total == 3, rows
    for row in rows:
        assert row["place_total"] == row["count"], row
        assert row["place_pending"] == (row["place_done_count"] < row["place_total"]), row


# --------------------------------------------------------------------------- #
# 7. 어긋남 경고는 **어긋난 그 링크**의 시각만 쓴다 (2026-08-30 CEO 지적)
# --------------------------------------------------------------------------- #

def test_dispatch_mismatch_warning_uses_only_the_mismatched_links_time(client, workbench_on):
    """경고 줄의 시각은 **어긋난 링크**의 것이다 — 집을 접은 최솟값이 아니다.

    집계는 두 값을 따로 만든다: ``dispatch_ours_at`` 은 멤버 전체의 가장 이른 발송 시각,
    ``dispatch_mismatch_ours_at`` 은 **네이버가 침묵하는 링크만** 모은 것이다. 예전에는
    경고 문장이 앞의 것을 썼다. 멤버가 [정상 09:00, 어긋남 16:02] 이면 화면이
    "우리 발송 09:00 · 네이버 기록 없음" 이라 적는데, **그 09:00 은 네이버가 기록한
    건**이다. 발송처리는 되돌릴 수 없는 호출이고 이 문장은 그 호출이 유실된 자리를
    가리키므로, 틀린 시각을 적으면 사람이 판매자센터에서 엉뚱한 건을 뒤진다.

    두 값이 다시 한 값으로 접히면 이 테스트가 빨강이 된다 — 그게 이번 라운드의 핵심
    회귀 자리다. 우리 표식은 UTC naive 로 저장되므로 09:00·16:02(KST)는
    ``00:00``·``07:02``(UTC)로 넣는다.
    """
    _login(client)
    order = _order()
    # 정상 — 우리 09:00 · 네이버 12:03. 어긋남이 아니다(두 축이 서로를 확인한다).
    _link(order_no="N-HSA-MISTIME", product="어긋남시각 정상건", amount=2000000,
          place_status="OK", dispatched_at="2026-08-26T00:00:00",
          send_date="2026-08-26T12:03:00.000+09:00", order_id=int(order.id))
    # 어긋남 — 우리 16:02 · 네이버 침묵. 경고가 가리켜야 하는 유일한 링크다.
    _link(order_no="N-HSA-MISTIME", product="어긋남시각 유실건", amount=900000,
          place_status="OK", dispatched_at="2026-08-26T07:02:00", send_date="",
          order_id=int(order.id))

    cell = _status_cell(_row(_open(client), "N-HSA-MISTIME"))
    warns = _warns(cell)

    assert warns == [_tight("우리 발송 2026-08-26 16:02 · 네이버 기록 없음")], warns
    assert "09:00" not in cell, (
        "네이버가 기록한 형제의 시각을 '네이버 기록 없음' 이라 말했다", cell)


def test_dispatch_mismatch_warning_never_borrows_a_siblings_time(client, workbench_on):
    """시각 없는 형제가 섞여도 경고는 **자기 링크의 시각**만 쓴다.

    앞 테스트는 "더 이른 정상 발송" 으로 되돌림을 잡는다. 이건 반대 모양이다 — 우리도
    네이버도 침묵하는 형제(어긋남 아님·시각 없음)가 섞인 집이다. 경고가 집계값으로
    되돌아가면 이 집에서도 문장이 서지만, 그때 붙는 시각은 어긋난 링크의 것이 아니다.
    """
    _login(client)
    order = _order()
    # 우리도 네이버도 침묵 — 어긋남이 아니고 시각도 없다.
    _link(order_no="N-HSA-MISTIME-ONE", product="시각없는 형제", amount=1500000,
          place_status="OK", order_id=int(order.id))
    # 어긋남 — 우리 16:02 · 네이버 침묵.
    _link(order_no="N-HSA-MISTIME-ONE", product="어긋남 본건", amount=700000,
          place_status="OK", dispatched_at="2026-08-26T07:02:00", send_date="",
          order_id=int(order.id))

    warns = _warns(_status_cell(_row(_open(client), "N-HSA-MISTIME-ONE")))

    assert warns == [_tight("우리 발송 2026-08-26 16:02 · 네이버 기록 없음")], warns


# --------------------------------------------------------------------------- #
# 8. 취소·반품 줄의 날짜·사유 (목업 확정본 · 2026-08-30 사람 결정 1)
# --------------------------------------------------------------------------- #

def test_settled_return_shows_the_confirmed_date_and_the_collect_refund_tail(client, workbench_on):
    """확정된 반품은 **배지에 확정 날짜**, 작은 글자에 수거·환불 조각을 낸다.

    목업 확정본 E13 이 이 줄이다: `반품 완료 08-26` · `수거 완료 08-25 · 환불 완료`.
    서버가 이 값들을 계산해 놓고 화면이 안 읽던 시절, 화면은 `반품 완료` 한 낱말만 내서
    "언제 끝났나 · 환불은 나갔나" 를 사람이 판매자센터에서 다시 확인해야 했다
    (2026-08-30 CEO 지적 4 — 계산만 하고 아무도 안 읽는 죽은 값이었다).

    ``==`` 로 잠그는 이유: 조각이 **더 붙어도** 빨강이어야 한다. 사유를 안 준 집인데
    작은 글자에 사유가 뜨면 그건 다른 멤버의 값이 샌 것이다.
    """
    _login(client)
    order = _order()
    _link(order_no="N-HSA-CLAIM-RETDONE", product="반품 확정 집", amount=1580000,
          place_status="OK", claim_status="RETURN_DONE",
          dispatched_at="2026-08-20T00:00:00",
          send_date="2026-08-20T12:00:00.000+09:00", order_id=int(order.id),
          return_block={
              "claimStatus": "RETURN_DONE", "claimType": "RETURN",
              "collectCompletedDate": "2026-08-25T09:17:35.539+09:00",
              "returnCompletedDate": "2026-08-26T10:02:11.000+09:00",
              "refundStandbyStatus": "환불처리완료",
          })

    claim_row = _axis_row(_status_cell(_row(_open(client), "N-HSA-CLAIM-RETDONE")),
                          "취소·반품")

    assert _badges(claim_row) == [_tight("반품 완료 08-26")], claim_row
    assert _whens(claim_row) == [_tight("수거 완료 08-25 · 환불 완료")], claim_row


def test_unsettled_return_shows_the_reason_and_the_refund_due_date(client, workbench_on):
    """진행 중 반품은 **사유와 환불 예정일**을 낸다 — 확정 날짜는 안 낸다.

    목업 확정본 E12 가 이 줄이다: 배지 `수거중 · 확정 전`, 작은 글자
    `단순 변심 · 환불 예정 08-30`. 사유는 코드 라벨(``CLAIM_REASON_LABELS``)이고 고객이
    쓴 원문(``detailed_reason``)이 아니다 — 길이가 안 정해져 있어 좁은 칸에 못 싣는다.

    배지 낱말은 목업의 `반품 수거중` 이 아니라 상수 `수거중` 이다: 수거는 반품·교환
    **양쪽**에서 오므로 `반품` 을 붙이면 교환 건에서 화면이 틀린 이름을 말한다
    (계약 §3.3 — 상수가 목업을 이기는 자리).

    아직 안 끝난 일에 끝난 날짜를 적지 않는지도 함께 문다: 확정 날짜 조각이 배지에
    붙으면 ``==`` 가 빨강이 된다.
    """
    _login(client)
    _link(order_no="N-HSA-CLAIM-COLLECTING", product="반품 진행 집", amount=1100000,
          place_status="OK", claim_status="COLLECTING",
          return_block={
              "claimStatus": "COLLECTING", "claimType": "RETURN",
              "returnReason": "SIMPLE_INTENT_CHANGED",
              "refundExpectedDate": "2026-08-30T00:00:00.000+09:00",
          })

    claim_row = _axis_row(_status_cell(_row(_open(client), "N-HSA-CLAIM-COLLECTING")),
                          "취소·반품")

    assert _badges(claim_row) == [_tight("수거중 · 확정 전")], claim_row
    assert _whens(claim_row) == [_tight("단순 변심 · 환불 예정 08-30")], claim_row


def test_collect_done_household_shows_the_collect_time(client, workbench_on):
    """수거가 끝난 집은 **수거 시각**을 낸다 — 같은 낱말을 두 번 적지 않는다.

    수거 완료는 아직 반품 확정이 아니다(``CLAIM_PHASES`` 가 ``in_progress`` 로 둔다).
    그래서 배지에 `확정 전` 꼬리가 붙는다. 날짜는 **배지에** 붙인다 — 배지 낱말이 이미
    `수거 완료` 라서 작은 글자에 `수거 완료 08-25` 를 또 적으면 한 줄에 같은 낱말이 두 번
    선다(2026-08-30 CEO 지적 3, 그 전까지 이 테스트가 중복 출력을 그대로 잠그고 있었다).
    그 날짜는 **끝난 하위 사건의 시각**이라 미확정 배지에 붙어도 거짓이 아니다.
    환불 예정일도 사유도 안 준 집이므로 작은 글자는 통째로 안 나온다 — 뜨면 다른 값이 샌 것이다.
    """
    _login(client)
    _link(order_no="N-HSA-CLAIM-COLLECTDONE", product="수거 완료 집", amount=980000,
          place_status="OK", claim_status="COLLECT_DONE",
          return_block={
              "claimStatus": "COLLECT_DONE", "claimType": "RETURN",
              "collectCompletedDate": "2026-08-25T09:17:35.539+09:00",
          })

    claim_row = _axis_row(_status_cell(_row(_open(client), "N-HSA-CLAIM-COLLECTDONE")),
                          "취소·반품")

    assert _badges(claim_row) == [_tight("수거 완료 08-25 · 확정 전")], claim_row
    assert _whens(claim_row) == [], claim_row


def test_claim_without_any_date_or_reason_shows_the_badge_alone(client, workbench_on):
    """줄 재료가 없는 클레임은 **배지만** 낸다 — 빈 조각을 만들지 않는다.

    "값이 없다"와 "우리가 모른다"를 화면에서 같은 모양으로 만들지 않기 위한 규칙이다
    (계약 §3). 빈 문자열이 와도 ``.wb-st__when`` 을 만들어 두면 빈 칸이 하나 생기고,
    그 빈 칸은 다음 사람에게 "값이 없는 게 확인됐다" 로 읽힌다.

    취소 확정 집을 쓰는 이유: 오늘 이 화면에서 **날짜 출처가 실제로 없는** 클레임
    종류다. 반품 축(``mapping.RETURN_BLOCK_KEYS``)이 ``cancel`` 블록을 일부러 빼기
    때문이다 — 취소 블록의 환불 필드를 반품 축으로 읽으면 취소만 된 건이 "반품 진행"
    이라고 말한다(스테이징 344 링크 중 50건이 그랬다). 그래서 화면은 그 자리를
    지어내지 않고 배지 하나로 끝낸다.
    """
    _login(client)
    _link(order_no="N-HSA-CLAIM-BARE", product="취소 확정 집", amount=1120000,
          place_status="", claim_status="CANCEL_DONE")

    claim_row = _axis_row(_status_cell(_row(_open(client), "N-HSA-CLAIM-BARE")),
                          "취소·반품")

    assert _badges(claim_row) == [_tight("취소 완료")], claim_row
    assert _whens(claim_row) == [], ("줄 재료가 없는데 작은 글자를 만들었다", claim_row)


# --------------------------------------------------------------------------- #
# 9. 칩 라벨의 단일 출처 (2026-08-30 사람 결정 4)
# --------------------------------------------------------------------------- #

def test_chip_labels_follow_the_server_constant(client, workbench_on, monkeypatch):
    """서버 상수를 바꾸면 **렌더된 칩도 따라 바뀐다** — 템플릿이 두 벌째 안 적는다.

    :func:`test_chip_labels_start_with_the_badge_word` 는 상수와 화면이 **일치하는지**만
    묻는다. 그건 드리프트 감시지 단일 출처의 증거가 아니다 — 템플릿이 같은 네 낱말을
    손으로 적어 두면 그 테스트는 계속 초록이다(실제로 그랬다, 2026-08-30 CEO 지적).

    그래서 상수를 **바꿔** 본다. 화면이 상수를 읽고 있으면 바뀐 낱말이 그대로 나오고
    옛 낱말은 사라진다. 템플릿이 하드코딩으로 되돌아가면 이 테스트가 빨강이 된다.
    """
    from foms.web.admin import naver_ingest as mod

    original = mod.HISTORY_STATUS_CHIPS
    _login(client)
    _link(order_no="N-HSA-CHIPSRC", product="칩 출처 확인", amount=100000)

    before = _tight(_chips(_open(client)))
    for _query, label in original:
        assert _tight(label) in before, (f"칩 '{label}' 이 기본 화면에 없다", before)

    monkeypatch.setattr(mod, "HISTORY_STATUS_CHIPS",
                        (("COLLECTED", "받아옴 · 상수에서 온 낱말"),))
    after = _tight(_chips(_open(client)))

    assert _tight("받아옴 · 상수에서 온 낱말") in after, (
        "상수를 바꿨는데 칩이 안 따라왔다 — 템플릿이 라벨을 손으로 적고 있다", after)
    for _query, label in original:
        assert _tight(label) not in after, (
            f"상수에서 뺀 칩 '{label}' 이 아직 화면에 있다 — 두 벌째 출처가 남았다", after)


# --------------------------------------------------------------------------- #
# 10. 클레임 없는 링크는 반품 축을 파싱하지 않는다 (2026-08-30 사람 결정 3)
# --------------------------------------------------------------------------- #

def test_links_without_a_claim_never_parse_the_return_axis(client, workbench_on, monkeypatch):
    """클레임이 없는 링크에는 ``_return_axis_view`` 를 **한 번도 안 부른다**.

    반품 축 파싱은 링크마다 스냅샷 블록을 훑고 시각 3종을 KST 로 편다. 이력 표는 쪽당
    50집이고 집마다 멤버가 여럿이라, 전 링크에 걸면 화면에 낼 것이 하나도 없는 집까지
    같은 값을 치른다(2026-08-30 CEO 지적 3). 판정 술어는 ``claim_label`` — 라벨을 준
    멤버만 축도 갖는다는 규약이라 라벨 없는 링크에는 낼 것이 애초에 없다.

    **양성 대조군을 같은 모집단 안에서** 함께 돈다: 세는 장치가 실제로 작동하는지
    증명하지 않으면 "0회" 는 계측이 안 걸린 것과 구별되지 않는다.

    링크를 전부 ``reviewed`` 로 만드는 이유는 계측 격리다 — 확인 안 된 건이 하나라도
    있으면 처리 탭 pane 이 자동으로 열려 **그 링크의** 반품 축을 한 번 판다. 그건 다른
    화면의 몫이라 이력 표의 값에 섞이면 안 된다.
    """
    from foms.web.admin import naver_ingest as mod

    seen: list[int] = []
    original = mod._return_axis_view

    def _counted(link: Any) -> dict[str, Any]:
        """부른 링크 id 를 적어 두고 원래 함수를 그대로 부른다."""
        seen.append(int(link.id))
        return original(link)

    monkeypatch.setattr(mod, "_return_axis_view", _counted)
    _login(client)
    order = _order()
    _link(order_no="N-HSA-NOCLAIM-A", product="클레임없음 본품", amount=1000000,
          place_status="OK", order_id=int(order.id), reviewed=True)
    _link(order_no="N-HSA-NOCLAIM-A", product="클레임없음 상부장", amount=200000,
          place_status="OK", order_id=int(order.id), reviewed=True)
    _link(order_no="N-HSA-NOCLAIM-B", product="클레임없음 별집", amount=300000,
          reviewed=True)

    _open(client)

    assert seen == [], ("클레임 없는 링크에 반품 축 파싱이 걸렸다", seen)

    claimed = _link(order_no="N-HSA-WITHCLAIM", product="클레임있음 집", amount=400000,
                    place_status="OK", claim_status="RETURN_REQUEST", reviewed=True)
    _open(client)

    assert seen == [int(claimed.id)], ("양성 대조군 — 세는 장치가 안 걸렸다", seen)


# --------------------------------------------------------------------------- #
# 11. 근거 없는 문구는 화면에 없다 (2026-08-30 사람 결정 5)
# --------------------------------------------------------------------------- #

def test_shipping_due_overrun_says_only_the_fact_we_can_prove(client, workbench_on, monkeypatch):
    """발송기한 초과는 `발송기한 N일 지남` 까지만 말한다 — `네이버 자동 취소 가능` 은 없다.

    앞 문장은 우리가 가진 값(``shippingDueDate``)에서 바로 나오는 사실이다. 뒷 문장은
    네이버가 초과 건을 실제로 자동 취소한다는 주장인데, 그 근거가 상수·문서·테스트
    어디에도 없었다(2026-08-30 CEO 지적). 운영자가 그 문장을 보고 판매자센터 확인을
    건너뛸 수 있는 종류의 주장이라 지웠다 — 다시 들어오면 이 테스트가 빨강이 된다.

    오늘 날짜를 고정하는 이유: 초과 일수가 진짜로 계산된 값인지를 잠그기 위해서다.
    자릿수만 보면(``\\d+``) 0 이든 999 든 초록이라 계산이 망가져도 안 보인다.
    """
    from foms.web.admin import naver_ingest as mod

    monkeypatch.setattr(mod, "get_today_kst", lambda: datetime.date(2026, 8, 30))
    _login(client)
    _link(order_no="N-HSA-DUEOVER", product="발송기한 지난 집", amount=1200000,
          place_status="OK", shipping_due="2026-08-20")

    body = _open(client)
    naver_row = _axis_row(_status_cell(_row(body, "N-HSA-DUEOVER")), "네이버")

    assert _tight("발송기한 10일 지남") in _tight(naver_row), naver_row
    assert _tight("네이버 자동 취소 가능") not in _tight(body), (
        "근거 없는 자동 취소 주장이 화면에 돌아왔다")

# --------------------------------------------------------------------------- #
# 2026-08-30 minor 정리 라운드 — CEO 재판정이 "안 단언됨" 으로 짚은 분기들
# --------------------------------------------------------------------------- #

def test_closed_order_household_says_the_order_was_dropped(client, workbench_on):
    """ERP 주문을 접은 집은 `주문 접음` 이라고 말한다.

    `foms_state == 'closed'` 분기는 코드에만 있고 화면 단언이 없었다(2026-08-30 CEO 재판정).
    수집은 됐는데 사람이 주문을 지운 집이 `주문 만듦` 으로 보이면 정산에서 살아 있는
    주문으로 센다.
    """
    _login(client)
    order = _order(product="접은 주문")
    order.status = "DELETED"
    db_session.commit()
    _link(order_no="N-HSA-CLOSED", product="접은 주문 집", order_id=order.id,
          place_status="OK", reviewed=True)

    cell = _status_cell(_row(_open(client), "N-HSA-CLOSED"))

    assert _tight("주문 접음") in _badges(_axis_row(cell, "FOMS")), cell
    assert "주문 만듦" not in cell, cell


def test_confirm_failure_paints_the_place_step_and_says_why(client, workbench_on):
    """발주확인이 실패한 집은 파이프 첫 칸이 `발주확인 실패` 이고 사유가 경고 줄에 남는다.

    실패 축은 서버에만 있고 렌더 단언이 없었다. 실패를 `발주확인 할 차례` 로 칠하면
    사람이 다시 눌러도 되는 줄 알고, 사유(네이버 응답)는 화면 어디에도 없게 된다.
    """
    _login(client)
    order = _order(product="발주확인 실패")
    _link(order_no="N-HSA-FAILCONFIRM", product="발주확인 실패 집", order_id=order.id,
          place_status="", fail_reason="이미 발주확인된 상품주문입니다",
          fail_action="confirm", reviewed=True)

    cell = _status_cell(_row(_open(client), "N-HSA-FAILCONFIRM"))

    assert "발주확인 실패" in cell, cell
    assert _tight("이미 발주확인된 상품주문입니다") in " ".join(_warns(cell)), cell


def test_dispatch_failure_keeps_the_place_step_done(client, workbench_on):
    """발송처리 실패는 **발송 칸만** 빨갛다 — 이미 끝난 발주확인까지 뒤집지 않는다."""
    _login(client)
    order = _order(product="발송처리 실패")
    _link(order_no="N-HSA-FAILDISPATCH", product="발송처리 실패 집", order_id=order.id,
          place_status="OK", fail_reason="배송방법 코드 거부",
          fail_action="dispatch", reviewed=True)

    cell = _status_cell(_row(_open(client), "N-HSA-FAILDISPATCH"))

    assert "발송처리 실패" in cell, cell
    assert "발주확인 완료" in cell, cell
    assert _tight("배송방법 코드 거부") in " ".join(_warns(cell)), cell


def test_settled_claim_household_says_dispatch_will_not_happen(client, workbench_on):
    """취소·반품이 도는 집의 발송 칸은 `발송 안 함` 이다 — `할 차례` 가 아니다.

    `dispatch_moot` 분기에 화면 단언이 없었다. 이 자리에 `발송처리 할 차례` 가 뜨면
    되돌릴 수 없는 발송을 취소 진행 건에 보내라고 화면이 부추기는 셈이다.
    """
    _login(client)
    order = _order(product="반품 진행")
    _link(order_no="N-HSA-MOOT", product="반품 진행 집", order_id=order.id,
          place_status="OK", claim_status="COLLECTING", reviewed=True,
          return_block={"claimStatus": "COLLECTING", "claimType": "RETURN"})

    cell = _status_cell(_row(_open(client), "N-HSA-MOOT"))

    assert "발송 안 함" in cell, cell
    assert "발송처리 할 차례" not in cell, cell


def test_our_dispatch_confirmed_by_naver_says_so(client, workbench_on):
    """우리가 보냈고 네이버도 찍은 건은 `네이버 확인됨` 이라고 말한다.

    부속 문구 표(계약 §3.2)에서 이 줄만 단언이 없었다. 판매자센터에서 직접 나간 건
    (우리 기록 없음)과 **다른 사실**이라 두 문구가 뒤바뀌면 안 된다.
    """
    _login(client)
    order = _order(product="발송 완료")
    _link(order_no="N-HSA-CONFIRMED", product="발송 완료 집", order_id=order.id,
          place_status="OK", dispatched_at="2026-08-28T11:40:00",
          send_date="2026-08-28T12:03:00+09:00", reviewed=True)

    cell = _status_cell(_row(_open(client), "N-HSA-CONFIRMED"))

    assert "네이버 확인됨" in cell, cell
    assert "판매자센터에서 직접" not in cell, cell


def test_unreadable_claim_time_never_becomes_a_fake_date(client, workbench_on):
    """읽을 수 없는 시각 원문이 **가짜 날짜**로 잘려 나오지 않는다.

    시각은 못 읽으면 원문을 그대로 남기는 규약이다(`_dispatch_time_text`). 예전 코드는
    그 원문을 `[5:10]` 으로 무조건 잘라서 `PENDING_REFUND_2026` 을 `반품 완료 NG_RE` 로
    적었다(2026-08-30 CEO 재판정 — `_history_shipping_due` 에서 고친 함정의 재발).
    날짜로 못 읽으면 조각을 통째로 안 내는 것이 옳다.
    """
    _login(client)
    _link(order_no="N-HSA-BADDATE", product="못 읽는 시각 집", place_status="OK",
          claim_status="RETURN_DONE", reviewed=True,
          return_block={"claimStatus": "RETURN_DONE", "claimType": "RETURN",
                        "returnCompletedDate": "PENDING_REFUND_2026"})

    cell = _status_cell(_row(_open(client), "N-HSA-BADDATE"))
    claim_row = _axis_row(cell, "취소·반품")

    assert _badges(claim_row) == [_tight("반품 완료")], claim_row
    assert "NG_RE" not in cell, cell


def test_settled_cancel_household_shows_the_cancel_date_and_refund(client, workbench_on):
    """확정된 **취소** 집도 날짜와 환불 완료를 낸다 — 반품만 되던 자리다.

    반품 축(`extract_return_axis`)은 `cancel` 블록을 **일부러 뺀다**: 취소 블록의 환불
    필드가 반품 진행으로 새어 취소만 된 건에 "반품 진행" 줄이 뜨던 결함(2026-08-27) 때문이다.
    그 결과 순수 취소 건은 확정 시각도 환불 상태도 영영 빈 값이었고, 목업 확정본의
    `취소 완료 08-26 · 환불 완료` 가 배지 한 낱말로 줄어 있었다.

    고치는 방향은 **축을 하나 더 두는 것**이지 반품 축에 `cancel` 을 도로 넣는 것이 아니다 —
    그건 고친 누출을 되살린다. 이 테스트는 두 사실을 함께 잠근다:
    ① 취소 확정 집에 날짜·환불 완료가 뜬다 ② 그 집에 반품 진행 낱말(`수거 완료`)이 안 뜬다.
    """
    _login(client)
    _link(order_no="N-HSA-CANCELDONE", product="취소 확정 집", place_status="OK",
          claim_status="CANCEL_DONE", reviewed=True,
          cancel_block={"claimStatus": "CANCEL_DONE", "claimType": "CANCEL",
                        "cancelCompletedDate": "2026-08-26T20:31:00.000+09:00",
                        "refundStandbyStatus": "환불처리완료"})

    claim_row = _axis_row(_status_cell(_row(_open(client), "N-HSA-CANCELDONE")), "취소·반품")

    assert _badges(claim_row) == [_tight("취소 완료 08-26")], claim_row
    assert _whens(claim_row) == [_tight("환불 완료")], claim_row
    assert "수거 완료" not in claim_row, claim_row


def test_cancel_request_without_approval_shows_no_date(client, workbench_on):
    """승인 전 취소 요청은 **날짜를 안 낸다** — 없는 값을 지어내지 않는다.

    운영 실데이터에 `cancelApprovalDate`·`cancelCompletedDate` 가 둘 다 없는 요청 건이
    실제로 있다(link 79). 그 집에 날짜가 뜨면 아직 안 끝난 일에 끝난 날짜를 적는 셈이다.
    """
    _login(client)
    _link(order_no="N-HSA-CANCELREQ", product="취소 요청 집", place_status="OK",
          claim_status="CANCEL_REQUEST", reviewed=True,
          cancel_block={"claimStatus": "CANCEL_REQUEST", "claimType": "CANCEL"})

    claim_row = _axis_row(_status_cell(_row(_open(client), "N-HSA-CANCELREQ")), "취소·반품")

    assert _badges(claim_row) == [_tight("취소 요청 · 확정 전")], claim_row
    assert _whens(claim_row) == [], claim_row
