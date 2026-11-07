"""FCOMM-01 프리랜서 화면 묶음: 도면 작업실 — 회사 영업 때 화면 그대로, 주문은 자기 것만(사용자 결정 2026-11-07).

묶음 파일: foms/services/auth/freelancer_screens/drawing.py. 설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.
이 묶음은 판 화면과 읽기만 연다 — 자기 주문 쓰기 API 는 D27 쪽 몫이라 여기서 열림 · 닫힘을 단언하지 않는다.

* 목록(PC · 셸 조각 · 모바일 v2): 내 고객만 보이고 남의 고객 · 주문 번호는 없다 — ``?mine=0`` · 검색 · 컨펌 포함 ·
  완료 칸 모두. 칸 숫자 · '누적 완료' 숫자도 내 주문만 센다. 남의 주문 ``?focus_order=`` 는 404.
* 주문 하나(상세 · 태블릿 시트 · 마법사 화면 · 마법사 읽기 API): 내 주문 200 · 남의 주문 404. 마법사 key 읽기는
  내 주문 URL 에 남의 주문 key 를 실어도 400. 주문과 무관한 도면팀 설정 읽기 2개는 200.
* AI 도면팀원 노트(도면팀 내부 화면)는 열지 않는다.
* 대조군(같은 모집단): 프리랜서 아닌 영업 직원은 둘 다 본다.
* 캐시: 같은 계정이 프리랜서로 지정된 직후 직원 범위로 센 '누적 완료' 숫자를 받지 않는다(음성 대조군: 표시를 빼면 깨진다).
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from flask import template_rendered

import foms.services.auth.freelancer_screens as screens
from db import db_session
from foms.services.auth.freelancer_scope import (
    FREELANCER_ALLOWED_ENDPOINTS,
    FREELANCER_ORDER_NOT_FOUND_MSG,
    FREELANCER_ORDER_QUERY_ARGS,
    FREELANCER_ORDER_VIEW_ARGS,
)
from foms.services.auth.freelancer_screens import drawing as drawing_screen
from foms.services.common import dashboard_cache
from foms.services.sales_commission.links import resync_freelancer_links
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, OrderFreelancerLink
from tests.domains.test_auth_finance import _login, _make_user
from tests.support.fragver_fake_redis import FakeRedis

MATCH = "가짜도면프리"        # 프리랜서 맞출 이름 = 계정 이름(이름 판정 함정이 실제로 걸리게)
PHONE = "02-0000-0000"
OWN = {"wait": "도면본인대기고객", "sent": "도면본인전달고객", "done": "도면본인완료고객"}
# 남의 주문 — 이름 판정(퀘스트 담당 이름 · 영업 배정 id)으로는 프리랜서 "내 것"처럼 보이는 함정 포함.
OTHER = {"wait": "도면남퀘스트고객", "sent": "도면남배정고객", "done": "도면남완료고객"}
DASHBOARD = "erp_drawing_workbench.erp_drawing_workbench_dashboard"
SHELL_HEADERS = {"X-FOMS-ERP-SHELL": "1"}


# --------------------------------------------------------------------------
# 시드(가짜 값)
# --------------------------------------------------------------------------
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


def _order(customer: str, *, manager: str, drawing_status: str, extra: dict | None = None) -> int:
    sd = {
        "parties": {"manager": {"name": manager}, "orderer": {"name": "라홈"},
                    "customer": {"name": customer, "phone": PHONE}},
        "schedule": {"measurement": {"date": "2030-01-05"}},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "DRAWING"},
        "drawing_status": drawing_status,
        **(extra or {}),
    }
    order = Order(received_date="2030-01-01", customer_name=customer, phone=PHONE, address="가짜시 가짜구",
                  product="가짜장", status="DRAWING", manager_name=manager, is_erp_order=True, structured_data=sd,
                  erp_stage_code="DRAWING", erp_measurement_date="2030-01-05")
    db_session.add(order)
    db_session.commit()
    return order.id


def _ensure_link(order_id: int, user_id: int) -> None:
    exists = db_session.query(OrderFreelancerLink).filter_by(order_id=order_id, user_id=user_id).first()
    if exists is None:
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user_id, relation="MANAGER_PRIMARY"))
        db_session.commit()


@pytest.fixture()
def world(app):
    """프리랜서 1 · 대조군 영업 직원 1 + 내 주문 3(대기 · 확정 대기 · 완료) · 남의 주문 3(함정 포함)."""
    fl = _named_user("STAFF", "SALES", MATCH)
    _designate(fl, MATCH)
    staff = _named_user("STAFF", "SALES", "가짜다른영업")
    own = {key: _order(name, manager=MATCH, drawing_status=status)
           for (key, name), status in zip(OWN.items(), ("PENDING", "TRANSFERRED", "CONFIRMED"))}
    for order_id in own.values():
        _ensure_link(order_id, fl.id)  # 저장 훅이 이미 붙였을 수 있다(대표 담당 = 맞출 이름)
    other = {
        "wait": _order(OTHER["wait"], manager="가짜남담당", drawing_status="PENDING",
                       extra={"workflow": {"stage": "DRAWING", "current_quest": {"owner_person": MATCH}}}),
        "sent": _order(OTHER["sent"], manager="가짜남담당", drawing_status="TRANSFERRED",
                       extra={"assignments": {"sales_assignee_user_ids": [fl.id]}}),
        "done": _order(OTHER["done"], manager="가짜남담당", drawing_status="CONFIRMED"),
    }
    return SimpleNamespace(fl=fl, staff=staff, own=own, other=other)


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


@contextmanager
def _contexts(app):
    """그린 템플릿의 문맥(목록 줄 · 칸 숫자)을 모은다."""
    seen: list[tuple[str, dict]] = []

    def _record(sender, template, context, **extra):
        seen.append((template.name, context))

    template_rendered.connect(_record, app)
    try:
        yield seen
    finally:
        template_rendered.disconnect(_record, app)


def _dashboard(app, user, query: str = "", headers: dict | None = None) -> tuple[str, list[int], dict]:
    """목록을 그려 (HTML, 줄 주문 번호, 칸 숫자) 를 돌려준다."""
    with _contexts(app) as seen:
        resp = _client(app, user).get(f"/erp/drawing-workbench{query}", headers=headers or {})
    assert resp.status_code == 200, (query, resp.status_code)
    ctx = next(c for _name, c in seen if "rows" in c and "stats" in c)
    return resp.get_data(as_text=True), [int(r["id"]) for r in ctx["rows"]], dict(ctx["stats"])


def _v2(monkeypatch, *users) -> None:
    """모바일 v2 셸을 이 사용자들에게 켠다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", ",".join(str(u.id) for u in users))


def _assert_names(text: str, present, absent) -> None:
    missing = [n for n in present if n not in text]
    leaked = [n for n in absent if n in text]
    assert not missing and not leaked, {"missing": missing, "leaked": leaked}


# --------------------------------------------------------------------------
# 묶음 파일
# --------------------------------------------------------------------------
def test_screen_file_is_merged(app):
    assert "drawing" in screens.MODULES
    assert drawing_screen.ALLOWED_ENDPOINTS <= FREELANCER_ALLOWED_ENDPOINTS
    for endpoint, args in drawing_screen.ORDER_VIEW_ARGS.items():
        assert FREELANCER_ORDER_VIEW_ARGS[endpoint] == args
    assert FREELANCER_ORDER_QUERY_ARGS[DASHBOARD] == ("focus_order",)
    rules = {r.endpoint for r in app.url_map.iter_rules()}
    assert drawing_screen.ALLOWED_ENDPOINTS <= rules  # 이름이 실제 endpoint 다
    assert "erp_drawing_workbench.erp_drawing_agent_note" not in drawing_screen.ALLOWED_ENDPOINTS


# --------------------------------------------------------------------------
# 목록 — 손님 쪽 값으로 "내 것만"을 끌 수 없다, 숫자도 내 주문만
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", ["", "?mine=0", "?mine=", "?q=도면", "?assignee="])
def test_dashboard_lists_only_own_orders(world, app, query):
    body, ids, stats = _dashboard(app, world.fl, query)
    expected = [OWN["wait"], OWN["sent"]] + ([OWN["done"]] if query.startswith("?q=") else [])
    _assert_names(body, expected, OTHER.values())
    assert set(ids) <= set(world.own.values()) and set(world.own.values()) - {world.own["done"]} <= set(ids)
    assert set(ids).isdisjoint(world.other.values())
    assert (stats["total"], stats["TRANSFERRED"], stats["CONFIRMED"]) == (2, 1, 1), stats


@pytest.mark.parametrize("query", ["?include_confirmed=1", "?status=CONFIRMED", "?mine=0&include_confirmed=1"])
def test_dashboard_confirmed_views_only_own(world, app, query):
    body, ids, stats = _dashboard(app, world.fl, query)
    _assert_names(body, [OWN["done"]], OTHER.values())
    assert world.own["done"] in ids and set(ids).isdisjoint(world.other.values())
    assert stats["CONFIRMED"] == 1


def test_dashboard_shell_fragment_and_mobile_v2_only_own(world, app, monkeypatch):
    body, ids, _stats = _dashboard(app, world.fl, "?view=fragment&mine=0", headers=SHELL_HEADERS)
    _assert_names(body, [OWN["wait"], OWN["sent"]], OTHER.values())
    assert set(ids).isdisjoint(world.other.values())
    _v2(monkeypatch, world.fl, world.staff)
    for query in ("?mine=0", "?mine=0&page=1&view=fragment"):
        body, ids, _stats = _dashboard(app, world.fl, query, headers=SHELL_HEADERS if "view=" in query else None)
        _assert_names(body, [OWN["wait"], OWN["sent"]], OTHER.values())
        assert set(ids).isdisjoint(world.other.values())
        control, _ids, _stats = _dashboard(app, world.staff, query,
                                           headers=SHELL_HEADERS if "view=" in query else None)
        _assert_names(control, list(OWN.values())[:2] + list(OTHER.values())[:2], [])


def test_dashboard_negative_control_staff_sees_everyone(world, app):
    body, ids, stats = _dashboard(app, world.staff, "?mine=0")
    _assert_names(body, [OWN["wait"], OWN["sent"], OTHER["wait"], OTHER["sent"]], [])
    assert {world.own["wait"], world.other["wait"], world.own["sent"], world.other["sent"]} <= set(ids)
    assert (stats["total"], stats["CONFIRMED"]) == (4, 2), stats


def test_focus_order_deeplink(world, app):
    client = _client(app, world.fl)
    assert client.get(f"/erp/drawing-workbench?focus_order={world.other['wait']}").status_code == 404
    assert client.get(
        f"/erp/drawing-workbench?focus_order={world.own['wait']}&focus_order={world.other['wait']}").status_code == 404
    _body, ids, _stats = _dashboard(app, world.fl, f"?focus_order={world.own['wait']}")
    assert ids == [world.own["wait"]]
    # 대조군: 직원은 남의 주문 딥링크도 착지한다.
    assert _dashboard(app, world.staff, f"?focus_order={world.other['wait']}")[1] == [world.other["wait"]]


# --------------------------------------------------------------------------
# 주문 하나 — 상세 · 태블릿 시트 · 마법사 화면
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/erp/drawing-workbench/{id}",
    "/erp/drawing-workbench/{id}?tab=requests",
    "/erp/drawing-workbench/tablet-sheet/{id}",
    "/erp/drawing-workbench/{id}/wizard",
])
def test_single_order_pages(world, app, path):
    client = _client(app, world.fl)
    mine = client.get(path.format(id=world.own["sent"]))
    assert mine.status_code == 200, mine.status_code
    _assert_names(mine.get_data(as_text=True), [OWN["sent"]], OTHER.values())
    assert client.get(path.format(id=world.other["sent"])).status_code == 404
    # 대조군: 직원은 남의 주문도 연다.
    control = _client(app, world.staff).get(path.format(id=world.other["sent"]))
    assert control.status_code == 200 and OTHER["sent"] in control.get_data(as_text=True)


@pytest.mark.parametrize("suffix", ["drawing-wizard", "drawing-wizard?item=0", "drawing-wizard/pending",
                                    "drawing-wizard/versions"])
def test_wizard_read_apis(world, app, suffix):
    client = _client(app, world.fl)
    mine = client.get(f"/api/orders/{world.own['wait']}/{suffix}")
    assert mine.status_code == 200 and mine.get_json()["success"] is True
    theirs = client.get(f"/api/orders/{world.other['wait']}/{suffix}")
    assert theirs.status_code == 404 and theirs.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG
    if suffix.startswith("drawing-wizard?") or suffix == "drawing-wizard":
        text = json.dumps(mine.get_json(), ensure_ascii=False)
        _assert_names(text, [OWN["wait"]], OTHER.values())


def test_wizard_key_reads_stay_inside_the_order(world, app):
    """버전 내용 · 그림 원본은 이 주문 접두어 key 만 받는다 — 내 주문 URL 에 남의 주문 key 를 실어도 400."""
    client = _client(app, world.fl)
    other_key = f"orders/{world.other['wait']}/drawing_wizard/versions/x.json"
    for suffix in ("version-content", "asset-raw"):
        resp = client.get(f"/api/orders/{world.own['wait']}/drawing-wizard/{suffix}?key={other_key}")
        assert resp.status_code == 400, (suffix, resp.status_code)
        theirs = client.get(f"/api/orders/{world.other['wait']}/drawing-wizard/{suffix}?key={other_key}")
        assert theirs.status_code == 404 and theirs.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG


@pytest.mark.parametrize("path", ["/api/orders/drawing-wizard/presets", "/api/orders/drawing-wizard/bom-rules"])
def test_wizard_global_setting_reads(world, app, path):
    resp = _client(app, world.fl).get(path)
    assert resp.status_code == 200 and resp.get_json()["success"] is True


def test_agent_note_page_is_still_blocked(world, app):
    resp = _client(app, world.fl).get("/erp/drawing-workbench/agent-note")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/erp/dashboard")


# --------------------------------------------------------------------------
# 캐시 — 지정 직후 직원 범위 숫자를 받지 않는다
# --------------------------------------------------------------------------
@pytest.fixture()
def micro_cache(monkeypatch):
    """대시보드 조각 캐시(Redis)를 메모리 대역으로 켠다."""
    fake = FakeRedis()
    monkeypatch.setattr(dashboard_cache, "is_dashboard_micro_cache_enabled", lambda: True)
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: fake)
    return fake


def test_designation_switches_workbench_cache_immediately(app, micro_cache):
    user = _named_user("STAFF", "SALES", "가짜나중영업")
    _designate(user, "가짜나중프리", active=False)
    for name in ("도면나중이름고객1", "도면나중이름고객2"):  # 직원 시절 이름 판정으로만 "내 것"
        _order(name, manager="가짜나중영업", drawing_status="CONFIRMED")
    _order("도면나중연결고객", manager="가짜나중프리", drawing_status="CONFIRMED")  # 프리랜서가 되면 연결 표로 "내 것"
    _body, _ids, before = _dashboard(app, user, "?mine=1")
    assert before["CONFIRMED"] == 2
    assert any(":workbench_queue_ids:" in key for key in micro_cache.kv)

    _designate(user, "가짜나중프리", active=True)
    resync_freelancer_links(db_session, user.id)
    db_session.commit()
    body, _ids, after = _dashboard(app, user, "?mine=1&include_confirmed=1")
    assert after["CONFIRMED"] == 1, after
    _assert_names(body, ["도면나중연결고객"], ["도면나중이름고객1", "도면나중이름고객2"])
    _body, _ids, again = _dashboard(app, user, "?mine=1")  # 같은 키(컨펌 제외) — 지정 전 값이 아니다
    assert again["CONFIRMED"] == 1, again
