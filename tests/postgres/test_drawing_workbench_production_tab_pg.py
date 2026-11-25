"""도면 작업실 '생산 중' 칸 SQL 실 PostgreSQL 계약 (PGTEST-00 lane, 설계서 2026-11-25 §2-1 · §7 · D3 검토 6).

SQLite 레인은 JSON 경로 · 스칼라 하위 질의 · ``IS NULL`` 정렬을 PostgreSQL 과 다르게 그린다. 여기서 운영과 같은 방언으로 돌려
뜻이 같은지 고정한다:

1. 모집단 — 생산 전부 + 시공일이 오늘이거나 뒤이고 시공 방문이 안 열린 시공 대기(지남 · 시작 · 다른 단계는 빠짐).
2. 차례 — ① 요청 · 고치는 중 후보(RETURNED 또는 ``drawing_fix`` 칸 — ``->>`` NULL 여부) 먼저 ② 나머지 시공일 순(없음은 맨 뒤).
3. 상한 — ② 만 잘리고 ① 은 안 잘린다, 숨은 수 = 모집단 − 보인 줄.
4. 칸 숫자 — 하이드레이트 문장에 실은 스칼라 하위 질의(바깥과 안 묶임)가 모집단 수와 같고, 줄이 없을 때의 한 번 세기도 같다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 이름은 지어낸 값, 날짜는 오늘(KST)에서 센다.
"""
from __future__ import annotations

import datetime

from foms.services.datetime_kst import get_today_kst
from foms.services.drawing_workbench_read_model import fetch_production_tab_order_ids, hydrate_with_production_count
from models import Order, OrderConstructionAttempt


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def _order(session, stage: str, cdays, **sd_extra) -> int:
    order = Order(received_date=_day(-30), customer_name="가짜고객", phone="010-0000-0000", address="가짜시", product="가짜장",
                  status=stage, is_erp_order=True, erp_stage_code=stage,
                  erp_construction_date=_day(cdays) if cdays is not None else None,
                  structured_data={"workflow": {"stage": stage}, "drawing_status": "CONFIRMED", **sd_extra})
    session.add(order)
    session.flush()
    return order.id


def _seed(session) -> dict[str, int]:
    ids = {
        "prod_late": _order(session, "PRODUCTION", 9), "prod_none": _order(session, "PRODUCTION", None),
        "fixing": _order(session, "PRODUCTION", 40, drawing_fix={"fixing": {"sheet:s1": {"no": 2}}}),
        "returned": _order(session, "생산", 50, drawing_status="RETURNED"),
        "wait_today": _order(session, "CONSTRUCTION", 0), "wait_later": _order(session, "시공", 2),
        "past": _order(session, "CONSTRUCTION", -1), "started": _order(session, "CONSTRUCTION", 1),
        "drawing": _order(session, "DRAWING", 5), "cs": _order(session, "CS", 5),
    }
    session.add(OrderConstructionAttempt(order_id=ids["started"], status="IN_PROGRESS", is_current=True))
    session.flush()
    return ids


def _query(session):
    return session.query(Order).filter(Order.active_filter(), Order.is_erp_order.is_(True))


def test_population_order_and_count_match_on_postgresql(pg_session):
    ids = _seed(pg_session)
    got = fetch_production_tab_order_ids(_query(pg_session), today=_day(0))
    assert got["hidden"] == 0
    assert got["order_ids"] == [ids["fixing"], ids["returned"], ids["wait_today"], ids["wait_later"], ids["prod_late"],
                                ids["prod_none"]]
    orders, count = hydrate_with_production_count(_query(pg_session), got["order_ids"], today=_day(0))
    assert [o.id for o in orders] == got["order_ids"] and count == 6
    assert hydrate_with_production_count(_query(pg_session), [], today=_day(0)) == ([], 6)          # 빈 큐 — 숫자만 한 번
    orders, count = hydrate_with_production_count(_query(pg_session), [ids["drawing"]], today=_day(0))
    assert [o.id for o in orders] == [ids["drawing"]] and count == 6                               # 칸 숫자는 줄 id 와 무관


def test_cap_cuts_only_the_rest_on_postgresql(pg_session):
    ids = _seed(pg_session)
    got = fetch_production_tab_order_ids(_query(pg_session), today=_day(0), cap=2)
    assert got["order_ids"] == [ids["fixing"], ids["returned"], ids["wait_today"], ids["wait_later"]] and got["hidden"] == 2
