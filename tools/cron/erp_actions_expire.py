"""ERP 할 일 제안 밤 정리(FOMS-cron 밤 단계 — 설계서 2026-11-14-foms-graft 3.4 · 3.10).

- 기간이 끝난(넣을 값 날짜가 지났거나 만든 지 7일) 열린 · 실패한 제안을 '기간 끝남'으로 닫는다
  (:func:`foms.services.erp_actions.lifecycle.expire_due`).
- 되맞추기: '실행 중'으로 2분 넘게 남은 줄과 사람이 주문 화면에서 끝낸 바로가기 제안을 맞춘다
  (:func:`foms.services.erp_actions.lifecycle.reconcile` — 승인 대기 읽기도 같은 함수를 부른다).
- 스위치와 상관없이 돈다 — 제안이 없으면 아무것도 쓰지 않고 exit 0(스위치가 꺼진 지금은 늘 그렇다).
- 기본은 시험 돌리기(세기만 하고 되돌림). ``--apply`` 일 때만 커밋한다.
- Flask 앱은 불러오지 않는다(expire_brain_proposals.py 와 같은 길).
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

logger = logging.getLogger("erp_actions_expire")


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
    """기간 끝남 닫기 + 되맞추기(``apply`` 가 거짓이면 세고 되돌림). 돌려주는 값: {expired, reconciled, applied}."""
    from foms.services.erp_actions.lifecycle import expire_due, reconcile

    own = session is None
    engine = None
    if own:
        session, engine = _make_session()
    try:
        when = now or now_utc_naive()
        summary = {"expired": expire_due(session, when), "reconciled": reconcile(session, when), "applied": bool(apply)}
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
    parser = argparse.ArgumentParser(description="ERP 할 일 제안 기간 끝남 닫기 · 되맞추기(기본: 시험 돌리기)")
    parser.add_argument("--apply", action="store_true", help="닫고 맞춘 것을 커밋한다")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = run(apply=args.apply)
    logger.info("erp_actions_expire %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
