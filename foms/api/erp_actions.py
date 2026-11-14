"""한 곳 승인 대기 — ERP 할 일 제안 JSON API(설계서 2026-11-14-foms-graft 3.5 · 3.6, 머리 ``/api/erp-actions``).

읽기: ``GET /badge`` 수 · ``GET /open?order_ids=1,2`` 주문 칩(100개까지) · ``GET /inbox`` 카드 · ``GET /proposals/<번호>`` 자세히.
쓰기: ``POST /proposals/<번호>/approve`` · ``/reject`` · ``/snooze``(공용 CSRF · Origin 가드 뒤 · 길 목록 ``STAFF_MUTATION`` —
처리기 안에서 할 일의 ``policy_id`` 를 생명주기가 다시 본다. 가드가 꺼진 시험 맥락에서도 뚫리지 않는다).

- 여는 사람: :func:`.access.actions_viewer`(켜진 내부 계정 + ``actions`` 스위치 + 통과하는 정책 하나) — 아니면 404, 로그인 안 함 401.
  협력사 · 꺼진 계정 · 스위치 꺼짐도 404(협력사 세션은 앞 문지기가 먼저 막는다). 볼 수 없는 제안은 없는 제안과 같은 404.
- 결정한 사람은 로그인 사용자(``g.current_user``)뿐 — 본문의 사람 칸은 읽지 않는다.
- 답은 ``{"success", "data", "error"}`` · ``Cache-Control: private, no-store``(사람마다 다르다). 오류 글은 실패 표의 말 · 막는 조건의 말만.
- 승인 대기 읽기(``/inbox``)는 되맞추기(``executing`` 2분 넘김 · 끝난 바로가기)를 먼저 돌린다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.api.erp_action_runners import RUNNERS
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive
from foms.services.erp_actions.access import actions_viewer
from foms.services.erp_actions.lifecycle import ActionError, approve, reconcile, reject, snooze
from foms.services.erp_actions.registry import message
from foms.services.erp_actions.views import MAX_ORDER_IDS, badge, detail, inbox, open_for_orders

logger = logging.getLogger(__name__)

erp_actions_api_bp = Blueprint("erp_actions_api", __name__, url_prefix="/api/erp-actions")

__all__ = ["erp_actions_api_bp"]

_STATUS = {"ACTION_FORBIDDEN": 404, "ACTION_SHAPE": 400, "ACTION_NOT_OPEN": 409, "ACTION_BASE_CHANGED": 409,
           "ACTION_PRECONDITION": 409}
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."


def _reply(status: int, data: Any, error: Optional[str]) -> tuple[Any, int]:
    """답 — 사람마다 보이는 것이 달라 캐시하지 않는다."""
    response = jsonify({"success": error is None, "data": data, "error": error})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _viewer() -> tuple[Any, Optional[tuple[Any, int]]]:
    """로그인 안 함 401 · 볼 수 없는 사람 404 · 볼 수 있으면 (사용자, None)."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, _reply(401, None, "로그인이 필요합니다.")
    if not actions_viewer(user):
        return None, _reply(404, None, message("ACTION_FORBIDDEN"))
    return user, None


def _body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _int(value: Any) -> Optional[int]:
    """정수만(참 · 거짓 · 글자는 ``None``)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _error(db: Any, user: Any, exc: ActionError) -> tuple[Any, int]:
    """생명주기 거절 → 답. 기준 판이 바뀌었으면 새 카드(자세히)를 싣는다."""
    db.rollback()
    status = _STATUS.get(exc.code, 409)
    if status == 404:
        return _reply(404, None, message("ACTION_FORBIDDEN"))
    data: dict[str, Any] = {"code": exc.code}
    if exc.fields:
        data["fields"] = list(exc.fields)
    if exc.code == "ACTION_PRECONDITION":
        data["reason"] = exc.message
    if exc.code == "ACTION_BASE_CHANGED" and exc.proposal_id is not None:
        data["card"] = detail(db, user, exc.proposal_id, now_utc_naive())
        db.rollback()
    return _reply(status, data, exc.message)


def _write(run: Any) -> tuple[Any, int]:
    """쓰기 하나 — 볼 수 있나 → 생명주기 → (필요하면) 커밋. 생명주기 거절 · DB 오류는 되감는다."""
    user, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    try:
        data = run(db, user)
        db.commit()
    except ActionError as exc:
        return _error(db, user, exc)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[ERP-ACTION] 쓰기 DB 오류 endpoint=%s", request.endpoint)
        return _reply(500, None, _SAVE_FAILED)
    return _reply(200, data, None if data.get("status") != "failed" else data.get("message"))


def _read(build: Any) -> tuple[Any, int]:
    """읽기 하나 — 볼 수 있나 → 읽기 → 읽기 트랜잭션 닫기(없으면 404)."""
    user, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    try:
        data = build(db, user)
    finally:
        db.rollback()
    return _reply(200, data, None) if data is not None else _reply(404, None, message("ACTION_FORBIDDEN"))


def _order_ids(raw: str) -> Optional[list[int]]:
    """``1,2,3`` → 주문 번호(겹침 빼고). 100개를 넘으면 ``None``(꼴 오류), 숫자가 아닌 조각은 버린다."""
    ids = list(dict.fromkeys(int(part) for part in (raw or "").split(",") if part.strip().isdigit()))
    return ids if len(ids) <= MAX_ORDER_IDS else None


# ── 읽기 ─────────────────────────────────────────────────────────────────
@erp_actions_api_bp.route("/badge", methods=["GET"])
def erp_actions_badge() -> tuple[Any, int]:
    """위 아이콘 · 레일 · 폰 칸 수(이 사람 기준)."""
    return _read(lambda db, user: badge(db, user, now=now_utc_naive()))


@erp_actions_api_bp.route("/open", methods=["GET"])
def erp_actions_open() -> tuple[Any, int]:
    """보이는 주문들의 제안 칩(질의 하나)."""
    user, denied = _viewer()
    if denied:
        return denied
    ids = _order_ids(request.args.get("order_ids", ""))
    if ids is None:
        return _reply(400, {"code": "ACTION_SHAPE", "fields": ["order_ids"]}, message("ACTION_SHAPE"))
    db = get_db()
    try:
        items = open_for_orders(db, user, ids, now=now_utc_naive())
    finally:
        db.rollback()
    return _reply(200, {"items": {str(order_id): item for order_id, item in items.items()}}, None)


@erp_actions_api_bp.route("/inbox", methods=["GET"])
def erp_actions_inbox() -> tuple[Any, int]:
    """승인 대기 카드 — 되맞추기를 먼저 돌린다(바뀐 줄이 있으면 커밋)."""
    user, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    now = now_utc_naive()
    try:
        if reconcile(db, now):
            db.commit()
        data = inbox(db, user, now)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[ERP-ACTION] 승인 대기 읽기 DB 오류")
        return _reply(500, None, _SAVE_FAILED)
    db.rollback()
    return _reply(200, data, None)


@erp_actions_api_bp.route("/proposals/<int:proposal_id>", methods=["GET"])
def erp_actions_detail(proposal_id: int) -> tuple[Any, int]:
    """제안 자세히(볼 수 없으면 없는 것과 같은 404)."""
    return _read(lambda db, user: detail(db, user, proposal_id, now_utc_naive()))


# ── 쓰기 ─────────────────────────────────────────────────────────────────
@erp_actions_api_bp.route("/proposals/<int:proposal_id>/approve", methods=["POST"])
def erp_actions_approve(proposal_id: int) -> tuple[Any, int]:
    """승인 → 실행(두 걸음). 본문 ``{"base_version", "edits"?, "reason_code"?, "reason_note"?, "view_ms"?}``."""
    body = _body()
    base = _int(body.get("base_version"))
    if base is None:
        user, denied = _viewer()
        return denied or _reply(400, {"code": "ACTION_SHAPE", "fields": ["base_version"]}, message("ACTION_SHAPE"))
    return _write(lambda db, user: approve(
        db, proposal_id, actor=user, runners=RUNNERS, base_version=base, edits=body.get("edits"),
        reason_code=body.get("reason_code"), reason_note=body.get("reason_note"), view_ms=body.get("view_ms"),
        now=now_utc_naive()))


@erp_actions_api_bp.route("/proposals/<int:proposal_id>/reject", methods=["POST"])
def erp_actions_reject(proposal_id: int) -> tuple[Any, int]:
    """거절 — 본문 ``{"code", "view_ms"?}``(까닭 다섯 가운데 하나)."""
    body = _body()

    def _run(db: Any, user: Any) -> dict[str, Any]:
        row = reject(db, proposal_id, actor=user, code=body.get("code"), view_ms=body.get("view_ms"),
                               now=now_utc_naive())
        return {"id": row.id, "status": row.status, "reject_code": row.reject_code}

    return _write(_run)


@erp_actions_api_bp.route("/proposals/<int:proposal_id>/snooze", methods=["POST"])
def erp_actions_snooze(proposal_id: int) -> tuple[Any, int]:
    """나중에 — 다음 날 06:00(한국 시간)까지 접는다."""
    def _run(db: Any, user: Any) -> dict[str, Any]:
        row = snooze(db, proposal_id, actor=user, now=now_utc_naive())
        return {"id": row.id, "status": row.status,
                "snoozed_until": format_datetime_kst(row.snoozed_until, "%Y-%m-%d %H:%M")}

    return _write(_run)
