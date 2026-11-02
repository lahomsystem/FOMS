"""회사 지식 빈 지식 목록 주 1회(FOMS-cron 밤 단계 — 설계서 2026-11-02-haud-master-brain 10.3).

- 설정 '빈 지식 묶기'(``gap_enabled``)가 꺼져 있으면(처음 값) 아무것도 하지 않고 exit 0.
- 켜져 있으면 이번 주(한국 월요일) 목록이 이미 있을 때 exit 0, 없으면 지난 7일 '모름' · '틀림' 질문을 보조 모델로 묶어
  (:func:`foms.services.brain.chat_gaps.run_weekly_gaps`) 저장한다. 돈은 챗봇 돈 줄 · 상한 안(상담 초안과 따로).
- 켜 놓았는데 부를 수 없으면(키 · 하루 상한 · 돈 줄) exit 3 — 밤 러너가 실패로 알린다(조용히 넘어가지 않게).
- 기본은 시험 돌리기(묶고 되돌림 — 돈은 든다). ``--apply`` 일 때만 커밋한다. Flask 앱은 불러오지 않는다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.datetime_kst import now_kst  # noqa: E402
from tools.cron.expire_brain_proposals import _make_session  # noqa: E402

logger = logging.getLogger("brain_chat_gaps")
NOT_READY_EXIT = 3


def run(*, apply: bool = False, session=None, now=None, client=None, clusterer=None) -> dict:
    """이번 주 빈 지식 목록(``apply`` 가 거짓이면 되돌림). 돌려주는 값: 요약 + {applied} 또는 {error}."""
    from foms.services.brain.chat_gaps import run_weekly_gaps
    from foms.services.cs_agent.brain_spend import BrainError

    own = session is None
    engine = None
    if own:
        session, engine = _make_session()
    try:
        try:
            summary = run_weekly_gaps(session, now=now or now_kst(), client=client, clusterer=clusterer)
        except BrainError as exc:
            session.rollback()
            return {"error": exc.code}
        if apply:
            session.commit()
        else:
            session.rollback()
        return {**summary, "applied": bool(apply)}
    except Exception:
        session.rollback()
        raise
    finally:
        if own:
            session.close()
            if engine is not None:
                engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="회사 지식 빈 지식 목록 주 1회(기본: 시험 돌리기)")
    parser.add_argument("--apply", action="store_true", help="만든 목록을 커밋한다")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = run(apply=args.apply)
    logger.info("brain_chat_gaps %s", summary)
    return NOT_READY_EXIT if "error" in summary else 0


if __name__ == "__main__":
    sys.exit(main())
