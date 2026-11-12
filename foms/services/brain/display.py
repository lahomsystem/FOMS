"""회사 지식 화면 표시 표 — **유형마다 색 · 아이콘 · 이름 하나**를 모든 화면이 같이 쓴다(설계서 7.5 원칙 · 7.6 '링크 종류마다 색').

- 색은 이 표가 정본이다. 그림(유형 지도 캔버스)은 이 값을 그대로 받고, HTML 칩은 같은 값을 담은 CSS 클래스
  (``static/css/contexts/brain/brain.css`` 의 ``.brain-type--<유형>``)를 쓴다 — 시험이 둘을 견준다.
- 상태는 색이 아니라 **모양**으로 보인다(은퇴 = 회색 · 초안 = 점선 · 낡음 = 주황 테두리). 그래서 유형 색에는 회색 · 주황을 쓰지
  않는다.
- 유형 · 링크 종류 자체는 :mod:`.constants` 가 정본이다(화면에서 고치지 않는다). 여기는 이름 · 색 · 아이콘만.
"""

from __future__ import annotations

from typing import Any

from foms.services.brain.constants import (
    AGENT_WORK_TYPES, BRAND_COMMON, CANON_EXTERNAL_TYPES, COMMON_TYPES, COPY_EXTERNAL_TYPES, CS_TYPES, DRAWING_TYPES,
    EXT_CALCULATOR, EXT_ERP_STAGE, EXT_FORM, EXT_MACRO, EXT_SCREEN, EXT_SETTING, EXT_STORE, LINK_KINDS,
    OBSERVATION_TYPES, SCOPE_ADMIN, SCOPE_ALL, SCOPE_PRICE, SCOPE_TEAM_PREFIX, TEAMS, TYPES,
)
from foms.services.brain.schemas import CHOICE_LABELS
from foms.services.orders.team_labels import team_label

#: 유형 → (이름, 색, Font Awesome 6 아이콘). 바깥 정본 자리(계산기 · 설정)는 brain 항목이 아니라 가리키기만 한다.
TYPE_DISPLAY: dict[str, tuple[str, str, str]] = {
    # 공통 바탕 — 파랑 · 남색 · 청록 · 갈색 · 자주
    "brand": ("브랜드", "#1e3a8a", "fa-tag"),
    "product_line": ("제품 라인", "#1d4ed8", "fa-couch"),
    "option": ("옵션", "#0369a1", "fa-sliders"),
    "spec": ("규격", "#0e7490", "fa-ruler-combined"),
    "build_rule": ("제작 조건", "#0f766e", "fa-screwdriver-wrench"),
    "policy": ("정책", "#4338ca", "fa-gavel"),
    "price_rule": ("가격 규칙", "#854d0e", "fa-won-sign"),
    "owner_decision": ("사장님 결정", "#9f1239", "fa-stamp"),
    "term": ("용어", "#3730a3", "fa-book"),
    "fact": ("사실", "#155e75", "fa-circle-info"),
    "process_step": ("공정 단계", "#0c4a6e", "fa-list-check"),
    # 상담 층 — 초록
    "situation": ("상황", "#15803d", "fa-comments"),
    "template": ("상용구", "#166534", "fa-comment-dots"),
    "lesson": ("배운 점", "#4d7c0f", "fa-lightbulb"),
    "tone": ("말투 규칙", "#3f6212", "fa-microphone"),
    "image_read_rule": ("그림 읽기 규칙", "#047857", "fa-image"),
    # 도면 층 — 보라
    "part_kind": ("그림 조각 종류", "#7e22ce", "fa-puzzle-piece"),
    "bom_rule": ("자재표 규칙", "#6d28d9", "fa-list-ol"),
    "drawing_rule": ("도면 규칙", "#a21caf", "fa-compass-drafting"),
    # 관찰 — 분홍 계열
    "case": ("사례", "#9d174d", "fa-folder-open"),
    "image_read": ("그림 읽기 결과", "#be185d", "fa-eye"),
    "photo_observation": ("사진 관찰", "#831843", "fa-camera"),
    # 에이전트 일 — 빨강
    "conflict": ("엇갈림", "#b91c1c", "fa-triangle-exclamation"),
    "question": ("물어볼 것", "#991b1b", "fa-circle-question"),
    # 바깥 정본 자리(가리키기만 — 값은 그 자리가 정본)
    EXT_CALCULATOR: ("견적 계산기", "#1f2937", "fa-calculator"),
    EXT_SETTING: ("설정 값", "#312e81", "fa-gear"),
    EXT_ERP_STAGE: ("ERP 단계", "#134e4a", "fa-diagram-project"),
    # 바깥 사본 자리(정본 값을 베껴 둔 바깥 글 — 7.8 다음 6. 글 지문 · 확인 날로 점검만)
    EXT_MACRO: ("매크로(사본)", "#5b21b6", "fa-comment-medical"),
    EXT_STORE: ("스토어 상세(사본)", "#6b21a8", "fa-store"),
    EXT_SCREEN: ("화면(사본)", "#4c1d95", "fa-display"),
    EXT_FORM: ("양식(사본)", "#581c87", "fa-file-lines"),
}

#: 유형 묶음(유형 지도의 층층 · 목록 차례). (키, 이름, 유형들)
TYPE_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("common", "공통 바탕", COMMON_TYPES),
    ("cs", "상담 층", CS_TYPES),
    ("drawing", "도면 층", DRAWING_TYPES),
    ("observation", "관찰", OBSERVATION_TYPES),
    ("agent_work", "에이전트 일", AGENT_WORK_TYPES),
    ("external", "바깥 정본(가리키기만)", CANON_EXTERNAL_TYPES),
    ("external_copy", "바깥 사본(점검만)", COPY_EXTERNAL_TYPES),
)

#: 링크 종류 → (짧은 이름, 색, 나가는 쪽 이름, 들어오는 쪽 이름). 카드는 방향마다 따로 묶는다.
LINK_DISPLAY: dict[str, tuple[str, str, str, str]] = {
    "applies_to": ("적용", "#2563eb", "적용 대상", "적용되는 규칙"),
    "requires": ("필요", "#0d9488", "필요한 것", "이것을 필요로 함"),
    "excludes": ("제외", "#dc2626", "함께 못 하는 것", "이것과 함께 못 함"),
    "value_from": ("값 정본", "#1f2937", "값 정본 자리", "값을 가져가는 항목"),
    "copy_in": ("사본", "#7c3aed", "사본", "정본"),
    "supersedes": ("대체", "#9f1239", "대체한 앞 항목", "대체한 결정"),
    "evidence_of": ("근거", "#be185d", "근거로 받친 항목", "근거 관찰"),
    "caused_by": ("원인", "#92400e", "원인", "결과"),
    "fixed_by": ("고침", "#166534", "고친 방법", "고친 대상"),
    "about": ("대한 것", "#b45309", "무엇에 대한 것", "이 항목에 대한 엇갈림 · 물어볼 것"),
    "decided_by": ("정한 결정", "#e11d48", "정한 사장님 결정", "이 결정이 정한 항목"),
    "at_step": ("공정 단계", "#0891b2", "걸린 공정 단계", "이 단계에 걸린 항목"),
    "uses": ("씀", "#0284c7", "쓰는 공통 바탕", "이것을 쓰는 항목"),
    "answers": ("답함", "#16a34a", "답하는 상황", "이 상황의 기준 답"),
    "refines": ("다듬음", "#65a30d", "다듬은 것", "다듬은 배운 점"),
    "broader": ("위 항목", "#6366f1", "위(넓은) 항목", "아래(좁은) 항목"),
    "part_of": ("들어감", "#9333ea", "들어가는 제품 라인", "이 제품의 그림 조각 종류"),
}

LAYER_LABELS: dict[str, str] = {"common": "공통 바탕", "cs": "상담", "drawing": "도면", "production": "생산"}
BRAND_LABELS: dict[str, str] = {"LAHOM": "라홈", "HAUD": "하우드", BRAND_COMMON: "공통"}
STATUS_LABELS: dict[str, str] = {"draft": "초안", "active": "사용 중", "retired": "은퇴"}
CONFIDENCE_LABELS: dict[str, str] = {"confirmed": "확정", "evidenced": "근거 있음", "observed": "관찰"}
GRADE_LABELS: dict[str, str] = {"A": "A", "B_LIGHT": "B(가벼움)", "B": "B"}
EVIDENCE_LABELS: dict[str, str] = {"import": "지식 문서에서 옮김", "decision": "사장님 결정", "document": "문서",
                                   "case": "사례", "observation": "관찰", "person": "사람 확인"}
OP_LABELS: dict[str, str] = {"create": "새로 만듦", "update": "고침", "retire": "은퇴", "delete": "지움",
                             "link_add": "연결 더함", "link_remove": "연결 뺌"}
#: 에이전트 이름(``agent:<이름>`` — 만든 이 · 제안한 이) → 화면 이름(점검 F13 — 코드 이름을 보이지 않는다). 모르는 이름은
#: :data:`AGENT_FALLBACK`. 이름 정본은 :data:`foms.services.brain.photo_cards.AGENT` · ``chat_reports.CHAT_AGENT`` ·
#: ``foms.services.cs_agent.handoff_learning_gates.AGENT``(시험이 맞춘다).
AGENT_LABELS: dict[str, str] = {"cs_photo": "AI(사진 다시 배우기)", "brain_chat": "AI(물어보기 틀림 신고)",
                                "cs_handoff_learning": "AI(넘긴 상담 배우기)"}
AGENT_FALLBACK = "AI"
#: 값 칸 이름(이력 탭의 '바뀐 칸').
FIELD_LABELS: dict[str, str] = {
    "name": "이름", "text": "글", "status": "상태", "confidence": "확실한 정도", "risk_grade": "위험 등급", "valid_from": "유효 시작",
    "valid_to": "유효 끝", "checked_at": "마지막 확인", "evidence_kind": "근거 종류", "evidence_ref": "근거 위치",
    "visibility": "보기 범위", "copies": "사본 목록", "payload": "세부 칸",
}
#: 관문 이름 · 결과 이름(제안 카드 — 6절 다섯 관문 중 지금 도는 것과 아직 안 도는 것).
GATE_LABELS: dict[str, str] = {"form": "꼴", "mask": "가림(개인정보 0)", "hanja": "한자 0", "numbers": "숫자 출처",
                               "conflict": "승인 지식과 부딪침", "evidence": "근거 수", "eval": "평가 묶음 재시험"}
GATE_VALUE_LABELS: dict[str, str] = {"pass": "통과", "fail": "안 됨", "not_run": "아직 안 돌림", "unavailable": "준비 안 됨",
                                     "skipped": "해당 없음"}
#: 거절 까닭 칩(7.5 — 남겨서 같은 제안이 다시 오지 않게). 차례 = 화면 차례.
REJECT_LABELS: dict[str, str] = {"knowledge_right": "회사 지식이 맞음 — 바깥 글 고칠 일",
                                 "outside_right": "바깥 글이 맞음 — 회사 지식 고침",
                                 "both_right": "둘 다 맞음 — 경우를 적음",
                                 "wrong_number": "숫자 틀림", "one_customer": "한 손님 일", "not_policy": "정책 아님",
                                 "needs_photo": "사진 필요", "other": "그 밖"}
#: 유형별 '승인의 뜻' 한 줄(7.5 — 승인 = 명백한 문제 없음 확인, 위키백과 pending changes 꼴). 동작 줄 뒤에 붙는다.
OP_MEANING: dict[str, str] = {
    "create": "승인하면 새 지식이 생기고 AI · 직원이 이 내용을 쓰기 시작해요.",
    "update": "승인하면 이 지식이 바뀌고, 바뀌기 전 내용은 수정 기록에 남아요.",
    "retire": "승인하면 AI 가 이 지식을 더는 쓰지 않아요(수정 기록은 남아요).",
    "delete": "승인하면 이 지식과 이어진 연결이 닫혀요(수정 기록은 남아요).",
    "link_add": "승인하면 두 지식이 이어져요.",
    "link_remove": "승인하면 두 지식의 연결이 끊겨요(수정 기록은 남아요).",
}
#: 묶음 ① · ④ 는 글 · 금액이 안 바뀐다(설계서 7.9) — 유형 경고(가격 '금액이 바뀔 수 있어요' 등) 대신 이 한 줄.
BIN_MEANING: dict[str, str] = {
    "names": "이름 · 비슷한 말만 바뀌어요. 글 · 금액은 그대로예요.",
    "mark": "표시만 해요. 글 · 금액은 그대로예요.",
    "calc": "견적 계산기 제품 · 옵션이에요. 금액은 계산기를 가리키기만 해요.",
    "rules": "규칙과 제품 · 옵션을 잇기만 해요. 글 · 금액은 그대로예요.",
}
TYPE_MEANING: dict[str, str] = {
    "price_rule": "손님에게 가는 금액이 바뀔 수 있어요. 숫자를 확인해 주세요.",
    "policy": "상담 · 도면 · 생산이 모두 따르는 정책이에요.",
    "template": "손님에게 그대로 나가는 글이에요.",
    "drawing_rule": "도면팀 · AI 도면팀원이 따라요.",
}
APPROVAL_NOTE = "승인은 '명백한 문제가 없다'는 확인이에요."
#: '승인 대기' 위에 한 번만 — 카드마다 되풀이하지 않는다(사장님 11-04 "반복되는 말이 너무 많아").
INBOX_NOTE = "승인하면 바로 반영되고, 바뀌기 전 내용은 수정 기록에 남아요. 승인 전에는 아무것도 바뀌지 않아요."


def approval_meaning(op: str, item_type: str | None, bin_name: str | None = None) -> str:
    """제안 카드의 주의 한 줄 — ① · ④ 묶음 줄, 아니면 유형 줄(가격 · 정책 · 상용구 · 도면 규칙), 없으면 빈 글.

    동작 줄(:data:`OP_MEANING`) · 승인 뜻(:data:`APPROVAL_NOTE`)은 모든 카드에 같아 '승인 대기' 위에 한 번만
    (:data:`INBOX_NOTE` — 사장님 11-04 "반복되는 말이 너무 많아")."""
    kind = BIN_MEANING.get(bin_name or "") or TYPE_MEANING.get(item_type or "", "")
    parts = [kind]
    return " ".join(part for part in parts if part)


#: 지식 표 정렬 · 확인 거르기 이름.
SORT_LABELS: dict[str, str] = {"usage": "쓰인 횟수 많은 순", "checked": "오래 확인 안 한 순", "name": "이름 순"}
CHECK_LABELS: dict[str, str] = {"needs_check": "승인 대기", "stale": "확인 날 지남"}


def visibility_label(value: str) -> str:
    """보기 범위 값 → 화면 이름."""
    if value == SCOPE_ALL:
        return "내부 모두"
    if value == SCOPE_PRICE:
        return "사장님 · 관리자"
    if value == SCOPE_ADMIN:
        return "관리자만"
    if value.startswith(SCOPE_TEAM_PREFIX):
        return team_label(value[len(SCOPE_TEAM_PREFIX):]) + "만"  # 팀 이름 정본 하나(team_labels.py)
    return value


def type_label(item_type: str) -> str:
    """유형 → 이름(모르는 유형은 키 그대로)."""
    return TYPE_DISPLAY.get(item_type, (item_type, "", ""))[0]


def display_table() -> dict[str, Any]:
    """화면 스크립트에 싣는 표 한 덩어리(``data-brain-display`` — JSON)."""
    return {
        "types": {t: {"label": label, "color": color, "icon": icon} for t, (label, color, icon) in TYPE_DISPLAY.items()},
        "type_order": list(TYPES),
        "groups": [{"key": key, "label": label, "types": list(types)} for key, label, types in TYPE_GROUPS],
        "links": {k: {"label": v[0], "color": v[1], "out": v[2], "in": v[3]} for k, v in LINK_DISPLAY.items()},
        "link_order": list(LINK_KINDS),
        "layers": LAYER_LABELS, "brands": BRAND_LABELS, "statuses": STATUS_LABELS, "confidences": CONFIDENCE_LABELS,
        "grades": GRADE_LABELS, "ops": OP_LABELS, "sorts": SORT_LABELS, "checks": CHECK_LABELS,
        "fields": FIELD_LABELS, "gates": GATE_LABELS, "gate_values": GATE_VALUE_LABELS, "rejects": REJECT_LABELS,
        "visibilities": {v: visibility_label(v) for v in (SCOPE_ALL, SCOPE_PRICE, SCOPE_ADMIN,
                                                           *(SCOPE_TEAM_PREFIX + t for t in TEAMS))},
        "choices": CHOICE_LABELS,  # 고르기 값 이름표(칸 자리 → 값 → 이름 — 고칠 말 · 승인 대기 칸 표 · 확인 칸)
    }


def agent_label(name: str) -> str:
    """에이전트 이름 → 화면 이름(모르면 'AI')."""
    return AGENT_LABELS.get(name, AGENT_FALLBACK)
