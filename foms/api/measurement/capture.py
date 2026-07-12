"""B2 실측 캡처 mutation handler (`foms.api.measurement.capture`).

`POST /api/erp/measurement/capture/<int:order_id>` — `sd['measurement']['dims']`
및 `sd['measurement']['note']`를 부분 갱신한다. 사진 첨부는 기존 멀티파트
`POST /api/orders/<id>/attachments`(category=measurement)를 그대로 재사용하므로
여기서는 다루지 않는다.

**spec_rows·items[]·출고가 등 금액 SSOT는 무터치** — 오직 `sd['measurement']` 노드만
기록한다(신설). JSONB 쓰기는 copy.deepcopy + flag_modified 패턴을 따른다.
"""

from __future__ import annotations

import copy
import datetime
import logging
from typing import Any, Optional, Tuple

from flask import jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, User

logger = logging.getLogger(__name__)

_DIM_KEYS = ("w", "d", "h")
_DIM_MIN = 0
_DIM_MAX = 10000
_NOTE_MAX = 2000


def _validate_dims(raw: Any) -> Tuple[Optional[dict], Optional[str]]:
    """dims 페이로드 검증 → ({w,d,h}, error).

    각 값은 int(mm)이고 0 < v < 10000 이어야 한다. 세 값(w,d,h) 모두 필요하며,
    error가 not None이면 400.
    """
    if not isinstance(raw, dict):
        return None, "치수 형식이 올바르지 않습니다."
    dims: dict = {}
    for key in _DIM_KEYS:
        value = raw.get(key)
        # bool은 int의 하위형이라 명시 배제(True/False를 치수로 오인 금지).
        if isinstance(value, bool) or not isinstance(value, int):
            return None, f"치수({key})는 정수(mm)여야 합니다."
        if not (_DIM_MIN < value < _DIM_MAX):
            return None, f"치수({key})는 0 초과 10000 미만이어야 합니다."
        dims[key] = value
    return dims, None


def _resolve_by_name(db: Any, user_id: Optional[int]) -> str:
    """세션 사용자 표시명(없으면 username, 그래도 없으면 SYSTEM)."""
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user and getattr(user, "name", None):
        return user.name
    return session.get("username") or "SYSTEM"


def save_measurement_capture(order_id: int) -> Any:
    """실측 치수/특이사항을 `sd['measurement']`에 부분 갱신한다.

    Body: `{dims?: {w,d,h(int mm)}, note?: str}`. dims·note 중 최소 하나는 필요.
    spec_rows·items[]는 건드리지 않는다. OrderEvent(MEASUREMENT_DIMS_SAVED) 기록.
    반환: `{success, data:{measurement}}` 또는 오류 `{success:false, error}`.
    """
    db = get_db()
    data = request.get_json(silent=True) or {}
    has_dims = data.get("dims") is not None
    has_note = "note" in data
    if not has_dims and not has_note:
        return jsonify({"success": False, "error": "저장할 치수 또는 특이사항이 없습니다."}), 400

    dims: Optional[dict] = None
    if has_dims:
        dims, err = _validate_dims(data.get("dims"))
        if err:
            return jsonify({"success": False, "error": err}), 400

    note: Optional[str] = None
    if has_note:
        raw_note = data.get("note")
        raw_note = "" if raw_note is None else raw_note
        if not isinstance(raw_note, str):
            return jsonify({"success": False, "error": "특이사항 형식이 올바르지 않습니다."}), 400
        note = raw_note.strip()[:_NOTE_MAX]

    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        sd = copy.deepcopy(order.structured_data) if isinstance(order.structured_data, dict) else {}
        # spec_rows·items[]·출고가 등 금액 SSOT는 무터치 — measurement 노드만 기록한다.
        measurement = sd.get("measurement") if isinstance(sd.get("measurement"), dict) else {}
        user_id = session.get("user_id")

        if dims is not None:
            measurement["dims"] = {
                "w": dims["w"],
                "d": dims["d"],
                "h": dims["h"],
                "noted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "by_name": _resolve_by_name(db, user_id),
            }
        if note is not None:
            measurement["note"] = note

        sd["measurement"] = measurement
        order.structured_data = sd
        flag_modified(order, "structured_data")

        db.add(
            OrderEvent(
                order_id=order.id,
                event_type="MEASUREMENT_DIMS_SAVED",
                payload={
                    "has_dims": dims is not None,
                    "note_len": len(note) if note is not None else 0,
                },
                created_by_user_id=user_id,
            )
        )
        db.commit()

        return jsonify({"success": True, "data": {"measurement": sd["measurement"]}})
    except Exception as exc:  # noqa: BLE001 - 상위에서 롤백 후 500 반환
        db.rollback()
        logger.exception("[MEASUREMENT] capture 저장 오류: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


__all__ = ["save_measurement_capture"]
