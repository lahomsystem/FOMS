"""FOMS 공지사항 JSON API(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §4).

관리자(ADMIN · MANAGER) — ``notices_admin_api``, 접두 ``/api/admin/notices``:

- ``GET ""`` 목록(지운 것 빼고) · ``POST ""`` 만들기 · ``GET /<id>`` 한 건(고치기 화면) · ``PUT /<id>`` 고치기 ·
  ``DELETE /<id>`` 지우기(soft) · ``GET /<id>/status`` 확인 현황 · ``GET /audience-options`` 받는 사람 고르기 칩 · 수.
  만들기 · 고치기 커밋 뒤 지금 게시 중이고 아직 안 보낸 공지면 받는 사람 폰으로 보낸다(설계서 §7, 한 번만).

받는 사람(로그인한 본사 직원 · 협력사 직원) — ``notices_api``, 접두 ``/api/notices``:

- ``GET ""`` 내 공지 ``{items, unread, pending}``(목록 — 본문까지) · ``GET "?view=popup"`` 창 · 배지용 ``{pending, unread}``
  (본사 공용 창 스크립트가 모든 페이지에서 부른다 — 목록 본문을 싣지 않는다) · ``POST /<id>/ack`` 확인 → ``{pending, unread}`` ·
  ``POST /<id>/read`` 읽음.
  남의 공지 · 없는 공지 · 지난 공지는 404(있는지도 알리지 않는다). 협력사 문지기 허용 목록에 세 endpoint 가 있다.

미인증 401 · 관리자 아님 403(JSON — 리다이렉트 없음). 쓰기는 공용 CSRF · Origin 가드와 쓰기 정책 엔진 뒤
(manifest: 관리자 ``MANAGER_MUTATION`` · 받는 사람 ``ACCOUNT_SELF``). 응답은 ``{"success", "data", "error"}`` 이고 오류 글은
이 모듈과 :mod:`foms.services.notices.payload` 가 정한 글만 싣는다. 판정 · 쓰기는 :mod:`foms.services.notices.service`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.notices.admin import (
    ack_status,
    admin_notice_rows,
    audience_options as svc_audience_options,
    create_notice,
    delete_notice,
    notice_detail,
    update_notice,
)
from foms.services.notices.payload import NoticeInputError
from foms.services.notices.push import push_notice_if_due
from foms.services.notices.service import (
    ack_notice as svc_ack_notice,
    mark_read,
    notice_summary,
    pending_popups_from,
    unread_count,
    visible_notices,
)

logger = logging.getLogger(__name__)

notices_admin_api_bp = Blueprint("notices_admin_api", __name__, url_prefix="/api/admin/notices")
notices_api_bp = Blueprint("notices_api", __name__, url_prefix="/api/notices")

_ADMIN_ROLES = frozenset({"ADMIN", "MANAGER"})
_NOT_FOUND = "공지를 찾을 수 없습니다."
_SAVE_FAILED = "저장하지 못했습니다. 잠시 뒤 다시 해 주세요."


def _ok(data: Any, status: int = 200) -> tuple[Any, int]:
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _fail(status: int, error: str) -> tuple[Any, int]:
    return jsonify({"success": False, "data": None, "error": error}), status


def _signed_in() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    """켜진 로그인 사용자(본사 · 협력사 모두) — 아니면 401."""
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return None, _fail(401, "로그인이 필요합니다.")
    return user, None


def _admin() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    """켜진 ADMIN · MANAGER(본사 직원) — 아니면 401 · 403."""
    user, denied = _signed_in()
    if denied:
        return None, denied
    role = str(getattr(user, "role", "") or "").strip().upper()
    if role not in _ADMIN_ROLES or getattr(user, "partner_org_id", None) is not None:
        return None, _fail(403, "관리자만 쓸 수 있습니다.")
    return user, None


def _push_after_commit(db, notice_id: int) -> None:
    """커밋한 공지가 지금 게시 중이고 아직 안 보냈으면 폰으로 보낸다(설계서 §7). 실패해도 응답은 그대로 —
    보내지 못한 공지는 SIDEFX 예약 스캔이 다시 본다."""
    try:
        push_notice_if_due(db, notice_id, enqueue=True)
    except Exception:  # noqa: BLE001 - 공지는 이미 저장됐다
        db.rollback()
        logger.warning("[NOTICE] 공지 폰 알림 준비 실패 id=%s", notice_id, exc_info=True)


def _body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


# --------------------------------------------------------------------------
# 관리자
# --------------------------------------------------------------------------
@notices_admin_api_bp.route("", methods=["GET"], endpoint="list_notices")
def admin_list_notices():
    """관리자 공지 목록(지운 것 빼고)."""
    _actor, denied = _admin()
    if denied:
        return denied
    db = get_db()
    return _ok({"items": admin_notice_rows(db)})


@notices_admin_api_bp.route("/audience-options", methods=["GET"])
def audience_options():
    """받는 사람 고르기 칩 · 사람 수."""
    _actor, denied = _admin()
    if denied:
        return denied
    return _ok(svc_audience_options(get_db()))


@notices_admin_api_bp.route("", methods=["POST"], endpoint="create_notice")
def api_create_notice():
    """공지 만들기 — 틀리면 400(쉬운 한글 한 줄)."""
    actor, denied = _admin()
    if denied:
        return denied
    db = get_db()
    try:
        notice = create_notice(db, actor, _body())
        notice_id = int(notice.id)
        db.commit()
    except NoticeInputError as err:
        db.rollback()
        return _fail(400, str(err))
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[NOTICE] 공지 만들기 저장 실패", exc_info=True)
        return _fail(500, _SAVE_FAILED)
    _push_after_commit(db, notice_id)
    return _ok(notice_detail(db, notice_id), 201)


@notices_admin_api_bp.route("/<int:notice_id>", methods=["GET"])
def get_notice(notice_id: int):
    """공지 한 건(고치기 화면) — 없거나 지웠으면 404."""
    _actor, denied = _admin()
    if denied:
        return denied
    detail = notice_detail(get_db(), notice_id)
    if detail is None:
        return _fail(404, _NOT_FOUND)
    return _ok(detail)


@notices_admin_api_bp.route("/<int:notice_id>", methods=["PUT"], endpoint="update_notice")
def api_update_notice(notice_id: int):
    """공지 고치기 — 없거나 지웠으면 404, 틀리면 400."""
    actor, denied = _admin()
    if denied:
        return denied
    db = get_db()
    try:
        notice = update_notice(db, actor, notice_id, _body())
        if notice is None:
            db.rollback()
            return _fail(404, _NOT_FOUND)
        db.commit()
    except NoticeInputError as err:
        db.rollback()
        return _fail(400, str(err))
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[NOTICE] 공지 고치기 저장 실패 id=%s", notice_id, exc_info=True)
        return _fail(500, _SAVE_FAILED)
    # 예약이었던 공지를 지금 게시로 바꿨으면 여기서 보낸다(이미 보낸 공지는 다시 보내지 않는다).
    _push_after_commit(db, notice_id)
    return _ok(notice_detail(db, notice_id))


@notices_admin_api_bp.route("/<int:notice_id>", methods=["DELETE"], endpoint="delete_notice")
def api_delete_notice(notice_id: int):
    """공지 지우기(soft) — 없거나 이미 지웠으면 404."""
    actor, denied = _admin()
    if denied:
        return denied
    db = get_db()
    try:
        if not delete_notice(db, actor, notice_id):
            db.rollback()
            return _fail(404, _NOT_FOUND)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[NOTICE] 공지 지우기 저장 실패 id=%s", notice_id, exc_info=True)
        return _fail(500, _SAVE_FAILED)
    return _ok({"id": int(notice_id), "deleted": True})


@notices_admin_api_bp.route("/<int:notice_id>/status", methods=["GET"])
def notice_status(notice_id: int):
    """확인 현황 — 없거나 지웠으면 404."""
    _actor, denied = _admin()
    if denied:
        return denied
    status = ack_status(get_db(), notice_id)
    if status is None:
        return _fail(404, _NOT_FOUND)
    return _ok(status)


# --------------------------------------------------------------------------
# 받는 사람(본사 · 협력사)
# --------------------------------------------------------------------------
@notices_api_bp.route("", methods=["GET"])
def list_notices():
    """내 공지 목록 · 안 읽음 수 · 확인 안 한 창 공지. ``?view=popup`` 이면 목록 없이 ``{pending, unread}`` 만."""
    user, denied = _signed_in()
    if denied:
        return denied
    if request.args.get("view") == "popup":
        return _ok(notice_summary(get_db(), user))
    items = visible_notices(get_db(), user)
    return _ok({
        "items": items,
        "unread": sum(1 for item in items if not item["read"]),
        "pending": pending_popups_from(items),
    })


@notices_api_bp.route("/<int:notice_id>/ack", methods=["POST"])
def ack_notice(notice_id: int):
    """공지 확인 — 남은 창 공지를 돌려준다(창이 다음 공지를 띄운다). 내 공지가 아니면 404."""
    user, denied = _signed_in()
    if denied:
        return denied
    db = get_db()
    try:
        if not svc_ack_notice(db, user, notice_id):
            db.rollback()
            return _fail(404, _NOT_FOUND)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[NOTICE] 공지 확인 저장 실패 id=%s", notice_id, exc_info=True)
        return _fail(500, _SAVE_FAILED)
    return _ok(notice_summary(db, user))


@notices_api_bp.route("/<int:notice_id>/read", methods=["POST"])
def read_notice(notice_id: int):
    """공지 읽음(목록에서 열어 봄). 내 공지가 아니면 404."""
    user, denied = _signed_in()
    if denied:
        return denied
    db = get_db()
    try:
        if not mark_read(db, user, notice_id):
            db.rollback()
            return _fail(404, _NOT_FOUND)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[NOTICE] 공지 읽음 저장 실패 id=%s", notice_id, exc_info=True)
        return _fail(500, _SAVE_FAILED)
    return _ok({"id": int(notice_id), "read": True, "unread": unread_count(db, user)})
