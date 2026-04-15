"""Shared helpers for the legacy attachments API."""

from __future__ import annotations

from foms.api.files import build_file_download_url, build_file_view_url
from foms.services.files.upload_policy import ERP_MEDIA_ALLOWED_EXTENSIONS
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


def serialize_attachment(att: OrderAttachment) -> dict:
    """Convert attachment ORM object to API payload with resolved URLs."""
    data = att.to_dict()
    data["category"] = normalize_attachment_category(data.get("category")) or "measurement"
    storage_key = _att_key(att, "storage_key")
    thumbnail_key = _att_key(att, "thumbnail_key")
    data["view_url"] = build_file_view_url(storage_key) if storage_key else ""
    data["download_url"] = build_file_download_url(storage_key) if storage_key else ""
    data["thumbnail_view_url"] = build_file_view_url(thumbnail_key) if thumbnail_key else None
    return data


__all__ = [
    "ATTACHMENT_CATEGORIES",
    "DRAWING_ATTACHMENT_EXTRA_EXTENSIONS",
    "_att_key",
    "allowed_erp_attachment_file",
    "get_erp_media_max_size",
    "normalize_attachment_category",
    "parse_attachment_item_index",
    "resolve_attachment_category",
    "serialize_attachment",
]
