"""PARTNER-02: 협력사 화면 JSON API — 주문 등록 · 파일 올리기.

모든 엔드포인트는 ``partner_required`` (활성 협력사 계정만) + 주문마다 ``partner_can_read_order``
(자기 협력사 주문만)를 지난다. 기존 업로드 API(``/api/upload/session`` 등)는 주문 범위 판정이
없어 협력사에게 열지 않는다 — 여기서 서버가 폴더·분류를 정한다.
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §5.1
"""
from __future__ import annotations

import os

from flask import Blueprint, g, jsonify, request, session

from db import get_db
from foms.api.files.blueprint import ASYNC_ATTACHMENT_THUMBNAIL
from foms.api.files.common import DRAWING_ATTACHMENT_EXTRA_EXTENSIONS, get_erp_media_max_size
from foms.api.files.order_routes import ATTACHMENT_ADDED, emit_attachment_event
from foms.services.auth.partner_scope import partner_can_read_order, partner_required
from foms.services.common.dashboard_cache import (
    ATTACHMENT_DASHBOARD_FAMILIES,
    invalidate_dashboard_families,
)
from foms.services.error_logging import log_handled_exception
from foms.services.files.upload_policy import ERP_MEDIA_ALLOWED_EXTENSIONS
from foms.services.order_attachment_thumbnail import schedule_order_attachment_thumbnail_generation
from foms.services.partners.orders import PartnerOrderError, create_partner_order
from foms.services.storage import get_storage
from models import Order, OrderAttachment, PartnerOrg

partner_api_bp = Blueprint("partner_api", __name__, url_prefix="/api/partner")

# 협력사가 파일을 더 올릴 수 있는 단계 — 우리 CS 가 도면으로 넘기기 전까지.
UPLOAD_OPEN_STAGES = frozenset({"RECEIVED", "MEASURE"})

# kind → (첨부 분류, 폴더 이름, 허용 확장자). 폴더 이름은 원본 보존 판정
# (order_attachment_permissions.PARTNER_ORIGINAL_FOLDERS)과 같아야 한다.
_KINDS = {
    "photo": ("measurement", "partner_measurement", frozenset(ERP_MEDIA_ALLOWED_EXTENSIONS)),
    "draft": (
        "drawing",
        "partner_draft",
        frozenset(ERP_MEDIA_ALLOWED_EXTENSIONS) | frozenset(DRAWING_ATTACHMENT_EXTRA_EXTENSIONS),
    ),
}


def _fail(message: str, status: int):
    return jsonify({"success": False, "data": None, "error": message}), status


def _own_order(db, order_id: int) -> Order | None:
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    return order if partner_can_read_order(g.current_user, order) else None


@partner_api_bp.route("/orders", methods=["POST"])
@partner_required
def create_order():
    """협력사 주문 등록. 본문 JSON — :func:`create_partner_order` 참조."""
    db = get_db()
    user = g.current_user
    org = db.query(PartnerOrg).filter(PartnerOrg.id == user.partner_org_id).first()
    try:
        order = create_partner_order(db, user, org, request.get_json(silent=True))
        db.commit()
    except PartnerOrderError as exc:
        db.rollback()
        return _fail(str(exc), 400)
    return jsonify({"success": True, "data": {"order_id": order.id}, "error": None})


@partner_api_bp.route("/orders/<int:order_id>/files", methods=["POST"])
@partner_required
def upload_file(order_id: int):
    """파일 1개 올리기(multipart: ``file``, ``kind`` = photo | draft)."""
    db = get_db()
    order = _own_order(db, order_id)
    if order is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    if (order.erp_stage_code or "").upper() not in UPLOAD_OPEN_STAGES:
        return _fail("도면 작업이 시작된 주문에는 파일을 더 올릴 수 없습니다. 담당자에게 보내 주세요.", 409)
    kind = _KINDS.get((request.form.get("kind") or "").strip())
    if kind is None:
        return _fail("파일 종류(사진/초안 도면)를 골라 주세요.", 400)
    category, folder_name, allowed_exts = kind
    file = request.files.get("file")
    if not file or not file.filename:
        return _fail("파일이 없습니다.", 400)
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed_exts:
        return _fail(f"올릴 수 없는 파일 형식입니다. 가능: {', '.join(sorted(allowed_exts))}", 400)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    max_size = get_erp_media_max_size(file.filename)
    if file_size > max_size:
        return _fail(f"파일이 너무 큽니다. 최대 {max_size // (1024 * 1024)}MB 입니다.", 400)

    storage = get_storage()
    folder = f"orders/{order.id}/{folder_name}"
    result = storage.upload_file(file, file.filename, folder)
    if not result.get("success"):
        return _fail("파일을 올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.", 502)
    storage_key = result.get("key")
    file_type = storage.get_file_type(file.filename)
    try:
        attachment = OrderAttachment(
            order_id=order.id,
            filename=file.filename,
            file_type=file_type,
            category=category,
            file_size=file_size,
            storage_key=storage_key,
            thumbnail_key=None,
            user_id=session.get("user_id"),
        )
        db.add(attachment)
        emit_attachment_event(db, attachment, ATTACHMENT_ADDED)
        db.commit()
    except Exception:
        db.rollback()
        log_handled_exception("partner upload attachment row")
        return _fail("파일 기록을 남기지 못했습니다. 다시 시도해 주세요.", 500)
    invalidate_dashboard_families(*ATTACHMENT_DASHBOARD_FAMILIES)
    if ASYNC_ATTACHMENT_THUMBNAIL and file_type == "image" and storage_key:
        schedule_order_attachment_thumbnail_generation(attachment.id, storage_key)
    return jsonify({
        "success": True,
        "data": {"attachment_id": attachment.id, "filename": attachment.filename, "kind": folder_name},
        "error": None,
    })
