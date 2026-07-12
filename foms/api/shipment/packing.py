"""ERP 출고 패킹 체크리스트 API. (B6)

스키마: ``sd['shipment']['packing']`` =
``{items:[{key, label, qty, checked, at, by_name}], updated_at}``.

최초 GET 시 저장된 packing이 없으면 ``sd['items']``에서 파생한다(제품별
"본체 패널 / 도어 / 철물" 3항). 파생 결과는 읽기 시 메모리에만 존재하며,
실제 저장은 첫 POST 때 이뤄진다(JSONB 오염 방지).

JSONB 쓰기는 ``copy.deepcopy`` + ``flag_modified`` + ``db.commit()`` 규약을 따르고,
저장 시 OrderEvent ``PACKING_UPDATED``를 남긴다.
"""

from __future__ import annotations

import copy
import datetime
import logging
from functools import wraps
from typing import Any, Callable

from flask import jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.api.shipment.settings import erp_shipment_bp
from foms.web.auth import get_user_by_id
from models import Order, OrderEvent

logger = logging.getLogger(__name__)

# 통합 후보: 아래 팀 권한은 향후 erp_permissions.py의 표준 헬퍼/데코레이터로
# 승격할 예정이다. B6 범위에서는 erp_permissions.py를 무터치로 두고 출고 패킹
# 전용 로컬 데코레이터로만 유지한다.
_PACKING_EDIT_ALLOWED_TEAMS = ("CS", "SALES", "SHIPMENT", "CONSTRUCTION")

# 파생 기본 항목: (key 접미사, 라벨 접미사).
_DERIVED_PART_SUFFIXES = (
    ("body", "본체 패널"),
    ("door", "도어"),
    ("hardware", "철물"),
)


def _can_edit_packing(user: Any) -> bool:
    """출고 패킹 체크리스트를 수정할 수 있는 사용자인지 판정한다.

    Args:
        user: 현재 사용자(``None`` 허용).

    Returns:
        ADMIN 또는 team이 CS/SALES/SHIPMENT/CONSTRUCTION이면 ``True``.
    """
    if not user:
        return False
    if (getattr(user, "role", None) or "").strip().upper() == "ADMIN":
        return True
    return (getattr(user, "team", None) or "").strip().upper() in _PACKING_EDIT_ALLOWED_TEAMS


def _packing_edit_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """출고 패킹 read/write 권한 데코레이터(모듈 로컬 — 통합 후보).

    로그인 세션이 없으면 401, 권한 팀이 아니면 403 JSON을 반환한다.
    """

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user = get_user_by_id(session.get("user_id"))
        if not user:
            return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401
        if not _can_edit_packing(user):
            return jsonify({"success": False, "error": "출고 패킹 수정 권한이 없습니다."}), 403
        return f(*args, **kwargs)

    return wrapped


def _derive_packing_items(sd: dict[str, Any]) -> list[dict[str, Any]]:
    """``sd['items']``에서 기본 패킹 항목을 파생한다(제품별 3항).

    Args:
        sd: 주문 structured_data.

    Returns:
        제품마다 "본체 패널 / 도어 / 철물" 3개 행을 담은 리스트. items가
        없으면 빈 리스트.
    """
    items = sd.get("items")
    derived: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return derived
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = (item.get("product_name") or item.get("name") or "").strip() or f"제품 {idx + 1}"
        for suffix_key, suffix_label in _DERIVED_PART_SUFFIXES:
            derived.append(
                {
                    "key": f"item{idx}_{suffix_key}",
                    "label": f"{name} {suffix_label}",
                    "qty": 1,
                    "checked": False,
                    "at": None,
                    "by_name": None,
                }
            )
    return derived


def _load_packing_items(sd: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """저장된 패킹 items를 반환한다. 없으면 파생(저장 안 함).

    Returns:
        ``(items, persisted)`` — persisted가 ``False``면 파생 결과.
    """
    shipment = sd.get("shipment")
    if isinstance(shipment, dict):
        packing = shipment.get("packing")
        if isinstance(packing, dict) and isinstance(packing.get("items"), list):
            return packing["items"], True
    return _derive_packing_items(sd), False


def _packing_payload(items: list[dict[str, Any]], persisted: bool) -> dict[str, Any]:
    """API 응답 data 블록을 구성한다."""
    checked = sum(1 for it in items if isinstance(it, dict) and it.get("checked"))
    return {
        "items": items,
        "checked_count": checked,
        "total": len(items),
        "persisted": persisted,
    }


@erp_shipment_bp.route("/api/erp/shipment/packing/<int:order_id>", methods=["GET"])
@_packing_edit_required
def api_shipment_packing_get(order_id: int):
    """출고 패킹 체크리스트 조회(없으면 items[]에서 파생, 저장하지 않음)."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    items, persisted = _load_packing_items(sd)
    return jsonify({"success": True, "data": _packing_payload(items, persisted)})


@erp_shipment_bp.route("/api/erp/shipment/packing/<int:order_id>", methods=["POST"])
@_packing_edit_required
def api_shipment_packing_save(order_id: int):
    """패킹 체크 상태 갱신 및 항목 추가(JSONB 저장 + OrderEvent 기록)."""
    updates = None
    add = None
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates")
    add = payload.get("add")
    if updates is None and add is None:
        return jsonify({"success": False, "error": "updates 또는 add가 필요합니다."}), 400
    if updates is not None and not isinstance(updates, list):
        return jsonify({"success": False, "error": "updates는 배열이어야 합니다."}), 400
    if add is not None and not isinstance(add, dict):
        return jsonify({"success": False, "error": "add는 객체여야 합니다."}), 400

    add_label = ""
    add_qty = 1
    if add is not None:
        add_label = str(add.get("label") or "").strip()
        if not add_label:
            return jsonify({"success": False, "error": "추가 항목 label이 필요합니다."}), 400
        try:
            add_qty = int(add.get("qty") or 1)
        except (TypeError, ValueError):
            add_qty = 1
        if add_qty <= 0:
            add_qty = 1

    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

    user = get_user_by_id(session.get("user_id"))
    by_name = (getattr(user, "name", None) or getattr(user, "username", None) or "").strip()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        sd = copy.deepcopy(order.structured_data if isinstance(order.structured_data, dict) else {})
        shipment = sd.get("shipment")
        if not isinstance(shipment, dict):
            shipment = {}
            sd["shipment"] = shipment
        packing = shipment.get("packing")
        if not isinstance(packing, dict) or not isinstance(packing.get("items"), list):
            packing = {"items": _derive_packing_items(sd), "updated_at": None}
            shipment["packing"] = packing
        items = packing["items"]
        by_key = {it.get("key"): it for it in items if isinstance(it, dict)}

        for upd in updates or []:
            if not isinstance(upd, dict):
                continue
            row = by_key.get(upd.get("key"))
            if row is None:
                continue
            checked = bool(upd.get("checked"))
            row["checked"] = checked
            row["at"] = now_iso if checked else None
            row["by_name"] = by_name if checked else None

        if add_label:
            new_key = f"custom_{int(datetime.datetime.now().timestamp() * 1000)}_{len(items)}"
            items.append(
                {
                    "key": new_key,
                    "label": add_label,
                    "qty": add_qty,
                    "checked": False,
                    "at": None,
                    "by_name": None,
                }
            )

        packing["updated_at"] = now_iso
        checked_count = sum(1 for it in items if it.get("checked"))
        total = len(items)

        order.structured_data = sd
        flag_modified(order, "structured_data")
        db.add(
            OrderEvent(
                order_id=order.id,
                event_type="PACKING_UPDATED",
                payload={"checked_count": checked_count, "total": total},
                created_by_user_id=getattr(user, "id", None),
            )
        )
        db.commit()
        return jsonify({"success": True, "data": _packing_payload(items, True)})
    except Exception as exc:
        db.rollback()
        logger.exception("[SHIPMENT_PACKING] save error: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500
