"""'회사 지식' 제안함 · 다시 확인 · 판 되돌리기 JSON API(설계서 7.5 화면 4 · 5 · 6 · 7.7 · D101 · D103 · D104 · ⑤-3).

**쓰기는 모두 이름 있는 액션**(:mod:`foms.services.brain.actions` 목록 — :func:`~foms.services.brain.action_runner.perform`
하나로 꼴 검사 → 서비스)이다. 경로마다 받는 액션은 액션 목록의 ``endpoint`` 가 정한다:

- ``POST /proposals`` ``{"action": "propose_edit" | "propose_retire" | "propose_delete" | "item_rollback", …}`` 사람 제안
  (그 항목을 볼 수 있는 사람 누구나).
- ``POST /proposals/<id>/apply`` 넣기(``apply``) · 고쳐 넣기(``edit_apply`` — 본문에 ``edits`` 가 있을 때) ·
  ``POST /proposals/<id>/reject`` 거절 · ``POST /proposals/bulk-apply`` 등급 A 모두 넣기.
- ``POST /recheck/confirm`` 아직 맞음 · ``POST /releases/<번호>/rollback`` 판 되돌리기(ADMIN 만).

읽기: ``GET /inbox`` 제안함 · ``GET /inbox/count`` 알림 수(폰 알림은 아직 없고 나중에 이 수를 쓴다) · ``GET /recheck`` 다시
확인 · ``GET /actions`` 액션 · 도구 · 속성 틀 표(⑤-5 가 같은 목록을 쓴다) · ``GET /metrics`` 결정 숫자(ADMIN 만).

여는 사람은 읽기 API 와 같다(ADMIN · 층 승인자 팀 MANAGER — 그 밖 404, 로그인 안 함 401). **결정한 사람은 로그인 사용자에서만**
받는다(본문의 사람 칸은 읽지 않는다 — R10-18). 결정할 수 없거나 볼 수 없는 제안 · 항목은 없는 것과 같은 404. 쓰기는 공용 CSRF ·
Origin 가드 뒤이고 정책 manifest 는 ``MANAGER_MUTATION``(판 되돌리기는 ``ADMIN_OPS``) — 실제 판정은 서비스 · 엔진이 다시 한다.
응답은 ``{"success", "data", "error"}``, 오류 글은 액션 목록이 정한 말만(문제 목록은 칸 이름 · 규칙 글뿐).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.brain import actions
from foms.services.brain.access import screen_viewer
from foms.services.brain.action_runner import perform
from foms.services.brain.errors import (
    BrainConfirmError, BrainConflictError, BrainDocSyncError, BrainError, BrainPermissionError, BrainRejectedError,
    BrainRollbackBlockedError, BrainShapeError,
)
from foms.services.brain.inbox import inbox, inbox_counts
from foms.services.brain.metrics import decision_metrics
from foms.services.brain.recheck import recheck_counts, recheck_list
from foms.services.brain.schemas import spec_table
from foms.services.brain.scope import Viewer
from foms.services.datetime_kst import get_today_kst, now_utc_naive

logger = logging.getLogger(__name__)

brain_review_api_bp = Blueprint("brain_review_api", __name__, url_prefix="/api/brain")

NOT_FOUND = actions.FAILURES["BRAIN_FORBIDDEN"]


def _reply(status: int, data: Any, error: Optional[str]) -> tuple[Any, int]:
    """응답 — 사람마다 보이는 것이 달라 캐시하지 않는다."""
    response = jsonify({"success": error is None, "data": data, "error": error})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _viewer() -> tuple[Optional[Viewer], Optional[tuple[Any, int]]]:
    """로그인 안 함 401 · 열 수 없는 사람 404 · 열 수 있으면 (Viewer, None)."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, _reply(401, None, "로그인이 필요합니다.")
    viewer = screen_viewer(user)
    if viewer is None:
        return None, _reply(404, None, NOT_FOUND)
    return viewer, None


def _body() -> dict[str, Any]:
    """JSON 본문(객체 아니면 빈 dict)."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _error_reply(exc: BrainError) -> tuple[Any, int]:
    """서비스 오류 → 액션 목록의 말 · 코드(볼 수 없음 · 권한 없음은 없는 것과 같은 404)."""
    if isinstance(exc, BrainPermissionError):
        return _reply(404, None, NOT_FOUND)
    data: dict[str, Any] = {"code": exc.code if exc.code in actions.FAILURES else "BRAIN_ERROR"}
    status = 409
    if isinstance(exc, BrainConflictError):
        data["current_version"] = exc.current_version
    elif isinstance(exc, BrainConfirmError):
        data["field"], status = exc.field, 400
    elif isinstance(exc, BrainRejectedError):
        data["reject_code"] = exc.reject_code
    elif isinstance(exc, BrainRollbackBlockedError):
        data["count"] = exc.count
    elif isinstance(exc, BrainDocSyncError):
        data["brand"], data["reason"] = exc.brand, exc.reason
    elif isinstance(exc, BrainShapeError):
        data["problems"], status = list(exc.problems), 400
    return _reply(status, data, actions.message(data["code"]))


def _act(choose: Callable[[], Any], body: Mapping[str, Any], allowed: tuple[str, ...]) -> tuple[Any, int]:
    """권한 확인 → 액션 하나(이 경로가 받는 액션만) → 커밋. 서비스 오류 · DB 오류면 되돌린다."""
    _seen, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    try:
        chosen = choose()
        if chosen not in allowed:
            raise BrainShapeError([f"action: {' / '.join(allowed)} 가운데 하나여야 한다"])
        _action, data = perform(db, chosen, actor=g.current_user, body=body)
        db.commit()
    except BrainError as exc:
        db.rollback()
        return _error_reply(exc)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[회사 지식 쓰기] DB 오류 endpoint=%s", request.endpoint)
        return _reply(500, None, "저장하지 못했어요. 잠시 뒤 다시 해 주세요.")
    return _reply(200, data, None)


def _read(build: Callable[[Any, Viewer], Any]) -> tuple[Any, int]:
    """권한 확인 → 읽기 → 읽기 트랜잭션 닫기."""
    viewer, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    try:
        data = build(db, viewer)
    finally:
        db.rollback()
    return _reply(200, data, None) if data is not None else _reply(404, None, NOT_FOUND)


def routed(endpoint: str) -> tuple[str, ...]:
    """그 경로가 받는 액션 이름(액션 목록의 ``endpoint`` 가 정본)."""
    return tuple(a.name for a in actions.ACTIONS.values() if a.endpoint == endpoint)


# ── 읽기 ─────────────────────────────────────────────────────────────────
@brain_review_api_bp.route("/inbox", methods=["GET"])
def brain_inbox() -> tuple[Any, int]:
    """제안함(화면 4)."""
    return _read(lambda db, viewer: inbox(db, viewer, now=now_utc_naive()))


@brain_review_api_bp.route("/inbox/count", methods=["GET"])
def brain_inbox_count() -> tuple[Any, int]:
    """알림 수 — 제안함 수 · 다시 확인 묶음 한 줄(폰 알림은 나중에 이 수를 쓴다)."""
    return _read(lambda db, viewer: {"inbox": inbox_counts(db, viewer, now_utc_naive()),
                                     "recheck": recheck_counts(db, viewer, today=get_today_kst())})


@brain_review_api_bp.route("/recheck", methods=["GET"])
def brain_recheck() -> tuple[Any, int]:
    """다시 확인 목록(화면 5)."""
    return _read(lambda db, viewer: recheck_list(db, viewer, today=get_today_kst()))


@brain_review_api_bp.route("/actions", methods=["GET"])
def brain_actions() -> tuple[Any, int]:
    """액션 · 도구 · 속성 틀 표(코드 상수 — DB 를 읽지 않는다). 사장님만 하는 액션은 ADMIN 에게만."""
    return _read(lambda _db, viewer: {"actions": [a for a in actions.specs(ui_only=False)
                                                  if viewer.is_admin or not a["admin_only"]],
                                      "tools": actions.tool_specs(), "schemas": spec_table()})


@brain_review_api_bp.route("/metrics", methods=["GET"])
def brain_metrics() -> tuple[Any, int]:
    """결정 숫자 — ADMIN 만(그 밖 404)."""
    days = request.args.get("days", type=int) or 30
    return _read(lambda db, viewer: decision_metrics(db, now=now_utc_naive(), days=days) if viewer.is_admin else None)


# ── 쓰기(이름 있는 액션) ─────────────────────────────────────────────────
@brain_review_api_bp.route("/proposals", methods=["POST"])
def brain_propose() -> tuple[Any, int]:
    """고칠 말 · 은퇴 · 지우기 · 항목 되돌리기 제안(사람 제안 — 제안함으로)."""
    body = _body()
    return _act(lambda: body.get("action"), body, routed("brain_review_api.brain_propose"))


@brain_review_api_bp.route("/proposals/<int:change_id>/apply", methods=["POST"])
def brain_apply(change_id: int) -> tuple[Any, int]:
    """넣기 · 고쳐 넣기(권한 · 보기 범위 · 기준 판 · 등급 B 확인 · 속성 틀을 다시 본다)."""
    body = {**_body(), "change_id": change_id}
    return _act(lambda: "edit_apply" if body.get("edits") else "apply", body, routed("brain_review_api.brain_apply"))


@brain_review_api_bp.route("/proposals/<int:change_id>/reject", methods=["POST"])
def brain_reject(change_id: int) -> tuple[Any, int]:
    """거절(까닭 칩)."""
    return _act(lambda: "reject", {**_body(), "change_id": change_id}, routed("brain_review_api.brain_reject"))


@brain_review_api_bp.route("/proposals/bulk-apply", methods=["POST"])
def brain_bulk_apply() -> tuple[Any, int]:
    """등급 A 만 한꺼번에 넣기."""
    return _act(lambda: "bulk_apply", _body(), routed("brain_review_api.brain_bulk_apply"))


@brain_review_api_bp.route("/recheck/confirm", methods=["POST"])
def brain_recheck_confirm() -> tuple[Any, int]:
    """'아직 맞음' 한 번 — 확인 날만 바꾸는 제안 → 반영 동작."""
    return _act(lambda: "recheck", _body(), routed("brain_review_api.brain_recheck_confirm"))


@brain_review_api_bp.route("/releases/<int:number>/rollback", methods=["POST"])
def brain_release_rollback(number: int) -> tuple[Any, int]:
    """판 · 층 되돌리기(ADMIN 만 — 같은 판 번호를 한 번 더 받아 확인)."""
    return _act(lambda: "release_rollback", {**_body(), "number": number},
                routed("brain_review_api.brain_release_rollback"))
