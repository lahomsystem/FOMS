"""HTTP routes for the canonical files API (`foms.api.files` package).

Registry and product code import `foms.api.files` directly.
Wave 8 (W8-B5): legacy `apps.api.files` direct-import bridge removed.
"""
from __future__ import annotations

import logging
import os
import posixpath

from flask import Blueprint, Response, g, jsonify, redirect, request, send_file
from sqlalchemy import or_

from db import get_db
from models import Order, OrderAttachment
from foms.web.auth import login_required
from foms.services import audit_writer
from foms.services.attachment_visibility import include_deleted
from foms.services.files.list_thumb import (
    LIST_THUMB_CACHE_CONTROL,
    LIST_THUMB_LONG_EDGE,
    LIST_THUMB_ROUTE_PREFIX,
    LIST_THUMB_SIZES,
    is_list_thumb_source,
    list_thumb_key,
    list_thumb_query,
)
from foms.services.files.list_thumb_schedule import schedule_list_thumb
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.storage import get_storage

logger = logging.getLogger(__name__)

_ACCESS_DENIED_MSG = "이 파일에 접근할 권한이 없습니다."
_FILE_NOT_FOUND_MSG = "파일을 찾을 수 없습니다."

#: ``access_logs.action`` 태그 (AUDIT-LOG T6). 조회 화면은 없다 — SQL 전용(스펙 §3-1).
ACTION_FILE_VIEW = "FILE_VIEW"
ACTION_FILE_PRESIGNED = "FILE_PRESIGNED"
ACTION_FILE_DOWNLOAD = "FILE_DOWNLOAD"


def _user_id(user) -> int | None:
    try:
        return int(getattr(user, "id", None))
    except (TypeError, ValueError):
        return None


def _deny_order_scope(user, order_id: int):
    """order_id 소유 order 를 read scope(:func:`user_can_read_order`)로 게이트."""
    order = get_db().query(Order).filter(Order.id == order_id).first()
    if not user_can_read_order(user, order):
        return 403, _ACCESS_DENIED_MSG
    return None


def _deny_draft_scope(user, owner_id: int):
    """``order-drafts/{user_id}/...`` 는 본인(또는 ADMIN/MANAGER)만 접근."""
    role = (getattr(user, "role", None) or "").strip().upper()
    if owner_id == _user_id(user) or role in ("ADMIN", "MANAGER"):
        return None
    return 403, _ACCESS_DENIED_MSG


def _deny_deleted_attachment(storage_key: str):
    """tombstone 된 첨부의 object key 면 404 로 막는다 (ATTACH-LIFE-01).

    canonical key 경로(``orders/<id>/...``)는 :func:`_deny_order_scope` 만 타고
    ``order_attachments`` 행을 **조회하지 않기 때문에**, 이 lookup 이 없으면 삭제된 첨부가
    blob purge 유예 기간 내내 그대로 열람된다. 전역 tombstone 필터는 살아있는 행만
    돌려주므로 여기서는 ``include_deleted`` opt-in 으로 삭제 행을 직접 찾는다.

    Args:
        storage_key: 요청된 object key 원문(본체 또는 썸네일 key).

    Returns:
        삭제된 첨부면 ``(404, message)``, 아니면 ``None``.
    """
    row = (
        include_deleted(
            get_db()
            .query(OrderAttachment.id)
            .filter(
                OrderAttachment.deleted_at.isnot(None),
                or_(OrderAttachment.storage_key == storage_key,
                    OrderAttachment.thumbnail_key == storage_key),
            )
        )
        .first()
    )
    return (404, _FILE_NOT_FOUND_MSG) if row is not None else None


def _deny_file_access(storage_key: str):
    """view/download/presigned 공용 권한 게이트 (FILE-01).

    요청 key 의 소유 order 를 canonical key path 또는 attachment row 로 resolve 한 뒤
    order read scope 를 적용한다. resolve 되지 않는 raw/비정규 key 는 거부한다(arbitrary
    object 접근 차단). ``ponytail: order read scope 는 현재 order-무관 전역 read 이나
    per-order 확장 시 자동 적용되도록 chokepoint 로 order 를 load 한다``.

    Args:
        storage_key: 요청된 object key(``<path:storage_key>``).

    Returns:
        거부면 ``(status, message)``, 허용이면 ``None``.
    """
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return 403, _ACCESS_DENIED_MSG

    raw = (storage_key or "").strip()
    norm = posixpath.normpath(raw) if raw else ""
    canonical = bool(raw) and norm == raw and not norm.startswith(("..", "/"))
    if canonical:
        parts = norm.split("/")
        if len(parts) >= 2 and parts[1].isdigit():
            if parts[0] == "orders":
                denied = _deny_order_scope(user, int(parts[1]))
                if denied:
                    return denied
                # canonical 분기는 attachment row 를 안 보므로 tombstone 을 직접 판정한다.
                # read scope 통과 뒤에 두어 비인가 사용자에게 "삭제됨"을 알리지 않는다.
                return _deny_deleted_attachment(raw)
            if parts[0] == "order-drafts":
                return _deny_draft_scope(user, int(parts[1]))

    # legacy coverage gate: 비정규/미지원 namespace 는 attachment row 가 cover 해야 허용.
    # 이 조회는 전역 tombstone 필터를 그대로 받는다 — 삭제된 첨부는 여기서 안 잡히고
    # ``att is None`` 으로 떨어져 403 이 된다(별도 분기 불필요).
    att = (
        get_db()
        .query(OrderAttachment)
        .filter(or_(OrderAttachment.storage_key == raw,
                    OrderAttachment.thumbnail_key == raw))
        .first()
    )
    if att is None:
        return 403, _ACCESS_DENIED_MSG
    return _deny_order_scope(user, att.order_id)


def _order_id_from_key(storage_key: str) -> int | None:
    """canonical ``orders/<id>/...`` key 에서 주문 id 를 뽑는다.

    ``order-drafts/<user_id>/...`` 는 주문 id 가 아니므로 제외한다. 파싱 실패는 감사
    보조 정보 부재일 뿐이라 조용히 ``None`` 이다.

    Args:
        storage_key: 요청된 object key 원문.

    Returns:
        주문 id, 또는 canonical order key 가 아니면 ``None``.
    """
    parts = (storage_key or "").split("/")
    if len(parts) >= 2 and parts[0] == "orders" and parts[1].isdigit():
        return int(parts[1])
    return None


def _record_file_access(
    action: str, storage_key: str, *, dedupe_window_seconds: float | None = None
) -> None:
    """파일 접근 1건을 ``access_logs`` 에 독립 커밋한다 (AUDIT-LOG T6).

    파일 라우트는 GET 이라 본 트랜잭션 commit 이 없다 — 동승 기록은 teardown 에서 소실되므로
    전용 감사 engine 으로 즉시 커밋한다(:mod:`foms.services.audit_writer`). 기록 실패는
    writer 안에서 로그 후 흡수되며 파일 응답에 **절대** 영향을 주지 않는다.

    ``StorageAdapter.get_download_url`` 메서드 내부가 아니라 **라우트 호출부**에만 둔다 —
    그 메서드는 채널·WAM·admin 헬스체크 등 14곳이 호출하므로 내부 계측은 감사 테이블을
    비-사용자 트래픽으로 오염시킨다(스펙 §4 T6).

    Args:
        action: ``FILE_VIEW``/``FILE_PRESIGNED``/``FILE_DOWNLOAD``.
        storage_key: 접근 대상 object key.
        dedupe_window_seconds: dedupe 창(초). ``None`` 이면 매 건 기록.
    """
    user = getattr(g, "current_user", None)
    audit_writer.record_file_access(
        action,
        storage_key=storage_key,
        user_id=_user_id(user) if user is not None else None,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        order_id=_order_id_from_key(storage_key),
        dedupe_window_seconds=dedupe_window_seconds,
    )


def build_file_view_url(storage_key: str) -> str:
    """파일 미리보기 URL 생성 (files_bp /api/files/view 경로)"""
    return f"/api/files/view/{storage_key}"


def build_file_thumb_url(storage_key: str, size: int = LIST_THUMB_LONG_EDGE) -> str:
    """목록 작은 그림 URL 생성 (files_bp /api/files/thumb 경로 — 원본 key 를 받는다).

    작은 칸(40~112px)의 ``<img src>`` 전용. 눌러 크게 보기는 :func:`build_file_view_url`(원본)이다.
    그림이 아닌 key 는 길이 404 이므로 부르는 쪽이 ``is_list_thumb_source`` 로 먼저 거른다(서비스 레이어는
    같은 모양을 :func:`foms.services.files.list_thumb.list_thumb_url` 로 만든다 — 거르기까지 한 번에).
    ``size=640`` 이면 중간 크기 칸용 ``?w=640``(SPEC 2026-11-20-mid-size-image). 320 주소는 꼬리가 없다.
    """
    return f"{LIST_THUMB_ROUTE_PREFIX}{storage_key}{list_thumb_query(size)}"


def build_file_download_url(storage_key: str) -> str:
    """파일 다운로드 URL 생성 (files_bp /api/files/download 경로)"""
    return f"/api/files/download/{storage_key}"


files_bp = Blueprint("files", __name__, url_prefix="/api/files")


def _with_no_store(response):
    """Prevent browser/SW reuse of short-lived storage redirects and URL JSON."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _no_store_json(payload: dict, status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    return _with_no_store(response)


@files_bp.route("/view/<path:storage_key>", methods=["GET"])
@login_required
def view(storage_key: str):
    """공용 파일 미리보기(인라인)"""
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return jsonify({"success": False, "message": "비정상적인 경로입니다."}), 400

        denied = _deny_file_access(storage_key)
        if denied:
            status, message = denied
            return jsonify({"success": False, "message": message}), status

        storage = get_storage()
        if storage.storage_type in ["r2", "s3"]:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if not url:
                return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
            # 302 를 실제로 발급할 때만 기록한다(권한 거부·404 는 접근이 아니다).
            _record_file_access(
                ACTION_FILE_VIEW, storage_key,
                dedupe_window_seconds=audit_writer.ACCESS_VIEW_DEDUPE_WINDOW_SECONDS,
            )
            return _with_no_store(redirect(url))

        # 로컬 스토리지 send_file 경로는 미계측 — 운영은 R2 전용이라 스펙 §4 T6 이 한계로 수용.
        file_path = os.path.join(storage.upload_folder, storage_key)
        if not os.path.exists(file_path):
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
        return send_file(file_path, as_attachment=False)
    except Exception:
        logger.exception("파일 미리보기 오류")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "파일을 처리하는 중 오류가 발생했습니다.",
                }
            ),
            500,
        )


def _thumb_size_arg(raw: str | None) -> int | None:
    """``?w=`` → 허용 크기(320 · 640). 없으면 320(기본), 그 밖(숫자 아님 · 빈 값 포함)은 None → 400.

    아무 크기나 받으면 저장소에 파생 파일이 끝없이 쌓인다(SPEC 2026-11-20-mid-size-image §3-1 ①).
    """
    if raw is None:
        return LIST_THUMB_LONG_EDGE
    # 글자 그대로만 맞춘다(``0640`` · 전각 숫자 · 앞뒤 빈칸 = 400) — 같은 그림에 주소가 여럿 생기지 않게.
    return next((size for size in LIST_THUMB_SIZES if raw == str(size)), None)


@files_bp.route("/thumb/<path:storage_key>", methods=["GET"])
@login_required
def thumb(storage_key: str):
    """목록 작은 그림(긴 변 320px JPEG, ``?w=640`` 이면 640px) — SPEC 2026-11-19-list-drawing-small-image §3-1.

    ``?w=`` 는 320(기본) · 640 둘만 받는다(그 밖은 400, SPEC 2026-11-20-mid-size-image). 저장 이름 · 워커 작업 ·
    자물쇠가 크기마다 따로이고, 문지기 · 캐시 머리글 · 감사 기록 없음 · 원본 302 는 크기와 상관없이 같다.

    문지기는 원본 보기와 같은 :func:`_deny_file_access`(원본 key). 저장된 작은 그림이 있으면 그 바이트를
    ``immutable`` 로, 없으면 워커에 만들기를 한 번 예약하고 이번만 원본으로 보낸다(``no-store`` 302 —
    보기 길과 같은 서명 주소). **web 은 그림을 줄이지 않는다.**

    감사 기록(``FILE_VIEW``)은 남기지 않는다 — 목록 미리보기는 화면 그리기 부산물이고 한 화면이 서로 다른
    key 수백 개를 부른다(``audit_writer.ACCESS_VIEW_SKIP_BASENAME_PREFIXES`` 의 ``thumb_`` 예외와 같은 취지).
    원본을 눌러 크게 보면 보기 길이 지금처럼 남긴다.
    """
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return jsonify({"success": False, "message": "비정상적인 경로입니다."}), 400
        size = _thumb_size_arg(request.args.get("w"))
        if size is None:
            return jsonify({"success": False, "message": "지원하지 않는 그림 크기입니다."}), 400
        if not is_list_thumb_source(storage_key):
            return jsonify({"success": False, "message": _FILE_NOT_FOUND_MSG}), 404

        denied = _deny_file_access(storage_key)
        if denied:
            status, message = denied
            return jsonify({"success": False, "message": message}), status

        storage = get_storage()
        small_key = list_thumb_key(storage_key, size)
        if storage.storage_type in ["r2", "s3"]:
            data = storage.read_file_bytes(small_key) if storage.object_exists(small_key) else None
            if data:
                response = Response(data, mimetype="image/jpeg")
                response.headers["Cache-Control"] = LIST_THUMB_CACHE_CONTROL
                return response
            schedule_list_thumb(storage_key, size)  # 큐가 없거나 막히면 조용히 건너뜀(원본이 계속 나간다)
            url = storage.get_download_url(storage_key, expires_in=3600)
            if not url:
                return jsonify({"success": False, "message": _FILE_NOT_FOUND_MSG}), 404
            return _with_no_store(redirect(url))

        # 로컬 저장소: 비공개 저장(put_private_bytes)을 받지 않아 작은 그림이 저절로 생기지 않는다(개발용).
        # 저장본이 있으면 그것, 없으면 원본을 그대로 — 개발 화면이 깨지지 않게.
        small_path = os.path.join(storage.upload_folder, small_key)
        if os.path.isfile(small_path):
            response = send_file(small_path, mimetype="image/jpeg", conditional=False)
            response.headers["Cache-Control"] = LIST_THUMB_CACHE_CONTROL
            return response
        file_path = os.path.join(storage.upload_folder, storage_key)
        if not os.path.exists(file_path):
            return jsonify({"success": False, "message": _FILE_NOT_FOUND_MSG}), 404
        return _with_no_store(send_file(file_path, as_attachment=False))
    except Exception:
        logger.exception("작은 그림 오류")
        return jsonify({"success": False, "message": "파일을 처리하는 중 오류가 발생했습니다."}), 500


@files_bp.route("/presigned-urls/<path:storage_key>", methods=["GET"])
@login_required
def presigned_urls(storage_key: str):
    """R2/S3 직접 링크용 presigned URL 반환. 미리보기/다운로드 시 앱 경유 없이 최단 경로."""
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return _no_store_json({"success": False, "message": "비정상적인 경로입니다."}, 400)

        denied = _deny_file_access(storage_key)
        if denied:
            status, message = denied
            return _no_store_json({"success": False, "message": message}, status)

        storage = get_storage()
        if storage.storage_type in ["r2", "s3"]:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if not url:
                return _no_store_json({"success": False, "message": "파일을 찾을 수 없습니다."}, 404)
            # 서명 URL 발급 = 앱 밖에서 열람 가능한 권한을 넘기는 것 — dedupe 없이 매 건 기록.
            _record_file_access(ACTION_FILE_PRESIGNED, storage_key)
            return _no_store_json({"success": True, "view_url": url, "download_url": url})

        # 로컬 모드는 서명 URL 을 발급하지 않고 앱 경유 URL 만 돌려준다(접근 아님 — 미계측).
        return _no_store_json(
            {
                "success": True,
                "view_url": build_file_view_url(storage_key),
                "download_url": build_file_download_url(storage_key),
            }
        )
    except Exception:
        logger.exception("presigned-urls 오류")
        return (
            _no_store_json(
                {
                    "success": False,
                    "message": "파일을 처리하는 중 오류가 발생했습니다.",
                },
                500,
            )
        )


@files_bp.route("/download/<path:storage_key>", methods=["GET"])
@login_required
def download(storage_key: str):
    """공용 파일 다운로드. R2/S3에서는 presigned URL에 ResponseContentDisposition(attachment)을 넣어 새 창에서도 다운로드되게 함."""
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return jsonify({"success": False, "message": "비정상적인 경로입니다."}), 400

        denied = _deny_file_access(storage_key)
        if denied:
            status, message = denied
            return jsonify({"success": False, "message": message}), status

        storage = get_storage()
        if storage.storage_type in ["r2", "s3"]:
            filename = os.path.basename(storage_key)
            if not filename:
                filename = "download"
            filename_safe = filename.replace('"', "'")
            disposition = f'attachment; filename="{filename_safe}"'
            url = storage.get_download_url(
                storage_key,
                expires_in=3600,
                response_content_disposition=disposition,
            )
            if not url:
                return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
            # 다운로드는 의도적 1회 행위 — dedupe 하지 않는다(반복 = 반복 반출).
            _record_file_access(ACTION_FILE_DOWNLOAD, storage_key)
            return _with_no_store(redirect(url))

        # 로컬 스토리지 send_file 경로는 미계측(스펙 §4 T6 한계 — 운영은 R2).
        file_path = os.path.join(storage.upload_folder, storage_key)
        if not os.path.exists(file_path):
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
        return send_file(file_path, as_attachment=True)
    except Exception:
        logger.exception("파일 다운로드 오류")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "파일을 처리하는 중 오류가 발생했습니다.",
                }
            ),
            500,
        )
