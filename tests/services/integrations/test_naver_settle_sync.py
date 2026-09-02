"""SETTLE-CHANNEL-01 §4: 정산 동기화 계약 테스트 (SQLite 레인).

네트워크를 타지 않는다 — 고정 JSON 픽스처(문서 원문 필드명 그대로)를 주는 FakeClient 로
결정적으로 고정한다. 여기서 지키는 계약 일곱:

* **멱등**: 같은 날짜를 두 번 돌려도 행 수가 같다(파티션 통째 교체).
* **소급 변경 감지**: 이미 적재한 파티션의 금액이 바뀌면 ``stats["retro_changes"]`` 에 남는다.
* **매칭 축**: ``PROD_ORDER`` 행만 붙이고, 배송비 행은 ``NA``, 링크 없는 상품주문은 ``UNMATCHED``.
* **부호 보존**: 음수 금액을 뒤집지 않는다(정산 후 취소·빠른정산 회수는 원래 음수다).
* **쿼터 중단**: 헤더가 오면 그 자리에서 멈추고 **성공 구간을 전진시키지 않는다**.
* **dry_run 무기록**: 이력 행도 정산 행도 워터마크도 만들지 않는다.
* **부가세 익월 10일 규칙**: 10일 전에는 안 당기고, 10일 이후 전월분을 **한 번만** 당긴다.

러너(``scripts/maintenance/run_naver_settle_sync.py``)와 ``start.sh`` 배선은
``test_naver_auto_dispatch.py`` 와 같은 방식으로 소스에서 잰다.
"""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal

import pytest

from db import db_session
from foms.services.integrations.naver_commerce import settle_sync
from foms.services.integrations.naver_commerce.settle_sync import (
    read_settle_state,
    run_settle_sync,
)
from models import (
    ExternalOrderLink,
    NaverSettleCase,
    NaverSettleCommission,
    NaverSettleDaily,
    NaverSettleSyncRun,
    NaverVatCase,
    NaverVatDaily,
    Order,
)

TODAY = date(2026, 9, 2)
D1 = "2026-09-01"
D2 = "2026-09-02"

#: 부가세 규칙을 켜는 날(익월 10일 이후).
VAT_DAY = date(2026, 9, 15)


# --------------------------------------------------------------------------- #
# 픽스처 — 필드명은 문서 원문(camelCase) 그대로
# docs/research/2026-09-02-naver-settlement/raw/*.md
# --------------------------------------------------------------------------- #

def _daily(expect_date: str, settle_amount: str = "1000000") -> dict:
    """``settle/daily`` element 1건."""
    return {
        "settleBasisStartDate": "2026-08-25",
        "settleBasisEndDate": "2026-08-31",
        "settleExpectDate": expect_date,
        "settleCompleteDate": expect_date,
        "settleAmount": settle_amount,
        "paySettleAmount": "1050000",
        "commissionSettleAmount": "-50000",
        "benefitSettleAmount": "0",
        "deductionRestoreSettleAmount": "0",
        "payHoldbackAmount": "0",
        "minusChargeAmount": "0",
        "differenceSettleAmount": "0",
        "returnCareSettleAmount": "0",
        "normalSettleAmount": settle_amount,
        "quickSettleAmount": "0",
        "preferentialCommissionAmount": "0",
        "settlementLimitAmount": "0",
        "settleMethodType": "ACCOUNT",
        "bankType": "KOOKMIN",
        "depositorName": "라홈시스템",
        "accountNo": "12345678901234",
        "merchantId": "ncp_merchant",
        "merchantName": "라홈",
    }


def _case(product_order_id: str, *, product_order_type: str = "PROD_ORDER",
          pay_settle_amount: str = "1250000", settle_type: str = "NORMAL_SETTLE_ORIGINAL") -> dict:
    """``settle/case`` element 1건."""
    return {
        "settleBasisDate": "2026-08-30",
        "settleExpectDate": D1,
        "settleCompleteDate": D1,
        "payDate": "2026-08-28",
        "orderId": f"ORD-{product_order_id}",
        "productOrderId": product_order_id,
        "productOrderType": product_order_type,
        "settleType": settle_type,
        "productId": "PRD-1",
        "productName": "루나 붙박이장 3000",
        "purchaserName": "김구매",
        "paySettleAmount": pay_settle_amount,
        "totalPayCommissionAmount": "-37500",
        "freeInstallmentCommissionAmount": "0",
        "sellingInterlockCommissionAmount": "-2500",
        "benefitSettleAmount": "0",
        "settleExpectAmount": pay_settle_amount,
        "merchantId": "ncp_merchant",
        "merchantName": "라홈",
        "contractNo": "C-1",
    }


def _commission(product_order_id: str) -> dict:
    """``settle/commission-details`` element 1건(주문번호 키가 ``orderNo`` 다)."""
    return {
        "orderNo": f"ORD-{product_order_id}",
        "productOrderId": product_order_id,
        "productOrderType": "PROD_ORDER",
        "productId": "PRD-1",
        "productName": "루나 붙박이장 3000",
        "merchantId": "ncp_merchant",
        "merchantName": "라홈",
        "purchaserName": "김구매",
        "settleType": "NORMAL_SETTLE_ORIGINAL",
        "settleBasisDate": "2026-08-30",
        "settleExpectDate": D1,
        "settleCompleteDate": D1,
        "taxReturnDate": "2026-08-30",
        "commissionBasisAmount": "1250000",
        "commissionType": "PAY_COMMISSION",
        "payMeansType": "CARD",
        "commissionAmount": "-37500",
        "maximumSellingInterlockCommissionAmount": "500000",
    }


def _vat_daily(basis_date: str) -> dict:
    """``vat/daily`` element 1건(대소문자가 특이한 두 키를 그대로 쓴다)."""
    return {
        "settleBasisDate": basis_date,
        "totalSalesAmount": "2000000",
        "taxationSalesAmount": "1800000",
        "taxExemptionSalesAmount": "200000",
        "creditCardAmount": "1500000",
        "cashInComeDeductionAmount": "300000",
        "cashOutGoingEvidenceAmount": "100000",
        "cashExclusionIssuanceAmount": "50000",
        "otherAmount": "50000",
        "merchantId": "ncp_merchant",
        "merchantName": "라홈",
    }


def _vat_case(basis_date: str, product_order_id: str) -> dict:
    """``vat/case`` element 1건."""
    row = _vat_daily(basis_date)
    row.update({
        "orderId": f"ORD-{product_order_id}",
        "productOrderId": product_order_id,
        "productOrderType": "PROD_ORDER",
        "detailType": "PAY_SETTLE",
        "status": "ORIGINAL_SALES",
        "productName": "루나 붙박이장 3000",
    })
    return row


class FakeClient:
    """고정 픽스처를 돌려주는 가짜 정산 클라이언트(호출 이력·쿼터 헤더 관측 포함)."""

    def __init__(self, *, daily: list | None = None, cases: dict | None = None,
                 commissions: dict | None = None, vat_daily: list | None = None,
                 vat_cases: list | None = None, quota_after: int | None = None) -> None:
        self.daily = list(daily or [])
        self.cases = dict(cases or {})
        self.commissions = dict(commissions or {})
        self.vat_daily = list(vat_daily or [])
        self.vat_cases = list(vat_cases or [])
        self.quota_after = quota_after
        self.calls: list[tuple[str, str]] = []
        self.last_quota_limit_header = None

    def _page(self, endpoint: str, key: str, elements: list) -> dict:
        self.calls.append((endpoint, key))
        if self.quota_after is not None and len(self.calls) >= self.quota_after:
            self.last_quota_limit_header = "5"
        return {"elements": list(elements),
                "pagination": {"page": 1, "size": 1000, "totalPages": 1,
                               "totalElements": len(elements)}}

    def get_settle_daily(self, start_date, end_date, *, page=1, page_size=1000):
        return self._page("settle/daily", f"{start_date}~{end_date}", self.daily)

    def get_settle_cases(self, search_date, *, page=1, page_size=1000, **kwargs):
        key = search_date.isoformat()
        return self._page("settle/case", key, self.cases.get(key, []))

    def get_settle_commission_details(self, search_date, *, page=1, page_size=1000, **kwargs):
        key = search_date.isoformat()
        return self._page("settle/commission-details", key, self.commissions.get(key, []))

    def get_vat_daily(self, start_date, end_date, *, page=1, page_size=1000):
        return self._page("vat/daily", f"{start_date}~{end_date}", self.vat_daily)

    def get_vat_cases(self, start_date, end_date, *, page=1, page_size=1000):
        return self._page("vat/case", f"{start_date}~{end_date}", self.vat_cases)


@pytest.fixture
def narrow_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """조회 구간을 4일로 좁힌다 — 계약은 같고 픽스처만 읽기 쉬워진다."""
    monkeypatch.setattr(settle_sync, "DEFAULT_ROLLING_DAYS", 2)
    monkeypatch.setattr(settle_sync, "DEFAULT_FUTURE_DAYS", 1)


def _run(client: FakeClient, *, today: date = TODAY, **kwargs) -> dict:
    """실대기 없이 1회 실행한다."""
    kwargs.setdefault("trigger", "SCHEDULE")
    return run_settle_sync(db_session, client, today=today,
                           sleep=lambda _seconds: None, **kwargs)


def _order_id(name: str = "김고객") -> int:
    order = Order(received_date="2026-08-01", customer_name=name, phone="010-1111-2222",
                  address="서울시 강남구 테헤란로 152", product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _link(external_id: str, *, order_id: int | None = None) -> int:
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             external_order_no=f"ORD-{external_id}", order_id=order_id,
                             sync_status="LINKED" if order_id else "PENDING_REVIEW",
                             raw_snapshot={"productOrder": {"productOrderId": external_id}})
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def _counts() -> dict[str, int]:
    """테이블별 행 수."""
    return {model.__tablename__: db_session.query(model).count()
            for model in (NaverSettleDaily, NaverSettleCase, NaverSettleCommission,
                          NaverVatDaily, NaverVatCase)}


# --------------------------------------------------------------------------- #
# ① 멱등 — 두 번 돌려도 행 수가 같다
# --------------------------------------------------------------------------- #

def test_rerun_keeps_row_counts_identical(app, narrow_range):
    """같은 응답을 두 번 적재해도 행이 쌓이지 않는다(파티션 통째 교체)."""
    client = FakeClient(daily=[_daily(D1), _daily(D2)],
                        cases={D1: [_case("PO-1")]},
                        commissions={D1: [_commission("PO-1")]})
    first = _run(client)
    assert first["ok"] is True and first["status"] == "OK"
    after_first = _counts()
    assert after_first["naver_settle_daily"] == 2
    assert after_first["naver_settle_case"] == 1
    assert after_first["naver_settle_commission"] == 1

    second = _run(client)
    assert second["ok"] is True
    assert _counts() == after_first
    # 값이 안 바뀌었으니 소급 변경도 없다.
    assert second["stats"]["retro_changes"] == []


def test_rerun_opens_a_new_run_row_and_advances_coverage(app, narrow_range):
    """실행마다 이력 행이 생기고, 성공하면 성공 구간이 전진한다."""
    client = FakeClient(daily=[_daily(D1)])
    _run(client)
    _run(client)
    runs = db_session.query(NaverSettleSyncRun).order_by(NaverSettleSyncRun.id).all()
    assert [run.status for run in runs] == ["OK", "OK"]
    state = read_settle_state(db_session)
    assert state["coverage_from"] == "2026-08-31" and state["coverage_to"] == "2026-09-03"
    assert state["last_ok_at"] and state["rev"] == 2
    # 엔드포인트마다 어디까지 훑었는지 따로 남는다(부가세는 구간이 다르다).
    per_endpoint = state["per_endpoint"]
    assert per_endpoint["settle/daily"]["last_ok_date"] == "2026-09-03"
    assert per_endpoint["settle/case"]["last_ok_date"] == "2026-09-03"
    assert per_endpoint["settle/case"]["calls"] == 4


# --------------------------------------------------------------------------- #
# ② 소급 변경 감지
# --------------------------------------------------------------------------- #

def test_retro_change_is_reported_when_amount_moves(app, narrow_range):
    """이미 적재한 날짜의 금액이 바뀌면 소급 변경으로 잡힌다."""
    client = FakeClient(daily=[_daily(D1, "1000000")])
    first = _run(client)
    assert first["stats"]["retro_changes"] == []

    client.daily = [_daily(D1, "900000")]
    second = _run(client)
    changes = second["stats"]["retro_changes"]
    assert len(changes) == 1, changes
    change = changes[0]
    assert change["table"] == "naver_settle_daily" and change["date"] == D1
    assert Decimal(change["old_total"]) == Decimal("1000000")
    assert Decimal(change["new_total"]) == Decimal("900000")
    assert change["old_count"] == 1 and change["new_count"] == 1
    # 이력 행에도 같은 통계가 남는다(화면 예외 목록이 이걸 읽는다).
    run = db_session.query(NaverSettleSyncRun).order_by(NaverSettleSyncRun.id.desc()).first()
    assert run.stats["retro_changes"] == changes


def test_row_disappearing_is_a_retro_change_too(app, narrow_range):
    """행이 통째로 사라진 것도 소급 변경이다(응답에 없는 날짜도 비운다)."""
    client = FakeClient(daily=[_daily(D1)])
    _run(client)
    client.daily = []
    second = _run(client)
    assert db_session.query(NaverSettleDaily).count() == 0
    assert [c["new_count"] for c in second["stats"]["retro_changes"]] == [0]


def test_first_load_is_not_counted_as_a_retro_change(app, narrow_range):
    """처음 적재는 소급 변경이 아니다 — 그것까지 세면 첫 백필이 통째로 '변경'이 된다."""
    client = FakeClient(daily=[_daily(D1), _daily(D2)],
                        cases={D1: [_case("PO-1")]})
    assert _run(client)["stats"]["retro_changes"] == []


# --------------------------------------------------------------------------- #
# ③ 매칭 — PROD_ORDER 만
# --------------------------------------------------------------------------- #

def test_only_prod_order_rows_are_matched(app, narrow_range):
    """상품주문만 붙인다: 링크+주문=MATCHED, 링크 없음=UNMATCHED, 배송비=NA."""
    order_id = _order_id()
    link_id = _link("PO-MATCH", order_id=order_id)
    orphan_link_id = _link("PO-ORPHAN")  # 링크는 있는데 주문이 없다(보류 상태)
    client = FakeClient(cases={D1: [
        _case("PO-MATCH"),
        _case("PO-NOLINK"),
        _case("PO-ORPHAN"),
        _case("PO-DELIVERY", product_order_type="DELIVERY"),
    ]})
    _run(client)

    rows = {row.product_order_id: row
            for row in db_session.query(NaverSettleCase).all()}
    assert rows["PO-MATCH"].match_status == "MATCHED"
    assert rows["PO-MATCH"].foms_order_id == order_id
    assert rows["PO-MATCH"].link_id == link_id
    assert rows["PO-NOLINK"].match_status == "UNMATCHED"
    assert rows["PO-NOLINK"].foms_order_id is None and rows["PO-NOLINK"].link_id is None
    # 링크는 붙었지만 주문이 없는 건도 미매칭이다(예외 목록 대상).
    assert rows["PO-ORPHAN"].match_status == "UNMATCHED"
    assert rows["PO-ORPHAN"].link_id == orphan_link_id
    assert rows["PO-ORPHAN"].foms_order_id is None
    # 배송비 행은 붙을 주문이 없다 — 미매칭으로 세면 매칭률이 100% 에 못 닿는다.
    assert rows["PO-DELIVERY"].match_status == "NA"
    assert rows["PO-DELIVERY"].link_id is None


def test_matching_ignores_links_from_other_channels(app, narrow_range):
    """채널이 다른 링크에는 붙지 않는다."""
    order_id = _order_id()
    link = ExternalOrderLink(channel="OTHER", external_id="PO-MATCH", order_id=order_id,
                             sync_status="LINKED", raw_snapshot={})
    db_session.add(link)
    db_session.commit()
    _run(FakeClient(cases={D1: [_case("PO-MATCH")]}))
    row = db_session.query(NaverSettleCase).one()
    assert row.match_status == "UNMATCHED" and row.foms_order_id is None


def test_matching_uses_one_batch_query_per_partition(app, narrow_range):
    """매칭은 배치 조회다 — 행마다 부르면(N+1) 원장이 커질수록 느려진다."""
    from sqlalchemy import event

    from db import engine

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        if "external_order_links" in statement.lower():
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        _run(FakeClient(cases={D1: [_case(f"PO-{index}") for index in range(20)]}))
    finally:
        event.remove(engine, "before_cursor_execute", _record)
    assert len(statements) == 1, statements


# --------------------------------------------------------------------------- #
# ④ 부호 보존
# --------------------------------------------------------------------------- #

def test_negative_amounts_are_stored_untouched(app, narrow_range):
    """정산 후 취소·회수 행의 음수를 뒤집지 않는다(재계산 금지)."""
    client = FakeClient(
        daily=[_daily(D1, "-250000")],
        cases={D1: [_case("PO-CANCEL", pay_settle_amount="-1250000",
                          settle_type="NORMAL_SETTLE_AFTER_CANCEL")]})
    _run(client)
    daily = db_session.query(NaverSettleDaily).one()
    assert daily.settle_amount == Decimal("-250000")
    assert daily.commission_settle_amount == Decimal("-50000")
    case = db_session.query(NaverSettleCase).one()
    assert case.pay_settle_amount == Decimal("-1250000")
    assert case.settle_type == "NORMAL_SETTLE_AFTER_CANCEL"
    # 원본은 손대지 않고 통째로 남는다.
    assert case.raw_snapshot["paySettleAmount"] == "-1250000"


def test_naver_field_names_land_on_the_right_columns(app, narrow_range):
    """대소문자가 특이한 부가세 두 키가 우리 컬럼으로 정확히 온다."""
    client = FakeClient(vat_daily=[_vat_daily("2026-08-03")])
    _run(client, today=VAT_DAY)
    row = db_session.query(NaverVatDaily).filter(
        NaverVatDaily.settle_basis_date == date(2026, 8, 3)).one()
    assert row.cash_income_deduction_amount == Decimal("300000")
    assert row.cash_outgoing_evidence_amount == Decimal("100000")
    assert row.total_sales_amount == Decimal("2000000")


# --------------------------------------------------------------------------- #
# ⑤ 쿼터 중단
# --------------------------------------------------------------------------- #

def test_quota_header_aborts_without_advancing_the_watermark(app, narrow_range):
    """쿼터 헤더를 만나면 그 자리에서 멈추고 성공 구간을 전진시키지 않는다."""
    client = FakeClient(daily=[_daily(D1)], cases={D1: [_case("PO-1")]}, quota_after=1)
    result = _run(client)

    assert result["ok"] is False and result["status"] == "ABORTED_QUOTA"
    assert "gncp-gw-quota-limit" in (result["error"] or "")
    # 첫 호출에서 멈췄으니 그 뒤 호출은 없다.
    assert len(client.calls) == 1
    assert _counts() == {name: 0 for name in _counts()}

    run = db_session.query(NaverSettleSyncRun).one()
    assert run.status == "ABORTED_QUOTA" and run.finished_at is not None
    state = read_settle_state(db_session)
    assert state.get("coverage_to") is None and state.get("last_ok_at") is None
    assert state["last_status"] == "ABORTED_QUOTA" and state["last_error"]


def test_stale_quota_header_does_not_abort_the_next_run(app, narrow_range):
    """지난 실행이 남긴 헤더 값 때문에 다음 실행이 첫 호출부터 죽지 않는다."""
    client = FakeClient(daily=[_daily(D1)])
    client.last_quota_limit_header = "5"
    result = _run(client)
    assert result["status"] == "OK"


def test_failure_is_recorded_and_returned_not_raised(app, narrow_range):
    """예외는 이력·상태에 남기고 ``ok=False`` 로 돌려준다(re-raise 하지 않는다)."""

    class BoomClient(FakeClient):
        def get_settle_daily(self, start_date, end_date, *, page=1, page_size=1000):
            raise RuntimeError("네이버 500")

    result = _run(BoomClient())
    assert result["ok"] is False and result["status"] == "FAILED"
    assert "네이버 500" in (result["error"] or "")
    run = db_session.query(NaverSettleSyncRun).one()
    assert run.status == "FAILED" and "네이버 500" in (run.error or "")
    state = read_settle_state(db_session)
    assert state.get("coverage_to") is None and state["last_error"]


# --------------------------------------------------------------------------- #
# ⑥ dry_run 무기록
# --------------------------------------------------------------------------- #

def test_dry_run_calls_naver_but_writes_nothing(app, narrow_range):
    """조회는 하고 DB 에는 아무것도 남기지 않는다 — 이력 행도 워터마크도 없다."""
    client = FakeClient(daily=[_daily(D1), _daily(D2)],
                        cases={D1: [_case("PO-1")]},
                        commissions={D1: [_commission("PO-1")]})
    result = _run(client, dry_run=True)

    assert result["ok"] is True and result["dry_run"] is True
    assert client.calls, "dry_run 도 조회는 한다"
    assert result["stats"]["rows"]["naver_settle_daily"] == 2
    assert _counts() == {name: 0 for name in _counts()}
    assert db_session.query(NaverSettleSyncRun).count() == 0
    assert read_settle_state(db_session) == {}


# --------------------------------------------------------------------------- #
# ⑦ 부가세 익월 10일 규칙
# --------------------------------------------------------------------------- #

def test_vat_is_skipped_before_the_tenth(app, narrow_range):
    """10일 전에는 전월 확정본을 당기지 않는다(아직 확정이 아니다)."""
    client = FakeClient(vat_daily=[_vat_daily("2026-08-03")],
                        vat_cases=[_vat_case("2026-08-03", "PO-1")])
    _run(client, today=date(2026, 9, 9))
    assert [call for call in client.calls if call[0].startswith("vat/")] == []
    assert db_session.query(NaverVatDaily).count() == 0
    assert read_settle_state(db_session).get("vat_final_month") is None


def test_vat_is_loaded_once_after_the_tenth_and_marked_final(app, narrow_range):
    """10일 이후 전월분을 **한 번만** 당기고 확정 표식을 남긴다."""
    client = FakeClient(vat_daily=[_vat_daily("2026-08-03")],
                        vat_cases=[_vat_case("2026-08-03", "PO-1")])
    _run(client, today=VAT_DAY)

    vat_calls = [call for call in client.calls if call[0].startswith("vat/")]
    assert [call[0] for call in vat_calls] == ["vat/daily", "vat/case"]
    assert vat_calls[0][1] == "2026-08-01~2026-08-31"
    daily = db_session.query(NaverVatDaily).one()
    assert daily.is_final is True and daily.settle_basis_date == date(2026, 8, 3)
    assert db_session.query(NaverVatCase).count() == 1
    assert read_settle_state(db_session)["vat_final_month"] == "2026-08"

    # 같은 달에 다시 돌려도 부가세는 안 부른다(확정본을 두 번 받을 이유가 없다).
    client.calls.clear()
    _run(client, today=VAT_DAY)
    assert [call for call in client.calls if call[0].startswith("vat/")] == []


def test_backfill_reloads_every_month_up_to_last_month(app, narrow_range):
    """백필은 시작 달부터 전월까지 월 단위로 다시 받는다."""
    client = FakeClient(vat_daily=[_vat_daily("2026-08-03")])
    _run(client, today=TODAY, trigger="BACKFILL", backfill_from=date(2026, 7, 15))
    vat_windows = [call[1] for call in client.calls if call[0] == "vat/daily"]
    assert vat_windows == ["2026-07-01~2026-07-31", "2026-08-01~2026-08-31"]


# --------------------------------------------------------------------------- #
# 확정 구간 재조회 금지 · 백필 창
# --------------------------------------------------------------------------- #

def test_finalized_days_are_not_refetched_unless_backfilling(app):
    """예정일+30일이 지난 날짜는 백필이 아닌 한 다시 읽지 않는다."""
    assert settle_sync.is_finalized(date(2026, 8, 2), TODAY) is True
    assert settle_sync.is_finalized(date(2026, 8, 3), TODAY) is False

    client = FakeClient()
    _run(client, backfill_from=date(2026, 6, 1), trigger="BACKFILL")
    backfill_days = {call[1] for call in client.calls if call[0] == "settle/case"}
    assert "2026-06-01" in backfill_days

    client.calls.clear()
    _run(client)
    normal_days = {call[1] for call in client.calls if call[0] == "settle/case"}
    assert min(normal_days) == "2026-08-03"


def test_backfill_is_split_into_thirty_day_windows(app):
    """긴 백필 구간은 30일 창으로 쪼개 순차로 돈다."""
    client = FakeClient()
    _run(client, backfill_from=date(2026, 6, 4), trigger="BACKFILL")
    daily_windows = [call[1] for call in client.calls if call[0] == "settle/daily"]
    assert daily_windows[0] == "2026-06-04~2026-07-03"
    assert daily_windows[-1].endswith("~2026-09-16")
    assert len(daily_windows) == len(
        settle_sync.split_windows(date(2026, 6, 4), date(2026, 9, 16)))


def test_unknown_trigger_is_rejected_without_any_call(app, narrow_range):
    """알 수 없는 실행 유형은 네이버를 부르기 전에 거절한다."""
    client = FakeClient(daily=[_daily(D1)])
    with pytest.raises(ValueError):
        _run(client, trigger="WHENEVER")
    assert client.calls == []


def test_call_interval_is_respected_between_calls(app, narrow_range):
    """호출 사이에 간격을 둔다(2 RPS 방벽은 워커 동시성 1 하나뿐이다)."""
    waits: list[float] = []
    client = FakeClient(daily=[_daily(D1)], cases={D1: [_case("PO-1")]})
    run_settle_sync(db_session, client, today=TODAY, trigger="SCHEDULE",
                    sleep=waits.append)
    assert waits and set(waits) == {settle_sync.CALL_INTERVAL_SECONDS}
    # 첫 호출 앞에는 대기하지 않는다.
    assert len(waits) == len(client.calls) - 1


# --------------------------------------------------------------------------- #
# 값 변환 단위 계약
# --------------------------------------------------------------------------- #

def test_amount_parsing_keeps_decimal_precision():
    """float 로 떨어뜨리지 않는다 — 이진 부동소수는 합계가 1원씩 어긋난다."""
    assert settle_sync.parse_settle_amount("1250000.55") == Decimal("1250000.55")
    assert settle_sync.parse_settle_amount(-37500) == Decimal("-37500")
    assert settle_sync.parse_settle_amount(None) is None
    assert settle_sync.parse_settle_amount("") is None
    assert settle_sync.parse_settle_amount("없음") is None


def test_date_parsing_returns_date_not_datetime():
    """날짜에 시각을 붙이지 않는다(naive=UTC 규약과 섞이면 하루씩 밀린다)."""
    parsed = settle_sync.parse_settle_date("2026-09-01")
    assert parsed == date(2026, 9, 1) and type(parsed) is date
    assert settle_sync.parse_settle_date("") is None
    assert settle_sync.parse_settle_date("2026-13-99") is None


def test_row_builder_copies_the_element_into_raw_snapshot():
    """원본은 통째로 남는다 — 컬럼은 SQL 이 좁혀야 하는 축의 사본일 뿐이다."""
    element = _case("PO-RAW")
    row = settle_sync.build_row(element, settle_sync.CASE_FIELDS)
    assert row["raw_snapshot"] == element
    element["paySettleAmount"] = "999"
    assert row["raw_snapshot"]["paySettleAmount"] == "1250000", "원본을 참조로 물면 안 된다"
    assert row["product_order_id"] == "PO-RAW"
    assert row["settle_expect_date"] == date(2026, 9, 1)


# --------------------------------------------------------------------------- #
# 러너 · start.sh 배선 (test_naver_auto_dispatch.py 와 같은 방식)
# --------------------------------------------------------------------------- #

def _repo_file(relative: str) -> str:
    import pathlib

    return (pathlib.Path(__file__).resolve().parents[3] / relative).read_text(encoding="utf-8")


def _runner():
    """러너 모듈을 파일 경로로 읽어 온다(scripts/ 는 패키지가 아니다)."""
    import importlib.util
    import pathlib

    path = (pathlib.Path(__file__).resolve().parents[3]
            / "scripts" / "maintenance" / "run_naver_settle_sync.py")
    spec = importlib.util.spec_from_file_location("run_naver_settle_sync", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_window_and_backfill_parsing(app):
    """시각 창·백필 인자를 조용히 기본값으로 흘리지 않는다."""
    from datetime import datetime

    from foms.services.integrations.naver_commerce.client import KST

    runner = _runner()
    at = runner.parse_at("05:30")
    assert runner.in_window(datetime(2026, 9, 2, 5, 30, tzinfo=KST), at, 10)
    assert not runner.in_window(datetime(2026, 9, 2, 5, 29, tzinfo=KST), at, 10)
    assert not runner.in_window(datetime(2026, 9, 2, 5, 40, tzinfo=KST), at, 10)
    for bad in ("05시30", "25:00", "", "05:70"):
        with pytest.raises(ValueError):
            runner.parse_at(bad)
    assert runner.parse_backfill_from("2026-06-04") == date(2026, 6, 4)
    assert runner.parse_backfill_from(None) is None
    with pytest.raises(ValueError):
        runner.parse_backfill_from("2026/06/04")


def test_runner_exposes_expected_cli_flags():
    """수동 점검(--once/--dry-run/--json)과 배선(--loop/--at/--window/--backfill-from)."""
    source = _repo_file("scripts/maintenance/run_naver_settle_sync.py")
    for flag in ("--once", "--dry-run", "--json", "--loop", "--at", "--window",
                 "--backfill-from"):
        assert f'"{flag}"' in source, f"러너에 {flag} 가 없다"


def test_start_sh_gate_is_off_by_default_and_inside_worker_branch():
    """정산 동기화 루프는 WORKER 분기 안에서, 게이트가 1일 때만 뜬다."""
    text = _repo_file("start.sh")
    assert 'if [ "$FOMS_NAVER_SETTLE_SYNC_ENABLED" = "1" ]; then' in text

    marker = 'if [ "$USE_RQ_WORKER" = "1" ]; then'
    separator = chr(10) + "else" + chr(10)
    worker_branch = text.split(marker, 1)[1].split(separator, 1)[0]
    assert "run_naver_settle_sync.py" in worker_branch
    # web(gunicorn) 분기에는 없어야 한다 — 네이버 호출 IP 단일 출구 계약.
    assert "run_naver_settle_sync.py" not in text.split(separator, 1)[1]


def test_start_sh_loop_runs_in_background_with_time_defaults():
    """백그라운드(&)로 띄우고, 시각·창 기본값을 env 로 바꿀 수 있어야 한다."""
    text = _repo_file("start.sh")
    block = text.split("run_naver_settle_sync.py", 1)[1].split("fi", 1)[0]
    assert "--loop" in block and block.rstrip().endswith("&")
    assert "${FOMS_NAVER_SETTLE_SYNC_AT:-05:30}" in block
    assert "${FOMS_NAVER_SETTLE_SYNC_WINDOW_MINUTES:-10}" in block


def test_feature_flag_defaults_to_off(monkeypatch: pytest.MonkeyPatch):
    """기능 스위치 기본값은 꺼짐이다(정기 호출을 당장 멈출 손잡이)."""
    from foms.services.feature_flags import is_naver_settle_sync_enabled

    monkeypatch.delenv("FOMS_NAVER_SETTLE_SYNC_ENABLED", raising=False)
    assert is_naver_settle_sync_enabled() is False
    monkeypatch.setenv("FOMS_NAVER_SETTLE_SYNC_ENABLED", "1")
    assert is_naver_settle_sync_enabled() is True


# --------------------------------------------------------------------------- #
# 큐 · 태스크 배선
# --------------------------------------------------------------------------- #

def test_enqueue_returns_false_without_a_queue(monkeypatch: pytest.MonkeyPatch):
    """큐가 없으면 조용히 성공한 척하지 않는다 — 동기 폴백도 없다(호출 IP 계약)."""
    from foms.services.jobs import queue as queue_mod

    monkeypatch.setattr(queue_mod, "get_rq_queue", lambda: None)
    assert queue_mod.enqueue_naver_settle_sync(actor_user_id=1) is False


def test_enqueue_uses_the_dedupe_job_id(monkeypatch: pytest.MonkeyPatch):
    """중복 enqueue 방지 키로 넣는다 — 연타해도 워커가 같은 구간을 여러 번 훑지 않는다."""
    from foms.services.jobs import queue as queue_mod

    captured: dict = {}

    class FakeQueue:
        connection = object()

        def enqueue(self, path, *args, **kwargs):
            captured["path"] = path
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(queue_mod, "get_rq_queue", lambda: FakeQueue())
    monkeypatch.setattr(queue_mod, "_settle_sync_in_flight", lambda _q: False)
    assert queue_mod.enqueue_naver_settle_sync(7, backfill_from="2026-06-04") is True
    assert captured["path"].endswith("run_naver_settle_sync_task")
    assert captured["args"] == (7, "2026-06-04", False)
    assert captured["kwargs"]["job_id"] == queue_mod._SETTLE_SYNC_JOB_ID

    monkeypatch.setattr(queue_mod, "_settle_sync_in_flight", lambda _q: True)
    assert queue_mod.enqueue_naver_settle_sync(7) is False


def test_task_is_exported_for_the_worker():
    """워커가 문자열 경로로 찾는 태스크가 실제로 있다."""
    from foms.services.jobs import tasks as tasks_mod

    assert "run_naver_settle_sync_task" in tasks_mod.__all__
    assert callable(tasks_mod.run_naver_settle_sync_task)


def test_fixtures_use_the_documented_field_names():
    """픽스처가 문서 원문 필드명을 쓴다 — 이름이 어긋나면 계약이 헛돈다."""
    documented = {name for name, _column, _kind in settle_sync.CASE_FIELDS}
    assert documented <= set(_case("PO-X")), documented - set(_case("PO-X"))
    vat_keys = {name for name, _column, _kind in settle_sync.VAT_DAILY_FIELDS}
    assert vat_keys <= set(_vat_daily("2026-08-03"))
    daily_keys = {name for name, _column, _kind in settle_sync.DAILY_FIELDS}
    assert daily_keys <= set(_daily(D1))
    commission_keys = {name for name, _column, _kind in settle_sync.COMMISSION_FIELDS}
    assert commission_keys <= set(_commission("PO-X"))
    assert copy.deepcopy(_vat_case("2026-08-03", "PO-1")).keys() >= {
        name for name, _column, _kind in settle_sync.VAT_CASE_FIELDS}
