"""합성 평가 묶음 — 답할 질문 30 + 지식에 없는 질문 10(설계서 11절 판 1 완료 기준 · 7.7 · D105 '평가 질문을 실행되는 시험으로').

손으로 꾸민 합성 지식(:data:`ITEMS`)과 질문만 쓴다 — 실제 가격 · 손님 글 · 직원 이름 없음. 질문마다 기대 항목 키를 단다.
실제 묶음은 학습 폴더(저장소 밖)에 두고 ``scripts/maintenance/brain_chat_eval.py`` 로 같은 길을 돈다.
"""

from __future__ import annotations

from typing import Any

from foms.services.brain.eval_set import EvalQuestion, parse_questions
from tests.support.brain_support import create

#: (키, 유형, 이름, 글, 실음 칸) — 공통 바탕 · 상담 층. 낱말이 서로 겹치지 않게 꾸몄다.
ITEMS: tuple[tuple[str, str, str, str, dict[str, Any]], ...] = (
    ("eval/sliding", "spec", "슬라이딩 깊이", "슬라이딩 장 몸통 깊이 합성 기준 650mm", {"value": 650, "unit": "mm"}),
    ("eval/hinge", "build_rule", "경첩 개수", "여닫이 문짝 경첩 합성 기준 셋", {}),
    ("eval/molding", "build_rule", "몰딩 높이", "천장 몰딩 높이 합성 기준", {}),
    ("eval/no-molding", "build_rule", "무몰딩 천고", "무몰딩 천고 상한 합성 기준", {}),
    ("eval/handle", "option", "손잡이 종류", "손잡이 고르기 합성 안내", {"price_kind": "extra"}),
    ("eval/fridge", "product_line", "냉장고장", "냉장고장 구성 합성 안내", {}),
    ("eval/vanity", "product_line", "화장대", "화장대 구성 합성 안내", {}),
    ("eval/drawer", "option", "서랍 추가", "서랍 추가 합성 안내", {"price_kind": "extra"}),
    ("eval/shelf", "option", "선반 칸수", "선반 칸수 합성 안내", {"price_kind": "included"}),
    ("eval/mirror", "option", "거울 문", "거울 문 합성 안내", {"price_kind": "quote"}),
    ("eval/lighting", "option", "조명 설치", "조명 설치 합성 안내", {"price_kind": "extra"}),
    ("eval/top", "spec", "상판 두께", "상판 두께 합성 기준 30mm", {"value": 30, "unit": "mm"}),
    ("eval/baseboard", "spec", "걸레받이 높이", "걸레받이 높이 합성 기준 60mm", {"value": 60, "unit": "mm"}),
    ("eval/measure", "policy", "실측 방문", "실측 방문 합성 정책", {"doc_id": "measure", "approved_by": "합성",
                                                          "approved_at": "2026-10-30"}),
    ("eval/delivery", "policy", "운송 일정", "운송 일정 합성 정책", {"doc_id": "delivery", "approved_by": "합성",
                                                          "approved_at": "2026-10-30"}),
    ("eval/install", "policy", "설치 순서", "설치 순서 합성 정책", {"doc_id": "install", "approved_by": "합성",
                                                          "approved_at": "2026-10-30"}),
    ("eval/demolish", "policy", "철거 범위", "철거 범위 합성 정책", {"doc_id": "demolish", "approved_by": "합성",
                                                          "approved_at": "2026-10-30"}),
    ("eval/warranty", "policy", "보증 기간", "보증 기간 합성 정책", {"doc_id": "warranty", "approved_by": "합성",
                                                          "approved_at": "2026-10-30"}),
    ("eval/refund", "policy", "환불 절차", "환불 절차 합성 정책", {"doc_id": "refund", "approved_by": "합성",
                                                          "approved_at": "2026-10-30"}),
    ("eval/payment", "policy", "결제 수단", "결제 수단 합성 정책", {"doc_id": "payment", "approved_by": "합성",
                                                          "approved_at": "2026-10-30"}),
    ("eval/booking", "policy", "예약 변경", "예약 변경 합성 정책", {"doc_id": "booking", "approved_by": "합성",
                                                          "approved_at": "2026-10-30"}),
    ("eval/color", "option", "색상 고르기", "색상 견본 합성 안내", {"price_kind": "included"}),
    ("eval/material", "spec", "소재 등급", "소재 등급 합성 기준 E0", {}),
    ("eval/edge", "build_rule", "엣지 마감", "엣지 마감 합성 기준", {}),
    ("eval/packing", "build_rule", "포장 방식", "포장 방식 합성 기준", {}),
    ("eval/corner", "build_rule", "코너장 조건", "코너장은 여닫이만 되고 슬라이딩은 안 되는 합성 조건", {}),
    ("eval/term-builtin", "term", "붙박이장", "붙박이장 합성 용어", {"aliases": ["빌트인장"], "broader": "가구"}),
    ("eval/term-pantry", "term", "팬트리", "팬트리 합성 용어", {"aliases": ["식료품장"], "broader": "수납"}),
    ("eval/term-island", "term", "아일랜드", "아일랜드 합성 용어", {"aliases": ["섬식탁"], "broader": "주방"}),
    ("eval/lesson-photo", "lesson", "사진 먼저", "사진 먼저 받기 합성 배운 점", {}),
)
_CS_TYPES = {"lesson"}

#: 답할 질문 30(기대 키 하나) + 지식에 없는 질문 10(기대 없음). 셋은 다른 이름으로 묻는다(SKOS).
QUESTIONS: list[dict[str, Any]] = [
    {"id": "a01", "q": "슬라이딩 장은 깊이가 얼마나 돼요?", "expect": ["eval/sliding"]},
    {"id": "a02", "q": "여닫이 문짝에 경첩은 몇 개 달아요?", "expect": ["eval/hinge"]},
    {"id": "a03", "q": "몰딩 높이 기준 알려 주세요", "expect": ["eval/molding"]},
    {"id": "a04", "q": "무몰딩 천고 상한이 있나요?", "expect": ["eval/no-molding"]},
    {"id": "a05", "q": "손잡이 종류는 어떤 게 있어요?", "expect": ["eval/handle"]},
    {"id": "a06", "q": "냉장고장 구성이 궁금해요", "expect": ["eval/fridge"]},
    {"id": "a07", "q": "화장대 구성은요?", "expect": ["eval/vanity"]},
    {"id": "a08", "q": "서랍 추가 되나요?", "expect": ["eval/drawer"]},
    {"id": "a09", "q": "선반 칸수는 어떻게 정해요?", "expect": ["eval/shelf"]},
    {"id": "a10", "q": "거울 문 달 수 있어요?", "expect": ["eval/mirror"]},
    {"id": "a11", "q": "조명 설치도 해 주나요?", "expect": ["eval/lighting"]},
    {"id": "a12", "q": "상판 두께는요?", "expect": ["eval/top"]},
    {"id": "a13", "q": "걸레받이 높이 기준", "expect": ["eval/baseboard"]},
    {"id": "a14", "q": "실측 방문은 어떻게 잡아요?", "expect": ["eval/measure"]},
    {"id": "a15", "q": "운송 일정 정책 알려 줘", "expect": ["eval/delivery"]},
    {"id": "a16", "q": "설치 순서가 어떻게 돼요?", "expect": ["eval/install"]},
    {"id": "a17", "q": "철거 범위는 어디까지예요?", "expect": ["eval/demolish"]},
    {"id": "a18", "q": "보증 기간이 얼마나 돼요?", "expect": ["eval/warranty"]},
    {"id": "a19", "q": "환불 절차 알려 주세요", "expect": ["eval/refund"]},
    {"id": "a20", "q": "결제 수단은 뭐가 돼요?", "expect": ["eval/payment"]},
    {"id": "a21", "q": "예약 변경하려면요?", "expect": ["eval/booking"]},
    {"id": "a22", "q": "색상 견본 볼 수 있어요?", "expect": ["eval/color"]},
    {"id": "a23", "q": "소재 등급이 뭐예요?", "expect": ["eval/material"]},
    {"id": "a24", "q": "엣지 마감 기준은요?", "expect": ["eval/edge"]},
    {"id": "a25", "q": "포장 방식 알려 주세요", "expect": ["eval/packing"]},
    {"id": "a26", "q": "코너장은 슬라이딩도 돼요?", "expect": ["eval/corner"]},
    {"id": "a27", "q": "빌트인장이 뭐예요?", "expect": ["eval/term-builtin"]},
    {"id": "a28", "q": "식료품장 만들 수 있어요?", "expect": ["eval/term-pantry"]},
    {"id": "a29", "q": "섬식탁은 무엇인가요?", "expect": ["eval/term-island"]},
    {"id": "a30", "q": "사진 먼저 받아야 해요?", "expect": ["eval/lesson-photo"], "layer": "cs"},
    {"id": "u01", "q": "주차 요금은 얼마예요?", "expect": []},
    {"id": "u02", "q": "점심 메뉴 추천해 줘", "expect": []},
    {"id": "u03", "q": "회식 장소가 어디예요?", "expect": []},
    {"id": "u04", "q": "연차 신청은 누구에게 해요?", "expect": []},
    {"id": "u05", "q": "택배 송장 번호 조회", "expect": []},
    {"id": "u06", "q": "사무실 와이파이 비밀번호", "expect": []},
    {"id": "u07", "q": "워크숍 참석 명단", "expect": []},
    {"id": "u08", "q": "명함 주문은 어떻게 해요?", "expect": []},
    {"id": "u09", "q": "복합기 토너 교체", "expect": []},
    {"id": "u10", "q": "출장비 정산 서류", "expect": []},
]


def seed(session: Any, admin: Any) -> None:
    """합성 지식을 반영(사람 승인)으로 넣는다. 커밋한다."""
    for key, item_type, name, text, payload in ITEMS:
        extra: dict[str, Any] = {"payload": payload} if payload else {}
        if item_type in ("policy", "build_rule"):
            extra["checked_at"] = "2026-10-30"
        layer = "cs" if item_type in _CS_TYPES else "common"
        brand = "LAHOM" if layer == "cs" else "COMMON"
        create(session, admin, key, item_type=item_type, layer=layer, brand=brand, name=name, text=text, **extra)
    session.commit()


def questions() -> list[EvalQuestion]:
    """평가 질문(검사한 꼴)."""
    return parse_questions(QUESTIONS)


# ── 전사 지식 온톨로지 점검의 평가 질문 여섯 + 말 바뀜(제주 · 도서산간) — 합성 꼴 ─────────────────────────────
_DOC = {"approved_by": "합성", "approved_at": "2026-10-30"}
#: (키, 유형, 층, 이름, 글, 실음 칸 · 그 밖 칸). 점검 '평가 질문으로 따라가 보면'의 여섯 질문을 합성 지식으로 옮겼다.
AUDIT_ITEMS: tuple[tuple[str, str, str, str, str, dict[str, Any]], ...] = (
    ("eval/short-hinged", "price_rule", "common", "여닫이 짧은 길이 값 규칙",
     "여닫이 장이 최소 길이보다 짧으면 최소 길이 값을 받는 합성 규칙",
     {"payload": {"doc_id": "short-hinged", **_DOC}, "checked_at": "2026-10-30"}),
    ("eval/remote-shipping", "policy", "common", "도서산간 운임 정책", "도서산간 지역 운임 합성 정책",
     {"payload": {"doc_id": "remote-shipping", **_DOC, "aliases": ["섬 지역 배송비"], "hidden_labels": ["도서 산간"]}}),
    ("eval/term-remote", "term", "common", "도서산간", "육지에서 먼 곳을 이르는 합성 용어",
     {"payload": {"aliases": ["제주", "섬 지역"], "broader": "권역"}}),
    ("eval/part-door", "part_kind", "drawing", "도어 조각", "정면 문짝 그림 조각 합성 종류", {}),
    ("eval/d83", "owner_decision", "common", "D83 결정", "옛 몰딩 기준을 새 기준으로 바꾼 합성 결정",
     {"payload": {"doc_id": "d83", **_DOC, "decision_no": "D83"}, "evidence_ref": "원장 합성 번호"}),
    ("eval/old-molding", "build_rule", "common", "옛 몰딩 기준", "옛 몰딩 합성 기준", {"checked_at": "2026-10-30"}),
    # 공정 단계(7.8 다음 3) — 손님용 단계 이름은 다른 이름
    ("eval/step-measure", "process_step", "common", "실측 단계", "주문 뒤 집에 가서 재는 합성 공정 단계",
     {"payload": {"erp_stage": "MEASURE", "step_order": 2, "aliases": ["실측 방문 단계"]}}),
)
#: (링크 종류, 시작, 끝) — 그림 조각 → 제품(7.8 다음 5 — ``part_of``) · 제품 → 옵션 · 결정 → 대체한 앞 항목.
AUDIT_LINKS: tuple[tuple[str, str, str], ...] = (
    ("part_of", "eval/part-door", "eval/fridge"),
    ("requires", "eval/vanity", "eval/handle"),
    ("supersedes", "eval/d83", "eval/old-molding"),
)
#: 점검 질문 여섯(합성 꼴) + 말 바뀜 둘. 기대 키는 '찾기 단계에 들어야 할 항목'(평가 실행기 ``--retrieval-only`` 와 같은 잣대).
AUDIT_QUESTIONS: list[dict[str, Any]] = [
    {"id": "x01", "q": "1,350mm 여닫이 장은 얼마이고 왜 그래요?", "expect": ["eval/short-hinged"]},
    {"id": "x02", "q": "제주 운임에 걸리는 정책은?", "expect": ["eval/remote-shipping"]},
    {"id": "x03", "q": "냉장고장은 어떤 그림 조각 종류를 만드나?", "expect": ["eval/part-door"]},
    {"id": "x04", "q": "슬라이딩 깊이 값을 베끼는 매크로는?", "expect": ["eval/sliding"]},
    {"id": "x05", "q": "손잡이 종류는 어느 제품에 들어가나?", "expect": ["eval/vanity"]},
    {"id": "x06", "q": "D83 은 무엇을 바꿨나?", "expect": ["eval/d83"]},
    {"id": "x07", "q": "실측 방문 단계는 주문 흐름에서 어디예요?", "expect": ["eval/step-measure"]},  # 새 유형(7.8)
    {"id": "s01", "q": "섬 지역 배송비 알려 주세요", "expect": ["eval/remote-shipping"]},
    {"id": "s02", "q": "도서 산간 운임은?", "expect": ["eval/remote-shipping"]},
]


def seed_audit(session: Any, admin: Any) -> None:
    """점검 질문용 합성 지식 · 링크 · 사본(:func:`seed` 뒤에). 커밋한다."""
    from foms.services.brain.apply import apply_change
    from foms.services.brain.proposals import Proposer, propose_update
    from tests.support.brain_support import NOW, REASON, link

    for key, item_type, layer, name, text, extra in AUDIT_ITEMS:
        create(session, admin, key, item_type=item_type, layer=layer, name=name, text=text, **extra)
    for kind, src, dst in AUDIT_LINKS:
        link(session, admin, kind, src, dst)
    change = propose_update(session, key="eval/sliding", base_version=1, after={"copies": ["매크로 깊이 안내"]},
                            reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")
    apply_change(session, change.id, actor=admin, now=NOW)
    session.commit()


def audit_questions() -> list[EvalQuestion]:
    """점검 평가 질문(검사한 꼴)."""
    return parse_questions(AUDIT_QUESTIONS)
