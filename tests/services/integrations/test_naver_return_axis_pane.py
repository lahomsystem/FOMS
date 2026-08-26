"""반품 진행(수거·환불) 축이 워크벤치 화면에 뜨는가 — T8-S0 표시 계약.

추출은 `test_naver_return_axis.py` 가 잠근다. 여기는 **화면이 그 사실을 말하는가**만 본다.

고정하는 계약:

* 값이 없는 건은 **줄 자체를 안 낸다** — 빈 칸이나 `-` 로 채우면 "값이 없다"와
  "우리가 모른다"가 같은 모양이 된다(F-1~F-3 과 같은 규율).
* 회수지는 **우리 차가 가야 할 곳**이라 주소·연락처를 같이 낸다(자사 배송·자사 회수).
* 시각은 사람이 읽는 KST 로 편다. 못 읽는 값은 **원문 그대로** 남긴다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, User

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
    user = User(username=f"wb_admin_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(*, claim: dict | None = None) -> ExternalOrderLink:
    """수집만 된 링크 1건. ``claim`` 을 주면 그대로 ``cancel`` 블록에 싣는다."""
    external_id = f"PO-RA-{_uid()}"
    order_no = f"N-RA-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "김주문"},
        "productOrder": {
            "productOrderId": external_id, "productName": "붙박이장",
            "totalPaymentAmount": 594000, "placeOrderStatus": "OK",
            "claimStatus": (claim or {}).get("claimStatus"),
            "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
        },
    }
    if claim:
        snapshot["cancel"] = claim
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             place_order_status="OK")
    db_session.add(link)
    db_session.commit()
    return link


def _body(client) -> str:
    return client.get(TRIAGE_PATH).get_data(as_text=True)


def test_plain_order_shows_no_return_block(app, client, workbench_on):
    """클레임이 없는 건은 반품 줄을 **한 글자도** 내지 않는다."""
    _login(client)
    _link()
    body = _body(client)
    assert "wb-return" not in body
    assert "반품 진행" not in body


def test_collect_and_refund_facts_are_shown(app, client, workbench_on):
    """수거 완료·환불 예정·대기 사유가 화면에 뜬다(지금까지 판매자센터를 열어야 알았다)."""
    _login(client)
    _link(claim={
        "claimStatus": "COLLECT_DONE",
        "collectCompletedDate": "2026-08-26T14:05:00.000+09:00",
        "refundExpectedDate": "2026-08-28T09:00:00.000+09:00",
        "refundStandbyStatus": "WAIT",
        "refundStandbyReason": "회수 상품 검수 대기",
    })
    body = _body(client)
    assert "반품 진행" in body
    assert "2026-08-26 14:05" in body
    assert "2026-08-28 09:00" in body
    assert "회수 상품 검수 대기" in body


def test_collect_address_is_shown_for_our_own_pickup(app, client, workbench_on):
    """회수지는 **우리 차가 갈 곳**이다 — 주소와 연락처를 같이 낸다."""
    _login(client)
    _link(claim={
        "claimStatus": "COLLECTING",
        "collectAddress": {"name": "박회수", "tel1": "010-7777-8888",
                           "baseAddress": "경기 성남시 분당구 2",
                           "detailedAddress": "302동 1503호", "zipCode": "13529"},
    })
    body = _body(client)
    assert "경기 성남시 분당구 2 302동 1503호" in body
    assert "박회수" in body
    assert "010-7777-8888" in body
    # 회수지만 왔으면 **진행 줄은 안 낸다** — 라벨만 있고 안이 빈 줄이 뜨던 자리다
    # (2026-08-26 CEO 리뷰 A3). 회수지는 자기 줄이 맡는다.
    assert "반품 진행" not in body


def test_collecting_status_label_is_korean_on_screen(app, client, workbench_on):
    """수거중이 배지에 **영문 원문**으로 뜨지 않는다(T8-S0 이 고친 자리)."""
    _login(client)
    _link(claim={"claimStatus": "COLLECTING"})
    body = _body(client)
    assert "수거중" in body
    assert "COLLECTING" not in body
