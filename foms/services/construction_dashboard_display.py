"""Display helpers for ERP construction dashboard mobile queue cards."""

from __future__ import annotations

from typing import Any

from foms.api.files import build_file_view_url
from foms.services.feature_flags import env_bool_or_mobile_v2
from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    _erp_has_media,
    self_measurement_four_checks_done,
)
from foms.services.erp_mobile_order_display import (
    product_subtitle_from_sd,
    resolve_manager_phone_for_queue,
)
from foms.services.estimate_service import build_measurement_manager_phone_map
from foms.services.production_dashboard_display import (
    _production_first_item,
    _production_spec_display,
)
from models import OrderAttachment

__all__ = [
    "construction_stage_badge_modifier",
    "construction_thumb_enabled",
    "enrich_construction_mobile_rows",
    "build_construction_preview_attachments_map",
    "build_construction_row_dtos",
]

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
_DRAWING_CATEGORIES = frozenset({"drawing"})
_MEASUREMENT_CATEGORIES = frozenset({"measurement", "measure_photo", "photo"})
_ATTACHMENT_CATEGORIES = _DRAWING_CATEGORIES | _MEASUREMENT_CATEGORIES | frozenset(
    {"construction"}
)
# Soft cap for lightbox gallery hydration (card chrome still shows 3+N via template).
# Was 4 — left siblings beyond cap unreachable in GlobalImageViewer.
_MAX_PREVIEW_COUNT = 50


def _preview_categories(*, drawing_only: bool) -> frozenset[str]:
    """Return attachment categories allowed on construction mobile card previews."""
    if drawing_only:
        return _DRAWING_CATEGORIES
    return _ATTACHMENT_CATEGORIES


def construction_thumb_enabled(*, mobile_v2_active: bool = False) -> bool:
    """Return whether construction mobile card thumbnails are enabled.

    Args:
        mobile_v2_active: ERP mobile v2 cohort active for current user.

    Returns:
        True when explicit env is truthy, or env unset and ``mobile_v2_active``.
    """
    return env_bool_or_mobile_v2(
        "FOMS_V3_CONSTRUCTION_THUMB_ENABLED",
        mobile_v2_active=mobile_v2_active,
    )


def construction_stage_badge_modifier(stage: str | None) -> str:
    """Return v1.1 stage badge CSS modifier for a construction queue row.

    Args:
        stage: Human-readable stage label (e.g. ``시공중``, ``시공완료``).

    Returns:
        Modifier suffix such as ``--construction`` or ``--completed``.
    """
    label = (stage or "").strip()
    if label == "시공완료":
        return "--completed"
    return "--construction"


def _is_image_filename(filename: str | None) -> bool:
    name = (filename or "").strip().lower()
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def _is_image_file_entry(entry: dict[str, Any]) -> bool:
    name = (
        (entry.get("filename") or entry.get("name") or entry.get("key") or "")
        .strip()
        .lower()
    )
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def _url_from_file_entry(entry: dict[str, Any]) -> str | None:
    if not isinstance(entry, dict):
        return None
    key = (entry.get("key") or "").strip()
    if not key or not _is_image_file_entry(entry):
        return None
    view_url = (entry.get("view_url") or "").strip()
    if view_url:
        return view_url
    return build_file_view_url(key)


_DRAWING_KEY_MARKERS = ("/drawing/", "/drawing_wizard/")


def _is_drawing_file_entry(entry: dict[str, Any]) -> bool:
    """True if a ``drawing_current_files`` entry points at a drawing asset.

    drawing_current_files carries no category field; transfer API accepts any
    file key, so measurement/general photos (``orders/<id>/attachments/...``)
    can leak in. The only signal is the storage-key path — drawing assets live
    under ``orders/<id>/drawing/`` or ``orders/<id>/drawing_wizard/``. Used to
    keep the construction card (drawing-only) from showing non-drawing files.

    Args:
        entry: A drawing_current_files list item.

    Returns:
        True when the entry's key or view_url path marks it as a drawing.
    """
    if not isinstance(entry, dict):
        return False
    path = f"{entry.get('key') or ''} {entry.get('view_url') or ''}".lower()
    return any(marker in path for marker in _DRAWING_KEY_MARKERS)


def _thumb_url_from_attachment(attachment: OrderAttachment) -> str | None:
    """Card thumbnail URL (prefers generated thumbnail_key)."""
    thumb_key = (attachment.thumbnail_key or "").strip()
    if thumb_key:
        return build_file_view_url(thumb_key)
    return _view_url_from_attachment(attachment)


def _view_url_from_attachment(attachment: OrderAttachment) -> str | None:
    """Full attachment view URL for lightbox zoom (original storage_key)."""
    storage_key = (attachment.storage_key or "").strip()
    if not storage_key:
        return None
    if (attachment.file_type or "").strip().lower() == "image" or _is_image_filename(
        attachment.filename
    ):
        return build_file_view_url(storage_key)
    return None


def _preview_item_from_file_entry(entry: dict[str, Any]) -> dict[str, str] | None:
    view_url = _url_from_file_entry(entry)
    if not view_url:
        return None
    label = (
        (entry.get("filename") or entry.get("name") or entry.get("key") or "도면")
        .strip()
        or "도면"
    )
    return {"thumb": view_url, "view": view_url, "label": label}


def _preview_item_from_attachment(attachment: OrderAttachment) -> dict[str, str] | None:
    view_url = _view_url_from_attachment(attachment)
    if not view_url:
        return None
    thumb_url = _thumb_url_from_attachment(attachment) or view_url
    label = (attachment.filename or "도면").strip() or "도면"
    return {"thumb": thumb_url, "view": view_url, "label": label}


def _collect_preview_items(
    row: dict[str, Any],
    db: Any,
    *,
    drawing_only: bool = False,
    preloaded_attachments: list[OrderAttachment] | None = None,
) -> list[dict[str, str]]:
    """Resolve preview items (thumb + full view) for one construction queue row.

    ``preloaded_attachments`` 제공 시 주문별 OrderAttachment 단건 조회를 생략한다
    (배치 사전조회로 N+1 제거). None이면 기존 per-row 조회 경로를 그대로 사용한다.
    """
    categories = _preview_categories(drawing_only=drawing_only)
    seen_views: set[str] = set()
    items: list[dict[str, str]] = []

    def _add(item: dict[str, str] | None) -> None:
        if not item:
            return
        view = (item.get("view") or "").strip()
        if not view or view in seen_views:
            return
        seen_views.add(view)
        items.append(
            {
                "thumb": item.get("thumb") or view,
                "view": view,
                "label": (item.get("label") or "도면").strip() or "도면",
            }
        )

    sd = row.get("structured_data") if isinstance(row.get("structured_data"), dict) else {}
    order_id = row.get("id")
    if not drawing_only or _DRAWING_CATEGORIES.intersection(categories):
        for entry in sd.get("drawing_current_files") or []:
            if drawing_only and not _is_drawing_file_entry(entry):
                continue
            _add(_preview_item_from_file_entry(entry))
            if len(items) >= _MAX_PREVIEW_COUNT:
                return items[:_MAX_PREVIEW_COUNT]

    if not order_id:
        return items[:_MAX_PREVIEW_COUNT]

    if preloaded_attachments is not None:
        attachments = preloaded_attachments
    else:
        attachments = (
            db.query(OrderAttachment)
            .filter(
                OrderAttachment.order_id == int(order_id),
                OrderAttachment.category.in_(sorted(categories)),
            )
            .order_by(OrderAttachment.created_at.asc(), OrderAttachment.id.asc())
            .all()
        )

    def _sort_key(att: OrderAttachment) -> tuple[int, Any]:
        cat = (att.category or "").strip().lower()
        if cat in _DRAWING_CATEGORIES:
            bucket = 0
        elif cat in _MEASUREMENT_CATEGORIES:
            bucket = 1
        else:
            bucket = 2
        return (bucket, att.created_at or "")

    for attachment in sorted(attachments, key=_sort_key):
        _add(_preview_item_from_attachment(attachment))
        if len(items) >= _MAX_PREVIEW_COUNT:
            break

    return items[:_MAX_PREVIEW_COUNT]


def count_preview_attachments(
    row: dict[str, Any],
    db: Any,
    *,
    drawing_only: bool = False,
    preloaded_count: int | None = None,
) -> int:
    """Count preview-eligible attachments for card +N badge (may exceed grid cap).

    ``preloaded_count`` 제공 시 주문별 COUNT 조회를 생략한다(배치 사전조회 길이 재사용).
    """
    categories = _preview_categories(drawing_only=drawing_only)
    sd = row.get("structured_data") if isinstance(row.get("structured_data"), dict) else {}
    order_id = row.get("id")
    structured_count = len(
        [
            entry
            for entry in (sd.get("drawing_current_files") or [])
            if _url_from_file_entry(entry)
            and (not drawing_only or _is_drawing_file_entry(entry))
        ]
    )
    if not order_id:
        return structured_count

    if preloaded_count is not None:
        db_count = preloaded_count
    else:
        db_count = (
            db.query(OrderAttachment)
            .filter(
                OrderAttachment.order_id == int(order_id),
                OrderAttachment.category.in_(sorted(categories)),
            )
            .count()
        )
    return max(structured_count, db_count)


def build_construction_preview_attachments_map(
    db: Any, rows: list[dict[str, Any]], *, drawing_only: bool = False
) -> dict[int, list[OrderAttachment]]:
    """페이지 행들의 미리보기 첨부를 1회 in_ 조회로 주문별 사전 그룹화(N+1 제거).

    per-row ``_collect_preview_items``/``count_preview_attachments``의 주문별
    OrderAttachment 조회를 대체한다. 카테고리 필터·created_at asc 정렬을 per-row 경로와
    동일하게 유지하므로(전역 created_at asc → 주문별 부분수열도 asc) 결과는 byte-identical.

    Args:
        db: SQLAlchemy 세션.
        rows: 현재 페이지 행 dict 리스트.
        drawing_only: 시공팀 도면 전용 미리보기 여부(카테고리 결정).

    Returns:
        dict[int, list[OrderAttachment]]: order_id -> 첨부 리스트(created_at asc).
    """
    categories = _preview_categories(drawing_only=drawing_only)
    order_ids: list[int] = []
    for row in rows or []:
        oid = row.get("id")
        if oid:
            order_ids.append(int(oid))
    out: dict[int, list[OrderAttachment]] = {oid: [] for oid in order_ids}
    if not order_ids:
        return out
    attachments = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category.in_(sorted(categories)),
        )
        .order_by(OrderAttachment.created_at.asc(), OrderAttachment.id.asc())
        .all()
    )
    for att in attachments:
        out.setdefault(int(att.order_id), []).append(att)
    return out


def enrich_construction_mobile_rows(
    rows: list[dict[str, Any]],
    db: Any,
    *,
    mobile_v2_active: bool = False,
    drawing_only: bool = False,
) -> None:
    """Attach v1.1 badge + thumbnail fields to construction ``paginated_orders`` dicts.

    Args:
        rows: Mutable list of row dicts built in ``construction.dashboard``.
        db: SQLAlchemy session for attachment lookup.
        drawing_only: When True (시공팀), show drawing-category previews only.
    """
    thumb_on = construction_thumb_enabled(mobile_v2_active=mobile_v2_active)
    # N+1 제거: 미리보기 첨부를 페이지 전체 1회 in_ 조회로 사전 그룹화(행마다 조회 X).
    preview_map = (
        build_construction_preview_attachments_map(db, rows, drawing_only=drawing_only)
        if thumb_on
        else {}
    )
    for row in rows:
        stage = row.get("stage")
        row["stage_badge_modifier"] = construction_stage_badge_modifier(
            str(stage) if stage is not None else None
        )
        row["construction_thumb_active"] = thumb_on
        row["drawing_preview_only"] = drawing_only
        if not thumb_on:
            row["thumbnail_url"] = None
            row["attachment_previews"] = []
            row["attachment_preview_items"] = []
            continue
        oid = row.get("id")
        preloaded = preview_map.get(int(oid)) if oid else None
        preview_items = _collect_preview_items(
            row, db, drawing_only=drawing_only, preloaded_attachments=preloaded
        )
        preview_urls = [item["view"] for item in preview_items]
        row["attachment_preview_items"] = preview_items
        row["attachment_previews"] = preview_urls
        row["thumbnail_url"] = preview_items[0]["thumb"] if preview_items else None
        if drawing_only:
            row["attachments_count"] = count_preview_attachments(
                row,
                db,
                drawing_only=True,
                preloaded_count=(len(preloaded) if preloaded is not None else None),
            )


def _display_stage_for_order(order, structured_data):
    stage = _erp_get_stage(order, structured_data)
    history = (structured_data.get("workflow") or {}).get("history") or []
    is_started = any(str(entry.get("note")).strip() == "시공 시작" for entry in history)
    if stage in ("CONSTRUCTION", "시공"):
        return "시공중" if is_started else "시공대기"
    if stage in ("COMPLETED", "완료", "AS_WAIT") or stage == "CS":
        return "시공완료"
    if stage == "CONSTRUCTING":
        return "시공중"
    return None


def _workmode_display_fields(structured_data: dict[str, Any]) -> tuple[str, str]:
    """v3 workmode 카드용 경량 표시 필드(품목 라벨·규격) 파생. 실패 시 ''.

    기존 SSOT 헬퍼만 재사용한다(신규 쿼리 없음, 이미 로드된 structured_data에서만 파생):
    - 품목 라벨: ``product_subtitle_from_sd`` (모바일 큐 카드 subtitle SSOT)
    - 규격 표시: ``_production_spec_display`` (생산 대시보드 첫 항목 W×D×H SSOT)

    Args:
        structured_data: 주문 structured_data(JSONB) dict. 파생 실패는 ''로 완만히 강등.

    Returns:
        (workmode_product_label, workmode_spec_display) — 각 파생 실패 시 ''.
    """
    try:
        label = product_subtitle_from_sd(structured_data) or ""
    except Exception:
        label = ""
    try:
        first_item, _ = _production_first_item(structured_data)
        spec = _production_spec_display(first_item)
    except Exception:
        spec = ""
    return label, spec


def build_construction_row_dtos(orders, att_counts, f_stage):
    """시공 대시보드 표시용 row DTO 조립 (구 erp_construction_dashboard enriched 루프). 동작 보존.

    자가실측 미완료 / 표시단계 없음 / f_stage 불일치는 기존대로 건너뛴다(verbatim).
    필터링·정렬·pagination 결정은 하지 않는다(라우트 유지).

    Args:
        orders: 표시 후보 Order 객체 리스트.
        att_counts: order_id -> 첨부 수.
        f_stage: 단계 필터('' 또는 시공대기/시공중/시공완료).

    Returns:
        list[dict]: 원본 enriched와 동일 구조.
    """
    enriched = []
    # N+1 제거: 실측담당자 연락처는 출고 설정 1회 로드로 만든 map을 행마다 재사용.
    # (이전엔 행마다 load_erp_shipment_settings 재조회 → 브라우즈 최대 300행 N+1)
    manager_phone_map = build_measurement_manager_phone_map()
    for order in orders:
        if getattr(order, "is_self_measurement", False) and not self_measurement_four_checks_done(order):
            continue
        structured_data = _ensure_dict(order.structured_data)
        display_stage = _display_stage_for_order(order, structured_data)
        if not display_stage:
            continue
        if f_stage and display_stage != f_stage:
            continue

        alerts = _erp_alerts(order, structured_data, att_counts.get(order.id, 0))
        workmode_product_label, workmode_spec_display = _workmode_display_fields(
            structured_data
        )
        enriched.append(
            {
                "id": order.id,
                "is_erp_order": order.is_erp_order,
                "is_self_measurement": getattr(order, "is_self_measurement", False),
                "structured_data": structured_data,
                "customer_name": (((structured_data.get("parties") or {}).get("customer") or {}).get("name")) or "-",
                "address": (
                    ((structured_data.get("site") or {}).get("address_full"))
                    or ((structured_data.get("site") or {}).get("address_main"))
                )
                or "-",
                "stage": display_stage,
                "alerts": alerts,
                "has_media": _erp_has_media(order, att_counts.get(order.id, 0)),
                "attachments_count": att_counts.get(order.id, 0),
                "orderer_name": (((structured_data.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
                or None,
                "owner_team": "CONSTRUCTION",
                "measurement_date": (((structured_data.get("schedule") or {}).get("measurement") or {}).get("date")),
                "construction_date": (((structured_data.get("schedule") or {}).get("construction") or {}).get("date")),
                "manager_name": (((structured_data.get("parties") or {}).get("manager") or {}).get("name")) or "-",
                "manager_phone": resolve_manager_phone_for_queue(
                    structured_data.get("parties") or {},
                    order=order,
                    manager_phone_map=manager_phone_map,
                ),
                "phone": (((structured_data.get("parties") or {}).get("customer") or {}).get("phone")) or "-",
                "as_received_date": getattr(order, "as_received_date", None) or "",
                "as_received_done": bool((getattr(order, "as_received_date", None) or "").strip()),
                # v3 workmode 카드용 표시 필드(파생만; 기존 소비자는 미읽음, ''는 미표시).
                "workmode_product_label": workmode_product_label,
                "workmode_spec_display": workmode_spec_display,
            }
        )
    return enriched
