"""생산 파트 표시 쓰기 API — 도면 카드의 작업 시작 · 같이 작업 · 기본 · 완료 · 되돌리기 · 시작 취소 · 담당 바꾸기
(설계서 §15.4 · 2026-11-23 §7 · 2026-11-25 multi-holder §7-1).

* ``POST /api/production/part-marks`` — 한 장. 몸 ``{order_id, drawing_key, part, action, seen[, seen_by][, seen_me]
  [, target_user_id]}``. ``action`` = take · basic · done · undo · release · takeover · join · remove · check.
  ``seen_by`` = 옛 화면이 본 담당 id(null = 담당 없음, 한 명일 때만 뜻) — 담당 바꾸기는 이것이나 ``target_user_id`` 를 꼭 보낸다.
  ``seen_me`` = 새 화면이 본 내 몫(none · held · done — 안 보내면 견주지 않음), ``target_user_id`` = 바꾸기 · 시작 취소 대상.
  ``check`` = PC [완료 처리](시작 + 완료를 한 요청 — 반장 · 관리자만, 판결 2).
* ``POST /api/production/part-marks/basic`` — 재단 [남은 N장 모두 기본]. 몸 ``{part:'cut', seen:'none', items:[{order_id,
  drawing_key}…]}``(최대 200). **화면이 보낸 목록만** 바꾼다(서버가 '남은 전부'를 고르지 않는다) · 일부 성공.

이 모듈은 로그인 · 파트 문(:mod:`foms.services.production.part_access`) · 몸 읽기 · tx 만 맡는다. 잠금 · 전이 표 · 막는 까닭 ·
쓰기 · 공정 칸 동기화 · 첫 카드 제작 시작 · 감사는 :mod:`foms.services.production.part_mark_write` 다. CSRF · 정책 가드는
다른 생산 API 와 같이 before_request(매니페스트 두 곳)가 건다. API 층은 웹 층을 부르지 않는다(레이어 래칫) — 로그인은
``g.current_user``.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from db import get_db
from foms.services.orders.revision import RevisionError
from foms.services.production.part_access import VIEW_ADMIN, VIEW_PART, VIEW_SUB, part_account_parts, part_view_mode
from foms.services.production.part_constants import BASIC_ALLOWED_PART, PRODUCTION_PART_KEYS
from foms.services.production.mark_crew import SHARE_VALUES
from foms.services.production.part_card_crew import attach_crew
from foms.services.production.part_mark_rules import (
    ACTION_BASIC,
    ACTION_CHECK,
    ACTION_TAKEOVER,
    MARK_ACTIONS,
    SEEN_BY_UNSET,
    SEEN_VALUES,
    STALE_MESSAGE,
)
from foms.services.production.part_mark_write import MarkRefusal, MarkRequest, bulk_basic, mark_one

production_part_marks_bp = Blueprint("production_part_marks", __name__, url_prefix="/api/production")

#: 일괄 기본 한 번의 장 수 상한(화면 한 장 카드 캡과 같다).
BULK_MAX_ITEMS = 200
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."
#: PC [완료 처리](``check``)는 감독 단추 — 반장 · 관리자만(판결 2, 지금 대신 처리 문과 같다).
CHECK_FORBIDDEN_MESSAGE = "[완료 처리]는 반장이나 관리자만 할 수 있어요."


def _ok(data: dict[str, Any]):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200


def _fail(refusal: MarkRefusal):
    data = {"code": refusal.code, **refusal.extra}
    attach_crew(data.get("mark"), getattr(g, "current_user", None))  # 진 경합 화면이 그 카드를 서버 모습으로(multi-holder M2)
    body = {"success": False, "data": data, "error": refusal.message}
    return jsonify(body), refusal.status


def _with_crew(data: dict[str, Any], user: Any) -> dict[str, Any]:
    """응답 표시마다 누른 사람 몫 칸(``crew`` — 이름 줄 · 내 몫, :func:`~part_card_crew.crew_view`)을 붙인다(쿼리 0)."""
    attach_crew(data.get("mark"), user)
    for item in data.get("applied") or []:
        attach_crew(item, user)
    for item in data.get("skipped") or []:
        attach_crew(item.get("mark"), user)
    return data


def _int_id(value: Any) -> int:
    """양의 정수 id(불린 · 글은 거절)."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MarkRefusal(400, "BAD_REQUEST", "주문 번호가 올바르지 않아요.")
    return value


def _drawing_key(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > 500:
        raise MarkRefusal(400, "BAD_REQUEST", "도면 장이 올바르지 않아요.")
    return text


def _choice(value: Any, allowed: tuple[str, ...], label: str) -> str:
    text = value.strip().lower() if isinstance(value, str) else ""
    if text not in allowed:
        raise MarkRefusal(400, "BAD_REQUEST", f"{label} 값이 올바르지 않아요.")
    return text


def _seen_by(body: dict[str, Any], action: str) -> Any:
    """``seen_by`` — 안 보냄(:data:`SEEN_BY_UNSET`) · null(담당 없음으로 봄) · 양의 정수. 담당 바꾸기는 이것이나 대상을 꼭 보낸다."""
    if "seen_by" not in body:
        if action == ACTION_TAKEOVER and body.get("target_user_id") is None:
            raise MarkRefusal(400, "BAD_REQUEST", "본 담당 값이 올바르지 않아요.")
        return SEEN_BY_UNSET
    value = body.get("seen_by")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MarkRefusal(400, "BAD_REQUEST", "본 담당 값이 올바르지 않아요.")
    return value


def _seen_me(body: dict[str, Any]) -> Any:
    """``seen_me`` — 안 보냄(None — 옛 화면, 견주지 않음) · none · held · done."""
    if body.get("seen_me") is None:
        return None
    return _choice(body.get("seen_me"), SHARE_VALUES, "본 내 몫")


def _target_uid(body: dict[str, Any]) -> Any:
    """``target_user_id`` — 안 보냄(None) · 양의 정수(바꾸기 · 시작 취소 대상)."""
    value = body.get("target_user_id")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MarkRefusal(400, "BAD_REQUEST", "고른 사람 값이 올바르지 않아요.")
    return value


def _actor() -> Any:
    """로그인한 사람(``_set_current_user`` 가 비활성 · 끊긴 세션은 이미 비웠다)."""
    user = getattr(g, "current_user", None)
    if user is None:
        raise MarkRefusal(401, "AUTH_REQUIRED", "로그인이 필요해요.")
    return user


def _gate_part(user: Any, part: str) -> bool:
    """파트 문(D53 · D55 · 2026-11-23 §4-12 · §5). 통과하면 남의 장을 대신 처리할 수 있는지(관리자 · 대신)를 돌려준다.

    관리자 · 대신(반장) = 네 파트 모두 + 덮어쓰기. 파트 계정 = 계정 파트들 중 하나만(여러 파트도 됨).

    Raises:
        MarkRefusal: 쓸 수 없는 계정 403 ``PART_REQUIRED`` · 내 파트 밖 403 ``PART_FORBIDDEN``.
    """
    mode = part_view_mode(user)
    if mode in (VIEW_ADMIN, VIEW_SUB):
        return True
    if mode != VIEW_PART:
        raise MarkRefusal(403, "PART_REQUIRED", "생산 파트가 정해진 계정만 작업할 수 있어요.")
    if part not in part_account_parts(user):
        raise MarkRefusal(403, "PART_FORBIDDEN", "자기 파트만 작업할 수 있어요.")
    return False


def _parse_one(body: dict[str, Any]) -> MarkRequest:
    """한 장 몸 → :class:`MarkRequest`(검사 순서: 주문 · 장 · 파트 · 누름 · 본 상태 · 본 담당 · 본 내 몫 · 대상)."""
    order_id, key = _int_id(body.get("order_id")), _drawing_key(body.get("drawing_key"))
    part = _choice(body.get("part"), PRODUCTION_PART_KEYS, "파트")
    action = _choice(body.get("action"), MARK_ACTIONS, "누름")
    seen = _choice(body.get("seen"), SEEN_VALUES, "본 상태")
    return MarkRequest(order_id=order_id, key=key, part=part, action=action, seen=seen, seen_by=_seen_by(body, action),
                       seen_me=_seen_me(body), target_uid=_target_uid(body))


def _run(handler: Any) -> Any:
    """핸들러 하나를 한 tx 로 돌리고 응답으로 바꾼다(거절 · 동시 첫 표시 · DB 오류는 되감고 해요체 한 문장)."""
    db = get_db()
    try:
        data = handler(db)
        db.commit()
    except MarkRefusal as refusal:
        db.rollback()
        return _fail(refusal)
    except RevisionError as exc:  # 공정 칸 동기화 · 제작 시작의 주문 쓰기 길 — 이미 잠근 주문이라 드물다
        db.rollback()
        return _fail(MarkRefusal(exc.status_code, exc.error_code or "SAVE_FAILED", _SAVE_FAILED))
    except IntegrityError:  # 같은 장 · 파트 첫 표시가 동시에 두 번(잠금 없는 레인) — 나중 것은 낡은 화면이다
        db.rollback()
        return _fail(MarkRefusal(409, "MARK_CONFLICT", STALE_MESSAGE))
    except SQLAlchemyError:
        db.rollback()
        return _fail(MarkRefusal(500, "SAVE_FAILED", _SAVE_FAILED))
    return _ok(data)


@production_part_marks_bp.route("/part-marks", methods=["POST"])
def api_part_mark():
    """도면 한 장 · 내 파트 표시 하나를 바꾼다(작업 시작 · 같이 작업 · 기본 · 완료 · 되돌리기 · 시작 취소 · 담당 바꾸기 ·
    PC [완료 처리]). 멱등 다시 보냄은 200."""

    def _handle(db: Any) -> dict[str, Any]:
        user = _actor()
        req = _parse_one(request.get_json(silent=True) or {})
        override = _gate_part(user, req.part)
        if req.action == ACTION_BASIC and req.part != BASIC_ALLOWED_PART:
            raise MarkRefusal(400, "BASIC_CUT_ONLY", "'기본'은 재단에만 있어요.")
        if req.action == ACTION_CHECK and not override:
            raise MarkRefusal(403, "PART_FORBIDDEN", CHECK_FORBIDDEN_MESSAGE)
        return _with_crew(mark_one(db, user, override, req), user)

    return _run(_handle)


def _parse_bulk(body: dict[str, Any]) -> tuple[str, list[tuple[int, str]]]:
    """일괄 몸 → (파트, 보낸 순서의 (주문, 장) 목록 · 겹침 제거)."""
    part = _choice(body.get("part"), PRODUCTION_PART_KEYS, "파트")
    if _choice(body.get("seen"), SEEN_VALUES, "본 상태") != "none":
        raise MarkRefusal(400, "BAD_REQUEST", "안 본 도면만 한 번에 기본으로 할 수 있어요.")
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise MarkRefusal(400, "BAD_REQUEST", "기본으로 할 도면을 골라 주세요.")
    if len(items) > BULK_MAX_ITEMS:
        raise MarkRefusal(400, "TOO_MANY", f"한 번에 {BULK_MAX_ITEMS}장까지만 할 수 있어요.")
    pairs: list[tuple[int, str]] = []
    for item in items:
        item = item if isinstance(item, dict) else {}
        pair = (_int_id(item.get("order_id")), _drawing_key(item.get("drawing_key")))
        if pair not in pairs:
            pairs.append(pair)
    return part, pairs


@production_part_marks_bp.route("/part-marks/basic", methods=["POST"])
def api_part_marks_basic():
    """재단 [남은 N장 모두 기본] — 화면이 보낸 목록만 기본으로. 맞는 장만 바꾸고 나머지는 ``skipped`` 로(전부 실패해도 200)."""

    def _handle(db: Any) -> dict[str, Any]:
        user = _actor()
        part, pairs = _parse_bulk(request.get_json(silent=True) or {})
        override = _gate_part(user, part)
        if part != BASIC_ALLOWED_PART:
            raise MarkRefusal(400, "BASIC_CUT_ONLY", "'기본'은 재단에만 있어요.")
        return _with_crew(bulk_basic(db, user, override, pairs), user)

    return _run(_handle)
