"""UPLOAD-02: per-file 업로드 ticket routes (issue / complete).

per-file ticket 을 발급/확정하는 order-mutation 라우트. 권한은 FILE-01 ``upload_authz``
category 정책을 **in-handler** 로 재검사(:func:`category_upload_allowed` → 기존
``STAFF_MUTATION``/``DRAWING_TEAM``/``CONSTRUCTION_EDIT`` 정책 재사용)하고, 공용 write guard
(:func:`~foms.services.request_write_guard.enforce_csrf_origin`)와 정책 가드가 before_request
로 함께 enforce 한다(UPLOAD-INTENT-01 route 와 동일 관례). 발급/확정 로직·server-derived
key·재검사·tamper/expiry/type/size 는 :mod:`foms.services.orders.upload_ticket` 가 소유하고
이 모듈은 HTTP 배선만 한다.

정책 등재(오케스트레이터): 두 endpoint 는 order_mutation_policy manifest 에 ``STAFF_MUTATION``
로 등재된다(coarse gate = VIEWER deny + STAFF 허용; category 별 세부 권한은 handler 가
재검사). write_guard manifest 에는 exempt 로 넣지 않는다(정상 CSRF 보호 대상).
"""
from __future__ import annotations

from flask import jsonify, request, session

from db import get_db
from foms.api.files.blueprint import attachments_bp
from foms.api.files.common import parse_attachment_item_index, resolve_attachment_category
from foms.services.files.upload_authz import category_upload_allowed
from foms.services.orders.upload_ticket import (
    UploadTicketError,
    UploadTicketForbidden,
    complete_ticket,
    issue_ticket,
)
from foms.web.auth import get_user_by_id, login_required
from models import Order, UploadTicket


def _current_user():
    """세션 user_id 로 현재 사용자 로드(권한 판정용)."""
    uid = session.get("user_id")
    return get_user_by_id(uid) if uid else None


def _serialize_ticket(ticket: UploadTicket) -> dict:
    """UploadTicket 을 API 응답 dict 로 직렬화한다."""
    return {
        "id": ticket.id,
        "order_id": ticket.order_id,
        "category": ticket.category,
        "item_id": ticket.item_id,
        "item_index": ticket.item_index,
        "object_key": ticket.object_key,
        "filename": ticket.filename,
        "file_type": ticket.file_type,
        "file_size": ticket.file_size,
        "state": ticket.state,
        "expires_at": ticket.expires_at.isoformat() if ticket.expires_at else None,
    }


@attachments_bp.route("/orders/<int:order_id>/upload-tickets", methods=["POST"])
@login_required
def api_issue_upload_ticket(order_id):
    """per-file 업로드 ticket 발급(ISSUED, 900s, server-derived key)."""
    db = get_db()
    try:
        data = request.get_json(silent=True) or {}
        filename = data.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            return jsonify({"success": False, "data": None, "error": "filename이 필요합니다."}), 400
        try:
            file_size = int(data.get("size"))
        except (TypeError, ValueError):
            return jsonify({"success": False, "data": None, "error": "size가 필요합니다."}), 400
        category = resolve_attachment_category("", data.get("category", "measurement"))
        ok, item_index, err = parse_attachment_item_index(data.get("item_index"))
        if not ok:
            return jsonify({"success": False, "data": None, "error": err}), 400

        user = _current_user()
        # in-handler evaluate_policy(기존 category 정책 재사용) — VIEWER/무권한 403.
        if not category_upload_allowed(user, category):
            return jsonify({"success": False, "data": None, "error": "이 업로드를 수행할 권한이 없습니다."}), 403
        if db.query(Order).filter(Order.id == order_id).first() is None:
            return jsonify({"success": False, "data": None, "error": "주문을 찾을 수 없습니다."}), 404

        ticket = issue_ticket(
            db, order_id=order_id, filename=filename, file_size=file_size,
            user=user, category=category, item_index=item_index,
        )
        db.commit()
        return jsonify({"success": True, "data": _serialize_ticket(ticket), "error": None})
    except UploadTicketForbidden as e:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 403
    except UploadTicketError as e:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 400
    # 예기치 못한 예외는 그대로 전파한다 — 공용 error handler 가 INTERNAL_ERROR JSON 으로
    # 담고 teardown_appcontext(close_db) 가 scoped session 을 rollback 한다(str(e) 미노출).


@attachments_bp.route("/upload-tickets/<int:ticket_id>/complete", methods=["POST"])
@login_required
def api_complete_upload_ticket(ticket_id):
    """ISSUED ticket 을 확정해 첨부로 소비(재검사·tamper/expiry/type/size, retry idempotent)."""
    db = get_db()
    try:
        data = request.get_json(silent=True) or {}
        object_key = data.get("key")
        if not isinstance(object_key, str) or not object_key.strip():
            return jsonify({"success": False, "data": None, "error": "key가 필요합니다."}), 400
        file_size = None
        if data.get("size") is not None:
            try:
                file_size = int(data.get("size"))
            except (TypeError, ValueError):
                return jsonify({"success": False, "data": None, "error": "size가 유효하지 않습니다."}), 400

        # auth 재검사는 ticket.category 를 알아야 하므로 complete_ticket(service)가 in-handler
        # 로 수행한다(category_upload_allowed) — 공용 정책/write guard 가 before_request 로 보강.
        ticket, attachment = complete_ticket(
            db, ticket_id=ticket_id, object_key=object_key,
            user=_current_user(), file_size=file_size,
        )
        db.commit()
        return jsonify({
            "success": True,
            "data": {"ticket": _serialize_ticket(ticket), "attachment_id": attachment.id},
            "error": None,
        })
    except UploadTicketForbidden as e:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 403
    except UploadTicketError as e:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 400
    # 예기치 못한 예외는 그대로 전파한다 — 공용 error handler 가 INTERNAL_ERROR JSON 으로
    # 담고 teardown_appcontext(close_db) 가 scoped session 을 rollback 한다(str(e) 미노출).


__all__ = [
    "api_complete_upload_ticket",
    "api_issue_upload_ticket",
]
