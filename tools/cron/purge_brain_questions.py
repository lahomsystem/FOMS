"""회사 지식 물어보기 기록 보관 1년 지우기(FOMS-cron 밤 단계 — 설계서 2026-11-02-haud-master-brain 10.3 '보관 1년').

- 1년(365일) 지난 ``brain_questions`` 줄과 그 질문의 틀림 신고(``brain_wrong_reports``) · 질문 벡터(``brain_embeddings`` 근원
  ``chatbot_question`` — 표가 있을 때), 1년 지난 신고를 묶음마다 지운다
  (:func:`foms.services.brain.chat_log.purge_questions`). 감사 한 줄 ``BRAIN_CHAT_PURGE``(수만).
- 기본은 시험 돌리기(세기만 하고 되돌림). ``--apply`` 일 때만 커밋한다. 지울 것이 없으면 exit 0.
- Flask 앱은 불러오지 않는다(앱 초기화가 Railway Heartbeat 시간 초과를 부른다 — expire_brain_proposals.py 와 같은 길).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from tools.cron.expire_brain_proposals import _make_session  # noqa: E402

logger = logging.getLogger("purge_brain_questions")


def run(*, apply: bool = False, session=None, now=None, keep_days: int = 365) -> dict:
    """보관 기간이 지난 질문 · 신고 지우기(``apply`` 가 거짓이면 세고 되돌림). 돌려주는 값: {questions, reports, applied}."""
    from foms.services.brain.chat_log import purge_questions
    from models import SecurityLog

    own = session is None
    engine = None
    if own:
        session, engine = _make_session()
    try:
        when = now or now_utc_naive()
        gone = purge_questions(session, now_utc=when, keep_days=keep_days)
        summary = {**gone, "applied": bool(apply)}
        if apply:
            if gone["questions"] or gone["reports"] or gone["vectors"]:
                session.add(SecurityLog(action="BRAIN_CHAT_PURGE", target_type="brain_questions", timestamp=when,
                                        message=f"BRAIN_CHAT_PURGE questions={gone['questions']} reports={gone['reports']} "
                                                f"vectors={gone['vectors']}", detail=gone))
            session.commit()
        else:
            session.rollback()
        return summary
    except Exception:
        session.rollback()
        raise
    finally:
        if own:
            session.close()
            if engine is not None:
                engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="회사 지식 물어보기 기록 1년 지우기(기본: 시험 돌리기)")
    parser.add_argument("--apply", action="store_true", help="지운 것을 커밋한다")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("purge_brain_questions %s", run(apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
