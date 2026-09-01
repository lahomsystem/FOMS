"""재결제 원 주문 줄 — 화면·상수 계약 (NVREPAY · 2026-08-28).

**왜 필요한가**: 재결제를 주문에 붙이고 나면 담당자가 해야 할 다음 일은 **옛 네이버 주문을
취소(발송 전)하거나 반품(발송 후)** 하는 것이다. 그런데 붙이는 순간 화면에서 옛 결제 정보가
통째로 사라졌다 — 그 정보가 `아직 안 붙은 집` 갈래에만 있었기 때문이다. 담당자는 판매자센터를
따로 열어 주문번호로 찾아 들어가고 있었다.

여기서 못박는 것 다섯:

1. **NVREPAY-01** 옛 집 행이 ``link_id`` 를 싣는다 — 없으면 화면이 그 집을 가리킬 수 없다.
   그리고 **지금 보고 있는 집은 세지 않는다**(빼지 않으면 "옛 주문이 살아 있다"가 자기 자신을
   가리킨다).
2. **NVREPAY-02** 링크 0건일 때 화면은 "네이버 주문 확인 안 됨"이라고 말하고,
   **"없습니다"라고 단정하지 않는다**. 수집이 결제완료 상태만 가져오므로 첫 스윕 전에 이미
   처리가 끝난 주문은 영영 안 들어오고, 그 관측이 "정말 없음"과 똑같다.
3. **NVREPAY-03** 새 결제를 받은 뒤로 옛 주문을 읽은 적이 없으면 그 사실을 말하고, 앵커가
   **다시 읽고 열기**로 바뀐다. 읽은 적이 있으면 그냥 연다.
4. **NVREPAY-04** 우리가 보내는 취소 사유는 공식 범례의 부분집합이다.
5. **NVREPAY-05** 취소·반품 모달이 **상세 사유가 고객에게 그대로 간다**고 말한다.
"""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.fulfillment import (
    CANCEL_REASONS,
    OFFICIAL_CANCEL_REASONS,
)
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.integrations.naver_commerce.order_candidates import origin_facts
from models import ExternalOrderLink, Order, User

TRIAGE_PATH = "/admin/naver-ingest/triage"

#: 화면이 절대 말하면 안 되는 문장. 근거가 "링크가 0건"이라는 음성 신호 하나뿐인데
#: 확정형으로 말한다 — 실제로 있었는데 우리가 못 가져온 경우와 관측이 같다.
FORBIDDEN = (
    "네이버에 주문이 없습니다",
    "이 고객은 네이버 주문이 없습니다",
    "네이버 주문 없음",
)

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
    user = User(username=f"wborigin_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, tel: str) -> Order:
    order = Order(received_date="2026-08-01", customer_name="원주문고객", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 9 101호",
                  product="붙박이장", status="RECEIVED", payment_amount=0,
                  structured_data={})
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, tel: str, amount: int, order_id: int,
          relation: str = "NEW", dispatched: bool = False,
          created_at=None, refreshed_at: str = "") -> ExternalOrderLink:
    """수집 링크 1건.

    ``relation='REPAY'`` 면 pane 이 관계 블록을 렌더한다(그 안에 원 주문 줄이 산다).
    ``dispatched`` 는 네이버 원본 쪽 신호(``delivery.sendDate``)로 넣는다 — 판매자센터에서
    사람이 발송한 집을 잡는 축이라, 우리 표식만 보는 것보다 이쪽이 진짜 함정이다.
    """
    external_id = f"PO-ORIGIN-{_uid()}"
    product_order = {
        "productOrderId": external_id, "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "원주문고객", "tel1": tel,
                            "baseAddress": "서울 강남구 9", "detailedAddress": "101호"},
    }
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel},
                "productOrder": product_order}
    if dispatched:
        snapshot["delivery"] = {"sendDate": "2026-08-20T10:00:00.000+09:00"}
    state = {}
    if refreshed_at:
        state["claim_sync"] = {"refreshed_at": refreshed_at}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no,
                             raw_snapshot=copy.deepcopy(snapshot),
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED", order_id=order_id,
                             relation=relation,
                             triage_state=copy.deepcopy(state) or None)
    if created_at is not None:
        link.created_at = created_at
    db_session.add(link)
    db_session.commit()
    return link


def _origin_block(body: str) -> str:
    """원 주문 줄만 잘라 낸다(다른 블록 문구와 안 섞이게)."""
    needle = 'data-wb-origin='
    at = body.find(needle)
    assert at >= 0, "원 주문 줄이 렌더되지 않았다"
    start = body.rfind("<div", 0, at)
    end = body.find("<div class=\"wb-cmp-title\"", at)
    return body[start:end if end > 0 else len(body)]


def _body(client, *, link_id: int) -> str:
    return client.get(TRIAGE_PATH,
                      query_string={"tab": "work", "link_id": link_id}).get_data(as_text=True)


# --------------------------------------------------------------------------- #
# NVREPAY-01 — 식별자
# --------------------------------------------------------------------------- #

def test_origin_row_carries_the_link_id(app):
    """옛 집 행이 ``link_id`` 를 싣는다 — 없으면 화면이 그 집을 가리킬 수 없다."""
    order = _order(tel="010-9200-0001")
    old = _link(order_no="N-ORG-1-OLD", tel="010-9200-0001", amount=1_000_000,
                order_id=int(order.id))
    new = _link(order_no="N-ORG-1-NEW", tel="010-9200-0001", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    facts = origin_facts(db_session, order.id, exclude_link_ids={int(new.id)})

    assert facts["link_count"] == 1, "지금 보고 있는 집을 뺀 나머지만 센다"
    assert len(facts["alive_rows"]) == 1
    row = facts["alive_rows"][0]
    assert row["link_id"] == int(old.id)
    assert row["external_order_no"] == "N-ORG-1-OLD"
    assert old.external_id in row["product_order_ids"]
    assert row["amount_total"] == 1_000_000


def test_origin_does_not_count_the_household_we_are_looking_at(app):
    """자기 자신을 옛 주문이라고 말하지 않는다."""
    order = _order(tel="010-9200-0002")
    new = _link(order_no="N-ORG-2-NEW", tel="010-9200-0002", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    facts = origin_facts(db_session, order.id, exclude_link_ids={int(new.id)})

    assert facts["link_count"] == 0
    assert facts["alive_rows"] == []


def test_addon_sibling_is_not_an_origin_order(app):
    """추가결제는 **대체된 옛 주문이 아니다** — 원 주문 자리에 세우지 않는다.

    2026-08-28 운영 실데이터에서 잡은 결함. 주문 #4854 는 재결제(REPAY)와 추가결제(ADDON)를
    함께 달고 있었고, ADDON 집은 배송 중(살아 있음)이었다. 관계를 안 가렸더니 화면이 그
    25,000원 차액 결제를 "옛 주문이 아직 살아 있습니다 — 반품으로 처리합니다"로 지목했다.
    차액만 더 받은 결제를 반품하면 받은 돈이 도로 나간다.

    판정 축은 도크와 같다 — 대체된 집은 ``relation == 'NEW'`` 인 집뿐이다.
    """
    order = _order(tel="010-9200-0005")
    _link(order_no="N-ORG-5-ADDON", tel="010-9200-0005", amount=25_000,
          order_id=int(order.id), relation="ADDON", dispatched=True)
    new = _link(order_no="N-ORG-5-NEW", tel="010-9200-0005", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    facts = origin_facts(db_session, order.id, exclude_link_ids={int(new.id)})

    assert facts["link_count"] == 0, "추가결제를 옛 주문으로 셌다"
    assert facts["alive_rows"] == []


def test_addon_sibling_does_not_make_the_screen_ask_for_a_return(client, workbench_on):
    """같은 결함의 화면 쪽 — 추가결제가 있어도 '반품하세요'가 뜨면 안 된다."""
    _login(client)
    order = _order(tel="010-9200-0006")
    _link(order_no="N-ORG-6-ADDON", tel="010-9200-0006", amount=25_000,
          order_id=int(order.id), relation="ADDON", dispatched=True)
    new = _link(order_no="N-ORG-6-NEW", tel="010-9200-0006", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    block = _origin_block(_body(client, link_id=int(new.id)))

    assert "네이버 옛 주문이 아직 살아 있습니다" not in block
    assert "N-ORG-6-ADDON" not in block
    assert "네이버 주문 확인 안 됨" in block


def test_origin_row_marks_a_dispatched_household(app):
    """발송된 옛 집은 취소가 아니라 반품 대상이다 — 행이 그 축을 들고 있어야 한다."""
    order = _order(tel="010-9200-0003")
    _link(order_no="N-ORG-3-OLD", tel="010-9200-0003", amount=1_000_000,
          order_id=int(order.id), dispatched=True)
    new = _link(order_no="N-ORG-3-NEW", tel="010-9200-0003", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    facts = origin_facts(db_session, order.id, exclude_link_ids={int(new.id)})

    assert facts["alive_rows"][0]["dispatched"] is True


def test_origin_read_at_falls_back_to_collection_time(app):
    """``claim_sync.refreshed_at`` 이 없어도 '읽은 적 없음'이 아니다 — 수집도 읽은 것이다.

    이걸 놓치면 방금 수집한 정상 건에까지 "언제 읽었는지 모른다"가 붙고, 담당자가 그
    경고를 아무 데서나 보게 되어 정작 낡은 건에서 무시한다.
    """
    order = _order(tel="010-9200-0004")
    collected = now_utc_naive() - timedelta(days=3)
    _link(order_no="N-ORG-4-OLD", tel="010-9200-0004", amount=1_000_000,
          order_id=int(order.id), created_at=collected)
    new = _link(order_no="N-ORG-4-NEW", tel="010-9200-0004", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    facts = origin_facts(db_session, order.id, exclude_link_ids={int(new.id)})

    assert facts["alive_rows"][0]["read_at"] == collected.isoformat()


# --------------------------------------------------------------------------- #
# NVREPAY-02 — '확인 안 됨'은 '없음'이 아니다
# --------------------------------------------------------------------------- #

def test_screen_says_unconfirmed_not_absent(client, workbench_on):
    """링크 0건이면 '확인 안 됨'이라고 말한다 — '없습니다'라고 단정하지 않는다.

    예약금 건(최초 접수가 네이버가 아니고 ERP 에 직접 등록된 주문)이 정확히 이 자리다.
    """
    _login(client)
    order = _order(tel="010-9200-0011")
    new = _link(order_no="N-ORG-11-NEW", tel="010-9200-0011", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    block = _origin_block(_body(client, link_id=int(new.id)))

    assert "네이버 주문 확인 안 됨" in block
    assert "어느 쪽인지 이 화면은 알 수 없습니다" in block
    for phrase in FORBIDDEN:
        assert phrase not in block, f"확정형 문구가 살아났다: {phrase}"


def test_screen_points_to_the_old_household(client, workbench_on):
    """살아 있는 옛 주문은 **그 집 화면으로 가는 길**과 함께 나온다."""
    _login(client)
    order = _order(tel="010-9200-0012")
    old = _link(order_no="N-ORG-12-OLD", tel="010-9200-0012", amount=1_000_000,
                order_id=int(order.id))
    new = _link(order_no="N-ORG-12-NEW", tel="010-9200-0012", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    block = _origin_block(_body(client, link_id=int(new.id)))

    assert "네이버 옛 주문이 아직 살아 있습니다" in block
    assert "N-ORG-12-OLD" in block
    assert f"link_id={old.id}" in block, "옛 집 pane 으로 가는 주소가 없다"


def test_screen_sends_a_dispatched_household_to_return(client, workbench_on):
    """발송된 옛 주문에는 '취소'가 아니라 '반품'이라고 말한다."""
    _login(client)
    order = _order(tel="010-9200-0013")
    _link(order_no="N-ORG-13-OLD", tel="010-9200-0013", amount=1_000_000,
          order_id=int(order.id), dispatched=True)
    new = _link(order_no="N-ORG-13-NEW", tel="010-9200-0013", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    block = _origin_block(_body(client, link_id=int(new.id)))

    assert "이미 발송 처리된 주문입니다" in block
    assert "반품" in block
    assert "이 옛 주문은 네이버에서 취소해야 합니다" not in block


# --------------------------------------------------------------------------- #
# NVREPAY-03 — 새 결제 이후 확인 여부
# --------------------------------------------------------------------------- #

def test_stale_origin_makes_the_anchor_refresh_first(client, workbench_on):
    """새 결제 뒤로 옛 주문을 읽은 적이 없으면 말하고, 앵커가 먼저 다시 읽는다.

    그 구간이 "고객이 스스로 취소했는데 우리가 또 취소를 거는" 위험이 사는 자리다.
    """
    _login(client)
    order = _order(tel="010-9200-0021")
    old_at = now_utc_naive() - timedelta(days=30)
    _link(order_no="N-ORG-21-OLD", tel="010-9200-0021", amount=1_000_000,
          order_id=int(order.id), created_at=old_at)
    new = _link(order_no="N-ORG-21-NEW", tel="010-9200-0021", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    block = _origin_block(_body(client, link_id=int(new.id)))

    assert "새 결제를 받은 뒤로 이 옛 주문을 확인한 적이 없습니다" in block
    assert "wb-origin-open" in block
    assert "옛 주문 다시 읽고 열기" in block


def test_fresh_origin_just_opens(client, workbench_on):
    """새 결제 뒤에 읽은 기록이 있으면 그냥 연다 — 거짓 경고를 심지 않는다."""
    _login(client)
    order = _order(tel="010-9200-0022")
    # 새 결제를 **먼저** 만든다. 읽은 시각이 그보다 뒤여야 "새 결제 뒤에 확인했다"가 된다.
    new = _link(order_no="N-ORG-22-NEW", tel="010-9200-0022", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")
    _link(order_no="N-ORG-22-OLD", tel="010-9200-0022", amount=1_000_000,
          order_id=int(order.id), created_at=now_utc_naive() - timedelta(days=30),
          refreshed_at=(now_utc_naive() + timedelta(minutes=1)).isoformat())

    block = _origin_block(_body(client, link_id=int(new.id)))

    assert "새 결제를 받은 뒤로 이 옛 주문을 확인한 적이 없습니다" not in block
    assert "wb-origin-open" not in block
    assert "이 상태는" in block and "에 읽은 것입니다" in block


# --------------------------------------------------------------------------- #
# NVREPAY-04 — 사유 범례 잠금
# --------------------------------------------------------------------------- #

def test_cancel_reasons_are_a_subset_of_the_official_legend():
    """우리가 **보내는** 취소 사유는 공식 범례 안에만 있다.

    읽기로 오는 코드가 쓰기로 받는 코드보다 넓다(공식 #1137). 스냅샷에서 봤다는 것은
    보낼 수 있다는 뜻이 아니다 — 반품에서 ``WRONG_DELAYED_DELIVERY`` 로 한 번 겪었다.
    """
    unknown = set(CANCEL_REASONS) - set(OFFICIAL_CANCEL_REASONS)
    assert not unknown, f"공식 범례 밖 코드: {sorted(unknown)}"


def test_official_cancel_legend_excludes_etc():
    """``ETC`` 는 표에 있어도 API 로 지정할 수 없다(#3335) — 상수에 두지 않는다."""
    assert "ETC" not in OFFICIAL_CANCEL_REASONS


def test_sold_out_label_says_what_it_does():
    """`SOLD_OUT` 은 상품을 품절 처리하고 패널티 대상이다 — 고르기 전에 보여야 한다."""
    assert "SOLD_OUT" in CANCEL_REASONS, "정당한 품절 취소 경로를 없애지 않는다"
    assert "품절 처리" in CANCEL_REASONS["SOLD_OUT"]


# --------------------------------------------------------------------------- #
# NVREPAY-05 — 상세 사유는 고객에게 그대로 간다
# --------------------------------------------------------------------------- #

def test_cancel_modal_warns_that_the_detail_reaches_the_buyer(client, workbench_on):
    """상세 사유는 네이버페이 결제내역·톡톡에 원문 그대로 뜬다(공식 #2823).

    취소 모달과 반품 모달은 **동시에 렌더되지 않는다** — 취소는 미발송 집에서만,
    반품은 발송된 집에서만 열린다(버튼과 같은 조건). 그래서 따로 세운다.
    """
    _login(client)
    order = _order(tel="010-9200-0031")
    new = _link(order_no="N-ORG-31-NEW", tel="010-9200-0031", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    body = _body(client, link_id=int(new.id))

    assert 'id="wb-cancel-detail"' in body, "취소 모달이 렌더되지 않았다"
    assert "고객에게 그대로 보입니다" in body
    assert "네이버톡톡에 그대로 뜹니다" in body


def test_return_modal_warns_that_the_detail_reaches_the_buyer(client, workbench_on):
    """반품 모달도 같은 고지를 진다 — 발송된 집에서만 열린다."""
    _login(client)
    order = _order(tel="010-9200-0033")
    sent = _link(order_no="N-ORG-33-SENT", tel="010-9200-0033", amount=1_400_000,
                 order_id=int(order.id), relation="REPAY", dispatched=True)

    body = _body(client, link_id=int(sent.id))

    assert 'id="wb-return-detail"' in body, "반품 모달이 렌더되지 않았다"
    assert "고객에게 그대로 보입니다" in body
    assert "네이버톡톡에 그대로 뜹니다" in body


def test_cancel_placeholder_does_not_suggest_a_stock_reason(client, workbench_on):
    """옛 예시('재고 없음')는 고객에게 나갈 문장으로 오도적이고 SOLD_OUT 을 끌어당겼다."""
    _login(client)
    order = _order(tel="010-9200-0032")
    new = _link(order_no="N-ORG-32-NEW", tel="010-9200-0032", amount=1_400_000,
                order_id=int(order.id), relation="REPAY")

    body = _body(client, link_id=int(new.id))

    assert "고객 통화 확인 — 재고 없음" not in body
    assert "새 주문으로 다시 결제하셨습니다" in body


# --------------------------------------------------------------------------- #
# 재현 — 네이버만 "발송됨"이라고 말하는 집에서 pane 이 취소를 연다
# --------------------------------------------------------------------------- #

def test_pane_closes_cancel_when_only_naver_says_dispatched(client, workbench_on):
    """네이버 원본이 발송을 말하면 **취소 버튼이 닫혀야** 한다.

    판매자센터에서 사람이 직접 발송처리한 집은 우리 표식(``dispatched_at``)이 없다.
    그런데 화면 다른 자리(정리 띠·관계 블록)는 ``delivery.sendDate`` 를 읽어 "이미 발송
    처리된 주문 — 반품"이라고 말한다. 두 축이 갈리면 같은 집을 두고 화면이 "반품 건"이라
    적어 놓고 **취소 버튼**을 열어 준다.
    """
    _login(client)
    order = _order(tel="010-9200-0099")
    sent = _link(order_no="N-ORG-99-SENT", tel="010-9200-0099", amount=1_000_000,
                 order_id=int(order.id), relation="NEW", dispatched=True)

    body = _body(client, link_id=int(sent.id))

    # 버튼을 아예 안 내든 잠그든 둘 다 좋다 — **누를 수 없으면** 된다.
    at = body.find('id="wb-cancel"')
    if at >= 0:
        tag = body[body.rfind("<button", 0, at):body.find(">", at) + 1]
        assert "disabled" in tag, f"네이버가 발송을 말하는데 취소가 열려 있다: {tag}"
        assert "wb-modal-cancel" not in tag, "잠갔다면서 모달을 열어 준다"
        # 이유 없이 잠근 버튼은 사람이 계속 누른다.
        assert "네이버에 이미 발송 기록이 있습니다" in tag, tag
    # 빈손 통과를 막는다: 버튼을 감췄어도 **취소 모달이 남아 있으면** 안 된다.
    # 모달이 살아 있으면 다른 경로(북마크·직접 호출)가 그 입력을 그대로 쓴다.
    assert 'id="wb-cancel-reason"' not in body, "취소 모달이 그대로 살아 있다"


def test_pane_offers_return_instead_when_only_naver_says_dispatched(client, workbench_on):
    """취소를 닫았으면 **반품 접수**가 그 자리를 대신해야 한다.

    둘 다 닫으면 담당자는 판매자센터로 갈 수밖에 없는데, 그 집은 우리가 처리할 수 있다.
    """
    _login(client)
    order = _order(tel="010-9200-0098")
    sent = _link(order_no="N-ORG-98-SENT", tel="010-9200-0098", amount=1_000_000,
                 order_id=int(order.id), relation="NEW", dispatched=True)

    body = _body(client, link_id=int(sent.id))

    at = body.find('id="wb-return"')
    assert at >= 0, "반품 접수 버튼이 없다"
    tag = body[body.rfind("<button", 0, at):body.find(">", at) + 1]
    assert "disabled" not in tag, f"취소도 반품도 닫히면 화면이 막다른 길이 된다: {tag}"


def test_service_refuses_cancel_when_only_naver_says_dispatched(app):
    """서버도 막는다 — 화면만 고치면 열린 탭·북마크가 그 가드를 우회한다.

    발송처리·반품 접수·반품 승인은 이미 두 신호를 본다. 취소만 빠져 있었다.
    """
    from foms.services.integrations.naver_commerce import fulfillment

    order = _order(tel="010-9200-0097")
    sent = _link(order_no="N-ORG-97-SENT", tel="010-9200-0097", amount=1_000_000,
                 order_id=int(order.id), relation="NEW", dispatched=True)

    class _Client:
        def __init__(self):
            self.calls = []

        def request_cancel_product_order(self, pid, *, reason, detail=None):
            self.calls.append(pid)
            return {"data": {"successProductOrderIds": [pid], "failProductOrderInfos": []}}

    fake = _Client()
    with pytest.raises(fulfillment.FulfillmentError) as exc:
        fulfillment.cancel_order(db_session, fake, link_id=int(sent.id),
                                 reason="INTENT_CHANGED")

    assert "반품" in str(exc.value)
    assert fake.calls == [], "되돌릴 수 없는 취소가 네이버로 나갔다"
