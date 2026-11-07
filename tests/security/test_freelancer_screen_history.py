"""프리랜서 화면 묶음: 과거 이력 검색(``erp_history``) — 열되 내 주문만(FCOMM-01 · 사용자 결정 2026-11-07).

묶음 파일: foms/services/auth/freelancer_screens/history.py · 거르기: foms/web/orders/history.py.

* 문지기: 이력 화면 · 태블릿 시트가 허용 목록에 있다(묶음 폴더가 모은다). 시트 ``order_id`` · 화면 ``?focus_order=`` 는
  남의 번호면 404.
* 이력 화면(PC · 셸 조각 · 모바일 v2 큐 카드)은 단계 필터 · 검색어 · 통합 검색 결과(``from_search=1``) · 초성 ·
  ``?mine=0`` · 필터 없음(내 것 자동) 모두 내 고객명만 있고 남의 고객명은 없다. 건수도 내 것만 센다. 남의 고객명으로
  찾아도 0건이고 대시보드로 되보내지도 않는다.
* 태블릿 시트: 내 주문 200, 남의 주문 404(주소창 document 요청도 편집 화면으로 보내기 전에 404).
* 대조군(같은 모집단): 프리랜서 아닌 영업 직원 · 꺼진 프리랜서는 둘 다 본다.
* 캐시: 이력 쪽 조각 캐시를 직원 · 프리랜서가 번갈아 그려도 섞이지 않고, 프리랜서로 지정한 직후 옛 조각을 받지 않는다.
모든 이름 · 전화번호는 가짜 값이다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.auth import freelancer_screens
from foms.services.auth.freelancer_scope import (
    FREELANCER_ALLOWED_ENDPOINTS,
    FREELANCER_ORDER_QUERY_ARGS,
    FREELANCER_ORDER_VIEW_ARGS,
)
from foms.services.common import dashboard_cache
from foms.services.sales_commission.links import resync_freelancer_links
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, OrderFreelancerLink
from tests.domains.test_auth_finance import _login, _make_user
from tests.support.fragver_fake_redis import FakeRedis

MATCH = "가짜이력프리"       # 프리랜서 설정의 맞출 이름(주문 담당 칸과 같으면 저장 훅이 연결)
USER_NAME = "가짜이력영업"   # 프리랜서 계정 표시 이름 — 이 이름이 담당인 주문은 남의 주문이다
OWN = "이력본인고객"
OTHER = "이력남의고객"
PHONE = "02-0000-0000"
_SCREEN_ENDPOINTS = ("erp_history.history_dashboard", "erp_history.history_tablet_sheet")


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    """조각 캐시는 기본으로 끈다(REDIS_URL 없음 → 바로 계산). 캐시 시험만 메모리 대역을 켠다."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    dashboard_cache.reset_dashboard_cache_runtime_for_tests()
    yield
    dashboard_cache.reset_dashboard_cache_runtime_for_tests()


def _completed_order(customer: str, *, manager: str) -> int:
    """끝난 지 오래된 주문(이력 화면이 찾는 대상)."""
    sd = {
        "parties": {"manager": {"name": manager}, "customer": {"name": customer, "phone": PHONE},
                    "orderer": {"name": "라홈"}},
        "schedule": {"construction": {"date": "2025-03-10"}},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "COMPLETED"},
    }
    order = Order(received_date="2025-03-01", customer_name=customer, phone=PHONE, address="가짜시 이력구",
                  product="가짜장", status="COMPLETED", manager_name=manager, is_erp_order=True,
                  erp_stage_code="COMPLETED", structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


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


def _ensure_link(order_id: int, user_id: int) -> None:
    exists = db_session.query(OrderFreelancerLink).filter_by(order_id=order_id, user_id=user_id).first()
    if exists is None:
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user_id, relation="MANAGER_PRIMARY"))
        db_session.commit()


@pytest.fixture()
def world(app):
    """프리랜서 1 · 대조군 영업 직원 1 + 내 끝난 주문 1(연결) · 남의 끝난 주문 1(담당 이름이 내 계정 이름)."""
    fl = _named_user("STAFF", "SALES", USER_NAME)
    _designate(fl, MATCH)
    staff = _named_user("STAFF", "SALES", "가짜다른영업")
    own_id = _completed_order(OWN, manager=MATCH)
    _ensure_link(own_id, fl.id)
    other_id = _completed_order(OTHER, manager=USER_NAME)
    return SimpleNamespace(fl=fl, staff=staff, own_id=own_id, other_id=other_id)


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


def _get(app, user, path: str, *, status: int = 200, headers: dict | None = None) -> str:
    resp = _client(app, user).get(path, headers=headers or {})
    assert resp.status_code == status, (path, resp.status_code, resp.headers.get("Location"))
    return resp.get_data(as_text=True)


def _assert_only_own(text: str) -> None:
    assert OWN in text and OTHER not in text, {"own": OWN in text, "leaked_other": OTHER in text}


def _assert_sees_both(text: str) -> None:
    assert OWN in text and OTHER in text, {"own": OWN in text, "other": OTHER in text}


def _v2(monkeypatch, *users) -> None:
    """모바일 v2 셸(이력 큐 카드)을 이 사용자들에게 켠다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", ",".join(str(u.id) for u in users))


# 손님 쪽 값(mine 끄기 · 통합 검색 표식 · 검색어 · 필터 없음)마다 같은 판정. 모두 내 고객명이 걸리는 조건이다.
_ONLY_OWN_QUERIES = (
    "?stage=COMPLETED",
    "?stage=COMPLETED&mine=0",
    "?stage=COMPLETED&mine=",
    "?q=고객",
    "?q=고객&from_search=1",
    "?q=고객&from_search=1&mine=0",
    f"?q={PHONE}&from_search=1",
    "?q=ㅇㄹ&from_search=1",           # 초성 — 두 고객명 모두 ㅇㄹ 로 시작한다
    "?date_from=2000-01-01&from_search=1",
    "",                                  # 필터 없음 — 프리랜서는 "내 것만"이 켜져 있어 내 주문을 자동으로 보여 준다
)


# --------------------------------------------------------------------------
# 문지기 — 묶음 파일이 연다
# --------------------------------------------------------------------------
def test_history_bundle_is_merged_into_gate():
    assert "history" in freelancer_screens.MODULES
    assert set(_SCREEN_ENDPOINTS) <= FREELANCER_ALLOWED_ENDPOINTS
    assert FREELANCER_ORDER_VIEW_ARGS["erp_history.history_tablet_sheet"] == ("order_id",)
    assert FREELANCER_ORDER_QUERY_ARGS["erp_history.history_dashboard"] == ("focus_order",)


# --------------------------------------------------------------------------
# 이력 화면 — 내 주문만(건수 포함)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", _ONLY_OWN_QUERIES)
def test_history_page_shows_only_own_orders(world, app, query):
    body = _get(app, world.fl, f"/erp/history/{query}")
    _assert_only_own(body)
    assert "검색 결과 (총 1건)" in body


@pytest.mark.parametrize("query", [q for q in _ONLY_OWN_QUERIES if q and "mine=0" not in q])
def test_staff_control_sees_both(world, app, query):
    """대조군(같은 모집단): 프리랜서 아닌 영업 직원은 같은 조건에서 둘 다 본다(통합 검색 결과는 전체 폭)."""
    path = f"/erp/history/{query}"
    if "from_search" not in query:
        path += "&from_search=1"  # 검색어만이면 대시보드로 되보낼 수 있어 통합 검색 경로로 본다
    body = _get(app, world.staff, path)
    _assert_sees_both(body)
    assert "검색 결과 (총 2건)" in body


def test_inactive_freelancer_is_a_normal_sales_account(world, app):
    """꺼진 프리랜서(active false)는 보통 영업 직원과 같다 — 통합 검색 결과가 전체 폭이다."""
    _designate(world.fl, MATCH, active=False)
    _assert_sees_both(_get(app, world.fl, "/erp/history/?q=고객&from_search=1"))


@pytest.mark.parametrize("query", [f"?q={OTHER}", f"?q={OTHER}&from_search=1", f"?q={OTHER}&from_search=1&mine=0",
                                   "?q=ㅇㄹㄴ&from_search=1"])
def test_searching_someone_elses_customer_finds_nothing(world, app, query):
    """남의 고객명(초성 포함)으로 찾아도 0건 — 대시보드로 되보내지도 않는다(302 아님). 대조군은 찾는다."""
    body = _get(app, world.fl, f"/erp/history/{query}")
    assert OTHER not in body.replace(f'value="{OTHER}"', "")  # 검색창이 검색어를 되돌려 싣는 것은 뺀다
    assert "조건에 맞는 이력이 없습니다." in body
    control = _get(app, world.staff, f"/erp/history/{query.replace('&mine=0', '')}"
                   + ("" if "from_search" in query else "&from_search=1"))
    assert "검색 결과 (총 1건)" in control and f'data-order-id="{world.other_id}"' in control


def test_shell_fragment_is_scoped(world, app):
    """ERP 셸 탭 본문(조각) — 같은 처리 경로, 같은 범위."""
    headers = {"X-FOMS-ERP-SHELL": "1"}
    body = _get(app, world.fl, "/erp/history/?q=고객&from_search=1&view=fragment", headers=headers)
    _assert_only_own(body)
    _assert_sees_both(_get(app, world.staff, "/erp/history/?q=고객&from_search=1&view=fragment", headers=headers))


def test_mobile_v2_queue_cards_are_scoped(world, app, monkeypatch):
    _v2(monkeypatch, world.fl, world.staff)
    body = _get(app, world.fl, "/erp/history/?q=고객&from_search=1&mine=0")
    _assert_only_own(body)
    assert f'data-order-id="{world.own_id}"' in body and f'data-order-id="{world.other_id}"' not in body
    _assert_sees_both(_get(app, world.staff, "/erp/history/?q=고객&from_search=1"))


def test_focus_order_query_is_order_scoped(world, app):
    client = _client(app, world.fl)
    assert client.get(f"/erp/history/?stage=COMPLETED&focus_order={world.other_id}").status_code == 404
    assert client.get(f"/erp/history/?focus_order={world.own_id}&focus_order={world.other_id}").status_code == 404
    own = client.get(f"/erp/history/?stage=COMPLETED&focus_order={world.own_id}")
    assert own.status_code == 200 and OTHER not in own.get_data(as_text=True)
    # 대조군: 직원은 그대로(서버는 이 값을 읽지 않는다 — 화면 JS 의 카드 강조뿐).
    assert _client(app, world.staff).get(f"/erp/history/?stage=COMPLETED&focus_order={world.other_id}").status_code == 200


# --------------------------------------------------------------------------
# 태블릿 읽기전용 시트(주문 1건)
# --------------------------------------------------------------------------
def test_tablet_sheet_own_200_other_404(world, app):
    client = _client(app, world.fl)
    own = client.get(f"/erp/history/tablet-sheet/{world.own_id}")
    assert own.status_code == 200 and OWN in own.get_data(as_text=True)
    assert client.get(f"/erp/history/tablet-sheet/{world.other_id}").status_code == 404
    assert client.get("/erp/history/tablet-sheet/999999").status_code == 404  # 없는 주문도 같은 답
    # 주소창(document) 요청: 내 주문은 편집 화면으로 보내고, 남의 주문은 보내기 전에 404.
    doc = {"Sec-Fetch-Dest": "document"}
    mine = client.get(f"/erp/history/tablet-sheet/{world.own_id}", headers=doc)
    assert mine.status_code == 302 and f"/{world.own_id}" in mine.headers.get("Location", "")
    assert client.get(f"/erp/history/tablet-sheet/{world.other_id}", headers=doc).status_code == 404
    # 대조군: 직원은 남의 주문 시트도 연다.
    control = _client(app, world.staff).get(f"/erp/history/tablet-sheet/{world.other_id}")
    assert control.status_code == 200 and OTHER in control.get_data(as_text=True)


# --------------------------------------------------------------------------
# 캐시 — 이력 쪽 조각(order_ids · 건수)
# --------------------------------------------------------------------------
@pytest.fixture()
def micro_cache(monkeypatch):
    """대시보드 조각 캐시(Redis)를 메모리 대역으로 켠다."""
    fake = FakeRedis()
    monkeypatch.setattr(dashboard_cache, "is_dashboard_micro_cache_enabled", lambda: True)
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: fake)
    return fake


def test_history_page_cache_never_crosses_users(world, app, micro_cache):
    for _round in range(2):  # 두 번째 바퀴는 캐시에서 나온다
        staff_body = _get(app, world.staff, "/erp/history/?q=고객&from_search=1")
        _assert_sees_both(staff_body)
        assert "검색 결과 (총 2건)" in staff_body
        fl_body = _get(app, world.fl, "/erp/history/?q=고객&from_search=1")
        _assert_only_own(fl_body)
        assert "검색 결과 (총 1건)" in fl_body
    assert any(":page_rows:" in key for key in micro_cache.kv)


def test_designation_switches_history_cache_key_immediately(app, micro_cache):
    """같은 계정 · 같은 mine 이어도 프리랜서로 지정한 직후 이름 판정으로 채운 옛 조각(목록 · 건수)을 받지 않는다."""
    user = _named_user("STAFF", "SALES", "가짜나중영업")
    _designate(user, "가짜나중프리", active=False)
    _completed_order("이력나중이름고객", manager="가짜나중영업")   # 직원 시절 이름 판정으로만 "내 것"
    _completed_order("이력나중연결고객", manager="가짜나중프리")   # 프리랜서가 되면 연결 표로 "내 것"
    before = _get(app, user, "/erp/history/?stage=COMPLETED&mine=1")
    assert "이력나중이름고객" in before and "이력나중연결고객" not in before

    _designate(user, "가짜나중프리", active=True)
    resync_freelancer_links(db_session, user.id)
    db_session.commit()
    after = _get(app, user, "/erp/history/?stage=COMPLETED&mine=1")
    assert "이력나중연결고객" in after and "이력나중이름고객" not in after
    assert "검색 결과 (총 1건)" in after
