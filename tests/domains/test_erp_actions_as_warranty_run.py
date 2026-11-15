"""AS 접수 제안 실행 — 무상 AS 는 시공일로부터 1년(사용자 결정 D224 · D235 · 접목판 점검 2차 w6-07).

완료 기준: 승인 창이 '무상 기간 지남'이라 말한 주문은 실제 접수 기록도 '미정'(사람이 정한다)으로 들어간다 — 지난 주문을
'무상 추정'으로 쌓지 않는다. 시공일을 모르면 '미정', 1년 안이면 지금처럼 '무상'. 합성 주문만 쓴다.
"""

from __future__ import annotations

import datetime

import pytest

import foms.api.erp_action_runners as api_runners
from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import Order
from tests.domains.test_erp_actions_runners import _admin, _order, _req


def _billing(order_id: int) -> str:
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    return ((saved.structured_data or {}).get("shipment") or {}).get("as_billing", {}).get("type")


@pytest.mark.parametrize("days_ago, want", [(30, "free"), (366, "undecided"), (3 * 365, "undecided"), (None, "undecided")])
def test_register_as_writes_billing_by_the_free_period(app, days_ago, want):
    admin = _admin()
    construction = None
    if days_ago is not None:
        day = get_today_kst() - datetime.timedelta(days=days_ago)
        construction = (day.isoformat(), "오전")
    order = _order("COMPLETED", construction=construction)
    with app.test_request_context("/api/erp-actions/proposals/41/approve", method="POST"):
        out = api_runners.RUNNERS["register_as"](db_session, _req(order, "register_as", {"as_content": "합성 내용"}, admin))
    assert out.status == "executed"
    assert _billing(order.id) == want
