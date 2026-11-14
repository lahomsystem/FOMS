"""챗봇 기록 — ``brain_questions`` 한 줄 · 사람마다 하루 질문 수 · 피드백 · 보관 1년(설계서 10.3 · 12절 '직원 감시로 읽힘').

- 기록 칸: **가린 질문**(가림 검사 0 인 글만 — 가림이 못 지운 글은 기록 · 모델 어디에도 가지 않는다) · 보인 답 · 근거 키 · 모름 ·
  확신(모델) · 물을 곳 · 층 · 모델 · 묻는 사람 번호(ADMIN 만 본다) · 피드백(도움 됨 · 안 됨 · 틀림) · 고칠 말(가린 글).
- **직원별 모아 보기는 만들지 않는다**(근로 감시 — 원장 Q20). 사람 번호는 하루 질문 수 상한과 '내 질문에만 피드백'에만 쓴다.
- 피드백은 묻는 사람 자기 질문에만. '틀림'이면 그 답의 근거 항목마다 신고 한 줄(:mod:`.chat_reports`)이 붙고, 같은 항목에 서로
  다른 사람 둘 이상이면 이름 있는 에이전트 액션 ``report_conflict``(:func:`.action_runner.perform_agent`)로 승인자에게 올린다.
- :func:`purge_questions` — 1년 지난 질문 · 신고를 지운다(밤 단계 ``tools/cron/purge_brain_questions.py``).
- :func:`my_history` — **내가 물은 것만**(오늘 · 지난 7일, 가린 글 앞부분 · 모름 · 주문 읽기 여부 — 설계서 2026-11-14-foms-graft
  3.7 ``GET /api/brain/chat/history``). 남의 질문 · 묻는 사람 번호 · 답 글은 싣지 않는다.
- 근거 키에 ERP 주문 키(``erp:order/<번호>`` — 접목판 ERP 읽기)가 섞여 있어도 '틀림' 신고는 회사 지식 키에만 붙는다.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable, Optional

from sqlalchemy import delete, func, select

from foms.persistence.brain.models import BrainQuestion, BrainWrongReport
from foms.persistence.graft.models import BrainUsageEvent
from foms.services.brain.action_runner import perform_agent
from foms.services.brain.chat_prompt import ASK_ADMIN, ASK_ERP, ASK_OWNER, CERTAINTY_LABELS
from foms.services.brain.chat_reports import CHAT_AGENT, add_reports, drop_reports, raisable
from foms.services.brain.embeddings import SOURCE_QUESTION, drop_vectors
from foms.services.brain.errors import BrainError
from foms.services.cs_agent.masking import leak_counts, mask
from foms.services.erp_ontology.read import ORDER_KEY_PREFIX, order_id_of
from foms.services.orders.team_labels import team_label

logger = logging.getLogger(__name__)

FEEDBACKS: tuple[str, ...] = ("helpful", "not_helpful", "wrong")
KEEP_DAYS = 365
MAX_NOTE = 500
PURGE_BATCH = 1000
_KST = datetime.timedelta(hours=9)
#: 내 질문 목록 — 줄 수 · 가린 글 앞 글자 수 · 지난 며칠(오늘 포함).
HISTORY_LIMIT, HISTORY_CHARS, HISTORY_DAYS = 20, 60, 7
_ASK_LABELS = {ASK_OWNER: "사장님", ASK_ADMIN: "관리자", ASK_ERP: "주문 화면", "ACCOUNTING": "회계팀"}


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
    keys = [k for k in (row.evidence_keys or []) if isinstance(k, str) and order_id_of(k) is None]  # 주문 키는 신고 밖
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


def _order_read(session: Any, question_ids: list[int]) -> set[int]:
    """그 질문들 가운데 주문을 읽은 것(쓰인 곳에 주문 키가 남은 질문) — 질의 한 번(색인 ``(ref_kind, ref_id)``)."""
    if not question_ids:
        return set()
    refs = session.execute(select(BrainUsageEvent.ref_id).where(
        BrainUsageEvent.ref_kind == "question", BrainUsageEvent.ref_id.in_([str(i) for i in question_ids]),
        BrainUsageEvent.reader == "chatbot", BrainUsageEvent.item_key.like(ORDER_KEY_PREFIX + "%"))).scalars()
    return {int(ref) for ref in refs if str(ref).isdigit()}


def _ask_label(ask_team: Optional[str]) -> str:
    """물을 곳 짧은 이름(모름 줄 옆 — '도면팀' · '사장님' · '주문 화면')."""
    if not ask_team:
        return ""
    return _ASK_LABELS.get(ask_team) or team_label(ask_team)


def _history_row(row: BrainQuestion, erp_read: bool) -> dict[str, Any]:
    """내 질문 한 줄 — 가린 글 앞부분 · 모름 · 주문 읽기 · 확신 · 물을 곳 · 물은 때(한국)."""
    text = row.masked_question or ""
    short = text[:HISTORY_CHARS] + ("…" if len(text) > HISTORY_CHARS else "")
    return {"id": row.id, "text": short, "unknown": bool(row.unknown), "erp": erp_read,
            "certainty": row.confidence, "certainty_label": CERTAINTY_LABELS.get(row.confidence or "", ""),
            "ask_team": row.ask_team if row.unknown else None,
            "ask_label": _ask_label(row.ask_team) if row.unknown else "",
            "asked_at": (row.asked_at + _KST).isoformat(timespec="minutes") if row.asked_at else None}


def my_history(session: Any, *, asker_id: int, now_utc: datetime.datetime,
               limit: int = HISTORY_LIMIT) -> dict[str, Any]:
    """내가 물은 것 — 오늘(한국 날)과 그 앞 6일, 새것부터 :data:`HISTORY_LIMIT` 줄까지. 남의 질문은 질의 단계에서 뺀다.

    Args:
        session: DB 세션(읽기만).
        asker_id: 로그인한 묻는 사람 번호(본문 값이 아니다).
        now_utc: 지금(UTC naive).
        limit: 줄 수 상한(1 ~ :data:`HISTORY_LIMIT`).

    Returns:
        ``{"today": [줄], "week": [줄], "days": 7, "limit": n}``.
    """
    size = max(1, min(int(limit), HISTORY_LIMIT))
    today_start = kst_day_start(now_utc)
    since = today_start - datetime.timedelta(days=HISTORY_DAYS - 1)
    rows = session.execute(select(BrainQuestion).where(
        BrainQuestion.asker_id == int(asker_id), BrainQuestion.asked_at >= since)
        .order_by(BrainQuestion.asked_at.desc(), BrainQuestion.id.desc()).limit(size)).scalars().all()
    read = _order_read(session, [row.id for row in rows])
    out: dict[str, Any] = {"today": [], "week": [], "days": HISTORY_DAYS, "limit": size}
    for row in rows:
        out["today" if row.asked_at >= today_start else "week"].append(_history_row(row, row.id in read))
    return out
