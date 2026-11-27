"""프리랜서와 옛 생산 판 — 옛 문은 닫혔고, 생산 화면은 새 첫 화면 하나다.

사장님 결정(2026-11-27): 옛 생산 보드를 없애며 프리랜서를 새 첫 화면(``/erp/production/home``)으로 들인다. 옛 주소는 넘겨주지
않는다("이것도 지우기"). 새 첫 화면의 "내 주문만" 시험은 tests/security/test_freelancer_production_home.py 로 옮겼다.

여기 남는 것:

* 옛 생산 보드 · 옛 옆 시트 · 공정 읽기 GET 은 프리랜서에게 닫혀 있다(내 주문이든 남의 주문이든 — 화면은 프리랜서 홈으로,
  API 는 403). 회사 영업 직원은 라우트가 남아 있는 동안 그대로 연다(대조군).
* 생산 묶음에서 뺀 주문 1건 읽기 문(상세 묶음 · QR 라벨 · QR 그림)은 다른 화면 묶음 · "내 주문 일 API" 가 그대로 연다:
  내 주문 200, 남의 주문 404.
* 생산 쓰기는 내 주문이어도 문지기가 막는다(403), 남의 주문은 404 — 예전 뜻("회사 직원 규칙을 따른다")이 바뀌었다.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services import dashboard_counts
from foms.services.auth.freelancer_scope import FREELANCER_DENIED_MSG, FREELANCER_ORDER_NOT_FOUND_MSG
from foms.services.datetime_kst import get_today_kst
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order
from tests.domains.test_auth_finance import _login, _make_user

MATCH = "가짜생산프리"        # 프리랜서 설정의 맞출 이름(주문 담당 칸과 같으면 연결)
USER_NAME = "가짜생산영업"    # 프리랜서 계정 표시 이름 — 이 이름이 담당인 주문은 남의 주문이다
OWN = "생산본인담당"
OTHER = "생산남일반"
BOARD = "/erp/production/dashboard"
_FL_HOME = "/erp/dashboard"


def _today() -> str:
    return get_today_kst().isoformat()


def _order(customer: str, *, manager: str = "아무개", stage: str = "PRODUCTION") -> Order:
    today = _today()
    sd = {
        "parties": {"manager": {"name": manager}, "customer": {"name": customer}, "orderer": {"name": "라홈"}},
        "schedule": {"construction": {"date": today}},
        "workflow": {"stage": stage},
        "items": [{"product_name": "가짜장", "spec_width": "900", "quantity": 1}],
    }
    order = Order(
        received_date=today, customer_name=customer, phone="02-0000-0000", address="가짜시 가짜구",
        product="가짜장", status=stage, manager_name=manager, is_erp_order=True,
        structured_data=sd, erp_stage_code=stage, erp_construction_date=today,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _named_user(role: str, team: str, name: str) -> SimpleNamespace:
    """계정을 만들고 값만 담아 돌려준다(요청이 끝나면 세션이 닫혀 ORM 객체는 못 읽는다)."""
    user = _make_user(role, team)
    user.name = name
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=role, team=team, name=name, partner_org_id=None)


@pytest.fixture()
def world(app):
    """프리랜서 1 · 대조군 영업 직원 1 + 내 주문 1(담당 연결) · 남의 주문 1."""
    with dashboard_counts._cache_lock:
        dashboard_counts._cache.clear()
    fl = _named_user("STAFF", "SALES", USER_NAME)
    save_freelancer(db_session, fl.id, {"match_name": MATCH, "start_month": "2020-01", "tax_type": "NONE", "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    staff = _named_user("STAFF", "SALES", "다른생산영업")
    own = _order(OWN, manager=MATCH)            # 저장 훅이 MANAGER_PRIMARY 연결
    other = _order(OTHER)
    return SimpleNamespace(fl=fl, staff=staff, own_id=own.id, other_id=other.id)


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


def _get(app, user, path: str, *, status: int = 200) -> str:
    resp = _client(app, user).get(path)
    assert resp.status_code == status, (path, resp.status_code)
    return resp.get_data(as_text=True)


# --------------------------------------------------------------------------
# 옛 문 — 프리랜서에게 닫혀 있다(넘겨주기 없음)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    BOARD,
    BOARD + "?mine=0",
    BOARD + "?focus_order={own}",
    BOARD + "?focus_order={other}",
    "/erp/production/tablet-sheet/{own}",
    "/erp/production/tablet-sheet/{other}",
])
def test_old_board_and_side_sheet_are_closed_for_freelancer(world, app, path):
    resp = _client(app, world.fl).get(path.format(own=world.own_id, other=world.other_id))
    assert resp.status_code == 302 and resp.headers["Location"].endswith(_FL_HOME)
    body = resp.get_data(as_text=True)
    assert OWN not in body and OTHER not in body


def test_production_steps_read_api_is_closed_for_freelancer(world, app):
    """공정 읽기 GET — 2026-11-27 지운 길(같은 주소 POST 만 남음). 허용 목록 · "내 주문 일 API" 에 없어 내 주문이든 남의 주문이든 문지기 403."""
    client = _client(app, world.fl)
    for order_id in (world.own_id, world.other_id):
        resp = client.get(f"/api/orders/{order_id}/production/steps")
        assert resp.status_code == 403 and resp.get_json()["error"] == FREELANCER_DENIED_MSG


def test_staff_still_opens_old_doors_while_routes_remain(world, app):
    """대조군: 위 닫힘은 프리랜서 문지기 때문이다 — 회사 영업 직원에게는 프리랜서 문구 · 프리랜서 홈이 나오지 않는다.

    옛 라우트는 2026-11-27 지웠다 — 직원에게는 없는 주소(404)다(프리랜서 홈 302 가 아니다)."""
    client = _client(app, world.staff)
    for path in (BOARD + "?mine=0", f"/erp/production/tablet-sheet/{world.other_id}"):
        resp = client.get(path)
        assert resp.status_code == 404, (path, resp.status_code)
    resp = client.get(f"/api/orders/{world.other_id}/production/steps")
    assert (resp.get_json(silent=True) or {}).get("error") != FREELANCER_DENIED_MSG


# --------------------------------------------------------------------------
# 주문 1건 읽기 문(다른 묶음이 연다) — 내 주문 200, 남의 주문 404
# --------------------------------------------------------------------------
def test_detail_payload_own_opens_other_404(world, app):
    client = _client(app, world.fl)
    mine = client.get(f"/api/orders/{world.own_id}/detail-payload")
    assert mine.status_code == 200 and mine.get_json()["success"] is True
    assert OWN in json.dumps(mine.get_json(), ensure_ascii=False)
    theirs = client.get(f"/api/orders/{world.other_id}/detail-payload")
    assert theirs.status_code == 404 and theirs.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG
    assert OTHER not in theirs.get_data(as_text=True)
    assert _client(app, world.staff).get(f"/api/orders/{world.other_id}/detail-payload").status_code == 200  # 대조군


def test_qr_label_and_svg_own_opens_other_404(world, app):
    assert OWN in _get(app, world.fl, f"/erp/orders/{world.own_id}/label")
    assert OTHER not in _get(app, world.fl, f"/erp/orders/{world.other_id}/label", status=404)
    client = _client(app, world.fl)
    assert client.get(f"/api/orders/{world.own_id}/qr.svg").status_code == 200
    assert client.get(f"/api/orders/{world.other_id}/qr.svg").status_code == 404
    assert OTHER in _get(app, world.staff, f"/erp/orders/{world.other_id}/label")  # 대조군


# --------------------------------------------------------------------------
# 쓰기 — 내 주문이어도 문지기 403, 남의 주문은 404(전수는 test_freelancer_production_home.py)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/orders/{id}/production/start",
    "/api/orders/{id}/production/steps",
    "/api/orders/{id}/production/hold",
])
def test_production_writes_are_closed_by_the_gate(world, app, path):
    mine = _client(app, world.fl).post(path.format(id=world.own_id), json={})
    assert mine.status_code == 403 and mine.get_json()["error"] == FREELANCER_DENIED_MSG
    theirs = _client(app, world.fl).post(path.format(id=world.other_id), json={})
    assert theirs.status_code == 404 and theirs.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG
