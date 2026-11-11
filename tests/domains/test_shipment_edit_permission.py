"""출고 쓰기 권한 계약 (설계서 2026-11-09-tablet-production-ui §14.4 · D24 · D31, sqlite domains lane).

출고 배정 저장(``POST /api/erp/shipment/update/<id>``)과 AS 추천 4종(as-recommendations ·
prewarm · apply · cancel)을 쓸 수 있는 사람은 관리자 · CS팀 · 출고팀(STAFF · MANAGER)뿐이다.
영업팀(``MEASURE`` 포함)은 보기만 한다. 고정하는 것:

* :func:`can_edit_shipment` 진리표.
* 다섯 API 의 문지기 — 통과 팀은 403 이 아니고, 막힌 팀은 403.
* 정책 ``SHIPMENT_ASSIGN`` 판정이 헬퍼와 같은 답(정책과 데코레이터가 같은 규칙).
* 정책 ``SHIPMENT_EDIT``(물류 상태 · 변경 확인 · 보관 몫)는 영업팀을 그대로 통과시킨다 — D31 범위 밖.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_permissions import can_edit_shipment
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from models import User


def _u(role: str, team: str | None, **extra):
    return SimpleNamespace(id=1, role=role, team=team, is_active=extra.pop("is_active", True),
                           partner_org_id=extra.pop("partner_org_id", None), **extra)


TRUTH_TABLE = [
    ("admin", _u("ADMIN", None), True),
    ("admin-sales", _u("ADMIN", "SALES"), True),
    ("cs-staff", _u("STAFF", "CS"), True),
    ("cs-manager", _u("MANAGER", "CS"), True),
    ("accounting-staff", _u("STAFF", "ACCOUNTING"), True),
    ("shipment-staff", _u("STAFF", "SHIPMENT"), True),
    ("shipment-manager", _u("MANAGER", " shipment "), True),
    ("sales-staff", _u("STAFF", "SALES"), False),
    ("sales-manager", _u("MANAGER", "SALES"), False),
    ("measure-staff", _u("STAFF", "MEASURE"), False),
    ("construction-staff", _u("STAFF", "CONSTRUCTION"), False),
    ("production-staff", _u("STAFF", "PRODUCTION"), False),
    ("partner", _u("PARTNER", "SHIPMENT", partner_org_id=3), False),
    ("partner-org-staff", _u("STAFF", "CS", partner_org_id=3), False),
    ("inactive-cs", _u("STAFF", "CS", is_active=False), False),
    ("inactive-admin", _u("ADMIN", None, is_active=False), False),
    ("viewer-cs", _u("VIEWER", "CS"), False),
    ("viewer-shipment", _u("VIEWER", "SHIPMENT"), False),
    ("none", None, False),
]


@pytest.mark.parametrize("label,user,expected", TRUTH_TABLE, ids=[row[0] for row in TRUTH_TABLE])
def test_can_edit_shipment_truth_table(label, user, expected) -> None:
    assert can_edit_shipment(user) is expected, label


@pytest.mark.parametrize("label,user,expected", TRUTH_TABLE, ids=[row[0] for row in TRUTH_TABLE])
def test_shipment_assign_policy_matches_helper(label, user, expected) -> None:
    """정책 ``SHIPMENT_ASSIGN`` 이 헬퍼와 같은 답을 낸다 — 가드와 데코레이터가 갈라지지 않는다."""
    assert evaluate_policy(POLICY_REGISTRY["SHIPMENT_ASSIGN"], user).allowed is expected, label


def test_shipment_edit_policy_still_allows_sales() -> None:
    """물류 상태 · 변경 확인 · 보관이 쓰는 ``SHIPMENT_EDIT`` 는 바꾸지 않았다(영업팀 그대로 통과)."""
    for team in ("SALES", "MEASURE", "CS", "SHIPMENT"):
        assert evaluate_policy(POLICY_REGISTRY["SHIPMENT_EDIT"], _u("STAFF", team)).allowed, team
    assert POLICY_REGISTRY["SHIPMENT_EDIT"].gate is None


# --------------------------------------------------------------------------- #
# API 문지기(sqlite client) — TESTING 이라 before_request 가드는 꺼져 있고 데코레이터 · 핸들러 판정만 돈다.
# --------------------------------------------------------------------------- #
WRITE_ENDPOINTS = [
    ("/api/erp/shipment/update/987654", {"construction_time": "오전 10시"}),
    ("/api/erp/shipment/as-recommendations", {}),
    ("/api/erp/shipment/as-recommendations/prewarm", {}),
    ("/api/erp/shipment/as-recommendations/apply", {}),
    ("/api/erp/shipment/as-recommendations/cancel", {}),
]

ALLOWED_ACCOUNTS = [("ADMIN", None), ("STAFF", "CS"), ("STAFF", "SHIPMENT"), ("MANAGER", "SHIPMENT")]
BLOCKED_ACCOUNTS = [("STAFF", "SALES"), ("MANAGER", "SALES"), ("STAFF", "MEASURE"),
                    ("STAFF", "CONSTRUCTION"), ("VIEWER", "CS")]


def _login(client, role: str, team: str | None) -> None:
    user = User(
        username=f"ship-perm-{role}-{team}".lower(), password=generate_password_hash("secret"),
        role=role, team=team, name="출고권한", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


@pytest.mark.parametrize("role,team", ALLOWED_ACCOUNTS)
def test_write_endpoints_pass_for_admin_cs_shipment(client, role, team) -> None:
    _login(client, role, team)
    for url, body in WRITE_ENDPOINTS:
        resp = client.post(url, json=body)
        assert resp.status_code not in (401, 403), (role, team, url, resp.status_code, resp.get_data(as_text=True)[:200])


@pytest.mark.parametrize("role,team", BLOCKED_ACCOUNTS)
def test_write_endpoints_forbid_sales_construction_viewer(client, role, team) -> None:
    _login(client, role, team)
    for url, body in WRITE_ENDPOINTS:
        resp = client.post(url, json=body)
        assert resp.status_code == 403, (role, team, url, resp.status_code)
        assert resp.get_json()["success"] is False


# --------------------------------------------------------------------------- #
# 화면 — 편집 칸은 같은 헬퍼 값으로 열고 닫는다(단추만 남고 403 나는 화면 금지).
# --------------------------------------------------------------------------- #
def _make_order():
    from foms.services.datetime_kst import get_today_kst
    from models import Order

    # 출고 화면은 한국 날짜로 '오늘'을 고른다 — date.today() 면 CI(UTC) 아침 9시 전에 하루 어긋난다.
    today = get_today_kst().strftime("%Y-%m-%d")
    order = Order(
        received_date=today, customer_name="출고권한 화면", phone="010-1111-2222", address="Seoul",
        product="장", status="IN_CONSTRUCTION", is_erp_order=True,
        structured_data={"schedule": {"construction": {"date": today}}, "shipment": {"construction_workers": ["가팀"]}},
    )
    db_session.add(order)
    db_session.commit()
    return order


@pytest.mark.parametrize("role,team,editable", [("STAFF", "SHIPMENT", True), ("STAFF", "CS", True),
                                                ("STAFF", "SALES", False), ("STAFF", "MEASURE", False)])
def test_tablet_sheet_assign_button_follows_helper(client, role, team, editable) -> None:
    _login(client, role, team)
    order = _make_order()
    resp = client.get(f"/erp/shipment/tablet-sheet/{order.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert ('data-tablet-sheet-action="shipment-save"' in html) is editable
    assert ("data-tablet-time-chip" in html) is editable
    assert ("data-tablet-assign-time" in html) is editable


@pytest.mark.parametrize("role,team,editable", [("STAFF", "SHIPMENT", True), ("STAFF", "SALES", False)])
def test_pc_dashboard_edit_flag_follows_helper(client, role, team, editable) -> None:
    _login(client, role, team)
    _make_order()
    resp = client.get("/erp/shipment")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f'data-can-edit="{"true" if editable else "false"}"' in html
    assert ('shipment-text-input' in html) is editable
