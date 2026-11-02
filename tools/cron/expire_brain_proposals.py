"""회사 지식 제안 밤 정리(FOMS-cron 밤 단계 — 설계서 2026-11-02-haud-master-brain 7.5 승인 흐름 · 7.7 · 사장님 D103 · D104).

- 만든 뒤 4주가 지난 **AI 제안만** '기간 끝남'(``expired``)으로 닫는다 — 사람 제안은 닫지 않는다
  (:func:`foms.services.brain.decide.expire_ai_proposals`, 감사 한 줄 ``BRAIN_EXPIRE count=n``).
- 기준 판이 바뀐 열린 제안에 '기준 판 바뀜' 시각을 적는다(반영 동작이 그 순간 적지만, 그 전에 쌓인 제안까지 맞춘다 —
  :func:`foms.services.brain.decide.flag_stale_bases`).
- 기본은 시험 돌리기(세기만 하고 되돌림). ``--apply`` 일 때만 커밋한다. 닫을 것이 없으면 exit 0.
- Flask 앱은 불러오지 않는다(앱 초기화가 Railway Heartbeat 시간 초과를 부른다 — purge_cs_edit_photos.py 와 같은 길).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.db_url_resolver import sqlalchemy_url  # noqa: E402

logger = logging.getLogger("expire_brain_proposals")


def _make_session():
    """DATABASE_URL 로 맨 세션을 만든다(Flask 앱 없이)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    url = sqlalchemy_url(url)
    engine_kwargs: dict = {"pool_pre_ping": True}
    if "sqlite" not in url:
        engine_kwargs["connect_args"] = {"connect_timeout": 10}
    engine = create_engine(url, **engine_kwargs)
    return sessionmaker(bind=engine)(), engine


def run(*, apply: bool = False, session=None, now=None) -> dict:
    """AI 제안 기간 끝남 닫기 + 기준 판 바뀜 표시(``apply`` 가 거짓이면 세고 되돌림). 돌려주는 값: {expired, flagged, applied}."""
    from foms.services.brain.decide import expire_ai_proposals, flag_stale_bases

    own = session is None
    engine = None
    if own:
        session, engine = _make_session()
    try:
        when = now or now_utc_naive()
        summary = {"expired": expire_ai_proposals(session, now=when), "flagged": flag_stale_bases(session, now=when),
                   "applied": bool(apply)}
        if apply:
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
    parser = argparse.ArgumentParser(description="회사 지식 AI 제안 4주 닫기 · 기준 판 바뀜 표시(기본: 시험 돌리기)")
    parser.add_argument("--apply", action="store_true", help="닫고 표시한 것을 커밋한다")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = run(apply=args.apply)
    logger.info("expire_brain_proposals %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
