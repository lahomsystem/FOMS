"""프리랜서 화면 묶음: 생산 판 — 회사 영업 때 쓰던 화면을 그대로 열되 주문은 자기 것만.

사용자 결정(2026-11-07), 묶음 파일 foms/services/auth/freelancer_screens/production.py.

* 생산 판(PC 목록 · 휴대폰 큐 · 태블릿 칸반 · 취소 묘비 · 검색)은 켜진 프리랜서에게 내 주문만 보인다 — ``?mine=0`` ·
  ``?mine=`` · 쿠키 없음 모두. 숫자판(단계 수 · 긴급/D-n 배지 · 전체 수)도 내 주문만 센다.
* 담당 이름이 프리랜서 계정 이름과 같은 주문 · ``sales_assignee_user_ids`` 에 내 id 가 든 주문은 남의 주문이다(연결 표 하나).
* 주문 1건 읽기 문(태블릿 시트 · 공정 체크 읽기 · 상세 묶음 · QR 라벨 · QR 그림): 내 주문 200, 남의 주문 404.
* 쓰기(제작 시작 · 공정 체크 쓰기)는 그대로 닫혀 있다(403).
* 숫자판 조각 캐시: 사용자를 번갈아 그려도 섞이지 않고, 같은 계정을 프리랜서로 켠 직후 이름 판정 숫자를 받지 않는다.
* 대조군(같은 모집단): 프리랜서 아닌 영업 직원 · 꺼진 프리랜서는 전부 본다.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import foms.services.production_read_model as read_model
import foms.web.production.dashboard as production_page
from db import db_session
from foms.services import dashboard_counts
from foms.services.auth.freelancer_scope import FREELANCER_DENIED_MSG, FREELANCER_ORDER_NOT_FOUND_MSG
from foms.services.common import dashboard_cache
from foms.services.datetime_kst import get_today_kst
from foms.services.sales_commission.links import resync_freelancer_links
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, OrderFreelancerLink
from tests.domains.test_auth_finance import _login, _make_user
from tests.support.fragver_fake_redis import FakeRedis

MATCH = "가짜생산프리"        # 프리랜서 설정의 맞출 이름(주문 담당 칸과 같으면 연결)
USER_NAME = "가짜생산영업"    # 프리랜서 계정 표시 이름 — 이 이름이 담당인 주문은 남의 주문이다
OWN = ("생산본인담당", "생산본인등록")
OTHERS = ("생산남이름", "생산남배정", "생산남일반")
OTHER_TOMB = "생산남취소"
BOARD = "/erp/production/dashboard"


def _today() -> str:
    return get_today_kst().isoformat()


def _order(customer: str, *, manager: str = "아무개", stage: str = "PRODUCTION", urgent: bool = False,
           deleted: bool = False, extra: dict | None = None) -> Order:
    today = _today()
    sd = {
        "parties": {"manager": {"name": manager}, "customer": {"name": customer}, "orderer": {"name": "라홈"}},
        "schedule": {"construction": {"date": today}},
        "workflow": {"stage": stage},
        "items": [{"product_name": "가짜장", "spec_width": "900", "quantity": 1}],
        "flags": {"urgent": urgent},
        **(extra or {}),
    }
    order = Order(
        received_date=today, customer_name=customer, phone="02-0000-0000", address="가짜시 가짜구",
        product="가짜장", status="DELETED" if deleted else stage, manager_name=manager, is_erp_order=True,
        structured_data=sd, erp_stage_code=stage, erp_construction_date=today,
        deleted_at=f"{today} 12:00:00" if deleted else None,
    )
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
    """프리랜서 1 · 대조군 영업 직원 1 + 내 주문 2(담당 연결 · 직접 등록) · 남의 주문 3 · 남의 취소 묘비 1."""
    with dashboard_counts._cache_lock:
        dashboard_counts._cache.clear()
    fl = _named_user("STAFF", "SALES", USER_NAME)
    _designate(fl, MATCH)
    staff = _named_user("STAFF", "SALES", "다른생산영업")
    own_mgr = _order(OWN[0], manager=MATCH, urgent=True)            # 저장 훅이 MANAGER_PRIMARY 연결
    own_creator = _order(OWN[1], stage="CONFIRM")                    # 직접 등록(CREATOR) — 담당 이름과 무관
    db_session.add(OrderFreelancerLink(order_id=own_creator.id, user_id=fl.id, relation="CREATOR"))
    db_session.commit()
    others = [
        _order(OTHERS[0], manager=USER_NAME, urgent=True),
        _order(OTHERS[1], stage="CONSTRUCTION", extra={"assignments": {"sales_assignee_user_ids": [fl.id]}}),
        _order(OTHERS[2]),
    ]
    _order(OTHER_TOMB, deleted=True)
    return SimpleNamespace(fl=fl, staff=staff, own_id=own_mgr.id, other_id=others[2].id)


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


def _get(app, user, path: str, *, status: int = 200) -> str:
    resp = _client(app, user).get(path)
    assert resp.status_code == status, (path, resp.status_code)
    return resp.get_data(as_text=True)


def _assert_only_own(text: str, own=OWN, others=OTHERS + (OTHER_TOMB,)) -> None:
    missing = [name for name in own if name not in text]
    leaked = [name for name in others if name in text]
    assert not missing and not leaked, {"missing_own": missing, "leaked_others": leaked}


def _assert_sees_all(text: str, names=OWN + OTHERS) -> None:
    assert [name for name in names if name not in text] == []


def _v2(monkeypatch, *users) -> None:
    """모바일 v2 셸(휴대폰 큐 · 태블릿 칸반 · 묘비)을 이 사용자들에게 켠다(쿠키 없음 = 모든 표면을 그린다)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", ",".join(str(u.id) for u in users))


def _board_ctx(app, user, monkeypatch, query: str = "") -> dict:
    """생산 판이 템플릿에 넘기는 값(숫자판 · 목록)을 잡는다."""
    captured: dict = {}

    def _fake_render(template_name, **ctx):
        captured.clear()
        captured.update(ctx)
        return ""

    monkeypatch.setattr(production_page, "render_template", _fake_render)
    assert _client(app, user).get(BOARD + query).status_code == 200
    return dict(captured)


def _counts(ctx: dict) -> tuple[int, int, int]:
    """(전체 수, 단계 수 합, 긴급 배지)."""
    return (ctx["total_orders"], sum(s["count"] for s in ctx["step_stats"].values()), ctx["kpis"]["urgent_count"])


# --------------------------------------------------------------------------
# 판 화면 — 목록 · 숫자 · 칸반 · 묘비 · 검색
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", ["", "?mine=0", "?mine="])
def test_desktop_board_lists_only_own_orders(world, app, query):
    _assert_only_own(_get(app, world.fl, BOARD + query))
    _assert_sees_all(_get(app, world.staff, BOARD + (query or "?mine=0")))  # 같은 모집단 대조군


def test_mobile_queue_kanban_and_tombstones_are_link_scoped(world, app, monkeypatch):
    """휴대폰 큐 · 태블릿 칸반 · 취소 묘비(남의 취소 주문 고객명) 모두 내 주문만."""
    _v2(monkeypatch, world.fl, world.staff)
    body = _get(app, world.fl, BOARD + "?mine=0")
    assert "foms-kanban-card" in body and "erp-production-mobile-v2" in body  # 세 표면이 다 그려졌다
    _assert_only_own(body)
    control = _get(app, world.staff, BOARD + "?mine=0")
    _assert_sees_all(control, names=OWN + OTHERS + (OTHER_TOMB,))


def test_board_counts_are_own_only(world, app, monkeypatch):
    """숫자판: 전체 2 · 단계 합 2 · 긴급 1(내 것) — 직원은 전체 5 · 긴급 2."""
    ctx = _board_ctx(app, world.fl, monkeypatch, "?mine=0")
    assert _counts(ctx) == (2, 2, 1)
    assert ctx["erp_mine_only"] is True
    assert {o["customer_name"] for o in ctx["orders"]} == set(OWN)
    staff_ctx = _board_ctx(app, world.staff, monkeypatch, "?mine=0")
    assert _counts(staff_ctx) == (5, 5, 2)


def test_board_search_finds_only_own_orders(world, app):
    """검색은 내 주문 안에서만 찾는다. 검색창이 검색어를 되돌려 싣으므로 고객명 앞부분으로 찾는다."""
    _assert_only_own(_get(app, world.fl, BOARD + "?q=생산"))
    prefix = OTHERS[2][:3]  # 남의 주문 셋 모두에 맞는 앞부분
    assert [name for name in OTHERS if name in _get(app, world.fl, BOARD + "?q=" + prefix)] == []
    _assert_sees_all(_get(app, world.staff, BOARD + "?q=" + prefix), names=OTHERS)  # 대조군


def test_focus_order_deeplink_is_own_only(world, app):
    resp = _client(app, world.fl).get(f"{BOARD}?focus_order={world.other_id}")
    assert resp.status_code == 404 and OTHERS[2] not in resp.get_data(as_text=True)
    assert OWN[0] in _get(app, world.fl, f"{BOARD}?focus_order={world.own_id}&stage=제작완료")
    assert OTHERS[2] in _get(app, world.staff, f"{BOARD}?focus_order={world.other_id}&stage=제작완료")


def test_inactive_freelancer_is_a_normal_sales_account(world, app):
    _designate(world.fl, MATCH, active=False)
    _assert_sees_all(_get(app, world.fl, BOARD + "?mine=0"))


# --------------------------------------------------------------------------
# 주문 1건 읽기 문 — 내 주문 200, 남의 주문 404
# --------------------------------------------------------------------------
def test_tablet_sheet_own_opens_other_404(world, app):
    assert OWN[0] in _get(app, world.fl, f"/erp/production/tablet-sheet/{world.own_id}")
    assert OTHERS[2] not in _get(app, world.fl, f"/erp/production/tablet-sheet/{world.other_id}", status=404)
    assert OTHERS[2] in _get(app, world.staff, f"/erp/production/tablet-sheet/{world.other_id}")


@pytest.mark.parametrize("path", [
    "/api/orders/{id}/production/steps",
    "/api/orders/{id}/detail-payload",
])
def test_order_read_apis_own_opens_other_404(world, app, path):
    client = _client(app, world.fl)
    mine = client.get(path.format(id=world.own_id))
    assert mine.status_code == 200 and mine.get_json()["success"] is True
    theirs = client.get(path.format(id=world.other_id))
    assert theirs.status_code == 404 and theirs.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG
    assert OTHERS[2] not in theirs.get_data(as_text=True)
    assert _client(app, world.staff).get(path.format(id=world.other_id)).status_code == 200  # 대조군


def test_detail_payload_carries_own_customer(world, app):
    payload = _client(app, world.fl).get(f"/api/orders/{world.own_id}/detail-payload").get_json()
    assert OWN[0] in json.dumps(payload, ensure_ascii=False)


def test_qr_label_and_svg_own_opens_other_404(world, app):
    assert OWN[0] in _get(app, world.fl, f"/erp/orders/{world.own_id}/label")
    assert OTHERS[2] not in _get(app, world.fl, f"/erp/orders/{world.other_id}/label", status=404)
    client = _client(app, world.fl)
    assert client.get(f"/api/orders/{world.own_id}/qr.svg").status_code == 200
    assert client.get(f"/api/orders/{world.other_id}/qr.svg").status_code == 404
    assert OTHERS[2] in _get(app, world.staff, f"/erp/orders/{world.other_id}/label")  # 대조군


# --------------------------------------------------------------------------
# 쓰기 — D27: 자기 주문은 회사 영업 직원과 같은 답, 남의 주문은 문지기 응답
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/orders/{id}/production/start",
    "/api/orders/{id}/production/steps",
    "/api/orders/{id}/production/hold",
])
def test_production_writes_follow_staff_rules_on_own_order_only(world, app, path):
    mine = _client(app, world.fl).post(path.format(id=world.own_id), json={})
    assert (mine.get_json(silent=True) or {}).get("error") != FREELANCER_DENIED_MSG
    assert mine.headers.get("X-Auth-Policy") != "denied", mine.get_json()  # 프리랜서라서 막히지 않는다
    theirs = _client(app, world.fl).post(path.format(id=world.other_id), json={})
    assert theirs.status_code == 403 and theirs.get_json()["error"] == FREELANCER_DENIED_MSG


# --------------------------------------------------------------------------
# 숫자판 조각 캐시
# --------------------------------------------------------------------------
@pytest.fixture()
def micro_cache(monkeypatch):
    """대시보드 조각 캐시(Redis)를 메모리 대역으로 켠다."""
    fake = FakeRedis()
    monkeypatch.setattr(dashboard_cache, "is_dashboard_micro_cache_enabled", lambda: True)
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: fake)
    return fake


def test_summary_cache_never_crosses_users(world, app, monkeypatch, micro_cache):
    for _round in range(2):  # 두 번째 바퀴는 캐시에서 나온다
        assert _counts(_board_ctx(app, world.staff, monkeypatch, "?mine=0")) == (5, 5, 2)
        assert _counts(_board_ctx(app, world.fl, monkeypatch, "?mine=0")) == (2, 2, 1)
    assert any(":summary_counts:" in key for key in micro_cache.kv)


def _switch_world():
    """직원 시절 이름 판정으로 "내 것" 2건, 프리랜서가 되면 연결 표로 "내 것" 1건."""
    user = _named_user("STAFF", "SALES", "나중생산영업")
    _designate(user, "나중생산프리", active=False)
    _order("나중이름하나", manager="나중생산영업")
    _order("나중이름둘", manager="나중생산영업")
    _order("나중연결", manager="나중생산프리")
    return user


def _activate(user) -> None:
    _designate(user, "나중생산프리", active=True)
    resync_freelancer_links(db_session, user.id)
    db_session.commit()


def test_designation_switches_summary_cache_key_immediately(app, monkeypatch, micro_cache):
    user = _switch_world()
    assert _board_ctx(app, user, monkeypatch, "?mine=1")["total_orders"] == 2
    _activate(user)
    ctx = _board_ctx(app, user, monkeypatch, "?mine=1")
    assert ctx["total_orders"] == 1
    assert [o["customer_name"] for o in ctx["orders"]] == ["나중연결"]


def test_designation_cache_negative_control(app, monkeypatch, micro_cache):
    """음성 대조군: 열쇠에 프리랜서 표시가 없으면 직원 시절 숫자(2)를 그대로 받는다 — 위 시험이 표시를 실제로 본다."""
    monkeypatch.setattr(read_model, "is_list_freelancer", lambda user: False)
    user = _switch_world()
    assert _board_ctx(app, user, monkeypatch, "?mine=1")["total_orders"] == 2
    _activate(user)
    assert _board_ctx(app, user, monkeypatch, "?mine=1")["total_orders"] == 2
