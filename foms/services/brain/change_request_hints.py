"""문장으로 채우기 안내(설계서 2026-11-18-brain-sentence-change 5절 표 3판) — 능력 질문(시험지)의 모자란 재료 → 쉬운 말 한 줄.

온톨로지 시험지 화면(``/brain?tab=onto&kind=cq``)의 모자란 줄에서 [문장으로 채우기]를 누르면 승인 대기 화면의 입력 칸으로 온다
(``/brain?tab=inbox&fill=<질문 번호>``). 그 칸 바로 아래에 그 질문(표의 일반화한 질문 — 손님 글이 아니다)과 모자란 것을 한 줄씩
보이는 말이 이 표 **한 곳**이다(화면 길 :mod:`foms.web.brain` 이 읽어 템플릿에 넘기고, 시험지 화면은 :func:`fill_kinds` 로 어느 줄에
링크를 달지 가른다).

- 지식 종류 · 연결 종류마다 (모자란 말 · 적는 예시). 예시는 지어낸 짧은 글이다 — 금액 · 사람 이름 · 손님 글 없음.
- 문장으로 고치기가 **만들 수 없는 것**(:data:`.change_request_model.CREATE_TYPES` 밖 — 가격 규칙 · 사장님 결정 · 기준 답 문구,
  설계서 12절)은 "이 칸으로 못 채워요 — <어디서>" 로 정직하게 적고 예시를 두지 않는다. 채울 수 있나는 손으로 적지 않고
  ``CREATE_TYPES`` 로 가른다(분석기가 바뀌면 안내도 같이 바뀐다 — 시험이 표와 맞춘다).
- ERP 재료(``erp:`` — 주문 · 일정)는 회사 지식으로 채우지 않으므로 안내에 넣지 않는다(시험지 화면이 이미 'ERP 붙으면 풀림'으로 가른다).
- 질문 번호는 표(:data:`.ontology_cqs.CQS`)에 있는 것만 받는다. 무엇이 모자란지는 보는 사람의 보기 범위로 센 점수
  (:func:`.ontology_view.ontology_summary`)에서 읽는다 — 시험지 화면과 같은 수.
"""

from __future__ import annotations

import datetime
from typing import Any, NamedTuple, Optional

from foms.services.brain.change_request_model import CREATE_TYPES
from foms.services.brain.constants import ALLOWED_LINKS, LINK_KINDS
from foms.services.brain.display import LINK_DISPLAY, TYPE_DISPLAY
from foms.services.brain.ontology_cqs import CQS, ERP_NEEDS
from foms.services.brain.ontology_view import ontology_summary
from foms.services.brain.scope import Viewer

__all__ = ["FILL_ID_MAX", "Hint", "LINK_HINTS", "TYPE_HINTS", "fill_hint", "fill_kinds", "hint_for"]

#: 주소 ``fill`` 값 길이 상한(질문 번호는 ``E02`` 꼴 — 더 긴 값은 읽지 않는다).
FILL_ID_MAX = 8


class Hint(NamedTuple):
    """모자란 것 하나의 안내 — 말 · 예시(못 채우는 것이면 ``None``)."""

    gap: str
    example: Optional[str]


#: 지식 종류 → 안내. 문장으로 고치기가 못 만드는 종류(가격 규칙 · 사장님 결정 · 기준 답 문구)는 예시 없이 어디서 채우는지만.
TYPE_HINTS: dict[str, Hint] = {
    "build_rule": Hint("제작 조건이 없어요 — 만들 수 있는 조건 · 못 만드는 조건을 적어 주세요",
                       "ㄱ자 코너장은 여닫이 문으로만 만들어요"),
    "situation": Hint("상황이 없어요 — 손님이 어떤 처지에서 묻는지와 그때 어떻게 하는지 적어 주세요",
                      "천장에 보가 지나가는 집은 보 아래에 맞춰 장을 나눠 달아요"),
    "spec": Hint("규격이 없어요 — 두께 · 깊이 · 높이처럼 정해진 크기를 적어 주세요",
                 "붙박이장 문짝 두께는 18mm 예요"),
    "term": Hint("용어가 없어요 — 손님이 쓰는 말이 무슨 뜻인지 적어 주세요",
                 "'무몰딩'은 천장과 장 사이에 마감판을 대지 않는 거예요"),
    "policy": Hint("정책이 없어요 — 손님에게 적용하는 회사 규칙을 적어 주세요",
                   "시공 뒤 1년 안에 생긴 하자는 무료로 고쳐 드려요"),
    "fact": Hint("사실이 없어요 — 회사 사정 · 일 나눔 · 일하는 순서를 있는 그대로 적어 주세요",
                 "쇼룸은 없고 시공 사례 사진을 보내 드려요"),
    "product_line": Hint("제품 라인이 없어요 — 파는 제품 묶음을 적어 주세요",
                         "드레스룸 시스템장도 팔아요"),
    "option": Hint("옵션이 없어요 — 더하거나 고를 수 있는 것을 적어 주세요",
                   "붙박이장에 LED 조명을 더할 수 있어요"),
    "process_step": Hint("공정 단계가 없어요 — 일하는 순서의 한 단계를 적어 주세요",
                         "실측 다음에는 도면 확인 단계가 있어요"),
    "price_rule": Hint("가격 규칙은 이 칸으로 못 채워요 — 금액은 견적 계산기에서 고치고, 가격 규칙 항목은 Claude 에게 "
                       "말씀해 주세요", None),
    "owner_decision": Hint("사장님 결정은 이 칸으로 못 채워요 — 결정은 Claude 에게 말씀해 주시면 결정 기록과 함께 넣어요", None),
    "template": Hint("기준 답 문구는 이 칸으로 못 채워요 — 손님에게 나가는 글이라 Claude 에게 말씀해 주세요", None),
}

#: 연결 종류 → 안내. 괄호 안은 시험지 화면의 이름(같은 것을 찾을 수 있게).
LINK_HINTS: dict[str, Hint] = {
    "requires": Hint("꼭 같이(필요) 연결이 없어요 — 무엇을 하려면 무엇이 꼭 같이 있어야 하는지 적어 주세요",
                     "상부장 LED 조명은 콘센트 옵션이 꼭 같이 있어야 해요"),
    "excludes": Hint("같이 못 함(제외) 연결이 없어요 — 같이 할 수 없는 두 가지를 적어 주세요",
                     "미닫이 문은 ㄱ자 코너장에 달 수 없어요"),
    "at_step": Hint("공정 단계 잇기(공정 단계) 연결이 없어요 — 정책 · 사실이 일의 어느 단계에서 쓰이는지 적어 주세요",
                    "잔금은 시공을 마친 날에 받아요"),
    "applies_to": Hint("적용 연결이 없어요 — 규칙이 어느 제품 · 옵션에 걸리는지 적어 주세요",
                       "무몰딩 조건은 붙박이장에만 걸려요"),
    "broader": Hint("위 항목 연결이 없어요 — 좁은 것이 어느 넓은 것에 드는지 적어 주세요",
                    "ㄱ자 코너장은 붙박이장의 한 갈래예요"),
    "decided_by": Hint("사장님 결정 잇기(정한 결정) 연결이 없어요 — 어느 사장님 결정이 정한 정책인지 적어 주세요"
                       "(그 결정이 지식에 있어야 이어요)",
                       "리뷰 적립 정책은 지난달 사장님 결정으로 정했어요"),
    "value_from": Hint("값 정본 연결이 없어요 — 값을 어느 계산기 · 설정에서 가져오는지 적어 주세요"
                       "(그 자리가 지식에 있어야 이어요)",
                       "도어를 더할 때 값은 견적 계산기의 도어 칸에서 가져와요"),
}


def _type_fillable(item_type: str) -> bool:
    return item_type in CREATE_TYPES and item_type in TYPE_HINTS


def _link_fillable(kind: str) -> bool:
    return kind in LINK_KINDS and kind in LINK_HINTS and bool(ALLOWED_LINKS[kind][0])


def fill_kinds() -> dict[str, list[str]]:
    """문장으로 채울 수 있는 지식 종류 · 연결 종류 — 시험지 화면이 줄마다 링크를 달지 가른다(``data-fill-kinds``)."""
    return {"types": sorted(t for t in TYPE_HINTS if _type_fillable(t)),
            "links": sorted(k for k in LINK_HINTS if _link_fillable(k))}


def hint_for(*, item_type: Optional[str] = None, kind: Optional[str] = None) -> dict[str, Any]:
    """모자란 것 하나 → ``{"gap", "example", "fillable"}``. 표에 없는 종류는 화면 이름으로 짧게(못 채움)."""
    if item_type is not None:
        hint, fillable = TYPE_HINTS.get(item_type), _type_fillable(item_type)
    else:
        hint, fillable = LINK_HINTS.get(kind or ""), _link_fillable(kind or "")
    if hint is None:
        label = TYPE_DISPLAY.get(item_type or "", LINK_DISPLAY.get(kind or "", (item_type or kind or "",)))[0]
        return {"gap": f"{label} — 모자라요", "example": None, "fillable": False}
    return {"gap": hint.gap, "example": hint.example if fillable else None, "fillable": fillable}


def _known_id(raw: Any) -> Optional[str]:
    code = str(raw or "").strip()[:FILL_ID_MAX]
    return code if any(cq.cq_id == code for cq in CQS) else None


def fill_hint(session: Any, viewer: Viewer, raw_id: Any, *, today: datetime.date) -> Optional[dict[str, Any]]:
    """입력 칸 아래 안내 — 표에 없는 번호면 ``None``(안내 없이 지금 칸 그대로).

    Args:
        session: 읽기 세션.
        viewer: 보는 사람(점수는 그 사람의 보기 범위로 센다 — 시험지 화면과 같은 수).
        raw_id: 주소의 ``fill`` 값.
        today: KST 오늘.

    Returns:
        ``{"id", "question", "gaps": [{"gap", "example", "fillable"}], "example"}`` — 회사 지식 재료(ERP 밖)만, 표의 차례
        (필요한 종류 → 연결). ``example`` 은 채울 수 있는 첫 모자람의 예시(없으면 ``None``).
    """
    code = _known_id(raw_id)
    if code is None:
        return None
    rows = ontology_summary(session, viewer, today=today)["cq"]["rows"]
    row = next(r for r in rows if r["id"] == code)
    gaps = [hint_for(item_type=n["type"]) for n in row["needs"] if not n["have"] and n["type"] not in ERP_NEEDS]
    gaps += [hint_for(kind=link["kind"]) for link in row["links"] if not link["have"]]
    example = next((g["example"] for g in gaps if g["fillable"] and g["example"]), None)
    return {"id": code, "question": row["question"], "gaps": gaps, "example": example}
