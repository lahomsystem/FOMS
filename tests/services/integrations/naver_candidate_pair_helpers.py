"""네이버 붙이기 후보 **쌍 판정** 계약 테스트의 공용 픽스처·헬퍼.

테스트 두 파일(``test_naver_candidate_pair_signal`` = 판정·문구,
``test_naver_candidate_pair_render`` = 렌더·버튼·표 전수)이 이 한 벌을 쓴다.
한 파일에 다 두면 500줄 파일 상한(``tests/harness/test_file_size_ratchet``)에
걸리는데, 헬퍼를 복사해 나누면 두 파일의 픽스처가 조용히 갈린다 —
그러면 같은 상황을 두 파일이 다르게 재현한다.

``test_`` 로 시작하지 않으므로 pytest 가 수집하지 않는다.
"""

from __future__ import annotations

import re

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.integrations.naver_commerce.order_candidates import (
    find_order_candidates,
    recommended_relation,
    search_orders_for_attach,
)
from foms.services.integrations.naver_commerce.repay_reconcile import (
    attach_reconcile_plans,
)
from models import ExternalOrderLink, Order, User

TRIAGE_PATH = "/admin/naver-ingest/triage"
SEARCH_PATH = "/admin/naver-ingest/{link_id}/order-search"

#: ②열 신호 문구의 두 낱말. **판정 축이 아니라 표시 축**이다 — 화면이 실제로 그 말을
#: 적는지(그리고 반대말을 안 적는지)를 보는 음성 대조군에만 쓴다.
REPAY_TEXT = "재결제 신호"
ADDON_TEXT = "추가결제 신호"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다 — 후보 표는 이 게이트 안에서만 산다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    """관리자 1명으로 로그인한다(후보 표는 개인정보를 연다)."""
    user = User(username=f"wbpair_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, tel: str, name: str = "쌍판정고객") -> int:
    """후보로 잡힐 기존 ERP 주문 1건 — **id 를 돌려준다**.

    요청이 끝나면 세션이 걷히므로(``db_session.remove``) ORM 인스턴스는 detach 된다.
    요청 뒤에도 쓰는 값은 처음부터 정수로 들고 다닌다.
    """
    order = Order(received_date="2026-09-01", customer_name=name, phone=tel,
                  erp_phone_digits=tel.replace("-", ""),
                  address="경기 성남 분당 백현로 206 410동 1203호",
                  product="붙박이장", status="RECEIVED", payment_amount=0)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _link(*, order_no: str, tel: str, amount: int, claim: str = "",
          order_id: int | None = None, name: str = "쌍판정고객") -> ExternalOrderLink:
    """수집 링크 1건. ``order_id`` 를 주면 그 주문에 이미 붙은 **후보 쪽 수집분**이 된다.

    ``claim`` 은 상품주문 단위 ``claimStatus`` 원문이다 — 집계는 ``aggregate_claim``(SSOT)
    이 하므로 여기서 코드를 손으로 만들지 않는다.
    """
    external_id = f"PO-PAIR-{_uid()}"
    product_order = {
        "productOrderId": external_id,
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": name, "tel1": tel,
                            "baseAddress": "경기 성남 분당 백현로 206",
                            "detailedAddress": "410동 1203호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererName": name, "ordererTel": tel},
                "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _candidate_row(link: ExternalOrderLink, order_id: int) -> dict:
    """그 후보 1건의 행만 뽑는다(다른 후보와 안 섞이게)."""
    rows = find_order_candidates(db_session, link)
    row = next((item for item in rows if item["order_id"] == order_id), None)
    assert row is not None, f"주문 #{order_id} 가 후보 표에 없다 — 전제가 깨졌다"
    return row


def _pane(client, *, link_id: int) -> str:
    """상세 pane 본문(HTTP). **렌더 결과**로 봐야 화면이 따라온 것을 증명한다."""
    response = client.get(TRIAGE_PATH, query_string={"tab": "work", "link_id": link_id})
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _seek(client, *, link_id: int, query: str) -> str:
    """찾아서 붙이기 결과 조각 본문(HTTP)."""
    response = client.get(SEARCH_PATH.format(link_id=link_id), query_string={"q": query})
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _attach_buttons(body: str) -> list[str]:
    """후보 표의 붙이기 버튼 여는 태그만 잘라 낸다(강조색 확인용)."""
    return re.findall(r"<button[^>]*wb-attach[^>]*>", body)


def _seek_buttons(body: str) -> list[str]:
    """검색 결과 조각의 붙이기 버튼 여는 태그(순서 그대로)."""
    return re.findall(r"<button[^>]*wb-seek-attach[^>]*>", body)


def _button_relation(button: str) -> str:
    """버튼 태그에서 관계 한 낱말을 뽑는다 — 순서 대조용."""
    match = re.search(r'data-relation="([A-Z]+)"', button)
    assert match, f"관계 없는 붙이기 버튼: {button}"
    return match.group(1)


def _reconcile_plans(link: ExternalOrderLink, order_id: int) -> dict:
    """그 후보 행의 정리 계획 — 템플릿이 ``cand.reconcile`` 로 읽는 바로 그 값이다."""
    rows = find_order_candidates(db_session, link)
    attach_reconcile_plans(db_session, rows)
    row = next(item for item in rows if item["order_id"] == order_id)
    return row["reconcile"]

