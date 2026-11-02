"""AI 상담 [수정하기] 자세한 이유 사진 원본 90일 지우기(FOMS-cron 밤 단계 — 설계서 2026-10-27-cs-ai-agent 17.6.1 (b) · D94).

- 기본은 시험 돌리기(지울 줄을 세기만). ``--apply`` 일 때만 저장소(R2)에서 지우고 줄에 ``purged_at`` 을 적는다.
- 저장소가 클라우드가 아니면(이 서비스에 R2 env 가 없음) 줄을 '지움'으로 적지 않고 exit 3 — 밤 러너가 실패로 알린다.
  지울 줄이 없으면 저장소를 열지 않고 exit 0 이다(사진 올리기가 꺼져 있는 동안은 늘 0).
- 저장소에서 못 지운 줄이 있으면 exit 1(그 줄은 다음 밤에 다시).
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

logger = logging.getLogger("purge_cs_edit_photos")

EXIT_FAILED, EXIT_NOT_CLOUD = 1, 3


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


def run(*, apply: bool = False, session=None, now=None, storage_factory=None) -> dict:
    """90일 지난 원본을 지운다(``apply`` 가 거짓이면 세기만). 돌려주는 값: {due, purged, failed, halted}."""
    from foms.services.cs_agent.photo_purge import purge_old_photos
    from foms.services.storage import get_storage

    own = session is None
    engine = None
    if own:
        session, engine = _make_session()
    try:
        result = purge_old_photos(session, now_utc=now or now_utc_naive(), apply=apply,
                                  storage_factory=storage_factory or get_storage)
        return result.summary()
    except Exception:
        session.rollback()
        raise
    finally:
        if own:
            session.close()
            if engine is not None:
                engine.dispose()


def exit_code(summary: dict) -> int:
    """요약 → 종료 코드(0 성공 · 1 못 지운 줄 · 3 저장소가 클라우드가 아님)."""
    if summary.get("halted"):
        return EXIT_NOT_CLOUD
    return EXIT_FAILED if summary.get("failed") else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI 상담 자세한 이유 사진 원본 90일 지우기(기본: 시험 돌리기)")
    parser.add_argument("--apply", action="store_true", help="저장소에서 지우고 줄에 purged_at 을 적는다")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = run(apply=args.apply)
    logger.info("purge_cs_edit_photos %s", summary)
    return exit_code(summary)


if __name__ == "__main__":
    sys.exit(main())
