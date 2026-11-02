"""챗봇 기록 — ``brain_questions`` 한 줄 · 사람마다 하루 질문 수 · 피드백 · 보관 1년(설계서 10.3 · 12절 '직원 감시로 읽힘').

- 기록 칸: **가린 질문**(가림 검사 0 인 글만 — 가림이 못 지운 글은 기록 · 모델 어디에도 가지 않는다) · 보인 답 · 근거 키 · 모름 ·
  확신(모델) · 물을 곳 · 층 · 모델 · 묻는 사람 번호(ADMIN 만 본다) · 피드백(도움 됨 · 안 됨 · 틀림) · 고칠 말(가린 글).
- **직원별 모아 보기는 만들지 않는다**(근로 감시 — 원장 Q20). 사람 번호는 하루 질문 수 상한과 '내 질문에만 피드백'에만 쓴다.
- 피드백은 묻는 사람 자기 질문에만. '틀림'이면 그 답의 근거 항목마다 신고 한 줄(:mod:`.chat_reports`)이 붙고, 같은 항목에 서로
  다른 사람 둘 이상이면 이름 있는 에이전트 액션 ``report_conflict``(:func:`.action_runner.perform_agent`)로 승인자에게 올린다.
- :func:`purge_questions` — 1년 지난 질문 · 신고를 지운다(밤 단계 ``tools/cron/purge_brain_questions.py``).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable, Optional

from sqlalchemy import delete, func, select

from foms.persistence.brain.models import BrainQuestion, BrainWrongReport
from foms.services.brain.action_runner import perform_agent
from foms.services.brain.chat_reports import CHAT_AGENT, add_reports, drop_reports, raisable
from foms.services.brain.embeddings import SOURCE_QUESTION, drop_vectors
from foms.services.brain.errors import BrainError
from foms.services.cs_agent.masking import leak_counts, mask

logger = logging.getLogger(__name__)

FEEDBACKS: tuple[str, ...] = ("helpful", "not_helpful", "wrong")
KEEP_DAYS = 365
MAX_NOTE = 500
PURGE_BATCH = 1000
_KST = datetime.timedelta(hours=9)


class ChatFeedbackError(ValueError):
    """피드백을 받을 수 없다 — ``code``: ``not_found``(없거나 내 질문이 아님) · ``shape`` · ``mask``(고칠 말에 개인정보)."""

    def __init__(self, code: str) -> None:
        """코드만."""
        super().__init__(code)
        self.code = code


def kst_day_start(now_utc: datetime.datetime) -> datetime.datetime:
    """UTC naive 지금 → 그 한국 날 0시(UTC naive)."""
    local = now_utc + _KST
    return datetime.datetime(local.year, local.month, local.day) - _KST


def asked_today(session: Any, asker_id: int, now_utc: datetime.datetime) -> int:
    """이 사람이 오늘(한국 날) 물은 수(기록된 질문)."""
    return int(session.execute(select(func.count()).select_from(BrainQuestion).where(
        BrainQuestion.asker_id == int(asker_id), BrainQuestion.asked_at >= kst_day_start(now_utc))).scalar_one())


def log_question(session: Any, *, asker_id: int, masked_question: str, answer: str, evidence: Iterable[str],
                 unknown: bool, confidence: Optional[str], ask_team: Optional[str], layer: Optional[str],
                 model: Optional[str], now_utc: datetime.datetime) -> BrainQuestion:
    """질문 한 줄을 넣는다(가린 글만 · flush 만)."""
    row = BrainQuestion(asked_at=now_utc, asker_id=int(asker_id), masked_question=masked_question, answer=answer,
                        evidence_keys=list(evidence), unknown=bool(unknown), confidence=confidence,
                        ask_team=ask_team, layer=layer, model=model)
    session.add(row)
    session.flush()
    return row


def masked_note(note: Any) -> Optional[str]:
    """고칠 말 → 가린 글(비면 ``None``). 가린 뒤에도 개인정보 꼴이 남으면 :class:`ChatFeedbackError` ``mask``."""
    if note is None or (isinstance(note, str) and not note.strip()):
        return None
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise ChatFeedbackError("shape")
    hidden = mask(note.strip())
    if any(leak_counts(hidden).values()):
        raise ChatFeedbackError("mask")
    return hidden


def raise_reported(session: Any, keys: Iterable[str], *, now_utc: datetime.datetime) -> list[str]:
    """서로 다른 사람 둘 이상인 항목을 승인자에게 올린다(이름 있는 에이전트 액션 — 관문을 못 넘으면 신고만 남긴다)."""
    raised = []
    for key in dict.fromkeys(keys):
        if not raisable(session, key):
            continue
        try:
            with session.begin_nested():
                perform_agent(session, "report_conflict", agent=CHAT_AGENT, body={"key": key}, now=now_utc)
            raised.append(key)
        except BrainError as exc:
            logger.warning("[회사 지식 물어보기] 틀림 신고를 올리지 못했다 key=%s code=%s", key, exc.code)
    return raised


def record_feedback(session: Any, *, question_id: Any, asker_id: int, feedback: Any, note: Any,
                    now_utc: datetime.datetime) -> dict[str, Any]:
    """내 질문에 피드백 — 틀림이면 근거 항목마다 신고 · 둘 이상이면 승인자에게. 커밋은 부르는 쪽.

    Raises:
        ChatFeedbackError: 없음 · 내 질문 아님(``not_found`` — 같은 답) · 꼴 · 고칠 말 가림 실패.
    """
    if feedback not in FEEDBACKS or isinstance(question_id, bool) or not isinstance(question_id, int):
        raise ChatFeedbackError("shape")
    row = session.get(BrainQuestion, question_id, with_for_update=True)
    if row is None or row.asker_id != int(asker_id):
        raise ChatFeedbackError("not_found")
    hidden = masked_note(note)
    row.feedback, row.feedback_note = feedback, hidden
    keys = [k for k in (row.evidence_keys or []) if isinstance(k, str)]
    raised: list[str] = []
    if feedback == "wrong" and keys:
        add_reports(session, question_id=row.id, reporter_id=row.asker_id, keys=keys, note=hidden, now=now_utc)
        raised = raise_reported(session, keys, now_utc=now_utc)
    else:
        drop_reports(session, question_id=row.id)
    session.flush()
    return {"id": row.id, "feedback": feedback, "reported": feedback == "wrong" and bool(keys), "raised": raised}


def purge_questions(session: Any, *, now_utc: datetime.datetime, keep_days: int = KEEP_DAYS,
                    batch: int = PURGE_BATCH) -> dict[str, int]:
    """보관 기간이 지난 질문 · 신고 · 질문 벡터를 지운다(묶음마다 flush — 커밋은 부르는 쪽). ``{"questions", "reports", "vectors"}``."""
    cutoff = now_utc - datetime.timedelta(days=int(keep_days))
    gone = {"questions": 0, "reports": 0, "vectors": 0}
    while True:
        ids = list(session.execute(select(BrainQuestion.id).where(BrainQuestion.asked_at < cutoff)
                                   .order_by(BrainQuestion.id).limit(batch)).scalars())
        if not ids:
            break
        gone["reports"] += session.execute(delete(BrainWrongReport).where(
            BrainWrongReport.question_id.in_(ids)).execution_options(synchronize_session=False)).rowcount or 0
        gone["vectors"] += drop_vectors(session, SOURCE_QUESTION, (str(i) for i in ids))  # 질문 벡터도 같이(1년)
        gone["questions"] += session.execute(delete(BrainQuestion).where(
            BrainQuestion.id.in_(ids)).execution_options(synchronize_session=False)).rowcount or 0
        session.flush()
    gone["reports"] += session.execute(delete(BrainWrongReport).where(
        BrainWrongReport.created_at < cutoff).execution_options(synchronize_session=False)).rowcount or 0
    return gone
