"""일정표 누락 검출기(tools/perf/measurement_osd_gap_check.py)의 판정 계약.

실측 화면 보충 술어에서 JSON 통째 검색을 뺀 근거를 운영 승격 전에 다시 재는 도구라,
검출기가 조용히 0 을 내면 근거가 거짓이 된다. 빠진 날짜를 잡는지(양성)·일정표가 있으면
안 잡는지(음성)·평평한 컬럼 안전망 판정이 맞는지를 지킨다.
"""

from tools.perf.measurement_osd_gap_check import find_gaps


def _row(oid, *, mdate=None, emd=None, sd=None, is_erp=True):
    return (oid, is_erp, mdate, emd, sd or {}, "MEASURE", None)


def test_order_with_schedule_row_is_not_a_gap():
    rows = [_row(1, emd="2026-10-01", sd={"schedule": {"measurement": {"date": "2026-10-01"}}})]
    assert find_gaps(rows, {1: {"2026-10-01"}}) == []


def test_missing_schedule_row_is_reported_and_flat_column_catches_it():
    rows = [_row(2, emd="2026-10-02", sd={"schedule": {"measurement": {"date": "2026-10-02"}}})]
    assert find_gaps(rows, {}) == [(2, "MEASURE", None, ["2026-10-02"], ["2026-10-02"])]


def test_item_only_date_without_flat_column_is_a_lost_gap():
    """품목에만 있는 실측일은 평평한 컬럼에 없다 — 안전망에 안 걸린다고 보고해야 한다."""
    rows = [_row(3, sd={"items": [{"measurement_date": "2026-10-03"}]})]
    gaps = find_gaps(rows, {})
    assert gaps == [(3, "MEASURE", None, ["2026-10-03"], [])]
