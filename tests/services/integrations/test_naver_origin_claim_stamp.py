"""옛 주문 클레임 도장 — **언제 끝났고 얼마가 돌아갔나** (2026-09-09 P-4).

재결제로 갈아탄 뒤 옛 주문 줄은 `옛 주문 반품 완료 — 고객이 이미 처리해 할 일 없습니다`
까지만 말했다. 담당자가 실제로 확인해야 하는 두 값(확정 시각·환불액)은 판매자센터를
따로 열어야 보였다.

두 값은 이미 수집해 둔 원본에 있다 — 2026-09-09 운영 읽기 전용 조회로 확인했다:

* 확정 시각: 취소 358건 전부 ``cancelCompletedDate``, 반품 166건 전부
  ``returnCompletedDate``. **종류에 따라 한쪽만** 실려 온다.
* 환불액: ``initialPaymentAmount - remainPaymentAmount``. ``totalPaymentAmount`` 로
  재진술하면 **부분 환불**(운영 2건)에서 틀린다. 클레임 없는 1,766건은 두 값이 정확히
  같아 이 뺄셈이 0 이다 — 음성 대조군이 데이터 안에 이미 있다.

이 파일은 그 두 값이 원본에서 나오고(서비스 축), 화면 한 줄로 찍히고(HTTP 축),
**모르는 조각은 안 찍힌다**(음성 대조군)는 것을 문다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import (
    extract_claim_settlement_facts,
    group_key_text,
)
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


def _login(client) -> User:
    user = User(username=f"nvstamp_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order() -> Order:
    order = Order(received_date="2026-08-01", customer_name="도장고객",
                  phone="010-3333-4444", address="서울 강남구 1 101호",
                  product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return order


def _snapshot(*, order_no: str, external_id: str, claim_status: str = "",
              claim_type: str = "", initial: int = 0, remain: int = 0,
              return_done_at: str = "", cancel_done_at: str = "") -> dict:
    """운영 원본과 **같은 모양**의 상품주문 1건.

    금액 두 값은 클레임 유무와 무관하게 늘 실려 온다(운영 2,303행 전부) — 픽스처도
    그렇게 둬야 "값이 없어서 도장이 안 찍혔다"와 "0원이라 안 찍혔다"가 안 섞인다.
    """
    snapshot: dict = {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": external_id, "productName": "붙박이장",
            "totalPaymentAmount": initial,
            "initialPaymentAmount": initial,
            "remainPaymentAmount": remain,
            "claimStatus": claim_status or None,
            "claimType": claim_type or None,
        },
    }
    if return_done_at:
        snapshot["return"] = {"returnCompletedDate": return_done_at}
    if cancel_done_at:
        snapshot["cancel"] = {"cancelCompletedDate": cancel_done_at}
    return snapshot


def _link(*, order_no: str, order_id: int, relation: str, **snap) -> ExternalOrderLink:
    """붙어 있는 수집 링크 1건."""
    external_id = f"PO-STAMP-{_uid()}"
    snapshot = _snapshot(order_no=order_no, external_id=external_id, **snap)
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="LINKED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             relation=relation, order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 서비스 축 — 원본에서 두 값을 뽑는다
# --------------------------------------------------------------------------- #

def test_a_finished_return_carries_its_time_and_its_money():
    """반품 확정본은 ``returnCompletedDate`` 와 환불액을 함께 낸다."""
    facts = extract_claim_settlement_facts(_snapshot(
        order_no="N-1", external_id="PO-1", claim_status="RETURN_DONE",
        claim_type="RETURN", initial=1156500, remain=0,
        return_done_at="2026-09-08T15:27:00.000+09:00"))

    assert facts["completed_at"] == "2026-09-08T15:27:00.000+09:00"
    assert facts["refunded_amount"] == 1156500
    assert facts["known"] is True


def test_a_finished_cancel_reads_its_own_date_field():
    """취소 확정본은 ``cancelCompletedDate`` 를 읽는다 — 반품 필드는 없다.

    두 축을 한 블록 목록으로 합치면 2026-08-27 에 고친 누출(취소 블록의 환불 필드가
    반품 진행으로 샌다)이 되살아난다. 종류마다 자기 필드만 실려 오는 것을 못박는다.
    """
    facts = extract_claim_settlement_facts(_snapshot(
        order_no="N-2", external_id="PO-2", claim_status="CANCEL_DONE",
        claim_type="CANCEL", initial=40000, remain=0,
        cancel_done_at="2026-09-08T10:00:00.000+09:00"))

    assert facts["completed_at"] == "2026-09-08T10:00:00.000+09:00"
    assert facts["refunded_amount"] == 40000


def test_a_partial_refund_is_the_difference_not_the_payment():
    """부분 환불은 **차액**이다 — 결제 금액을 그대로 쓰면 틀린다(운영 2건)."""
    facts = extract_claim_settlement_facts(_snapshot(
        order_no="N-3", external_id="PO-3", claim_status="RETURN_DONE",
        claim_type="RETURN", initial=1000000, remain=400000,
        return_done_at="2026-09-08T15:27:00.000+09:00"))

    assert facts["refunded_amount"] == 600000


def test_a_live_payment_refunds_nothing():
    """음성 대조군 — 클레임 없는 건은 두 값이 같아 환불액이 0 이고 시각이 없다."""
    facts = extract_claim_settlement_facts(_snapshot(
        order_no="N-4", external_id="PO-4", initial=500000, remain=500000))

    assert facts["refunded_amount"] == 0
    assert facts["completed_at"] == ""


def test_we_say_nothing_when_the_snapshot_says_nothing():
    """금액 두 값이 없으면 ``None`` 이다 — 0원이라고 적지 않는다."""
    facts = extract_claim_settlement_facts({"productOrder": {"productOrderId": "PO-5"}})

    assert facts["refunded_amount"] is None
    assert facts["known"] is False


# --------------------------------------------------------------------------- #
# 화면 축 — 옛 주문 줄에 도장이 찍힌다
# --------------------------------------------------------------------------- #

def test_the_old_order_line_stamps_when_and_how_much(client, workbench_on):
    """확정된 옛 주문 줄이 `09-08 15:27 · 환불 1,156,500원` 을 함께 말한다.

    시각은 서울 시각이고 연도는 뗀다(목록 배지·머리줄과 같은 규칙 — 옛 주문은 전부
    올해다). 금액은 세 자리마다 쉼표를 넣는다.
    """
    _login(client)
    order = _order()
    _link(order_no=f"N-STAMP-ORIG-{_uid()}", order_id=int(order.id), relation="NEW",
          claim_status="RETURN_DONE", claim_type="RETURN",
          initial=1156500, remain=0, return_done_at="2026-09-08T15:27:00.000+09:00")
    repay = _link(order_no=f"N-STAMP-REPAY-{_uid()}", order_id=int(order.id),
                  relation="REPAY", initial=1200000, remain=1200000)

    body = client.get(TRIAGE_PATH,
                      query_string={"tab": "work", "link_id": repay.id}
                      ).get_data(as_text=True)

    assert "09-08 15:27 · 환불 1,156,500원" in body, "옛 주문 도장이 안 찍혔다"


def test_an_unfinished_claim_gets_no_stamp(client, workbench_on):
    """음성 대조군 — 아직 확정 전인 옛 주문에는 도장을 안 찍는다.

    확정 전에 시각·금액을 적으면 화면이 아직 안 나간 환불을 확정해 말한다. 같은 화면이
    바로 위에서 "네이버가 아직 확정하지 않았습니다" 라고 말하고 있어 정면으로 부딪힌다.
    """
    _login(client)
    order = _order()
    _link(order_no=f"N-STAMP-PEND-{_uid()}", order_id=int(order.id), relation="NEW",
          claim_status="RETURN_REQUEST", claim_type="RETURN",
          initial=1156500, remain=1156500)
    repay = _link(order_no=f"N-STAMP-PREPAY-{_uid()}", order_id=int(order.id),
                  relation="REPAY", initial=1200000, remain=1200000)

    body = client.get(TRIAGE_PATH,
                      query_string={"tab": "work", "link_id": repay.id}
                      ).get_data(as_text=True)

    assert "환불 1,156,500원" not in body, "확정 전인데 환불액을 확정해 말한다"
    assert "wb-relation__stamp" not in body, body[:0]
