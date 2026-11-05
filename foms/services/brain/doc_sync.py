"""반영 때 상담 지식 문서 다시 쓰기 — 표가 정본이고, 상담 두뇌가 읽는 지식 문서는 반영마다 표에서 같은 꼴로 다시 만든다
(설계서 7.5 '저장 꼴' · 3.1 규칙 1).

- 부르는 곳은 반영 동작(:func:`.apply.apply_change`) 하나다 — 승인 · 고쳐 승인 · 한꺼번에 · 아직 맞음 · 항목 되돌리기 · 판
  되돌리기 · 주간 고침 안 승인이 모두 그 길을 지난다. 옮기기(:mod:`.doc_import` — 문서 → 표)는 부르지 않는다.
- 지식 문서 유형(:data:`.constants.DOC_TYPES`) 항목 동작만 — 그 브랜드 문서(공통 항목이면 모든 브랜드 문서). 링크 동작은 문서
  칸을 바꾸지 않는다.
- **같은 트랜잭션**: 문서 줄을 잠그고(브랜드 이름 차례) 표에서 다시 만든 문서를
  :func:`foms.services.cs_agent.knowledge.save_document` 로 넣는다(버전 · 수정 기록 · 감사 그대로, 넣는 사람 = 승인한 사람).
  같은 문서면 쓰지 않는다. 반영 동작의 저장점 안에서 돌아, 여기서 멈추면 반영째 되돌아간다 — 표와 문서가 조용히 갈라지지 않는다.
- **이 반영 밖의 차이는 덮지 않는다**: 저장된 문서와 다시 만든 문서가 이 반영이 건드린 문서 id 밖에서 다르면(옮기기 전 ·
  문서를 직접 고침 · 꼴이 틀림) 반영을 멈춘다(:class:`.errors.BrainDocSyncError`) — 표에서 다시 만들면 표에 없는 문서 글이
  사라지기 때문이다. 관리자가 옮기기(문서 → 표) 또는 맞추기(표 → 문서, :func:`publish_documents`)로 먼저 맞춘다.
- 로그 · 오류에는 브랜드 · 문서 id · 코드만 싣는다(글 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain.constants import BRAND_COMMON, DOC_TYPES, OBJECT_OPS
from foms.services.brain.doc_bridge import regenerate_document
from foms.services.brain.errors import BrainDocSyncError
from foms.services.cs_agent.knowledge import (
    KNOWN_BRANDS, KnowledgeError, KnowledgeNoChangeError, KnowledgeSchemaError, read_stored, save_document,
)
from foms.services.cs_agent.knowledge_doc import diff_documents
from foms.services.datetime_kst import now_utc_naive

logger = logging.getLogger(__name__)

#: 이 반영 밖 차이로 멈출 때 오류에 싣는 문서 id 상한.
MAX_STRAY_IDS = 20


def doc_brands(change: BrainChange) -> tuple[str, ...]:
    """이 반영이 다시 써야 할 지식 문서 브랜드 — 지식 문서 유형 항목 동작만(공통 항목이면 모든 브랜드)."""
    if change.op not in OBJECT_OPS or change.item_type not in DOC_TYPES:
        return ()
    return tuple(sorted(KNOWN_BRANDS)) if change.brand == BRAND_COMMON else (change.brand,)


def _touched_ids(session: Any, change: BrainChange, result_version: Optional[int]) -> frozenset[str]:
    """이 반영이 건드린 문서 id — 기준 판 · 새 판의 실음 칸 ``doc_id``(문서 id 를 바꾼 고침이면 둘 다)."""
    versions = [v for v in (change.base_version, result_version) if v is not None]
    payloads = session.execute(select(BrainObject.payload).where(
        BrainObject.item_key == change.item_key, BrainObject.version.in_(versions))).scalars() if versions else ()
    return frozenset(str(p["doc_id"]) for p in payloads if isinstance(p, dict) and p.get("doc_id"))


def stray_ids(stored: Optional[dict[str, Any]], regenerated: dict[str, Any], touched: Iterable[str]) -> list[str]:
    """두 문서가 건드린 id 밖에서 다른 항목 id(더함 · 뺌 · 칸 · 차례). 빈 목록이면 이 반영만큼만 다르다."""
    allowed = set(touched)
    diff = diff_documents(stored, regenerated)
    ids = {*diff.added, *diff.removed, *diff.changed} - allowed
    old = [row["id"] for row in (stored or {}).get("items") or [] if row["id"] not in allowed]
    new = [row["id"] for row in regenerated.get("items") or [] if row["id"] not in allowed]
    if [i for i in old if i in new] != [i for i in new if i in old]:  # 다른 항목의 차례가 바뀜
        ids.add("(차례)")
    return sorted(ids)


def _save(session: Any, brand: str, document: dict[str, Any], *, version: int, actor_id: int,
          now: datetime.datetime) -> Optional[int]:
    """다시 만든 문서를 넣는다 — 새 버전(같은 문서면 ``None``). 버전 엇갈림 · 꼴 오류는 반영째 멈춘다."""
    try:
        return save_document(session, brand, document, actor_user_id=actor_id, expected_version=version,
                             now=now).version
    except KnowledgeNoChangeError:
        return None
    except KnowledgeError as exc:
        raise BrainDocSyncError(brand, exc.code) from None


def sync_documents(session: Any, change: BrainChange, *, actor_id: int, result_version: Optional[int],
                   now: datetime.datetime) -> dict[str, int]:
    """반영 하나 뒤 — 닿은 브랜드 지식 문서를 표에서 다시 만들어 넣는다. 브랜드 → 새 문서 버전(바뀐 것 없으면 빠짐).

    Raises:
        BrainDocSyncError: 저장된 문서 꼴이 틀림 · 다시 만든 문서가 꼴에 맞지 않음 · 이 반영 밖 차이 · 버전 엇갈림.
    """
    brands = doc_brands(change)
    if not brands:
        return {}
    touched = _touched_ids(session, change, result_version)
    written: dict[str, int] = {}
    for brand in brands:  # 브랜드 이름 차례로 잠근다 — 같은 때 두 반영이 서로 기다리다 막히지 않게
        stored = read_stored(session, brand, for_update=True)
        if stored.problem:
            raise BrainDocSyncError(brand, "stored_invalid")
        try:
            regenerated = regenerate_document(session, brand)
        except KnowledgeSchemaError:
            raise BrainDocSyncError(brand, "regenerate_invalid") from None
        if stored.document is None and not regenerated["items"]:
            continue  # 문서도 표 항목도 없는 브랜드 — 빈 문서를 만들지 않는다
        stray = stray_ids(stored.document, regenerated, touched)
        if stray:
            logger.warning("[회사 지식] 지식 문서가 표와 달라 반영을 멈춘다 brand=%s change=%s ids=%s",
                           brand, change.id, stray[:MAX_STRAY_IDS])
            raise BrainDocSyncError(brand, "drift", stray[:MAX_STRAY_IDS])
        version = _save(session, brand, regenerated, version=stored.version, actor_id=actor_id, now=now)
        if version is not None:
            written[brand] = version
    return written


def publish_documents(session: Any, *, actor_id: int, brands: Iterable[str] = (),
                      now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """맞추기(표 → 문서) — 브랜드마다 표에서 다시 만든 문서를 넣는다(관리자 스크립트 ``--publish`` 만, 커밋은 호출자).

    표가 정본이라 문서에만 있는 글은 이때 문서에서 빠진다(빠지기 전 문서는 지식 문서 수정 기록에 남는다 — 되돌릴 수 있다).
    돌려주는 값: 브랜드 → ``{"version", "diff"}``(바뀐 것 없으면 ``version`` 은 지금 버전, ``diff`` 는 ``None``).
    """
    out: dict[str, Any] = {}
    for brand in sorted(brands or KNOWN_BRANDS):
        stored = read_stored(session, brand, for_update=True)
        try:
            regenerated = regenerate_document(session, brand)
        except KnowledgeSchemaError:
            raise BrainDocSyncError(brand, "regenerate_invalid") from None
        if stored.document is None and not regenerated["items"]:
            out[brand] = {"version": stored.version, "diff": None}  # 문서도 표 항목도 없는 브랜드 — 빈 문서를 만들지 않는다
            continue
        version = _save(session, brand, regenerated, version=stored.version, actor_id=actor_id,
                        now=now or now_utc_naive())
        out[brand] = {"version": version if version is not None else stored.version,
                      "diff": diff_documents(stored.document, regenerated).summary() if version is not None else None}
    return out
