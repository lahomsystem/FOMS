"""구매확정 건에는 반품 접수를 열지 않는다 (2026-09-22).

네이버는 구매확정(``PURCHASE_DECIDED``) 뒤 반품·취소 API 를 아예 받지 않는다:

* 반품 요청 endpoint 문서 — "발송완료·배송중·배송완료 상태에서 호출" (그 밖은 400).
* 공식 답변(commerce-api Discussions #1618, 커머스API 권현철) — "'취소 요청API',
  '취소 요청 승인API'는 구매확정 이전의 주문에 대해서만 정상 반영이 가능합니다.
  구매확정 후 취소는 '구매자와 협의 후' [판매관리 > 구매확정 내역]에서 취소 처리로
  진행해주셔야합니다."

그런데 화면 술어(``is_return_pending``)는 발송 여부와 우리 멱등 표식만 봐서 **보낼 수 없는
건에 버튼이 열려 있었다.** 담당자가 누르면 네이버가 400 ``주문상태 확인 필요(반품 불가능
주문상태)`` 로 거절했고 그 실패가 워크벤치 실패 띠에 쌓였다(운영 2026090895141851 이가령
4건 전부).

여기서 못박는 것 넷:

1. 구매확정 상품주문은 반품 접수 **대상이 아니다**(``is_return_pending`` False).
2. 사본 컬럼이 안 채워진 옛 행도 **원본 스냅샷으로** 같은 판정을 받는다.
3. 배송완료 건은 그대로 대상이다(음성 대조군) — 가드가 반품 전체를 막으면 안 된다.
4. 서버는 조용히 빈 결과를 돌려주지 않고 **사람 말로 거절한다**.
"""
import pytest

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.fulfillment import (
    FulfillmentError,
    PURCHASE_DECIDED_BLOCK_TEXT,
    is_purchase_decided,
    is_return_pending,
    request_return,
    return_sendable,
)
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


def _link(*, status: str, order_no: str = "N-PD-1", mirror: bool = True,
          tel: str = "010-7200-0001") -> ExternalOrderLink:
    """발송이 끝난 상품주문 1건 — 상품주문상태만 바꿔 가며 쓴다."""
    product_order = {
        "productOrderId": f"PO-PD-{_uid()}",
        "productName": "리라 TV 월플렉스",
        "productOrderStatus": status,
        "totalPaymentAmount": 180_000,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": "경기 화성시 영통로 60", "detailedAddress": "1404호"},
    }
    snapshot = {
        "order": {"orderId": order_no, "ordererTel": tel},
        "productOrder": product_order,
        # 발송은 네이버 원본으로도 참이어야 한다 — 우리 표식 없이 판매자센터에서 나간 건.
        "delivery": {"sendDate": "2026-09-09T16:50:25.446+09:00",
                     "deliveryMethod": "DIRECT_DELIVERY"},
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=product_order["productOrderId"],
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot), sync_status="LINKED",
                             relation="NEW")
    if mirror:
        link.product_order_status = status
    db_session.add(link)
    db_session.commit()
    return link


def test_purchase_decided_link_is_not_a_return_target(app):
    """구매확정 건은 반품 접수 대상이 아니다 — 버튼·모달 건수·서버 todo 가 같이 닫힌다."""
    link = _link(status="PURCHASE_DECIDED")

    assert is_purchase_decided(link) is True
    assert is_return_pending(link) is False
    assert return_sendable(link) is False


def test_snapshot_only_row_is_judged_the_same(app):
    """사본 컬럼이 비어 있어도 원본 스냅샷으로 같은 판정을 받는다(옛 행)."""
    link = _link(status="PURCHASE_DECIDED", order_no="N-PD-2", mirror=False)

    assert link.product_order_status is None
    assert is_purchase_decided(link) is True
    assert is_return_pending(link) is False


def test_delivered_link_is_still_a_return_target(app):
    """배송완료 건은 그대로 반품 대상이다 — 가드가 반품 전체를 막으면 안 된다(음성 대조군)."""
    link = _link(status="DELIVERED", order_no="N-PD-3")

    assert is_purchase_decided(link) is False
    assert is_return_pending(link) is True
    assert return_sendable(link) is True


def test_server_refuses_with_the_next_action(app):
    """서버는 조용히 끝내지 않고 **다음 행동**을 말하며 거절한다."""
    link = _link(status="PURCHASE_DECIDED", order_no="N-PD-4")

    class _NeverCalled:
        def request_return_product_order(self, *args, **kwargs):  # pragma: no cover - 호출되면 실패
            raise AssertionError("구매확정 건에 네이버를 부르면 안 된다")

    with pytest.raises(FulfillmentError) as exc:
        request_return(db_session, client=_NeverCalled(), link_id=int(link.id),
                       reason="INTENT_CHANGED", actor_user_id=1)

    assert "구매확정" in str(exc.value)
    assert "구매확정 내역" in str(exc.value)
    assert str(exc.value) == PURCHASE_DECIDED_BLOCK_TEXT
