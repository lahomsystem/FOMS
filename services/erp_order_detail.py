"""ERP 작업 큐 상세 preload payload helpers."""

import logging
from collections import defaultdict

from apps.api.files import build_file_download_url, build_file_view_url
from models import OrderAttachment
from services.erp_display import _ensure_dict

logger = logging.getLogger(__name__)


def _slim_structured_data(sd: dict) -> dict:
    """상세 패널에 실제 필요한 필드만 추출하여 payload 크기를 줄인다.

    Args:
        sd: Order.structured_data 전체 딕셔너리

    Returns:
        상세 패널 렌더링에 필요한 핵심 필드만 포함한 딕셔너리
    """
    workflow = sd.get('workflow') or {}
    return {
        'schedule': sd.get('schedule', {}),
        'items': sd.get('items', []),
        'parties': sd.get('parties', {}),
        'workflow': {
            'stage': workflow.get('stage'),
            'history': workflow.get('history', []),
        },
        'checklist': sd.get('checklist', {}),
        'shipment': sd.get('shipment', {}),
        'site': sd.get('site', {}),
        'quests': sd.get('quests', []),
        'assignments': sd.get('assignments', {}),
    }


def _serialize_attachment(attachment: OrderAttachment) -> dict:
    """OrderAttachment ORM 인스턴스를 JSON 직렬화 가능한 dict로 변환한다.

    Args:
        attachment: OrderAttachment ORM 인스턴스

    Returns:
        첨부파일 정보 dict
    """
    storage_key = str(attachment.storage_key or "")
    thumbnail_key = str(attachment.thumbnail_key) if attachment.thumbnail_key is not None else ""
    return {
        "id": attachment.id,
        "order_id": attachment.order_id,
        "filename": attachment.filename,
        "file_type": attachment.file_type,
        "category": attachment.category or "measurement",
        "item_index": attachment.item_index,
        "file_size": attachment.file_size,
        "storage_key": storage_key,
        "key": storage_key,
        "thumbnail_key": thumbnail_key or None,
        "view_url": build_file_view_url(storage_key) if storage_key else "",
        "download_url": build_file_download_url(storage_key) if storage_key else "",
        "thumbnail_view_url": build_file_view_url(thumbnail_key) if thumbnail_key else None,
        "created_at": attachment.created_at.strftime("%Y-%m-%d %H:%M:%S") if attachment.created_at is not None else None,
        "user_id": attachment.user_id,
    }


def _extract_row_id_and_structured_data(row):
    """row(ORM 인스턴스 또는 dict)에서 order_id와 structured_data를 추출한다.

    Args:
        row: Order ORM 인스턴스 또는 dict

    Returns:
        tuple[int | None, dict]: (order_id, structured_data)
    """
    if isinstance(row, dict):
        return row.get("id"), _ensure_dict(row.get("structured_data"))
    return getattr(row, "id", None), _ensure_dict(getattr(row, "structured_data", None))


def build_order_detail_payload_map(db, rows):
    """작업 큐 표시 행 목록에서 상세 preload payload 맵을 생성한다.

    IN 쿼리로 structured_data와 첨부파일을 일괄 조회하여 N+1 방지.

    Args:
        db: SQLAlchemy 세션
        rows: Order ORM 인스턴스 또는 dict의 리스트

    Returns:
        dict[int, dict]: {order_id: {"success": True, "structured_data": ..., "attachments": [...]}}
    """
    structured_map = {}
    order_ids = []

    for row in rows or []:
        order_id, structured_data = _extract_row_id_and_structured_data(row)
        if not order_id:
            continue
        structured_map[order_id] = structured_data
        order_ids.append(order_id)

    if not order_ids:
        return {}

    attachments_map = defaultdict(list)
    attachments = (
        db.query(OrderAttachment)
        .filter(OrderAttachment.order_id.in_(order_ids))
        .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.desc())
        .all()
    )

    for attachment in attachments:
        attachments_map[attachment.order_id].append(_serialize_attachment(attachment))

    return {
        order_id: {
            "success": True,
            "structured_data": _slim_structured_data(structured_map.get(order_id, {})),
            "attachments": attachments_map.get(order_id, []),
        }
        for order_id in order_ids
    }


def attach_order_detail_payloads(db, rows):
    """표시 행에 상세 preload payload를 직접 주입한다 (서버사이드 preload).

    Args:
        db: SQLAlchemy 세션
        rows: Order ORM 인스턴스 또는 dict의 리스트. 각 항목에 detail_payload 속성이 추가됨.

    Returns:
        None
    """
    payload_map = build_order_detail_payload_map(db, rows)
    for row in rows or []:
        order_id, structured_data = _extract_row_id_and_structured_data(row)
        payload = payload_map.get(
            order_id,
            {
                "success": True,
                "structured_data": structured_data,
                "attachments": [],
            },
        )
        if isinstance(row, dict):
            row["detail_payload"] = payload
        else:
            setattr(row, "detail_payload", payload)
