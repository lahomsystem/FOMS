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


def _link(*, claim: dict | None = None, block: str = "return") -> ExternalOrderLink:
    """수집만 된 링크 1건. ``claim`` 을 주면 ``block`` 이름으로 싣는다.

    2026-08-27 정정: 기본이 ``cancel`` 이었다. 그래서 **양성 픽스처가 곧 결함**이었고
    (취소 블록을 반품 축으로 읽는 것), 음성 사례는 "클레임 아예 없음" 하나뿐이라
    취소만 된 건에 반품 줄이 뜨는 것을 아무도 못 봤다. 기본을 ``return`` 으로 바꾸고
    ``cancel`` 은 **음성 사례를 만들 때** 명시적으로 넘긴다.
    """
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
        snapshot[block] = claim
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
    # 우편번호도 같이 낸다 — 배차·경로를 잡는 값이고 원본에 이미 실려 온다.
    assert "우편번호 13529" in body
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


def test_cancel_only_order_shows_no_return_block(app, client, workbench_on):
    """**취소만 된 건도** 반품 줄을 내지 않는다 (2026-08-27 CEO A1).

    지금까지 음성 사례가 "클레임 아예 없음" 하나뿐이었다. 취소 블록에도 환불 필드가
    실려 오므로, 반품 축이 그것을 읽으면 머리의 배지는 `취소 완료` 인데 몸통은
    `반품 진행` 이라고 말한다 — 스테이징 실데이터 344 링크 중 50건이 그랬다.
    """
    _login(client)
    _link(block="cancel", claim={
        "claimStatus": "CANCEL_DONE",
        "refundExpectedDate": "2026-08-23T00:00:00.000+09:00",
        "refundStandbyStatus": "환불처리완료",
        "refundStandbyReason": "취소 진행중건 존재",
    })
    body = _body(client)
    assert "wb-return" not in body
    assert "반품 진행" not in body


def test_collect_zip_code_is_omitted_when_missing(app, client, workbench_on):
    """우편번호가 없는 회수지는 **그 자리를 아예 안 낸다**(빈 칸·`-` 금지).

    이 줄의 다른 값들과 같은 규율이다 — 라벨만 남겨 두면 화면이 "우편번호가 없다"와
    "우리가 모른다"를 같은 모양으로 말한다.
    """
    _login(client)
    _link(claim={
        "claimStatus": "COLLECTING",
        "collectAddress": {"name": "박회수", "tel1": "010-7777-8888",
                           "baseAddress": "경기 성남시 분당구 2",
                           "detailedAddress": "302동 1503호"},
    })
    body = _body(client)
    assert "경기 성남시 분당구 2 302동 1503호" in body   # 회수지 줄 자체는 뜬다
    assert "우편번호" not in body
