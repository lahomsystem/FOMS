"""원본 스냅샷에 **이미 들어 있던** 사실 3종이 화면에 닿는지 (2026-08-26).

근거: ``docs/guides/NAVER_FIELD_INVENTORY.md`` §3 우선순위 3건. 셋 다 수집분 281/281 에
들어 있는데 화면이 안 읽었을 뿐이라 **네이버로 나가는 호출은 0이다**.

* F-1 ``cancelDetailedReason`` — 고객이 직접 쓴 사유 원문. 재결제 판정의 결정적 근거인데
  지금까지 담당자가 이 한 줄을 보려고 판매자센터를 따로 열었다.
* F-2 ``delivery.sendDate`` — 발송처리를 우리가 눌러 놓고 그 결과 시각을 화면이 안 읽었다.
  우리 기록과 나란히 둬야 **어긋남**이 보인다(그게 이 줄의 값어치다).
* F-3 ``remain*``/``initial*`` — 부분취소 뒤 **남은 몇 개인지**(표의 숫자는 원래 값이다).

이 파일이 무는 규율은 하나 더 있다: **없는 값을 지어내지 않는다.** 원본이 말한 적 없는
것은 빈 칸이나 ``-`` 로 채우지 않고 **줄 자체를 내지 않는다** — 그래야 화면이 침묵과
거짓말을 구분한다. 그리고 F-3 은 회귀 위험이 가장 큰 자리다(281/281 이 그 필드를 갖고
있어서 존재 여부로 판정하면 모든 행이 부분취소로 보인다) — 아닌 행이 **지금 화면 그대로**
인지를 여기서 못박는다.
"""

from __future__ import annotations

import pathlib
from typing import Optional

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import ExternalOrderLink

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _pane,
    _uid,
    workbench_on,
)

PANE_PATH = "/admin/naver-ingest/triage/pane"

CSS_PATH = pathlib.Path("static/css/admin/naver-workbench.css")
PANE_TEMPLATE_PATH = pathlib.Path("templates/admin/partials/naver_workbench_pane.html")


def _patch(link: ExternalOrderLink, *, product_order: Optional[dict] = None,
           **blocks) -> ExternalOrderLink:
    """수집된 링크의 원본 스냅샷에 축을 얹는다(JSONB 수정 패턴).

    ``_collected`` 가 만드는 모양을 그대로 두고 **재려는 축만** 더한다 — 픽스처 모양이
    두 벌이 되면 재려던 것과 다른 것을 재게 된다.

    Args:
        link: 수집된 링크.
        product_order: ``productOrder`` 에 병합할 필드.
        blocks: 최상위에 얹을 블록(``cancel``·``delivery`` 등).

    Returns:
        갱신된 링크 행.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    snapshot = dict(row.raw_snapshot or {})
    if product_order:
        snapshot["productOrder"] = dict(snapshot.get("productOrder") or {}, **product_order)
    snapshot.update(blocks)
    row.raw_snapshot = snapshot
    flag_modified(row, "raw_snapshot")
    db_session.commit()
    return row


def _mark_dispatched(link_id: int, stamp: str) -> None:
    """워커가 남기는 발송 표식(``triage_state['fulfillment']['dispatched_at']``)을 써 넣는다.

    Args:
        link_id: 링크 id.
        stamp: UTC naive isoformat 문자열(워커가 남기는 모양 그대로).
    """
    row = db_session.get(ExternalOrderLink, int(link_id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = dict(state.get("fulfillment") or {}, dispatched_at=stamp)
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _pane_html(client, link_id: int) -> str:
    """상세 pane 조각만 받아 온다(레이아웃·목록 없음)."""
    response = client.get(f"{PANE_PATH}?link_id={link_id}")
    assert response.status_code == 200, response.status_code
    return _pane(response.get_data(as_text=True))


def _product_table(pane: str) -> str:
    """상품주문 행 단위 표만 잘라 온다 — 집 단위 표와 섞이면 재려던 것을 못 잰다."""
    return pane.split('data-cmp-section="product-orders"')[1].split("</table>")[0]


# --------------------------------------------------------------------------- #
# F-1 — 고객이 쓴 사유 원문
# --------------------------------------------------------------------------- #

def test_customer_written_reason_reaches_the_screen(client, workbench_on):
    """사유 원문이 있는 집은 **그 문장이 그대로** 화면에 나온다.

    배지("취소 요청")는 코드 라벨이라 왜 취소인지를 말하지 못한다. 실데이터
    "일시불 재결제 예정" 이 재결제/추가결제를 가르는 근거다.
    """
    _login(client)
    link = _collected(order_no="N-WB-REASON", product="붙박이장", amount=100000,
                      claim_status="CANCEL_REQUEST")
    _patch(link, cancel={"claimStatus": "CANCEL_REQUEST",
                         "cancelReason": "CHANGE_MIND",
                         "cancelDetailedReason": "일시불 재결제 예정"})

    pane = _pane_html(client, link.id)

    assert "wb-claim-reason" in pane, "사유 원문 줄이 통째로 없다"
    assert "일시불 재결제 예정" in pane, "고객이 쓴 문장이 화면에 닿지 않았다"


def test_reason_code_and_written_sentence_are_not_merged(client, workbench_on):
    """코드값(``reason``)과 문장(``detailed_reason``)은 다른 축이다 — 문장 자리에 코드가 오면 안 된다."""
    _login(client)
    link = _collected(order_no="N-WB-REASON2", product="붙박이장", amount=100000,
                      claim_status="CANCEL_REQUEST")
    _patch(link, cancel={"claimStatus": "CANCEL_REQUEST",
                         "cancelReason": "CHANGE_MIND",
                         "cancelDetailedReason": "다른 색으로 다시 주문할게요"})

    # 여는 태그 기준으로 자른다 — 그냥 클래스 이름으로 자르면 안쪽 `__k`·`__v` 에서
    # 또 잘려 문장이 든 뒷부분이 통째로 빠진 조각을 단언하게 된다.
    reason_line = _pane_html(client, link.id).split('class="wb-claim-reason ')[1].split("</div>")[0]

    assert "다른 색으로 다시 주문할게요" in reason_line
    assert "CHANGE_MIND" not in reason_line, "코드값이 문장 자리에 새어 들어왔다"


def test_no_written_reason_means_no_line_at_all(client, workbench_on):
    """사유 원문이 없는 집은 **그 줄 자체가 없다** — 빈 칸도 '-' 도 아니다.

    빈 칸을 내면 사람은 "고객이 아무 말도 안 했다"로 읽는다. 사실은 화면이 모르는 것이다.
    """
    _login(client)
    link = _collected(order_no="N-WB-NOREASON", product="붙박이장", amount=100000,
                      claim_status="CANCEL_REQUEST")
    _patch(link, cancel={"claimStatus": "CANCEL_REQUEST", "cancelReason": "CHANGE_MIND"})

    pane = _pane_html(client, link.id)

    assert "wb-claim-reason" not in pane, "사유 원문이 없는데 빈 줄이 났다"
    assert "고객이 쓴 사유" not in pane


# --------------------------------------------------------------------------- #
# F-2 — 발송 결과(우리 기록 ↔ 네이버가 말하는 것)
# --------------------------------------------------------------------------- #

def test_naver_send_date_reaches_the_screen(client, workbench_on):
    """네이버가 말하는 발송 시각과 배송 상태가 한 줄로 나온다."""
    _login(client)
    link = _collected(order_no="N-WB-SEND", product="붙박이장", amount=100000)
    _patch(link, delivery={"deliveryMethod": "DIRECT_DELIVERY",
                           "deliveryStatus": "NOT_TRACKING",
                           "sendDate": "2026-08-25T14:03:00.000+09:00"})

    pane = _pane_html(client, link.id)

    assert "발송처리 2026-08-25 14:03" in pane, "발송 시각이 화면에 닿지 않았다"
    assert "배송추적 없음" in pane, "배송 상태 낱말이 없다"


def test_unknown_delivery_status_is_shown_raw(client, workbench_on):
    """모르는 상태값은 **원문 그대로** 보여준다 — 숨기면 화면이 그 사실을 잃는다."""
    _login(client)
    link = _collected(order_no="N-WB-SEND-RAW", product="붙박이장", amount=100000)
    _patch(link, delivery={"deliveryStatus": "SOMETHING_NEW",
                           "sendDate": "2026-08-25T09:00:00.000+09:00"})

    assert "SOMETHING_NEW" in _pane_html(client, link.id)


def test_no_send_record_on_either_side_means_no_row(client, workbench_on):
    """양쪽 다 발송 기록이 없으면 **그 줄이 없다**."""
    _login(client)
    link = _collected(order_no="N-WB-NOSEND", product="붙박이장", amount=100000)

    pane = _pane_html(client, link.id)

    assert "wb-sendline" not in pane, "발송 기록이 없는데 줄이 났다"
    assert "발송 시각 없음" not in pane


def test_our_record_without_naver_is_a_visible_gap(client, workbench_on):
    """우리는 보냈다는데 네이버가 침묵하면 **어긋남이 화면에 뜬다** — 이것이 이 줄의 값어치다."""
    _login(client)
    link = _collected(order_no="N-WB-GAP", product="붙박이장", amount=100000)
    # 워커가 남기는 표식은 UTC naive isoformat 이다(2026-08-25 05:03 UTC = 14:03 KST).
    _mark_dispatched(link.id, "2026-08-25T05:03:00")

    pane = _pane_html(client, link.id)

    assert "wb-sendline" in pane, "우리 기록이 있는데 발송 줄이 없다"
    assert "발송처리 2026-08-25 14:03" in pane, "우리 기록 시각이 KST 로 안 보인다"
    assert "어긋남" in pane, "한쪽만 기록이 있는데 화면이 조용하다"
    assert "발송 시각 없음" in pane, "네이버 쪽이 침묵한다는 사실을 말하지 않았다"


def test_both_sides_recorded_is_not_flagged_as_a_gap(client, workbench_on):
    """양쪽 다 기록이 있으면 어긋남이 아니다 — 상시 켜진 경고는 아무도 안 읽는다."""
    _login(client)
    link = _collected(order_no="N-WB-BOTH", product="붙박이장", amount=100000)
    _patch(link, delivery={"deliveryStatus": "NOT_TRACKING",
                           "sendDate": "2026-08-25T14:03:00.000+09:00"})
    _mark_dispatched(link.id, "2026-08-25T05:03:00")

    pane = _pane_html(client, link.id)

    assert "wb-sendline" in pane
    assert "어긋남" not in pane, "정상인 집에 경고가 떴다"


def test_naver_only_send_is_shown_but_not_alarmed(client, workbench_on):
    """네이버에만 발송 기록이 있는 집은 **사실만 보이고 경고는 없다**.

    2026-08-26 스테이징 실데이터가 만든 단언이다: 발송 줄 44건 중 41건이 이 방향이었고
    (우리 쪽만 있는 진짜 사고는 0건), 전부 경고가 붙어 있었다. 그 방향은 사고가 아니라
    **판매자센터에서 직접 나간 발송**이라, 경고로 치면 93% 가 상시 경고가 되어 진짜
    어긋남을 덮는다. 두 열은 그대로 나란히 있으니 사실 자체는 사라지지 않는다.
    """
    _login(client)
    link = _collected(order_no="N-WB-NAVERONLY", product="붙박이장", amount=100000)
    _patch(link, delivery={"deliveryStatus": "NOT_TRACKING",
                           "sendDate": "2026-08-25T14:03:00.000+09:00"})

    pane = _pane_html(client, link.id)

    assert "wb-sendline" in pane, "네이버가 발송을 말하는데 줄이 없다"
    assert "발송처리 2026-08-25 14:03" in pane, "네이버 쪽 시각이 화면에 닿지 않았다"
    assert "아직 없음" in pane, "우리 쪽이 비어 있다는 사실을 말하지 않았다"
    assert "어긋남" not in pane, "판매자센터 직접 발송에 경고가 붙었다(41/44 상시 경고)"


# --------------------------------------------------------------------------- #
# F-3 — 부분취소 잔여 (회귀 위험이 가장 큰 자리)
# --------------------------------------------------------------------------- #

def test_non_partial_row_looks_exactly_like_today(client, workbench_on):
    """부분취소가 **아닌** 행은 지금 화면 그대로다.

    ``remain*``/``initial*`` 는 281/281 전 건에 온다. 존재 여부로 판정하면 **모든 행이**
    부분취소로 보인다 — 그게 이 필드의 함정이고, 이 단언이 그 함정을 막는 자물쇠다.
    """
    _login(client)
    link = _collected(order_no="N-WB-WHOLE", product="붙박이장", amount=100000)
    _patch(link, product_order={"quantity": 3,
                                "initialQuantity": 3, "remainQuantity": 3,
                                "initialPaymentAmount": 100000,
                                "remainPaymentAmount": 100000})

    table = _product_table(_pane_html(client, link.id))

    assert "wb-cmp__remain" not in table, "부분취소가 아닌 행에 잔여 줄이 붙었다"
    assert "남은" not in table
    # 지금 화면이 말하던 값은 그대로다 — 수량·금액·제품이 전부 제자리에 있다.
    assert "붙박이장" in table
    assert "100,000" in table
    assert "3" in table


def test_partial_row_shows_what_is_left(client, workbench_on):
    """부분취소인 행만 **남은 값**이 함께 보인다.

    표에 찍히는 수량·금액은 네이버 ``quantity``·``totalPaymentAmount`` 라 클레임이 걸려도
    안 줄어든다 — 즉 이미 **원래 값**이다. 그 옆에 "원래 3"을 또 놓으면 같은 숫자를 두 번
    말하는 셈이라, 여기서 덧붙일 새 사실은 남은 값 하나뿐이다.
    """
    _login(client)
    link = _collected(order_no="N-WB-PART", product="붙박이장", amount=120000)
    _patch(link, product_order={"quantity": 3, "totalPaymentAmount": 120000,
                                "initialQuantity": 3, "remainQuantity": 1,
                                "initialPaymentAmount": 120000,
                                "remainPaymentAmount": 40000})

    table = _product_table(_pane_html(client, link.id))

    assert "wb-cmp__remain" in table, "부분취소 행인데 남은 값이 없다"
    assert "남은 1" in table, "남은 수량이 화면에 닿지 않았다"
    assert "남은 40,000" in table, "남은 금액이 화면에 닿지 않았다"


def test_fully_canceled_row_is_not_called_partial(client, workbench_on):
    """**전부취소된 행에는 잔여 줄이 없다** — 2026-08-26 실데이터가 만든 자물쇠.

    스테이징 100건에서 "부분취소"로 잔여 줄이 붙던 18건이 전부 ``remain == 0`` 인
    전부취소·전부반품이었고, 붙은 숫자는 바로 위에 찍힌 값과 **같은 숫자**였다.
    """
    _login(client)
    link = _collected(order_no="N-WB-FULLCANCEL", product="붙박이장", amount=1303600)
    _patch(link, product_order={"quantity": 14, "totalPaymentAmount": 1303600,
                                "initialQuantity": 14, "remainQuantity": 0,
                                "initialPaymentAmount": 1303600,
                                "remainPaymentAmount": 0})

    table = _product_table(_pane_html(client, link.id))

    assert "wb-cmp__remain" not in table, "전부취소를 부분취소라고 불렀다"
    assert "남은" not in table


def test_amount_only_partial_cancel_does_not_fake_a_quantity_change(client, workbench_on):
    """금액만 깎인 부분취소는 **금액 줄만** 낸다 — 수량은 안 바뀌었으니 할 말이 없다."""
    _login(client)
    link = _collected(order_no="N-WB-PART-AMT", product="붙박이장", amount=100000)
    _patch(link, product_order={"quantity": 2, "totalPaymentAmount": 100000,
                                "initialQuantity": 2, "remainQuantity": 2,
                                "initialPaymentAmount": 100000,
                                "remainPaymentAmount": 90000})

    table = _product_table(_pane_html(client, link.id))

    assert "남은 90,000" in table
    assert "남은 2" not in table, "안 바뀐 수량에 잔여를 붙였다"


# --------------------------------------------------------------------------- #
# 스타일은 전용 CSS 에만 (인라인 금지 규칙)
# --------------------------------------------------------------------------- #

def test_new_styles_live_in_the_workbench_css():
    """새 요소 3종의 스타일이 전용 CSS 에 있다 — 인라인 style 로 새지 않았다."""
    css = CSS_PATH.read_text(encoding="utf-8")

    for selector in (".wb-claim-reason", ".wb-sendline__gap", ".wb-cmp__remain"):
        assert selector in css, f"{selector} 스타일이 없다"

    markup = PANE_TEMPLATE_PATH.read_text(encoding="utf-8")
    for needle in ("wb-claim-reason", "wb-sendline", "wb-cmp__remain"):
        assert needle in markup, f"{needle} 마크업이 없다"
    assert 'style="' not in markup, "pane 템플릿에 인라인 스타일이 들어왔다"
