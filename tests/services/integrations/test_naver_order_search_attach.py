"""T2 — **후보 0건일 때 주문을 찾아서 붙이기** 계약.

원장: `docs/plans/2026-08-31-naver-approve-attach-refresh-ledger.md`.

왜 필요한가
-----------
자동 매칭은 세 축뿐이다(`order_candidates.find_order_candidates`, 180일 창):
수취인 전화 100 · 주문자 전화 80 · 이름+주소 앞부분 60. 그래서 재결제·추가결제가
**다른 이름 · 다른 전화 · 다른 주소**로 들어오면 — 가족이 대신 결제했거나 시공지가
바뀌었거나 새 번호로 샀거나 — 후보가 0건이고, 그러면 붙이기 버튼이 화면에 **아예 없다**.
담당자는 새 주문을 만들고 **옛 주문은 유령이 된다**.

막힌 것은 서버가 아니라 화면이었다: `POST /admin/naver-ingest/<link_id>/attach` 는
후보 목록과 무관하게 `order_id` 를 받는다. 그래서 이 파일이 무는 것은 셋이다.

* **찾기 진입점이 그 자리에 있는가** — 후보 0건에서도(그때가 유일한 경로다)
* **검색이 세 축(이름·전화·주문번호)으로 실제로 찾는가** — 자동 매칭이 못 잡은 주문까지
* **붙인 뒤가 기존 흐름과 같은가** — 목록 밖 주문도 집 전체가 붙고 되돌릴 수 있다
"""

from __future__ import annotations

import re

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.phone_search import normalize_phone_digits
from foms.services.integrations.naver_commerce.order_candidates import (
    SEARCH_LIMIT,
    find_order_candidates,
    search_orders_for_attach,
)
from models import ExternalOrderLink, Order, User

TRIAGE_PATH = "/admin/naver-ingest/triage"
SEARCH_PATH = "/admin/naver-ingest/{link_id}/order-search"
ATTACH_PATH = "/admin/naver-ingest/{link_id}/attach"

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
    user = User(username=f"wbseek_{role.lower()}_{_uid()}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, name: str = "박아버지", phone: str = "010-9999-8888",
           address: str = "인천 부평구 부평대로 1", status: str = "RECEIVED",
           payment: int = 1_000_000, draft: bool = False) -> int:
    """기존 ERP 주문 1건 — **id 를 돌려준다**.

    요청이 끝나면 세션이 걷히므로(``db_session.remove``) ORM 인스턴스는 detach 된다.
    요청 뒤에도 쓰는 값은 처음부터 정수로 들고 다닌다.

    ``erp_phone_digits`` 를 함께 채운다 — 운영 주문은 저장 때 ``sync_erp_flat_columns``
    가 채우는 인덱스 컬럼이고, 전화 검색이 그 컬럼을 탄다(P1-02). 비워 두면 화면에서는
    되는 검색이 테스트에서만 안 되는 가짜 red 가 된다.
    """
    order = Order(received_date="2026-06-01", customer_name=name, phone=phone,
                  erp_phone_digits=normalize_phone_digits(phone),
                  address=address, product="붙박이장", status=status,
                  payment_amount=payment, is_erp_order=True if draft else None)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _collected(*, order_no: str = "", amount: int = 1_500_000,
               name: str = "김딸", tel: str = "010-1111-2222",
               address: str = "서울 강남구 테헤란로 152",
               relation: str = "", order_id: int | None = None) -> ExternalOrderLink:
    """수집 링크 1건 — 기본값은 위 `_order` 와 이름·전화·주소가 전부 다르다."""
    external_id = f"PO-SEEK-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no or f"N-SEEK-{_uid()}", "ordererName": name,
                  "ordererTel": tel},
        "productOrder": {
            "productOrderId": external_id, "productName": "로라 무몰딩 1cm",
            "totalPaymentAmount": amount,
            "shippingAddress": {"name": name, "tel1": tel,
                                "baseAddress": address, "detailedAddress": "101호"},
        },
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="LINKED" if order_id else "COLLECTED",
                             external_order_no=snapshot["order"]["orderId"],
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             relation=relation or None, order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _fresh(link_id: int) -> ExternalOrderLink:
    """요청 뒤 DB 상태를 다시 읽는다(요청은 자기 세션에서 커밋한다)."""
    db_session.expire_all()
    return db_session.get(ExternalOrderLink, link_id)


def _pane(client, link: ExternalOrderLink) -> str:
    response = client.get(f"{TRIAGE_PATH}?tab=work&link_id={link.id}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _search(client, link: ExternalOrderLink, query: str):
    return client.get(SEARCH_PATH.format(link_id=link.id) + f"?q={query}")


# --------------------------------------------------------------------------- #
# 1. 진입점 — 후보 0건에서도 붙일 길이 있다
# --------------------------------------------------------------------------- #

def test_zero_candidates_still_offer_a_way_to_find_the_order(client, workbench_on):
    """후보가 0건이어도 **찾는 자리**가 있다 — 없으면 새 주문을 만드는 수밖에 없다."""
    _login(client)
    _order()                      # 있지만 자동 매칭은 못 잡는 주문
    link = _collected()

    assert find_order_candidates(db_session, link) == [], "전제: 자동 후보 0건"
    body = _pane(client, link)

    assert 'id="wb-seek-q"' in body, "찾기 입력칸이 없다"
    assert 'id="wb-seek-run"' in body, "찾기 버튼이 없다"
    assert "wb-attach" not in body, "후보가 없는데 후보 표 붙이기 버튼이 났다"


def test_candidate_table_also_offers_the_search(client, workbench_on):
    """후보가 있어도 진입점은 남는다 — 셋 다 달라 **엉뚱한 후보 1건**만 뜨는 집이 있다."""
    _login(client)
    # 이름·주소 규칙으로 자동 후보에 잡히는 주문.
    _order(name="김딸", address="서울 강남구 테헤란로 152")
    link = _collected()

    assert find_order_candidates(db_session, link), "전제: 자동 후보가 있다"
    body = _pane(client, link)

    assert "wb-attach" in body, "후보 표는 그대로 있어야 한다"
    assert 'id="wb-seek-q"' in body, "후보가 있어도 직접 찾기는 남는다"
    assert "여기에 없나요?" in body


def test_attached_household_has_no_search_entry(client, workbench_on):
    """이미 붙은 집에는 찾기가 없다 — 두 번 붙이는 자리를 만들지 않는다."""
    _login(client)
    order_id = _order()
    link = _collected(relation="REPAY", order_id=order_id)

    body = _pane(client, link)

    assert 'id="wb-seek-q"' not in body
    assert "되돌리기" in body, "붙은 집은 되돌리기가 그 자리다"


# --------------------------------------------------------------------------- #
# 2. 검색 — 자동 매칭이 못 잡은 주문을 세 축으로 찾는다
# --------------------------------------------------------------------------- #

def test_search_finds_the_order_automatic_matching_missed(client, workbench_on):
    """이름·전화·주소가 **전부 다른** 주문도 이름으로 찾아 붙일 수 있다."""
    _login(client)
    order_id = _order()
    link = _collected()

    body = _search(client, link, "박아버지").get_data(as_text=True)

    assert f"#{order_id}" in body, "찾은 주문 번호가 보여야 한다"
    assert 'data-relation="ADDON"' in body and 'data-relation="REPAY"' in body
    assert f'data-order-id="{order_id}"' in body


def test_search_finds_by_phone_tail(client, workbench_on):
    """전화 뒷자리로 찾는다 — 담당자가 통화 기록에서 보는 값이다."""
    _login(client)
    order_id = _order(phone="010-9999-8888")
    link = _collected()

    body = _search(client, link, "98888").get_data(as_text=True)

    assert f"#{order_id}" in body
    assert "전화 일치" in body, "무엇으로 걸렸는지 말해야 한다"


def test_search_finds_by_order_number(client, workbench_on):
    """주문번호로 찾는다 — 숫자를 **전화 경로가 가로채면** 자기 주문을 못 찾는다."""
    _login(client)
    order_id = _order()
    link = _collected()

    body = _search(client, link, str(order_id)).get_data(as_text=True)

    assert f"#{order_id}" in body
    assert "주문번호 일치" in body
    # `#` 을 붙여 쳐도 같은 주문이 나온다(사람은 화면에 보이는 `#1234` 를 그대로 친다).
    assert f"#{order_id}" in _search(client, link, f"%23{order_id}").get_data(as_text=True)


def test_search_says_nothing_found_without_claiming_none_exists(client, workbench_on):
    """못 찾으면 **다시 찾는 법**까지 말한다 — "없습니다"로 끝내면 새 주문을 만든다."""
    _login(client)
    _order()
    link = _collected()

    body = _search(client, link, "없는이름").get_data(as_text=True)

    assert "찾은 주문이 없습니다" in body
    assert "주문번호" in body, "다시 찾는 축을 안내해야 한다"
    assert "새 주문" in body


def test_search_refuses_a_one_letter_query(client, workbench_on):
    """한 글자는 조회하지 않는다 — 성씨 한 자면 주문 전체를 훑는 것과 같다."""
    _login(client)
    order_id = _order(name="김")
    link = _collected()

    body = _search(client, link, "김").get_data(as_text=True)

    assert "두 글자 이상" in body
    assert f"#{order_id}" not in body


def test_search_never_offers_a_deleted_or_draft_order(client, workbench_on):
    """휴지통·초안은 결과에 없다 — 초안에 붙이면 승격 레이스에 걸린다(유령 주문 사고)."""
    _login(client)
    trashed_id = _order(name="박휴지", status="DELETED")
    draft_id = _order(name="박초안", status="DRAFT", draft=True)
    link = _collected()

    body = _search(client, link, "박초").get_data(as_text=True)

    assert f"#{trashed_id}" not in body
    assert f"#{draft_id}" not in body


def test_search_result_is_a_fragment_without_ids(client, workbench_on):
    """조각은 레이아웃도 id 도 없다 — pane 안에 꽂히므로 id 는 문서 중복이다(절대 규칙 1)."""
    _login(client)
    _order()
    link = _collected()

    body = _search(client, link, "박아버지").get_data(as_text=True)

    assert "<html" not in body.lower(), "조각에 레이아웃이 딸려 왔다"
    # `data-link-id=` 같은 속성은 id 가 아니다 — 요소 id 만 문다.
    assert re.search(r'\sid="', body) is None, "조각이 id 를 달았다"


def test_search_says_when_it_cut_the_list(client, workbench_on):
    """넘치면 **넘쳤다고 말한다** — 조용한 절단은 '이게 전부'로 읽힌다."""
    _login(client)
    for _ in range(SEARCH_LIMIT + 2):
        _order(name="박많은")
    link = _collected()

    result = search_orders_for_attach(db_session, link, query="박많은")

    assert len(result["rows"]) == SEARCH_LIMIT
    assert result["truncated"] is True
    body = _search(client, link, "박많은").get_data(as_text=True)
    assert "더 있습니다" in body


def test_search_carries_the_deposit_sentence(client, workbench_on):
    """붙인 뒤 **예약금에 넣을 금액**을 버튼이 들고 온다 — 검색 경로엔 정리 카드가 없다."""
    _login(client)
    _order()
    link = _collected(amount=1_500_000)

    body = _search(client, link, "박아버지").get_data(as_text=True)

    assert "data-deposit=" in body
    assert "1,500,000" in body, "새 집 금액이 안내 문장에 있어야 한다"


# --------------------------------------------------------------------------- #
# 3. 권한·게이트 — 검색은 개인정보를 연다
# --------------------------------------------------------------------------- #

def test_search_is_closed_when_the_workbench_gate_is_off(client, monkeypatch):
    """게이트 OFF 면 404 다 — 그 화면에는 이 경로가 없다(pane 과 같은 규율)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "0")
    _login(client)
    link = _collected()

    assert _search(client, link, "박아버지").status_code == 404


def test_search_404s_for_an_unknown_link(client, workbench_on):
    """없는 링크로는 못 연다 — 검색은 고객 이름·주소를 여는 자리다."""
    _login(client)

    assert client.get(SEARCH_PATH.format(link_id=999_999) + "?q=박").status_code == 404


def test_search_needs_a_login(client, workbench_on):
    """로그인 없이는 못 연다."""
    link = _collected()

    response = _search(client, link, "박아버지")

    assert response.status_code in (302, 401, 403)


# --------------------------------------------------------------------------- #
# 4. 붙인 뒤 — 기존 흐름과 같다
# --------------------------------------------------------------------------- #

def test_attaching_a_searched_order_moves_the_whole_household(client, workbench_on):
    """후보 목록 **밖** 주문에 붙여도 집 전체가 함께 움직인다(붙이기 계약 그대로)."""
    _login(client)
    order_id = _order()
    first = _collected(order_no="N-SEEK-WHOLE")
    second = _collected(order_no="N-SEEK-WHOLE", name="김딸")
    first_id, second_id = int(first.id), int(second.id)

    assert find_order_candidates(db_session, first) == [], "전제: 자동 후보 0건"
    response = client.post(ATTACH_PATH.format(link_id=first_id),
                           json={"order_id": order_id, "relation": "REPAY"})

    assert response.status_code == 200 and response.get_json()["success"] is True
    assert _fresh(first_id).order_id == order_id
    assert _fresh(second_id).order_id == order_id
    assert _fresh(first_id).relation == "REPAY"


def test_searched_attach_is_reversible(client, workbench_on):
    """되돌릴 수 있다 — 그래서 이 경로에 불가역 4종 세트 모달을 두지 않는다."""
    _login(client)
    order_id = _order()
    link_id = int(_collected().id)

    client.post(ATTACH_PATH.format(link_id=link_id),
                json={"order_id": order_id, "relation": "REPAY"})
    undo = client.post(f"/admin/naver-ingest/{link_id}/detach", json={})

    assert undo.status_code == 200
    assert _fresh(link_id).order_id is None
