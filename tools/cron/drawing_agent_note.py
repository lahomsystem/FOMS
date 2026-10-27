"""AI 도면팀원 주간 노트 만들기(FOMS-cron 밤 단계).

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 A3

- 매일 밤(02:00 KST) 돌지만 그 주(월~일, KST) 노트가 이미 있으면 아무것도 안 한다 — 월요일 밤에 쉬어도 다음 날 만든다.
- 기본은 시험 돌리기(무엇을 만들지 세기만, 쓰지 않음). ``--apply`` 일 때만 노트를 저장하고 도면팀 알림을 남긴다.
- Flask 앱은 불러오지 않는다(앱 초기화가 Railway Heartbeat 시간 초과를 부른다 — cleanup_order_drafts.py 와 같은 길).
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

logger = logging.getLogger("drawing_agent_note")


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
    """이번 주 노트가 없으면 만든다. 돌려주는 값: {created, week, questions, labels}."""
    from foms.services import drawing_agent_notes as notes

    now = now or now_utc_naive()
    own = session is None
    engine = None
    if own:
        session, engine = _make_session()
    try:
        week = notes.week_id(now)
        if any(n.get("id") == week for n in notes.load_book(session)["notes"]):
            return {"created": False, "week": week, "reason": "already"}
        if not apply:
            preview = notes.build_note(session, now, notes.load_book(session))
            session.rollback()
            return {"created": False, "week": week, "reason": "dry-run",
                    "questions": len(preview["questions"]), "labels": preview["stats"]["labels"]}
        note = notes.create_weekly_note(session, now)
        session.commit()
        return {"created": note is not None, "week": week,
                "questions": len(note["questions"]) if note else 0, "labels": note["stats"]["labels"] if note else 0}
    except Exception:
        session.rollback()
        raise
    finally:
        if own:
            session.close()
            if engine is not None:
                engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI 도면팀원 주간 노트(기본: 시험 돌리기)")
    parser.add_argument("--apply", action="store_true", help="노트를 저장하고 도면팀 알림을 남긴다")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = run(apply=args.apply)
    logger.info("drawing_agent_note %s", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
