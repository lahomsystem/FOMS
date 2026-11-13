"""협력사 AS 접수 · 수정 · AS방 PUSH JSON API(PARTNER-AS-02, 사용자 2026-11-13).

* ``GET  /api/partner/orders/<id>/as``        — 접수 창 값(할 일 · 지금 접수 글 · 지난 AS · 완공 사진 · AS방 줄).
* ``POST /api/partner/orders/<id>/as``        — 처음 · 재접수(multipart ``content`` · ``construction_photo_ids`` ·
  ``recurrence`` · ``photos`` · ``defer_push`` · ``idempotency_key``).
* ``POST /api/partner/orders/<id>/as/edit``   — 진행 중인 건 고치기(``content`` · ``change_note`` · ``defer_push``).
* ``POST /api/partner/orders/<id>/as/files``  — 파일 1개(``file`` · ``as_log_id`` · ``sort_order``) — 지금 접수 줄에만.
* ``POST /api/partner/orders/<id>/as/push``   — AS방 보내기(``change_note``) — 파일을 다 올린 뒤 · 실패 뒤 다시.

쓰기는 본사 접수 정본 :func:`register_as_from_payload` 그대로(새 건 · 같은 건 갱신 · 원장 · 감사 · 앞 사진 옮기기).
보내기는 본사 AS PUSH 와 같은 :func:`run_manual_push` (``push_kind='as'`` — 같은 방 · 같은 글 · 같은 이력 칸).
AS방 전송이 실패해도 접수 · 수정은 남는다(화면이 [다시 보내기]를 보인다).
설계서: docs/specs/2026-11-13-partner-as-intake-edit-push_SPEC.md
"""
from __future__ import annotations

import logging
import os
from typing import Any

from flask import Blueprint, g, jsonify, make_response, request

from db import get_db
from foms.api.channel.channel_integration import run_manual_push
from foms.api.cs.as_orders import register_as_from_payload
from foms.api.files.blueprint import ASYNC_ATTACHMENT_THUMBNAIL
from foms.api.files.common import get_erp_media_max_size
from foms.api.files.order_routes import ATTACHMENT_ADDED, emit_attachment_event
from foms.api.files.routes import build_file_view_url
from foms.api.notifications import invalidate_badge_cache_for_user_ids, resolve_notification_recipient_user_ids
from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import partner_can_read_order, partner_required
from foms.services.channel_as_attachments import last_pushed_max_attachment_id
from foms.services.common.dashboard_cache import (
    ATTACHMENT_DASHBOARD_FAMILIES,
    DASHBOARD_FAMILY_ORDERS,
    invalidate_dashboard_families,
)
from foms.services.error_logging import log_handled_exception
from foms.services.files.heic_convert import jpeg_if_heic
from foms.services.files.upload_policy import ERP_MEDIA_ALLOWED_EXTENSIONS
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.order_attachment_thumbnail import schedule_order_attachment_thumbnail_generation
from foms.services.partners import as_intake as svc
from foms.services.partners.completion import (
    CompletionPhotoError,
    construction_photos_for_partner,
    pick_construction_photos,
)
from foms.services.storage import get_storage
from models import Notification, Order, OrderAttachment, SecurityLog

logger = logging.getLogger(__name__)

partner_as_bp = Blueprint("partner_as", __name__, url_prefix="/api/partner")

AS_FOLDER = "as"
MAX_FILES_PER_RECEPTION = 20
_BUSY = "지금은 처리할 수 없습니다. 화면을 새로고침한 뒤 다시 시도해 주세요."
PUSH_SENT_NOTE = "AS방에 보냈습니다."
PUSH_FAILED_NOTE = "AS방 전송은 실패했습니다. 접수는 남아 있으니 [AS방 다시 보내기]를 눌러 주세요."


def _fail(message: str, status: int):
    return jsonify({"success": False, "data": None, "error": message}), status


def _ok(data: dict):
    return jsonify({"success": True, "data": data, "error": None})


def _own_order(db, order_id: int) -> Order | None:
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    return order if partner_can_read_order(g.current_user, order) else None


def _label(user: Any) -> str:
    return f"{user.name}{svc.PARTNER_TAIL}"


def _flag(raw: Any) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "on", "yes")


# ── 파일 ──────────────────────────────────────────────────────────────────────


def _store_file(order_id: int, f, as_log_id: str, sort_order: int | None) -> OrderAttachment:
    """사진 · 동영상 한 개를 AS 폴더에 올리고 접수 줄에 묶은 첨부 행을 만든다(호출자가 commit).

    Raises:
        svc.PartnerASError: 형식 · 크기 위반(400) · 저장 실패(502).
    """
    f, heic_error = jpeg_if_heic(f)  # 아이폰 HEIC 는 JPEG 로(SPEC 2026-11-04-heic-to-jpeg)
    if heic_error:
        raise svc.PartnerASError(heic_error, 400)
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ERP_MEDIA_ALLOWED_EXTENSIONS:
        raise svc.PartnerASError("사진이나 동영상만 올릴 수 있습니다.", 400)
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)
    if size > get_erp_media_max_size(f.filename):
        raise svc.PartnerASError("파일이 너무 큽니다.", 400)
    storage = get_storage()
    result = storage.upload_file(f, f.filename, f"orders/{order_id}/{AS_FOLDER}")
    if not result.get("success"):
        raise svc.PartnerASError("파일을 올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.", 502)
    attachment = OrderAttachment(
        order_id=order_id, filename=f.filename, file_type=storage.get_file_type(f.filename), category="as",
        as_log_id=as_log_id, file_size=size, storage_key=result.get("key"), thumbnail_key=None,
        sort_order=sort_order, user_id=g.current_user.id,
    )
    get_db().add(attachment)
    emit_attachment_event(get_db(), attachment, ATTACHMENT_ADDED)
    return attachment


def _after_files(attachments: list[OrderAttachment]) -> None:
    invalidate_dashboard_families(*ATTACHMENT_DASHBOARD_FAMILIES)
    if not ASYNC_ATTACHMENT_THUMBNAIL:
        return
    for a in attachments:
        if a.file_type == "image" and a.storage_key:
            schedule_order_attachment_thumbnail_generation(a.id, a.storage_key)


def _store_request_photos(order_id: int, reception_id: str) -> tuple[int, str | None]:
    """접수 요청에 같이 온 ``photos``(1판 방식) — 접수가 확정된 뒤 붙인다. 반환 (올린 수, 오류 문구)."""
    files = [f for f in request.files.getlist("photos") if f and f.filename][:MAX_FILES_PER_RECEPTION]
    db, saved = get_db(), []
    try:
        for i, f in enumerate(files):
            saved.append(_store_file(order_id, f, reception_id, i))
        db.commit()
    except svc.PartnerASError as exc:
        db.commit()  # 앞서 올린 파일은 남긴다
        _after_files(saved)
        return len(saved), str(exc)
    _after_files(saved)
    return len(saved), None


# ── AS방 PUSH ─────────────────────────────────────────────────────────────────


def _unsent_attachment_ids(db, order: Order) -> list[int]:
    """이 건 지금 접수 줄의 파일 중 AS방에 아직 안 보낸 것(마지막 PUSH 의 가장 큰 첨부 id 보다 새것)."""
    entry = svc.current_reception(order)
    if not entry:
        return []
    sd = order.structured_data or {}
    floor = last_pushed_max_attachment_id(sd.get(svc.PUSH_HISTORY_KEY))
    rows = (db.query(OrderAttachment.id)
            .filter(OrderAttachment.order_id == order.id, OrderAttachment.category == "as",
                    OrderAttachment.as_log_id == str(entry.get("id") or ""), OrderAttachment.id > floor)
            .order_by(OrderAttachment.sort_order.asc(), OrderAttachment.id.asc()).all())
    return [r.id for r in rows][:MAX_FILES_PER_RECEPTION]


def _push(db, user: Any, order_id: int, change_note: str = "") -> tuple[bool, str]:
    """AS방 PUSH 한 건(본사 AS PUSH 와 같은 길). 반환 (성공, 화면에 보일 한 줄)."""
    try:
        db.expire_all()
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if order is None or svc.as_mode(order) != svc.MODE_EDIT:
            return False, PUSH_FAILED_NOTE
        body, status = run_manual_push(db, {
            "order_id": order.id, "text": "", "push_kind": "as",
            "change_note": svc.push_change_note(order, change_note),
            "attachment_ids": _unsent_attachment_ids(db, order),
        }, user, pushed_by_name=_label(user))
    except Exception:  # noqa: BLE001 - 접수는 끝났다, 전송 실패만 알린다
        db.rollback()
        log_handled_exception("partner AS push")
        return False, PUSH_FAILED_NOTE
    if body.get("success"):
        return True, PUSH_SENT_NOTE
    db.rollback()
    logger.warning("[협력사 AS PUSH] 실패 order=%s status=%s msg=%s", order_id, status, body.get("message"))
    return False, PUSH_FAILED_NOTE


# ── 접수 · 고치기 ─────────────────────────────────────────────────────────────


def _register(db, order: Order, payload: dict, **labels) -> tuple[dict | None, Any]:
    """본사 접수 정본을 부른다. 반환 (성공 본문, None) 또는 (None, 실패 응답)."""
    resp = make_response(register_as_from_payload(order.id, payload, g.current_user.id, **labels))
    body = resp.get_json(silent=True) or {}
    if resp.status_code == 200 and body.get("success"):
        return body, None
    if resp.status_code == 400:
        return None, _fail(str(body.get("message") or "입력을 확인해 주세요."), 400)
    logger.warning("[협력사 AS] 본사 접수 거부 order=%s status=%s", order.id, resp.status_code)
    return None, _fail(_BUSY, 409)


def _record(db, user: Any, order: Order, text: str, *, edit: bool) -> None:
    """감사 · (처음 · 재접수면) CS 벨 1건 — 우리 쪽이 협력사 AS 를 놓치지 않게(사용자 2026-10-28)."""
    action = "PARTNER_AS_UPDATED" if edit else "PARTNER_AS_REGISTERED"
    db.add(SecurityLog(user_id=user.id, message=f"협력사 AS {'수정' if edit else '접수'}: #{order.id}",
                       action=action, target_type="order", target_id=order.id,
                       detail=normalize_security_detail({"partner_org_id": order.partner_org_id})))
    if not edit:
        customer = str((((order.structured_data or {}).get("parties") or {}).get("customer") or {}).get("name") or "")
        notification = Notification(
            order_id=order.id, notification_type="PARTNER_AS_REGISTERED", target_team="CS", title="협력사 AS 접수",
            message=f"[협력사] 주문 #{order.id}" + (f" ({customer.strip()})" if customer.strip() else "")
            + f" AS 가 접수되었습니다. 내용: {text[:80]}",
            created_by_user_id=user.id, created_by_name=_label(user),
        )
        db.add(notification)
        db.flush()
        fan_out_new_notification(db, notification, actor_user_id=user.id)
    db.commit()
    if not edit:
        invalidate_badge_cache_for_user_ids(resolve_notification_recipient_user_ids(
            db, target_team="CS", target_manager_name=None, include_admin=False))


def _finish(db, order_id: int, reception_id: str, change_note: str = "") -> Any:
    """접수 · 고치기 뒤 — 같이 온 사진을 붙이고, 미루지 않았으면 AS방에 보낸다."""
    invalidate_dashboard_families(DASHBOARD_FAMILY_ORDERS)
    photos, photo_error = _store_request_photos(order_id, reception_id) if reception_id else (0, None)
    data = {"order_id": order_id, "reception_log_id": reception_id, "photos": photos}
    if photo_error:
        data["photo_error"] = photo_error
    if not _flag(request.form.get("defer_push") or (request.get_json(silent=True) or {}).get("defer_push")):
        data["push_sent"], data["push_note"] = _push(db, g.current_user, order_id, change_note)
    return _ok(data)


def _form() -> dict:
    return request.form if request.form else (request.get_json(silent=True) or {})


@partner_as_bp.route("/orders/<int:order_id>/as", methods=["GET"])
@partner_required
def as_form(order_id: int):
    """접수 창 값 — 할 일(new · reintake · edit)과 그 칸들. 할 일이 없으면 mode=None."""
    db = get_db()
    order = _own_order(db, order_id)
    if order is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    view = svc.form_view(order)
    photos = construction_photos_for_partner(db, order) if view["mode"] in (svc.MODE_NEW, svc.MODE_REINTAKE) else []
    view["construction_photos"] = [
        {"id": p["id"], "filename": p["filename"], "is_image": p["is_image"],
         "url": build_file_view_url(p["storage_key"]), "thumb_url": build_file_view_url(p["thumbnail_key"])}
        for p in photos
    ]
    return _ok(view)


@partner_as_bp.route("/orders/<int:order_id>/as", methods=["POST"])
@partner_required
def register_as(order_id: int):
    """처음 · 재접수 — 본사 접수 정본으로 새 AS 건을 연다. 진행 중인 건이 있으면 409(고치기 길로)."""
    db = get_db()
    order = _own_order(db, order_id)
    if order is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    form = _form()
    try:
        mode = svc.as_mode(order)
        if mode == svc.MODE_EDIT:
            raise svc.PartnerASError("이미 진행 중인 AS 가 있습니다. [AS 접수 수정]으로 고쳐 주세요.")
        if mode is None:
            raise svc.PartnerASError("시공이 끝난 주문만 AS 를 접수할 수 있습니다.")
        text = svc.clean_content(form.get("content"))
        raw_ids = request.form.getlist("construction_photo_ids") if request.form else form.get("construction_photo_ids")
        ref_photos = pick_construction_photos(db, order_id, raw_ids or [])
    except svc.PartnerASError as exc:
        return _fail(str(exc), exc.status)
    except CompletionPhotoError as exc:
        return _fail(str(exc), 400)
    payload = {"as_content": svc.reception_text(text, ref_photos), "billing_type": "undecided",
               "source_screen": "partner_portal", "recurrence": _flag(form.get("recurrence")) and mode == svc.MODE_REINTAKE,
               "idempotency_key": str(form.get("idempotency_key") or "")[:64] or None}
    extra = {"ref_attachment_ids": [pid for pid, _name in ref_photos]} if ref_photos else None
    body, error = _register(db, order, payload, actor_label=_label(g.current_user),
                            system_text=svc.SYSTEM_TEXT_NEW, reception_extra=extra)
    if error is not None:
        return error
    _record(db, g.current_user, order, text, edit=False)
    return _finish(db, order_id, str(body.get("reception_log_id") or ""))


@partner_as_bp.route("/orders/<int:order_id>/as/edit", methods=["POST"])
@partner_required
def edit_as(order_id: int):
    """진행 중인 AS 고치기 — 본사 "AS 접수 수정"과 같은 같은 건 갱신(건 수 그대로 · 비용 잠금 · 앞 사진 옮김)."""
    db = get_db()
    order = _own_order(db, order_id)
    if order is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    form = _form()
    try:
        if svc.as_mode(order) != svc.MODE_EDIT:
            raise svc.PartnerASError("고칠 수 있는 진행 중인 AS 가 없습니다. 화면을 새로고침해 주세요.")
        text = svc.clean_content(form.get("content"))
        note = svc.clean_change_note(form.get("change_note"))
    except svc.PartnerASError as exc:
        return _fail(str(exc), exc.status)
    ref_line, extra = svc.edit_carry(order)
    payload = {"as_content": f"{text}\n{ref_line}" if ref_line else text, "billing_type": "undecided",
               "source_screen": "partner_portal", "idempotency_key": str(form.get("idempotency_key") or "")[:64] or None}
    body, error = _register(db, order, payload, actor_label=_label(g.current_user),
                            system_text=svc.SYSTEM_TEXT_EDIT, reception_extra=extra)
    if error is not None:
        return error
    _record(db, g.current_user, order, text, edit=True)
    return _finish(db, order_id, str(body.get("reception_log_id") or ""), note)


@partner_as_bp.route("/orders/<int:order_id>/as/files", methods=["POST"])
@partner_required
def upload_as_file(order_id: int):
    """파일 1개 — 진행 중인 건의 **지금 접수 줄**에만 붙는다(다른 줄 · 끝난 건 400)."""
    db = get_db()
    order = _own_order(db, order_id)
    if order is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    entry = svc.current_reception(order) if svc.as_mode(order) == svc.MODE_EDIT else None
    as_log_id = str(request.form.get("as_log_id") or "")
    if not entry or as_log_id != str(entry.get("id") or ""):
        return _fail("AS 접수 줄이 바뀌었습니다. 화면을 새로고침한 뒤 다시 올려 주세요.", 400)
    f = request.files.get("file")
    if not f or not f.filename:
        return _fail("파일이 없습니다.", 400)
    count = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id, OrderAttachment.category == "as",
                                             OrderAttachment.as_log_id == as_log_id).count()
    if count >= MAX_FILES_PER_RECEPTION:
        return _fail(f"한 번에 {MAX_FILES_PER_RECEPTION}개까지 올릴 수 있습니다.", 400)
    raw_sort = str(request.form.get("sort_order") or "")
    try:
        attachment = _store_file(order_id, f, as_log_id, int(raw_sort) if raw_sort.isdigit() else None)
        db.commit()
    except svc.PartnerASError as exc:
        db.rollback()
        return _fail(str(exc), exc.status)
    except Exception:  # noqa: BLE001 - 첨부 행 실패는 다시 올리게 한다
        db.rollback()
        log_handled_exception("partner AS file row")
        return _fail("파일 기록을 남기지 못했습니다. 다시 시도해 주세요.", 500)
    _after_files([attachment])
    return _ok({"attachment_id": attachment.id, "filename": attachment.filename})


@partner_as_bp.route("/orders/<int:order_id>/as/push", methods=["POST"])
@partner_required
def push_as(order_id: int):
    """AS방 보내기 — 진행 중인 건만. 실린 파일 = 이 건 지금 접수 줄의 아직 안 보낸 파일."""
    db = get_db()
    order = _own_order(db, order_id)
    if order is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    if svc.as_mode(order) != svc.MODE_EDIT:
        return _fail("보낼 진행 중인 AS 가 없습니다.", 409)
    note = str((request.get_json(silent=True) or {}).get("change_note") or "").strip()[:svc.MAX_CHANGE_NOTE]
    sent, message = _push(db, g.current_user, order_id, note)
    if not sent:
        return _fail(message, 502)
    db.expire_all()
    fresh = db.query(Order).filter(Order.id == order_id).first()
    return _ok({"push_note": message, "push": svc.push_status(fresh)})
