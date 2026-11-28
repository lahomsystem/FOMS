"""생산 도면 펜 기록 API — 도면에 펜으로 적은 치수 · 메모(설계서 2026-11-28 생산 도면 펜 기록 §8 · §6-5 · 약속 4).

* ``GET /api/production/drawing-notes?order_id=&drawing_key=`` — 쓰기 화면을 열 때 한 번. ``data.note`` =
  ``{objects, base_w, base_h, version, by, at}`` 또는 null. 문 = 생산 첫 화면을 볼 수 있음(:func:`can_view_production_home`) +
  그 주문 읽기 범위 + key 가 지금 확정 도면 + 그림 도면.
* ``PUT /api/production/drawing-notes`` — 저장. ``multipart/form-data``: ``payload``(JSON 글 — ``order_id`` · ``drawing_key`` ·
  ``objects`` · ``base_w`` · ``base_h`` · ``seen_version``(연 순간의 버전, 새 기록이면 0)) + ``ink``(펜 기록만 그린 투명 PNG).
  ``data.note`` = ``{version, view_url, by, at}``. 문 = :func:`~foms.services.production.pen_record.can_write`.
* ``DELETE /api/production/drawing-notes`` — 기록 지우기(JSON ``{order_id, drawing_key, seen_version}``). ``data.note`` = null.

스위치(``pen_record.enabled``)가 꺼져 있으면 셋 다 없는 길과 같은 404 다. 거절은 생산 파트 표시 API 와 같은 꼴
``{"success": false, "data": {"code": "<코드>"}, "error": "<글>"}``(코드 · 글은 :mod:`~foms.services.production.drawing_note_write`).
쓰기 둘은 다른 생산 쓰기처럼 before_request 의 CSRF · 정책 가드(매니페스트 두 곳 — ``PRODUCTION_EDIT``)가 먼저 건다.
이 모듈은 스위치 · 로그인 · 몸 읽기 · tx(커밋 · 되감기 · 되감은 요청이 올린 그림 지우기)만 맡는다. API 층은 웹 층을 부르지 않는다.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from db import get_db
from foms.services.common.dashboard_cache import ATTACHMENT_DASHBOARD_FAMILIES, invalidate_dashboard_families
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.production import pen_record
from foms.services.production.drawing_note_write import (
    MAX_INK_BYTES,
    NoteJob,
    NoteRefusal,
    changed_message,
    delete_note,
    discard_uploads,
    read_note,
    save_note,
    winner_message,
)
from foms.services.production.home_access import can_view_production_home

production_drawing_notes_bp = Blueprint("production_drawing_notes", __name__, url_prefix="/api/production")

#: ``payload`` 글의 상한(검사 전 — 기록 원본 400KB 는 검사가 따로 잰다). 넘으면 바로 413. 폼 칸 하나가 1 MiB 를 넘으면 그 앞에서
#: 플랫폼(``foms/platform/request_limits.py``)이 413 ``REQUEST_BODY_TOO_LARGE`` 로 먼저 막는다.
MAX_PAYLOAD_CHARS = 1_000_000
_READ_FAILED = "기록을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요."


def _ok(data: dict[str, Any]):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200


def _fail(status: int, code: str, message: str):
    return jsonify({"success": False, "data": {"code": code}, "error": message}), status


def _refused(refusal: NoteRefusal):
    return _fail(refusal.status, refusal.code, refusal.message)


def _user() -> Any:
    """스위치(꺼짐 = 없는 길과 같은 404) → 로그인(``_set_current_user`` 가 비활성 · 끊긴 세션은 이미 비웠다)."""
    if not pen_record.enabled():
        abort(404)
    return getattr(g, "current_user", None)


def _order_id(value: Any) -> int:
    if isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise NoteRefusal("BAD_REQUEST")
    return value


def _drawing_key(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > 500:
        raise NoteRefusal("BAD_REQUEST")
    return text


def _seen_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise NoteRefusal("BAD_REQUEST")
    return value


def _put_job() -> NoteJob:
    """``multipart/form-data`` 몸 → :class:`NoteJob`(기록 원본 · 좌표 기준은 버전 견줌 뒤에 서비스가 검사한다)."""
    raw = request.form.get("payload")
    if not isinstance(raw, str) or not raw:
        raise NoteRefusal("BAD_REQUEST")
    if len(raw) > MAX_PAYLOAD_CHARS:
        raise NoteRefusal("NOTE_TOO_LARGE")
    try:
        body = json.loads(raw)
    except ValueError:
        raise NoteRefusal("BAD_REQUEST") from None
    if not isinstance(body, dict):
        raise NoteRefusal("BAD_REQUEST")
    ink_file = request.files.get("ink")
    ink = ink_file.read(MAX_INK_BYTES + 1) if ink_file is not None else b""
    if len(ink) > MAX_INK_BYTES:
        raise NoteRefusal("NOTE_TOO_LARGE")
    return NoteJob(order_id=_order_id(body.get("order_id")), key=_drawing_key(body.get("drawing_key")),
                   seen_version=_seen_version(body.get("seen_version")), objects=body.get("objects"),
                   base_w=body.get("base_w"), base_h=body.get("base_h"), ink=ink)


def _write(make_job: Callable[[], NoteJob], handler: Callable[[Any, Any, NoteJob], dict[str, Any]]):
    """쓰기 한 번 — 스위치 · 로그인 · 쓰기 문(몸 읽기보다 먼저, §8 "문 →") · 몸 → 한 tx. 되감으면 올린 그림을 지운다."""
    user = _user()
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "로그인이 필요해요.")
    if not pen_record.can_write(user):
        return _refused(NoteRefusal("PEN_FORBIDDEN"))
    try:
        job = make_job()
    except NoteRefusal as refusal:
        return _refused(refusal)
    db = get_db()
    try:
        data = handler(db, user, job)
        db.commit()
    except NoteRefusal as refusal:
        db.rollback()
        discard_uploads(job)
        return _refused(refusal)
    except IntegrityError:  # 같은 장 첫 저장이 동시에 두 번(잠금 없는 레인) — 나중 것은 낡은 화면이다
        db.rollback()
        discard_uploads(job)
        try:
            message = winner_message(db, job.order_id, job.key)
        except SQLAlchemyError:
            db.rollback()
            message = changed_message(None)
        return _refused(NoteRefusal("NOTE_CHANGED", message))
    except SQLAlchemyError:
        db.rollback()
        discard_uploads(job)
        return _refused(NoteRefusal("SAVE_FAILED"))
    invalidate_dashboard_families(*ATTACHMENT_DASHBOARD_FAMILIES)  # 첨부 '생산' 분류가 바뀌었다(업로드 · 삭제와 같은 캐시)
    return _ok(data)


@production_drawing_notes_bp.route("/drawing-notes", methods=["GET"])
def api_drawing_note_get():
    """쓰기 화면을 열 때 한 번 — 그 장의 기록 원본(없으면 null). 읽기 전용."""
    user = _user()
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "로그인이 필요해요.")
    # 주문 없이 묻는 읽기 범위 — 우리 직원은 전역, 협력사 · 켜진 프리랜서는 주문마다라 이 길을 받지 않는다(30초 받아 오기와 같은 문)
    if not can_view_production_home(user) or not user_can_read_order(user, None):
        return _fail(403, "FORBIDDEN", "생산 화면을 볼 수 있는 직원만 볼 수 있어요.")
    db = get_db()
    try:
        order_id, key = _order_id(request.args.get("order_id")), _drawing_key(request.args.get("drawing_key"))
        data = read_note(db, user, order_id, key)
    except NoteRefusal as refusal:
        db.rollback()
        return _refused(refusal)
    except SQLAlchemyError:
        db.rollback()
        return _fail(500, "READ_FAILED", _READ_FAILED)
    db.rollback()  # 읽기만 했다
    return _ok(data)


@production_drawing_notes_bp.route("/drawing-notes", methods=["PUT"])
def api_drawing_note_put():
    """저장 — 기록 원본은 새 표에, 도면 + 기록을 합친 그림은 주문 첨부 '생산' 분류에(같은 도면 앞 그림은 지운 표시)."""
    return _write(_put_job, lambda db, user, job: save_note(db, user, job))  # 감사 한 줄은 save_note 안(감사 스캔이 호출을 따라간다)


def _delete_job() -> NoteJob:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise NoteRefusal("BAD_REQUEST")
    return NoteJob(order_id=_order_id(body.get("order_id")), key=_drawing_key(body.get("drawing_key")),
                   seen_version=_seen_version(body.get("seen_version")))


@production_drawing_notes_bp.route("/drawing-notes", methods=["DELETE"])
def api_drawing_note_delete():
    """기록 지우기 — 화면의 "다 지우고 [저장]". 기록 줄을 지우고 합친 그림도 지운 표시(15번 답 "그림도 지움")."""
    return _write(_delete_job, lambda db, user, job: delete_note(db, user, job))


__all__ = ["api_drawing_note_delete", "api_drawing_note_get", "api_drawing_note_put", "production_drawing_notes_bp"]
