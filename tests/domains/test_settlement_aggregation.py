"""정산 대시보드 집계 서비스 계약 테스트 (SETTLE-DASH-01 M1).

`foms/services/settlement_aggregation.py` 의 계약을 코드로 못박는다. 이 스위트가
red 로 잡아야 하는 것:

1. **모집단 이탈** — 대상 상태 3종 밖 주문·soft delete·ERP draft 가 섞이거나,
   `is_erp_order=False` 주문이 새어 들어오는 것(완료 대시보드와 파리티가 깨진다).
2. **200건 캡 회귀** — 완료 대시보드 로더(`_COMPLETION_BROWSE_LIMIT=200`)를 재사용하면
   201번째 주문부터 매출이 조용히 증발한다. 이 서비스의 존재 이유가 그 캡을 안 타는 것이다.
3. **금액 SSOT 이탈** — 출고가/예약금/잔금/과입금을 새 식으로 다시 짜면 같은 주문의 금액이
   화면마다 갈린다. 완료 대시보드 `_completion_row` 를 **직접 import 해서** 대조한다.
4. **이중 계상** — `schedule.construction.date` 는 콤마 조인 복수 날짜를 담는다.
   한 주문이 두 달 버킷에 들어가면 매출이 부풀려진다.
5. **암묵 drop** — 완료일이 없거나 비-ISO 인 주문(운영 11.7%)을 조용히 버리면
   합계가 어디에도 안 잡힌다. `unknown_completion` 으로 분리돼야 한다.

테스트 데이터 규율: 존재하지 않는 FK id 를 쓰지 않는다(SQLite 는 FK 를 강제하지 않아
로컬만 통과하고 PG 레인에서 터진다). 링크 행은 실제 Order 를 만들고 그 id 를 쓴다.
"""

from __future__ import annotations

import copy
import datetime

import pytest

from db import db_session
from foms.api.cs.dashboard import SETTLEMENT_DEPARTMENTS
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.erp_policy_constants import (
    ORDER_SETTLEMENT_ALERT_TARGET_STATUSES,
    STAGE_LABELS,
)
from foms.services.settlement_aggregation import (
    aggregate_settlement,
    aging_bucket,
    completion_day_key,
    completion_month_key,
    week_key,
)
from foms.web.cs.completion_dashboard import (
    SETTLEMENT_DEPARTMENT_OPTIONS,
    _completion_month_key,
    _completion_row,
    _format_krw,
)
from models import ExternalOrderLink, Order

# aging 5버킷 고정 순서(브리프 §3).
AGING_BUCKET_ORDER = ("LE7", "D8_30", "D31_60", "D61_90", "D91_PLUS")

# 완료 대시보드가 None 금액에 쓰는 표기. 파리티 역파싱 기준.
_KRW_NONE = _format_krw(None)


# --- 시드 헬퍼 ------------------------------------------------------------


def _seed_order(
    *,
    completion: str | None = None,
    sd: dict | None = None,
    status: str = "COMPLETED",
    stage: str | None = "COMPLETED",
    is_erp_order: bool = True,
    deleted_at: str | None = None,
    customer_name: str = "정산고객",
    manager_name: str | None = "담당자",
    as_axis_status: str | None = None,
    commit: bool = True,
) -> Order:
    """정산 모집단 주문 1건을 시드한다.

    Args:
        completion: `schedule.construction.date` 에 넣을 완료일 원문. None 이면 키 자체를
            만들지 않는다(완료일 미상 케이스).
        sd: 금액·정산 blob 등 나머지 structured_data 조각(deepcopy 해서 쓴다).
        status: Order.status.
        stage: Order.erp_stage_code. 기본은 완료 계열이라 §4.4 단계 모집단에서 빠진다.
        is_erp_order: ERP 주문 플래그. False 면 모집단에서 제외돼야 한다(D4).
        deleted_at: soft delete 표식.
        customer_name: 표시용 이름.
        manager_name: Order.manager_name 컬럼값(담당자 집계 fallback 축).
        as_axis_status: AS 축 투영값. None 이면 `before_insert` 훅이 status 에서 유도한다
            (AS 계열 status 가 아니면 그대로 None). AS 축은 있는데 status 는 완료로
            덮인 2026-08-14 사고형 행을 만들려면 명시로 준다 — 훅이 명시값을 존중한다.
        commit: False 면 호출자가 모아서 commit 한다(대량 시드용).

    Returns:
        생성된 Order.
    """
    payload = copy.deepcopy(sd) if sd else {}
    if completion is not None:
        schedule = dict(payload.get("schedule") or {})
        construction = dict(schedule.get("construction") or {})
        construction["date"] = completion
        schedule["construction"] = construction
        payload["schedule"] = schedule
    order = Order(
        received_date="2026-01-01",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울시 강남구",
        product="붙박이장",
        status=status,
        manager_name=manager_name,
        is_erp_order=is_erp_order,
        erp_stage_code=stage,
        deleted_at=deleted_at,
        as_axis_status=as_axis_status,
        structured_data=payload,
    )
    db_session.add(order)
    if commit:
        db_session.commit()
    return order


def _link_channel(order: Order, *, channel: str = "NAVER", external_id: str = "EXT-1") -> ExternalOrderLink:
    """실제 Order 행에 외부 채널 링크를 건다(가짜 FK id 금지 규율).

    Args:
        order: 이미 commit 된 Order.
        channel: 채널 코드.
        external_id: 채널 상품주문 id. `UNIQUE(channel, external_id)` 라 호출마다 달라야 한다.

    Returns:
        생성된 ExternalOrderLink.
    """
    link = ExternalOrderLink(channel=channel, external_id=external_id, order_id=order.id)
    db_session.add(link)
    db_session.commit()
    return link


def _money(items_total: int | None = None, deposit: int | None = None) -> dict:
    """출고가/예약금만 있는 최소 structured_data 를 만든다."""
    payload: dict = {}
    if items_total is not None:
        payload["totals"] = {"items_total": items_total}
    if deposit is not None:
        payload["payment"] = {"deposit": deposit}
    return payload


def _unformat_krw(text: str) -> int | None:
    """`_format_krw` 의 역함수 — 완료 대시보드 표시 문자열을 정수로 되돌린다."""
    if text == _KRW_NONE:
        return None
    return int(str(text).replace(",", ""))


def _row_overpaid(row: dict) -> int:
    """완료 대시보드 행에서 과입금 정수를 뽑는다(0 이면 빈 문자열로 나온다)."""
    text = row.get("overpaid_display") or ""
    return 0 if not text else int(_unformat_krw(text) or 0)


def _by_key(items: list[dict], key: str) -> dict[str, dict]:
    """리스트 응답을 코드 키 기준 dict 로 뒤집는다(순서 무관 조회용)."""
    return {item[key]: item for item in items}


def _bucket_keys(buckets: list[dict]) -> list[str]:
    """버킷 리스트의 key 순서 목록."""
    return [bucket["key"] for bucket in buckets]


def _this_month() -> str:
    """KST 오늘이 속한 월("YYYY-MM") — 기간 무관 지표 테스트의 기본 범위."""
    today = get_today_kst()
    return f"{today.year:04d}-{today.month:02d}"


def _days_ago(days: int) -> str:
    """KST 오늘 기준 N일 전 날짜("YYYY-MM-DD").

    `get_today_kst()` 는 이미 `date` 를 돌려준다 — `.date()` 를 부르면 AttributeError.
    """
    return (get_today_kst() - datetime.timedelta(days=days)).isoformat()


# --- 반환 스키마 ----------------------------------------------------------


def test_returns_exact_schema_keys(app):
    """브리프 §3 이 못박은 키 집합을 정확히 낸다(키 추가·누락 모두 red).

    분석(analytics) 탭이 추가한 키까지 여기서 못박는다:

    - ``managers``/``managers_total`` — 담당자별 매출 순위표. 화면이 KPI 와 나란히
      그리므로 합계가 `kpi` 와 어긋나면 안 된다(별도 항등 테스트가 잠근다).
    - ``prev_totals`` — 직전 구간 스칼라. `prev_buckets` 는 시계열이라 "직전 구간 총
      수금" 같은 값을 낼 수 없어 스칼라를 따로 낸다.
    - ``kpi.collected_deposit``/``collected_balance`` — 기존 `collected_approx` 를
      구성 두 항으로 쪼갠 것(합은 그대로 `collected_approx`).
    - ``settlement_status.as_total_count``/``as_billing_free_count``/
      ``as_billing_undecided_count`` — AS 청구 판정 분포. 유상 확정 1개 숫자만으로는
      "아직 안 정한 AS 가 몇 건인가"를 볼 수 없었다.

    `==` 를 `<=`/`issubset` 으로 낮추지 않는다 — 키가 조용히 늘어나는 것을 잡는 게
    이 단언의 존재 이유다.
    """
    _seed_order(completion="2026-07-15", sd=_money(1000000, 300000))
    _seed_order(completion="2026-07-16", sd=_money(500000, 0), status="AS_RECEIVED",
                stage="MEASURE")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="day"
    )

    assert set(result) == {
        "range", "kpi", "buckets", "prev_buckets", "prev_totals", "aging",
        "aging_unknown", "channels", "managers", "managers_total",
        "settlement_status", "stages", "unknown_completion",
    }
    assert result["range"] == {
        "month_from": "2026-07", "month_to": "2026-07", "granularity": "day",
    }
    assert set(result["kpi"]) == {
        "revenue", "completed_count", "avg_shipping_price", "receivable_total",
        "receivable_count", "collected_approx", "collected_deposit",
        "collected_balance", "overpaid_total",
    }
    assert set(result["prev_totals"]) == {
        "revenue", "completed_count", "avg_shipping_price", "collected_deposit",
        "collected_balance", "collected_approx", "overpaid_total", "deduction_total",
    }
    assert set(result["managers_total"]) == {"count", "revenue"}
    for item in result["managers"]:
        assert set(item) == {"manager", "count", "revenue"}
    for bucket in result["buckets"] + result["prev_buckets"]:
        assert set(bucket) == {"key", "label", "revenue", "count"}
        assert isinstance(bucket["label"], str) and bucket["label"]
    assert [item["bucket"] for item in result["aging"]] == list(AGING_BUCKET_ORDER)
    for item in result["aging"]:
        assert set(item) == {"bucket", "label", "count", "amount"}
    assert set(result["aging_unknown"]) == {"count", "amount"}
    assert set(result["unknown_completion"]) == {"count", "amount"}
    assert result["channels"], "채널 집계가 비어 있으면 안 된다(링크 없는 건도 '일반')"
    for item in result["channels"]:
        assert set(item) == {"channel", "count", "revenue"}
    assert set(result["settlement_status"]) == {
        "issued_count", "pending_count", "cash_receipt_requested", "cash_receipt_issued",
        "as_total_count", "as_billing_paid_count", "as_billing_paid_amount",
        "as_billing_free_count", "as_billing_undecided_count", "deductions_by_department",
    }
    for item in result["settlement_status"]["deductions_by_department"]:
        assert set(item) == {"department", "label", "amount", "count"}
    assert result["stages"], "완료 계열이 아닌 stage 주문이 있으면 stages 가 비면 안 된다"
    for item in result["stages"]:
        assert set(item) == {"stage", "label", "count", "amount"}


# --- 계약 1: 모집단 술어 --------------------------------------------------


def test_population_includes_only_target_statuses(app):
    """대상 상태 3종만 집계된다 — 신규 상수 없이 정책 SSOT 를 그대로 쓴다."""
    assert ORDER_SETTLEMENT_ALERT_TARGET_STATUSES == ("COMPLETED", "AS_RECEIVED", "AS_COMPLETED")

    _seed_order(completion="2026-07-10", sd=_money(100000, 0), status="COMPLETED")
    _seed_order(completion="2026-07-11", sd=_money(200000, 0), status="AS_RECEIVED")
    _seed_order(completion="2026-07-12", sd=_money(300000, 0), status="AS_COMPLETED")
    for other in ("PRODUCTION", "CS", "RECEIVED", "CONSTRUCTION"):
        _seed_order(completion="2026-07-13", sd=_money(9000000, 0), status=other,
                    stage="MEASURE")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["completed_count"] == 3
    assert result["kpi"]["revenue"] == 600000


def test_population_excludes_soft_deleted_and_erp_draft(app):
    """`Order.active_filter()` 준수 — soft delete·ERP draft(status/meta.draft) 제외."""
    _seed_order(completion="2026-07-10", sd=_money(100000, 0))
    _seed_order(completion="2026-07-10", sd=_money(9000000, 0),
                deleted_at="2026-07-20 00:00:00")
    _seed_order(completion="2026-07-10", sd={"totals": {"items_total": 9000000},
                                             "meta": {"draft": True}})
    _seed_order(completion="2026-07-10", sd=_money(9000000, 0), status="DRAFT")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["completed_count"] == 1
    assert result["kpi"]["revenue"] == 100000


def test_population_excludes_non_erp_orders(app):
    """D4 — `is_erp_order=False` 는 제외된다.

    `active_filter()` 는 ERP draft 만 잘라내므로 비-ERP 주문은 **그 필터를 통과한다**.
    `Order.is_erp_order.is_(True)` 를 빼면 완료 대시보드 베이스 쿼리와 파리티가 깨지고
    비-ERP 주문이 매출로 잡힌다.
    """
    _seed_order(completion="2026-07-10", sd=_money(100000, 0), is_erp_order=True)
    _seed_order(completion="2026-07-10", sd=_money(9000000, 0), is_erp_order=False)
    _seed_order(completion="2026-07-10", status="AS_COMPLETED", is_erp_order=False,
                sd={"totals": {"items_total": 9000000}, "meta": {"draft": True}})

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["completed_count"] == 1
    assert result["kpi"]["revenue"] == 100000


# --- 계약 2: 200건 캡 무관성 ----------------------------------------------


def test_aggregate_is_not_capped_at_200_rows(app):
    """201건 시드에서 전량이 집계된다 — 완료 대시보드 200건 캡 회귀 방지선."""
    total = 0
    for index in range(201):
        price = 100000 + index
        total += price
        _seed_order(
            completion=f"2026-07-{(index % 28) + 1:02d}",
            sd=_money(price, 0),
            customer_name=f"고객{index}",
            commit=False,
        )
    db_session.commit()

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["completed_count"] == 201
    assert result["kpi"]["revenue"] == total
    assert sum(bucket["count"] for bucket in result["buckets"]) == 201
    assert sum(bucket["revenue"] for bucket in result["buckets"]) == total


# --- 계약 3: 금액 파리티 (완료 대시보드 SSOT) -----------------------------


_PARITY_SAMPLES = [
    pytest.param(
        {"totals": {"items_total": 1000000}, "payment": {"deposit": 300000}},
        1000000, 300000, 700000, 0,
        id="normal",
    ),
    pytest.param(
        {"payment": {"deposit": 100000}},
        None, 100000, None, 0,
        id="shipping_price_none",
    ),
    pytest.param(
        {"totals": {"items_total": 0}, "payment": {"deposit": 500000}},
        0, 500000, 0, 0,
        id="deposit_only_zero_items",
    ),
    pytest.param(
        {"totals": {"items_total": 200000}, "payment": {"deposit": 500000}},
        200000, 500000, 0, 300000,
        id="overpaid_clamped_balance",
    ),
    pytest.param(
        {
            "totals": {"items_total": 1000000, "free_input_amount": 50000},
            "payment": {"deposit": 200000, "discount": 30000},
        },
        1020000, 200000, 820000, 0,
        id="free_input_and_discount",
    ),
    pytest.param(
        {
            "totals": {"items_total": 900000},
            "payments": {"deposit": 400000},
            "payment": {"balance_confirmed": False},
        },
        900000, 400000, 500000, 0,
        id="legacy_payments_deposit",
    ),
]


@pytest.mark.parametrize(
    "sd,expected_shipping,expected_deposit,expected_balance,expected_overpaid",
    _PARITY_SAMPLES,
)
def test_amounts_match_completion_dashboard_row(
    app, sd, expected_shipping, expected_deposit, expected_balance, expected_overpaid
):
    """출고가·예약금·잔금·과입금이 `_completion_row` 와 비트 단위로 같다.

    두 겹으로 잠근다:
    1) 완료 대시보드 행 자체가 스펙 값을 내는지(파리티 기준선이 먼저 흔들리는 것 방지).
    2) 커널이 같은 값을 내는지.

    `free_input_and_discount` 표본은 잔금에 discount 를 3번째 인자로 또 넣는 이중 차감
    (820,000 → 790,000)을, `overpaid_clamped_balance`/`deposit_only_zero_items` 표본은
    과입금 클램프 규칙(총액 0 이하는 과입금 아님)을 red 로 잡는다.
    """
    order = _seed_order(completion="2026-07-15", sd=sd)
    row = _completion_row(order)

    assert _unformat_krw(row["shipping_price_display"]) == expected_shipping
    assert _unformat_krw(row["deposit_display"]) == expected_deposit
    assert row["balance_amount"] == expected_balance
    assert _row_overpaid(row) == expected_overpaid

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )
    kpi = result["kpi"]
    assert kpi["completed_count"] == 1
    assert kpi["revenue"] == (expected_shipping or 0)
    assert kpi["collected_approx"] == (expected_deposit or 0)
    assert kpi["overpaid_total"] == expected_overpaid

    unpaid = (
        not row["paid"]
        and isinstance(expected_balance, int)
        and expected_balance > 0
    )
    assert kpi["receivable_total"] == (expected_balance if unpaid else 0)
    assert kpi["receivable_count"] == (1 if unpaid else 0)


def test_avg_shipping_price_is_revenue_over_count(app):
    """평균 출고가 = revenue // completed_count."""
    _seed_order(completion="2026-07-10", sd=_money(1000000, 0))
    _seed_order(completion="2026-07-11", sd=_money(1000001, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["revenue"] == 2000001
    assert result["kpi"]["completed_count"] == 2
    assert result["kpi"]["avg_shipping_price"] == 1000000


def test_avg_shipping_price_is_zero_when_no_orders(app):
    """0건이면 평균은 0 — ZeroDivisionError 로 죽지 않는다."""
    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["completed_count"] == 0
    assert result["kpi"]["revenue"] == 0
    assert result["kpi"]["avg_shipping_price"] == 0


def test_collected_approx_adds_confirmed_balance(app):
    """당월 수금 근사 = 기간 내 예약금 합 + balance_confirmed 건의 잔금 합."""
    _seed_order(
        completion="2026-07-10",
        sd={
            "totals": {"items_total": 1000000},
            "payment": {"deposit": 300000, "balance_confirmed": True},
        },
    )
    _seed_order(
        completion="2026-07-11",
        sd={"totals": {"items_total": 500000}, "payment": {"deposit": 100000}},
    )

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    # 300,000 + 700,000(확인된 잔금) + 100,000 = 1,100,000
    assert result["kpi"]["collected_approx"] == 1100000


# --- 계약 4: 이중 계상 방지 -----------------------------------------------


def test_completion_month_key_matches_completion_dashboard(app):
    """`completion_month_key` 가 완료 대시보드 `_completion_month_key` 와 같은 값을 낸다."""
    samples = [
        "2026-07-30",
        "2026-07-30, 2026-08-02",
        "2026-07-30,2026-08-02",
        "2026-07",
        "  2026-07-30  ",
        "",
        "미정",
        "20260730",
        None,
        1234,
    ]
    for value in samples:
        assert completion_month_key(value) == _completion_month_key(value), value


def test_multi_date_completion_lands_in_exactly_one_month_bucket(app):
    """콤마 복수 완료일(두 달 걸침)은 **첫 날짜의 월** 1개 버킷에만 귀속된다."""
    _seed_order(completion="2026-07-30, 2026-08-02", sd=_money(1000000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-08", granularity="month"
    )

    buckets = _by_key(result["buckets"], "key")
    assert _bucket_keys(result["buckets"]) == ["2026-07", "2026-08"]
    assert buckets["2026-07"]["count"] == 1
    assert buckets["2026-07"]["revenue"] == 1000000
    assert buckets["2026-08"]["count"] == 0
    assert buckets["2026-08"]["revenue"] == 0
    assert result["kpi"]["completed_count"] == 1
    assert result["kpi"]["revenue"] == 1000000


def test_multi_date_completion_day_bucket_uses_first_date(app):
    """일 버킷도 첫 날짜에만 귀속된다(두 날짜에 각각 세면 건수가 부푼다)."""
    assert completion_day_key("2026-07-30, 2026-08-02") == "2026-07-30"
    assert completion_day_key("2026-07-30") == "2026-07-30"
    assert completion_day_key("") == ""
    assert completion_day_key("미정") == ""
    assert completion_day_key("2026-07") == ""
    assert completion_day_key(None) == ""

    _seed_order(completion="2026-07-30, 2026-08-02", sd=_money(1000000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="day"
    )

    buckets = _by_key(result["buckets"], "key")
    assert buckets["2026-07-30"]["count"] == 1
    assert sum(bucket["count"] for bucket in result["buckets"]) == 1


# --- 계약 5: 완료일 미상 분리 ---------------------------------------------


def test_unknown_completion_is_separated_not_dropped(app):
    """완료일 없음/빈 문자열/비-ISO 는 기간 버킷 밖 `unknown_completion` 으로 잡힌다."""
    _seed_order(completion="2026-07-10", sd=_money(1000000, 0))
    _seed_order(completion=None, sd=_money(100000, 0))
    _seed_order(completion="", sd=_money(200000, 0))
    _seed_order(completion="미정", sd=_money(300000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["unknown_completion"]["count"] == 3
    assert result["unknown_completion"]["amount"] == 600000
    assert result["kpi"]["completed_count"] == 1
    assert result["kpi"]["revenue"] == 1000000
    assert sum(bucket["count"] for bucket in result["buckets"]) == 1


# --- 계약 6: 미수 판정 ----------------------------------------------------


def test_receivable_matches_completion_dashboard_paid_predicate(app):
    """미수 판정은 완료 대시보드와 같은 **truthiness** 규칙이다.

    `balance_confirmed` 저장값은 bool 로 강제되지 않는다. `"Y"` 같은 truthy 비-bool 을
    `is not True` 로 판정하면 이미 받은 돈이 미수로 잡힌다.
    """
    paid_true = _seed_order(completion="2026-07-10", sd={
        "totals": {"items_total": 1000000},
        "payment": {"deposit": 100000, "balance_confirmed": True},
    })
    paid_truthy_string = _seed_order(completion="2026-07-11", sd={
        "totals": {"items_total": 1000000},
        "payment": {"deposit": 100000, "balance_confirmed": "Y"},
    })
    unpaid_false = _seed_order(completion="2026-07-12", sd={
        "totals": {"items_total": 1000000},
        "payment": {"deposit": 100000, "balance_confirmed": False},
    })
    unpaid_missing = _seed_order(completion="2026-07-13", sd={
        "totals": {"items_total": 1000000},
        "payment": {"deposit": 100000},
    })

    # 파리티 기준선: 완료 대시보드가 앞 둘을 '받음'으로 본다.
    assert _completion_row(paid_true)["paid"] is True
    assert _completion_row(paid_truthy_string)["paid"] is True
    assert _completion_row(unpaid_false)["paid"] is False
    assert _completion_row(unpaid_missing)["paid"] is False

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["receivable_count"] == 2
    assert result["kpi"]["receivable_total"] == 1800000


def test_receivable_excludes_zero_and_clamped_balance(app):
    """잔금 0·클램프로 0 이 된 건(과입금)·출고가 None 은 미수가 아니다."""
    _seed_order(completion="2026-07-10", sd=_money(500000, 500000))   # 잔금 0
    _seed_order(completion="2026-07-11", sd=_money(200000, 500000))   # 클램프 후 0
    _seed_order(completion="2026-07-12", sd=_money(None, 100000))     # 출고가 None
    _seed_order(completion="2026-07-13", sd=_money(1000000, 100000))  # 미수 900,000

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["receivable_count"] == 1
    assert result["kpi"]["receivable_total"] == 900000
    assert result["kpi"]["overpaid_total"] == 300000


def test_receivable_is_period_independent(app):
    """미수는 기간 무관 지표 — 조회 기간 밖 완료건도 합산된다."""
    _seed_order(completion="2026-02-10", sd=_money(1000000, 100000))
    _seed_order(completion="2026-07-10", sd=_money(1000000, 100000))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["kpi"]["completed_count"] == 1
    assert result["kpi"]["receivable_count"] == 2
    assert result["kpi"]["receivable_total"] == 1800000


# --- 계약 7: aging 버킷 경계 ----------------------------------------------


@pytest.mark.parametrize(
    "days,expected",
    [
        (0, "LE7"),
        (7, "LE7"),
        (8, "D8_30"),
        (30, "D8_30"),
        (31, "D31_60"),
        (60, "D31_60"),
        (61, "D61_90"),
        (90, "D61_90"),
        (91, "D91_PLUS"),
        (365, "D91_PLUS"),
    ],
)
def test_aging_bucket_boundaries(days, expected):
    """경계 전수 — off-by-one 이 버킷을 통째로 옆으로 민다."""
    assert aging_bucket(days) == expected


def test_aging_bucket_future_completion_is_le7():
    """완료일이 미래(경과일 음수)여도 5버킷 밖으로 새지 않는다."""
    assert aging_bucket(-1) == "LE7"
    assert aging_bucket(-30) == "LE7"


def test_aging_distributes_receivables_by_days_since_completion(app):
    """미수건이 (오늘 KST − 완료일) 경과일로 5버킷에 정확히 나뉜다."""
    for days in (7, 8, 30, 31, 60, 61, 90, 91):
        _seed_order(completion=_days_ago(days), sd=_money(1000000, 100000),
                    customer_name=f"미수{days}")

    result = aggregate_settlement(
        db_session,
        month_from=_this_month(),
        month_to=_this_month(),
        granularity="month",
    )

    aging = _by_key(result["aging"], "bucket")
    assert [item["bucket"] for item in result["aging"]] == list(AGING_BUCKET_ORDER)
    assert aging["LE7"]["count"] == 1
    assert aging["D8_30"]["count"] == 2
    assert aging["D31_60"]["count"] == 2
    assert aging["D61_90"]["count"] == 2
    assert aging["D91_PLUS"]["count"] == 1
    assert aging["LE7"]["amount"] == 900000
    assert aging["D8_30"]["amount"] == 1800000
    assert aging["D31_60"]["amount"] == 1800000
    assert aging["D61_90"]["amount"] == 1800000
    assert aging["D91_PLUS"]["amount"] == 900000
    assert result["aging_unknown"] == {"count": 0, "amount": 0}
    assert sum(item["count"] for item in result["aging"]) == result["kpi"]["receivable_count"]


def test_aging_unknown_holds_receivables_without_completion_date(app):
    """완료일 미상 미수건은 버킷이 아니라 `aging_unknown` 으로 간다(암묵 drop 금지)."""
    _seed_order(completion=_days_ago(10), sd=_money(1000000, 100000))
    _seed_order(completion=None, sd=_money(1000000, 100000))
    _seed_order(completion="미정", sd=_money(1000000, 100000))

    result = aggregate_settlement(
        db_session,
        month_from=_this_month(),
        month_to=_this_month(),
        granularity="month",
    )

    assert result["aging_unknown"]["count"] == 2
    assert result["aging_unknown"]["amount"] == 1800000
    assert sum(item["count"] for item in result["aging"]) == 1
    assert result["kpi"]["receivable_count"] == 3
    assert result["kpi"]["receivable_total"] == 2700000


# --- 계약 8: 채널 LEFT JOIN ----------------------------------------------


def test_channel_defaults_to_general_when_no_link(app):
    """링크 0건이어도 정상 동작하고 전부 '일반' 으로 잡힌다."""
    _seed_order(completion="2026-07-10", sd=_money(100000, 0))
    _seed_order(completion="2026-07-11", sd=_money(200000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    channels = _by_key(result["channels"], "channel")
    assert channels["일반"]["count"] == 2
    assert channels["일반"]["revenue"] == 300000
    assert channels.get("NAVER", {"count": 0})["count"] == 0


def test_channel_uses_external_order_link_channel(app):
    """링크가 있으면 그 channel 로 귀속된다."""
    linked = _seed_order(completion="2026-07-10", sd=_money(700000, 0))
    _link_channel(linked, channel="NAVER", external_id="PO-1")
    _seed_order(completion="2026-07-11", sd=_money(300000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    channels = _by_key(result["channels"], "channel")
    assert channels["NAVER"]["count"] == 1
    assert channels["NAVER"]["revenue"] == 700000
    assert channels["일반"]["count"] == 1
    assert channels["일반"]["revenue"] == 300000


def test_multiple_links_on_one_order_do_not_double_count(app):
    """한 주문에 링크가 여럿(ADDON/REPAY)이어도 LEFT JOIN fan-out 으로 두 번 세지 않는다."""
    order = _seed_order(completion="2026-07-10", sd=_money(700000, 100000))
    _link_channel(order, channel="NAVER", external_id="PO-A")
    _link_channel(order, channel="NAVER", external_id="PO-B")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    channels = _by_key(result["channels"], "channel")
    assert channels["NAVER"]["count"] == 1
    assert channels["NAVER"]["revenue"] == 700000
    assert result["kpi"]["completed_count"] == 1
    assert result["kpi"]["revenue"] == 700000
    assert result["kpi"]["receivable_total"] == 600000


# --- 계약 9: 주 버킷 경계 -------------------------------------------------


def test_week_key_month_starting_monday():
    """2026-06-01 은 월요일 — 1~7일이 W1, 8일부터 W2, 29~30일이 W5."""
    assert datetime.date(2026, 6, 1).weekday() == 0
    assert week_key("2026-06-01") == "2026-06-W1"
    assert week_key("2026-06-07") == "2026-06-W1"
    assert week_key("2026-06-08") == "2026-06-W2"
    assert week_key("2026-06-29") == "2026-06-W5"
    assert week_key("2026-06-30") == "2026-06-W5"


def test_week_key_month_starting_sunday():
    """2026-03-01 은 일요일 — 1일 홀로 W1, 2일(월)부터 W2."""
    assert datetime.date(2026, 3, 1).weekday() == 6
    assert week_key("2026-03-01") == "2026-03-W1"
    assert week_key("2026-03-02") == "2026-03-W2"
    assert week_key("2026-03-08") == "2026-03-W2"
    assert week_key("2026-03-09") == "2026-03-W3"


def test_week_key_last_week_of_31_day_month():
    """31일 달의 마지막 주 — 2026-03(1일 일요일)은 W6, 2026-08(1일 토요일)도 W6."""
    assert week_key("2026-03-31") == "2026-03-W6"
    assert datetime.date(2026, 8, 1).weekday() == 5
    assert week_key("2026-08-01") == "2026-08-W1"
    assert week_key("2026-08-02") == "2026-08-W1"
    assert week_key("2026-08-03") == "2026-08-W2"
    assert week_key("2026-08-30") == "2026-08-W5"
    assert week_key("2026-08-31") == "2026-08-W6"


def test_week_key_rejects_non_iso_day_key():
    """일 키가 아니면 빈 문자열(예외로 집계를 죽이지 않는다)."""
    assert week_key("") == ""
    assert week_key("미정") == ""
    assert week_key("2026-06") == ""


def test_week_granularity_buckets_cover_whole_month(app):
    """주 granularity 는 그 달의 주를 빠짐없이 채운다(빈 주도 0)."""
    _seed_order(completion="2026-06-08", sd=_money(400000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-06", month_to="2026-06", granularity="week"
    )

    assert _bucket_keys(result["buckets"]) == [
        "2026-06-W1", "2026-06-W2", "2026-06-W3", "2026-06-W4", "2026-06-W5",
    ]
    buckets = _by_key(result["buckets"], "key")
    assert buckets["2026-06-W2"]["count"] == 1
    assert buckets["2026-06-W2"]["revenue"] == 400000
    assert buckets["2026-06-W1"]["count"] == 0
    assert buckets["2026-06-W5"]["revenue"] == 0


def test_day_granularity_fills_empty_days_with_zero(app):
    """일 granularity 는 그 달 전 일자를 0으로 채운다."""
    _seed_order(completion="2026-07-15", sd=_money(500000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="day"
    )

    keys = _bucket_keys(result["buckets"])
    assert len(keys) == 31
    assert keys[0] == "2026-07-01"
    assert keys[-1] == "2026-07-31"
    buckets = _by_key(result["buckets"], "key")
    assert buckets["2026-07-15"]["count"] == 1
    assert buckets["2026-07-01"]["count"] == 0
    assert buckets["2026-07-01"]["revenue"] == 0


def test_prev_buckets_cover_the_immediately_preceding_window(app):
    """`prev_buckets` = 요청 범위 직전의 동일 개월수 구간."""
    _seed_order(completion="2026-05-10", sd=_money(500000, 0))
    _seed_order(completion="2026-07-10", sd=_money(700000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-08", granularity="month"
    )

    assert _bucket_keys(result["buckets"]) == ["2026-07", "2026-08"]
    assert _bucket_keys(result["prev_buckets"]) == ["2026-05", "2026-06"]
    prev = _by_key(result["prev_buckets"], "key")
    assert prev["2026-05"]["count"] == 1
    assert prev["2026-05"]["revenue"] == 500000
    assert prev["2026-06"]["count"] == 0
    # 기간 KPI 는 요청 범위만 센다(직전 구간이 새어 들어오면 안 된다).
    assert result["kpi"]["completed_count"] == 1
    assert result["kpi"]["revenue"] == 700000


# --- 계약 10: 파라미터 검증 -----------------------------------------------


@pytest.mark.parametrize(
    "month_from,month_to",
    [
        ("2026-7", "2026-08"),
        ("202607", "2026-08"),
        ("2026-07", "2026-8"),
        ("2026-07", "20260808"),
        ("", "2026-08"),
        ("2026-07", ""),
        ("2026-07-01", "2026-08-01"),
    ],
)
def test_invalid_month_format_raises(app, month_from, month_to):
    """`^\\d{4}-\\d{2}$` 아닌 월 파라미터는 ValueError."""
    with pytest.raises(ValueError):
        aggregate_settlement(db_session, month_from=month_from, month_to=month_to)


def test_reversed_range_raises(app):
    """범위 역전은 ValueError."""
    with pytest.raises(ValueError):
        aggregate_settlement(db_session, month_from="2026-08", month_to="2026-07")


def test_range_over_twelve_months_raises(app):
    """12개월 초과는 ValueError(§4.2 성능 가드). 정확히 12개월은 허용."""
    with pytest.raises(ValueError):
        aggregate_settlement(db_session, month_from="2026-01", month_to="2027-01")

    ok = aggregate_settlement(db_session, month_from="2026-01", month_to="2026-12",
                              granularity="month")
    assert len(ok["buckets"]) == 12


@pytest.mark.parametrize("granularity", ["", "hour", "year", "DAY", "weekly", None])
def test_invalid_granularity_raises(app, granularity):
    """`day|week|month` 밖의 granularity 는 ValueError."""
    with pytest.raises(ValueError):
        aggregate_settlement(
            db_session, month_from="2026-07", month_to="2026-07", granularity=granularity
        )


def test_single_month_range_is_allowed(app):
    """같은 월 from==to 는 정상(경계 역전으로 오판하면 안 된다)."""
    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )
    assert _bucket_keys(result["buckets"]) == ["2026-07"]


# --- 계약 11: 단계별 물린 금액 --------------------------------------------


def test_stages_exclude_completed_stage_codes(app):
    """완료 계열 stage(COMPLETED/AS_COMPLETED)와 stage 미지정은 제외된다."""
    _seed_order(completion=None, sd=_money(100000, 0), status="PRODUCTION", stage="MEASURE")
    _seed_order(completion=None, sd=_money(200000, 0), status="DRAWING", stage="DRAWING")
    _seed_order(completion="2026-07-10", sd=_money(9000000, 0), status="COMPLETED",
                stage="COMPLETED")
    _seed_order(completion="2026-07-10", sd=_money(9000000, 0), status="AS_COMPLETED",
                stage="AS_COMPLETED")
    _seed_order(completion=None, sd=_money(9000000, 0), status="RECEIVED", stage=None)
    _seed_order(completion=None, sd=_money(9000000, 0), status="PRODUCTION", stage="MEASURE",
                is_erp_order=False)

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    stages = _by_key(result["stages"], "stage")
    assert stages["MEASURE"]["count"] == 1
    assert stages["MEASURE"]["amount"] == 100000
    assert stages["DRAWING"]["count"] == 1
    assert stages["DRAWING"]["amount"] == 200000
    assert stages.get("COMPLETED", {"count": 0})["count"] == 0
    assert stages.get("AS_COMPLETED", {"count": 0})["count"] == 0
    assert sum(item["count"] for item in result["stages"]) == 2


def test_stage_labels_come_from_policy_constants(app):
    """라벨은 `STAGE_LABELS` SSOT 기준 — 목업의 '해피콜' 라벨을 복제하지 않는다."""
    _seed_order(completion=None, sd=_money(100000, 0), status="PRODUCTION", stage="MEASURE")
    _seed_order(completion=None, sd=_money(200000, 0), status="DRAWING", stage="DRAWING")
    _seed_order(completion=None, sd=_money(300000, 0), status="PRODUCTION", stage="PRODUCTION")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    labels = {item["label"] for item in result["stages"]}
    assert "해피콜" not in labels
    for item in result["stages"]:
        if item["stage"] in STAGE_LABELS:
            assert item["label"] == STAGE_LABELS[item["stage"]]
    stages = _by_key(result["stages"], "stage")
    assert stages["MEASURE"]["label"] == "실측"
    assert stages["DRAWING"]["label"] == "도면"
    assert stages["PRODUCTION"]["label"] == "생산"


def test_stages_are_outside_the_period_scope(app):
    """단계 카드는 현재 시점 스냅샷 — 조회 기간과 무관하게 잡힌다."""
    _seed_order(completion="2020-01-01", sd=_money(100000, 0), status="PRODUCTION",
                stage="MEASURE")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    stages = _by_key(result["stages"], "stage")
    assert stages["MEASURE"]["count"] == 1


# --- 계약 12: 정산 현황 ---------------------------------------------------


def test_empty_deductions_list_counts_as_pending(app):
    """`deductions: []` 는 falsy — '청구완료' 가 아니라 '대기'다."""
    _seed_order(completion="2026-07-10", sd={
        "totals": {"items_total": 100000},
        "settlement": {"deductions": []},
    })
    _seed_order(completion="2026-07-11", sd=_money(100000, 0))
    _seed_order(completion="2026-07-12", sd={
        "totals": {"items_total": 100000},
        "settlement": {"deductions": [{"department": "SALES", "amount": -50000}]},
    })

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    status = result["settlement_status"]
    assert status["issued_count"] == 1
    assert status["pending_count"] == 2


def test_deductions_by_department_are_positive_sums(app):
    """부서별 차감은 저장된 음수를 **절대값(양수)** 으로 합산한다."""
    _seed_order(completion="2026-07-10", sd={
        "totals": {"items_total": 1000000},
        "settlement": {"deductions": [
            {"department": "SALES", "amount": -50000},
            {"department": "SALES", "amount": -20000},
            {"department": "DRAWING", "amount": -10000},
        ]},
    })

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    by_dept = result["settlement_status"]["deductions_by_department"]
    assert [item["department"] for item in by_dept] == list(SETTLEMENT_DEPARTMENTS)
    assert [item["label"] for item in by_dept] == [label for _code, label in SETTLEMENT_DEPARTMENT_OPTIONS]
    assert all(item["amount"] >= 0 for item in by_dept)
    dept = _by_key(by_dept, "department")
    assert dept["SALES"]["amount"] == 70000
    assert dept["SALES"]["count"] == 2
    assert dept["DRAWING"]["amount"] == 10000
    assert dept["DRAWING"]["count"] == 1
    assert dept["PRODUCTION"]["amount"] == 0
    assert dept["PRODUCTION"]["count"] == 0
    assert dept["CONSTRUCTION"]["amount"] == 0
    assert dept["CUSTOMER"]["amount"] == 0


def test_cash_receipt_priority_issued_over_requested(app):
    """현금영수증 우선순위 issued > requested > none — 발행건은 요청으로 중복 계상하지 않는다."""
    _seed_order(completion="2026-07-10", sd={
        "totals": {"items_total": 100000},
        "payment": {"cash_receipt": "현금영수증 010-1111-2222"},
        "settlement": {"cash_receipt": {"issued": True}},
    })
    _seed_order(completion="2026-07-11", sd={
        "totals": {"items_total": 100000},
        "payment": {"cash_receipt": "010-2222-3333"},
    })
    _seed_order(completion="2026-07-12", sd={
        "totals": {"items_total": 100000},
        "payment": {"cash_receipt": "   "},
    })
    _seed_order(completion="2026-07-13", sd=_money(100000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    status = result["settlement_status"]
    assert status["cash_receipt_issued"] == 1
    assert status["cash_receipt_requested"] == 1


def test_as_billing_requires_strict_confirmed_true(app):
    """AS 유상은 `type=='paid'` **and** `confirmed is True`(엄격) 일 때만 잡힌다.

    미수 판정(truthiness)과 달리 여기는 엄격 비교다. `"Y"` 를 확정으로 받으면
    AS 대시보드 배지(`paid_unconfirmed`)와 정산 금액이 어긋난다.
    """
    _seed_order(completion="2026-07-10", sd={
        "totals": {"items_total": 100000},
        "shipment": {"as_billing": {"type": "paid", "confirmed": True, "amount": 150000}},
    }, status="AS_COMPLETED")
    _seed_order(completion="2026-07-11", sd={
        "totals": {"items_total": 100000},
        "shipment": {"as_billing": {"type": "paid", "confirmed": "Y", "amount": 999999}},
    }, status="AS_COMPLETED")
    _seed_order(completion="2026-07-12", sd={
        "totals": {"items_total": 100000},
        "shipment": {"as_billing": {"type": "paid", "confirmed": False, "amount": 300000}},
    }, status="AS_COMPLETED")
    _seed_order(completion="2026-07-13", sd={
        "totals": {"items_total": 100000},
        "shipment": {"as_billing": {"type": "free", "confirmed": True, "amount": 50000}},
    }, status="AS_COMPLETED")
    _seed_order(completion="2026-07-14", sd={
        "totals": {"items_total": 100000},
        "shipment": {"as_billing": {"type": "undecided", "confirmed": True, "amount": 70000}},
    }, status="AS_COMPLETED")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    status = result["settlement_status"]
    assert status["as_billing_paid_count"] == 1
    assert status["as_billing_paid_amount"] == 150000


# --- 계약 13: 담당자별 매출 -----------------------------------------------


def _manager_sd(name: str, items_total: int) -> dict:
    """`parties.manager.name` 이 실린 structured_data(담당자 파생 1순위 축)."""
    return {"totals": {"items_total": items_total}, "parties": {"manager": {"name": name}}}


def test_manager_derivation_prefers_structured_parties_over_column(app):
    """담당자 표시명은 `sd.parties.manager.name` → `Order.manager_name` → "-" 순이다.

    이웃 표면(`foms/api/cs/dashboard.py` 완료 카드 직렬화)이 이미 이 순서로 그린다.
    순서를 뒤집으면 같은 주문의 담당자가 카드와 집계에서 갈린다.
    """
    _seed_order(completion="2026-07-10", sd=_manager_sd("김성훈", 100000),
                manager_name="컬럼담당")
    _seed_order(completion="2026-07-11", sd=_money(200000, 0), manager_name="컬럼담당")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    managers = _by_key(result["managers"], "manager")
    assert set(managers) == {"김성훈", "컬럼담당"}
    assert managers["김성훈"]["count"] == 1
    assert managers["김성훈"]["revenue"] == 100000
    assert managers["컬럼담당"]["count"] == 1


def test_manager_grouping_folds_case_and_whitespace(app):
    """대소문자·앞뒤 공백만 다른 표기는 한 행으로 접힌다.

    접지 않으면 같은 담당자가 순위표에서 여러 줄로 쪼개져 1등 매출이 실제보다 작아진다.
    표기는 **가장 흔한 원본 철자**를 쓴다("Kim" 2회 > "kim" 1회 → "Kim").
    """
    for index, raw in enumerate(("Kim", " Kim ", "kim")):
        _seed_order(completion=f"2026-07-1{index}", sd=_money(100000, 0),
                    manager_name=raw, customer_name=f"고객{index}")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert len(result["managers"]) == 1
    assert result["managers"][0] == {"manager": "Kim", "count": 3, "revenue": 300000}


def test_manager_unassigned_bucket_is_last_and_not_dropped(app):
    """담당자 미상(빈 값·"-")은 `(미지정)` 한 행으로 모이고 **항상 마지막**이다.

    매출이 1등이어도 마지막이다 — 순위 정렬에 섞으면 "1등 담당자"가 사람이 아닌 빈칸이
    된다. 그렇다고 버리지도 않는다(암묵 drop 금지 — 버리면 합계가 KPI 와 갈린다).
    """
    _seed_order(completion="2026-07-10", sd=_money(9000000, 0), manager_name=None)
    _seed_order(completion="2026-07-11", sd=_money(1000000, 0), manager_name="-")
    _seed_order(completion="2026-07-12", sd=_money(500000, 0), manager_name="   ")
    _seed_order(completion="2026-07-13", sd=_money(300000, 0), manager_name="박영희")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert [item["manager"] for item in result["managers"]] == ["박영희", "(미지정)"]
    assert result["managers"][-1]["count"] == 3
    assert result["managers"][-1]["revenue"] == 10500000


def test_managers_are_ordered_by_revenue_desc(app):
    """순위표는 매출 내림차순이다(건수 순이 아니다)."""
    _seed_order(completion="2026-07-10", sd=_money(100000, 0), manager_name="적은매출")
    _seed_order(completion="2026-07-11", sd=_money(100000, 0), manager_name="적은매출")
    _seed_order(completion="2026-07-12", sd=_money(100000, 0), manager_name="적은매출")
    _seed_order(completion="2026-07-13", sd=_money(900000, 0), manager_name="큰매출")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert [item["manager"] for item in result["managers"]] == ["큰매출", "적은매출"]
    assert [item["revenue"] for item in result["managers"]] == [900000, 300000]


def test_managers_total_equals_kpi_revenue_and_count(app):
    """항등식 — `sum(count) == kpi.completed_count`, `sum(revenue) == kpi.revenue`.

    화면이 KPI 카드와 담당자 순위표를 나란히 그린다. 한 행이라도 새면(미지정 drop·
    출고가 None 건 제외) 두 숫자가 눈앞에서 어긋난다. 출고가 미산출 건은 매출에 0 을
    기여하되 **건수에는 남아야** 한다.
    """
    _seed_order(completion="2026-07-10", sd=_manager_sd("김성훈", 1000000))
    _seed_order(completion="2026-07-11", sd=_money(500000, 0), manager_name="박영희")
    _seed_order(completion="2026-07-12", sd=_money(None, 100000), manager_name="박영희")
    _seed_order(completion="2026-07-13", sd=_money(300000, 0), manager_name=None)
    _seed_order(completion="2026-07-14", sd=_money(200000, 0), manager_name="Kim")
    _seed_order(completion="2026-07-15", sd=_money(200000, 0), manager_name=" kim ")
    # 기간 밖 — 담당자 합계에도 KPI 에도 들어오면 안 된다.
    _seed_order(completion="2026-02-10", sd=_money(9000000, 0), manager_name="김성훈")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    kpi, total = result["kpi"], result["managers_total"]
    assert sum(item["count"] for item in result["managers"]) == kpi["completed_count"]
    assert sum(item["revenue"] for item in result["managers"]) == kpi["revenue"]
    assert total == {"count": kpi["completed_count"], "revenue": kpi["revenue"]}
    assert total == {"count": 6, "revenue": 2200000}
    managers = _by_key(result["managers"], "manager")
    assert managers["박영희"]["count"] == 2
    assert managers["박영희"]["revenue"] == 500000
    assert managers["Kim"]["count"] == 2


def test_managers_are_empty_when_period_has_no_rows(app):
    """기간에 건이 없으면 순위표는 비고 합계는 0 이다(가짜 `(미지정)` 0행 금지)."""
    _seed_order(completion="2026-02-10", sd=_money(9000000, 0), manager_name="김성훈")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["managers"] == []
    assert result["managers_total"] == {"count": 0, "revenue": 0}


# --- 계약 14: 수금 분해 ---------------------------------------------------


def test_collected_split_sums_to_collected_approx(app):
    """항등식 — `collected_deposit + collected_balance == collected_approx`.

    분석 탭이 수금을 '예약금/잔금' 두 막대로 쪼개 그린다. 두 항을 화면이 따로 더하게
    두면 총액이 KPI 와 갈린다. 커널이 세 값을 한 곳에서 낸다.
    """
    _seed_order(completion="2026-07-10", sd={
        "totals": {"items_total": 1000000},
        "payment": {"deposit": 300000, "balance_confirmed": True},
    })
    _seed_order(completion="2026-07-11", sd={
        "totals": {"items_total": 500000}, "payment": {"deposit": 100000},
    })

    kpi = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )["kpi"]

    assert kpi["collected_deposit"] == 400000
    assert kpi["collected_balance"] == 700000
    assert kpi["collected_approx"] == 1100000
    assert kpi["collected_deposit"] + kpi["collected_balance"] == kpi["collected_approx"]


def test_collected_balance_only_counts_confirmed_balances(app):
    """잔금 항은 `balance_confirmed` 건만 센다 — 미수는 수금이 아니다."""
    _seed_order(completion="2026-07-10", sd={
        "totals": {"items_total": 1000000},
        "payment": {"deposit": 200000, "balance_confirmed": False},
    })

    kpi = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )["kpi"]

    assert kpi["collected_deposit"] == 200000
    assert kpi["collected_balance"] == 0
    assert kpi["collected_approx"] == 200000
    assert kpi["receivable_total"] == 800000


# --- 계약 15: AS 청구 분포 -------------------------------------------------


def _as_sd(billing: dict | None, items_total: int = 100000) -> dict:
    """AS 청구 blob 이 실린 structured_data. billing=None 이면 shipment 자체가 없다."""
    payload: dict = {"totals": {"items_total": items_total}}
    if billing is not None:
        payload["shipment"] = {"as_billing": billing}
    return payload


def _as_counts(result: dict) -> tuple[int, int, int, int]:
    """(총건, 유상확정, 무상, 미확정) 튜플 — 분할 항등식 단언용."""
    status = result["settlement_status"]
    return (
        status["as_total_count"],
        status["as_billing_paid_count"],
        status["as_billing_free_count"],
        status["as_billing_undecided_count"],
    )


def test_as_breakdown_partitions_the_as_population(app):
    """분할 항등식 — 유상확정 + 무상 + 미확정 == `as_total_count`.

    4분류 SSOT(`as_billing_badge_kind`)의 'paid'/'paid_unconfirmed'/'undecided'/None 을
    3버킷으로 접는다. 어느 갈래도 어디에도 안 잡히면 화면의 도넛 합이 총건과 안 맞는다.
    """
    _seed_order(completion="2026-07-10", status="AS_COMPLETED", sd=_as_sd(
        {"type": "paid", "confirmed": True, "amount": 150000}))
    _seed_order(completion="2026-07-11", status="AS_COMPLETED", sd=_as_sd(
        {"type": "paid", "confirmed": "Y", "amount": 999999}))
    _seed_order(completion="2026-07-12", status="AS_COMPLETED", sd=_as_sd(
        {"type": "paid", "confirmed": False, "amount": 300000}))
    _seed_order(completion="2026-07-13", status="AS_COMPLETED", sd=_as_sd(
        {"type": "undecided"}))
    _seed_order(completion="2026-07-14", status="AS_COMPLETED", sd=_as_sd(
        {"type": "free", "confirmed": True}))
    _seed_order(completion="2026-07-15", status="AS_RECEIVED", sd=_as_sd(None))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    total, paid, free, undecided = _as_counts(result)
    assert (total, paid, free, undecided) == (6, 1, 2, 3)
    assert paid + free + undecided == total
    assert result["settlement_status"]["as_billing_paid_amount"] == 150000


def test_as_population_uses_as_axis_status_not_legacy_status(app):
    """AS 모집단은 `as_axis_status IS NOT NULL`(AS-AXIS-01) — status 술어가 아니다.

    `status in ('AS_RECEIVED','AS_COMPLETED')` 는 2026-08-14 사고로 폐기됐다. status 는
    overlay projection 이라 외부 write 한 번에 'COMPLETED' 로 덮이고, 그 순간 AS 건이
    모집단에서 통째로 빠진다. **구 술어가 놓치던 바로 그 행**을 여기서 잡는다.
    """
    _seed_order(completion="2026-07-10", status="COMPLETED", as_axis_status="COMPLETED",
                sd=_as_sd({"type": "undecided"}))
    _seed_order(completion="2026-07-11", status="COMPLETED", as_axis_status="IN_PROGRESS",
                sd=_as_sd({"type": "free"}))
    # AS 축이 없는 순수 완료건 — 분모에 들어오면 안 된다.
    _seed_order(completion="2026-07-12", status="COMPLETED", sd=_money(100000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    total, paid, free, undecided = _as_counts(result)
    assert (total, paid, free, undecided) == (2, 0, 1, 1)
    assert paid + free + undecided == total


def test_as_total_covers_legacy_paid_row_without_axis(app):
    """AS 축이 비었는데 유상 확정만 남은 레거시 행도 분모에 든다(분자 > 분모 방지).

    투영 백필 이전 데이터가 그렇다. 분모에서 빼면 `as_billing_paid_count` 가
    `as_total_count` 를 넘어 화면이 "2건 중 3건 유상" 을 그린다.
    """
    _seed_order(completion="2026-07-10", status="COMPLETED", as_axis_status=None,
                sd=_as_sd({"type": "paid", "confirmed": True, "amount": 50000}))
    _seed_order(completion="2026-07-11", status="AS_COMPLETED", sd=_as_sd({"type": "free"}))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    total, paid, free, undecided = _as_counts(result)
    assert (total, paid, free, undecided) == (2, 1, 1, 0)
    assert paid <= total
    assert paid + free + undecided == total


def test_as_counts_are_zero_without_as_rows(app):
    """AS 축도 유상 청구도 없으면 AS 분포는 전부 0 이다."""
    _seed_order(completion="2026-07-10", sd=_money(100000, 0))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert _as_counts(result) == (0, 0, 0, 0)


def test_as_counts_are_scoped_to_the_requested_period(app):
    """AS 분포도 `channels`/정산현황과 같은 기간 스코프다(기간 밖 AS 는 안 센다)."""
    _seed_order(completion="2026-07-10", status="AS_COMPLETED", sd=_as_sd({"type": "free"}))
    _seed_order(completion="2026-02-10", status="AS_COMPLETED", sd=_as_sd({"type": "free"}))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert _as_counts(result) == (1, 0, 1, 0)


# --- 계약 16: 직전 구간 스칼라 --------------------------------------------


def test_prev_totals_are_scoped_to_the_previous_window(app):
    """`prev_totals` 는 **직전 구간**만 센다(요청 구간이 새어 들어오면 비교가 무의미)."""
    _seed_order(completion="2026-06-10", sd={
        "totals": {"items_total": 500000},
        "payment": {"deposit": 200000, "balance_confirmed": True},
    })
    _seed_order(completion="2026-07-10", sd=_money(900000, 100000))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    prev = result["prev_totals"]
    assert prev["revenue"] == 500000
    assert prev["completed_count"] == 1
    assert prev["avg_shipping_price"] == 500000
    assert prev["collected_deposit"] == 200000
    assert prev["collected_balance"] == 300000
    assert prev["collected_approx"] == 500000
    # 요청 구간 KPI 는 그대로여야 한다(양방향 누수 확인).
    assert result["kpi"]["revenue"] == 900000
    assert result["kpi"]["completed_count"] == 1


def test_prev_totals_match_the_same_range_run_one_window_earlier(app):
    """직전 구간 스칼라 = 그 구간을 **요청 구간으로 돌렸을 때**의 값과 같다.

    스코프와 정의(수금 분해·과입금·차감 범위)를 한 번에 잠근다. 한쪽만 규칙이 바뀌면
    화면이 사과와 오렌지를 비교한다.
    """
    _seed_order(completion="2026-06-10", sd={
        "totals": {"items_total": 1000000},
        "payment": {"deposit": 300000, "balance_confirmed": True},
        "settlement": {"deductions": [{"department": "SALES", "amount": -40000}]},
    })
    _seed_order(completion="2026-06-20", sd=_money(200000, 500000))  # 과입금 300,000
    _seed_order(completion="2026-07-10", sd=_money(900000, 0))

    current = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )
    shifted = aggregate_settlement(
        db_session, month_from="2026-06", month_to="2026-06", granularity="month"
    )

    prev, kpi = current["prev_totals"], shifted["kpi"]
    for key in ("revenue", "completed_count", "avg_shipping_price",
                "collected_deposit", "collected_balance", "collected_approx",
                "overpaid_total"):
        assert prev[key] == kpi[key], key
    assert prev["deduction_total"] == sum(
        item["amount"] for item in shifted["settlement_status"]["deductions_by_department"]
    )
    assert prev["deduction_total"] == 40000
    assert prev["overpaid_total"] == 300000


def test_prev_totals_omit_period_independent_metrics(app):
    """`prev_totals` 에 미수·aging 키를 담지 않는다.

    그 둘은 기간 무관 지표(모집단 전체)라 "직전 구간의 미수" 라는 값이 존재하지 않는다.
    담으면 화면이 없는 비교를 그린다 — 실제로는 같은 숫자를 두 번 보여주게 된다.
    """
    _seed_order(completion="2026-06-10", sd=_money(1000000, 100000))
    _seed_order(completion="2026-07-10", sd=_money(1000000, 100000))

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    prev = result["prev_totals"]
    assert not [key for key in prev if key.startswith("receivable")]
    assert not [key for key in prev if "aging" in key]
    # 미수는 기간 무관이라 KPI 한 곳에만 있고, 두 건 모두를 센다.
    assert result["kpi"]["receivable_count"] == 2
