"""주문 첨부 HEIC → JPEG 백그라운드 변환 (SPEC docs/specs/2026-11-04-heic-to-jpeg_SPEC.md §2-2).

브라우저가 R2 에 바로 올린 아이폰 원본(HEIC)을 서버가 읽어 JPEG 로 바꾸고, 첨부 줄의 key · 이름 · 크기를
바꾼 뒤 썸네일을 만든다. 원본 HEIC 는 기존 ``STORAGE_DELETE`` 지연 삭제 길로 예약한다(사용자 결정: 원본 지우기).

실패하면 HEIC 를 그대로 둔다 — 업로드 자체는 이미 성공 상태다.
"""

from __future__ import annotations

import datetime
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from foms.services import order_attachment_thumbnail
from foms.services.common.dashboard_cache import ATTACHMENT_DASHBOARD_FAMILIES, invalidate_dashboard_families
from foms.services.datetime_kst import now_utc_naive
from foms.services.files.heic_convert import HEIC_EXTS, heic_to_jpeg
from foms.services.files.purge_policy import ATTACHMENT_PURGE_GRACE
from foms.services.jobs.queue import enqueue_heic_conversion
from foms.services.orders.drawing_key_safety import referenced_keys
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.storage import get_storage

logger = logging.getLogger(__name__)

__all__ = [
    "convert_order_attachment_heic",
    "is_heic_filename",
    "schedule_order_attachment_heic_conversion",
    "schedule_order_attachment_post_upload",
]

#: 첨부 이벤트 타입 — 정본 상수는 ``foms/api/files/order_routes.py``(services → api import 금지라 문자열로 둔다).
_ATTACHMENT_META_UPDATED = "ATTACHMENT_META_UPDATED"
_STORAGE_DELETE = "STORAGE_DELETE"

#: 결과 코드(테스트 · 로그용).
CONVERTED = "converted"
SKIPPED = "skipped"
FAILED = "failed"

_executor = ThreadPoolExecutor(max_workers=1)


def is_heic_filename(filename: object) -> bool:
    """파일 이름(또는 key) 확장자가 HEIC/HEIF 인지."""
    if not isinstance(filename, str) or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].strip().lower() in HEIC_EXTS


def _jpeg_filename_for(filename: str) -> str:
    """``IMG_0001.HEIC`` → ``IMG_0001.jpg`` (협력사 변환 ``jpeg_if_heic`` 와 같은 이름 규칙)."""
    base = filename.rsplit(".", 1)[0] if "." in (filename or "") else (filename or "")
    return f"{base or 'photo'}.jpg"


def _now() -> datetime.datetime:
    return now_utc_naive()


def _upload_jpeg(storage: Any, jpeg: bytes, filename: str, folder: str) -> Optional[str]:
    result = storage.upload_file(io.BytesIO(jpeg), filename, folder)
    if not result or not result.get("success"):
        return None
    return result.get("key")


def convert_order_attachment_heic(attachment_id: int, storage_key: str, *, db: Any = None,
                                  storage: Any = None) -> str:
    """첨부 1건의 HEIC 를 JPEG 로 바꾼다. 반환은 :data:`CONVERTED` · :data:`SKIPPED` · :data:`FAILED`.

    Args:
        attachment_id: 대상 ``OrderAttachment.id``.
        storage_key: 예약 때의 HEIC key(그 사이 key 가 바뀌었으면 손대지 않는다).
        db: 세션(테스트용). 없으면 ``db_session()`` 을 열고 닫는다.
        storage: 저장소(테스트용). 없으면 ``get_storage()``.
    """
    from models import Order, OrderAttachment, OrderEvent

    if not attachment_id or not storage_key or not is_heic_filename(storage_key):
        return SKIPPED
    if storage is None:
        storage = get_storage()

    data = storage.read_file_bytes(storage_key)
    if not data:
        logger.warning("[heic] 원본을 읽지 못함 attachment=%s key=%s", attachment_id, storage_key)
        return FAILED
    try:
        jpeg = heic_to_jpeg(data)  # 협력사 사진과 같은 규격(긴 변 1920px · 품질 80) — 공용 함수
    except Exception:  # noqa: BLE001 - 깨진 HEIC 는 원본을 그대로 두고 기록만 남긴다
        logger.warning("[heic] 변환 실패 attachment=%s key=%s", attachment_id, storage_key, exc_info=True)
        return FAILED

    own_session = db is None
    if own_session:
        from db import db_session

        db = db_session()
    new_key: Optional[str] = None
    try:
        attachment = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.id == int(attachment_id))
            .with_for_update()
            .first()
        )
        if attachment is None or attachment.deleted_at is not None or attachment.storage_key != storage_key:
            db.rollback()
            return SKIPPED
        order = db.get(Order, attachment.order_id)
        if order is not None:
            # 그 사이 도면 기록 등이 이 key 를 쓰기 시작했으면 key 를 바꾸지 않는다(참조가 깨진다).
            if referenced_keys(db, order.id, order.structured_data, [storage_key],
                               exclude_attachment_ids=[attachment.id]):
                db.rollback()
                return SKIPPED

        folder = storage_key.rsplit("/", 1)[0] if "/" in storage_key else "uploads"
        new_filename = _jpeg_filename_for(attachment.filename)
        new_key = _upload_jpeg(storage, jpeg, new_filename, folder)
        if not new_key:
            db.rollback()
            logger.warning("[heic] JPEG 업로드 실패 attachment=%s", attachment_id)
            return FAILED

        old_thumb = attachment.thumbnail_key
        attachment.storage_key = new_key
        attachment.filename = new_filename
        attachment.file_type = "image"
        attachment.file_size = len(jpeg)
        attachment.thumbnail_key = None
        now = _now()
        event = OrderEvent(
            order_id=attachment.order_id,
            event_type=_ATTACHMENT_META_UPDATED,
            payload={
                "attachment_id": attachment.id,
                "storage_key": new_key,
                "thumbnail_key": None,
                "filename": new_filename,
                "category": attachment.category,
                "change": "heic_to_jpeg",
                "converted_from": storage_key,
            },
            created_by_user_id=None,
            created_at=now,
        )
        db.add(event)
        db.flush()

        for old in (storage_key, old_thumb):
            if not old:
                continue
            enqueue_side_effect(
                db,
                source_domain="ORDER_EVENT",
                source_id=event.id,
                effect_type=_STORAGE_DELETE,
                payload={"object_key": old, "order_id": attachment.order_id, "attachment_id": attachment.id},
                dedupe_key=f"attachment:{attachment.id}:{old}",
                available_at=now + ATTACHMENT_PURGE_GRACE,
                now=now,
            )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            logger.warning("[heic] rollback 실패", exc_info=True)
        if new_key:
            storage.delete_file(new_key)  # 줄이 바뀌지 않았으니 새 JPEG 는 고아 — 바로 지운다
        logger.exception("[heic] 첨부 갱신 실패 attachment=%s", attachment_id)
        return FAILED
    finally:
        if own_session:
            from db import db_session

            db.close()
            db_session.remove()

    try:
        invalidate_dashboard_families(*ATTACHMENT_DASHBOARD_FAMILIES)
    except Exception:
        logger.warning("[heic] 캐시 무효화 실패", exc_info=True)

    order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation(int(attachment_id), new_key)
    return CONVERTED


def _run_in_thread(attachment_id: int, storage_key: str) -> None:
    try:
        convert_order_attachment_heic(attachment_id, storage_key)
    except Exception:
        logger.exception("[heic] 백그라운드 변환 오류 attachment=%s", attachment_id)


def schedule_order_attachment_heic_conversion(attachment_id: int, storage_key: str) -> None:
    """변환 작업을 예약한다 — RQ 먼저, 안 되면 ThreadPool(썸네일 예약과 같은 길)."""
    if not attachment_id or not storage_key:
        return
    try:
        if enqueue_heic_conversion(attachment_id, storage_key):
            return
    except Exception:
        logger.warning("[heic] enqueue 실패 — ThreadPool 로 돌림", exc_info=True)
    try:
        _executor.submit(_run_in_thread, int(attachment_id), storage_key)
    except Exception:
        logger.exception("[heic] 예약 실패 attachment=%s", attachment_id)


def schedule_order_attachment_post_upload(attachment_id: int, storage_key: str) -> None:
    """업로드 직후 할 일 — HEIC 면 JPEG 변환(끝나면 썸네일까지), 아니면 썸네일만."""
    if is_heic_filename(storage_key):
        schedule_order_attachment_heic_conversion(attachment_id, storage_key)
        return
    order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation(attachment_id, storage_key)

