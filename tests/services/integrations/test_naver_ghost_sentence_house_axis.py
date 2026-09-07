# -*- coding: utf-8 -*-
"""유령 폐기 문장이 **집 수와 상품주문 수를 한 통에 세던** 자리 (2026-09-07).

취소 뒤 재결제가 들어온 주문에서 화면은 `14건 중 9건만 취소됐습니다` 라고 말했다.
실제로는 9건이 **옛 집**(취소된 집)의 상품주문이고 5건이 **지금 받은 새 결제**였다.
링크(상품주문) 수를 한 통에 세니 담당자가 읽는 문장이 사실이 아니었다 — "아직 절반이
안 취소됐다"로 읽히지만, 취소돼야 할 집은 이미 전부 취소돼 있었다.

여기서 못박는 것 셋:

1. 세 갈래가 각각 **자기 축의 문장**을 낸다 — 지금 집이 죽었는가, 살아 있는가,
   집을 특정할 수 없는가.
2. **한 문장 안에서 단위를 섞지 않는다** — 집 축 문장에는 `건 중` 이 없고,
   상품주문 축 문장에는 `집 중` 이 없다.
3. `can_discard` · `applicable` · `discard_needs_reason` 은 세 갈래 전부에서 그대로다.
   이번 변경은 **문장뿐**이다.
"""
from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.ghost_orders import judge_order_discard
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order

# 화면 낱말 — 여기서만 적고 단언은 이 상수를 쓴다.
HERE_ALIVE_HEAD = "지금 보고 있는 이 집은 살아 있는 결제입니다"
ONLY_THIS_HOUSE = "이 집만 취소됐고"
HOUSE_UNIT = "집 중"      # 집 축 문장에만 나온다
LINK_UNIT = "건 중"       # 상품주문 축 문장에만 나온다
PRODUCT_ORDER_UNIT = "상품주문 "

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


def _order(*, status: str = "RECEIVED", tel: str) -> Order:
    """ERP 주문 1건."""
    order = Order(received_date="2026-08-13", customer_name=f"집축{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 1 101호",
                  product="붙박이장", status=status, payment_amount=0, is_erp_order=True)
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, amount: int, order_id: int, tel: str, claim: str = "",
          relation: str = "NEW", address: str = "서울 강남구 1") -> ExternalOrderLink:
    """그 주문에 붙은 상품주문 1줄. 집(묶음키)은 주문번호·전화·주소가 가른다."""
    product_order = {
        "productOrderId": f"PO-GH-{_uid()}",
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": address, "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel}, "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=product_order["productOrderId"],
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED", relation=relation, order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _two_dead_one_alive(tel: str) -> tuple[Order, str, str]:
    """취소된 집 2개(각 상품주문 2건) + 살아 있는 새 결제 집 1개.

    운영에서 문제가 난 모양 그대로다 — 옛 집들이 통째로 취소되고 새 결제가 하나 붙었다.

    Returns:
        ``(주문, 살아 있는 집 키, 취소된 집 하나의 키)``.
    """
    order = _order(tel=tel)
    order_id = int(order.id)
    dead = _link(order_no="N-HX-A", amount=300_000, claim="CANCEL_DONE",
                 order_id=order_id, tel=tel)
    _link(order_no="N-HX-A", amount=120_000, claim="CANCEL_DONE", order_id=order_id, tel=tel)
    _link(order_no="N-HX-B", amount=250_000, claim="CANCEL_DONE", order_id=order_id, tel=tel)
    _link(order_no="N-HX-B", amount=110_000, claim="CANCEL_DONE", order_id=order_id, tel=tel)
    alive = _link(order_no="N-HX-C", amount=1_082_140, order_id=order_id, tel=tel,
                  relation="REPAY")
    return order, alive.group_key, dead.group_key


def test_says_this_house_only_when_the_viewed_house_is_dead(app):
    """(a) 지금 보는 집이 취소된 집 — 살아 있는 다른 집을 이름으로 짚는다."""
    tel = "010-7600-0001"
    order = _order(tel=tel)
    dead = _link(order_no="N-HX-1", amount=300_000, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)
    _link(order_no="N-HX-1-ADD", amount=1_082_140, order_id=int(order.id), tel=tel,
          relation="ADDON", address="서울 서초구 9")

    view = judge_order_discard(db_session, int(order.id), group_key=dead.group_key)

    assert ONLY_THIS_HOUSE in view["discard_block"]
    assert HOUSE_UNIT not in view["discard_block"], "집 수를 셀 자리가 아닌데 셌다"


def test_names_the_viewed_house_as_alive_when_it_is_the_new_payment(app):
    """(b) **핵심 회귀** — 지금 보는 집이 살아 있는 새 결제면 그렇게 말한다.

    이 갈래가 통째로 빠져 있어서 (c) 로 떨어졌고, 그래서 문장이 링크 수를 한 통에 셌다.
    """
    order, alive_key, _dead_key = _two_dead_one_alive("010-7600-0002")

    view = judge_order_discard(db_session, int(order.id), group_key=alive_key)

    block = view["discard_block"]
    assert block.startswith(HERE_ALIVE_HEAD), f"다른 갈래로 떨어졌다: {block}"
    assert "3집 중 2집이 취소됐고, 이 집을 포함한 1집이 살아 있습니다" in block
    assert LINK_UNIT not in block, f"집 축 문장에 상품주문 수를 섞었다: {block}"
    assert view["can_discard"] is False
    assert view["applicable"] is True


def test_falls_back_to_product_order_counts_without_a_group_key(app):
    """(c) 집을 특정할 수 없으면 **상품주문 축**으로 말한다 — 단위를 밝힌다."""
    order, _alive_key, _dead_key = _two_dead_one_alive("010-7600-0003")

    view = judge_order_discard(db_session, int(order.id))

    block = view["discard_block"]
    assert PRODUCT_ORDER_UNIT in block, "무엇을 5건이라 세는지 문장이 안 밝혔다"
    assert "상품주문 5건 중 4건만 취소됐습니다" in block
    assert HOUSE_UNIT not in block, "집을 모르는데 집 수를 셌다"


def test_partial_cancel_inside_one_house_speaks_in_product_orders(app):
    """(c) 집 **하나** 안에서만 부분 취소 — 집 축으로 말할 사실이 없다.

    이때 취소된 집은 0개다. 집 축으로 말하면 `1집 중 0집이 취소됐고` 라는 헛소리가 되고,
    사실은 링크 축에 있다.
    """
    tel = "010-7600-0004"
    order = _order(tel=tel)
    dead = _link(order_no="N-HX-4", amount=300_000, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)
    _link(order_no="N-HX-4", amount=200_000, order_id=int(order.id), tel=tel)

    view = judge_order_discard(db_session, int(order.id), group_key=dead.group_key)

    block = view["discard_block"]
    assert "상품주문 2건 중 1건만 취소됐습니다" in block
    assert HOUSE_UNIT not in block, "취소된 집이 0개인데 집 수 문장을 냈다"


def test_the_verdict_axis_is_untouched_across_all_three_branches(app):
    """경계 못박기 — 문장을 세 갈래로 갈랐어도 판정 3종은 한 글자도 안 움직인다."""
    order, alive_key, dead_key = _two_dead_one_alive("010-7600-0005")
    order_id = int(order.id)

    branches = [judge_order_discard(db_session, order_id, group_key=alive_key),
                judge_order_discard(db_session, order_id, group_key=dead_key),
                judge_order_discard(db_session, order_id)]

    for view in branches:
        assert view["applicable"] is True
        assert view["can_discard"] is False, "살아 있는 집이 붙은 주문이 열렸다"
        assert view["discard_needs_reason"] is False

    # 음성 대조군 — 전부 취소·확정 주문은 문장 없이 그대로 열린다.
    control_tel = "010-7600-0006"
    control = _order(tel=control_tel)
    _link(order_no="N-HX-6", amount=558_400, claim="CANCEL_DONE",
          order_id=int(control.id), tel=control_tel)

    control_view = judge_order_discard(db_session, int(control.id))

    assert control_view["can_discard"] is True
    assert control_view["discard_block"] == ""
