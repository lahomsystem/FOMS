"""회사 지식 AI 부르기 한 곳 — 직원 챗봇 · 빈 지식 묶기 · AI 제안 부딪침 판정(설계서 10.2 '모델' · 6절 관문 ② · 10.3).

**새 클라이언트를 만들지 않는다** — 상담 두뇌의 부르기(:func:`foms.services.cs_agent.brain._send` — 최악값 예약 · 시간 초과는
다시 보내지 않음 · 오류 꼴 · SDK 다시 하기 0)와 돈 계산(:func:`foms.services.cs_agent.brain_prompt.worst_case_cost` ·
:func:`~foms.services.cs_agent.brain_prompt.usage_cost`)을 그대로 쓰고 **돈 줄만 따로**(:data:`.chat_settings.SPEND_KEY` — 상담 초안
하루 상한과 따로) 쓴다. 상한은 :func:`.chat_settings.daily_cap`(화면 값 · env 천장 — 비우면 부르지 않음).

- 준비 확인: 본문을 쓰는 디버그 로거가 꺼짐 · (기본 클라이언트면) 키 env 가 있음(:func:`foms.services.cs_agent.brain._check_environment`).
- 생각은 adaptive · effort 는 늘 적는다 · 구조화 출력 하나 · 도구 없음 · 서버 쪽 대체는 보내지 않는다(돈 예약을 늘리지 않게).
- 거절 · 쓸 수 없는 멈춤은 :class:`BrainUnavailable`. 글은 로그에 싣지 않는다(코드 · 돈 · 시간만). 세션을 여러 번 커밋한다.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from foms.services.brain.chat_settings import SPEND_KEY, ChatSettings, daily_cap
from foms.services.cs_agent import brain
from foms.services.cs_agent import brain_prompt as prompt
from foms.services.cs_agent.brain_spend import (
    BAD_RESPONSE, BrainNotReady, BrainUnavailable, check_budget, settle_spend,
)
from foms.services.cs_agent.settings import PanelSettings

logger = logging.getLogger(__name__)

NO_CAP = "chat_cap_missing"
REFUSED = "refused"
_ANSWERED = frozenset({"end_turn", "stop_sequence"})


@dataclass(frozen=True)
class Answered:
    """부르기 한 번 — 마지막 글 블록 · 실제 돈 · 걸린 ms · 답한 모델."""

    text: str
    cost: Decimal
    latency_ms: int
    model: str


def build_params(*, model: str, effort: str, max_tokens: int, system: str, user: str,
                 schema: dict[str, Any]) -> dict[str, Any]:
    """``beta.messages.create`` 인자(상담 두뇌 :func:`foms.services.cs_agent.brain._params` 와 같은 꼴 — 대체 없음)."""
    return {"model": model, "max_tokens": int(max_tokens), "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            "system": [{"type": "text", "text": system}], "messages": [{"role": "user", "content": user}]}


def call_model(session: Any, params: dict[str, Any], *, cfg: ChatSettings, now: datetime.datetime,
               timeout_s: Optional[float] = None, client: Any = None) -> Answered:
    """한 번 부른다 — 상한 확인 → 예약 · 부르기(상담 두뇌 길) → 바로잡기 → 멈춤 확인.

    Raises:
        BrainNotReady: 하루 상한 비움 · env 틀림 · 키 없음 · 디버그 로그 · 401 · 403.
        SpendCapReached: 오늘 챗봇 돈(예약 포함)이 상한에 닿음.
        BrainUnavailable: 시간 초과 · 429 · API 오류 · 거절 · 쓸 수 없는 멈춤.
    """
    cap = daily_cap(cfg)
    if cap is None:
        raise BrainNotReady(NO_CAP)
    brain._check_environment(need_key=client is None)  # noqa: SLF001 — 두뇌 한 곳의 준비 확인
    check_budget(session, cap=cap, now=now, key=SPEND_KEY)
    session.commit()  # 부르는 동안 읽기 트랜잭션을 열어 두지 않는다
    limits = PanelSettings({"realtime_timeout_s": int(timeout_s or cfg.get("timeout_s")), "realtime_retries": 0})
    api = client if client is not None else brain._default_client()  # noqa: SLF001
    try:
        response, latency_ms, reserved = brain._send(api, params, realtime=True, session=session, cap=cap,  # noqa: SLF001
                                                     now=now, cfg=limits, spend_key=SPEND_KEY)
    finally:
        if client is None:
            api.close()
    _tokens, cost = prompt.usage_cost(response, model=params["model"])
    settle_spend(session, reserved, cost, now=now, key=SPEND_KEY)
    stop = getattr(response, "stop_reason", None)
    logger.info("[회사 지식 AI] model=%s stop=%s cost=%s ms=%d", params["model"], stop, cost, latency_ms)
    if stop not in _ANSWERED:
        raise BrainUnavailable(REFUSED if stop == "refusal" else BAD_RESPONSE)
    return Answered(text=prompt.answer_text(response), cost=cost, latency_ms=latency_ms,
                    model=str(getattr(response, "model", None) or params["model"]))
