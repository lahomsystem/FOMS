"""
시공 완료 대시보드용 API.
계획서: docs/plans/2026-03-02-construction-completion-dashboard-plan.md
- GET /api/orders/completion: 완료·AS 건 목록 + 시공 사진(category=construction) + 시공자 코멘트.
- POST /api/orders/<id>/settlement/issue: 비용 청구/차감 이벤트 기록 (structured_data.settlement).
"""
import copy
from foms.services.error_logging import log_handled_exception
import datetime

from flask import Blueprint, jsonify, request, session
from sqlalchemy import or_
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required
from db import get_db
from foms.api.files import build_file_download_url, build_file_view_url
from foms.services.as_content_safety import combined_as_content_text
from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate
from foms.services.erp_order_deeplink import load_focus_order_only
from foms.services.erp_display import _ensure_dict
from foms.services.common.erp_mine_filter import erp_mine_only_for_construction
from foms.services.erp_permissions import build_mine_sql_filter, is_order_related_to_user
from foms.services.erp_policy import ORDER_SETTLEMENT_ALERT_TARGET_STATUSES
from foms.services.foms_unified_search import (
    _compact,
    _matches_phone,
    _order_customer_name,
    _order_phone,
    is_chosung_query,
    matches_query,
)
from foms.services.request_utils import get_search_query_arg
from foms.services.datetime_kst import format_datetime_kst
from models import Order, OrderAttachment, OrderEvent, SecurityLog, User

# 완료 대시보드 대상: 시공 완료·AS 접수 등 (정책 상수는 `foms.services.erp_policy` SSOT)
TARGET_STATUSES = ORDER_SETTLEMENT_ALERT_TARGET_STATUSES
CONSTRUCTION_CATEGORY = "construction"
# 무검색 브라우즈: 최근 N건만 (성능·리뷰 큐 UX)
_COMPLETION_BROWSE_LIMIT = 200
# 검색(q) 결과 상한 — SQL 필터 후 cap (창 밖 누락 없음, 동명 다수만 제한)
_COMPLETION_SEARCH_LIMIT = 500
# 초성 검색: Python 스캔 상한 (completion 전체가 이보다 크면 별도 인덱스 필요)
_COMPLETION_CHOSUNG_SCAN_LIMIT = 2000


def _apply_mine_filter(query, user, *, mine_only: bool):
    """전역 mine 또는 시공팀 강제 mine을 로그인 사용자의 역할 관계로 제한."""
    if not mine_only or not user:
        return query
    mine_conds = build_mine_sql_filter(user)
    if not mine_conds:
        return query.filter(Order.id == -1)
    return query.filter(or_(*mine_conds))

# 비용 청구 귀속 대상 (계획서 3.1)
SETTLEMENT_DEPARTMENTS = ("SALES", "DRAWING", "PRODUCTION", "CONSTRUCTION", "CUSTOMER")

erp_orders_completion_bp = Blueprint(
    "erp_orders_completion",
    __name__,
    url_prefix="/api/orders",
)


def _att_view_url(storage_key):
    if not storage_key:
        return ""
    return build_file_view_url(storage_key)


def _att_download_url(storage_key):
    if not storage_key:
        return ""
    return build_file_download_url(storage_key)


def _completion_base_query(db):
    """Active ERP completion-queue orders (COMPLETED / AS_*)."""
    return (
        db.query(Order)
        .filter(
            Order.active_filter(),
            Order.is_erp_order.is_(True),
            Order.status.in_(TARGET_STATUSES),
        )
    )


def _completion_order_matches_query(order: Order, query: str) -> bool:
    """Python-side match for chosung and post-filter parity with unified search."""
    if matches_query(_order_customer_name(order), query):
        return True
    if _matches_phone(_order_phone(order), order.erp_phone_digits, query):
        return True
    for field in (str(order.id), order.product, order.address, order.manager_name):
        if matches_query(field, query):
            return True
    return False


def _load_completion_orders(
    db,
    *,
    search_q: str = "",
    focus_order_id: int | None = None,
    current_user=None,
    mine_only: bool = False,
) -> list[Order]:
    """
    Load completion dashboard rows.

    Browse (no ``q``): latest ``_COMPLETION_BROWSE_LIMIT`` — 성능·리뷰 큐용.
    Search (``q``): SQL/Python 필터로 **전체 completion 풀**에서 매칭 (최신 N 창 아님).
    ``focus_order``: 검색 카드 클릭 — PK 단건만 반환 (``q``는 검색창 표시용, 목록 확장 금지).
    """
    base = _completion_base_query(db)
    base = _apply_mine_filter(base, current_user, mine_only=mine_only)
    if focus_order_id:
        orders = load_focus_order_only(base, focus_order_id)
        return [
            order for order in orders
            if not mine_only or is_order_related_to_user(order, current_user)
        ]

    trimmed_q = (search_q or "").strip()
    orders: list[Order]

    if trimmed_q:
        if is_chosung_query(trimmed_q):
            candidates = (
                base.order_by(Order.id.desc())
                .limit(_COMPLETION_CHOSUNG_SCAN_LIMIT)
                .all()
            )
            orders = [
                order for order in candidates
                if _completion_order_matches_query(order, trimmed_q)
            ][: _COMPLETION_SEARCH_LIMIT]
        else:
            term = f"%{_compact(trimmed_q)}%"
            if term.strip("%"):
                orders = (
                    base.filter(erp_order_dashboard_search_predicate(term))
                    .order_by(Order.id.desc())
                    .limit(_COMPLETION_SEARCH_LIMIT)
                    .all()
                )
            else:
                orders = []
    else:
        orders = (
            base.order_by(Order.id.desc())
            .limit(_COMPLETION_BROWSE_LIMIT)
            .all()
        )

    if mine_only:
        orders = [
            order for order in orders
            if is_order_related_to_user(order, current_user)
        ]
    return orders


def _serialize_completion_orders(db, orders: list[Order]) -> list[dict]:
    """Build JSON payload rows for completion dashboard cards."""
    order_ids = [o.id for o in orders]
    if not order_ids:
        return []

    atts = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == CONSTRUCTION_CATEGORY,
        )
        .order_by(OrderAttachment.order_id, OrderAttachment.created_at.asc())
        .all()
    )
    atts_by_order: dict[int, list] = {}
    for attachment in atts:
        atts_by_order.setdefault(attachment.order_id, []).append(attachment)

    result = []
    for order in orders:
        sd = _ensure_dict(order.structured_data)
        schedule = sd.get("schedule") or {}
        construction_date = (schedule.get("construction") or {}).get("date")
        parties = sd.get("parties") or {}
        customer_name = (parties.get("customer") or {}).get("name") or getattr(order, "customer_name", None) or "-"
        manager_name = (parties.get("manager") or {}).get("name") or getattr(order, "manager_name", None) or "-"
        items = sd.get("items") or []
        product_summary = ", ".join(
            str((item.get("product_name") or "").strip() or "")
            for item in items if isinstance(item, dict) and (item.get("product_name") or "").strip()
        )[:80] or "-"

        shipment = sd.get("shipment") or {}
        as_content_raw = shipment.get("as_content") or ""
        as_content_text = combined_as_content_text(
            sd,
            notes_fallback=getattr(order, "notes", None) or "",
        )
        fail_history = sd.get("construction_fail_history") or []
        completion_note = (sd.get("workflow") or {}).get("completion_note") or ""

        construction_photos = []
        for attachment in atts_by_order.get(order.id, []):
            construction_photos.append({
                "id": attachment.id,
                "filename": attachment.filename,
                "file_type": attachment.file_type or "image",
                "storage_key": attachment.storage_key,
                "view_url": _att_view_url(attachment.storage_key),
                "download_url": _att_download_url(attachment.storage_key),
                "created_at": format_datetime_kst(attachment.created_at, "%Y-%m-%d %H:%M") if attachment.created_at else None,
            })

        result.append({
            "id": order.id,
            "status": order.status,
            "is_self_measurement": getattr(order, "is_self_measurement", False),
            "construction_date": construction_date,
            "customer_name": customer_name,
            "manager_name": manager_name,
            "product_summary": product_summary,
            "as_content": as_content_raw,
            "as_content_text": as_content_text,
            "construction_fail_history": fail_history,
            "completion_note": completion_note,
            "construction_photos": construction_photos,
        })
    return result


@erp_orders_completion_bp.route("/completion", methods=["GET"])
@login_required
def api_orders_completion():
    """완료·AS 건 목록 + 시공 사진 썸네일·URL + 시공자 코멘트(as_content, construction_fail_history 등)."""
    try:
        db = get_db()
        user = get_user_by_id(session.get("user_id"))
        search_q = get_search_query_arg("q", "search")
        focus_order_id = request.args.get("focus_order", type=int)
        mine_only = erp_mine_only_for_construction(request, user)
        orders = _load_completion_orders(
            db,
            search_q=search_q,
            focus_order_id=focus_order_id,
            current_user=user,
            mine_only=mine_only,
        )
        result = _serialize_completion_orders(db, orders)
        return jsonify({"success": True, "orders": result})
    except Exception as e:
        log_handled_exception()
        return jsonify({"success": False, "message": str(e)}), 500


@erp_orders_completion_bp.route("/<int:order_id>/settlement/issue", methods=["POST"])
@login_required
def api_settlement_issue(order_id):
    """비용 청구/차감 이벤트 기록. structured_data.settlement에 deductions 추가, status=ISSUE_RAISED."""
    db = None
    try:
        user = get_user_by_id(session.get("user_id"))
        if user and getattr(user, "team", None) == "CONSTRUCTION":
            return jsonify({"success": False, "message": "시공팀은 비용 청구를 등록할 수 없습니다."}), 403

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404
        if order.status not in TARGET_STATUSES:
            return jsonify({"success": False, "message": "완료·AS 건에만 비용 청구를 등록할 수 있습니다."}), 400

        data = request.get_json() or {}
        department = (data.get("department") or "").strip().upper()
        amount = data.get("amount")
        reason = (data.get("reason") or "").strip()
        charge_to_user_id = data.get("charge_to_user_id")

        if department not in SETTLEMENT_DEPARTMENTS:
            return jsonify({"success": False, "message": "귀속 대상이 올바르지 않습니다. (SALES, DRAWING, PRODUCTION, CONSTRUCTION, CUSTOMER)"}), 400
        if amount is None:
            return jsonify({"success": False, "message": "청구 금액을 입력해주세요."}), 400
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "청구 금액을 숫자로 입력해주세요."}), 400
        if amount > 0:
            amount = -amount
        if not reason:
            return jsonify({"success": False, "message": "사유를 입력해주세요."}), 400

        charge_to_name = None
        if charge_to_user_id is not None and charge_to_user_id != "":
            if department == "CUSTOMER":
                charge_to_user_id = None
            else:
                try:
                    uid = int(charge_to_user_id)
                except (TypeError, ValueError):
                    return jsonify({"success": False, "message": "귀속 인원이 올바르지 않습니다."}), 400
                charge_user = db.query(User).filter(User.id == uid, User.is_active == True).first()
                if not charge_user:
                    return jsonify({"success": False, "message": "해당 귀속 인원을 찾을 수 없거나 비활성입니다."}), 400
                if (charge_user.team or "").strip().upper() != department:
                    return jsonify({"success": False, "message": "선택한 인원이 해당 부서 소속이 아닙니다."}), 400
                charge_to_user_id = uid
                charge_to_name = str(charge_user.name) if charge_user.name is not None else None

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        created_by = user.name if user else "Unknown"
        now_iso = datetime.datetime.now().isoformat()
        ded_id = f"DED-{order_id}-{int(datetime.datetime.now().timestamp() * 1000)}"

        sd = _ensure_dict(order.structured_data)
        settlement = sd.get("settlement")
        if not isinstance(settlement, dict):
            settlement = {"status": "PENDING", "base_cost": None, "deductions": [], "final_cost": None}
        deductions = settlement.get("deductions")
        if not isinstance(deductions, list):
            deductions = []
        ded_item = {
            "id": ded_id,
            "department": department,
            "amount": amount,
            "reason": reason,
            "created_at": now_iso,
            "created_by": created_by,
        }
        if charge_to_user_id is not None:
            ded_item["charge_to_user_id"] = charge_to_user_id
        if charge_to_name:
            ded_item["charge_to_name"] = charge_to_name
        deductions.append(ded_item)
        settlement["deductions"] = deductions
        settlement["status"] = "ISSUE_RAISED"
        base = settlement.get("base_cost")
        if base is not None and isinstance(base, (int, float)):
            settlement["final_cost"] = base + sum(d.get("amount", 0) for d in deductions)
        sd["settlement"] = settlement
        order.structured_data = copy.deepcopy(sd)  # type: ignore[assignment]
        flag_modified(order, "structured_data")

        event_payload = {
            "deduction_id": ded_id,
            "department": department,
            "amount": amount,
            "reason": reason,
            "created_by": created_by,
        }
        if charge_to_user_id is not None:
            event_payload["charge_to_user_id"] = charge_to_user_id
        if charge_to_name:
            event_payload["charge_to_name"] = charge_to_name
        db.add(OrderEvent(
            order_id=order_id,
            event_type="SETTLEMENT_ISSUE_RAISED",
            payload=event_payload,
            created_by_user_id=user_id,
        ))
        log_msg = f"주문 #{order_id} 비용 청구: {department}"
        if charge_to_name:
            log_msg += f" {charge_to_name}({charge_to_user_id})"
        log_msg += f" {amount}원 - {reason[:50]}"
        db.add(SecurityLog(user_id=user_id, message=log_msg))
        db.commit()

        return jsonify({
            "success": True,
            "message": "비용 청구가 등록되었습니다.",
            "deduction_id": ded_id,
            "settlement": settlement,
        })
    except Exception as e:
        if db is not None:
            db.rollback()
        log_handled_exception()
        return jsonify({"success": False, "message": str(e)}), 500


@erp_orders_completion_bp.route("/<int:order_id>/cash-receipt/issue", methods=["POST"])
@login_required
def api_cash_receipt_issue(order_id):
    """현금영수증 발행 기록. body {note(str, optional)}.

    ``structured_data.settlement.cash_receipt = {issued: True, at, by, note}`` 를 기록한다.
    발행은 terminal(재발행 없음) — 이미 발행된 건은 409 로 거절한다. 정산 발행과 동일하게
    시공팀(CONSTRUCTION)은 차단한다. JSONB 는 copy.deepcopy+flag_modified 규약을 따른다.

    Args:
        order_id: 대상 주문 id.

    Returns:
        ``{success, data:{cash_receipt}}`` 또는 오류 JSON(400/403/404/409/500).
    """
    db = None
    try:
        user = get_user_by_id(session.get("user_id"))
        if user and getattr(user, "team", None) == "CONSTRUCTION":
            return jsonify({"success": False, "error": "시공팀은 현금영수증을 발행할 수 없습니다."}), 403

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404
        if order.status not in TARGET_STATUSES:
            return jsonify({"success": False, "error": "완료·AS 건에만 현금영수증을 발행할 수 있습니다."}), 400

        data = request.get_json(silent=True) or {}
        note_raw = data.get("note")
        note = note_raw.strip() if isinstance(note_raw, str) else ""

        sd = _ensure_dict(order.structured_data)
        settlement = sd.get("settlement")
        if not isinstance(settlement, dict):
            settlement = {"status": "PENDING", "base_cost": None, "deductions": [], "final_cost": None}
        existing = settlement.get("cash_receipt")
        if isinstance(existing, dict) and existing.get("issued"):
            return jsonify({"success": False, "error": "이미 현금영수증이 발행된 건입니다."}), 409

        user_id = session.get("user_id")
        issued_by = user.name if user else "Unknown"
        now_iso = datetime.datetime.now().isoformat()
        cash_receipt = {"issued": True, "at": now_iso, "by": issued_by, "note": note}
        settlement["cash_receipt"] = cash_receipt
        sd["settlement"] = settlement
        order.structured_data = copy.deepcopy(sd)  # type: ignore[assignment]
        flag_modified(order, "structured_data")

        db.add(OrderEvent(
            order_id=order_id,
            event_type="CASH_RECEIPT_ISSUED",
            payload={"issued_by": issued_by, "note": note},
            created_by_user_id=user_id,
        ))
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 현금영수증 발행"))
        db.commit()
        return jsonify({"success": True, "data": {"cash_receipt": cash_receipt}})
    except Exception as e:
        if db is not None:
            db.rollback()
        log_handled_exception()
        return jsonify({"success": False, "error": str(e)}), 500


__all__ = [
    "erp_orders_completion_bp",
    "api_orders_completion",
    "api_settlement_issue",
    "api_cash_receipt_issue",
]
