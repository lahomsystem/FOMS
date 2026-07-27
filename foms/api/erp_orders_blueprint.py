"""도면(blueprint) 이미지 API — BLUEPRINT-01 정본(P0-11 remediation).

legacy route(P0-11)는 (1) ``@login_required`` 만으로 열려 있었고(exact order policy 없음),
(2) direct R2 업로드 후 ``order.blueprint_image_url`` scalar 를 **직접 썼으며**(version/event
없음), (3) direct-upload complete 는 client key 를 **substring** 으로만 검사했고, (4) 삭제는
동기였다. 이 모듈은 네 가지를 정본화한다:

* **exact order policy**: 모든 write 를 in-handler :func:`evaluate_policy` (``STAFF_MUTATION``)
  로 재검사한다(login-only 아님). VIEWER/무권한은 403.
* **ORDER_BLUEPRINT ticket(UPLOAD-02)**: 업로드는 direct R2 대신 per-file ticket(issue →
  presigned PUT → complete)로 한다. object key 는 **서버가 유도** 하고 complete 는 ticket 의
  key 와 **exact-match** 로 tamper 를 검사한다(substring 검사 금지).
* **current projection version/event**: 저장/삭제는 :mod:`blueprint_projection` typed
  current projection 으로 하며 version bump(complete_ticket REV-00 / REV-00 mutation)·
  OrderEvent 를 동반한다(scalar direct write 금지 — scalar 는 병행 파생 projection).
* **typed replace / delete outbox**: 교체·삭제 시 이전 R2 object 는 ``STORAGE_DELETE`` outbox
  로 예약한다(동기 R2 삭제 금지).

읽기(GET)는 projection 을 우선 읽고 scalar 로 폴백해 read 소비처 무회귀를 보장한다.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional, Tuple

from flask import Blueprint, jsonify, request, session

from db import get_db
from foms.services.error_logging import log_handled_exception
from foms.services.orders.blueprint_projection import (
    clear_current_blueprint,
    get_current_blueprint,
    set_current_blueprint,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import execute_order_mutation
from foms.services.orders.upload_ticket import (
    UploadTicketError,
    UploadTicketForbidden,
    complete_ticket,
    issue_ticket,
)
from foms.services.storage import get_storage
from foms.web.auth import get_user_by_id, login_required
from models import Order

logger = logging.getLogger(__name__)

# blueprint 업로드는 도면 파일이지만 서버 category 열거(measurement/drawing/construction/as)에
# 'blueprint' 가 없고 blueprint 폴더는 resolve_attachment_category 가 이미 measurement 로
# 매핑한다(공유 category 체계 무변경). all-STAFF 권한(STAFF_MUTATION)과도 일치하므로 ticket
# category 는 measurement 로 발급하고, blueprint 정체성은 typed projection·event 가 담는다.
_TICKET_CATEGORY = "measurement"
_POLICY = POLICY_REGISTRY["STAFF_MUTATION"]
_GENERIC_ERROR = "요청을 처리하는 중 오류가 발생했습니다."

erp_orders_blueprint_bp = Blueprint('erp_orders_blueprint', __name__, url_prefix='/api')


def _current_user() -> Any:
    """세션 user_id 로 현재 사용자 로드(권한 판정용)."""
    uid = session.get("user_id")
    return get_user_by_id(uid) if uid else None


def _err(message: str, status: int):
    """{success,data,error} 실패 응답."""
    return jsonify({"success": False, "data": None, "error": message}), status


def _require_policy() -> Tuple[Optional[Any], Optional[Any]]:
    """in-handler exact order policy(STAFF_MUTATION) 재검사. (user, error_response) 반환."""
    user = _current_user()
    decision = evaluate_policy(_POLICY, user)
    if not decision.allowed:
        return None, _err(decision.reason, decision.status)
    return user, None


@erp_orders_blueprint_bp.route('/orders/<int:order_id>/blueprint', methods=['POST'])
@login_required
def api_upload_blueprint(order_id):
    """ORDER_BLUEPRINT 업로드 ticket 발급(server-derived key + presigned PUT)."""
    db = get_db()
    user, denied = _require_policy()
    if denied:
        return denied
    try:
        data = request.get_json(silent=True) or {}
        filename = data.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            return _err("filename이 필요합니다.", 400)
        try:
            file_size = int(data.get("size"))
        except (TypeError, ValueError):
            return _err("size가 필요합니다.", 400)
        if db.query(Order).filter(Order.id == order_id).first() is None:
            return _err("주문을 찾을 수 없습니다.", 404)

        ticket = issue_ticket(
            db, order_id=order_id, filename=filename, file_size=file_size,
            user=user, category=_TICKET_CATEGORY,
        )
        put_url = get_storage().generate_presigned_put_url(
            ticket.object_key, _content_type(filename))
        db.commit()
        return jsonify({"success": True, "error": None, "data": {
            "ticket_id": ticket.id, "key": ticket.object_key,
            "presigned_put_url": put_url,
            "expires_at": ticket.expires_at.isoformat() if ticket.expires_at else None,
        }})
    except UploadTicketForbidden as e:
        db.rollback()
        return _err(str(e), 403)
    except UploadTicketError as e:
        db.rollback()
        return _err(str(e), 400)
    except Exception:
        db.rollback()
        log_handled_exception()
        return _err(_GENERIC_ERROR, 500)


@erp_orders_blueprint_bp.route('/orders/<int:order_id>/blueprint/complete', methods=['POST'])
@login_required
def api_blueprint_complete(order_id):
    """업로드 ticket 을 확정(exact key)하고 current blueprint projection 으로 설정한다."""
    db = get_db()
    user, denied = _require_policy()
    if denied:
        return denied
    try:
        data = request.get_json(silent=True) or {}
        try:
            ticket_id = int(data.get("ticket_id"))
        except (TypeError, ValueError):
            return _err("ticket_id가 필요합니다.", 400)
        key = data.get("key")
        if not isinstance(key, str) or not key.strip():
            return _err("key가 필요합니다.", 400)

        ticket, attachment = complete_ticket(
            db, ticket_id=ticket_id, object_key=key, user=user)
        if ticket.order_id != order_id:  # exact order: ticket 이 이 주문 소속이어야 한다.
            db.rollback()
            return _err("대상 주문과 일치하지 않는 ticket입니다.", 400)

        order = db.query(Order).filter(Order.id == order_id).first()
        current = set_current_blueprint(
            db, order, attachment=attachment, actor_user_id=getattr(user, "id", None))
        db.commit()
        return jsonify({"success": True, "error": None, "url": current["view_url"], "data": {
            "url": current["view_url"], "attachment_id": attachment.id, "ticket_id": ticket.id,
        }})
    except UploadTicketForbidden as e:
        db.rollback()
        return _err(str(e), 403)
    except UploadTicketError as e:
        db.rollback()
        return _err(str(e), 400)
    except Exception:
        db.rollback()
        log_handled_exception()
        return _err(_GENERIC_ERROR, 500)


@erp_orders_blueprint_bp.route('/orders/<int:order_id>/blueprint', methods=['GET'])
@login_required
def api_get_blueprint(order_id):
    """current blueprint 이미지 URL 조회(projection 우선·scalar 폴백)."""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return _err("주문을 찾을 수 없습니다.", 404)
        current = get_current_blueprint(order)
        url = (current or {}).get("view_url") or (order.blueprint_image_url or None)
        return jsonify({"success": True, "url": url})
    except Exception:
        log_handled_exception()
        return _err(_GENERIC_ERROR, 500)


@erp_orders_blueprint_bp.route('/orders/<int:order_id>/blueprint', methods=['DELETE'])
@login_required
def api_delete_blueprint(order_id):
    """current blueprint projection 삭제 + 이전 object STORAGE_DELETE outbox(REV-00 version)."""
    db = get_db()
    user, denied = _require_policy()
    if denied:
        return denied
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return _err("주문을 찾을 수 없습니다.", 404)
        if get_current_blueprint(order) is None and not order.blueprint_image_url:
            return jsonify({"success": True, "error": None, "data": {"removed": False}})

        uid = getattr(user, "id", None)
        scope = hashlib.sha256(f"blueprint-delete:{order_id}".encode()).hexdigest()

        def _mutate(sess, locked):
            clear_current_blueprint(sess, locked[0], actor_user_id=uid)
            return {locked[0].id: [f"ORDER_DETAIL:{order_id}"]}

        result = execute_order_mutation(
            db, actor_user_id=uid, policy_id="STAFF_MUTATION", order_ids=[order_id],
            scope_hash=scope, request_hash=scope, mutation=_mutate,
        )
        db.commit()
        resp = jsonify({"success": True, "error": None, "data": {
            "removed": True, "mutation_receipt": result.read_receipt_id}})
        for k, v in result.headers.items():
            resp.headers[k] = v
        return resp
    except Exception:
        db.rollback()
        log_handled_exception()
        return _err(_GENERIC_ERROR, 500)


def _content_type(filename: str) -> str:
    """확장자 → 이미지 Content-Type(presigned PUT 서명용, 미상은 octet-stream)."""
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "webp": "image/webp",
    }.get(ext, "application/octet-stream")
