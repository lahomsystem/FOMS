"""P1-2(단위 판정 — 라우트 통합 계약은 test_dashboard_cache_save_scope_routes.py): 저장 경로의 대시보드 캐시 통째 비우기(broad)를 바뀐 탭만 비우게 좁힌 계약.

운영 30일 동안 캐시 무효화가 하루 500~1,300번 일어났고 적중률은 38~53% 에 머물렀다.
저장 경로 13곳 + 날짜 동기화 리스너가 저장 한 번마다 7 family 를 전부 비웠기 때문이다.

판정 기준은 하나다: **그 family 의 캐시된 slice DTO 가 이 저장의 바뀐 값을 담을 수 있는가.**
이 파일은 판정 함수 단위로 경로마다 "그 변경이 보이는 탭의 캐시는 비워지고, 무관한 탭은 남는다" 를 고정하고,
소속 자체가 바뀌는 전이(AS 접수·새 주문·status 변경·초안 승격)는 broad 그대로임을 고정한다.

비워진 family 는 ``invalidate_dashboard_family`` 를 가로채 센다 — 라우트의 손 호출, MUT-CACHE-01
리스너, 날짜 동기화 리스너가 모두 이 한 함수를 거치므로 요청 하나가 실제로 비운 전부가 잡힌다.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from foms.services.common import dashboard_cache as dc
from foms.services.datetime_kst import get_today_kst

ALL = set(dc.ALL_DASHBOARD_FAMILIES)
TODAY = datetime.date(2026, 10, 1)


def _iso(days: int, base: datetime.date | None = None) -> str:
    return ((base or get_today_kst()) + datetime.timedelta(days=days)).isoformat()


# =========================================================================== #
# 1) 순수 판정 — dashboard_families_for_order_save
# =========================================================================== #
def _order(stage="PRODUCTION", *, status=None, measurement=None, construction=None,
           customer="홍길동", items=None, drawing_status=None, draft=False, **flat):
    sd = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": customer, "phone": "010-1234-5678"}},
        "schedule": {
            "measurement": {"date": measurement or ""},
            "construction": {"date": construction or ""},
        },
        "items": items if items is not None else [{"product_name": "붙박이장", "price": 100}],
    }
    if drawing_status:
        sd["drawing_status"] = drawing_status
    if draft:
        sd["meta"] = {"draft": True}
    base = dict(
        status=status or stage, deleted_at=None, is_erp_order=True, erp_stage_code=stage,
        customer_name=customer, phone="010-1234-5678", address="서울", product="붙박이장",
        manager_name="영업", measurement_date=None, erp_measurement_date=measurement,
        scheduled_date=None, erp_construction_date=construction, is_regional=False,
        is_self_measurement=False, measurement_completed=False,
        regional_sales_order_upload=False, regional_blueprint_sent=False,
        regional_order_upload=False, structured_data=sd,
    )
    base.update(flat)
    return SimpleNamespace(**base)


#: 검색 필드(첫 품목명)는 그대로 두고 금액만 바꾼 품목 — "내용만 바뀐 저장".
PRICE_ONLY = [{"product_name": "붙박이장", "price": 777}]


def _families(before, after) -> set[str]:
    return set(dc.dashboard_families_for_order_save(
        dc.order_dashboard_cache_axes(before), dc.order_dashboard_cache_axes(after), today=TODAY,
    ))


def test_save_without_dates_in_window_scopes_to_stage_family():
    """생산 단계·실측은 지난달·시공은 두 달 뒤: 품목 값만 바뀌면 orders + 생산 숫자판만."""
    before = _order("PRODUCTION", measurement=_iso(-40, TODAY), construction=_iso(60, TODAY))
    after = _order("PRODUCTION", measurement=_iso(-40, TODAY), construction=_iso(60, TODAY),
                   items=[{"product_name": "붙박이장", "price": 200}])
    assert _families(before, after) == {"orders", "production"}


def test_measurement_date_in_window_keeps_measurement_family():
    """실측일이 오늘~14일 창 안이면 단계와 무관하게 실측 캐시(품목 목록 DTO)를 비운다."""
    before = _order("DRAWING", measurement=_iso(0, TODAY))
    after = _order("DRAWING", measurement=_iso(0, TODAY),
                   items=[{"product_name": "붙박이장", "price": 999}])
    assert _families(before, after) == {"orders", "drawing", "measurement"}


def test_construction_date_in_window_keeps_shipment_family():
    """시공일이 출고 패널 창(오늘~14일) 안이면 출고 집계(자수·작업자)를 비운다."""
    before = _order("PRODUCTION", construction=_iso(3, TODAY))
    after = _order("PRODUCTION", construction=_iso(3, TODAY),
                   items=[{"product_name": "붙박이장", "price": 1}])
    assert _families(before, after) == {"orders", "production", "shipment"}


def test_measurement_date_change_outside_window_still_clears_measurement():
    """창 밖이라도 실측일이 바뀌면 지난 날짜 목록의 소속이 바뀐다 → 실측 family.
    실측일 문자열은 과거 이력 검색 대상이라 history 도."""
    before = _order("PRODUCTION", measurement=_iso(-40, TODAY))
    after = _order("PRODUCTION", measurement=_iso(-39, TODAY))
    assert {"measurement", "history"} <= _families(before, after)


def test_regional_flag_change_clears_measurement_panel():
    before = _order("PRODUCTION", measurement=_iso(-40, TODAY))
    after = _order("PRODUCTION", measurement=_iso(-40, TODAY), is_regional=True)
    assert "measurement" in _families(before, after)


def test_identity_change_clears_history_search():
    """이름이 바뀌면 과거 이력 검색 결과(단계 무관 전체 주문)의 소속이 바뀐다."""
    before = _order("PRODUCTION")
    after = _order("PRODUCTION", customer="김철수")
    assert _families(before, after) == {"orders", "production", "history"}


def test_completed_order_also_clears_construction_summary():
    """시공 숫자판은 완료 단계도 센다(시공완료) — 단계 family(history) + construction."""
    assert _families(_order("COMPLETED"), _order("COMPLETED", items=PRICE_ONLY)) == {
        "orders", "history", "construction",
    }


def test_construction_stage_also_clears_production_summary():
    """생산 숫자판은 시공 단계도 센다(제작완료 버킷) — construction + production."""
    assert _families(_order("CONSTRUCTION"), _order("CONSTRUCTION", items=PRICE_ONLY)) == {
        "orders", "construction", "production",
    }


def test_received_order_without_dates_clears_orders_only():
    assert _families(_order("RECEIVED"), _order("RECEIVED", items=PRICE_ONLY)) == {"orders"}


def test_drawing_status_change_clears_drawing_queue():
    before = _order("PRODUCTION", drawing_status="CONFIRMED")
    after = _order("PRODUCTION", drawing_status="RETURNED")
    assert "drawing" in _families(before, after)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (_order("RECEIVED", draft=True, status="DRAFT"), _order("RECEIVED")),  # 초안 승격
        (_order("PRODUCTION"), _order("PRODUCTION", status="AS_RECEIVED")),  # status 변경
        (_order("PRODUCTION"), _order("PRODUCTION", deleted_at=datetime.datetime(2026, 10, 1))),
        (_order("실측중"), _order("실측중", items=[])),  # 모르는 단계
        (_order("RECEIVED"), _order("DRAWING")),  # 도메인 탭 없는 단계에서 이동
    ],
)
def test_membership_transitions_stay_broad(before, after):
    assert _families(before, after) == ALL


def test_missing_before_snapshot_is_broad():
    after = dc.order_dashboard_cache_axes(_order("PRODUCTION"))
    assert set(dc.dashboard_families_for_order_save(None, after, today=TODAY)) == ALL


def test_before_snapshot_is_frozen_against_in_place_edits():
    """저장 도중 structured_data 를 제자리에서 고쳐도 전 스냅샷은 그대로여야 비교가 된다."""
    order = _order("PRODUCTION")
    before = dc.order_dashboard_cache_axes(order)
    order.structured_data["parties"]["customer"]["name"] = "바뀐 이름"
    order.customer_name = "바뀐 이름"
    assert "history" in dc.dashboard_families_for_order_save(
        before, dc.order_dashboard_cache_axes(order), today=TODAY
    )


# --- 정본 상수와 같은지(드리프트 = 과소무효화) --------------------------------
def test_summary_stage_sets_match_read_models():
    from foms.services.construction_read_model import CONSTRUCTION_ALL_STAGE_CODES
    from foms.services.production_read_model import PRODUCTION_BASE_STAGE_CODES

    assert dc.CONSTRUCTION_SUMMARY_STAGE_CODES == frozenset(CONSTRUCTION_ALL_STAGE_CODES)
    assert dc.PRODUCTION_SUMMARY_STAGE_CODES == frozenset(PRODUCTION_BASE_STAGE_CODES)


def test_date_window_matches_measurement_panel_range(monkeypatch):
    import foms.services.measurement_dashboard_filters as mdf

    monkeypatch.setattr(mdf, "get_search_query_arg", lambda *a, **k: "")
    f = mdf.parse_measurement_dashboard_filters(SimpleNamespace(args={}), TODAY)

    assert f.range_start == TODAY
    assert (f.range_end - f.range_start).days == dc.DASHBOARD_DATE_WINDOW_DAYS


# --- 일정 종류 → family -------------------------------------------------------
def test_schedule_kind_scopes():
    assert set(dc.dashboard_families_for_schedule_change({"measurement"})) == {
        "orders", "measurement", "construction", "history", "production",
    }
    assert set(dc.dashboard_families_for_schedule_change({"construction"})) == {
        "orders", "shipment", "construction", "history", "production",
    }
    assert set(dc.dashboard_families_for_schedule_change({"as_visit"})) == {
        "orders", "shipment", "construction",
    }
    # 품목 날짜는 품목 dict 안에 있다 → 실측 제품 목록 DTO 도.
    assert "measurement" in dc.dashboard_families_for_schedule_change(
        {"construction"}, item_level=True
    )
    assert set(dc.dashboard_families_for_schedule_change({"completion"})) == ALL
