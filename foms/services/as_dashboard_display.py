"""Display helpers for ERP AS dashboard mobile cards."""

from __future__ import annotations

from typing import Any

from foms.api.files import build_file_view_url
from foms.services.feature_flags import env_bool_or_mobile_v2
from foms.services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders
from foms.services.as_content_safety import sanitize_as_content_html
from models import OrderAttachment

__all__ = [
    "as_stage_badge_modifier",
    "as_thumb_enabled",
    "batch_resolve_as_thumbnail_urls",
    "apply_as_dashboard_row_display_fields",
]

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def as_thumb_enabled(*, mobile_v2_active: bool = False) -> bool:
    """Return whether mobile AS card thumbnails are enabled.

    Args:
        mobile_v2_active: ERP mobile v2 cohort active for current user.

    Returns:
        True when explicit env is truthy, or env unset and ``mobile_v2_active``.
    """
    return env_bool_or_mobile_v2(
        "FOMS_V3_AS_THUMB_ENABLED",
        mobile_v2_active=mobile_v2_active,
    )


def as_stage_badge_modifier(*, status: str, as_pending: bool) -> str:
    """Return v1.1 stage badge CSS modifier for an AS row.

    Args:
        status: Order status code (e.g. ``AS_RECEIVED``, ``AS_COMPLETED``).
        as_pending: Whether the row is marked pending on visit date.

    Returns:
        Modifier suffix such as ``--cs`` or ``--completed``.
    """
    if status == "AS_COMPLETED":
        return "--completed"
    return "--cs"


def _is_image_filename(filename: str | None) -> bool:
    name = (filename or "").strip().lower()
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def _attachment_image_url(attachment: OrderAttachment) -> str | None:
    thumb_key = (attachment.thumbnail_key or "").strip()
    if thumb_key:
        return build_file_view_url(thumb_key)
    storage_key = (attachment.storage_key or "").strip()
    if not storage_key:
        return None
    if (attachment.file_type or "").strip().lower() == "image" or _is_image_filename(
        attachment.filename
    ):
        return build_file_view_url(storage_key)
    return None


def batch_resolve_as_thumbnail_urls(order_ids: list[int], db: Any) -> dict[int, str | None]:
    """Resolve first AS image thumbnail URL per order id.

    Args:
        order_ids: Order primary keys on the current page.
        db: SQLAlchemy session.

    Returns:
        Mapping of order id to view URL (missing keys mean no thumbnail).
    """
    if not as_thumb_enabled() or not order_ids:
        return {}

    attachments = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == "as",
        )
        .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.asc())
        .all()
    )

    urls: dict[int, str | None] = {}
    for attachment in attachments:
        oid = int(attachment.order_id)
        if oid in urls:
            continue
        url = _attachment_image_url(attachment)
        if url:
            urls[oid] = url
    return urls


def _normalize_construction_worker_names(value):
    """Return display-ready construction worker names from legacy or ERP payloads."""
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value or '').replace('\n', ',').split(',')

    workers = []
    for item in raw_values:
        if isinstance(item, dict):
            raw_name = item.get('name') or item.get('text') or item.get('value') or ''
        else:
            raw_name = item
        name = str(raw_name or '').strip()
        if name and name not in workers:
            workers.append(name)
    return workers


def apply_as_dashboard_row_display_fields(rows, db, *, mobile_v2_active):
    """AS 대시보드 rows에 표시 필드를 in-place 보강 (구 erp_as_dashboard 표시 블록). 동작 보존.

    structured_data 정규화 + ERP 표시 필드 + AS 사진 보유/대기/도면/영업택배 플래그 +
    시공자 목록 + AS 내용 HTML(+notes 폴백) + 썸네일 + 단계 배지를 채운다. 캐시 아님.
    batch_resolve_as_thumbnail_urls / as_thumb_enabled 동작은 변경하지 않는다.

    Args:
        rows: 현재 페이지 Order 객체 리스트.
        db: SQLAlchemy 세션.
        mobile_v2_active: ERP mobile v2 cohort 활성 여부(썸네일 게이트).
    """
    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)  # type: ignore[assignment]
    apply_erp_display_fields_to_orders(rows)
    # AS 카테고리 첨부가 있는 주문 ID 집합 (버튼 색상: 있음=파란색, 없음=분홍 파스텔)
    order_ids = [r.id for r in rows]
    as_photo_order_ids = set()
    if order_ids:
        as_with_photos = db.query(OrderAttachment.order_id).filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == 'as'
        ).distinct().all()
        as_photo_order_ids = {x[0] for x in as_with_photos}
    thumb_flag = as_thumb_enabled(mobile_v2_active=mobile_v2_active)
    thumb_urls = batch_resolve_as_thumbnail_urls(order_ids, db) if order_ids else {}
    for r in rows:
        r.has_as_photos = r.id in as_photo_order_ids
        shipment = r.structured_data.get('shipment') or {}
        r.as_pending = shipment.get('as_pending') is True
        r.has_as_blueprint = shipment.get('as_blueprint') is True
        r.is_sales_delivery = shipment.get('sales_delivery') is True
        r.construction_workers = _normalize_construction_worker_names(
            shipment.get('construction_workers')
        )
        r.construction_workers_text = ', '.join(r.construction_workers)
        r.as_content_html = sanitize_as_content_html(shipment.get('as_content'))
        has_secondary_as_content = 'as_content_2' in shipment
        secondary_as_content_html = sanitize_as_content_html(shipment.get('as_content_2'))
        if not has_secondary_as_content and not secondary_as_content_html:
            secondary_as_content_html = sanitize_as_content_html(getattr(r, 'notes', '') or '')
        r.as_content_2_html = secondary_as_content_html
        r.as_thumb_enabled = thumb_flag
        r.thumbnail_url = thumb_urls.get(r.id) if thumb_flag else None
        r.stage_badge_modifier = as_stage_badge_modifier(
            status=str(r.status or ""),
            as_pending=bool(r.as_pending),
        )
