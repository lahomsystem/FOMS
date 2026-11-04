"""master brain 유형 · 층 · 링크 · 허용 짝 · 값 목록 — 설계서 2026-11-02-haud-master-brain 4절 · 5절 · 6절 · 3.1 · 7.8.

**유형(스키마)은 코드 + 설계서로만 바꾼다** — 화면에서 고치지 않는다(7.5 끝 · 유형 남발 막기). 허용 짝(어떤 유형 → 어떤 링크 →
어떤 유형)은 :data:`ALLOWED_LINKS` 하나(+ 좁힘 :data:`NARROW_ENDS` · :data:`SAME_TYPE_KINDS`)이고 반영 동작(:mod:`.apply`)이
검사한다. 항목 값에 따른 링크 제약(근거 종류 · 고리 · 맞서는 짝)은 :mod:`.link_rules`.

설계서와 다른 점(까닭은 보고 · 원장):

- ``fact``(사실) 유형을 공통 바탕에 둔다 — 지금 지식 문서의 종류 ``fact`` 를 옮길 자리. 제품 · 규격 · 용어로 나누는 일은
  설계서 11절 판 1 ② '공통 바탕 항목 정리(사장님 승인)'에서 제안으로 한다.
- 4절 링크 설명('규칙 → 제품 · 옵션' 같은 글)을 짝 표로 옮겼다. ``caused_by`` · ``fixed_by`` 는 판 3 유형(공정 · 불량)이
  아직 없어 짝이 0 이다.
- ``about``(에이전트 일 → 정체 항목) 링크를 더했다(전사 지식 온톨로지 점검 '지금 8' — 설계서 4절 9 종류 밖 열 번째).
- 7.8 온톨로지 바로잡기(⑤-6 · D115 ~ D126): 공정 단계 유형(``process_step``) · 링크 일곱(``decided_by`` · ``at_step`` ·
  ``uses`` · ``answers`` · ``refines`` · ``broader`` · ``part_of``) · 바깥 자리 다섯(ERP 단계 정본 + 사본 넷) · 근거 종류별 가격
  규칙 연결 개수(:func:`cardinality`) · 값 목록 검사 한 곳(:func:`value_problems`).
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from foms.services.cs_agent.knowledge_doc import (
    KIND_BUILD_RULE, KIND_FACT, KIND_OWNER_DECISION, KIND_POLICY, KIND_PRICE_RULE, KIND_TEMPLATE, KNOWN_BRANDS,
)

# ── 브랜드 · 층 ──────────────────────────────────────────────────────────
BRAND_COMMON = "COMMON"
#: 브랜드 칸 값 — 채널 짝의 브랜드(라홈 · 하우드) + 공통(두 브랜드에 같은 사실 — 3.1 규칙 1 · D99).
BRANDS: tuple[str, ...] = (*sorted(KNOWN_BRANDS), BRAND_COMMON)

LAYER_COMMON, LAYER_CS, LAYER_DRAWING, LAYER_PRODUCTION = "common", "cs", "drawing", "production"
LAYERS: tuple[str, ...] = (LAYER_COMMON, LAYER_CS, LAYER_DRAWING, LAYER_PRODUCTION)

# ── 유형(판 1 · 2 — 4절 · 7.8) ───────────────────────────────────────────
COMMON_TYPES: tuple[str, ...] = (
    "brand", "product_line", "option", "spec", "build_rule", "policy", "price_rule", "owner_decision", "term", "fact",
    "process_step",  # 공정 단계(7.8 다음 3 · D117 — ERP 주문 단계를 가리키고 정책 · 사실을 단계에 잇는다)
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

# ── 링크(4절 아홉 + about + 7.8 일곱) · 허용 짝 ─────────────────────────
LINK_KINDS: tuple[str, ...] = (
    "applies_to", "requires", "excludes", "value_from", "copy_in", "supersedes", "evidence_of", "caused_by", "fixed_by",
    "about", "decided_by", "at_step", "uses", "answers", "refines", "broader", "part_of",
)
#: 바깥 자리(brain 항목이 아니라 가리키기만 — 키 머리 → 가짜 유형). **정본 자리**(``value_from`` 의 끝 — 값은 그 자리가 정본)와
#: **사본 자리**(``copy_in`` 의 끝 — 정본 값을 베껴 둔 바깥 글: 매크로 · 스토어 상세 구획 · 화면 · 양식, 7.8 다음 6).
EXT_CALCULATOR, EXT_SETTING, EXT_ERP_STAGE = "ext_calculator", "ext_setting", "ext_erp_stage"
EXT_MACRO, EXT_STORE, EXT_SCREEN, EXT_FORM = "ext_macro", "ext_store", "ext_screen", "ext_form"
EXTERNAL_PREFIXES: dict[str, str] = {
    "calc:": EXT_CALCULATOR, "setting:": EXT_SETTING, "erp:stage/": EXT_ERP_STAGE,
    "macro:": EXT_MACRO, "store:": EXT_STORE, "screen:": EXT_SCREEN, "form:": EXT_FORM,
}
CANON_EXTERNAL_TYPES: tuple[str, ...] = (EXT_CALCULATOR, EXT_SETTING, EXT_ERP_STAGE)
COPY_EXTERNAL_TYPES: tuple[str, ...] = (EXT_MACRO, EXT_STORE, EXT_SCREEN, EXT_FORM)
EXTERNAL_TYPES: tuple[str, ...] = (*CANON_EXTERNAL_TYPES, *COPY_EXTERNAL_TYPES)
#: 바깥 자리 키 꼴(머리 포함) — ``#`` 뒤는 칸 · 구획. 계산기 · 설정은 실재 확인(:mod:`.external`)이 있어 넓게 두고, 사본 자리는
#: 있음을 확인할 길이 없어(매크로 · 스토어) 이 꼴만 본다. ERP 단계 값은 소문자로 적는다(키는 소문자 하나 — 정본 코드와는
#: 대문자로 바꿔 견준다. 대소문자가 다른 같은 단계 링크가 둘 생기지 않게).
EXTERNAL_KEY_PATTERNS: dict[str, re.Pattern[str]] = {
    EXT_CALCULATOR: re.compile(r"calc:[a-z0-9_.:/-]{1,110}"),
    EXT_SETTING: re.compile(r"setting:[a-z0-9_.-]{1,70}(?:#[a-z0-9_]{1,40})?"),
    EXT_ERP_STAGE: re.compile(r"erp:stage/[a-z_]{1,40}"),
    EXT_MACRO: re.compile(r"macro:[a-z0-9_-]{1,60}"),
    EXT_STORE: re.compile(r"store:[a-z0-9_.-]{1,60}#[a-z0-9_.-]{1,40}"),
    EXT_SCREEN: re.compile(r"screen:[a-z0-9_./-]{1,100}"),
    EXT_FORM: re.compile(r"form:[a-z0-9_.-]{1,60}"),
}
_RULES_TO_PRODUCTS = frozenset({
    "spec", "build_rule", "policy", "price_rule", "image_read_rule", "drawing_rule", "bom_rule", "situation",
})
#: 링크 종류 → (시작 유형들, 끝 유형들). 설계서 4절 · 8절 · 7.8 글을 짝으로 옮긴 것.
ALLOWED_LINKS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    # 규칙 → 제품 · 옵션(4절) · 상황 → 제품(17.5). 그림 조각 종류 → 제품 라인은 ``part_of`` 로 옮겼다(7.8 다음 5)
    "applies_to": (_RULES_TO_PRODUCTS, frozenset({"product_line", "option"})),
    # 제작 조건('ㄱ자는 여닫이만') — 같은 짝에 필요 + 제외를 함께 두지 않는다(:mod:`.link_rules`)
    "requires": (frozenset({"build_rule", "product_line", "option"}), frozenset({"product_line", "option", "spec"})),
    "excludes": (frozenset({"build_rule", "product_line", "option"}), frozenset({"product_line", "option", "spec"})),
    # 항목 → 정본 자리(계산기 id · SystemSetting 키(+ 칸) — 8절 자재표 규칙 키 · 공정 단계 → ERP 단계 정본)
    "value_from": (frozenset({"product_line", "option", "spec", "price_rule", "bom_rule", "process_step"}),
                   frozenset(CANON_EXTERNAL_TYPES)),
    # 정본 → 사본(brain 안 기준 답 문구 · 바깥 사본 자리 — 7.8 다음 6. 링크 실음 칸은 본 글 지문 · 확인 날만)
    "copy_in": (frozenset(COMMON_TYPES), frozenset({"template", *COPY_EXTERNAL_TYPES})),
    # 새 결정 → 앞 항목(3.1 규칙 5) — 반영하면 앞 항목의 유효 끝을 찍는다(7.8 다음 2), 고리 금지
    "supersedes": (frozenset({"owner_decision"}), frozenset(IDENTITY_TYPES)),
    # 관찰 → 항목(관찰은 근거로만)
    "evidence_of": (frozenset(OBSERVATION_TYPES), frozenset(IDENTITY_TYPES)),
    # 판 3(불량 → 공정 → 고침) — 유형이 생길 때 짝을 넣는다
    "caused_by": (frozenset(), frozenset()),
    "fixed_by": (frozenset(), frozenset()),
    # 에이전트 일(엇갈림 · 물어볼 것) → 무엇에 대한 것인가(점검 '지금 8') — 열린 엇갈림이 그 항목을 '확인 필요'로 만든다
    "about": (frozenset(AGENT_WORK_TYPES), frozenset(IDENTITY_TYPES)),
    # 정체 항목 → 그것을 정한 사장님 결정(7.8 다음 2)
    "decided_by": (frozenset(t for t in IDENTITY_TYPES if t != "owner_decision"), frozenset({"owner_decision"})),
    # 정책 · 사실 · 제작 조건 · 상황 · 기준 답 → 공정 단계(7.8 다음 3 · D117)
    "at_step": (frozenset({"policy", "fact", "build_rule", "situation", "template"}), frozenset({"process_step"})),
    # 상담 · 도면 층 항목 → 쓰는 공통 바탕(규격 · 정책 · 용어 · 제작 조건 — 7.8 다음 5)
    "uses": (frozenset({*CS_TYPES, *DRAWING_TYPES}), frozenset({"spec", "policy", "term", "build_rule"})),
    "answers": (frozenset({"template"}), frozenset({"situation"})),  # 기준 답 → 상황
    "refines": (frozenset({"lesson"}), frozenset({"situation", "template", "tone"})),  # 배운 점 → 다듬은 것
    # 좁은 항목 → 넓은 항목(같은 유형끼리 — SKOS ``broader`` 방향, 고리 금지)
    "broader": (frozenset(IDENTITY_TYPES), frozenset(IDENTITY_TYPES)),
    "part_of": (frozenset({"part_kind"}), frozenset({"product_line"})),  # 그림 조각 종류 → 제품 라인(8절)
}
#: 짝 표를 시작 유형마다 더 좁힘 — (시작 유형, 종류) → 받는 끝 유형. ERP 단계 정본은 공정 단계만 가리킨다.
NARROW_ENDS: dict[tuple[str, str], frozenset[str]] = {
    **{(t, "value_from"): frozenset({EXT_CALCULATOR, EXT_SETTING})
       for t in ("product_line", "option", "spec", "price_rule", "bom_rule")},
    ("process_step", "value_from"): frozenset({EXT_ERP_STAGE}),
}
#: 같은 유형끼리만 잇는 종류.
SAME_TYPE_KINDS: frozenset[str] = frozenset({"broader"})
#: 고리를 막는 종류 · 같은 두 항목 사이에 함께 두지 않는 종류 짝(7.8 다음 14 — :mod:`.link_rules`).
ACYCLIC_KINDS: frozenset[str] = frozenset({"supersedes", "broader"})
OPPOSED_KINDS: dict[str, str] = {"requires": "excludes", "excludes": "requires"}
#: 연결 개수 규칙(7.7 · D105) — (시작 유형, 링크 종류) → (최소, 최대). 그 항목에서 **나가는** 지금 · 유효 기간 안 링크 수.
#: 최대(``None`` = 끝없음)는 반영 동작이 링크 더하기 때 막고(:mod:`.apply`), 최소는 막지 않고 카드 '빠진 링크' · 품질 수
#: (:mod:`.quality`)로만 알린다. 적지 않은 짝은 (0, 끝없음). **가격 규칙 → 정본 자리는 근거 종류로 갈린다**(:data:`BASIS_RULES`).
LINK_CARDINALITY: dict[tuple[str, str], tuple[int, int | None]] = {
    ("spec", "value_from"): (0, 1),  # 규격 값 정본은 하나까지
    ("option", "value_from"): (0, 1),  # 옵션 → 계산기 옵션 하나까지
    ("bom_rule", "value_from"): (1, 1),  # 자재표 규칙은 '가리키는 항목'(8절) — 설정 키 꼭 하나
    ("process_step", "value_from"): (0, 1),  # 공정 단계 → ERP 단계 정본 하나까지(7.8 다음 3)
    **{(t, "evidence_of"): (1, None) for t in OBSERVATION_TYPES},  # 관찰은 받치는 항목이 하나 이상(외톨이 관찰)
}
#: 가격 규칙 근거 종류(``payload.basis`` — 7.8 다음 1 · 사장님 D115) → (최소, 최대, 받는 끝 유형): 계산기 값 · 회사 지식 정본
#: (운임 등 — 연결 없음) · 두 값의 차이 · 설정 값.
PRICE_RULE_TYPE, BASIS_FIELD = "price_rule", "basis"
BASIS_RULES: dict[str, tuple[int, int, tuple[str, ...]]] = {
    "calc": (1, 1, (EXT_CALCULATOR,)),
    "brain": (0, 0, ()),
    "derived": (2, 2, (EXT_CALCULATOR, EXT_SETTING)),
    "setting": (1, 1, (EXT_SETTING,)),
}
PRICE_BASES: tuple[str, ...] = tuple(BASIS_RULES)
#: 근거 종류가 빈 옛 가격 규칙 — 최소는 따지지 않고(카드 '근거 종류 비었음'), 최대 · 끝은 예전 그대로(정본 자리 하나).
BASIS_EMPTY_RULE: tuple[int, int, tuple[str, ...]] = (0, 1, (EXT_CALCULATOR, EXT_SETTING))

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
REJECT_CODES: tuple[str, ...] = ("wrong_number", "one_customer", "not_policy", "needs_photo", "other",
                                 *("knowledge_right", "outside_right", "both_right"))
#: ③ 질문 카드 답(설계서 7.9 · D152) — 엇갈림 · 질문 제안을 닫는 까닭. 보통 거절 칩에는 안 보인다.
ANSWER_CODES: tuple[str, ...] = ("knowledge_right", "outside_right", "both_right")
#: 사장님만 반영하는 유형(5절 — 가격 · 정책 · 사장님 결정). 공통 바탕 은퇴 · 지우기도 사장님만.
OWNER_ONLY_TYPES: frozenset[str] = frozenset({"price_rule", "policy", "owner_decision"})
#: 층 승인자 팀(5절 '그 층 승인자' · 사장님 D101 — 그 팀 팀장). 그 팀의 켜진 MANAGER 가 사장님 몫이 아닌 제안을 반영한다.
#: 공통 바탕은 승인자 팀이 없다(ADMIN 만).
LAYER_APPROVER_TEAMS: dict[str, str] = {LAYER_CS: "CS", LAYER_DRAWING: "DRAWING", LAYER_PRODUCTION: "PRODUCTION"}
#: 이름표 칸만 바뀌는 고침(승인 대기 ①)을 층 · 유형과 상관없이 결정하는 팀의 MANAGER(사장님 D167 — 상담팀장).
NAME_APPROVER_TEAM = "CS"
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
    KIND_BUILD_RULE: ("build_rule", LAYER_COMMON),  # 7.8 다음 9 — 상담 견적 검사가 지식 문서의 제작 조건을 읽는다
}
TYPE_KINDS: dict[str, str] = {item_type: kind for kind, (item_type, _layer) in KIND_TYPES.items()}
DOC_TYPES: tuple[str, ...] = tuple(TYPE_KINDS)
#: 지식 문서 항목일 수도, brain 만의 항목일 수도 있는 유형 — 실음 칸에 ``doc_id`` 가 있을 때만 지식 문서 항목(다시 만들기 ·
#: 옮기기 · 문서 꼴 검사 대상). 제작 조건은 링크로 제품을 묶는 brain 항목이 먼저 있었다(7.8 다음 9).
OPTIONAL_DOC_TYPES: frozenset[str] = frozenset({"build_rule"})

# ── 꼴 상한 ──────────────────────────────────────────────────────────────
KEY_RE = re.compile(r"[a-z0-9][a-z0-9_.:/-]{0,119}")
MAX_NAME, MAX_TEXT, MAX_REASON, MAX_REF, MAX_COPIES, MAX_EVIDENCE = 200, 2000, 500, 200, 50, 50
MAX_PAYLOAD_CHARS = 20000
MAX_NEIGHBOUR_DEPTH, MAX_NEIGHBOUR_LIMIT, MAX_SEARCH_LIMIT = 2, 200, 100
#: 이웃 지도 · 뇌 보기 — 한 번에 싣는 선 상한 · 뇌 보기 바탕 점 상한(흐린 전체 그림 — 자리만).
MAX_NEIGHBOUR_EDGES, MAX_BRAIN_POINTS = 1000, 5000


def basis_of(payload: Any) -> Optional[str]:
    """가격 규칙 근거 종류(정한 값이 아니거나 비었으면 ``None``)."""
    value = payload.get(BASIS_FIELD) if isinstance(payload, Mapping) else None
    return value if value in BASIS_RULES else None


def basis_rule(payload: Any) -> tuple[int, int, tuple[str, ...]]:
    """가격 규칙 → 정본 자리 규칙 — (최소, 최대, 받는 끝 유형). 근거 종류가 비면 :data:`BASIS_EMPTY_RULE`."""
    basis = basis_of(payload)
    return BASIS_RULES[basis] if basis else BASIS_EMPTY_RULE


def cardinality(from_type: str | None, kind: str, payload: Any = None) -> tuple[int, int | None]:
    """(시작 유형, 링크 종류)의 연결 개수 규칙 — (최소, 최대). 적지 않은 짝은 (0, ``None``).

    가격 규칙 → 정본 자리(``value_from``)는 그 항목 실음 칸의 근거 종류(``payload``)로 갈린다(D115)."""
    if from_type == PRICE_RULE_TYPE and kind == "value_from":
        low, high, _ends = basis_rule(payload)
        return low, high
    return LINK_CARDINALITY.get((from_type or "", kind), (0, None))


def cardinality_rules() -> list[tuple[str, str, Optional[str], int, int | None]]:
    """품질 수 · 안내용 규칙 줄 — (시작 유형, 종류, 근거 종류(가격 규칙만 — 빈 근거는 ``""``), 최소, 최대)."""
    rows: list[tuple[str, str, Optional[str], int, int | None]] = [
        (t, k, None, low, high) for (t, k), (low, high) in LINK_CARDINALITY.items()]
    rows += [(PRICE_RULE_TYPE, "value_from", basis, low, high) for basis, (low, high, _e) in BASIS_RULES.items()]
    rows.append((PRICE_RULE_TYPE, "value_from", "", BASIS_EMPTY_RULE[0], BASIS_EMPTY_RULE[1]))
    return rows


def external_type(key: str) -> str | None:
    """바깥 자리 키(:data:`EXTERNAL_PREFIXES` 머리)면 그 가짜 유형, 아니면 ``None``."""
    return next((kind for prefix, kind in EXTERNAL_PREFIXES.items() if key.startswith(prefix)), None)


def link_allowed(from_type: str, kind: str, to_type: str) -> bool:
    """(시작 유형, 링크 종류, 끝 유형) 짝이 허용 표에 있나(시작 유형별 좁힘 · 같은 유형끼리 종류 포함)."""
    pair = ALLOWED_LINKS.get(kind)
    if pair is None or from_type not in pair[0] or to_type not in pair[1]:
        return False
    narrow = NARROW_ENDS.get((from_type, kind))
    if narrow is not None and to_type not in narrow:
        return False
    return kind not in SAME_TYPE_KINDS or from_type == to_type


def is_doc_item(item_type: Optional[str], payload: Any) -> bool:
    """지식 문서 항목인가 — 지식 문서 유형이고, 고를 수 있는 유형(:data:`OPTIONAL_DOC_TYPES`)은 문서 id 가 있을 때만."""
    if item_type not in DOC_TYPES:
        return False
    return item_type not in OPTIONAL_DOC_TYPES or bool(isinstance(payload, Mapping) and payload.get("doc_id"))


def value_problems(*, item_type: Any = None, brand: Any = None, kind: Any = None, status: Any = None,
                   check: tuple[str, ...] = ("item_type", "brand", "kind", "status")) -> list[str]:
    """유형 · 브랜드 · 링크 종류 · 상태 값이 정한 목록 안인가 — **값 목록 검사 한 곳**(7.8 다음 14). DB 검사 제약은 유형이 늘
    때마다 마이그레이션이 붙어 두지 않고, 쓰는 길(:mod:`.gates` · :mod:`.proposals`)과 품질 수(:mod:`.quality`)가 이 목록을 쓴다.

    Args:
        check: 볼 칸 이름(부르는 쪽이 가진 칸만).
    """
    lists = {"item_type": (item_type, TYPES, "유형"), "brand": (brand, BRANDS, "브랜드"),
             "kind": (kind, LINK_KINDS, "링크 종류"), "status": (status, OBJECT_STATUSES, "상태")}
    return [f"{name}: 정한 {lists[name][2]} 값이 아니다(값 목록은 코드 + 설계서로만 더한다)"
            for name in check if lists[name][0] not in lists[name][1]]


def heavier_grade(*grades: str) -> str:
    """가장 무거운 등급(A < B_LIGHT < B)."""
    return max(grades, key=GRADES.index)
