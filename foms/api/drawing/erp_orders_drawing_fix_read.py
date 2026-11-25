"""생산 넘어간 주문의 도면 수정 — 도면별 공장 진행 · 보내기 미리 보기 읽기 API(설계서 2026-11-25 R1, D2).

``GET /api/orders/<id>/drawing/fix/progress[?sheet=<시트 id>…&pick=<바꿀 도면 key|NEW>…&mode=…&target=<key>…&retransfer=1]``

* 늘: 지금 확정 도면마다 ``{no, ident, key, factory, parts{cut:{state,name}…}, worked, line, fixing, requests}``.
* 보낼 것(``sheet`` · ``pick``)을 주면 ``plan`` = 전달 API 와 **같은 함수**(``plan_transfer_files`` · ``changed_numbers`` ·
  ``worked_warnings``)로 계산한 ``{changed, changed_line, warnings, order_made, error}`` — 마법사 [저장] 창 · 작업실 전달 창이 '바뀐
  도면' 줄과 보내기 전 확인 창을 미리 그린다(확인은 한 번 — 보낼 때 ``ack_worked``). ``pick`` 은 직접 올린 파일마다 하나(아직 안
  고른 파일은 빈 값 — 계산에서 뺀다).
* 쿼리 = 주문 1 + 표시 1(생산 · 시공 단계만 — 그 밖 단계는 표시를 읽지 않는다). 쓰기 없음 — 정책 매니페스트 등재 대상이 아니다.
* 문: 로그인(``g.current_user`` — before_request 가 비활성 · 끊긴 세션은 이미 비웠다, 401) + 도면 작업 참여자(지정 담당 ·
  도면팀 · 관리자 — 작업실 · 마법사 저장과 같은 술어, 403).
* 같은 Blueprint(``erp_orders_drawing``)에 라우트만 더한다 — ``foms/api/drawing/__init__.py`` 가 이 모듈을 import 한다.
"""

from __future__ import annotations

from typing import Any

from flask import g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.api.drawing.erp_orders_drawing import erp_orders_drawing_bp
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.drawing_fix_progress import drawings_progress, order_made_warning, worked_warnings
from foms.services.erp_display import _ensure_dict
from foms.services.erp_policy import is_drawing_workbench_participant
from foms.services.orders.confirm_drawing_gate import effective_drawing_status
from foms.services.orders.drawing_fix_transfer import STAGE_CONSTRUCTION, STAGE_PRODUCTION, load_marks
from foms.services.orders.drawing_transfer import (
    clean_sheet_id,
    is_drawing_hotfix_stage,
    materialize_pending_snapshot,
    order_by_wizard_sheets,
)
from foms.services.orders.drawing_transfer_plan import (
    NEW_TARGET,
    changed_line,
    changed_numbers,
    changed_old_entries,
    is_manual_file,
    plan_transfer_files,
)
from foms.services.orders.state_axes import read_main_stage
from models import Order

_PREVIEW = "__preview__/"
_LIST_CAP = 60


def _fail(status: int, code: str, message: str):
    return jsonify({"success": False, "data": {"code": code}, "error": message}), status


def _arg_list(name: str) -> list[str]:
    return [str(v).strip() for v in request.args.getlist(name)[:_LIST_CAP]]


def _preview_files(order: Order, sd: dict[str, Any], sheets: list[str], picks: list[str]) -> tuple[list, dict]:
    """보낼 것 → 전달 API 가 받을 파일 꼴(대기함에 있는 시트는 그 그림 key, 아직 없는 시트 · 직접 올린 파일은 자리 key)."""
    pending = {p["sheet_id"]: p for p in materialize_pending_snapshot(order)}
    files = []
    for sid in dict.fromkeys(s for s in (clean_sheet_id(x) for x in sheets) if s):
        entry = pending.get(sid)
        files.append({"key": entry["key"] if entry else f"{_PREVIEW}{sid}", "sheet_id": sid})
    chosen = {}
    for i, pick in enumerate(picks):
        if pick:
            key = f"{_PREVIEW}file{i}"
            files.append({"key": key})
            chosen[key] = pick if pick == NEW_TARGET else pick[:500]
    return order_by_wizard_sheets(files, sd), chosen


def _plan(order: Order, sd: dict[str, Any], marks: list[Any], hotfix: bool) -> dict[str, Any]:
    """보내기 미리 보기 — 전달 API 와 같은 자리 계산 · 같은 경고."""
    new_files, picks = _preview_files(order, sd, _arg_list("sheet"), _arg_list("pick"))
    old_files = list(sd.get("drawing_current_files") or [])
    plan = plan_transfer_files(
        old_files, new_files, sd, drawing_status=effective_drawing_status(sd, default="PENDING"), hotfix=hotfix,
        mode=str(request.args.get("mode") or ""), replace_target_keys=_arg_list("target"),
        is_retransfer=request.args.get("retransfer") == "1", picks=picks if hotfix else None)
    if plan.error:
        return {"error": plan.error, "changed": None, "changed_line": "", "warnings": [], "order_made": False,
                "sheet_taken": []}
    changed = changed_numbers(old_files, plan.updated_files, plan.pairs)
    stage = read_main_stage(order)
    warnings: list[dict[str, Any]] = []
    if stage == STAGE_CONSTRUCTION:
        warnings = order_made_warning()
    elif stage == STAGE_PRODUCTION:
        warnings = worked_warnings(sd, marks, changed_old_entries(old_files, plan.updated_files))
    return {"error": None, "changed": changed, "changed_line": changed_line(changed), "warnings": warnings,
            "order_made": stage == STAGE_CONSTRUCTION, "sheet_taken": _sheet_taken(sd, old_files, new_files, hotfix)}


def _sheet_taken(sd: dict[str, Any], old_files: list, new_files: list, hotfix: bool) -> list[str]:
    """이번 시트 파일만으로 바뀌거나 빠지는 옛 도면 key — 파일 고르기가 그 도면 단추를 끈다(고르면 서버 400 PICK_TARGET, 셋째 판 4).

    마법사에서 지운 시트의 옛 판(빠짐)도 들어간다. 직접 올린 파일은 빼고 같은 함수로 다시 계산한다(쿼리 0).
    """
    sheets_only = [f for f in new_files if not is_manual_file(f)]
    plan = plan_transfer_files(old_files, sheets_only, sd, drawing_status=effective_drawing_status(sd, default="PENDING"),
                               hotfix=hotfix, mode=str(request.args.get("mode") or ""), replace_target_keys=_arg_list("target"),
                               is_retransfer=request.args.get("retransfer") == "1", picks={} if hotfix else None)
    if plan.error or not sheets_only:
        return []
    return [str(f.get("key") or "") for _no, f in changed_old_entries(old_files, plan.updated_files)]


@erp_orders_drawing_bp.route("/<int:order_id>/drawing/fix/progress", methods=["GET"])
def api_drawing_fix_progress(order_id: int):
    """도면별 공장 진행(+ 보낼 것을 주면 미리 보기) — 로그인 안 됨 401, 볼 수 없는 사람 403, 없는 주문 404."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "다시 로그인해 주세요.")
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True)).first()
        if order is None:
            return _fail(404, "NOT_FOUND", "주문을 찾을 수 없어요.")
        if not is_drawing_workbench_participant(user, order):
            return _fail(403, "FORBIDDEN", "도면팀이나 관리자만 볼 수 있어요.")
        sd = _ensure_dict(order.structured_data)
        hotfix = is_drawing_hotfix_stage(order)
        marks = load_marks(db, order.id) if hotfix else []
        data: dict[str, Any] = {"order_id": order.id, "hotfix": hotfix, "stage": read_main_stage(order),
                                "drawings": drawings_progress(sd, marks, resolve_final_drawing_files(sd))}
        if "sheet" in request.args or "pick" in request.args:
            data["plan"] = _plan(order, sd, marks, hotfix)
    except SQLAlchemyError:
        db.rollback()
        return _fail(500, "READ_FAILED", "진행을 받아 오지 못했어요. 잠시 뒤 다시 해 주세요.")
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200


__all__ = ["api_drawing_fix_progress"]
