"""'AI 시험' 매주 저절로 한 번 — WORKER 15분 바퀴 학습 몫의 단계 ``weekly_eval``(설계서 2026-11-22-ai-eval-meaning-judge 2.4 ·
사장님 11-22 '매주 월요일 자동' · 상담 원장 D281).

조건이 모두 맞을 때만 [시험 다시 돌리기]와 같은 길로 줄 일을 넣는다(:func:`.evals.add_run` → :func:`.evals.enqueue_run` —
돌리는 사람 칸은 비운다, ``actor_id=None``):

1. KST 월요일이다(그날 첫 바퀴가 넣는다 — 시간 창은 두지 않는다).
2. 설정이 준비됐다(:attr:`.evals.EvalSettings.ready` — 돈 상한 · 묶음 크기가 0 이 아니다).
3. 지난 :data:`GAP` 안에 시작한 결과 줄 가운데 돈을 쓴 줄도, 이 단계가 넣은 줄(누른 사람 없음)도 없다. 이 단계가 넣은 줄을
   함께 보는 까닭: 스테이징처럼 열쇠가 없어 돈 없이 '준비 안 됨'으로 끝나는 곳에서 15분마다 다시 넣어 결과 줄 열 개
   (:data:`.evals.KEEP_RUNS`)를 밀어내지 않게 한다.
4. 도는 줄이 없다(:func:`.evals.add_run` 이 ``EVAL_BUSY`` 로 거절하면 넣지 않는다).

큐 넣기가 실패하면 그 줄을 '실패'(``queue_unavailable``)로 풀어 단추를 막지 않는다 — 그 주는 다시 넣지 않는다(3). 감사 줄은
적지 않는다(사람이 누른 것이 아니다 — 결과 줄의 누른 사람 칸이 빈 것이 표시다). 숫자 · 코드만 돌려준다.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Mapping

from foms.services.ai_staff import evals as store
from foms.services.cs_agent.state import KST

logger = logging.getLogger(__name__)

__all__ = ["GAP", "run_weekly_eval"]

#: 이 안에 돈을 쓴(또는 이 단계가 넣은) 결과 줄이 있으면 넣지 않는다.
GAP = datetime.timedelta(days=6)


def _counts(run: Mapping[str, Any], since: datetime.datetime) -> bool:
    """이번 주 몫으로 치는 결과 줄인가 — ``since`` 뒤에 시작했고 돈을 썼거나 누른 사람이 없다(모듈 설명 3)."""
    started = store.parse_started(run)
    if started is None or started < since:
        return False
    cost = store.parse_money(run.get("cost_usd", "0"))
    return run.get("actor_id") is None or (cost is not None and cost > 0)


def run_weekly_eval(session: Any, *, now: datetime.datetime) -> dict[str, Any]:
    """매주 한 번 넣기(모듈 설명). 커밋한다. ``{"off": 코드}`` 이면 넣지 않았다 — 바퀴 요약에 싣지 않는다."""
    if now.astimezone(KST).weekday() != 0:
        return {"off": "not_monday"}
    settings = store.read_eval_settings(session)
    if not settings.ready:
        session.rollback()
        return {"off": "not_ready"}
    since = store.naive_utc(now) - GAP
    if any(_counts(run, since) for run in store.latest_results(session)):
        session.rollback()
        return {"off": "already_this_week"}
    try:
        run = store.add_run(session, actor_id=None, now=now, settings=settings)
    except store.EvalError as exc:
        session.rollback()
        return {"off": "busy" if exc.code == "EVAL_BUSY" else exc.code}
    session.commit()
    if store.enqueue_run(run["id"]):
        logger.info("[AI 시험] 매주 한 번 줄에 넣음 run=%s", run["id"])
        return {"queued": run["id"]}
    store.update_run(session, run["id"], now, status=store.FAILED, code="queue_unavailable")
    session.commit()
    logger.warning("[AI 시험] 매주 한 번 줄 넣기 실패 — 이번 주는 다시 넣지 않는다 run=%s", run["id"])
    return {"queued": None, "code": "queue_unavailable"}
