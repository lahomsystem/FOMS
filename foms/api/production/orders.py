"""
ERP 주문 생산(제작) API. (Phase 4-5f)
erp.py에서 분리: production/start, production/complete, production/steps.
"""

import copy
import datetime
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

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get("workflow") or {}
        wf["stage"] = "PRODUCTION"
        wf["stage_updated_at"] = datetime.datetime.now().isoformat()
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

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get("workflow") or {}
        wf["stage"] = "CONSTRUCTION"
        wf["stage_updated_at"] = datetime.datetime.now().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "CONSTRUCTION",
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": "제작 완료 (시공/출고 대기)",
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

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
    at=None, by_name=None, reason="" 로 초기화한다. JSONB 는 copy.deepcopy+flag_modified
    규약을 따른다. 권한은 생산 공정 스텝과 동일(ADMIN 또는 CS/SALES/PRODUCTION 팀).

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
