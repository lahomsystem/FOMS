"""공장 [도면 수정 요청] API(설계서 2026-11-25 N3 · §2-4 · §4-1 · §4-2 · §6, D4) + 요청 사진 올리기.

``POST /api/orders/<id>/production/drawing-request`` 몸 ``{targets: [{sheet_id} | {key}], note, photos?: [{key, filename}]}``(머리글
``Idempotency-Key``). 응답 ``{success, data: {request, changed, keys, block, mutation_version}, error}``.
``POST /api/orders/<id>/production/drawing-request/photo``(multipart ``file``) — 사진 한 장을 영업 수정 요청 참고 파일과 같은 자리
(``orders/<id>/drawing_gateway/revisions``)에 둔다. 영업 쪽 업로드 길(``drawing-gateway-upload``)은 ``ERP_EDIT``(CS · 영업 + 관리자)라
생산 계정(반장 · 파트 계정)이 못 지나서 생산 쪽 길을 따로 연다 — 저장 · 검사는 같은 함수(``normalize_revision_files``).

* 누가(§4-1): 관리자 · 반장 = 모든 도면, 파트 계정 = 자기 공장 도면만(``drawing_fix_requests.can_request_drawing_fix``), 생산 단계만.
  그 밖 403 ``REQUEST_FORBIDDEN`` · 생산 단계 아님 409 ``INVALID_STAGE``(§4-2 에 글이 없어 공장 완료 API 의 지금 글).
* 몸(§4-2): 사유 빈 글 400 ``REQUEST_NOTE_REQUIRED`` · 도면 0장 400 ``REQUEST_PICK`` · 사진 4장 이상 · 경로 이상 400 ``REQUEST_PHOTOS`` ·
  지금 도면에 없는 장 409 ``FIX_NOT_CURRENT``(D3 지금 글) · 이미 막힌 도면(고치는 중 · 영업 요청 · 열린 공장 요청 — 도면 판 카드와 같은
  판정)이 끼면 409 ``REQUEST_BLOCKED``(그 막힘의 지금 글). 같은 열쇠로 다시 왔는데 요청 줄이 없으면 409 ``REQUEST_CLOSED``.
* 사진 길: 그 주문에 이 사람 몫 도면(사람 · 공장 — 막힘은 안 봄)이 없으면 403 · 그림 파일만(저장소 ``get_file_type``) · 몸 상한은 영업
  창구 업로드와 같은 줄(``foms/platform/request_limits.py``).
* 한 tx: 행 잠금 → 판정 → REV-00 엔진(``execute_order_mutation`` — 멱등 열쇠를 받는 길. ``execute_single_order_write`` 는 열쇠를 안 받는다)
  안에서 deepcopy 사본에 요청을 적고 재대입 · ``flag_modified`` · 버전 +1 → ``OrderEvent PRODUCTION_DRAWING_REQUESTED`` → 감사(``log_access``
  — D3 와 같은 길) → 알림 줄 + 받는 사람 state → 커밋. 같은 열쇠로 다시 온 요청은 쓰기 · 이벤트 · 감사 · 알림 0, 같은 요청을 돌려준다.
* 알림(§6 · 사장님 답 Q11 "영업 수정 요청과 똑같이"): 도면팀 전원 + 관리자 — 종(``target_team='DRAWING'``) + 폰(커밋 뒤 enqueue) + 확인 창
  (실시간 ``interrupt``). 제목 "공장 도면 수정 요청".
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
# 감사 = log_access(대신 로그인 표지 · detail 정규화 · 감사 행만 되감는 savepoint). api → web 새 import 는 레이어 래칫이 막아 D3 와 같이
# 같은 길을 이미 쓰는 전달 API 모듈에서 가져온다.
from foms.api.drawing.erp_orders_drawing import log_access
from foms.api.notifications import invalidate_badge_cache_for_user_ids, resolve_notification_recipient_user_ids
from foms.services.audit_message_display import describe_order_action
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import _ensure_dict
from foms.services.notifications.drawing_factory_request_push import REQUEST_TITLE, REQUEST_TYPE
from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.drawing_fix_marks import FixRefusal, resolve_targets
from foms.services.orders.drawing_fix_requests import (
    INVALID_STAGE,
    MAX_PHOTOS,
    MESSAGES,
    PHOTOS_BAD,
    PHOTOS_TOO_MANY,
    REQUEST_BLOCKED,
    REQUEST_CLOSED,
    REQUEST_EVENT,
    REQUEST_FORBIDDEN,
    REQUEST_NOTE_REQUIRED,
    REQUEST_PHOTOS,
    REQUEST_PICK,
    STAGE_PRODUCTION,
    RequestRefusal,
    add_request,
    can_request_drawing_fix,
    can_request_people,
    clean_note,
    entry_block,
    find_request,
    has_requestable_drawing,
    numbers_label,
    photo_rows,
    request_id,
    request_message,
)
from foms.services.orders.drawing_gate_followups import invalidate_after_drawing_revision
from foms.services.orders.drawing_revision_files import normalize_revision_files
from foms.services.orders.revision import RevisionError, execute_order_mutation, lock_order_row
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.part_card_state import order_block
from foms.services.storage import get_storage
from models import Notification, Order, OrderEvent

logger = logging.getLogger(__name__)

#: REV-00 영수증 정책 id(멱등 열쇠의 범위). 앞문 정책은 매니페스트의 ``PRODUCTION_EDIT``.
REQUEST_POLICY_ID = "PRODUCTION_DRAWING_REQUEST"
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."
_NOT_FOUND = "주문을 찾을 수 없어요."
_UPLOADED = "DRAWING_GATEWAY_FILE_UPLOADED"

erp_orders_drawing_request_bp = Blueprint("erp_orders_drawing_request", __name__, url_prefix="/api/orders")


def _fail(status: int, code: str, message: str):
    return jsonify({"success": False, "data": {"code": code}, "error": message}), status


def _actor_name(user: Any) -> str:
    return getattr(user, "name", None) or getattr(user, "username", None) or ""


def _customer(order: Any, sd: Any) -> str:
    name = (((sd.get("parties") or {}).get("customer") or {}).get("name") or "") if isinstance(sd, dict) else ""
    return str(name or getattr(order, "customer_name", None) or "").strip()


def _parse(order_id: int, body: Any) -> tuple[str, list[Any], list[dict[str, str]]]:
    """몸 → (사유, 고른 도면, 사진 저장 모양). 틀리면 400 :class:`RequestRefusal`(§4-2 차례: 사유 → 도면 → 사진)."""
    body = body if isinstance(body, dict) else {}
    note = clean_note(body.get("note"))
    if not note:
        raise RequestRefusal(400, REQUEST_NOTE_REQUIRED)
    targets = body.get("targets")
    if not isinstance(targets, list) or not targets:
        raise RequestRefusal(400, REQUEST_PICK)
    raw = [] if body.get("photos") is None else body.get("photos")
    if not isinstance(raw, list):
        raise RequestRefusal(400, REQUEST_PHOTOS, PHOTOS_BAD)
    if len(raw) > MAX_PHOTOS:
        raise RequestRefusal(400, REQUEST_PHOTOS, PHOTOS_TOO_MANY)
    files, rejects = normalize_revision_files(order_id, raw)
    if rejects:
        raise RequestRefusal(400, REQUEST_PHOTOS, PHOTOS_BAD)
    return note, targets, photo_rows(files)


def _locked_order(db: Any, order_id: int) -> Order:
    """잠근 주문(없음 · 지움 · ERP 아님은 LookupError) — 생산 단계가 아니면 409 ``INVALID_STAGE``."""
    order = lock_order_row(db, order_id)
    if order is None or order.status == "DELETED" or order.deleted_at is not None or not order.is_erp_order:
        raise LookupError(order_id)
    if read_main_stage(order) != STAGE_PRODUCTION:
        raise RequestRefusal(409, INVALID_STAGE)
    return order


def _record(db: Any, order: Any, user: Any, req: dict[str, Any]) -> Notification:
    """이벤트 1 + 감사 1 + 알림 줄 1(받는 사람 state 까지, 같은 tx). 폰 · 실시간 알림은 커밋 뒤(:func:`_announce`)."""
    payload = {"request_id": req["id"], "numbers": req["numbers"], "idents": req["targets"], "by_name": req["by_name"],
               "factory": req["factory"], "photos": len(req["photos"])}
    db.add(OrderEvent(order_id=order.id, event_type=REQUEST_EVENT, created_by_user_id=user.id, payload=payload))
    context = order_audit_context(order)
    log_access(describe_order_action(order_id=order.id, action=REQUEST_EVENT, note=numbers_label(req["numbers"]), **context),
               user.id, auto_commit=False, action=REQUEST_EVENT, target_type="order", target_id=int(order.id),
               detail={**payload, **context}, db=db)
    sd = _ensure_dict(order.structured_data)
    notification = Notification(order_id=order.id, notification_type=REQUEST_TYPE, target_team="DRAWING", title=REQUEST_TITLE,
                                message=request_message(int(order.id), _customer(order, sd), req["numbers"], req["note"]),
                                created_by_user_id=user.id, created_by_name=_actor_name(user))
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)
    return notification


def _write(db: Any, user: Any, order_id: int, body: Any, idem: Optional[str]) -> dict[str, Any]:
    """잠근 주문 위에서 판정 → 쓰기(멱등 열쇠가 같으면 다시 쓰지 않음). 커밋 · 되감기는 부르는 쪽.

    Raises:
        RequestRefusal · FixRefusal: §4-2 거절. LookupError: 주문 없음. RevisionError: 엔진 거절(열쇠 재사용 등).
    """
    note, targets, photos = _parse(order_id, body)
    order = _locked_order(db, order_id)
    picked = resolve_targets(_ensure_dict(order.structured_data), targets)
    if not can_request_drawing_fix(user, order, [entry for _no, entry in picked]):
        raise RequestRefusal(403, REQUEST_FORBIDDEN)
    rid = request_id(user.id, idem)
    at = now_utc_naive().replace(microsecond=0).isoformat() + "Z"
    made: dict[str, Any] = {}

    def _mutate(_sess: Any, locked: list[Order]) -> dict[int, list[str]]:
        target = locked[0]
        sd = copy.deepcopy(_ensure_dict(target.structured_data))
        # 이미 막힌 도면이 끼면 거절 — 창 고르기와 같은 판정(도면 판 카드의 막힌 칸), 글은 그 막힘의 지금 글. 엔진 콜백 안이라 같은
        # 열쇠로 다시 온 요청(제가 막은 도면)은 여기 오기 전에 영수증으로 돌아간다.
        for _no, entry in picked:
            block = entry_block(sd, entry)
            if block is not None:
                raise RequestRefusal(409, REQUEST_BLOCKED, block["why"])
        made["request"] = add_request(sd, picked, rid=rid, note=note, photos=photos, user_id=user.id,
                                      by_name=_actor_name(user), at=at)
        target.structured_data = sd
        flag_modified(target, "structured_data")
        return {order_id: [f"ORDER_DETAIL:{order_id}", "ORDERS_INDEX"]}

    text = json.dumps(body if isinstance(body, dict) else {}, sort_keys=True, ensure_ascii=False, default=str)
    result = execute_order_mutation(
        db, actor_user_id=user.id, policy_id=REQUEST_POLICY_ID, order_ids=[order_id],
        scope_hash=hashlib.sha256(f"{REQUEST_POLICY_ID}:{order_id}".encode("utf-8")).hexdigest(),
        request_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(), idempotency_key=idem, mutation=_mutate)
    if result.replayed:
        replayed = find_request(_ensure_dict(order.structured_data), rid)
        if replayed is None:  # 영수증은 있는데 요청 줄이 없다(손으로 지운 자료 등) — 빈 요청 대신 "다시 열어 주세요"
            raise RequestRefusal(409, REQUEST_CLOSED)
        return {"order": order, "request": replayed, "picked": picked, "notification": None}
    return {"order": order, "request": made["request"], "picked": picked,
            "notification": _record(db, order, user, made["request"])}


def _announce(db: Any, order: Any, user: Any, notification: Notification) -> None:
    """커밋 뒤 — 폰 알림 enqueue · 받는 사람 종 배지 · 확인 창(영업 수정 요청과 같은 받는 사람 · 같은 등급)."""
    enqueue_push_for_notification(notification.id, db=db)
    recipients = resolve_notification_recipient_user_ids(db, target_team="DRAWING", target_manager_name=None, include_admin=True)
    invalidate_badge_cache_for_user_ids(recipients)
    sd = _ensure_dict(order.structured_data)
    emit_erp_notification_to_users(recipients, {
        "notification_id": notification.id, "order_id": int(order.id), "notification_type": REQUEST_TYPE,
        "title": notification.title, "message": notification.message, "created_by_name": _actor_name(user),
        "customer_name": _customer(order, sd),
        # ACTION-REQUIRED 등급(확인 창) — 등급 판정은 서버 몫, 영업 수정 요청과 같은 표지.
        "interrupt": True,
    })


def _response(result: dict[str, Any]):
    order, req = result["order"], result["request"]
    sd = _ensure_dict(order.structured_data)
    entries = [entry for _no, entry in result["picked"]]
    # 보낸 도면 카드가 바로 그릴 막힌 칸(도면 판과 같은 함수 — 화면 == 서버)
    block = next((b for b in (order_block({"structured_data": sd}, entry) for entry in entries) if b), None)
    data = {"request": req, "changed": result["notification"] is not None, "keys": [entry["key"] for entry in entries],
            "block": {k: block[k] for k in ("kind", "text", "why")} if block else None,
            "mutation_version": int(order.mutation_version or 0)}
    return jsonify({"success": True, "data": data, "error": None})


@erp_orders_drawing_request_bp.route("/<int:order_id>/production/drawing-request", methods=["POST"])
def api_production_drawing_request(order_id: int):
    """공장 [도면 수정 요청] — 고른 도면이 그 순간 막히고 도면팀 전원 + 관리자에게 알림이 간다."""
    user = getattr(g, "current_user", None)  # before_request(_set_current_user) — 비활성 · 끊긴 세션은 이미 비웠다
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "다시 로그인해 주세요.")
    if not can_request_people(user):
        return _fail(403, REQUEST_FORBIDDEN, MESSAGES[REQUEST_FORBIDDEN])
    idem = (request.headers.get("Idempotency-Key") or "").strip()[:64] or None
    db = get_db()
    try:
        result = _write(db, user, order_id, request.get_json(silent=True), idem)
        db.commit()
    except (RequestRefusal, FixRefusal) as refusal:
        db.rollback()
        return _fail(refusal.status, refusal.code, refusal.message)
    except LookupError:
        db.rollback()
        return _fail(404, "NOT_FOUND", _NOT_FOUND)
    except RevisionError as exc:
        db.rollback()
        return _fail(exc.status_code, exc.error_code, _SAVE_FAILED)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("[DRAWING_REQUEST] order %s: %s", order_id, exc)
        return _fail(500, "SAVE_FAILED", _SAVE_FAILED)
    if result["notification"] is not None:
        _announce(db, result["order"], user, result["notification"])
        invalidate_after_drawing_revision(result["order"])
    return _response(result)


def _audit_photo(db: Any, order: Order, user: Any, filename: str, key: str) -> None:
    """사진 한 장 감사 — 영업 창구 업로드와 같은 행동 이름(``DRAWING_GATEWAY_FILE_UPLOADED``)."""
    context = order_audit_context(order)
    log_access(describe_order_action(order_id=order.id, action=_UPLOADED, note=filename, **context), user.id,
               action=_UPLOADED, target_type="order", target_id=int(order.id),
               detail={"filename": filename, "storage_key": key, "via": "production_drawing_request", **context}, db=db)


@erp_orders_drawing_request_bp.route("/<int:order_id>/production/drawing-request/photo", methods=["POST"])
def api_production_drawing_request_photo(order_id: int):
    """요청 사진 한 장 올리기(요청을 보내기 전) — ``{file: {key, filename, view_url}}``."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "다시 로그인해 주세요.")
    if not can_request_people(user):
        return _fail(403, REQUEST_FORBIDDEN, MESSAGES[REQUEST_FORBIDDEN])
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return _fail(400, REQUEST_PHOTOS, PHOTOS_BAD)
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None or order.status == "DELETED" or order.deleted_at is not None or not order.is_erp_order:
        return _fail(404, "NOT_FOUND", _NOT_FOUND)
    if read_main_stage(order) != STAGE_PRODUCTION:
        return _fail(409, INVALID_STAGE, MESSAGES[INVALID_STAGE])
    if not has_requestable_drawing(user, _ensure_dict(order.structured_data)):  # 그 주문에 이 사람 몫 도면이 없다(남의 공장 주문)
        return _fail(403, REQUEST_FORBIDDEN, MESSAGES[REQUEST_FORBIDDEN])
    storage = get_storage()
    if storage.get_file_type(upload.filename) != "image":  # 그림 파일만(저장소 판정 — 첨부 · 창구가 쓰는 같은 확장자 표)
        return _fail(400, REQUEST_PHOTOS, PHOTOS_BAD)
    saved = storage.upload_file(upload, upload.filename, f"orders/{order_id}/drawing_gateway/revisions")
    rows, rejects = normalize_revision_files(order_id, [{"key": saved.get("key"), "filename": upload.filename}]) \
        if saved.get("success") else ([], ["upload"])
    if rejects:
        logger.warning("[DRAWING_REQUEST] photo upload refused order=%s: %s", order_id, rejects)
        return _fail(400, REQUEST_PHOTOS, PHOTOS_BAD)
    _audit_photo(db, order, user, rows[0]["filename"], rows[0]["key"])
    file = {k: rows[0][k] for k in ("key", "filename", "view_url")}
    return jsonify({"success": True, "data": {"file": file}, "error": None})


__all__ = ["REQUEST_POLICY_ID", "api_production_drawing_request", "api_production_drawing_request_photo",
           "erp_orders_drawing_request_bp"]
