"""RUM 일별 히스토그램 집계 (Redis, 추세 감시용).

배경: P3 — 실사용 성능 회귀를 사용자보다 대시보드가 먼저 발견하는 마지막 그물.
정확 p95가 목적이 아니라 추세 감시이므로 **고정 버킷 히스토그램**(메모리 상수)으로
집계한다. 요청 hot path 부담을 최소화하기 위해 파이프라인 HINCRBY+EXPIRE 1왕복만 쓴다.

회귀 판정(rum-daily): KST 오늘 제외 · 일별 MIN_DAY_SAMPLES · 유효 recent
RECENT_WINDOW일 **전부** threshold 초과(지속) · 표시는 중앙값. 아침 cron 오탐 차단.

Key: ``foms:rum:v1:<YYYY-MM-DD>:<metric>`` (Redis Hash, field=bucket index, value=count)
TTL: 35일. Redis 부재/오류 시 조용히 skip(기존 fail-open 관례).

무인증 수신 엔드포인트의 키 카디널리티 공격을 막기 위해 **고정 메트릭명 화이트리스트**
만 집계한다(임의 metric 문자열은 키를 만들지 않는다).
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Final, NamedTuple

logger = logging.getLogger("foms.rum")

KEY_VERSION: Final[str] = "v1"
KEY_PREFIX: Final[str] = f"foms:rum:{KEY_VERSION}"
TTL_SECONDS: Final[int] = 35 * 24 * 3600

# rum-baseline.js 가 실제 전송하는 고정 메트릭명만 집계한다.
#   LCP/INP/LOAD = Web Vitals + nav timing, SWAP = ERP 셸 탭 프래그먼트 스왑 소요(ms).
ALLOWED_METRICS: Final[frozenset[str]] = frozenset({"LCP", "INP", "LOAD", "SWAP"})

# 고정 버킷 상한(ms). 마지막 버킷은 open-ended(5000+ ms).
#   버킷0 [0,100) 1 [100,300) 2 [300,800) 3 [800,2000) 4 [2000,5000) 5 [5000,+inf)
BUCKET_UPPER_BOUNDS_MS: Final[tuple[int, ...]] = (100, 300, 800, 2000, 5000)
BUCKET_COUNT: Final[int] = len(BUCKET_UPPER_BOUNDS_MS) + 1
BUCKET_LOWER_BOUNDS_MS: Final[tuple[int, ...]] = (0,) + BUCKET_UPPER_BOUNDS_MS
# open-ended 최상위 버킷 보간용 명목 상한(ms). 실제 값이 아니라 p-quantile 보간 상한.
OPEN_TOP_NOMINAL_MS: Final[int] = 10000

# 회귀 판정 임계치: 최근 p95 가 baseline 중앙값 대비 이 배수 이상이면 WARN.
REGRESSION_THRESHOLD: Final[float] = 1.5

# 일별 최소 표본. 미만이면 그 날 p95 는 회귀 판정에서 제외(아침 미완성·SWAP 희소 오탐 차단).
MIN_DAY_SAMPLES: Final[int] = 30

# 회귀 창에서 KST 오늘(미완성)을 제외한다. rum-daily cron(07:30 KST) 오탐 근본 차단.
SKIP_TODAY_FOR_REGRESSION: Final[bool] = True

# 표본 구성 변화(sample shift) 가드: p95 회귀 판정이 떠도, 최근 구간의
# p50 이 baseline 대비 안정(배수 이하)이고 표본량이 급감(배수 이하)했다면
# "코드 회귀"가 아니라 "측정 모집단 변화"(예: 휴가로 사무실 데스크톱 이탈
# → 느린 모바일 코호트만 잔존)로 보고 red 대신 ⚠️ 경고로 강등한다.
# 근거: 2026-08-05 INP x1.96 오경보 — p50 은 12일간 52~60ms 로 불변,
# 표본만 97% 증발(주말 저표본일의 고 p95 패턴과 동일). 진짜 전면 회귀는
# p50 도 움직이고 표본량은 유지된다.
SAMPLE_SHIFT_P50_STABLE_MAX: Final[float] = 1.25
SAMPLE_SHIFT_VOLUME_MAX: Final[float] = 0.5

_KST: Final[timezone] = timezone(timedelta(hours=9))


def bucket_index(value_ms: float) -> int:
    """값(ms)을 히스토그램 버킷 인덱스(0..BUCKET_COUNT-1)로 매핑한다.

    Args:
        value_ms: 밀리초 값(음수 아님 가정).

    Returns:
        0 이상 BUCKET_COUNT-1 이하의 버킷 인덱스.
    """
    for i, upper in enumerate(BUCKET_UPPER_BOUNDS_MS):
        if value_ms < upper:
            return i
    return BUCKET_COUNT - 1


def today_kst_str() -> str:
    """KST 기준 오늘 날짜 문자열(YYYY-MM-DD). 운영 사용자 한국 기준 일별 버킷."""
    return datetime.now(_KST).strftime("%Y-%m-%d")


def recent_kst_dates(days: int) -> list[str]:
    """오늘(KST)부터 과거로 ``days``일치 날짜 문자열 리스트(최신순).

    Args:
        days: 며칠치를 반환할지(>=1).

    Returns:
        ``["2026-07-04", "2026-07-03", ...]`` 형태 최신→과거 순 리스트.
    """
    today = datetime.now(_KST).date()
    return [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(max(1, days))]


def build_rum_key(date_str: str, metric: str) -> str:
    """집계 Redis 키 문자열 생성(``foms:rum:v1:<date>:<metric>``)."""
    return f"{KEY_PREFIX}:{date_str}:{metric}"


def record_metric(
    metric: Any,
    value: Any,
    *,
    redis_client: Any | None = None,
    date_str: str | None = None,
) -> bool:
    """수신 메트릭을 일별 히스토그램 버킷에 HINCRBY 로 집계한다.

    fail-open: 화이트리스트 밖 metric / 파싱 불가 value / Redis 부재/오류는 조용히
    skip(False 반환). 요청 응답·기존 동작에는 영향을 주지 않는다.

    Args:
        metric: 메트릭명. ALLOWED_METRICS 에 없으면 무시.
        value: 밀리초 값(숫자로 변환 가능해야 함).
        redis_client: 주입용(테스트). None 이면 dashboard_cache 의 공유 클라이언트 재사용.
        date_str: 주입용(테스트). None 이면 KST 오늘.

    Returns:
        집계 성공 시 True, skip 시 False.
    """
    if not isinstance(metric, str) or metric not in ALLOWED_METRICS:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    # 음수/NaN 방어(NaN 은 자기 자신과 != ).
    if v < 0 or v != v:
        return False

    if redis_client is None:
        try:
            from foms.services.common.dashboard_cache import get_dashboard_redis

            redis_client = get_dashboard_redis()
        except Exception:  # pragma: no cover - import/런타임 방어
            redis_client = None
    if redis_client is None:
        return False

    key = build_rum_key(date_str or today_kst_str(), metric)
    idx = bucket_index(v)
    try:
        pipe = redis_client.pipeline()
        pipe.hincrby(key, str(idx), 1)
        pipe.expire(key, TTL_SECONDS)
        pipe.execute()
        return True
    except Exception as exc:  # Redis 지연/장애 → 집계만 skip.
        logger.warning("[RUM] aggregate skip: %s", exc)
        return False


def histogram_from_hash(raw: dict[Any, Any] | None) -> list[int]:
    """Redis HGETALL 결과(field=bucket idx, value=count)를 버킷 카운트 리스트로 변환.

    Args:
        raw: ``{"0": "12", "5": "3"}`` 형태 dict(문자/정수 키 혼용 허용).

    Returns:
        길이 BUCKET_COUNT 의 카운트 리스트. 범위 밖/파싱불가 항목은 무시.
    """
    counts = [0] * BUCKET_COUNT
    for field, val in (raw or {}).items():
        try:
            idx = int(field)
            if 0 <= idx < BUCKET_COUNT:
                counts[idx] = int(val)
        except (TypeError, ValueError):
            continue
    return counts


def percentile_from_histogram(counts: list[int], q: float) -> float | None:
    """고정 버킷 히스토그램에서 q 분위수를 선형 보간으로 근사한다.

    Args:
        counts: 길이 BUCKET_COUNT 의 버킷 카운트.
        q: 0..1 분위(예: 0.95).

    Returns:
        근사 분위수(ms). 표본이 없으면 None.
    """
    total = sum(counts)
    if total <= 0:
        return None
    target = q * total
    cum = 0.0
    for i, c in enumerate(counts):
        if c <= 0:
            continue
        prev = cum
        cum += c
        if cum >= target:
            lower = BUCKET_LOWER_BOUNDS_MS[i]
            upper = (
                BUCKET_UPPER_BOUNDS_MS[i]
                if i < len(BUCKET_UPPER_BOUNDS_MS)
                else OPEN_TOP_NOMINAL_MS
            )
            frac = (target - prev) / c
            return float(lower) + (float(upper) - float(lower)) * frac
    return None


class RegressionVerdict(NamedTuple):
    """회귀 판정 결과.

    Attributes:
        regressed: True=회귀 WARN, False=정상, None=데이터 부족.
        recent_p95: 최근 구간 대표 p95(중앙값). 데이터 없으면 None.
        baseline_p95: baseline 구간 p95 중앙값. 데이터 없으면 None.
        ratio: recent/baseline 비율. 계산 불가 시 None.
    """

    regressed: bool | None
    recent_p95: float | None
    baseline_p95: float | None
    ratio: float | None


# 회귀 판정 창(일): 최근 RECENT_WINDOW 일 p95 vs 직전 BASELINE_WINDOW 일 p95 중앙값.
# SKIP_TODAY_FOR_REGRESSION 이면 조회 일수 하한 = 1(오늘)+RECENT+BASELINE.
RECENT_WINDOW: Final[int] = 2
BASELINE_WINDOW: Final[int] = 5


def p95_for_regression(p95: float | None, samples: int) -> float | None:
    """회귀 판정에 넣을 일별 p95. 표본 부족·결측이면 None.

    Args:
        p95: 히스토그램 근사 p95(ms).
        samples: 해당일 표본 수.

    Returns:
        samples >= MIN_DAY_SAMPLES 이고 p95 가 있을 때만 p95, 아니면 None.
    """
    if p95 is None or samples < MIN_DAY_SAMPLES:
        return None
    return p95


def detect_regression(
    recent_p95: list[float | None],
    baseline_p95: list[float | None],
    threshold: float = REGRESSION_THRESHOLD,
) -> RegressionVerdict:
    """최근 구간이 baseline 대비 지속 회귀면 WARN.

    - 표시용 recent/baseline 대표값: 각 구간 p95 **중앙값**.
    - 판정: 유효 recent 일이 ``RECENT_WINDOW``개 이상이고, **전부**가
      ``baseline_중앙값 * threshold`` 이상일 때만 regressed=True.
      하루만 남거나 하루만 spike면 skip/OK(아침·희소 오탐 차단).

    Args:
        recent_p95: 최근 구간(예: 최근 2일) 일별 p95 리스트(None 허용).
        baseline_p95: baseline 구간(예: 직전 5일) 일별 p95 리스트(None 허용).
        threshold: 회귀 배수(기본 1.5 = +50%).

    Returns:
        RegressionVerdict. 유효 recent < RECENT_WINDOW 이거나 baseline 없으면
        regressed=None.
    """
    recent_vals = [x for x in recent_p95 if x is not None]
    baseline_vals = [x for x in baseline_p95 if x is not None]
    if not recent_vals or not baseline_vals:
        return RegressionVerdict(None, None, None, None)
    recent_med = statistics.median(recent_vals)
    base_med = statistics.median(baseline_vals)
    if base_med <= 0:
        return RegressionVerdict(None, recent_med, base_med, None)
    ratio = recent_med / base_med
    # 하루만 유효하면 "지속"을 주장할 수 없음 → 판정 skip.
    if len(recent_vals) < RECENT_WINDOW:
        return RegressionVerdict(None, recent_med, base_med, ratio)
    cutoff = base_med * threshold
    sustained = all(v >= cutoff for v in recent_vals)
    return RegressionVerdict(sustained, recent_med, base_med, ratio)


def detect_sample_shift(
    recent_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
) -> bool:
    """p95 회귀가 표본 구성 변화(모집단 이동)로 설명되는지 판정한다.

    조건(둘 다 충족 시 True):
    - 최근 구간 p50 중앙값 <= baseline p50 중앙값 × SAMPLE_SHIFT_P50_STABLE_MAX
      (typical 사용자 체감 불변 — 전면 회귀면 p50 도 움직인다)
    - 최근 구간 일별 표본 중앙값 <= baseline 일별 표본 중앙값 × SAMPLE_SHIFT_VOLUME_MAX
      (모집단 급감 — 빠른 코호트 이탈로 tail 이 저절로 상승하는 구도)

    p50 데이터가 없으면 보수적으로 False(강등하지 않음).

    Args:
        recent_rows: 최근 구간 day_stats 행 목록.
        baseline_rows: baseline 구간 day_stats 행 목록.

    Returns:
        표본 구성 변화로 설명 가능하면 True.
    """
    # p95 판정과 동일한 유효일 필터(samples >= MIN_DAY_SAMPLES)를 양쪽에 적용.
    # baseline 창에 이미 붕괴된 저표본일이 섞이면(전환기) 원시 중앙값이 오염되어
    # 가드가 미발동한다 — 2026-08-05 실데이터(08-02 n=21 혼입)로 확인된 함정.
    recent_ok = [r for r in recent_rows if int(r["samples"]) >= MIN_DAY_SAMPLES]
    base_ok = [r for r in baseline_rows if int(r["samples"]) >= MIN_DAY_SAMPLES]
    recent_p50 = [r["p50"] for r in recent_ok if r["p50"] is not None]
    base_p50 = [r["p50"] for r in base_ok if r["p50"] is not None]
    recent_n = [int(r["samples"]) for r in recent_ok]
    base_n = [int(r["samples"]) for r in base_ok]
    if not recent_p50 or not base_p50 or not recent_n or not base_n:
        return False
    base_p50_med = statistics.median(base_p50)
    base_n_med = statistics.median(base_n)
    if base_p50_med <= 0 or base_n_med <= 0:
        return False
    p50_stable = (
        statistics.median(recent_p50) <= base_p50_med * SAMPLE_SHIFT_P50_STABLE_MAX
    )
    volume_collapsed = (
        statistics.median(recent_n) <= base_n_med * SAMPLE_SHIFT_VOLUME_MAX
    )
    return p50_stable and volume_collapsed


def day_stats(redis_client: Any, date_str: str, metric: str) -> dict[str, Any]:
    """하루치 히스토그램 → ``{date, samples, p50, p95}``.

    Args:
        redis_client: ``hgetall`` 지원 Redis 클라이언트(조회 전용).
        date_str: ``YYYY-MM-DD``.
        metric: ALLOWED_METRICS 원소.

    Returns:
        일자·표본수·p50·p95(표본 없으면 p50/p95 는 None).
    """
    raw = redis_client.hgetall(build_rum_key(date_str, metric))
    counts = histogram_from_hash(raw)
    return {
        "date": date_str,
        "samples": sum(counts),
        "p50": percentile_from_histogram(counts, 0.50),
        "p95": percentile_from_histogram(counts, 0.95),
    }


def _regression_day_offset() -> int:
    """회귀 슬라이스 시작 오프셋(0=오늘 포함, 1=오늘 스킵)."""
    return 1 if SKIP_TODAY_FOR_REGRESSION else 0


def build_rum_report(redis_client: Any, days: int = 7) -> dict[str, Any]:
    """메트릭별 최근 ``days``일 p50/p95 추세 + 회귀 판정을 JSON 직렬화 리포트로 집계.

    CLI(``tools/perf/rum_report.py``)와 admin 엔드포인트(``/api/foms/rum/report``)의
    **단일 진실원**. 요청 hot path 가 아니라 감시용이라 조회는 메트릭×일자 HGETALL 뿐.

    회귀 창은 기본적으로 KST 오늘을 제외하고(미완성 일 오탐 차단), 일별
    ``samples < MIN_DAY_SAMPLES`` 인 날의 p95 는 판정에서 뺀다. recent/baseline
    대표값은 모두 중앙값.

    Args:
        redis_client: ``hgetall`` 지원 클라이언트(운영은 앱 내부 Redis, CLI 는 REDIS_URL).
        days: 조회 일수(최소 today-skip+RECENT+BASELINE 로 보정).

    Returns:
        ``{days, metrics: [{metric, daily: [...], regression: {...}}], regressed: bool,
        warnings: [str]}``. ``regressed`` 는 메트릭 중 하나라도 WARN 이면 True.
    """
    offset = _regression_day_offset()
    days = max(offset + RECENT_WINDOW + BASELINE_WINDOW, days)
    dates = recent_kst_dates(days)  # 최신 → 과거
    metrics_out: list[dict[str, Any]] = []
    any_regressed = False
    warnings: list[str] = []
    for metric in sorted(ALLOWED_METRICS):
        daily = [day_stats(redis_client, d, metric) for d in dates]
        window = daily[offset:]
        recent_rows = window[:RECENT_WINDOW]
        baseline_rows = window[RECENT_WINDOW : RECENT_WINDOW + BASELINE_WINDOW]
        recent_p95 = [
            p95_for_regression(row["p95"], int(row["samples"])) for row in recent_rows
        ]
        baseline_p95 = [
            p95_for_regression(row["p95"], int(row["samples"])) for row in baseline_rows
        ]
        verdict = detect_regression(recent_p95, baseline_p95)
        sample_shift = False
        if verdict.regressed:
            sample_shift = detect_sample_shift(recent_rows, baseline_rows)
            if sample_shift:
                warnings.append(
                    f"{metric}: ⚠️ 표본 구성 변화 의심 — p95 x{verdict.ratio:.2f} 상승했으나 "
                    f"p50 안정·표본 급감(모집단 이동). red 아님, 표본 회복 후 재평가."
                )
            else:
                any_regressed = True
                warnings.append(
                    f"{metric}: recent p95 {verdict.recent_p95:.0f}ms vs baseline 중앙값 "
                    f"{verdict.baseline_p95:.0f}ms (x{verdict.ratio:.2f})"
                )
        eligible_recent_n = sum(
            int(row["samples"])
            for row, p in zip(recent_rows, recent_p95)
            if p is not None
        )
        eligible_baseline_n = sum(
            int(row["samples"])
            for row, p in zip(baseline_rows, baseline_p95)
            if p is not None
        )
        metrics_out.append(
            {
                "metric": metric,
                "daily": daily,
                "regression": {
                    "regressed": verdict.regressed,
                    "sample_shift": sample_shift,
                    "recent_p95": verdict.recent_p95,
                    "baseline_p95": verdict.baseline_p95,
                    "ratio": verdict.ratio,
                    "recent_samples": eligible_recent_n,
                    "baseline_samples": eligible_baseline_n,
                },
            }
        )
    return {
        "days": days,
        "metrics": metrics_out,
        "regressed": any_regressed,
        "warnings": warnings,
    }
