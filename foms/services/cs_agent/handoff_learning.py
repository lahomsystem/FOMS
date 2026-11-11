"""넘긴 상담 배우기 — AI 가 사람에게 넘긴 상담에서 직원이 직접 한 답을 회사 지식 제안으로(사장님 11-11 '넘긴 것을 학습해서
다음엔 AI 가 답하게').

AI 가 답을 몰라 넘긴 차례(``skipped`` · ``handoff``)나 보내기 전 검사에 걸린 차례(``check_failed``)에는 직원이 데스크에서 직접
답한다(사례 기억 :mod:`.case_memory` 가 가린 직원 답을 붙인다). 지금 사례 재료(:mod:`.case_material` · :mod:`.brain_cases`)는
이것을 '말투 · 순서만 참고'로 쓰고 그 안의 사실은 다음 초안에 쓰지 않는다. 이 길은 그 사실 · 정책을 사장님 승인 대기 카드로
올린다 — 승인한 것만 지식 문서에 들어가 다음 초안이 답할 수 있다(사진 학습 :mod:`.photo_learning` 과 같은 제안 길).

WORKER 15분 바퀴 학습 몫(:mod:`.learning_pass`)이 부르고, **밤(KST :data:`WINDOW_HOURS`)에 하루 한 번**만 돈다(부르기 전에 날
표를 남긴다 — :func:`claim_day`, 재시작 · 두 컨테이너가 겹쳐도 한 번). 창은 월요일 새벽 주간 고침 안 · 사진 학습 창(3 ~ 6시)
앞이라 한 바퀴에 학습 부르기가 셋 겹치지 않는다. 끄고 켜기는 :func:`.learning_brain.off_reason`(패널 '넘긴 상담 배우기' — 처음
끔 · 비상 정지 · 초안 끔 · 학습 돈 상한).

1. **읽기(가린 글만)**: 지난 7일(:data:`.weekly_fix.LOOKBACK`) 라홈 차례 가운데 ``skipped`` 이고 (넘김 + 까닭
   :data:`LEARN_REASONS`) 또는 보내기 전 검사에 걸린 것, 가린 직원 답이 있고 끝난 꼴이 학습 재료(복사 · 버림 제외)이며 떼어 둔
   줄이 아닌 것. 늘 사람이 답하는 까닭(:data:`HUMAN_ONLY_REASONS` — 불만 · 주문 조회 · 할인 · 환불 · 사람만 말하는 금액)과 그런
   검사 코드(:data:`HUMAN_ONLY_CHECKS`) · 견적 계산 차례(금액 정본은 계산기)는 뺀다 — 다만 직원이 넘김 메모 [배우기]로 직접
   보낸 차례(``send_state`` 보냄 — :mod:`.handoff_send`)는 그 까닭이어도 읽는다('AI 냐' 차례 빼고). [흘리기]한 차례는 끝난 꼴
   '버림'이라 늘 빠진다. **이미 읽은 차례는 다시 읽지 않는다**
   (:func:`used_ids`). 오래된 것부터 패널 '한 번에 읽는 사례 수'만.
   **창을 '지난번 성공한 날부터'가 아니라 늘 7일로 둔 까닭**: 읽은 차례 표가 이미 같은 사례를 두 번 막는다. 움직이는 시작점을
   두면 실패한 밤 · 상한을 넘어 남은 사례 · 밤 뒤에 붙은 직원 답이 시작점과 표 사이에서 조용히 빠진다. 7일 창이면 첫 밤 · 건너뛴
   밤 · 밀린 사례가 같은 규칙으로 다음 밤에 읽히고, 7일이 지난 사례는 저절로 빠진다(주간 고침 안 · 사진 학습과 같은 7일).
2. **재료**: 사례마다 가린 손님 글 · 가린 직원 답 · 그 상담 전체 대화에서 그 손님 글을 가운데 둔 앞뒤 대화(직원 답 · 손님 반응
   포함 — :func:`.handoff_learning_prompt.talk_window`, 읽기 :func:`.full_conversation.read_talk`). 대화를 못 읽으면 질문 앞
   6줄. 조각마다 가림 검사 — 하나라도 걸리면 그 사례만 뺀다(``mask_dropped``). 보낼 사례가 하나도 없으면 부르지
   않는다.
3. **두뇌(학습 모델 — 주간 고침 안 모델 칸 · 학습 돈 상한 · 시간 상한 :data:`TIMEOUT_S`)**: 회사 지식 목록 · 이미 낸 제안과 견줘
   사실 · 정책 새로 만들기 · 고치기 안(:mod:`.handoff_learning_prompt`). 응답이 오면 보낸 사례를 '읽음'으로 적는다(돈을 쓴 사례는
   다시 보내지 않는다 — 부르기가 실패하면 적지 않아 다음 밤에 다시 본다).
4. **관문 · 넣기**(:mod:`.handoff_learning_gates`): 꼴 · 가림 · 근거 · 숫자 · 대상 · 같음 · 겹침 · 부딪침 → 제안 길로만 '승인 대기'.

로그 · 결과에는 숫자 · 코드만 싣는다(글 · 상담 id 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.brain.constants import CHANGE_OPEN
from foms.services.brain.proposals import known_text
from foms.services.cs_agent.brain_spend import BrainError
from foms.services.cs_agent.case_memory import LEARNING_OUTCOMES, OUTCOME_EDITED
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.drafting import SKIP_CHECK, SKIP_HANDOFF
from foms.services.cs_agent.edit_detail_settings import WEEKLY_MODEL_FIELD
from foms.services.cs_agent.full_conversation import Talk, case_limit, read_talk, talk_on
from foms.services.cs_agent.handoff_learn_settings import CASES_FIELD, EDIT_LEARN_FIELD, HANDOFF_LEARN_FIELD
from foms.services.cs_agent.handoff_learning_gates import EVIDENCE_MIN_CHATS, file_proposals, seen_proposals
from foms.services.cs_agent.handoff_learning_prompt import (
    build_params, case_lines, knowledge_lines, knowledge_rows, pending_lines, raw_proposals, talk_window,
)
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.learning_brain import call_learning, off_reason
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.send import SEND_BRAND
from foms.services.cs_agent.send_record import NOT_TAUGHT_REASONS, SEND_SENT
from foms.services.cs_agent.state import KST
from foms.services.cs_agent.turns import STATE_SKIPPED
from foms.services.cs_agent.weekly_fix import LOOKBACK
from models import CsAgentTurn, SystemSetting

logger = logging.getLogger(__name__)

__all__ = [
    "HUMAN_ONLY_CHECKS", "HUMAN_ONLY_REASONS", "LEARN_REASONS", "QUOTE_PREFIX", "STORE_KEY", "WINDOW_HOURS",
    "claim_day", "collect_cases", "day_id", "in_window", "mark_used", "run_handoff_learning", "used_ids",
]

STORE_KEY = "cs_agent_handoff_learn"
WINDOW_HOURS = (1, 3)  # 날마다 KST 1시 ~ 3시 앞(월요일 3 ~ 6시 주간 고침 안 · 사진 학습 창 앞)
#: 배울 넘김 까닭 — 모름 · 사진 · 일정 · 그 밖. 보내기 전 검사에 걸린 차례(``check_failed``)도 배운다.
LEARN_REASONS: tuple[str, ...] = ("unsure", "photo", "schedule", "other")
#: 늘 사람이 답하는 까닭 — 배우지 않는다(검사에 걸린 차례도 이 까닭이면 뺀다).
HUMAN_ONLY_REASONS: tuple[str, ...] = ("complaint", "order_lookup", "discount_refund", "human_only_amount")
#: 늘 사람 몫인 보내기 전 검사 코드(사람만 말하는 금액 · 할인 · 환불 약속) — 그 검사에 걸린 차례는 배우지 않는다.
HUMAN_ONLY_CHECKS: frozenset[str] = frozenset({"human_only_amount", "discount_promise", "refund_promise"})
QUOTE_PREFIX = "quote_"  # 견적 계산이 사람에게 넘긴 까닭(:mod:`.quote_calc` · :mod:`.quote_rules`) — 배우지 않는다
MAX_DAYS, MAX_USED, MAX_SCAN, MAX_PENDING, TIMEOUT_S = 14, 2000, 2000, 30, 120
EDITED = "edited"  # 사례 갈래 — AI 초안을 직원이 고쳐 보내며 '왜 고쳤나요'를 적은 차례(패널 '고쳐 보낸 상담도 배우기')


def day_id(now: datetime.datetime) -> str:
    """KST 날 이름(예 ``2026-11-11``)."""
    return now.astimezone(KST).date().isoformat()


def in_window(now: datetime.datetime) -> bool:
    """KST :data:`WINDOW_HOURS` 안인가(날마다)."""
    return WINDOW_HOURS[0] <= now.astimezone(KST).hour < WINDOW_HOURS[1]


# ── 날 표 · 읽은 차례 표(SystemSetting 한 줄) ─────────────────────────────
def _doc(row: Any) -> dict[str, list[Any]]:
    """저장 값 → ``{"days": [KST 날], "used": [차례 id]}`` 사본(틀린 칸은 빈 목록)."""
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    days = [d for d in value.get("days") or [] if isinstance(d, str)] if isinstance(value.get("days"), list) else []
    used = ([i for i in value.get("used") or [] if isinstance(i, int) and not isinstance(i, bool)]
            if isinstance(value.get("used"), list) else [])
    return {"days": days, "used": used}


def _locked(session: Any) -> Any:
    """표 줄을 잠가 읽는다(없으면 먼저 만들어 커밋)."""
    if session.get(SystemSetting, STORE_KEY) is None:
        session.add(SystemSetting(setting_key=STORE_KEY, setting_value={"days": [], "used": []},
                                  description="AI 상담팀원 넘긴 상담 배우기 — 날마다 한 번 표 · 읽은 차례"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return session.get(SystemSetting, STORE_KEY, populate_existing=True, with_for_update=True)


def _put(row: Any, doc: dict[str, list[Any]]) -> None:
    row.setting_value = doc
    flag_modified(row, "setting_value")


def claim_day(session: Any, day: str) -> bool:
    """이 날 처음이면 날 표를 남기고(커밋) 참 — 이미 돌았으면 거짓(두 컨테이너가 겹쳐도 한 번)."""
    row = _locked(session)
    doc = _doc(row)
    if day in doc["days"]:
        session.rollback()
        return False
    _put(row, {**doc, "days": [*doc["days"], day][-MAX_DAYS:]})
    session.commit()
    return True


def used_ids(session: Any) -> frozenset[int]:
    """이미 두뇌에 보낸(또는 가림 검사로 뺀) 차례 id."""
    return frozenset(_doc(session.get(SystemSetting, STORE_KEY, populate_existing=True))["used"])


def mark_used(session: Any, ids: Iterable[int]) -> None:
    """차례를 '읽음'으로 적고 커밋한다(최근 :data:`MAX_USED` 개 — 7일 창 밖 차례는 어차피 다시 안 고른다)."""
    fresh = [int(i) for i in ids]
    if not fresh:
        return
    row = _locked(session)
    doc = _doc(row)
    merged = list(dict.fromkeys([*doc["used"], *fresh]))[-MAX_USED:]
    _put(row, {**doc, "used": merged})
    session.commit()


# ── 읽기 ─────────────────────────────────────────────────────────────────
def _turn_rows(session: Any, since: datetime.datetime, *, edits: bool = False) -> list[Any]:
    """지난 7일 넘김 · 검사 걸림 차례(가린 직원 답이 있는 것 · 떼어 둔 줄 제외) — 가린 칸 · 코드만, 오래된 것부터.
    ``edits`` 면 AI 초안을 직원이 고쳐 보내며 '왜 고쳤나요'를 적은 차례(끝난 꼴 '고침' · 가린 자세한 이유 있음)도."""
    turn = CsAgentTurn
    taught = and_(turn.error_code.in_((SKIP_HANDOFF, SKIP_CHECK)), turn.send_state == SEND_SENT,
                  or_(turn.handoff_reason.is_(None), turn.handoff_reason.notin_(NOT_TAUGHT_REASONS)))
    learnable = or_(and_(turn.error_code == SKIP_HANDOFF, turn.handoff_reason.in_(LEARN_REASONS)),
                    and_(turn.error_code == SKIP_CHECK,
                         or_(turn.handoff_reason.is_(None), turn.handoff_reason.notin_(HUMAN_ONLY_REASONS))),
                    taught)
    picked = and_(turn.state == STATE_SKIPPED, learnable)
    if edits:  # 사장님 11-11 — 고친 답 + 까닭도 회사 지식 제안으로(까닭을 적은 것만)
        picked = or_(picked, and_(turn.state != STATE_SKIPPED, turn.outcome == OUTCOME_EDITED,
                                  turn.edit_detail_masked.isnot(None)))
    stmt = (select(turn.id, turn.chat_id, turn.intent, turn.error_code, turn.handoff_reason, turn.check_codes,
                   turn.masked_question, turn.staff_reply_masked, turn.masked_context, turn.last_user_message_id,
                   turn.desk_manager_id, turn.send_state, turn.state, turn.masked_draft, turn.edit_reason,
                   turn.edit_detail_masked, turn.sent_by_user_id)
            .where(turn.brand == SEND_BRAND, picked,
                   turn.outcome.in_(LEARNING_OUTCOMES), turn.held_out.is_(False), turn.staff_reply_masked.isnot(None),
                   turn.updated_at >= since)
            .order_by(turn.id).limit(MAX_SCAN))
    return list(session.execute(stmt))


def _human_only(row: Any) -> bool:
    """늘 사람 몫인 검사에 걸린 차례 · 견적 계산 차례(금액 정본은 계산기 — 넘긴 까닭 ``quote_…``)인가. 직원이 넘김 메모
    [배우기]로 직접 보낸 차례는 아니다(직원이 배우라고 골랐다 — :mod:`.handoff_send`)."""
    codes = row.check_codes if isinstance(row.check_codes, list) else []
    if row.error_code != SKIP_CHECK or row.send_state == SEND_SENT:
        return False
    return (str(row.handoff_reason or "").startswith(QUOTE_PREFIX)
            or bool(HUMAN_ONLY_CHECKS.intersection(c for c in codes if isinstance(c, str))))


def _staff(row: Any) -> Optional[str]:
    """답한 직원 표지 — 채널톡 상담원 번호, 없으면 FOMS 직원 번호(FOMS 화면으로 고쳐 보낸 차례)."""
    if row.desk_manager_id:
        return str(row.desk_manager_id)
    return f"user-{int(row.sent_by_user_id)}" if row.sent_by_user_id is not None else None


def _case(row: Any) -> dict[str, Any]:
    """사례 dict — 넘김 · 검사 걸림 · 고쳐 보냄(``reason`` = ``edited`` · AI 초안 · 고친 까닭)."""
    edited = row.state != STATE_SKIPPED
    reason = EDITED if edited else row.handoff_reason if row.error_code == SKIP_HANDOFF else SKIP_CHECK
    return {"turn_id": row.id, "chat_id": row.chat_id, "intent": row.intent, "reason": reason,
            "question": row.masked_question, "reply": row.staff_reply_masked, "context": row.masked_context,
            "anchor": row.last_user_message_id, "staff": _staff(row), "taught": row.send_state == SEND_SENT and not edited,
            "draft": row.masked_draft if edited else None, "why": row.edit_detail_masked if edited else None,
            "chip": row.edit_reason if edited else None}


def collect_cases(session: Any, now: datetime.datetime, *, cap: int, edits: bool = False) -> list[dict[str, Any]]:
    """읽기(모듈 설명 1) — 사례 dict(차례 id · 상담 id · 의도 · 넘긴 까닭 · 가린 질문 · 가린 직원 답 · 질문 앞 6줄 · 기준 글 id)."""
    used = used_ids(session)
    out = []
    for row in _turn_rows(session, naive_utc(now - LOOKBACK), edits=edits):
        if row.id in used or _human_only(row) or not (row.staff_reply_masked or "").strip():
            continue
        out.append(_case(row))
        if len(out) >= cap:
            break
    return out


def _talks(reader: Any, cfg: Any, cases: Sequence[dict[str, Any]]) -> dict[int, str]:
    """사례마다 앞뒤 대화 글 — 차례 id → 글. 상담마다 한 번만 읽는다(이 부르기 메모리에서만). 끔 · 읽기 도우미 없음 · 못 읽음 ·
    그 손님 글을 못 찾음이면 빠진다(그 사례는 질문 앞 6줄)."""
    if not talk_on(cfg) or reader is None or not cases:
        return {}
    limit = case_limit(cfg, len(cases))
    read: dict[str, Optional[Talk]] = {}
    out: dict[int, str] = {}
    for case in cases:
        chat = str(case["chat_id"] or "")
        if chat and chat not in read:
            read[chat] = read_talk(reader, SEND_BRAND, chat, cfg)
        talk = read.get(chat)
        text = talk_window(talk, str(case["anchor"] or ""), limit) if talk is not None else None
        if text:
            out[case["turn_id"]] = text
    return out


def _cap(cfg: Any) -> int:
    """패널 '한 번에 읽는 사례 수'."""
    value = cfg.get(CASES_FIELD)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 20


def _known(session: Any) -> str:
    """숫자 허용 글 — 회사 지식(반영 · 확정) + 라홈 상담 승인 지식."""
    cs = load_approved(session, SEND_BRAND)
    return "\n".join([known_text(session), *(item.text for item in cs.items)])


def _propose(session: Any, sent: list[dict[str, Any]], blocks: list[list[str]], used: list[int], *, cfg: Any,
             now: datetime.datetime, client: Any, counts: dict[str, Any]) -> None:
    """두뇌 → 읽음 표 → 관문 → 제안 길(모듈 설명 3 · 4)."""
    rows = knowledge_rows(session)
    knowledge, approved = knowledge_lines(rows), [row.text for row in rows if row.text]
    pending = pending_lines([(label, text) for status, _key, label, text in seen_proposals(session)
                             if status == CHANGE_OPEN][:MAX_PENDING])
    params = build_params(blocks, knowledge, pending, model=str(cfg.get(WEEKLY_MODEL_FIELD)), cfg=cfg)
    session.commit()
    called = call_learning(session, params, cfg=cfg, now=now, timeout_s=TIMEOUT_S, client=client)
    mark_used(session, used)
    raw = raw_proposals(called.response)
    counts["proposed"] = len(raw)
    known = _known(session)
    approved += [item.text for item in load_approved(session, SEND_BRAND).items]
    got = file_proposals(session, raw, sent, now=now, known=known, approved=approved)
    session.commit()
    counts["filed"] = got.pop("filed")
    counts["blocked"] = got


def run_handoff_learning(session: Any, *, now: datetime.datetime, client: Any = None,
                         reader: Any = None) -> dict[str, Any]:
    """넘김 학습 한 번(모듈 설명). 커밋한다. 숫자 · 코드만 돌려준다 — 반영하는 일은 하지 않는다(승인은 사람).

    ``reader`` 는 전체 대화를 읽는 채널톡 읽기 도우미(감시 바퀴가 넘긴다 — 없으면 앞뒤 대화 없이 질문 앞 6줄)."""
    if not in_window(now):
        return {"off": "not_window"}
    off, cfg = off_reason(session, HANDOFF_LEARN_FIELD)
    if off is not None:
        session.rollback()
        return {"off": off}
    day = day_id(now)
    if not claim_day(session, day):
        return {"off": "already_today"}
    cases = collect_cases(session, now, cap=_cap(cfg), edits=cfg.get(EDIT_LEARN_FIELD) is True)
    session.commit()  # 채널톡 읽기 동안 읽기 트랜잭션을 열어 두지 않는다
    talks = _talks(reader, cfg, cases)
    counts: dict[str, Any] = {"day": day, "cases": len(cases), "talks": len(talks), "mask_dropped": 0, "sent": 0,
                              "proposed": 0, "filed": 0, "blocked": {}, "halted": None}
    sent, blocks, dropped = [], [], []
    for case in cases:
        try:
            blocks.append(case_lines({**case, "talk": talks.get(case["turn_id"])}))
            sent.append(case)
        except MaskLeak:  # 그 사례만 뺀다(가림 검사 — 글은 남기지 않는다)
            dropped.append(case["turn_id"])
    counts.update(mask_dropped=len(dropped), sent=len(sent))
    if len({case["chat_id"] for case in sent}) < EVIDENCE_MIN_CHATS:
        mark_used(session, dropped)
        counts["halted"] = "too_few_customers" if sent else None
    else:
        try:
            _propose(session, sent, blocks, [*(case["turn_id"] for case in sent), *dropped], cfg=cfg, now=now,
                     client=client, counts=counts)
        except MaskLeak:
            session.rollback()
            counts["halted"] = "mask_leak"
        except BrainError as exc:
            session.rollback()
            counts["halted"] = exc.code
    logger.info("[CS 넘김 학습] day=%s cases=%d talks=%d mask_dropped=%d sent=%d proposed=%d filed=%d blocked=%s "
                "halted=%s", day, counts["cases"], counts["talks"], counts["mask_dropped"], counts["sent"],
                counts["proposed"], counts["filed"], counts["blocked"], counts["halted"])
    return counts
