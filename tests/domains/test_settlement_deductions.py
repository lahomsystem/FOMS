"""정산 차감 보강 시험(설계서 FCOMM-01 §10 · §11.2 · §11.3, 검수 원장 A12 · A17).

1. 유효 판정 정본 — 취소한 차감은 정산 집계 · 실무 탭 "청구됨" · 완료 화면 · 수수료 계산 어디서도 안 센다.
2. 취소 API — 회계팀 · 관리자만, 사유 필수 · 500자, 두 번이면 409, 모르는 id 404, 이벤트 · 감사, 지우지 않음.
3. 넣기 — 메인 단계 CS 허용(J1), 영업 귀속은 사람 필수, 잠금 길(버전 +1 · receipt), 잠금 뒤 다시 읽기.
4. 프리랜서 — FINANCE_MUTATION 거부.

알림(D17)은 ``test_settlement_deductions_notify.py``. 요율 · 고객 · 이름은 모두 가짜 값이다.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from db import db_session
from foms.services import settlement_deduction_service as service
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.sales_commission.calc import sales_deduction_total
from foms.services.sales_commission.settings import load_settings, save_freelancer
from foms.services.settlement_aggregation import aggregate_settlement
from foms.services.settlement_deductions import (
    has_valid_deduction,
    is_valid_deduction,
    valid_deductions,
)
from foms.services.settlement_rows import list_settlement_rows
from foms.web.cs.completion_dashboard import _completion_row, _completion_settlement_memo
from models import Order, OrderEvent, OrderMutationReceipt, SecurityLog
from tests.domains.test_auth_finance import _login, _make_user, policy_on  # noqa: F401 — 픽스처 재사용
from tests.domains.test_settlement_aggregation import _seed_order

_VOIDED = {"voided_at": "2026-11-06T10:00:00+09:00", "voided_by": 1, "void_reason": "잘못 넣음"}


def _ded(ded_id: str = "DED-1", *, department: str = "SALES", amount: int = -50_000,
         charge_to: int | None = None, voided: bool = False) -> dict:
    entry = {"id": ded_id, "department": department, "amount": amount, "reason": "가상 사유",
             "created_at": "2026-11-01T09:00:00", "created_by": "가상회계"}
    if charge_to is not None:
        entry["charge_to_user_id"] = charge_to
    if voided:
        entry.update(_VOIDED)
    return entry


def _order_with(deductions: list, *, status: str = "COMPLETED", stage: str | None = "COMPLETED") -> int:
    """정산 대상 주문 1건 → id(요청 뒤에는 세션이 비워지므로 객체 대신 id 로 다닌다)."""
    return _seed_order(completion="2026-10-15", status=status, stage=stage, customer_name="가상고객", sd={
        "totals": {"items_total": 1_000_000},
        "settlement": {"status": "ISSUE_RAISED", "deductions": copy.deepcopy(deductions)},
    }).id


def _reload(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _freelancer() -> object:
    """켜진 프리랜서 계정(직원 · 영업팀) — 맞출 이름은 가짜 값."""
    user = _make_user(role="STAFF", team="SALES")
    version, _ = load_settings(db_session)
    save_freelancer(db_session, user.id, {"match_name": f"가상프리랜서{user.id}", "start_month": "2026-11",
                                          "tax_type": "NONE", "active": True},
                    base_version=version, actor_user_id=user.id)
    db_session.commit()
    return user


def _void(client, order_id: int, ded_id: str = "DED-1", reason: object = "가상 취소 사유"):
    return client.post(f"/api/orders/{order_id}/settlement/deductions/{ded_id}/void", json={"reason": reason})


def _issue(client, order_id: int, **body):
    payload = {"department": "CUSTOMER", "amount": 30_000, "reason": "가상 청구"}
    payload.update(body)
    return client.post(f"/api/orders/{order_id}/settlement/issue", json=payload)


# ==========================================================================
# 1. 유효 판정 정본
# ==========================================================================
def test_valid_deductions_keep_only_dicts_without_void_mark():
    good, voided = _ded("A"), _ded("B", voided=True)
    sd = {"settlement": {"deductions": [good, voided, "깨진-행", 7, None, {"voided_at": ""}]}}

    assert valid_deductions(sd) == [good, {"voided_at": ""}]
    assert is_valid_deduction(good) and not is_valid_deduction(voided) and not is_valid_deduction("x")
    for broken in (None, {}, {"settlement": None}, {"settlement": {"deductions": "x"}}, "문자"):
        assert valid_deductions(broken) == []
    assert has_valid_deduction({"deductions": [voided]}) is False
    assert has_valid_deduction({"deductions": [voided, good]}) is True


@pytest.mark.parametrize("voided", [False, True])
def test_voided_deduction_stops_counting_everywhere(app, voided):
    """같은 주문 — 취소 표시만 다르다. 유효면 6곳 모두 차감 있음, 취소면 모두 없음(음성 대조군 겸용)."""
    oid = _order_with([_ded(charge_to=77, voided=voided)])
    order = _reload(oid)
    sd = order.structured_data
    expect_issued = not voided

    agg = aggregate_settlement(db_session, month_from="2026-10", month_to="2026-10", granularity="month")
    status = agg["settlement_status"]
    sales = next(d for d in status["deductions_by_department"] if d["department"] == "SALES")
    assert status["issued_count"] == (1 if expect_issued else 0)
    assert sales["amount"] == (50_000 if expect_issued else 0)

    issued_rows = list_settlement_rows(db_session, settlement="issued")["total_count"]
    pending_rows = list_settlement_rows(db_session, settlement="pending")["total_count"]
    assert (issued_rows, pending_rows) == ((1, 0) if expect_issued else (0, 1))

    assert _completion_row(order)["settlement_issued"] is expect_issued
    assert len(_completion_settlement_memo(sd["settlement"])) == (1 if expect_issued else 0)
    assert sales_deduction_total(sd, 77) == (50_000 if expect_issued else 0)


# ==========================================================================
# 2. 취소 API
# ==========================================================================
@pytest.mark.parametrize("role,team,allowed", [
    ("ADMIN", None, True),
    ("MANAGER", "ACCOUNTING", True),
    ("STAFF", "ACCOUNTING", True),
    ("MANAGER", "CS", False),
    ("STAFF", "SALES", False),
    ("STAFF", "CS", False),
    ("VIEWER", None, False),
])
def test_void_permission_matrix_with_policy_guard(client, app, policy_on, role, team, allowed):  # noqa: F811
    oid = _order_with([_ded()])
    _login(client, _make_user(role=role, team=team))

    resp = _void(client, oid)

    assert resp.status_code == (200 if allowed else 403), resp.get_data(as_text=True)
    entry = _reload(oid).structured_data["settlement"]["deductions"][0]
    assert bool(entry.get("voided_at")) is allowed


def test_void_handler_rechecks_permission_when_guard_is_off(client, app):
    """엔진 가드가 꺼진 환경(TESTING 기본)에서도 핸들러가 회계팀 · 관리자만 남긴다."""
    oid = _order_with([_ded()])
    _login(client, _make_user(role="MANAGER", team="CS"))

    resp = _void(client, oid)

    assert resp.status_code == 403 and resp.headers.get("X-Auth-Policy") is None
    assert not _reload(oid).structured_data["settlement"]["deductions"][0].get("voided_at")


def test_freelancer_cannot_void(client, app, policy_on):  # noqa: F811
    oid = _order_with([_ded()])
    _login(client, _freelancer())

    assert _void(client, oid).status_code == 403


def test_void_marks_never_deletes_and_writes_event_and_log(client, app):
    oid = _order_with([_ded("DED-1", charge_to=77), _ded("DED-2", department="DRAWING", amount=-10_000)])
    accountant = _make_user(role="STAFF", team="ACCOUNTING")
    _login(client, accountant)
    version_before = _reload(oid).mutation_version

    resp = _void(client, oid, "DED-1", "  고객이 직접 처리함  ")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    saved = _reload(oid)
    entries = saved.structured_data["settlement"]["deductions"]
    assert [e["id"] for e in entries] == ["DED-1", "DED-2"], "지우지 않는다"
    first = entries[0]
    assert first["voided_at"].endswith("+09:00"), "한국 시각"
    assert (first["voided_by"], first["voided_by_name"], first["void_reason"]) == (
        accountant.id, accountant.name, "고객이 직접 처리함")
    assert not entries[1].get("voided_at"), "다른 차감은 그대로"
    assert saved.mutation_version == version_before + 1
    assert body["data"]["mutation_version"] == saved.mutation_version

    event = db_session.query(OrderEvent).filter(
        OrderEvent.order_id == oid, OrderEvent.event_type == "SETTLEMENT_DEDUCTION_VOIDED").one()
    assert event.payload == {"deduction_id": "DED-1", "amount": -50_000, "department": "SALES",
                             "reason": "고객이 직접 처리함", "charge_to_user_id": 77}
    assert event.created_by_user_id == accountant.id
    logs = [r.message for r in db_session.query(SecurityLog).filter(SecurityLog.user_id == accountant.id)]
    assert any(m.startswith(f"주문 #{oid} 차감 취소: SALES") for m in logs), logs


@pytest.mark.parametrize("reason,expected", [
    ("", "취소 사유를 적어 주세요."),
    ("   ", "취소 사유를 적어 주세요."),
    (None, "취소 사유를 적어 주세요."),
    ("가" * 501, "취소 사유는 500자까지 적을 수 있어요."),
])
def test_void_requires_reason_within_500(client, app, reason, expected):
    oid = _order_with([_ded()])
    _login(client, _make_user(role="ADMIN"))

    resp = _void(client, oid, reason=reason)

    assert resp.status_code == 400 and resp.get_json()["error"] == expected
    assert not _reload(oid).structured_data["settlement"]["deductions"][0].get("voided_at")


def test_void_500_chars_is_accepted(client, app):
    oid = _order_with([_ded()])
    _login(client, _make_user(role="ADMIN"))
    assert _void(client, oid, reason="가" * 500).status_code == 200


def test_void_twice_is_409_and_unknown_is_404(client, app):
    oid = _order_with([_ded()])
    _login(client, _make_user(role="ADMIN"))

    assert _void(client, oid).status_code == 200
    second = _void(client, oid)
    assert second.status_code == 409 and second.get_json()["error"] == "이미 취소한 차감이에요."
    assert _void(client, oid, "DED-없음").status_code == 404
    assert _void(client, oid + 999).status_code == 404
    events = db_session.query(OrderEvent).filter(OrderEvent.event_type == "SETTLEMENT_DEDUCTION_VOIDED").count()
    assert events == 1, "거부된 요청은 이벤트를 남기지 않는다"


# ==========================================================================
# 3. 넣기
# ==========================================================================
def test_issue_allowed_for_main_stage_cs_even_if_status_is_not_completed(client, app):
    """J1 — 글자(status)가 완료가 아니어도 메인 단계가 CS 면 넣는다. 공용 상수는 그대로."""
    _login(client, _make_user(role="STAFF", team="CS"))
    cs_stage = _order_with([], status="ON_HOLD", stage="CS")
    production = _order_with([], status="ON_HOLD", stage="PRODUCTION")

    assert _issue(client, cs_stage).status_code == 200
    rejected = _issue(client, production)
    assert rejected.status_code == 400
    assert rejected.get_json()["message"] == "완료·AS 건에만 비용 청구를 등록할 수 있습니다."
    from foms.services.orders.erp_policy_constants import ORDER_SETTLEMENT_ALERT_TARGET_STATUSES
    assert "ON_HOLD" not in ORDER_SETTLEMENT_ALERT_TARGET_STATUSES


def test_sales_deduction_requires_a_person(client, app):
    oid = _order_with([])
    _login(client, _make_user(role="STAFF", team="ACCOUNTING"))

    resp = _issue(client, oid, department="SALES")

    assert resp.status_code == 400
    assert resp.get_json()["message"] == "영업 귀속 차감은 사람을 골라야 해요."
    assert _reload(oid).structured_data["settlement"]["deductions"] == []
    seller = _make_user(role="STAFF", team="SALES")
    assert _issue(client, oid, department="SALES", charge_to_user_id=seller.id).status_code == 200


def test_two_sequential_issues_both_persist_and_bump_version(client, app, monkeypatch):
    """잠금 길을 탄다 — 잠금 조회를 부르고, 버전이 1씩 오르고, FINANCE_MUTATION receipt 가 남는다."""
    locked: list[int] = []
    real_lock = service.lock_order_row
    monkeypatch.setattr(service, "lock_order_row", lambda db, oid: locked.append(oid) or real_lock(db, oid))
    oid = _order_with([])
    _login(client, _make_user(role="STAFF", team="CS"))
    start = _reload(oid).mutation_version

    first = _issue(client, oid, amount=10_000).get_json()
    second = _issue(client, oid, amount=20_000).get_json()

    assert first["success"] and second["success"]
    assert first["deduction_id"] != second["deduction_id"]
    assert (first["data"]["mutation_version"], second["data"]["mutation_version"]) == (start + 1, start + 2)
    saved = _reload(oid)
    assert [d["amount"] for d in saved.structured_data["settlement"]["deductions"]] == [-10_000, -20_000]
    assert saved.mutation_version == start + 2
    assert locked == [oid, oid]
    receipts = db_session.query(OrderMutationReceipt).filter(OrderMutationReceipt.policy_id == "FINANCE_MUTATION")
    assert receipts.count() == 2
    assert set(second["settlement"]) >= {"status", "deductions"}, "예전 응답 모양 유지"


def test_issue_stale_if_match_is_rejected_without_write(client, app):
    oid = _order_with([])
    _login(client, _make_user(role="ADMIN"))

    resp = client.post(f"/api/orders/{oid}/settlement/issue", headers={"If-Match": str(_reload(oid).mutation_version + 5)},
                       json={"department": "CUSTOMER", "amount": 1000, "reason": "가상"})

    assert resp.status_code == 409 and resp.get_json()["code"] == "REVISION_CONFLICT"
    assert _reload(oid).structured_data["settlement"]["deductions"] == []


def test_issue_rereads_row_under_lock_so_a_concurrent_save_is_kept(app):
    """잠금 전에 읽어 둔 낡은 객체가 있어도, 그사이 커밋된 남의 저장(CS 메모)을 지우지 않는다(A12)."""
    oid = _order_with([])
    actor = _make_user(role="STAFF", team="CS")
    stale = db_session.get(Order, oid)
    fresh_sd = copy.deepcopy(stale.structured_data)
    fresh_sd["payment"] = {"balance_note": "CS 가 그사이 저장한 메모"}
    db_session.connection().execute(text("UPDATE orders SET structured_data = :sd WHERE id = :id"),
                                    {"sd": json.dumps(fresh_sd, ensure_ascii=False), "id": oid})
    assert "payment" not in stale.structured_data, "세션에는 아직 낡은 값이 있다(대조)"

    service.issue_deduction(db_session, order_id=oid, actor=actor,
                            data={"department": "CUSTOMER", "amount": 5000, "reason": "가상"})
    db_session.commit()

    saved = _reload(oid).structured_data
    assert saved["payment"] == {"balance_note": "CS 가 그사이 저장한 메모"}
    assert len(saved["settlement"]["deductions"]) == 1


def test_void_removes_amount_from_final_cost_and_resets_status(app):
    oid = _order_with([_ded("DED-1", department="CUSTOMER", amount=-30_000)])
    order = _reload(oid)
    sd = copy.deepcopy(order.structured_data)
    sd["settlement"]["base_cost"] = 100_000
    order.structured_data = sd
    db_session.commit()

    service.void_deduction(db_session, order_id=oid, deduction_id="DED-1",
                           actor=_make_user(role="ADMIN"), reason="가상")
    db_session.commit()

    settlement = _reload(oid).structured_data["settlement"]
    assert (settlement["final_cost"], settlement["status"]) == (100_000, "PENDING")


# ==========================================================================
# 4. 프리랜서는 FINANCE_MUTATION 을 못 쓴다
# ==========================================================================
@pytest.mark.parametrize("path,body", [
    ("/api/orders/{oid}/settlement/issue", {"department": "CUSTOMER", "amount": 1000, "reason": "가상"}),
    ("/api/orders/{oid}/payment-confirm", {"type": "deposit", "confirmed": True}),
    ("/api/orders/{oid}/cash-receipt/issue", {"note": "가상"}),
])
def test_freelancer_is_denied_finance_mutation(client, app, policy_on, path, body):  # noqa: F811
    oid = _order_with([])
    _login(client, _freelancer())

    resp = client.post(path.format(oid=oid), json=body)

    assert resp.status_code == 403 and resp.headers.get("X-Auth-Policy") == "denied"
    assert resp.get_json()["success"] is False
    assert db_session.query(OrderEvent).filter(OrderEvent.order_id == oid).count() == 0


def test_engine_denies_freelancer_only_for_finance(app):
    freelancer = _freelancer()
    decision = evaluate_policy(POLICY_REGISTRY["FINANCE_MUTATION"], freelancer)

    assert (decision.allowed, decision.status, decision.reason) == (
        False, 403, "프리랜서 계정으로는 이 작업을 할 수 없어요.")
    assert evaluate_policy(POLICY_REGISTRY["ERP_EDIT"], freelancer).allowed, "다른 업무는 3단계 전까지 그대로"
    plain_seller = _make_user(role="STAFF", team="SALES")
    assert evaluate_policy(POLICY_REGISTRY["FINANCE_MUTATION"], plain_seller).allowed, "대조군 — 일반 영업"
    # 영업팀이 아닌 계정은 설정을 읽지 않는다(DB 없이 도는 판정 시험이 그대로 통과해야 한다).
    accounting = SimpleNamespace(id=freelancer.id, role="STAFF", team="ACCOUNTING", is_active=True)
    assert evaluate_policy(POLICY_REGISTRY["FINANCE_MUTATION"], accounting).allowed


def test_sales_commission_write_policy_is_the_accounting_gate():
    policy = POLICY_REGISTRY["SALES_COMMISSION_WRITE"]
    assert policy.gate == "foms.services.settlement_channel_access:is_accounting_or_admin"
    assert tuple(policy.teams) == ("ACCOUNTING",) and policy.viewer is False
