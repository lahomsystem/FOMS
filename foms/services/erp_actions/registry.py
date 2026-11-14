"""ERP 할 일 목록 — 지금 기능에 이름을 붙여 감싼다(설계서 2026-11-14-foms-graft 3.3 · 3.4). **선언만 있는 작은 목록**이다.

할 일마다 이름 · 화면 이름 · 대상 물건 · 넣을 값 꼴 · 정책(지금 정책 표 ``POLICY_REGISTRY`` 이름 — 감싼 길과 같은 것) · 갈래 ·
AI 가 가질 수 있는 가장 높은 수준 · 감싼 기능 글 · 폰 승인 · 채널톡 작은 창 줄을 적는다. 실행 · 미리 보기 · 끝난 조건 함수는
여기 두지 않는다(:mod:`.preview` · :mod:`.runners` 가 이름 → 함수 표로 잇는다).

- 갈래(:data:`MODES`): ``run`` 승인하면 실행 · ``link`` 바로가기만(감싼 처리기를 요청에서 떼어 내지 못한 할 일만 남는 꼴 —
  판 1 끝에는 없다, D206) · ``human`` 사람만(제안 · 실행 길 없음 — 넣을 값도 없다).
- 넣을 값 꼴(:data:`PARAM_KINDS`): ``date``('YYYY-MM-DD' · 오늘 이후) · ``time_slot``(:data:`TIME_SLOTS` — 시공일 쓰기
  ``construction_schedule.TIME_CHOICES`` 와 같은 글자, 시험이 견준다) · ``masked_text``(가림 검사 0 · 길이 상한) · ``choice`` ·
  ``users``(사람 고르기 — 사용자 번호만 · 겹침 뺌 · 상한) · ``flag``(참 · 거짓). 전화 · 주소 · 금액을 받는 꼴은 없다.
- 꼭 있어야 함(``required``): 날짜 · 글 · 고르기는 본문에 칸이 있어야 한다. 사람 고르기는 **승인하는 사람이 골라야 실행된다**는
  뜻이다 — 제안 때는 비워 둔다(AI 는 사람을 고르지 않는다 · 비면 빈 목록), 빈 채 승인하면 감싼 본체가 막는다(409).
  비어도 되는 칸이 비면 처음 값(``default`` — 없으면 빈 값)이다. 시공일 두 할 일의 ``notify_customer``(손님 알림톡 — 시공일
  안내, D213)는 처음 값이 참이다. 알림톡이 쓸 수 있는 상태인지는 :mod:`.construction_notice` 가 주문마다 본다.
- ``notify_team``: 새 제안의 폰 알림(설계서 3.14 · D215)이 그 주문 담당에게 못 갈 때 받는 팀(:mod:`.notify`).
- 이 모듈은 가볍게 둔다(선언만 — 시공일 쓰기 모듈처럼 알림까지 끌어오는 import 를 하지 않는다). 어느 길에서 먼저 불려도 된다.
- :func:`parse_params` 가 정한 칸만 · 꼴을 본다 — 틀리면 :class:`ActionShapeError`(칸 이름만 싣는다, 받은 값은 싣지 않는다).
- 수준은 0 ~ 2 까지만 있다(자율 수준 3 — 사람 승인 없는 실행 — 의 코드는 만들지 않는다).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from foms.services.cs_agent.masking import MaskLeak, require_masked
from foms.services.datetime_kst import get_today_kst

__all__ = [
    "ACTIONS", "ActionShapeError", "ActionSpec", "EVIDENCE_KINDS", "FAILURES", "HUMAN_LABEL", "KIND_CHOICE",
    "KIND_DATE", "KIND_FLAG", "KIND_MASKED_TEXT", "KIND_TIME_SLOT", "KIND_USERS", "LEVEL_LABELS", "LEVELS",
    "MAX_EVIDENCE", "MAX_LEVEL", "MAX_REASON", "MAX_USERS", "MODE_HUMAN", "MODE_LINK", "MODE_RUN", "MODES",
    "NOTIFY_CUSTOMER", "PARAM_KINDS", "Param", "REJECT_CODES",
    "REJECT_LABELS", "SOURCE_KINDS", "STATUS_EXECUTED", "STATUS_EXECUTING", "STATUS_EXPIRED", "STATUS_FAILED",
    "STATUS_OPEN", "STATUS_REJECTED", "STATUS_SUPERSEDED", "STATUSES", "TIME_SLOTS", "dedupe_key", "get",
    "level_label", "message", "parse_params", "specs",
]

# ── 갈래 · 수준 ──────────────────────────────────────────────────────────
MODE_RUN, MODE_LINK, MODE_HUMAN = "run", "link", "human"
MODES: tuple[str, ...] = (MODE_RUN, MODE_LINK, MODE_HUMAN)
#: 자율 수준 — 0 읽기만(제안을 만들지 않음) · 1 초안 · 2 제안. 3(실행 뒤 알림)은 판 1 에 없다.
LEVELS: tuple[int, ...] = (0, 1, 2)
MAX_LEVEL = 2
LEVEL_LABELS: dict[int, str] = {0: "0 읽기만", 1: "1 초안", 2: "2 제안"}
HUMAN_LABEL = "사람만"

# ── 제안 상태(표 erp_action_proposals 검사 제약과 같은 글자) ──────────────────
STATUS_OPEN, STATUS_EXECUTING, STATUS_EXECUTED = "open", "executing", "executed"
STATUS_FAILED, STATUS_REJECTED, STATUS_EXPIRED, STATUS_SUPERSEDED = "failed", "rejected", "expired", "superseded"
STATUSES: tuple[str, ...] = (STATUS_OPEN, STATUS_EXECUTING, STATUS_EXECUTED, STATUS_FAILED, STATUS_REJECTED,
                             STATUS_EXPIRED, STATUS_SUPERSEDED)

# ── 제안 칸 상한 · 근거 · 출처(설계서 3.4) ─────────────────────────────────
MAX_REASON = 500
MAX_EVIDENCE = 8
EVIDENCE_KINDS: tuple[str, ...] = ("brain", "order", "cs_turn", "visit")
SOURCE_KINDS: tuple[str, ...] = ("cs_turn", "sweep")

# ── 거절 까닭 · 실패 말 ──────────────────────────────────────────────────
REJECT_CODES: tuple[str, ...] = ("wrong_date", "misread", "no_slot", "already_done", "other")
REJECT_LABELS: dict[str, str] = {
    "wrong_date": "날짜가 틀림",
    "misread": "손님 말을 잘못 읽음",
    "no_slot": "팀 자리 없음",
    "already_done": "이미 처리함",
    "other": "그 밖",
}
#: 실패 코드 → 화면 말(오류 글은 이 말만 나간다 — 받은 값 · 예외 글을 싣지 않는다).
FAILURES: dict[str, str] = {
    "ACTION_NOT_OPEN": "이미 처리된 제안이에요 — 새로 불러와 주세요.",
    "ACTION_BASE_CHANGED": "제안을 만든 뒤 주문이 바뀌었어요 — 바뀐 값으로 다시 봐 주세요.",
    "ACTION_PRECONDITION": "지금 주문 상태로는 할 수 없어요 — 주문 화면에서 확인해 주세요.",
    "ACTION_FORBIDDEN": "찾을 수 없습니다.",
    "ACTION_SHAPE": "값이 맞지 않아요 — 칸을 확인해 주세요.",
    "ACTION_FAILED": "실행하지 못했어요 — 주문 화면에서 확인해 주세요.",
}

# ── 넣을 값 꼴 ───────────────────────────────────────────────────────────
KIND_DATE, KIND_TIME_SLOT, KIND_MASKED_TEXT, KIND_CHOICE = "date", "time_slot", "masked_text", "choice"
KIND_USERS, KIND_FLAG = "users", "flag"
PARAM_KINDS: tuple[str, ...] = (KIND_DATE, KIND_TIME_SLOT, KIND_MASKED_TEXT, KIND_CHOICE, KIND_USERS, KIND_FLAG)
#: 사람 고르기 한 번에 고를 수 있는 사람 수 상한.
MAX_USERS = 10
#: 시간대 — 빈 글(정하지 않음) · 오전 · 오후 · 종일. ``construction_schedule.TIME_CHOICES`` 와 같은 글자(시험이 견준다).
TIME_SLOTS: tuple[str, ...] = ("", "오전", "오후", "종일")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class ActionShapeError(ValueError):
    """넣을 값 꼴이 틀림 — :attr:`fields` 에 칸 이름만(받은 값 · 글은 싣지 않는다). 코드는 ``ACTION_SHAPE``."""

    code = "ACTION_SHAPE"

    def __init__(self, fields: tuple[str, ...]) -> None:
        self.fields = tuple(fields)
        super().__init__(f"{self.code}: {', '.join(self.fields)}")


@dataclass(frozen=True)
class Param:
    """넣을 값 하나 — 이름 · 꼴(:data:`PARAM_KINDS`) · 화면 이름 · 꼭 있어야 함 · 고를 값 · 글 길이 상한."""

    name: str
    kind: str
    label: str
    required: bool = True
    choices: tuple[str, ...] = ()
    limit: int = 0
    default: Any = None  # 비어도 되는 칸이 비었을 때의 값(없으면 꼴마다 빈 값 — :func:`_empty`)


@dataclass(frozen=True)
class ActionSpec:
    """할 일 하나(설계서 3.3 표 한 줄)."""

    name: str
    label: str
    target: str  # 대상 물건 종류(foms/services/erp_ontology/objects.py OBJECT_TYPES 의 코드 이름)
    params: tuple[Param, ...]
    policy_id: Optional[str]  # POLICY_REGISTRY 이름 — mode = human 이면 None
    mode: str
    level_cap: int
    wraps: str  # 감싼 지금 기능(글)
    phone_ok: bool = False
    wam_inline: bool = False
    notify_team: Optional[str] = None  # 폰 알림 — 주문 담당이 없을 때 받는 팀(설계서 3.14 · D215)


_SLOT = Param("time", KIND_TIME_SLOT, "시간대", required=False, choices=TIME_SLOTS)
#: 시공일 쓰기와 같이 손님에게 시공일 안내 알림톡을 보낼까(D213 — 처음 값 참, 고쳐서 승인에서 끈다).
NOTIFY_CUSTOMER = Param("notify_customer", KIND_FLAG, "손님 알림톡(시공일 안내)", required=False, default=True)

ACTIONS: dict[str, ActionSpec] = {spec.name: spec for spec in (
    ActionSpec("schedule_construction", "시공 잡기", "erp:visit",
               (Param("date", KIND_DATE, "시공 날"), _SLOT, NOTIFY_CUSTOMER), "CONSTRUCTION_SCHEDULE_EDIT", MODE_RUN, 2,
               "validate_schedule_input → write_construction_schedule → finalize_schedule_notifications(시공일이 빈 "
               "주문) · 협력사 주문은 confirm_partner_request", phone_ok=True, notify_team="SHIPMENT"),
    ActionSpec("move_construction", "방문 옮기기(시공)", "erp:visit",
               (Param("date", KIND_DATE, "시공 날"), _SLOT, NOTIFY_CUSTOMER), "CONSTRUCTION_SCHEDULE_EDIT", MODE_RUN, 2,
               "시공 잡기와 같은 함수(시공일이 이미 있는 주문) · 사유가 필요한 변경이면 승인 창 사유를 attach_reason 에",
               phone_ok=True, notify_team="SHIPMENT"),
    ActionSpec("schedule_as_visit", "방문 옮기기(AS)", "erp:as_case",
               (Param("date", KIND_DATE, "AS 방문 날"),), "ERP_EDIT", MODE_RUN, 2, "schedule_as_cycle", phone_ok=True,
               notify_team="CS"),
    ActionSpec("register_as", "AS 접수", "erp:as_case",
               (Param("as_content", KIND_MASKED_TEXT, "증상", limit=MAX_REASON),), "CONSTRUCTION_EDIT", MODE_RUN, 2,
               "register_as_from_payload", phone_ok=True, notify_team="CS"),
    ActionSpec("send_measure_alimtalk", "알림톡 보내기(실측 예약)", "erp:visit", (), "STAFF_MUTATION", MODE_RUN, 1,
               "send_alimtalk(서식은 지금 있는 실측 예약 하나 — 손님에게 나가는 글)", phone_ok=True, notify_team="SALES"),
    ActionSpec("add_construction_note", "시공 메모 더하기", "erp:order",
               (Param("note", KIND_MASKED_TEXT, "시공 메모", limit=200),), "ERP_EDIT", MODE_RUN, 2,
               "construction_note(새 서비스 함수 — structured_data.notes.construction_note 끝에 한 줄)",
               phone_ok=True, wam_inline=True, notify_team="CS"),
    ActionSpec("advance_stage", "단계 넘기기", "erp:order", (), "STAFF_MUTATION", MODE_RUN, 2,
               "approve_quest_from_payload(현재 작업 승인 본체 — 승인을 다 받았는데 단계가 그대로인 주문을 다시 넘긴다)",
               phone_ok=True, notify_team="CS"),
    ActionSpec("assign_draftsman", "도면 담당 맡기기", "erp:drawing",
               (Param("user_ids", KIND_USERS, "도면 담당", limit=MAX_USERS),), "STAFF_MUTATION", MODE_RUN, 2,
               "assign_draftsman_from_payload(도면 담당 지정 본체 — 사람은 승인하는 사람이 고른다)", notify_team="DRAWING"),
    ActionSpec("move_measurement", "방문 옮기기(실측)", "erp:visit",
               (Param("date", KIND_DATE, "실측 날"),), "ERP_EDIT", MODE_RUN, 2,
               "update_order_field_from_payload(칸 고치기 본체 — 칸 measurement_date 만)", phone_ok=True,
               notify_team="SALES"),
    ActionSpec("send_construction_alimtalk", "알림톡 보내기(시공일 안내)", "erp:visit", (), "STAFF_MUTATION", MODE_RUN, 1,
               "send_construction_alimtalk(새 — 시공일 안내 서식 · 손님에게 나가는 글, 설계서 3.13)", phone_ok=True,
               notify_team="CS"),
    ActionSpec("cancel_order", "주문 취소", "erp:order", (), None, MODE_HUMAN, 0, "— (사람만 — 돈이 걸린 일)"),
)}


def get(name: Any) -> ActionSpec:
    """이름 → 할 일(모르는 이름은 :class:`ActionShapeError` — 칸 이름 ``action``)."""
    spec = ACTIONS.get(name) if isinstance(name, str) else None
    if spec is None:
        raise ActionShapeError(("action",))
    return spec


def message(code: str) -> str:
    """실패 코드 → 화면 말(모르는 코드는 ``ACTION_FAILED`` 말)."""
    return FAILURES.get(code, FAILURES["ACTION_FAILED"])


def level_label(spec: ActionSpec) -> str:
    """할 일의 수준 상한 화면 말(사람만 할 일은 '사람만')."""
    return HUMAN_LABEL if spec.mode == MODE_HUMAN else LEVEL_LABELS[spec.level_cap]


def _clean_date(value: Any, today: datetime.date) -> Optional[str]:
    """'YYYY-MM-DD' 이고 오늘 이후면 그 글, 아니면 ``None``."""
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return None
    try:
        day = datetime.date.fromisoformat(value)
    except ValueError:
        return None
    return value if day >= today else None


def _clean_text(value: Any, limit: int) -> Optional[str]:
    """한 줄로 모은 글 — 비지 않고 · 상한 안 · 가림 검사 0 이면 그 글, 아니면 ``None``."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or len(text) > limit:
        return None
    try:
        return require_masked(text)
    except MaskLeak:
        return None


def _clean_users(value: Any, limit: int) -> Optional[list[int]]:
    """사람 고르기 — 양의 정수 사용자 번호 목록(겹침은 앞 차례로 뺀다 · 상한 안). 틀리면 ``None``. 빈 목록은 된다."""
    if not isinstance(value, (list, tuple)) or not all(
            isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value):
        return None
    ids = list(dict.fromkeys(value))
    return ids if not limit or len(ids) <= limit else None


def _clean(param: Param, value: Any, today: datetime.date) -> Any:
    """값 하나를 꼴대로 본다 — 맞으면 정리한 값, 틀리면 ``None``."""
    if param.kind == KIND_DATE:
        return _clean_date(value, today)
    if param.kind == KIND_MASKED_TEXT:
        return _clean_text(value, param.limit)
    if param.kind in (KIND_TIME_SLOT, KIND_CHOICE):
        text = value.strip() if isinstance(value, str) else None
        return text if text is not None and text in param.choices else None
    if param.kind == KIND_USERS:
        return _clean_users(value, param.limit)
    if param.kind == KIND_FLAG:
        return value if isinstance(value, bool) else None
    raise ValueError(f"모르는 꼴: {param.kind}")


def _empty(param: Param) -> Any:
    """비어도 되는 칸이 비었을 때의 값 — 처음 값이 있으면 그 값, 없으면 사람 고르기는 빈 목록 · 참거짓은 거짓 · 그 밖은 빈 글."""
    if param.default is not None:
        return param.default
    return [] if param.kind == KIND_USERS else (False if param.kind == KIND_FLAG else "")


def parse_params(name: Any, body: Any, *, today: Optional[datetime.date] = None) -> dict[str, Any]:
    """본문을 그 할 일의 넣을 값으로 검사한다 — 정한 칸만 · 꼴이 맞아야.

    Args:
        name: 할 일 이름(:data:`ACTIONS`). ``human`` 할 일은 넣을 값 길이 없어 거절한다.
        body: 넣을 값 dict. 정한 칸 밖 이름이 있으면 거절(칸 이름 ``params``).
        today: 날짜 꼴의 '오늘'(없으면 한국 오늘 — :func:`get_today_kst`).

    Returns:
        칸 이름 → 정리한 값(날짜 'YYYY-MM-DD' · 시간대 · 한 줄 글 · 사용자 번호 목록 · 참거짓). 없어도 되는 칸이 비면
        :func:`_empty`. 사람 고르기 칸은 꼭 있어야 해도 비면 빈 목록이다(제안 때는 아무도 고르지 않는다).

    Raises:
        ActionShapeError: 모르는 할 일 · 사람만 할 일 · 정한 칸 밖 · 빠진 칸 · 꼴 틀림(칸 이름만 싣는다).
    """
    spec = get(name)
    if spec.mode == MODE_HUMAN:
        raise ActionShapeError(("action",))
    if not isinstance(body, Mapping):
        raise ActionShapeError(("params",))
    known = {param.name for param in spec.params}
    problems = ["params"] if any(key not in known for key in body) else []
    day, out = today or get_today_kst(), {}
    for param in spec.params:
        value = body.get(param.name)
        if value is None:
            if param.required and param.kind != KIND_USERS:
                problems.append(param.name)
            else:
                out[param.name] = _empty(param)
            continue
        cleaned = _clean(param, value, day)
        if cleaned is None:
            problems.append(param.name)
        else:
            out[param.name] = cleaned
    if problems:
        raise ActionShapeError(tuple(problems))
    return out


def dedupe_key(action: Any, order_id: Optional[int], params: Optional[Mapping[str, Any]],
               scope: Optional[str] = None) -> str:
    """겹침 열쇠 ``'<할 일>:<주문 번호>:<값 지문>'`` — 같은 할 일 · 주문 · 값이면 같고 하나라도 다르면 다르다.

    값 지문은 칸 이름 순으로 맞춘 JSON 의 sha256 앞 16자다(칸 순서가 달라도 같은 값). 주문이 없으면 ``-``.
    ``scope`` 는 넣을 값이 없는 할 일의 '상황'(실측 일정 · 단계 · 시공일 — 훑기 규칙이 준다)이다. 주면 지문 재료에
    ``_scope`` 로 들어가 상황이 바뀌면 열쇠가 달라진다(거절된 뒤 날짜 · 단계가 바뀌면 다시 제안 — 원장 F-08). ``None`` 이면
    지금 열쇠 그대로.
    """
    spec = get(action)
    if order_id is not None and (isinstance(order_id, bool) or not isinstance(order_id, int)):
        raise ActionShapeError(("order_id",))
    material = dict(params or {})
    if scope is not None:
        material["_scope"] = str(scope)
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return f"{spec.name}:{'-' if order_id is None else order_id}:{digest}"


def _param_spec(param: Param) -> dict[str, Any]:
    """넣을 값 하나 → 화면 표(고를 값은 이름까지)."""
    out: dict[str, Any] = {"name": param.name, "kind": param.kind, "label": param.label, "required": param.required}
    if param.choices:
        out["choices"] = [{"value": value, "label": value or "정하지 않음"} for value in param.choices]
    if param.limit:
        out["limit"] = param.limit
    if param.default is not None:
        out["default"] = param.default
    return out


def specs() -> list[dict[str, Any]]:
    """화면 · 온톨로지에 싣는 할 일 표 — 이름 · 화면 이름 · 대상 · 갈래 · 수준 상한 · 정책 · 감싼 기능 · 폰 · 작은 창 · 넣을 값."""
    return [{"name": s.name, "label": s.label, "target": s.target, "mode": s.mode, "level_cap": s.level_cap,
             "level_label": level_label(s), "policy_id": s.policy_id, "wraps": s.wraps, "phone_ok": s.phone_ok,
             "wam_inline": s.wam_inline, "params": [_param_spec(p) for p in s.params]} for s in ACTIONS.values()]
