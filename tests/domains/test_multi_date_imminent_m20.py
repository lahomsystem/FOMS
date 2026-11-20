"""시공일이 여럿일 때 자동 할 일 · 임박 배지 (묶음 B, 설계서 5.4 · 결정 M20).

날짜 글 "2026-11-17, 2026-11-24" 를 통째로 날짜로 읽으려다 None 이 돼, 시공 D-3 · 생산 D-2
할 일과 배지가 빠지고 긴급 할 일 기한에 날짜 둘이 든 글이 들어가던 것을 잠근다.
규칙: 오늘 이후(오늘 포함) 가장 가까운 날, 모두 지났으면 마지막 날. 할 일은 주문 · 키당 하나.
"""
from __future__ import annotations

import datetime

import pytest

from foms.services import erp_display
from foms.services.common.business_calendar import business_days_until
from foms.services.orders import erp_policy_tasks as tasks

TWO_DATES = "2026-11-17, 2026-11-24"   # 둘 다 화요일


def _sd(cons_text, *, stage="PRODUCTION", urgent=False, items=None, meas_text=None):
    sd = {
        "workflow": {"stage": stage},
        "schedule": {"construction": {"date": cons_text}, "measurement": {"date": meas_text}},
        "flags": {"urgent": urgent},
    }
    if items is not None:
        sd["items"] = items
    return sd


@pytest.fixture
def fixed_today(monkeypatch):
    """할 일 모듈과 배지 모듈의 "오늘"을 한 날짜로 묶는다."""
    def _set(day: datetime.date):
        monkeypatch.setattr(tasks, "get_today_kst", lambda: day)
        monkeypatch.setattr(tasks, "_business_days_until",
                            lambda iso: business_days_until(iso, today=day))
        monkeypatch.setattr(erp_display, "get_today_kst", lambda: day)
    return _set


def _by_key(specs):
    keys = [s.auto_key for s in specs]
    assert len(keys) == len(set(keys)), keys   # 주문 · 키당 하나 — 날짜마다 따로 만들지 않는다
    return {s.auto_key: s for s in specs}


def test_two_future_dates_use_the_nearest(fixed_today):
    """둘 다 앞날이면 가까운 날(11-17)로 D-3 · D-2 · 틀 기한 · 긴급 기한이 잡힌다."""
    fixed_today(datetime.date(2026, 11, 16))
    out = _by_key(tasks.build_auto_tasks(_sd(TWO_DATES, urgent=True)))
    assert out["AUTO_CONSTRUCT_D3"].due_date == "2026-11-17"
    assert out["AUTO_CONSTRUCT_D3"].meta["construction_date"] == "2026-11-17"
    assert out["AUTO_CONSTRUCT_D3"].meta["d"] == 1
    assert out["AUTO_PRODUCTION_D2"].due_date == "2026-11-17"
    assert out["AUTO_URGENT"].due_date == "2026-11-17"            # 날짜 둘이 든 글이 아니다
    assert out["TEMPLATE_PRODUCTION_PRODUCTION_PLAN"].due_date == "2026-11-13"  # 영업일 -2


def test_first_date_passed_moves_to_the_next(fixed_today):
    """첫 시공이 지나면 다음 날짜(11-24)로 옮긴다."""
    fixed_today(datetime.date(2026, 11, 20))
    out = _by_key(tasks.build_auto_tasks(_sd(TWO_DATES, urgent=True)))
    assert out["AUTO_CONSTRUCT_D3"].due_date == "2026-11-24"
    assert out["AUTO_CONSTRUCT_D3"].meta["d"] == 2
    assert out["AUTO_PRODUCTION_D2"].due_date == "2026-11-24"
    assert out["AUTO_URGENT"].due_date == "2026-11-24"
    assert out["TEMPLATE_PRODUCTION_PRODUCTION_PLAN"].due_date == "2026-11-20"


def test_all_dates_passed_use_the_last(fixed_today):
    """모두 지났으면 마지막 날 — 임박 할 일은 없고 틀 기한 · 긴급 기한은 마지막 날 기준."""
    fixed_today(datetime.date(2026, 11, 26))
    out = _by_key(tasks.build_auto_tasks(_sd(TWO_DATES, urgent=True)))
    assert "AUTO_CONSTRUCT_D3" not in out and "AUTO_PRODUCTION_D2" not in out
    assert out["AUTO_URGENT"].due_date == "2026-11-24"
    assert out["TEMPLATE_PRODUCTION_PRODUCTION_PLAN"].due_date == "2026-11-20"


def test_single_date_order_is_unchanged_control(fixed_today):
    """대조군 — 시공일 하나인 주문은 날짜 둘(가까운 날이 같은) 주문과 같은 결과다."""
    fixed_today(datetime.date(2026, 11, 16))
    single = tasks.build_auto_tasks(_sd("2026-11-17", urgent=True))
    double = tasks.build_auto_tasks(_sd(TWO_DATES, urgent=True))
    assert single == double
    out = _by_key(single)
    assert set(out) == {"AUTO_URGENT", "AUTO_CONSTRUCT_D3", "AUTO_PRODUCTION_D2",
                        "TEMPLATE_PRODUCTION_PRODUCTION_PLAN"}


def test_far_single_date_makes_no_imminent_task_control(fixed_today):
    """대조군 — 시공일이 멀면(하나든 둘이든) 임박 할 일이 없다."""
    fixed_today(datetime.date(2026, 11, 2))
    for text in ("2026-11-17", TWO_DATES):
        out = _by_key(tasks.build_auto_tasks(_sd(text)))
        assert "AUTO_CONSTRUCT_D3" not in out and "AUTO_PRODUCTION_D2" not in out, text


def test_item_only_later_date_is_read_and_cancelled_item_is_not(fixed_today):
    """제품 칸에만 적힌 둘째 날짜도 읽는다. 취소된 제품의 날짜는 안 읽는다."""
    fixed_today(datetime.date(2026, 11, 20))
    items = [{"construction_date": "2026-11-17"}, {"construction_date": "2026-11-24"}]
    out = _by_key(tasks.build_auto_tasks(_sd("2026-11-17", items=items)))
    assert out["AUTO_CONSTRUCT_D3"].due_date == "2026-11-24"
    cancelled = [{"construction_date": "2026-11-17"},
                 {"construction_date": "2026-11-24", "cancel": {"reason": "other"}}]
    out = _by_key(tasks.build_auto_tasks(_sd("2026-11-17", items=cancelled)))
    assert "AUTO_CONSTRUCT_D3" not in out


def test_unreadable_text_keeps_old_behaviour(fixed_today):
    """대조군 — 날짜로 못 읽는 글은 지금처럼 임박 할 일이 없고 긴급 기한에 글이 그대로 남는다."""
    fixed_today(datetime.date(2026, 11, 16))
    out = _by_key(tasks.build_auto_tasks(_sd("미정", urgent=True)))
    assert "AUTO_CONSTRUCT_D3" not in out
    assert out["AUTO_URGENT"].due_date == "미정"
    assert out["TEMPLATE_PRODUCTION_PRODUCTION_PLAN"].due_date is None
    assert _by_key(tasks.build_auto_tasks(_sd(None, urgent=True)))["AUTO_URGENT"].due_date is None


def test_measurement_dates_follow_the_same_pick(fixed_today):
    """실측일도 같은 함수를 지난다 — 날짜 둘이면 가까운 날로 D-4 할 일이 나온다."""
    fixed_today(datetime.date(2026, 11, 16))
    sd = _sd(None, stage="MEASURE", meas_text="2026-11-18, 2026-11-25")
    out = _by_key(tasks.build_auto_tasks(sd))
    assert out["AUTO_MEASURE_D4"].due_date == "2026-11-18"


# --- 대시보드 임박 배지 -------------------------------------------------------

def test_alert_badge_reads_two_dates(fixed_today):
    """날짜 둘인 주문도 시공 D-3 · 생산 D-2 배지가 뜬다(가까운 날 기준)."""
    fixed_today(datetime.date(2026, 11, 16))
    alerts = erp_display._erp_alerts(None, _sd(TWO_DATES), 0)
    assert alerts["construction_d3"] is True and alerts["construction_days"] == 1
    assert alerts["production_d2"] is True

    fixed_today(datetime.date(2026, 11, 20))   # 첫 날이 지남 → 다음 날짜
    alerts = erp_display._erp_alerts(None, _sd(TWO_DATES), 0)
    assert alerts["construction_d3"] is True and alerts["construction_days"] == 2

    fixed_today(datetime.date(2026, 11, 26))   # 모두 지남 → 마지막 날(지난 날)이라 배지 없음
    alerts = erp_display._erp_alerts(None, _sd(TWO_DATES), 0)
    assert alerts["construction_d3"] is False and alerts["construction_days"] < 0


def test_alert_badge_single_date_control(fixed_today):
    """대조군 — 시공일 하나인 주문의 배지 값은 날짜 둘(가까운 날이 같은) 주문과 같다."""
    fixed_today(datetime.date(2026, 11, 16))
    assert erp_display._erp_alerts(None, _sd("2026-11-17"), 0) == \
        erp_display._erp_alerts(None, _sd(TWO_DATES), 0)
    far = erp_display._erp_alerts(None, _sd("2026-12-17"), 0)
    assert far["construction_d3"] is False and far["production_d2"] is False
    none = erp_display._erp_alerts(None, _sd("미정"), 0)
    assert none["construction_days"] is None and none["construction_d3"] is False


def test_alert_badge_ignores_item_dates_so_kpi_projection_matches(fixed_today):
    """배지는 주문 칸 글만 본다 — 숫자판은 schedule 만 투영해 같은 함수를 부르므로 수가 안 갈린다."""
    fixed_today(datetime.date(2026, 11, 20))
    full = _sd("2026-11-17", items=[{"construction_date": "2026-11-24"}])
    projected = {k: full[k] for k in ("flags", "schedule", "workflow")}
    assert erp_display._erp_alerts(None, full, 0) == erp_display._erp_alerts(None, projected, 0)


def test_alert_badge_measurement_two_dates(fixed_today):
    """실측 D-4 배지도 날짜 둘을 읽는다."""
    fixed_today(datetime.date(2026, 11, 16))
    alerts = erp_display._erp_alerts(None, _sd(None, meas_text="2026-11-18, 2026-11-25"), 0)
    assert alerts["measurement_d4"] is True and alerts["measurement_days"] == 2
