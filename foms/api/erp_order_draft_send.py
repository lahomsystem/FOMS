"""마법사 초안(등록 전) 발송 API — 알림톡 예약안내 · 실측방 채널톡 PUSH (WIZ-SEND-01 T3).

주문 등록 **전** 단계에서 고객·실측방으로 안내를 보내는 4개 라우트다. 대상은 ``Order`` 가
아니라 ``OrderDraft(draft_key)`` 이고(설계 D1 — 버튼이 몰래 주문을 만들지 않는다), 본문은
언제나 **서버가 저장된 최신 초안 payload 로 재조립**한다(설계 D2, 알림톡 스펙 §6.4 F2
"클라 텍스트 불신"). 클라이언트가 본문 텍스트를 보내는 자리는 이 모듈에 없다.

발송 이력은 ``OrderDraft.send_history`` 에 굳히고(설계 D3 — payload 는 autosave 가 통째로
덮는다), 등록 시 새 주문 ``structured_data`` 의 정본 키로 승계된다(T5).

게이트는 ``foms/api/erp_order_draft.py`` 와 같다: 로그인 + ADMIN/MANAGER/STAFF + 마법사
플래그. CSRF/Origin 은 공용 write guard before_request 가 담당하므로 라우트에 별도
데코레이터를 두지 않는다(manifest 등재가 그 계약).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from flask import Blueprint, jsonify, request, session

from db import get_db
from models import OrderDraft, User

from foms.api.erp_order_draft import _draft_payload_to_structured
from foms.services.audit_message_display import describe_action
from foms.services.channel_client import is_configured as channel_is_configured
from foms.services.channel_draft_push import (
    collect_draft_measure_files,
    push_measure_room_for_draft,
)
from foms.services.channel_measure_message import build_measure_push_text
from foms.services.datetime_kst import now_utc_naive
from foms.services.feature_flags import wizard_new_order_enabled
from foms.services.kakao_alimtalk import (
    build_draft_dedupe_key,
    build_draft_history_entry,
    build_draft_schedule_signature,
    draft_ineligible_reason,
    is_configured as alimtalk_is_configured,
    render_preview,
    send_alimtalk_for_sd,
)
from foms.services.order_draft_service import (
    SEND_KIND_ALIMTALK,
    SEND_KIND_CHANNEL_MEASURE,
    OrderDraftNotFoundError,
    record_draft_send,
)
from foms.web.auth import log_access, login_required, role_required

logger = logging.getLogger(__name__)

erp_order_draft_send_bp = Blueprint(
    "erp_order_draft_send", __name__, url_prefix="/api/erp/order-draft"
)

#: 초안 발송 권한. ``erp_order_draft`` · PC 수동 발송과 같은 집합(VIEWER 제외).
_SEND_ROLES = ["ADMIN", "MANAGER", "STAFF"]

#: 재전송 변경 메모 길이 규칙 — PC 채널톡 수동 푸쉬와 같은 값
#: (``channel_integration._MIN_CHANGE_NOTE_LEN`` / ``_MAX_CHANGE_NOTE_LEN``).
_MIN_CHANGE_NOTE_LEN = 1
_MAX_CHANGE_NOTE_LEN = 500

#: 재전송 변경 이력 보존 개수 — PC ``_PUSH_CHANGE_LOG_CAP`` 과 같은 값.
_PUSH_CHANGE_LOG_CAP = 20

#: 같은 초안·같은 종류의 발송이 이 시간(초) 안에 또 들어오면 중복 요청으로 본다.
#: 전송 자체는 행 잠금으로 직렬화되지만, 직렬화만으로는 두 번 나가는 것을 못 막는다
#: (뒤 요청이 앞 요청을 기다렸다가 그대로 또 보낸다). 사람의 의도적 재발송은 이력을
#: 확인하고 누르므로 이 창을 넘고, 더블클릭·재시도 폭주는 이 안에서 걸린다.
_DUPLICATE_SEND_WINDOW_SECONDS = 10

__all__ = ["erp_order_draft_send_bp"]


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _user_id() -> int | None:
    """세션의 로그인 사용자 id(없으면 ``None``)."""
    raw = session.get("user_id")
    return int(raw) if raw is not None else None


def _require_wizard() -> tuple[Any, int] | None:
    """마법사 게이트(``erp_order_draft._require_wizard`` 와 동일 기준)."""
    if not wizard_new_order_enabled(_user_id()):
        return jsonify({"success": False, "data": None, "error": "WIZARD_DISABLED"}), 403
    return None


def _envelope(data: Any, error: str | None, status: int = 200) -> tuple[Any, int]:
    """프로젝트 표준 응답 ``{success, data, error}``."""
    return jsonify({"success": error is None, "data": data, "error": error}), status


def _load_draft(draft_key: str, uid: int, *, for_update: bool = False) -> OrderDraft | None:
    """**소유자 본인의** 초안 1건을 읽는다(남의 draft_key 로는 절대 발송되지 않는다).

    Args:
        draft_key: 초안 키.
        uid: 로그인 사용자 id.
        for_update: 참이면 행 잠금(``FOR UPDATE``)까지 잡는다 — 발송 경로에서 읽기·전송·
            이력 기록이 다른 요청과 섞이지 않게 한다(SQLite 는 이 절을 무시한다).

    Returns:
        초안 행. 없거나 남의 것이면 ``None``.
    """
    key = (draft_key or "").strip()
    if not key:
        return None
    query = get_db().query(OrderDraft).filter(
        OrderDraft.user_id == uid,
        OrderDraft.draft_key == key,
    )
    if for_update:
        query = query.with_for_update()
    return query.one_or_none()


def _draft_structured(row: OrderDraft) -> dict[str, Any]:
    """초안 payload 를 정식 structured_data 로 변환한다(제출 경로와 같은 변환기)."""
    payload = row.payload if isinstance(row.payload, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return _draft_payload_to_structured(data)


def _send_history(row: OrderDraft) -> dict[str, Any]:
    """행의 발송 이력 dict(없으면 빈 dict)."""
    return row.send_history if isinstance(row.send_history, dict) else {}


def _last_entry(row: OrderDraft, kind: str) -> dict[str, Any] | None:
    """종류별 마지막 발송 이력 1건(없으면 ``None``)."""
    entry = _send_history(row).get(kind)
    return entry if isinstance(entry, dict) else None


def _actor_name(uid: int | None) -> str | None:
    """발송 시점의 사용자 표시명(이력·채널톡 botName 용)."""
    if uid is None:
        return None
    user = get_db().get(User, uid)
    name = getattr(user, "name", None) if user is not None else None
    return str(name) if name else None


def _parse_sent_at(raw: Any) -> datetime.datetime | None:
    """이력의 ``sent_at`` 문자열을 naive UTC datetime 으로 읽는다(못 읽으면 ``None``)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw.strip())
    except ValueError:
        logger.warning("초안 발송 이력의 sent_at 을 읽지 못했다: %r", raw)
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def _is_duplicate_send(entry: dict[str, Any] | None) -> bool:
    """직전 성공 발송이 :data:`_DUPLICATE_SEND_WINDOW_SECONDS` 안이면 중복으로 본다."""
    if not entry or entry.get("error"):
        return False
    sent_at = _parse_sent_at(entry.get("sent_at"))
    if sent_at is None:
        return False
    return (now_utc_naive() - sent_at).total_seconds() < _DUPLICATE_SEND_WINDOW_SECONDS


def _audit_draft_send(
    *,
    action: str,
    row: OrderDraft,
    uid: int | None,
    sent: bool,
    error: str | None,
    detail: dict[str, Any] | None = None,
) -> None:
    """초안 발송 1건을 구조화 감사로 남긴다(고객에게 나간 것은 추적 가능해야 한다).

    본문은 남기지 않는다 — 치환 텍스트·변환 텍스트에는 고객 정보가 섞인다(원장 PII 최소화).
    대상은 주문이 아니므로 ``target_type='order_draft'`` + ``OrderDraft.id`` 다.

    Args:
        action: ``ALIMTALK_DRAFT_SENT`` 또는 ``CHANNEL_PUSH_DRAFT_SENT``.
        row: 대상 초안 행.
        uid: 행위자 user id.
        sent: 실제 전송 성공 여부.
        error: 실패 사유 코드(성공이면 ``None``).
        detail: 추가 구조화 정보(첨부 수·재전송 여부 등).
    """
    log_access(
        describe_action(
            action,
            target_label=f"주문 초안 #{row.id}",
            note=None if sent else f"실패: {error}",
        ),
        uid,
        auto_commit=False,
        action=action,
        target_type="order_draft",
        target_id=int(row.id),
        detail={"draft_key": row.draft_key, "sent": bool(sent), "error": error,
                **(detail or {})},
    )


# ---------------------------------------------------------------------------
# 알림톡(실측 예약 안내)
# ---------------------------------------------------------------------------
@erp_order_draft_send_bp.route("/alimtalk/preview", methods=["GET"])
@login_required
@role_required(_SEND_ROLES)
def api_draft_alimtalk_preview() -> tuple[Any, int]:
    """초안 알림톡 미리보기(서버 렌더 + 자격 판정 + 마지막 이력).

    Returns:
        ``data = {'text', 'eligible', 'ineligible_reason', 'last', 'configured'}``.
        미자격이어도 사유 확인용으로 ``text`` 를 함께 준다(주문 경로와 같은 계약).
    """
    blocked = _require_wizard()
    if blocked is not None:
        return blocked
    uid = _user_id()
    if uid is None:
        return _envelope(None, "unauthorized", 401)

    row = _load_draft(request.args.get("draft_key") or "", uid)
    if row is None:
        return _envelope(None, "draft_not_found", 404)

    sd = _draft_structured(row)
    reason = draft_ineligible_reason(sd)
    return _envelope({
        "text": render_preview(sd),
        "eligible": reason is None,
        "ineligible_reason": reason,
        "last": _last_entry(row, SEND_KIND_ALIMTALK),
        "configured": alimtalk_is_configured(),
    }, None)


@erp_order_draft_send_bp.route("/alimtalk/send", methods=["POST"])
@login_required
@role_required(_SEND_ROLES)
def api_draft_alimtalk_send() -> tuple[Any, int]:
    """초안 알림톡 발송(요청 body 는 ``draft_key`` 만 읽는다).

    Returns:
        ``data = {'sent', 'error', 'message_id', 'last'}``. 전송 실패(벤더 오류·미자격)는
        200 + ``error`` 코드다. 서버 미설정 503, 초안 없음 404, 중복 요청 409.
    """
    blocked = _require_wizard()
    if blocked is not None:
        return blocked
    uid = _user_id()
    if uid is None:
        return _envelope(None, "unauthorized", 401)

    body = request.get_json(silent=True) or {}
    if not alimtalk_is_configured():
        return _envelope(None, "not_configured", 503)

    db = get_db()
    row = _load_draft(body.get("draft_key") or "", uid, for_update=True)
    if row is None:
        return _envelope(None, "draft_not_found", 404)
    if _is_duplicate_send(_last_entry(row, SEND_KIND_ALIMTALK)):
        return _envelope(None, "duplicate_request", 409)

    sd = _draft_structured(row)
    reason = draft_ineligible_reason(sd)
    if reason is not None:
        # 발송 시도가 없었으므로 이력에는 남기지 않는다(승계 시 가짜 실패 이력이 된다).
        _audit_draft_send(action="ALIMTALK_DRAFT_SENT", row=row, uid=uid,
                          sent=False, error=reason, detail={"template": "measure"})
        db.commit()
        return _envelope({"sent": False, "error": reason, "message_id": None,
                          "last": _last_entry(row, SEND_KIND_ALIMTALK)}, reason)

    dedupe_key = build_draft_dedupe_key(row.draft_key)
    result = send_alimtalk_for_sd(sd, sent_by=uid, dedupe_key=dedupe_key)
    entry = build_draft_history_entry(
        dedupe_key=dedupe_key,
        message_id=result.get("message_id"),
        error=result.get("error"),
        sent_by=uid,
        sent_by_name=_actor_name(uid),
        draft_schedule=build_draft_schedule_signature(sd),
    )
    return _finish_send(
        db, row=row, uid=uid, kind=SEND_KIND_ALIMTALK, entry=entry,
        action="ALIMTALK_DRAFT_SENT",
        sent=bool(result.get("sent")), error=result.get("error"),
        audit_detail={"template": "measure"},
        data={"sent": bool(result.get("sent")), "error": result.get("error"),
              "message_id": result.get("message_id"), "last": entry},
    )


# ---------------------------------------------------------------------------
# 실측방 채널톡 PUSH
# ---------------------------------------------------------------------------
@erp_order_draft_send_bp.route("/channel-push/preview", methods=["GET"])
@login_required
@role_required(_SEND_ROLES)
def api_draft_channel_push_preview() -> tuple[Any, int]:
    """초안 실측 PUSH 미리보기(서버 조립 본문 + 첨부 수 + 마지막 이력).

    Returns:
        ``data = {'text', 'files_count', 'last', 'configured'}``.
    """
    blocked = _require_wizard()
    if blocked is not None:
        return blocked
    uid = _user_id()
    if uid is None:
        return _envelope(None, "unauthorized", 401)

    row = _load_draft(request.args.get("draft_key") or "", uid)
    if row is None:
        return _envelope(None, "draft_not_found", 404)

    return _envelope({
        "text": build_measure_push_text(_draft_structured(row), draft_notice=True),
        "files_count": len(collect_draft_measure_files(row.payload)),
        "last": _last_entry(row, SEND_KIND_CHANNEL_MEASURE),
        "configured": channel_is_configured(),
    }, None)


def _validate_change_note(raw: Any, *, is_resend: bool) -> tuple[str, str | None]:
    """재전송 변경 메모를 PC 채널톡 경로와 같은 규칙(1~500자)으로 검증한다.

    Args:
        raw: 요청 body 의 ``change_note`` 원값.
        is_resend: 이미 발송 이력이 있는지.

    Returns:
        ``(정규화된 메모, 오류코드 | None)`` — 최초 발송이면 메모는 항상 빈 문자열이다.
    """
    note = str(raw or "").strip()
    if not is_resend:
        return "", None
    if len(note) < _MIN_CHANGE_NOTE_LEN:
        return "", "change_note_required"
    if len(note) > _MAX_CHANGE_NOTE_LEN:
        return "", "change_note_too_long"
    return note, None


def _build_push_entry(
    prev: dict[str, Any] | None,
    *,
    result: dict[str, Any],
    is_resend: bool,
    change_note: str,
    sent_by_name: str | None,
    sent_at: str,
) -> dict[str, Any]:
    """실측방 PUSH 이력 entry 를 **주문 정본과 같은 키**로 조립한다.

    키 집합은 ``channel_integration._record_push_metadata`` 가 쓰는 것과 같다 — 승계가
    무변환 복사이므로 여기서 이름이 갈리면 등록 후 화면이 이력을 못 읽는다. 첨부 id 축
    (``attachment_ids``·``max_attachment_id``)은 초안에 ``OrderAttachment`` 행이 아직
    없으므로 넣지 않는다(등록 시 새 id 로 처음 계산되는 것이 옳다).

    Args:
        prev: 직전 이력(재전송 change_log 누적용).
        result: :func:`push_measure_room_for_draft` 결과.
        is_resend: 재전송 여부.
        change_note: 재전송 변경 메모.
        sent_by_name: 발송자 표시명.
        sent_at: 발송 시각 ISO 문자열.

    Returns:
        ``OrderDraft.send_history[channeltalk_push_measure_room]`` 에 굳힐 dict.
    """
    entry: dict[str, Any] = {
        "pushed": True,
        "message_id": result.get("message_id"),
        "group_id": result.get("group_id"),
        "sent_at": sent_at,
        "is_modified": is_resend,
    }
    if is_resend:
        change_log = list((prev or {}).get("change_log") or [])
        change_log.append({
            "at": sent_at,
            "by": sent_by_name,
            "note": change_note,
            "message_id": result.get("message_id"),
        })
        entry["change_log"] = change_log[-_PUSH_CHANGE_LOG_CAP:]
    return entry


#: 실측 PUSH 실패 코드 → HTTP 상태(PC 수동 푸쉬 응답 규약과 같은 뜻).
_PUSH_ERROR_STATUS = {
    "not_configured": 503,
    "group_missing": 503,
    "group_retired": 410,
    "send_failed": 502,
    "not_sent": 502,
}


@erp_order_draft_send_bp.route("/channel-push/send", methods=["POST"])
@login_required
@role_required(_SEND_ROLES)
def api_draft_channel_push_send() -> tuple[Any, int]:
    """초안 실측 PUSH 발송(본문·첨부 모두 서버가 저장된 초안으로 재조립).

    Returns:
        성공 시 ``data = {'sent', 'files_count', 'last'}``. 실패는
        :data:`_PUSH_ERROR_STATUS` 의 상태 코드 + ``error``. 초안 없음 404,
        재전송 메모 누락 400, 중복 요청 409.
    """
    blocked = _require_wizard()
    if blocked is not None:
        return blocked
    uid = _user_id()
    if uid is None:
        return _envelope(None, "unauthorized", 401)

    body = request.get_json(silent=True) or {}
    if not channel_is_configured():
        return _envelope(None, "not_configured", 503)

    db = get_db()
    row = _load_draft(body.get("draft_key") or "", uid, for_update=True)
    if row is None:
        return _envelope(None, "draft_not_found", 404)

    prev = _last_entry(row, SEND_KIND_CHANNEL_MEASURE)
    is_resend = bool(prev and prev.get("pushed"))
    change_note, note_error = _validate_change_note(body.get("change_note"), is_resend=is_resend)
    if note_error is not None:
        return _envelope(None, note_error, 400)
    if _is_duplicate_send(prev):
        return _envelope(None, "duplicate_request", 409)

    sent_by_name = _actor_name(uid)
    result = push_measure_room_for_draft(
        sd=_draft_structured(row),
        files=collect_draft_measure_files(row.payload),
        user_id=uid,
        user_name=sent_by_name,
        change_note=change_note,
    )
    if not result.get("sent"):
        error = str(result.get("error") or "send_failed")
        # 전송이 안 됐으므로 이력은 남기지 않는다(PC 경로와 같다 — 이력은 전송 성공의 기록).
        _audit_draft_send(action="CHANNEL_PUSH_DRAFT_SENT", row=row, uid=uid,
                          sent=False, error=error,
                          detail={"push_kind": "measure_room", "is_resend": is_resend})
        db.commit()
        return _envelope({"sent": False, "error": error, "files_count": 0},
                         error, _PUSH_ERROR_STATUS.get(error, 502))

    entry = _build_push_entry(
        prev, result=result, is_resend=is_resend, change_note=change_note,
        sent_by_name=sent_by_name, sent_at=now_utc_naive().isoformat(),
    )
    return _finish_send(
        db, row=row, uid=uid, kind=SEND_KIND_CHANNEL_MEASURE, entry=entry,
        action="CHANNEL_PUSH_DRAFT_SENT", sent=True, error=None,
        audit_detail={"push_kind": "measure_room", "is_resend": is_resend,
                      "files_count": result.get("files_count")},
        data={"sent": True, "error": None, "files_count": result.get("files_count"),
              "last": entry},
    )


# ---------------------------------------------------------------------------
# 이력 기록 + 감사 + 커밋 (두 발송 경로 공통 꼬리)
# ---------------------------------------------------------------------------
def _finish_send(
    db: Any,
    *,
    row: OrderDraft,
    uid: int | None,
    kind: str,
    entry: dict[str, Any],
    action: str,
    sent: bool,
    error: str | None,
    audit_detail: dict[str, Any],
    data: dict[str, Any],
) -> tuple[Any, int]:
    """발송 이력을 굳히고 감사를 남긴 뒤 한 트랜잭션으로 커밋한다.

    메시지는 이미 고객에게 나갔으므로 **이력 기록 실패를 삼키지 않는다** — 조용히 넘기면
    "보냈는데 기록이 없는" 초안이 되고, 등록 시 승계할 것도 사라진다.

    Args:
        db: 요청 세션.
        row: 대상 초안 행.
        uid: 행위자 user id.
        kind: 이력 종류 상수.
        entry: 굳힐 이력 dict.
        action: 감사 action 코드.
        sent: 전송 성공 여부(감사 표기용).
        error: 전송 실패 코드(성공이면 None).
        audit_detail: 감사 detail 추가 항목.
        data: 성공 응답의 ``data``.

    Returns:
        표준 envelope 응답.
    """
    try:
        record_draft_send(db, draft_key=row.draft_key, user_id=int(uid), kind=kind, entry=entry)
    except (OrderDraftNotFoundError, ValueError):
        db.rollback()
        logger.exception(
            "초안 발송 이력 기록 실패 — 메시지는 이미 나갔다 (draft_key=%s, kind=%s)",
            row.draft_key, kind,
        )
        return _envelope({**data, "history_recorded": False}, "history_not_recorded", 500)

    _audit_draft_send(action=action, row=row, uid=uid, sent=sent, error=error,
                      detail=audit_detail)
    db.commit()
    return _envelope(data, error)
