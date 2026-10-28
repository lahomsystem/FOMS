"""기준 답 · 지식 저장 — 브랜드마다 SystemSetting 키 하나에 항목 문서를 두고, **승인 항목만** 초안 재료로 낸다(플랜 C2-1).

설계서 7절 2 · 7.1(C2-0 확정안) · 15.3 의 3a 줄. 문서 꼴 · 승인 거르기 · 차이는 순수 모듈 :mod:`.knowledge_doc`, 여기는
DB 읽기 · 쓰기다. 3a 자동 답은 :meth:`ApprovedKnowledge.templates_for_intent` 의 글만 보내고, 모델은 의도 id 만 고른다
(:meth:`ApprovedKnowledge.template_intents`).

- **키(브랜드마다 하나)**: :func:`knowledge_key` — ``cs_agent_knowledge_lahom`` · ``cs_agent_knowledge_haud``(바로 끄기
  ``cs_agent_switch`` · 루프 기록 ``cs_agent_loop_state`` 와 같은 꼴). 재료를 내는 길은 :func:`load_approved` 하나다.
  저장 값의 꼴이 틀리거나 다른 브랜드 문서면 재료 0 + 경고 로그 — 막는 쪽으로 닫힌다.
- **쓰는 길 = 기존 설정 쓰기 길(SHIPMENT-REFERENCE-01)**: 검사(잠금 전) → 줄 ``FOR UPDATE`` → 버전 대조(낙관적 잠금) →
  값 갈아 끼우기 · 버전 +1 → 수정 기록(``SystemSettingReceipt`` — 그 버전 문서 전체) + 감사 원장(``SecurityLog``)을 한
  트랜잭션에. 커밋은 호출자 몫이다(``shipment_reference.update_shipment_reference_lists`` · ``drawing_wizard_presets
  .update_wizard_presets`` 와 같은 규약). 멱등 키는 쓰지 않는다 — 다시 넣기는 버전 대조가 막는다.
- **되돌리기**: 수정 기록에서 그 버전 문서를 꺼내 같은 길로 **새 버전**으로 쓴다(버전 번호는 되감지 않는다).
  넣은 사람 계정을 관리자 화면에서 삭제(비활성화)하면 그 사람의 수정 기록이 같이 지워진다(``user_deletion``
  ``_DELETE_USER_REFERENCE_FIELDS``) — 그 버전으로는 되돌릴 수 없고, 저장소 밖 원본 문서를 다시 넣어야 한다.
- **공개 저장소**: 이 모듈은 틀만 있다. 실제 기준 답 · 가격 · 사장님 결정은 저장소 밖에서 승인받아 관리자 스크립트
  (``tools/ops/cs_agent_knowledge.py``)로 넣는다. 오류 · 로그 · 요약에는 항목 id · 개수만 싣고 글은 싣지 않는다.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.cs_agent.knowledge_doc import (
    KNOWN_BRANDS,
    ApprovedKnowledge,
    KnowledgeDiff,
    KnowledgeError,
    KnowledgeItem,
    KnowledgeSchemaError,
    approved_items,
    count_items,
    diff_documents,
    validate_document,
)
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog, SystemSetting, SystemSettingReceipt

logger = logging.getLogger(__name__)

__all__ = [
    "KEY_PREFIX", "KNOWN_BRANDS", "POLICY_ID", "ApprovedKnowledge", "KnowledgeConflictError", "KnowledgeError",
    "KnowledgeHistoryError", "KnowledgeItem", "KnowledgeNoChangeError", "KnowledgeSchemaError", "SaveResult",
    "StoredKnowledge", "count_items", "diff_documents", "history", "knowledge_key", "load_approved", "read_stored",
    "rollback", "save_document", "templates_for_intent", "validate_document", "version_document",
]

KEY_PREFIX = "cs_agent_knowledge_"
#: 수정 기록(``SystemSettingReceipt.policy_id``) 이름 — 이 이름의 기록만 되돌리기 · 이력 재료가 된다.
POLICY_ID = "CS_AGENT_KNOWLEDGE"
#: 수정 기록의 ``expires_at``. 다른 설정 영수증은 커밋 + 24시간(다시 보내기 창)이고 그 칸으로 오래된 줄을 지울 색인이
#: 있다(``ix_ssr_expires_id`` — '향후 retention purge'). 지식 기록은 되돌리기 이력이라 길게 둔다(원장 R6-17).
RECEIPT_KEEP = datetime.timedelta(days=3650)


class KnowledgeConflictError(KnowledgeError):
    """읽은 버전과 지금 버전이 다르다(다른 사람이 먼저 넣었다) — 모의 실행부터 다시."""

    code = "REVISION_CONFLICT"

    def __init__(self, current_version: int) -> None:
        """지금 버전을 싣는다."""
        super().__init__(f"버전이 다르다 — 지금 버전 {current_version}")
        self.current_version = int(current_version)


class KnowledgeHistoryError(KnowledgeError):
    """되돌릴 버전의 수정 기록이 없거나 지금 꼴로 읽을 수 없다."""

    code = "CS_KNOWLEDGE_HISTORY"


class KnowledgeNoChangeError(KnowledgeError):
    """새 문서가 지금 문서와 같다 — 같은 내용으로 버전만 늘리지 않는다."""

    code = "CS_KNOWLEDGE_NO_CHANGE"


def knowledge_key(brand: str) -> str:
    """브랜드의 SystemSetting 키.

    Raises:
        ValueError: 모르는 브랜드(채널 짝 ``channel_read.CHANNEL_BRANDS`` 에 없는 이름).
    """
    if brand not in KNOWN_BRANDS:
        raise ValueError(f"모르는 브랜드: {brand!r}")
    return KEY_PREFIX + brand.lower()


# ── 읽기 ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class StoredKnowledge:
    """저장된 문서(정본) · 버전. 줄은 있는데 꼴이 틀리면 ``document`` 는 ``None`` 이고 ``problem`` 에 까닭."""

    brand: str
    version: int  # 0 = 넣은 적 없음
    document: Optional[dict[str, Any]] = field(default=None, repr=False)  # 기준 답 · 가격 — 로그에 따라가지 않게
    problem: Optional[str] = None


def _stored_of(row: Optional[SystemSetting], brand: str) -> StoredKnowledge:
    """설정 줄 → :class:`StoredKnowledge`. 저장 값을 다시 검사한다(손으로 고친 값 · 다른 브랜드 문서를 거른다)."""
    if row is None:
        return StoredKnowledge(brand, 0)
    version = int(row.version or 0)
    if row.setting_value is None:
        return StoredKnowledge(brand, version, problem="값이 비었다")
    try:
        return StoredKnowledge(brand, version, validate_document(copy.deepcopy(row.setting_value), brand=brand))
    except KnowledgeSchemaError as exc:
        return StoredKnowledge(brand, version, problem="; ".join(exc.problems[:3]))


def read_stored(session: Any, brand: str, *, for_update: bool = False) -> StoredKnowledge:
    """저장된 문서를 읽는다(매번 DB 에서 새로). ``for_update`` 면 그 줄을 잠근다(PostgreSQL)."""
    row = session.get(SystemSetting, knowledge_key(brand), populate_existing=True,
                      with_for_update=True if for_update else None)
    return _stored_of(row, brand)


def load_approved(session: Any, brand: str) -> ApprovedKnowledge:
    """그 브랜드의 승인 항목 묶음 — 초안 · 자동 답 재료를 내는 유일한 길. 꼴이 틀린 저장 값은 재료 0 + 경고."""
    stored = read_stored(session, brand)
    if stored.problem:
        logger.warning("[CS 지식] 저장된 기준 답 꼴이 틀려 재료를 내지 않는다 key=%s version=%s problem=%s",
                       knowledge_key(brand), stored.version, stored.problem)
    return ApprovedKnowledge(brand, stored.version, approved_items(stored.document), stored.problem)


def templates_for_intent(session: Any, brand: str, intent: str) -> tuple[KnowledgeItem, ...]:
    """그 브랜드 · 의도의 승인된 기준 답 문구(:meth:`ApprovedKnowledge.templates_for_intent`)."""
    return load_approved(session, brand).templates_for_intent(intent)


# ── 수정 기록(이력) ──────────────────────────────────────────────────────
def _receipts(session: Any, brand: str) -> Any:
    """이 브랜드 지식의 수정 기록 질의(설정 키 색인 ``ix_ssr_setting_key``)."""
    return session.query(SystemSettingReceipt).filter(
        SystemSettingReceipt.setting_key == knowledge_key(brand), SystemSettingReceipt.policy_id == POLICY_ID)


def _body_data(receipt: SystemSettingReceipt) -> dict[str, Any]:
    """수정 기록 본문의 ``data`` 칸(꼴이 틀리면 빈 dict)."""
    body = receipt.response_body if isinstance(receipt.response_body, dict) else {}
    return body["data"] if isinstance(body.get("data"), dict) else {}


def version_document(session: Any, brand: str, version: int) -> dict[str, Any]:
    """그 버전에 넣은 문서(정본)를 수정 기록에서 꺼낸다.

    Raises:
        KnowledgeHistoryError: 기록이 없거나(넣은 적 없는 버전 · 넣은 사람 계정 삭제) 지금 꼴로 읽을 수 없다.
    """
    receipt = (_receipts(session, brand).filter(SystemSettingReceipt.resulting_version == int(version))
               .order_by(SystemSettingReceipt.id.desc()).first())
    if receipt is None:
        raise KnowledgeHistoryError(f"버전 {version} 의 수정 기록이 없다")
    try:
        return validate_document(copy.deepcopy(_body_data(receipt).get("knowledge")), brand=brand)
    except KnowledgeSchemaError as exc:
        raise KnowledgeHistoryError(f"버전 {version} 기록을 지금 꼴로 읽을 수 없다: {exc}") from exc


def history(session: Any, brand: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """최근 수정 기록(새 것부터) — 버전 · 시각 · 넣은 사람 id · 되돌린 버전 · 개수(글 없음)."""
    rows = _receipts(session, brand).order_by(SystemSettingReceipt.resulting_version.desc(),
                                              SystemSettingReceipt.id.desc()).limit(limit).all()
    entries = []
    for receipt in rows:
        data = _body_data(receipt)
        created = receipt.created_at
        entries.append({
            "version": receipt.resulting_version, "actor_user_id": receipt.actor_user_id,
            "at": created.isoformat(timespec="seconds") if isinstance(created, datetime.datetime) else str(created),
            "restored_from": data.get("restored_from_version"),
            "counts": count_items(data.get("knowledge") if isinstance(data.get("knowledge"), dict) else None)})
    return entries


# ── 쓰기(기존 설정 쓰기 길) ──────────────────────────────────────────────
@dataclass(frozen=True)
class SaveResult:
    """쓰기 결과 — 새 버전 · 수정 기록 id · 차이."""

    brand: str
    version: int
    receipt_id: str
    diff: KnowledgeDiff
    restored_from: Optional[int] = None


def _hash_of(document: Mapping[str, Any]) -> str:
    """정본 문서의 sha256(수정 기록 ``request_hash``)."""
    blob = json.dumps(document, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _put_value(session: Any, row: Optional[SystemSetting], brand: str, document: dict[str, Any]) -> SystemSetting:
    """값을 통째로 갈아 끼운다(줄이 없으면 버전 0 으로 만든다 — 호출부가 1 로 올린다)."""
    if row is None:
        row = SystemSetting(setting_key=knowledge_key(brand), version=0,
                            description=f"AI 상담팀원 기준 답 · 지식({brand}) — 승인 항목만 재료(플랜 C2-1)")
        try:
            with session.begin_nested():  # 없는 줄은 FOR UPDATE 가 못 잠근다 — 같은 때 첫 넣기가 겹치면 여기서 갈린다
                session.add(row)
                session.flush()
        except IntegrityError:
            # 다른 사람이 먼저 첫 버전을 넣었다 — 버전 충돌로 알린다(SQL 값 · 문서가 든 오류 글은 내보내지 않는다, R6-16)
            existing = session.get(SystemSetting, knowledge_key(brand), populate_existing=True)
            raise KnowledgeConflictError(int(existing.version or 0) if existing is not None else 0) from None
    row.setting_value = copy.deepcopy(document)
    flag_modified(row, "setting_value")
    return row


def _record(session: Any, *, brand: str, document: dict[str, Any], version: int, actor_user_id: int,
            restored_from: Optional[int], now: datetime.datetime) -> str:
    """수정 기록(그 버전 문서 전체) + 감사 원장 한 줄을 같은 트랜잭션에 넣는다. 수정 기록 id 를 돌려준다."""
    receipt_id = str(uuid.uuid4())
    body = {"success": True, "data": {"version": version, "brand": brand, "knowledge": copy.deepcopy(document),
                                      "restored_from_version": restored_from}}
    session.add(SystemSettingReceipt(
        read_receipt_id=receipt_id, actor_user_id=actor_user_id, setting_key=knowledge_key(brand),
        policy_id=POLICY_ID, idempotency_key=None, request_hash=_hash_of(document), response_status=200,
        response_body=body, resulting_version=version, expires_at=now + RECEIPT_KEEP))
    verb = "UPDATE" if restored_from is None else "ROLLBACK"
    tail = "" if restored_from is None else f" restored_from={restored_from}"
    session.add(SecurityLog(user_id=actor_user_id, message=(
        f"CS_AGENT_KNOWLEDGE_{verb} key={knowledge_key(brand)} version={version} "
        f"approved={len(approved_items(document))} total={count_items(document)['total']}{tail}")))
    session.flush()
    return receipt_id


def _write(session: Any, brand: str, document: dict[str, Any], *, actor_user_id: int, expected_version: int,
           now: Optional[datetime.datetime], restored_from: Optional[int]) -> SaveResult:
    """잠금 → 버전 대조 → 값 · 버전 → 수정 기록 · 감사(커밋은 호출자)."""
    row = session.get(SystemSetting, knowledge_key(brand), populate_existing=True, with_for_update=True)
    current = int(row.version or 0) if row is not None else 0
    if expected_version != current:
        raise KnowledgeConflictError(current)
    before = _stored_of(row, brand).document
    if before == document:
        raise KnowledgeNoChangeError(f"지금 버전 {current} 과 같은 문서다 — 쓰지 않는다")
    row = _put_value(session, row, brand, document)
    row.version = current + 1
    receipt_id = _record(session, brand=brand, document=document, version=row.version, actor_user_id=actor_user_id,
                         restored_from=restored_from, now=now or now_utc_naive())
    return SaveResult(brand, row.version, receipt_id, diff_documents(before, document), restored_from)


def save_document(session: Any, brand: str, doc: Any, *, actor_user_id: int, expected_version: int,
                  now: Optional[datetime.datetime] = None) -> SaveResult:
    """새 문서를 새 버전으로 넣는다(커밋은 호출자). 검사는 잠금 전에 한다.

    Args:
        session: DB 세션.
        brand: 브랜드(키를 정한다 — 문서의 ``brand`` 와 같아야 한다).
        doc: 넣을 문서(신뢰하지 않는다).
        actor_user_id: 넣는 사람(켜진 ADMIN — 수정 기록 · 감사 주체).
        expected_version: 모의 실행에서 읽은 지금 버전(넣은 적 없으면 0).
        now: 시험 주입(UTC naive).

    Returns:
        :class:`SaveResult`.

    Raises:
        KnowledgeSchemaError: 문서 꼴이 틀림. KnowledgeConflictError: 버전이 다름. KnowledgeNoChangeError: 바뀐 것 없음.
    """
    document = validate_document(doc, brand=brand)
    return _write(session, brand, document, actor_user_id=actor_user_id, expected_version=expected_version,
                  now=now, restored_from=None)


def rollback(session: Any, brand: str, to_version: int, *, actor_user_id: int, expected_version: int,
             now: Optional[datetime.datetime] = None) -> SaveResult:
    """이전 버전 문서를 수정 기록에서 꺼내 같은 길로 새 버전으로 쓴다(커밋은 호출자).

    Returns:
        :class:`SaveResult` (``restored_from`` = ``to_version``).

    Raises:
        KnowledgeHistoryError: 그 버전 기록이 없음. KnowledgeConflictError · KnowledgeNoChangeError: :func:`save_document` 와 같다.
    """
    document = version_document(session, brand, to_version)
    return _write(session, brand, document, actor_user_id=actor_user_id, expected_version=expected_version,
                  now=now, restored_from=int(to_version))
