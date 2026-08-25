"""nav 뱃지 단일 비행 회귀 테스트 (2026-08-24, 승격 게이트 1).

뱃지는 **모든 페이지 렌더**에 실린다. 워크벤치 v3 게이트가 켜지면 모집단이 COUNT 1회에서
처리 탭 목록 전체로 바뀌고, 스테이징 73집 실측에서 콜드 1회가 **113ms**(최악 280ms)였다.

캐시가 만료되는 순간 동시 요청이 몰리면 그 수만큼 계산이 동시에 돈다 — 전 직원 개방은
곧 동시 사용자 증가라 그 자리가 실제 위험이다. 여기서는 **계산이 한 번만 도는지**를 잰다.
"""

from __future__ import annotations

import threading
import time

import pytest

from foms.services.integrations.naver_commerce import triage_count as tc


@pytest.fixture(autouse=True)
def _clean_cache():
    tc.reset_triage_count_cache_for_tests()
    yield
    tc.reset_triage_count_cache_for_tests()


def _hammer(monkeypatch, *, threads: int, compute_ms: int = 60):
    """동시에 ``threads`` 개가 뱃지를 읽게 하고 계산 횟수를 돌려준다."""
    calls: list[int] = []
    lock = threading.Lock()

    def _slow_compute(db, *, workbench=False):
        with lock:
            calls.append(1)
        time.sleep(compute_ms / 1000)   # 네트워크·쿼리 대신 시간만 쓴다
        return 7

    monkeypatch.setattr(tc, "compute_triage_pending_count", _slow_compute)

    results: list[int] = []
    barrier = threading.Barrier(threads)

    def _worker():
        barrier.wait()               # 캐시가 빈 **같은 순간**에 몰리게 한다
        results.append(tc.get_triage_pending_count(object(), workbench=True))

    workers = [threading.Thread(target=_worker) for _ in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=10)
    return len(calls), results


def test_concurrent_cold_requests_compute_once(monkeypatch):
    """캐시가 비었을 때 8개가 동시에 들어와도 계산은 **1회**여야 한다."""
    calls, results = _hammer(monkeypatch, threads=8)

    assert calls == 1, f"동시 요청 수만큼 계산이 돌면 안 된다(실제 {calls}회)"
    assert results == [7] * 8, "기다린 쪽도 같은 값을 받아야 한다"


def test_waiters_do_not_recompute_after_the_winner_fills_cache(monkeypatch):
    """잠금을 기다린 쪽은 **캐시를 다시 본다** — 재확인이 없으면 줄만 서고 일은 N번이다."""
    calls, _ = _hammer(monkeypatch, threads=4)
    assert calls == 1

    # 캐시가 살아 있는 동안은 계산이 더 늘지 않는다.
    tc.get_triage_pending_count(object(), workbench=True)
    assert calls == 1


def test_populations_do_not_block_each_other(monkeypatch):
    """게이트 on/off 모집단은 캐시 칸도 계산 잠금도 따로다.

    한 칸을 계산하는 동안 다른 칸이 막히면, 게이트 켠 사람 하나가 나머지 전원의 뱃지를
    붙잡는다.
    """
    seen: list[bool] = []

    def _compute(db, *, workbench=False):
        seen.append(workbench)
        time.sleep(0.05)
        return 1 if workbench else 2

    monkeypatch.setattr(tc, "compute_triage_pending_count", _compute)

    out: dict[str, int] = {}
    t_on = threading.Thread(
        target=lambda: out.__setitem__("on", tc.get_triage_pending_count(object(), workbench=True)))
    t_off = threading.Thread(
        target=lambda: out.__setitem__("off", tc.get_triage_pending_count(object(), workbench=False)))
    t_on.start()
    t_off.start()
    t_on.join(timeout=10)
    t_off.join(timeout=10)

    assert out == {"on": 1, "off": 2}, "모집단마다 자기 값을 받아야 한다"
    assert sorted(seen) == [False, True], "두 모집단 모두 자기 계산을 돌린다"


def test_expired_cache_recomputes(monkeypatch):
    """TTL 이 지나면 다시 계산한다 — 잠금이 값을 영원히 얼려서는 안 된다."""
    calls = []

    def _compute(db, *, workbench=False):
        calls.append(1)
        return len(calls)

    monkeypatch.setattr(tc, "compute_triage_pending_count", _compute)
    monkeypatch.setattr(tc, "TRIAGE_COUNT_CACHE_TTL_SEC", 0)

    first = tc.get_triage_pending_count(object(), workbench=True)
    second = tc.get_triage_pending_count(object(), workbench=True)

    assert (first, second) == (1, 2), "만료 뒤에는 새 값을 읽어야 한다"


def test_failure_still_fails_open_under_the_lock(monkeypatch):
    """계산이 터져도 0 으로 접고 잠금이 남지 않는다(뱃지가 전 페이지를 죽이지 않는다)."""
    def _boom(db, *, workbench=False):
        raise RuntimeError("스냅샷 모양이 예상 밖")

    monkeypatch.setattr(tc, "_work_groups_count_for_test_boom", _boom, raising=False)
    monkeypatch.setattr(tc, "_workbench_group_count", _boom)

    assert tc.get_triage_pending_count(object(), workbench=True) == 0
    # 잠금이 풀려 있어야 다음 요청이 통과한다.
    assert tc.get_triage_pending_count(object(), workbench=True) == 0
