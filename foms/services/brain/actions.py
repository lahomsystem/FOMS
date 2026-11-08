"""이름 있는 액션 유형(설계서 7.7 · 사장님 D104) — 화면 단추마다 하나. **선언만 있는 작은 목록**이다.

액션마다 이름 · 화면 이름 · 매개변수 꼴 · 제출 조건(권한 · 대상 · 기준 판) · 실패 말 · 끝난 말을 적는다. 엔진은 그대로
:func:`.apply.apply_change` 하나이고, 액션은 그 위 얇은 층이다(:mod:`.action_runner` 가 이름 → 서비스를 잇는다).

- **API 는 이 목록으로 본문을 검사한다**(:func:`parse` — 정한 칸 밖 · 꼴이 틀린 값은 400, 서비스에 닿기 전).
- **화면은 이 목록으로 단추 · 고르기 칸을 그린다**(:func:`specs` 를 ``data-actions`` 로 싣는다 — 이름 · 거절 칩 · 고칠 칸).
- **⑤-5 챗봇 · 에이전트 도구 목록**도 같은 목록에서 나온다(:func:`tool_specs` — JSON Schema 꼴 입력). **지금 에이전트 도구로
  내놓는 것은 읽기 셋뿐**이다(:data:`foms.services.brain.chat_tools.AGENT_TOOLS`) — 쓰기 액션은 하나도 모델 도구로 열지 않는다
  (:data:`AGENT_EXPOSED_WRITES` 빈 묶음). 챗봇 화면은 사람에게 ``propose_edit`` 를 권한다.
- 코드(에이전트) 길 액션은 :data:`AGENT_ACTION_TYPES` — 챗봇 '틀림' 신고 묶음(``report_conflict``)이 이 꼴로 선언되고
  :func:`foms.services.brain.action_runner.perform_agent` 로만 돈다(화면 단추 · HTTP 길 없음).
- 제안 · 결정 줄의 ``action`` · ``decided_action`` 칸(마이그레이션 ``brain_01``)이 여기 이름을 쓴다. 사람이 누르는 단추가
  아닌 이름(옮기기 ``import`` · 기간 끝남 ``expire`` · 다른 화면의 주간 고침 안 승인 ``weekly_fix``)은 :data:`SYSTEM_ACTIONS`,
  에이전트 길(새 항목 · 링크 제안)은
  :data:`AGENT_ACTIONS`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from foms.services.brain.constants import BULK_MAX, HUMAN_EDIT_FIELDS, KEY_RE, LAYERS, MAX_REASON, REJECT_CODES
from foms.services.brain.display import LAYER_LABELS, REJECT_LABELS
from foms.services.brain.errors import BrainShapeError

KINDS: tuple[str, ...] = ("key", "int", "int_or_null", "text", "choice", "fields", "confirm", "ids", "ms")


@dataclass(frozen=True)
class Param:
    """매개변수 하나 — 이름 · 꼴(:data:`KINDS`) · 화면 이름 · 꼭 있어야 함 · 고른 값."""

    name: str
    kind: str
    label: str
    required: bool = True
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionType:
    """액션 유형 하나."""

    name: str
    label: str
    summary: str
    stage: str  # propose · decide
    endpoint: str
    params: tuple[Param, ...]
    criteria: tuple[str, ...]
    failures: tuple[str, ...]
    done: str
    ui: bool = True
    phone: bool = False
    admin_only: bool = False


#: 실패 코드 → 화면 말(서비스 오류 ``code`` 와 같은 이름 — 오류 글은 이 말만 나간다).
FAILURES: dict[str, str] = {
    "BRAIN_FORBIDDEN": "찾을 수 없습니다.",
    "BRAIN_BASE_CHANGED": "제안을 만든 뒤 지식이 바뀌었어요 — 새로 불러온 뒤 다시 봐 주세요.",
    "BRAIN_CONFIRM": "등급 B 는 핵심 값 확인 칸을 눌러야 승인돼요.",
    "BRAIN_REJECTED_BEFORE": "같은 제안이 이미 거절됐어요 — 다시 올리지 않아요.",
    "BRAIN_OPEN_PROPOSAL": "이 지식에 승인을 기다리는 제안이 있어요 — '승인 대기'에서 먼저 정해 주세요.",
    "BRAIN_ROLLBACK_BLOCKED": "뒤 판이 같은 지식을 또 고쳐 판째 되돌릴 수 없어요 — 지식마다 되돌려 주세요.",
    "BRAIN_SHAPE": "값이 맞지 않아요 — 칸을 확인해 주세요.",
    "BRAIN_TARGET": "지금 상태와 맞지 않아요 — 이미 결정됐거나 바뀐 것이 없어요. 새로 불러와 주세요.",
    "BRAIN_GATE": "글 관문을 넘지 못했어요(개인정보 · 한자 · 숫자 출처).",
    "BRAIN_LINK_LIMIT": "이 종류 링크는 더 이을 수 없어요(연결 개수 상한) — 앞 링크를 먼저 빼 주세요.",
    "BRAIN_EXTERNAL_MISSING": "가리킨 계산기 · 설정 자리가 없거나 지금 확인할 수 없어요 — 키를 확인해 주세요.",
    "BRAIN_LINK_RULE": "이 링크는 이을 수 없어요(근거 종류와 맞지 않는 자리 · 필요와 제외를 함께 · 고리) — 앞 링크를 확인해 주세요.",
    "BRAIN_DOC_SYNC": "AI 상담이 읽는 지식 문서가 회사 지식과 달라서 넣지 않았어요 — 관리자에게 둘을 맞춰 달라고 알려 주세요.",
    "BRAIN_ERROR": "처리하지 못했어요 — 새로 불러온 뒤 다시 해 주세요.",
}
#: 사람이 누르는 단추가 아닌 이름 — 옮기기 · 기간 끝남(밤 단계) · 주간 고침 안 승인(그 화면 단추 — :mod:`.template_fix`).
SYSTEM_ACTIONS: tuple[str, ...] = ("import", "expire", "weekly_fix")
#: 에이전트 · 코드 길의 제안 이름(새 항목 · 링크 · 챗봇 틀림 신고 묶음 · 다시 배운 사진 교훈 카드 — 화면 단추 없음).
AGENT_ACTIONS: tuple[str, ...] = ("propose_create", "propose_link", "report_conflict", "photo_relearn")
#: 에이전트(모델)에게 도구로 내놓은 쓰기 액션 — 지금은 없다(읽기만 — 설계서 5절 · 10.1 '챗봇은 쓰지 않는다').
AGENT_EXPOSED_WRITES: tuple[str, ...] = ()

_KEY = Param("key", "key", "항목 키")
_BASE = Param("base_version", "int", "기준 판")
_REASON = Param("reason", "text", "까닭")
_CHANGE = Param("change_id", "int", "제안 번호")
_MS = Param("view_ms", "ms", "결정까지 걸린 밀리초", required=False)
_CONFIRM = Param("confirm", "confirm", "등급 B 핵심 값 확인", required=False)
_SEE = "볼 수 있는 항목(보기 범위)"
_DECIDE = ("결정 권한(층 승인자 · 사장님 몫 — D101)", _SEE, "열린 제안")
_PROPOSE_FAIL = ("BRAIN_FORBIDDEN", "BRAIN_SHAPE", "BRAIN_BASE_CHANGED", "BRAIN_REJECTED_BEFORE", "BRAIN_TARGET")
_DECIDE_FAIL = ("BRAIN_FORBIDDEN", "BRAIN_SHAPE", "BRAIN_TARGET", "BRAIN_BASE_CHANGED", "BRAIN_CONFIRM",
                "BRAIN_LINK_LIMIT", "BRAIN_EXTERNAL_MISSING",  # 링크 더하기 — 연결 개수 상한 · 바깥 정본 실재(D105)
                "BRAIN_DOC_SYNC")  # 지식 문서 유형 — 상담 지식 문서를 같이 다시 쓴다(7.5)
_PROPOSALS = "brain_review_api.brain_propose"

ACTIONS: dict[str, ActionType] = {a.name: a for a in (
    ActionType("propose_edit", "고칠 말 제안", "고칠 내용을 '승인 대기'에 올려요. 승인되면 바뀌어요.", "propose",
               _PROPOSALS, (_KEY, _BASE, Param("after", "fields", "고칠 칸"), _REASON),
               (_SEE, "기준 판 = 지금 판", "같은 제안이 거절된 적 없음", "속성 틀(7.7)"), _PROPOSE_FAIL,
               "'승인 대기'에 올렸어요."),
    ActionType("propose_retire", "은퇴 제안", "승인되면 AI 가 이 지식을 더는 쓰지 않아요.", "propose",
               _PROPOSALS, (_KEY, _BASE, _REASON), (_SEE, "기준 판 = 지금 판", "아직 은퇴 안 함"), _PROPOSE_FAIL,
               "'승인 대기'에 올렸어요."),
    ActionType("propose_delete", "지우기 제안", "승인되면 이 지식을 지워요(수정 기록은 남아요).", "propose",
               _PROPOSALS, (_KEY, _BASE, _REASON), (_SEE, "기준 판 = 지금 판"), _PROPOSE_FAIL, "'승인 대기'에 올렸어요."),
    ActionType("item_rollback", "이 버전으로 되돌리기 제안", "옛 판의 값을 새 제안으로 제안함에 넣는다(바로 바뀌지 않음).", "propose",
               _PROPOSALS, (_KEY, Param("to_version", "int", "되돌릴 판"), _REASON), (_SEE, "그 판을 볼 수 있음"),
               _PROPOSE_FAIL, "'승인 대기'에 올렸어요."),
    ActionType("apply", "승인", "제안을 그대로 넣는다(새 판).", "decide", "brain_review_api.brain_apply",
               (_CHANGE, Param("base_version", "int_or_null", "기준 판"), _CONFIRM, _MS),
               (*_DECIDE, "기준 판 = 지금 판", "등급 B 는 핵심 값 확인"), _DECIDE_FAIL, "승인했어요 — 이제 이 내용으로 써요.",
               phone=True),
    ActionType("edit_apply", "고쳐서 승인", "승인자가 '후' 값을 고친 뒤 넣는다(처음 값은 남는다).", "decide",
               "brain_review_api.brain_apply",
               (_CHANGE, Param("base_version", "int_or_null", "기준 판"), Param("edits", "fields", "고친 값"), _CONFIRM,
                _MS), (*_DECIDE, "기준 판 = 지금 판", "고친 값이 속성 틀에 맞음"), _DECIDE_FAIL,
               "고친 값으로 승인했어요."),
    ActionType("reject", "거절", "까닭 칩 하나로 거절한다(같은 제안이 다시 오지 않게 남김).", "decide",
               "brain_review_api.brain_reject",
               (_CHANGE, Param("code", "choice", "거절 까닭", choices=REJECT_CODES), _MS), _DECIDE,
               ("BRAIN_FORBIDDEN", "BRAIN_SHAPE", "BRAIN_TARGET"), "거절했어요 — 같은 제안은 다시 오지 않아요."),
    ActionType("bulk_apply", "한꺼번에 승인", "등급 A 제안, 또는 관리자의 이름표만 · 사본 링크만 제안을 한꺼번에 승인한다(D151).",
               "decide", "brain_review_api.brain_bulk_apply", (Param("ids", "ids", "제안 번호들"),),
               (*_DECIDE, "모두 등급 A 또는 (관리자 · 이름표만 · 사본 링크만)"), ("BRAIN_SHAPE",), "승인했어요."),
    ActionType("recheck", "아직 맞음", "확인 날 · 낡음 날만 오늘로 미는 제안을 만들어 곧바로 넣는다.", "decide",
               "brain_review_api.brain_recheck_confirm", (_KEY, Param("version", "int", "지금 판"), _MS),
               ("결정 권한", _SEE, "지금 판 = 화면 판", "열린 제안 없음"),
               ("BRAIN_FORBIDDEN", "BRAIN_BASE_CHANGED", "BRAIN_OPEN_PROPOSAL", "BRAIN_DOC_SYNC"),
               "확인했어요 — 다음 확인 날이 뒤로 밀렸어요.", phone=True),
    ActionType("release_rollback", "판 되돌리기", "한 판의 한 층을 그 판 앞으로 되돌린다(되돌린 판도 이력에 남음).", "decide",
               "brain_review_api.brain_release_rollback",
               (Param("number", "int", "판 번호"), Param("layer", "choice", "층", choices=LAYERS),
                Param("confirm_number", "int", "판 번호 확인")),
               ("사장님(ADMIN)만", "판 0 아님", "뒤 판이 같은 항목을 안 고침"),
               ("BRAIN_FORBIDDEN", "BRAIN_SHAPE", "BRAIN_TARGET", "BRAIN_ROLLBACK_BLOCKED", "BRAIN_LINK_LIMIT",
                "BRAIN_EXTERNAL_MISSING", "BRAIN_DOC_SYNC"),  # 뺀 링크를 다시 더할 때 — 연결 개수 상한 · 바깥 정본 실재(D105)
               "판을 되돌렸어요 — 되돌린 판도 이력에 남아요.", admin_only=True),
)}


#: 코드(에이전트) 길 액션 — 같은 꼴(이름 · 매개변수 · 조건 · 실패 말)로 선언한다. 사람 단추 목록(:data:`ACTIONS`)과 따로다.
AGENT_ACTION_TYPES: dict[str, ActionType] = {a.name: a for a in (
    ActionType("report_conflict", "틀림 신고 묶음",
               "챗봇 '틀림'이 같은 항목에 서로 다른 사람 둘 이상이면 승인자에게 엇갈림 항목 제안을 올린다(10.3).", "propose",
               "", (_KEY,),
               ("서로 다른 사람 2명 이상(지금 판에 대한 신고)", "그 신고로 연 엇갈림 제안이 없음", "관문 셋(7.7 · D105)"),
               ("BRAIN_TARGET", "BRAIN_GATE", "BRAIN_SHAPE"), "승인자 제안함에 올렸어요.", ui=False),
)}


def known_names() -> frozenset[str]:
    """제안 · 결정 줄의 액션 칸에 들어갈 수 있는 이름 모두."""
    return frozenset(ACTIONS) | frozenset(SYSTEM_ACTIONS) | frozenset(AGENT_ACTIONS)


def get(name: Any) -> ActionType:
    """이름 → 액션(모르는 이름은 꼴 오류)."""
    action = ACTIONS.get(name) if isinstance(name, str) else None
    if action is None:
        raise BrainShapeError([f"action: {' / '.join(ACTIONS)} 가운데 하나여야 한다"])
    return action


def _int(value: Any) -> bool:
    """정수인가(참 · 거짓 빼고)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _fields_ok(value: Any) -> bool:
    """고칠 칸 묶음 — 이름 · 글 · 유효 기간 또는 ``payload.<칸>``(종류별 틀은 서비스가 본다), 값은 글 · 수 · 목록 · 없음."""
    if not isinstance(value, dict) or not value or len(value) > 20:
        return False
    names_ok = all(isinstance(k, str) and (k in HUMAN_EDIT_FIELDS or (k.startswith("payload.") and 8 < len(k) <= 48))
                   for k in value)
    return names_ok and all(v is None or isinstance(v, (str, int, float, list)) for v in value.values())


def _ok(param: Param, value: Any) -> bool:
    """값 하나가 꼴에 맞나."""
    kind = param.kind
    checks = {
        "key": lambda v: isinstance(v, str) and bool(KEY_RE.fullmatch(v)),
        "int": _int,
        "int_or_null": lambda v: v is None or _int(v),
        "text": lambda v: isinstance(v, str) and bool(v.strip()) and len(v) <= MAX_REASON,
        "choice": lambda v: v in param.choices,
        "fields": _fields_ok,
        "confirm": lambda v: isinstance(v, dict) and isinstance(v.get("field"), str) and isinstance(v.get("value"), str),
        "ids": lambda v: isinstance(v, list) and 0 < len(v) <= BULK_MAX and all(_int(i) for i in v),
        "ms": lambda v: _int(v) and 0 <= v <= 86_400_000,
    }
    return checks[kind](value)


def parse(name: Any, body: Mapping[str, Any], *, agent: bool = False) -> tuple[ActionType, dict[str, Any]]:
    """본문을 그 액션의 매개변수로 검사한다 — 정한 칸만 · 꼴이 맞아야(틀리면 :class:`BrainShapeError`, 칸 이름만 싣는다).
    ``agent`` 면 코드 길 액션 목록(:data:`AGENT_ACTION_TYPES`)에서 찾는다."""
    if agent:
        action = AGENT_ACTION_TYPES.get(name) if isinstance(name, str) else None
        if action is None:
            raise BrainShapeError([f"action: {' / '.join(AGENT_ACTION_TYPES)} 가운데 하나여야 한다"])
    else:
        action = get(name)
    problems, out = [], {}
    for param in action.params:
        present = param.name in body and body[param.name] is not None
        if not present:
            if param.required and param.kind != "int_or_null":
                problems.append(f"{param.name}: 꼭 있어야 한다")
            out[param.name] = None
            continue
        if not _ok(param, body[param.name]):
            problems.append(f"{param.name}: {param.label} 꼴이 맞지 않는다")
            continue
        out[param.name] = body[param.name]
    if problems:
        raise BrainShapeError(problems)
    return action, out


def message(code: str) -> str:
    """실패 코드 → 화면 말."""
    return FAILURES.get(code, FAILURES["BRAIN_ERROR"])


def _param_spec(param: Param) -> dict[str, Any]:
    """매개변수 → 화면 · 도구 표(거절 칩은 이름까지)."""
    spec: dict[str, Any] = {"name": param.name, "kind": param.kind, "label": param.label, "required": param.required}
    if param.choices:
        labels = {"code": REJECT_LABELS, "layer": LAYER_LABELS}.get(param.name, {})
        spec["choices"] = [{"value": c, "label": labels.get(c, c)} for c in param.choices]
    if param.kind == "fields":
        spec["fields"] = list(HUMAN_EDIT_FIELDS) + ["payload.<속성 틀 칸>"]
    return spec


def specs(*, ui_only: bool = True) -> list[dict[str, Any]]:
    """화면에 싣는 액션 표(``data-actions``) — 이름 · 화면 이름 · 단계 · 매개변수 · 조건 · 실패 말 · 휴대폰 · 사장님만."""
    return [{"name": a.name, "label": a.label, "summary": a.summary, "stage": a.stage,
             "params": [_param_spec(p) for p in a.params], "criteria": list(a.criteria),
             "failures": {code: FAILURES[code] for code in a.failures}, "done": a.done, "phone": a.phone,
             "admin_only": a.admin_only} for a in ACTIONS.values() if a.ui or not ui_only]


_JSON_TYPES = {"key": {"type": "string"}, "int": {"type": "integer"}, "int_or_null": {"type": ["integer", "null"]},
               "text": {"type": "string", "maxLength": MAX_REASON}, "fields": {"type": "object"},
               "confirm": {"type": "object", "properties": {"field": {"type": "string"}, "value": {"type": "string"}}},
               "ids": {"type": "array", "items": {"type": "integer"}, "maxItems": BULK_MAX},
               "ms": {"type": "integer", "minimum": 0}}


def tool_specs(names: Optional[tuple[str, ...]] = None) -> list[dict[str, Any]]:
    """⑤-5 챗봇 · 에이전트 도구 목록 — 이름 · 설명(요약 + 제출 조건) · JSON Schema 입력."""
    tools = []
    for action in ACTIONS.values():
        if names is not None and action.name not in names:
            continue
        props = {p.name: ({"type": "string", "enum": list(p.choices)} if p.kind == "choice" else dict(_JSON_TYPES[p.kind]))
                 for p in action.params}
        tools.append({"name": "brain_" + action.name, "description": action.summary + " 조건: " + " · ".join(action.criteria),
                      "input_schema": {"type": "object", "properties": props, "additionalProperties": False,
                                       "required": [p.name for p in action.params if p.required]}})
    return tools
