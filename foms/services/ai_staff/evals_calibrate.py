"""'AI 시험' 채점하는 AI 맞추기 — 사장님 채점과 견준 두 비율 · 바로잡은 통과율 · 오차 폭(설계서 2026-11-23-brain-learning-upgrade 4.2).

순수 셈이다(DB · 네트워크 없음 · 새 패키지 없음 — 표준 :mod:`math` · :mod:`random` 만). 재료는 사장님이 채점한 초안(넘김 빼고)마다
(사장님 '보내도 돼요'인가, 채점하는 AI 가 통과라 했나) 짝과, 보이는 시험의 판정받은 초안 수 · 통과 수다.

- **두 비율**: 나쁜 답을 잡은 비율 = 사장님 '안 돼요' 가운데 AI 가 실패라 한 몫(:attr:`Calibration.caught` — 특이도) · 좋은 답을
  통과시킨 비율 = 사장님 '보내도 돼요' 가운데 AI 가 통과라 한 몫(:attr:`Calibration.passed_ok` — 민감도).
- **바로잡은 통과율**(Rogan–Gladen): ``(본 통과율 + 특이도 − 1) ÷ (민감도 + 특이도 − 1)`` 을 0 ~ 1 로 자른다. 분모가 0 이하면
  (채점이 동전 던지기보다 못하면) 정하지 않는다(``None``).
- **오차 폭**: 씨앗을 정한 모수 붓스트랩 — 세 비율을 저마다 이항 분포에서 :data:`ROUNDS` 번 다시 뽑아 바로잡은 값의 2.5 ·
  97.5 백분위수(선형 보간). 같은 재료면 늘 같은 값이다(:data:`SEED`). 이항 뽑기는 누적 확률 표(로그 감마)를 한 번 만들고 고른
  수를 이분 찾기로 바꾼다 — 파이썬 3.11 에도 있는 것만 쓴다.
- **보이는 때**: 채점한 초안이 :data:`MIN_GRADED` 개 이상이고 그 가운데 '보내도 돼요' · '안 돼요'가 저마다 :data:`MIN_EACH` 개
  이상일 때만 비율을 낸다. 그 전에는 수만(:attr:`Calibration.ready` 거짓).
"""

from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass
from typing import Optional, Sequence

__all__ = ["MIN_EACH", "MIN_GRADED", "ROUNDS", "SEED", "Calibration", "binomial_cdf", "bootstrap_range", "calibrate",
           "quantile", "rogan_gladen"]

MIN_GRADED, MIN_EACH = 30, 5
ROUNDS, SEED = 2000, 20261123
LOW, HIGH = 0.025, 0.975


@dataclass(frozen=True)
class Calibration:
    """채점 견주기 결과 — 채점한 초안 수 · 사장님 '보내도 돼요' · '안 돼요' 수 · 두 비율 · 바로잡은 통과율 · 오차 폭(없으면 ``None``)."""

    graded: int
    ok: int
    bad: int
    caught: Optional[float] = None
    passed_ok: Optional[float] = None
    corrected: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    observed: Optional[float] = None

    @property
    def ready(self) -> bool:
        """비율을 낼 만큼 모였나(모듈 설명 '보이는 때')."""
        return self.graded >= MIN_GRADED and self.ok >= MIN_EACH and self.bad >= MIN_EACH


def rogan_gladen(observed: float, sensitivity: float, specificity: float) -> Optional[float]:
    """바로잡은 통과율 — ``(observed + specificity − 1) / (sensitivity + specificity − 1)`` 을 0 ~ 1 로. 분모 ≤ 0 이면 ``None``."""
    denominator = sensitivity + specificity - 1
    if denominator <= 0:
        return None
    return min(1.0, max(0.0, (observed + specificity - 1) / denominator))


def binomial_cdf(n: int, p: float) -> list[float]:
    """이항 분포(시행 ``n`` · 확률 ``p``)의 누적 확률 표 — 길이 ``n + 1``, 마지막은 1. 로그 감마로 세어 큰 ``n`` 도 넘치지 않는다."""
    if p <= 0:
        return [1.0] * (n + 1)
    if p >= 1:
        return [0.0] * n + [1.0]
    log_p, log_q = math.log(p), math.log1p(-p)
    total, table = 0.0, []
    for k in range(n + 1):
        log_c = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
        total += math.exp(log_c + k * log_p + (n - k) * log_q)
        table.append(total)
    table[-1] = 1.0
    return table


def _draw(rng: random.Random, table: Sequence[float]) -> int:
    """누적 확률 표에서 하나 뽑기(이분 찾기)."""
    return min(bisect.bisect_right(table, rng.random()), len(table) - 1)


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """정렬된 값의 ``q`` 백분위수(선형 보간 — 값이 하나면 그 값)."""
    position = q * (len(sorted_values) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def bootstrap_range(observed: tuple[int, int], ok: tuple[int, int], bad: tuple[int, int], *, rounds: int = ROUNDS,
                    seed: int = SEED) -> Optional[tuple[float, float]]:
    """바로잡은 통과율의 오차 폭(2.5 · 97.5 백분위수). 짝은 (모두, 그 가운데 수) — 본 통과 · 사장님 '보내도 돼요'에서 AI 통과 ·
    사장님 '안 돼요'에서 AI 실패. 정해지는 판(분모 > 0)이 하나도 없으면 ``None``."""
    tables = [(n, binomial_cdf(n, hit / n)) for n, hit in (observed, ok, bad)]
    rng = random.Random(seed)
    values = []
    for _ in range(rounds):
        p, se, sp = (_draw(rng, table) / n for n, table in tables)
        value = rogan_gladen(p, se, sp)
        if value is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    return quantile(values, LOW), quantile(values, HIGH)


def calibrate(pairs: Sequence[tuple[bool, bool]], observed: tuple[int, int] = (0, 0)) -> Calibration:
    """채점 짝(사장님 '보내도 돼요'인가, AI 통과인가) · 보이는 시험의 (판정받은 초안 수, 통과 수) → :class:`Calibration`.

    모이기 전(:attr:`Calibration.ready` 거짓)에는 수만 채운다. 판정받은 초안이 없으면(옛 자로 돈 시험 등) 두 비율만 낸다.
    """
    ok = sum(1 for owner_ok, _judge in pairs if owner_ok)
    bad = len(pairs) - ok
    counts = Calibration(graded=len(pairs), ok=ok, bad=bad)
    if not counts.ready:
        return counts
    ok_pass = sum(1 for owner_ok, judge_pass in pairs if owner_ok and judge_pass)
    bad_fail = sum(1 for owner_ok, judge_pass in pairs if not owner_ok and not judge_pass)
    sensitivity, specificity = ok_pass / ok, bad_fail / bad
    total, passed = observed
    if total <= 0:
        return Calibration(len(pairs), ok, bad, caught=specificity, passed_ok=sensitivity)
    rate = passed / total
    corrected = rogan_gladen(rate, sensitivity, specificity)
    spread = bootstrap_range((total, passed), (ok, ok_pass), (bad, bad_fail)) if corrected is not None else None
    return Calibration(len(pairs), ok, bad, caught=specificity, passed_ok=sensitivity, corrected=corrected,
                       low=spread[0] if spread else None, high=spread[1] if spread else None, observed=rate)
