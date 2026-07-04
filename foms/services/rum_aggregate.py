"""RUM 일별 히스토그램 집계 (Redis, 추세 감시용).

배경: P3 — 실사용 성능 회귀를 사용자보다 대시보드가 먼저 발견하는 마지막 그물.
정확 p95가 목적이 아니라 추세 감시이므로 **고정 버킷 히스토그램**(메모리 상수)으로
집계한다. 요청 hot path 부담을 최소화하기 위해 파이프라인 HINCRBY+EXPIRE 1왕복만 쓴다.

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
        recent_p95: 최근 구간 대표 p95(최댓값). 데이터 없으면 None.
        baseline_p95: baseline 구간 p95 중앙값. 데이터 없으면 None.
        ratio: recent/baseline 비율. 계산 불가 시 None.
    """

    regressed: bool | None
    recent_p95: float | None
    baseline_p95: float | None
    ratio: float | None


def detect_regression(
    recent_p95: list[float | None],
    baseline_p95: list[float | None],
    threshold: float = REGRESSION_THRESHOLD,
) -> RegressionVerdict:
    """최근 p95(최댓값)가 baseline p95 중앙값 대비 threshold 배 이상이면 회귀로 판정.

    Args:
        recent_p95: 최근 구간(예: 최근 2일) 일별 p95 리스트(None 허용).
        baseline_p95: baseline 구간(예: 직전 5일) 일별 p95 리스트(None 허용).
        threshold: 회귀 배수(기본 1.5 = +50%).

    Returns:
        RegressionVerdict. 어느 한쪽이라도 유효 표본이 없으면 regressed=None.
    """
    recent_vals = [x for x in recent_p95 if x is not None]
    baseline_vals = [x for x in baseline_p95 if x is not None]
    if not recent_vals or not baseline_vals:
        return RegressionVerdict(None, None, None, None)
    recent_max = max(recent_vals)
    base_med = statistics.median(baseline_vals)
    if base_med <= 0:
        return RegressionVerdict(None, recent_max, base_med, None)
    ratio = recent_max / base_med
    return RegressionVerdict(ratio >= threshold, recent_max, base_med, ratio)
