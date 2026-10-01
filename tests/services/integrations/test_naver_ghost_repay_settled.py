# -*- coding: utf-8 -*-
"""유령 주문 '재결제 받음 처리' — 손으로 끝내기 · 되돌리기 (2026-10-01).

네이버 취소 뒤 회사 계좌로 받은 주문은 재결제가 네이버 큐에 안 들어와 '재결제 예정'
표시가 저절로 풀리지 않는다(#5374). 사용자 결정 2026-10-01:

1. 재결제 예정 표시가 있는 주문만, 메모를 적어야 끝낼 수 있다.
2. 끝낸 주문은 띠에서 빠지고, pane 에 기록과 되돌리기가 남는다.
3. 되돌리면 '재결제 기다림' 으로 띠에 다시 선다.
"""
from __future__ import annotations

import pathlib

from db import db_session
from foms.services.integrations.naver_commerce.ghost_orders import (
    find_ghost_orders,
    judge_order_discard,
    read_repay_expected,
    read_repay_settled,
    set_repay_expected,
    set_repay_settled,
)
from models import Order
from tests.services.integrations.naver_ghost_repay_helpers import (  # noqa: F401
    AT_SHAPE,
    BAND_TEMPLATE,
    PANE_TEMPLATE,
    WORKBENCH_JS,
    _ghost,
    _login,
    _user,
    workbench_on,
)

SETTLED_PATH = "/admin/naver-ingest/ghost/{}/repay-settled"


def _band_ids() -> set[int]:
    return {row["order_id"] for row in find_ghost_orders(db_session, limit=1000)["rows"]}


def test_a_settled_order_leaves_the_band_and_the_pane_keeps_it(app):
    """끝낸 주문은 띠에서 빠지고, pane 은 기록을 싣고 모집단 밖이라고 말한다."""
    order = _ghost(tel="010-7915-0001", order_no="N-RS-1")
    set_repay_expected(order, actor_user_id=1, note="계좌로 받기로 함")
    set_repay_settled(order, actor_user_id=1, actor_name="김담당", note="10-01 계좌 입금")
    db_session.commit()

    assert int(order.id) not in _band_ids()
    view = judge_order_discard(db_session, int(order.id))
    assert view["repay_settled"]["note"] == "10-01 계좌 입금"
    assert AT_SHAPE.match(view["repay_settled"]["at"])
    assert view["in_ghost_band"] is False


def test_a_settled_record_without_the_mark_does_not_hide_the_row(app):
    """음성 대조군 — 표시를 푼 주문이 옛 기록 때문에 숨으면 안 된다."""
    order = _ghost(tel="010-7915-0002", order_no="N-RS-2")
    set_repay_settled(order, actor_user_id=1, note="옛 기록")
    db_session.commit()

    assert int(order.id) in _band_ids()
    assert judge_order_discard(db_session, int(order.id))["repay_settled"] is None


def test_the_route_settles_and_reverts(app, client, workbench_on):
    """끝내면 띠에서 빠지고, 되돌리면 표시가 그대로 남은 채 띠로 돌아온다."""
    _login(client)
    order = _ghost(tel="010-7915-0003", order_no="N-RS-3")
    order_id = int(order.id)
    set_repay_expected(order, actor_user_id=1)
    db_session.commit()

    on = client.post(SETTLED_PATH.format(order_id),
                     json={"settled": True, "note": "10-01 계좌 입금 오해진"})
    assert on.status_code == 200, on.get_data(as_text=True)
    assert on.get_json()["data"]["repay_settled"]["by_name"]
    db_session.expire_all()
    assert order_id not in _band_ids()

    off = client.post(SETTLED_PATH.format(order_id), json={"settled": False})
    assert off.status_code == 200, off.get_data(as_text=True)
    assert off.get_json()["data"]["repay_settled"] is None
    db_session.expire_all()
    reverted = db_session.get(Order, order_id)
    assert read_repay_settled(reverted) is None
    assert read_repay_expected(reverted) is not None, "되돌리기가 재결제 예정 표시까지 지웠다"
    assert order_id in _band_ids()


def test_the_route_needs_the_mark_first(app, client, workbench_on):
    """재결제 예정 표시가 없는 주문은 끝낼 수 없다."""
    _login(client)
    order = _ghost(tel="010-7915-0004", order_no="N-RS-4")

    response = client.post(SETTLED_PATH.format(int(order.id)),
                           json={"settled": True, "note": "계좌 입금"})

    assert response.status_code == 400
    db_session.expire_all()
    assert read_repay_settled(db_session.get(Order, int(order.id))) is None


def test_the_route_needs_a_note(app, client, workbench_on):
    """메모 없이는 끝낼 수 없다 — 공백만 있는 메모도 막는다."""
    _login(client)
    order = _ghost(tel="010-7915-0005", order_no="N-RS-5")
    set_repay_expected(order, actor_user_id=1)
    db_session.commit()

    response = client.post(SETTLED_PATH.format(int(order.id)),
                           json={"settled": True, "note": "   "})

    assert response.status_code == 400
    db_session.expire_all()
    assert read_repay_settled(db_session.get(Order, int(order.id))) is None


def test_the_route_is_closed_when_the_gate_is_off(app, client):
    """게이트가 꺼져 있으면 라우트도 닫힌다."""
    _login(client)
    order = _ghost(tel="010-7915-0006", order_no="N-RS-6")

    response = client.post(SETTLED_PATH.format(int(order.id)),
                           json={"settled": True, "note": "x"})

    assert response.status_code == 403


def test_the_buttons_are_wired():
    """띠·pane 버튼과 JS 핸들러가 같은 id 와 라우트를 문다."""
    band = pathlib.Path(BAND_TEMPLATE).read_text(encoding="utf-8")
    pane = pathlib.Path(PANE_TEMPLATE).read_text(encoding="utf-8")
    js = pathlib.Path(WORKBENCH_JS).read_text(encoding="utf-8")
    assert 'id="wb-ghost-repay-settled"' in band and 'data-settled="1"' in band
    assert 'data-settled="0"' in pane and "ghost_discard.repay_settled" in pane
    assert "'wb-ghost-repay-settled': submitGhostRepaySettled" in js
    assert "/repay-settled" in js
