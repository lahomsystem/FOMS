"""Shared helpers for the legacy attachments API."""

from __future__ import annotations

from typing import Any

from foms.api.files.routes import build_file_download_url, build_file_view_url
from foms.services.attachment_sort import (
    next_attachment_sort_order,
    parse_attachment_sort_order,
)
from foms.services.files.upload_policy import ERP_MEDIA_ALLOWED_EXTENSIONS
from foms.services.order_attachment_permissions import can_delete_order_attachment
from models import OrderAttachment


DRAWING_ATTACHMENT_EXTRA_EXTENSIONS = {"pdf", "zip", "dwg", "dxf"}
ATTACHMENT_CATEGORIES = ("measurement", "drawing", "construction", "as")


def _att_key(att: OrderAttachment, key: str) -> str | None:
    """ORM 인스턴스에서 storage_key/thumbnail_key 값을 꺼낸다."""
    value = getattr(att, key, None)
    return str(value) if value is not None and value else None


def normalize_attachment_category(raw_category):
    """첨부 카테고리 정규화."""
    category = (raw_category or "measurement").strip().lower()
    if category not in ATTACHMENT_CATEGORIES:
        return None
    return category


def parse_attachment_item_index(raw_item_index):
    """제품별 첨부를 위한 item_index 파싱."""
    if raw_item_index is None:
        return True, None, None
    value = str(raw_item_index).strip().lower()
    if value in ("", "null", "none"):
        return True, None, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return False, None, "item_index는 0 이상의 정수 또는 null 이어야 합니다."
    if parsed < 0:
        return False, None, "item_index는 0 이상의 정수 또는 null 이어야 합니다."
    return True, parsed, None


def resolve_as_log_ref(order: Any, category, raw_as_log_id):
    """AS 첨부를 타임라인 기록에 결합할 ``as_log_id`` 검증 (AS-FRESH-01 T2).

    form 업로드와 direct 업로드 완료 두 경로가 공유한다 — 한쪽만 손보면 같은 파일이
    올라온 경로에 따라 결합되기도 안 되기도 한다.

    Args:
        order: 대상 ``Order``(structured_data 로 항목 존재를 확인).
        category: 정규화된 첨부 카테고리.
        raw_as_log_id: 요청이 보낸 원값(없으면 None/빈 문자열).

    Returns:
        ``(ok, as_log_id | None, 오류문구 | None)``. 값이 없으면 ``(True, None, None)``.
    """
    log_id = str(raw_as_log_id or "").strip()
    if not log_id:
        return True, None, None
    if len(log_id) > 64:
        return False, None, "as_log_id 형식이 올바르지 않습니다."
    if category != "as":
        # 결합 축은 AS 첨부 전용이다. 다른 분류에 붙으면 회차 필터·기록별 렌더가
        # 조용히 오작동한다(조용한 무시 대신 명시 거부).
        return False, None, "as_log_id 는 AS 첨부에만 지정할 수 있습니다."
    structured = getattr(order, "structured_data", None)
    entries = ((structured or {}).get("shipment") or {}).get("as_log")
    if not isinstance(entries, list):
        entries = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("deleted") is True:
            continue
        if str(entry.get("id") or "") == log_id:
            return True, log_id, None
    return False, None, "결합할 AS 기록을 찾을 수 없습니다."


def resolve_as_sort_order(db, order_id, category, as_log_id, raw):
    """업로드 요청의 sort_order 를 확정한다 (AS-SORT-01).

    AS 첨부가 값을 안 보내면 같은 기록 그룹의 max+1. 다른 분류는 NULL 유지.

    Args:
        db: 세션.
        order_id: 주문 PK.
        category: 정규화된 분류.
        as_log_id: 결합된 기록 id(없으면 None).
        raw: 요청 원값.

    Returns:
        ``(ok, sort_order|None, 오류문구|None)``.
    """
    ok, sort_order, err = parse_attachment_sort_order(raw)
    if not ok:
        return False, None, err
    if sort_order is None and category == "as":
        sort_order = next_attachment_sort_order(db, order_id, as_log_id)
    return True, sort_order, None


def allowed_erp_attachment_file(filename, category="measurement"):
    """ERP Beta 첨부 확장자 검증 (카테고리별 정책)."""
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    allowed_exts = set(ERP_MEDIA_ALLOWED_EXTENSIONS)
    if normalize_attachment_category(category) == "drawing":
        allowed_exts.update(DRAWING_ATTACHMENT_EXTRA_EXTENSIONS)
    return ext in allowed_exts


def get_erp_media_max_size(filename):
    """ERP Beta 첨부 파일 타입별 최대 크기 (바이트)."""
    if "." not in filename:
        return 10 * 1024 * 1024
    ext = filename.rsplit(".", 1)[1].lower()
    image_exts = ["jpg", "jpeg", "png", "gif", "webp"]
    video_exts = ["mp4", "mov", "avi", "mkv", "webm"]
    if ext in image_exts:
        return 20 * 1024 * 1024
    if ext in video_exts:
        return 500 * 1024 * 1024
    return 20 * 1024 * 1024


def resolve_attachment_category(folder: str, category_param):
    """Infer attachment category from explicit param or upload folder."""
    if category_param is not None:
        return normalize_attachment_category(category_param) or "measurement"
    parts = folder.split("/")
    if len(parts) >= 2 and parts[0] == "orders" and parts[1].isdigit():
        seg = parts[2] if len(parts) > 2 else "measurement"
        if seg == "drawing_gateway":
            return "drawing"
        if seg == "blueprint":
            return "measurement"
        return normalize_attachment_category(seg) or "measurement"
    return "measurement"


def serialize_attachment(
    att: OrderAttachment,
    *,
    order: Any | None = None,
    user: Any | None = None,
) -> dict:
    """Convert attachment ORM object to API payload with resolved URLs."""
    data = att.to_dict()
    data["category"] = normalize_attachment_category(data.get("category")) or "measurement"
    storage_key = _att_key(att, "storage_key")
    thumbnail_key = _att_key(att, "thumbnail_key")
    data["view_url"] = build_file_view_url(storage_key) if storage_key else ""
    data["download_url"] = build_file_download_url(storage_key) if storage_key else ""
    data["thumbnail_view_url"] = build_file_view_url(thumbnail_key) if thumbnail_key else None
    if order is not None and user is not None:
        data["can_delete"] = can_delete_order_attachment(user, order, att)
    return data


__all__ = [
    "ATTACHMENT_CATEGORIES",
    "DRAWING_ATTACHMENT_EXTRA_EXTENSIONS",
    "_att_key",
    "allowed_erp_attachment_file",
    "get_erp_media_max_size",
    "next_attachment_sort_order",
    "normalize_attachment_category",
    "parse_attachment_item_index",
    "parse_attachment_sort_order",
    "resolve_as_log_ref",
    "resolve_as_sort_order",
    "resolve_attachment_category",
    "serialize_attachment",
]
