# -*- coding: utf-8 -*-
"""집 pane 폐기 블록의 **실측 전/후** 한 줄 (2026-09-07).

취소·반품이 들어왔을 때 담당자가 알아야 하는 것은 "돈이 어떻게 되나" 만이 아니다.
**실측을 이미 나갔는가** 가 회수·정산·응대를 전부 가른다. 유령 목록(띠)에 붙인 것과
**같은 문구·같은 클래스**를 집 pane 의 휴지통 블록에도 낸다 — 같은 사실을 두 낱말로
말하면 두 화면이 서로를 반박한다.

여기서 못박는 것 셋:

1. 블록이 그려지면 **항상** 실측 줄이 있다(모르면 "실측일 없음" 이라고 말한다).
2. **판정은 한 글자도 안 바뀐다** — 확정 전 취소는 실측 줄이 붙어도 휴지통이 잠긴 채다.
3. 클레임이 하나도 없는 주문의 pane 에는 블록도 실측 줄도 없다(음성 대조군).
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, User
from tests.services.integrations._markup import is_disabled

PANE_PATH = "/admin/naver-ingest/triage/pane"
DISCARD_BUTTON = "wb-pane-ghost-discard"

# 화면 낱말 — 이 세 개가 사용자 원문이다. 여기서만 적고 단언은 이 상수를 쓴다.
AFTER_TEXT = "실측 후"
BEFORE_TEXT = "실측 전"
NONE_TEXT = "실측일 없음"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    """pane 을 열 사용자. 휴지통 사유 칸은 ADMIN 에게만 뜬다."""
    user = User(username=f"gmeas_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, status: str = "RECEIVED", tel: str, measurement: str | None = None) -> Order:
    """ERP 주문 1건. ``measurement`` 이 있으면 **structured schedule** 에 넣는다.

    운영의 유령 주문은 ERP 주문이고 실측일 정본은 structured schedule 이다 — 싱크
    컬럼(첫 날짜만 담는다)이 아니라 그 경로를 태워야 실제와 같은 것을 잰다.
    """
    structured = {"schedule": {"measurement": {"date": measurement}}} if measurement else None
    order = Order(received_date="2026-08-13", customer_name=f"실측{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 1 101호",
                  product="붙박이장", status=status, payment_amount=0,
                  is_erp_order=True, structured_data=structured)
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, amount: int, order_id: int, tel: str,
          claim: str = "") -> ExternalOrderLink:
    """그 주문에 붙은 네이버 상품주문 1줄."""
    product_order = {
        "productOrderId": f"PO-GM-{_uid()}",
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel}, "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=product_order["productOrderId"],
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED", relation="NEW", order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _pane(client, link_id: int) -> str:
    """집 pane 조각 HTML."""
    response = client.get(f"{PANE_PATH}?link_id={link_id}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_data(as_text=True)


def _shift(days: int) -> str:
    """오늘 기준 상대 날짜(YYYY-MM-DD). 고정 날짜를 쓰면 테스트가 썩는다."""
    return (get_today_kst() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")


def test_pane_says_after_measure_for_a_past_measurement_date(app, client, workbench_on):
    """실측일이 지난 주문 — 확정 취소 pane 에 '실측 후' 와 그 날짜(MM-DD)가 나온다."""
    _login(client)
    tel = "010-7300-0001"
    past = _shift(-5)
    order = _order(tel=tel, measurement=past)
    link = _link(order_no="N-GM-1", amount=667_600, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert AFTER_TEXT in body, "실측을 이미 나간 주문인데 pane 이 말하지 않는다"
    assert past[5:] in body, "실측 후라고만 하고 언제였는지 안 적었다"
    assert "wb-ghost__meas" in body, "유령 목록과 다른 클래스를 썼다"


def test_pane_says_before_measure_and_keeps_the_lock(app, client, workbench_on):
    """실측일이 미래 — '실측 전' 이 붙어도 **확정 전 취소는 그대로 잠겨 있다**.

    표시 축 추가일 뿐이라는 것을 여기서 못박는다: 휴지통이 열리면 취소가 거부됐을 때
    살아 있어야 할 주문이 휴지통에 있다.
    """
    _login(client)
    tel = "010-7300-0002"
    future = _shift(5)
    order = _order(tel=tel, measurement=future)
    link = _link(order_no="N-GM-2", amount=558_400, claim="CANCEL_REQUEST",
                 order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert BEFORE_TEXT in body
    assert AFTER_TEXT not in body, "미래 실측일인데 이미 나갔다고 말했다"
    assert is_disabled(body, DISCARD_BUTTON), "실측 줄을 넣으면서 판정이 열렸다"
    assert "지금은 안 됨" in body


def test_pane_says_it_does_not_know_without_a_measurement_date(app, client, workbench_on):
    """실측일이 없으면 **모른다고 말한다** — 날짜를 지어내지 않는다."""
    _login(client)
    tel = "010-7300-0003"
    order = _order(tel=tel)
    link = _link(order_no="N-GM-3", amount=300_000, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert NONE_TEXT in body
    assert AFTER_TEXT not in body and BEFORE_TEXT not in body
    # 실측 줄 안에 날짜가 섞여 나오면 아는 척이다 — 줄 하나만 떼어 본다.
    line = body.split("wb-ghost__meas")[1].split("</div>")[0]
    assert not any(ch.isdigit() for ch in line), f"모른다면서 숫자를 적었다: {line}"


def test_pane_without_any_claim_has_no_measure_line(app, client, workbench_on):
    """음성 대조군 — 클레임이 하나도 없으면 폐기 블록도 실측 줄도 없다.

    실측일이 지난 주문이라도 마찬가지다. 이 줄은 '취소·반품을 어떻게 접느냐' 를 읽는
    자리에만 붙는다 — 모든 pane 에 상시로 서 있으면 그 자리는 아무도 안 읽는다.
    """
    _login(client)
    tel = "010-7300-0004"
    order = _order(tel=tel, measurement=_shift(-3))
    link = _link(order_no="N-GM-4", amount=900_000, order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert "wb-ghost__meas" not in body, "클레임이 없는데 실측 줄이 섰다"
    assert AFTER_TEXT not in body
    assert BEFORE_TEXT not in body
    assert NONE_TEXT not in body
    assert DISCARD_BUTTON not in body, "클레임이 없는데 휴지통 블록이 그려졌다"
