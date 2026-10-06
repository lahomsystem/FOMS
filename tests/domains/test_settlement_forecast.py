"""정산 대시보드 — 예상/실제 매출 · 일반/라홈 비중 · 공통 기간(날짜 범위) 계약.

사용자 결정(2026-10-06):

1. **예상 매출** = 진행 단계와 무관하게 시공일이 들어가 있는 주문 전부의 출고가 합.
2. **실제 매출** = 시공완료(완료 · AS접수 · AS완료) 주문의 출고가 합 — 기존 ``kpi.revenue``.
3. **채널 비중** = 일반 / 라홈. 라홈 = 발주사 이름에 '라홈' + 네이버 주문 전부.
4. **기간 설정** = 모든 정산 탭이 같은 날짜 범위(``date_from``/``date_to``)를 쓴다.

이 스위트가 red 로 잡아야 하는 것:

- 실제 매출이 ``kpi.revenue`` 와 갈리는 것(같은 행·같은 구간이라 항등식이어야 한다).
- 예상 매출이 상태로 걸러져 진행 중 주문이 빠지는 것.
- 날짜가 아닌 시공일('미정')이 예상 매출에 들어가는 것.
- 라홈 판정이 알림톡 브랜드 판정(``resolve_brand``)과 갈리는 것.
- 달 단위 날짜 범위가 월 파라미터 결과와 달라지는 것(이번 달 화면이 예전과 달라진다).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.kakao_alimtalk import resolve_brand
from foms.services.settlement_aggregation import (
    BRAND_GENERAL,
    BRAND_LAHOM,
    MAX_RANGE_DAYS,
    aggregate_settlement,
    brand_channel_of,
    parse_day_range,
)
from foms.services.settlement_rows import list_settlement_rows
from tests.domains.test_auth_finance import _login, _make_user  # noqa: E402
from tests.domains.test_settlement_aggregation import (  # noqa: E402
    _link_channel,
    _money,
    _seed_order,
)

API_URL = "/api/settlement/aggregates"
ROWS_URL = "/api/settlement/rows"


def _with_orderer(sd: dict, name: str) -> dict:
    """structured_data 조각에 발주사 이름을 붙인다."""
    payload = dict(sd)
    payload["parties"] = {"orderer": {"name": name}}
    return payload


def _brands(result: dict) -> dict[str, dict]:
    return {item["channel"]: item for item in result["brand_channels"]}


# ==========================================================================
# 1. 예상 vs 실제
# ==========================================================================
def test_expected_counts_every_stage_with_a_construction_date(app):
    """진행 중 주문도 시공일이 있으면 예상에 든다. 실제는 시공완료만이다."""
    _seed_order(completion="2026-07-10", sd=_money(1_000_000))
    _seed_order(completion="2026-07-11", sd=_money(400_000), status="MEASURE", stage="MEASURE")
    _seed_order(completion="2026-07-12", sd=_money(300_000), status="DRAWING", stage="DRAWING")
    _seed_order(completion="2026-07-13", sd=_money(200_000), status="AS_RECEIVED", stage="MEASURE")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )
    forecast = result["forecast"]

    assert forecast["expected_revenue"] == 1_900_000
    assert forecast["expected_count"] == 4
    assert forecast["actual_revenue"] == 1_200_000
    assert forecast["actual_count"] == 2


def test_actual_revenue_is_identical_to_kpi_revenue(app):
    """실제 매출은 기존 기간 매출과 같은 숫자다(모집단·구간이 같다)."""
    _seed_order(completion="2026-07-02", sd=_money(700_000))
    _seed_order(completion="2026-07-20", sd=_money(None))          # 출고가 미산출
    _seed_order(completion="2026-06-30", sd=_money(900_000))       # 구간 밖
    _seed_order(completion="2026-07-05", sd=_money(500_000), status="PRODUCTION",
                stage="PRODUCTION")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="day"
    )

    assert result["forecast"]["actual_revenue"] == result["kpi"]["revenue"] == 700_000
    assert result["forecast"]["actual_count"] == result["kpi"]["completed_count"] == 2
    actual_by_bucket = [b["actual"] for b in result["forecast"]["buckets"]]
    revenue_by_bucket = [b["revenue"] for b in result["buckets"]]
    assert actual_by_bucket == revenue_by_bucket


def test_actual_never_exceeds_expected_per_bucket(app):
    """실제 모집단은 예상 모집단의 부분집합이다 — 버킷마다 실제 ≤ 예상."""
    _seed_order(completion="2026-07-01", sd=_money(100_000))
    _seed_order(completion="2026-07-01", sd=_money(50_000), status="MEASURE", stage="MEASURE")
    _seed_order(completion="2026-07-15", sd=_money(80_000), status="AS_COMPLETED",
                stage="AS_COMPLETED")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="week"
    )

    for bucket in result["forecast"]["buckets"]:
        assert bucket["actual"] <= bucket["expected"]
        assert bucket["actual_count"] <= bucket["expected_count"]


def test_non_date_construction_value_is_not_expected_revenue(app):
    """'미정'·'10월(' 처럼 날짜가 아닌 시공일은 어느 구간에도 들지 않는다."""
    _seed_order(completion="미정", sd=_money(800_000), status="DRAWING", stage="DRAWING")
    _seed_order(completion="10월(", sd=_money(800_000), status="MEASURE", stage="MEASURE")
    _seed_order(completion="2026-07-09", sd=_money(100_000), status="DRAWING", stage="DRAWING")

    result = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="month"
    )

    assert result["forecast"]["expected_count"] == 1
    assert result["forecast"]["expected_revenue"] == 100_000


def test_unpriced_expected_order_counts_but_adds_zero(app):
    """출고가를 아직 못 낸 주문은 건수에만 들고 금액은 0 으로 든다(따로 센다)."""
    _seed_order(completion="2026-07-09", sd=_money(None), status="MEASURE", stage="MEASURE")
    _seed_order(completion="2026-07-09", sd=_money(300_000), status="MEASURE", stage="MEASURE")

    forecast = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07"
    )["forecast"]

    assert forecast["expected_count"] == 2
    assert forecast["expected_revenue"] == 300_000
    assert forecast["expected_unpriced_count"] == 1


def test_draft_and_deleted_orders_stay_out_of_expected(app):
    """살아 있는 ERP 주문만 — 삭제·비ERP 주문은 예상에도 없다."""
    _seed_order(completion="2026-07-09", sd=_money(100_000), status="MEASURE", stage="MEASURE",
                deleted_at="2026-07-10 00:00:00")
    _seed_order(completion="2026-07-09", sd=_money(100_000), status="MEASURE", stage="MEASURE",
                is_erp_order=False)

    forecast = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07"
    )["forecast"]

    assert forecast["expected_count"] == 0


def test_forecast_prev_totals_follow_the_previous_span(app):
    """직전 구간 합계가 KPI 증감 비교의 기준이다."""
    _seed_order(completion="2026-06-10", sd=_money(600_000))
    _seed_order(completion="2026-06-11", sd=_money(100_000), status="MEASURE", stage="MEASURE")

    prev = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07"
    )["forecast"]["prev"]

    assert prev == {
        "expected_revenue": 700_000, "expected_count": 2,
        "actual_revenue": 600_000, "actual_count": 1,
    }


# ==========================================================================
# 2. 일반 / 라홈
# ==========================================================================
def test_brand_split_lahom_orderer_and_naver_go_to_lahom(app):
    """발주사 '라홈' 과 네이버 주문은 라홈, 그 밖은 일반."""
    _seed_order(completion="2026-07-03", sd=_with_orderer(_money(1_000_000), "라홈"))
    _seed_order(completion="2026-07-03", sd=_with_orderer(_money(300_000), "하우드"))
    _seed_order(completion="2026-07-03", sd=_with_orderer(_money(200_000), "숨고"),
                status="MEASURE", stage="MEASURE")
    naver = _seed_order(completion="2026-07-04", sd=_with_orderer(_money(500_000), "개인"))
    _link_channel(naver, channel="NAVER", external_id="PO-BRAND-1")

    brands = _brands(aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07"
    ))

    assert [b for b in brands] == [BRAND_GENERAL, BRAND_LAHOM]
    assert brands[BRAND_LAHOM]["label"] == "라홈"
    assert brands[BRAND_LAHOM]["actual_revenue"] == 1_500_000
    assert brands[BRAND_LAHOM]["actual_count"] == 2
    assert brands[BRAND_GENERAL]["label"] == "일반"
    assert brands[BRAND_GENERAL]["actual_revenue"] == 300_000
    assert brands[BRAND_GENERAL]["expected_revenue"] == 500_000
    assert brands[BRAND_GENERAL]["expected_count"] == 2
    # 라홈 칸 안의 네이버 몫(shop in shop) — 칸 합계에 이미 들어 있는 부분값이다.
    assert brands[BRAND_LAHOM]["naver_actual_revenue"] == 500_000
    assert brands[BRAND_LAHOM]["naver_actual_count"] == 1
    assert brands[BRAND_LAHOM]["naver_expected_revenue"] == 500_000
    assert brands[BRAND_GENERAL]["naver_expected_revenue"] == 0


def test_naver_share_inside_lahom_never_exceeds_lahom(app):
    """네이버 몫은 라홈 칸의 부분집합이다 — 예상·실제 모두 라홈 합계 이하."""
    done = _seed_order(completion="2026-07-04", sd=_with_orderer(_money(500_000), "라홈"))
    _link_channel(done, channel="NAVER", external_id="PO-BRAND-2")
    pending = _seed_order(completion="2026-07-20", sd=_with_orderer(_money(200_000), "라홈"),
                          status="PRODUCTION", stage="PRODUCTION")
    _link_channel(pending, channel="NAVER", external_id="PO-BRAND-3")
    _seed_order(completion="2026-07-05", sd=_with_orderer(_money(900_000), "라홈"))

    lahom = _brands(aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07"
    ))[BRAND_LAHOM]

    assert lahom["naver_expected_revenue"] == 700_000
    assert lahom["naver_expected_count"] == 2
    assert lahom["naver_actual_revenue"] == 500_000
    assert lahom["naver_actual_revenue"] <= lahom["actual_revenue"] == 1_400_000
    assert lahom["naver_expected_revenue"] <= lahom["expected_revenue"] == 1_600_000


def test_brand_channels_always_has_both_rows(app):
    """데이터가 없어도 두 칸을 낸다(화면이 빈 칸을 그릴 자리를 잃지 않게)."""
    result = aggregate_settlement(db_session, month_from="2026-07", month_to="2026-07")

    assert [b["channel"] for b in result["brand_channels"]] == [BRAND_GENERAL, BRAND_LAHOM]
    assert all(b["expected_revenue"] == 0 for b in result["brand_channels"])


def test_brand_totals_add_up_to_forecast_totals(app):
    """두 칸의 합 = 예상·실제 합계(빠지는 주문이 없다)."""
    _seed_order(completion="2026-07-03", sd=_with_orderer(_money(1_000_000), "라홈"))
    _seed_order(completion="2026-07-03", sd=_money(300_000))      # 발주사 없음 → 일반
    _seed_order(completion="2026-07-08", sd=_with_orderer(_money(70_000), "라홈 강남"),
                status="CONFIRM", stage="CONFIRM")

    result = aggregate_settlement(db_session, month_from="2026-07", month_to="2026-07")
    brands, forecast = result["brand_channels"], result["forecast"]

    assert sum(b["expected_revenue"] for b in brands) == forecast["expected_revenue"]
    assert sum(b["actual_revenue"] for b in brands) == forecast["actual_revenue"]
    assert sum(b["expected_count"] for b in brands) == forecast["expected_count"]


@pytest.mark.parametrize("name", ["라홈", "라홈 시스템", "(주)라홈", "하우드", "숨고", "", None])
def test_brand_rule_matches_alimtalk_brand_rule_for_non_naver(name):
    """네이버가 아닌 주문의 라홈 판정은 알림톡 브랜드 판정과 같다(규칙 이중화 방지)."""
    sd = {"parties": {"orderer": {"name": name}}}
    expected = BRAND_LAHOM if resolve_brand(sd) == "LAHOM" else BRAND_GENERAL
    assert brand_channel_of(sd, "일반") == expected


def test_naver_is_lahom_even_without_lahom_orderer():
    assert brand_channel_of({"parties": {"orderer": {"name": "개인"}}}, "NAVER") == BRAND_LAHOM
    assert brand_channel_of(None, "NAVER") == BRAND_LAHOM


# ==========================================================================
# 3. 날짜 범위
# ==========================================================================
def test_whole_month_date_range_equals_month_params(app):
    """'이번 달' 날짜 범위(1일~말일)는 월 파라미터와 결과가 같다(전월 비교선 포함)."""
    _seed_order(completion="2026-07-02", sd=_money(700_000))
    _seed_order(completion="2026-06-15", sd=_money(300_000))
    _seed_order(completion="2026-07-20", sd=_money(90_000), status="MEASURE", stage="MEASURE")

    by_month = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-07", granularity="day"
    )
    by_date = aggregate_settlement(
        db_session, date_from="2026-07-01", date_to="2026-07-31", granularity="day"
    )

    assert by_date == by_month


def test_partial_range_filters_days_and_compares_equal_length_span(app):
    """달 중간 구간은 그 날짜만 보고, 직전 비교는 같은 일수의 바로 앞 구간이다."""
    _seed_order(completion="2026-07-09", sd=_money(100_000))       # 구간 밖(앞)
    _seed_order(completion="2026-07-10", sd=_money(200_000))       # 구간 안
    _seed_order(completion="2026-07-16", sd=_money(400_000))       # 구간 안
    _seed_order(completion="2026-07-17", sd=_money(800_000))       # 구간 밖(뒤)
    _seed_order(completion="2026-07-03", sd=_money(50_000))        # 직전 구간 안

    result = aggregate_settlement(
        db_session, date_from="2026-07-10", date_to="2026-07-16", granularity="day"
    )

    assert result["kpi"]["revenue"] == 600_000
    assert [b["key"] for b in result["buckets"]][0] == "2026-07-10"
    assert len(result["buckets"]) == 7
    assert result["range"]["prev_date_from"] == "2026-07-03"
    assert result["range"]["prev_date_to"] == "2026-07-09"
    assert result["prev_totals"]["revenue"] == 150_000


def test_year_crossing_month_labels_carry_the_year(app):
    """해를 넘는 구간의 월 라벨에는 연도가 붙는다("1월"이 두 번 나오지 않게)."""
    result = aggregate_settlement(
        db_session, date_from="2025-11-01", date_to="2026-02-28", granularity="month"
    )

    assert [b["label"] for b in result["buckets"]] == ["25년 11월", "25년 12월", "26년 1월", "26년 2월"]


def test_full_year_range_is_allowed():
    start, end = parse_day_range("2028-01-01", "2028-12-31")   # 윤년 366일
    assert (end - start).days + 1 == MAX_RANGE_DAYS


@pytest.mark.parametrize(
    "date_from,date_to",
    [
        ("2026-07-1", "2026-07-31"),       # zero-pad 없음
        ("2026-02-30", "2026-03-01"),      # 달력에 없는 날
        ("2026-07-31", "2026-07-01"),      # 역전
        ("2026-01-01", "2027-01-02"),      # 366일 초과
        ("2026-07-01", None),              # 한쪽만
    ],
)
def test_bad_date_ranges_raise(app, date_from, date_to):
    with pytest.raises(ValueError):
        aggregate_settlement(db_session, date_from=date_from, date_to=date_to)


def test_api_accepts_date_range_and_rejects_half_range(client, app):
    _seed_order(completion="2026-07-12", sd=_money(500_000))
    _login(client, _make_user(role="ADMIN"))

    ok = client.get(f"{API_URL}?date_from=2026-07-10&date_to=2026-07-20&granularity=day")
    half = client.get(f"{API_URL}?date_from=2026-07-10&granularity=day")

    assert ok.status_code == 200, ok.get_data(as_text=True)[:300]
    data = ok.get_json()["data"]
    assert data["range"]["date_from"] == "2026-07-10"
    assert data["forecast"]["actual_revenue"] == 500_000
    assert half.status_code == 400
    assert half.get_json()["success"] is False


def test_rows_date_range_keeps_only_orders_built_in_that_span(app):
    """실무 탭도 같은 기간 바를 따른다 — 시공일이 구간 안인 행만, 시공일 미상은 빠진다."""
    inside = _seed_order(completion="2026-07-12", sd=_money(500_000), customer_name="안쪽")
    _seed_order(completion="2026-08-02", sd=_money(500_000), customer_name="바깥")
    _seed_order(completion=None, sd=_money(500_000), customer_name="미상")

    data = list_settlement_rows(db_session, date_from="2026-07-01", date_to="2026-07-31")
    unfiltered = list_settlement_rows(db_session)

    assert [row["order_id"] for row in data["rows"]] == [inside.id]
    assert data["filters"]["date_from"] == "2026-07-01"
    assert unfiltered["total_count"] == 3


def test_rows_api_rejects_bad_date_range(client, app):
    _login(client, _make_user(role="ADMIN"))

    response = client.get(f"{ROWS_URL}?date_from=2026-07-31&date_to=2026-07-01")

    assert response.status_code == 400
