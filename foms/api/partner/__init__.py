"""PARTNER-02: 협력사 화면 JSON API — 주문 등록 · 파일 올리기.

모든 엔드포인트는 ``partner_required`` (활성 협력사 계정만) + 주문마다 ``partner_can_read_order``
(자기 협력사 주문만)를 지난다. 기존 업로드 API(``/api/upload/session`` 등)는 주문 범위 판정이
없어 협력사에게 열지 않는다 — 여기서 서버가 폴더·분류를 정한다.
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §5.1
"""
from __future__ import annotations

import os

from flask import Blueprint, Response, g, jsonify, request, session

from db import get_db
from foms.api.files.blueprint import ASYNC_ATTACHMENT_THUMBNAIL
from foms.api.files.common import DRAWING_ATTACHMENT_EXTRA_EXTENSIONS, get_erp_media_max_size
from foms.api.files.order_routes import ATTACHMENT_ADDED, emit_attachment_event
from foms.api.notifications import invalidate_badge_cache_for_user_ids, resolve_notification_recipient_user_ids
from foms.services.auth.partner_scope import partner_can_read_order, partner_required
from foms.services.common.dashboard_cache import (
    ATTACHMENT_DASHBOARD_FAMILIES,
    DASHBOARD_FAMILY_ORDERS,
    invalidate_dashboard_families,
)
from foms.services.error_logging import log_handled_exception
from foms.services.files.upload_policy import ERP_MEDIA_ALLOWED_EXTENSIONS
from foms.services.order_attachment_thumbnail import schedule_order_attachment_thumbnail_generation
from foms.services.orders.order_transition_service import TransitionError
from foms.services.orders.revision import RevisionError
from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
from foms.services.orders.as_cycle_service import ASCycleError
from foms.services.orders.drawing_gate_followups import invalidate_after_drawing_revision
from foms.services.partners.as_intake import PartnerASError, register_partner_as
from foms.services.partners.drawing_confirm import PartnerConfirmError, approve_partner_drawing
from foms.services.partners.revision import REVISION_FOLDER, PartnerRevisionError, request_partner_revision
from foms.services.partners.logo import partner_org_of, read_partner_logo
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
    # 받는 사람(CS 팀 + 담당 영업)의 벨 배지를 바로 갱신한다.
    recipients = set(resolve_notification_recipient_user_ids(
        db, target_team="CS", target_manager_name=None, include_admin=False))
    if org.owner_user_id:
        recipients.add(int(org.owner_user_id))
    invalidate_badge_cache_for_user_ids(recipients)
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


@partner_api_bp.route("/orders/<int:order_id>/approve-drawing", methods=["POST"])
@partner_required
def approve_drawing(order_id: int):
    """"이대로 만들어 주세요" — 고객컨펌 승인 → 생산(:func:`approve_partner_drawing`)."""
    db = get_db()
    payload = request.get_json(silent=True) or {}
    key = str(payload.get("idempotency_key") or request.headers.get("Idempotency-Key") or "")[:64] or None
    try:
        approve_partner_drawing(db, g.current_user, order_id, idempotency_key=key)
        db.commit()
    except PartnerConfirmError as exc:
        db.rollback()
        return _fail(str(exc), exc.status)
    except (TransitionError, RevisionError):
        db.rollback()
        log_handled_exception("partner approve drawing transition")
        return _fail("지금은 처리할 수 없습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.", 409)
    invalidate_dashboard_families(DASHBOARD_FAMILY_ORDERS)
    return jsonify({"success": True, "data": {"order_id": order_id}, "error": None})


MAX_PHOTOS = 10
_PHOTO_EXTS = frozenset({"jpg", "jpeg", "png", "webp", "heic", "gif"})


def _upload_photos(order_id: int, folder: str) -> list[dict]:
    """요청의 ``photos`` 를 검사해 서버에서 올린다. 반환 ``[{key, filename, file_type, size}]``.

    Raises:
        PartnerRevisionError: 형식·크기·개수 위반(400) — 호출자가 메시지를 그대로 보여 준다.
    """
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if len(files) > MAX_PHOTOS:
        raise PartnerRevisionError(f"사진은 {MAX_PHOTOS}장까지 올릴 수 있습니다.", 400)
    storage = get_storage()
    out = []
    for f in files:
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in _PHOTO_EXTS:
            raise PartnerRevisionError("사진(jpg · png · webp)만 올릴 수 있습니다.", 400)
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
        if size > get_erp_media_max_size(f.filename):
            raise PartnerRevisionError("사진이 너무 큽니다.", 400)
        result = storage.upload_file(f, f.filename, f"orders/{order_id}/{folder}")
        if not result.get("success"):
            raise PartnerRevisionError("사진을 올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.", 502)
        out.append({"key": result.get("key"), "filename": f.filename,
                    "file_type": storage.get_file_type(f.filename), "size": size})
    return out


@partner_api_bp.route("/orders/<int:order_id>/revision", methods=["POST"])
@partner_required
def request_revision(order_id: int):
    """도면 수정 요청(multipart: ``note``, ``photos``) — 직원 수정 요청과 같은 효과."""
    db = get_db()
    if _own_order(db, order_id) is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    try:
        photos = _upload_photos(order_id, REVISION_FOLDER)
        notification = request_partner_revision(
            db, g.current_user, order_id, request.form.get("note"),
            [{"key": p["key"], "filename": p["filename"]} for p in photos],
        )
        db.commit()
    except PartnerRevisionError as exc:
        db.rollback()
        return _fail(str(exc), exc.status)
    except RevisionError:
        db.rollback()
        log_handled_exception("partner revision request")
        return _fail("지금은 처리할 수 없습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.", 409)
    # 커밋 뒤: 직원 수정 요청과 같은 알림 경로(웹 푸시 · 배지 · 도면팀 확인 창).
    enqueue_push_for_notification(notification.id, db=db)
    recipients = resolve_notification_recipient_user_ids(
        db, target_team="DRAWING", target_manager_name=None, include_admin=True)
    invalidate_badge_cache_for_user_ids(recipients)
    order = db.query(Order).filter(Order.id == order_id).first()
    invalidate_after_drawing_revision(order)
    emit_erp_notification_to_users(recipients, {
        "notification_id": notification.id,
        "order_id": order_id,
        "notification_type": "DRAWING_REVISION",
        "title": notification.title,
        "message": notification.message,
        "created_by_name": notification.created_by_name,
        "interrupt": True,
    })
    return jsonify({"success": True, "data": {"order_id": order_id}, "error": None})


@partner_api_bp.route("/orders/<int:order_id>/as", methods=["POST"])
@partner_required
def register_as(order_id: int):
    """AS 접수(multipart: ``content``, ``photos``). 사진은 접수 원문 줄(as_log_id)에 붙는다."""
    db = get_db()
    if _own_order(db, order_id) is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    key = (request.form.get("idempotency_key") or "")[:64] or None
    try:
        reception_id = register_partner_as(db, g.current_user, order_id, request.form.get("content"),
                                           idempotency_key=key)
        db.commit()
    except PartnerASError as exc:
        db.rollback()
        return _fail(str(exc), exc.status)
    except (ASCycleError, RevisionError):
        db.rollback()
        log_handled_exception("partner AS register")
        return _fail("지금은 처리할 수 없습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.", 409)
    invalidate_dashboard_families(DASHBOARD_FAMILY_ORDERS)
    # 사진은 접수가 확정된 뒤 붙인다 — 사진이 실패해도 AS 접수는 남는다(화면이 알려 준다).
    try:
        photos = _upload_photos(order_id, "as")
    except PartnerRevisionError as exc:
        return jsonify({"success": True, "data": {"order_id": order_id, "photo_error": str(exc)}, "error": None})
    for p in photos:
        attachment = OrderAttachment(
            order_id=order_id, filename=p["filename"], file_type=p["file_type"], category="as",
            as_log_id=reception_id, file_size=p["size"], storage_key=p["key"], thumbnail_key=None,
            user_id=session.get("user_id"),
        )
        db.add(attachment)
        emit_attachment_event(db, attachment, ATTACHMENT_ADDED)
    db.commit()
    if photos:
        invalidate_dashboard_families(*ATTACHMENT_DASHBOARD_FAMILIES)
    return jsonify({"success": True, "data": {"order_id": order_id, "photos": len(photos)}, "error": None})


@partner_api_bp.route("/orders/<int:order_id>/logo", methods=["GET"])
def order_logo(order_id: int):
    """협력사 주문 도면에 넣을 협력사 로고 — **우리 직원용**(도면 마법사가 같은 출처로 읽는다).

    도면 PNG 는 html2canvas 로 만들어져 R2 서명 URL(다른 출처) 이미지는 빠진다. 그래서 앱이 바이트를
    직접 내준다. 협력사 세션은 문지기 허용 목록 밖이라 여기 오지 못한다. key 는 DB 값만 쓴다.
    """
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return _fail("로그인이 필요합니다.", 401)
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id).first()
    org = partner_org_of(db, order) if order is not None else None
    found = read_partner_logo(get_storage(), org)
    if found is None:
        return _fail("로고가 없습니다.", 404)
    data, mimetype = found
    response = Response(data, mimetype=mimetype)
    response.headers["Cache-Control"] = "private, max-age=600"
    return response
