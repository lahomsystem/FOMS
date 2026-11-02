"""'회사 지식' 화면 시험 재료 — 합성 사람(역할 × 팀) · 합성 항목(보기 범위 넷) · 링크 · 열린 제안 · 은퇴 · 낡음.

손으로 꾸민 합성 이름 · 글만 쓴다(금액 · 손님 글 · 직원 이름 · 비밀값 없음). 날짜는 :data:`TODAY` 기준이고, 화면 시험은
:func:`foms.services.datetime_kst.get_today_kst` 를 이 날로 묶는다.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import update

from foms.persistence.brain.models import BrainObject
from foms.services.brain.apply import apply_change
from foms.services.brain.proposals import Proposer, propose_retire, propose_update
from foms.services.brain.store import current_object
from tests.support.brain_support import NOW, REASON, TWO_SOURCES, agent_judge, create, link, person, setting

#: 한국 2026-11-02 — :data:`tests.support.brain_support.NOW` 의 한국 날짜.
TODAY = datetime.date(2026, 11, 2)
LONG_AGO = "2026-01-05"  # 제작 조건 주기 90일을 넘김 → 낡음


def people(session: Any) -> dict[str, Any]:
    """역할 × 팀 — 여는 사람 넷(ADMIN · CS/DRAWING/PRODUCTION MANAGER)과 못 여는 사람들(대조군)."""
    return {
        "admin": person(session, "bs_admin"),
        "cs_mgr": person(session, "bs_cs_mgr", role="MANAGER", team="CS"),
        "dr_mgr": person(session, "bs_dr_mgr", role="MANAGER", team="DRAWING"),
        "pr_mgr": person(session, "bs_pr_mgr", role="MANAGER", team="PRODUCTION"),
        "sales_mgr": person(session, "bs_sales_mgr", role="MANAGER", team="SALES"),
        "cs_staff": person(session, "bs_cs_staff", role="STAFF", team="CS"),
        "viewer": person(session, "bs_viewer", role="VIEWER", team="CS"),
        "off_admin": person(session, "bs_off_admin", active=False),
    }


def graph(session: Any, admin: Any) -> None:
    """제품 둘 · 규칙 넷(모두 · 도면팀 · 가격 재량 · 관리) · 낡은 제작 조건 · 초안 · 은퇴 · 열린 제안 · 바깥 정본 · 사본."""
    create(session, admin, "common/door", name="여닫이 문짝", copies=["매크로 문짝 안내", "스토어 상세 문짝 칸"])
    create(session, admin, "common/slide", name="미닫이 문짝")
    create(session, admin, "common/fit", item_type="build_rule", name="문짝 맞춤 규칙", checked_at=LONG_AGO)
    create(session, admin, "common/fresh", item_type="build_rule", name="문짝 새 규칙", checked_at="2026-11-01")
    create(session, admin, "common/draft", item_type="build_rule", name="문짝 초안 규칙", status="draft")
    create(session, admin, "common/old", item_type="build_rule", name="문짝 옛 규칙")
    create(session, admin, "drawing/rule", item_type="drawing_rule", layer="drawing", name="문짝 도면 규칙",
           visibility="team:DRAWING")
    create(session, admin, "common/discount", item_type="price_rule", name="문짝 재량 규칙", visibility="price",
           checked_at="2026-10-20",
           payload={"doc_id": "discount", "approved_by": "합성", "approved_at": "2026-10-20"})
    create(session, admin, "common/ask", item_type="question", name="문짝 물어볼 것", visibility="admin")
    link(session, admin, "applies_to", "common/fit", "common/door")
    link(session, admin, "applies_to", "drawing/rule", "common/door")
    link(session, admin, "applies_to", "common/discount", "common/door")
    link(session, admin, "requires", "common/fit", "common/slide")
    setting(session, "drawing_wizard_bom_rules")
    link(session, admin, "value_from", "common/door", "calc:product/7")
    link(session, admin, "value_from", "common/door", "setting:drawing_wizard_bom_rules")
    retire = propose_retire(session, key="common/old", base_version=1, reason=REASON,
                            proposer=Proposer.user(admin.id), now=NOW)
    apply_change(session, retire.id, actor=admin, now=NOW)
    # 고친 판(이력 둘) · 열린 제안 하나(확인 필요)
    fix = propose_update(session, key="common/door", base_version=1, after={"text": "합성 설명 고친 문짝"},
                         reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")
    apply_change(session, fix.id, actor=admin, now=NOW)
    with agent_judge():  # 에이전트 제안은 관문 셋을 넘어야 들어간다(7.7 · D105)
        propose_update(session, key="common/fit", base_version=1, after={"name": "문짝 맞춤 규칙 고침"}, reason=REASON,
                       proposer=Proposer.agent_named("cs_agent"), now=NOW, known="", evidence=TWO_SOURCES)
    session.execute(update(BrainObject).where(BrainObject.item_key == "common/fresh",
                                              BrainObject.superseded_at.is_(None)).values(usage_count=9))
    session.execute(update(BrainObject).where(BrainObject.item_key == "common/fit",
                                              BrainObject.superseded_at.is_(None)).values(usage_count=4))
    session.commit()


def world(session: Any) -> dict[str, Any]:
    """사람 + 항목을 만들고 사람 dict 를 돌려준다(커밋함)."""
    who = people(session)
    graph(session, who["admin"])
    assert current_object(session, "common/old").status == "retired"
    return who
