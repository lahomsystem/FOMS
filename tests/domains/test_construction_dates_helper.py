"""시공일 읽기 도우미 계약 (묶음 B — 틀린 완료 막기, 설계서 5.1).

``foms/services/orders/construction_dates.py`` 는 순수 함수다 — DB 없이 잠근다.
"고쳐지는 꼴"(시공일 둘)과 "그대로여야 하는 꼴"(시공일 하나 · 모두 지남 · 취소 제품)을 같이 둔다.
"""
from __future__ import annotations

import datetime

import pytest

from foms.services.orders import construction_dates as cd

TODAY = datetime.date(2026, 11, 5)


def _sd(order_text=None, items=None):
    sd = {"schedule": {"construction": {"date": order_text}}}
    if items is not None:
        sd["items"] = items
    return sd


def test_two_dates_in_order_text_are_split_sorted_and_deduped():
    """주문 칸 글의 쉼표 여러 날 — 적힌 순서와 무관하게 오름차순, 같은 날은 한 번."""
    assert cd.all_construction_dates(_sd("2026-11-17, 2026-11-05")) == ["2026-11-05", "2026-11-17"]
    assert cd.all_construction_dates(_sd("2026-11-05,2026-11-05")) == ["2026-11-05"]
    assert cd.all_construction_dates(_sd("2026/11/5, 2026.11.17")) == ["2026-11-05", "2026-11-17"]


def test_item_only_later_date_is_included():
    """제품 칸에만 적힌 뒤 시공일도 읽는다(주문 칸은 첫 날만)."""
    sd = _sd("2026-11-05", items=[
        {"name": "붙박이장", "construction_date": "2026-11-05"},
        {"name": "화장대", "construction_date": "2026-11-17"},
    ])
    assert cd.all_construction_dates(sd) == ["2026-11-05", "2026-11-17"]
    assert cd.remaining_construction_note(sd, TODAY) == "11/17 시공이 남아 있어요"


def test_cancelled_item_date_is_excluded():
    """취소된 제품(``cancel`` dict)의 시공일은 남은 시공으로 치지 않는다."""
    sd = _sd("2026-11-05", items=[
        {"name": "붙박이장", "construction_date": "2026-11-05"},
        {"name": "화장대", "construction_date": "2026-11-17", "cancel": {"reason": "customer_change"}},
    ])
    assert cd.all_construction_dates(sd) == ["2026-11-05"]
    assert cd.remaining_construction_note(sd, TODAY) == ""
    assert cd.production_split_note(sd) == ""


@pytest.mark.parametrize("garbage", [
    None, "", "미정", "추후 협의", "2026-13-40", "2026-11-051", 20261105, {"a": 1}, ["2026-11-17"], True,
])
def test_garbage_text_never_raises_and_yields_nothing(garbage):
    """못 읽는 날짜 글 · 엉뚱한 형식은 예외 없이 버린다."""
    assert cd.split_date_text(garbage) == []
    sd = _sd(garbage, items=[{"construction_date": garbage}, "not-a-dict", None])
    assert cd.all_construction_dates(sd) == []
    assert cd.remaining_construction_note(sd, TODAY) == ""
    assert cd.production_split_note(sd) == ""


@pytest.mark.parametrize("broken_sd", [
    None, "", [], "text", {"schedule": "x"}, {"schedule": {"construction": "2026-11-17"}},
    {"schedule": None, "items": "x"}, {"items": {"construction_date": "미정"}},
])
def test_broken_structured_data_never_raises(broken_sd):
    """``structured_data`` 모양이 깨져 있어도 빈 값으로 끝난다."""
    assert cd.all_construction_dates(broken_sd) == []
    assert cd.remaining_construction_dates(broken_sd, TODAY) == []
    assert cd.remaining_construction_note(broken_sd, TODAY) == ""


def test_garbage_token_beside_valid_date_keeps_the_valid_one():
    """한 글 안에 못 읽는 토큰이 섞여도 읽히는 날짜는 남긴다."""
    assert cd.split_date_text("2026-11-05, 미정, 2026-11-17 오후") == ["2026-11-05", "2026-11-17"]


def test_all_past_dates_leave_no_note():
    """시공일이 모두 지났으면 한 줄이 없다(대조군)."""
    sd = _sd("2026-10-01, 2026-10-20")
    assert cd.remaining_construction_dates(sd, TODAY) == []
    assert cd.remaining_construction_note(sd, TODAY) == ""


def test_single_date_order_has_no_note_on_its_own_day():
    """시공일이 하나뿐인 주문은 그날 [시공 완료]를 눌러도 한 줄이 없다(대조군)."""
    sd = _sd("2026-11-05")
    assert cd.remaining_construction_note(sd, TODAY) == ""
    assert cd.production_split_note(sd) == ""


def test_today_boundary_uses_kst_today(monkeypatch):
    """오늘 시공일은 "남은 시공"이 아니다 — 오늘보다 뒤만. 오늘은 ``get_today_kst()``."""
    sd = _sd("2026-11-05, 2026-11-06")
    monkeypatch.setattr(cd, "get_today_kst", lambda: datetime.date(2026, 11, 5))
    assert cd.remaining_construction_note(sd) == "11/6 시공이 남아 있어요"   # 첫날 누름
    monkeypatch.setattr(cd, "get_today_kst", lambda: datetime.date(2026, 11, 6))
    assert cd.remaining_construction_note(sd) == ""                        # 둘째 날 누름
    monkeypatch.setattr(cd, "get_today_kst", lambda: datetime.date(2026, 11, 4))
    assert cd.remaining_construction_note(sd) == "11/5 · 11/6 시공이 남아 있어요"


def test_production_note_only_with_two_or_more_distinct_dates():
    """[제작 완료] 글은 서로 다른 시공일이 둘 이상일 때만 — 날짜가 지났는지는 보지 않는다."""
    assert cd.production_split_note(_sd("2026-11-05, 2026-11-17")) == (
        "시공일이 11/5 · 11/17 두 번이에요. 제품이 모두 제작됐나요?"
    )
    assert cd.production_split_note(_sd("2026-11-05, 2026-11-17, 2026-12-01")) == (
        "시공일이 11/5 · 11/17 · 12/1 세 번이에요. 제품이 모두 제작됐나요?"
    )
    # 같은 날을 주문 칸과 제품 칸에 두 번 적은 것은 한 번이다
    same_day = _sd("2026-11-05", items=[{"construction_date": "2026-11-05"}])
    assert cd.production_split_note(same_day) == ""


def test_pick_nearest_date_prefers_upcoming_then_last():
    """M20 — 오늘 이후(오늘 포함) 가장 가까운 날, 모두 지났으면 마지막 날."""
    days = ["2026-11-05", "2026-11-17", "2026-11-24"]
    assert cd.pick_nearest_date(days, datetime.date(2026, 11, 1)) == datetime.date(2026, 11, 5)
    assert cd.pick_nearest_date(days, datetime.date(2026, 11, 5)) == datetime.date(2026, 11, 5)
    assert cd.pick_nearest_date(days, datetime.date(2026, 11, 6)) == datetime.date(2026, 11, 17)
    assert cd.pick_nearest_date(days, datetime.date(2026, 12, 1)) == datetime.date(2026, 11, 24)
    assert cd.pick_nearest_date([], datetime.date(2026, 11, 1)) is None
