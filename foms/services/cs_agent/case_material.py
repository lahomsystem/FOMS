"""사례 기억(L0)의 다음 초안 재료 — 같은 브랜드 비슷한 지난 사례 고르기 · 다듬기 · 사례에만 있는 이름 뽑기.

설계서 17.2 · 17.5(사례는 관찰) · 17.6 L0, 플랜 C10-4 · 검수 R14. 사례를 쌓는 쪽은 :mod:`.case_memory`, 두뇌에 싣는 꼴은
:mod:`.brain_cases` 다(500줄 상한으로 나눴다).

- **고르기**(:func:`similar_cases` — 초안 차례가 두뇌를 부르기 전에): 같은 브랜드 · 끝난 꼴이 그대로 · 고침 · 직접 답(복사 ·
  버림 · 시험용 떼어 둠 제외)이고 질문 · 사람 답 글이 있는 사례 가운데 가린 질문이 지금 손님 글과 비슷한 것
  :data:`~.brain_cases.MAX_CASES` 개까지. PostgreSQL 은 pg_trgm(``%`` 로 GIN 색인을 타고 ``similarity`` 순 — 문턱
  :data:`CASE_MIN_SIMILARITY` 를 이 트랜잭션에만), SQLite 시험 레인은 같은 셈의 파이썬 대체(:func:`trigram_similarity`).
  DB 오류면 되돌리고 사례 없이 초안을 쓴다(R14-7 — 사례 때문에 그 차례 초안을 잃지 않게).
- **한글 묶음 확인(R14-2)**: pg_trgm 은 DB 지역 설정이 한글을 글자로 보지 않으면(예 ``C``) 한글 낱말을 묶지 못해 비슷함이
  늘 0 이 된다 — 오류 없이 사례 0 건. 프로세스마다 한 번 ``show_trgm`` 이 비면 경고(코드만)를 남긴다.
- **다듬기(R14-3 · R14-8)**: 질문은 :data:`CASE_QUESTION_LIMIT` 자로 짧게, 사람 답은 앞 인사 줄 · 끝 맺음말 줄(담당 이름 ·
  직함 · 감사 인사)을 떼고 :data:`CASE_TEXT_LIMIT` 자로. 파일만 보낸 답처럼 남는 글이 없으면 재료에서 뺀다. 모두 가림 검사를
  다시 넘은 것만.
- **사례에만 있는 이름(R14-3)**: 가림이 놓친 이름꼴(직함 · 맺음말 · '저는 …' 문맥의 세 글자 이름)이 사례에만 있고 지금 상담 ·
  승인 지식에는 없으면 :func:`case_only_names` 가 돌려준다 — 초안 차례가 보내기 전 검사의 '예시에만 있는 낱말'로 넘겨, 다른
  손님 · 다른 직원 이름을 새 초안에 옮기면 막힌다.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.brain_cases import MAX_CASES
from foms.services.cs_agent.case_memory import LEARNING_OUTCOMES, masked_join
from foms.services.cs_agent.drafting_read import FILE_NOTE, ChatLine
from foms.services.cs_agent.masking import leak_counts, looks_like_name

logger = logging.getLogger(__name__)

__all__ = [
    "CASE_MIN_SIMILARITY", "CASE_QUESTION_LIMIT", "CASE_TEXT_LIMIT", "TRGM_BLIND", "case_only_names",
    "current_question", "similar_cases", "trim_answer", "trigram_similarity",
]

#: 비슷한 사례로 보는 가장 낮은 trgm 비슷함 — 한국어 짧은 문의는 같은 뜻이어도 0.2~0.3 이라 pg_trgm 처음 값(0.3)보다 낮춘다.
CASE_MIN_SIMILARITY = 0.2
CASE_TEXT_LIMIT = 500  # 두뇌에 싣는 사람 답 하나의 글자 상한
CASE_QUESTION_LIMIT = 200  # 두뇌에 싣는 사례 질문 하나의 글자 상한(짧게 — R14-4)
QUERY_TEXT_LIMIT = 1000  # 비슷함을 재는 지금 손님 글의 글자 상한
CASE_POOL = 2000  # SQLite 레인이 비슷함을 재는 최근 사례 수
TRGM_PROBE = "선반 깊이"  # 한글 묶음 확인 글
TRGM_BLIND = "trgm_no_hangul"  # pg_trgm 이 한글을 못 묶는다(경고 코드)
CASES_FAILED = "cases_read_failed"  # 사례 읽기 DB 오류(경고 코드)
_CHECKED = {"trgm": False}  # 프로세스마다 한 번

# ── 비슷함(pg_trgm 과 같은 셈) ───────────────────────────────────────────
_WORD = re.compile(r"[^\W_]+")


def _trigrams(value: str) -> set[str]:
    """pg_trgm 과 같은 셈의 세 글자 묶음 — 소문자 · 글자 · 숫자 낱말마다 앞 빈칸 둘 · 뒤 빈칸 하나를 붙인다."""
    out: set[str] = set()
    for word in _WORD.findall(value.lower()):
        padded = f"  {word} "
        out.update(padded[i:i + 3] for i in range(len(padded) - 2))
    return out


def trigram_similarity(left: str, right: str) -> float:
    """pg_trgm ``similarity`` 의 파이썬 대체 — 겹친 세 글자 묶음 수 ÷ 합친 묶음 수(0~1). 묶음이 없으면 0."""
    a, b = _trigrams(left or ""), _trigrams(right or "")
    return len(a & b) / len(a | b) if a and b else 0.0


def current_question(lines: Sequence[ChatLine]) -> Optional[str]:
    """지금 손님 글 — 마지막 공개 직원 글 뒤 손님 글을 가려 이은 것(가림 검사를 넘은 글만, :data:`QUERY_TEXT_LIMIT` 자까지)."""
    after = max((i for i, line in enumerate(lines) if line.meta.is_answer), default=-1)
    joined = masked_join(line for line in lines[after + 1:] if line.meta.is_customer_signal)
    return joined[:QUERY_TEXT_LIMIT] if joined else None


# ── 다듬기 ───────────────────────────────────────────────────────────────
#: 앞 인사 줄(짧은 줄만) · 끝 맺음말 줄(짧은 줄만 — '… 드림' · 감사 · 작별 인사 · '담당: …' · 직함으로 끝나는 줄).
_GREETING = re.compile(r"^(?:안녕하세요|안녕하십니까|반갑습니다)")
_CLOSING = re.compile(r"(?:드림|올림)\W*$|^(?:감사합니다|감사드립니다)|좋은 하루|행복한 하루|수고하세요|"
                      r"^담당자?\s*[:：]?\s*\S+\W*$|"
                      r"(?:매니저|실장|대리|팀장|과장|주임|상담원|상담사)(?:입니다|이었습니다|였습니다)?\W*$")
_SHORT_LINE = 30


def trim_answer(answer: str) -> str:
    """사람 답에서 앞 인사 줄 · 끝 맺음말 줄을 뗀다(줄 전체가 짧은 인사 · 맺음일 때만 — 본문 줄은 남긴다)."""
    lines = [line.strip() for line in answer.replace("\r\n", "\n").split("\n") if line.strip()]
    while lines and len(lines[0]) <= _SHORT_LINE and _GREETING.search(lines[0]):
        lines.pop(0)
    while lines and len(lines[-1]) <= _SHORT_LINE and _CLOSING.search(lines[-1]):
        lines.pop()
    return "\n".join(lines)


def _trimmed(question: str, answer: str) -> Optional[tuple[str, str]]:
    """두뇌에 실을 짝 — 짧게 자르고 인사 · 맺음말을 떼고 가림 검사를 다시 넘은 것만. 남는 답 글(파일 표시 말고)이 없으면 ``None``."""
    answer = trim_answer(answer)[:CASE_TEXT_LIMIT].strip()
    pair = (question[:CASE_QUESTION_LIMIT].strip(), answer)
    if not answer.replace(FILE_NOTE, "").strip():
        return None
    return pair if all(part and not any(leak_counts(part).values()) for part in pair) else None


# ── 사례에만 있는 이름 ───────────────────────────────────────────────────
_TITLES = "님|씨|고객님|매니저|실장|대리|팀장|과장|부장|차장|주임|사원|상담원|상담사|드림|올림|앞으로|이랑|한테|에게|께"
_NAME_BEFORE_TITLE = re.compile(rf"(?<![가-힣])([가-힣]{{3}})\s?(?:{_TITLES})")
_NAME_AFTER_INTRO = re.compile(r"(?:담당자?는?|저는|제가|성함은?|이름은?)\s*[:：]?\s*([가-힣]{3})"
                               r"(?=$|[^가-힣]|요|입니다|이에요|예요|인데요|이고)")


def _names_in(value: str) -> set[str]:
    """글 속 이름꼴 — 직함 · 맺음 앞, '저는 · 담당 · 성함' 뒤의 세 글자 낱말 가운데 가림과 같은 판정으로 이름꼴인 것."""
    found = {m.group(1) for rx in (_NAME_BEFORE_TITLE, _NAME_AFTER_INTRO) for m in rx.finditer(value)}
    return {word for word in found if looks_like_name(word)}


def case_only_names(cases: Sequence[tuple[str, str]], known: Iterable[str]) -> tuple[str, ...]:
    """사례 글에만 있는 이름꼴 — ``known``(지금 상담 글 · 승인 지식 글)에 없는 것만, 정렬해서. 보내기 전 검사의 예시 낱말로 쓴다."""
    seen = "\n".join(known)
    names = {name for question, answer in cases for name in _names_in(f"{question}\n{answer}")}
    return tuple(sorted(name for name in names if name not in seen))


# ── 고르기 ───────────────────────────────────────────────────────────────
def _usable(brand: str) -> tuple[Any, ...]:
    """재료가 되는 사례 줄 — 같은 브랜드 · 그대로 · 고침 · 직접 답 · 떼어 두지 않음 · 질문과 사람 답이 있음."""
    turn = CsAgentTurn
    return (turn.brand == brand, turn.outcome.in_(LEARNING_OUTCOMES), turn.held_out.is_(False),
            turn.masked_question.isnot(None), turn.staff_reply_masked.isnot(None))


def _pg_statement(brand: str, query: str, limit: int) -> Any:
    """PostgreSQL 사례 질의 — ``%``(trgm 문턱 — GIN 색인을 탄다)로 거르고 ``similarity`` 높은 것 · 새 사례부터."""
    score = func.similarity(CsAgentTurn.masked_question, query)
    return (select(CsAgentTurn.masked_question, CsAgentTurn.staff_reply_masked)
            .where(*_usable(brand), CsAgentTurn.masked_question.bool_op("%")(query))
            .order_by(score.desc(), CsAgentTurn.id.desc()).limit(limit))


def warn_if_trgm_blind(session: Any) -> None:
    """프로세스마다 한 번 — pg_trgm 이 한글 낱말을 묶지 못하면(DB 지역 설정) 경고한다(코드만, 글 없음)."""
    if _CHECKED["trgm"]:
        return
    _CHECKED["trgm"] = True
    if not session.execute(text("SELECT show_trgm(:probe)"), {"probe": TRGM_PROBE}).scalar():
        logger.warning("[CS 사례] pg_trgm 이 한글 낱말을 묶지 못해 비슷한 사례가 늘 0 건이다 — DB 지역 설정을 본다 code=%s",
                       TRGM_BLIND)


def _pg_cases(session: Any, brand: str, query: str, limit: int) -> list[tuple[str, str]]:
    """PostgreSQL — 이 트랜잭션만 trgm 문턱을 :data:`CASE_MIN_SIMILARITY` 로 두고 :func:`_pg_statement` 로 읽는다."""
    warn_if_trgm_blind(session)
    session.execute(text("SELECT set_config('pg_trgm.similarity_threshold', :value, true)"),
                    {"value": str(CASE_MIN_SIMILARITY)})
    found = session.execute(_pg_statement(brand, query, limit))
    return [(row.masked_question, row.staff_reply_masked) for row in found]


def _py_cases(session: Any, brand: str, query: str, limit: int) -> list[tuple[str, str]]:
    """SQLite 시험 레인 — 최근 :data:`CASE_POOL` 사례를 :func:`trigram_similarity` 로 재서 같은 문턱 · 같은 순서."""
    stmt = (select(CsAgentTurn.id, CsAgentTurn.masked_question, CsAgentTurn.staff_reply_masked)
            .where(*_usable(brand)).order_by(CsAgentTurn.id.desc()).limit(CASE_POOL))
    scored = [(trigram_similarity(row.masked_question, query), row.id, row) for row in session.execute(stmt)]
    scored = sorted((item for item in scored if item[0] >= CASE_MIN_SIMILARITY), key=lambda item: (-item[0], -item[1]))
    return [(row.masked_question, row.staff_reply_masked) for _, _, row in scored[:limit]]


def similar_cases(session: Any, brand: str, lines: Sequence[ChatLine], *,
                  limit: int = MAX_CASES) -> tuple[tuple[str, str], ...]:
    """다음 초안 재료 — 같은 브랜드 비슷한 지난 사례 (가린 질문, 사람이 보낸 가린 답), 비슷한 것부터 ``limit`` 개까지.

    지금 손님 글(:func:`current_question`)이 없으면 빈 튜플. 다듬기(모듈 설명)를 지나 남은 사례만 돌려준다(두뇌가 실을 때
    가림 검사를 한 번 더 본다). DB 를 읽기만 한다 — 커밋은 부르는 쪽(두뇌가 곧 커밋한다). DB 오류면 되돌리고 빈 튜플.
    """
    query = current_question(lines)
    if not query:
        return ()
    pick = _pg_cases if session.get_bind().dialect.name == "postgresql" else _py_cases
    try:
        rows = pick(session, brand, query, int(limit))
    except SQLAlchemyError as exc:
        session.rollback()
        logger.warning("[CS 사례] 비슷한 사례를 못 읽어 사례 없이 초안을 쓴다 code=%s error=%s", CASES_FAILED,
                       type(exc).__name__)
        return ()
    return tuple(pair for question, answer in rows if (pair := _trimmed(question, answer)) is not None)
