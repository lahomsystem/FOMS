"""학습 길 두뇌 부르기 한 곳 — 사진 설명(:mod:`.photo_desc`) · 주간 고침 안(:mod:`.weekly_fix`)이 같이 쓴다(설계서 17.6.1 (d) · (e)).

- **켜는 조건**(:func:`off_reason`): 패널 그 길 칸 켬 · 비상 정지 아님(:func:`.turns.read_switch`) · 초안 스위치가 꺼지지 않음 ·
  패널 '학습 돈 상한'이 있음. 하나라도 아니면 부르지 않는다(학습 돈 상한을 비우면 학습 길은 막는 쪽으로 닫힌다).
- **돈 두 줄**(R10-22): 보내기 전 최악값을 **학습 돈 줄**(:data:`.brain_spend.LEARNING_SPEND_KEY`)에 학습 돈 상한으로 예약하고,
  부르기는 두뇌 한 곳(:func:`.brain._send`)이 **하루 돈 줄**에 하루 상한으로 한 번 더 예약한다 — 학습 돈은 하루 돈 안에서도
  센다. 응답이 오면 두 줄 모두 실제 값으로 바로잡는다. 부르기 실패면 하루 줄은 :func:`.brain._send` 가 바로잡고, 학습 줄은
  키 · 권한 거절(돈 0)과 하루 상한 막힘만 0 으로, 그 밖에는 최악값을 남긴다(막는 쪽).
- 다시 하기 0 · 시간 상한은 부르는 쪽이 정한다. 모델 글 · 사진 · 상담 글은 로그에 싣지 않는다.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from foms.services.cs_agent import brain
from foms.services.cs_agent import brain_prompt as prompt
from foms.services.cs_agent.brain_spend import (
    LEARNING_SPEND_KEY, BrainNotReady, SpendCapReached, check_budget, daily_cap_usd, reserve_spend, settle_spend,
)
from foms.services.cs_agent.edit_detail_settings import switch_value
from foms.services.cs_agent.settings import PanelSettings, read_settings
from foms.services.cs_agent.turns import DRAFT_OFF, draft_mode, read_switch

logger = logging.getLogger(__name__)

__all__ = [
    "LEARNING_CAP_FIELD", "OFF_CAP", "OFF_DRAFT", "OFF_STOP", "OFF_SWITCH", "Called", "call_learning", "learning_cap",
    "off_reason",
]

LEARNING_CAP_FIELD = "learning_cap_usd_panel"
OFF_SWITCH, OFF_STOP, OFF_DRAFT, OFF_CAP = "switch_off", "emergency_stop", "draft_off", "no_learning_cap"


@dataclass(frozen=True)
class Called:
    """부르기 한 번 — 응답 · 토큰 · 돈(대체까지 넣은 실제 값) · 걸린 ms."""

    response: Any
    tokens: prompt.Tokens
    cost: Decimal
    latency_ms: int


def learning_cap(cfg: PanelSettings) -> Optional[Decimal]:
    """패널 학습 돈 상한(달러) — 비었거나 틀리면 ``None``(학습 길을 부르지 않는다)."""
    raw = cfg.get(LEARNING_CAP_FIELD)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def off_reason(session: Any, field: str) -> tuple[Optional[str], PanelSettings]:
    """이 학습 길을 지금 부르면 안 되는 까닭 코드(되면 ``None``)와 새로 읽은 패널 설정."""
    cfg = read_settings(session, log=False)
    if not switch_value(cfg, field):
        return OFF_SWITCH, cfg
    if not read_switch(session):
        return OFF_STOP, cfg
    if draft_mode(session) == DRAFT_OFF:
        return OFF_DRAFT, cfg
    if learning_cap(cfg) is None:
        return OFF_CAP, cfg
    return None, cfg


def _limited(cfg: PanelSettings, timeout_s: float) -> PanelSettings:
    """이 부르기의 시간 상한 · 다시 하기 0(시간 초과는 다시 보내지 않는다)."""
    values = {**cfg.values, "realtime_timeout_s": max(1, int(timeout_s)), "realtime_retries": 0}
    return PanelSettings(values, cfg.version, cfg.fallback_fields)


def call_learning(session: Any, params: dict[str, Any], *, cfg: PanelSettings, now: datetime.datetime,
                  timeout_s: float, client: Any = None) -> Called:
    """학습 길 한 번 부르기(모듈 설명의 돈 두 줄). 커밋한다.

    Raises:
        BrainNotReady: 키 · 하루 상한 env · 돈 줄 꼴 · 디버그 로그 · 401 · 403. SpendCapReached: 학습 · 하루 상한.
        BrainUnavailable: 시간 넘김 · 오류 응답.
    """
    cap = learning_cap(cfg)
    if cap is None:
        raise BrainNotReady(OFF_CAP)
    brain._check_environment(need_key=client is None)  # noqa: SLF001 — 두뇌 한 곳의 준비 확인
    day_cap = cfg.daily_cap(daily_cap_usd())
    check_budget(session, cap=day_cap, now=now)
    check_budget(session, cap=cap, now=now, key=LEARNING_SPEND_KEY)
    worst = prompt.worst_case_cost(params)
    reserve_spend(session, worst, cap=cap, now=now, key=LEARNING_SPEND_KEY)
    api = client if client is not None else brain._default_client()  # noqa: SLF001
    try:
        response, latency_ms, reserved = brain._send(api, params, realtime=True, session=session, cap=day_cap,  # noqa: SLF001
                                                     now=now, cfg=_limited(cfg, timeout_s))
    except (BrainNotReady, SpendCapReached):
        settle_spend(session, worst, Decimal(0), now=now, key=LEARNING_SPEND_KEY)  # 보내지 않았거나 돈 0 인 거절
        raise
    except brain.BrainError:
        settle_spend(session, worst, worst, now=now, key=LEARNING_SPEND_KEY)  # 청구됐을 수 있다 — 최악값을 남긴다
        raise
    finally:
        if client is None:
            api.close()
    tokens, cost = prompt.usage_cost(response, model=params["model"])
    settle_spend(session, reserved, cost, now=now)
    settle_spend(session, worst, cost, now=now, key=LEARNING_SPEND_KEY)
    return Called(response=response, tokens=tokens, cost=cost, latency_ms=latency_ms)
