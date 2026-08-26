"""T4 — 집 1건을 지목해 네이버에서 다시 읽는다(읽기 전용) 계약.

고정하는 계약:

* **새 불가역 호출 0개.** 발주확인·발송처리·취소는 이 경로에서 절대 나가지 않는다.
* `refresh_claims` 를 **한 줄도 안 고치고** 재사용한다 — 알림 묶기·자기취소 억제·중복
  억제·스냅샷/발주상태/묶음키 갱신이 전부 그대로 따라온다.
* 대상은 **집 전체**다. 집 판정은 `fulfillment.links_of_group`(발송처리와 같은 SSOT)를
  쓴다 — 여기서 다시 짜면 화면이 가른 집과 다시 읽는 대상이 어긋난다(분할배송 사고).
* 네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 계약). web 은 enqueue 만 한다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import refresh_household
from models import ExternalOrderLink

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _detail(external_id: str, *, order_no: str, tel: str = "010-3333-4444",
            claim: str = "") -> dict:
    product_order = {
        "productOrderId": external_id,
        "productOrderStatus": "PAYED",
        "productName": "붙박이장",
        "totalPaymentAmount": 500000,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    return {"order": {"orderId": order_no, "ordererName": "김주문"},
            "productOrder": product_order}


def _link(*, order_no: str, tel: str = "010-3333-4444",
          external_id: str = "") -> ExternalOrderLink:
    external_id = external_id or f"po-{_uid()}"
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             external_order_no=order_no, sync_status="COLLECTED",
                             raw_snapshot=_detail(external_id, order_no=order_no, tel=tel))
    db_session.add(link)
    db_session.commit()
    return link


class ReadOnlyClient:
    """상세 조회만 허용하는 가짜 클라이언트.

    쓰기 경로가 호출되면 **터진다** — "새 불가역 호출 0개"를 말이 아니라 코드로 잠근다.
    """

    def __init__(self) -> None:
        self.asked: list[list[str]] = []

    def get_product_orders(self, ids):
        self.asked.append(list(ids))
        return [_detail(str(i), order_no="N-1") for i in ids]

    def _forbidden(self, *args, **kwargs):
        raise AssertionError("다시 읽기는 네이버에 아무것도 쓰지 않는다")

    confirm_product_orders = _forbidden
    dispatch_product_orders = _forbidden
    cancel_product_order = _forbidden


def test_refresh_household_asks_for_every_link_in_the_house(app):
    """집 안의 상품주문을 **전부** 다시 읽는다(세부옵션이 빠지면 화면이 반만 최신)."""
    order_no = f"N-{_uid()}"
    house = [_link(order_no=order_no) for _ in range(3)]
    client = ReadOnlyClient()

    result = refresh_household(db_session, client=client, link_id=int(house[0].id))

    assert len(client.asked) == 1
    assert sorted(client.asked[0]) == sorted(str(link.external_id) for link in house)
    assert result["targets"] == 3


def test_refresh_household_does_not_cross_into_another_house(app):
    """같은 주문번호라도 수취인이 다르면 다른 집이다(분할배송 — 남의 집을 건드리지 않는다)."""
    order_no = f"N-{_uid()}"
    mine = _link(order_no=order_no, tel="010-1111-1111")
    other = _link(order_no=order_no, tel="010-2222-2222")
    client = ReadOnlyClient()

    refresh_household(db_session, client=client, link_id=int(mine.id))

    assert client.asked[0] == [str(mine.external_id)]
    assert str(other.external_id) not in client.asked[0]


def test_refresh_household_without_order_no_touches_only_that_link(app):
    """주문번호가 없는 옛 수집분은 자기 자신만 다시 읽는다."""
    link = ExternalOrderLink(channel="NAVER", external_id=f"po-{_uid()}",
                             sync_status="COLLECTED",
                             raw_snapshot=_detail("po-x", order_no=""))
    db_session.add(link)
    db_session.commit()
    client = ReadOnlyClient()

    result = refresh_household(db_session, client=client, link_id=int(link.id))

    assert client.asked[0] == [str(link.external_id)]
    assert result["targets"] == 1


def test_refresh_household_raises_for_unknown_link(app):
    """없는 링크를 지목하면 **네이버를 부르지 않고** 실패한다."""
    from foms.services.integrations.naver_commerce.fulfillment import FulfillmentError

    client = ReadOnlyClient()
    with pytest.raises(FulfillmentError):
        refresh_household(db_session, client=client, link_id=999_999_999)
    assert client.asked == []


def test_refresh_household_updates_snapshot_through_refresh_claims(app):
    """`refresh_claims` 재사용의 값어치 — 스냅샷·클레임 반영이 그대로 따라온다."""
    order_no = f"N-{_uid()}"
    link = _link(order_no=order_no)
    external_id = str(link.external_id)

    class ClaimClient(ReadOnlyClient):
        def get_product_orders(self, ids):
            self.asked.append(list(ids))
            return [_detail(external_id, order_no=order_no, claim="RETURN_REQUEST")]

    result = refresh_household(db_session, client=ClaimClient(), link_id=int(link.id))

    # `refresh_claims` 는 커밋하지 않는다(커밋은 호출자 몫) — 여기서 커밋해야 DB 에 남는다.
    db_session.commit()
    db_session.refresh(link)
    assert result["refreshed"] == 1
    assert result["claimed"] == 1
    assert link.raw_snapshot["productOrder"]["claimStatus"] == "RETURN_REQUEST"


# ------------------------------------------------- 큐 출구 (web 은 enqueue 만 한다)

def test_enqueue_naver_refresh_returns_false_without_queue(monkeypatch):
    """큐가 없으면 **조용히 성공한 척하지 않는다** — 화면이 사실을 말할 수 있어야 한다."""
    from foms.services.jobs import queue as jobs_queue

    monkeypatch.setattr(jobs_queue, "get_rq_queue", lambda: None)
    assert jobs_queue.enqueue_naver_refresh(1, 2) is False


def test_enqueue_naver_refresh_targets_the_worker_task(monkeypatch):
    """web 에서 네이버를 직접 부르지 않는다 — WORKER 태스크 경로로만 나간다(호출 IP 계약)."""
    from foms.services.jobs import queue as jobs_queue

    calls: list[tuple] = []

    class FakeQueue:
        def enqueue(self, path, *args, **kwargs):
            calls.append((path, args, kwargs))

    monkeypatch.setattr(jobs_queue, "get_rq_queue", lambda: FakeQueue())
    assert jobs_queue.enqueue_naver_refresh(77, 5) is True

    path, args, _kwargs = calls[0]
    assert path.endswith(".run_naver_refresh_task")
    assert args == (77, 5)
