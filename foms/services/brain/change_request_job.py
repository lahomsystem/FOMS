"""문장으로 고치기 분석 — WORKER 줄 일(설계서 2026-11-18-brain-sentence-change 6절 '줄 일로 돌릴지는 실측으로' — 운영 web 에는
AI 열쇠가 없다, 열쇠는 WORKER 에만 · 상담 두뇌 C3-0).

- **넣기**(:func:`enqueue_analysis`): web 이 묶음 줄을 ``analyzing`` 으로 만들고(또는 되물음 답으로 되돌리고) **커밋한 뒤** RQ
  ``default`` 줄에 넣는다 — 상담 AI 평가 줄 일(:func:`foms.services.ai_staff.evals.enqueue_run`)과 같은 줄 · 같은 버릇(줄 일 번호
  고정 · 시간 상한 · 다시 하기 0 · 큐가 없으면 넣지 않고 web 에서 대신 돌리지 않는다). 일 함수는
  :func:`foms.services.jobs.tasks.run_brain_change_request_task`(얇은 들머리 — WORKER 가 미리 읽는 모듈) → :func:`run_change_request_job`.
- **한 번만**(:func:`run_change_request`): 묶음 줄을 잠가 읽고 ``analyzing`` 이 아니거나, 이번 분석(``analyzing_at``)을 이미 다른
  일이 잡았으면(``claimed``) 아무것도 하지 않는다 — 다시 하기 · 두 번 누름이 AI 를 두 번 부르지 않게. 잡은 표시를 커밋한 뒤 분석한다.
- 분석(:func:`.change_request.analyze_closed`)은 ``ready`` · ``asked`` · ``failed`` 로 닫는다(뜻밖의 오류는 ``error:<이름>``). 일이
  아예 돌지 못하면 10분 뒤 읽기가 ``stuck`` 으로 닫는다(:func:`.change_request_store.close_stuck`).
- 넣은 사람의 권한은 역할 · 팀으로 다시 본다(:func:`.change_request_store.role_viewer` — 접목판 스위치는 web 에서 이미 봤다.
  WORKER env 에 스위치가 없어도 된다). 그 사이 권한을 잃었으면 ``failed``(``forbidden``).
로그에는 번호 · 상태 · 코드만 싣는다(글 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from db import db_session
from foms.persistence.brain.models import BrainChangeRequest
from foms.services.brain.change_request import analyze_closed
from foms.services.brain.change_request_store import ANALYZING, ANALYZING_AT, CLAIMED, save_bundle
from models import User

logger = logging.getLogger(__name__)

__all__ = ["SKIPPED", "run_change_request", "run_change_request_job"]

SKIPPED = "skipped"


def run_change_request(session: Any, request_id: Any, *, client: Any = None,
                       now: Optional[datetime.datetime] = None) -> str:
    """묶음 하나 분석(한 번만) — 닫은 상태 또는 :data:`SKIPPED`. 세션을 커밋한다."""
    row = session.get(BrainChangeRequest, int(request_id), with_for_update=True, populate_existing=True)
    bundle = (row.bundle or {}) if row is not None else {}
    claimed = bundle.get(CLAIMED)
    if row is None or row.status != ANALYZING or (claimed is not None and claimed == bundle.get(ANALYZING_AT)):
        session.rollback()
        logger.info("[문장으로 고치기 줄 일] 건너뜀 request=%s status=%s", request_id,
                    row.status if row is not None else None)
        return SKIPPED
    save_bundle(row, {**bundle, CLAIMED: bundle.get(ANALYZING_AT)})
    session.commit()  # 잡은 표시 — 같은 분석의 둘째 일은 여기서 멈춘다
    user = session.get(User, row.created_by)
    row = analyze_closed(session, row, user, client=client, now=now)
    session.commit()
    logger.info("[문장으로 고치기 줄 일] 끝 request=%s status=%s code=%s", row.id, row.status, row.error_code)
    return row.status


def run_change_request_job(request_id: int) -> str:
    """RQ 줄 일 본체 — 세션을 열고 :func:`run_change_request` 한 번(WORKER 의 큐 소비자가 꺼낸다)."""
    session = db_session()
    try:
        return run_change_request(session, int(request_id))
    finally:
        session.close()
        db_session.remove()
