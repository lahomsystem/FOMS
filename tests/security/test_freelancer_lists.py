"""FCOMM-01 3단계 겹 3: 프리랜서 목록 강제 거르기 + 허용 화면 조각 전수 점검 계약(플랜 T16).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.1 · §6.3 겹 3 · §6.5, 검수 원장 A3 · A9 · A10.

* "내 주문" = 연결 표(order_freelancer_links) 하나. 담당 이름이 내 계정 이름과 같은 주문 · ``sales_assignee_user_ids``
  에 내 id 가 든 주문 · 퀘스트 담당 이름이 나인 주문은 **남의 주문**이다.
* 허용 목록의 목록 화면 · API 마다 내 고객명은 있고 남의 고객명은 없다 — ``?mine=0`` · ``?mine=`` · 쿠키 없음 ·
  ``tower_mine=0`` 모두.
* 실측 판: 그날 네이버 주문이 있어도 일괄 발송 띠가 안 뜬다. 모바일 홈 검색: "전체 이력에 N건 더" 없음,
  결과 0건이어도 이력 검색으로 안 보낸다.
* 숫자(달력 칸 · 오늘 요약 · 그날 목록 · 하단 배지)도 내 주문만 센다.
* 대조군(같은 모집단): 프리랜서 아닌 영업 직원 · 관리자는 전부 본다.
* 캐시 층마다 다른 사용자로 번갈아 그린다(대시보드 조각 캐시 · 배지 캐시 · 프리랜서로 지정한 직후).
모든 이름 · 숫자는 가짜 값이다.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from flask import g
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services import dashboard_counts
from foms.services.common import dashboard_cache
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_permissions import build_mine_sql_filter, is_order_related_to_user, mine_membership_clause
from foms.services.orders.dashboard_control_tower import build_field_ops_for_day, build_month_calendar
from foms.services.sales_commission.links import resync_freelancer_links
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, OrderFreelancerLink
from tests.domains.test_auth_finance import _login, _make_user
from tests.services.integrations.test_naver_bulk_dispatch_measurement_strip import _naver_measured_today
from tests.support.fragver_fake_redis import FakeRedis

MATCH = "가짜프리A"          # 프리랜서 설정의 맞출 이름(주문 담당 칸과 완전 일치하면 연결)
USER_NAME = "가짜영업"       # 프리랜서 계정 표시 이름 — 이 이름이 담당인 주문은 남의 주문이다
OWN = ("본인담당고객", "본인등록고객")
OWN_UNDATED = "본인미정고객"
OTHERS = ("남이름고객", "남배정고객", "남퀘스트고객", "남일반고객")
OTHER_UNDATED = "남미정고객"
NAVER = "네이버남고객"
LEGACY = "이력남고객"


def _today() -> str:
    return get_today_kst().isoformat()


def _order(customer: str, *, manager: str = "아무개", measure: bool = True, construction: bool = False,
           extra: dict | None = None, erp: bool = True) -> Order:
    today = _today()
    schedule = {}
    if measure:
        schedule["measurement"] = {"date": today}
    if construction:
        schedule["construction"] = {"date": today}
    sd = {"parties": {"manager": {"name": manager}, "customer": {"name": customer}, "orderer": {"name": "라홈"}},
          "schedule": schedule, "workflow": {"stage": "MEASURE"}, **(extra or {})}
    order = Order(received_date=today, customer_name=customer, phone="010-0000-0000", address="가짜시 가짜구",
                  product="가짜장", status="MEASURE", manager_name=manager, is_erp_order=erp, structured_data=sd,
                  erp_stage_code="MEASURE" if erp else None,
                  erp_measurement_date=today if measure else None, measurement_date=today if measure else None,
                  erp_construction_date=today if construction else None)
    db_session.add(order)
    db_session.commit()
    return order


def _designate(user, match: str, *, active: bool = True) -> None:
    save_freelancer(db_session, user.id, {"match_name": match, "start_month": "2020-01", "tax_type": "NONE",
                                          "active": active},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()


def _named_user(role: str, team: str, name: str) -> SimpleNamespace:
    """계정을 만들고 값만 담아 돌려준다(요청이 끝나면 세션이 닫혀 ORM 객체는 못 읽는다)."""
    user = _make_user(role, team)
    user.name = name
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=role, team=team, name=name, partner_org_id=None)


@pytest.fixture()
def world(app):
    """프리랜서 1 · 대조군(영업 직원 · 관리자) + 내 주문 3 · 남의 주문 5(이름 · 배정 id · 퀘스트 · 일반 · 미정)."""
    with dashboard_counts._cache_lock:
        dashboard_counts._cache.clear()  # 프로세스 캐시 — 앞 시험의 같은 id 배지가 남아 있을 수 있다
    fl = _named_user("STAFF", "SALES", USER_NAME)
    _designate(fl, MATCH)
    staff = _named_user("STAFF", "SALES", "다른영업")
    admin = _named_user("ADMIN", "CS", "가짜관리")
    own_mgr = _order(OWN[0], manager=MATCH, construction=True)     # 저장 훅이 MANAGER_PRIMARY 연결
    own_creator = _order(OWN[1])                                    # 직접 등록(CREATOR) — 담당 이름과 무관
    db_session.add(OrderFreelancerLink(order_id=own_creator.id, user_id=fl.id, relation="CREATOR"))
    db_session.commit()
    _order(OWN_UNDATED, manager=MATCH, measure=False)
    others = [
        _order(OTHERS[0], manager=USER_NAME),
        _order(OTHERS[1], extra={"assignments": {"sales_assignee_user_ids": [fl.id]}}),
        _order(OTHERS[2], extra={"workflow": {"stage": "MEASURE", "current_quest": {"owner_person": USER_NAME}}}),
        _order(OTHERS[3], construction=True),
        _order(OTHER_UNDATED, manager=USER_NAME, measure=False),
    ]
    return SimpleNamespace(fl=fl, staff=staff, admin=admin, own_mgr_id=own_mgr.id, own_creator_id=own_creator.id,
                           other_plain_id=others[3].id)


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


def _get(app, user, path: str, *, status: int = 200) -> str:
    resp = _client(app, user).get(path)
    assert resp.status_code == status, (path, resp.status_code)
    return resp.get_data(as_text=True)


def _json_text(app, user, path: str) -> tuple[dict, str]:
    resp = _client(app, user).get(path)
    assert resp.status_code == 200, (path, resp.status_code)
    payload = resp.get_json()
    return payload, json.dumps(payload, ensure_ascii=False)


def _assert_only_own(text: str, own=OWN, others=OTHERS + (OTHER_UNDATED, NAVER)) -> None:
    missing = [name for name in own if name not in text]
    leaked = [name for name in others if name in text]
    assert not missing and not leaked, {"missing_own": missing, "leaked_others": leaked}


def _assert_sees_all(text: str, names=OWN + OTHERS) -> None:
    assert [name for name in names if name not in text] == []


def _v2(monkeypatch, *users) -> None:
    """모바일 v2 셸(타워 · 큐 · 하단 배지)을 이 사용자들에게 켠다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", ",".join(str(u.id) for u in users))


# --------------------------------------------------------------------------
# 목록 화면 — 손님 쪽 값으로 "내 것만"을 끌 수 없다
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", ["?mine=0", "?mine=", ""])
def test_desktop_dashboard_list_is_link_scoped(world, app, query):
    _assert_only_own(_get(app, world.fl, f"/erp/dashboard{query}"))
    for control in (world.staff, world.admin):  # 같은 모집단 대조군: 다 보인다
        _assert_sees_all(_get(app, control, f"/erp/dashboard{query or '?mine=0'}"))


def test_inactive_freelancer_is_a_normal_sales_account(world, app):
    """꺼진 프리랜서(active false)는 막지 않는다 — 보통 영업 직원과 같다(설계서 §6.3 "켜진 프리랜서")."""
    _designate(world.fl, MATCH, active=False)
    _assert_sees_all(_get(app, world.fl, "/erp/dashboard?mine=0"))


def test_mobile_queue_and_scroll_chunk_are_link_scoped(world, app, monkeypatch):
    _v2(monkeypatch, world.fl, world.admin)
    for path in ("/erp/dashboard?view=queue&mine=0", "/erp/dashboard?view=queue&mine=0&mobile_chunk=1&page=1"):
        _assert_only_own(_get(app, world.fl, path))
        _assert_sees_all(_get(app, world.admin, path))


def test_mobile_tower_counts_and_risk_samples_are_link_scoped(world, app, monkeypatch):
    """오늘 요약(실측 · 시공 수)과 위험 카드 고객명은 연결 표 범위에서만 나온다 — tower_mine=0 이어도."""
    _v2(monkeypatch, world.fl, world.admin)
    body = _get(app, world.fl, "/erp/dashboard?tower_mine=0")
    assert "실측 2 · 시공 1 · AS 0" in body
    assert OWN[0] in body  # 시공 임박 위험 카드 고객명(내 주문)
    assert [name for name in OTHERS if name in body] == []
    assert "실측 6 · 시공 2 · AS 0" in _get(app, world.admin, "/erp/dashboard?tower_mine=0")


def test_month_calendar_and_day_list_are_link_scoped(world, app):
    month = _today()[:7]
    cal, cal_text = _json_text(app, world.fl, f"/erp/dashboard/field-calendar?month={month}&tower_mine=0")
    assert cal["success"] and "실측 2건, 시공 1건, AS 0건" in cal_text
    _, admin_cal = _json_text(app, world.admin, f"/erp/dashboard/field-calendar?month={month}&tower_mine=0")
    assert "실측 6건, 시공 2건, AS 0건" in admin_cal

    ops, ops_text = _json_text(app, world.fl, f"/erp/dashboard/field-ops?date={_today()}&tower_mine=0")
    data = ops["data"]
    assert (data["count"], data["measure_count"], data["construction_count"]) == (2, 2, 1)
    _assert_only_own(ops_text)
    admin_ops, admin_text = _json_text(app, world.admin, f"/erp/dashboard/field-ops?date={_today()}&tower_mine=0")
    assert admin_ops["data"]["count"] == 6
    _assert_sees_all(admin_text)


def test_tower_base_is_scoped_even_if_a_caller_passes_mine_off(world, app):
    """두 번째 겹: 달력 · 그날 목록을 mine_only=False 로 부르는 새 호출부가 생겨도 프리랜서 base 는 연결 표 범위."""
    month = _today()[:7]
    with app.test_request_context("/"):
        assert build_month_calendar(db_session, world.fl, month, mine_only=False)["measure_total"] == 2
        assert build_field_ops_for_day(db_session, world.fl, _today(), mine_only=False)["count"] == 2
        assert build_month_calendar(db_session, world.admin, month, mine_only=False)["measure_total"] == 6


# --------------------------------------------------------------------------
# 실측 판 · 실측 API
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", ["?mine=0", "?mine=", ""])
def test_measurement_board_is_link_scoped_and_hides_naver_strip(world, app, query):
    """그날 네이버 주문이 있어도 프리랜서 실측 판 HTML 에는 남의 고객명이 없다(띠 끔 — 검수 A3)."""
    _naver_measured_today(_today(), customer=NAVER)
    body = _get(app, world.fl, f"/erp/measurement{query}")
    _assert_only_own(body)
    assert "data-naver-dispatch-count" not in body
    control = _get(app, world.staff, "/erp/measurement?mine=0")  # 대조군: 띠도 남의 주문도 보인다
    assert 'data-naver-dispatch-count="1"' in control and NAVER in control
    _assert_sees_all(control)


def test_measurement_board_mobile_list_is_link_scoped(world, app, monkeypatch):
    _naver_measured_today(_today(), customer=NAVER)
    _v2(monkeypatch, world.fl)
    body = _get(app, world.fl, "/erp/measurement?mine=0")
    _assert_only_own(body)
    assert "data-naver-dispatch-count" not in body


def test_measurement_summary_and_undated_apis_are_link_scoped(world, app):
    _, summary = _json_text(app, world.fl, "/api/erp/measurement/summary?mine=0")
    _assert_only_own(summary)
    _, control = _json_text(app, world.staff, "/api/erp/measurement/summary?mine=0")
    _assert_sees_all(control)

    undated, undated_text = _json_text(app, world.fl, "/api/erp/measurement/undated?mine=0")
    assert undated["data"]["total"] == 1
    _assert_only_own(undated_text, own=(OWN_UNDATED,))
    _, control_undated = _json_text(app, world.staff, "/api/erp/measurement/undated?mine=0")
    _assert_sees_all(control_undated, names=(OWN_UNDATED, OTHER_UNDATED))


# --------------------------------------------------------------------------
# mine 밖에서 계산되던 조각(검수 A10 · 겹 2 보강)
# --------------------------------------------------------------------------
def test_dashboard_search_has_no_history_more_or_history_redirect(world, app):
    _order(LEGACY, measure=False, erp=False)  # 대시보드 밖(ERP 아님) — 이력 검색에만 걸린다
    body = _get(app, world.fl, "/erp/dashboard?q=고객")
    assert "전체 이력에" not in body and LEGACY not in body
    _assert_only_own(body)
    assert "전체 이력에 1건 더" in _get(app, world.staff, "/erp/dashboard?q=고객")  # 대조군

    # 결과 0건 검색: 직원은 이력 검색으로 보내지만(302) 프리랜서는 그 자리에서 0건(남의 주문 없음).
    # 검색창이 검색어를 되돌려 싣으므로 고객명 앞부분으로 찾는다.
    assert OTHERS[3] not in _get(app, world.fl, f"/erp/dashboard?q={OTHERS[3][:3]}")
    assert "/erp/history" in _client(app, world.staff).get(f"/erp/dashboard?q={LEGACY}").headers.get("Location", "")


def test_focus_order_never_injects_someone_elses_order(world, app):
    resp = _client(app, world.fl).get(f"/erp/dashboard?focus_order={world.other_plain_id}")
    assert resp.status_code in (200, 404)  # 404 = 문지기의 주문 번호 판정(겹 2)이 먼저 막은 경우
    assert OTHERS[3] not in resp.get_data(as_text=True)
    assert OTHERS[3] in _get(app, world.admin, f"/erp/dashboard?focus_order={world.other_plain_id}")


# --------------------------------------------------------------------------
# 판정 함수 — 연결 표 하나 · 담당에서 빠지면 안 보인다
# --------------------------------------------------------------------------
def _mine_count(app, user) -> int:
    with app.test_request_context("/"):
        g.current_user = user
        clause = mine_membership_clause(build_mine_sql_filter(user, scope="all"))
        return db_session.query(Order).filter(clause).count()


def test_predicates_use_link_table_only_and_follow_unassignment(world, app):
    orders = {o.customer_name: o for o in db_session.query(Order).all()}
    for scope in (None, "sales", "drawing", "construction", "all"):
        with app.test_request_context("/"):
            related = {name for name, o in orders.items() if is_order_related_to_user(o, world.fl, scope=scope)}
        assert related == {*OWN, OWN_UNDATED}, scope
    assert _mine_count(app, world.fl) == 3
    assert _mine_count(app, world.staff) == 0  # 대조군: 직원은 이름 판정 그대로(이름 다른영업 → 0건)

    # 담당에서 빠지면(규칙 4) 연결이 지워져 안 보인다. 직접 등록(CREATOR)은 담당과 무관하게 남는다.
    for order_id in (world.own_mgr_id, world.own_creator_id):
        order = db_session.get(Order, order_id)
        sd = copy.deepcopy(order.structured_data)
        sd["parties"]["manager"]["name"] = "다른사람"
        order.structured_data = sd
        flag_modified(order, "structured_data")
    db_session.commit()
    with app.test_request_context("/"):
        assert not is_order_related_to_user(db_session.get(Order, world.own_mgr_id), world.fl)
        assert is_order_related_to_user(db_session.get(Order, world.own_creator_id), world.fl)
    _assert_only_own(_get(app, world.fl, "/erp/dashboard?mine=0"), own=(OWN[1],), others=(OWN[0],) + OTHERS)


# --------------------------------------------------------------------------
# 하단 배지 · 캐시 층
# --------------------------------------------------------------------------
def test_nav_badges_count_only_linked_orders_and_cache_is_per_user(world, app, monkeypatch):
    """배지 메모리 캐시(사용자 id 열쇠): 직원이 먼저 채워도 프리랜서는 내 수만, mine_only=False 를 넘겨도 내 수만."""
    with app.test_request_context("/"):
        assert dashboard_counts.get_nav_badge_counts(world.admin, mine_only=False)["measurement"] == 8
        assert dashboard_counts.get_nav_badge_counts(world.fl, mine_only=False)["measurement"] == 3
        assert dashboard_counts.get_nav_badge_counts(world.fl)["measurement"] == 3
        assert dashboard_counts.get_nav_badge_counts(world.admin, mine_only=False)["measurement"] == 8
    _v2(monkeypatch, world.fl)
    body = _get(app, world.fl, "/erp/dashboard?view=queue&mine=0")
    assert 'aria-label="미처리 3건"' in body and 'aria-label="미처리 8건"' not in body


@pytest.fixture()
def micro_cache(monkeypatch):
    """대시보드 조각 캐시(Redis)를 메모리 대역으로 켠다."""
    fake = FakeRedis()
    monkeypatch.setattr(dashboard_cache, "is_dashboard_micro_cache_enabled", lambda: True)
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: fake)
    return fake


def test_dashboard_slice_cache_never_crosses_users(world, app, monkeypatch, micro_cache):
    """타워 · 달력 · 실측 패널/목록 조각 캐시: 관리자 → 프리랜서 → 관리자 순서로 번갈아 그려도 섞이지 않는다."""
    _v2(monkeypatch, world.fl, world.admin)
    month = _today()[:7]
    for _round in range(2):  # 두 번째 바퀴는 캐시에서 나온다
        assert "실측 6 · 시공 2" in _get(app, world.admin, "/erp/dashboard?tower_mine=0")
        assert "실측 2 · 시공 1" in _get(app, world.fl, "/erp/dashboard?tower_mine=0")
        assert "실측 6건, 시공 2건" in _json_text(app, world.admin, f"/erp/dashboard/field-calendar?month={month}")[1]
        assert "실측 2건, 시공 1건" in _json_text(app, world.fl, f"/erp/dashboard/field-calendar?month={month}")[1]
        _assert_sees_all(_get(app, world.admin, "/erp/measurement?mine=0"))
        _assert_only_own(_get(app, world.fl, "/erp/measurement?mine=0"))
    assert any(":mobile_control_tower:" in key for key in micro_cache.kv)
    assert any(":main_rows:" in key for key in micro_cache.kv)


def test_designation_switches_cache_keys_immediately(app, micro_cache):
    """같은 계정이 프리랜서로 지정된 직후, 이름 판정으로 채운 캐시(같은 사용자 · 같은 mine)를 받지 않는다."""
    user = _named_user("STAFF", "SALES", "나중영업")
    _designate(user, "나중프리B", active=False)
    _order("나중이름고객", manager="나중영업")    # 직원 시절 이름 판정으로만 "내 것"
    _order("나중연결고객", manager="나중프리B")   # 프리랜서가 되면 연결 표로 "내 것"
    before = _get(app, user, "/erp/measurement?mine=1")
    assert "나중이름고객" in before and "나중연결고객" not in before

    _designate(user, "나중프리B", active=True)
    resync_freelancer_links(db_session, user.id)
    db_session.commit()
    after = _get(app, user, "/erp/measurement?mine=1")
    assert "나중연결고객" in after and "나중이름고객" not in after
