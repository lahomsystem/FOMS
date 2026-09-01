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
from tests.services.integrations._markup import is_disabled, open_tag

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
    """신규는 배지를 달지 않는다 — 대부분이 신규라 다 달면 배지가 무의미해진다.

    v3 에서 '추가결제·재결제' 는 **필터 칩 라벨**로도 화면에 항상 있다(목록을 거르는
    장치라 관계와 무관하게 뜬다). 글자만 세면 늘 실패하므로, 배지 자체(관계 배지가
    쓰는 `badge bg-info`)가 0인지를 문다 — 지키려던 뜻은 "이 집이 후속으로 보이면 안
    된다" 다.

    **관계 섹션 자체는 이제 뜬다**(T2, 2026-08-31). 후보 0건이어도 `주문 직접 찾기`
    진입점이 그 자리에 있어야 하기 때문이다. 섹션이 있다는 것과 이 집이 후속으로
    **보인다**는 것은 다른 말이다 — 후자는 배지와 붙이기 버튼이 말한다.
    """
    _login(client)
    link = _collected(order_no="N-REL-NEW")

    body = _body(client, tab="work", link_id=link.id)

    assert "badge bg-info" not in body, "신규 집에 관계 배지가 달렸다"
    assert "wb-attach" not in body, "신규 집에 붙이기 후보가 떴다"
    # 칩은 배지가 아니다 — 목록 필터라 관계와 무관하게 늘 있다.
    assert 'data-filter="rel"' in body


# --------------------------------------------------------------------------- #
# T-R2 관계 섹션 — 후보·붙이기·되돌리기 (D3)
# --------------------------------------------------------------------------- #

def test_detail_offers_existing_orders_with_attach_buttons(client, workbench_on):
    """후보가 있으면 상세에 '기존 주문' 표와 붙이기 버튼 2종이 뜬다."""
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-CAND")

    body = _body(client, tab="work", link_id=link.id)

    assert "wb-attach" in body, "붙이기 버튼이 있어야 한다"
    assert 'data-relation="ADDON"' in body
    assert 'data-relation="REPAY"' in body
    assert f"#{order.id}" in body, "어느 주문에 붙는지 번호가 보여야 한다"


def test_candidate_table_shows_the_customers_cancel_sentence(client, workbench_on):
    """후보 표의 `네이버 옛 결제` 열이 **고객이 쓴 사유 원문**까지 말한다 (2026-08-26).

    판정(재결제냐 추가결제냐)이 실제로 일어나는 자리는 pane 위쪽이 아니라 이 표다.
    라벨 `전부 취소` 는 무엇이 일어났는지만 말하고, 왜 취소했는지는 이 문장에 있다.
    """
    _login(client)
    order = _order()
    old = _collected(order_no="N-REL-OLDCXL", amount=500000, claim_status="CANCEL_DONE",
                     order_id=int(order.id), relation="REPAY")
    snapshot = dict(old.raw_snapshot)
    snapshot["cancel"] = {"claimStatus": "CANCEL_DONE",
                          "cancelDetailedReason": "일시불 재결제 예정"}
    old.raw_snapshot = snapshot
    db_session.commit()
    link = _collected(order_no="N-REL-NEWPAY", amount=600000)

    body = _body(client, tab="work", link_id=link.id)

    assert "wb-cand__reason" in body, "후보 표에 사유 원문 자리가 없다"
    assert "일시불 재결제 예정" in body, "고객이 쓴 문장이 판정 자리에 닿지 않았다"


def test_candidate_without_a_cancel_reason_prints_no_empty_quote(client, workbench_on):
    """사유가 없는 후보에는 **빈 따옴표조차 내지 않는다** — 빈 칸은 거짓말이다."""
    _login(client)
    order = _order()
    _collected(order_no="N-REL-OLDALIVE", amount=500000, order_id=int(order.id),
               relation="ADDON")
    link = _collected(order_no="N-REL-NEWALIVE", amount=50000)

    body = _body(client, tab="work", link_id=link.id)

    assert "wb-cand__reason" not in body, "사유가 없는데 사유 줄이 났다"


def test_candidate_table_is_absent_without_candidates(client, workbench_on):
    """후보가 없으면 **후보 표**를 내지 않는다 — 빈 표는 거짓말이다.

    2026-08-31(T2)까지는 섹션 자체를 안 냈다. 그런데 자동 매칭이 못 잡는 조합
    (가족 대리결제·시공지 변경·번호 변경)이 바로 재결제라, 정작 붙여야 할 때 붙이는
    길이 화면에 아예 없었다. 지금은 **찾기 진입점**이 그 자리를 채운다
    (:func:`test_zero_candidates_still_offer_a_way_to_find_the_order`).
    """
    _login(client)
    link = _collected(order_no="N-REL-NOCAND")

    body = _body(client, tab="work", link_id=link.id)

    assert "wb-attach" not in body
    assert "wb-cmp--cand" not in body, "후보가 없는데 후보 표가 났다"


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

    assert "wb-attach" not in body


# --------------------------------------------------------------------------- #
# T-R3 발송처리 관계별 분기 (D1·D2)
# --------------------------------------------------------------------------- #

def test_addon_can_close_before_place_confirmation(client, workbench_on):
    """추가결제는 발주확인 전에도 발송처리가 열린다 — 물건이 따로 나가지 않는다.

    D1 개정 2026-08-27: 버튼 라벨이 `발송처리` 하나로 통일돼 **라벨로는 close_now 를
    못 가른다**(같은 호출인데 이름이 둘이면 다른 기능으로 읽힌다). 판별자는 close_now
    가지에서만 나오는 안내 문장 `물건이 따로 나가지 않습니다` 다.
    """
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-ADDON-DISP", relation="ADDON",
                      order_id=int(order.id), place_status="NOT_YET")

    body = _body(client, tab="work", link_id=link.id)

    assert "물건이 따로 나가지 않습니다" in body
    assert not is_disabled(body, "wb-dispatch"), open_tag(body, "wb-dispatch")


def test_new_household_stays_locked_before_place_confirmation(client, workbench_on):
    """신규는 그대로다 — 발주확인 전이면 사유 달린 회색 잠금."""
    _login(client)
    link = _collected(order_no="N-REL-NEW-LOCK", place_status="NOT_YET")

    body = _body(client, tab="work", link_id=link.id)

    assert is_disabled(body, "wb-dispatch"), open_tag(body, "wb-dispatch")
    assert "물건이 따로 나가지 않습니다" not in body


def test_repay_stays_locked_before_place_confirmation(client, workbench_on):
    """재결제는 발송처리가 잠기고 '바로 닫는' 안내도 뜨지 않는다 (D1 개정 2026-08-24).

    재결제는 원 주문을 취소하고 그 물건값을 다시 낸 것이라 **원 주문의 물건이 나중에
    한 번 나간다** — 발주확인이 먼저다. 화면에서 발송처리 버튼이 파랗게 켜져 있으면 두 번째
    클릭이 그대로 불가역 호출이 된다(구매자에게 "배송 시작", 취소 버튼 소멸).

    배지('재결제')는 그대로 있어야 한다 — 관계를 숨기는 게 아니라 버튼만 닫는 것이다.
    """
    _login(client)
    order = _order()
    link = _collected(order_no="N-REL-REPAY-LOCK", relation="REPAY",
                      order_id=int(order.id), place_status="NOT_YET")

    body = _body(client, tab="work", link_id=link.id)

    assert "재결제" in body, "관계 배지는 그대로 보여야 한다"
    assert "물건이 따로 나가지 않습니다" not in body, "재결제 집에 close_now 안내가 떴다"
    assert is_disabled(body, "wb-dispatch"), open_tag(body, "wb-dispatch")
    assert "신규 주문이라" not in body, "재결제 집을 '신규 집'이라 불렀다"


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


# --------------------------------------------------------------------------- #
# T-R4 판매자 직접취소 — 화면 (스펙 §3.4)
# --------------------------------------------------------------------------- #

def test_detail_has_a_cancel_button_and_reason_picker(client, workbench_on):
    """취소는 판매자센터로 나가지 않고 여기서 한다 — 버튼 + 사유 선택."""
    _login(client)
    link = _collected(order_no="N-REL-CXL")

    body = _body(client, tab="work", link_id=link.id)

    assert 'id="wb-cancel"' in body
    assert 'id="wb-modal-cancel"' in body
    assert 'value="INTENT_CHANGED"' in body, "네이버 사유 코드를 그대로 보낸다"
    assert "구매 의사 취소" in body, "사람이 읽는 라벨도 함께 보여준다"
    # `SOLD_OUT` 은 2026-09-01 사용자 지시로 목록에서 빠졌다 — 고르면 상품이 네이버에서
    # 내려가고 판매관리 패널티가 붙는다. 화면에 되살아나면 여기서 빨개진다.
    assert 'value="SOLD_OUT"' not in body


def test_cancel_modal_restates_the_count_and_says_it_is_final(client, workbench_on):
    """불가역 4종 세트 — 건수 재진술 + 되돌릴 수 없음 + 사후 경로."""
    _login(client)
    link = _collected(order_no="N-REL-CXL-MODAL")

    body = _body(client, tab="work", link_id=link.id)

    assert "되돌릴 수 없습니다" in body
    assert "환불" in body or "결제" in body, "구매자에게 무엇이 일어나는지 말해야 한다"


def test_dispatched_household_cannot_be_cancelled(client, workbench_on):
    """발송처리한 집은 취소가 아니라 반품이다 — 버튼을 열지 않는다(서버도 막는다)."""
    _login(client)
    link = _collected(order_no="N-REL-CXL-SENT")
    link.triage_state = {"fulfillment": {"dispatched_at": "2026-08-22T00:00:00"}}
    db_session.commit()

    body = _body(client, tab="work", link_id=link.id)

    assert 'id="wb-cancel"' not in body


def test_cancel_failure_is_not_retried_as_a_place_confirmation(client, workbench_on):
    """취소 실패를 '발주확인'으로 재시도하면 안 된다 — 되돌릴 수 없는 오발사다.

    실패 행의 action 은 워커가 적은 값 그대로 살아야 한다. 모르는 값을 confirm 으로
    강등하면, 취소하려던 집에 발주확인이 나간다.
    """
    _login(client)
    link = _collected(order_no="N-REL-CXL-FAIL")
    link.triage_state = {"fulfillment": {"last_error": "상품 주문 상태 확인 필요",
                                         "last_error_action": "cancel",
                                         "last_error_at": "2026-08-22T01:00:00"}}
    db_session.commit()

    body = _body(client, tab="work", link_id=link.id)

    assert f'{link.id}:confirm' not in body
    assert "취소" in body


def test_cancel_failure_alone_leaves_no_retry_button(client, workbench_on):
    """취소 실패만 있으면 '실패한 집만 다시 시도' 버튼을 내지 않는다.

    취소는 사유를 다시 골라야 한다 — 버튼 하나로 되보낼 수 없다.
    """
    _login(client)
    link = _collected(order_no="N-REL-CXL-FAIL2")
    link.triage_state = {"fulfillment": {"last_error": "네이버 거절",
                                         "last_error_action": "cancel",
                                         "last_error_at": "2026-08-22T01:00:00"}}
    db_session.commit()

    body = _body(client, tab="work", link_id=link.id)

    assert 'id="wb-retry-failed"' not in body


def test_place_tab_also_flags_addon_households(client, workbench_on):
    """'발주확인 전' 탭에서도 관계가 보인다 — 같은 배지 규칙(D4)."""
    _login(client)
    order = _order()
    _collected(order_no="N-REL-PLACE-ADDON", relation="ADDON", order_id=int(order.id),
               place_status="NOT_YET")

    body = _body(client, tab="place")

    assert "추가결제" in body


# --------------------------------------------------------------------------- #
# 푸시 전 리뷰 [치명] — 취소한 집은 화면에서도 닫힌다
# --------------------------------------------------------------------------- #

def _mark_canceled(link: ExternalOrderLink) -> None:
    """워커가 취소를 성공시킨 뒤의 상태."""
    link.triage_state = {"fulfillment": {"canceled_at": "2026-08-22T01:00:00",
                                         "cancel_reason": "SOLD_OUT"}}
    db_session.commit()


def test_cancelled_household_cannot_be_dispatched(client, workbench_on):
    """취소한 집으로 발송처리가 나가면 안 된다 — 서버도 막지만 화면이 먼저다.

    v3 는 버튼을 지우는 대신 **잠가서 남긴다**(계약 §3.3) — 사라진 버튼은 이유를
    말해 주지 못한다. 보내는 길(모달·확인 버튼)이 없다는 것이 지켜야 할 뜻이다.
    """
    _login(client)
    link = _collected(order_no="N-REL-CXL-DONE")
    _mark_canceled(link)

    body = _body(client, tab="work", link_id=link.id)

    head = open_tag(body, "wb-dispatch")
    assert is_disabled(body, "wb-dispatch"), head
    assert "취소한 주문입니다" in head, "왜 잠겼는지 버튼이 말해야 한다"
    assert 'id="wb-modal-dispatch"' not in body
    assert 'id="wb-dispatch-confirm"' not in body
    assert "취소 완료" in body


def test_cancelled_household_cannot_create_an_order(client, workbench_on):
    """취소한 집으로 주문을 만들지 않는다."""
    _login(client)
    link = _collected(order_no="N-REL-CXL-NOORDER")
    _mark_canceled(link)

    body = _body(client, tab="work", link_id=link.id)

    assert "취소한 주문입니다" in body


def test_cancelled_household_leaves_the_place_filter(client, workbench_on):
    """'발주확인 전' 갈래에서 빠진다 — 안 빼면 전부 선택 → 발주확인이 취소한 집으로 나간다.

    v3 에서 그 갈래는 탭이 아니라 칩이다. 옛 주소(`?tab=place`)도 같은 곳을 가리켜야
    한다 — 열어 둔 탭·북마크가 빈 화면으로 떨어지면 안 된다.
    """
    _login(client)
    link = _collected(order_no="N-REL-CXL-PLACE", place_status="NOT_YET")
    _mark_canceled(link)

    for body in (_body(client, tab="work", f="place"), _body(client, tab="place")):
        assert body.count('<a class="wb-row') == 0, "취소한 집이 발주확인 목록에 남아 있다"
        assert "0주문" in body.split('data-filter="place"')[1].split("</a>")[0]
        assert 'class="wb-pick"' not in body, "고를 수 있으면 벌크로 발주확인이 나간다"


def test_a_mixed_relation_household_is_not_offered_close_now(client, workbench_on):
    """형제 하나가 신규면 close_now 를 열지 않는다 — 서버 all 규칙과 같은 판정."""
    _login(client)
    order = _order()
    lead = _collected(order_no="N-REL-MIXED", relation="ADDON", order_id=int(order.id),
                      place_status="NOT_YET", amount=500000)
    _collected(order_no="N-REL-MIXED", place_status="NOT_YET", amount=100)

    body = _body(client, tab="work", link_id=lead.id)

    assert "물건이 따로 나가지 않습니다" not in body
    assert is_disabled(body, "wb-dispatch"), open_tag(body, "wb-dispatch")


def test_cancel_refusal_is_not_hidden_by_another_failure(client, workbench_on):
    """한 집에 실패가 섞이면 **취소 거절**을 보여준다 — 가려지면 재시도가 반대 조작을 쏜다."""
    _login(client)
    first = _collected(order_no="N-REL-MIXFAIL", amount=500000)
    second = _collected(order_no="N-REL-MIXFAIL", amount=100)
    first.triage_state = {"fulfillment": {"last_error": "이미 발송처리한 주문입니다",
                                          "last_error_action": "cancel",
                                          "last_error_at": "2026-08-22T02:00:00"}}
    second.triage_state = {"fulfillment": {"last_error": "발주확인이 먼저입니다",
                                           "last_error_action": "dispatch",
                                           "last_error_at": "2026-08-22T01:00:00"}}
    db_session.commit()

    body = _body(client, tab="work", link_id=first.id)

    assert "이미 발송처리한 주문입니다" in body
    assert 'id="wb-retry-failed"' not in body, "취소 거절 집에 재시도 버튼을 내면 안 된다"


def test_modal_counts_the_household_the_server_will_touch(client, workbench_on):
    """모달 건수 = 서버가 처리할 건수 (2026-08-23 리뷰 F5).

    확인 완료된 형제는 큐에서 빠지지만 워커는 그 집을 통째로 처리한다. 화면이 큐 기준으로
    세면 "1건 취소합니다"라고 읽히고 2건이 환불된다.
    """
    from foms.services.datetime_kst import now_utc_naive

    _login(client)
    lead = _collected(order_no="N-REL-COUNT", amount=500000)
    sibling = _collected(order_no="N-REL-COUNT", amount=100)
    sibling.reviewed_at = now_utc_naive()
    db_session.commit()

    body = _body(client, tab="work", link_id=lead.id)

    assert "상품주문 2건" in body, "확인 완료된 형제도 세어야 한다"
    assert body.count("2건을") >= 1
