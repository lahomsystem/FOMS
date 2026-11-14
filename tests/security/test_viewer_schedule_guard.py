"""F-01 — 조회 전용(VIEWER) 계정은 시공일 쓰기 길 셋을 못 지난다 · 문지기 함수가 있는 정책도 VIEWER 막기가 먼저다.

결함: CS · 영업팀 VIEWER 가 ``CONSTRUCTION_SCHEDULE_EDIT`` 의 길 셋(협력사 희망 판 [확정] · [되돌리기] · 주문 화면 시공일 칸)을
지나 시공일을 썼다. 엔진(:func:`evaluate_policy`)이 문지기 함수(1-b)를 VIEWER 막기(2)보다 먼저 돌렸고, 그 문지기
``can_edit_construction_schedule`` 은 팀만 보는 ``can_edit_erp`` 를 그대로 믿었다.

대조군: 같은 팀 STAFF · MANAGER 와 ADMIN 은 그대로 200, VIEWER 의 읽기(출고 화면 · 주문 화면 열기)는 그대로 열린다.
시험 자료(이름 · 전화 · 주소)는 전부 지어낸 값이다.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_permissions import can_edit_construction_schedule
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, Policy, evaluate_policy
from models import Order, OrderFieldChange, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _user,
    world,
)

#: 우리 직원 팀 전부(+ 별칭 · 옛 이름 · 팀 없음) — VIEWER 표의 행.
_ALL_TEAMS = ("CS", "SALES", "ACCOUNTING", "MEASURE", "SHIPMENT", "DRAWING", "PRODUCTION", "CONSTRUCTION", None)
_VIEWER_REASON = "조회 전용 계정은 이 작업을 할 수 없습니다."


@pytest.fixture(params=[True, False], ids=["guard_on", "guard_off"])
def guard(request, app):
    """before_request 가드를 켜고(운영과 같음) / 끄고(핸들러 안 재검사만) 둘 다 본다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = request.param
    yield request.param
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


@pytest.fixture
def policy_on(app):
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _day(n: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=n)).isoformat()


def _partner_order(app, partner_id, *, name="가짜고객") -> int:
    resp = _create(app, partner_id, {**_PAYLOAD, "customer_name": name,
                                     "requested_construction_date": _day(3), "requested_construction_time": ""})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


_ROUTES = {
    "confirm": "/api/erp/shipment/partner-requests/{oid}/confirm",
    "set": "/api/orders/{oid}/construction-schedule",
    "revert": "/api/erp/shipment/partner-requests/{oid}/revert",
}


def _post(app, user_id, kind, order_id, date=None):
    client = _client(app, db_session.get(User, user_id))
    body = {} if kind == "revert" else {"date": date or _day(4), "time": ""}
    return client.post(_ROUTES[kind].format(oid=order_id), json=body)


def _snapshot(order_id):
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    changes = db_session.query(OrderFieldChange).filter(OrderFieldChange.order_id == order_id).count()
    schedule = ((order.structured_data or {}).get("schedule") or {}).get("construction")
    return order.erp_construction_date, schedule, changes


def _ready_order(app, world, kind) -> int:
    """길마다 본체가 돌면 성공할 주문 — 되돌리기는 STAFF 가 먼저 정해 둔다."""
    order_id = _partner_order(app, world["partner_a"])
    if kind == "revert":
        assert _post(app, world["staff"], "confirm", order_id, _day(3)).status_code == 200
    return order_id


# --------------------------------------------------------------------------- #
# 1. 재현 — VIEWER(CS · 영업)는 길 셋 모두 403, 본체 미실행 · DB 변화 0
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", sorted(_ROUTES))
@pytest.mark.parametrize("team", ["CS", "SALES"])
def test_viewer_cannot_write_construction_schedule(app, world, guard, team, kind):
    order_id = _ready_order(app, world, kind)
    before = _snapshot(order_id)
    viewer = _user(role="VIEWER", team=team).id

    resp = _post(app, viewer, kind, order_id)

    assert resp.status_code == 403, (team, kind, resp.status_code, resp.get_json())
    body = resp.get_json()
    assert body["success"] is False and body["code"] == "FORBIDDEN"
    if guard:  # 운영 — before_request 가드가 핸들러 전에 막는다
        assert resp.headers.get("X-Auth-Policy") == "denied"
    assert _snapshot(order_id) == before


@pytest.mark.parametrize("team", ["CS", "SALES"])
def test_viewer_cannot_write_schedule_through_field_update(app, world, policy_on, team):
    """시공일을 쓰는 네 번째 길(옛 칸 저장 — 핸들러는 팀만 보는 can_edit_erp) 도 VIEWER 는 가드에서 막힌다."""
    order_id = _partner_order(app, world["partner_a"], name="칸저장고객")
    before = _snapshot(order_id)
    client = _client(app, _user(role="VIEWER", team=team))
    resp = client.post("/api/update_order_field", json={"order_id": order_id, "field": "scheduled_date", "value": _day(6)})
    assert resp.status_code == 403 and resp.headers.get("X-Auth-Policy") == "denied"
    assert _snapshot(order_id) == before


# --------------------------------------------------------------------------- #
# 2. 대조군 — 같은 팀 STAFF · MANAGER, ADMIN 은 그대로 쓴다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role,team", [
    ("STAFF", "CS"), ("STAFF", "SALES"), ("MANAGER", "CS"), ("MANAGER", "SALES"), ("ADMIN", None),
])
def test_same_team_staff_manager_and_admin_still_write_schedule(app, world, policy_on, role, team):
    actor = _user(role=role, team=team).id
    order_id = _partner_order(app, world["partner_a"], name=f"대조{role}{team}")
    for kind, date in (("confirm", _day(3)), ("set", _day(5)), ("revert", None)):
        resp = _post(app, actor, kind, order_id, date)
        assert resp.status_code == 200, (role, team, kind, resp.get_json())
        assert resp.headers.get("X-Auth-Policy") is None
    assert not _snapshot(order_id)[0]  # 되돌리기까지 끝나 시공일이 비었다


# --------------------------------------------------------------------------- #
# 3. VIEWER 읽기 길은 그대로 — 출고 화면 · 주문 화면은 열리고, 시공일 쓰기 단추만 숨는다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("team", ["CS", "SALES"])
def test_viewer_read_paths_still_open_and_write_controls_hidden(app, world, policy_on, team):
    order_id = _partner_order(app, world["partner_a"], name="읽기고객")
    viewer = _client(app, _user(role="VIEWER", team=team))

    page = viewer.get("/erp/shipment")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "data-prb" in html and f'data-prb-chip="{order_id}"' in html  # 희망 판 · 주문 칩은 보인다
    assert 'data-can-set="0"' in html and 'draggable="true"' not in html  # 끌기 · 정하기는 없다

    # 주문 읽기(전사 공용 조회 — 상세 패널 · 구조화 데이터). 주문 편집 화면(/edit)은 원래 STAFF 이상 전용(role_required)이라 대상 아님.
    for path in (f"/api/orders/{order_id}/structured", f"/api/orders/{order_id}/detail-payload"):
        read = viewer.get(path)
        assert read.status_code == 200 and read.get_json()["success"] is True, (path, read.status_code)

    # 대조군: 같은 팀 STAFF 는 판에서 정할 수 있다
    staff_html = _client(app, _user(role="STAFF", team=team)).get("/erp/shipment").get_data(as_text=True)
    assert 'data-can-set="1"' in staff_html and 'draggable="true"' in staff_html


# --------------------------------------------------------------------------- #
# 4. 엔진 표 — 문지기 함수가 있는 정책을 포함해 VIEWER 를 허용하지 않는 정책은 전부 VIEWER 403
# --------------------------------------------------------------------------- #
def _person(role, team, uid=990001):
    return SimpleNamespace(id=uid, role=role, team=team, is_active=True, partner_org_id=None, name="가짜직원")


_GATED = sorted(pid for pid, p in POLICY_REGISTRY.items() if p.gate is not None)
_NON_VIEWER = sorted(pid for pid, p in POLICY_REGISTRY.items() if not p.viewer)


def test_gated_policy_list_is_what_this_table_covers():
    """문지기 정책이 새로 생기면 이 표가 자동으로 그 정책까지 덮는다 — 지금 9종, 전부 VIEWER 비허용."""
    assert _GATED == sorted([
        "CONSTRUCTION_SCHEDULE_EDIT", "CS_AGENT_SEND", "NAVER_INGEST_RUN", "PARTNER_STATEMENT",
        "SALES_COMMISSION_WRITE", "SETTLEMENT_CHANNEL_READ", "SETTLEMENT_CHANNEL_SYNC",
        "SETTLEMENT_DASHBOARD_READ", "SHIPMENT_ASSIGN",
    ])
    assert all(not POLICY_REGISTRY[pid].viewer for pid in _GATED)


@pytest.mark.parametrize("team", _ALL_TEAMS)
@pytest.mark.parametrize("policy_id", _NON_VIEWER)
def test_viewer_denied_by_every_non_viewer_policy(policy_id, team):
    decision = evaluate_policy(POLICY_REGISTRY[policy_id], _person("VIEWER", team))
    assert not decision.allowed, (policy_id, team)
    assert decision.status == 403 and decision.code == "FORBIDDEN"
    assert decision.reason == _VIEWER_REASON  # 문지기 함수가 아니라 VIEWER 막기가 거절했다


@pytest.mark.parametrize("policy_id", _GATED)
def test_gated_policy_controls_admin_passes(policy_id):
    """대조군 — 문지기 정책 9종 모두 ADMIN 은 통과(VIEWER 막기가 다른 역할을 건드리지 않는다)."""
    assert evaluate_policy(POLICY_REGISTRY[policy_id], _person("ADMIN", None)).allowed


@pytest.mark.parametrize("policy_id", sorted(pid for pid, p in POLICY_REGISTRY.items() if p.viewer and not p.anonymous))
def test_viewer_allowed_policies_unchanged(policy_id):
    """VIEWER 허용 정책(알림 · 구독 · 긴급 호출 · 계산 · 물어보기 · 자기 계정)은 그대로 통과."""
    assert evaluate_policy(POLICY_REGISTRY[policy_id], _person("VIEWER", "CS")).allowed


# 순서 자체를 못 박는 가짜 문지기 — 실제 문지기 함수가 VIEWER 를 걸러 주든 말든 엔진이 먼저 막는다.
def gate_yes(user):  # noqa: D401 — 시험용 문지기
    return True


def gate_no(user):  # noqa: D401 — 시험용 문지기
    return False


_YES = f"{__name__}:gate_yes"
_NO = f"{__name__}:gate_no"


def test_viewer_deny_runs_before_gate_function():
    policy = Policy("TEST_GATED_WRITE", teams=("CS",), gate=_YES)
    assert not evaluate_policy(policy, _person("VIEWER", "CS")).allowed
    assert evaluate_policy(policy, _person("STAFF", "CS")).allowed  # 문지기는 그대로 STAFF 를 판정


def test_viewer_allowed_policy_with_gate_still_asks_gate():
    """VIEWER 허용 정책에 문지기가 붙으면 VIEWER 도 문지기 판정을 받는다(막기를 앞에 둬도 문지기를 건너뛰지 않는다)."""
    assert evaluate_policy(Policy("TEST_V_YES", teams="*", viewer=True, gate=_YES), _person("VIEWER", "CS")).allowed
    assert not evaluate_policy(Policy("TEST_V_NO", teams="*", viewer=True, gate=_NO), _person("VIEWER", "CS")).allowed


# --------------------------------------------------------------------------- #
# 5. 문지기 함수 — 시공일 쓰기 판정(화면 단추도 같은 함수)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role,team,expected", [
    ("VIEWER", "CS", False), ("VIEWER", "SALES", False), ("VIEWER", "ACCOUNTING", False),
    ("VIEWER", "MEASURE", False), ("VIEWER", "SHIPMENT", False), ("VIEWER", None, False),
    ("STAFF", "CS", True), ("STAFF", "SALES", True), ("STAFF", "ACCOUNTING", True), ("STAFF", "MEASURE", True),
    ("STAFF", "SHIPMENT", True), ("MANAGER", "CS", True), ("MANAGER", "SHIPMENT", True), ("ADMIN", None, True),
    ("STAFF", "CONSTRUCTION", False), ("STAFF", "DRAWING", False), ("STAFF", "PRODUCTION", False),
])
def test_can_edit_construction_schedule_table(role, team, expected):
    assert can_edit_construction_schedule(_person(role, team)) is expected


def test_can_edit_construction_schedule_rejects_partner_and_inactive():
    partner = SimpleNamespace(id=1, role="PARTNER", team=None, is_active=True, partner_org_id=7)
    inactive = SimpleNamespace(id=2, role="STAFF", team="CS", is_active=False, partner_org_id=None)
    assert can_edit_construction_schedule(partner) is False
    assert can_edit_construction_schedule(inactive) is False
    assert can_edit_construction_schedule(None) is False
