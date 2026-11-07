"""화면 묶음: 견적 계산기(WDCalculator) — 켜진 프리랜서는 내 견적 · 내 주문만 (FCOMM-01, 사용자 결정 11-07).

묶음 파일 foms/services/auth/freelancer_screens/wdcalculator.py, 판정 foms/services/wdcalculator/freelancer_estimates.py.

* 계산기 화면 · 계산은 열린다. ``?order_id=`` 가 남의 주문이면 화면부터 404.
* 견적 "내 것" = 내 주문에 이은 견적(읽기는 하나라도, 고치기 · 지우기는 모두 내 주문) + 이 로그인에서 만든 안 이은 견적.
  남의 견적 · 남이 만든 안 이은 견적 · 없는 번호는 같은 404(존재 여부를 알리지 않는다).
* 주문 찾기는 내 주문만, 잇기 · 풀기 · 저장의 주문 번호도 내 주문만(404).
* 주문 저장 뒤 견적 맞추기(wdc-estimate-sync)는 모두에게 고침 — 본문 견적이 URL 주문에 이어져 있어야 고친다.
* 대조군: 프리랜서 아닌 영업 직원은 전과 같다(모든 견적 · 주문).
"""
from __future__ import annotations

import itertools
import json

import pytest

import foms.api.wdcalculator.blueprint as wd_module
from db import db_session
from foms.services.auth.freelancer_scope import (
    FREELANCER_ALLOWED_ENDPOINTS,
    FREELANCER_ORDER_NOT_FOUND_MSG,
    FREELANCER_ORDER_QUERY_ARGS,
    FREELANCER_ORDER_VIEW_ARGS,
)
from foms.services.auth.freelancer_screens import wdcalculator as screen
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from foms.services.wdcalculator.freelancer_estimates import SESSION_KEY
from models import Order, OrderFreelancerLink, User
from tests.domains.test_auth_finance import _login, _make_user
from wdcalculator_db import init_wdcalculator_db, wd_calculator_session
from wdcalculator_models import Estimate, EstimateHistory, EstimateOrderMatch, WDCalculatorProductSettings

_seq = itertools.count(1)
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}
_CUSTOMER = "계산기가짜고객"
_EST_404 = "견적을 찾을 수 없습니다."


# --------------------------------------------------------------------------
# 시드(가짜 값)
# --------------------------------------------------------------------------
def _clear_wd() -> None:
    for model in (EstimateOrderMatch, EstimateHistory, Estimate, WDCalculatorProductSettings):
        wd_calculator_session.query(model).delete()
    wd_calculator_session.commit()


@pytest.fixture
def wd(app, tmp_path, monkeypatch):
    """계산기 표를 비우고 가짜 제품 1개 단가표를 쓴다(데이터 파일 대신)."""
    products = tmp_path / "products.json"
    products.write_text(json.dumps({"products": [{
        "id": 1, "name": "가짜장", "pricing_type": "30cm", "additional_options": [],
        "coupon_type": "percentage", "coupon_value": 0, "price_30cm": 1000, "price_1cm": 10,
    }]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(wd_module, "WD_CALCULATOR_DATA_PATH", str(products))
    init_wdcalculator_db()
    _clear_wd()
    yield wd_calculator_session
    wd_calculator_session.rollback()
    _clear_wd()
    wd_calculator_session.remove()


def _freelancer() -> User:
    user = _make_user("STAFF", "SALES")
    user.match_name = f"가짜계산기담당{next(_seq)}"
    version, _cfg, _changed = save_freelancer(
        db_session, user.id,
        {"match_name": user.match_name, "start_month": "2020-01", "tax_type": "NONE", "active": True},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return user


def _order(manager: str = "남의담당") -> int:
    sd = {
        "parties": {"manager": {"name": manager}, "orderer": {"name": "라홈"}, "customer": {"name": _CUSTOMER}},
        "schedule": {"measurement": {"date": "2030-01-05"}},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "MEASURE"},
    }
    order = Order(
        received_date="2030-01-01", customer_name=_CUSTOMER, phone="02-0000-0000", address="가짜시",
        product="가짜장", status="MEASURE", manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_stage_code="MEASURE", erp_measurement_date="2030-01-05",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _ensure_link(order_id: int, user: User) -> None:
    if not db_session.query(OrderFreelancerLink).filter_by(order_id=order_id, user_id=user.id).first():
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user.id, relation="MANAGER_PRIMARY"))
        db_session.commit()


def _estimate(name: str, *order_ids: int) -> int:
    est = Estimate(customer_name=name, estimate_data={"totalPrice": 1000, "estimates": []})
    wd_calculator_session.add(est)
    wd_calculator_session.flush()
    for oid in order_ids:
        wd_calculator_session.add(EstimateOrderMatch(estimate_id=est.id, order_id=oid))
    wd_calculator_session.commit()
    return est.id


def _client(app, user: User):
    client = app.test_client()
    _login(client, user)
    return client


@pytest.fixture
def world(app, wd):
    fl = _freelancer()
    own, other = _order(manager=fl.match_name), _order()
    _ensure_link(own, fl)
    return {
        "fl_id": fl.id, "own": own, "other": other,
        "e_own": _estimate("가짜내견적", own),
        "e_other": _estimate("가짜남견적", other),
        "e_loose": _estimate("가짜안이은견적"),
        "e_shared": _estimate("가짜같이이은견적", own, other),
    }


def _fl(world) -> User:
    """세계의 프리랜서(요청 뒤 세션이 닫혀도 다시 읽는다)."""
    return db_session.get(User, world["fl_id"])


def _is_404(resp, message: str = _EST_404) -> bool:
    body = resp.get_json(silent=True) or {}
    return resp.status_code == 404 and body.get("success") is False and body.get("error") == message


def _payload(name: str = "가짜저장", **extra):
    return {"customer_name": name, "estimate_data": {"totalPrice": 2000, "estimates": []}, **extra}


def _search_ids(client) -> set[int]:
    body = client.get("/api/wdcalculator/search-estimates").get_json()
    assert body["success"] is True
    return {e["id"] for e in body["estimates"]}


def _total(estimate_id: int) -> int:
    wd_calculator_session.expire_all()
    return wd_calculator_session.query(Estimate).filter(Estimate.id == estimate_id).first().estimate_data["totalPrice"]


# --------------------------------------------------------------------------
# 묶음 파일 등록
# --------------------------------------------------------------------------
def test_screen_file_merged_into_gate():
    assert screen.ALLOWED_ENDPOINTS <= FREELANCER_ALLOWED_ENDPOINTS
    assert FREELANCER_ORDER_VIEW_ARGS["wdcalculator.api_orders_wdc_estimate_sync"] == ("order_id",)
    assert FREELANCER_ORDER_QUERY_ARGS["wdcalculator.wdcalculator"] == ("order_id",)
    # 설정 화면 · 설정 바꾸기는 열지 않는다.
    for closed in ("wdcalculator.wdcalculator_product_settings", "wdcalculator.api_wdcalculator_save_product",
                   "wdcalculator.api_wdcalculator_delete_product", "wdcalculator.api_wdcalculator_save_category",
                   "wdcalculator.api_wdcalculator_save_notes_category",
                   "wdcalculator.api_wdcalculator_get_notes_categories",
                   "wdcalculator.api_wdcalculator_save_spec_field_preset"):
        assert closed not in FREELANCER_ALLOWED_ENDPOINTS, closed


# --------------------------------------------------------------------------
# 화면 · 계산
# --------------------------------------------------------------------------
def test_page_and_calculate_open(app, world):
    client = _client(app, _fl(world))
    assert client.get("/wdcalculator").status_code == 200
    assert client.get("/wdcalculator?embedded=1").status_code == 200
    assert client.get(f"/wdcalculator?order_id={world['own']}&estimate_id={world['e_own']}").status_code == 200
    assert client.get(f"/wdcalculator?order_id={world['other']}").status_code == 404
    resp = client.post("/api/wdcalculator/calculate", json={"product_id": 1, "width_mm": 600})
    assert resp.status_code == 200 and resp.get_json()["success"] is True


# --------------------------------------------------------------------------
# 견적 찾기 · 열기 · 지우기
# --------------------------------------------------------------------------
def test_search_lists_only_my_estimates(app, world):
    client = _client(app, _fl(world))
    assert _search_ids(client) == {world["e_own"], world["e_shared"]}
    # 검색어를 넣어도 남의 견적은 안 나온다(이름 · 번호 검색).
    body = client.get("/api/wdcalculator/search-estimates?customer_name=가짜남견적").get_json()
    assert body["estimates"] == []
    body = client.get(f"/api/wdcalculator/search-estimates?customer_name={world['e_other']}").get_json()
    assert world["e_other"] not in {e["id"] for e in body["estimates"]}


def test_open_only_my_estimates_404_otherwise(app, world):
    client = _client(app, _fl(world))
    for key in ("e_own", "e_shared"):
        resp = client.get(f"/api/wdcalculator/estimate/{world[key]}")
        assert resp.status_code == 200 and resp.get_json()["estimate"]["id"] == world[key], key
    # 남의 견적 · 남이 만든 안 이은 견적 · 없는 번호는 같은 404.
    for estimate_id in (world["e_other"], world["e_loose"], 999999):
        assert _is_404(client.get(f"/api/wdcalculator/estimate/{estimate_id}")), estimate_id


def test_delete_needs_every_match_mine(app, world):
    client = _client(app, _fl(world))
    for key in ("e_other", "e_loose", "e_shared"):
        assert _is_404(client.delete(f"/api/wdcalculator/estimate/{world[key]}")), key
    wd_calculator_session.expire_all()
    assert wd_calculator_session.query(Estimate).count() == 4
    resp = client.delete(f"/api/wdcalculator/estimate/{world['e_own']}")
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    wd_calculator_session.expire_all()
    assert wd_calculator_session.query(Estimate).filter(Estimate.id == world["e_own"]).first() is None


# --------------------------------------------------------------------------
# 저장 — 새 견적은 이 로그인 동안 내 것, 고치기는 내 견적만, 주문 번호는 내 주문만
# --------------------------------------------------------------------------
def test_save_new_estimate_is_mine_for_this_login(app, world):
    client = _client(app, _fl(world))
    resp = client.post("/api/wdcalculator/save-estimate", json=_payload())
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    new_id = resp.get_json()["estimate_id"]
    with client.session_transaction() as sess:
        assert sess[SESSION_KEY] == {"u": world["fl_id"], "ids": [new_id]}
    assert new_id in _search_ids(client)
    assert client.get(f"/api/wdcalculator/estimate/{new_id}").status_code == 200
    again = client.post("/api/wdcalculator/save-estimate", json=_payload(estimate_id=new_id, estimate_data={
        "totalPrice": 3000, "estimates": []}))
    assert again.status_code == 200 and again.get_json()["estimate_id"] == new_id
    assert _total(new_id) == 3000

    # 다른 프리랜서 · 같은 사람의 새 로그인에는 안 보인다(안 이은 견적).
    stranger = _client(app, _freelancer())
    assert _is_404(stranger.get(f"/api/wdcalculator/estimate/{new_id}"))
    assert new_id not in _search_ids(stranger)
    relogin = _client(app, _fl(world))
    assert _is_404(relogin.get(f"/api/wdcalculator/estimate/{new_id}"))

    # 내 주문에 이으면 새 로그인에서도 보인다.
    assert client.post("/api/wdcalculator/match-order",
                       json={"estimate_id": new_id, "order_id": world["own"]}).get_json()["success"] is True
    assert relogin.get(f"/api/wdcalculator/estimate/{new_id}").status_code == 200


def test_session_list_is_bound_to_user(app, world):
    """세션에 남은 다른 사람 번호 목록(관리자가 프리랜서로 들어가 본 뒤 등)은 쓰지 않는다."""
    client = _client(app, _fl(world))
    with client.session_transaction() as sess:
        sess[SESSION_KEY] = {"u": world["fl_id"] + 1000, "ids": [world["e_loose"]]}
    assert _is_404(client.get(f"/api/wdcalculator/estimate/{world['e_loose']}"))
    assert world["e_loose"] not in _search_ids(client)


def test_save_update_only_my_estimates(app, world):
    client = _client(app, _fl(world))
    for key in ("e_other", "e_loose", "e_shared", None):
        estimate_id = world[key] if key else 999999
        resp = client.post("/api/wdcalculator/save-estimate", json=_payload(estimate_id=estimate_id))
        assert _is_404(resp, "수정할 견적을 찾을 수 없습니다."), key
    for key in ("e_other", "e_loose", "e_shared"):
        assert _total(world[key]) == 1000, key
    ok = client.post("/api/wdcalculator/save-estimate", json=_payload(estimate_id=world["e_own"]))
    assert ok.status_code == 200 and ok.get_json()["success"] is True
    assert _total(world["e_own"]) == 2000


def test_save_with_order_id_only_my_order(app, world):
    client = _client(app, _fl(world))
    for order_id in (world["other"], 999999):
        assert _is_404(client.post("/api/wdcalculator/save-estimate", json=_payload(order_id=order_id)),
                       FREELANCER_ORDER_NOT_FOUND_MSG), order_id
    wd_calculator_session.expire_all()
    assert wd_calculator_session.query(Estimate).count() == 4
    ok = client.post("/api/wdcalculator/save-estimate", json=_payload(order_id=world["own"]))
    assert ok.status_code == 200 and ok.get_json()["order_id"] == world["own"]


# --------------------------------------------------------------------------
# 주문 찾기 · 잇기 · 풀기
# --------------------------------------------------------------------------
def test_search_orders_only_my_orders(app, world):
    client = _client(app, _fl(world))
    body = client.get(f"/api/wdcalculator/search-orders?customer_name={_CUSTOMER}").get_json()
    assert body["success"] is True and [o["id"] for o in body["orders"]] == [world["own"]]


def test_match_only_my_order_and_my_estimate(app, world):
    client = _client(app, _fl(world))
    new_id = client.post("/api/wdcalculator/save-estimate", json=_payload()).get_json()["estimate_id"]
    # 남의 주문 · 없는 주문에는 못 잇는다.
    for order_id in (world["other"], 999999):
        resp = client.post("/api/wdcalculator/match-order", json={"estimate_id": new_id, "order_id": order_id})
        assert _is_404(resp, FREELANCER_ORDER_NOT_FOUND_MSG), order_id
    # 남의 견적 · 남이 만든 안 이은 견적은 내 주문에도 못 잇는다(남의 견적을 가져오는 길).
    for key in ("e_other", "e_loose"):
        resp = client.post("/api/wdcalculator/match-order", json={"estimate_id": world[key], "order_id": world["own"]})
        assert _is_404(resp), key
    wd_calculator_session.expire_all()
    assert wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.estimate_id.in_([new_id, world["e_other"], world["e_loose"]]),
        EstimateOrderMatch.order_id == world["own"]).count() == 0
    ok = client.post("/api/wdcalculator/match-order", json={"estimate_id": new_id, "order_id": world["own"]})
    assert ok.status_code == 200 and ok.get_json()["success"] is True


def test_unmatch_only_my_order(app, world):
    client = _client(app, _fl(world))
    for body in ({"order_id": world["other"]}, {"order_id": world["other"], "estimate_id": world["e_other"]},
                 {"order_id": world["other"], "estimate_id": world["e_shared"]}):
        assert _is_404(client.post("/api/wdcalculator/unmatch-order", json=body), FREELANCER_ORDER_NOT_FOUND_MSG)
    wd_calculator_session.expire_all()
    assert wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.order_id == world["other"]).count() == 2
    ok = client.post("/api/wdcalculator/unmatch-order",
                     json={"order_id": world["own"], "estimate_id": world["e_shared"]})
    assert ok.status_code == 200 and ok.get_json()["removed"] == 1
    wd_calculator_session.expire_all()
    # 남의 주문 쪽 이음은 그대로.
    assert wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.estimate_id == world["e_shared"]).one().order_id == world["other"]


# --------------------------------------------------------------------------
# 주문 저장 뒤 견적 맞추기(wdc-estimate-sync)
# --------------------------------------------------------------------------
def test_sync_freelancer_only_estimates_of_url_order_all_mine(app, world):
    client = _client(app, _fl(world))
    url = f"/api/orders/{world['own']}/wdc-estimate-sync"
    # 남의 주문 URL 은 문지기가 404.
    assert _is_404(client.post(f"/api/orders/{world['other']}/wdc-estimate-sync", json=_payload()),
                   FREELANCER_ORDER_NOT_FOUND_MSG)
    # 내 주문 URL 이어도 본문 견적이 그 주문에 안 이었거나(남의 · 안 이은 · 없는) 남의 주문에도 이었으면 404.
    for key in ("e_other", "e_loose", "e_shared", None):
        estimate_id = world[key] if key else 999999
        resp = client.post(url, json=_payload(estimate_id=estimate_id))
        assert resp.status_code == 404 and resp.get_json()["success"] is False, key
    for key in ("e_other", "e_loose", "e_shared"):
        assert _total(world[key]) == 1000, key
    ok = client.post(url, json=_payload(estimate_id=world["e_own"]))
    assert ok.status_code == 200 and ok.get_json()["estimate_id"] == world["e_own"]
    assert _total(world["e_own"]) == 2000
    # 번호 없이 부르면 새 견적 — 이 로그인 동안 내 것.
    created = client.post(url, json=_payload()).get_json()["estimate_id"]
    assert client.get(f"/api/wdcalculator/estimate/{created}").status_code == 200


def test_sync_regression_for_normal_staff(app, world):
    """보안 검토 회귀(모두에게): 다른 주문에 이은 견적 번호로 덮어쓰지 못한다."""
    client = _client(app, _make_user("STAFF", "SALES"))
    resp = client.post(f"/api/orders/{world['own']}/wdc-estimate-sync",
                       json=_payload(estimate_id=world["e_other"]))
    assert resp.status_code == 404 and resp.get_json()["success"] is False
    assert _total(world["e_other"]) == 1000
    ok = client.post(f"/api/orders/{world['other']}/wdc-estimate-sync",
                     json=_payload(estimate_id=world["e_other"]))
    assert ok.status_code == 200 and ok.get_json()["estimate_id"] == world["e_other"]
    assert _total(world["e_other"]) == 2000


# --------------------------------------------------------------------------
# 대조군 — 프리랜서 아닌 영업 직원은 전과 같다
# --------------------------------------------------------------------------
def test_normal_sales_staff_unaffected(app, world):
    client = _client(app, _make_user("STAFF", "SALES"))
    every = {world[k] for k in ("e_own", "e_other", "e_loose", "e_shared")}
    assert _search_ids(client) == every
    for estimate_id in every:
        assert client.get(f"/api/wdcalculator/estimate/{estimate_id}").status_code == 200
    # 없는 번호는 전과 같이 200 + 실패(404 아님).
    missing = client.get("/api/wdcalculator/estimate/999999")
    assert missing.status_code == 200 and missing.get_json()["success"] is False
    body = client.get(f"/api/wdcalculator/search-orders?customer_name={_CUSTOMER}").get_json()
    assert {o["id"] for o in body["orders"]} == {world["own"], world["other"]}
    resp = client.post("/api/wdcalculator/save-estimate", json=_payload(estimate_id=world["e_loose"]))
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    with client.session_transaction() as sess:
        assert SESSION_KEY not in sess  # 프리랜서 아니면 세션에 두지 않는다
    match = client.post("/api/wdcalculator/match-order", json={"estimate_id": world["e_loose"], "order_id": world["other"]})
    assert match.get_json()["success"] is True
    assert client.delete(f"/api/wdcalculator/estimate/{world['e_shared']}").get_json()["success"] is True
