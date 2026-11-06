"""FCOMM-01 T9 — 영업 수수료 달 마감 · 지급 완료 · 마감 취소(서비스 · API · 권한).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §3.5 · §4.3 · §8 · §9 · §11 · J3 · J9,
검수 원장 A14(굳힘) · A15(늦게 들어온 시공비) · A16(오름차순 · 잠금).
요율 · 금액 · 이름은 모두 가짜 값이다(저장소 공개 — 실제 요율은 설정에만 있다).
"""
from __future__ import annotations

import copy
import datetime

import pytest
from sqlalchemy.orm import Query
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.sales_commission import closing as closing_mod
from foms.services.sales_commission.closing import (
    ClosingError,
    cancel_closing,
    close_month,
    list_closings,
    mark_paid,
    preview_closing,
)
from foms.services.sales_commission.read_model import closed_order_ids, commission_rows
from foms.services.sales_commission.settings import (
    FreelancerSettingsError,
    add_rate,
    latest_closed_month,
    load_settings,
    save_freelancer,
)
from models import Order, SalesCommissionClosing, SecurityLog, SystemSetting, User
from tests.domains.test_auth_finance import _login, _make_user, policy_on  # noqa: F401 — 픽스처 재사용
from tests.domains.test_sales_commission_api import MATCH, OTHER_MATCH, _add_freelancer, _input, _order

CLOSINGS = "/api/sales-commission/closings"
LINE_KEYS = {"order_id", "kind", "deal_type", "shipping_price", "install_cost", "deduction_total", "rate_bp",
             "commission", "label", "completion_month"}
_ALLOWED = [("ADMIN", None), ("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")]
_DENIED = [("MANAGER", "CS"), ("STAFF", "SALES")]


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    """오늘 = 2030-04-10(한국 시각). 시드 달(2030-01~04)이 '앞으로 올 달'로 막히지 않게 고정한다."""
    monkeypatch.setattr(closing_mod, "get_today_kst", lambda: datetime.date(2030, 4, 10))


@pytest.fixture
def world(app):
    """프리랜서 둘. F: 계산 끝난 줄 2(합 180,000) + 시공비 기다림 1 + 요율 기다림 1. G: 계산 끝난 줄 1."""
    fl = _add_freelancer(MATCH)
    other = _add_freelancer(OTHER_MATCH)
    ids = {
        # (2,500,000 − 1,000,000) × 4% = 60,000
        "a": _order(manager=MATCH, orderer="라홈 가짜점", construction="2030-02-10"),
        # (3,000,000 − 1,000,000) × 6% = 120,000
        "b": _order(manager=MATCH, orderer="하우드", construction="2030-03-05", price=3_000_000),
        # 시공 완료 2030-01 · 시공비 없음
        "wait_cost": _order(manager=MATCH, orderer="라홈", construction="2030-01-20", price=2_000_000),
        # 숨고 · 지정 요율 없음
        "wait_rate": _order(manager=MATCH, orderer="숨고", construction="2030-03-07"),
        # G 몫: (2,000,000 − 1,000,000) × 4% = 40,000
        "g": _order(manager=OTHER_MATCH, orderer="라홈", construction="2030-02-15", price=2_000_000),
    }
    for key in ("a", "b", "g"):
        _input(ids[key], install_cost=1_000_000)
    _input(ids["wait_rate"], install_cost=500_000)
    return {"fl": fl.id, "other": other.id, "ids": ids}


def _set_tax(user_id: int, tax_type: str) -> None:
    version, configs = load_settings(db_session)
    cfg = configs[user_id]
    save_freelancer(db_session, user_id, {"match_name": cfg.match_name, "start_month": cfg.start_month,
                                          "tax_type": tax_type, "active": True},
                    base_version=version, actor_user_id=None)
    db_session.commit()


def _close(user_id: int, month: str, actor: int | None = None) -> SalesCommissionClosing:
    row = close_month(db_session, user_id, month, actor_user_id=actor)
    db_session.commit()
    return row


def _row_ids(user_id: int, month: str) -> set[int]:
    return {r["order_id"] for r in commission_rows(db_session, user_id, month, "completion")["rows"]}


def _set_manager(order_id: int, name: str) -> None:
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    sd["parties"]["manager"]["name"] = name
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.manager_name = name
    db_session.commit()


def _logs(action: str) -> list[SecurityLog]:
    return db_session.query(SecurityLog).filter(SecurityLog.action == action).order_by(SecurityLog.id).all()


# --------------------------------------------------------------------------
# 미리 보기 · 마감 스냅샷
# --------------------------------------------------------------------------
def test_preview_takes_done_rows_and_leaves_waiting_rows(world):
    ids = world["ids"]
    data = preview_closing(db_session, world["fl"], "2030-03")
    lines = {line["order_id"]: line for line in data["lines"]}
    assert set(lines) == {ids["a"], ids["b"]}
    assert all(set(line) == LINE_KEYS for line in data["lines"])
    assert lines[ids["a"]] == {
        "order_id": ids["a"], "kind": "NORMAL", "deal_type": "LAHOM", "shipping_price": 2_500_000,
        "install_cost": 1_000_000, "deduction_total": 0, "rate_bp": 400, "commission": 60_000,
        "label": "가짜고객 · 가짜장", "completion_month": "2030-02"}
    assert lines[ids["b"]]["deal_type"] == "HAUD" and lines[ids["b"]]["commission"] == 120_000
    assert data["totals"] == {"gross": 180_000, "tax_income": 0, "tax_local": 0, "vat": 0, "net": 180_000}
    assert data["waiting_counts"] == {"WAIT_COST": 1, "WAIT_RATE": 1}
    assert {w["order_id"] for w in data["waiting"]} == {ids["wait_cost"], ids["wait_rate"]}
    assert data["can_close"] is True and data["block_reason"] is None and data["adjust_count"] == 0
    assert db_session.query(SalesCommissionClosing).count() == 0  # 미리 보기는 쓰지 않는다


@pytest.mark.parametrize("tax_type,expected", [
    ("WITHHOLD_3_3", {"tax_income": 5_400, "tax_local": 540, "vat": 0, "net": 174_060}),
    ("VAT_10", {"tax_income": 0, "tax_local": 0, "vat": 18_000, "net": 198_000}),
    ("NONE", {"tax_income": 0, "tax_local": 0, "vat": 0, "net": 180_000}),
])
def test_close_freezes_lines_totals_and_tax(world, tax_type, expected):
    _set_tax(world["fl"], tax_type)
    actor = _make_user("STAFF", "ACCOUNTING")
    preview = preview_closing(db_session, world["fl"], "2030-03")
    row = _close(world["fl"], "2030-03", actor.id)
    assert (row.month, row.status, row.tax_type, row.gross) == ("2030-03", "CLOSED", tax_type, 180_000)
    assert {k: getattr(row, k) for k in expected} == expected
    assert row.lines == preview["lines"] and row.closed_by_user_id == actor.id and row.closed_at is not None
    log = _logs("SALES_COMMISSION_CLOSED")[-1]
    assert log.target_id == row.id and log.user_id == actor.id
    assert log.detail["line_count"] == 2 and log.detail["gross"] == 180_000 and log.detail["net"] == expected["net"]
    assert sorted(log.detail["order_ids"]) == sorted([world["ids"]["a"], world["ids"]["b"]])
    assert "lines" not in log.detail and "가짜고객" not in str(log.detail)  # 감사 원장에 고객명 없음


# --------------------------------------------------------------------------
# J9 굳힘 · 늦게 들어온 시공비(A14 · A15)
# --------------------------------------------------------------------------
def test_closed_orders_never_reenter_anyone_even_after_manager_change(world):
    ids = world["ids"]
    _close(world["fl"], "2030-03")
    assert closed_order_ids(db_session) == {ids["a"], ids["b"]}
    assert closed_order_ids(db_session, world["other"]) == set()
    assert _row_ids(world["fl"], "2030-04") == {ids["wait_cost"], ids["wait_rate"]}
    _set_manager(ids["a"], OTHER_MATCH)  # 마감 뒤 대표 담당 F → G
    assert _row_ids(world["other"], "2030-04") == {ids["g"]}  # G 에게 안 간다
    # 대조군: 마감을 취소하면 같은 주문이 이제 G 의 줄로 나온다 — 위 결과는 마감 덕분이다
    cancel_closing(db_session, db_session.query(SalesCommissionClosing).one().id, actor_user_id=None,
                   reason="가짜 대조군")
    db_session.commit()
    assert _row_ids(world["other"], "2030-04") == {ids["g"], ids["a"]}


def test_waiting_row_joins_a_later_closing_once_cost_is_entered(world):
    ids = world["ids"]
    _close(world["fl"], "2030-03")
    _input(ids["wait_cost"], install_cost=500_000)
    row = _close(world["fl"], "2030-04")
    lines = {line["order_id"]: line for line in row.lines}
    assert set(lines) == {ids["wait_cost"]}  # 시공 완료는 2030-01 이지만 시공비가 들어간 뒤 마감에 들어간다
    assert lines[ids["wait_cost"]]["completion_month"] == "2030-01"
    assert lines[ids["wait_cost"]]["commission"] == 60_000 and row.gross == 60_000


# --------------------------------------------------------------------------
# 거부 규칙
# --------------------------------------------------------------------------
def test_months_close_in_ascending_order_only(world):
    _close(world["fl"], "2030-03")
    for month in ("2030-02", "2030-03"):
        with pytest.raises(ClosingError) as err:
            close_month(db_session, world["fl"], month, actor_user_id=None)
        db_session.rollback()
        assert err.value.status == 409 and "이미 그 뒤 달까지 마감했어요" in str(err.value)
    preview = preview_closing(db_session, world["fl"], "2030-02")
    assert preview["can_close"] is False and preview["latest_closed_month"] == "2030-03"
    assert db_session.query(SalesCommissionClosing).count() == 1


def test_future_month_rejected_but_current_month_allowed(world):
    with pytest.raises(ClosingError) as err:
        close_month(db_session, world["fl"], "2030-05", actor_user_id=None)
    assert err.value.status == 400 and str(err.value) == "아직 오지 않은 달은 마감할 수 없어요."
    assert preview_closing(db_session, world["fl"], "2030-05")["can_close"] is False
    assert _close(world["fl"], "2030-04").month == "2030-04"  # 이번 달은 된다


def test_zero_gross_rejected(world):
    empty = _add_freelancer("빈가짜")
    with pytest.raises(ClosingError) as err:
        close_month(db_session, empty.id, "2030-03", actor_user_id=None)
    db_session.rollback()
    assert err.value.status == 400 and str(err.value) == "이번 달은 줄 돈이 없어요."
    assert preview_closing(db_session, empty.id, "2030-03")["block_reason"] == "이번 달은 줄 돈이 없어요."
    _close(world["fl"], "2030-03")
    with pytest.raises(ClosingError) as err:  # 이미 다 마감해 남은 게 기다리는 줄뿐이어도 같다
        close_month(db_session, world["fl"], "2030-04", actor_user_id=None)
    assert err.value.status == 400
    db_session.rollback()
    assert db_session.query(SalesCommissionClosing).count() == 1


def test_bad_inputs_and_inactive_freelancer(world):
    for user_id, month, status in ((world["fl"], "2030-3", 400), ("x", "2030-03", 400), (999_999, "2030-03", 404)):
        with pytest.raises(ClosingError) as err:
            close_month(db_session, user_id, month, actor_user_id=None)
        db_session.rollback()
        assert err.value.status == status


def test_closing_locks_settings_row_before_writing(world, monkeypatch):
    """SQLite 에는 진짜 행 잠금이 없다 — 설정 줄에 FOR UPDATE 조회를 거는지(그리고 맨 먼저인지)를 본다."""
    locked: list[tuple[type, int]] = []
    original = Query.with_for_update

    def spy(self, *args, **kwargs):
        locked.append((self.column_descriptions[0]["entity"], db_session.query(SalesCommissionClosing).count()))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", spy)
    row = _close(world["fl"], "2030-03")
    assert locked and locked[0] == (SystemSetting, 0)  # 마감 줄을 넣기 전에 설정 줄부터 잡는다
    locked.clear()
    cancel_closing(db_session, row.id, actor_user_id=None, reason="가짜 잠금 확인")
    db_session.commit()
    assert [entity for entity, _count in locked] == [SystemSetting, SalesCommissionClosing]


# --------------------------------------------------------------------------
# 지급 완료 · 마감 취소
# --------------------------------------------------------------------------
def test_mark_paid_then_locked(world):
    actor = _make_user("ADMIN", None)
    row = _close(world["fl"], "2030-03")
    paid = mark_paid(db_session, row.id, actor_user_id=actor.id)
    db_session.commit()
    assert paid.status == "PAID" and paid.paid_by_user_id == actor.id and paid.paid_at is not None
    assert _logs("SALES_COMMISSION_PAID")[-1].target_id == row.id
    with pytest.raises(ClosingError) as err:
        mark_paid(db_session, row.id, actor_user_id=actor.id)
    db_session.rollback()
    assert err.value.status == 409
    with pytest.raises(ClosingError) as err:
        cancel_closing(db_session, row.id, actor_user_id=actor.id, reason="가짜")
    db_session.rollback()
    assert err.value.status == 409 and str(err.value) == "지급한 마감은 되돌릴 수 없어요."
    assert db_session.get(SalesCommissionClosing, row.id) is not None


def test_cancel_only_latest_closed_with_reason(world):
    ids = world["ids"]
    march = _close(world["fl"], "2030-03")
    _input(ids["wait_cost"], install_cost=500_000)
    april = _close(world["fl"], "2030-04")
    with pytest.raises(ClosingError) as err:
        cancel_closing(db_session, march.id, actor_user_id=None, reason="가짜")
    db_session.rollback()
    assert err.value.status == 409 and "2030-04" in str(err.value)
    for reason in ("", "   ", None, 3, "가" * 501):
        with pytest.raises(ClosingError) as err:
            cancel_closing(db_session, april.id, actor_user_id=None, reason=reason)
        db_session.rollback()
        assert err.value.status == 400
    april_id = april.id
    snapshot = cancel_closing(db_session, april_id, actor_user_id=None, reason="가짜 시공비 오타")
    db_session.commit()
    assert snapshot["month"] == "2030-04" and snapshot["gross"] == 60_000
    assert db_session.get(SalesCommissionClosing, april_id) is None
    log = _logs("SALES_COMMISSION_CLOSING_CANCELLED")[-1]
    assert log.target_id == april_id and log.detail["reason"] == "가짜 시공비 오타"
    assert log.detail["month"] == "2030-04" and log.detail["line_count"] == 1
    assert log.detail["order_ids"] == [ids["wait_cost"]] and log.detail["net"] == 60_000
    assert ids["wait_cost"] in _row_ids(world["fl"], "2030-04")  # 지운 마감의 주문은 다시 줄로 나온다
    cancel_closing(db_session, march.id, actor_user_id=None, reason="가짜")  # 이제 3월이 가장 최근
    db_session.commit()
    assert list_closings(db_session, world["fl"]) == []


def test_list_closings_newest_first(world):
    _close(world["fl"], "2030-03")
    _input(world["ids"]["wait_cost"], install_cost=500_000)
    _close(world["fl"], "2030-04")
    data = list_closings(db_session, world["fl"])
    assert [c["month"] for c in data] == ["2030-04", "2030-03"]
    assert data[1]["line_count"] == 2 and len(data[1]["lines"]) == 2 and data[1]["status"] == "CLOSED"
    assert list_closings(db_session, world["other"]) == []


# --------------------------------------------------------------------------
# 요율 저장 — 마감한 달 이하 적용 달 거부(§4.1)
# --------------------------------------------------------------------------
def test_latest_closed_month_blocks_rate_for_closed_months(world):
    assert latest_closed_month(db_session, world["fl"]) is None
    _close(world["fl"], "2030-03")
    assert latest_closed_month(db_session, world["fl"]) == "2030-03"
    assert latest_closed_month(db_session, world["other"]) is None
    rate = {"lahom_bp": 450, "haud_bp": 650, "personal_bp": 850}
    for month in ("2030-02", "2030-03"):
        with pytest.raises(FreelancerSettingsError) as err:
            add_rate(db_session, world["fl"], {**rate, "effective_month": month},
                     base_version=load_settings(db_session)[0], actor_user_id=None)
        db_session.rollback()
        assert "2030-03 까지는 이미 마감했어요" in str(err.value)
    add_rate(db_session, world["fl"], {**rate, "effective_month": "2030-04"},
             base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, world["other"], {**rate, "effective_month": "2030-03"},  # 대조군: G 는 마감 없음
             base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()


# --------------------------------------------------------------------------
# API 권한 · 흐름
# --------------------------------------------------------------------------
def _client(app, role, team):
    client = app.test_client()
    _login(client, _make_user(role, team))
    return client


@pytest.mark.parametrize("role,team", _ALLOWED)
def test_api_full_flow_for_accounting_and_admin(app, world, role, team):
    client = _client(app, role, team)
    fl = world["fl"]
    resp = client.get(f"{CLOSINGS}/preview?user_id={fl}&month=2030-03")
    assert resp.status_code == 200 and resp.get_json()["data"]["totals"]["gross"] == 180_000
    resp = client.post(CLOSINGS, json={"user_id": fl, "month": "2030-03"})
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None and body["data"]["line_count"] == 2
    closing_id = body["data"]["id"]
    assert resp.headers.get("Cache-Control") == "private, no-store"
    resp = client.post(CLOSINGS, json={"user_id": fl, "month": "2030-03"})
    assert resp.status_code == 409 and resp.get_json()["success"] is False
    listed = client.get(f"{CLOSINGS}?user_id={fl}").get_json()["data"]["closings"]
    assert [c["id"] for c in listed] == [closing_id]
    assert client.delete(f"{CLOSINGS}/{closing_id}", json={}).status_code == 400
    resp = client.delete(f"{CLOSINGS}/{closing_id}", json={"reason": "가짜 다시 마감"})
    assert resp.status_code == 200 and resp.get_json()["data"]["cancelled"]["month"] == "2030-03"
    closing_id = client.post(CLOSINGS, json={"user_id": fl, "month": "2030-03"}).get_json()["data"]["id"]
    resp = client.post(f"{CLOSINGS}/{closing_id}/paid")
    assert resp.status_code == 200 and resp.get_json()["data"]["status"] == "PAID"
    assert client.post(f"{CLOSINGS}/{closing_id}/paid").status_code == 409
    resp = client.delete(f"{CLOSINGS}/{closing_id}", json={"reason": "가짜"})
    assert resp.status_code == 409 and resp.get_json()["error"] == "지급한 마감은 되돌릴 수 없어요."


def _denied_calls(client, fl: int, closing_id: int) -> list[int]:
    return [
        client.get(f"{CLOSINGS}?user_id={fl}").status_code,
        client.get(f"{CLOSINGS}/preview?user_id={fl}&month=2030-04").status_code,
        client.post(CLOSINGS, json={"user_id": fl, "month": "2030-04"}).status_code,
        client.post(f"{CLOSINGS}/{closing_id}/paid").status_code,
        client.delete(f"{CLOSINGS}/{closing_id}", json={"reason": "가짜"}).status_code,
    ]


@pytest.mark.parametrize("who", [*_DENIED, "freelancer"])
def test_api_denied_for_cs_sales_and_freelancer(app, world, who):
    row = _close(world["fl"], "2030-03")
    if who == "freelancer":
        client = app.test_client()
        _login(client, db_session.get(User, world["fl"]))
    else:
        client = _client(app, *who)
    assert _denied_calls(client, world["fl"], row.id) == [403] * 5
    db_session.expire_all()
    rows = db_session.query(SalesCommissionClosing).all()
    assert [(r.id, r.month, r.status) for r in rows] == [(row.id, "2030-03", "CLOSED")]  # 아무것도 안 바뀜


@pytest.mark.parametrize("role,team,allowed", [*[(r, t, True) for r, t in _ALLOWED],
                                               *[(r, t, False) for r, t in _DENIED]])
def test_api_write_policy_guard(app, world, policy_on, role, team, allowed):  # noqa: F811
    client = _client(app, role, team)
    resp = client.post(CLOSINGS, json={"user_id": world["fl"], "month": "2030-03"})
    if allowed:
        assert resp.status_code == 201, resp.get_json()
    else:
        assert resp.status_code == 403 and resp.headers.get("X-Auth-Policy") == "denied"
        assert db_session.query(SalesCommissionClosing).count() == 0


def test_api_unauthenticated_and_validation(app, world):
    assert app.test_client().get(f"{CLOSINGS}?user_id={world['fl']}").status_code == 401
    client = _client(app, "ADMIN", None)
    assert client.get(CLOSINGS).status_code == 400
    assert client.get(f"{CLOSINGS}/preview?month=2030-03").status_code == 400
    assert client.get(f"{CLOSINGS}/preview?user_id={world['fl']}&month=2030-3").status_code == 400
    assert client.get(f"{CLOSINGS}/preview?user_id=999999&month=2030-03").status_code == 404
    assert client.post(CLOSINGS, data="x", content_type="text/plain").status_code == 400
    assert client.post(CLOSINGS, json={"user_id": world["fl"], "month": "2030/03"}).status_code == 400
    assert client.post(CLOSINGS, json={"user_id": world["fl"], "month": "2030-05"}).status_code == 400
    assert client.post(CLOSINGS, json={"user_id": 999_999, "month": "2030-03"}).status_code == 404
    assert client.post(f"{CLOSINGS}/999999/paid").status_code == 404
    assert client.delete(f"{CLOSINGS}/999999", json={"reason": "가짜"}).status_code == 404
