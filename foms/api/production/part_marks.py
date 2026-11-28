"""생산 파트 표시 쓰기 API — 도면 카드의 작업 시작 · 같이 작업 · 기본 · 완료 · 되돌리기 · 시작 취소 · 담당 바꾸기
(설계서 §15.4 · 2026-11-23 §7 · 2026-11-25 multi-holder §7-1).

* ``POST /api/production/part-marks`` — 한 장. 몸 ``{order_id, drawing_key, part, action, seen[, seen_by][, seen_me]
  [, target_user_id][, to_user_id]}``. ``action`` = take · basic · done · undo · release · takeover · join · remove · check.
  ``seen_by`` = 옛 화면이 본 담당 id(null = 담당 없음, 한 명일 때만 뜻) — 담당 바꾸기는 이것이나 ``target_user_id`` 를 꼭 보낸다.
  ``seen_me`` = 새 화면이 본 내 몫(none · held · done — 안 보내면 견주지 않음), ``target_user_id`` = 바꾸기 · 시작 취소 대상(자리를 내주는 사람).
  ``to_user_id``(담당 바꾸기만 · 2026-11-28 흐름 셋 §1-3) = 받는 사람 — 안 보내면 누른 사람(지금 동작). 남에게 주기는 반장 · 관리자만
  (403 ``GIVE_FORBIDDEN``). 담당이 바뀐 응답에는 ``gave``(누가 · 누구 자리를 · 누구에게 · ``self``), 바뀐 응답마다 ``holders_before``.
* ``GET /api/production/part-marks/receivers`` — 반장 · 관리자의 [담당 바꾸기 ›] 창 "누구에게 줄까요?"를 열 때 한 번. 질의 ``order_id`` ·
  ``drawing_key`` · ``part``[· ``target_user_id`` = 자리를 내줄 사람]. 답 ``{people: [{user_id, name, me, line}]}`` — 맨 앞 '나', 읽기 전용.
  ``check`` = PC [완료 처리](시작 + 완료를 한 요청 — 반장 · 관리자만, 판결 2).
  ``seen_cancel``(안 보내도 됨 · true/false) = 취소 창이 그 단추에 대해 보여 준 것 — "제작 시작도 같이 취소돼요" 줄이 보였으면 true.
  실은 누름만 견준다: 실제 되돌림 판정과 다르면 409 ``CANCEL_NOTICE_STALE``(아무것도 안 바뀜 — 사장님 2026-11-27 "창에 보인 대로만 된다").
* ``POST /api/production/part-marks/basic`` — 재단 [남은 N장 모두 기본]. 몸 ``{part:'cut', seen:'none', items:[{order_id,
  drawing_key}…]}``(최대 200). **화면이 보낸 목록만** 바꾼다(서버가 '남은 전부'를 고르지 않는다) · 일부 성공.
* ``GET /api/production/part-marks/cancel-preview`` — [<파트> 시작 취소] · [<파트> 완료 취소] · [기본 취소] 창을 열 때(사장님 2026-11-27
  "창에도 미리 알리기" · "여기도 미리 알리기"). 질의 = 한 장 쓰기 몸과 같은 칸(``action`` 은 release · remove · undo 만). 답
  ``{run_cancelled}`` = 지금 그 취소를 누르면 제작 시작도 같이 취소되는지. 읽기 전용이고, 문(로그인 · 파트 문)과 판정은 쓰기와 같은 함수다(``mark_one(dry=True)`` — 쓰기 직전까지 같은 길).

알람 거는 줄 둘(흐름 셋 §1-7 · 약속 3): 한 장 쓰기 결과를 받은 바로 뒤 ``floor_alarm.note_mark``(커밋 전 — 적기만), 공용 ``_run`` 의
커밋 바로 뒤 ``floor_alarm.flush``(되감은 길에는 닿지 않는다). 함수 몸은 :mod:`foms.services.production.floor_alarm` 것이다.

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
from foms.services.orders.drawing_factory import sheet_factory
from foms.services.orders.revision import RevisionError
from foms.services.production import floor_alarm
from foms.services.production.factory_scope import factory_gate
from foms.services.production.part_access import VIEW_ADMIN, VIEW_PART, VIEW_SUB, part_account_parts, part_view_mode
from foms.services.production.part_constants import BASIC_ALLOWED_PART, PRODUCTION_PART_KEYS
from foms.services.production.mark_crew import SHARE_VALUES
from foms.services.production.part_card_crew import attach_crew
from foms.services.production.part_mark_rules import (
    ACTION_BASIC,
    ACTION_CHECK,
    ACTION_RELEASE,
    ACTION_REMOVE,
    ACTION_TAKEOVER,
    ACTION_UNDO,
    GIVE_FORBIDDEN,
    GIVE_FORBIDDEN_MESSAGE,
    MARK_ACTIONS,
    SEEN_BY_UNSET,
    SEEN_VALUES,
    STALE_MESSAGE,
)
from foms.services.production.part_mark_bulk import bulk_basic
from foms.services.production.part_mark_write import MarkRefusal, MarkRequest, check_order, current_entry, mark_one
from foms.services.production.part_receivers import list_people, order_and_mark

production_part_marks_bp = Blueprint("production_part_marks", __name__, url_prefix="/api/production")

#: 일괄 기본 한 번의 장 수 상한(화면 한 장 카드 캡과 같다).
BULK_MAX_ITEMS = 200
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."
#: PC [완료 처리](``check``)는 감독 단추 — 반장 · 관리자만(판결 2, 지금 대신 처리 문과 같다).
CHECK_FORBIDDEN_MESSAGE = "[완료 처리]는 반장이나 관리자만 할 수 있어요."
#: 미리 보기가 받는 누름 — 표시 줄을 미정으로 돌릴 수 있는 취소 셋(내 시작 취소 · 반장이 남의 시작 취소 · 완료 취소/기본 취소).
PREVIEW_ACTIONS: tuple[str, ...] = (ACTION_RELEASE, ACTION_REMOVE, ACTION_UNDO)
_PREVIEW_TEXT_ARGS = ("drawing_key", "part", "action", "seen", "seen_me")
_PREVIEW_ID_ARGS = ("order_id", "seen_by", "target_user_id")
_READ_FAILED = "확인하지 못했어요. 잠시 뒤 다시 해 주세요."


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


def _to_uid(body: dict[str, Any]) -> Any:
    """``to_user_id`` — 안 보냄(None — 누른 사람이 받는다) · 양의 정수(담당 바꾸기에서 받는 사람)."""
    value = body.get("to_user_id")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MarkRefusal(400, "BAD_REQUEST", "받는 사람 값이 올바르지 않아요.")
    return value


def _seen_cancel(body: dict[str, Any]) -> Any:
    """``seen_cancel`` — 안 보냄(None — 옛 화면 · 다른 화면, 견주지 않음) · true(줄이 보였다) · false(안 보였다). 그 밖은 400."""
    value = body.get("seen_cancel")
    if value is not None and not isinstance(value, bool):
        raise MarkRefusal(400, "BAD_REQUEST", "본 취소 안내 값이 올바르지 않아요.")
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
    """한 장 몸 → :class:`MarkRequest`(검사 순서: 주문 · 장 · 파트 · 누름 · 본 상태 · 본 담당 · 본 내 몫 · 대상 · 받는 사람)."""
    order_id, key = _int_id(body.get("order_id")), _drawing_key(body.get("drawing_key"))
    part = _choice(body.get("part"), PRODUCTION_PART_KEYS, "파트")
    action = _choice(body.get("action"), MARK_ACTIONS, "누름")
    seen = _choice(body.get("seen"), SEEN_VALUES, "본 상태")
    return MarkRequest(order_id=order_id, key=key, part=part, action=action, seen=seen, seen_by=_seen_by(body, action),
                       seen_me=_seen_me(body), target_uid=_target_uid(body), to_uid=_to_uid(body))


def _run(handler: Any) -> Any:
    """핸들러 하나를 한 tx 로 돌리고 응답으로 바꾼다(거절 · 동시 첫 표시 · DB 오류는 되감고 해요체 한 문장). 커밋 바로 뒤에 적어 둔
    알람을 보낸다(``floor_alarm.flush`` — 되감은 길은 그 앞에서 돌아가 닿지 않는다)."""
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
    floor_alarm.flush(db)
    return _ok(data)


@production_part_marks_bp.route("/part-marks", methods=["POST"])
def api_part_mark():
    """도면 한 장 · 내 파트 표시 하나를 바꾼다(작업 시작 · 같이 작업 · 기본 · 완료 · 되돌리기 · 시작 취소 · 담당 바꾸기 ·
    PC [완료 처리]). 멱등 다시 보냄은 200."""

    def _handle(db: Any) -> dict[str, Any]:
        user = _actor()
        body = request.get_json(silent=True) or {}
        req, shown = _parse_one(body), _seen_cancel(body)  # 몸 검사(400)는 지금처럼 파트 문(403)보다 먼저
        override = _gate_part(user, req.part)
        if req.action == ACTION_BASIC and req.part != BASIC_ALLOWED_PART:
            raise MarkRefusal(400, "BASIC_CUT_ONLY", "'기본'은 재단에만 있어요.")
        if req.action == ACTION_CHECK and not override:
            raise MarkRefusal(403, "PART_FORBIDDEN", CHECK_FORBIDDEN_MESSAGE)
        if req.action == ACTION_TAKEOVER and req.to_uid not in (None, user.id) and not override:
            raise MarkRefusal(403, GIVE_FORBIDDEN, GIVE_FORBIDDEN_MESSAGE)  # 남에게 주기는 반장 · 관리자만(사장님 2026-11-28)
        data = mark_one(db, user, override, req, seen_cancel=shown)
        floor_alarm.note_mark(db, user, req, data)  # 커밋 전 — 세션 주머니에 적기만(약속 3)
        return _with_crew(data, user)

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


def _preview_body(args: Any) -> dict[str, Any]:
    """미리 보기 질의 → 한 장 쓰기 몸과 같은 꼴(같은 :func:`_parse_one` 이 검사한다). 번호 칸은 정수로, 빈 ``seen_by`` 는 null(담당 없음으로 봄)."""
    body: dict[str, Any] = {key: args.get(key) for key in _PREVIEW_TEXT_ARGS if key in args}
    for key in _PREVIEW_ID_ARGS:
        if key not in args:
            continue
        text = (args.get(key) or "").strip()
        if text.isascii() and text.isdigit():
            body[key] = int(text)
        else:
            body[key] = None if key == "seen_by" and not text else text  # 숫자가 아닌 글은 _parse_one 이 400 으로 거절
    return body


@production_part_marks_bp.route("/part-marks/cancel-preview", methods=["GET"])
def api_part_mark_cancel_preview():
    """[<파트> 시작 취소] · [<파트> 완료 취소] · [기본 취소]를 누르기 전 — 지금 그 취소를 누르면 제작 시작도 같이 취소되는지(``run_cancelled``). 읽기 전용.

    문 · 검사 · 판정은 한 장 쓰기와 같다(같은 ``_parse_one`` · ``_gate_part`` · ``mark_one`` — ``dry`` 라 잠금 · 쓰기만 없다). 누르면 거절될
    누름(409 — 낡은 화면 · 막힌 주문)은 같이 취소될 것도 없으니 ``False``, 그 밖 거절(400 · 401 · 403 · 404)은 쓰기와 같은 답이다.
    """
    db = get_db()
    try:
        user = _actor()
        req = _parse_one(_preview_body(request.args))
        override = _gate_part(user, req.part)
        if req.action not in PREVIEW_ACTIONS:
            raise MarkRefusal(400, "BAD_REQUEST", "누름 값이 올바르지 않아요.")
        cancelled = bool(mark_one(db, user, override, req, dry=True)["run_cancelled"])
    except MarkRefusal as refusal:
        db.rollback()
        if refusal.status == 409:
            return _ok({"run_cancelled": False})
        return _fail(MarkRefusal(refusal.status, refusal.code, refusal.message))
    except SQLAlchemyError:
        db.rollback()
        return _fail(MarkRefusal(500, "READ_FAILED", _READ_FAILED))
    db.rollback()  # 읽기만 했다 — 세션에 남은 것이 있어도 버린다
    return _ok({"run_cancelled": cancelled})


@production_part_marks_bp.route("/part-marks/receivers", methods=["GET"])
def api_part_mark_receivers():
    """반장 · 관리자의 [담당 바꾸기 ›] 창 "누구에게 줄까요?" — 그 도면을 넘겨받을 수 있는 사람들(맨 앞 '나'). 읽기 전용 · 쿼리 2.

    문은 쓰기와 같다(로그인 · 파트 문 · 반장/관리자 — 파트 계정 403 ``GIVE_FORBIDDEN`` · 남의 공장 도면 403 ``OTHER_FACTORY``). 판정은
    쓰기와 같은 함수(:func:`~foms.services.production.part_receivers.can_receive`)라 목록에 있는 사람은 쓰기도 받는다(그사이 바뀌면 쓰기가 409).
    """
    db = get_db()
    try:
        user = _actor()
        body = _preview_body(request.args)
        order_id, key = _int_id(body.get("order_id")), _drawing_key(body.get("drawing_key"))
        part, seat = _choice(body.get("part"), PRODUCTION_PART_KEYS, "파트"), _target_uid(body)
        if not _gate_part(user, part):
            raise MarkRefusal(403, GIVE_FORBIDDEN, GIVE_FORBIDDEN_MESSAGE)
        order, row = order_and_mark(db, order_id, key, part)
        entry = current_entry(check_order(order), key)
        gate = factory_gate(user, order.structured_data, entry, action=ACTION_TAKEOVER, row=row)
        if gate is not None:
            raise MarkRefusal.from_gate(gate)
        people = list_people(db, user, part, sheet_factory(order.structured_data, entry), row, seat)
    except MarkRefusal as refusal:
        db.rollback()
        return _fail(MarkRefusal(refusal.status, refusal.code, refusal.message))
    except SQLAlchemyError:
        db.rollback()
        return _fail(MarkRefusal(500, "READ_FAILED", _READ_FAILED))
    db.rollback()  # 읽기만 했다
    return _ok({"people": people})
