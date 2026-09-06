"""F-07 — 정산 동기화 러너의 창당 1회 가드(순수 함수 ``should_run``·``records_day``) 계약 (2026-09-05).

창(10분) 안에서 매 tick(60초) 실행하면 같은 동기화가 5번 돌아 run 이 5행 쌓이고, 예외 큐는
최신 run 만 읽어 첫 run 의 소급 변경이 화면에서 사라졌다(감사 F-07, 운영 run 19~23 실측).
러너 모듈은 import 시 앱을 부팅하므로 기존 파일의 ``_runner`` 로더를 그대로 쓴다(복제 금지) —
그래서 각 테스트가 ``app`` 픽스처를 받는다(``test_runner_window_and_backfill_parsing`` 과 같은 이유).

B-01(2026-09-06, CFO 백로그 3차): 확정 구간(예정일+30일) 밖 정정은 백필 없이는 영원히 안
들어온다. ``--loop`` 는 KST 매월 1일 첫 실행을 전월 1일부터 백필로 돈다 — 순수 함수
``monthly_backfill_from``·스위치 ``monthly_backfill_enabled``·``_run_loop`` 소스 계약을 여기서 못 박는다.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime

from foms.services.integrations.naver_commerce.client import KST
from tests.services.integrations.test_naver_settle_sync import _runner

#: 기본 배선과 같은 창 — 05:30 부터 10분.
AT = (5, 30)
WINDOW = 10


def test_should_run_on_first_tick_inside_the_window(app):
    """창 안 첫 tick, 아직 오늘 안 돌았다 → 실행."""
    runner = _runner()
    now = datetime(2026, 9, 5, 5, 31, tzinfo=KST)
    assert runner.should_run(now, AT, WINDOW, None) is True


def test_should_not_run_again_on_the_next_tick_of_the_same_window(app):
    """같은 창의 다음 tick, 오늘 이미 돌았다 → 실행하지 않는다(run 이 5행 쌓이던 원인)."""
    runner = _runner()
    now = datetime(2026, 9, 5, 5, 32, tzinfo=KST)
    assert runner.should_run(now, AT, WINDOW, date(2026, 9, 5)) is False


def test_should_run_again_on_the_next_day_window(app):
    """다음 날 창 — 어제 돌았어도 오늘은 다시 실행."""
    runner = _runner()
    now = datetime(2026, 9, 6, 5, 30, tzinfo=KST)
    assert runner.should_run(now, AT, WINDOW, date(2026, 9, 5)) is True


def test_should_not_run_outside_the_window_even_if_never_ran(app):
    """창 밖이면 한 번도 안 돌았어도 실행하지 않는다(창 밖 실행은 쿼터를 낮에 나눠 쓰게 한다)."""
    runner = _runner()
    now = datetime(2026, 9, 5, 5, 45, tzinfo=KST)
    assert runner.should_run(now, AT, WINDOW, None) is False


def test_records_day_after_ok(app):
    """OK 로 돌아오면 오늘 몫은 끝 — 같은 창의 다음 tick 이 다시 돌면 F-07(OK 뒤 OK) 그대로다."""
    assert _runner().records_day({"status": "OK"}) is True


def test_does_not_record_day_after_failed_so_the_next_tick_retries(app):
    """FAILED 는 기록하지 않는다 — 05:31 일시 장애 한 번이 그날 동기화를 통째로 지우던 회귀.

    ``run_settle_sync`` 는 실패를 예외가 아니라 반환값으로 주므로, 반환됐다는 사실만으로
    날짜를 찍으면 남은 창 tick 이 재시도하지 않는다. FAILED 는 coverage 를 안 밀어 재시도해도
    F-07 이 되살아나지 않고, 상한은 창 길이(창/tick 회)다.
    """
    assert _runner().records_day({"status": "FAILED", "error": "token expired"}) is False


def test_records_day_after_quota_abort_because_retry_only_burns_quota(app):
    """ABORTED_QUOTA 는 기록한다 — 쿼터가 바닥난 뒤 창 안 재시도는 헛돌고 쿼터만 더 깎는다."""
    assert _runner().records_day({"status": "ABORTED_QUOTA"}) is True


def test_run_loop_records_the_day_only_after_a_returned_result(app):
    """루프는 ``should_run`` 으로 판정하고, 날짜 기록은 ``_sync_once`` 가 **반환한 뒤**에만 한다.

    예외로 빠져나오면 기록되지 않아 다음 tick 이 다시 시도한다(FAILED 반환은 ``records_day`` 가
    걸러 다음 tick 이 다시 시도한다).
    """
    source = inspect.getsource(_runner()._run_loop)
    assert "should_run(now, at, args.window, last_run_day)" in source
    assert "last_run_day = now.date()" in source
    assert source.index("_sync_once(") < source.index("last_run_day = now.date()")
    assert "in_window(now_kst()" not in source, "가드 없는 옛 판정이 남아 있다"
    assert "if records_day(result):" in source, "FAILED 반환을 거르는 가드가 없다"
    assert source.index("if records_day(result):") < source.index("last_run_day = now.date()")


# --------------------------------------------------------------------------- #
# B-01 — 매월 1일 자동 백필(순수 함수 + 스위치 + _run_loop 소스 계약)
# --------------------------------------------------------------------------- #

#: 러너가 읽는 스위치 이름 — 운영 env 문서·설계서와 같은 리터럴.
MONTHLY_SWITCH = "FOMS_NAVER_SETTLE_MONTHLY_BACKFILL"


def test_monthly_backfill_from_is_the_previous_month_first_on_day_one(app):
    """9월 1일 → 8월 1일(전월 전체를 다시 읽는다)."""
    assert _runner().monthly_backfill_from(date(2026, 9, 1)) == date(2026, 8, 1)


def test_monthly_backfill_from_rolls_january_back_to_last_december(app):
    """1월 1일 → 전년 12월 1일(연 경계에서 월 뺄셈이 틀리지 않는다)."""
    assert _runner().monthly_backfill_from(date(2026, 1, 1)) == date(2025, 12, 1)


def test_monthly_backfill_from_is_none_off_day_one(app):
    """1일이 아니면 None — 평일 SCHEDULE 실행은 그대로 45일 롤링이다."""
    runner = _runner()
    assert runner.monthly_backfill_from(date(2026, 9, 2)) is None
    assert runner.monthly_backfill_from(date(2026, 9, 30)) is None


def test_monthly_backfill_from_is_none_when_the_switch_is_off(app, monkeypatch):
    """스위치가 꺼지면 1일이라도 None. env ``0`` → 꺼짐, 미설정 → 켜짐(기본 1)."""
    runner = _runner()
    assert runner.MONTHLY_BACKFILL_ENV == MONTHLY_SWITCH
    assert runner.monthly_backfill_from(date(2026, 9, 1), enabled=False) is None
    monkeypatch.setenv(MONTHLY_SWITCH, "0")
    assert runner.monthly_backfill_enabled() is False
    assert runner.monthly_backfill_from(date(2026, 9, 1),
                                        enabled=runner.monthly_backfill_enabled()) is None
    monkeypatch.delenv(MONTHLY_SWITCH, raising=False)
    assert runner.monthly_backfill_enabled() is True


def test_run_loop_asks_monthly_backfill_before_sync_once_and_cli_value_wins(app):
    """``_run_loop`` 는 ``should_run`` 판정 **뒤**·``_sync_once`` 호출 **앞**에 월초 판정을 하고,
    명시 ``--backfill-from`` 이 월초 자동값보다 우선한다(``backfill_from or monthly``).
    기존 F-07 소스 계약(``should_run(...)`` 판정)은 그대로 살아 있어야 한다.
    """
    source = inspect.getsource(_runner()._run_loop)
    call = "monthly_backfill_from(now.date(), enabled=monthly_backfill_enabled())"
    guard = "should_run(now, at, args.window, last_run_day)"
    assert guard in source, "F-07 창당 1회 가드가 사라졌다"
    assert call in source, "월초 백필 판정이 없다"
    assert source.index(guard) < source.index(call) < source.index("_sync_once(")
    assert "backfill_from or monthly" in source, "명시 --backfill-from 우선 규칙이 없다"
    assert "monthly_backfill=" in source, "started 로그가 스위치 상태를 말하지 않는다"
