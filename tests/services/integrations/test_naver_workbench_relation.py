"""워크벤치 관계 축(추가결제·재결제) + 발송처리 분기 계약 테스트.

스펙 `docs/specs/2026-08-22-naver-workbench-relation-and-cancel_SPEC.md` (D1~D4).

**왜 필요한가**: 관계 축 UI 가 옛 화면(`naver_triage.html`)에만 있어서, 게이트를 켠 계정은
추가결제·재결제 업무를 화면에서 아예 할 수 없었다. 라우트·판정 로직은 살아 있었고 화면만
없었다 — 그 자리를 이 파일이 문다.
"""

from __future__ import annotations

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
    return str(_SEQ[0])


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"wbrel_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, name: str = "이수취", address: str = "서울 강남구 1 101호") -> Order:
    """붙일 만한 기존 주문 1건 — 이름+주소 규칙으로 후보에 잡힌다."""
    order = Order(received_date="2026-08-01", customer_name=name, phone="010-3333-4444",
                  address=address, product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return order


def _collected(*, order_no: str, product: str = "붙박이장", amount: int = 100000,
               place_status: str = "OK", relation: str = "", order_id: int | None = None,
               claim_status: str = "") -> ExternalOrderLink:
    """수집 링크 1건. ``relation``/``order_id`` 를 주면 이미 붙은 집이 된다."""
    external_id = f"PO-REL-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": external_id, "productName": product,
            "productOption": "", "totalPaymentAmount": amount,
            "claimStatus": claim_status or None,
            "placeOrderStatus": place_status or None,
            "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
        },
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="LINKED" if order_id else "COLLECTED",
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             place_order_status=place_status or None,
                             relation=relation or None, order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _body(client, **params) -> str:
    return client.get(TRIAGE_PATH, query_string=params).get_data(as_text=True)


# --------------------------------------------------------------------------- #
# T-R1 관계 배지 (D4 — 추가결제·재결제만, 신규는 무배지)
# --------------------------------------------------------------------------- #

def test_queue_row_flags_an_addon_household(client, workbench_on):
    """붙어 있는 집은 큐 줄에서 '추가결제'로 보인다 — 목록만 보고 성격을 안다."""
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-ADDON", relation="ADDON", order_id=int(order.id))

    body = _body(client, tab="work", link_id=link.id)

    assert "추가결제" in body


def test_queue_row_flags_a_repay_household(client, workbench_on):
    """재결제도 마찬가지다 — 라벨이 다르다."""
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-REPAY", relation="REPAY", order_id=int(order.id))

    body = _body(client, tab="work", link_id=link.id)

    assert "재결제" in body


def test_new_household_gets_no_relation_badge(client, workbench_on):
    """신규는 배지를 달지 않는다 — 대부분이 신규라 다 달면 배지가 무의미해진다."""
    _login(client)
    link = _collected(order_no="N-REL-NEW")

    body = _body(client, tab="work", link_id=link.id)

    assert "추가결제" not in body
    assert "재결제" not in body


# --------------------------------------------------------------------------- #
# T-R2 관계 섹션 — 후보·붙이기·되돌리기 (D3)
# --------------------------------------------------------------------------- #

def test_detail_offers_existing_orders_with_attach_buttons(client, workbench_on):
    """후보가 있으면 상세에 '기존 주문' 표와 붙이기 버튼 2종이 뜬다."""
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-CAND")

    body = _body(client, tab="work", link_id=link.id)

    assert "naver-attach-btn" in body, "붙이기 버튼이 있어야 한다"
    assert 'data-relation="ADDON"' in body
    assert 'data-relation="REPAY"' in body
    assert f"#{order.id}" in body, "어느 주문에 붙는지 번호가 보여야 한다"


def test_attach_section_is_absent_without_candidates(client, workbench_on):
    """후보가 없으면 섹션 자체를 내지 않는다 — 빈 상자는 화면만 길게 만든다."""
    _login(client)
    link = _collected(order_no="N-REL-NOCAND")

    body = _body(client, tab="work", link_id=link.id)

    assert "naver-attach-btn" not in body


def test_attached_household_shows_the_order_and_a_way_back(client, workbench_on):
    """붙은 집은 어느 주문에 붙었는지와 되돌리기를 함께 보여준다."""
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-ATT", relation="ADDON", order_id=int(order.id))

    body = _body(client, tab="work", link_id=link.id)

    assert "되돌리기" in body
    assert f"#{order.id}" in body


def test_attached_household_does_not_offer_more_candidates(client, workbench_on):
    """이미 붙었으면 후보를 또 늘어놓지 않는다(두 번 붙이는 사고 방지)."""
    _login(client)
    order = _order()
    _order(name="이수취", address="서울 강남구 1 202호")
    link = _collected(order_no="N-REL-ATT2", relation="ADDON", order_id=int(order.id))

    body = _body(client, tab="work", link_id=link.id)

    assert "naver-attach-btn" not in body


# --------------------------------------------------------------------------- #
# T-R3 발송처리 관계별 분기 (D1·D2)
# --------------------------------------------------------------------------- #

def test_addon_can_close_before_place_confirmation(client, workbench_on):
    """추가결제는 발주확인 전에도 '지금 닫기'가 열린다 — 물건이 따로 나가지 않는다."""
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-ADDON-DISP", relation="ADDON",
                      order_id=int(order.id), place_status="NOT_YET")

    body = _body(client, tab="work", link_id=link.id)

    assert "지금 닫기" in body
    assert 'id="wb-dispatch" disabled' not in body


def test_new_household_stays_locked_before_place_confirmation(client, workbench_on):
    """신규는 그대로다 — 발주확인 전이면 사유 달린 회색 잠금."""
    _login(client)
    link = _collected(order_no="N-REL-NEW-LOCK", place_status="NOT_YET")

    body = _body(client, tab="work", link_id=link.id)

    assert 'id="wb-dispatch" disabled' in body
    assert "지금 닫기" not in body


def test_new_dispatch_modal_warns_about_real_shipment(client, workbench_on):
    """신규 발송처리 모달은 '실제 출고·시공 시점'을 크게 경고한다(D2)."""
    _login(client)
    link = _collected(order_no="N-REL-NEW-WARN", place_status="OK")

    body = _body(client, tab="work", link_id=link.id)

    assert "실제 출고" in body


def test_addon_modal_says_it_closes_the_payment(client, workbench_on):
    """추가결제 모달은 '물건이 따로 나가지 않는다'는 업무 규칙을 문장으로 말한다."""
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-ADDON-MODAL", relation="ADDON",
                      order_id=int(order.id), place_status="NOT_YET")

    body = _body(client, tab="work", link_id=link.id)

    assert "따로 나가지 않" in body
