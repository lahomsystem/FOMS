"""ERP 작업 큐 상세 preload payload helpers."""

from foms.services.erp_display import _ensure_dict
from foms.services.erp_quest_display import (
    assignee_user_ids_from_sd,
    load_assignee_user_map_batch,
    resolve_order_role_assignees,
)

__all__ = [
    "build_order_detail_payload_map",
    "attach_order_detail_payloads",
]


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
        'payment': sd.get('payment', {}),
        'payments': sd.get('payments', {}),
        'totals': sd.get('totals', {}),
        'parties': sd.get('parties', {}),
        'workflow': {
            'stage': workflow.get('stage'),
            'stage_updated_at': workflow.get('stage_updated_at'),
            'history': workflow.get('history', []),
        },
        'checklist': sd.get('checklist', {}),
        'shipment': sd.get('shipment', {}),
        'site': sd.get('site', {}),
        'quests': sd.get('quests', []),
        'assignments': sd.get('assignments', {}),
        'notes': sd.get('notes', {}),
        'flags': sd.get('flags', {}),
        'drawing_status': sd.get('drawing_status'),
        'drawing_assignees': sd.get('drawing_assignees', []),
        'drawing_current_files': sd.get('drawing_current_files', []),
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

    현재 배치는 전달받은 행의 `structured_data`만 슬림화해 preload payload를 만든다.
    `db` 인자는 호출 계약 호환성을 위해 유지한다.

    Args:
        db: SQLAlchemy 세션 (호환성 유지를 위해 전달됨)
        rows: Order ORM 인스턴스 또는 dict의 리스트

    Returns:
        dict[int, dict]: {order_id: {"success": True, "structured_data": ...}}
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

    order_by_id = {}
    for row in rows or []:
        order_id, _ = _extract_row_id_and_structured_data(row)
        if order_id and not isinstance(row, dict):
            order_by_id[order_id] = row

    user_map = load_assignee_user_map_batch(db, list(structured_map.values())) if db else {}

    return {
        order_id: {
            "success": True,
            "structured_data": _slim_structured_data(structured_map.get(order_id, {})),
            "role_assignees": resolve_order_role_assignees(
                structured_map.get(order_id, {}),
                order=order_by_id.get(order_id),
                user_map=user_map,
            ),
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
                "role_assignees": resolve_order_role_assignees(
                    structured_data,
                    order=None if isinstance(row, dict) else row,
                    user_map=load_assignee_user_map_batch(db, [structured_data]) if db else {},
                ),
            },
        )
        if isinstance(row, dict):
            row["detail_payload"] = payload
        else:
            setattr(row, "detail_payload", payload)
