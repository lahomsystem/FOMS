"""Display helpers for ERP AS dashboard mobile cards."""

from __future__ import annotations

import datetime
from typing import Any

from foms.api.files import build_file_view_url
from foms.services.feature_flags import env_bool_or_mobile_v2
from foms.services.erp_display import (
    _ensure_dict,
    apply_erp_display_fields_to_orders,
    get_today_kst,
)
from foms.services.as_content_safety import sanitize_as_content_html
from models import OrderAttachment

__all__ = [
    "as_stage_badge_modifier",
    "as_thumb_enabled",
    "batch_resolve_as_thumbnail_urls",
    "batch_resolve_as_compare_photos",
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


def _parse_iso_date(value: Any) -> datetime.date | None:
    """Parse a ``YYYY-MM-DD`` string to a ``date`` (leniently), else return None.

    Args:
        value: 문자열/None (앞 10자를 ISO date 로 해석).

    Returns:
        파싱된 date 또는 파싱 실패/빈 값이면 None.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None


def _as_visit_dday(as_visit_date: Any, today: datetime.date) -> int | None:
    """Return integer D-day (visit - today) for a ``YYYY-MM-DD`` visit date, else None.

    Args:
        as_visit_date: AS 방문일 문자열(YYYY-MM-DD) 또는 None.
        today: 기준일(get_today_kst() 반환값, KST date).

    Returns:
        방문일까지 남은 일수(음수=지남). 방문일 미설정/파싱 실패면 None.
    """
    visit = _parse_iso_date(as_visit_date)
    if visit is None:
        return None
    return (visit - today).days


def _compare_photo_entry(attachment: OrderAttachment) -> dict[str, str] | None:
    """Return ``{thumb, full, name}`` for an image AS attachment, else None.

    썸네일 키가 있으면 그리드 <img> 용 thumb 로, 전체 이미지 view_url 은 full(뷰어)로 쓴다.
    이미지가 아니면(문서/영상) None → 대조 그리드에서 제외.

    Args:
        attachment: AS 카테고리 OrderAttachment 1건.

    Returns:
        {thumb, full, name} 매핑 또는 이미지가 아니면 None.
    """
    storage_key = (attachment.storage_key or "").strip()
    if not storage_key:
        return None
    is_image = (attachment.file_type or "").strip().lower() == "image" or _is_image_filename(
        attachment.filename
    )
    if not is_image:
        return None
    full_url = build_file_view_url(storage_key)
    thumb_key = (attachment.thumbnail_key or "").strip()
    thumb_url = build_file_view_url(thumb_key) if thumb_key else full_url
    return {"thumb": thumb_url, "full": full_url, "name": (attachment.filename or "AS 사진")}


def batch_resolve_as_compare_photos(rows, db: Any) -> dict[int, dict[str, list]]:
    """주문별 AS 전/후(before/after) 사진 리스트를 배치 해석 (태블릿 대조 표면용).

    AS 사진에는 전/후 구분 스키마가 없다(``OrderAttachment.category == 'as'`` 만 존재).
    따라서 "가능한 데이터"로 매핑한다: AS 이미지 첨부를 ``created_at`` 기준으로
    ``Order.as_completed_date`` 이전이면 '접수 시'(before), 완료일 당일/이후면 '조치 후'(after)로
    나눈다. 완료일이 없으면(미완료 건) 전량 before, after 는 빈 리스트(→ placeholder). 단일
    ``in_()`` 쿼리로 페이지 전체를 해석해 N+1 을 만들지 않는다(batch_resolve_as_thumbnail_urls 정합).

    Args:
        rows: 현재 페이지 Order 리스트(각 ``as_completed_date`` 보유).
        db: SQLAlchemy 세션.

    Returns:
        ``{order_id: {'before': [ {thumb, full, name} ], 'after': [ ... ] }}``.
    """
    order_ids = [r.id for r in rows]
    result: dict[int, dict[str, list]] = {
        oid: {"before": [], "after": []} for oid in order_ids
    }
    if not order_ids:
        return result
    completed_map = {
        r.id: _parse_iso_date(getattr(r, "as_completed_date", None)) for r in rows
    }
    attachments = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == "as",
        )
        .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.asc())
        .all()
    )
    for attachment in attachments:
        entry = _compare_photo_entry(attachment)
        if entry is None:
            continue
        bucket = result.get(int(attachment.order_id))
        if bucket is None:
            continue
        completed = completed_map.get(int(attachment.order_id))
        created = attachment.created_at.date() if attachment.created_at else None
        if completed is not None and created is not None and created >= completed:
            bucket["after"].append(entry)
        else:
            bucket["before"].append(entry)
    return result


def _as_billing_badge(billing: Any) -> str | None:
    """상태 셀 billing 배지 종류. 무상(확정 여부 무관)은 None(무배지).

    Args:
        billing: ``structured_data.shipment.as_billing`` 값(비 dict면 무상 취급).

    Returns:
        'paid' | 'paid_unconfirmed' | 'undecided' | None.
    """
    b = billing if isinstance(billing, dict) else {}
    btype = str(b.get('type') or 'free').lower()
    if btype == 'paid':
        return 'paid' if b.get('confirmed') is True else 'paid_unconfirmed'
    if btype == 'undecided':
        return 'undecided'
    return None


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
    # 태블릿 가로 대조 표면(전/후 사진)은 코호트(v2/v3)에서만 렌더 → 코호트일 때만 추가 배치 쿼리.
    compare_photos = (
        batch_resolve_as_compare_photos(rows, db)
        if (mobile_v2_active and order_ids)
        else {}
    )
    _today = get_today_kst()
    for r in rows:
        r.has_as_photos = r.id in as_photo_order_ids
        shipment = r.structured_data.get('shipment') or {}
        r.as_pending = shipment.get('as_pending') is True
        r.as_billing_badge = _as_billing_badge(shipment.get('as_billing'))
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
        r.as_visit_dday = _as_visit_dday(getattr(r, "as_visit_date", None), _today)
        # 방문 시각(태블릿 대조 표면 방문 블록용) — 이미 로드된 structured_data 재소비(신규 쿼리 0).
        # api_as_schedule 가 schedule.as_visit.time 에 저장한다(HH:MM 문자열). 없으면 빈 문자열.
        _schedule = r.structured_data.get("schedule") or {}
        _as_visit_meta = (_schedule.get("as_visit") or {}) if isinstance(_schedule, dict) else {}
        r.as_visit_time = str(_as_visit_meta.get("time") or "").strip()
        _cmp = compare_photos.get(r.id) or {"before": [], "after": []}
        r.as_before_photos = _cmp["before"]
        r.as_after_photos = _cmp["after"]
