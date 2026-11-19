"""넘긴 상담 배우기 — 직원이 직접 한 답을 날마다 회사 지식으로(사장님 11-11 '넘긴 것을 학습해서 다음엔 AI 가 답하게' · 11-19
'매일 학습하고 온톨로지 만들고 계속 업그레이드 — 매번 승인 대신 즉시 반영, 내가 확인하고 추후 수정 · 삭제').

AI 가 답을 몰라 넘긴 차례(``skipped`` · ``handoff``)나 보내기 전 검사에 걸린 차례(``check_failed``)에는 직원이 데스크에서 직접
답한다(사례 기억 :mod:`.case_memory` 가 가린 직원 답을 붙인다). 지금 사례 재료(:mod:`.case_material` · :mod:`.brain_cases`)는
이것을 '말투 · 순서만 참고'로 쓰고 그 안의 사실은 다음 초안에 쓰지 않는다. 이 길이 그 사실 · 정책 · 상황 · 제작 조건 · 비슷한 말을
회사 지식으로 만든다(사진 학습 :mod:`.photo_learning` 과 같은 제안 길).

WORKER 15분 바퀴 학습 몫(:mod:`.learning_pass`)이 부르고, **밤(KST :data:`WINDOW_HOURS`) 창 안에서 남은 사례가 없을 때까지**
바퀴마다 한 번씩 돈다(:data:`MAX_RUNS` 번까지 — 부르기 전에 횟수와 잠깐 잠금을 남긴다, :func:`claim_day`. 재시작 · 두 컨테이너가
겹쳐도 같은 사례를 두 번 읽지 않게). 읽을 사례가 없거나 부르기가 실패하면 그 밤을 닫는다(:func:`close_day`). 창은 월요일 새벽
주간 고침 안 · 사진 학습 창(3 ~ 6시) 앞이다. 끄고 켜기는 :func:`.learning_brain.off_reason`(패널 '넘긴 상담 배우기' — 처음 끔 ·
비상 정지 · 초안 끔 · 학습 돈 상한).

1. **읽기(가린 글만)**: 지난 7일(:data:`.weekly_fix.LOOKBACK`) 라홈 차례 가운데 ``skipped`` 이고 (넘김 + 까닭
   :data:`LEARN_REASONS`) 또는 보내기 전 검사에 걸린 것, 가린 직원 답이 있고 끝난 꼴이 학습 재료(복사 · 버림 제외)이며 떼어 둔
   줄이 아닌 것. 늘 사람이 답하는 까닭(:data:`HUMAN_ONLY_REASONS` — 불만 · 주문 조회 · 할인 · 환불 · 사람만 말하는 금액)과 그런
   검사 코드(:data:`HUMAN_ONLY_CHECKS`) · 견적 계산 차례(금액 정본은 계산기)는 뺀다 — 다만 직원이 넘김 메모 [배우기]로 직접
   보낸 차례(``send_state`` 보냄 — :mod:`.handoff_send`)는 그 까닭이어도 읽는다('AI 냐' 차례 빼고). [흘리기]한 차례는 끝난 꼴
   '버림'이라 늘 빠진다. 패널 '초안이 나간 상담도 배우기'가 켜져 있으면 AI 초안을 직원이 고쳐 보냈거나(``edited``) 초안을 안 쓰고
   직접 답한(``direct``) 차례도 읽는다. **이미 읽은 차례는 다시 읽지 않는다**(:func:`used_ids`). **새 것부터** 패널 '한 번에 읽는
   사례 수'만 — 오늘 상담을 오늘 밤 배우고, 남은 밀린 사례는 같은 밤 다음 바퀴가 읽는다(예전에는 오래된 것부터 하루 한 번이라
   배우기가 엿새쯤 밀렸고 7일이 지난 사례는 못 읽은 채 빠졌다 — 운영 11-19 지난 7일 배울 사례 144 가운데 5만 읽음).
   **창을 '지난번 성공한 날부터'가 아니라 늘 7일로 둔 까닭**: 읽은 차례 표가 이미 같은 사례를 두 번 막는다. 움직이는 시작점을
   두면 실패한 밤 · 밤 뒤에 붙은 직원 답이 시작점과 표 사이에서 조용히 빠진다.
2. **재료 — 상담 전체 대화 · 사진(사장님 11-19)**: 상담마다 전체 대화(:func:`.full_conversation.read_talk` — 가린 글)를 한 번
   읽고, 그 상담의 차례들이 읽은 손님 사진 설명(:func:`.image_summaries.summaries_by_turn`)을 그 사진이 온 글 자리에 ``▶`` 줄로
   끼운다. 자 수 상한(패널 상한과 한 번 합 ÷ 상담 수) 안이면 전체를 한 번만 싣고 같은 상담의 다른 사례는 그 대화를 가리킨다.
   넘으면 사례마다 그 손님 글을 가운데 둔 앞뒤 대화 창(:func:`.handoff_learning_prompt.talk_window`). 대화를 못 읽으면 질문 앞
   6줄. 조각마다 가림 검사 — 하나라도 걸리면 그 사례만 뺀다(``mask_dropped``). 보낼 사례가 하나도 없으면 두뇌를 부르지 않는다.
3. **두뇌(학습 모델 — 주간 고침 안 모델 칸)**: 회사 지식 · 온톨로지 목록과 견줘 안(사실 · 정책 새로 만들기 · 고치기 · 다른 말,
   상황 · 제작 조건 · 비슷한 말 · 잇기)을 구조화 출력으로. 부르기가 끝나면 보낸 차례를 '읽음'으로 적는다(같은 사례를 다음 밤에
   다시 보내지 않는다 — 부르기가 실패하면 적지 않아 다음 밤에 다시 본다).
4. **관문 · 넣기**(:mod:`.handoff_learning_gates` · :mod:`.handoff_learning_onto`): 꼴 · 가림 · 근거 · 숫자 · 대상 · 같음 · 겹침 ·
   부딪침 → 제안 길. 패널 '배운 것 바로 반영'이 켜져 있으면 관문을 지난 안을 그 자리에서 반영하고(:func:`auto_learn` — 사람
   승인자 칸은 비워 '사람이 아직 안 봄'으로 남는다), 꺼져 있으면 '승인 대기'로만. 지금 지식과 다른 말은 어느 쪽이든 덮어쓰지
   않고 승인 대기 ③ 엇갈림 카드로 모은다.

로그 · 결과에는 숫자 · 코드만 싣는다(글 · 상담 id 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.brain.apply import AutoLearn
from foms.services.brain.constants import CHANGE_OPEN
from foms.services.brain.proposals import known_text
from foms.services.cs_agent.brain_spend import BrainError
from foms.services.cs_agent import photo_learning_prompt as onto_prompt
from foms.services.cs_agent.case_memory import LEARNING_OUTCOMES, OUTCOME_DIRECT, OUTCOME_EDITED
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.drafting import SKIP_CHECK, SKIP_HANDOFF
from foms.services.cs_agent.edit_detail_settings import WEEKLY_MODEL_FIELD
from foms.services.cs_agent.full_conversation import MIN_CASE_CHARS, case_limit, read_talk, talk_on, talk_text
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD, CASES_FIELD, EDIT_LEARN_FIELD, HANDOFF_LEARN_FIELD
from foms.services.cs_agent.handoff_learning_gates import EVIDENCE_MIN_CHATS, file_proposals, seen_proposals
from foms.services.cs_agent.handoff_learning_onto import file_ontology
from foms.services.cs_agent.handoff_learning_prompt import (
    anchor_mark, build_params, case_lines, complete, knowledge_lines, knowledge_rows, pending_lines, raw_ontology,
    raw_proposals, talk_window,
)
from foms.services.cs_agent.image_summaries import summaries_by_turn
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.learning_brain import call_learning, off_reason
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.send import SEND_BRAND
from foms.services.cs_agent.send_record import NOT_TAUGHT_REASONS, SEND_SENT
from foms.services.cs_agent.state import KST
from foms.services.cs_agent.turns import STATE_SKIPPED
from foms.services.cs_agent.weekly_fix import LOOKBACK
from models import CsAgentTurn, SecurityLog, SystemSetting, User

logger = logging.getLogger(__name__)

__all__ = [
    "HUMAN_ONLY_CHECKS", "HUMAN_ONLY_REASONS", "LEARN_REASONS", "QUOTE_PREFIX", "STORE_KEY", "WINDOW_HOURS",
    "DIRECT", "EDITED", "LEASE", "MAX_RUNS", "auto_learn", "claim_day", "close_day", "collect_cases", "day_id",
    "in_window", "mark_used", "release", "run_handoff_learning", "used_ids",
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
MAX_DAYS, MAX_USED, MAX_SCAN, MAX_PENDING, TIMEOUT_S = 14, 2000, 2000, 30, 300
EDITED = "edited"  # 사례 갈래 — AI 초안을 직원이 고쳐 보낸 차례(패널 '초안이 나간 상담도 배우기')
DIRECT = "direct"  # 사례 갈래 — AI 초안을 안 쓰고 직원이 직접 답한 차례(같은 칸)
#: 한 밤에 부르는 횟수 상한(창 2시간 · 15분 바퀴) · 부르는 동안의 잠깐 잠금(겹친 컨테이너가 같은 사례를 읽지 않게).
MAX_RUNS, LEASE = 8, datetime.timedelta(minutes=10)


def day_id(now: datetime.datetime) -> str:
    """KST 날 이름(예 ``2026-11-11``)."""
    return now.astimezone(KST).date().isoformat()


def in_window(now: datetime.datetime) -> bool:
    """KST :data:`WINDOW_HOURS` 안인가(날마다)."""
    return WINDOW_HOURS[0] <= now.astimezone(KST).hour < WINDOW_HOURS[1]


# ── 날 표 · 읽은 차례 표(SystemSetting 한 줄) ─────────────────────────────
def _doc(row: Any) -> dict[str, Any]:
    """저장 값 → ``{"days": [닫은 KST 날], "used": [차례 id], "runs": {KST 날: 부른 횟수}, "lease": 잠금 끝 시각}`` 사본(틀린
    칸은 빈 값)."""
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    days = [d for d in value.get("days") or [] if isinstance(d, str)] if isinstance(value.get("days"), list) else []
    used = ([i for i in value.get("used") or [] if isinstance(i, int) and not isinstance(i, bool)]
            if isinstance(value.get("used"), list) else [])
    runs = value.get("runs") if isinstance(value.get("runs"), dict) else {}
    runs = {d: n for d, n in runs.items() if isinstance(d, str) and isinstance(n, int) and not isinstance(n, bool)}
    lease = value.get("lease") if isinstance(value.get("lease"), str) else None
    return {"days": days, "used": used, "runs": runs, "lease": lease}


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


def _leased(doc: dict[str, Any], now: datetime.datetime) -> bool:
    """다른 부르기가 아직 도는가(잠금 끝 시각이 지금보다 뒤)."""
    try:
        return doc["lease"] is not None and datetime.datetime.fromisoformat(doc["lease"]) > now
    except ValueError:
        return False


def claim_day(session: Any, day: str, now: Optional[datetime.datetime] = None) -> bool:
    """이 밤에 한 번 더 불러도 되면 횟수 · 잠깐 잠금을 남기고(커밋) 참 — 그 밤을 닫았거나(:func:`close_day`) :data:`MAX_RUNS` 번
    불렀거나 다른 부르기가 도는 중이면 거짓(두 컨테이너가 겹쳐도 같은 사례를 두 번 읽지 않는다)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    row = _locked(session)
    doc = _doc(row)
    done = doc["runs"].get(day, 0)
    if day in doc["days"] or done >= MAX_RUNS or _leased(doc, now):
        session.rollback()
        return False
    runs = dict(sorted({**doc["runs"], day: done + 1}.items())[-MAX_DAYS:])
    _put(row, {**doc, "runs": runs, "lease": (now + LEASE).isoformat()})
    session.commit()
    return True


def release(session: Any) -> None:
    """잠깐 잠금을 푼다(커밋) — 한 번 부르기가 끝났다."""
    row = _locked(session)
    _put(row, {**_doc(row), "lease": None})
    session.commit()


def close_day(session: Any, day: str) -> None:
    """그 밤을 닫는다(커밋) — 읽을 사례가 없거나 부르기가 실패했다. 다음 바퀴는 다음 밤까지 부르지 않는다."""
    row = _locked(session)
    doc = _doc(row)
    if day not in doc["days"]:
        _put(row, {**doc, "days": [*doc["days"], day][-MAX_DAYS:]})
    session.commit()


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
    """지난 7일 넘김 · 검사 걸림 차례(가린 직원 답이 있는 것 · 떼어 둔 줄 제외) — 가린 칸 · 코드만, **새 것부터**.
    ``edits`` 면 AI 초안이 나간 차례 가운데 직원이 고쳐 보냈거나(끝난 꼴 '고침') 초안을 안 쓰고 직접 답한 것(끝난 꼴 '직접 답')도."""
    turn = CsAgentTurn
    taught = and_(turn.error_code.in_((SKIP_HANDOFF, SKIP_CHECK)), turn.send_state == SEND_SENT,
                  or_(turn.handoff_reason.is_(None), turn.handoff_reason.notin_(NOT_TAUGHT_REASONS)))
    learnable = or_(and_(turn.error_code == SKIP_HANDOFF, turn.handoff_reason.in_(LEARN_REASONS)),
                    and_(turn.error_code == SKIP_CHECK,
                         or_(turn.handoff_reason.is_(None), turn.handoff_reason.notin_(HUMAN_ONLY_REASONS))),
                    taught)
    picked = and_(turn.state == STATE_SKIPPED, learnable)
    if edits:  # 사장님 11-11 고친 답 + 까닭 · 11-19 '모든 대화' — 초안을 안 쓰고 직접 답한 것도
        picked = or_(picked, and_(turn.state != STATE_SKIPPED, turn.outcome.in_((OUTCOME_EDITED, OUTCOME_DIRECT))))
    stmt = (select(turn.id, turn.chat_id, turn.intent, turn.error_code, turn.handoff_reason, turn.check_codes,
                   turn.masked_question, turn.staff_reply_masked, turn.masked_context, turn.last_user_message_id,
                   turn.desk_manager_id, turn.send_state, turn.state, turn.masked_draft, turn.edit_reason,
                   turn.edit_detail_masked, turn.sent_by_user_id, turn.outcome)
            .where(turn.brand == SEND_BRAND, picked,
                   turn.outcome.in_(LEARNING_OUTCOMES), turn.held_out.is_(False), turn.staff_reply_masked.isnot(None),
                   turn.updated_at >= since)
            .order_by(turn.id.desc()).limit(MAX_SCAN))
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
    """사례 dict — 넘김 · 검사 걸림 · 고쳐 보냄(``reason`` = ``edited`` · AI 초안 · 고친 까닭) · 초안 안 씀(``direct`` · AI 초안)."""
    drafted = row.state != STATE_SKIPPED
    edited = drafted and row.outcome == OUTCOME_EDITED
    reason = (EDITED if edited else DIRECT if drafted
              else row.handoff_reason if row.error_code == SKIP_HANDOFF else SKIP_CHECK)
    return {"turn_id": row.id, "chat_id": row.chat_id, "intent": row.intent, "reason": reason,
            "question": row.masked_question, "reply": row.staff_reply_masked, "context": row.masked_context,
            "anchor": row.last_user_message_id, "staff": _staff(row), "taught": row.send_state == SEND_SENT and not drafted,
            "draft": row.masked_draft if drafted else None, "why": row.edit_detail_masked if edited else None,
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


def _photo_marks(session: Any, chats: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    """상담 → (메시지 id → 사진 줄) — 그 상담의 모든 차례가 읽은 손님 사진 설명(가린 글 · 같은 사진은 한 번)."""
    rows = session.execute(select(CsAgentTurn.id, CsAgentTurn.chat_id).where(
        CsAgentTurn.brand == SEND_BRAND, CsAgentTurn.chat_id.in_(list(chats))).order_by(CsAgentTurn.id)).all() if chats else []
    seen = summaries_by_turn(session, [row.id for row in rows])
    out: dict[str, dict[str, list[str]]] = {}
    shown: set[tuple[str, str, str]] = set()
    for row in rows:
        for line in seen.get(row.id, ()):
            chat = str(row.chat_id)
            if (chat, line.message_id, line.text) in shown:
                continue
            shown.add((chat, line.message_id, line.text))
            marks = out.setdefault(chat, {})
            number = sum(len(lines) for lines in marks.values()) + 1
            marks.setdefault(line.message_id, []).append(f"▶ 사진 {number} (손님) {line.text}")
    return out


def _talks(reader: Any, cfg: Any, cases: Sequence[dict[str, Any]],
           photos: Optional[dict[str, dict[str, list[str]]]] = None) -> dict[int, dict[str, Any]]:
    """사례마다 대화 재료 — 차례 id → ``{"talk": 글, "whole": 전체인가}`` 또는 ``{"talk_ref": 그 대화를 실은 사례}``(모듈 설명 2).
    상담마다 한 번만 읽는다(이 부르기 메모리에서만). 끔 · 읽기 도우미 없음 · 못 읽음 · 그 손님 글을 못 찾음이면 빠진다(그 사례는
    질문 앞 6줄)."""
    if not talk_on(cfg) or reader is None or not cases:
        return {}
    by_chat: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        by_chat.setdefault(str(case["chat_id"] or ""), []).append(case)
    limit = case_limit(cfg, len(by_chat))
    out: dict[int, dict[str, Any]] = {}
    for chat, mine in by_chat.items():
        talk = read_talk(reader, SEND_BRAND, chat, cfg) if chat else None
        if talk is None:
            continue
        pictures = (photos or {}).get(chat) or {}
        if sum(len(text) for _, text in talk.turns) <= limit:  # 전체가 들어간다 — 한 번만 싣고 나머지는 가리킨다
            marks = {key: list(lines) for key, lines in pictures.items()}
            for case in mine:
                if str(case["anchor"] or "") in talk.ids:
                    marks.setdefault(str(case["anchor"]), []).append(anchor_mark(case["turn_id"]))
            whole = talk_text(talk, limit=limit, marks=marks)
            if whole:
                out[mine[0]["turn_id"]] = {"talk": whole, "whole": True}
                out.update({case["turn_id"]: {"talk_ref": mine[0]["turn_id"]} for case in mine[1:]})
                continue
        share = max(MIN_CASE_CHARS, limit // len(mine))
        for case in mine:
            text = talk_window(talk, str(case["anchor"] or ""), share, pictures)
            if text:
                out[case["turn_id"]] = {"talk": text}
    return out


def _blocks(cases: Sequence[dict[str, Any]], talks: dict[int, dict[str, Any]],
            ) -> tuple[list[dict[str, Any]], list[list[str]], list[int]]:
    """사례 줄 만들기 — (보낼 사례, 사례 줄, 가림 검사로 뺀 차례 id). 전체 대화를 실은 사례가 빠지면 같은 상담의 다음 사례가
    대신 싣는다."""
    sent, blocks, dropped = [], [], []
    holder: dict[int, int] = {}
    for case in cases:
        extra = dict(talks.get(case["turn_id"]) or {})
        first = extra.get("talk_ref")
        if first is not None:
            extra = {"talk_ref": holder[first]} if first in holder else dict(talks.get(first) or {})
        try:
            blocks.append(case_lines({**case, **extra}))
        except MaskLeak:  # 그 사례만 뺀다(가림 검사 — 글은 남기지 않는다)
            dropped.append(case["turn_id"])
            continue
        sent.append(case)
        if extra.get("whole"):
            holder[first if first is not None else case["turn_id"]] = case["turn_id"]
    return sent, blocks, dropped


def auto_learn(session: Any, cfg: Any) -> Optional[AutoLearn]:
    """패널 '배운 것 바로 반영'이 켜져 있으면 그 길(:class:`foms.services.brain.apply.AutoLearn`), 아니면 ``None``.

    누구 이름으로 감사 · 판 줄을 남기나 — 그 칸을 마지막으로 바꾼 사람이 지금도 켜진 ADMIN 이면 그 사람, 아니면 가장 먼저 만든
    켜진 ADMIN. 켜진 ADMIN 이 하나도 없으면 ``None``(승인 대기로만)."""
    if cfg.get(AUTO_FIELD) is not True:
        return None
    admins = [int(i) for i in session.execute(select(User.id).where(
        func.upper(User.role) == "ADMIN", User.is_active.is_(True)).order_by(User.id)).scalars()]
    last = session.execute(select(SecurityLog.user_id).where(
        SecurityLog.action == "CS_AGENT_SETTINGS_UPDATE", SecurityLog.message.like(f"%{AUTO_FIELD}%"))
        .order_by(SecurityLog.id.desc()).limit(1)).scalar()
    if last in admins:
        return AutoLearn(int(last))
    return AutoLearn(admins[0]) if admins else None


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
    """두뇌 → 읽음 표 → 관문 → 제안 길 · 바로 반영(모듈 설명 3 · 4)."""
    rows = knowledge_rows(session)
    knowledge, approved = knowledge_lines(rows), [row.text for row in rows if row.text]
    ontology = onto_prompt.knowledge_lines(onto_prompt.knowledge_rows(session))
    pending = pending_lines([(label, text) for status, _key, label, text in seen_proposals(session)
                             if status == CHANGE_OPEN][:MAX_PENDING])
    params = build_params(blocks, knowledge, pending, model=str(cfg.get(WEEKLY_MODEL_FIELD)), cfg=cfg,
                          ontology=ontology)
    session.commit()
    called = call_learning(session, params, cfg=cfg, now=now, timeout_s=TIMEOUT_S, client=client)
    if not complete(called.response):  # 출력 상한에 끊김 · 거절 — 읽음으로 적지 않는다(안이 통째로 사라지지 않게)
        counts["halted"] = "incomplete"
        return
    mark_used(session, used)
    raw, onto = raw_proposals(called.response), raw_ontology(called.response)
    counts["proposed"] = len(raw) + len(onto)
    known = _known(session)
    approved += [item.text for item in load_approved(session, SEND_BRAND).items]
    auto = auto_learn(session, cfg)
    session.commit()
    got = file_proposals(session, raw, sent, now=now, known=known, approved=approved, auto=auto)
    more = file_ontology(session, onto, sent, now=now, known=known, auto=auto)
    session.commit()
    for name, key in (("filed", "filed"), ("applied", "applied"), ("cards", "conflict_card")):
        counts[name] = got.pop(key, 0) + more.pop(key, 0)
    counts["blocked"] = {code: got.get(code, 0) + more.get(code, 0) for code in sorted({*got, *more})}


def run_handoff_learning(session: Any, *, now: datetime.datetime, client: Any = None,
                         reader: Any = None) -> dict[str, Any]:
    """넘김 학습 한 번(모듈 설명). 커밋한다. 숫자 · 코드만 돌려준다.

    ``reader`` 는 전체 대화를 읽는 채널톡 읽기 도우미(감시 바퀴가 넘긴다 — 없으면 앞뒤 대화 없이 질문 앞 6줄)."""
    if not in_window(now):
        return {"off": "not_window"}
    off, cfg = off_reason(session, HANDOFF_LEARN_FIELD)
    if off is not None:
        session.rollback()
        return {"off": off}
    day = day_id(now)
    if not claim_day(session, day, now):
        return {"off": "already_today"}
    cases = collect_cases(session, now, cap=_cap(cfg), edits=cfg.get(EDIT_LEARN_FIELD) is True)
    photos = _photo_marks(session, sorted({str(case["chat_id"] or "") for case in cases} - {""}))
    session.commit()  # 채널톡 읽기 동안 읽기 트랜잭션을 열어 두지 않는다
    talks = _talks(reader, cfg, cases, photos)
    counts: dict[str, Any] = {"day": day, "cases": len(cases), "talks": len(talks), "mask_dropped": 0, "sent": 0,
                              "proposed": 0, "filed": 0, "applied": 0, "cards": 0, "blocked": {}, "halted": None}
    try:
        _run(session, cases, talks, cfg=cfg, now=now, client=client, counts=counts)
    except Exception:  # 뜻밖의 오류 — 그 밤을 닫고 잠금을 푼 뒤 그대로 올린다(학습 몫이 길 이름 · 예외 종류만 적는다)
        session.rollback()
        close_day(session, day)
        release(session)
        raise
    if not cases or counts["halted"] is not None:  # 남은 사례가 없다 · 부르기가 실패했다 — 이 밤은 여기까지
        close_day(session, day)
    release(session)
    logger.info("[CS 넘김 학습] day=%s cases=%d talks=%d mask_dropped=%d sent=%d proposed=%d filed=%d applied=%d "
                "cards=%d blocked=%s halted=%s", day, counts["cases"], counts["talks"], counts["mask_dropped"],
                counts["sent"], counts["proposed"], counts["filed"], counts["applied"], counts["cards"],
                counts["blocked"], counts["halted"])
    return counts


def _run(session: Any, cases: list[dict[str, Any]], talks: dict[int, dict[str, Any]], *, cfg: Any,
         now: datetime.datetime, client: Any, counts: dict[str, Any]) -> None:
    """사례 줄 → 두뇌 → 넣기(:func:`run_handoff_learning` 의 가운데 — 수는 ``counts`` 에 채운다)."""
    sent, blocks, dropped = _blocks(cases, talks)
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
