"""KST datetime 표시 SSOT(format_datetime_kst) 계약 테스트."""
from datetime import datetime

import pytz

from foms.services.datetime_kst import format_datetime_kst
from models import OrderEstimate
from wdcalculator_models import Estimate


def test_format_datetime_kst_converts_utc_naive_to_kst() -> None:
    """Railway naive UTC(04:57) → KST(13:57) 변환."""
    assert format_datetime_kst(datetime(2026, 6, 9, 4, 57, 29)) == "2026-06-09 13:57:29"


def test_format_datetime_kst_converts_aware_utc_to_kst() -> None:
    aware = pytz.UTC.localize(datetime(2026, 6, 9, 4, 57, 29))
    assert format_datetime_kst(aware) == "2026-06-09 13:57:29"


def test_format_datetime_kst_none_returns_none() -> None:
    assert format_datetime_kst(None) is None


def test_wdcalculator_estimate_to_dict_uses_kst_created_at() -> None:
    """WDCalculator Estimate API 직렬화가 KST 생성일을 반환한다."""
    estimate = Estimate(
        customer_name="이철기",
        estimate_data={"totalPrice": 1000},
    )
    estimate.id = 700
    estimate.created_at = datetime(2026, 6, 9, 4, 57, 29)
    estimate.updated_at = datetime(2026, 6, 9, 4, 57, 29)

    payload = estimate.to_dict()

    assert payload["created_at"] == "2026-06-09 13:57:29"
    assert payload["updated_at"] == "2026-06-09 13:57:29"


def test_order_estimate_to_dict_uses_kst_timestamps() -> None:
    """ERP OrderEstimate API 직렬화가 KST 생성·수정 시각을 반환한다."""
    estimate = OrderEstimate(
        order_id=1,
        estimate_number="20260609_1",
        customer_name="이철기",
        estimate_date="2026-06-09",
        items=[],
        total_amount=0,
    )
    estimate.created_at = datetime(2026, 6, 9, 4, 57, 29)
    estimate.updated_at = datetime(2026, 6, 9, 4, 57, 29)

    payload = estimate.to_dict()

    assert payload["created_at"] == "2026-06-09 13:57:29"
    assert payload["updated_at"] == "2026-06-09 13:57:29"
