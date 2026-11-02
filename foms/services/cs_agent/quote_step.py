"""견적 계산 넣기 — 초안 차례(15분 바퀴 · 빠른 길 공통)에서 초안 두뇌 전에 견적 재료를 뽑고 계산기 값을 붙인다(플랜 C10-6).

관리 화면 '견적 계산 넣기'(``quote_calc_enabled``, 처음 끔)가 꺼져 있으면 아무것도 하지 않는다 — 초안 재료 · 허용 목록 · 두뇌
부름 모두 예전 그대로다. 켜져 있을 때 차례(설계서 17.4 길 1 ~ 3 · 5):

1. **견적 문의 같은가(코드)** — 마지막 공개 직원 글 뒤 손님 글에 견적 · 값 · 크기 말(:data:`QUOTE_CUE`)이 없으면 그만(뽑기를
   부르지 않는다 — 돈 · 시간은 견적 문의일 때만).
2. **계산기 설정 읽기** — 못 읽거나 라홈 제품이 없으면 그만(로그만 — 예전 그대로 초안).
3. **뽑기(두뇌 구조화 출력 한 번)** — :func:`.quote_brain.extract_quote`. 견적 문의(``quote_request``)가 아니면 계산 없이 초안.
   두뇌 오류(준비 안 됨 · 돈 상한 · 가림 · 못 씀)는 초안 두뇌와 같게 부르는 쪽이 다룬다(같은 ``except``). 뽑기가 '크기는 손님
   첨부에'(``size_in_attachment``)라 해도 두뇌 재료에 손님이 보낸 첨부 표시(:data:`.drafting_read.FILE_NOTE`)가 없으면 거짓으로
   돌린다(모델이 지어낸 첨부로 가로 묻기를 건너뛰지 않게 — :func:`customer_sent_file`).
4. **확인 날 · 제작 조건 · 계산** — 확인 날은 값 지문 기록(:func:`.quote_check.observe` — D74), 계산은
   :func:`.quote_calc.evaluate`. 제작 조건 줄을 못 읽으면 빈 규칙이 아니라 사람에게(R17-9). 결과가 사람에게(``human``)면 초안
   없이 넘김 기록만. 나머지는 ``calculator_lines`` · 허용 목록 · 직원 참고 줄을 초안 차례에 넘긴다 — 도면에서 크기 확인
   (``size_in_drawing``)도 여기다: 금액 없는 초안 + 직원 참고 줄로 직원에게 간다(넘김 까닭 코드는 기록의 ``code``).

결과 값(:meth:`QuoteStep.record` — 상태 · 두뇌 줄 · 허용 금액 줄)과 뽑기 호출의 토큰 · 돈 · 시간은 부르는 쪽
(:meth:`.drafting_pass.DraftPass.quote`)이 초안 두뇌 **전에** 차례 줄에 적는다(R17-1 · R17-3). 글은 로그에 싣지 않는다.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from sqlalchemy.exc import SQLAlchemyError

from foms.services.cs_agent.brain_prompt import ROLE_USER, DraftRequest, DraftResult
from foms.services.cs_agent.drafting_read import FILE_NOTE
from foms.services.cs_agent.knowledge_doc import ApprovedKnowledge
from foms.services.cs_agent.quote_brain import QUOTE_INTENT, QuoteAsk, extract_quote
from foms.services.cs_agent.quote_calc import HUMAN_RULE_UNREADABLE, RuleUnreadable, build_rules, evaluate
from foms.services.cs_agent.quote_check import PriceCheck, observe
from foms.services.cs_agent.quote_record import STATUS_HUMAN, STATUS_NOT_QUOTE, record_value
from foms.services.cs_agent.settings import read_settings
from foms.services.wdcalculator.catalog import Catalog, read_catalog

logger = logging.getLogger("foms.services.cs_agent.drafting")

__all__ = [
    "QUOTE_CUE", "SETTING", "STATUS_NOT_QUOTE", "QuoteStep", "customer_sent_file", "looks_like_quote", "merge_usage",
    "prepare",
]

SETTING = "quote_calc_enabled"  # 관리 화면 칸 이름
#: 견적 문의 같은 말(코드 거르기 — 뽑기를 부를지만 정한다. 정말 견적 문의인지는 뽑기가 정한다).
QUOTE_CUE = re.compile(
    r"견적|가격|금액|비용|얼마|단가|만\s?원|사이즈|치수|가로|세로|높이|천고|폭|"
    r"\d[\d,.]*\s*(?:mm|㎜|cm|㎝|m|미터|미리|센치|자)(?![a-z])", re.IGNORECASE)


@dataclass(frozen=True)
class QuoteStep:
    """견적 계산 넣기 결과. ``human`` 이 있으면 초안 없이 사람에게(까닭 코드), 아니면 ``lines`` · ``allowed`` · ``note`` 를 쓴다."""

    status: str
    lines: tuple[str, ...] = ()
    allowed: tuple[str, ...] = ()
    note: str = ""
    human: Optional[str] = None
    usage: Optional[QuoteAsk] = None
    code: Optional[str] = None

    def apply(self, request: DraftRequest) -> DraftRequest:
        """초안 재료에 계산 결과 줄을 넣는다(없으면 그대로)."""
        return dataclasses.replace(request, calculator_lines=self.lines) if self.lines else request

    def record(self) -> dict[str, Any]:
        """차례 줄 ``quote_lines`` 에 남길 값(:mod:`.quote_record`)."""
        return record_value(self.status, lines=self.lines, allowed=self.allowed, code=self.human or self.code)


def looks_like_quote(texts: Iterable[str]) -> bool:
    """손님 글에 견적 · 값 · 크기 말이 있나(:data:`QUOTE_CUE`)."""
    return any(QUOTE_CUE.search(text or "") for text in texts)


def customer_sent_file(request: DraftRequest) -> bool:
    """두뇌 재료(최근 공개 글)에 손님이 보낸 첨부 표시가 있나 — 직원이 보낸 그림은 세지 않는다."""
    return any(role == ROLE_USER and FILE_NOTE in text for role, text in request.messages)


def merge_usage(result: DraftResult, step: Optional[QuoteStep]) -> DraftResult:
    """초안 결과에 뽑기 호출의 토큰 · 돈 · 시간을 더한다(차례 줄의 돈이 그 차례 전부가 되게)."""
    usage = step.usage if step is not None else None
    if usage is None:
        return result
    return dataclasses.replace(
        result, input_tokens=result.input_tokens + usage.input_tokens,
        output_tokens=result.output_tokens + usage.output_tokens,
        cache_read_tokens=result.cache_read_tokens + usage.cache_read_tokens,
        cache_write_tokens=result.cache_write_tokens + usage.cache_write_tokens,
        cost_usd=result.cost_usd + usage.cost_usd, latency_ms=result.latency_ms + usage.latency_ms)


def _catalog(reader: Callable[[], Catalog], chat_id: str) -> Optional[Catalog]:
    """계산기 설정(못 읽거나 라홈 제품이 없으면 ``None`` — 예전 그대로 초안)."""
    try:
        catalog = reader()
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("[CS 견적] 계산기 설정을 못 읽어 계산 없이 초안 chat=%s why=%s", chat_id, type(exc).__name__)
        return None
    if not catalog.products_of():
        logger.warning("[CS 견적] 계산기에 라홈 제품이 없어 계산 없이 초안 chat=%s", chat_id)
        return None
    return catalog


def prepare(*, session: Any, knowledge: ApprovedKnowledge, request: DraftRequest, texts: Iterable[str],
            now: datetime.datetime, stop: Any, summary: Any, quoter: Optional[Callable[..., QuoteAsk]] = None,
            catalog_reader: Optional[Callable[[], Catalog]] = None,
            price_check: Optional[Callable[..., PriceCheck]] = None) -> Optional[QuoteStep]:
    """견적 계산 넣기 한 번(모듈 설명의 차례). ``None`` 이면 예전 그대로 초안(끔 · 견적 말 없음 · 계산기 못 읽음).

    Raises:
        BrainNotReady · SpendCapReached · MaskLeak · BrainUnavailable: 뽑기 두뇌 오류(초안 두뇌와 같게 다룬다).
    """
    if not looks_like_quote(texts) or not read_settings(session, log=False).get(SETTING):
        return None
    catalog = _catalog(catalog_reader or read_catalog, request.chat_id)
    if catalog is None:
        return None
    try:
        rules, unreadable = build_rules(knowledge.items), False
    except RuleUnreadable as exc:
        logger.warning("[CS 견적] 제작 조건 줄을 못 읽었다 — 견적 문의면 사람에게 item=%s", exc)
        rules, unreadable = (), True
    stop.check()  # 두뇌 전
    summary.brain_calls += 1
    ask = (quoter or extract_quote)(request, catalog, session=session, now=now)
    if ask.size_in_attachment and not customer_sent_file(request):
        ask = dataclasses.replace(ask, size_in_attachment=False)  # 손님 첨부가 없으면 예전처럼 가로를 묻는다
    if not ask.quote_request:
        step = QuoteStep(STATUS_NOT_QUOTE, usage=ask)
    elif unreadable:
        step = QuoteStep(STATUS_HUMAN, human=HUMAN_RULE_UNREADABLE, usage=ask)
    else:
        check = (price_check or observe)(session, catalog, now=now)
        outcome = evaluate(ask, catalog, rules, check=check, now=now)
        step = QuoteStep(outcome.status, lines=outcome.lines, allowed=outcome.allowed, note=outcome.note,
                         human=outcome.code if outcome.status == STATUS_HUMAN else None, usage=ask,
                         code=outcome.code)
    summary.quotes[step.status] = summary.quotes.get(step.status, 0) + 1
    logger.info("[CS 견적] chat=%s intent=%s status=%s code=%s", request.chat_id,
                QUOTE_INTENT if ask.quote_request else "other", step.status, step.human or step.code)
    return step
