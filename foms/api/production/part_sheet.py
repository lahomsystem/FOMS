"""PC 공정 칸 → 도면 목록 창 읽기 API — 창을 열 때만 부른다(사장님 2026-11-24 "PC 에서도 도면별로 체크").

``GET /api/production/part-sheet?order_id=N&part=cut``

* 한 주문 · 한 파트의 확정 도면 장마다 상태 · 담당(맡은 때) · 완료한 사람(때) · 바뀐 기록 · 막힘 글
  (:func:`foms.services.production.pc_sheet.build_part_sheet`) + 그 줄의 PC 공정 칸 · 상태 칸 HTML(첫 화면과 같은 매크로
  ``pc_steps`` · ``pc_status`` — 체크한 뒤 화면이 그 줄 칸만 바꿔 끼운다) + 반장 손 체크 확인 창 자료(``sheets`` · ``parts`` —
  공정 API GET 과 같은 :func:`step_api_extras`). 바뀐 기록 목록은 있는 ``GET /api/production/part-history`` 가 준다.
* 쓰기는 없다 — 화면은 있는 쓰기 길(``POST /api/production/part-marks`` · ``POST /api/orders/<id>/production/steps``)만 쓴다.
  ``can_write`` = 남의 장을 대신 처리할 수 있는 사람(:func:`can_override_marks` — 관리자 · 반장). 화면은 [고치기] 켬일 때만 단추를 그린다.
* 쿼리 3(로그인 사용자 읽기 빼고): 주문 1 + 표시 줄(네 파트) 1 + 지금 회차 1. 날짜 탭 · PC 쿼리 상한과 무관(누를 때만).
* 문: 생산 첫 화면을 볼 수 있는 직원 + 주문 읽기 범위 — 바뀐 기록 API(``part_history.py``)와 같다. GET 이라 CSRF · 정책 가드 밖.
* 같은 Blueprint(``production_part_marks``)에 라우트만 더한다 — ``foms/api/production/__init__.py`` 가 이 모듈을 import 한다.
"""

from __future__ import annotations

from typing import Any

from flask import g, get_template_attribute, jsonify, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.api.production.part_marks import production_part_marks_bp
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.home_access import can_view_production_home
from foms.services.production.part_access import can_override_marks
from foms.services.production.part_constants import PRODUCTION_PART_KEYS
from foms.services.production.part_marks_query import order_marks
from foms.services.production.part_progress import step_api_extras
from foms.services.production.pc_sheet import build_part_sheet
from foms.services.production.pc_view import pc_row_view
from foms.services.production_read_model import fetch_production_current_run_starts
from models import Order

#: 첫 화면 PC 줄 매크로 파일 — 공정 칸(``pc_steps``) · 상태 칸(``pc_status``)을 같은 매크로로 그린다.
PC_MACROS = "production/partials/home_pc_macros.html"


def _fail(status: int, code: str, message: str):
    return jsonify({"success": False, "data": {"code": code}, "error": message}), status


def _parse(args: Any) -> tuple[int, str] | None:
    """질의 → (주문 id, 파트). 틀리면 None."""
    raw = str(args.get("order_id") or "").strip()
    part = str(args.get("part") or "").strip().lower()
    if not raw.isdigit() or int(raw) <= 0 or part not in PRODUCTION_PART_KEYS:
        return None
    return int(raw), part


def _customer(order: Order, sd: dict[str, Any]) -> str:
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    return str(customer.get("name") or order.customer_name or "-")


def _row_html(order: Order, sd: dict[str, Any], marks: list[Any], starts: dict[int, Any]) -> dict[str, Any]:
    """그 줄의 PC 공정 칸 · 상태 칸 HTML 과 늦음 표(생산 단계가 아니면 비운다 — 화면은 칸을 그대로 둔다)."""
    if read_main_stage(order) != "PRODUCTION":
        return {"cells_html": None, "status_html": None, "late": None}
    row = pc_row_view(int(order.id), sd, order.erp_construction_date, marks, starts.get(int(order.id)),
                      int(order.id) in starts, get_today_kst())
    return {"cells_html": str(get_template_attribute(PC_MACROS, "pc_steps")(row)),
            "status_html": str(get_template_attribute(PC_MACROS, "pc_status")(row)),
            "late": (row.get("pc_late") or {}).get("level")}


@production_part_marks_bp.route("/part-sheet", methods=["GET"])
def api_part_sheet():
    """한 주문 · 한 파트의 도면 목록(창 자료) — 볼 수 없는 사람 403, 질의가 틀리면 400, 없는 주문 404."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "로그인이 필요해요.")
    if not can_view_production_home(user) or not user_can_read_order(user, None):
        return _fail(403, "FORBIDDEN", "생산 화면을 볼 수 있는 직원만 볼 수 있어요.")
    parsed = _parse(request.args)
    if parsed is None:
        return _fail(400, "BAD_REQUEST", "주문 번호나 파트 값이 올바르지 않아요.")
    order_id, part = parsed
    db = get_db()
    try:
        order = (db.query(Order).filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True))
                 .first())
        if order is None:
            return _fail(404, "NOT_FOUND", "주문을 찾을 수 없어요.")
        marks = order_marks(db, order_id)
        starts = fetch_production_current_run_starts(db, [order])
    except SQLAlchemyError:
        db.rollback()
        return _fail(500, "READ_FAILED", "도면 목록을 받아 오지 못했어요. 잠시 뒤 다시 해 주세요.")
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    hold = production.get("hold") if isinstance(production.get("hold"), dict) else {}
    sheet = build_part_sheet(sd, marks, part, hold_active=bool(hold.get("active")))
    for row in sheet["rows"]:
        row["thumb"] = (url_for("erp_production_page.erp_production_part_thumb", order_id=order_id, key=row["key"])
                        if row["image"] else None)
    data = {"order_id": order_id, "customer_name": _customer(order, sd), "can_write": can_override_marks(user),
            **sheet, **step_api_extras(sd, marks), **_row_html(order, sd, marks, starts)}
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200
