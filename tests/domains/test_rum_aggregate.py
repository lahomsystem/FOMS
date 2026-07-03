"""RUM 집계/리포트 순수 단위 테스트 (P3).

- 히스토그램 버킷 매핑
- Redis 부재 fail-open
- HINCRBY 집계(가짜 Redis)
- 화이트리스트 방어(카디널리티)
- p95 보간 / 회귀 판정
"""

from __future__ import annotations

import pytest

from foms.services import rum_aggregate as ra


# --- 가짜 Redis (pipeline HINCRBY/EXPIRE/HGETALL 최소 구현) --------------------
class _FakePipeline:
    def __init__(self, store: dict) -> None:
        self._store = store
        self._ops: list = []

    def hincrby(self, key: str, field: str, amount: int):
        self._ops.append(("hincrby", key, field, amount))
        return self

    def expire(self, key: str, ttl: int):
        self._ops.append(("expire", key, ttl))
        return self

    def execute(self) -> list:
        results = []
        for op in self._ops:
            if op[0] == "hincrby":
                _, key, field, amount = op
                h = self._store.setdefault(key, {})
                h[field] = int(h.get(field, 0)) + amount
                results.append(h[field])
            elif op[0] == "expire":
                self._store.setdefault("__ttl__", {})[op[1]] = op[2]
                results.append(True)
        self._ops = []
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self.store)

    def hgetall(self, key: str) -> dict:
        return dict(self.store.get(key, {}))


class _BoomRedis:
    def pipeline(self):
        raise RuntimeError("redis down")


# --- 버킷 매핑 -----------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0),
        (99, 0),
        (100, 1),
        (299, 1),
        (300, 2),
        (799, 2),
        (800, 3),
        (1999, 3),
        (2000, 4),
        (4999, 4),
        (5000, 5),
        (999999, 5),
    ],
)
def test_bucket_index_mapping(value, expected):
    assert ra.bucket_index(value) == expected


# --- record_metric fail-open ---------------------------------------------------
def test_record_metric_redis_missing_returns_false(monkeypatch):
    monkeypatch.setattr(
        "foms.services.common.dashboard_cache.get_dashboard_redis", lambda: None
    )
    assert ra.record_metric("LCP", 123) is False


def test_record_metric_redis_error_fail_open():
    assert (
        ra.record_metric("LCP", 500, redis_client=_BoomRedis(), date_str="2026-07-04")
        is False
    )


# --- 화이트리스트/파싱 방어 -----------------------------------------------------
def test_record_metric_rejects_unknown_metric():
    fake = _FakeRedis()
    assert ra.record_metric("EVIL", 100, redis_client=fake, date_str="2026-07-04") is False
    assert fake.store == {}


def test_record_metric_rejects_nonnumeric_value():
    fake = _FakeRedis()
    assert ra.record_metric("LCP", "abc", redis_client=fake, date_str="2026-07-04") is False
    assert fake.store == {}


def test_record_metric_rejects_negative():
    fake = _FakeRedis()
    assert ra.record_metric("SWAP", -5, redis_client=fake, date_str="2026-07-04") is False
    assert fake.store == {}


# --- HINCRBY 집계 --------------------------------------------------------------
def test_record_metric_hincrby_aggregates():
    fake = _FakeRedis()
    day = "2026-07-04"
    # LCP: 50ms(b0), 250ms(b1), 250ms(b1), 6000ms(b5)
    for v in (50, 250, 250, 6000):
        assert ra.record_metric("LCP", v, redis_client=fake, date_str=day) is True
    key = ra.build_rum_key(day, "LCP")
    hist = ra.histogram_from_hash(fake.store[key])
    assert hist == [1, 2, 0, 0, 0, 1]
    # TTL 도 설정되었는지
    assert fake.store["__ttl__"][key] == ra.TTL_SECONDS


# --- histogram_from_hash 방어 --------------------------------------------------
def test_histogram_from_hash_ignores_out_of_range():
    hist = ra.histogram_from_hash({"0": "3", "9": "5", "bad": "2", "2": "7"})
    assert hist == [3, 0, 7, 0, 0, 0]


# --- p95 보간 ------------------------------------------------------------------
def test_percentile_empty_is_none():
    assert ra.percentile_from_histogram([0] * ra.BUCKET_COUNT, 0.95) is None


def test_percentile_single_bucket_interpolates_within_range():
    # 전부 b1 [100,300): p50 은 그 구간 안.
    counts = [0, 10, 0, 0, 0, 0]
    p50 = ra.percentile_from_histogram(counts, 0.50)
    assert p50 is not None and 100 <= p50 <= 300


def test_percentile_p95_lands_in_tail_bucket():
    # 90개 b0, 10개 b4([2000,5000)). p95 는 tail 버킷.
    counts = [90, 0, 0, 0, 10, 0]
    p95 = ra.percentile_from_histogram(counts, 0.95)
    assert p95 is not None and 2000 <= p95 <= 5000


def test_percentile_open_top_uses_nominal_upper():
    counts = [0, 0, 0, 0, 0, 4]
    p95 = ra.percentile_from_histogram(counts, 0.95)
    assert p95 is not None and 5000 <= p95 <= ra.OPEN_TOP_NOMINAL_MS


# --- 회귀 판정 -----------------------------------------------------------------
def test_detect_regression_warns_on_spike():
    # baseline 중앙값 200, recent max 400 → x2 >= 1.5 → WARN
    v = ra.detect_regression([400.0, 210.0], [200.0, 190.0, 210.0, 205.0, 195.0])
    assert v.regressed is True
    assert v.ratio is not None and v.ratio >= 1.5


def test_detect_regression_ok_when_stable():
    v = ra.detect_regression([210.0, 205.0], [200.0, 190.0, 210.0, 205.0, 195.0])
    assert v.regressed is False


def test_detect_regression_none_when_insufficient():
    assert ra.detect_regression([], [200.0]).regressed is None
    assert ra.detect_regression([200.0], []).regressed is None


def test_detect_regression_threshold_boundary():
    # 정확히 1.5배 → 경계 포함(>=) 이므로 WARN
    v = ra.detect_regression([300.0], [200.0])
    assert v.regressed is True
