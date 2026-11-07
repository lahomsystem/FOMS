"""FCOMM-01 T5 — 영업 수수료 탭 API(읽기 모델 · 줄 상태 · 시공비 저장 · 권한).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §2.1 · §3 · §9 · §11.2.
요율 · 금액 · 이름은 모두 가짜 값이다(저장소 공개 — 실제 요율은 설정에만 있다).
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.sales_commission.read_model import commission_row_for_order, commission_rows
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from models import (
    ExternalOrderLink,
    Order,
    OrderFieldChange,
    PartnerOrg,
    SalesCommissionInput,
    SecurityLog,
    User,
)
from tests.domains.test_auth_finance import _login, _make_user

ROWS = "/api/sales-commission/rows"
FREELANCERS = "/api/sales-commission/freelancers"
INPUTS = "/api/sales-commission/inputs"
MATCH = "가짜프리"
OTHER_MATCH = "다른가짜"
MONTH = "2030-03"
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}

_ALLOWED = [("ADMIN", None), ("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")]
_DENIED = [("MANAGER", "CS"), ("STAFF", "SALES")]


# --------------------------------------------------------------------------
# 시드
# --------------------------------------------------------------------------
def _add_freelancer(match_name: str, start_month: str = "2030-01"):
    user = _make_user("STAFF", "SALES")
    version, _cfg, _changed = save_freelancer(
        db_session, user.id, {"match_name": match_name, "start_month": start_month, "tax_type": "NONE", "active": True},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return user


def _order(*, manager: str = "", orderer: str = "", stage: str = "CS", construction: str | None = "2030-02-10",
           measurement: str | None = "2030-01-05", price: int = 2_500_000, customer: str = "가짜고객",
           status: str = "COMPLETED", partner_org_id: int | None = None, deleted_at: str | None = None,
           extra: dict | None = None) -> int:
    schedule: dict = {}
    if construction is not None:
        schedule["construction"] = {"date": construction}
    if measurement is not None:
        schedule["measurement"] = {"date": measurement}
    sd = {
        "parties": {"manager": {"name": manager}, "orderer": {"name": orderer}, "customer": {"name": customer}},
        "schedule": schedule,
        "items": [{"product_name": "가짜장", "price": price}],
        "workflow": {"stage": stage},
        **(extra or {}),
    }
    order = Order(
        received_date="2030-01-01", customer_name=customer, phone="010-0000-0000", address="가짜시",
        product="가짜장", status=status, manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_stage_code=stage, erp_construction_date=construction, erp_measurement_date=measurement,
        partner_org_id=partner_org_id, deleted_at=deleted_at,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _input(order_id: int, install_cost=None, rate_override_bp=None):
    db_session.add(SalesCommissionInput(order_id=order_id, install_cost=install_cost,
                                        rate_override_bp=rate_override_bp, version=1))
    db_session.commit()


@pytest.fixture
def world(app):
    """프리랜서 둘 · 주문 여럿. 고른 달은 2030-03(시공 완료 기준이면 이 달까지)."""
    fl = _add_freelancer(MATCH)
    other = _add_freelancer(OTHER_MATCH)
    employee = _make_user("STAFF", "CS")
    partner = PartnerOrg(name="가짜협력사")
    db_session.add(partner)
    db_session.commit()
    ded = {"settlement": {"deductions": [
        {"id": "d1", "department": "SALES", "charge_to_user_id": fl.id, "amount": -100_000, "reason": "가짜 재방문",
         "created_at": "2030-02-11T10:00:00", "created_by": "가짜회계"},
        {"id": "d2", "department": "SALES", "charge_to_user_id": fl.id, "amount": -999, "voided_at": "2030-02-12"},
        {"id": "d3", "department": "CS", "amount": -777},
    ]}}
    ids = {
        "lahom": _order(manager=MATCH, orderer="라홈 가짜점", extra=ded),
        "personal": _order(manager="아무개", orderer=MATCH, stage="COMPLETED", construction="2030-03-01",
                           measurement="2030-01-20", price=2_000_000),
        "manual": _order(manager=MATCH, orderer="숨고", construction="2030-03-05", measurement="2030-02-01"),
        "naver": _order(manager=MATCH, orderer="가짜손님", construction="2030-01-20", measurement="2030-01-03"),
        "production": _order(manager=MATCH, orderer="하우드", stage="PRODUCTION", construction="2030-03-02",
                             measurement="2030-01-25"),
        "before_start": _order(manager=MATCH, orderer="라홈", measurement="2029-12-28"),
        "future": _order(manager=MATCH, orderer="라홈", construction="2030-04-01"),
        "other_fl": _order(manager=OTHER_MATCH, orderer="라홈"),
        "employee": _order(manager=employee.name, orderer="라홈"),
        "partner": _order(manager=MATCH, orderer="라홈", partner_org_id=partner.id),
        "draft": _order(manager=MATCH, orderer="라홈", status="DRAFT"),
        "deleted": _order(manager=MATCH, orderer="라홈", deleted_at="2030-02-20"),
        "near": _order(manager=MATCH + "2", orderer="라홈", customer="비슷한고객"),
    }
    db_session.add(ExternalOrderLink(channel="NAVER", external_id="FAKE-1", order_id=ids["naver"]))
    db_session.add(OrderFieldChange(change_set_id="cs-1", order_id=ids["lahom"], path="parties.orderer.name",
                                    path_template="parties.orderer.name", op="update", actor_user_id=fl.id))
    db_session.add(OrderFieldChange(change_set_id="cs-2", order_id=ids["lahom"], path="parties.customer.phone",
                                    path_template="parties.customer.phone", op="update", actor_user_id=fl.id))
    db_session.add(OrderFieldChange(change_set_id="cs-3", order_id=ids["personal"], path="parties.orderer.name",
                                    path_template="parties.orderer.name", op="update", actor_user_id=employee.id))
    db_session.commit()
    _input(ids["lahom"], install_cost=1_000_000)
    _input(ids["manual"], install_cost=500_000)
    _input(ids["naver"], install_cost=500_000)
    return {"fl": fl.id, "other": other.id, "ids": ids}


def _client(app, role, team):
    client = app.test_client()
    _login(client, _make_user(role, team))
    return client


def _rows_by_id(data):
    return {row["order_id"]: row for row in data["rows"]}


# --------------------------------------------------------------------------
# 읽기 모델
# --------------------------------------------------------------------------
def test_completion_rows_population_and_states(world):
    ids = world["ids"]
    data = commission_rows(db_session, world["fl"], MONTH, "completion")
    rows = _rows_by_id(data)
    assert set(rows) == {ids["lahom"], ids["personal"], ids["manual"], ids["naver"]}
    lahom = rows[ids["lahom"]]
    assert lahom["deal_type"] == "LAHOM" and lahom["rate_bp"] == 400 and lahom["state"] == "DONE"
    assert lahom["deduction_total"] == 100_000 and [d["id"] for d in lahom["deductions"]] == ["d1"]
    assert lahom["deductions"][0]["amount"] == 100_000 and lahom["deductions"][0]["reason"] == "가짜 재방문"
    assert lahom["commission"] == 56_000  # (2,500,000 − 1,000,000 − 100,000) × 4%
    assert lahom["customer_name"] == "가짜고객" and lahom["product_summary"] == "가짜장"
    assert lahom["completion_month"] == "2030-02" and lahom["input_version"] == 1
    personal = rows[ids["personal"]]
    assert personal["deal_type"] == "PERSONAL" and personal["state"] == "WAIT_COST" and personal["commission"] is None
    assert personal["input_version"] == 0 and personal["rate_bp"] == 800
    manual = rows[ids["manual"]]
    assert manual["deal_type"] == "MANUAL" and manual["state"] == "WAIT_RATE" and manual["rate_bp"] is None
    naver = rows[ids["naver"]]
    assert naver["deal_type"] == "LAHOM" and naver["commission"] == 80_000  # 네이버 = 라홈 요율
    assert [r["order_id"] for r in data["rows"]] == [ids["naver"], ids["lahom"], ids["personal"], ids["manual"]]
    summary = data["summary"]
    assert summary["total_commission"] == 136_000 and summary["month"] == MONTH
    assert summary["counts"] == {"WAIT_COST": 1, "WAIT_RATE": 1, "DONE": 2, "FORECAST": 0}
    assert data["freelancer"]["match_name"] == MATCH


def test_other_freelancer_sees_only_own(world):
    data = commission_rows(db_session, world["other"], MONTH, "completion")
    assert [r["order_id"] for r in data["rows"]] == [world["ids"]["other_fl"]]


def test_earlier_month_cuts_later_completions(world):
    ids = world["ids"]
    rows = _rows_by_id(commission_rows(db_session, world["fl"], "2030-02", "completion"))
    assert set(rows) == {ids["lahom"], ids["naver"]}


def test_measurement_basis_gives_forecast_rows(world):
    ids = world["ids"]
    data = commission_rows(db_session, world["fl"], "2030-01", "measurement")
    rows = _rows_by_id(data)
    assert set(rows) == {ids["lahom"], ids["personal"], ids["naver"], ids["production"], ids["future"]}
    assert rows[ids["production"]]["state"] == "FORECAST" and rows[ids["production"]]["deal_type"] == "HAUD"
    # 시공 완료 달(2030-04)이 고른 달 뒤여도 실측 달로 보인다 — 완료는 됐으니 예상이 아니다
    assert rows[ids["future"]]["state"] == "WAIT_COST" and rows[ids["future"]]["completion_month"] == "2030-04"
    assert rows[ids["lahom"]]["state"] == "DONE"
    assert data["summary"]["counts"]["FORECAST"] >= 1 and data["summary"]["basis"] == "measurement"


def test_self_edits_only_freelancer_on_commission_fields(world):
    ids = world["ids"]
    rows = _rows_by_id(commission_rows(db_session, world["fl"], MONTH, "completion"))
    edits = rows[ids["lahom"]]["self_edits"]
    assert [e["field"] for e in edits] == ["parties.orderer.name"] and edits[0]["at"]
    assert rows[ids["personal"]]["self_edits"] == []  # 다른 직원이 바꾼 기록은 표시 안 함


def test_near_misses_flag_similar_manager_name(world):
    data = commission_rows(db_session, world["fl"], MONTH, "completion")
    assert data["near_misses"] == [{"order_id": world["ids"]["near"], "customer_name": "비슷한고객",
                                    "name_seen": MATCH + "2"}]
    # 대조군: 다른 프리랜서 이름 · 다른 직원 이름은 경고에 안 뜬다
    other = commission_rows(db_session, world["other"], MONTH, "completion")
    assert other["near_misses"] == []


def test_row_for_order_resolves_owner_or_none(world):
    ids = world["ids"]
    row = commission_row_for_order(db_session, ids["lahom"])
    assert row is not None and row["commission"] == 56_000
    assert commission_row_for_order(db_session, ids["employee"]) is None
    assert commission_row_for_order(db_session, ids["partner"]) is None
    assert commission_row_for_order(db_session, ids["before_start"]) is None


def test_bad_arguments_raise(world):
    with pytest.raises(ValueError):
        commission_rows(db_session, world["fl"], "2030-13", "completion")
    with pytest.raises(ValueError):
        commission_rows(db_session, world["fl"], MONTH, "weekly")
    with pytest.raises(ValueError):
        commission_rows(db_session, 999_999, MONTH, "completion")


# --------------------------------------------------------------------------
# GET 권한 · 검사
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", _ALLOWED)
def test_get_rows_allowed(app, world, role, team):
    client = _client(app, role, team)
    resp = client.get(f"{ROWS}?user_id={world['fl']}&month={MONTH}&basis=completion")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None and len(body["data"]["rows"]) == 4
    resp = client.get(FREELANCERS)
    assert resp.status_code == 200
    assert [f["match_name"] for f in resp.get_json()["data"]["freelancers"]] == sorted([MATCH, OTHER_MATCH])


@pytest.mark.parametrize("role,team", _DENIED)
def test_get_rows_denied(app, world, role, team):
    client = _client(app, role, team)
    resp = client.get(f"{ROWS}?user_id={world['fl']}&month={MONTH}")
    assert resp.status_code == 403 and resp.get_json()["success"] is False
    assert client.get(FREELANCERS).status_code == 403


def test_get_rows_denied_for_freelancer_self(app, world):
    client = app.test_client()
    _login(client, db_session.get(User, world["fl"]))
    assert client.get(f"{ROWS}?user_id={world['fl']}&month={MONTH}").status_code == 403


def test_get_rows_unauthenticated_401(app, world):
    assert app.test_client().get(f"{ROWS}?user_id={world['fl']}&month={MONTH}").status_code == 401


def test_get_rows_validation(app, world):
    client = _client(app, "ADMIN", None)
    assert client.get(f"{ROWS}?month={MONTH}").status_code == 400
    assert client.get(f"{ROWS}?user_id={world['fl']}&month=2030-3").status_code == 400
    assert client.get(f"{ROWS}?user_id={world['fl']}&month={MONTH}&basis=week").status_code == 400
    employee = _make_user("STAFF", "SALES")
    assert client.get(f"{ROWS}?user_id={employee.id}&month={MONTH}").status_code == 404


# --------------------------------------------------------------------------
# PUT 시공비 저장
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", _ALLOWED)
def test_put_allowed_creates_then_updates_with_version(app, world, role, team):
    oid = world["ids"]["personal"]
    client = _client(app, role, team)
    resp = client.put(f"{INPUTS}/{oid}", json={"install_cost": 500_000, "version": 0})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["input"]["version"] == 1 and data["input"]["install_cost"] == 500_000
    assert data["row"]["state"] == "DONE" and data["row"]["commission"] == 120_000  # (2,000,000 − 500,000) × 8%
    resp = client.put(f"{INPUTS}/{oid}", json={"note": "가짜 메모", "version": 1})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["input"] == {"order_id": oid, "install_cost": 500_000, "rate_override_bp": None,
                             "note": "가짜 메모", "version": 2}  # 본문에 없는 칸은 그대로
    resp = client.put(f"{INPUTS}/{oid}", json={"install_cost": 1, "version": 1})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "그사이 다른 사람이 고쳤어요. 다시 불러와 주세요."
    assert body["data"]["current"]["input_version"] == 2 and body["data"]["input"]["install_cost"] == 500_000
    logs = (db_session.query(SecurityLog).filter(SecurityLog.action == "SALES_COMMISSION_INPUT_SAVED")
            .order_by(SecurityLog.id).all())
    assert len(logs) == 2 and all(log.target_id == oid for log in logs)
    assert logs[0].detail["changed"]["install_cost"] == {"before": None, "after": 500_000}


def test_put_existing_row_requires_its_version(app, world):
    oid = world["ids"]["manual"]  # 시드에서 version 1 로 이미 있음
    client = _client(app, "ADMIN", None)
    assert client.put(f"{INPUTS}/{oid}", json={"rate_override_bp": 700}).status_code == 409  # version 없음 = 0
    resp = client.put(f"{INPUTS}/{oid}", json={"rate_override_bp": 700, "version": 1})
    assert resp.status_code == 200
    row = resp.get_json()["data"]["row"]
    assert row["state"] == "DONE" and row["rate_bp"] == 700 and row["commission"] == 140_000


@pytest.mark.parametrize("role,team", _DENIED)
def test_put_denied(app, world, role, team):
    oid = world["ids"]["personal"]
    client = _client(app, role, team)
    assert client.put(f"{INPUTS}/{oid}", json={"install_cost": 1, "version": 0}).status_code == 403
    assert db_session.get(SalesCommissionInput, oid) is None


def test_put_denied_for_freelancer_self(app, world):
    oid = world["ids"]["personal"]
    client = app.test_client()
    _login(client, db_session.get(User, world["fl"]))
    assert client.put(f"{INPUTS}/{oid}", json={"install_cost": 1, "version": 0}).status_code == 403
    assert db_session.get(SalesCommissionInput, oid) is None


@pytest.mark.parametrize("body", [
    {"install_cost": -1, "version": 0},
    {"install_cost": "1,000", "version": 0},
    {"install_cost": True, "version": 0},
    {"install_cost": 1.5, "version": 0},
    {"rate_override_bp": 10_001, "version": 0},
    {"rate_override_bp": -5, "version": 0},
    {"note": "가" * 501, "version": 0},
    {"note": 3, "version": 0},
    {"install_cost": 1, "version": "0"},
])
def test_put_validation_400(app, world, body):
    oid = world["ids"]["personal"]
    client = _client(app, "ADMIN", None)
    resp = client.put(f"{INPUTS}/{oid}", json=body)
    assert resp.status_code == 400 and resp.get_json()["success"] is False
    assert db_session.get(SalesCommissionInput, oid) is None


def test_put_bad_orders_404(app, world):
    client = _client(app, "ADMIN", None)
    for oid in (world["ids"]["partner"], world["ids"]["deleted"], world["ids"]["draft"], 999_999):
        assert client.put(f"{INPUTS}/{oid}", json={"install_cost": 1, "version": 0}).status_code == 404


def test_put_for_order_without_freelancer_returns_null_row(app, world):
    oid = world["ids"]["employee"]
    client = _client(app, "ADMIN", None)
    resp = client.put(f"{INPUTS}/{oid}", json={"install_cost": 1, "version": 0})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["row"] is None and data["input"]["version"] == 1
