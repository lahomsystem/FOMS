"""초안 차례의 '주문 확인해 답하기' — 주문 문의 때만 본인을 확인해 ERP 주문 세부를 두뇌에 싣는다(설계서 2026-11-12 온톨로지 5.6).

사장님 11-12 D189: "고객 확인이 안 될 때 고객 이름, 전화번호를 물어보고 ERP 에서 해당 주문 건의 정보를 파악 … 매번 하는 게 아니라
고객이 일정 변경 등의 문의가 들어왔을 때만". D190: 찾은 주문은 **바로 초안에** 쓴다(직원 참고만 단계 없음). 관리 칸 '주문 확인해
답하기'(:data:`.onto_settings.ONTO_ORDER_FIELD`, 처음 끔)가 꺼져 있으면 설정 한 번 읽기뿐 — 표 쓰기 · 채널톡 읽기 · 두뇌 0(예전 그대로).

초안 차례(:mod:`.drafting` — 15분 바퀴 · 빠른 길 공통, :class:`.drafting_pass.DraftPass`)가 두 자리에서 부른다:

1. **두뇌 전**(:func:`lookup_first`): 이 상담에서 성함 · 휴대폰을 물은 지(:data:`ASK_WINDOW` 안) 아직 찾지 못했으면 손님 원문으로
   찾는다 — 찾으면 주문 칸을 실은 재료로 두뇌를 한 번만 부른다.
2. **두뇌 넘김 뒤**(:func:`lookup_after`): 두뇌가 주문 문의(넘김 까닭 :data:`ORDER_REASONS`)로 넘겼을 때만 찾는다(그 밖 문의는 ERP 를
   읽지 않는다). 찾으면 주문 칸을 실어 두뇌를 한 번 더 부르고(쓰임은 두 번을 더한다), 못 찾으면 성함 · 휴대폰을 한 번 묻는 초안
   (:data:`ASK_TEXT` — 톡톡은 묻지 않고 넘김), 이미 물었으면 넘김 + 직원 참고(:data:`NOTE_TEXTS`). 후보가 여럿이면 품목 · 주소 조각을
   한 번 더 묻는다(:data:`ASK_MORE_TEXT`).

찾기 순서(:mod:`.order_find`): 주문 번호 + 전화 끝 네 자리 → 손님이 알려 준 휴대폰 + 이름 → 채널톡 손님 정보. 주문 번호가 있는데
끝 네 자리가 틀리면 손님에게 아무것도 알리지 않고 직원 참고만(``mismatch``) — 그 상담은 :data:`ASK_WINDOW` 동안 번호 길을 잠근다
(번호 짐작 막기 — :func:`number_locked`). 확인된 주문은 허용 칸만 싣는다(:mod:`.order_block`).
초안 검사는 그 주문의 날을 확정 날로, 실측 시간대를 허용 글로 받는다(:meth:`OrderTurn.dates` · :meth:`OrderTurn.allowed`).

**감사 줄**: 찾을 때마다 SystemSetting :data:`LOG_KEY` 에 (상담 id · 차례 줄 id · 결과 · 확정 근거 · 주문 번호 · 실은 칸 이름 · 때)를
남긴다(최근 :data:`LOG_LIMIT` 개) — 값 · 글은 없다. 로그엔 상담 id · 결과 코드만.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from foms.services.cs_agent.brain_prompt import HANDOFF_NONE
from foms.services.cs_agent.checks_rules import is_naver_talk
from foms.services.cs_agent.drafting_read import _get as read_get
from foms.services.cs_agent.onto_settings import order_lookup_on
from foms.services.cs_agent.order_block import OrderFacts, order_block, order_facts
from foms.services.cs_agent.order_find import NONE, Lookup, by_contact, by_number, by_profile, narrow, read_profile
from foms.services.cs_agent.settings import read_settings
from models import SystemSetting

logger = logging.getLogger(__name__)

__all__ = [
    "ASK_MORE_TEXT", "ASK_TEXT", "ASK_WINDOW", "LOG_KEY", "LOG_LIMIT", "NOTE_TEXTS", "ORDER_REASONS", "OrderTurn",
    "lookup_after", "lookup_first", "number_locked", "pending_ask",
]

ORDER_REASONS = frozenset({"order_lookup", "schedule"})
FOUND, ASKED, ASKED_MORE, NOT_FOUND, SEVERAL, MISMATCH, TALKTALK = (
    "found", "asked", "asked_more", "none", "several", "mismatch", "talktalk")
ASK_WINDOW = datetime.timedelta(days=3)
LOG_KEY, LOG_LIMIT = "cs_agent_order_lookup_log", 2000
ASK_TEXT = "정확한 확인을 위해 주문하신 분 성함과 휴대폰 번호를 남겨 주시면 확인해서 안내드릴게요."
ASK_MORE_TEXT = ("같은 성함과 번호로 주문이 여러 건 확인돼요. 문의하신 제품이나 설치 주소의 동 이름을 알려 주시면 확인해서 "
                 "안내드릴게요.")
#: 결과 코드 → 직원 참고 줄(정한 말만 — 손님 글 · 값 없음).
NOTE_TEXTS = {
    ASKED: "주문 확인: AI 가 성함 · 휴대폰 번호를 물었어요(ERP 주문을 찾으려고)",
    ASKED_MORE: "주문 확인: 같은 성함 · 휴대폰의 열린 주문이 여럿이라 제품 · 주소를 한 번 더 물었어요",
    NOT_FOUND: "주문 확인: ERP 에서 이 손님의 열린 주문을 찾지 못했어요",
    SEVERAL: "주문 확인: 같은 성함 · 휴대폰의 열린 주문이 여럿이라 하나로 고르지 못했어요",
    MISMATCH: "주문 확인: 손님이 적은 주문 번호와 전화 끝 네 자리가 맞지 않았어요(손님에게는 알리지 않음)",
    TALKTALK: "주문 확인: 톡톡이라 번호를 묻지 않았어요 — ERP 에서 찾아 주세요",
}
_USAGE = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "cost_usd", "latency_ms")


@dataclass(frozen=True)
class OrderTurn:
    """차례 하나의 주문 확인 결과 — 결과 코드 · 확인된 주문 값(찾았을 때만)."""

    act: str
    facts: Optional[OrderFacts] = None

    def apply(self, request: Any) -> Any:
        """초안 재료에 주문 칸을 넣는다(찾았을 때만 — 아니면 그대로)."""
        return dataclasses.replace(request, order_lines=order_block(self.facts)) if self.facts else request

    def note(self) -> str:
        """직원 참고 줄 — 찾았으면 주문 번호 · 담당 팀, 아니면 결과 말."""
        return self.facts.staff_line() if self.facts else NOTE_TEXTS.get(self.act, "")

    def dates(self) -> tuple[datetime.date, ...]:
        """초안 검사의 확정 날(찾았을 때만)."""
        return self.facts.dates() if self.facts else ()

    def allowed(self) -> tuple[str, ...]:
        """초안 숫자 검사에 더할 글(찾았을 때만)."""
        return self.facts.allowed_texts() if self.facts else ()


def _log_rows(session: Any, *, lock: bool = False) -> tuple[Any, list[dict[str, Any]]]:
    """감사 줄(설정 줄 · dict 목록)."""
    row = session.get(SystemSetting, LOG_KEY, populate_existing=True, with_for_update=lock)
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    return row, [item for item in value.get("rows") or () if isinstance(item, dict)]


def _utc(now: datetime.datetime) -> datetime.datetime:
    """바퀴 시각 → UTC naive(시간대가 없으면 이미 UTC naive 로 본다)."""
    return now.astimezone(datetime.timezone.utc).replace(tzinfo=None) if now.tzinfo else now


def _record(ctx: Any, row: Any, act: str, lookup: Lookup = NONE, facts: Optional[OrderFacts] = None) -> None:
    """감사 줄 하나를 더하고 커밋한다 — 상담 id · 차례 줄 id · 결과 · 근거 · 주문 번호 · 칸 이름 · 때(값 · 글 없음)."""
    entry = {"chat": row.chat_id, "turn": row.id, "act": act, "basis": lookup.basis,
             "order": facts.order_id if facts else None, "fields": list(facts.fields()) if facts else [],
             "candidates": len(lookup.candidates), "at": _utc(ctx.now).isoformat(timespec="seconds")}
    session = ctx.session
    setting, rows = _log_rows(session, lock=True)
    value = {"rows": [*rows[-(LOG_LIMIT - 1):], entry]}
    if setting is None:
        session.add(SystemSetting(setting_key=LOG_KEY, setting_value=value,
                                  description="AI 상담팀원 주문 확인 감사 줄(상담 id · 결과 · 근거 · 주문 번호 · 칸 이름만 — 값 없음)"))
    else:
        setting.setting_value = value
    session.commit()
    logger.info("[CS 주문] 주문 확인 chat=%s act=%s basis=%s", row.chat_id, act, lookup.basis or "-")


def _recent(session: Any, chat_id: str, now: datetime.datetime) -> list[dict[str, Any]]:
    """이 상담의 :data:`ASK_WINDOW` 안 감사 줄(오래된 것부터 · 때를 못 읽는 줄은 뺀다)."""
    _, rows = _log_rows(session)
    out = []
    for item in rows:
        if item.get("chat") != chat_id:
            continue
        try:
            at = datetime.datetime.fromisoformat(str(item.get("at")))
        except ValueError:
            continue
        if _utc(now) - at <= ASK_WINDOW:
            out.append(item)
    return out


def pending_ask(session: Any, chat_id: str, now: datetime.datetime) -> Optional[str]:
    """이 상담의 마지막 감사 줄이 :data:`ASK_WINDOW` 안의 '물음'(asked · asked_more)이면 그 코드, 아니면 ``None``."""
    rows = _recent(session, chat_id, now)
    last = rows[-1].get("act") if rows else None
    return str(last) if last in (ASKED, ASKED_MORE) else None


def number_locked(session: Any, chat_id: str, now: datetime.datetime) -> bool:
    """이 상담에서 :data:`ASK_WINDOW` 안에 주문 번호 · 끝 네 자리가 한 번 틀렸나 — 그러면 번호 길은 잠근다(번호 짐작 막기)."""
    return any(item.get("act") == MISMATCH for item in _recent(session, chat_id, now))


def _texts(lines: Sequence[Any]) -> list[str]:
    """손님 공개 글 원문(이 바퀴 메모리에만 — 찾기에만 쓰고 남기지 않는다)."""
    return [line.text for line in lines
            if line.meta.is_customer_signal and not line.meta.is_private and line.text.strip()]


def _search(ctx: Any, row: Any, texts: Sequence[str], *, profile: bool) -> Lookup:
    """주문 번호 + 끝 네 자리(한 번 틀린 상담은 잠금) → 휴대폰 + 이름(좁히기 포함) → (``profile`` 이면) 채널톡 손님 정보."""
    if not number_locked(ctx.session, row.chat_id, ctx.now):
        lookup = by_number(ctx.session, texts)
        if lookup.status in ("one", "mismatch"):
            return lookup
    lookup = narrow(by_contact(ctx.session, texts), texts)
    if lookup.status == "none" and profile:
        lookup = by_profile(ctx.session, read_profile(ctx.reader, row.brand, row.chat_id, read_get))
    return lookup


def _found(ctx: Any, row: Any, lookup: Lookup) -> OrderTurn:
    """확인된 주문 → 주문 칸 값 + 감사 줄."""
    facts = order_facts(lookup.order, lookup.basis)
    ctx.stop.check()  # 쓰기 전
    _record(ctx, row, FOUND, lookup, facts)
    return OrderTurn(FOUND, facts)


def lookup_first(ctx: Any, row: Any, request: Any, lines: Sequence[Any]) -> Any:
    """두뇌 전 — 성함 · 휴대폰을 물은 뒤 아직 못 찾은 상담이면 손님 원문으로 찾는다. 찾으면 주문 칸을 실은 재료(아니면 그대로)."""
    if not order_lookup_on(read_settings(ctx.session, log=False)) or pending_ask(ctx.session, row.chat_id, ctx.now) is None:
        return request
    lookup = _search(ctx, row, _texts(lines), profile=False)
    if lookup.status != "one":
        return request  # 못 찾음 · 여럿 · 틀림은 두뇌가 넘긴 뒤(:func:`lookup_after`) 마무리한다
    turn = _found(ctx, row, lookup)
    ctx.order_turns[row.id] = turn
    return turn.apply(request)


def _with_usage(result: Any, first: Any) -> Any:
    """두 번째 두뇌 결과에 첫 호출의 토큰 · 돈 · 시간을 더한다(차례 줄의 돈이 그 차례 전부가 되게)."""
    return dataclasses.replace(result, **{name: getattr(result, name) + getattr(first, name) for name in _USAGE})


def _after_miss(ctx: Any, row: Any, lookup: Lookup, medium: Optional[str]) -> OrderTurn:
    """못 찾음 · 여럿 · 틀림 → 물음(한 번만) 또는 넘김 결과 + 감사 줄."""
    asked = pending_ask(ctx.session, row.chat_id, ctx.now)
    if lookup.status == "mismatch":
        act = MISMATCH
    elif not medium or is_naver_talk(medium):  # 톡톡 · 매체 모름 — 채팅으로 번호를 받지 않는다(D30)
        act = TALKTALK
    elif lookup.status == "several":
        act = SEVERAL if asked == ASKED_MORE else ASKED_MORE
    else:
        act = NOT_FOUND if asked else ASKED
    ctx.stop.check()  # 쓰기 전
    _record(ctx, row, act, lookup)
    return OrderTurn(act)


def lookup_after(ctx: Any, row: Any, request: Any, result: Any, lines: Sequence[Any], medium: Optional[str]) -> Any:
    """두뇌가 주문 문의로 넘긴 뒤 — 찾으면 주문 칸을 실어 한 번 더 부른 결과, 물을 차례면 물음 초안, 아니면 직원 참고를 더한 넘김.

    끔 · 넘김 아님 · 주문 문의 아님 · 이 차례에 이미 찾았으면 ``result`` 그대로. 두뇌 오류는 올린다(부르는 쪽이 받는다).
    """
    if (not result.handoff or result.handoff_reason not in ORDER_REASONS or row.id in ctx.order_turns
            or not order_lookup_on(read_settings(ctx.session, log=False))):
        return result
    lookup = _search(ctx, row, _texts(lines), profile=bool(medium) and not is_naver_talk(medium))
    turn = _found(ctx, row, lookup) if lookup.status == "one" else _after_miss(ctx, row, lookup, medium)
    ctx.order_turns[row.id] = turn
    if turn.facts is not None:
        ctx.stop.check()  # 두뇌 전
        ctx.summary.brain_calls += 1
        return _with_usage(ctx.brain(turn.apply(request), session=ctx.session, now=ctx.now), result)
    if turn.act in (ASKED, ASKED_MORE):
        return dataclasses.replace(result, draft=ASK_TEXT if turn.act == ASKED else ASK_MORE_TEXT, evidence_ids=(),
                                   handoff=False, handoff_reason=HANDOFF_NONE, staff_note="")
    return dataclasses.replace(result, staff_note="\n".join(part for part in (result.staff_note, turn.note()) if part))
