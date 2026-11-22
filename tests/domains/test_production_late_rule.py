"""생산 늦음 · 빠듯 규칙 — 설계서 docs/specs/2026-11-21-production-pc-viewer_SPEC.md §8 · §13 결정 3(일하는 날로 센다).
도면 · 컨펌 기다림 줄은 도면 마감(시공일 − 2영업일)에 맞춘다 — 설계서 docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md §7.

표의 경계값 전부(자리 넷 × 빠듯 · 늦음 · 없음) + 주말 · 공휴일 빼기 + 지난 시공일 + 보류(멈춘 공정 자리) + 제작 완료 · 검수 끝
+ 시공일 없음 + KST 자정 경계(UTC 서버에서도 KST 오늘로 센다). 순수 함수라 DB 없이 돈다.
기준 날: 2026-11-23 (월) — 11/24 화 = 일하는 날 1, 11/25 = 2, 11/26 = 3, 11/27 금 = 4, 11/30 월 = 5, 12/1 = 6.
"""
from __future__ import annotations

import datetime

import pytest

from foms.services.common.business_calendar import business_days_between
from foms.services.production.late_rule import LATE_THRESHOLDS, late_spot, production_late_level, production_late_view

MON = datetime.date(2026, 11, 23)
_KEYS = ("cut", "edge", "assemble", "inspect")
_LABELS = {"cut": "재단", "edge": "엣지", "assemble": "조립", "inspect": "검수"}


def _row(stage: str, due: str | None, *, done: int = 0, hold: bool = False, run: bool = True, view: str = "prod") -> dict:
    steps = [{"key": k, "label": _LABELS[k], "done": i < done, "now": False} for i, k in enumerate(_KEYS)]
    return {"home_stage": stage, "home_view": view, "construction_date": due, "home_steps": steps,
            "hold_active": hold, "home_has_run": run}


def _d(day: int, month: int = 11) -> str:
    return datetime.date(2026, month, day).isoformat()


def test_숫자_표는_설계서_제안값_한_곳() -> None:
    # 기다림('wait')은 표가 아니라 도면 마감으로 센다(2026-11-22 §7 — 표에서 지웠다)
    assert LATE_THRESHOLDS == {"ready": (4, 2), "early": (3, 1), "final": (2, 0)}


@pytest.mark.parametrize(("row", "cases"), [
    # 도면 · 컨펌 기다림: 마감(시공일 − 2영업일) 지남 = 늦음, 마감 오늘 · 다음 영업일 = 빠듯, 그 밖 없음(오늘 11/23 월)
    # 11/24 화 → 마감 11/20 금 · 11/25 수 → 11/23 월(오늘) · 11/26 목 → 11/24 화(다음 영업일) · 11/27 금 → 11/25 수
    (_row("컨펌 기다림", None, view="wait", run=False), [(_d(24), "late"), (_d(25), "tight"), (_d(26), "tight"), (_d(27), None)]),
    (_row("도면 기다림", None, view="wait", run=False), [(_d(23), "late"), (_d(24), "late"), (_d(26), "tight"), (_d(30), None)]),
    # 제작 대기: 빠듯 W ≤ 4 · 늦음 W ≤ 2 (옛 '생산 D-2' 배지와 같은 기준점)
    (_row("제작 대기", None, run=False), [(_d(25), "late"), (_d(26), "tight"), (_d(27), "tight"), (_d(30), None)]),
    # 재단 · 엣지 중: 빠듯 W ≤ 3 · 늦음 W ≤ 1
    (_row("재단 중", None), [(_d(24), "late"), (_d(25), "tight"), (_d(26), "tight"), (_d(27), None)]),
    (_row("엣지 중", None, done=1), [(_d(24), "late"), (_d(25), "tight"), (_d(26), "tight"), (_d(27), None)]),
    # 조립 · 검수 중: 빠듯 W ≤ 2 · 늦음 W ≤ 0
    (_row("조립 중", None, done=2), [(_d(23), "late"), (_d(24), "tight"), (_d(25), "tight"), (_d(26), None)]),
    (_row("검수 중", None, done=3), [(_d(23), "late"), (_d(24), "tight"), (_d(25), "tight"), (_d(26), None)]),
])
def test_자리마다_경계값(row: dict, cases: list) -> None:
    for due, want in cases:
        assert production_late_level({**row, "construction_date": due}, MON) == want, (row["home_stage"], due)


def test_주말은_일하는_날에서_빠진다() -> None:
    fri = datetime.date(2026, 11, 20)
    # 금 → 다음 월: 달력 3일, 일하는 날 1일 → 재단 중 늦음(W ≤ 1). 달력 날로 셌다면 빠듯도 아니었다(D-3 > 1)
    assert business_days_between(fri, datetime.date(2026, 11, 23)) == 1
    assert production_late_level(_row("재단 중", _d(23)), fri) == "late"
    # 금 → 일: 일하는 날 0 → 조립 중 늦음
    assert production_late_level(_row("조립 중", _d(22), done=2), fri) == "late"
    # 금 → 다음 수(달력 5일, 일하는 날 3) → 제작 대기 빠듯
    assert production_late_level(_row("제작 대기", _d(25), run=False), fri) == "tight"


def test_공휴일도_빠진다_성탄절() -> None:
    wed = datetime.date(2026, 12, 23)
    # 12/24 목(1) · 12/25 금 공휴일 · 주말 · 12/28 월(2) → W = 2 → 제작 대기 늦음. 공휴일을 세면 3 이라 빠듯이었다
    assert business_days_between(wed, datetime.date(2026, 12, 28)) == 2
    assert production_late_level(_row("제작 대기", _d(28, 12), run=False), wed) == "late"


def test_지난_시공일은_자리와_상관없이_늦음_제작_완료만_뺀다() -> None:
    past = _d(20)
    for row in (_row("도면 기다림", past, view="wait", run=False), _row("제작 대기", past, run=False),
                _row("검수 중", past, done=3), _row("검수 끝", past, done=4)):
        assert production_late_level(row, MON) == "late", row["home_stage"]
    assert production_late_level(_row("제작 완료", past, done=4, view="done"), MON) is None
    # 검수 끝(모든 공정 끝)은 앞날이면 색 없음 — 남은 일은 [제작 완료] 누르기뿐
    assert production_late_level(_row("검수 끝", _d(24), done=4), MON) is None


def test_보류는_멈춘_공정의_자리() -> None:
    # 회차 있음 + 재단 끝 → 엣지에서 멈춤 = 재단 · 엣지 자리(늦음 W ≤ 1)
    held = _row("보류", _d(24), done=1, hold=True)
    assert late_spot(held) == ("early", "엣지에서 보류")
    assert production_late_level(held, MON) == "late"
    # 조립에서 멈춤 = 조립 · 검수 자리(W 1 → 빠듯)
    assert production_late_level(_row("보류", _d(24), done=2, hold=True), MON) == "tight"
    # 회차 없이 보류 = 제작 대기 자리(W 2 → 늦음)
    assert late_spot(_row("보류", None, hold=True, run=False)) == ("ready", "시작 전 보류")
    assert production_late_level(_row("보류", _d(25), hold=True, run=False), MON) == "late"


def test_시공일_없음은_색이_없다() -> None:
    assert production_late_level(_row("제작 대기", None, run=False), MON) is None
    assert production_late_level(_row("제작 대기", "", run=False), MON) is None
    assert production_late_view(_row("제작 대기", None, run=False), MON) == {"level": None, "line": "", "tip": ""}


def test_줄_글과_마우스_글() -> None:
    view = production_late_view(_row("제작 대기", _d(24), run=False), MON)
    assert view == {"level": "late", "line": "늦음 — 내일 시공, 아직 시작 전", "tip": "시공까지 일하는 날 1일"}
    view = production_late_view(_row("엣지 중", _d(26), done=1), MON)
    assert view == {"level": "tight", "line": "빠듯 — 시공 D-3, 아직 엣지", "tip": "시공까지 일하는 날 3일"}
    view = production_late_view(_row("재단 중", _d(23)), MON)
    assert view["line"] == "늦음 — 오늘 시공, 아직 재단" and view["tip"] == "시공까지 일하는 날 0일"
    view = production_late_view(_row("컨펌 기다림", _d(21), view="wait", run=False), MON)
    assert view == {"level": "late", "line": "늦음 — 시공 2일 지남, 아직 컨펌 기다림", "tip": "시공일 2일 지남"}
    # 줄에 쓰는 D-n 은 달력 날(D-3), 색 기준은 일하는 날 — 같은 숫자가 아닐 수 있어 마우스 글에 적는다
    assert production_late_view(_row("제작 대기", _d(30), run=False), MON)["tip"] == "시공까지 일하는 날 5일"
    # 여러 시공일 주문은 견줄 날(due)을 따로 받는다
    assert production_late_level(_row("제작 대기", _d(1, 12), run=False), MON, due=datetime.date(2026, 11, 24)) == "late"


def test_기다림_줄은_도면_마감에_맞춘다_띠와_같은_말() -> None:
    """설계서 2026-11-22 §7 — 띠는 주황 '마감 내일' 인데 PC 줄은 빨강 '늦음' 이던 것을 하나로. 오늘 11/24 (화) 예(§7 표)."""
    tue = datetime.date(2026, 11, 24)
    wait = _row("도면 기다림", None, view="wait", run=False)
    assert production_late_level({**wait, "construction_date": _d(27)}, tue) == "tight"  # 금(W 3): 빨강 → 주황
    assert production_late_level({**wait, "construction_date": _d(30)}, tue) is None  # 월(W 4): 주황 → 색 없음
    assert production_late_level({**wait, "construction_date": _d(25)}, tue) == "late"  # 수: 빨강 그대로
    # 줄 글 — 늦음은 마감 날과 막힌 까닭(행의 dw_blocker), 빠듯은 마감 '언제'
    fixing = {**wait, "construction_date": _d(25), "dw_blocker": {"key": "fixing", "label": "도면 고치는 중", "none": False}}
    assert production_late_view(fixing, tue)["line"] == "늦음 — 도면 마감 11/23 (월) 지남, 아직 도면 고치는 중"
    assert production_late_view({**wait, "construction_date": _d(27)}, tue)["line"] == "빠듯 — 도면 마감 내일"
    # 금요일에 월요일 마감 = 빠듯 '월요일'(다음 영업일을 '내일'로 친다, §14 답 4)
    fri = datetime.date(2026, 11, 27)
    assert production_late_level({**wait, "construction_date": _d(2, 12)}, fri) == "tight"
    assert production_late_view({**wait, "construction_date": _d(2, 12)}, fri)["line"] == "빠듯 — 도면 마감 월요일"
    # 다른 자리 표는 그대로(제작 대기 W 2 = 늦음)
    assert production_late_level(_row("제작 대기", _d(26), run=False), tue) == "late"


def test_KST_자정_경계_UTC_서버에서도_KST_오늘(monkeypatch) -> None:
    """UTC 11/22 15:30 = KST 11/23 00:30. 오늘은 KST 11/23 이어야 하고(get_today_kst), 11/23 시공 조립 중은 W 0 → 늦음.
    서버 날짜(UTC 11/22)로 셌다면 W 1 → 빠듯이었다."""
    import foms.services.datetime_kst as kst

    real = datetime.datetime

    class _Frozen(real):
        @classmethod
        def now(cls, tz=None):
            utc = real(2026, 11, 22, 15, 30, tzinfo=datetime.timezone.utc)
            return utc.astimezone(tz) if tz else utc.replace(tzinfo=None)

    monkeypatch.setattr(kst.datetime, "datetime", _Frozen)
    today = kst.get_today_kst()
    assert today == MON
    row = _row("조립 중", _d(23), done=2)
    assert production_late_level(row, today) == "late"
    assert production_late_level(row, datetime.date(2026, 11, 22)) == "tight"
