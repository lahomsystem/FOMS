"""태블릿 시공 탭 첫 화면 읽기 모델(설계서 tablet-production-ui §13.4 · P13-2, 결정 D41 · D42).

대조군: 지금 시공 목록(접수 최신순 50건)은 오래 전 접수한 오늘 시공 집을 놓친다 — 같은 자료로 새 읽기 모델은 잡는다.
쿼리는 A(날짜별 집 수 — 구조 자료를 읽지 않음) · B(고른 날 + 미리 볼 날 줄) 두 번뿐이다.
"""
from __future__ import annotations

import datetime
import itertools
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from db import db_session, engine
from foms.services.construction import tablet_first as tf
from foms.services.construction_read_model import (
    CONSTRUCTION_BROWSE_CAP,
    apply_construction_list_scope_filter,
    paginate_construction_orders,
)
from foms.services.sales_commission.settings import load_settings, save_freelancer
from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet
from models import Order, OrderFreelancerLink, OrderScheduleDate
from tests.domains.test_auth_finance import _make_user

TODAY = datetime.date(2026, 11, 12)  # 목요일
_seq = itertools.count(1)
WORKERS = [{"name": "최우진", "capacity": 10, "off_dates": []},
           {"name": "김태호", "capacity": 10, "off_dates": []}]


def _d(n: int) -> str:
    return (TODAY + datetime.timedelta(days=n)).isoformat()


def _order(customer: str, *, day: str | None, stage: str = "CONSTRUCTION", status: str = "CONSTRUCTION",
           workers: list[str] | None = None, manager: str = "영업담당", created: datetime.datetime | None = None,
           extra: dict | None = None, osd_rows: int = 1) -> int:
    sd = {
        "parties": {"manager": {"name": manager}, "customer": {"name": customer}, "orderer": {"name": "라홈"}},
        "workflow": {"stage": stage},
        "items": [{"product_name": "여닫이 붙박이장 120W", "spec_width": "3000", "quantity": 1},
                  {"product_name": "신발장", "spec_width": "900", "quantity": 1}],
        "site": {"address_full": "경기도 성남시 분당구 정자동 느티마을 301동"},
        "schedule": {"construction": {"date": day, "time": "오후"}} if day else {},
        "shipment": {"construction_workers": workers or []},
        **(extra or {}),
    }
    order = Order(received_date=_d(0), customer_name=customer, phone="010-0000-0000",
                  address="경기도 성남시 분당구 정자동", product="장", status=status, manager_name=manager,
                  is_erp_order=True, structured_data=sd, erp_stage_code=stage)
    if created is not None:
        order.created_at = created
    db_session.add(order)
    db_session.flush()
    if day:
        for i in range(osd_rows):  # 같은 날 일정 줄이 여럿(주문 + 품목)이어도 집은 하나
            db_session.add(OrderScheduleDate(order_id=order.id, kind="construction", date=day,
                                             source="beta_schedule" if i == 0 else "beta_item", item_index=i or None))
    db_session.commit()
    return order.id


def _first(user=None, *, mine=False, **kw):
    return tf.build_tablet_first(db_session, user=user, mine_only=mine, worker_settings=WORKERS, today=TODAY, **kw)


def _ids(result) -> dict[str, list[int]]:
    return {s["date"]: [r["id"] for g in s["groups"] for r in g["rows"]] for s in result["sections"]}


def _admin():
    return _make_user("ADMIN", "CS")


@pytest.fixture()
def db(app):
    yield db_session


def test_old_received_today_house_counted_where_current_list_misses_it(db) -> None:
    """대조군: 오래 전 접수한 오늘 시공 집 1 + 최근 접수한 먼 날 집 50 — 지금 목록 1쪽(50건)엔 없고 새 모델엔 있다."""
    old = _order("오래된고객", day=_d(0), created=datetime.datetime(2026, 9, 20, 9, 0))
    for i in range(50):
        _order(f"최근고객{i}", day=_d(9), created=datetime.datetime(2026, 11, 11, 9, 0) + datetime.timedelta(minutes=i))
    base = db.query(Order).filter(Order.dashboard_active_filter(days=60), Order.is_erp_order.is_(True))
    _, _, _, page = paginate_construction_orders(apply_construction_list_scope_filter(base, ""), page=1,
                                                 total_cap=CONSTRUCTION_BROWSE_CAP)
    assert old not in [o.id for o in page]  # 지금 3분할 '오늘' 칩이 고르는 모집단 — 결함 재현
    result = _first(_admin())
    assert result["selected"] == _d(0) and result["selected_count"] == 1
    assert _ids(result)[_d(0)] == [old]
    assert result["days"][9]["count"] == 50 and result["next_date"] == _d(9)
    assert len(_ids(result)[_d(9)]) == 50  # 미리 볼 날


def test_count_scope_production_in_measure_out_as_out_deleted_out(db) -> None:
    """D42 ①: 생산 단계 집은 넣고 '생산중', 생산 전 단계 · AS · 지운 주문은 뺀다. 같은 날 일정 줄 둘이어도 1집."""
    cons = _order("시공고객", day=_d(1), osd_rows=2)
    prod = _order("생산고객", day=_d(1), stage="PRODUCTION", status="PRODUCTION")
    _order("실측고객", day=_d(1), stage="MEASURE", status="MEASURE")
    _order("AS고객", day=_d(1), stage="AS", status="AS_RECEIVED")
    gone = _order("지운고객", day=_d(1))
    o = db.get(Order, gone)
    o.deleted_at = datetime.datetime(2026, 11, 1)
    db.commit()
    result = _first(_admin(), selected=_d(1))
    assert result["selected_count"] == 2
    rows = {r["id"]: r for s in result["sections"] for g in s["groups"] for r in g["rows"]}
    assert set(rows) == {cons, prod}
    assert rows[prod]["stage"] == "생산중" and rows[prod]["in_production"] is True
    assert rows[prod]["packing_text"] == "생산중"
    assert rows[cons]["stage"] == "시공대기" and rows[cons]["packing_text"] == "포장 전"


def test_construction_team_sees_own_houses_only_and_starts_on_own_name(db) -> None:
    """시공팀(mine 강제): 시공자 이름에 내 이름이 든 집만 센다 · 처음 칸 = 내 이름(설정 명단에 있을 때)."""
    me = _make_user("STAFF", "CONSTRUCTION")
    me.name = "최우진"
    db.commit()
    mine = _order("내집", day=_d(0), workers=["최우진"])
    _order("남의집", day=_d(0), workers=["김태호"])
    _order("빈집", day=_d(0))
    result = _first(me, mine=True)
    assert result["selected_count"] == 1 and _ids(result)[_d(0)] == [mine]
    assert result["worker"] == "최우진"
    everyone = _first(me, mine=True, worker="")  # 전체 칸을 골라도 시공팀은 내 집만(칸 거름이 가리지 않게)
    assert everyone["worker"] == "" and everyone["selected_count"] == 1 and _ids(everyone)[_d(0)] == [mine]
    staff = _first(_admin())  # 대조군: 관리자 = 회사 전체, 처음 칸 = 전체
    assert staff["selected_count"] == 3 and staff["worker"] == ""


def test_worker_filter_includes_second_worker_and_empty_worker_means_all(db) -> None:
    lead = _order("둘이간집", day=_d(0), workers=["최우진", "박성민"])
    _order("혼자간집", day=_d(0), workers=["김태호"])
    picked = _first(_admin(), worker="박성민")
    assert picked["worker"] == "박성민" and _ids(picked)[_d(0)] == [lead]
    group = picked["sections"][0]["groups"][0]
    assert group["key"] == "최우진" and group["names"] == ["최우진", "박성민"]
    assert _first(_admin(), worker="")["selected_count"] == 2


def test_freelancer_scope_linked_orders_only_and_no_company_roster(db) -> None:
    fl = _make_user("STAFF", "SALES")
    save_freelancer(db, fl.id, {"match_name": f"프리{next(_seq)}", "start_month": "2020-01", "tax_type": "NONE",
                                "active": True}, base_version=load_settings(db)[0], actor_user_id=None)
    db.commit()
    own = _order("프리내집", day=_d(0), workers=["외주기사"])
    _order("프리남의집", day=_d(0), workers=["최우진"])
    db.add(OrderFreelancerLink(order_id=own, user_id=fl.id, relation="MANAGER_PRIMARY"))
    db.commit()
    result = _first(SimpleNamespace(id=fl.id, username=fl.username, name=fl.name, role="STAFF", team="SALES"),
                    mine=True, is_freelancer=True)
    assert result["selected_count"] == 1 and _ids(result)[_d(0)] == [own]
    assert result["worker_options"] == ["외주기사"]  # 회사 명단(최우진 · 김태호) 없음


def test_zero_day_points_to_next_day_and_preview_only(db) -> None:
    nxt = _order("다음집", day=_d(4))
    result = _first(_admin(), selected=_d(3))
    assert result["selected_count"] == 0 and result["next_date"] == _d(4) and result["next_count"] == 1
    assert [s["date"] for s in result["sections"]] == [_d(4)] and result["sections"][0]["preview"] is True
    assert _ids(result) == {_d(4): [nxt]}
    assert result["days"][0]["is_today"] and result["days"][3]["is_selected"]
    assert result["days"][2]["weekday_label"] == "토" and result["days"][2]["is_weekend"]


def test_cap_overflow_is_reported_not_silently_dropped(db, monkeypatch) -> None:
    for i in range(3):
        _order(f"캡고객{i}", day=_d(0))
    monkeypatch.setattr(tf, "DAY_ROWS_CAP", 2)
    sec = _first(_admin())["sections"][0]
    assert sec["count"] == 3 and sum(len(g["rows"]) for g in sec["groups"]) == 2 and sec["hidden"] == 1


def test_groups_colors_match_shipment_day_sheet_and_rows_sorted_by_time(db) -> None:
    """묶음 · 색 = 출고 build_tablet_day_sheet 그대로 · 묶음 안 = 시간 순 · 줄 칸 값."""
    late = _order("늦은집", day=_d(0), workers=["최우진"], extra={"shipment": {
        "construction_workers": ["최우진"], "construction_time": "14:00",
        "packing": {"items": [{"key": "a", "checked": True}, {"key": "b", "checked": False}]}}})
    early = _order("이른집", day=_d(0), workers=["최우진"], extra={"shipment": {
        "construction_workers": ["최우진"], "construction_time": "오전 8시",
        "packing": {"items": [{"key": "a", "checked": True}], "departed_at": "2026-11-12T07:40:00"}},
        "drawing_transfer_history": [{}, {}]})
    none_ = _order("빈집", day=_d(0))
    sec = _first(_admin())["sections"][0]
    assert [g["key"] for g in sec["groups"]] == ["", "최우진"]
    assert [r["id"] for r in sec["groups"][1]["rows"]] == [early, late]
    ref = build_tablet_day_sheet([db.get(Order, i) for i in (none_, early, late)], WORKERS, _d(0))
    assert [g["color_index"] for g in sec["groups"]] == [g["color_index"] for g in ref["groups"]]
    e, l_ = sec["groups"][1]["rows"]
    assert e["time_text"] == "오전 8시" and e["packing_text"] == "출발 07:40" and e["drawing_text"] == "전달본 v2"
    assert l_["packing_text"] == "포장 1/2" and l_["drawing_missing"] is True
    assert e["district"] == "분당구" and e["address_rest"].startswith("성남시 정자동")
    assert e["product"] == "여닫이 붙박이장 외 1" and e["units"] == 13.0 and e["agency"] == "라홈"
    blank = sec["groups"][0]["rows"][0]
    assert blank["time_text"] == "오후" and blank["time_plan"] is True


def test_two_queries_and_count_query_reads_no_structured_data(db) -> None:
    _order("하나", day=_d(0))
    _order("둘", day=_d(2))
    u = _admin()  # 요청 안의 로그인 사용자처럼 속성을 미리 읽어 둔 값(만료된 ORM 객체 다시 읽기를 세지 않게)
    user = SimpleNamespace(id=u.id, username=u.username, name=u.name, role="ADMIN", team="CS")
    seen: list[str] = []

    def _on(conn, cursor, statement, *a):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", _on)
    try:
        _first(user)
    finally:
        event.remove(engine, "before_cursor_execute", _on)
    assert len(seen) == 2, seen
    count_sql = seen[0].lower()
    assert "count(distinct" in count_sql and "group by" in count_sql
    assert "orders.structured_data" not in count_sql  # 바깥 주문 줄의 JSONB 를 풀지 않는다(초안 표식은 별칭 · 부분 색인)
    assert "order_schedule_dates.kind" in count_sql and "order_schedule_dates.date in" in count_sql
    assert "limit" in seen[1].lower()


def test_kind_pair_case_keeps_or_meaning_for_unpaired_kinds(db) -> None:
    """종류 짝을 CASE 한 식으로 바꿔도(계획 세우기 비용) 뜻은 옛 OR 와 같다 — AS 아님 = 시공일, AS = AS 방문일만.

    대조군: 짝이 안 맞는 줄(AS 아닌 집의 AS 방문일 · AS 집의 시공일)은 수에도 줄에도 없다. (상태 NULL 집은 짝 앞에서
    ``Order.active_filter()`` 의 ``status != 'DELETED'`` 가 이미 뺀다 — 옛 꼴도 같다.)
    """
    plain = _order("시공집", day=_d(0))
    visit = {"schedule": {"as_visit": {"date": _d(0)}}}  # AS 방문 일정 줄은 동기화가 구조 자료에서 만든다
    as_ok = _order("에이에스", day=None, stage="AS", status="AS_RECEIVED", extra=visit)
    plain_as_visit = _order("시공집방문일만", day=None, extra=visit)
    as_construction = _order("에이에스시공일만", day=_d(0), stage="AS", status="AS_RECEIVED")
    kinds = {(oid, k) for oid, k in db_session.query(OrderScheduleDate.order_id, OrderScheduleDate.kind)}
    assert {(as_ok, "as_visit"), (plain_as_visit, "as_visit"), (as_construction, "construction"),
            (plain, "construction")} <= kinds
    result = _first(_admin(), worker="")
    assert result["selected_count"] == 2
    assert sorted(_ids(result)[_d(0)]) == sorted([plain, as_ok])


def test_count_and_row_queries_use_case_kind_pair_not_cross_table_or(db) -> None:
    """쿼리 A · B 의 종류 짝은 CASE 한 식이다 — 두 표에 걸친 OR 로 되돌리면 PG 계획 세우기가 3배 넘게 는다(로컬 PG 17 실측)."""
    _order("하나", day=_d(0))
    user = SimpleNamespace(id=1, username="u", name="u", role="ADMIN", team="CS")
    seen: list[str] = []

    def _on(conn, cursor, statement, *a):
        seen.append(" ".join(statement.lower().split()))

    event.listen(engine, "before_cursor_execute", _on)
    try:
        _first(user)
    finally:
        event.remove(engine, "before_cursor_execute", _on)
    assert len(seen) == 2, seen
    for sql in seen:
        assert "case when (order_schedule_dates.kind = " in sql, sql
        assert "order_schedule_dates.kind = ? and" not in sql and "order_schedule_dates.kind = %(" not in sql.split("case when")[0]


def test_bad_date_falls_back_to_today() -> None:
    assert tf.parse_day("2026-02-30") is None and tf.parse_day("x") is None and tf.parse_day("2026-11-13") == "2026-11-13"
    assert tf.resolve_default_worker(None, login_names=[" 최우진 "], option_names=["최우진"]) == "최우진"
    assert tf.resolve_default_worker("", login_names=["최우진"], option_names=["최우진"]) == ""
