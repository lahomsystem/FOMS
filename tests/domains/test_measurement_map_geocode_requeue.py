"""실측 지도 지오코딩 재큐 백오프 계약 (`foms.api.measurement.map`).

`geocode_status='failed'` 주문은 지도를 열 때마다 무조건 재큐돼서 단일 RQ 워커를 점유하고
카카오 쿼터만 태웠다(운영 실패 37건). 이 스위트는 새 술어를 고정한다:

* ``pending`` — 최근에 예약된 것이면 재큐하지 않는다(중복 enqueue 금지). 다만 예약 시각이
  없거나 오래된 ``pending`` 은 다시 집는다 — 주소 수정 경로가 ``pending`` 만 찍고 죽은
  outbox 에 예약해 영구 고착되던 계열의 구제책(2026-09-01, 스윕 술어와 같은 규칙).
* ``address_error`` — 재큐하지 않는다(카카오가 "그런 주소 없음"이라 답한 건).
* ``NULL``(미시도) — 즉시 재큐한다(기존 동작 유지 — 백오프가 미시도를 막으면 안 된다).
* ``failed`` — 마지막 시도(``geocoded_at``)로부터 백오프 간격이 지나야 재큐한다.
  **영구 제외가 아니다** — 간격이 지나면 다시 큐에 들어간다.
* ``failed`` + ``geocoded_at`` 없음(레거시 행) — 1회 재시도해 시각을 남긴다.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

import foms.api.measurement.map as measurement_map
from foms.api.measurement.map import (
    FAILED_GEOCODE_REQUEUE_INTERVAL,
    _enqueue_missing_measurement_geocodes,
    _should_requeue_geocode,
)
from foms.services.geocode_retry import PENDING_RETRY_INTERVAL

_NOW = datetime.datetime(2026, 8, 31, 12, 0, 0)


def _order(order_id: int, *, geocode_status, geocoded_at=None, lat=None, lng=None,
           address: str = "서울시 강남구 테헤란로 1"):
    """좌표 없는(=재큐 후보) 주문 스텁."""
    return SimpleNamespace(
        id=order_id,
        lat=lat,
        lng=lng,
        address=address,
        geocode_status=geocode_status,
        geocoded_at=geocoded_at,
        is_erp_order=False,
        structured_data=None,
    )


class _FakeDb:
    """commit 횟수만 세는 세션 스텁."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def enqueued(monkeypatch):
    """RQ enqueue 를 가로채 order_id 리스트로 기록한다(외부 큐/카카오 호출 금지)."""
    calls: list[int] = []
    monkeypatch.setattr(
        measurement_map, "enqueue_geocode_order_address", lambda oid: calls.append(oid)
    )
    return calls


# --------------------------------------------------------------------------- #
# 술어 단위
# --------------------------------------------------------------------------- #
def test_recent_pending_is_not_requeued():
    """방금 예약된 pending 은 재큐하지 않는다(중복 enqueue 0)."""
    order = _order(1, geocode_status="pending",
                   geocoded_at=_NOW - (PENDING_RETRY_INTERVAL / 2))
    assert _should_requeue_geocode(order, now=_NOW) is False


def test_stuck_pending_is_requeued():
    """예약 시각이 없는 pending(고착 계열)은 다시 집는다.

    ``reset_order_geocode_on_address_change`` 는 ``pending`` 만 찍고 ``geocoded_at`` 은
    건드리지 않는다. 예약이 SIDEFX outbox 로 갔다가 소비되지 않으면 그 주문은 영원히
    ``pending`` 으로 남는다 — 그때 화면이 유일한 구제 경로다.
    """
    order = _order(1, geocode_status="pending", geocoded_at=None)
    assert _should_requeue_geocode(order, now=_NOW) is True


def test_address_error_is_never_requeued():
    """음성 대조군: 주소가 조회되지 않는 건은 나이와 무관하게 재큐하지 않는다."""
    stale = _order(6, geocode_status="address_error",
                   geocoded_at=_NOW - datetime.timedelta(days=30))
    assert _should_requeue_geocode(stale, now=_NOW) is False
    assert _should_requeue_geocode(
        _order(7, geocode_status="address_error", geocoded_at=None), now=_NOW) is False


def test_never_attempted_is_requeued_immediately():
    """NULL(미시도)은 즉시 큐 — 백오프가 첫 시도를 막으면 안 된다."""
    order = _order(2, geocode_status=None)
    assert _should_requeue_geocode(order, now=_NOW) is True


def test_recent_failure_is_backed_off():
    """최근 실패 건은 재큐하지 않는다(카카오 쿼터·워커 점유 방지)."""
    order = _order(3, geocode_status="failed",
                   geocoded_at=_NOW - (FAILED_GEOCODE_REQUEUE_INTERVAL / 2))
    assert _should_requeue_geocode(order, now=_NOW) is False


def test_stale_failure_is_requeued_again():
    """백오프 간격이 지난 실패 건은 다시 큐에 들어간다(영구 제외가 아니다)."""
    order = _order(4, geocode_status="failed",
                   geocoded_at=_NOW - FAILED_GEOCODE_REQUEUE_INTERVAL
                   - datetime.timedelta(minutes=1))
    assert _should_requeue_geocode(order, now=_NOW) is True


def test_failure_without_timestamp_is_requeued_once():
    """실패 시각이 없는 레거시 행은 1회 재시도해 geocoded_at 을 남긴다."""
    order = _order(5, geocode_status="failed", geocoded_at=None)
    assert _should_requeue_geocode(order, now=_NOW) is True


# --------------------------------------------------------------------------- #
# 호출 경로(지도 응답이 실제로 넣는 것)
# --------------------------------------------------------------------------- #
def test_enqueue_skips_recent_failures_but_keeps_untried(enqueued, monkeypatch):
    """지도 조회 1회: 미시도는 큐에 들어가고, 최근 실패 건은 상태도 pending 으로 바뀌지 않는다."""
    monkeypatch.setattr(measurement_map, "now_utc_naive", lambda: _NOW)
    untried = _order(11, geocode_status=None)
    fresh_failure = _order(12, geocode_status="failed",
                           geocoded_at=_NOW - datetime.timedelta(hours=1))
    stale_failure = _order(13, geocode_status="failed",
                           geocoded_at=_NOW - datetime.timedelta(days=7))
    db = _FakeDb()

    _enqueue_missing_measurement_geocodes(db, [untried, fresh_failure, stale_failure])

    assert enqueued == [11, 13]
    assert untried.geocode_status == "pending"
    assert stale_failure.geocode_status == "pending"
    assert fresh_failure.geocode_status == "failed"  # 상태를 덮어쓰지 않는다
    # 시도 표식이 찍혀야 다음 조회에서 백오프가 걸린다(같은 건 반복 재큐 차단).
    assert untried.geocoded_at == _NOW
    assert stale_failure.geocoded_at == _NOW
    assert db.commits == 1


def test_enqueue_does_not_commit_when_everything_backed_off(enqueued, monkeypatch):
    """전부 백오프면 큐도 commit 도 없다(반복 조회가 write 를 만들지 않는다)."""
    monkeypatch.setattr(measurement_map, "now_utc_naive", lambda: _NOW)
    orders = [
        _order(21, geocode_status="failed", geocoded_at=_NOW - datetime.timedelta(minutes=5)),
        _order(22, geocode_status="pending", geocoded_at=_NOW - datetime.timedelta(minutes=1)),
        _order(23, geocode_status="address_error", geocoded_at=None),
    ]
    db = _FakeDb()

    _enqueue_missing_measurement_geocodes(db, orders)

    assert enqueued == []
    assert db.commits == 0


def test_orders_with_coordinates_are_never_enqueued(enqueued, monkeypatch):
    """좌표가 이미 있으면 상태와 무관하게 큐에 넣지 않는다."""
    monkeypatch.setattr(measurement_map, "now_utc_naive", lambda: _NOW)
    order = _order(31, geocode_status="failed", geocoded_at=None, lat=37.5, lng=127.0)
    db = _FakeDb()

    _enqueue_missing_measurement_geocodes(db, [order])

    assert enqueued == []
    assert db.commits == 0
