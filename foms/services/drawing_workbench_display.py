"""Display helpers for ERP drawing workbench dashboard rows."""

from __future__ import annotations

from typing import Any

from foms.api.files import build_file_download_url, build_file_view_url
from foms.services.datetime_kst import format_datetime_kst
from foms.services.drawing_confirm_cleanup import stray_drawing_rows
from foms.services.feature_flags import env_bool_or_mobile_v2
from foms.services.order_attachment_permissions import can_delete_order_attachment
from models import OrderAttachment, User

__all__ = [
    "build_stray_drawing_files",
    "drawing_thumb_enabled",
    "pick_row_thumbnail_url",
    "resolve_row_image_list",
    "resolve_row_thumbnail_url",
]

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def drawing_thumb_enabled(*, mobile_v2_active: bool = False) -> bool:
    """Return whether mobile drawing card thumbnails are enabled.

    Args:
        mobile_v2_active: ERP mobile v2 cohort active for current user.

    Returns:
        True when explicit env is truthy, or env unset and ``mobile_v2_active``.
    """
    return env_bool_or_mobile_v2(
        "FOMS_V3_DRAWING_THUMB_ENABLED",
        mobile_v2_active=mobile_v2_active,
    )


def _is_image_file(file_entry: dict[str, Any]) -> bool:
    """Return True when a drawing file entry looks like an image."""
    name = (
        (file_entry.get("filename") or file_entry.get("name") or file_entry.get("key") or "")
        .strip()
        .lower()
    )
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def _collect_image_entries(drawing_files: list[Any]) -> list[dict[str, str]]:
    """Filter ``drawing_current_files`` down to image entries with a storage key.

    Args:
        drawing_files: ``drawing_current_files`` entries from structured_data.

    Returns:
        Ordered ``{key, filename, view_url, download_url}`` dicts (URLs may be empty
        strings when the legacy entry stored no URL — the caller derives them).
    """
    entries: list[dict[str, str]] = []
    for entry in drawing_files:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("key") or "").strip()
        if not key or not _is_image_file(entry):
            continue
        entries.append(
            {
                "key": key,
                "filename": (entry.get("filename") or entry.get("name") or key.rsplit("/", 1)[-1]).strip(),
                "view_url": (entry.get("view_url") or "").strip(),
                "download_url": (entry.get("download_url") or "").strip(),
            }
        )
    return entries


def resolve_row_image_list(
    order_id: int,
    drawing_files: list[Any],
    db: Any,
    *,
    mobile_v2_active: bool = False,
) -> list[dict[str, str]]:
    """Resolve every image drawing file on a workbench row for the fullscreen viewer.

    행당 ``OrderAttachment`` 조회는 최대 1회(파일마다 재조회 금지 — sd 에 ``view_url`` 이
    전부 있으면 조회 자체가 없다).

    Args:
        order_id: Order primary key.
        drawing_files: ``drawing_current_files`` entries from structured_data.
        db: SQLAlchemy session for optional ``OrderAttachment.thumbnail_key`` lookup.
        mobile_v2_active: ERP mobile v2 cohort active for current user.

    Returns:
        Ordered ``{key, filename, view_url, download_url}`` dicts (GlobalImageViewer 형식);
        파생 썸네일이 있는 항목만 ``thumb_url`` 이 추가된다. 썸네일 비활성/이미지 0장이면 [].
    """
    if not drawing_thumb_enabled(mobile_v2_active=mobile_v2_active):
        return []

    entries = _collect_image_entries(drawing_files)
    if not entries:
        return []

    attachments_by_key: dict[str, OrderAttachment] = {}
    if any(not entry["view_url"] for entry in entries):
        attachments_by_key = {
            attachment.storage_key: attachment
            for attachment in db.query(OrderAttachment)
            .filter(
                OrderAttachment.order_id == order_id,
                OrderAttachment.storage_key.in_([entry["key"] for entry in entries]),
            )
            .all()
        }

    for entry in entries:
        key = entry["key"]
        # 저장 URL 은 믿지 않는다(SPEC §4.3.4). 위 조회 여부만 저장 URL 유무로 정하고(기존 동작),
        # 화면에 싣는 URL 은 늘 key 로 만든다.
        entry["view_url"] = build_file_view_url(key)
        entry["download_url"] = build_file_download_url(key)
        attachment = attachments_by_key.get(key)
        thumb_key = (
            (attachment.thumbnail_key or "").strip() if attachment is not None else ""
        )
        # 파생 썸네일이 있는 항목만 thumb_url 을 싣는다(공통 경로에선 키 자체가 없어 wire 증가 0).
        if thumb_key:
            entry["thumb_url"] = build_file_view_url(thumb_key)
    return entries


def pick_row_thumbnail_url(image_files: list[dict[str, str]]) -> str | None:
    """Pick the card thumbnail URL from a ``resolve_row_image_list`` result.

    Args:
        image_files: Result of :func:`resolve_row_image_list`.

    Returns:
        First image's thumbnail URL (파생 썸네일 우선), or None for an empty list.
    """
    if not image_files:
        return None
    first = image_files[0]
    return first.get("thumb_url") or first.get("view_url") or None


def resolve_row_thumbnail_url(
    order_id: int,
    drawing_files: list[Any],
    db: Any,
    *,
    mobile_v2_active: bool = False,
) -> str | None:
    """Resolve a view URL for the first image drawing file on a workbench row.

    Args:
        order_id: Order primary key.
        drawing_files: ``drawing_current_files`` entries from structured_data.
        db: SQLAlchemy session for optional ``OrderAttachment.thumbnail_key`` lookup.
        mobile_v2_active: ERP mobile v2 cohort active for current user.

    Returns:
        View URL string, or None when thumbnails are disabled or no image exists.
    """
    return pick_row_thumbnail_url(
        resolve_row_image_list(order_id, drawing_files, db, mobile_v2_active=mobile_v2_active)
    )


def build_stray_drawing_files(db: Any, order: Any, structured_data: Any, user: Any) -> list[dict[str, Any]]:
    """도면 작업실 '도면 칸에 따로 올라온 파일' 카드 행(2026-10-27, 주문 5690 사본).

    대상 판정은 :func:`foms.services.drawing_confirm_cleanup.stray_drawing_rows` 가 한다.
    지우기는 첨부 삭제 API 를 그대로 쓰므로 ``can_delete`` 도 그 API 의 권한 함수 답이다.

    Args:
        db: 활성 세션.
        order: 대상 주문.
        structured_data: 주문 ``structured_data``.
        user: 현재 사용자(없으면 지우기 버튼 없음).

    Returns:
        ``{id, filename, view_url, thumb_url, is_image, uploader, uploaded_at, can_delete}`` 목록.
    """
    rows = stray_drawing_rows(db, int(order.id), structured_data)
    if not rows:
        return []
    uploader_ids = {r.user_id for r in rows if r.user_id is not None}
    names = (
        dict(db.query(User.id, User.name).filter(User.id.in_(uploader_ids)).all())
        if uploader_ids else {}
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.storage_key or "").strip()
        thumb_key = str(row.thumbnail_key or "").strip()
        filename = row.filename or key.rsplit("/", 1)[-1] or "-"
        is_image = _is_image_file({"filename": filename, "key": key})
        out.append({
            "id": row.id,
            "filename": filename,
            "view_url": build_file_view_url(key) if key else "",
            "thumb_url": build_file_view_url(thumb_key or key) if (thumb_key or (is_image and key)) else "",
            "is_image": is_image,
            "uploader": names.get(row.user_id) or "-",
            "uploaded_at": format_datetime_kst(row.created_at, "%m/%d %H:%M") or "-",
            "can_delete": bool(user) and can_delete_order_attachment(user, order, row),
        })
    return out
