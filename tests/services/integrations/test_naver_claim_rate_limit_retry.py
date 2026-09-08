"""불가역 클레임 호출의 429 한정 1회 재전송 계약 (2026-09-08).

**왜 생겼나.** 담당자가 반품 승인을 눌렀는데 실패했다(주문 2026090362157171 · 상품주문
2026090341528051, 2026-09-08 15:26)::

    HTTP 429 GW.RATE_LIMIT {"message":"요청이 많아 서비스를 일시적으로 사용할 수 없습니다."}

게이트웨이 한도는 2 RPS 고정이다. 그런데 취소·반품 5종은 ``retry=False`` 라 한 번 걸리면
그대로 실패로 남고, 담당자가 그 주문을 다시 열어 다시 눌러야 했다.

**왜 429 만 예외인가.** ``retry=False`` 의 근거는 "타임아웃은 '안 나갔다'가 아니다" 였다 —
네이버가 이미 환불을 처리했는데 응답만 못 받은 갈래가 있어 맹목 재전송이 곧 중복 환불이다.
**429 에는 그 갈래가 없다.** 게이트웨이가 한도를 넘긴 요청을 **본체에 넘기기 전에** 끊은
것이라 클레임이 만들어졌을 수가 없다. 그래서 이것만 되돌릴 수 있는 실패다.

**이 파일이 못박는 것.**

1. 429 를 맞은 불가역 호출은 1초 쉬고 **한 번** 다시 보낸다(그 뒤 200 이면 성공이다).
2. **딱 한 번**이다. 두 번째도 429 면 그대로 올린다 — 창이 안 비었다는 뜻이라 더 두들기면
   한도만 더 먹는다.
3. **음성 대조군**: 500 은 예전 그대로 재전송하지 않는다. 이 줄이 없으면 "429 가 된다"만
   보고 불가역 계약이 통째로 열린 것을 못 잡는다 — 그쪽은 중복 환불이 난다.
4. 되돌릴 수 있는 읽기 호출(``retry=True``)의 429 백오프는 건드리지 않는다.
"""

from __future__ import annotations

import pytest

from foms.services.integrations.naver_commerce.client import (
    RATE_LIMIT_RETRY_DELAY_SECONDS,
    NaverCommerceHTTPError,
)
from tests.services.integrations.test_naver_commerce_client import (
    FakeResponse,
    TOKEN_PATH,
    make_client,
    token_response,
)

PRODUCT_ORDER_ID = "2026090341528051"
RETURN_APPROVE_PATH = (
    f"/v1/pay-order/seller/product-orders/{PRODUCT_ORDER_ID}/claim/return/approve"
)
CANCEL_APPROVE_PATH = (
    f"/v1/pay-order/seller/product-orders/{PRODUCT_ORDER_ID}/claim/cancel/approve"
)

#: 담당자가 실제로 받은 본문(2026-09-08 15:26).
GW_RATE_LIMIT_BODY = (
    '{"code":"GW.RATE_LIMIT","message":"요청이 많아 서비스를 일시적으로 사용할 수 '
    '없습니다.","timestamp":"2026-09-08T15:27:02.770+09:00"}'
)


def test_return_approve_retries_once_after_a_rate_limit_and_succeeds():
    """429 → 1초 쉬고 한 번 더 → 200. 담당자가 다시 누르지 않아도 된다."""
    client, transport, slept = make_client({
        TOKEN_PATH: [token_response()],
        RETURN_APPROVE_PATH: [
            FakeResponse(429, text=GW_RATE_LIMIT_BODY),
            FakeResponse(200, {"data": {"productOrderId": PRODUCT_ORDER_ID}}),
        ],
    })

    result = client.approve_return_product_order(PRODUCT_ORDER_ID)

    assert result == {"data": {"productOrderId": PRODUCT_ORDER_ID}}
    assert len(transport.calls_to(RETURN_APPROVE_PATH)) == 2, "재전송하지 않았다"
    assert slept == [RATE_LIMIT_RETRY_DELAY_SECONDS], (
        "2 RPS 창 하나(1초)를 비우고 보내야 한다")


def test_rate_limit_retry_happens_exactly_once():
    """두 번째도 429 면 그대로 올린다 — 창이 안 비었으면 더 두들기지 않는다."""
    client, transport, slept = make_client({
        TOKEN_PATH: [token_response()],
        RETURN_APPROVE_PATH: [FakeResponse(429, text=GW_RATE_LIMIT_BODY)],
    })

    with pytest.raises(NaverCommerceHTTPError) as exc:
        client.approve_return_product_order(PRODUCT_ORDER_ID)

    assert exc.value.status == 429
    assert len(transport.calls_to(RETURN_APPROVE_PATH)) == 2, "첫 시도 + 재전송 1회여야 한다"
    assert slept == [RATE_LIMIT_RETRY_DELAY_SECONDS]


def test_cancel_approve_gets_the_same_single_retry():
    """취소 승인도 같은 등급이다 — 규율이 두 갈래로 갈리지 않는다."""
    client, transport, slept = make_client({
        TOKEN_PATH: [token_response()],
        CANCEL_APPROVE_PATH: [
            FakeResponse(429, text=GW_RATE_LIMIT_BODY),
            FakeResponse(200, {"data": {}}),
        ],
    })

    client.approve_cancel_product_order(PRODUCT_ORDER_ID)

    assert len(transport.calls_to(CANCEL_APPROVE_PATH)) == 2
    assert slept == [RATE_LIMIT_RETRY_DELAY_SECONDS]


def test_server_error_on_an_irreversible_call_is_still_never_retried():
    """음성 대조군 — 500 은 예전 그대로 **한 번도** 다시 보내지 않는다.

    500·타임아웃은 "네이버가 이미 환불을 처리했는데 응답만 못 받았다" 갈래를 품는다.
    거기서 재전송하면 중복 환불이고, 되돌리는 엔드포인트가 없다. 이 테스트가 빨개지면
    429 예외를 뚫다가 불가역 계약 전체가 열린 것이다.
    """
    client, transport, slept = make_client({
        TOKEN_PATH: [token_response()],
        RETURN_APPROVE_PATH: [
            FakeResponse(500, text="boom"),
            FakeResponse(200, {"data": {}}),
        ],
    })

    with pytest.raises(NaverCommerceHTTPError) as exc:
        client.approve_return_product_order(PRODUCT_ORDER_ID)

    assert exc.value.status == 500
    assert len(transport.calls_to(RETURN_APPROVE_PATH)) == 1, "불가역 호출이 500 에 재전송됐다"
    assert slept == []


def test_reading_calls_keep_their_exponential_backoff():
    """음성 대조군 — 되돌릴 수 있는 읽기 호출의 429 백오프는 그대로다.

    새 갈래가 ``retry=True`` 경로까지 먹으면 읽기 재시도 횟수가 조용히 하나씩 늘어난다.
    """
    from datetime import datetime, timedelta

    from foms.services.integrations.naver_commerce.client import KST
    from tests.services.integrations.test_naver_commerce_client import CHANGED_PATH

    client, transport, slept = make_client({
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [FakeResponse(429, text="too many")],
    }, max_retries=3)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)

    with pytest.raises(NaverCommerceHTTPError):
        client.get_last_changed_statuses(start, start + timedelta(hours=1))

    assert slept == [1.0, 2.0, 4.0], "읽기 호출의 지수 백오프가 바뀌었다"
    assert len(transport.calls_to(CHANGED_PATH)) == 4
