"""생산 파트 바뀐 기록 목록 API — 누를 때만 부른다(설계서 2026-11-23 §4-11 B12 · §7).

``GET /api/production/part-history?order_id=N[&part=edge][&key=<도면 장 key>][&sheet_id=<시트 신원>]``

* 한 주문의 카드 표시 이벤트(``PRODUCTION_PART_MARKED`` — 맡기 · 기본 · 완료 · 되돌리기 · 맡기 취소 · 담당 바꾸기)와 공정 칸
  이벤트(``PRODUCTION_STEP_CHECKED`` — 손 체크 · 카드 동기화)를 시각 순으로 돌려준다. 카드 담당 칸 · 작업 시트
  [바뀐 기록 보기]가 연다(요약 "박엣지에서 바뀜 14:20" 은 표시 줄 칸이 이미 들고 있다 — 이 API 는 전체 목록).
* 거르기: ``part`` = 그 파트(카드 이벤트의 ``part`` · 공정 칸 이벤트의 ``key``), ``key`` · ``sheet_id`` = 그 장의 카드
  이벤트만(둘 다 주면 어느 하나라도 맞는 것 — 판이 바뀌어도 같은 시트를 잇는다). 장을 거르면 공정 칸 이벤트는 뺀다.
* 쿼리 ≤ 2(로그인 사용자 읽기 빼고): 이벤트 ⋈ 주문(살아 있는 ERP 주문만) 1 + 이름 스냅샷(``by_name``)이 없는 옛
  이벤트의 사용자 이름 ``id IN`` 1(새 이벤트만이면 0). 날짜 탭 · PC 쿼리 상한과 무관하다(누를 때만, N+1 없음).
* 문: 생산 첫 화면을 볼 수 있는 직원(:func:`can_view_production_home`) + 주문 읽기 범위(:func:`user_can_read_order`) —
  30초 받아 오기(``part_marks_read.py``)와 같다. 읽기라 쓰기 정책 가드 · CSRF 대상이 아니다(GET).
* 같은 Blueprint(``production_part_marks``)에 라우트만 더한다 — ``foms/api/production/__init__.py`` 가 이 모듈을 import 한다.
"""

from __future__ import annotations

from typing import Any, Optional

from flask import g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.api.production.part_marks import production_part_marks_bp
from foms.services.datetime_kst import parse_datetime_utc
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.production.home_access import can_view_production_home
from foms.services.production.part_constants import PRODUCTION_PART_KEYS
from models import Order, OrderEvent, User

MARK_EVENT = "PRODUCTION_PART_MARKED"
STEP_EVENT = "PRODUCTION_STEP_CHECKED"
HISTORY_EVENT_TYPES: tuple[str, ...] = (MARK_EVENT, STEP_EVENT)
#: 한 번에 돌려주는 기록 수 상한(가장 최근 것부터 자른다 — 한 주문 장 × 파트 × 누름이라 보통 수십 줄).
HISTORY_CAP = 500


class _BadRequest(Exception):
    """질의 값이 틀렸을 때(상태 · 코드 · 글)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _fail(status: int, code: str, message: str):
    return jsonify({"success": False, "data": {"code": code}, "error": message}), status


def _parse_filters(args: Any) -> dict[str, Any]:
    """질의 → ``{order_id, part, key, sheet_id}``.

    Raises:
        _BadRequest: 주문 번호가 양의 정수가 아니거나 · 모르는 파트 · 너무 긴 key · 시트 신원.
    """
    raw = str(args.get("order_id") or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        raise _BadRequest("주문 번호가 올바르지 않아요.")
    part = str(args.get("part") or "").strip().lower() or None
    if part is not None and part not in PRODUCTION_PART_KEYS:
        raise _BadRequest("파트 값이 올바르지 않아요.")
    key = str(args.get("key") or "").strip() or None
    sheet_id = str(args.get("sheet_id") or "").strip() or None
    if (key and len(key) > 500) or (sheet_id and len(sheet_id) > 64):
        raise _BadRequest("도면 장이 올바르지 않아요.")
    return {"order_id": int(raw), "part": part, "key": key, "sheet_id": sheet_id}


def fetch_history_events(db: Any, order_id: int) -> tuple[list[OrderEvent], bool]:
    """그 주문의 카드 · 공정 칸 이벤트(시각 순) — 쿼리 1. 살아 있는 ERP 주문만(지운 주문 · 초안 밖 주문은 빈 목록).

    Returns:
        (이벤트 목록, 상한에서 잘렸는지).
    """
    rows = (
        db.query(OrderEvent)
        .join(Order, Order.id == OrderEvent.order_id)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type.in_(HISTORY_EVENT_TYPES),
                Order.active_filter(), Order.is_erp_order.is_(True))
        .order_by(OrderEvent.created_at.desc(), OrderEvent.id.desc())
        .limit(HISTORY_CAP + 1)
        .all()
    )
    truncated = len(rows) > HISTORY_CAP
    return list(reversed(rows[:HISTORY_CAP])), truncated


def _matches(event: OrderEvent, filters: dict[str, Any]) -> bool:
    payload = event.payload if isinstance(event.payload, dict) else {}
    is_mark = event.event_type == MARK_EVENT
    part = payload.get("part") if is_mark else payload.get("key")
    if filters["part"] and part != filters["part"]:
        return False
    if filters["key"] or filters["sheet_id"]:
        if not is_mark:
            return False
        hit_key = filters["key"] and payload.get("key") == filters["key"]
        hit_sheet = filters["sheet_id"] and payload.get("sheet_id") == filters["sheet_id"]
        return bool(hit_key or hit_sheet)
    return True


def _missing_names(db: Any, events: list[OrderEvent]) -> dict[int, str]:
    """이름 스냅샷이 없는 옛 이벤트의 사용자 이름 — 있을 때만 쿼리 1(``id IN``)."""
    ids = sorted({int(e.created_by_user_id) for e in events if e.created_by_user_id is not None
                  and not (isinstance(e.payload, dict) and e.payload.get("by_name"))})
    if not ids:
        return {}
    return {int(uid): (name or username) for uid, name, username in
            db.query(User.id, User.name, User.username).filter(User.id.in_(ids)).all()}


def _iso(value: Any) -> Optional[str]:
    aware = parse_datetime_utc(value) if value is not None else None
    return aware.isoformat() if aware is not None else None


def history_item(event: OrderEvent, names: dict[int, str]) -> dict[str, Any]:
    """기록 한 줄 — 화면이 "박엣지 맡음 11/23 09:10 → 김민준으로 바뀜 14:20 → 김민준 완료 15:02" 를 그린다.

    ``kind``: 카드 = take · basic · done · undo · release · takeover, 공정 칸 = ``step_on`` · ``step_off``.
    시각은 시간대 붙은 UTC ISO(화면이 KST 로 바꾼다).
    """
    payload = event.payload if isinstance(event.payload, dict) else {}
    is_mark = event.event_type == MARK_EVENT
    by_name = payload.get("by_name") or names.get(int(event.created_by_user_id or 0))
    return {
        "at": _iso(event.created_at),
        "kind": payload.get("action") if is_mark else ("step_on" if payload.get("done") else "step_off"),
        "part": payload.get("part") if is_mark else payload.get("key"),
        "drawing_key": payload.get("key") if is_mark else None,
        "sheet_id": payload.get("sheet_id") if is_mark else None,
        "from": payload.get("from") if is_mark else None,
        "to": payload.get("to") if is_mark else None,
        "by_name": by_name or None,
        "from_name": payload.get("from_name"),
        "holder_name": payload.get("holder_name"),
        "override": bool(payload.get("override")),
        "via": payload.get("via"),
        "trigger": payload.get("trigger"),
    }


@production_part_marks_bp.route("/part-history", methods=["GET"])
def api_part_history():
    """한 주문(· 파트 · 장)의 바뀐 기록 전체 — 볼 수 없는 사람 403, 질의가 틀리면 400."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "로그인이 필요해요.")
    if not can_view_production_home(user) or not user_can_read_order(user, None):
        return _fail(403, "FORBIDDEN", "생산 화면을 볼 수 있는 직원만 볼 수 있어요.")
    try:
        filters = _parse_filters(request.args)
    except _BadRequest as exc:
        return _fail(400, "BAD_REQUEST", exc.message)
    db = get_db()
    try:
        events, truncated = fetch_history_events(db, filters["order_id"])
        events = [e for e in events if _matches(e, filters)]
        names = _missing_names(db, events)
    except SQLAlchemyError:
        db.rollback()
        return _fail(500, "READ_FAILED", "기록을 받아 오지 못했어요. 잠시 뒤 다시 해 주세요.")
    data = {"order_id": filters["order_id"], "items": [history_item(e, names) for e in events],
            "truncated": truncated}
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200
