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
    AGENT_WORK_TYPES, BRAND_COMMON, COMMON_TYPES, CS_TYPES, DRAWING_TYPES, EXT_CALCULATOR, EXT_SETTING, LINK_KINDS,
    OBSERVATION_TYPES, SCOPE_ADMIN, SCOPE_ALL, SCOPE_PRICE, SCOPE_TEAM_PREFIX, TEAMS, TYPES,
)
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
    # 상담 층 — 초록
    "situation": ("상황", "#15803d", "fa-comments"),
    "template": ("기준 답 문구", "#166534", "fa-comment-dots"),
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
}

#: 유형 묶음(유형 지도의 층층 · 목록 차례). (키, 이름, 유형들)
TYPE_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("common", "공통 바탕", COMMON_TYPES),
    ("cs", "상담 층", CS_TYPES),
    ("drawing", "도면 층", DRAWING_TYPES),
    ("observation", "관찰", OBSERVATION_TYPES),
    ("agent_work", "에이전트 일", AGENT_WORK_TYPES),
    ("external", "바깥 정본(가리키기만)", (EXT_CALCULATOR, EXT_SETTING)),
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
}

LAYER_LABELS: dict[str, str] = {"common": "공통 바탕", "cs": "상담", "drawing": "도면", "production": "생산"}
BRAND_LABELS: dict[str, str] = {"LAHOM": "라홈", "HAUD": "하우드", BRAND_COMMON: "공통"}
STATUS_LABELS: dict[str, str] = {"draft": "초안", "active": "반영", "retired": "은퇴"}
CONFIDENCE_LABELS: dict[str, str] = {"confirmed": "확정", "evidenced": "근거 있음", "observed": "관찰"}
GRADE_LABELS: dict[str, str] = {"A": "A", "B_LIGHT": "B 가벼움", "B": "B"}
EVIDENCE_LABELS: dict[str, str] = {"import": "지식 문서에서 옮김", "decision": "사장님 결정", "document": "문서",
                                   "case": "사례", "observation": "관찰", "person": "사람 확인"}
OP_LABELS: dict[str, str] = {"create": "새로 만듦", "update": "고침", "retire": "은퇴", "delete": "지움",
                             "link_add": "링크 더함", "link_remove": "링크 뺌"}
#: 값 칸 이름(이력 탭의 '바뀐 칸').
FIELD_LABELS: dict[str, str] = {
    "name": "이름", "text": "글", "status": "상태", "confidence": "확신", "risk_grade": "위험 등급", "valid_from": "유효 시작",
    "valid_to": "유효 끝", "checked_at": "마지막 확인", "evidence_kind": "근거 종류", "evidence_ref": "근거 위치",
    "visibility": "보기 범위", "copies": "사본 목록", "payload": "실음 칸",
}
#: 관문 이름 · 결과 이름(제안 카드 — 6절 다섯 관문 중 지금 도는 것과 아직 안 도는 것).
GATE_LABELS: dict[str, str] = {"form": "꼴", "mask": "가림(개인정보 0)", "hanja": "한자 0", "numbers": "숫자 출처",
                               "conflict": "승인 지식과 부딪침", "evidence": "근거 수", "eval": "평가 묶음 재시험"}
GATE_VALUE_LABELS: dict[str, str] = {"pass": "통과", "fail": "안 됨", "not_run": "아직 안 돌림", "unavailable": "준비 안 됨",
                                     "skipped": "해당 없음"}
#: 거절 까닭 칩(7.5 — 남겨서 같은 제안이 다시 오지 않게). 차례 = 화면 차례.
REJECT_LABELS: dict[str, str] = {"wrong_number": "숫자 틀림", "one_customer": "한 손님 일", "not_policy": "정책 아님",
                                 "needs_photo": "사진 필요", "other": "그 밖"}
#: 유형별 '승인의 뜻' 한 줄(7.5 — 승인 = 명백한 문제 없음 확인, 위키백과 pending changes 꼴). 동작 줄 뒤에 붙는다.
OP_MEANING: dict[str, str] = {
    "create": "넣으면 새 항목이 생기고 에이전트 · 직원이 이 값을 읽기 시작해요.",
    "update": "넣으면 이 항목의 새 판이 되고, 앞 판은 이력에 남아요.",
    "retire": "넣으면 항목이 은퇴해 에이전트가 더는 쓰지 않아요(이력은 남아요).",
    "delete": "넣으면 지금 판이 닫히고 이 항목에 이어진 링크도 닫혀요(이력은 남아요).",
    "link_add": "넣으면 두 항목이 이 종류로 이어져요.",
    "link_remove": "넣으면 두 항목의 이음이 끊겨요(이력은 남아요).",
}
TYPE_MEANING: dict[str, str] = {
    "price_rule": "가격 규칙이라 손님에게 가는 금액이 바뀔 수 있어요 — 숫자를 직접 확인해 주세요.",
    "policy": "정책이라 상담 · 도면 · 생산이 모두 따라요.",
    "owner_decision": "사장님 결정 항목이에요.",
    "template": "기준 답 문구라 에이전트가 손님에게 그대로 보낼 수 있는 글이에요.",
    "drawing_rule": "도면 규칙이라 도면팀 · AI 도면팀원이 따라요.",
}
APPROVAL_NOTE = "승인은 '명백한 문제가 없다'는 확인이에요."


def approval_meaning(op: str, item_type: str | None) -> str:
    """제안 카드의 '승인의 뜻' 한 줄 — 동작 줄 + 유형 줄(있으면) + 승인 뜻."""
    parts = [OP_MEANING.get(op, ""), TYPE_MEANING.get(item_type or "", ""), APPROVAL_NOTE]
    return " ".join(part for part in parts if part)


#: 지식 표 정렬 · 확인 거르기 이름.
SORT_LABELS: dict[str, str] = {"usage": "쓰인 횟수 많은 순", "checked": "오래 확인 안 한 순", "name": "이름 순"}
CHECK_LABELS: dict[str, str] = {"needs_check": "확인 필요(열린 제안)", "stale": "낡음(확인 날 지남)"}


def visibility_label(value: str) -> str:
    """보기 범위 값 → 화면 이름."""
    if value == SCOPE_ALL:
        return "내부 모두"
    if value == SCOPE_PRICE:
        return "가격 재량(사장님 · 관리자)"
    if value == SCOPE_ADMIN:
        return "관리(관리자만)"
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
    }
