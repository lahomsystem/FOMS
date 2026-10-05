"""클레임 호출 사전 간격 조절 계약 (성능 원장 P3-7, 2026-10-05).

**왜 생겼나.** 운영에서 네이버 429 가 2건 났고 그중 1건은 반품 승인 실패였다. 반품 승인·
취소 승인 같은 클레임 호출은 집 하나의 상품주문 여러 건을 돌며 같은 API 를 연달아 부른다
(``fulfillment._approve_return_rows`` 등). 게이트웨이 한도는 앱·API 단위 2 RPS 다.
429 뒤 1회 재전송(``test_naver_claim_rate_limit_retry``)은 사후 복구이고, 여기서 못박는 것은
**보내기 전에** 간격을 벌리는 사전 조절이다.

**이 파일이 못박는 것.**

1. 조절기(:class:`CallSpacer`)는 칸을 예약한다 — 연달아 부르면 0, 0.5, 1.0 초를 기다리고,
   시간이 지나면 다시 0 이다. 잠은 잠금 밖에서 자므로 동시에 들어온 호출은 서로 다른 칸을
   받는다(스레드 50개, 겹치는 칸 0).
2. 클레임 5종은 전부 조절을 받는다. 연달아 세 번 부르면 실제 전송 사이가 0.5초 이상이다.
3. **음성 대조군**: 읽기(상세·변경분·정산)·발주확인·발송처리·토큰 발급은 조절하지 않는다.
   이 줄이 없으면 수집 루프까지 느려진 것을 못 잡는다.
4. 429 재전송은 이미 1초 쉬었으므로 더 기다리지 않는다(기존 계약 ``slept == [1.0]`` 유지).
5. 기본 조절기는 **프로세스 전역 하나**다 — 잡마다 클라이언트를 새로 만들어도 나눠 쓴다.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta

import pytest

from foms.services.integrations.naver_commerce.client import (
    CLAIM_CALL_SPACER,
    CLAIM_CALLS_PER_SECOND,
    RATE_LIMIT_RETRY_DELAY_SECONDS,
    RATE_LIMIT_RPS,
    CallSpacer,
    MemoryTokenCache,
    NaverCommerceClient,
)
from tests.services.integrations.test_naver_commerce_client import (
    CHANGED_PATH,
    CLIENT_ID,
    QUERY_PATH,
    SECRET,
    TOKEN_PATH,
    FakeClock,
    FakeResponse,
    FakeTransport,
    make_client,
    token_response,
)

PID = "2026090341528051"
CLAIM_PATHS = {
    "request_cancel": f"/v1/pay-order/seller/product-orders/{PID}/claim/cancel/request",
    "approve_cancel": f"/v1/pay-order/seller/product-orders/{PID}/claim/cancel/approve",
    "request_return": f"/v1/pay-order/seller/product-orders/{PID}/claim/return/request",
    "approve_return": f"/v1/pay-order/seller/product-orders/{PID}/claim/return/approve",
    "reject_return": f"/v1/pay-order/seller/product-orders/{PID}/claim/return/reject",
}
CLAIM_CALLS = {
    "request_cancel": lambda c: c.request_cancel_product_order(PID, reason="SOLD_OUT"),
    "approve_cancel": lambda c: c.approve_cancel_product_order(PID),
    "request_return": lambda c: c.request_return_product_order(
        PID, reason="INTENT_CHANGED", collect_method="RETURN_INDIVIDUAL"),
    "approve_return": lambda c: c.approve_return_product_order(PID),
    "reject_return": lambda c: c.reject_return_product_order(PID, reason="이미 설치되었습니다."),
}
INTERVAL = 1.0 / CLAIM_CALLS_PER_SECOND


class _TimedTransport(FakeTransport):
    """전송 시각(가짜 시계)을 함께 적는다 — 실제로 나간 간격을 본다."""

    def __init__(self, routes, clock: FakeClock) -> None:
        super().__init__(routes)
        self._clock = clock
        self.sent_at: list[tuple[str, float]] = []

    def request(self, method: str, url: str, **kwargs):
        self.sent_at.append((url, self._clock()))
        return super().request(method, url, **kwargs)


def _timed_client(routes, clock: FakeClock, spacer: CallSpacer | None = None):
    transport = _TimedTransport(routes, clock)
    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        clock.now += seconds

    client = NaverCommerceClient(
        CLIENT_ID, SECRET, transport=transport, token_cache=MemoryTokenCache(),
        sleep=fake_sleep,
        claim_spacer=spacer or CallSpacer(CLAIM_CALLS_PER_SECOND, clock=clock),
    )
    return client, transport, slept


# --- 조절기 단위 ---------------------------------------------------------------------------
def test_rate_matches_the_gateway_limit() -> None:
    assert CLAIM_CALLS_PER_SECOND == RATE_LIMIT_RPS == 2.0
    assert INTERVAL == pytest.approx(0.5)


def test_spacer_reserves_consecutive_slots_and_frees_them_over_time() -> None:
    clock = FakeClock()
    spacer = CallSpacer(2.0, clock=clock)
    assert [spacer.reserve() for _ in range(3)] == [0.0, 0.5, 1.0]
    clock.now = 0.7  # 칸은 0·0.5·1.0 이 잡혔고 다음 빈 칸은 1.5
    assert spacer.reserve() == pytest.approx(0.8)
    clock.now = 10.0  # 한참 지나면 바로 나간다
    assert spacer.reserve() == 0.0
    assert spacer.reserve() == pytest.approx(0.5)


@pytest.mark.parametrize("bad", [0, -1, 0.0])
def test_spacer_rejects_a_non_positive_rate(bad) -> None:
    with pytest.raises(ValueError):
        CallSpacer(bad)


def test_concurrent_reservations_never_share_a_slot() -> None:
    """스레드 50개가 같은 순간에 예약해도 칸이 겹치지 않는다(잠금 안에서는 계산만)."""
    clock = FakeClock()
    spacer = CallSpacer(2.0, clock=clock)
    barrier = threading.Barrier(50)
    delays: list[float] = []
    guard = threading.Lock()

    def worker() -> None:
        barrier.wait()
        value = spacer.reserve()
        with guard:
            delays.append(value)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert sorted(delays) == [i * 0.5 for i in range(50)]


# --- 클라이언트 배선 ------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(CLAIM_CALLS))
def test_every_claim_call_waits_for_its_slot(name) -> None:
    clock = FakeClock()
    client, transport, slept = _timed_client(
        {TOKEN_PATH: [token_response()], CLAIM_PATHS[name]: [FakeResponse(200, {"data": {}})]},
        clock)
    for _ in range(3):
        CLAIM_CALLS[name](client)
    assert slept == [INTERVAL, INTERVAL]
    sent = [at for url, at in transport.sent_at if url.endswith(CLAIM_PATHS[name])]
    assert len(sent) == 3
    assert all(b - a >= INTERVAL for a, b in zip(sent, sent[1:])), sent


def test_household_loop_of_return_approvals_is_spaced() -> None:
    """운영 사고 모양 — 집 하나의 상품주문 3건을 연달아 승인하면 0.5초씩 벌어져 나간다."""
    clock = FakeClock()
    pids = ["2026090341528051", "2026090341528052", "2026090341528053"]
    routes = {TOKEN_PATH: [token_response()]}
    for pid in pids:
        routes[f"/v1/pay-order/seller/product-orders/{pid}/claim/return/approve"] = [
            FakeResponse(200, {"data": {"successProductOrderIds": [pid]}})]
    client, transport, slept = _timed_client(routes, clock)
    for pid in pids:
        client.approve_return_product_order(pid)
    sent = [at for url, at in transport.sent_at if "/claim/" in url]
    assert sent == [0.0, 0.5, 1.0]
    assert slept == [0.5, 0.5]


def test_reads_writes_and_token_issuance_are_never_throttled() -> None:
    """음성 대조군 — 클레임이 아닌 호출은 몇 번을 불러도 기다리지 않는다."""
    confirm = "/v1/pay-order/seller/product-orders/confirm"
    dispatch = "/v1/pay-order/seller/product-orders/dispatch"
    settle = "/v1/pay-settle/settle/daily"
    client, transport, slept = make_client({
        TOKEN_PATH: [token_response()],
        QUERY_PATH: [FakeResponse(200, {"data": []})],
        CHANGED_PATH: [FakeResponse(200, {"data": {"lastChangeStatuses": []}})],
        confirm: [FakeResponse(200, {"data": {}})],
        dispatch: [FakeResponse(200, {"data": {}})],
        settle: [FakeResponse(200, {"elements": [], "pagination": {}})],
    })
    start = datetime(2026, 10, 5, 9, 0)
    for _ in range(3):
        client.get_product_orders(["1", "2"])
        client.get_last_changed_statuses(start, start + timedelta(minutes=5))
        client.confirm_place_orders(["1"])
        client.dispatch_product_orders([{"productOrderId": "1", "deliveryMethod": "DIRECT_DELIVERY"}])
        client.get_settle_daily(date(2026, 10, 1), date(2026, 10, 1))
    assert slept == []
    assert len(transport.calls_to(QUERY_PATH)) == 3


def test_token_issuance_before_the_first_claim_does_not_eat_a_slot() -> None:
    clock = FakeClock()
    client, transport, slept = _timed_client(
        {TOKEN_PATH: [token_response()], CLAIM_PATHS["approve_return"]: [FakeResponse(200, {"data": {}})]},
        clock)
    client.approve_return_product_order(PID)
    assert len(transport.calls_to(TOKEN_PATH)) == 1
    assert slept == []


def test_rate_limit_resend_does_not_wait_twice_but_the_next_claim_still_waits() -> None:
    """429 → 1초 쉬고 재전송(추가 대기 없음) → 그다음 클레임은 재전송 칸 뒤 0.5초."""
    clock = FakeClock()
    client, transport, slept = _timed_client({
        TOKEN_PATH: [token_response()],
        CLAIM_PATHS["approve_return"]: [
            FakeResponse(429, text='{"code":"GW.RATE_LIMIT"}'),
            FakeResponse(200, {"data": {}}),
        ],
    }, clock)
    client.approve_return_product_order(PID)
    assert slept == [RATE_LIMIT_RETRY_DELAY_SECONDS]
    client.approve_return_product_order(PID)
    assert slept == [RATE_LIMIT_RETRY_DELAY_SECONDS, INTERVAL]


def test_two_clients_sharing_a_spacer_share_the_slots() -> None:
    """잡 안에서 클라이언트를 새로 만들어도 같은 조절기를 나눠 쓰면 간격이 이어진다."""
    clock = FakeClock()
    spacer = CallSpacer(CLAIM_CALLS_PER_SECOND, clock=clock)
    routes = {TOKEN_PATH: [token_response()], CLAIM_PATHS["approve_cancel"]: [FakeResponse(200, {"data": {}})]}
    first, _, slept_first = _timed_client(routes, clock, spacer)
    second, _, slept_second = _timed_client(routes, clock, spacer)
    first.approve_cancel_product_order(PID)
    second.approve_cancel_product_order(PID)
    assert slept_first == [] and slept_second == [INTERVAL]


def test_default_spacer_is_one_per_process() -> None:
    a = NaverCommerceClient(CLIENT_ID, SECRET, token_cache=MemoryTokenCache())
    b = NaverCommerceClient(CLIENT_ID, SECRET, token_cache=MemoryTokenCache())
    assert a._claim_spacer is CLAIM_CALL_SPACER is b._claim_spacer
    assert CLAIM_CALL_SPACER.interval == pytest.approx(INTERVAL)
