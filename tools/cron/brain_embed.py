"""회사 지식 의미 찾기 벡터 밤 다시 넣기(FOMS-cron 밤 단계 — 사장님 D114 · 설계서 7절 '비슷한 것 찾기').

- 설정 '의미 찾기'(``brain_embeddings_enabled``)가 꺼져 있으면(처음 값) · 열쇠 env(``VOYAGE_API_KEY``) · 하루 돈 상한 · 벡터 표
  (pgvector)가 없으면 아무것도 하지 않고 exit 0(까닭 코드만 로그).
- 켜져 있으면 지금 판이 바뀐 항목(판 번호 · 글 지문이 다름)과 새 항목을 묶음마다 벡터로 바꿔 넣고, 은퇴 · 범위가 바뀐 항목의 벡터는
  지운다. 물어보기 가린 질문 가운데 벡터가 없는 것도 채운다(:func:`foms.services.brain.embed_sources.run_embed` — 근원
  ``brain_item`` · ``chatbot_question``). **상담 사례(``cs_case``)는 밤 단계에서 다루지 않는다**(백필 스크립트만). 돈은 의미 찾기 돈
  줄 · 상한 안.
- 켜 놓았는데 부르다 실패하면 exit 3(밤 러너가 실패로 알린다). 기본은 시험 돌리기(세기만 · 돈 0). ``--apply`` 일 때만 부르고 쓴다.
- Flask 앱은 불러오지 않는다. 한 번에 다룰 항목 상한 ``--limit``(처음 500).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.datetime_kst import now_kst  # noqa: E402
from tools.cron.expire_brain_proposals import _make_session  # noqa: E402

logger = logging.getLogger("brain_embed")
FAILED_EXIT = 3


def run(*, apply: bool = False, session=None, now=None, limit: int = 500, sources=None) -> dict:
    """벡터 다시 넣기(``apply`` 가 거짓이면 세기만). 돌려주는 값: {근원: 요약} 또는 {error}."""
    from foms.services.brain.chat_settings import read_chat_settings
    from foms.services.brain.embed_sources import NIGHTLY_SOURCES, run_embed
    from foms.services.brain.embeddings import EmbedUnavailable

    own = session is None
    engine = None
    if own:
        session, engine = _make_session()
    try:
        cfg = read_chat_settings(session)
        try:
            return run_embed(session, cfg=cfg, now=now or now_kst(), limit=limit, apply=apply,
                             sources=sources or NIGHTLY_SOURCES)
        except EmbedUnavailable as exc:
            session.rollback()
            return {"error": exc.code}
    finally:
        if own:
            session.close()
            if engine is not None:
                engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="회사 지식 의미 찾기 벡터 다시 넣기(기본: 시험 돌리기 — 돈 0)")
    parser.add_argument("--apply", action="store_true", help="실제로 부르고 넣는다(돈이 든다)")
    parser.add_argument("--limit", type=int, default=500, help="한 번에 다룰 항목 상한")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = run(apply=args.apply, limit=max(1, args.limit))
    logger.info("brain_embed %s", summary)
    return FAILED_EXIT if "error" in summary else 0


if __name__ == "__main__":
    sys.exit(main())
