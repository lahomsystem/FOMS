"""도면 탭 영업 → 고객 상태 읽기 모델 ``customer_send``(설계서 2026-09-29 §4.4 · §4.5 · Q1 · Q5).

도면 작업실 상세 라우트가 한 번 부른다. 조회는 두 번(발송 이벤트 최신 30건 · 도면 공유 링크
최신 50건, 둘 다 ``order_id`` 인덱스), 반복문 안 조회는 없다.

판정 규칙
* **이번 회차 발송** = 발송 이벤트 payload 의 ``round_at`` 이 지금 회차(``drawing_round_info``)의
  ``round_at`` 과 같음. 표지 없는 옛 이벤트만 ``created_at ≥ round_at`` 시각 비교로 대신한다.
* **같은 회차 앞 발송**(추가 전달 뒤) = 표지 ``round_at`` 이 지금 회차의 앞 전달 시각 중 하나, 또는
  표지 없이 지금 회차 첫 전달 ~ ``round_at`` 사이. '보냄'으로 치지 않고(추가분은 안 보냈다) 따로 보인다.
* **앞 회차 요약** = 표지 ``round`` 가 앞 회차, 또는 표지 없이 앞 회차 첫 전달 ~ 지금 회차 첫 전달 사이.
* **보냄** = ``status == 'sent'``(벤더 접수 — 고객 폰 도착이 아니다). 내 폰 문자·링크 복사·카카오
  공유는 보냄이 아니다(Q1) — **링크만 만듦**: 이번 회차 도착 뒤 직원이 발급했고(``created_by`` 있음)
  회수되지 않았으며 어떤 발송 이벤트와도 짝이 아닌 링크.
* 짝 링크 = 이벤트의 ``share_id`` 와 ``drawing_share_id``(통합 템플릿이 그 자리에서 발급한 도면
  링크). 표지 없는 옛 묶음 알림톡은 ±10초 안에 생긴 ``created_by`` 없는 도면 링크를 짝으로 본다.
* 열림 수 = 이번 회차에 보낸·만든 링크들의 열람 합. 마지막 열림 = 도면이 보이는 모든 링크 중
  가장 늦은 열람(이번 회차 도착 뒤일 때만). 누가 열었는지는 구분되지 않는다(직원 열람 포함).
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, NamedTuple

from foms.services import kakao_alimtalk as ka
from foms.services.datetime_kst import format_datetime_kst, get_today_kst, parse_datetime_utc
from foms.services.erp_policy import STAGE_NAME_TO_CODE
from foms.services.feature_flags import env_bool
from foms.services.orders.confirm_drawing_gate import normalize_stage_code
from foms.services.orders.drawing_customer_send import (
    RoundInfo,
    drawing_round_info,
    empty_customer_send_view,
    round_text,
    share_doc_label,
)
from foms.services.orders.drawing_customer_send_bar import build_customer_send_bar
from foms.services.orders.drawing_revision_edit import (
    can_edit_revision_request,
    edit_revision_prefill,
    editable_revision_request,
)
from foms.services.orders.drawing_revision_source import request_rounds
from foms.services.orders.quest_approve_authz import quest_approve_allowed
from foms.services.orders.quest_transition_service import find_stage_quest_for_approve
from models import OrderEvent, OrderShareToken

#: ``foms/api/share.py`` ``_BOTH_TEMPLATE_ENV_PREFIX`` 와 같아야 한다(테스트가 단언). 서비스가 api 를
#: import 하지 않게 값을 옮기지 않고 복제한다.
BOTH_TEMPLATE_ENV_PREFIX = "SOLAPI_TEMPLATE_SHARE_BOTH_ID_"

_SEND_EVENT_TYPES = ("SHARE_ALIMTALK", "SHARE_SMS")
_DRAWING_KINDS = ("drawing", "bundle")
_EVENT_LIMIT = 30
_TOKEN_LIMIT = 50
_LEGACY_PAIR_WINDOW = datetime.timedelta(seconds=10)
_CHANNEL_LABELS = {"SHARE_ALIMTALK": "알림톡", "SHARE_SMS": "회사 문자"}
#: "알림톡으로" · "회사 문자로"(받침 있는 말 뒤에는 '으로').
_CHANNEL_WITH = {"알림톡": "알림톡으로", "회사 문자": "회사 문자로"}
_ERROR_LABELS = {
    "invalid_phone": "번호 오류", "auth": "인증 오류", "balance": "잔액 부족",
    "template_mismatch": "템플릿 오류", "length_exceeded": "길이 초과", "unknown": "알 수 없는 오류",
}
LINK_ONLY_NOTE = "링크를 만들었어요(직접 보낸 경우 보냈는지는 기록되지 않아요)"
_SALES_ROLES = ("ADMIN", "MANAGER", "STAFF")
_CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}


class _Send(NamedTuple):
    channel: str
    status: str
    error: str
    at: datetime.datetime | None
    this_round: bool
    tagged_round: int | None
    tagged_round_at: str | None
    link_ids: frozenset[int]


def _utc(value: Any) -> datetime.datetime | None:
    return parse_datetime_utc(value) if value is not None else None


def _when(dt: datetime.datetime | None) -> str:
    """오늘이면 "HH:MM", 아니면 "MM-DD HH:MM"(KST)."""
    if dt is None:
        return ""
    today = get_today_kst().strftime("%m-%d")
    day = format_datetime_kst(dt, "%m-%d") or ""
    return format_datetime_kst(dt, "%H:%M" if day == today else "%m-%d %H:%M") or ""


def _when_long(dt: datetime.datetime | None) -> str:
    text = _when(dt)
    return f"오늘 {text}" if text and len(text) == 5 else text


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def can_approve_after_confirm(user: Any, order: Any, sd: Any) -> bool:
    """확정한 뒤 이 사용자가 고객 컨펌 승인에서 200 을 받을 것인가(§4.4-4).

    단계가 도면·고객컨펌일 때만 참일 수 있다(확정 뒤 재수정의 재확정 — 생산 이후 — 는 False).
    quest 는 승인 라우트와 **같은 함수**(``find_stage_quest_for_approve``)로 고른다.
    """
    if user is None:
        return False
    stage = normalize_stage_code(((sd or {}).get("workflow") or {}).get("stage") if isinstance(sd, Mapping)
                                 else None)
    if stage not in ("DRAWING", "CONFIRM"):
        return False
    quest, _ = find_stage_quest_for_approve(sd or {}, _CODE_TO_STAGE_NAME.get("CONFIRM", "CONFIRM"), "CONFIRM")
    return bool(quest_approve_allowed(user, order, "CONFIRM", quest))


def _load(db: Any, order_id: int) -> tuple[list[Any], list[Any]]:
    events = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type.in_(_SEND_EVENT_TYPES))
        .order_by(OrderEvent.created_at.desc(), OrderEvent.id.desc())
        .limit(_EVENT_LIMIT)
        .all()
    )
    tokens = (
        db.query(OrderShareToken)
        .filter(OrderShareToken.order_id == order_id, OrderShareToken.kind.in_(_DRAWING_KINDS))
        .order_by(OrderShareToken.created_at.desc(), OrderShareToken.id.desc())
        .limit(_TOKEN_LIMIT)
        .all()
    )
    return events, tokens


def _sends(events: list[Any], tokens: list[Any], info: RoundInfo,
           round_dt: datetime.datetime | None) -> list[_Send]:
    """발송 이벤트를 최신 순으로 해석한다(도면·묶음만)."""
    out: list[_Send] = []
    legacy_candidates = [t for t in tokens if t.kind == "drawing" and t.created_by_user_id is None]
    for ev in events:
        payload = ev.payload if isinstance(ev.payload, Mapping) else {}
        if payload.get("kind") not in _DRAWING_KINDS:
            continue
        at = _utc(ev.created_at)
        tagged = "round_at" in payload
        if tagged:
            this_round = payload.get("round_at") == info.round_at
        else:
            this_round = bool(round_dt and at and at >= round_dt)
        ids = {i for i in (_int_or_none(payload.get("share_id")),
                           _int_or_none(payload.get("drawing_share_id"))) if i is not None}
        if (not tagged and payload.get("kind") == "bundle" and ev.event_type == "SHARE_ALIMTALK"
                and "drawing_share_id" not in payload and at is not None):
            for t in legacy_candidates:
                t_at = _utc(t.created_at)
                if t_at is not None and abs(t_at - at) <= _LEGACY_PAIR_WINDOW:
                    ids.add(int(t.id))
        out.append(_Send(
            channel=_CHANNEL_LABELS.get(ev.event_type, "알림톡"),
            status=str(payload.get("status") or ""),
            error=str(payload.get("error") or ""),
            at=at, this_round=this_round,
            tagged_round=_int_or_none(payload.get("round")) if tagged else None,
            tagged_round_at=str(payload.get("round_at") or "") if tagged else None,
            link_ids=frozenset(ids),
        ))
    return out


def _views_part(views: int, last_viewed: datetime.datetime | None) -> str:
    if views > 0:
        return f" · 링크 열림 {views}번"
    if last_viewed is not None:
        return f" · 링크 열림 · 마지막 {_when(last_viewed)}"
    return ""


def _failed_text(attempt: _Send | None) -> str:
    if attempt is None or attempt.status == "sent":
        return ""
    when = _when(attempt.at)
    if attempt.status == "in_flight":
        return f"{when} {attempt.channel} 보내는 중이었음(결과 모름)"
    if attempt.error == "network":
        return f"{when} {attempt.channel} 결과 확인 안 됨"
    return f"{when} {attempt.channel} 실패 · {_ERROR_LABELS.get(attempt.error, attempt.error or '사유 모름')}"


def _attempt_state(attempt: _Send | None) -> str:
    """화면이 기계적으로 읽는 마지막 시도 결과(두 통 방지 경고용)."""
    if attempt is None:
        return ""
    if attempt.status == "sent":
        return "sent"
    return "unsure" if attempt.status == "in_flight" or attempt.error == "network" else "failed"


def _round_transfer_times(sd: Mapping[str, Any]) -> dict[int, list[str]]:
    """회차 → 그 회차 전달 시각들(이력 순서). 회차 규칙은 ``drawing_round_info`` 와 같다."""
    out: dict[int, list[str]] = {}
    requests_seen = 0
    for h in sd.get("drawing_transfer_history") or []:
        if not isinstance(h, Mapping):
            continue
        if h.get("action") == "REQUEST_REVISION":
            requests_seen += 1
        elif h.get("action") == "TRANSFER":
            out.setdefault(1 + requests_seen, []).append(
                str(h.get("transferred_at") or h.get("at") or "").strip())
    return out


def _in_window(at: datetime.datetime | None, lo: str, hi: datetime.datetime | None) -> bool:
    lo_dt = _utc(lo) if lo else None
    return bool(at and lo_dt and hi and lo_dt <= at < hi)


def _earlier_send(sends: list[_Send], times: list[str], round_dt: datetime.datetime | None) -> _Send | None:
    """추가 전달 뒤 같은 회차의 앞 전달분에 보낸 가장 최근 성공 발송."""
    earlier = set(times[:-1])
    if not earlier:
        return None
    for s in sends:
        if s.status != "sent" or s.this_round:
            continue
        if (s.tagged_round_at in earlier) if s.tagged_round_at is not None else _in_window(s.at, times[0], round_dt):
            return s
    return None


def _history_without_last_transfer(sd: Mapping[str, Any]) -> dict[str, Any]:
    history = [h for h in (sd.get("drawing_transfer_history") or []) if isinstance(h, Mapping)]
    idx = max((i for i, h in enumerate(history) if h.get("action") == "TRANSFER"), default=None)
    if idx is not None:
        history = history[:idx] + history[idx + 1:]
    return {"drawing_transfer_history": history}


def _cancel_warnings(sd: Mapping[str, Any], info: RoundInfo, detail: str) -> tuple[str, str]:
    rt = round_text(info.round)
    after = drawing_round_info(_history_without_last_transfer(sd))
    if after.transfer_count == 0:
        consequence = "취소하면 고객 화면에서도 도면이 사라져요."
    elif after.round == info.round:
        consequence = "취소하면 고객 화면에서도 이번에 더 올린 도면이 빠지고 앞 전달본이 다시 보여요."
    else:
        consequence = f"취소하면 고객 화면에서도 {rt}가 사라지고 {round_text(after.round)}가 다시 보여요."
    base = f"영업이 이 {rt} 도면을 고객에게 이미 보냈어요({detail}). {consequence} "
    # Q5-④: PC·모바일 둘 다 전달 취소 창에 [영업에게 먼저 알리기](긴급 호출 창) 버튼이 있다.
    text = base + "영업에게 먼저 알리려면 [영업에게 먼저 알리기]를 누르세요. 그래도 전달을 취소할까요?"
    return text, text


def _prev_summary(sd: Mapping[str, Any], info: RoundInfo, sends: list[_Send],
                  times: dict[int, list[str]], round_dt: datetime.datetime | None) -> str:
    if info.round < 2:
        return ""
    prev = info.round - 1
    prev_times = times.get(prev) or [""]
    cur_times = times.get(info.round) or []
    hi = (_utc(cur_times[0]) if cur_times and cur_times[0] else None) or round_dt
    history = [h if isinstance(h, Mapping) else {} for h in (sd.get("drawing_transfer_history") or [])]
    rounds = request_rounds(history)
    # 수정 요청은 출처(고객·영업)로 나누지 않고 한 줄로 센다(2026-09-30 사용자 결정).
    requests = sum(1 for r in rounds.values() if r == prev)
    sent = any(s.status == "sent" and (s.tagged_round == prev if s.tagged_round_at is not None
                                       else _in_window(s.at, prev_times[0], hi)) for s in sends)
    parts = [f"{prev}차", "보냄" if sent else "안 보냄"]
    if requests:
        parts.append(f"수정요청 {requests}건")
    return " · ".join(parts)


def _steps(*, arrival_label: str, file_count: int, round_dt: datetime.datetime | None,
           sent: _Send | None, link_only_at: datetime.datetime | None, views: int,
           last_viewed: datetime.datetime | None, drawing_status: str,
           earlier: _Send | None = None) -> list[dict[str, str]]:
    answered = drawing_status in ("RETURNED", "CONFIRMED")
    delivered = sent is not None or link_only_at is not None
    steps = [{"label": arrival_label, "sub": f"도면 {file_count}장", "when": _when(round_dt), "state": "done"}]
    if sent is not None:
        steps.append({"label": "고객에게 보냄", "sub": sent.channel, "when": _when(sent.at), "state": "done"})
    elif link_only_at is not None:
        steps.append({"label": "링크를 만들었어요", "sub": "직접 보낸 경우 보냈는지는 기록되지 않아요",
                      "when": _when(link_only_at), "state": "done"})
    else:
        sub = (f"추가 전달분 아직 안 보냄 · 앞 전달분 {_when(earlier.at)} {earlier.channel} 보냄" if earlier
               else "아직 안 보냄")
        steps.append({"label": "고객에게 보내기", "sub": sub, "when": "",
                      "state": "wait" if answered else "now"})
    view_sub = (f"{views}번 · 마지막 {_when(last_viewed)}" if views and last_viewed
                else (f"{views}번" if views else (f"마지막 {_when(last_viewed)}" if last_viewed else "")))
    steps.append({"label": "링크 열림", "sub": view_sub, "when": _when(last_viewed),
                  "state": "done" if (answered and delivered) else ("now" if delivered else "wait")})
    answer_sub = {"RETURNED": "수정요청", "CONFIRMED": "확정"}.get(drawing_status, "고치기 또는 OK")
    steps.append({"label": "고객 답", "sub": answer_sub, "when": "", "state": "done" if answered else "wait"})
    return steps


def build_customer_send_view(
    db: Any, order: Any, sd: Mapping[str, Any], user: Any, *,
    drawing_status: str, sales_side: bool, can_confirm_receipt: bool, can_cancel_revision: bool,
    is_admin: bool, is_drawing_participant: bool, drawing_mobile_buttons: int,
) -> dict[str, Any]:
    """작업실 상세 ``customer_send`` 화면값(§4.5 약속 — 키는 ``empty_customer_send_view`` 와 같다)."""
    view = empty_customer_send_view()
    sd = sd if isinstance(sd, Mapping) else {}
    status = (drawing_status or "").upper()
    info = drawing_round_info(sd)
    rt = round_text(info.round)
    round_dt = _utc(info.round_at) if info.round_at else None
    file_count = len([f for f in (sd.get("drawing_current_files") or []) if f])
    phone = ka.extract_valid_phone(dict(sd))
    can_send = bool(sales_side and status in ("TRANSFERRED", "CONFIRMED") and file_count > 0)
    arrival_label = ((f"{info.round}차 추가 전달 도착" if info.is_append else f"{info.round}차 도착")
                     if info.round else "")
    view.update(
        round=info.round, round_text=rt, round_at=info.round_at, is_append=info.is_append,
        arrived_at_text=format_datetime_kst(round_dt, "%m-%d %H:%M") or "" if round_dt else "",
        arrival_label=arrival_label, can_send=can_send, has_phone=bool(phone),
        phone_masked=ka._mask_phone(phone) if phone else "",
        can_change_phone=can_send,
        can_save_phone=bool(can_send and env_bool("FOMS_INLINE_EDIT_ENABLED")
                            and str(getattr(user, "role", "") or "").upper() in _SALES_ROLES),
        doc_label_drawing=share_doc_label(sd, "drawing"), doc_label_bundle=share_doc_label(sd, "bundle"),
        bundle_both_template=bool(ka._env(BOTH_TEMPLATE_ENV_PREFIX + ka.resolve_brand(dict(sd)))),
        can_customer_ok=bool(can_confirm_receipt),
        can_approve_after_confirm=can_approve_after_confirm(user, order, sd),
    )

    sent: _Send | None = None
    if info.round > 0:
        events, tokens = _load(db, int(order.id))
        sends = _sends(events, tokens, info, round_dt)
        this_round = [s for s in sends if s.this_round]
        sent = next((s for s in this_round if s.status == "sent"), None)
        paired = set().union(*(s.link_ids for s in sends)) if sends else set()
        link_only = [t for t in tokens
                     if t.created_by_user_id is not None and t.revoked_at is None and int(t.id) not in paired
                     and round_dt is not None and (_utc(t.created_at) or round_dt) >= round_dt]
        link_only_at = _utc(link_only[0].created_at) if link_only else None
        counted = set().union(*(s.link_ids for s in this_round if s.status == "sent")) if this_round else set()
        counted |= {int(t.id) for t in link_only}
        views = sum(int(t.view_count or 0) for t in tokens if int(t.id) in counted)
        viewed = [_utc(t.last_viewed_at) for t in tokens if t.last_viewed_at is not None]
        last_viewed = max((v for v in viewed if v is not None), default=None)
        if last_viewed is not None and (round_dt is None or last_viewed < round_dt):
            last_viewed = None
        views_part = _views_part(views, last_viewed)
        latest_attempt = this_round[0] if this_round else None
        times = _round_transfer_times(sd)
        earlier = None if sent is not None else _earlier_send(sends, times.get(info.round) or [], round_dt)
        view.update(
            sent_this_round=sent is not None, views=views,
            sent_earlier_text=f"{_when(earlier.at)} {earlier.channel}" if earlier else "",
            last_attempt_state=_attempt_state(latest_attempt),
            last_viewed_text=_when(last_viewed),
            link_only_text=f"{_when(link_only_at)} {LINK_ONLY_NOTE}" if link_only_at else "",
            failed_text=_failed_text(latest_attempt),
            prev_summary=_prev_summary(sd, info, sends, times, round_dt),
            steps=_steps(arrival_label=arrival_label, file_count=file_count, round_dt=round_dt, sent=sent,
                         link_only_at=link_only_at, views=views, last_viewed=last_viewed, drawing_status=status,
                         earlier=earlier),
        )
        if sent is not None:
            detail = f"{_when(sent.at)} {sent.channel}{views_part}"
            views_sentence = (f"링크가 {views}번 열렸어요" if views
                              else (f"링크 열림 · 마지막 {_when(last_viewed)}" if last_viewed else "아직 링크가 안 열렸어요"))
            joiner = "보냈고 " if views else "보냈어요 · "
            view["sent_text"] = f"{_when_long(sent.at)} {_CHANNEL_WITH.get(sent.channel, sent.channel)} {joiner}{views_sentence}"
            view["status_line"] = f"영업 → 고객 · {rt} 보냄 {detail}"
            if status == "TRANSFERRED":
                view["cancel_warning_text_pc"], view["cancel_warning_text_mobile"] = _cancel_warnings(sd, info, detail)
        elif latest_attempt is not None:
            view["status_line"] = f"영업 → 고객 · {rt} {_failed_text(latest_attempt)}"
        elif earlier is not None:
            view["status_line"] = (f"영업 → 고객 · {rt} 보냄 {_when(earlier.at)} {earlier.channel}{views_part}"
                                   " · 추가 전달분은 아직 안 보냄")
            if status == "TRANSFERRED":
                view["cancel_warning_text_pc"], view["cancel_warning_text_mobile"] = _cancel_warnings(
                    sd, info, f"{_when(earlier.at)} {earlier.channel}{views_part}")
        elif link_only_at is not None:
            view["status_line"] = f"영업 → 고객 · {rt} 링크만 만듦 {_when(link_only_at)}{views_part}"
        else:
            view["status_line"] = f"영업 → 고객 · {rt} 아직 안 보냄"
        if sales_side and status == "TRANSFERRED":
            view["turn_hint"] = (f"고객 답 기다리는 중 · {_when(sent.at)} {sent.channel}{views_part}" if sent
                                 else ("1차 초안 도착" if info.round == 1 and not info.is_append else arrival_label)
                                 + " · 고객에게 보여 줄 차례")

    _idx, entry = editable_revision_request(sd)
    can_edit = can_edit_revision_request(user, entry, is_admin=is_admin, sales_side=sales_side)
    view["edit_revision"] = edit_revision_prefill(int(order.id), entry) if can_edit else {}
    view["bar"] = build_customer_send_bar(
        drawing_status=status, stage_code=(sd.get("workflow") or {}).get("stage"), sales_side=sales_side,
        can_send=can_send, sent_this_round=sent is not None, can_confirm_receipt=can_confirm_receipt,
        can_cancel_revision=can_cancel_revision, can_edit_revision=can_edit,
        can_approve_after_confirm=bool(view["can_approve_after_confirm"]),
        show_urgent_call=bool(is_drawing_participant), drawing_mobile_buttons=drawing_mobile_buttons,
    )
    return view


__all__ = ["BOTH_TEMPLATE_ENV_PREFIX", "LINK_ONLY_NOTE", "build_customer_send_view", "can_approve_after_confirm"]
