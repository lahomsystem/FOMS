"""두뇌 — Claude API 를 부르는 한 곳. 가린 상담 글 · 승인 지식으로 답 초안 하나를 받는다(플랜 C3-2 · 설계서 11.1 D44).

초안 바퀴(:mod:`.drafting`)가 부른다. 바퀴는 선점 전에 :func:`check_ready` 로 준비를 한 번 본다(원장 R7-4).
모델 · 생각 깊이 · 최대 출력 · 시간 상한 · 다시 하기 · 캐시 · 대체 · 하루 상한(화면 값)은 관리 화면 설정
(:func:`.settings.read_settings`)을 부를 때마다 새로 읽는다 — 줄이 없으면 아래 상수 그대로다(처음 값 = 상수, 시험이 맞춘다).
돈 줄 · 오류 꼴은 :mod:`.brain_spend` 에 있고 이 모듈이 이름을 그대로 내보낸다. :func:`draft_reply` 의 순서(바꾸지 않는다):

1. **재료 확인** — 켠 브랜드(라홈)만 · 지식 브랜드가 같음 · 승인 지식이 있음 · 요청 본문을 쓰는 디버그 로거가 모두 꺼짐
   (:data:`SDK_BODY_LOGGERS` 와 그 아래 로거 — 켜면 SDK · HTTP 층이 본문 = 손님 글을 로그에 쓴다, R7-10) · 기본
   클라이언트면 env :data:`KEY_ENV` 가 있음.
2. **돈 막기** — env :data:`DAILY_CAP_ENV` (하루 상한, 달러)가 없거나 틀리면 부르지 않는다. 쓰는 상한은 env 와 화면 값 가운데
   작은 것이다(env 가 늘 천장). 오늘(KST) 돈 줄(SystemSetting :data:`SPEND_KEY` — 바로잡은 돈 + 부르는 중 예약)이 상한
   이상이면 :class:`SpendCapReached`. 읽은 뒤 커밋한다.
3. **가림** — 글마다 :func:`.masking.call_with_masked` (검사 0 일 때만 다음) → 만든 상담 글 덩어리를
   :func:`.masking.require_masked` 로 한 번 더(가림이 고장 나도 모델에 닿지 않게). 지시문 · 승인 지식은 회사 글이라 넣지
   않는다(기본 안내 전화 · 계좌가 들어 있을 수 있다).
4. **예약 → 부르기** — 보낼 때마다 먼저 최악값(:func:`.brain_prompt.worst_case_cost`)을 돈 줄 잠금 안에서 예약한다(R7-3 —
   바로잡은 돈 + 예약 + 이번 값이 상한을 넘으면 보내지 않는다). 그다음 ``client.with_options(timeout=…, max_retries=0)
   .beta.messages.create(…)``: 고른 모델, 생각은 adaptive(끌 수 없다), effort 는 늘 적는다, 구조화 출력, 도구 없음, 서버 쪽
   대체 ``fallbacks="default"`` (베타 :data:`FALLBACK_BETA` — 켬이고 그 모델이 받을 때만). **시간 초과는 다시 보내지
   않는다** — 서버가 이미 생성(과금)했을 수 있다. 다시 하기는 요청 바이트가 하나도 안 나간 연결 실패(연결 단계 오류)
   뿐이고, 모르면 다시 하지 않는다. SDK 는 429 를 스스로 다시 보내므로 SDK 다시 하기는 0 이다(설계서 11.1 의 6 ③).
5. **바로잡기** — 응답이 오면 예약을 실제 돈(:func:`.brain_prompt.usage_cost`)으로 바꾼다(쓸 수 없는 답이어도 센다).
   오류 응답(4xx · 5xx · 돈 상한)과 보내기 전 연결 실패는 0원, 응답이 없으면(시간 초과 · 보낸 뒤 끊김) 예약을 그대로 돈으로.
6. **결과** — 거절(``stop_reason == "refusal"``)이면 초안 없이 넘김(``stop_details.category`` 만 남김). 그 밖의 멈춤 ·
   틀린 JSON 은 :class:`BrainUnavailable` ``bad_response``. 401 · 403 은 키 · 권한 문제라 :class:`BrainNotReady`
   ``api_auth`` 다(돈 0 — 바퀴는 차례를 시도로 세지 않고 멈춘다).

보내기 전 검사(:func:`.checks.check_draft`, 매체를 꼭 넘김) · 직전 다시 읽기 · 넘김 코드 규칙은 부르는 쪽 몫이다.
손님 글 · 초안 · 직원 참고는 로그 · 오류 글 · repr 에 싣지 않는다 — 로그엔 상담 id · 코드 · 토큰 · 돈 · 시간만. SDK 오류는
이어 붙이지 않고(``from None``) 코드로 바꾼다 — SDK 오류 글에는 응답 본문이 들어 있다. 세션은 여러 번 커밋한다(돈 확인 ·
예약 · 바로잡기) — 부르는 쪽은 넘기기 전에 자기 쓰기를 마쳐 둔다.
"""

from __future__ import annotations

import datetime
import logging
import os
import time
from decimal import Decimal
from typing import Any, Optional

import anthropic
import httpx2

from foms.services.cs_agent import brain_prompt as prompt
from foms.services.cs_agent.brain_prompt import DraftRequest, DraftResult
from foms.services.cs_agent.brain_spend import (  # 코드 · 돈 줄 이름은 예전처럼 ``brain.`` 으로도 쓴다(초안 바퀴 · 시험)
    API_AUTH, API_ERROR, API_SPEND_LIMIT, BAD_RESPONSE, BRAND_MISMATCH, BRAND_NOT_ENABLED, CAP_INVALID, CAP_MISSING,
    DAILY_CAP_ENV, DAILY_CAP_REACHED, NO_API_KEY, NO_KNOWLEDGE, RATE_LIMITED, SDK_DEBUG_LOGGING, SPEND_KEY,
    SPEND_RECORD_INVALID, TIMEOUT, BrainError, BrainNotReady, BrainUnavailable, SpendCapReached, add_spend,
    check_budget, daily_cap_usd, kst_now, reserve_spend, settle_spend, spent_today,
)
from foms.services.cs_agent.knowledge_doc import ApprovedKnowledge
from foms.services.cs_agent.masking import call_with_masked, require_masked
from foms.services.cs_agent.settings import PanelSettings, read_settings
from models import SystemSetting  # noqa: F401 — 부르는 쪽 · 시험이 ``brain.SystemSetting`` 으로 돈 줄을 읽는다

logger = logging.getLogger(__name__)

__all__ = [
    "BATCH_RETRIES", "BATCH_TIMEOUT_SECONDS", "DAILY_CAP_ENV", "EFFORTS", "FALLBACK_BETA", "KEY_ENV", "MAX_TOKENS",
    "MODEL", "PRICES", "REALTIME_RETRIES", "REALTIME_TIMEOUT_SECONDS", "SDK_BODY_LOGGERS", "SPEND_KEY", "BrainError",
    "BrainNotReady", "BrainUnavailable", "DraftRequest", "DraftResult", "SpendCapReached", "add_spend", "check_budget",
    "check_ready", "daily_cap_usd", "draft_reply", "reserve_spend", "settle_spend", "spent_today",
]

MODEL = prompt.MODEL  # claude-opus-5-5 — 관리 화면 처음 값
PRICES = prompt.PRICES
#: 길마다 effort(처음 값) — Opus 5.5 기본은 medium 이라 늘 적는다. 그림자 1주 뒤 시험 묶음 점수 · 지연으로 다시 정한다(11.1 의 1).
EFFORTS: dict[str, str] = {prompt.PURPOSE_DRAFT: "high", prompt.PURPOSE_INTENT: "low"}
#: 출력 상한(처음 값 — 생각도 이 안에서 쓴다, 보이지 않아도 센다). 최악값 예약은 이 수 전부를 출력 단가로 센다.
MAX_TOKENS: dict[str, int] = {prompt.PURPOSE_DRAFT: 16000, prompt.PURPOSE_INTENT: 8000}
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # ``fallbacks="default"`` 짝(배열 꼴은 -06-01 — 섞으면 400)
FALLBACKS = "default"
#: 처음 값 — 실시간 길: 45초 · 다시 하기 0. 15분 루프(밤 · 견적) 길: 90초 · 보내기 전 연결 실패만 한 번 더(11.1 의 5 ·
#: 원장 R7-3). 화면은 실시간 다시 하기 · 두 길 시간만 바꾼다 — 15분 루프 다시 하기는 이 상수 그대로다.
REALTIME_TIMEOUT_SECONDS, REALTIME_RETRIES = 45.0, 0
BATCH_TIMEOUT_SECONDS, BATCH_RETRIES = 90.0, 1
RETRY_BACKOFF_SECONDS = 2.0
KEY_ENV = "ANTHROPIC_API_KEY"  # 이름만 — 값은 WORKER env 에만(C3-0, 사장님이 넣는다)
#: 요청 본문(가린 손님 글 · 승인 지식)을 디버그 로그에 쓸 수 있는 로거 — 이 이름과 이미 있는 그 아래 로거 가운데 하나라도
#: DEBUG 면 부르지 않는다(원장 R7-10 — 본문은 ``anthropic._base_client`` 가, 연결 내용은 ``httpcore2.connection`` 이 쓴다).
SDK_BODY_LOGGERS: tuple[str, ...] = ("anthropic", "anthropic._base_client", "httpx2", "httpcore2", "httpx", "httpcore")

#: 콘솔 돈 상한 응답(설계서 11.1 의 6 ③): 429 ``error.details.error_code`` · 400 ``invalid_request_error`` 글 머리.
SPEND_LIMIT_ERROR_CODE = "enforced_spend_limit_reached"
_SPEND_LIMIT_PREFIXES = ("you have reached your specified api usage limits",
                         "you have reached your specified workspace api usage limits")
#: 키 · 권한 거절 — 설정 문제라 차례 탓이 아니다(원장 R7-4).
_AUTH_STATUSES = frozenset({401, 403})
#: 요청 바이트가 하나도 안 나간 전송 오류(연결 · 연결 풀 단계). 이것만 확실히 0원이고, 연결 실패면 밤 길에서 한 번 더 한다.
_NEVER_SENT = (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout)
STOP_REFUSAL = "refusal"
_STOP_ANSWERED = frozenset({"end_turn", "stop_sequence"})
HANDOFF_REFUSED = "refused"  # 코드만 쓰는 넘김 까닭(모델은 고르지 못한다)
_sleep = time.sleep  # 시험이 바꾼다


# ── 준비 ─────────────────────────────────────────────────────────────────
def _body_logging_on() -> bool:
    """요청 본문을 쓸 수 있는 로거 가운데 DEBUG 가 켜진 것이 있나(:data:`SDK_BODY_LOGGERS` + 이미 있는 그 아래 로거)."""
    children = tuple(f"{name}." for name in SDK_BODY_LOGGERS)
    names = {*SDK_BODY_LOGGERS, *(n for n in list(logging.Logger.manager.loggerDict) if n.startswith(children))}
    return any(logging.getLogger(name).isEnabledFor(logging.DEBUG) for name in names)


def _check_material(brand: str, knowledge: ApprovedKnowledge) -> None:
    """켠 브랜드 · 같은 브랜드의 승인 지식이 있나. 아니면 :class:`BrainNotReady`."""
    if brand not in prompt.ENABLED_BRANDS:
        raise BrainNotReady(BRAND_NOT_ENABLED)
    if knowledge.brand != brand:
        raise BrainNotReady(BRAND_MISMATCH)
    if knowledge.problem or not knowledge.items:
        raise BrainNotReady(NO_KNOWLEDGE)


def _check_environment(*, need_key: bool) -> None:
    """본문을 쓰는 디버그 로거가 모두 꺼짐 · (기본 클라이언트면) 키가 있음. 아니면 :class:`BrainNotReady`."""
    if _body_logging_on():
        raise BrainNotReady(SDK_DEBUG_LOGGING)
    if need_key and not (os.environ.get(KEY_ENV) or "").strip():
        raise BrainNotReady(NO_API_KEY)


def _check_ready(request: DraftRequest, *, need_key: bool) -> None:
    """재료 · 설정 확인(부르기 전 · DB 전). 하나라도 틀리면 :class:`BrainNotReady`."""
    _check_material(request.brand, request.knowledge)
    _check_environment(need_key=need_key)


def check_ready(brand: str, knowledge: ApprovedKnowledge, *, session: Any = None,
                now: Optional[datetime.datetime] = None, client: Any = None) -> Decimal:
    """두뇌를 부를 준비가 됐나 — 초안 바퀴가 고르기 · 선점 전에 한 번 부른다(원장 R7-4). 쓰는 하루 상한(달러)을 돌려준다.

    본다: 켠 브랜드 · 같은 브랜드 승인 지식 · 본문을 쓰는 디버그 로거 · 키(``client`` 를 안 주면) · 하루 상한 env · 돈 줄 꼴 ·
    오늘 돈(예약 포함)이 **지금** 상한(env 와 화면 값 가운데 작은 것) 아래이고 초안 한 번(:func:`_floor_reserve`)을 부를 만큼
    남았는가. 그날 상한에 닿았어도 상한을 올리면 다음 바퀴부터 다시 지난다(멈춤은 지금 상한과 오늘 돈으로만 정한다).
    돈 줄을 읽은 트랜잭션은 커밋해 닫는다.

    Raises:
        BrainNotReady: 준비 안 됨(까닭은 코드). SpendCapReached: 오늘 상한에 이미 닿음 · 한 번 부를 만큼도 안 남음.
    """
    _check_material(brand, knowledge)
    _check_environment(need_key=client is None)
    env_cap = daily_cap_usd()
    session = session if session is not None else _default_session()
    cfg = read_settings(session, log=False)  # 설정 경고는 초안 바퀴가 바퀴마다 한 번 남긴다
    cap = cfg.daily_cap(env_cap)
    spent = check_budget(session, cap=cap, now=kst_now(now))
    need = _floor_reserve(cfg)
    if spent + need > cap:
        session.commit()
        logger.warning("[CS 두뇌] 남은 돈이 초안 한 번도 안 돼 부르지 않는다 key=%s spent=%s need=%s cap=%s",
                       SPEND_KEY, spent, need, cap)
        raise SpendCapReached(DAILY_CAP_REACHED)
    session.commit()
    return cap


def _floor_reserve(cfg: PanelSettings) -> Decimal:
    """초안 한 번이 적어도 예약할 돈 — 상담 글 · 지식이 없는 가장 작은 요청의 최악값(실제 요청은 늘 이보다 크다)."""
    model = cfg.model_for(prompt.PURPOSE_DRAFT)
    smallest: dict[str, Any] = {"model": model, "max_tokens": cfg.max_tokens_for(prompt.PURPOSE_DRAFT)}
    if cfg.fallback_on(model):
        smallest["fallbacks"] = FALLBACKS
    return prompt.worst_case_cost(smallest)


# ── 부르기 ───────────────────────────────────────────────────────────────
def _params(request: DraftRequest, conversation: str, now: datetime.datetime,
            cfg: PanelSettings) -> dict[str, Any]:
    """``beta.messages.create`` 인자 — 앞부분(system)에는 바뀌는 값을 넣지 않는다. 모델 · 깊이 · 출력 · 캐시 · 대체는 설정."""
    knowledge = request.knowledge
    model = cfg.model_for(request.purpose)
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": cfg.max_tokens_for(request.purpose),
        "thinking": {"type": "adaptive"},  # 끌 수 없다 — 대체 모델(Opus 4.8)은 빼면 생각 없이 돌아 적어 둔다
        "output_config": {"effort": cfg.effort_for(request.purpose),
                          "format": {"type": "json_schema", "schema": prompt.output_schema(knowledge)}},
        "system": prompt.system_blocks(request.brand, knowledge, cache_ttl=cfg.cache_ttl_for(request.daytime)),
        "messages": [{"role": "user", "content": prompt.task_text(
            purpose=request.purpose, chat_id=request.chat_id, medium=request.medium, now=now,
            calculator_lines=request.calculator_lines, conversation=conversation, cases=request.cases)}],
    }
    if cfg.fallback_on(model):  # Haiku 5.5 는 서버 쪽 대체가 없다 — 보내지 않는다
        params.update(betas=[FALLBACK_BETA], fallbacks=FALLBACKS)
    return params


def _spend_limited(exc: anthropic.APIStatusError) -> bool:
    """콘솔 돈 상한 응답인가 — 429 ``details.error_code`` 또는 400 · 429 글 머리(본문은 읽기만 하고 옮기지 않는다)."""
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    if details.get("error_code") == SPEND_LIMIT_ERROR_CODE:
        return True
    message = error.get("message") if isinstance(error.get("message"), str) else ""
    return exc.status_code in (400, 429) and message.strip().lower().startswith(_SPEND_LIMIT_PREFIXES)


def _failure_of(exc: anthropic.APIError) -> tuple[BrainError, bool, bool]:
    """SDK 오류 → (올릴 오류, 한 번 더 해도 되는가, 서버가 생성했을 수 있는가 = 예약을 돈으로 칠까).

    한 번 더는 요청 바이트가 안 나간 연결 실패만(SDK 가 이어 붙인 전송 오류로 가린다 — 모르면 안 한다). 시간 초과는
    다시 하지 않는다. 오류 응답(4xx · 5xx)은 돈 0, 응답이 없으면 생성됐을 수 있다.
    """
    never_sent = isinstance(exc.__cause__, _NEVER_SENT)
    if isinstance(exc, anthropic.APITimeoutError):  # APIConnectionError 보다 먼저(그 아래 종류다)
        return BrainUnavailable(TIMEOUT), False, not never_sent
    if isinstance(exc, anthropic.APIConnectionError):
        return BrainUnavailable(API_ERROR), never_sent, not never_sent
    if isinstance(exc, anthropic.APIStatusError):
        meta = {"status": exc.status_code, "request_id": exc.request_id}
        if _spend_limited(exc):
            return SpendCapReached(API_SPEND_LIMIT, **meta), False, False
        if exc.status_code in _AUTH_STATUSES:
            return BrainNotReady(API_AUTH, **meta), False, False
        if isinstance(exc, anthropic.RateLimitError):
            return BrainUnavailable(RATE_LIMITED, **meta), False, False
        if isinstance(exc, anthropic.DeadlineExceededError):  # 서버 쪽 시간 초과 — 생성했을 수 있다
            return BrainUnavailable(TIMEOUT, **meta), False, True
        return BrainUnavailable(API_ERROR, **meta), False, False
    if isinstance(exc, anthropic.APIResponseValidationError):  # 답은 왔다 — 생성됐다
        return BrainUnavailable(BAD_RESPONSE), False, True
    return BrainUnavailable(API_ERROR), False, True


def _limits(cfg: PanelSettings, *, realtime: bool) -> tuple[float, int]:
    """길마다 (시간 상한 초, 다시 하기 수) — 실시간 길은 둘 다 설정, 15분 루프 길은 시간만 설정(다시 하기는 상수)."""
    if realtime:
        return float(cfg.get("realtime_timeout_s")), int(cfg.get("realtime_retries"))
    return float(cfg.get("batch_timeout_s")), BATCH_RETRIES


def _send(api: Any, params: dict[str, Any], *, realtime: bool, session: Any, cap: Decimal,
          now: datetime.datetime, cfg: PanelSettings) -> tuple[Any, int, Decimal]:
    """부른다(SDK 다시 하기 0 — 다시 하기는 여기서 센다). 보낼 때마다 최악값을 먼저 예약한다. (응답, 걸린 ms, 예약)."""
    timeout, retries = _limits(cfg, realtime=realtime)
    messages = api.with_options(timeout=timeout, max_retries=0).beta.messages
    reserve = prompt.worst_case_cost(params)
    started = time.monotonic()
    for attempt in range(retries + 1):
        reserve_spend(session, reserve, cap=cap, now=now)
        try:
            response = messages.create(**params)
        except anthropic.APIError as exc:
            failure, retryable, maybe_billed = _failure_of(exc)
            settle_spend(session, reserve, reserve if maybe_billed else Decimal(0), now=now)
        else:
            return response, int((time.monotonic() - started) * 1000), reserve
        logger.warning("[CS 두뇌] 호출 실패 code=%s status=%s request_id=%s attempt=%d kept_reservation=%s",
                       failure.code, failure.status, failure.request_id, attempt + 1, maybe_billed)
        if not retryable or attempt >= retries:
            raise failure from None
        _sleep(RETRY_BACKOFF_SECONDS)
    raise AssertionError("닿지 않는 자리")  # pragma: no cover


def _result(request: DraftRequest, response: Any, *, tokens: prompt.Tokens, cost: Decimal, latency_ms: int,
            model: str, effort: str, cache_marked: bool) -> DraftResult:
    """응답 → 결과. 거절은 초안 없이 넘김, 그 밖의 멈춤 · 틀린 꼴은 :class:`BrainUnavailable` (돈은 이미 셌다)."""
    stop = getattr(response, "stop_reason", None)
    common: dict[str, Any] = dict(
        model=str(getattr(response, "model", None) or model), effort=effort,
        input_tokens=tokens.input, output_tokens=tokens.output, cache_read_tokens=tokens.cache_read,
        cache_write_tokens=tokens.cache_write, cost_usd=cost, latency_ms=latency_ms, stop_reason=stop,
        fallback_used=prompt.fallback_served(response) and stop != STOP_REFUSAL, cache_marked=cache_marked)
    logger.info("[CS 두뇌] chat=%s purpose=%s model=%s effort=%s stop=%s fallback=%s in=%d out=%d cache_read=%d "
                "cache_write=%d cost=%s ms=%d", request.chat_id, request.purpose, common["model"], common["effort"],
                stop, common["fallback_used"], tokens.input, tokens.output, tokens.cache_read, tokens.cache_write,
                cost, latency_ms)
    if stop == STOP_REFUSAL:
        category = getattr(getattr(response, "stop_details", None), "category", None)
        logger.warning("[CS 두뇌] 거절 — 초안 없이 사람에게 chat=%s category=%s", request.chat_id, category)
        return DraftResult(intent=prompt.INTENT_OTHER, draft="", evidence_ids=(), handoff=True,
                           handoff_reason=HANDOFF_REFUSED, staff_note="", refused=True,
                           refusal_category=category if isinstance(category, str) else None, **common)
    if stop not in _STOP_ANSWERED:
        logger.warning("[CS 두뇌] 쓸 수 없는 멈춤 chat=%s stop=%s", request.chat_id, stop)
        raise BrainUnavailable(BAD_RESPONSE)
    try:
        out = prompt.read_output(prompt.answer_text(response), intents=prompt.intent_choices(request.knowledge),
                                 evidence_ids=prompt.evidence_choices(request.knowledge))
    except prompt.OutputError as exc:
        logger.warning("[CS 두뇌] 출력 꼴이 틀렸다 chat=%s why=%s", request.chat_id, exc)
        raise BrainUnavailable(BAD_RESPONSE) from None
    handoff = out["handoff"]
    reason = prompt.HANDOFF_NONE
    if handoff:  # 넘기면 까닭이 있어야 한다 — 'none' 이면 '모름'으로
        reason = out["handoff_reason"] if out["handoff_reason"] != prompt.HANDOFF_NONE else prompt.HANDOFF_UNSURE
    draft = "" if handoff or request.purpose == prompt.PURPOSE_INTENT else out["draft"]
    return DraftResult(intent=out["intent"], draft=draft, evidence_ids=out["evidence_ids"], handoff=handoff,
                       handoff_reason=reason, staff_note=out["staff_note"], refused=False, **common)


def _default_session() -> Any:
    """세션을 안 넘기면 앱 기본 세션(가져올 때 DB 를 묶지 않으려고 부를 때 읽는다)."""
    from db import db_session

    return db_session


def _default_client() -> Any:
    """SDK 기본 클라이언트 — 부를 때 처음 만든다(가져올 때 만들지 않아 키 없이도 import 된다). 키는 env 의 API 키."""
    try:
        return anthropic.Anthropic()
    except anthropic.AnthropicError:  # 자격 증명 · 설정 파일을 못 읽음
        raise BrainNotReady(NO_API_KEY) from None


def draft_reply(request: DraftRequest, *, client: Any = None, session: Any = None,
                now: Optional[datetime.datetime] = None) -> DraftResult:
    """두뇌 한 번 — 확인 → 설정 · 돈 확인 → 가림 → 예약 · 부르기 → 바로잡기 → 결과(모듈 설명의 순서).

    Args:
        request: 재료(:class:`DraftRequest` — 글은 가리기 전 원문).
        client: Anthropic 클라이언트(시험은 가짜). 없으면 부를 때 ``anthropic.Anthropic()`` 을 만들고 끝나면 닫는다.
        session: DB 세션 — 설정 · 돈 줄을 읽고 · 예약하고 · 바로잡는다. 여러 번 커밋하니 넘기기 전에 부르는 쪽 쓰기를 마쳐 둔다.
        now: 지금(시간대 있는 값, 시험 주입). 돈의 날(KST)과 프롬프트의 '지금'.

    Returns:
        :class:`DraftResult` — 거절이면 ``refused`` · ``handoff`` 이고 초안이 없다.

    Raises:
        BrainNotReady: 브랜드 · 지식 · 키 · 상한 env · 돈 줄 · 디버그 로그(부르지 않음) · 401 · 403(돈 0).
        SpendCapReached: 오늘 상한(예약 포함)에 닿음 · 콘솔 상한 응답(다시 하지 않음).
        MaskLeak: 가린 뒤에도 개인정보 꼴이 남음(부르지 않음 — 칸별 숫자만).
        BrainUnavailable: 시간 초과 · 429 · API 오류 · 쓸 수 없는 답.
    """
    now = kst_now(now)
    _check_ready(request, need_key=client is None)
    env_cap = daily_cap_usd()
    session = session if session is not None else _default_session()
    cfg = read_settings(session, log=False)  # 부를 때마다 새로 — 화면에서 저장하면 다음 차례부터
    cap = cfg.daily_cap(env_cap)
    check_budget(session, cap=cap, now=now)
    session.commit()  # 부르는 동안 읽기 트랜잭션을 열어 두지 않는다('idle in transaction' 방지)
    roles = [role for role, _ in request.messages]

    def call(masked: list[str]) -> DraftResult:
        conversation = prompt.render_conversation(list(zip(roles, masked)))
        require_masked(conversation)  # 모델에 가는 손님 글 전부 — 가림이 고장 나도 여기서 멈춘다
        params = _params(request, conversation, now, cfg)
        api = client if client is not None else _default_client()
        try:
            response, latency_ms, reserved = _send(api, params, realtime=request.realtime, session=session, cap=cap,
                                                   now=now, cfg=cfg)
        finally:
            if client is None:
                api.close()
        tokens, cost = prompt.usage_cost(response, model=params["model"])
        settle_spend(session, reserved, cost, now=now)
        return _result(request, response, tokens=tokens, cost=cost, latency_ms=latency_ms, model=params["model"],
                       effort=params["output_config"]["effort"],
                       cache_marked=any("cache_control" in block for block in params["system"]))

    return call_with_masked([text for _, text in request.messages], call,
                            customer_names=request.customer_names, staff_names=request.staff_names)
