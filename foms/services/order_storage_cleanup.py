"""Storage cleanup helpers for permanently deleted orders."""

from __future__ import annotations

from typing import Any

from models import DrawingWizardPending, Order, OrderAttachment, UploadDraft, UploadTicket
from foms.services.storage import get_storage
from foms.services.error_logging import log_handled_exception

__all__ = ["delete_storage_files_for_order", "storage_targets_for_orders", "delete_storage_targets"]

VIEW_URL_PREFIX = "/api/files/view/"


def delete_storage_files_for_order(db: Any, order: Any) -> None:
    """Delete storage files linked to an order before the DB row is removed."""
    if not order:
        return

    order_id = order.id
    storage = get_storage()

    attachments = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).all()  # perf-ok: single-order attachments
    for attachment in attachments:
        try:
            if attachment.storage_key:
                storage.delete_file(attachment.storage_key)
        except Exception:
            log_handled_exception("storage cleanup delete_file")
        try:
            if attachment.thumbnail_key:
                storage.delete_file(attachment.thumbnail_key)
        except Exception:
            log_handled_exception("storage cleanup delete thumbnail")

    blueprint_url = (order.blueprint_image_url or "").strip()
    if blueprint_url.startswith(VIEW_URL_PREFIX):
        key = blueprint_url[len(VIEW_URL_PREFIX) :].lstrip("/")
        if key and ".." not in key:
            try:
                storage.delete_file(key)
            except Exception:
                log_handled_exception("storage cleanup delete blueprint")

    structured_data = order.structured_data or {}
    drawing_files = structured_data.get("drawing_current_files") or []
    for item in drawing_files:
        if not isinstance(item, dict):
            continue
        key = (item.get("key") or "").strip()
        if key and ".." not in key and f"orders/{order_id}/" in key:
            try:
                storage.delete_file(key)
            except Exception:
                log_handled_exception("storage cleanup delete structured key")


def _view_url_key(url: Any) -> str | None:
    text = (url or "").strip()
    if not text.startswith(VIEW_URL_PREFIX):
        return None
    key = text[len(VIEW_URL_PREFIX):].lstrip("/")
    return key if key and ".." not in key else None


def storage_targets_for_orders(db: Any, order_ids: list[int]) -> dict[str, list[str]]:
    """완전 삭제할 주문들의 저장소 파일 대상(키·접두어)을 모은다 — DB 행을 지우기 **전에** 부른다.

    주문 파일은 대부분 ``orders/<id>/`` 아래라 접두어로 지우고, 그 밖에 있을 수 있는 파일
    (썸네일 등)은 표에 남은 키로 지운다(SPEC 2026-10-20-purge-storage-files).

    Returns:
        ``{"keys": [...], "prefixes": [...]}`` (정렬·중복 제거).
    """
    ids = sorted({int(x) for x in order_ids})
    keys: set[str] = set()
    if not ids:
        return {"keys": [], "prefixes": []}
    for storage_key, thumbnail_key in db.query(
        OrderAttachment.storage_key, OrderAttachment.thumbnail_key
    ).filter(OrderAttachment.order_id.in_(ids)):
        keys.update(k for k in (storage_key, thumbnail_key) if k)
    for (object_key,) in db.query(UploadTicket.object_key).filter(UploadTicket.order_id.in_(ids)):
        if object_key:
            keys.add(object_key)
    for (object_key,) in db.query(DrawingWizardPending.object_key).filter(
        DrawingWizardPending.order_id.in_(ids)
    ):
        if object_key:
            keys.add(object_key)
    for (object_keys,) in db.query(UploadDraft.object_keys).filter(UploadDraft.order_id.in_(ids)):
        keys.update(k for k in (object_keys or []) if isinstance(k, str) and k)
    for blueprint_url, structured_data in db.query(
        Order.blueprint_image_url, Order.structured_data
    ).filter(Order.id.in_(ids)):
        key = _view_url_key(blueprint_url)
        if key:
            keys.add(key)
        for item in (structured_data or {}).get("drawing_current_files") or []:
            key = (item.get("key") or "").strip() if isinstance(item, dict) else ""
            if key and ".." not in key:
                keys.add(key)
    prefixes = [f"orders/{oid}/" for oid in ids]
    # 접두어로 지워질 키는 따로 세지 않는다(두 번 지우고 두 번 세는 것 방지).
    outside = sorted(k for k in keys if not k.startswith(tuple(prefixes)))
    return {"keys": outside, "prefixes": prefixes}


def delete_storage_targets(targets: dict[str, list[str]]) -> tuple[int, int]:
    """모은 대상을 지운다. 실패는 기록하고 나머지를 계속 지운다.

    Returns:
        ``(지운 파일 수, 실패 수)``. 접두어는 지운 파일 수를 더하고, 실패하면 1로 센다.
    """
    storage = get_storage()
    deleted = failed = 0
    for prefix in targets.get("prefixes") or []:
        try:
            deleted += int(storage.delete_prefix(prefix) or 0)
        except Exception:
            failed += 1
            log_handled_exception("storage cleanup delete prefix")
    for key in targets.get("keys") or []:
        try:
            if storage.delete_file(key):
                deleted += 1
            else:
                failed += 1
        except Exception:
            failed += 1
            log_handled_exception("storage cleanup delete key")
    return deleted, failed
