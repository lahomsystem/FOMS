# -*- coding: utf-8 -*-
"""휴지통에 넣었다는 **사실이 화면에 남는가** (2026-09-07).

담당자가 상세 pane 에서 `이 ERP 주문을 휴지통으로` 를 눌렀다. 주문은 실제로 접혔는데
화면에는 그 사실이 한 글자도 남지 않았다(2026-09-07 사용자 보고). 원인은 둘이다:
폐기 블록이 휴지통 주문을 만나면 통째로 사라졌고(`applicable=False`), 머리줄 배지는
휴지통 여부를 아예 보지 않았다. 그래서 접힌 주문이 살아 있는 것처럼 보였다.

여기서 못박는 것 넷:

1. 휴지통 주문이어도 클레임이 있으면 **블록이 그려진다** — 사라지지 않는다.
2. 그때 버튼은 잠기고 **왜 못 누르는지를 말한다**(라우트가 이미 막고 있던 말과 같은 말).
3. 머리줄은 클레임 유무와 **무관하게** 휴지통을 말한다 — 독립 축이다.
4. **판정 축은 한 글자도 안 바뀐다** — 살아 있는 주문의 `can_discard` 는 그대로 열린다.

휴지통에 넣을 때는 정본 엔진(:func:`foms.services.orders.soft_delete.soft_delete_order`)만
쓴다. 컬럼에 문자열을 직접 꽂으면 `structured_data['delete']` 가 안 생겨 **실제 경로를
검증하지 않는 셈**이 된다.
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.ghost_orders import judge_order_discard
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.orders.soft_delete import soft_delete_order
from models import ExternalOrderLink, Order, User

PANE_PATH = "/admin/naver-ingest/triage/pane"
DISCARD_BUTTON = "wb-pane-ghost-discard"

# 화면 낱말 — 여기서만 적고 단언은 이 상수를 쓴다.
# 배지는 마크업까지 포함해 잡는다: `휴지통` 이라는 낱말은 아래 후보 표·검색 표에도
# 쓰이므로, 낱말만 찾으면 머리줄이 아닌 자리에 속아 오탐이 난다.
TRASH_BADGE = '<span class="badge bg-dark text-white">휴지통</span>'
TRASH_BLOCK_TEXT = "이미 휴지통에 있습니다 — 주문 목록 휴지통에서 되돌립니다"

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


def _user(*, role: str = "ADMIN") -> User:
    """행위자 1명. soft delete 는 actor 와 OrderEvent 를 남기므로 실제 행이 필요하다."""
    user = User(username=f"gtrash_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, *, role: str = "ADMIN") -> User:
    """pane 을 열 사용자. 휴지통 사유 칸은 ADMIN 에게만 뜬다."""
    user = _user(role=role)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, status: str = "RECEIVED", tel: str) -> Order:
    """ERP 주문 1건(유령 후보와 같은 모양)."""
    order = Order(received_date="2026-08-13", customer_name=f"휴지{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 1 101호",
                  product="붙박이장", status=status, payment_amount=0, is_erp_order=True)
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, amount: int, order_id: int, tel: str,
          claim: str = "") -> ExternalOrderLink:
    """그 주문에 붙은 네이버 상품주문 1줄."""
    product_order = {
        "productOrderId": f"PO-GT-{_uid()}",
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


def _trash(order: Order, *, actor: User, reason: str,
           now: datetime.datetime | None = None) -> None:
    """정본 엔진으로 휴지통에 넣는다 — 컬럼에 값을 직접 꽂지 않는다."""
    soft_delete_order(db_session, order_id=int(order.id), actor_user_id=int(actor.id),
                      reason=reason, now=now)
    db_session.commit()


def _pane(client, link_id: int) -> str:
    """집 pane 조각 HTML."""
    response = client.get(f"{PANE_PATH}?link_id={link_id}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_data(as_text=True)


def test_trashed_order_with_a_claim_still_draws_the_block(app):
    """휴지통 주문이어도 클레임이 있으면 블록이 남는다 — 사라지면 아무 말도 못 한다."""
    actor = _user()
    tel = "010-7500-0001"
    order = _order(tel=tel)
    _link(order_no="N-GT-1", amount=558_400, claim="CANCEL_DONE",
          order_id=int(order.id), tel=tel)
    _trash(order, actor=actor, reason="네이버 취소 확정")

    view = judge_order_discard(db_session, int(order.id))

    assert view["applicable"] is True, "휴지통에 넣자 블록이 통째로 사라졌다"
    assert view["trashed"] is True
    assert view["can_discard"] is False, "이미 접힌 주문에 휴지통 버튼이 열렸다"
    assert view["discard_block"] == TRASH_BLOCK_TEXT
    # 사유 축은 판정 축이라 이번 변경이 건드리지 않는다(접수 단계 = 사유 불필요).
    assert view["discard_needs_reason"] is False


def test_trashed_order_reports_when_and_why(app):
    """언제·왜 접었는지를 말한다 — 시각은 KST `MM-DD HH:MM` 이다."""
    actor = _user()
    tel = "010-7500-0002"
    order = _order(tel=tel)
    _link(order_no="N-GT-2", amount=667_600, claim="CANCEL_DONE",
          order_id=int(order.id), tel=tel)
    # 저장은 naive=UTC 규약이다. 기대값을 피검 코드와 **같은 변환기**로 만들면 KST 축이
    # 동어반복이 되므로 손으로 적은 리터럴로 못박는다: 09-06 23:41 UTC + 9h = 09-07 08:41.
    stamp = datetime.datetime(2026, 9, 6, 23, 41, 17)
    reason = "고객 취소 확정 — 재결제 없음"
    _trash(order, actor=actor, reason=reason, now=stamp)

    view = judge_order_discard(db_session, int(order.id))

    assert view["trashed_at_text"] == "09-07 08:41"
    assert reason in view["trashed_note"]


def test_a_living_order_says_nothing_about_trash(app):
    """음성 대조군 — 같은 모집단인데 휴지통이 아니면 세 키가 전부 조용하다.

    판정이 흔들리지 않았다는 것도 여기서 함께 잰다: 살아 있는 전부취소·확정 주문은
    표기 축을 붙인 뒤에도 그대로 열린다.
    """
    tel = "010-7500-0003"
    order = _order(tel=tel)
    _link(order_no="N-GT-3", amount=300_000, claim="CANCEL_DONE",
          order_id=int(order.id), tel=tel)

    view = judge_order_discard(db_session, int(order.id))

    assert view["trashed"] is False
    assert view["trashed_at_text"] == ""
    assert view["trashed_note"] == ""
    assert view["can_discard"] is True, "휴지통 표기를 붙이면서 살아 있는 주문이 잠겼다"
    assert view["discard_block"] == ""


def test_blank_view_still_carries_the_trash_keys(app):
    """블록을 안 그리는 경로도 세 키를 **고정값으로** 들고 있다.

    `ghost_discard.trashed` 는 블록이 그려질 때만 사실을 말한다 — "이 주문이 휴지통인가"
    의 화면 정본은 머리줄 독립 키(`order_trashed`)다. 두 키가 같은 말을 하려 들면
    클레임 없는 주문에서 서로를 반박한다.
    """
    actor = _user()
    tel = "010-7500-0004"
    order = _order(tel=tel)
    _link(order_no="N-GT-4", amount=900_000, order_id=int(order.id), tel=tel)
    _trash(order, actor=actor, reason="오입력 정리")

    view = judge_order_discard(db_session, int(order.id))

    assert view["applicable"] is False, "클레임이 없는데 블록이 그려졌다"
    assert view["trashed"] is False
    assert view["trashed_at_text"] == ""
    assert view["trashed_note"] == ""


def test_pane_header_says_trash_even_without_any_claim(app, client, workbench_on):
    """머리줄은 클레임과 **무관하게** 휴지통을 말한다 — 그래서 독립 키다."""
    actor = _login(client)
    tel = "010-7500-0005"
    order = _order(tel=tel)
    link = _link(order_no="N-GT-5", amount=450_000, order_id=int(order.id), tel=tel)
    _trash(order, actor=actor, reason="중복 접수")

    body = _pane(client, int(link.id))

    assert TRASH_BADGE in body, "접힌 주문인데 머리줄이 한 글자도 말하지 않는다"
    # 음성 대조군 겸용 — 클레임이 없으므로 폐기 블록은 여전히 안 그려진다.
    assert DISCARD_BUTTON not in body, "클레임이 없는데 휴지통 블록이 그려졌다"


def test_restored_order_ignores_the_leftover_delete_projection(app):
    """음성 대조군 — **되살아난** 주문은 삭제 흔적이 남아 있어도 조용하다.

    legacy 복원 분기(``foms/web/orders/trash.py:311-318``)는 ``deleted_at`` 과 ``status``
    만 되돌리고 ``structured_data['delete']`` 를 pop 하지 않는다. projection 을 무조건
    읽으면 살아 있는 주문 화면에 삭제 시각·사유가 찍힌다 — 여기가 그 회귀를 잡는 자리다.
    """
    actor = _user()
    tel = "010-7500-0007"
    order = _order(tel=tel)
    _link(order_no="N-GT-7", amount=480_000, claim="CANCEL_DONE",
          order_id=int(order.id), tel=tel)
    _trash(order, actor=actor, reason="오입력 정리", now=datetime.datetime(2026, 9, 6, 23, 41, 17))
    # legacy 미러가 status 를 덮은 뒤 위 분기로 복원된 모양을 그대로 만든다:
    # 두 축은 지워지고 projection 만 남는다.
    order.status = "RECEIVED"
    order.deleted_at = None
    db_session.commit()
    assert (order.structured_data or {}).get("delete"), "복원 잔재를 못 만들면 검증이 헛돈다"

    view = judge_order_discard(db_session, int(order.id))

    assert view["trashed"] is False
    assert view["trashed_at_text"] == "", "복원된 주문에 삭제 시각이 찍혔다"
    assert view["trashed_note"] == "", "복원된 주문에 삭제 사유가 찍혔다"
    assert view["can_discard"] is True, "복원했는데 휴지통 버튼이 잠겼다"


def test_pane_block_prints_when_and_why_together(app, client, workbench_on):
    """클레임이 있는 휴지통 주문의 폐기 블록은 시각과 사유를 **한 줄에 함께** 낸다.

    서비스가 사실을 내도 템플릿이 안 그리면 담당자는 여전히 아무것도 못 읽는다.
    되돌릴 사람이 가장 먼저 묻는 두 가지라 같은 줄에서 잰다.
    """
    actor = _login(client)
    tel = "010-7500-0008"
    order = _order(tel=tel)
    link = _link(order_no="N-GT-8", amount=610_000, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)
    _trash(order, actor=actor, reason="고객 취소 확정",
           now=datetime.datetime(2026, 9, 6, 23, 41, 17))

    body = _pane(client, int(link.id))

    assert TRASH_BLOCK_TEXT in body, "잠긴 이유를 title 에만 두면 마우스 없는 기기는 못 읽는다"
    assert '<div class="wb-ghost__dim">09-07 08:41 삭제 · 고객 취소 확정</div>' in body


def test_pane_header_is_silent_for_a_living_order(app, client, workbench_on):
    """음성 대조군 — 살아 있는 주문의 머리줄에는 휴지통 배지가 없다."""
    _login(client)
    tel = "010-7500-0006"
    order = _order(tel=tel)
    link = _link(order_no="N-GT-6", amount=520_000, order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert TRASH_BADGE not in body, "살아 있는 주문을 접혔다고 말했다"
