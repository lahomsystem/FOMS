"""협력사 희망 시공일 건수(PG 레인) — JSONB 경로 술어가 실 PostgreSQL(psycopg3 서버 바인딩)에서 도는지.

SQLite 레인(:mod:`tests.security.test_partner_request_count`)은 JSON 경로를 다르게 풀어 PG 전용 오류
(같은 경로 식이 SELECT · GROUP BY 에서 다른 인자로 갈라지는 것 등)를 못 잡는다. 사용자 결정 2026-10-28:
협력사는 주문 · 실측까지만 하고 시공은 우리가 한다 — 확정 전 희망일도 시공 건수에 든다.
"""

from __future__ import annotations

import datetime
import time

from sqlalchemy.orm import Session

import foms.services.orders.dashboard_control_tower as tower
from foms.services.partners.construction_calendar import partner_construction_calendar
from foms.services.partners.orders import create_partner_order
from foms.services.partners.schedule_request import pending_request_counts
from foms.web.shipment.dashboard import _partner_pending_orders
from models import Order, PartnerOrg, User

_DAY = "2031-03-04"
_TODAY = datetime.date(2031, 3, 1)


def _suffix() -> str:
    return str(int(time.time() * 1_000_000) % 10_000_000)


def _cell(cal, iso):
    return next(c for w in cal["weeks"] for c in w if c["iso"] == iso)


def test_partner_request_counts_on_pg(pg_session: Session) -> None:
    org = PartnerOrg(name=f"가나가구-{_suffix()}")
    pg_session.add(org)
    pg_session.flush()
    user = User(username=f"rc-{_suffix()}", password="pw-not-committed", name="가나 직원", role="PARTNER",
                team=None, is_active=True, partner_org_id=org.id, contact_phone="010-1111-2222")
    pg_session.add(user)
    pg_session.flush()
    order = create_partner_order(pg_session, user, org, {
        "customer_name": "홍길동", "customer_phone": "010-0000-0000", "address": "서울 1",
        "items": [{"product_name": "붙박이장"}],
        "requested_construction_date": _DAY, "requested_construction_time": "오후",
    })
    pg_session.flush()

    only_this = pg_session.query(Order).filter(Order.id == order.id)
    assert pending_request_counts(only_this, [_DAY, "2031-03-05"]) == {_DAY: 1}
    assert [(o.id, d) for o, d in _partner_pending_orders(only_this, [_DAY], None, False)] == [(order.id, _DAY)]

    month = tower.build_month_calendar(pg_session, None, "2031-03", today=_TODAY)
    assert _cell(month, _DAY)["construction"] >= 1
    day = tower.build_field_ops_for_day(pg_session, None, _DAY, today=_TODAY)
    row = next(r for r in day["rows"] if r["id"] == order.id)
    assert row["readiness_label"] == "협력사 희망 · 확정 대기" and row["time"] == "오후"
    assert _cell(partner_construction_calendar(pg_session, org.id, "2031-03", today=_TODAY), _DAY)["count"] >= 1
