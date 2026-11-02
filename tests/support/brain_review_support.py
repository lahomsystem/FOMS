"""제안함 · 다시 확인 · 판 되돌리기 시험 재료 — 합성 사람(역할 × 팀) · 합성 항목 · 열린 제안(SQLite · PostgreSQL 레인 같이).

손으로 꾸민 합성 이름 · 글만 쓴다(금액 · 손님 글 · 직원 이름 · 비밀값 없음). 글에 숫자를 넣지 않는다(숫자 관문은 따로).

같은 모집단(상담 층 배운 점 둘)에 **보이는 것과 숨긴 것**을 같이 둔다 — 범위 거르기의 음성 대조군.
"""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.brain.proposals import Proposer, propose_update
from tests.support.brain_screen_support import people
from tests.support.brain_support import NOW, REASON, create

DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}


def items(session: Any, admin: Any) -> None:
    """항목 — 공통 제품 · 가격 규칙 · 제작 조건, 상담 층 배운 점(보임 · 도면팀만) · 말투, 도면 규칙."""
    create(session, admin, "common/door", name="여닫이 문짝")
    create(session, admin, "common/shipping", item_type="price_rule", name="운임 규칙", text="지역별 운임 기준",
           checked_at="2026-10-20", payload={"doc_id": "shipping", **DOC})
    create(session, admin, "common/fit", item_type="build_rule", name="문짝 맞춤 규칙", checked_at="2026-07-01")
    create(session, admin, "cs/lesson/photo", item_type="lesson", layer="cs", name="사진 먼저 받기")
    create(session, admin, "cs/lesson/hidden", item_type="lesson", layer="cs", name="도면팀만 보는 배운 점",
           visibility="team:DRAWING")
    create(session, admin, "cs/tone/polite", item_type="tone", layer="cs", name="부드러운 말투")
    create(session, admin, "drawing/rule/final", item_type="drawing_rule", layer="drawing", name="최종본만 올리기",
           checked_at="2026-10-01", visibility="team:DRAWING")


def open_proposals(session: Any, admin: Any, *, now: datetime.datetime = NOW) -> dict[str, int]:
    """열린 사람 제안 넷 — 가격 규칙(사장님 몫) · 상담 배운 점(보임) · 상담 배운 점(도면팀만) · 도면 규칙."""
    who = Proposer.user(admin.id)
    made = {
        "price": propose_update(session, key="common/shipping", base_version=1, after={"text": "지역별 운임 새 기준"},
                                reason=REASON, proposer=who, now=now, known=""),
        "cs": propose_update(session, key="cs/lesson/photo", base_version=1, after={"name": "사진 먼저 꼭 받기"},
                             reason=REASON, proposer=who, now=now, known=""),
        "hidden": propose_update(session, key="cs/lesson/hidden", base_version=1, after={"name": "숨은 배운 점 고침"},
                                 reason=REASON, proposer=who, now=now, known=""),
        "drawing": propose_update(session, key="drawing/rule/final", base_version=1,
                                  after={"text": "최종 도면만 올린다"}, reason=REASON, proposer=who, now=now, known=""),
    }
    return {name: change.id for name, change in made.items()}


def review_world(session: Any) -> dict[str, Any]:
    """사람 + 항목 + 열린 제안(커밋함) — ``{"people": {...}, "changes": {...}}``."""
    who = people(session)
    items(session, who["admin"])
    changes = open_proposals(session, who["admin"])
    session.commit()
    return {"people": who, "changes": changes}
