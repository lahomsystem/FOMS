"""NVREPAY-06: 출신 표식과 도크 게이트를 가른다 (설계서 2026-08-28 §7).

``structured_data['source']`` 가 뜻 두 개를 지고 있었다 — ① 주문 **출처**(누가 만들었나)
② 네이버 원본 도크 **렌더 게이트**(보여 줄 원본이 있나). 붙이기(``attach_link_to_order``)가
게이트를 켜려고 출처를 덮어썼기 때문에, **예약금 건처럼 ERP 에 직접 등록한 주문**에 재결제를
붙이는 순간 그 주문이 네이버 출신으로 뒤집혔다. 그러면 주문 상세 뱃지가
"네이버 스마트스토어에서 자동 수집된 주문입니다"라고 **거짓을 말한다**.

그렇다고 "그냥 안 찍기"는 오답이다 — 게이트가 없으면 붙이기는 성공했는데 사람이 볼 자리가
없다(2026-08-24 스테이징 실사례: 주문 4485 에 REPAY 6건·1,610,780원이 기록됐는데 화면은
빈손). 그래서 뜻 둘을 키 둘로 갈랐다:

* ``source`` = 출처 전용. 작성자는 ``mapping.build_structured_data`` 하나뿐.
* ``naver_linked``(:data:`LINKED_MARKER_KEY`) = 도크 게이트 전용. 붙이기가 켠다.

이 파일이 고정하는 것:

1. ERP 출신 주문에 붙여도 ``source`` 는 여전히 비어 있다(화면이 거짓말하지 않는다).
2. 그런데도 도크는 렌더된다(붙인 결과를 볼 자리가 있다).
3. 상세 '네이버 수집' 뱃지는 안 뜬다 — 뱃지 뜻은 "자동 수집된 주문"이라 출처 키가 맞다.
4. 네이버가 만든 주문은 종전대로 출처를 갖는다(게이트 분리가 수집 경로를 건드리지 않았다).
5. 폼 저장 한 번에 게이트가 닫히지 않는다 — 2026-08-24 사고의 재발 경로가 정확히 그것이다.

요청은 자기 세션에서 커밋하므로 검증은 항상 **id 로 다시 읽어서** 한다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.erp_orders_structured import (
    _OPERATIONAL_TOP_LEVEL_KEYS,
    _preserve_operational_structured_state,
)
from foms.services.integrations.naver_commerce.constants import (
    LINKED_MARKER_KEY,
    SOURCE_MARKER,
)
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, Order, User

_SEQ = [0]


def _uid() -> str:
    """테스트끼리 external_id·username 이 겹치지 않게 한다."""
    _SEQ[0] += 1
    return str(_SEQ[0])


def _owner() -> User:
    """주문 owner(ERP 접수 담당). ``create_order`` 가 owner 없는 주문을 허용하지 않는다."""
    user = User(username=f"origin_owner_{_uid()}", password=generate_password_hash("pw"),
                role="STAFF", team="CS", name="접수 담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _erp_order() -> int:
    """**ERP 에 직접 등록한 주문** — 예약금 건이 여기 해당한다.

    수집이 만든 주문이 아니므로 ``structured_data`` 에 ``source`` 키가 아예 없다.
    이 파일의 모든 판정이 그 사실 위에 서 있다. ``is_erp_order=True`` 는 ERP 등록 주문의
    실제 모양이고, 편집 페이지가 도크 bootstrap 을 만드는 조건이기도 하다
    (``order_edit_view_context.is_erp_order_record``).
    """
    owner = _owner()
    order = create_order(
        db_session,
        actor_user_id=owner.id, owner_user_id=owner.id,
        order_fields=dict(received_date="2026-08-28", customer_name="예약금 고객",
                          phone="010-4444-5555", address="서울시 송파구 올림픽로 300",
                          product="붙박이장", options="", status="RECEIVED"),
        structured_data={},
        is_erp_order=True,
    )
    db_session.commit()
    return int(order.id)


def _link(*, order_no: str = "N-REPAY") -> int:
    """붙일 수집 링크 1건(아직 어느 주문에도 안 붙어 있다)."""
    external_id = f"PO-ORIGIN-{_uid()}"
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="COLLECTED",
        raw_snapshot={
            "order": {"orderId": order_no, "ordererName": "예약금 고객",
                      "ordererTel": "010-4444-5555"},
            "productOrder": {
                "productOrderId": external_id,
                "productName": "로라 무몰딩 여닫이 30cm",
                "productClass": "조합형옵션상품",
                "totalPaymentAmount": 1610780,
                "quantity": 1,
                "shippingAddress": {"name": "예약금 고객", "tel1": "010-4444-5555",
                                    "baseAddress": "서울시 송파구 올림픽로 300",
                                    "detailedAddress": "101호"},
            },
        },
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def _order_sd(order_id: int) -> dict:
    """요청 뒤 주문의 structured_data 를 다시 읽는다."""
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data or {}


def _attach(auth_client, link_id: int, order_id: int, relation: str = "REPAY"):
    """붙이기 요청 1회(경로는 운영과 같은 HTTP 표면)."""
    response = auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                                json={"order_id": order_id, "relation": relation})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response


# --------------------------------------------------------------------------- #
# NVREPAY-06 — 출처는 안 뒤집힌다
# --------------------------------------------------------------------------- #

def test_attach_to_an_erp_origin_order_leaves_source_empty(auth_client):
    """ERP 출신 주문에 재결제를 붙여도 ``source`` 는 여전히 비어 있다.

    붙이기는 "이 주문에 네이버 결제가 하나 더 붙었다"는 사실만 안다. 그 사실은 **최초
    접수를 누가 받았는지** 를 말해 주지 않는다. 예약금을 전화로 받아 ERP 에 직접 등록한
    주문은 재결제를 아무리 붙여도 네이버 출신이 아니다.
    """
    order_id = _erp_order()
    assert "source" not in _order_sd(order_id), "사전 조건: 출처 없는 ERP 출신 주문"
    link_id = _link()

    _attach(auth_client, link_id, order_id)

    data = _order_sd(order_id)
    assert "source" not in data, "붙이기가 ERP 출신 주문을 네이버 출신으로 뒤집었다"
    assert data.get(LINKED_MARKER_KEY) is True, "게이트가 안 켜졌다 — 결과를 볼 자리가 없다"


def test_attach_to_an_erp_origin_order_still_records_the_money(auth_client):
    """출처를 안 건드려도 돈 기록은 그대로 남는다(게이트만 갈랐다)."""
    order_id = _erp_order()
    link_id = _link()

    _attach(auth_client, link_id, order_id)

    rows = _order_sd(order_id).get("pricing", {}).get("extra_payments")
    assert isinstance(rows, list) and rows, "붙였는데 결제 기록이 비었다"
    assert sum(int(row["amount"]) for row in rows) == 1610780


def test_dock_still_renders_for_an_erp_origin_order(auth_client):
    """출처가 비어 있어도 도크는 뜬다 — 이게 "그냥 안 찍기"가 오답인 이유다.

    붙이기가 기록한 추가결제를 읽는 코드는 이 도크 하나뿐이다. 게이트가 꺼지면 1,610,780원이
    DB 에만 있고 화면에는 없다(2026-08-24 주문 4485 실사례).
    """
    order_id = _erp_order()
    link_id = _link()
    _attach(auth_client, link_id, order_id)

    html = auth_client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert 'id="naver-origin-data"' in html
    assert 'id="erpNaverDockPane"' in html
    assert "erp-naver-dock.js" in html


def test_erp_origin_order_shows_no_intake_badge_after_attach(auth_client):
    """상세 '네이버 수집' 뱃지는 안 뜬다 — 뱃지 뜻이 "자동 수집된 주문"이기 때문이다.

    뱃지는 출처 키를 계속 본다(설계서 §7.2). 게이트 키로 바꾸면 화면이 다시 거짓을 말한다.
    """
    order_id = _erp_order()
    link_id = _link()
    _attach(auth_client, link_id, order_id)

    html = auth_client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert f'data-erp-order-source="{SOURCE_MARKER}"' not in html
    assert "네이버 스마트스토어에서 자동 수집된 주문입니다" not in html


def test_naver_created_order_keeps_its_source(auth_client):
    """수집이 만든 주문은 종전대로 출처를 갖는다(음성 대조군).

    게이트를 가르면서 진짜 출처까지 지워 버리면 대시보드 '담당 미지정' 모집단과 상세 뱃지가
    통째로 죽는다. 작성자 하나(``mapping.build_structured_data``)는 그대로다.
    """
    order_id = _erp_order()
    order = db_session.get(Order, order_id)
    order.structured_data = {"source": SOURCE_MARKER}
    db_session.commit()
    link_id = _link()

    _attach(auth_client, link_id, order_id, relation="ADDON")

    data = _order_sd(order_id)
    assert data.get("source") == SOURCE_MARKER
    assert data.get(LINKED_MARKER_KEY) is True


def test_intake_badge_does_not_claim_automatic_collection(auth_client):
    """뱃지는 **"자동 수집된 주문"이라고 단정하지 않는다**(2026-08-30).

    2026-08-28 이전 붙이기가 ``source`` 를 덮어써서 ERP 직접 등록 주문이 네이버 출신으로
    뒤집힌 과거분이 남아 있고, 소급 구별이 불가능하다(운영 실측 의심 최대 3건). 그래서
    문구를 둘 다 참인 말로 낮췄다 — "수집분이 연결돼 있다". 판정 키(``source``)는 그대로다.
    """
    order_id = _erp_order()
    order = db_session.get(Order, order_id)
    order.structured_data = {"source": SOURCE_MARKER}
    db_session.commit()

    html = auth_client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert f'data-erp-order-source="{SOURCE_MARKER}"' in html, "뱃지 자체는 그대로 뜬다"
    assert "자동 수집된 주문입니다" not in html, "단정 문구는 사라져야 한다"
    assert "수집분이 연결된 주문입니다" in html


def test_attach_is_idempotent_on_the_gate(auth_client):
    """두 번 눌러도 게이트는 하나다(같은 버튼 재전송 방어)."""
    order_id = _erp_order()
    link_id = _link()

    _attach(auth_client, link_id, order_id)
    _attach(auth_client, link_id, order_id)

    data = _order_sd(order_id)
    assert data.get(LINKED_MARKER_KEY) is True
    assert "source" not in data


# --------------------------------------------------------------------------- #
# 폼 저장이 게이트를 닫지 않는다 (2026-08-24 재발 경로)
# --------------------------------------------------------------------------- #

def _form_payload() -> dict:
    """편집 폼이 실제로 보내는 모양 — 채널 키는 아예 없다."""
    return {
        "items": [{"price": 1000}],
        "parties": {"customer": {"name": "예약금 고객"}},
        "site": {},
        "workflow": {},
        "schedule": {},
        "notes": "",
        "flags": {},
        "payment": {},
        "shipment": {},
        "entity_type": "order_structured",
    }


def test_form_save_keeps_the_dock_gate():
    """폼 저장 한 번에 도크가 닫히면 안 된다.

    allowlist 는 들어온 dict 에서 낯선 키를 걷어낼 뿐 빠진 옛 키를 되살리지 않는다.
    보존 목록에 없으면 **주문을 한 번 열어 저장하는 것만으로** 게이트가 조용히 사라진다 —
    ``source`` 가 그렇게 사라졌던 것이 2026-08-24 사고다.
    """
    old = {LINKED_MARKER_KEY: True,
           "pricing": {"extra_payments": [{"amount": 1610780, "relation": "REPAY"}]},
           "items": [{"price": 1000}], "parties": {}, "site": {}, "workflow": {}}
    incoming = _form_payload()

    _preserve_operational_structured_state(old, incoming)

    assert incoming.get(LINKED_MARKER_KEY) is True, "폼 저장 한 번에 도크가 닫혔다"


def test_form_save_does_not_invent_the_gate():
    """원래 없던 주문에 게이트를 만들어 넣지 않는다(근거 없는 도크 금지)."""
    old = {"items": [], "parties": {}}
    incoming = _form_payload()

    _preserve_operational_structured_state(old, incoming)

    assert LINKED_MARKER_KEY not in incoming


def test_preservation_list_uses_the_canonical_gate_key():
    """보존 목록 리터럴이 상수와 어긋나면 게이트가 조용히 사라진다.

    목록은 리터럴 문자열이라 상수 이름이 바뀌어도 아무도 red 로 잡아 주지 않는다.
    ``templates`` 리터럴을 상수에 묶어 둔 ``test_naver_unassigned_badge`` 와 같은 규율이다.
    """
    assert LINKED_MARKER_KEY in _OPERATIONAL_TOP_LEVEL_KEYS
    assert "source" in _OPERATIONAL_TOP_LEVEL_KEYS


@pytest.mark.parametrize("key", ("source", "naver", "pricing", LINKED_MARKER_KEY))
def test_channel_keys_survive_a_form_save(key):
    """채널 키 넷은 폼 저장을 거쳐도 함께 살아남는다(한쪽만 남으면 또 빈손이다)."""
    old = {"source": SOURCE_MARKER, LINKED_MARKER_KEY: True,
           "naver": {"external_order_no": "2026082410074701"},
           "pricing": {"extra_payments": [{"amount": 1610780}]},
           "items": [{"price": 1000}], "parties": {}, "site": {}, "workflow": {}}
    incoming = _form_payload()

    _preserve_operational_structured_state(old, incoming)

    assert incoming[key] == old[key], f"{key} 가 폼 저장 한 번에 사라졌다"
