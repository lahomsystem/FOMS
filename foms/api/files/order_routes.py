"""Order attachment CRUD routes.

ATTACH-LIFE-01(T4): 첨부 삭제는 **hard delete + R2 즉시삭제**가 아니라 tombstone
(``deleted_at``) + :class:`~models.OrderEvent` + ``STORAGE_DELETE`` outbox 지연삭제다.
업로드/메타수정/삭제/복구 4 경로가 모두 ``ATTACHMENT_*`` 이벤트를 남긴다(이전에는 기록 0).
"""

import datetime
import os
from typing import Any, Optional

from foms.services.error_logging import log_handled_exception

from flask import has_request_context, jsonify, request, session

from foms.web.auth import get_user_by_id, log_access, login_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.api.files.blueprint import (
    ASYNC_ATTACHMENT_THUMBNAIL,
    attachments_bp,
)
from foms.api.files.common import (
    DRAWING_ATTACHMENT_EXTRA_EXTENSIONS,
    allowed_erp_attachment_file,
    get_erp_media_max_size,
    normalize_attachment_category,
    parse_attachment_item_index,
    serialize_attachment,
)
from db import get_db
from foms.services.attachment_visibility import include_deleted
from foms.services.datetime_kst import now_utc_naive
from foms.services.files.upload_authz import category_upload_allowed
from foms.services.files.upload_policy import ERP_MEDIA_ALLOWED_EXTENSIONS
from foms.services.order_attachment_thumbnail import (
    schedule_order_attachment_thumbnail_generation,
)
from foms.services.order_attachment_permissions import (
    can_delete_order_attachment,
    can_manage_order_attachments,
    can_modify_order_attachment,
)
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.storage import get_storage
from models import DomainSideEffectOutbox, Order, OrderAttachment, OrderEvent

#: 첨부 수명주기 이벤트 타입(라벨은 foms/services/order_event_display.py 소유).
ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
ATTACHMENT_DELETED = "ATTACHMENT_DELETED"
ATTACHMENT_META_UPDATED = "ATTACHMENT_META_UPDATED"
ATTACHMENT_RESTORED = "ATTACHMENT_RESTORED"

#: SIDEFX outbox effect_type(공용 handler: foms/services/storage_delete_handler.py).
STORAGE_DELETE = "STORAGE_DELETE"

#: tombstone 후 R2 blob 을 실제로 지우기까지의 유예. 이 기간 안에는 복구 API 가 outbox
#: 예약을 취소하고 첨부를 되살릴 수 있다(유예가 지나 worker 가 집어가면 복구 불가).
ATTACHMENT_PURGE_GRACE = datetime.timedelta(days=7)

_TRUTHY = ("1", "true", "yes", "on")


def _current_user():
    """Load the logged-in user from session."""
    current_user_id = session.get("user_id")
    return get_user_by_id(current_user_id) if current_user_id else None


def _actor_user_id() -> Optional[int]:
    """이벤트 actor(로그인 사용자 id). 요청 밖(스크립트/워커)에서는 None."""
    if not has_request_context():
        return None
    return session.get("user_id")


def emit_attachment_event(
    db: Any,
    attachment: OrderAttachment,
    event_type: str,
    *,
    extra: Optional[dict] = None,
) -> OrderEvent:
    """첨부 수명주기 :class:`~models.OrderEvent` 1건을 남기고 id 를 확보한다.

    Args:
        db: 호출자가 소유한 세션(커밋 미수행 — flush 만 한다).
        attachment: 대상 첨부(신규 업로드면 이 함수의 flush 로 id 가 채워진다).
        event_type: ``ATTACHMENT_ADDED``/``DELETED``/``META_UPDATED``/``RESTORED``.
        extra: payload 에 덧붙일 키(예: item_index from/to).

    Returns:
        flush 되어 ``id`` 가 채워진 :class:`~models.OrderEvent`.
    """
    db.flush()  # 신규 첨부의 id 확보(payload·outbox FK source 가 id 를 요구한다)
    payload = {
        "attachment_id": attachment.id,
        "storage_key": attachment.storage_key,
        "thumbnail_key": attachment.thumbnail_key,
        "filename": attachment.filename,
        "category": attachment.category,
    }
    if extra:
        payload.update(extra)
    event = OrderEvent(
        order_id=attachment.order_id,
        event_type=event_type,
        payload=payload,
        created_by_user_id=_actor_user_id(),
        created_at=now_utc_naive(),
    )
    db.add(event)
    db.flush()
    _audit_attachment_event(db, attachment, event_type)
    return event


#: 첨부 수명주기 이벤트 → 감사 행위 코드. ``META_UPDATED`` 는 매핑하지 않는다 —
#: 항목 재배치는 ``order_events`` 로 충분하고 보안 원장까지 도배할 가치가 없다
#: (스펙 §3-3 "물어볼 수 있는 행위만 기록").
_ATTACHMENT_AUDIT_ACTIONS = {
    ATTACHMENT_ADDED: "FILE_UPLOADED",
    ATTACHMENT_DELETED: "FILE_DELETED",
    ATTACHMENT_RESTORED: "FILE_RESTORED",
}


def _audit_attachment_event(db: Any, attachment: OrderAttachment, event_type: str) -> None:
    """첨부 업로드/삭제/복구를 구조화 감사로 남긴다(AUDIT-LOG P4 C1).

    ``order_events`` 는 주문 타임라인이고 ``security_logs`` 는 "누가 무엇을 했는가"의
    원장이다. 파일은 사고 시 가장 먼저 묻는 대상이라 양쪽에 남긴다. 호출자의 트랜잭션에
    실으므로(``auto_commit=False``) 업로드가 롤백되면 감사 행도 함께 사라진다.

    :param db: 호출자가 소유한 세션.
    :param attachment: 대상 첨부.
    :param event_type: 첨부 수명주기 이벤트 타입.
    """
    action = _ATTACHMENT_AUDIT_ACTIONS.get(event_type)
    if not action:
        return
    order = db.get(Order, attachment.order_id)
    context = order_audit_context(order)
    log_access(
        describe_order_action(
            order_id=attachment.order_id, action=action,
            note=attachment.filename, **context,
        ),
        _actor_user_id(),
        auto_commit=False,
        action=action, target_type="order", target_id=int(attachment.order_id),
        detail={"attachment_id": attachment.id, "filename": attachment.filename,
                "category": attachment.category, "storage_key": attachment.storage_key,
                **context},
    )


def _attachment_object_keys(attachment: OrderAttachment) -> list[str]:
    """첨부가 소유한 스토리지 object key(본체·썸네일) 중 비어있지 않은 것만."""
    return [
        key
        for key in (
            getattr(attachment, "storage_key", None),
            getattr(attachment, "thumbnail_key", None),
        )
        if key
    ]


def _delete_dedupe_key(attachment_id: int, object_key: str) -> str:
    """object key 1개당 STORAGE_DELETE outbox dedupe 키(복구 시 정확 일치 조회에도 쓴다)."""
    return f"attachment:{attachment_id}:{object_key}"


def _enqueue_attachment_purge(
    db: Any, attachment: OrderAttachment, event_id: int, *, now: datetime.datetime
) -> None:
    """첨부 blob 삭제를 유예 후 ``STORAGE_DELETE`` outbox 로 예약한다(동기 R2 삭제 금지).

    공용 handler 가 행 1개당 ``payload['object_key']`` 하나를 지우므로 본체·썸네일을
    **행 2개**로 나눠 예약한다(handler 무수정). ``source_domain="ORDER_EVENT"`` 로 신규
    도메인을 만들지 않는다(one-of CHECK 준수).

    Args:
        db: 호출자 세션(커밋 미수행).
        attachment: tombstone 된 첨부.
        event_id: source 로 삼을 ``ATTACHMENT_DELETED`` 이벤트 id.
        now: 기준 시각(유예 계산 기준).
    """
    available_at = now + ATTACHMENT_PURGE_GRACE
    for object_key in _attachment_object_keys(attachment):
        enqueue_side_effect(
            db,
            source_domain="ORDER_EVENT",
            source_id=event_id,
            effect_type=STORAGE_DELETE,
            payload={
                "object_key": object_key,
                "order_id": attachment.order_id,
                "attachment_id": attachment.id,
            },
            dedupe_key=_delete_dedupe_key(attachment.id, object_key),
            available_at=available_at,
            now=now,
        )


def _attachment_purge_rows(db: Any, attachment: OrderAttachment) -> list:
    """이 첨부가 예약한 ``STORAGE_DELETE`` outbox 행을 dedupe_key 정확 일치로 조회한다."""
    keys = [
        _delete_dedupe_key(attachment.id, object_key)
        for object_key in _attachment_object_keys(attachment)
    ]
    if not keys:
        return []
    return (
        db.query(DomainSideEffectOutbox)
        .filter(
            DomainSideEffectOutbox.effect_type == STORAGE_DELETE,
            DomainSideEffectOutbox.dedupe_key.in_(keys),
        )
        .all()
    )


def _invalidate_attachment_caches() -> None:
    """첨부를 읽는 대시보드 family 캐시만 무효화한다(history 제외 — Tier B)."""
    from foms.services.common.dashboard_cache import (
        ATTACHMENT_DASHBOARD_FAMILIES,
        invalidate_dashboard_families,
    )

    invalidate_dashboard_families(*ATTACHMENT_DASHBOARD_FAMILIES)


@attachments_bp.route("/orders/<int:order_id>/attachments", methods=["GET"])
@login_required
def api_order_attachments_list(order_id):
    """주문 첨부 목록(ERP Beta 사진/동영상).

    기본은 살아있는 첨부만 반환한다(전역 tombstone 필터). ``?include_deleted=1`` 은
    휴지통 조회용 opt-in 으로, 첨부 관리 권한(관리자/담당자)이 있을 때만 허용한다.
    """
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        current_user = _current_user()
        want_deleted = (request.args.get("include_deleted") or "").strip().lower() in _TRUTHY
        if want_deleted and not can_manage_order_attachments(current_user, order):
            return jsonify({"success": False, "message": "삭제된 첨부를 조회할 권한이 없습니다."}), 403

        raw_filter_category = request.args.get("category")
        filter_category = None
        if raw_filter_category:
            filter_category = normalize_attachment_category(raw_filter_category)
            if not filter_category:
                return jsonify({"success": False, "message": "유효하지 않은 첨부 카테고리입니다."}), 400

        raw_filter_item_index = request.args.get("item_index")
        filter_item_index = None
        has_item_filter = raw_filter_item_index is not None
        if has_item_filter:
            ok, filter_item_index, err = parse_attachment_item_index(raw_filter_item_index)
            if not ok:
                return jsonify({"success": False, "message": err}), 400

        query = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id)
        if want_deleted:
            query = include_deleted(query)
        if filter_category:
            query = query.filter(OrderAttachment.category == filter_category)
        if has_item_filter:
            if filter_item_index is None:
                query = query.filter(OrderAttachment.item_index.is_(None))
            else:
                query = query.filter(OrderAttachment.item_index == filter_item_index)

        attachments = query.order_by(OrderAttachment.created_at.desc()).all()
        items = [
            serialize_attachment(attachment, order=order, user=current_user)
            for attachment in attachments
        ]
        return jsonify({"success": True, "attachments": items})
    except Exception as e:
        log_handled_exception()
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route("/orders/<int:order_id>/attachments", methods=["POST"])
@login_required
def api_order_attachments_upload(order_id):
    """주문 첨부 업로드(ERP Beta 사진/동영상)."""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "파일이 없습니다."}), 400
        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"success": False, "message": "파일명이 없습니다."}), 400

        category = normalize_attachment_category(request.form.get("category", "measurement"))
        if not category:
            return jsonify({"success": False, "message": "유효하지 않은 첨부 카테고리입니다."}), 400
        # UPLOAD-01: VIEWER 403 + 용도별 role/team (direct 경로와 동일 방어). folder 는 서버 생성.
        if not category_upload_allowed(_current_user(), category):
            return jsonify({"success": False, "message": "이 업로드를 수행할 권한이 없습니다."}), 403
        ok, item_index, err = parse_attachment_item_index(request.form.get("item_index"))
        if not ok:
            return jsonify({"success": False, "message": err}), 400

        if not allowed_erp_attachment_file(file.filename, category):
            allowed_exts = set(ERP_MEDIA_ALLOWED_EXTENSIONS)
            if category == "drawing":
                allowed_exts |= DRAWING_ATTACHMENT_EXTRA_EXTENSIONS
            allowed_exts_str = ", ".join(sorted(allowed_exts))
            return jsonify({"success": False, "message": f"허용되지 않은 파일 형식입니다. 지원 형식: {allowed_exts_str}"}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        max_size = get_erp_media_max_size(file.filename)
        if file_size > max_size:
            size_mb = max_size / (1024 * 1024)
            return jsonify({"success": False, "message": f"파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB까지 업로드 가능합니다."}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        storage = get_storage()
        folder = f"orders/{order_id}/attachments"
        result = storage.upload_file(file, file.filename, folder)
        if not result.get("success"):
            return jsonify({"success": False, "message": "파일 업로드 실패: " + result.get("message", "알 수 없는 오류")}), 500

        storage_key = result.get("key")
        filename = file.filename
        file_type = storage.get_file_type(filename)
        if category == "drawing":
            if file_type not in ["image", "video", "file"]:
                return jsonify({"success": False, "message": "지원되지 않는 도면 파일 형식입니다."}), 400
        elif file_type not in ["image", "video"]:
            return jsonify({"success": False, "message": "이미지/동영상만 업로드 가능합니다."}), 400

        thumbnail_key = None
        try:
            if file_type == "image" and hasattr(storage, "_generate_thumbnail") and not ASYNC_ATTACHMENT_THUMBNAIL:
                unique_filename = storage_key.rsplit("/", 1)[-1] if storage_key else None
                if unique_filename:
                    file.seek(0)
                    storage._generate_thumbnail(file, unique_filename, folder, "image", storage_key=storage_key)
                    thumbnail_key = f"{folder}/thumb_{unique_filename}"
        except Exception:
            thumbnail_key = None

        attachment = OrderAttachment(
            order_id=order_id,
            filename=filename,
            file_type=file_type,
            category=category,
            item_index=item_index,
            file_size=file_size,
            storage_key=storage_key,
            thumbnail_key=thumbnail_key,
            user_id=session.get("user_id"),
        )
        db.add(attachment)
        emit_attachment_event(db, attachment, ATTACHMENT_ADDED)
        db.commit()
        _invalidate_attachment_caches()
        db.refresh(attachment)
        if ASYNC_ATTACHMENT_THUMBNAIL and file_type == "image" and storage_key and not thumbnail_key:
            schedule_order_attachment_thumbnail_generation(attachment.id, storage_key)

        current_user = _current_user()
        return jsonify(
            {
                "success": True,
                "attachment": serialize_attachment(attachment, order=order, user=current_user),
            }
        )
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            log_handled_exception("order_routes rollback")
        log_handled_exception()
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route("/orders/<int:order_id>/attachments/<int:attachment_id>", methods=["PATCH"])
@login_required
def api_order_attachments_patch(order_id, attachment_id):
    """주문 첨부 메타 수정(제품 항목 연결/해제)."""
    try:
        payload = request.get_json(silent=True) or {}
        if "item_index" not in payload:
            return jsonify({"success": False, "message": "item_index 필드가 필요합니다."}), 400
        ok, item_index, err = parse_attachment_item_index(payload.get("item_index"))
        if not ok:
            return jsonify({"success": False, "message": err}), 400

        db = get_db()
        attachment = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.id == attachment_id, OrderAttachment.order_id == order_id)
            .first()
        )
        if not attachment:
            return jsonify({"success": False, "message": "첨부파일을 찾을 수 없습니다."}), 404

        order = db.query(Order).filter(Order.id == order_id).first()
        current_user = _current_user()
        if not can_modify_order_attachment(current_user, order, attachment):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "첨부파일 수정 권한이 없습니다. (관리자, 해당 주문 담당자, 또는 업로드한 본인만 가능)",
                    }
                ),
                403,
            )
        previous_item_index = getattr(attachment, "item_index", None)
        setattr(attachment, "item_index", item_index)
        if previous_item_index != item_index:
            # no-op PATCH 는 이벤트를 만들지 않는다(타임라인 노이즈 0).
            emit_attachment_event(
                db,
                attachment,
                ATTACHMENT_META_UPDATED,
                extra={"field": "item_index", "from": previous_item_index, "to": item_index},
            )
        db.commit()
        _invalidate_attachment_caches()
        db.refresh(attachment)
        return jsonify(
            {
                "success": True,
                "attachment": serialize_attachment(attachment, order=order, user=current_user),
            }
        )
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            log_handled_exception("order_routes rollback")
        log_handled_exception()
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route("/orders/<int:order_id>/attachments/<int:attachment_id>", methods=["DELETE"])
@login_required
def api_order_attachments_delete(order_id, attachment_id):
    """주문 첨부 삭제(ERP Beta) — tombstone + 이벤트 + 지연 blob 삭제 예약.

    row 를 지우지 않고 ``deleted_at``/``deleted_by_user_id`` 만 세운다(전역 필터가 이후 모든
    ORM SELECT 에서 제외). R2 blob 은 동기 삭제하지 않고 :data:`ATTACHMENT_PURGE_GRACE` 뒤
    ``STORAGE_DELETE`` outbox 로 예약하므로 그 사이에는 복구 API 로 되살릴 수 있다.
    """
    try:
        db = get_db()
        attachment = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.id == attachment_id, OrderAttachment.order_id == order_id)
            .first()
        )
        if not attachment:
            return jsonify({"success": False, "message": "첨부파일을 찾을 수 없습니다."}), 404

        order = db.query(Order).filter(Order.id == order_id).first()
        current_user = _current_user()
        if not can_delete_order_attachment(current_user, order, attachment):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "첨부파일 삭제 권한이 없습니다. (관리자, 해당 주문 담당자, 또는 업로드한 본인만 가능)",
                    }
                ),
                403,
            )

        now = now_utc_naive()
        attachment.deleted_at = now
        attachment.deleted_by_user_id = _actor_user_id()
        event = emit_attachment_event(
            db, attachment, ATTACHMENT_DELETED, extra={"deleted_at": now.isoformat()}
        )
        _enqueue_attachment_purge(db, attachment, event.id, now=now)
        db.commit()
        _invalidate_attachment_caches()
        return jsonify({"success": True})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            log_handled_exception("order_routes rollback")
        log_handled_exception()
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route(
    "/orders/<int:order_id>/attachments/<int:attachment_id>/restore", methods=["POST"]
)
@login_required
def api_order_attachments_restore(order_id, attachment_id):
    """삭제(tombstone)된 주문 첨부 복구 — 삭제 API 의 대칭.

    유예가 남아 blob 삭제가 아직 ``PENDING`` 인 동안에만 복구할 수 있다. 복구는 예약된
    ``STORAGE_DELETE`` outbox 행을 제거하고 tombstone 을 해제한 뒤
    ``ATTACHMENT_RESTORED`` 이벤트를 남긴다. worker 가 이미 집어간(=blob 이 사라졌거나
    사라지는 중인) 첨부는 되살리면 깨진 링크가 되므로 409 로 거절한다.
    """
    try:
        db = get_db()
        attachment = include_deleted(
            db.query(OrderAttachment).filter(
                OrderAttachment.id == attachment_id,
                OrderAttachment.order_id == order_id,
            )
        ).first()
        if not attachment or attachment.deleted_at is None:
            return jsonify({"success": False, "message": "삭제된 첨부파일을 찾을 수 없습니다."}), 404

        order = db.query(Order).filter(Order.id == order_id).first()
        current_user = _current_user()
        if not can_delete_order_attachment(current_user, order, attachment):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "첨부파일 복구 권한이 없습니다. (관리자, 해당 주문 담당자, 또는 업로드한 본인만 가능)",
                    }
                ),
                403,
            )

        purge_rows = _attachment_purge_rows(db, attachment)
        if not purge_rows or any(row.status != "PENDING" for row in purge_rows):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "유예 기간이 지나 스토리지 파일이 이미 삭제되었습니다. 복구할 수 없습니다.",
                    }
                ),
                409,
            )

        for row in purge_rows:
            db.delete(row)  # 예약 취소 — dedupe 키도 함께 풀려 재삭제가 가능해진다.
        attachment.deleted_at = None
        attachment.deleted_by_user_id = None
        emit_attachment_event(db, attachment, ATTACHMENT_RESTORED)
        db.commit()
        _invalidate_attachment_caches()
        db.refresh(attachment)
        return jsonify(
            {
                "success": True,
                "attachment": serialize_attachment(attachment, order=order, user=current_user),
            }
        )
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            log_handled_exception("order_routes rollback")
        log_handled_exception()
        return jsonify({"success": False, "message": str(e)}), 500


__all__ = [
    "ATTACHMENT_ADDED",
    "ATTACHMENT_DELETED",
    "ATTACHMENT_META_UPDATED",
    "ATTACHMENT_RESTORED",
    "ATTACHMENT_PURGE_GRACE",
    "api_order_attachments_delete",
    "api_order_attachments_list",
    "api_order_attachments_patch",
    "api_order_attachments_restore",
    "api_order_attachments_upload",
    "emit_attachment_event",
]
