"""
ERP 주문 생산(제작) API. (Phase 4-5f)
erp.py에서 분리: production/start, production/complete, production/steps.
"""

import copy
import datetime
from foms.services.datetime_kst import now_utc_naive
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required
from db import get_db
from models import Order, OrderEvent, SecurityLog
from foms.services.erp_display import _ensure_dict
from foms.services.erp_permissions import erp_edit_required
from foms.services.erp_sync_columns import sync_erp_flat_columns

erp_orders_production_bp = Blueprint("erp_orders_production", __name__, url_prefix="/api/orders")


# --- 생산 공정 스텝 권한/스키마 (erp_permissions 통합 후보) --------------------------
# 아래 _can_edit_production_steps / _production_steps_edit_required 는
# erp_permissions.erp_construction_edit_required 스타일을 모듈 로컬로 복제한 것이다.
# 생산 공정 스텝 체크는 ADMIN 또는 team∈(CS,SALES,PRODUCTION) 에게 허용한다.
# 안정화되면 erp_permissions.py 의 can_edit_* / *_edit_required 계열로 승격(통합) 검토.
_PRODUCTION_STEPS_EDIT_TEAMS = ("CS", "SALES", "PRODUCTION")

# 생산 공정 기본 5단계(cut/edge/paint/assemble/inspect). 최초 접근 시 서버가 생성한다.
_PRODUCTION_STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("cut", "재단"),
    ("edge", "엣지"),
    ("paint", "도장"),
    ("assemble", "조립"),
    ("inspect", "검수"),
)
_PRODUCTION_STEP_KEYS = frozenset(k for k, _ in _PRODUCTION_STEP_DEFS)

# 생산 불량 보고 사유 화이트리스트(시트 칩과 1:1)과 이력 캡(최근 20건 유지).
_PRODUCTION_DEFECT_REASONS = ("자재 불량", "가공 오류", "파손", "기타")
_PRODUCTION_DEFECTS_CAP = 20

# 보류 이력(hold_history) 캡 — 완료 후에도 보존되는 해제된 보류 기록(최근 20건 유지).
_PRODUCTION_HOLD_HISTORY_CAP = 20


def _can_edit_production_steps(user: Any) -> bool:
    """생산 공정 스텝 편집 가능 여부(ADMIN 또는 CS/SALES/PRODUCTION 팀)."""
    if not user:
        return False
    if user.role == "ADMIN":
        return True
    return (user.team or "").strip() in _PRODUCTION_STEPS_EDIT_TEAMS


def _production_steps_edit_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """생산 공정 스텝 write 권한 데코레이터(모듈 로컬; erp_permissions 통합 후보)."""

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user = get_user_by_id(session.get("user_id"))
        if not user:
            return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401
        if _can_edit_production_steps(user):
            return f(*args, **kwargs)
        return (
            jsonify(
                {
                    "success": False,
                    "error": "공정 스텝 수정 권한이 없습니다. (관리자, 라홈팀, 영업팀 또는 생산팀만 가능)",
                }
            ),
            403,
        )

    return wrapped


def _ensure_production_steps(sd: dict[str, Any]) -> list[dict[str, Any]]:
    """sd['production']['steps'] 를 보장한다(없으면 기본 5단계 미체크로 생성) 후 반환.

    :param sd: 수정 대상 structured_data (deepcopy 된 사본이어야 한다).
    :return: 공정 스텝 리스트(sd 내부 참조와 동일 객체).
    """
    production = sd.get("production")
    if not isinstance(production, dict):
        production = {}
        sd["production"] = production
    steps = production.get("steps")
    if not isinstance(steps, list) or not steps:
        steps = [
            {"key": key, "label": label, "done": False, "at": None, "by_name": None}
            for key, label in _PRODUCTION_STEP_DEFS
        ]
        production["steps"] = steps
    return steps


def _append_hold_history(production: dict[str, Any], released_by: str | None) -> None:
    """보류 해제 직전, active hold 를 hold_history 에 보존한다(완료 후 이력 소실 방지).

    보류 해제 2경로(hold API 직접 해제 · 전이 게이트 release)가 공유한다. 호출 시점의
    ``production['hold']`` 가 active 면 ``{reason, at(보류 시작), released_at(now),
    released_by}`` 를 ``production['hold_history']`` 리스트에 append 하고 최근
    ``_PRODUCTION_HOLD_HISTORY_CAP`` 건만 유지한다. active 가 아니면 아무것도 하지
    않는다(빈 해제·중복 append 방지). 호출부가 이 함수 뒤에 hold 를 초기화한다.

    :param production: ``sd['production']`` dict(호출부의 deepcopy 작업 사본 내부 참조).
    :param released_by: 해제자 이름(``user.name`` 또는 None).
    """
    hold = production.get("hold")
    if not (isinstance(hold, dict) and hold.get("active")):
        return
    history = production.get("hold_history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "reason": hold.get("reason") or "",
            "at": hold.get("at"),
            "released_at": now_utc_naive().isoformat(),
            "released_by": released_by,
        }
    )
    if len(history) > _PRODUCTION_HOLD_HISTORY_CAP:
        history = history[-_PRODUCTION_HOLD_HISTORY_CAP:]
    production["hold_history"] = history


def _apply_production_hold_gate(
    sd: dict[str, Any],
    *,
    release_hold: bool,
    via: str,
    order_id: int,
    user_id: int | None,
    released_by: str | None,
    db: Any,
) -> tuple[Any, int] | None:
    """생산 전이(start/complete/rework) 전 보류 게이트. 세 엔드포인트가 공유한다.

    ``sd['production']['hold']['active']`` 가 truthy 면 주문이 보류 중이다:
      - ``release_hold`` 가 True 가 아니면 409 HOLD_ACTIVE 응답 튜플을 반환한다
        (호출부가 즉시 return — 전이 미진행, sd 불변).
      - ``release_hold`` 가 True 면 같은 sd 안에서 hold 를 해제(active=False, hold API
        해제 형과 동일)하고 ``PRODUCTION_HOLD_TOGGLED``(via) OrderEvent 를 큐잉한 뒤
        None 을 반환한다(전이 진행).
    보류가 없으면(또는 active 아님) 아무것도 하지 않고 None 을 반환한다 —
    ``release_hold`` 가 True 여도 무해하며 정상 전이한다.

    sd 는 호출부의 작업 dict(전이 흐름이 이후 ``copy.deepcopy(sd)`` 로 저장)이며,
    여기서의 hold 갱신은 그 deepcopy 에 포함되어 함께 커밋된다.

    :param sd: 수정 대상 structured_data(전이 흐름의 작업 dict).
    :param release_hold: body ``release_hold`` 플래그(True 여야 해제).
    :param via: 이벤트 payload ``via`` 값("release_on_start"|"release_on_complete"|"release_on_rework").
    :param order_id: 대상 주문 id(OrderEvent 기록용).
    :param user_id: 해제자 user id(OrderEvent created_by).
    :param released_by: 해제자 이름(hold_history 보존용, ``user.name`` 또는 None).
    :param db: DB 세션(OrderEvent add).
    :return: 409 응답 튜플(보류·미해제) 또는 None(전이 진행).
    """
    production = sd.get("production")
    hold = production.get("hold") if isinstance(production, dict) else None
    if not (isinstance(hold, dict) and hold.get("active")):
        return None  # 보류 없음 → 정상 전이.

    if not release_hold:
        message = "보류 중인 주문입니다."
        reason = hold.get("reason")
        if reason:
            message += f" (사유: {reason})"
        return (
            jsonify(
                {"success": False, "code": "HOLD_ACTIVE", "message": message, "hold": hold}
            ),
            409,
        )

    # 해제 후 전이 — 직전 active hold 를 이력에 보존한 뒤(소실 방지) hold 초기화 + 토글 이벤트 기록.
    _append_hold_history(production, released_by)
    production["hold"] = {"active": False, "reason": "", "at": None, "by_name": None}
    db.add(
        OrderEvent(
            order_id=order_id,
            event_type="PRODUCTION_HOLD_TOGGLED",
            payload={
                "active": False,
                "reason": "",
                "via": via,
                "domain": "PRODUCTION_DOMAIN",
                "action": "PRODUCTION_HOLD_TOGGLED",
            },
            created_by_user_id=user_id,
        )
    )
    return None


@erp_orders_production_bp.route("/<int:order_id>/production/start", methods=["POST"])
@login_required
@erp_edit_required
def api_production_start(order_id):
    """제작 시작 (PRODUCTION 단계로 이동)"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        # 전이 전제조건: 제작대기(고객컨펌/CONFIRM) 에서만 시작 허용. 레거시 한글 값 포함.
        if order.erp_stage_code not in ("고객컨펌", "CONFIRM"):
            return (
                jsonify(
                    {
                        "success": False,
                        "code": "INVALID_STAGE",
                        "message": "제작대기 상태에서만 제작을 시작할 수 있습니다.",
                    }
                ),
                409,
            )

        body = request.get_json(silent=True) or {}
        release_hold = body.get("release_hold") is True

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)

        hold_gate = _apply_production_hold_gate(
            sd,
            release_hold=release_hold,
            via="release_on_start",
            order_id=order_id,
            user_id=user_id,
            released_by=user.name if user else None,
            db=db,
        )
        if hold_gate is not None:
            return hold_gate

        wf = sd.get("workflow") or {}
        wf["stage"] = "PRODUCTION"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "PRODUCTION",
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": "제작 시작",
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = "PRODUCTION"
        sync_erp_flat_columns(order, sd)

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 제작 시작 (PRODUCTION)"))
        db.commit()
        return jsonify({"success": True, "message": "제작이 시작되었습니다.", "new_status": "PRODUCTION"})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/complete", methods=["POST"])
@login_required
@erp_edit_required
def api_production_complete(order_id):
    """제작 완료 (CONSTRUCTION 단계로 이동)"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        # 전이 전제조건: 제작중(생산/PRODUCTION) 에서만 완료 허용. 레거시 한글 값 포함.
        if order.erp_stage_code not in ("생산", "PRODUCTION"):
            return (
                jsonify(
                    {
                        "success": False,
                        "code": "INVALID_STAGE",
                        "message": "제작중 상태에서만 제작을 완료할 수 있습니다.",
                    }
                ),
                409,
            )

        body = request.get_json(silent=True) or {}
        release_hold = body.get("release_hold") is True

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)

        hold_gate = _apply_production_hold_gate(
            sd,
            release_hold=release_hold,
            via="release_on_complete",
            order_id=order_id,
            user_id=user_id,
            released_by=user.name if user else None,
            db=db,
        )
        if hold_gate is not None:
            return hold_gate

        # 재제작(rework) 완료 판정 — active 면 완료 시 해제(count·reason·at·by_name 보존)하고
        # 이력 note·이벤트 payload 에 재제작임을 표기한다.
        production = sd.get("production") if isinstance(sd.get("production"), dict) else None
        rework = production.get("rework") if isinstance(production, dict) else None
        is_rework_completion = bool(isinstance(rework, dict) and rework.get("active"))

        wf = sd.get("workflow") or {}
        wf["stage"] = "CONSTRUCTION"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "CONSTRUCTION",
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": "제작 완료 (재제작)" if is_rework_completion else "제작 완료 (시공/출고 대기)",
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        if is_rework_completion:
            # active 만 해제(count·reason·at·by_name 보존)하고 완료 시각을 기록한다.
            # completed_at 은 uncomplete(완료 취소)가 "이 완료가 재제작 완료였는지" 판정하는
            # 근거 — 존재하면 uncomplete 가 rework 를 active=True 로 복원한다.
            rework["active"] = False
            rework["completed_at"] = now_utc_naive().isoformat()

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = "CONSTRUCTION"
        sync_erp_flat_columns(order, sd)

        event_payload = {
            "domain": "PRODUCTION_DOMAIN",
            "action": "PRODUCTION_COMPLETED",
            "target": "workflow.stage",
            "before": "PRODUCTION",
            "after": "CONSTRUCTION",
            "change_method": "API",
            "source_screen": "erp_production_dashboard",
            "reason": "제작 완료 (시공 대기)",
        }
        if is_rework_completion:
            event_payload["rework"] = True
        order_event = OrderEvent(
            order_id=order_id,
            event_type="PRODUCTION_COMPLETED",
            payload=event_payload,
            created_by_user_id=user_id,
        )
        db.add(order_event)

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 제작 완료 (CONSTRUCTION)"))
        db.commit()
        return jsonify(
            {
                "success": True,
                "message": "제작이 완료되었습니다. (시공 대기 상태로 변경)",
                "new_status": "CONSTRUCTION",
            }
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/rework", methods=["POST"])
@login_required
@erp_edit_required
def api_production_rework(order_id: int):
    """수정 제작 시작 (제작완료 → PRODUCTION 되돌림).

    제작완료(시공/CONSTRUCTION) 상태의 주문을 다시 제작중(PRODUCTION)으로 되돌린다.
    재제작 회차(count)를 누적하고 ``sd['production']['rework']`` 에 활성 표식을 남긴다
    (완료 시 ``api_production_complete`` 가 active=False 로 해제하며 count 는 보존).
    가드는 start/complete 와 동일 순서: 404 → INVALID_STAGE(제작완료가 아니면 409) →
    보류 게이트(HOLD_ACTIVE / release_hold, via="release_on_rework").

    :param order_id: 대상 주문 id.
    :param reason: (body) 수정 제작 사유(선택, trim). 빈 값 허용.
    :param release_hold: (body) 보류 해제 후 진행 여부(선택, bool).
    :return: ``{success, message, new_status}`` 또는 오류 JSON(에러 키 = message).
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        # 전이 전제조건: 제작완료(시공/CONSTRUCTION) 에서만 수정 제작 허용. 레거시 한글 값 포함.
        if order.erp_stage_code not in ("시공", "CONSTRUCTION"):
            return (
                jsonify(
                    {
                        "success": False,
                        "code": "INVALID_STAGE",
                        "message": "제작완료 상태에서만 수정 제작을 시작할 수 있습니다.",
                    }
                ),
                409,
            )

        body = request.get_json(silent=True) or {}
        release_hold = body.get("release_hold") is True
        reason_raw = body.get("reason")
        reason = reason_raw.strip() if isinstance(reason_raw, str) else ""

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)

        hold_gate = _apply_production_hold_gate(
            sd,
            release_hold=release_hold,
            via="release_on_rework",
            order_id=order_id,
            user_id=user_id,
            released_by=user.name if user else None,
            db=db,
        )
        if hold_gate is not None:
            return hold_gate

        wf = sd.get("workflow") or {}
        wf["stage"] = "PRODUCTION"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        note = "수정 제작 시작"
        if reason:
            note += f" — {reason}"
        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "PRODUCTION",
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": note,
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        production = sd.get("production")
        if not isinstance(production, dict):
            production = {}
            sd["production"] = production
        prev_rework = production.get("rework")
        prev_count = prev_rework.get("count") if isinstance(prev_rework, dict) else 0
        count = (prev_count or 0) + 1
        production["rework"] = {
            "active": True,
            "reason": reason,
            "count": count,
            "at": now_utc_naive().isoformat(),
            "by_name": user.name if user else None,
        }

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = "PRODUCTION"
        sync_erp_flat_columns(order, sd)

        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_REWORK_STARTED",
                payload={
                    "reason": reason,
                    "count": count,
                    "domain": "PRODUCTION_DOMAIN",
                    "action": "PRODUCTION_REWORK_STARTED",
                },
                created_by_user_id=user_id,
            )
        )
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 수정 제작 시작 (PRODUCTION)"))
        db.commit()
        return jsonify(
            {"success": True, "message": "수정 제작을 시작했습니다.", "new_status": "PRODUCTION"}
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/cancel", methods=["POST"])
@login_required
@erp_edit_required
def api_production_cancel(order_id: int):
    """제작 취소 (제작중 → 제작대기/CONFIRM 되돌림).

    제작중(생산/PRODUCTION) 상태의 주문을 제작대기(CONFIRM)로 되돌린다. 후진 전이이므로
    **보류 게이트를 적용하지 않는다** — 보류는 전진(시작·완료·수정 제작)만 막는 표시 전용
    플래그이며, 되돌리기는 보류가 걸린 채로도 허용한다(단, 아래처럼 정리한다).
    가드는 404 → INVALID_STAGE(제작중이 아니면 409) 순서. start 패턴과 동일하게
    deepcopy + flag_modified + sync_erp_flat_columns + SecurityLog + OrderEvent 를 남긴다.

    **깨끗한 되돌림(F-1)**: 취소는 진행 자체를 되돌리므로 진행 플래그를 정리한다(이력 보존).
    ``sd['production']`` 이 dict 면 (1) ``rework`` dict 의 ``active`` 를 False 로(count·reason·at
    보존), (2) ``hold`` 가 active 면 ``_append_hold_history`` 로 이력에 보존한 뒤 hold 초기화.
    이렇게 하면 제작대기로 복귀한 카드/시트에 재제작·보류 배지가 잔존하지 않는다.
    (완료 취소 ``uncomplete`` 는 제작중 복귀라 rework 를 **복원**하므로 여기와 반대다.)

    :param order_id: 대상 주문 id.
    :param reason: (body) 취소 사유(선택, trim). 빈 값 허용.
    :return: ``{success, message, new_status}`` 또는 오류 JSON(에러 키 = message).
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        # 전이 전제조건: 제작중(생산/PRODUCTION) 에서만 취소 허용. 레거시 한글 값 포함.
        if order.erp_stage_code not in ("생산", "PRODUCTION"):
            return (
                jsonify(
                    {
                        "success": False,
                        "code": "INVALID_STAGE",
                        "message": "제작중 상태에서만 제작을 취소할 수 있습니다.",
                    }
                ),
                409,
            )

        body = request.get_json(silent=True) or {}
        reason_raw = body.get("reason")
        reason = reason_raw.strip() if isinstance(reason_raw, str) else ""

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)

        wf = sd.get("workflow") or {}
        wf["stage"] = "CONFIRM"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        note = "제작 취소 (제작대기 복귀)"
        if reason:
            note += f" — {reason}"
        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "CONFIRM",
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": note,
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        # 깨끗한 되돌림(F-1b): 진행 플래그(rework/hold active) 정리 — 이력은 보존.
        production = sd.get("production")
        rework_cleared = False
        hold_released = False
        if isinstance(production, dict):
            rework = production.get("rework")
            if isinstance(rework, dict):
                rework_cleared = bool(rework.get("active"))
                rework["active"] = False  # count·reason·at 보존
            hold = production.get("hold")
            if isinstance(hold, dict) and hold.get("active"):
                _append_hold_history(production, user.name if user else None)
                production["hold"] = {"active": False, "reason": "", "at": None, "by_name": None}
                hold_released = True

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = "CONFIRM"
        sync_erp_flat_columns(order, sd)

        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_CANCELLED",
                payload={
                    "reason": reason,
                    "rework_cleared": rework_cleared,
                    "hold_released": hold_released,
                    "domain": "PRODUCTION_DOMAIN",
                    "action": "PRODUCTION_CANCELLED",
                },
                created_by_user_id=user_id,
            )
        )
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 제작 취소 (제작대기 복귀)"))
        db.commit()
        return jsonify(
            {
                "success": True,
                "message": "제작을 취소했습니다. (제작대기 복귀)",
                "new_status": "CONFIRM",
            }
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/uncomplete", methods=["POST"])
@login_required
@erp_edit_required
def api_production_uncomplete(order_id: int):
    """완료 취소 (제작완료 → 제작중/PRODUCTION 되돌림).

    제작완료(시공/CONSTRUCTION) 상태의 주문을 다시 제작중(PRODUCTION)으로 되돌린다.
    후진 전이이므로 **보류 게이트를 적용하지 않는다**(cancel 참조 — 보류는 유지된다).
    가드는 404 → INVALID_STAGE(제작완료가 아니면 409) 순서.

    **재제작 복원**: 직전 완료가 재제작 완료였다면(``rework`` dict 에 ``completed_at`` 가 있고
    ``active`` 가 False) 완료를 되돌리며 rework 를 ``active=True`` 로 복원하고 ``completed_at``
    키를 제거한다(회차 count 는 불변). 재제작 완료가 아니었으면 rework 는 건드리지 않는다.

    :param order_id: 대상 주문 id.
    :return: ``{success, message, new_status}`` 또는 오류 JSON(에러 키 = message).
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        # 전이 전제조건: 제작완료(시공/CONSTRUCTION) 에서만 완료 취소 허용. 레거시 한글 값 포함.
        if order.erp_stage_code not in ("시공", "CONSTRUCTION"):
            return (
                jsonify(
                    {
                        "success": False,
                        "code": "INVALID_STAGE",
                        "message": "제작완료 상태에서만 완료 취소할 수 있습니다.",
                    }
                ),
                409,
            )

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)

        wf = sd.get("workflow") or {}
        wf["stage"] = "PRODUCTION"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "PRODUCTION",
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": "완료 취소 (제작중 복귀)",
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        # 재제작 완료 되돌리기: 직전 완료가 재제작 완료였으면(completed_at 존재 + active False)
        # rework 를 다시 활성으로 복원하고 완료 시각 표식을 제거한다(count 보존).
        production = sd.get("production") if isinstance(sd.get("production"), dict) else None
        rework = production.get("rework") if isinstance(production, dict) else None
        rework_restored = False
        if isinstance(rework, dict) and rework.get("completed_at") and not rework.get("active"):
            rework["active"] = True
            rework.pop("completed_at", None)
            rework_restored = True

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = "PRODUCTION"
        sync_erp_flat_columns(order, sd)

        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_COMPLETE_REVERTED",
                payload={
                    "rework_restored": rework_restored,
                    "domain": "PRODUCTION_DOMAIN",
                    "action": "PRODUCTION_COMPLETE_REVERTED",
                },
                created_by_user_id=user_id,
            )
        )
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 완료 취소 (제작중 복귀)"))
        db.commit()
        return jsonify(
            {
                "success": True,
                "message": "완료를 취소했습니다. (제작중 복귀)",
                "new_status": "PRODUCTION",
            }
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/change-ack", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_change_ack(order_id: int):
    """생산 변경 확인(ack). 카드/시트 변경 스트립·묘비 [확인] 버튼이 호출한다.

    ``PRODUCTION_CHANGE_ACK`` OrderEvent 를 1건 기록만 한다(structured_data·상태 불변).
    이 ack 시각이 변경 감지 윈도를 리셋하므로 이후 대시보드 재조회 시 해당 주문의
    변경 스트립이 사라진다. **삭제(취소)된 주문에도 허용**한다 — 묘비 카드 확인용이라
    ``active_filter`` 대신 존재 여부만 확인한다.

    권한: 생산 공정 스텝과 동일 게이트(ADMIN 또는 CS/SALES/**PRODUCTION** 팀). ack 는
    "생산 인원 개인별" 설계라 생산팀 계정이 반드시 눌러야 하므로 erp_edit(ADMIN/CS/SALES
    전용)이 아닌 스텝 게이트를 재사용한다.

    :param order_id: 대상 주문 id.
    :return: ``{success, data:{order_id}}`` 또는 오류 JSON.
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if order is None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        payload = {"source": "tablet_kanban"}
        if order.deleted_at is not None:
            # 묘비 확인: 이 삭제 시점을 마커로 고정한다(시계 비교 없이 동등성으로 판정).
            # 복구 후 재삭제되면 deleted_at 값이 달라져 묘비가 다시 나타난다(의도된 동작).
            payload["deleted_at"] = str(order.deleted_at)
        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_CHANGE_ACK",
                payload=payload,
                created_by_user_id=session.get("user_id"),
            )
        )
        db.commit()
        return jsonify({"success": True, "data": {"order_id": order_id}})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/steps", methods=["GET"])
@login_required
def api_production_steps_get(order_id: int):
    """생산 공정 스텝 조회(시트 lazy 로드용).

    sd['production']['steps'] 가 없으면 기본 5단계를 메모리에서 파생만 하고 저장하지
    않는다(쓰기는 POST 소관). 읽기는 대시보드 열람과 동일하게 @login_required 만 요구
    — 편집 불가 팀도 진행 현황은 볼 수 있어야 한다.
    """
    db = get_db()
    order = db.get(Order, order_id)
    if not order or order.status == "DELETED" or order.deleted_at is not None:
        return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

    sd = _ensure_dict(order.structured_data)
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    steps = production.get("steps")
    if not isinstance(steps, list) or not steps:
        steps = [
            {"key": key, "label": label, "done": False, "at": None, "by_name": None}
            for key, label in _PRODUCTION_STEP_DEFS
        ]
    done_count = sum(1 for s in steps if isinstance(s, dict) and s.get("done"))
    defects = production.get("defects") if isinstance(production.get("defects"), list) else []
    latest_defect = defects[-1] if defects else None
    return jsonify(
        {
            "success": True,
            "data": {
                "steps": steps,
                "done_count": done_count,
                "total": len(steps),
                "latest_defect": latest_defect,
            },
        }
    )


@erp_orders_production_bp.route("/<int:order_id>/production/steps", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_steps(order_id: int):
    """생산 공정 스텝 체크 토글. body {key, done(bool)}.

    최초 접근 시 기본 5단계(cut/edge/paint/assemble/inspect)를 생성한 뒤 해당 key의
    done 상태를 반영한다(체크 시 at=UTC iso, by_name 기록). JSONB 는 deepcopy+flag_modified.
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        key = payload.get("key")
        done = payload.get("done")
        if key not in _PRODUCTION_STEP_KEYS or not isinstance(done, bool):
            return jsonify({"success": False, "error": "key 또는 done 값이 올바르지 않습니다."}), 400

        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        user = get_user_by_id(session.get("user_id"))
        sd = copy.deepcopy(_ensure_dict(order.structured_data))
        steps = _ensure_production_steps(sd)
        target = next((s for s in steps if s.get("key") == key), None)
        if target is None:  # 방어: 기본 5단계에는 항상 존재
            return jsonify({"success": False, "error": "해당 공정을 찾을 수 없습니다."}), 400

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        target["done"] = done
        target["at"] = now_iso if done else None
        target["by_name"] = (user.name if user else None) if done else None

        order.structured_data = sd
        flag_modified(order, "structured_data")
        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_STEP_CHECKED",
                payload={
                    "key": key,
                    "done": done,
                    "domain": "PRODUCTION_DOMAIN",
                    "action": "PRODUCTION_STEP_CHECKED",
                },
                created_by_user_id=session.get("user_id"),
            )
        )
        db.commit()
        done_count = sum(1 for s in steps if s.get("done"))
        return jsonify(
            {"success": True, "data": {"steps": steps, "done_count": done_count, "total": len(steps)}}
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/defect", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_defect(order_id: int):
    """생산 불량 보고. body {reason}.

    reason 은 화이트리스트(_PRODUCTION_DEFECT_REASONS)로 검증한다. 통과 시
    sd['production']['defects'] 에 {reason, at(UTC iso), by_name} 를 append 하고
    최근 _PRODUCTION_DEFECTS_CAP(20)건만 유지한다. OrderEvent 'PRODUCTION_DEFECT_REPORTED'
    를 남기며 JSONB 는 deepcopy+flag_modified 규약을 따른다.

    :param order_id: 대상 주문 id.
    :return: {success, data:{defects, latest, total}} 또는 오류 JSON.
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        reason = payload.get("reason")
        if reason not in _PRODUCTION_DEFECT_REASONS:
            return jsonify({"success": False, "error": "불량 사유 값이 올바르지 않습니다."}), 400

        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        user = get_user_by_id(session.get("user_id"))
        sd = copy.deepcopy(_ensure_dict(order.structured_data))
        production = sd.get("production")
        if not isinstance(production, dict):
            production = {}
            sd["production"] = production
        defects = production.get("defects")
        if not isinstance(defects, list):
            defects = []

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        entry = {"reason": reason, "at": now_iso, "by_name": (user.name if user else None)}
        defects.append(entry)
        if len(defects) > _PRODUCTION_DEFECTS_CAP:
            defects = defects[-_PRODUCTION_DEFECTS_CAP:]
        production["defects"] = defects

        order.structured_data = sd
        flag_modified(order, "structured_data")
        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_DEFECT_REPORTED",
                payload={
                    "reason": reason,
                    "domain": "PRODUCTION_DOMAIN",
                    "action": "PRODUCTION_DEFECT_REPORTED",
                },
                created_by_user_id=session.get("user_id"),
            )
        )
        db.commit()
        return jsonify(
            {"success": True, "data": {"defects": defects, "latest": entry, "total": len(defects)}}
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/hold", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_hold(order_id: int):
    """생산 보류 플래그 토글. body {active(bool), reason(str, optional)}.

    ``sd['production']['hold'] = {active, reason, at(UTC iso 또는 None), by_name}`` 를
    기록한다. 이는 **표시 전용 플래그**이며 워크플로 단계(``workflow.stage``)나
    ``order.status`` 를 전이시키지 않는다 — 칸반 카드·시트에 보류 배지를 노출하기 위한
    상태일 뿐이다. active=True 면 at/by_name/reason 을 기록하고, active=False(해제)면
    **초기화 직전 직전 active hold 를 ``hold_history`` 에 보존**(완료 후 이력 소실 방지,
    ``_append_hold_history``)한 뒤 at=None, by_name=None, reason="" 로 초기화한다. JSONB 는
    copy.deepcopy+flag_modified 규약을 따른다. 권한은 생산 공정 스텝과 동일(ADMIN 또는
    CS/SALES/PRODUCTION 팀).

    :param order_id: 대상 주문 id.
    :return: ``{success, data:{hold}}`` 또는 오류 JSON.
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        active = payload.get("active")
        if not isinstance(active, bool):
            return jsonify({"success": False, "error": "active 값(bool)이 올바르지 않습니다."}), 400
        reason_raw = payload.get("reason")
        reason = reason_raw.strip() if isinstance(reason_raw, str) else ""

        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        user = get_user_by_id(session.get("user_id"))
        sd = copy.deepcopy(_ensure_dict(order.structured_data))
        production = sd.get("production")
        if not isinstance(production, dict):
            production = {}
            sd["production"] = production

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        hold = {
            "active": active,
            "reason": reason if active else "",
            "at": now_iso if active else None,
            "by_name": (user.name if user else None) if active else None,
        }
        # 해제(active=False)면 직전 active hold 를 이력에 보존한 뒤 초기화한다(소실 방지).
        if not active:
            _append_hold_history(production, user.name if user else None)
        production["hold"] = hold

        order.structured_data = sd
        flag_modified(order, "structured_data")
        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_HOLD_TOGGLED",
                payload={
                    "active": active,
                    "reason": reason if active else "",
                    "domain": "PRODUCTION_DOMAIN",
                    "action": "PRODUCTION_HOLD_TOGGLED",
                },
                created_by_user_id=session.get("user_id"),
            )
        )
        db.commit()
        return jsonify({"success": True, "data": {"hold": hold}})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500
