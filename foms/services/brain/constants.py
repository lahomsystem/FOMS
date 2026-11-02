"""master brain 유형 · 층 · 링크 · 허용 짝 · 값 목록 — 설계서 2026-11-02-haud-master-brain 4절 · 5절 · 6절 · 3.1.

**유형(스키마)은 코드 + 설계서로만 바꾼다** — 화면에서 고치지 않는다(7.5 끝 · 유형 남발 막기). 허용 짝(어떤 유형 → 어떤 링크 →
어떤 유형)은 :data:`ALLOWED_LINKS` 하나이고 반영 동작(:mod:`.apply`)이 검사한다.

설계서와 다른 점(까닭은 보고 · 원장):

- ``fact``(사실) 유형을 공통 바탕에 둔다 — 지금 지식 문서의 종류 ``fact`` 를 옮길 자리. 제품 · 규격 · 용어로 나누는 일은
  설계서 11절 판 1 ② '공통 바탕 항목 정리(사장님 승인)'에서 제안으로 한다.
- 4절 링크 설명('규칙 → 제품 · 옵션' 같은 글)을 짝 표로 옮겼다. ``caused_by`` · ``fixed_by`` 는 판 3 유형(공정 · 불량)이
  아직 없어 짝이 0 이다.
- ``about``(에이전트 일 → 정체 항목) 링크를 더했다(전사 지식 온톨로지 점검 '지금 8' — 설계서 4절 9 종류 밖 열 번째).
"""

from __future__ import annotations

import re

from foms.services.cs_agent.knowledge_doc import (
    KIND_FACT, KIND_OWNER_DECISION, KIND_POLICY, KIND_PRICE_RULE, KIND_TEMPLATE, KNOWN_BRANDS,
)

# ── 브랜드 · 층 ──────────────────────────────────────────────────────────
BRAND_COMMON = "COMMON"
#: 브랜드 칸 값 — 채널 짝의 브랜드(라홈 · 하우드) + 공통(두 브랜드에 같은 사실 — 3.1 규칙 1 · D99).
BRANDS: tuple[str, ...] = (*sorted(KNOWN_BRANDS), BRAND_COMMON)

LAYER_COMMON, LAYER_CS, LAYER_DRAWING, LAYER_PRODUCTION = "common", "cs", "drawing", "production"
LAYERS: tuple[str, ...] = (LAYER_COMMON, LAYER_CS, LAYER_DRAWING, LAYER_PRODUCTION)

# ── 유형(판 1 · 2 — 4절) ─────────────────────────────────────────────────
COMMON_TYPES: tuple[str, ...] = (
    "brand", "product_line", "option", "spec", "build_rule", "policy", "price_rule", "owner_decision", "term", "fact",
)
CS_TYPES: tuple[str, ...] = ("situation", "template", "lesson", "tone", "image_read_rule")
DRAWING_TYPES: tuple[str, ...] = ("part_kind", "bom_rule", "drawing_rule")
OBSERVATION_TYPES: tuple[str, ...] = ("case", "image_read", "photo_observation")
AGENT_WORK_TYPES: tuple[str, ...] = ("conflict", "question")
#: 정체(제품 · 규칙 · 결정) 유형 — 관찰 · 에이전트 일과 나눈다(17.5 '정체성과 관찰 분리').
IDENTITY_TYPES: tuple[str, ...] = (*COMMON_TYPES, *CS_TYPES, *DRAWING_TYPES)
TYPES: tuple[str, ...] = (*IDENTITY_TYPES, *OBSERVATION_TYPES, *AGENT_WORK_TYPES)
#: 유형 → 들어갈 수 있는 층. 관찰 · 에이전트 일은 모든 층(층 표시 — 3.2 · 8절 '물어볼 것 한 곳').
TYPE_LAYERS: dict[str, frozenset[str]] = {
    **{t: frozenset({LAYER_COMMON}) for t in COMMON_TYPES},
    **{t: frozenset({LAYER_CS}) for t in CS_TYPES},
    **{t: frozenset({LAYER_DRAWING}) for t in DRAWING_TYPES},
    **{t: frozenset(LAYERS) for t in (*OBSERVATION_TYPES, *AGENT_WORK_TYPES)},
}

# ── 링크(9 종류 — 4절) · 허용 짝 ─────────────────────────────────────────
LINK_KINDS: tuple[str, ...] = (
    "applies_to", "requires", "excludes", "value_from", "copy_in", "supersedes", "evidence_of", "caused_by", "fixed_by",
    "about",
)
#: 바깥 정본 자리(``value_from`` 의 끝) — 키 머리 → 가짜 유형. brain 은 가리키기만 한다(값은 그 자리가 정본).
EXT_CALCULATOR, EXT_SETTING = "ext_calculator", "ext_setting"
EXTERNAL_PREFIXES: dict[str, str] = {"calc:": EXT_CALCULATOR, "setting:": EXT_SETTING}
_RULES_TO_PRODUCTS = frozenset({
    "spec", "build_rule", "policy", "price_rule", "image_read_rule", "drawing_rule", "bom_rule", "part_kind", "situation",
})
#: 링크 종류 → (시작 유형들, 끝 유형들). 설계서 4절 · 8절 글을 짝으로 옮긴 것.
ALLOWED_LINKS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    # 규칙 → 제품 · 옵션(4절) · 그림 조각 종류 → 제품 라인(8절 '어느 제품이 어느 조각을 만드나') · 상황 → 제품(17.5)
    "applies_to": (_RULES_TO_PRODUCTS, frozenset({"product_line", "option"})),
    # 제작 조건('ㄱ자는 여닫이만')
    "requires": (frozenset({"build_rule", "product_line", "option"}), frozenset({"product_line", "option", "spec"})),
    "excludes": (frozenset({"build_rule", "product_line", "option"}), frozenset({"product_line", "option", "spec"})),
    # 항목 → 정본 자리(계산기 id · SystemSetting 키 — 8절 자재표 규칙 키)
    "value_from": (frozenset({"product_line", "option", "spec", "price_rule", "bom_rule"}),
                   frozenset({EXT_CALCULATOR, EXT_SETTING})),
    # 정본 → brain 안 사본(기준 답 문구). 바깥 사본(매크로 · 스토어 상세)은 ``copies`` 칸(3.1 규칙 2).
    "copy_in": (frozenset(COMMON_TYPES), frozenset({"template"})),
    # 새 결정 → 앞 항목(3.1 규칙 5)
    "supersedes": (frozenset({"owner_decision"}), frozenset(IDENTITY_TYPES)),
    # 관찰 → 항목(관찰은 근거로만)
    "evidence_of": (frozenset(OBSERVATION_TYPES), frozenset(IDENTITY_TYPES)),
    # 판 3(불량 → 공정 → 고침) — 유형이 생길 때 짝을 넣는다
    "caused_by": (frozenset(), frozenset()),
    "fixed_by": (frozenset(), frozenset()),
    # 에이전트 일(엇갈림 · 물어볼 것) → 무엇에 대한 것인가(점검 '지금 8') — 열린 엇갈림이 그 항목을 '확인 필요'로 만든다
    "about": (frozenset(AGENT_WORK_TYPES), frozenset(IDENTITY_TYPES)),
}
#: 연결 개수 규칙(7.7 · D105) — (시작 유형, 링크 종류) → (최소, 최대). 그 항목에서 **나가는** 지금 · 유효 기간 안 링크 수.
#: 최대(``None`` = 끝없음)는 반영 동작이 링크 더하기 때 막고(:mod:`.apply`), 최소는 막지 않고 카드 '빠진 링크' · 품질 수
#: (:mod:`.quality`)로만 알린다. 적지 않은 짝은 (0, 끝없음). 기본값은 보고서에 적어 사장님께 여쭌다.
LINK_CARDINALITY: dict[tuple[str, str], tuple[int, int | None]] = {
    ("price_rule", "value_from"): (1, 1),  # 가격 규칙 값은 정본 자리 꼭 하나(계산기 · 설정 — 두 곳이면 어느 값인지 모른다)
    ("spec", "value_from"): (0, 1),  # 규격 값 정본은 하나까지
    ("option", "value_from"): (0, 1),  # 옵션 → 계산기 옵션 하나까지
    ("bom_rule", "value_from"): (1, 1),  # 자재표 규칙은 '가리키는 항목'(8절) — 설정 키 꼭 하나
    **{(t, "evidence_of"): (1, None) for t in OBSERVATION_TYPES},  # 관찰은 받치는 항목이 하나 이상(외톨이 관찰)
}

# ── 상태 · 확신 · 등급 · 근거 · 보기 범위 ────────────────────────────────
STATUS_DRAFT, STATUS_ACTIVE, STATUS_RETIRED = "draft", "active", "retired"
OBJECT_STATUSES: tuple[str, ...] = (STATUS_DRAFT, STATUS_ACTIVE, STATUS_RETIRED)
CONFIRMED, EVIDENCED, OBSERVED = "confirmed", "evidenced", "observed"
CONFIDENCES: tuple[str, ...] = (CONFIRMED, EVIDENCED, OBSERVED)
GRADE_A, GRADE_B_LIGHT, GRADE_B = "A", "B_LIGHT", "B"
GRADES: tuple[str, ...] = (GRADE_A, GRADE_B_LIGHT, GRADE_B)  # 뒤로 갈수록 무겁다(17.6 위험 등급)
#: 유형별 가장 가벼운 등급(17.6 표). 지우기 · 은퇴는 늘 B.
TYPE_GRADES: dict[str, str] = {
    **{t: GRADE_B_LIGHT for t in TYPES},
    **{t: GRADE_A for t in ("situation", "lesson", "tone", *AGENT_WORK_TYPES)},
    # 혼자 발송용 문구(지금 기준 답 문구가 3a 자동 답 재료) · 값 규칙 · 정책 · 사장님 결정
    **{t: GRADE_B for t in ("template", "policy", "price_rule", "owner_decision")},
}
EVIDENCE_IMPORT = "import"
EVIDENCE_KINDS: tuple[str, ...] = (EVIDENCE_IMPORT, "decision", "document", "case", "observation", "person")

SCOPE_ALL, SCOPE_PRICE, SCOPE_ADMIN, SCOPE_TEAM_PREFIX = "all", "price", "admin", "team:"
#: 팀 범위에 쓰는 팀(``User.team`` 정규화 값 — 설계서 2절 표).
TEAMS: tuple[str, ...] = ("CS", "SALES", "DRAWING", "PRODUCTION", "CONSTRUCTION", "SHIPMENT", "ACCOUNTING")
VISIBILITIES: tuple[str, ...] = (SCOPE_ALL, SCOPE_PRICE, SCOPE_ADMIN, *(SCOPE_TEAM_PREFIX + t for t in TEAMS))

# ── 제안 · 승인 ──────────────────────────────────────────────────────────
OP_CREATE, OP_UPDATE, OP_RETIRE, OP_DELETE = "create", "update", "retire", "delete"
OP_LINK_ADD, OP_LINK_REMOVE = "link_add", "link_remove"
OBJECT_OPS: tuple[str, ...] = (OP_CREATE, OP_UPDATE, OP_RETIRE, OP_DELETE)
LINK_OPS: tuple[str, ...] = (OP_LINK_ADD, OP_LINK_REMOVE)
CHANGE_OPEN, CHANGE_APPLIED, CHANGE_REJECTED, CHANGE_EXPIRED = "open", "applied", "rejected", "expired"
#: 거절 까닭 칩(7.5 승인 흐름 — 남겨서 같은 제안이 다시 오지 않게).
REJECT_CODES: tuple[str, ...] = ("wrong_number", "one_customer", "not_policy", "needs_photo", "other")
#: 사장님만 반영하는 유형(5절 — 가격 · 정책 · 사장님 결정). 공통 바탕 은퇴 · 지우기도 사장님만.
OWNER_ONLY_TYPES: frozenset[str] = frozenset({"price_rule", "policy", "owner_decision"})
#: 층 승인자 팀(5절 '그 층 승인자' · 사장님 D101 — 그 팀 팀장). 그 팀의 켜진 MANAGER 가 사장님 몫이 아닌 제안을 반영한다.
#: 공통 바탕은 승인자 팀이 없다(ADMIN 만).
LAYER_APPROVER_TEAMS: dict[str, str] = {LAYER_CS: "CS", LAYER_DRAWING: "DRAWING", LAYER_PRODUCTION: "PRODUCTION"}
#: 다시 확인 주기(7.5 '다시 확인' · 사장님 D103) — 가격 규칙 14일 · 제작 조건 · 정책 90일 · 도면 규칙 180일 · 용어 1년.
#: 없는 유형은 낡음 날을 두지 않는다.
STALE_DAYS: dict[str, int] = {"price_rule": 14, "build_rule": 90, "policy": 90, "drawing_rule": 180, "term": 365}
#: '다시 확인' 화면에 '다가오는' 항목으로 넣는 날 수(낡음 날이 오늘부터 이 안).
RECHECK_SOON_DAYS = 7

# ── 제안함 · 결정(7.5 승인 흐름 · 사장님 D103 — 13절 13 · 14) ───────────────
#: AI(에이전트) 제안은 한 주(한국 월요일 시작)에 **층마다** 이만큼만 제안함에 보인다(사장님 D106 — 회사 한 묶음이 아니라 공통 ·
#: 상담 · 도면 · 생산 층마다) — 쓰인 횟수 순. 그 주에 그 층에서 결정한 AI 제안 수만큼 줄어든다.
AI_WEEKLY_CAP = 20
#: AI 제안은 만든 뒤 이 날 수가 지나면 '기간 끝남'으로 저절로 닫힌다(사람 제안은 닫지 않는다).
AI_EXPIRE_DAYS = 28
#: 사람이 화면에서 고칠 말을 제안할 수 있는 칸(정체 · 보기 범위 · 실음 칸은 설계서 · 코드 길로만).
HUMAN_EDIT_FIELDS: tuple[str, ...] = ("name", "text", "valid_from", "valid_to")
#: 한꺼번에 넣기 상한(등급 A 만).
BULK_MAX = 50
#: 결정 시간 측정 — 카드를 보인 뒤 이 밀리초 안에 누르면 '5초 안 누름'으로 센다(7.5 '잘 도는지 숫자로').
FAST_DECISION_MS = 5000
#: 등급 B '핵심 값 하나 직접 확인'에서 고를 칸 차례(바뀐 칸 가운데 앞의 것).
KEY_FIELD_ORDER: tuple[str, ...] = (
    "text", "name", "valid_to", "valid_from", "status", "visibility", "checked_at", "copies", "confidence",
    "risk_grade", "evidence_ref", "evidence_kind", "payload",
)

# ── 지식 문서(상담 두뇌) ↔ 유형 ──────────────────────────────────────────
#: 지식 문서 종류 → brain 유형 · 층. 다시 만들기는 이 짝을 거꾸로 쓴다.
KIND_TYPES: dict[str, tuple[str, str]] = {
    KIND_TEMPLATE: ("template", LAYER_CS),
    KIND_FACT: ("fact", LAYER_COMMON),
    KIND_POLICY: ("policy", LAYER_COMMON),
    KIND_PRICE_RULE: ("price_rule", LAYER_COMMON),
    KIND_OWNER_DECISION: ("owner_decision", LAYER_COMMON),
}
TYPE_KINDS: dict[str, str] = {item_type: kind for kind, (item_type, _layer) in KIND_TYPES.items()}
DOC_TYPES: tuple[str, ...] = tuple(TYPE_KINDS)

# ── 꼴 상한 ──────────────────────────────────────────────────────────────
KEY_RE = re.compile(r"[a-z0-9][a-z0-9_.:/-]{0,119}")
MAX_NAME, MAX_TEXT, MAX_REASON, MAX_REF, MAX_COPIES, MAX_EVIDENCE = 200, 2000, 500, 200, 50, 50
MAX_PAYLOAD_CHARS = 20000
MAX_NEIGHBOUR_DEPTH, MAX_NEIGHBOUR_LIMIT, MAX_SEARCH_LIMIT = 2, 200, 100
#: 이웃 지도 · 뇌 보기 — 한 번에 싣는 선 상한 · 뇌 보기 바탕 점 상한(흐린 전체 그림 — 자리만).
MAX_NEIGHBOUR_EDGES, MAX_BRAIN_POINTS = 1000, 5000


def cardinality(from_type: str | None, kind: str) -> tuple[int, int | None]:
    """(시작 유형, 링크 종류)의 연결 개수 규칙 — (최소, 최대). 적지 않은 짝은 (0, ``None``)."""
    return LINK_CARDINALITY.get((from_type or "", kind), (0, None))


def external_type(key: str) -> str | None:
    """바깥 정본 자리 키(``calc:`` · ``setting:``)면 그 가짜 유형, 아니면 ``None``."""
    return next((kind for prefix, kind in EXTERNAL_PREFIXES.items() if key.startswith(prefix)), None)


def link_allowed(from_type: str, kind: str, to_type: str) -> bool:
    """(시작 유형, 링크 종류, 끝 유형) 짝이 허용 표에 있나."""
    pair = ALLOWED_LINKS.get(kind)
    return pair is not None and from_type in pair[0] and to_type in pair[1]


def heavier_grade(*grades: str) -> str:
    """가장 무거운 등급(A < B_LIGHT < B)."""
    return max(grades, key=GRADES.index)
