"""하루 판 — 반영마다 그날 판(층별 줄)에 붙인다(설계서 4절 '판' · 6절 · 17.6 '하루 한 판').

- 판 번호는 그날 모든 층이 같이 쓰고, 층마다 줄 하나(``uq_brain_releases_number_layer``) — 층마다 따로 되돌릴 수 있게.
- **판 0** = 지식 문서에서 옮겨 온 판. 옮기기(:mod:`.doc_import`)는 1 번 이상 판이 아직 없으면 판 0 에 붙는다.
- 그 밖에는 오늘(한국 날짜) 판(1 이상)이 있으면 그 번호, 없으면 가장 큰 번호 + 1.
- 판 줄에는 동작별 수와 바뀐 키(:data:`MAX_DIFF_KEYS` 까지 — 글 없음)만 둔다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.brain.models import BrainRelease
from foms.services.brain.store import kst_day

IMPORT_RELEASE = 0
MAX_DIFF_KEYS = 200


def release_number(session: Any, *, day: datetime.date, as_import: bool) -> int:
    """붙을 판 번호."""
    later = session.execute(select(func.max(BrainRelease.number)).where(BrainRelease.number > IMPORT_RELEASE)).scalar()
    if as_import and later is None:
        return IMPORT_RELEASE
    today = session.execute(select(func.max(BrainRelease.number)).where(
        BrainRelease.day == day, BrainRelease.number > IMPORT_RELEASE)).scalar()
    return int(today) if today is not None else int(later or IMPORT_RELEASE) + 1


def _row(session: Any, number: int, layer: str) -> Optional[BrainRelease]:
    """(번호, 층) 판 줄."""
    query = select(BrainRelease).where(BrainRelease.number == number, BrainRelease.layer == layer)
    return session.execute(query.execution_options(populate_existing=True)).scalar_one_or_none()


def ensure_row(session: Any, number: int, layer: str, *, day: datetime.date, actor_id: Optional[int],
                now: datetime.datetime) -> BrainRelease:
    """(번호, 층) 판 줄 — 없으면 만든다(같은 때 둘이 만들면 유일 색인에서 갈려 다시 읽는다)."""
    row = _row(session, number, layer)
    if row is not None:
        return row
    try:
        with session.begin_nested():
            row = BrainRelease(number=number, layer=layer, day=day, counts={}, diff={"keys": [], "more": 0},
                               created_by=actor_id, created_at=now, updated_at=now)
            session.add(row)
            session.flush()
        return row
    except IntegrityError:
        found = _row(session, number, layer)
        if found is None:
            raise
        return found


def attach(session: Any, *, layer: str, op: str, key: str, actor_id: Optional[int], now: datetime.datetime,
           as_import: bool = False) -> int:
    """반영 하나를 그날 판(층 줄)에 붙이고 판 번호를 돌려준다(커밋은 호출자)."""
    day = kst_day(now)
    number = release_number(session, day=day, as_import=as_import)
    row = ensure_row(session, number, layer, day=day, actor_id=actor_id, now=now)
    counts = copy.deepcopy(row.counts or {})
    counts[op] = int(counts.get(op, 0)) + 1
    diff = copy.deepcopy(row.diff or {"keys": [], "more": 0})
    keys = list(diff.get("keys") or [])
    if key not in keys and len(keys) < MAX_DIFF_KEYS:  # 같은 키가 같은 판에 두 번이면 수만 센다
        keys.append(key)
    elif key not in keys:
        diff["more"] = int(diff.get("more", 0)) + 1
    diff["keys"] = keys
    row.counts, row.diff, row.updated_at = counts, diff, now
    flag_modified(row, "counts")
    flag_modified(row, "diff")
    return number
