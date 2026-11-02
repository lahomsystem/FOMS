"""[수정하기] 자세한 이유 사진 원본 지우기 — 올린 날부터 :data:`KEEP` 90일(설계서 17.6.1 (b) · 사장님 결정 D94).

FOMS-cron 밤 단계(``tools/cron/purge_cs_edit_photos.py --apply`` — :mod:`tools.cron.nightly`)가 부른다. 90일 지난 원본을
저장소(R2)에서 지우고 줄은 ``storage_key`` NULL · ``purged_at`` 을 적는다. 가린 사진 설명(``desc_masked``)은 남긴다(배운 것은
글로 남는다 — D54). 직원 · ADMIN 이 지운 사진은 이미 바로 지웠다(:func:`.edit_detail.delete_photo`).

- **막는 쪽**: 저장소가 클라우드(R2 · S3)가 아니면(그 서비스에 R2 env 가 없음) 줄을 '지움'으로 적지 않고 :data:`NOT_CLOUD` 로
  멈춘다 — 저장소에 남은 파일을 지웠다고 적으면 다시는 찾지 못한다. 지울 줄이 없으면 저장소를 열지 않는다.
- 저장소에서 못 지운 줄은 그대로 둔다(다음 밤에 다시). 묶음마다 커밋한다. 로그는 수 · 코드만(key 없음).
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy import select, update

from foms.persistence.main.models import CsAgentTurnPhoto

logger = logging.getLogger(__name__)

__all__ = ["KEEP", "NOT_CLOUD", "PurgeResult", "due_filter", "purge_old_photos"]

KEEP = datetime.timedelta(days=90)
BATCH = 200
NOT_CLOUD = "storage_not_cloud"
_CLOUD = ("r2", "s3")


@dataclass
class PurgeResult:
    """밤 단계 한 번 — 지울 줄 · 지움 · 못 지움 수 · 멈춤 코드."""

    due: int = 0
    purged: int = 0
    failed: int = 0
    halted: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        """로그 · 시험 재료(수 · 코드만)."""
        return {"due": self.due, "purged": self.purged, "failed": self.failed, "halted": self.halted}


def due_filter(now_utc: datetime.datetime) -> tuple[Any, ...]:
    """지울 줄 — 살아 있는 원본(key 있음 · 아직 안 지움)이고 올린 지 :data:`KEEP` 넘은 것."""
    return (CsAgentTurnPhoto.purged_at.is_(None), CsAgentTurnPhoto.storage_key.isnot(None),
            CsAgentTurnPhoto.created_at < now_utc - KEEP)


def purge_old_photos(session: Any, *, now_utc: datetime.datetime, apply: bool,
                     storage_factory: Callable[[], Any]) -> PurgeResult:
    """90일 지난 원본을 지운다(``apply`` 가 거짓이면 세기만). 커밋한다.

    Args:
        session: DB 세션.
        now_utc: 지금(UTC, 시간대 없음 — 표 칸과 같은 꼴).
        apply: 참이면 저장소에서 지우고 줄을 적는다.
        storage_factory: 저장소 어댑터를 만드는 함수(지울 줄이 있을 때만 부른다 — 시험은 가짜).

    Returns:
        :class:`PurgeResult`.
    """
    result = PurgeResult()
    rows = session.execute(select(CsAgentTurnPhoto.id, CsAgentTurnPhoto.storage_key)
                           .where(*due_filter(now_utc)).order_by(CsAgentTurnPhoto.id)).all()
    session.rollback()
    result.due = len(rows)
    if not rows or not apply:
        return result
    storage = storage_factory()
    if getattr(storage, "storage_type", "") not in _CLOUD:
        logger.error("[CS 사진 지우기] 저장소가 클라우드가 아니라 멈춘다 code=%s due=%d", NOT_CLOUD, result.due)
        result.halted = NOT_CLOUD
        return result
    photos = CsAgentTurnPhoto.__table__
    for start in range(0, len(rows), BATCH):
        for row in rows[start:start + BATCH]:
            if storage.delete_file(row.storage_key) is False:
                result.failed += 1
                continue
            session.execute(update(photos).where(photos.c.id == row.id, photos.c.purged_at.is_(None))
                            .values(storage_key=None, purged_at=now_utc))
            result.purged += 1
        session.commit()
    logger.info("[CS 사진 지우기] %s", result.summary())
    return result
