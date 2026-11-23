"""'AI 시험' 사장님 채점 — 차례마다 AI 초안(가린 글)을 남기고, ADMIN 이 하루 :data:`DAILY_LIMIT` 개까지 채점한다
(설계서 2026-11-23-brain-learning-upgrade 4.1 · 판 ⑪ 'AI 시험' 칸 안).

- **남기기**(:func:`record` — :mod:`.evals_run` 이 '지난 상담' 차례마다): 모델까지 간 차례 한 줄(가림 검사 · 재료 꼴 · 모델 못 받음은
  남기지 않는다). 초안은 :func:`foms.services.cs_agent.masking.mask` 뒤 :func:`~foms.services.cs_agent.masking.require_masked` 를
  지난 글만 — 걸리면 줄을 남기지 않는다. 넘김 · 거절이면 빈 글과 넘긴 까닭 코드. 채점 코드는 결과 줄 ``codes`` 와 같은 글자.
- **비우기**(:func:`blank_old` — 시험을 시작할 때): :data:`KEEP` 지난 줄의 초안을 빈 글로(사장님 답 · 코드는 남는다).
- **채점할 차례**(:func:`queue_view`): 오늘(KST) 이 사람이 채점한 수를 뺀 만큼(:data:`DAILY_LIMIT` 까지). 아직 채점 안 했고
  :data:`KEEP` 안에 만든 줄을 새 시험부터, AI 가 통과라 한 것 · 실패라 한 것 · 넘긴 것을 번갈아(사장님 11-23 '반씩, 그리고 넘긴
  차례'). 판정을 못 받은 줄은 내지 않는다. **채점 코드는 화면에 보내지 않는다**(사장님이 모르고 채점한다). 손님 글 · 직원 답은
  차례 줄의 가린 칸(``masked_question`` · ``staff_reply_masked``)을 한 번에 읽는다 — 차례 줄이 없으면 그 줄은 뺀다.
- **채점 저장**(:func:`save_mark`): 초안이면 :data:`ANSWER_OK` · :data:`ANSWER_BAD`(+ 틀린 종류 하나 :data:`FAIL_KINDS`), 넘김이면
  :data:`ANSWER_HANDOFF_RIGHT` · :data:`ANSWER_SHOULD_ANSWER`. 서버가 모두 다시 본다 — 꼴 틀림 ``EVAL_MARK_SHAPE`` · 없음 · 이미
  채점함 · 오래됨 ``EVAL_MARK_GONE`` · 오늘 다 함 ``EVAL_MARK_LIMIT``. 감사 줄 :data:`AUDIT_MARK`(번호 · 코드만). 커밋은 부르는 쪽.
- **견주기 재료**(:func:`graded_pairs` · :func:`observed`): 채점한 초안마다 (사장님 '보내도 돼요'인가, AI 통과인가) 짝 · 넘김은
  사장님 답이 '늘 사람 몫' 분류(옳은 넘김)와 같은 수 · 보이는 시험의 판정받은 초안 수와 통과 수(:mod:`.evals_calibrate`).

모두 ADMIN 만(:func:`.evals._admin` — 아니면 ``EVAL_FORBIDDEN``, API 는 404). 로그 · 예외 · 감사 줄에는 번호 · 코드 · 수만 싣는다.
"""

from __future__ import annotations

import collections
import datetime
import logging
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import func, select

from foms.persistence.graft.models import MARK_ANSWERS, MARK_FAIL_KINDS, AiStaffEvalMark
from foms.services.ai_staff import evals as store
from foms.services.ai_staff import evals_meaning as meaning
from foms.services.audit_writer import normalize_security_detail
from foms.services.cs_agent.masking import MaskLeak, mask, require_masked
from foms.services.cs_agent.state import KST
from models import CsAgentTurn, SecurityLog

logger = logging.getLogger(__name__)

__all__ = [
    "ANSWERS", "AUDIT_MARK", "DAILY_LIMIT", "FAIL_KINDS", "FAIL_LABELS", "HANDOFF_SAID", "KEEP", "blank_old",
    "graded_pairs", "graded_today", "judge_passed", "observed", "queue_view", "record", "save_mark",
]

ANSWER_OK, ANSWER_BAD, ANSWER_HANDOFF_RIGHT, ANSWER_SHOULD_ANSWER = MARK_ANSWERS
ANSWERS, FAIL_KINDS = MARK_ANSWERS, MARK_FAIL_KINDS
DRAFT_ANSWERS = (ANSWER_OK, ANSWER_BAD)
HANDOFF_ANSWERS = (ANSWER_HANDOFF_RIGHT, ANSWER_SHOULD_ANSWER)
#: 틀린 종류 → 화면 말(사장님 11-23 — 사실이 틀림 · 없는 약속 · 말투).
FAIL_LABELS: dict[str, str] = {"wrong_fact": "사실이 틀림", "no_basis": "없는 약속", "tone": "말투"}
DAILY_LIMIT = 10
KEEP = datetime.timedelta(days=90)
#: 채점할 차례 후보로 읽는 줄 수(새 시험부터) — 번갈아 고르기 재료.
POOL = 300
AUDIT_MARK = "AI_STAFF_EVAL_MARK"
#: 넘김 · 거절 코드(초안 없음 — 넘김 단추) · AI 통과 코드 · 판정을 못 받은 코드(채점할 차례로 내지 않는다).
HANDOFF_CODES = frozenset({meaning.HANDOFF, meaning.RIGHT_HANDOFF, meaning.REFUSED})
PASS_CODES = frozenset({meaning.COPIED, meaning.PASS})
UNJUDGED = frozenset({meaning.UNKNOWN, meaning.MASK_LEAK})
#: 넘긴 까닭 코드 → 채점 화면의 쉬운 말(:data:`foms.services.cs_agent.brain_prompt.HANDOFF_REASONS` + 까닭 없음 · 거절).
HANDOFF_SAID: dict[str, str] = {
    "none": "까닭 없이 빈 초안을 냈어요", "unsure": "회사 지식에 근거가 없다고 봤어요",
    "human_only_amount": "사람이 정하는 금액이라고 봤어요", "discount_refund": "할인 · 환불 상담이라고 봤어요",
    "schedule": "날짜나 연락 약속이 필요하다고 봤어요", "complaint": "불만 · 하자 상담이라고 봤어요",
    "order_lookup": "주문 · 배송을 찾아봐야 한다고 봤어요", "photo": "사진 · 파일만 왔다고 봤어요",
    "asked_if_ai": "손님이 사람인지 AI 인지 물었다고 봤어요", "other": "AI 가 답하기 어렵다고 봤어요",
    meaning.REFUSED: "이 상담에는 답하지 않겠다고 했어요",
}
_FIELDS = frozenset({"mark", "answer", "fail_kind"})


def judge_passed(code: str) -> Optional[bool]:
    """초안 차례의 AI 판정 — 통과 참 · 실패 거짓. 넘김 · 거절 · 판정을 못 받은 코드는 ``None``."""
    if code in HANDOFF_CODES or code in UNJUDGED:
        return None
    return code in PASS_CODES


def _day_start(now: datetime.datetime) -> datetime.datetime:
    """오늘(KST) 0시 — UTC naive(채점 때 칸과 견준다)."""
    local = store.naive_utc(now).replace(tzinfo=datetime.timezone.utc).astimezone(KST)
    return store.naive_utc(datetime.datetime.combine(local.date(), datetime.time.min, tzinfo=KST))


# ── 남기기 · 비우기(시험 바퀴) ───────────────────────────────────────────
def record(session: Any, run_id: int, case: Any, result: Any, code: str) -> bool:
    """'지난 상담' 차례 하나를 남긴다(커밋은 부르는 쪽). 초안이 가림 검사에 걸리거나 같은 (시험, 차례) 줄이 이미 있으면 남기지 않는다.

    Returns:
        남겼으면 참.
    """
    if session.scalar(select(AiStaffEvalMark.id).where(AiStaffEvalMark.run_id == int(run_id),
                                                       AiStaffEvalMark.turn_id == case.turn_id)) is not None:
        logger.warning("[AI 시험] 채점 줄이 이미 있어 넘긴다 run=%s turn=%s", run_id, case.turn_id)
        return False
    handed = code in HANDOFF_CODES
    draft = ""
    if not handed:
        try:
            draft = require_masked(mask(result.draft))
        except MaskLeak as exc:
            logger.warning("[AI 시험] 초안 가림 검사 0 아님 — 채점 줄을 남기지 않음 run=%s turn=%s counts=%s",
                           run_id, case.turn_id, exc.counts)
            return False
    session.add(AiStaffEvalMark(run_id=int(run_id), turn_id=case.turn_id, brand=case.brand, draft=draft,
                                judge_code=str(code)[:32],
                                handoff_reason=str(result.handoff_reason or "none")[:24] if handed else None))
    return True


def blank_old(session: Any, now: datetime.datetime) -> int:
    """:data:`KEEP` 지난 줄의 초안을 빈 글로(커밋은 부르는 쪽). 비운 줄 수."""
    cutoff = store.naive_utc(now) - KEEP
    rows = list(session.scalars(select(AiStaffEvalMark).where(AiStaffEvalMark.created_at < cutoff,
                                                              AiStaffEvalMark.draft != "")))
    for row in rows:
        row.draft = ""
    session.flush()
    return len(rows)


# ── 채점할 차례 · 채점 저장(ADMIN) ──────────────────────────────────────
def graded_today(session: Any, user_id: int, now: datetime.datetime) -> int:
    """이 사람이 오늘(KST) 채점한 수."""
    return int(session.scalar(select(func.count()).select_from(AiStaffEvalMark).where(
        AiStaffEvalMark.graded_by == int(user_id), AiStaffEvalMark.graded_at >= _day_start(now))) or 0)


def _group(code: str) -> int:
    """번갈아 고를 무리 — 0 AI 통과 · 1 AI 실패 · 2 넘김."""
    return 2 if code in HANDOFF_CODES else 0 if code in PASS_CODES else 1


def _mixed(rows: Sequence[Any]) -> list[Any]:
    """새 시험부터 읽은 후보를 무리마다 줄 세운 뒤 통과 · 실패 · 넘김 차례로 하나씩 번갈아 꺼낸다."""
    queues = [collections.deque(row for row in rows if _group(row.judge_code) == n) for n in range(3)]
    out: list[Any] = []
    while any(queues):
        out.extend(queue.popleft() for queue in queues if queue)
    return out


def _said(reason: Optional[str]) -> str:
    """넘김 차례의 화면 말 한 문장."""
    return "AI 가 사람에게 넘겼어요 — " + HANDOFF_SAID.get(reason or "none", HANDOFF_SAID["other"])


def _items(session: Any, picked: Sequence[Any], left: int) -> list[dict[str, Any]]:
    """고른 줄 → 화면 칸(번호 · 갈래 · 손님 글 · 직원 답 · 초안 또는 넘김 말 — 채점 코드 없음). 차례 줄이 없으면 뺀다."""
    ids = [row.id for row in picked]
    marks = {row.id: row for row in session.execute(select(
        AiStaffEvalMark.id, AiStaffEvalMark.draft, AiStaffEvalMark.handoff_reason).where(AiStaffEvalMark.id.in_(ids)))}
    turns = {row.id: row for row in session.execute(select(
        CsAgentTurn.id, CsAgentTurn.masked_question, CsAgentTurn.staff_reply_masked).where(
        CsAgentTurn.id.in_([row.turn_id for row in picked])))}
    out: list[dict[str, Any]] = []
    for row in picked:
        turn, mark = turns.get(row.turn_id), marks.get(row.id)
        if turn is None or mark is None or not (turn.masked_question or "").strip():
            continue
        item = {"id": row.id, "question": turn.masked_question, "staff_reply": turn.staff_reply_masked or ""}
        if row.judge_code in HANDOFF_CODES:
            item.update(kind="handoff", handoff=_said(mark.handoff_reason))
        elif mark.draft:
            item.update(kind="draft", draft=mark.draft)
        else:
            continue
        out.append(item)
        if len(out) >= left:
            break
    return out


def queue_view(session: Any, actor: Any, now: datetime.datetime) -> dict[str, Any]:
    """오늘 채점할 차례(ADMIN 만 — 모듈 설명). 읽기만 한다.

    Returns:
        ``{"items": [...], "graded_today", "left", "limit", "fail_kinds": [{"code", "label"}]}``.

    Raises:
        EvalError: ``EVAL_FORBIDDEN``(ADMIN 아님).
    """
    viewer = store._admin(actor)  # noqa: SLF001 — 평가 쓰기 길과 같은 ADMIN 확인
    done = graded_today(session, int(viewer.user_id), now)
    left = max(0, DAILY_LIMIT - done)
    items: list[dict[str, Any]] = []
    if left:
        cutoff = store.naive_utc(now) - KEEP
        pool = session.execute(
            select(AiStaffEvalMark.id, AiStaffEvalMark.run_id, AiStaffEvalMark.turn_id, AiStaffEvalMark.judge_code)
            .where(AiStaffEvalMark.owner_answer.is_(None), AiStaffEvalMark.created_at >= cutoff,
                   AiStaffEvalMark.judge_code.notin_(tuple(UNJUDGED)))
            .order_by(AiStaffEvalMark.run_id.desc(), AiStaffEvalMark.id.asc()).limit(POOL)).all()
        items = _items(session, _mixed(pool)[:left * 2 + 5], left)
    return {"items": items, "graded_today": done, "left": left, "limit": DAILY_LIMIT,
            "fail_kinds": [{"code": code, "label": FAIL_LABELS[code]} for code in FAIL_KINDS]}


def _parse(body: Any) -> tuple[int, str, Optional[str]]:
    """본문 ``{"mark", "answer", "fail_kind"?}`` → (번호, 답, 틀린 종류). 하나라도 틀리면 ``EVAL_MARK_SHAPE``(칸 이름)."""
    if not isinstance(body, Mapping):
        raise store.EvalError("EVAL_MARK_SHAPE", ("mark",))
    mark, answer, kind = body.get("mark"), body.get("answer"), body.get("fail_kind")
    problems = [str(name)[:20] for name in body if name not in _FIELDS]
    if not isinstance(mark, int) or isinstance(mark, bool) or mark <= 0:
        problems.append("mark")
    if not isinstance(answer, str) or answer not in ANSWERS:
        problems.append("answer")
    if (kind is not None and (not isinstance(kind, str) or kind not in FAIL_KINDS)) or ((answer == ANSWER_BAD) != (
            kind is not None)):
        problems.append("fail_kind")
    if problems:
        raise store.EvalError("EVAL_MARK_SHAPE", tuple(dict.fromkeys(problems)))
    return int(mark), str(answer), kind


def save_mark(session: Any, actor: Any, body: Any, now: datetime.datetime) -> dict[str, Any]:
    """채점 하나 저장(ADMIN 만 — 커밋은 부르는 쪽). ``{"graded_today", "left"}``(채점 코드는 돌려주지 않는다).

    Raises:
        EvalError: ``EVAL_FORBIDDEN`` · ``EVAL_MARK_SHAPE``(꼴 · 갈래에 안 맞는 답) · ``EVAL_MARK_GONE``(없음 · 이미 채점함 ·
            오래됨 · 판정을 못 받은 줄) · ``EVAL_MARK_LIMIT``(오늘 :data:`DAILY_LIMIT` 개를 다 함).
    """
    viewer = store._admin(actor)  # noqa: SLF001 — 평가 쓰기 길과 같은 ADMIN 확인
    mark_id, answer, kind = _parse(body)
    at, user_id = store.naive_utc(now), int(viewer.user_id)
    done = graded_today(session, user_id, now)
    if done >= DAILY_LIMIT:
        raise store.EvalError("EVAL_MARK_LIMIT")
    row = (session.query(AiStaffEvalMark).filter(AiStaffEvalMark.id == mark_id)
           .populate_existing().with_for_update().first())
    if (row is None or row.owner_answer is not None or row.created_at < at - KEEP or row.judge_code in UNJUDGED
            or (row.judge_code not in HANDOFF_CODES and not row.draft)):
        raise store.EvalError("EVAL_MARK_GONE")
    if answer not in (HANDOFF_ANSWERS if row.judge_code in HANDOFF_CODES else DRAFT_ANSWERS):
        raise store.EvalError("EVAL_MARK_SHAPE", ("answer",))
    row.owner_answer, row.fail_kind, row.graded_by, row.graded_at = answer, kind, user_id, at
    session.add(SecurityLog(user_id=user_id, action=AUDIT_MARK, target_type="ai_staff_eval_mark", target_id=row.id,
                            message=f"AI 시험 채점 #{row.id}", detail=normalize_security_detail(
                                {"run": row.run_id, "turn": row.turn_id, "answer": answer, "fail_kind": kind})))
    session.flush()
    return {"graded_today": done + 1, "left": max(0, DAILY_LIMIT - done - 1)}


# ── 견주기 재료(판 ⑪ 지난 상담 줄 글) ───────────────────────────────────
def graded_pairs(session: Any) -> tuple[list[tuple[bool, bool]], tuple[int, int]]:
    """채점한 줄 모두 → (초안 짝 (사장님 '보내도 돼요'인가, AI 통과인가) 목록, (넘김 채점 수, '늘 사람 몫' 분류와 같은 수))."""
    pairs: list[tuple[bool, bool]] = []
    handed = agreed = 0
    rows = session.execute(select(AiStaffEvalMark.judge_code, AiStaffEvalMark.owner_answer)
                           .where(AiStaffEvalMark.graded_at.isnot(None)))
    for code, answer in rows:
        if code in HANDOFF_CODES and answer in HANDOFF_ANSWERS:
            handed += 1
            agreed += int((answer == ANSWER_HANDOFF_RIGHT) == (code == meaning.RIGHT_HANDOFF))
        elif answer in DRAFT_ANSWERS and judge_passed(code) is not None:
            pairs.append((answer == ANSWER_OK, bool(judge_passed(code))))
    return pairs, (handed, agreed)


def observed(session: Any, run_id: int) -> tuple[int, int]:
    """한 시험의 (판정받은 초안 수, 그 가운데 AI 통과 수) — 바로잡을 '본 통과율'."""
    verdicts = [judge_passed(code) for (code,) in session.execute(
        select(AiStaffEvalMark.judge_code).where(AiStaffEvalMark.run_id == int(run_id)))]
    known = [verdict for verdict in verdicts if verdict is not None]
    return len(known), sum(known)
