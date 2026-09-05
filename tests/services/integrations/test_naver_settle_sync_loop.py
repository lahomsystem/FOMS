"""F-07 — 정산 동기화 러너의 창당 1회 가드(순수 함수 ``should_run``·``records_day``) 계약 (2026-09-05).

창(10분) 안에서 매 tick(60초) 실행하면 같은 동기화가 5번 돌아 run 이 5행 쌓이고, 예외 큐는
최신 run 만 읽어 첫 run 의 소급 변경이 화면에서 사라졌다(감사 F-07, 운영 run 19~23 실측).
러너 모듈은 import 시 앱을 부팅하므로 기존 파일의 ``_runner`` 로더를 그대로 쓴다(복제 금지) —
그래서 각 테스트가 ``app`` 픽스처를 받는다(``test_runner_window_and_backfill_parsing`` 과 같은 이유).
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
