"""실측일 보충 술어는 큰 JSON 을 풀어 읽지 않는다.

예전 보충 술어의 ``CAST(structured_data AS VARCHAR) ILIKE '%날짜%'`` 가지가 스테이징 실측
화면 DB 시간 609ms 중 603ms(패널 486 + 목록 117)를 썼다. 걸린 행도 기록 시각 같은 오탐이라
호출자가 다시 걸러 버렸고, 그 가지만 줄 수 있던 "일정표에 빠진 주문" 은 스테이징 3,520건 중
0건이었다(2026-10-01 전체 성능 검사). 그런 주문을 잡는 안전망은 평평한 컬럼 두 개다.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from foms.services.measurement_read_model import _build_measurement_raw_match_filter


def _sql(expr) -> str:
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_fallback_predicate_never_casts_structured_data():
    sql = _sql(_build_measurement_raw_match_filter(["2026-10-01", "2026-10-02"]))

    assert "structured_data" not in sql
    assert "CAST(" not in sql.upper()


def test_fallback_predicate_keeps_flat_column_safety_net_for_every_date():
    sql = _sql(_build_measurement_raw_match_filter(["2026-10-01", "2026-10-02"]))

    for date_value in ("2026-10-01", "2026-10-02"):
        assert f"orders.measurement_date ILIKE '%%{date_value}%%'" in sql
        assert f"orders.erp_measurement_date = '{date_value}'" in sql


def test_fallback_predicate_is_none_without_dates():
    assert _build_measurement_raw_match_filter([]) is None
    assert _build_measurement_raw_match_filter(["", None, "  "]) is None
