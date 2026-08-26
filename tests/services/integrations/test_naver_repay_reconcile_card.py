"""재결제 정리 계획 카드 — 화면 계약 (R-3 · 2026-08-25).

**왜 필요한가**: 정리의 값어치는 두 동작이 **한 화면에서 한 번에** 끝나는 데 있다.
서버가 계획을 계산해도 화면이 그것을 안 실으면 담당자는 예전처럼 붙이기만 하고 멈춘다 —
스테이징 실데이터에 그 반쪽 흔적이 4건 남아 있었다.

여기서 못박는 것 넷:

1. 후보가 있으면 후보마다 **접힌 정리 계획 카드**가 함께 온다(관계는 버튼이 정한다).
2. 예약금 안내가 **관계 두 벌**로 실린다 — 재결제는 바꾸고, 추가결제는 더한다.
   숫자는 서버가 렌더한다. 화면이 다시 세지 않는다.
3. **접수 단계에서만** 취소 처리 라디오가 열린다 — 잠긴 후보는 라디오가 `disabled` 다.
4. 살아 있는 옛 결제가 있으면 **판매자센터 링크**로 안내한다(우리가 취소를 걸지 않는다).
"""

from __future__ import annotations

import copy

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, User

TRIAGE_PATH = "/admin/naver-ingest/triage"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:03d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다 — 정리 카드는 이 게이트 안에서만 산다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    user = User(username=f"wbplan_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, tel: str, status: str = "RECEIVED", deposit: int | None = None) -> Order:
    """후보로 잡힐 기존 주문 — 수취인 전화가 일치하면 100점으로 걸린다."""
    structured = {"payment": {"deposit": deposit}} if deposit is not None else {}
    order = Order(received_date="2026-08-01", customer_name="정리고객", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 9 101호",
                  product="붙박이장", status=status, payment_amount=0,
                  structured_data=copy.deepcopy(structured))
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, tel: str, amount: int, claim: str = "",
          order_id: int | None = None) -> ExternalOrderLink:
    """수집 링크 1건. ``order_id`` 를 주면 그 주문에 이미 붙은 옛 집이 된다."""
    external_id = f"PO-PLAN-{_uid()}"
    product_order = {
        "productOrderId": external_id, "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "정리고객", "tel1": tel,
                            "baseAddress": "서울 강남구 9", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel},
                "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _card(body: str, order_id: int) -> str:
    """그 후보의 정리 계획 카드 조각만 잘라 낸다(다른 후보 카드와 안 섞이게)."""
    needle = f'data-plan-for="{order_id}"'
    at = body.find(needle)
    assert at >= 0, f"주문 #{order_id} 의 정리 계획 카드가 없다"
    start = body.rfind("<div", 0, at)
    end = body.find('data-plan-for="', at + len(needle))
    return body[start:end if end > 0 else len(body)]


def _body(client, *, link_id: int) -> str:
    return client.get(TRIAGE_PATH,
                      query_string={"tab": "work", "link_id": link_id}).get_data(as_text=True)


def test_candidate_row_opens_a_plan_card(client, workbench_on):
    """후보 버튼은 바로 붙이지 않는다 — 두 동작을 함께 보여주는 카드를 연다."""
    _login(client)
    order = _order(tel="010-9100-0001")
    link = _link(order_no="N-PLAN-1", tel="010-9100-0001", amount=1_610_780)

    card = _card(_body(client, link_id=int(link.id)), int(order.id))

    assert "재결제로 정리" in _body(client, link_id=int(link.id)), "관계 버튼 문구가 바뀌었다"
    assert 'value="SUCCEED"' in card and 'value="DISCARD"' in card, "갈래 라디오 2개가 있어야 한다"
    assert "wb-plan-run" in card, "정리 실행 버튼이 없다"
    # 카드는 접힌 채로 온다 — 후보를 고르기 전에 계획이 펼쳐져 있으면 어느 후보의
    # 계획인지 화면이 말하지 못한다.
    assert "hidden" in card.split(">")[0]


def test_plan_card_carries_both_deposit_sentences(client, workbench_on):
    """예약금 안내는 관계 두 벌이다 — 재결제는 바꾸고 추가결제는 더한다."""
    _login(client)
    order = _order(tel="010-9100-0002", deposit=500_000)
    link = _link(order_no="N-PLAN-2", tel="010-9100-0002", amount=1_610_780)

    card = _card(_body(client, link_id=int(link.id)), int(order.id))

    assert "1,610,780원" in card, "재결제는 새 금액으로 바꾼다"
    assert "2,110,780원" in card, "추가결제는 기존 예약금 위에 더한다"
    assert "시스템이 넣지 않는다" in card, "자동 반영하지 않는다는 사실을 말해야 한다"


def test_plan_card_locks_discard_after_measure(client, workbench_on):
    """실측 이후 후보는 취소 처리 갈래가 잠긴다 — 서버도 같은 판정으로 거절한다."""
    _login(client)
    order = _order(tel="010-9100-0003", status="MEASURE")
    link = _link(order_no="N-PLAN-3", tel="010-9100-0003", amount=300_000)

    card = _card(_body(client, link_id=int(link.id)), int(order.id))
    discard_input = card[card.find('value="DISCARD"'):][:200]

    assert "disabled" in discard_input, "잠긴 갈래인데 라디오가 열려 있다"
    assert "MEASURE" in card, "왜 잠겼는지를 화면이 말해야 한다"


def test_plan_card_points_to_seller_center_when_the_old_payment_lives(client, workbench_on):
    """살아 있는 옛 결제는 안내만 한다 — 우리가 네이버에 취소를 걸지 않는다."""
    _login(client)
    order = _order(tel="010-9100-0004")
    _link(order_no="N-PLAN-4-OLD", tel="010-9100-0004", amount=1_191_900,
          order_id=int(order.id))
    link = _link(order_no="N-PLAN-4-NEW", tel="010-9100-0004", amount=1_610_780)

    card = _card(_body(client, link_id=int(link.id)), int(order.id))

    assert "살아 있는 옛 결제" in card
    assert "sell.smartstore.naver.com" in card, "판매자센터로 가는 길이 없다"
    assert "N-PLAN-4-OLD" in card, "어느 집이 살아 있는지 말해야 한다"


def test_no_candidates_means_no_plan_card(client, workbench_on):
    """후보가 없으면 카드도 없다 — 빈 상자는 화면만 길게 만든다."""
    _login(client)
    link = _link(order_no="N-PLAN-5", tel="010-9100-0005", amount=100_000)

    body = _body(client, link_id=int(link.id))

    assert "wb-plan__acts" not in body
