"""상담 AI 접목 한 걸음 — 초안 두뇌 뒤 근거 남기기 · 규칙 제안 셋(설계서 2026-11-14-foms-graft 3.9 · 3.11 · 7절).

초안 차례(:mod:`.drafting` — 15분 바퀴 · 빠른 길 공통)가 두뇌 결과를 차례 줄에 적은 뒤 :func:`after_draft` 를 한 번 부른다.
관리 칸 둘(:mod:`.graft_settings`)이 모두 꺼져 있으면 설정 한 번 읽기뿐 — 표 쓰기 · 질의 0(지금과 같다).

1. **근거 남기기**('근거 줄' 켬): 초안이 쓴 지식 문서 항목 id → 지금 판 회사 지식 키(:func:`foms.services.brain.usage.doc_keys`)와
   본인이 확인된 주문 키(``erp:order/<번호>``)를 차례 번호로 남긴다(``record_uses(..., reader='cs_draft', ref_kind='cs_turn')``).
2. **규칙 제안 셋**('할 일 제안' 켬 · 본인이 확인된 주문(:mod:`.order_step`)이 있을 때만 — 모델 지시문 · 출력 틀은 건드리지 않는다):
   ① AS 뜻 + 단계가 완료 · CS → ``register_as``(승인 대기로)
   ② AS · 불편 뜻 + 시공일이 앞날 → ``add_construction_note``(작은 창 줄 — :data:`.registry.ActionSpec.wam_inline`)
   ③ 일정 바꾸기 요청 + 손님 글에 달 · 날이 똑바로 적힘(요일만이면 만들지 않는다) → 실측이 아직 앞날이면 ``move_measurement``,
   시공일이 앞날이면 ``move_construction``(승인 대기로). '일정 바꾸기 요청'은 넘김 까닭 ``schedule`` 이거나, 주문 칸 규칙
   (:data:`.order_block.ORDER_RULES` — 확인된 주문이 있으면 넘기지 않고 직원 참고에 '일정 변경 요청'을 적는다)대로 넘기지 않은
   답의 직원 참고에 :data:`SCHEDULE_NOTE` 가 있는 것이다.
   수준은 :func:`foms.services.ai_staff.registry.level_of` (``'cs'``) — 0 이면 만들지 않는다. 막는 조건 · 겹침 · 가림 검사는
   :func:`foms.services.erp_actions.lifecycle.propose` 가 본다(커밋은 초안 길이 한다).

- 걸음마다 저장점 안에서 돈다 — 실패는 초안 길을 깨지 않고 경고 로그에 코드만 남긴다(:func:`_guarded`).
- 날짜는 :func:`get_today_kst`. 손님 글은 이 바퀴 메모리에서 규칙에만 쓰고, 제안 칸(증상 · 메모)에는 가린 글만 싣는다. 이유 ·
  근거 이름은 코드가 정한 말 · 주문 번호 · 날짜 · 회사 지식 항목 이름뿐이다. 로그에는 차례 번호 · 할 일 이름 · 코드만.
- 근거 이름 도우미(:func:`brain_labels` · :func:`order_label`)는 작은 창 칩(:mod:`.send_view`)도 같이 쓴다.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence

from sqlalchemy import select

from foms.persistence.brain.models import BrainObject
from foms.services.ai_staff.registry import level_of, proposer
from foms.services.brain.constants import SCOPE_ALL
from foms.services.brain.display import type_label
from foms.services.brain.store import is_current
from foms.services.brain.usage import doc_keys
from foms.services.brain.usage_events import READER_CS_DRAFT, record_uses
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.graft_settings import actions_on, evidence_on
from foms.services.cs_agent.masking import mask
from foms.services.cs_agent.settings import read_settings
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_actions.lifecycle import clean_reason_text, propose
from foms.services.erp_actions.preview import date_label
from foms.services.erp_actions.registry import MAX_EVIDENCE, TIME_SLOTS
from foms.services.erp_ontology.read import order_key
from models import Order

logger = logging.getLogger(__name__)

__all__ = [
    "AGENT", "Plan", "SCHEDULE_NOTE", "SOURCE_KIND", "after_draft", "asked_days", "brain_labels", "order_label",
    "plans",
]

AGENT = "cs"
SOURCE_KIND = "cs_turn"
#: 주문 칸 규칙(:data:`.order_block.ORDER_RULES`)이 일정 바꾸기 요청 때 직원 참고에 적게 한 말(시험이 그 규칙 글과 견준다).
SCHEDULE_NOTE = "일정 변경"
REGISTER_AS, ADD_NOTE = "register_as", "add_construction_note"
MOVE_MEASUREMENT, MOVE_CONSTRUCTION = "move_measurement", "move_construction"
_AS_DONE_STAGES = ("COMPLETED", "CS")
_AS_LIMIT, _NOTE_SNIPPET, _LABEL_LIMIT, _NAME_LIMIT = 300, 140, 60, 40
#: 올해 날짜가 이만큼 안쪽으로 지났으면 지난 날을 말한 것으로 본다(내년으로 넘기지 않는다).
_PAST_WINDOW_DAYS = 60
_AS_WORDS = re.compile(
    r"(?<![A-Za-z])(?:A/S|AS|a/s)(?![A-Za-z])|에이에스|하자|고장|불량|파손|깨[졌짐지]|부러[졌지]|수리|금이 ?갔|갈라[졌지]|"
    r"벌어[졌지]|틀어[졌지]|처[졌짐]|들[떴뜸뜨]|삐걱|끼익|덜컹|소리가 ?[나납들]|흔들[려리거]|안 ?(?:닫[혀히]|열[려리]|잠[겨기])|"
    r"빠[졌짐]|떨어[졌지]|누수|물이 ?새|곰팡이|녹이 ?[슬났]")
_TROUBLE_WORDS = re.compile(r"불편|불만|문제가|이상해|이상이|이상한")
_MONTH_DAY = re.compile(r"(?<!\d)(1[0-2]|0?[1-9])\s*월\s*(3[01]|[12]\d|0?[1-9])\s*일")
_FULL_DATE = re.compile(r"(?<!\d)(20\d{2})\s*[-./년]\s*(1[0-2]|0?[1-9])\s*[-./월]\s*(3[01]|[12]\d|0?[1-9])(?!\d)")
_CONSTRUCTION_WORDS = re.compile(r"시공|설치")

REASON_AS = "끝난 주문에 손님이 채널톡 상담으로 AS 를 물었어요. 증상은 가린 손님 글에서 옮겼어요."
REASON_NOTE = "시공 전 주문에 손님이 채널톡 상담으로 손볼 곳을 알렸어요. 시공 때 같이 봐 드리게 메모를 더해요."
_REASON_MOVE = "손님이 채널톡 상담에서 {kind} 날을 {day}로 바꿔 달라고 했어요."
_KIND_LABELS = {MOVE_MEASUREMENT: "실측", MOVE_CONSTRUCTION: "시공"}


@dataclass(frozen=True)
class Plan:
    """만들 제안 하나 — 할 일 이름 · 넣을 값 · 이유(코드가 정한 말)."""

    action: str
    params: dict[str, Any]
    reason: str


# ── 한 걸음 ──────────────────────────────────────────────────────────────
def after_draft(ctx: Any, row: Any, result: Any, lines: Sequence[Any]) -> None:
    """초안 두뇌 뒤 한 걸음 — 근거 남기기 · 규칙 제안(관리 칸이 켜진 것만). 커밋하지 않는다(초안 길이 커밋한다).

    Args:
        ctx: 초안 차례 재료(:class:`.drafting_pass.DraftPass` — ``session`` · ``now`` · ``stop`` · ``order_turns``).
        row: 선점한 차례 줄(``id`` · ``brand``).
        result: 두뇌 결과(:class:`.brain_prompt.DraftResult` — 주문 확인 뒤 최종 값).
        lines: 이번 읽기의 상담 글(:class:`.drafting_read.ChatLine`).
    """
    if getattr(result, "refused", False):
        return
    cfg = read_settings(ctx.session, log=False)
    evidence, actions = evidence_on(cfg), actions_on(cfg)
    if not (evidence or actions):
        return
    ctx.stop.check()  # 쓰기 전
    turn = getattr(ctx, "order_turns", {}).get(row.id)
    facts = getattr(turn, "facts", None)
    if evidence:
        _guarded(ctx, row, "evidence", lambda: _record_evidence(ctx, row, result, facts))
    if actions and facts is not None:
        texts = _customer_texts(lines, getattr(facts, "basis", ""))
        _guarded(ctx, row, "proposals", lambda: _propose_all(ctx, row, result, facts, texts))


def _guarded(ctx: Any, row: Any, step: str, work: Callable[[], Any]) -> None:
    """저장점 안에서 한 걸음 — 실패면 그 저장점만 되감고 경고 로그에 코드만(초안 길은 그대로)."""
    try:
        with ctx.session.begin_nested():
            work()
    except Exception as exc:  # noqa: BLE001 — 접목 걸음 실패가 초안 길을 깨지 않는다(로그엔 코드만)
        logger.warning("[CS 접목] 걸음 건너뜀 turn=%s step=%s code=%s", row.id, step, type(exc).__name__)


def _utc(now: datetime.datetime) -> datetime.datetime:
    """바퀴 시각 → UTC naive(시간대가 없으면 이미 UTC naive 로 본다)."""
    return naive_utc(now) if now.tzinfo else now


def _record_evidence(ctx: Any, row: Any, result: Any, facts: Any) -> int:
    """근거 남기기 — 회사 지식 키 + 확인된 주문 키를 차례 번호로(겹침은 한 번). 남긴 줄 수."""
    keys = doc_keys(ctx.session, row.brand, getattr(result, "evidence_ids", ()) or ())
    if facts is not None:
        keys.append(order_key(int(facts.order_id)))
    return record_uses(ctx.session, keys, READER_CS_DRAFT, SOURCE_KIND, row.id, _utc(ctx.now))


def _customer_texts(lines: Sequence[Any], basis: str) -> list[str]:
    """규칙이 읽는 손님 공개 글 원문(이 바퀴 메모리에만 — 남기지 않는다) — 마지막 공개 직원 글 뒤 글.

    손님이 방금 성함 · 휴대폰을 알려 줘 주문이 확인된 차례(확정 근거 ``contact`` — 주문 확인 물음의 답)면 그 물음 앞 묶음(물음을
    부른 손님 글 — 일정 · AS 문의)까지 읽는다.
    """
    answers = [i for i, line in enumerate(lines) if line.meta.is_answer]
    keep = 2 if basis == "contact" else 1
    start = answers[-keep] + 1 if len(answers) >= keep else 0
    return [line.text for line in lines[start:]
            if line.meta.is_customer_signal and not line.meta.is_private and (line.text or "").strip()]


def _matching(texts: Sequence[str], *patterns: Any) -> list[str]:
    """그 뜻 낱말이 든 글만(제안 칸에 실을 글 — 성함 · 휴대폰만 적은 답 글은 빠진다)."""
    return [text for text in texts if any(pattern.search(text) for pattern in patterns)]


def _propose_all(ctx: Any, row: Any, result: Any, facts: Any, texts: Sequence[str]) -> None:
    """확인된 주문의 규칙 제안 — 바깥 저장점(주문 · 근거 읽기) 안에서 할 일마다 저장점 하나(하나가 실패해도 다른 제안은 만든다)."""
    order = ctx.session.get(Order, int(facts.order_id))
    found = plans(result, order, texts, get_today_kst()) if order is not None else []
    if not found:
        return
    evidence = _proposal_evidence(ctx.session, row, result, order)
    for plan in found:
        _guarded(ctx, row, plan.action, lambda plan=plan: _propose_one(ctx, row, plan, order, evidence))


def _propose_one(ctx: Any, row: Any, plan: Plan, order: Any, evidence: list[dict[str, str]]) -> Optional[Any]:
    """수준을 읽고(0 이면 안 만듦) 제안 하나를 만든다 — 막힘 · 겹침 · 가림 걸림은 ``None``(생명주기가 코드만 로그)."""
    level = level_of(ctx.session, AGENT, plan.action)
    if level <= 0:
        logger.info("[CS 접목] 수준 0 이라 제안 안 만듦 turn=%s action=%s", row.id, plan.action)
        return None
    made = propose(ctx.session, action=plan.action, proposed_by=proposer(AGENT), order=order, params=plan.params,
                   reason=plan.reason, evidence=evidence, source_kind=SOURCE_KIND, source_ref=str(row.id),
                   level=level, now=_utc(ctx.now))
    if made is not None:
        logger.info("[CS 접목] 제안 만듦 turn=%s action=%s proposal=%s order=%s", row.id, plan.action, made.id,
                    order.id)
    return made


def _proposal_evidence(session: Any, row: Any, result: Any, order: Any) -> list[dict[str, str]]:
    """제안 근거 — 상담 차례 · 주문 + 초안이 쓴 회사 지식(이름이 가림 검사를 지난 것만). 여덟까지."""
    out = [{"kind": "cs_turn", "ref": str(row.id), "label": f"상담 차례 #{row.id}"},
           {"kind": "order", "ref": order_key(int(order.id)), "label": f"주문 #{order.id}"}]
    keys = doc_keys(session, row.brand, getattr(result, "evidence_ids", ()) or ())
    for key, label in brain_labels(session, keys).items():
        if clean_reason_text(label) is not None:
            out.append({"kind": "brain", "ref": key, "label": label})
    return out[:MAX_EVIDENCE]


# ── 근거 이름 ────────────────────────────────────────────────────────────
def brain_labels(session: Any, keys: Iterable[str]) -> dict[str, str]:
    """회사 지식 키 → 칩 이름('유형 · 항목 이름' — 지금 판 · 모두 보기 범위만, 키 차례). 이름은 :data:`_LABEL_LIMIT` 자까지.

    Args:
        session: DB 세션.
        keys: 회사 지식 키(ERP 물건 키는 섞여도 빠진다).

    Returns:
        키 → 이름(지금 판이 없거나 보기 범위가 좁은 항목은 뺀다 — 이름도 남에게 보이지 않게).
    """
    wanted = [key for key in dict.fromkeys(keys) if isinstance(key, str) and key]
    if not wanted:
        return {}
    rows = session.execute(select(BrainObject.item_key, BrainObject.item_type, BrainObject.name).where(
        BrainObject.item_key.in_(wanted), is_current(BrainObject), BrainObject.visibility == SCOPE_ALL)).all()
    found = {key: (item_type, name) for key, item_type, name in rows}
    out = {}
    for key in wanted:
        if key in found:
            item_type, name = found[key]
            text = " ".join(str(name or "").split())[:_NAME_LIMIT]
            out[key] = f"{type_label(item_type)} · {text}"[:_LABEL_LIMIT]
    return out


def order_label(order: Any) -> str:
    """주문 칩 이름 — '주문 #번호' + 시공 날(없으면 실측 날). 손님 이름 · 주소 · 금액은 없다."""
    construction, measurement = _days(order, "construction"), _days(order, "measurement")
    if construction:
        return f"주문 #{order.id} · 시공 {date_label(construction[0].isoformat())}"
    if measurement:
        return f"주문 #{order.id} · 실측 {date_label(measurement[0].isoformat())}"
    return f"주문 #{order.id}"


# ── 규칙 셋 ──────────────────────────────────────────────────────────────
def _schedule(order: Any, kind: str) -> dict[str, Any]:
    """``structured_data.schedule.<kind>`` 칸(없으면 빈 dict)."""
    data = getattr(order, "structured_data", None)
    node = data.get("schedule") if isinstance(data, dict) else None
    node = node.get(kind) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else {}


def _days(order: Any, kind: str) -> list[datetime.date]:
    """실측 · 시공 날(``structured_data.schedule`` 이 정본 — 없으면 납작 칸). 실측은 쉼표로 여러 날일 수 있다."""
    flat = getattr(order, "erp_measurement_date" if kind == "measurement" else "erp_construction_date", None)
    raw = str(_schedule(order, kind).get("date") or flat or "")
    out = []
    for part in raw.split(","):
        try:
            out.append(datetime.date.fromisoformat(part.strip()[:10]))
        except ValueError:
            continue
    return out


def _resolve(month: int, day: int, today: datetime.date) -> Optional[datetime.date]:
    """'M월 D일' → 날짜 — 올해가 오늘 이후면 올해, 막 지난 날(:data:`_PAST_WINDOW_DAYS`)이면 없음, 그 밖은 내년."""
    try:
        this = datetime.date(today.year, month, day)
    except ValueError:
        return None
    if this >= today:
        return this
    if (today - this).days <= _PAST_WINDOW_DAYS:
        return None
    try:
        return datetime.date(today.year + 1, month, day)
    except ValueError:
        return None


def asked_days(texts: Iterable[str], today: datetime.date) -> list[datetime.date]:
    """손님 글에 달 · 날이 똑바로 적힌 날짜(오늘 이후 · 겹침 없이 · 차례대로). 요일 · '다음 주' · 날만 적힌 글은 없다.

    Args:
        texts: 손님 글.
        today: 한국 오늘(:func:`get_today_kst`).

    Returns:
        날짜 목록.
    """
    found: list[datetime.date] = []
    for text in texts:
        for year, month, day in _FULL_DATE.findall(text):
            try:
                found.append(datetime.date(int(year), int(month), int(day)))
            except ValueError:
                continue
        found.extend(d for m, dd in _MONTH_DAY.findall(text) if (d := _resolve(int(m), int(dd), today)) is not None)
    return sorted({day for day in found if day >= today})


def _masked_text(texts: Sequence[str], limit: int) -> str:
    """손님 글을 글마다 가려 한 줄로 — ``limit`` 자 넘으면 자르고 '…'."""
    text = " ".join(" ".join(mask(item).split()) for item in texts).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _rule_register_as(result: Any, order: Any, texts: Sequence[str], today: datetime.date) -> Optional[Plan]:
    """① AS 뜻 + 단계 완료 · CS → AS 접수(증상은 가린 손님 글)."""
    if str(getattr(order, "erp_stage_code", "") or "").upper() not in _AS_DONE_STAGES:
        return None
    content = _masked_text(_matching(texts, _AS_WORDS), _AS_LIMIT)
    return Plan(REGISTER_AS, {"as_content": content}, REASON_AS) if content else None


def _rule_construction_note(result: Any, order: Any, texts: Sequence[str], today: datetime.date) -> Optional[Plan]:
    """② AS · 불편 뜻(낱말 · 넘김 까닭 ``complaint``) + 시공일이 앞날 → 시공 메모 한 줄(작은 창 줄)."""
    found = _matching(texts, _AS_WORDS, _TROUBLE_WORDS)
    if not found and getattr(result, "handoff_reason", "") == "complaint":
        found = list(texts)
    if not found or not any(day > today for day in _days(order, "construction")):
        return None
    snippet = _masked_text(found, _NOTE_SNIPPET)
    return Plan(ADD_NOTE, {"note": f"채널톡 상담: {snippet} — 시공 때 확인"}, REASON_NOTE) if snippet else None


def _schedule_ask(result: Any) -> bool:
    """일정 바꾸기 요청인가 — 넘김 까닭 ``schedule`` · 또는 넘기지 않은 답의 직원 참고에 :data:`SCHEDULE_NOTE`."""
    if getattr(result, "handoff_reason", "") == "schedule":
        return True
    return not getattr(result, "handoff", False) and SCHEDULE_NOTE in (getattr(result, "staff_note", "") or "")


def _move_target(text: str, measurement_ahead: bool, construction_ahead: bool) -> Optional[str]:
    """옮길 방문 — 손님 글이 시공(설치)만 말하면 시공, 실측만 말하면 실측, 둘 다 · 아무것도 아니면 앞날인 실측 먼저."""
    says_construction, says_measurement = bool(_CONSTRUCTION_WORDS.search(text)), "실측" in text
    if says_construction and not says_measurement:
        return MOVE_CONSTRUCTION if construction_ahead else None
    if says_measurement and not says_construction:
        return MOVE_MEASUREMENT if measurement_ahead else None
    if measurement_ahead:
        return MOVE_MEASUREMENT
    return MOVE_CONSTRUCTION if construction_ahead else None


def _rule_move(result: Any, order: Any, texts: Sequence[str], today: datetime.date) -> Optional[Plan]:
    """③ 일정 바꾸기 요청 + 달 · 날이 똑바로 적힌 날 하나 → 실측 · 시공 옮기기(지금 날과 같은 날 · 지난 날은 뺀다)."""
    if not _schedule_ask(result):
        return None
    measurement, construction = _days(order, "measurement"), _days(order, "construction")
    action = _move_target(" ".join(texts), any(d > today for d in measurement), any(d > today for d in construction))
    if action is None:
        return None
    current = measurement if action == MOVE_MEASUREMENT else construction
    wanted = [day for day in asked_days(texts, today) if day not in current]
    if len(wanted) != 1:  # 없거나 여럿이면(어느 날인지 모름) 만들지 않는다
        return None
    params: dict[str, Any] = {"date": wanted[0].isoformat()}
    if action == MOVE_CONSTRUCTION:
        time = str(_schedule(order, "construction").get("time") or "")
        params["time"] = time if time in TIME_SLOTS else ""
    reason = _REASON_MOVE.format(kind=_KIND_LABELS[action], day=date_label(params["date"]))
    return Plan(action, params, reason)


_RULES = (_rule_register_as, _rule_construction_note, _rule_move)


def plans(result: Any, order: Any, texts: Sequence[str], today: datetime.date) -> list[Plan]:
    """규칙 셋이 만들 제안(할 일마다 하나까지 · 규칙 차례).

    Args:
        result: 두뇌 결과(넘김 · 넘김 까닭 · 직원 참고).
        order: 본인이 확인된 주문.
        texts: 마지막 직원 답 뒤 손님 글 원문(메모리에만).
        today: 한국 오늘.

    Returns:
        :class:`Plan` 목록(막는 조건 · 수준은 아직 보지 않았다).
    """
    return [plan for rule in _RULES if (plan := rule(result, order, texts, today)) is not None]
