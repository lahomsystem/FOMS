"""추가결제일 때 원 주문 줄이 하는 말 (2026-09-08 담당자 지적).

**왜 필요한가**: 원 주문 줄은 재결제(REPAY) 하나만 보고 쓰였다. 재결제는 같은 물건 값을
다시 받은 것이라 옛 네이버 결제를 취소·반품해야 맞다. 그런데 **추가결제(ADDON)** 는 원
주문에 덧붙인 결제라 원 주문이 그대로 살아 있어야 하는데, 같은 줄이 그 화면에서도
``이 옛 주문은 네이버에서 취소해야 합니다`` 라고 말했다 — 화면이 담당자에게 멀쩡한 주문을
환불하라고 시킨 것이다(실사례: 주문번호 2026090889759381, 상품주문 4건 882,660원).

여기서 못박는 것 넷:

1. 추가결제 화면은 **취소하라고 말하지 않는다**.
2. 추가결제 화면은 한 줄로 끝난다 — ``추가결제라서 이 주문은 취소하지 않습니다``.
   오래 안 읽었다는 경고도 붙이지 않는다(정리할 대상이 아니라 경고할 것이 없다).
3. 사실(주문번호·건수·금액)과 여는 앵커는 그대로 남는다 — 낱말만 바뀌지 정보가 줄지 않는다.
4. **음성 대조군**: 같은 자리에서 재결제는 예전대로 ``취소해야 합니다`` 라고 말한다.
   (이 줄이 없으면 "추가결제 문구가 뜬다"만 보고 재결제 쪽이 죽은 것을 못 잡는다.)
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

#: 추가결제 화면이 **절대** 말하면 안 되는 문장(원 주문을 죽이라는 지시).
FORBIDDEN_FOR_ADDON = (
    "이 옛 주문은 네이버에서 취소해야 합니다",
    "네이버 옛 주문이 아직 살아 있습니다",
    "그 사이에 고객이 스스로 취소했을 수 있습니다",
)

ADDON_HEAD = "네이버 원 주문"
ADDON_TEXT = "추가결제라서"
REPAY_TEXT = "이 옛 주문은 네이버에서 취소해야 합니다"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:03d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다 — 원 주문 줄은 이 게이트 안에서만 산다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    """워크벤치를 볼 수 있는 관리자로 로그인한다."""
    user = User(username=f"wbaddon_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, tel: str) -> Order:
    """ERP 주문 1건(원 주문과 추가결제가 함께 붙을 자리)."""
    order = Order(received_date="2026-09-01", customer_name="추가결제고객", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 9 101호",
                  product="붙박이장", status="RECEIVED", payment_amount=0,
                  structured_data={})
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, tel: str, amount: int, order_id: int,
          relation: str = "NEW") -> ExternalOrderLink:
    """수집 링크 1건. ``relation`` 이 화면의 낱말을 가른다."""
    external_id = f"PO-ADDON-{_uid()}"
    product_order = {
        "productOrderId": external_id, "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "추가결제고객", "tel1": tel,
                            "baseAddress": "서울 강남구 9", "detailedAddress": "101호"},
    }
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel},
                "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no,
                             raw_snapshot=copy.deepcopy(snapshot),
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED", order_id=order_id,
                             relation=relation)
    db_session.add(link)
    db_session.commit()
    return link


def _origin_block(body: str) -> str:
    """원 주문 줄만 잘라 낸다(다른 블록 문구와 안 섞이게)."""
    needle = 'data-wb-origin='
    at = body.find(needle)
    assert at >= 0, "원 주문 줄이 렌더되지 않았다"
    start = body.rfind("<div", 0, at)
    end = body.find('<div class="wb-cmp-title"', at)
    return body[start:end if end > 0 else len(body)]


def _pane(client, *, link_id: int) -> str:
    return client.get(TRIAGE_PATH,
                      query_string={"tab": "work", "link_id": link_id}).get_data(as_text=True)


def _two_links(*, tel: str, relation: str) -> tuple[Order, ExternalOrderLink]:
    """원 주문 1건 + 그 뒤 결제 1건을 같은 ERP 주문에 붙인다."""
    order = _order(tel=tel)
    _link(order_no=f"N-ADDON-{_uid()}-ORIGIN", tel=tel, amount=882_660,
          order_id=int(order.id))
    later = _link(order_no=f"N-ADDON-{_uid()}-LATER", tel=tel, amount=120_000,
                  order_id=int(order.id), relation=relation)
    return order, later


def test_addon_pane_does_not_tell_us_to_cancel_the_origin(app, client, workbench_on):
    """추가결제 화면은 원 주문을 취소하라고 말하지 않는다."""
    _login(client)
    _order_row, addon = _two_links(tel="010-9300-0001", relation="ADDON")

    block = _origin_block(_pane(client, link_id=int(addon.id)))

    for phrase in FORBIDDEN_FOR_ADDON:
        assert phrase not in block, f"추가결제인데 화면이 '{phrase}' 라고 말한다"
    assert ADDON_HEAD in block, "원 주문을 가리키는 머리말이 없다"
    assert ADDON_TEXT in block
    assert "취소하지 않습니다" in block


def test_addon_pane_keeps_the_facts_and_the_anchor(app, client, workbench_on):
    """낱말만 바뀐다 — 주문번호·건수·금액과 여는 앵커는 그대로다."""
    _login(client)
    _order_row, addon = _two_links(tel="010-9300-0002", relation="ADDON")

    block = _origin_block(_pane(client, link_id=int(addon.id)))

    assert "-ORIGIN" in block, "원 주문번호가 사라졌다"
    assert "882,660" in block, "금액이 사라졌다"
    assert "상품주문 1건" in block
    assert "원 주문 열기" in block, "원 주문으로 가는 앵커가 사라졌다"


def test_repay_pane_still_says_cancel(app, client, workbench_on):
    """음성 대조군 — 재결제는 예전대로 '취소해야 합니다' 라고 말한다."""
    _login(client)
    _order_row, repay = _two_links(tel="010-9300-0003", relation="REPAY")

    block = _origin_block(_pane(client, link_id=int(repay.id)))

    assert REPAY_TEXT in block, "재결제 쪽 문구가 죽었다"
    assert ADDON_TEXT not in block, "재결제 화면에 추가결제 문구가 샜다"
