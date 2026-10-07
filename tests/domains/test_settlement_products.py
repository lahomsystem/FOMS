"""정산 "제품별 매출" 탭 계약 — 분류 규칙·정확 배분·요약 탭과의 항등식·API (2026-10-07).

이 스위트가 red 로 잡아야 하는 것:

1. 분류 규칙 이탈 — 운영 데이터로 검증한 정본 순서(비용 먼저·리폼 원문 판정·무몰딩 먼저·
   수납장은 옷장 낱말 없을 때만·도어 좁은 규칙)가 깨지는 것.
2. 배분 오차 — 제품군 합이 요약 탭 예상 매출(``forecast.expected_revenue``)과, 실제 합이
   ``kpi.revenue`` 와 1원이라도 갈리는 것. 같은 구간·같은 주문이라 항등식이어야 한다.
3. 투영 누락 — 이 탭의 판정이 :data:`PRODUCTS_SD_SPEC` 밖 경로를 읽기 시작하는 것.
4. 권한·형식 이탈 — 정산 대시보드와 다른 게이트, 400/403 형식 불일치.

테스트 데이터 규율: 실제 Order 행을 만들고 링크도 그 id 로 건다(가짜 FK id 금지).
"""
from __future__ import annotations

import copy
import json

import pytest

from db import db_session
from foms.services import settlement_products as sp
from foms.services import settlement_source as ss
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_display import _ensure_dict, erp_shipping_price_from_structured
from foms.services.settlement_aggregation import aggregate_settlement, brand_channel_of
from foms.services.settlement_product_rules import FAMILY_CODES, SERIES_CODES, family, series
from tests.domains.settlement_source_helpers import (
    SHAPES,
    row_for,
    seed_shapes,
    spec_without,
    uncovered_reads,
)
from tests.domains.test_auth_finance import _login, _make_user  # noqa: E402
from tests.domains.test_settlement_aggregation import (  # noqa: E402
    _link_channel,
    _money,
    _seed_order,
)
from tests.services.integrations.naver_list_snapshot_helpers import traced

API_URL = "/api/settlement/products"
FROM, TO = "2026-09-01", "2026-09-30"


def _items(*pairs, **extra) -> dict:
    """(품명, 단가) 쌍으로 품목 문서를 만든다(품목합은 저장하지 않아 단가 합 폴백을 탄다)."""
    sd = {"items": [{"product_name": name, "price": price, "quantity": 3} for name, price in pairs]}
    sd.update(extra)
    return sd


def _seed_mix() -> None:
    """배분·채널·상태 갈래가 한 번씩 걸리는 9월 주문 묶음 + 구간 밖 주문."""
    # 나머지가 생기는 배분(2,000,000 을 1:1:1) + 할인·자유입력이 출고가에 반영된 주문.
    _seed_order(completion="2026-09-03", sd=_items(
        ("로라 무몰딩 여닫이", 1_000_000), ("보테가 슬라이딩", 1_000_000), ("철거비", 1_000_000),
        payment={"discount": "2,000,000", "free_input": "배송: 1,000,000"}))
    # 라홈 발주사 + 진행 중(예상만).
    _seed_order(completion="2026-09-10", status="MEASURE", stage="MEASURE", sd=_items(
        ("아라 무몰딩 붙박이장", 700_000), ("냉장고장(리폼)", 300_000),
        parties={"orderer": {"name": "라홈시스템"}}))
    # 네이버(발주사 없음 — 그래도 라홈) + AS 완료(실제).
    naver = _seed_order(completion="2026-09-12", status="AS_COMPLETED", stage="AS_COMPLETED",
                        sd=_items(("모카 1000 슬라이딩", 333_333), ("수납장", 666_667)))
    _link_channel(naver, channel="NAVER", external_id="PROD-NAVER-1")
    # 품목합이 저장된 주문(단가 합과 달라도 출고가는 품목합) + 단가 0 품목 + 미분류 이름.
    _seed_order(completion="2026-09-15", sd={
        "items": [{"product_name": "  투도어 무몰딩 붙박이장 ", "price": "2,000,000"},
                  {"product_name": "발주방 등록 전", "price": 0},
                  {"product_name": "알수없는물건", "price": 10}],
        "totals": {"items_total": 2_500_000}})
    # 품목 없는 주문 / 단가 합 0 주문 / 출고가 미산출 주문.
    _seed_order(completion="2026-09-20", sd=_money(items_total=400_000))
    _seed_order(completion="2026-09-21", sd=_items(("붙박이장", 0), ("철거", 0),
                                                   totals={"items_total": 90_000}))
    _seed_order(completion="2026-09-22", sd={})
    # 구간 밖(8월) — 추이에는 들고 구간 합계에는 안 든다.
    _seed_order(completion="2026-08-31", sd=_items(("몰딩 여닫이", 5_000_000)))


def _period_sum(data: dict, field: str) -> int:
    return sum(entry[field] for entry in data["period"].values())


# ==========================================================================
# 1. 분류 규칙
# ==========================================================================
@pytest.mark.parametrize("name,expected_family,expected_series", [
    ("로라 무몰딩 여닫이", "NOMOLD_SWING", "LORA"),
    ("보테가 슬라이딩", "SLIDING", "BOTTEGA"),
    ("아라 무몰딩 붙박이장", "NOMOLD_SWING", "ARA"),
    ("냉장고장(리폼)", "REFRIG_REFORM", "BASIC"),
    ("냉장고장", "REFRIG", "BASIC"),
    ("철거비", "EXTRA", "BASIC"),
    ("붙박이장 철거", "EXTRA", "BASIC"),
    ("발주방 등록 전", "PLACEHOLDER", "BASIC"),
    ("외 3건", "PLACEHOLDER", "BASIC"),
    ("", "PLACEHOLDER", "BASIC"),
    (None, "PLACEHOLDER", "BASIC"),
    ("수납장", "STORAGE", "BASIC"),
    ("시스템 붙박이장", "SWING", "BASIC"),
    ("투도어 무몰딩 붙박이장", "NOMOLD_SWING", "BASIC"),
    ("도어 교체", "DOOR", "BASIC"),
    ("공틀", "DOOR", "BASIC"),
    ("모카 1000 슬라이딩", "SLIDING", "MOCHA"),
    ("스와니1200", "SLIDING", "SWANY"),
    ("몰딩 여닫이 120cm", "MOLD_SWING", "BASIC"),
    ("TV월 플렉스", "TV_WALL", "BASIC"),
    ("led 선반장", "STORAGE", "LED"),
    ("알수없는물건", "OTHER", "BASIC"),
])
def test_family_and_series_rules(name, expected_family, expected_series):
    """정본 규칙의 대표 이름 — 순서 의존 갈래(비용·리폼·무몰딩·도어·수납) 포함."""
    assert family(name) == expected_family
    assert series(name) == expected_series


def test_allocate_is_exact_largest_remainder():
    """몫 합이 정확히 총액이고, 남은 원은 나머지 큰 순(같으면 앞)으로 간다."""
    assert sp.allocate(1_000_001, [1, 1, 1]) == [333_334, 333_334, 333_333]
    assert sp.allocate(100, [1, 2]) == [33, 67]
    assert sp.allocate(0, [5, 5]) == [0, 0]
    assert sp.allocate(10, [0, 0]) is None
    for total in (1, 7, 999_999, 12_345_678):
        assert sum(sp.allocate(total, [3, 7, 11, 0, 13])) == total


# ==========================================================================
# 2. 요약 탭과의 항등식·배분
# ==========================================================================
def test_family_sums_equal_summary_forecast_and_kpi(app):
    """Σ 제품군 예상 == forecast.expected_revenue, Σ 실제 == kpi.revenue, 채널·시리즈 합도 같다."""
    _seed_mix()
    data = sp.aggregate_products(db_session, date_from=FROM, date_to=TO)
    summary = aggregate_settlement(db_session, date_from=FROM, date_to=TO, granularity="day")

    expected = summary["forecast"]["expected_revenue"]
    assert expected > 0, "빈 결과끼리 같다는 거짓 통과"
    assert _period_sum(data, "expected") == expected
    assert _period_sum(data, "actual") == summary["kpi"]["revenue"]
    assert data["allocation_check"]["sum_shipping"] == expected
    assert data["allocation_check"]["orders"] == summary["forecast"]["expected_count"] == 7
    lahom = next(b for b in summary["brand_channels"] if b["channel"] == "LAHOM")
    for field in ("expected", "actual"):
        assert sum(e["general"][field] + e["lahom"][field]
                   for e in data["period"].values()) == _period_sum(data, field)
        assert sum(s[field] for e in data["period"].values()
                   for s in e["series"].values()) == _period_sum(data, field)
        assert sum(e["lahom"][field] for e in data["period"].values()) == lahom[f"{field}_revenue"]
        assert (sum(e["naver"][field] for e in data["period"].values())
                == lahom[f"naver_{field}_revenue"])
        for entry in data["period"].values():
            assert entry["naver"][field] <= entry["lahom"][field]


def test_allocation_details_per_family(app):
    """나머지 1원·품목 없는 주문·단가 합 0·품목합 우선이 계약대로 배분된다."""
    _seed_mix()
    period = sp.aggregate_products(db_session, date_from=FROM, date_to=TO)["period"]

    # 1주문: 출고가 = 3,000,000 + 1,000,000 − 2,000,000 = 2,000,000 → 1:1:1 최대 잔여
    # (나머지 2원은 같은 나머지끼리 앞 품목부터).
    assert period["NOMOLD_SWING"]["series"]["LORA"]["expected"] == 666_667
    assert period["SLIDING"]["series"]["BOTTEGA"]["expected"] == 666_667
    # 철거 = 첫 주문 666,666 + 단가 합 0 주문의 둘째 품목(0원).
    assert period["EXTRA"]["expected"] == 666_666
    # 단가 합 0 주문은 첫 품목(붙박이장 → SWING)이 출고가 전액을 진다.
    assert period["SWING"]["expected"] == 90_000
    # 품목 없는 주문(400,000)과 출고가 미산출(0) 주문 → 미입력, 품목 수 0.
    # 품목합 2,500,000 주문의 '발주방 등록 전'(단가 0)은 배분 0 원이지만 품목 수 1.
    assert period["PLACEHOLDER"]["expected"] == 400_000
    assert period["PLACEHOLDER"]["expected_items"] == 1
    assert period["PLACEHOLDER"]["expected_orders"] == 3
    # 품목합 2,500,000 을 2,000,000 : 0 : 10 으로 → OTHER 는 12원(나머지 포함).
    assert period["OTHER"]["expected"] == 2_500_000 - period["NOMOLD_SWING"]["series"]["BASIC"]["expected"]
    assert period["OTHER"]["expected_raw"] == 10
    # 진행 중(MEASURE) 주문은 예상에만 든다.
    assert period["REFRIG_REFORM"]["expected"] == 300_000
    assert period["REFRIG_REFORM"]["actual"] == 0
    assert period["REFRIG_REFORM"]["lahom"]["expected"] == 300_000


def test_series_counts_items_and_naver_sits_inside_lahom(app):
    """시리즈 품목 수는 품목 줄 수(수량 곱 없음), 네이버는 라홈 칸 안의 부분값이다."""
    _seed_mix()
    period = sp.aggregate_products(db_session, date_from=FROM, date_to=TO)["period"]

    assert period["SLIDING"]["series"]["MOCHA"] == {
        "expected": 333_333, "actual": 333_333, "expected_items": 1, "actual_items": 1}
    assert period["SLIDING"]["expected_items"] == 2  # 보테가 + 모카(수량 3 은 곱하지 않는다)
    assert period["SLIDING"]["naver"] == {"expected": 333_333, "actual": 333_333}
    assert period["STORAGE"]["naver"] == period["STORAGE"]["lahom"] == {
        "expected": 666_667, "actual": 666_667}
    assert period["STORAGE"]["general"] == {"expected": 0, "actual": 0}


def test_names_trend_and_coverage(app):
    """대표 품명은 앞뒤 공백만 뗀 원문, 추이는 구간 끝 달로 끝나는 12개월, 미분류 비중."""
    _seed_mix()
    data = sp.aggregate_products(db_session, date_from=FROM, date_to=TO)

    assert ["투도어 무몰딩 붙박이장", 1] in data["top_names"]["NOMOLD_SWING"]
    assert data["unmapped_top"] == [["알수없는물건", 1, 10]]
    assert data["trend"]["months"][0] == "2025-10" and data["trend"]["months"][-1] == "2026-09"
    assert len(data["trend"]["months"]) == 12
    assert data["trend"]["by_month"]["2026-08"]["MOLD_SWING"] == {"expected": 5_000_000,
                                                                  "actual": 5_000_000}
    assert data["period"]["MOLD_SWING"]["expected"] == 0, "구간 밖 주문이 합계에 새었다"
    september = data["trend"]["by_month"]["2026-09"]
    assert sum(cell["expected"] for cell in september.values()) == _period_sum(data, "expected")
    assert data["selected_months"] == ["2026-09"]
    coverage = data["coverage"]
    assert coverage["items_total"] == 12 and coverage["items_other"] == 1
    assert coverage["revenue_other_share"] == round(
        data["period"]["OTHER"]["expected"] / _period_sum(data, "expected"), 5)


def test_empty_range_has_every_key_at_zero(app):
    """주문이 없는 구간도 모든 제품군·시리즈 키가 0 으로 있다."""
    data = sp.aggregate_products(db_session, date_from="2030-01-01", date_to="2030-02-15")

    assert list(data["period"]) == list(FAMILY_CODES)
    assert [f["code"] for f in data["families"]] == list(FAMILY_CODES)
    assert [s["code"] for s in data["series"]] == list(SERIES_CODES)
    assert data["series"][-1] == {"code": "BASIC", "label": "기본"}
    for entry in data["period"].values():
        assert list(entry["series"]) == list(SERIES_CODES)
        assert entry["expected"] == entry["actual"] == entry["expected_orders"] == 0
    assert data["selected_months"] == ["2030-01", "2030-02"]
    assert data["coverage"] == {"items_total": 0, "items_other": 0, "revenue_other_share": 0.0}
    assert data["allocation_check"] == {"orders": 0, "sum_shipping": 0, "sum_raw_items": 0}


def test_default_range_is_this_month_and_one_sided_range_raises(app):
    """날짜가 둘 다 없으면 이번 달(KST), 한쪽만 오면 ValueError."""
    today = get_today_kst()
    data = sp.aggregate_products(db_session)
    assert data["range"]["date_from"] == today.replace(day=1).isoformat()
    assert data["range"]["date_to"][:7] == today.isoformat()[:7]
    with pytest.raises(ValueError):
        sp.aggregate_products(db_session, date_from="2026-09-01")
    with pytest.raises(ValueError):
        sp.aggregate_products(db_session, date_from="2026-09-30", date_to="2026-09-01")


# ==========================================================================
# 3. 투영 — 판정이 읽는 경로 ⊆ PRODUCTS_SD_SPEC, 투영 답 == 통째 원본 답
# ==========================================================================
def _consume(row) -> dict:
    """이 탭의 행 판정 전부(완료일·출고가·채널·품목 줄)."""
    sd = _ensure_dict(row.structured_data)
    day = ((sd.get("schedule") or {}).get("construction") or {}).get("date")
    shipping = erp_shipping_price_from_structured(sd)
    shipping = shipping if isinstance(shipping, int) else 0
    return {"day": day, "brand": brand_channel_of(sd, "일반"),
            "lines": sp._order_lines(sd, shipping)}


def _trace() -> set:
    ops: set = set()
    for sd, attrs in SHAPES.values():
        _consume(row_for(traced(copy.deepcopy(sd), (), ops), attrs))
    return ops


def test_products_reads_only_projected_paths_with_negative_control():
    """읽힌 자리가 전부 투영 안 — 품명 경로를 뺀 투영이면 같은 측정이 짚는다."""
    ops = _trace()
    name_path = ("items", ss.ARRAY_ITEMS, "product_name")
    assert ((name_path, "get") in ops and (("parties", "orderer", "name"), "get") in ops)
    assert not uncovered_reads(ops, sp.PRODUCTS_SD_SPEC)
    assert (name_path, "get") in uncovered_reads(ops, spec_without(sp.PRODUCTS_SD_SPEC, name_path))


def test_projection_answers_equal_full_document(app, monkeypatch):
    """투영 문서로 낸 응답 == 통째 원본으로 낸 응답(음성 대조군: 품명 뺀 투영은 갈린다)."""
    seed_shapes(db_session)
    _seed_mix()

    def run() -> str:
        return json.dumps(sp.aggregate_products(db_session, date_from="2025-10-07",
                                                date_to="2026-10-07"), ensure_ascii=False)

    projected = run()
    monkeypatch.setattr(ss, "project_settlement_sd", lambda raw, spec=None: raw)
    full = run()
    assert projected == full
    dropped = spec_without(sp.PRODUCTS_SD_SPEC, ("items", ss.ARRAY_ITEMS, "product_name"))
    monkeypatch.setattr(ss, "project_settlement_sd", lambda raw, spec=None: ss._project(raw, dropped))
    assert run() != full


# ==========================================================================
# 4. API
# ==========================================================================
def test_api_allowed_actor_gets_contract_envelope(client, app):
    _seed_mix()
    _login(client, _make_user(role="ADMIN", team=None))

    resp = client.get(f"{API_URL}?date_from={FROM}&date_to={TO}")

    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    assert set(body["data"]) == {"range", "families", "series", "period", "trend",
                                 "selected_months", "top_names", "unmapped_top", "coverage",
                                 "allocation_check"}
    assert body["data"]["range"] == {"date_from": FROM, "date_to": TO}
    assert "정산고객" not in json.dumps(body, ensure_ascii=False), "고객명이 집계에 새었다"
    assert client.get(API_URL).status_code == 200, "기본 구간(이번 달)"


@pytest.mark.parametrize("query", ["date_from=2026-09-01", "date_from=2026-13-01&date_to=2026-12-31",
                                   "date_from=2026-09-30&date_to=2026-09-01",
                                   "date_from=2025-01-01&date_to=2026-12-31"])
def test_api_bad_range_is_400(client, app, query):
    _login(client, _make_user(role="MANAGER", team="ACCOUNTING"))

    resp = client.get(f"{API_URL}?{query}")

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False and body["data"] is None and body["error"]


@pytest.mark.parametrize("role,team", [("STAFF", "CS"), ("STAFF", "SALES"), ("VIEWER", None)])
def test_api_denied_actor_is_403(client, app, role, team):
    _seed_mix()
    _login(client, _make_user(role=role, team=team))

    resp = client.get(f"{API_URL}?date_from={FROM}&date_to={TO}")

    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False and body["data"] is None and body["error"]
