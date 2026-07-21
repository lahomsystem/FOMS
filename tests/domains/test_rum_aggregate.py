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
    # baseline 중앙값 200, recent 이틀 모두 >=1.5배 → 지속 회귀 WARN
    v = ra.detect_regression([400.0, 350.0], [200.0, 190.0, 210.0, 205.0, 195.0])
    assert v.regressed is True
    assert v.ratio is not None and v.ratio >= 1.5


def test_detect_regression_uses_recent_median_not_max():
    """recent 한 날만 spike면 지속 회귀 아님(오탐 차단)."""
    # 400만 spike, 100은 정상 → WARN 아님. 표시용 recent=median(250).
    v = ra.detect_regression([400.0, 100.0], [200.0, 190.0, 210.0, 205.0, 195.0])
    assert v.regressed is False
    assert v.recent_p95 == 250.0


def test_detect_regression_ok_when_stable():
    v = ra.detect_regression([210.0, 205.0], [200.0, 190.0, 210.0, 205.0, 195.0])
    assert v.regressed is False


def test_detect_regression_none_when_insufficient():
    assert ra.detect_regression([], [200.0]).regressed is None
    assert ra.detect_regression([200.0], []).regressed is None


def test_detect_regression_threshold_boundary():
    """단일 유효 recent 일만으로는 지속 판정 불가 → skip(None)."""
    v = ra.detect_regression([300.0], [200.0])
    assert v.regressed is None
    assert v.ratio == 1.5


def test_detect_regression_requires_sustained_recent_days():
    """유효 recent 2일 중 하루만 threshold 초과면 OK(메일 오탐 방지)."""
    v = ra.detect_regression([400.0, 220.0], [200.0, 200.0, 200.0, 200.0, 200.0])
    # 400/200=2.0 WARN급, 220/200=1.1 OK → sustained=False
    assert v.regressed is False


def test_detect_regression_skips_when_only_one_recent_day_eligible():
    """MIN 필터 후 recent 1일만 남으면 판정 skip(단일일 WARN 금지)."""
    v = ra.detect_regression([400.0, None], [200.0, 200.0, 200.0, 200.0, 200.0])
    assert v.regressed is None


def test_p95_for_regression_none_below_min_samples():
    """일별 표본이 MIN_DAY_SAMPLES 미만이면 회귀용 p95 는 None."""
    assert ra.p95_for_regression(50.0, ra.MIN_DAY_SAMPLES - 1) is None
    assert ra.p95_for_regression(50.0, ra.MIN_DAY_SAMPLES) == 50.0
    assert ra.p95_for_regression(None, 999) is None


# --- build_rum_report (서비스 함수, Redis 스텁) -------------------------------
def test_build_rum_report_structure_no_data():
    """데이터 없음 → metrics 전부 판정 skip, regressed=False, warnings 비어있음."""
    fake = _FakeRedis()
    report = ra.build_rum_report(fake, 7)
    min_days = 1 + ra.RECENT_WINDOW + ra.BASELINE_WINDOW
    assert report["days"] == min_days
    assert isinstance(report["metrics"], list)
    assert len(report["metrics"]) == len(ra.ALLOWED_METRICS)
    assert report["regressed"] is False
    assert report["warnings"] == []
    for block in report["metrics"]:
        assert set(block) == {"metric", "daily", "regression"}
        assert len(block["daily"]) == min_days
        assert block["regression"]["regressed"] is None


def test_build_rum_report_detects_regression_and_warns():
    """오늘 제외 후 recent 2일 tail spike + baseline 5일 저버킷 → SWAP 회귀 WARN."""
    fake = _FakeRedis()
    min_days = 1 + ra.RECENT_WINDOW + ra.BASELINE_WINDOW
    dates = ra.recent_kst_dates(min_days)  # [today, ...]
    # skip today: recent=dates[1:3], baseline=dates[3:8]
    recent_dates = dates[1 : 1 + ra.RECENT_WINDOW]
    baseline_dates = dates[
        1 + ra.RECENT_WINDOW : 1 + ra.RECENT_WINDOW + ra.BASELINE_WINDOW
    ]
    # MIN_DAY_SAMPLES 이상 표본(버킷 count 합)으로 시드.
    n = str(ra.MIN_DAY_SAMPLES)
    for d in recent_dates:
        fake.store[ra.build_rum_key(d, "SWAP")] = {"4": n}
    for d in baseline_dates:
        fake.store[ra.build_rum_key(d, "SWAP")] = {"0": n}

    report = ra.build_rum_report(fake, 7)
    swap = next(b for b in report["metrics"] if b["metric"] == "SWAP")
    assert swap["regression"]["regressed"] is True
    assert report["regressed"] is True
    assert any("SWAP" in w for w in report["warnings"])


def test_build_rum_report_skips_today_incomplete_spike():
    """오늘(미완성) open-bucket spike는 회귀 창에서 제외 → 전일 정상이면 OK."""
    fake = _FakeRedis()
    min_days = 1 + ra.RECENT_WINDOW + ra.BASELINE_WINDOW
    dates = ra.recent_kst_dates(min_days)
    n = str(ra.MIN_DAY_SAMPLES)
    # today only: open-top spike (아침 cron 오탐 재현).
    fake.store[ra.build_rum_key(dates[0], "LCP")] = {"5": n}
    # yesterday + day-before + baseline: 저버킷 정상.
    for d in dates[1:]:
        fake.store[ra.build_rum_key(d, "LCP")] = {"0": n}

    report = ra.build_rum_report(fake, 7)
    lcp = next(b for b in report["metrics"] if b["metric"] == "LCP")
    assert lcp["regression"]["regressed"] is False
    assert report["regressed"] is False


def test_build_rum_report_ignores_days_below_min_samples():
    """표본 부족한 날의 p95는 회귀 판정에 넣지 않는다 → recent 1일만 남으면 skip."""
    fake = _FakeRedis()
    min_days = 1 + ra.RECENT_WINDOW + ra.BASELINE_WINDOW
    dates = ra.recent_kst_dates(min_days)
    n_ok = str(ra.MIN_DAY_SAMPLES)
    # recent day1: 소수 표본 + open spike (무시). recent day2 + baseline: 정상.
    fake.store[ra.build_rum_key(dates[1], "INP")] = {"5": "3"}
    for d in dates[2:]:
        fake.store[ra.build_rum_key(d, "INP")] = {"0": n_ok}

    report = ra.build_rum_report(fake, 7)
    inp = next(b for b in report["metrics"] if b["metric"] == "INP")
    # 유효 recent < RECENT_WINDOW → 판정 skip(None), 메일 fail 안 함.
    assert inp["regression"]["regressed"] is None
    assert report["regressed"] is False


def test_build_rum_report_clamps_days_to_min_window():
    """days 가 창 합보다 작으면 today-skip+RECENT+BASELINE 로 보정된다."""
    fake = _FakeRedis()
    report = ra.build_rum_report(fake, 1)
    assert report["days"] == 1 + ra.RECENT_WINDOW + ra.BASELINE_WINDOW
