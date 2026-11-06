"""FCOMM-01 T12 — 영업 수수료 조정 줄(마감 뒤 바뀐 몫).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §1.2 J9 · §8.2 · §11.1("마감 뒤 대표 담당 F→G",
"마감 뒤 차감 추가·시공비 정정"), 검수 원장 A14 · A16.
요율 · 금액 · 이름은 모두 가짜 값이다(저장소 공개 — 실제 요율은 설정에만 있다).

시드: 프리랜서 F 의 2030-02 마감(라홈 a 60,000 · 하우드 b 120,000 · 숨고 m 100,000(지정 500bp) · 품목 둘 two 60,000
= 340,000)이 이미 있다. G 는 라홈 g(40,000) 하나 · 마감 없음. F 의 3월 주문 n 은 시공비가 비어 있다(필요한 시험만 넣는다).
"""
from __future__ import annotations

import copy
import csv
import datetime
import io
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

from db import db_session, engine
from foms.services.sales_commission import closing as closing_mod
from foms.services.sales_commission.adjust import compute_adjustments
from foms.services.sales_commission.closing import ClosingError, close_month, preview_closing
from foms.services.sales_commission.read_model import commission_rows
from foms.services.sales_commission.settings import SETTINGS_KEY, add_rate, load_settings
from models import Order, SalesCommissionClosing, SalesCommissionInput, SecurityLog, SystemSetting, User
from tests.domains.test_auth_finance import _login, _make_user
from tests.domains.test_my_commission_page import _content
from tests.domains.test_sales_commission_api import MATCH, OTHER_MATCH, _add_freelancer, _input, _order

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TWO_ITEMS = {"items": [{"product_name": "가짜장", "price": 2_000_000}, {"product_name": "가짜문", "price": 500_000}]}
FEB_GROSS = 340_000


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    """마감 서비스 오늘 = 2030-04-10(한국 시각) — 2030-02 ~ 04 를 마감할 수 있다."""
    monkeypatch.setattr(closing_mod, "get_today_kst", lambda: datetime.date(2030, 4, 10))


def _close(user_id: int, month: str) -> SalesCommissionClosing:
    row = close_month(db_session, user_id, month, actor_user_id=None)
    db_session.commit()
    return row


@pytest.fixture
def world(app):
    fl = _add_freelancer(MATCH)
    other = _add_freelancer(OTHER_MATCH)
    ids = {
        # (2,500,000 − 1,000,000) × 4% = 60,000
        "a": _order(manager=MATCH, orderer="라홈 가짜점", construction="2030-02-10"),
        # (3,000,000 − 1,000,000) × 6% = 120,000
        "b": _order(manager=MATCH, orderer="하우드", construction="2030-02-20", price=3_000_000),
        # 숨고 · 지정 500bp: (2,500,000 − 500,000) × 5% = 100,000
        "m": _order(manager=MATCH, orderer="숨고", construction="2030-02-25"),
        # 품목 둘(2,000,000 + 500,000): (2,500,000 − 1,000,000) × 4% = 60,000
        "two": _order(manager=MATCH, orderer="라홈 가짜점", construction="2030-02-12", extra=_TWO_ITEMS),
        # G 몫: (2,000,000 − 1,000,000) × 4% = 40,000
        "g": _order(manager=OTHER_MATCH, orderer="라홈", construction="2030-02-15", price=2_000_000),
        # F 의 3월 새 주문(시공비 없음). 넣으면 (2,000,000 − 1,000,000) × 4% = 40,000
        "n": _order(manager=MATCH, orderer="라홈", construction="2030-03-05", price=2_000_000),
    }
    for key in ("a", "b", "two", "g"):
        _input(ids[key], install_cost=1_000_000)
    _input(ids["m"], install_cost=500_000, rate_override_bp=500)
    feb = _close(fl.id, "2030-02")
    assert feb.gross == FEB_GROSS and {line["kind"] for line in feb.lines} == {"NORMAL"}
    return {"fl": fl.id, "other": other.id, "ids": ids}


# --------------------------------------------------------------------------
# 시드 도우미
# --------------------------------------------------------------------------
def _mutate_sd(order_id: int, change) -> None:
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    change(sd)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _add_deduction(order_id: int, *, did: str, amount: int, user_id: int | None, department: str = "SALES") -> None:
    def change(sd):
        entries = sd.setdefault("settlement", {}).setdefault("deductions", [])
        entries.append({"id": did, "department": department, "charge_to_user_id": user_id, "amount": amount,
                        "reason": "가짜 사유", "created_at": "2030-03-02T10:00:00", "created_by": "가짜회계"})
    _mutate_sd(order_id, change)


def _void_deduction(order_id: int, did: str) -> None:
    def change(sd):
        for entry in sd["settlement"]["deductions"]:
            if entry["id"] == did:
                entry["voided_at"] = "2030-04-01T09:00:00"
    _mutate_sd(order_id, change)


def _set_input(order_id: int, **fields) -> None:
    row = db_session.get(SalesCommissionInput, order_id)
    for key, value in fields.items():
        setattr(row, key, value)
    row.version = int(row.version or 1) + 1
    db_session.commit()


def _set_order(order_id: int, **columns) -> None:
    order = db_session.get(Order, order_id)
    for key, value in columns.items():
        setattr(order, key, value)
    db_session.commit()


def _by_key(lines: list[dict]) -> dict[tuple[int, str], dict]:
    return {(line["order_id"], line["kind"]): line for line in lines}


def _adjusts(user_id: int) -> dict[int, dict]:
    lines, _skipped = compute_adjustments(db_session, user_id)
    return {line["order_id"]: line for line in lines}


def _closed_sum(user_id: int, order_id: int) -> int:
    rows = db_session.query(SalesCommissionClosing).filter(SalesCommissionClosing.user_id == user_id).all()
    return sum(int(line["commission"]) for row in rows for line in row.lines if line["order_id"] == order_id)


# --------------------------------------------------------------------------
# 차감 · 시공비 · 품목 취소
# --------------------------------------------------------------------------
def test_no_change_gives_no_adjust_line(world):
    ids = world["ids"]
    _mutate_sd(ids["a"], lambda sd: sd["parties"]["customer"].update(name="이름바뀐고객"))  # 돈과 무관한 칸
    _input(ids["n"], install_cost=1_000_000)
    data = preview_closing(db_session, world["fl"], "2030-03")
    assert [(line["order_id"], line["kind"]) for line in data["lines"]] == [(ids["n"], "NORMAL")]
    assert (data["adjust_count"], data["adjust_total"], data["adjust_skipped"]) == (0, 0, [])
    assert data["totals"]["gross"] == 40_000


def test_late_deduction_adds_negative_adjust_next_to_new_normal_lines(world):
    ids, fl = world["ids"], world["fl"]
    _add_deduction(ids["a"], did="late", amount=-100_000, user_id=fl)
    # 대조군: CS 부서 차감 · G 에게 붙은 영업 차감은 F 의 몫을 바꾸지 않는다
    _add_deduction(ids["a"], did="cs", amount=-50_000, user_id=None, department="CS")
    _add_deduction(ids["a"], did="to-g", amount=-70_000, user_id=world["other"])
    _input(ids["n"], install_cost=1_000_000)

    data = preview_closing(db_session, fl, "2030-03")
    lines = _by_key(data["lines"])
    assert set(lines) == {(ids["n"], "NORMAL"), (ids["a"], "ADJUST")}
    # (2,500,000 − 1,000,000 − 100,000) × 4% = 56,000 → 이미 준 60,000 과의 차액 −4,000
    assert lines[(ids["a"], "ADJUST")] == {
        "order_id": ids["a"], "kind": "ADJUST", "deal_type": "LAHOM", "shipping_price": 2_500_000,
        "install_cost": 1_000_000, "deduction_total": 100_000, "rate_bp": 400, "commission": -4_000,
        "label": "가짜고객 · 가짜장", "completion_month": "2030-02"}
    assert [line["kind"] for line in data["lines"]] == ["NORMAL", "ADJUST"]
    assert (data["adjust_count"], data["adjust_total"]) == (1, -4_000)
    assert data["totals"]["gross"] == 36_000 and data["can_close"] is True

    row = _close(fl, "2030-03")
    assert row.gross == 36_000 and row.lines == data["lines"]
    assert _closed_sum(fl, ids["a"]) == 56_000


def test_voided_deduction_after_adjust_brings_it_back(world):
    ids, fl = world["ids"], world["fl"]
    _add_deduction(ids["a"], did="late", amount=-100_000, user_id=fl)
    _input(ids["n"], install_cost=1_000_000)
    _close(fl, "2030-03")  # 조정 −4,000
    _void_deduction(ids["a"], "late")

    april = _close(fl, "2030-04")
    assert [(line["order_id"], line["kind"], line["commission"]) for line in april.lines] == [
        (ids["a"], "ADJUST", 4_000)]
    assert april.lines[0]["deduction_total"] == 0
    assert _closed_sum(fl, ids["a"]) == 60_000  # 모든 줄 합 = 지금 다시 센 값
    assert compute_adjustments(db_session, fl) == ([], [])  # 더 바뀐 게 없으면 다음 마감엔 조정 없음


def test_install_cost_corrected_upward_gives_negative_adjust(world):
    ids, fl = world["ids"], world["fl"]
    _set_input(ids["b"], install_cost=1_500_000)
    _input(ids["n"], install_cost=1_000_000)
    row = _close(fl, "2030-03")
    adjust = _by_key(row.lines)[(ids["b"], "ADJUST")]
    # (3,000,000 − 1,500,000) × 6% = 90,000 → −30,000
    assert (adjust["install_cost"], adjust["rate_bp"], adjust["deal_type"], adjust["commission"]) == (
        1_500_000, 600, "HAUD", -30_000)
    assert row.gross == 40_000 - 30_000


def test_cancelled_item_after_closing_gives_negative_adjust(world):
    ids = world["ids"]
    _mutate_sd(ids["two"], lambda sd: sd["items"][1].update(cancel={"at": "2030-03-03", "by": "가짜"}))
    adjust = _adjusts(world["fl"])[ids["two"]]
    # 출고가 2,500,000 → 2,000,000: (2,000,000 − 1,000,000) × 4% = 40,000 → −20,000
    assert (adjust["shipping_price"], adjust["commission"]) == (2_000_000, -20_000)
    assert adjust["label"] == "가짜고객 · 가짜장"  # 취소 품목은 품목 이름에서도 빠진다
    assert set(_adjusts(world["fl"])) == {ids["two"]}


# --------------------------------------------------------------------------
# 굳힌 주인 · 거래구분 · 요율(J9)
# --------------------------------------------------------------------------
def test_manager_change_after_closing_keeps_adjust_with_frozen_owner(world):
    ids, fl, other = world["ids"], world["fl"], world["other"]

    def to_g_and_haud(sd):  # 대표 담당 F → G, 발주사도 하우드로(지금 판정이면 G · 하우드 600bp)
        sd["parties"]["manager"]["name"] = OTHER_MATCH
        sd["parties"]["orderer"]["name"] = "하우드"
    _mutate_sd(ids["a"], to_g_and_haud)
    _set_order(ids["a"], manager_name=OTHER_MATCH)
    _add_deduction(ids["a"], did="to-f", amount=-100_000, user_id=fl)
    _add_deduction(ids["a"], did="to-g", amount=-50_000, user_id=other)

    adjust = _adjusts(fl)[ids["a"]]
    assert (adjust["deal_type"], adjust["rate_bp"], adjust["deduction_total"], adjust["commission"]) == (
        "LAHOM", 400, 100_000, -4_000)  # 굳힌 주인 F · 라홈 · 400bp, F 에게 붙은 차감만
    g_preview = preview_closing(db_session, other, "2030-03")
    assert [(line["order_id"], line["kind"]) for line in g_preview["lines"]] == [(ids["g"], "NORMAL")]
    _close(other, "2030-03")
    assert compute_adjustments(db_session, other) == ([], [])  # G 에게는 일반 줄도 조정 줄도 안 간다
    assert ids["a"] not in {r["order_id"] for r in commission_rows(db_session, other, "2030-04", "completion")["rows"]}


def test_override_change_uses_new_rate_but_rate_table_change_keeps_frozen_rate(world):
    ids, fl = world["ids"], world["fl"]
    setting = db_session.query(SystemSetting).filter(SystemSetting.setting_key == SETTINGS_KEY).one()
    value = copy.deepcopy(setting.setting_value)
    value["freelancers"][str(fl)]["rates"][0].update(lahom_bp=500, haud_bp=700)  # 마감한 달의 표를 몰래 고친 셈
    setting.setting_value = value
    flag_modified(setting, "setting_value")
    db_session.commit()
    assert load_settings(db_session)[1][fl].rate_for("2030-02").lahom_bp == 500  # 고친 게 먹혔다(대조)
    add_rate(db_session, fl, {"effective_month": "2030-03", "lahom_bp": 450, "haud_bp": 650, "personal_bp": 850},
             base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    assert _adjusts(fl) == {}  # 요율 표가 바뀌어도 마감한 주문은 굳힌 요율

    _set_input(ids["m"], rate_override_bp=600)  # 숨고: 회계팀 지정 요율 500 → 600
    _set_input(ids["a"], rate_override_bp=300)  # 라홈도 회계팀 지정 요율이 바뀌면 새 값(J9)
    _input(ids["n"], install_cost=1_000_000)
    data = preview_closing(db_session, fl, "2030-03")
    lines = _by_key(data["lines"])
    # 숨고 (2,500,000 − 500,000) × 6% = 120,000 → +20,000 · 라홈 1,500,000 × 3% = 45,000 → −15,000
    assert (lines[(ids["m"], "ADJUST")]["rate_bp"], lines[(ids["m"], "ADJUST")]["commission"]) == (600, 20_000)
    assert lines[(ids["m"], "ADJUST")]["deal_type"] == "MANUAL"
    assert (lines[(ids["a"], "ADJUST")]["rate_bp"], lines[(ids["a"], "ADJUST")]["commission"]) == (300, -15_000)
    assert lines[(ids["n"], "NORMAL")]["rate_bp"] == 450  # 새 줄은 지금 요율 표
    assert set(lines) == {(ids["m"], "ADJUST"), (ids["a"], "ADJUST"), (ids["n"], "NORMAL")}

    _set_input(ids["m"], rate_override_bp=None)  # 지정 요율을 지우면 굳힌 500 그대로
    _set_input(ids["a"], rate_override_bp=None)
    assert _adjusts(fl) == {}


# --------------------------------------------------------------------------
# 빠진 주문 · 합계 0 이하
# --------------------------------------------------------------------------
def test_deleted_reverted_or_costless_orders_are_skipped_not_clawed_back(world):
    ids, fl = world["ids"], world["fl"]
    _add_deduction(ids["a"], did="late", amount=-100_000, user_id=fl)
    _set_order(ids["a"], deleted_at="2030-03-01")
    _set_input(ids["b"], install_cost=1_500_000)
    _set_order(ids["b"], erp_stage_code="PRODUCTION")
    _set_input(ids["m"], install_cost=None)
    _input(ids["n"], install_cost=1_000_000)

    data = preview_closing(db_session, fl, "2030-03")
    assert data["adjust_count"] == 0
    assert data["adjust_skipped"] == [
        {"order_id": ids["a"], "reason": "GONE", "reason_text": "지워진 주문", "label": "가짜고객 · 가짜장",
         "completion_month": "2030-02"},
        {"order_id": ids["b"], "reason": "STAGE", "reason_text": "단계가 되돌려진 주문", "label": "가짜고객 · 가짜장",
         "completion_month": "2030-02"},
        {"order_id": ids["m"], "reason": "WAIT_COST", "reason_text": "시공비가 빈 주문", "label": "가짜고객 · 가짜장",
         "completion_month": "2030-02"},
    ]
    row = _close(fl, "2030-03")
    assert [(line["order_id"], line["kind"]) for line in row.lines] == [(ids["n"], "NORMAL")]
    log = db_session.query(SecurityLog).filter(SecurityLog.action == "SALES_COMMISSION_CLOSED").order_by(
        SecurityLog.id.desc()).first()
    assert log.detail["adjust_skipped"] == [{"order_id": ids["a"], "reason": "GONE"},
                                            {"order_id": ids["b"], "reason": "STAGE"},
                                            {"order_id": ids["m"], "reason": "WAIT_COST"}]
    assert "가짜고객" not in str(log.detail)
    # 대조군: 단계가 다시 시공 완료로 오면 그때 차액이 조정 줄로 나온다
    _set_order(ids["b"], erp_stage_code="CS")
    assert _adjusts(fl)[ids["b"]]["commission"] == -30_000


def test_negative_only_month_is_rejected_then_nets_into_next_closing(world):
    ids, fl = world["ids"], world["fl"]
    _add_deduction(ids["a"], did="late", amount=-100_000, user_id=fl)
    data = preview_closing(db_session, fl, "2030-03")
    assert [(line["kind"], line["commission"]) for line in data["lines"]] == [("ADJUST", -4_000)]
    assert data["totals"]["gross"] == -4_000 and data["totals"]["net"] == 0
    assert data["can_close"] is False and data["block_reason"] == "이번 달은 줄 돈이 없어요."
    with pytest.raises(ClosingError) as err:
        close_month(db_session, fl, "2030-03", actor_user_id=None)
    db_session.rollback()
    assert err.value.status == 400

    _input(ids["n"], install_cost=1_000_000)
    april = _close(fl, "2030-04")
    assert sorted((line["kind"], line["commission"]) for line in april.lines) == [("ADJUST", -4_000),
                                                                                  ("NORMAL", 40_000)]
    assert april.gross == 36_000 and _closed_sum(fl, ids["a"]) == 56_000


# --------------------------------------------------------------------------
# 내려받기 · 내 수수료 화면 · 확인 창
# --------------------------------------------------------------------------
def test_csv_preview_api_and_freelancer_page_show_the_adjust_line(app, world, monkeypatch):
    import foms.web.sales_commission as page
    ids, fl = world["ids"], world["fl"]
    _add_deduction(ids["a"], did="late", amount=-100_000, user_id=fl)
    _input(ids["n"], install_cost=1_000_000)
    accounting = app.test_client()
    _login(accounting, _make_user("STAFF", "ACCOUNTING"))
    preview = accounting.get(f"/api/sales-commission/closings/preview?user_id={fl}&month=2030-03").get_json()
    assert preview["success"] is True
    assert (preview["data"]["adjust_count"], preview["data"]["adjust_total"]) == (1, -4_000)
    _close(fl, "2030-03")

    resp = accounting.get(f"/api/sales-commission/export.csv?user_id={fl}&month=2030-03")
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True).lstrip("﻿"))))
    adjust = [r for r in rows if r and r[-1] == "조정"]
    assert adjust == [["2030-02", "가짜고객 · 가짜장", "라홈", "2500000", "1000000", "100000", "4", "-4000", "조정"]]

    monkeypatch.setattr(page, "get_today_kst", lambda: datetime.date(2030, 4, 3))
    client = app.test_client()
    _login(client, db_session.get(User, fl))
    resp = client.get("/erp/my-commission?month=2030-03&basis=completion")
    assert resp.status_code == 200
    content = _content(resp.get_data(as_text=True))
    assert "36,000원" in content and "조정 · 라홈" in content and "2월 시공" in content
    assert "−4,000원" in content and "지난 마감 뒤 바뀐 몫 −4,000원" in content

    _void_deduction(ids["a"], "late")
    _close(fl, "2030-04")
    content = _content(client.get("/erp/my-commission?month=2030-04&basis=completion").get_data(as_text=True))
    assert "지난 마감 뒤 바뀐 몫 +4,000원" in content and "+4,000원" in content


def test_close_dialog_reads_adjust_fields():
    source = (_REPO_ROOT / "static/js/settlement/commission-close.js").read_text(encoding="utf-8")
    for key in ("adjust_count", "adjust_total", "adjust_skipped", "reason_text", "'조정'"):
        assert key in source, key


# --------------------------------------------------------------------------
# 조회 수 — 주문마다 묻지 않는다
# --------------------------------------------------------------------------
def _count_queries(fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def test_adjust_query_count_does_not_grow_with_closed_orders(world):
    fl = world["fl"]
    db_session.expire_all()
    _result, small = _count_queries(lambda: compute_adjustments(db_session, fl))
    _input(world["ids"]["n"], install_cost=1_000_000)
    for day in ("06", "07", "08"):
        oid = _order(manager=MATCH, orderer="라홈", construction=f"2030-03-{day}")
        _input(oid, install_cost=1_000_000)
    _close(fl, "2030-03")
    db_session.expire_all()
    result, large = _count_queries(lambda: compute_adjustments(db_session, fl))
    assert result == ([], [])
    assert small == large == 3  # 마감 1번 · 주문 1번 · 시공비 입력 1번
