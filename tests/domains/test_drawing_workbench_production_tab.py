"""생산 넘어간 주문의 도면 수정 D3 — 도면 작업실 '생산 중' 칸 · 상세 '공장 진행' 칸(설계서 2026-11-25 §2-1 · §2-2 · §7 · §10).

* 모집단(사장님 답 1 · Q1 · Q15): 생산 단계 전부 + 시공일이 오늘(KST)이거나 뒤이고 시공 방문이 안 열린 시공 대기. 시공일이 지난 것 ·
  시공을 시작한 것 · 시공일이 없는 시공 대기 · 그 밖 단계는 빠진다. 칸 숫자 = 그 사람 범위(내 것만 · 협력사 거르개)의 모집단 수.
* 정렬: ① 열린 요청(영업 · 공장, 요청 시각 오래된 것 먼저) ② 고치는 도면이 있는 주문 ③ 나머지 시공일 빠른 순(없음은 맨 뒤). ``sort=`` 가 이긴다.
* 상한: 요청 · 고치는 중 주문은 상한 없이 모두, 나머지만 1,000건 — 캡에 닿으면 목록 아래 "더 있는 N건은 안 보여요. 찾기로 찾아 주세요."
* 줄 값: 표시("수정 요청 · 영업" · "수정 요청 · 공장" · "도면 고치는 중") · 다음 액션 · 단계 낱말 · 공장 진행 요약(2공장이면 공장마다) · 대상 번호.
* 음성 대조군: 기본 목록 · 다른 칸 줄은 전과 같다(표시 · 진행 · 단계 낱말 없음, 생산 주문 안 섞임), 생산 아닌 주문 상세에는 '공장 진행' ·
  "생산 작업 시트 열기"가 없다. 시공 대기 상세는 "제작 완료"만, [수정 시작] 없음.

되돌리면 실패: 시공일 지난 시공 대기가 칸에 섞임 · 시공 시작한 주문이 남음 · 요청 주문이 캡에 잘림 · 정렬이 접수순 · 기본 목록에 생산 주문 ·
상세 버튼이 영업에게 보임. 이름 · 번호는 모두 지어낸 값이고 날짜는 오늘(KST)에서 센다.
"""
from __future__ import annotations

import datetime
import functools
import re

import pytest

import foms.web.drawing.workbench as workbench_routes
from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_workbench_read_model import count_workbench_tiles, fetch_production_tab_order_ids
from models import Order, PartnerOrg
from tests.support.drawing_fix_workbench_seed import (
    day,
    factory_request,
    key,
    login,
    make_order,
    make_user,
    put_mark,
    sales_request,
    start_construction,
)

ROW_ID = re.compile(r'class="form-check-input order-checkbox" value="(\d+)"')


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


@pytest.fixture
def drawer():
    return make_user("김도면", team="DRAWING")


def _ago(hours: int) -> str:
    return (now_utc_naive() - datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def _page(client, query: str = "status=PRODUCTION") -> str:
    res = client.get(f"/erp/drawing-workbench?{query}")
    assert res.status_code == 200
    return res.get_data(as_text=True)


def _ids(html: str) -> list[int]:
    return [int(x) for x in ROW_ID.findall(html)]


def _tile(html: str) -> int:
    return int(re.search(r'data-status="PRODUCTION"[^>]*>\s*<div class="erp-pro-pipeline__count">(\d+)</div>', html).group(1))


def _row(html: str, oid: int) -> str:
    start = html.index(f'order-checkbox" value="{oid}"')
    return html[html.rfind("<tr", 0, start):html.index("</tr>", start)]


def _base_query():
    return db_session.query(Order).filter(Order.active_filter(), Order.is_erp_order.is_(True))


# --- 모집단 ---------------------------------------------------------------------


def test_population_is_production_plus_construction_waiting_from_today(client, drawer):
    produce = make_order(stage="PRODUCTION", cdate=day(5))
    produce_no_date = make_order(stage="PRODUCTION", cdate=None)
    wait_today = make_order(stage="CONSTRUCTION", cdate=day(0))
    wait_later = make_order(stage="CONSTRUCTION", cdate=day(3))
    past = make_order(stage="CONSTRUCTION", cdate=day(-1))                # 시공일 지남 → 빠짐
    started = make_order(stage="CONSTRUCTION", cdate=day(2))
    start_construction(started)                                         # 시공 시작 → 빠짐
    no_date = make_order(stage="CONSTRUCTION", cdate=None)              # 시공일 없는 시공 대기 → 빠짐
    others = [make_order(stage=s, cdate=day(4)) for s in ("DRAWING", "CONFIRM", "CS", "COMPLETED")]
    expected = {produce, produce_no_date, wait_today, wait_later}

    got = fetch_production_tab_order_ids(_base_query(), today=day(0))
    assert set(got["order_ids"]) == expected and got["hidden"] == 0
    assert count_workbench_tiles(_base_query(), today=day(0))["production_count"] == 4

    login(client, drawer)
    html = _page(client)
    assert set(_ids(html)) == expected and _tile(html) == 4
    assert not {past, started, no_date, *others} & set(_ids(html))
    assert 'erp-pro-pipeline__stage--active" data-status="PRODUCTION"' in html.replace("\n", "")


def test_sort_requests_oldest_first_then_fixing_then_construction_date(client, drawer):
    rest_late = make_order(cdate=day(9), customer="한여름")
    rest_none = make_order(cdate=None, customer="윤봄")
    rest_soon = make_order(cdate=day(2), customer="서가을")
    fixing = make_order(cdate=day(30), customer="문바다", extra={"drawing_fix": {"fixing": {
        "sheet:s1": {"no": 2, "by_user_id": None, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"}}}})
    sales_new = make_order(cdate=day(40), status="RETURNED", history=[sales_request(_ago(1), targets=())], customer="정하늘")
    factory_old = make_order(cdate=day(50), customer="강가람", extra={"drawing_fix": {"requests": [
        factory_request(_ago(5), ["sheet:s2"], [3])]}})
    closed = make_order(cdate=day(1), customer="오솔길", extra={"drawing_fix": {"requests": [   # 반려 · 반영된 요청은 맨 위가 아님
        factory_request(_ago(9), ["sheet:s0"], [1], state="rejected"), factory_request(_ago(8), ["sheet:s0"], [1], state="done")]}})
    login(client, drawer)
    assert _ids(_page(client)) == [factory_old, sales_new, fixing, closed, rest_soon, rest_late, rest_none]
    by_id = _ids(_page(client, "status=PRODUCTION&sort=id"))              # sort= 가 이긴다(지금 규칙)
    assert by_id == sorted(by_id)


def test_requested_orders_are_never_cut_by_the_cap(client, drawer, monkeypatch):
    rest = [make_order(cdate=day(j)) for j in range(1, 5)]
    flagged = make_order(cdate=day(60), status="RETURNED", history=[sales_request(_ago(2))])
    fixing = make_order(cdate=None, extra={"drawing_fix": {"fixing": {"sheet:s0": {"no": 1, "by_name": "김도면", "at": ""}}}})
    got = fetch_production_tab_order_ids(_base_query(), today=day(0), cap=2)
    assert set(got["order_ids"]) == {flagged, fixing, rest[0], rest[1]} and got["hidden"] == 2

    monkeypatch.setattr(workbench_routes, "fetch_production_tab_order_ids",
                        functools.partial(fetch_production_tab_order_ids, cap=2))
    login(client, drawer)
    html = _page(client)
    assert _ids(html)[:2] == [flagged, fixing] and set(_ids(html)) == {flagged, fixing, rest[0], rest[1]}
    assert "더 있는 2건은 안 보여요. 찾기로 찾아 주세요." in html


def test_mine_and_partner_filters_keep_the_users_scope(client, drawer):
    other = make_user("오도면", team="DRAWING")
    mine = make_order(assignees=(drawer.id,))
    theirs = make_order(assignees=(other.id,))
    partner = PartnerOrg(name="가짜협력사")
    db_session.add(partner)
    db_session.commit()
    partner_id = partner.id
    order = db_session.get(Order, theirs)
    order.partner_org_id = partner_id
    db_session.commit()
    login(client, drawer)
    assert set(_ids(_page(client))) == {mine, theirs}
    html = _page(client, "status=PRODUCTION&mine=1")
    assert _ids(html) == [mine] and _tile(html) == 1
    html = _page(client, f"status=PRODUCTION&partner_org={partner_id}")
    assert _ids(html) == [theirs] and _tile(html) == 1


# --- 줄 값 ---------------------------------------------------------------------


def test_row_values_marks_next_action_stage_progress_and_targets(client, drawer):
    factory = make_order(cdate=day(7), customer="문바다", extra={"drawing_fix": {"requests": [
        factory_request(_ago(3), ["sheet:s2"], [3])]}})
    sales = make_order(cdate=day(3), customer="정하늘", status="RETURNED", factory2=("s1",),
                       history=[{**sales_request(_ago(2), targets=[]), "target_drawing_keys": []}])
    fixing = make_order(4, cdate=day(9), customer="서가을", extra={"drawing_fix": {"fixing": {
        "sheet:s1": {"no": 2, "by_user_id": None, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"}}}})
    plain = make_order(cdate=day(8), customer="윤봄")
    waiting = make_order(2, stage="CONSTRUCTION", cdate=day(10), customer="한여름")
    for name in ("s0", "s1", "s2"):
        put_mark(factory, key(factory, name), "cut", "DONE")
    put_mark(factory, key(factory, "s0"), "edge", "NEED", name="박엣지")
    put_mark(sales, key(sales, "s0"), "cut", "DONE")
    login(client, drawer)
    html = _page(client)
    assert _ids(html) == [factory, sales, fixing, plain, waiting]

    row = _row(html, factory)
    assert "dw-req-row is-factory" in row and '<span class="dw-event-chip is-order-change">수정 요청 · 공장</span>' in row
    assert "공장 수정 요청 · 박반장 · 도면 3" in row and '<span class="dw-fix-target">도면 3</span>' in row
    assert '<span class="dw-stage-word">생산</span>' in row
    assert "재단 <b>3/3</b> · 엣지 0/3 · 조립 0/3 · 검수 0/3" in row        # 맡음(작업 중)은 완료로 안 셈

    row = _row(html, sales)
    assert '<span class="dw-event-chip is-revision">수정 요청 · 영업</span>' in row and "영업 수정 요청 · 이영업" in row
    assert '<em class="foms-fac foms-fac--1">1공장</em>재단 1/2' in row and '<em class="foms-fac foms-fac--2">2공장</em>재단 0/1' in row

    row = _row(html, fixing)
    assert "dw-fix-row" in row and '<span class="dw-event-chip is-transfer">도면 고치는 중</span>' in row
    assert "도면 2 고치는 중 · 김도면" in row and '<span class="dw-fix-target">도면 2</span>' in row

    row = _row(html, plain)
    assert "dw-prod-marks" not in row and "dw-fix-target" not in row
    assert '<td class="small dw-next-action is-assign">도면 담당자 지정 필요</td>' in row      # 표시 없는 줄은 지금 글 그대로
    assert "재단 0/3 · 엣지 0/3" in row and "dw-req-row" not in row

    row = _row(html, waiting)
    assert '<span class="dw-stage-word">시공 대기</span>' in row and "<b>제작 완료</b>" in row


# --- 음성 대조군 ----------------------------------------------------------------


def test_default_list_and_other_tiles_are_unchanged(client, drawer):
    produced = make_order(cdate=day(5))
    returned = make_order(cdate=day(6), status="RETURNED", history=[sales_request(_ago(1))])   # 기본 큐에도 있다('수정 요청됨')
    drawing = make_order(stage="DRAWING", status="PENDING", cdate=day(7))
    login(client, drawer)
    for query in ("", "status=RETURNED", "status=WAITING", "include_confirmed=1"):
        html = _page(client, query)
        assert produced not in _ids(html) or query == "include_confirmed=1"
        for marker in ("dw-stage-word", "dw-prod-prog", "dw-prod-marks", "dw-fix-target", "dw-req-row", "dw-fix-row",
                       "workbench-fix.css", "더 있는", '<option value="PRODUCTION"'):
            assert marker not in html, (query, marker)
        assert _tile(html) == 2                                          # 칸 숫자는 어디서나 같다
    default = _page(client, "")
    assert set(_ids(default)) == {returned, drawing}
    assert '<span class="badge bg-danger">수정 요청됨</span>' in _row(default, returned)


def test_detail_shows_factory_progress_only_for_production_and_waiting(client, drawer):
    produce = make_order(cdate=day(5), factory2=("s2",), extra={"drawing_fix": {"fixing": {
        "sheet:s1": {"no": 2, "by_user_id": None, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"}},
        "requests": [factory_request(_ago(2), ["sheet:s0"], [1])]}})
    put_mark(produce, key(produce, "s0"), "cut", "DONE")
    put_mark(produce, key(produce, "s1"), "edge", "NEED", name="박엣지")
    put_mark(produce, key(produce, "s2"), "cut", "BASIC")
    waiting = make_order(2, stage="CONSTRUCTION", cdate=day(5))
    drawing = make_order(stage="DRAWING", status="PENDING")
    login(client, drawer)
    html = client.get(f"/erp/drawing-workbench/{produce}").get_data(as_text=True)
    assert "공장 진행" in html and "생산 작업 시트 열기" in html and f'href="/erp/production/sheet/{produce}"' in html
    assert "재단 완료 · 김재단" in html and "엣지 작업 중 · 박엣지" in html and "재단 기본" in html and "조립 미정" in html
    assert "도면 고치는 중 · 김도면 · 11/25 14:10" in html and "수정 요청 · 공장" in html
    assert html.count('data-dwp-act="start"') == 2 and html.count('data-dwp-act="stop"') == 1
    assert 'data-confirm="도면 1을 고치는 중으로 표시할까요? 공장에서 도면 1만 작업이 막혀요."' in html
    assert '<em class="foms-fac foms-fac--2">2공장</em>' in html and "workbench-drawing-fix.js" in html

    made = client.get(f"/erp/drawing-workbench/{waiting}").get_data(as_text=True)
    assert "공장 진행" in made and made.count(">제작 완료</span>") == 2 and "data-dwp-act" not in made
    assert "생산 작업 시트 열기" in made

    other = client.get(f"/erp/drawing-workbench/{drawing}").get_data(as_text=True)
    for marker in ("공장 진행", "생산 작업 시트 열기", "data-dwp", "workbench-drawing-fix.js", "dwp-table"):
        assert marker not in other, marker


def test_detail_buttons_follow_the_server_predicate(client, drawer):
    oid = make_order(cdate=day(5))
    sales = make_user("이영업", team="SALES")
    login(client, sales)
    html = client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True)
    assert "공장 진행" in html and "data-dwp-act" not in html and "workbench-drawing-fix.js" not in html


def test_population_sql_is_the_same_meaning_on_postgresql():
    """운영은 PostgreSQL — 요청 · 고치는 중 후보는 JSONB ``?`` 대신 ``->>`` NULL 여부(SQLite 시험과 같은 뜻), 시공 시작은 NOT EXISTS."""
    from sqlalchemy.dialects import postgresql

    from foms.services.drawing_workbench_read_model import _production_flagged_filter, build_production_tab_filter

    flagged = str(_production_flagged_filter().compile(dialect=postgresql.dialect()))
    population = str(build_production_tab_filter(day(0)).compile(dialect=postgresql.dialect()))
    assert "->>" in flagged and " ? " not in flagged and "?|" not in flagged
    assert "orders.erp_stage_code IN" in population and "NOT (EXISTS (SELECT" in population
    assert "order_construction_attempts.is_current IS true" in population


def test_factory_made_shows_at_row_end_and_counts_as_done(client, drawer):
    """그 공장이 제작 완료면 상세 줄 끝 "2공장 제작 완료", 목록 요약에서 그 공장 장은 모든 파트 완료로 센다."""
    from tests.support.production_factory_seed import set_factory_done

    oid = make_order(3, cdate=day(5), factory2=("s2",))
    set_factory_done(oid, 2, [key(oid, "s2")])
    login(client, drawer)
    detail = client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True)
    assert '<span class="dwp-made"><em class="foms-fac foms-fac--2">2공장</em> 제작 완료</span>' in detail
    assert detail.count("dwp-made") == 1
    row = _row(_page(client), oid)
    assert ('<em class="foms-fac foms-fac--2">2공장</em>재단 <b>1/1</b> · 엣지 <b>1/1</b> · 조립 <b>1/1</b> · 검수 <b>1/1</b>'
            in row)
    assert '<em class="foms-fac foms-fac--1">1공장</em>재단 0/2' in row
