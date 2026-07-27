"""UPLOAD-INTENT-01: pre-file upload DRAFT routes (create / cancel / finalize).

파일 업로드 전에 DRAFT id 를 발급/취소/확정하는 order-mutation 라우트. 권한은 kind →
FILE-01 ``upload_authz`` category 로 매핑해 재사용(drawing_revision=도면, as_cycle=시공/AS).
정책 gate 는 order_mutation_policy manifest 의 ``STAFF_MUTATION`` 로 등재된다(kind 별 세부
권한은 handler 가 :func:`category_upload_allowed` 로 재검사). 수명주기 로직은
:mod:`foms.services.orders.upload_intent` 가 소유하고 이 모듈은 HTTP 배선만 한다.
"""
from __future__ import annotations

from flask import jsonify, request, session

from db import get_db
from foms.api.files.blueprint import attachments_bp
from foms.services.error_logging import log_handled_exception
from foms.services.files.upload_authz import category_upload_allowed
from foms.services.orders.upload_intent import (
    UploadDraftError,
    cancel_upload_draft,
    create_upload_draft,
    effective_state,
    finalize_upload_draft,
)
from foms.web.auth import get_user_by_id, login_required
from models import UPLOAD_DRAFT_KINDS, Order, UploadDraft

#: kind → upload_authz category(권한 재사용). drawing_revision=도면, as_cycle=시공/AS.
_KIND_CATEGORY = {"drawing_revision": "drawing", "as_cycle": "as"}


def _current_user():
    """세션 user_id 로 현재 사용자 로드(권한 판정용)."""
    uid = session.get("user_id")
    return get_user_by_id(uid) if uid else None


def _serialize(draft: UploadDraft) -> dict:
    """DRAFT 를 API 응답 dict 로 직렬화(effective_state 로 lazy 만료 반영)."""
    return {
        "id": draft.id,
        "order_id": draft.order_id,
        "kind": draft.kind,
        "state": effective_state(draft),
        "object_keys": draft.object_keys or [],
        "expires_at": draft.expires_at.isoformat() if draft.expires_at else None,
    }


@attachments_bp.route("/orders/<int:order_id>/upload-drafts", methods=["POST"])
@login_required
def api_create_upload_draft(order_id):
    """파일 업로드 전 DRAFT id 발급(멱등). Order 불변."""
    db = get_db()
    try:
        data = request.get_json(silent=True) or {}
        kind = data.get("kind")
        if kind not in UPLOAD_DRAFT_KINDS:
            return jsonify({"success": False, "data": None, "error": "허용되지 않은 kind입니다."}), 400
        if not category_upload_allowed(_current_user(), _KIND_CATEGORY.get(kind)):
            return jsonify({"success": False, "data": None, "error": "이 업로드를 수행할 권한이 없습니다."}), 403
        if db.query(Order).filter(Order.id == order_id).first() is None:
            return jsonify({"success": False, "data": None, "error": "주문을 찾을 수 없습니다."}), 404

        idem = data.get("idempotency_key")
        draft = create_upload_draft(
            db, order_id=order_id, kind=kind,
            created_by_user_id=session.get("user_id"),
            idempotency_key=idem if isinstance(idem, str) and idem.strip() else None,
        )
        db.commit()
        return jsonify({"success": True, "data": _serialize(draft), "error": None})
    except UploadDraftError as e:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 - 상위에서 500 JSON 으로 감싼다
        db.rollback()
        log_handled_exception()
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


def _authorize_draft(draft: UploadDraft):
    """DRAFT kind 에 대한 업로드 권한(category_upload_allowed) 재검사 → 실패 시 403 응답."""
    if not category_upload_allowed(_current_user(), _KIND_CATEGORY.get(draft.kind)):
        return jsonify({"success": False, "data": None, "error": "이 업로드를 수행할 권한이 없습니다."}), 403
    return None


@attachments_bp.route("/upload-drafts/<int:draft_id>/cancel", methods=["POST"])
@login_required
def api_cancel_upload_draft(draft_id):
    """DRAFT 를 CANCELLED(terminal)로 마크(멱등). Order 불변."""
    db = get_db()
    try:
        draft = db.get(UploadDraft, draft_id)
        if draft is None:
            return jsonify({"success": False, "data": None, "error": "DRAFT를 찾을 수 없습니다."}), 404
        denied = _authorize_draft(draft)
        if denied is not None:
            return denied
        draft = cancel_upload_draft(db, draft_id)
        db.commit()
        return jsonify({"success": True, "data": _serialize(draft), "error": None})
    except UploadDraftError as e:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log_handled_exception()
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


@attachments_bp.route("/upload-drafts/<int:draft_id>/finalize", methods=["POST"])
@login_required
def api_finalize_upload_draft(draft_id):
    """DRAFT 확정(FINALIZED) — final command 만 Order version 1회 bump(REV-00)."""
    db = get_db()
    try:
        draft = db.get(UploadDraft, draft_id)
        if draft is None:
            return jsonify({"success": False, "data": None, "error": "DRAFT를 찾을 수 없습니다."}), 404
        denied = _authorize_draft(draft)
        if denied is not None:
            return denied
        draft = finalize_upload_draft(db, draft_id)
        db.commit()
        return jsonify({"success": True, "data": _serialize(draft), "error": None})
    except UploadDraftError as e:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log_handled_exception()
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


__all__ = [
    "api_cancel_upload_draft",
    "api_create_upload_draft",
    "api_finalize_upload_draft",
]
