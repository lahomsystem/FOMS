"""운영 AI · 일정 AI 훑기(FOMS-cron 밤 단계 — 설계서 2026-11-14-foms-graft 3.10 · D207 · D214).

- 규칙(:data:`foms.services.ai_staff.sweeps.RULES`)이 할 일 **제안만** 만든다 — 알림톡 · 푸시를 보내지 않는다(사람이 승인해야
  실행된다). 한 번에 30개까지, 직원 · 할 일 수준이 0 이면 그 규칙은 돌지 않는다.
- ``FOMS_GRAFT_PROPOSERS_ENABLED`` 가 꺼져 있으면(처음 값) 아무것도 읽지도 쓰지도 않고 exit 0(지금과 같다).
- 기본은 시험 돌리기(만들고 되돌림). ``--apply`` 일 때만 커밋한다. 규칙이 실패하면 되돌리고 exit 3(밤 단계 요약에 빨갛게).
- Flask 앱은 불러오지 않는다(앱 초기화가 Railway Heartbeat 시간 초과를 부른다 — expire_brain_proposals.py 와 같은 길).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.db_url_resolver import sqlalchemy_url  # noqa: E402

logger = logging.getLogger("ai_staff_sweep")
FAILED_EXIT_CODE = 3


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


def run(*, apply: bool = False, session=None, now=None, today=None) -> dict:
    """훑기 한 번(``apply`` 가 거짓이면 만들고 되돌림). 돌려주는 값: {enabled, created, by_rule, applied}.

    스위치가 꺼져 있으면 DB 에 붙지도 않는다(``session`` 을 받았어도 쓰지 않는다).
    """
    from foms.services.ai_staff.sweeps import run_sweep
    from foms.services.graft_flags import enabled_global

    if not enabled_global("proposers"):
        return {"enabled": False, "created": 0, "by_rule": {}, "applied": bool(apply)}
    own = session is None
    engine = None
    if own:
        session, engine = _make_session()
    try:
        result = run_sweep(session, now=now, today=today)
        summary = {"enabled": result.enabled, "created": result.created, "by_rule": dict(result.by_rule),
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
    parser = argparse.ArgumentParser(description="운영 AI · 일정 AI 규칙 훑기 — 할 일 제안만(기본: 시험 돌리기)")
    parser.add_argument("--apply", action="store_true", help="만든 제안 · 실행 기록을 커밋한다")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        summary = run(apply=args.apply)
    except Exception:
        logger.exception("ai_staff_sweep failed")
        return FAILED_EXIT_CODE
    logger.info("ai_staff_sweep %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
