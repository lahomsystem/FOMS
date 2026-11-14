"""할 일마다 막는 조건 · 바뀌는 칸 · 끝난 조건 · 차례 · 고를 값 — **이름 → 함수 표 한 곳**(설계서 2026-11-14-foms-graft 3.3 · 3.6).

- :data:`FUNCTIONS` — 할 일 이름 → :class:`ActionFns`(``check`` 막는 까닭 | None · ``preview`` 바뀌는 칸 · ``verify`` 끝난 조건 ·
  ``steps`` 승인하면 차례로 · ``ran`` 이 제안의 실행 흔적 — 없으면 ``verify``). 뒤 일감(T14 · T15)은 할 일 목록을 고치는 대신
  이 표에 줄을 더하거나 바꾼다. :data:`CHOICE_SOURCES` — (할 일, 넣을 값) → 고를 값 목록 함수(없으면 넣을 값의 ``choices``).
- 모두 순수 함수다 — 주문 줄 하나와 넣을 값만 읽는다(DB 질의 없음). ``steps`` 는 감싼 기능이 실제로 하는 일만 적는다.
- 화면 말은 코드가 정한 말 + 날짜 · 시간대 · 가림 검사를 지난 글뿐 — 손님 · 직원 이름 · 전화 · 주소 · 금액 · 시공 팀 · 인원 없음(D211).
"""

from __future__ import annotations

import copy
import datetime
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from foms.services.as_content_safety import sanitize_as_content_html
from foms.services.auth.partner_scope import is_partner_order
from foms.services.cs_agent.masking import MaskLeak, require_masked
from foms.services.cs_agent.order_block import AS_LABELS
from foms.services.datetime_kst import format_datetime_kst, get_today_kst
from foms.services.erp_actions.registry import ActionShapeError, get
from foms.services.erp_order_flags import is_erp_order_draft
from foms.services.kakao_alimtalk import _ineligible_reason  # 발송 자격 정본 — 다시 만들면 표시 · 발송 판정이 갈린다
from foms.services.notifications.drawing_order_change import should_alert_drawing_team
from foms.services.orders.as_cycle_service import current_cycle
from foms.services.orders.change_reason import is_reason_required
from foms.services.orders.construction_note import note_lines, note_problem
from foms.services.orders.construction_schedule import ScheduleInputError, validate_schedule_input
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.orders.erp_policy_permissions import get_assignee_ids
from foms.services.orders.stage_override import MAIN_PIPELINE_CODES
from foms.services.orders.state_axes import read_as_status, read_deleted, read_main_stage
from foms.services.orders.structured_diff import diff_structured
from foms.services.partners.schedule_request import request_open
from foms.services.production_change_alerts import PROD_STAGES

__all__ = [
    "ActionFns", "CHOICE_SOURCES", "FUNCTIONS", "NONE_LABEL", "alimtalk_action_key", "check", "date_label", "functions",
    "param_choices", "preview", "ran", "reason_required", "steps", "verify",
]

NONE_LABEL = "없음"
_WEEKDAYS = "월화수목금토일"
_OPEN_AS = ("RECEIVED", "IN_PROGRESS")
_TIME_LIMIT, _SNIPPET = 20, 30
_ALIMTALK_REASONS = {
    "order_not_found": "주문을 찾을 수 없어요.", "partner_order": "협력사 주문은 협력사가 손님에게 알려요.",
    "not_configured": "알림톡 설정이 없어 보낼 수 없어요.", "not_eligible": "실측 날짜가 없어 보낼 수 없어요.",
    "no_valid_phone": "손님 휴대폰 번호가 없어 보낼 수 없어요.", "brand_profile_missing": "이 브랜드 알림톡 서식이 아직 없어요.",
}
_DRAWING_ALERT = "도면팀 알림 — 도면 일이 걸린 주문"
_LINK_STEPS = ["주문 화면에서 처리 — 지금 화면 그대로(승인 대기에서는 실행하지 않아요)"]

Params = Mapping[str, Any]


@dataclass(frozen=True)
class ActionFns:
    """할 일 하나의 함수 넷(+ 선택 하나). 모두 ``(주문, 넣을 값)`` 을 받는다(``ran`` 은 제안 번호까지)."""

    check: Callable[[Any, Params], Optional[str]]
    preview: Callable[[Any, Params], list[dict[str, str]]]
    verify: Callable[[Any, Params], bool]
    steps: Callable[[Any, Params], list[str]]
    ran: Optional[Callable[[Any, Params, int], bool]] = None


# ── 공통 도우미 ──────────────────────────────────────────────────────────
def _sd(order: Any) -> dict[str, Any]:
    data = getattr(order, "structured_data", None)
    return data if isinstance(data, dict) else {}


def _node(data: Any, *path: str) -> dict[str, Any]:
    for name in path:
        data = data.get(name) if isinstance(data, dict) else None
    return data if isinstance(data, dict) else {}


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _masked(value: Any, limit: int = _TIME_LIMIT) -> str:
    """사람이 적은 짧은 글(시간대 등) — 한 줄 · 상한 · 가림 검사를 지난 것만, 아니면 빈 글."""
    text = " ".join(_text(value).split())
    if not text or len(text) > limit:
        return ""
    try:
        return require_masked(text)
    except MaskLeak:
        return ""


def date_label(value: Any) -> str:
    """'YYYY-MM-DD…' → '11-20(금)'(못 읽으면 빈 글)."""
    try:
        day = datetime.date.fromisoformat(_text(value)[:10])
    except ValueError:
        return ""
    return f"{day:%m-%d}({_WEEKDAYS[day.weekday()]})"


def _when(day: Any, time: Any = "") -> str:
    """날 + 시간대 화면 말(둘 다 없으면 '없음')."""
    return " ".join(part for part in (date_label(day), _masked(time)) if part) or NONE_LABEL


def _row(field: str, before: str, after: str) -> list[dict[str, str]]:
    return [{"field": field, "before": before, "after": after}]


def _gate(order: Any) -> Optional[str]:
    """모든 할 일의 공통 막는 조건 — 없는 주문 · 삭제된 주문 · 승격 전 초안 주문."""
    if order is None:
        return "주문을 찾을 수 없어요."
    if read_deleted(order) == "DELETED":
        return "삭제된 주문이에요."
    return "아직 등록 전인 초안 주문이에요." if is_erp_order_draft(order) else None


def _past(value: Any) -> Optional[str]:
    """날짜 넣을 값 — 'YYYY-MM-DD' 이고 오늘 이후가 아니면 그 까닭."""
    text = _text(value)
    try:
        day = datetime.date.fromisoformat(text) if len(text) == 10 else None
    except ValueError:
        day = None
    if day is None:
        return "날짜를 골라 주세요."
    return "지난 날짜예요." if day < get_today_kst() else None


def _drawing_alert(order: Any) -> list[str]:
    return [_DRAWING_ALERT] if should_alert_drawing_team(order, _sd(order)) else []


# ── 시공 잡기 · 방문 옮기기(시공) ─────────────────────────────────────────
def _construction(order: Any) -> tuple[str, str]:
    node = _node(_sd(order), "schedule", "construction")
    return _text(node.get("date")) or _text(getattr(order, "erp_construction_date", "")), _text(node.get("time"))


def _kept_time(order: Any, params: Params, first: bool) -> str:
    """승인하면 남을 시간대 — 협력사 주문 첫 시공일은 이미 있는 시간대를 그대로 둔다(희망 확정 길)."""
    current = _construction(order)[1]
    return current if first and is_partner_order(order) and current else _text(params.get("time"))


def _check_schedule(order: Any, params: Params, *, first: bool) -> Optional[str]:
    gate = _gate(order)
    if gate:
        return gate
    day, time = _construction(order)
    if first and day:
        return "이미 시공일이 있어요 — 방문 옮기기로 제안해야 해요."
    if not first and not day:
        return "아직 시공일이 없어요 — 시공 잡기로 제안해야 해요."
    if first and is_partner_order(order) and not request_open(_sd(order), getattr(order, "erp_stage_code", "") or ""):
        return "시공이 시작된 협력사 주문이에요."
    try:
        validate_schedule_input(params.get("date"), params.get("time"))
    except ScheduleInputError as exc:
        return str(exc)
    if not first and day == _text(params.get("date")) and time == _text(params.get("time")):
        return "이미 그 날 · 시간대로 잡혀 있어요."
    return None


def _preview_schedule(order: Any, params: Params, *, first: bool) -> list[dict[str, str]]:
    day, time = _construction(order)
    return _row("시공 날짜", _when(day, time), _when(params.get("date"), _kept_time(order, params, first)))


def _verify_schedule(order: Any, params: Params, *, first: bool) -> bool:
    day, time = _construction(order)
    wanted = _text(params.get("time"))
    return day == _text(params.get("date")) and (not wanted or time == _kept_time(order, params, first))


def _schedule_reason_required(order: Any, params: Params, *, first: bool) -> bool:
    """시공일 쓰기가 끝나면 사유를 물을 변경인가 — 쓰기와 같은 판정(:func:`is_reason_required`)을 미리 돌린다."""
    old_sd = _sd(order)
    new_sd = copy.deepcopy(old_sd)
    if not isinstance(new_sd.get("schedule"), dict):
        new_sd["schedule"] = {}
    if not isinstance(new_sd["schedule"].get("construction"), dict):
        new_sd["schedule"]["construction"] = {}
    node = new_sd["schedule"]["construction"]
    node["date"], node["time"] = _text(params.get("date")), _kept_time(order, params, first)
    return is_reason_required(diff_structured(old_sd, new_sd, max_changes=-1).changes, stage=read_main_stage(order))


def _steps_schedule(order: Any, params: Params, *, first: bool) -> list[str]:
    partner = is_partner_order(order)
    out = ["FOMS 협력사 희망 시공일 확정 — 출고 화면 [확정]과 같은 기능" if first and partner
           else "FOMS 시공일 · 시간대 쓰기 — 주문 화면 시공일 칸과 같은 기능", *_drawing_alert(order)]
    if getattr(order, "is_erp_order", False) and (getattr(order, "erp_stage_code", "") or "") in PROD_STAGES:
        out.append("생산팀 알림 — 시공일이 바뀌면")
    if partner:
        out.append("협력사 직원 폰 알림 — 시공일 안내")
    if _schedule_reason_required(order, params, first=first):
        out.append("변경 사유 남기기 — 승인 창에서 고른 사유")
    return out


# ── 방문 옮기기(AS) · AS 접수 ────────────────────────────────────────────
def _as_visit(order: Any) -> tuple[str, str]:
    node = _node(_sd(order), "schedule", "as_visit")
    return _text(node.get("date")), _text(node.get("time"))


def _check_as_visit(order: Any, params: Params) -> Optional[str]:
    gate = _gate(order)
    if gate:
        return gate
    if read_as_status(order) not in _OPEN_AS:
        return "열린 AS 가 없어요 — AS 접수가 먼저예요."
    same = _as_visit(order)[0] == _text(params.get("date"))
    return _past(params.get("date")) or ("이미 그 날로 잡혀 있어요." if same else None)


def _preview_as_visit(order: Any, params: Params) -> list[dict[str, str]]:
    day, time = _as_visit(order)
    return _row("AS 방문 날짜", _when(day, time), _when(params.get("date")))


def _check_register_as(order: Any, params: Params) -> Optional[str]:
    gate = _gate(order)
    if gate:
        return gate
    if read_as_status(order) in _OPEN_AS:
        return "이미 열린 AS 가 있어요 — AS 화면에서 확인해 주세요."
    return None if _text(params.get("as_content")) else "증상이 비었어요."


def _preview_register_as(order: Any, params: Params) -> list[dict[str, str]]:
    content = " ".join(_text(params.get("as_content")).split())
    snippet = content if len(content) <= _SNIPPET else content[:_SNIPPET] + "…"
    return _row("AS 건", AS_LABELS.get(read_as_status(order), NONE_LABEL), f"접수 · {snippet}")


def _verify_register_as(order: Any, params: Params) -> bool:
    cycle = current_cycle(_sd(order))
    if cycle is None or read_as_status(order) not in _OPEN_AS:
        return False
    return cycle.get("initial_content") == sanitize_as_content_html(params.get("as_content"))


# ── 알림톡 보내기(실측 예약) ─────────────────────────────────────────────
def alimtalk_action_key(order_id: int, proposal_id: int) -> str:
    """할 일 알림톡의 중복 막기 열쇠 — ``alimtalk:measure:<주문>:action:<제안 번호>``(설계서 3.4 '한 번만')."""
    return f"alimtalk:measure:{int(order_id)}:action:{int(proposal_id)}"


def _alimtalk_record(order: Any) -> dict[str, Any]:
    record = _sd(order).get("alimtalk_measurement")
    return record if isinstance(record, dict) else {}


def _alimtalk_sent(record: Mapping[str, Any]) -> bool:
    return bool(record.get("sent_at")) and record.get("error") is None and bool(record.get("message_id"))


def _check_alimtalk(order: Any, _params: Params) -> Optional[str]:
    gate = _gate(order)
    code = None if gate else _ineligible_reason(order, _sd(order))
    return gate or (_ALIMTALK_REASONS.get(code, "알림톡을 보낼 수 없는 주문이에요.") if code else None)


def _preview_alimtalk(order: Any, _params: Params) -> list[dict[str, str]]:
    record = _alimtalk_record(order)
    if _alimtalk_sent(record):
        before = f"{date_label(format_datetime_kst(record.get('sent_at'), '%Y-%m-%d')) or '전에'} 보냄"
    else:
        before = "못 보냄" if record.get("error") else "보낸 적 없음"
    return _row("손님 알림톡(실측 예약)", before, "1건 보냄")


def _ran_alimtalk(order: Any, _params: Params, proposal_id: int) -> bool:
    record = _alimtalk_record(order)
    return _alimtalk_sent(record) and record.get("dedupe_key") == alimtalk_action_key(order.id, proposal_id)


# ── 시공 메모 더하기 ─────────────────────────────────────────────────────
def _preview_note(order: Any, params: Params) -> list[dict[str, str]]:
    count = len(note_lines(_sd(order)))
    return _row("시공 메모", f"{count}줄" if count else NONE_LABEL, f"+ {_text(params.get('note'))}")


# ── 바로가기(link) — 단계 넘기기 · 도면 담당 맡기기 · 방문 옮기기(실측) ────────────
def _stage(order: Any) -> str:
    return _text(getattr(order, "erp_stage_code", "")).upper()


def _check_advance(order: Any, _params: Params) -> Optional[str]:
    stage = _stage(order)
    last = stage not in MAIN_PIPELINE_CODES or stage == MAIN_PIPELINE_CODES[-1]
    return _gate(order) or ("더 넘길 단계가 없어요." if last else None)


def _preview_advance(order: Any, _params: Params) -> list[dict[str, str]]:
    stage = _stage(order)
    index = MAIN_PIPELINE_CODES.index(stage) if stage in MAIN_PIPELINE_CODES else -1
    after = MAIN_PIPELINE_CODES[index + 1] if 0 <= index < len(MAIN_PIPELINE_CODES) - 1 else ""
    return _row("주문 단계", STAGE_LABELS.get(stage, NONE_LABEL), STAGE_LABELS.get(after, NONE_LABEL))


def _preview_assign(order: Any, _params: Params) -> list[dict[str, str]]:
    count = len(get_assignee_ids(order, "DRAWING_DOMAIN"))
    return _row("도면 담당", f"{count}명" if count else NONE_LABEL, "승인하는 사람이 고름")


def _measurement(order: Any) -> tuple[list[str], str]:
    node = _node(_sd(order), "schedule", "measurement")
    days = [part.strip() for part in _text(node.get("date") or getattr(order, "erp_measurement_date", "")).split(",")]
    return [day for day in days if day], _text(node.get("time"))


def _check_move_measurement(order: Any, params: Params) -> Optional[str]:
    problem = _gate(order) or _past(params.get("date"))
    if problem:
        return problem
    stage = _stage(order)
    if stage in MAIN_PIPELINE_CODES and MAIN_PIPELINE_CODES.index(stage) > MAIN_PIPELINE_CODES.index("MEASURE"):
        return "실측이 지난 주문이에요."
    return "이미 그 날로 잡혀 있어요." if _measurement(order)[0] == [_text(params.get("date"))] else None


def _preview_move_measurement(order: Any, params: Params) -> list[dict[str, str]]:
    days, time = _measurement(order)
    before = f"{', '.join(date_label(day) or day for day in days)} {_masked(time)}".strip()
    return _row("실측 날짜", before or NONE_LABEL, _when(params.get("date")))


def _fixed(lines: list[str]) -> Callable[[Any, Params], list[str]]:
    return lambda _order, _params: list(lines)


#: 할 일 이름 → 함수(한 곳). 할 일 목록 가운데 ``human``(사람만)은 제안 길이 없어 여기 없다.
FUNCTIONS: dict[str, ActionFns] = {
    "schedule_construction": ActionFns(
        lambda o, p: _check_schedule(o, p, first=True), lambda o, p: _preview_schedule(o, p, first=True),
        lambda o, p: _verify_schedule(o, p, first=True), lambda o, p: _steps_schedule(o, p, first=True)),
    "move_construction": ActionFns(
        lambda o, p: _check_schedule(o, p, first=False), lambda o, p: _preview_schedule(o, p, first=False),
        lambda o, p: _verify_schedule(o, p, first=False), lambda o, p: _steps_schedule(o, p, first=False)),
    "schedule_as_visit": ActionFns(
        _check_as_visit, _preview_as_visit, lambda o, p: _as_visit(o)[0] == _text(p.get("date")),
        _fixed(["FOMS AS 방문일 정하기 — AS 화면과 같은 기능", "AS 기록에 '방문일 확정' 한 줄"])),
    "register_as": ActionFns(
        _check_register_as, _preview_register_as, _verify_register_as,
        _fixed(["FOMS AS 접수 — AS 접수 창과 같은 기능", "AS 기록에 접수 내용 · '접수됨' 줄"])),
    "send_measure_alimtalk": ActionFns(
        _check_alimtalk, _preview_alimtalk, lambda o, p: _alimtalk_sent(_alimtalk_record(o)),
        _fixed(["손님 알림톡 1건 — 실측 예약 안내(지금 있는 서식 그대로)"]), _ran_alimtalk),
    "add_construction_note": ActionFns(
        lambda o, p: _gate(o) or note_problem(_sd(o), p.get("note")), _preview_note,
        lambda o, p: " ".join(_text(p.get("note")).split()) in note_lines(_sd(o)),
        lambda o, p: ["FOMS 시공 메모 끝에 한 줄 더하기 — 있던 메모는 그대로", *_drawing_alert(o)]),
    "advance_stage": ActionFns(_check_advance, _preview_advance, lambda o, p: False, _fixed(_LINK_STEPS)),
    "assign_draftsman": ActionFns(
        lambda o, p: _gate(o) or ("이미 도면 담당이 있어요." if get_assignee_ids(o, "DRAWING_DOMAIN") else None),
        _preview_assign, lambda o, p: bool(get_assignee_ids(o, "DRAWING_DOMAIN")), _fixed(_LINK_STEPS)),
    "move_measurement": ActionFns(
        _check_move_measurement, _preview_move_measurement,
        lambda o, p: _text(p.get("date")) in _measurement(o)[0], _fixed(_LINK_STEPS)),
}

#: (할 일, 넣을 값) → 고를 값 목록 함수(주문을 받는다). 뒤 일감이 더한다(예: 도면 담당 고르기 사람 목록).
CHOICE_SOURCES: dict[tuple[str, str], Callable[[Any], list[dict[str, Any]]]] = {}


def functions(action: Any) -> ActionFns:
    """할 일 이름 → 함수 묶음(표에 없으면 :class:`ActionShapeError` — 칸 이름 ``action``)."""
    fns = FUNCTIONS.get(action) if isinstance(action, str) else None
    if fns is None:
        raise ActionShapeError(("action",))
    return fns


def check(action: Any, order: Any, params: Params) -> Optional[str]:
    """막는 까닭(코드가 정한 화면 말) — 없으면 ``None``."""
    return functions(action).check(order, params)


def preview(action: Any, order: Any, params: Params) -> list[dict[str, str]]:
    """바뀌는 칸 ``[{"field", "before", "after"}]``(지금 주문 기준)."""
    return functions(action).preview(order, params)


def verify(action: Any, order: Any, params: Params) -> bool:
    """끝난 조건 — 주문이 이미 그 값이면 참(바로가기 닫기 · 되맞추기)."""
    return bool(functions(action).verify(order, params))


def ran(action: Any, order: Any, params: Params, proposal_id: int) -> bool:
    """이 제안이 실행된 흔적이 주문에 있나(되맞추기) — 할 일에 ``ran`` 이 없으면 :func:`verify`."""
    fns = functions(action)
    return bool(fns.ran(order, params, proposal_id)) if fns.ran else bool(fns.verify(order, params))


def steps(action: Any, order: Any, params: Params) -> list[str]:
    """승인하면 차례로 — 감싼 기능이 실제로 하는 일만."""
    return list(functions(action).steps(order, params))


def reason_required(action: Any, order: Any, params: Params) -> bool:
    """승인하면 지금 사유 원장이 사유를 물을 변경인가(시공일 쓰기 두 할 일만 — 그 밖은 거짓)."""
    if action not in ("schedule_construction", "move_construction") or order is None:
        return False
    return _schedule_reason_required(order, params, first=action == "schedule_construction")


def param_choices(action: Any, param: str, order: Any) -> list[dict[str, Any]]:
    """넣을 값 하나의 고를 값 ``[{"value", "label"}]`` — :data:`CHOICE_SOURCES` 함수가 있으면 그 값, 아니면 넣을 값의
    ``choices``(시간대 등). 모르는 할 일 · 넣을 값은 빈 목록."""
    source = CHOICE_SOURCES.get((action, param))
    if source is not None:
        return list(source(order))
    try:
        spec = get(action)
    except ActionShapeError:
        return []
    found = next((p for p in spec.params if p.name == param), None)
    return [{"value": value, "label": value or "정하지 않음"} for value in found.choices] if found else []
