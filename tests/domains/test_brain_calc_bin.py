"""제안함 ⑤ 계산기 제품 · 옵션(설계서 2026-11-12 온톨로지 4.1 · 사장님 D191 · D192).

계산기 정본에서 만든 제품 라인 · 옵션 만들기(금액 칸 없음)와 그 항목 → ``calc:`` 값 링크만 ⑤ · 사장님(관리자)만 한꺼번에 승인 ·
상담팀장은 ⑤ 를 한꺼번에 못 함 · 금액 칸이 든 만들기 · AI 제안 · 다른 링크는 예전 묶음. 합성 계산기만(꾸민 수 · 실제 이름 없음).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainLink
from foms.services.brain.access import wide_bins
from foms.services.brain.catalog_plan import catalog_plan
from foms.services.brain.decide import bulk_apply
from foms.services.brain.errors import BrainShapeError
from foms.services.brain.external import catalog_source
from foms.services.brain.inbox import inbox
from foms.services.brain.inbox_bins import BIN_CALC, bulk_ok_any_grade, card_bin
from foms.services.brain.plan_proposals import file_plan
from foms.services.brain.scope import viewer_of
from tests.domains.test_brain_catalog_plan import CATALOG, synth
from tests.support.brain_support import NOW, person

IMPORT = {"proposed_by": "import"}
CREATE = {"name": {"before": None, "after": "합성 제품"},
          "payload": {"before": None, "after": {"pref_label": "합성 제품", "price_unit": "30cm"}}}


@pytest.mark.parametrize("op, item_type, fields, link_kind, ends, want", [
    ("create", "product_line", CREATE, None, IMPORT, BIN_CALC),
    ("create", "option", CREATE, None, IMPORT, BIN_CALC),
    ("create", "product_line", {"payload": {"before": None, "after": {"price_30cm": 1}}}, None, IMPORT, "content"),
    ("create", "product_line", CREATE, None, {"proposed_by": "agent:cs"}, "content"),  # AI 제안은 ⑤ 아님
    ("create", "price_rule", CREATE, None, IMPORT, "content"),
    ("link_add", None, None, "value_from", {**IMPORT, "link_from": "product_line/lahom-1", "link_to": "calc:product/1"},
     BIN_CALC),
    ("link_add", None, None, "value_from", {**IMPORT, "link_from": "common/price", "link_to": "calc:product/1"}, "content"),
    ("link_add", None, None, "value_from", {**IMPORT, "link_from": "option/3-5", "link_to": "setting:x"}, "content"),
    ("link_add", None, None, "copy_in", {**IMPORT, "link_from": "option/3-5", "link_to": "form:x"}, "mark"),
    ("create", "product_line", CREATE, None, {}, "content"),  # 만든 쪽을 안 넘기면 예전 네 묶음 그대로
])
def test_calc_bin_is_only_catalog_items_and_their_calculator_links(op, item_type, fields, link_kind, ends, want):
    assert card_bin(op, item_type, fields, link_kind, **ends) == want


@pytest.fixture
def people(app):
    admin = person(db_session, "calc_bin_admin")
    lead = person(db_session, "calc_bin_lead", role="MANAGER", team="CS")
    db_session.commit()
    return admin, lead


def file_catalog():
    with catalog_source(synth):
        file_plan(db_session, catalog_plan(CATALOG), brand="LAHOM", apply=True, now=NOW)
    db_session.commit()
    return db_session.execute(select(BrainChange.id).where(BrainChange.status == "open")
                              .order_by(BrainChange.id)).scalars().all()


def test_only_the_owner_bulk_approves_calc_cards_then_the_value_links(people):
    admin, lead = people
    assert BIN_CALC in wide_bins(viewer_of(admin)) and BIN_CALC not in wide_bins(viewer_of(lead))  # D192
    ids = file_catalog()
    cards = inbox(db_session, viewer_of(admin), now=NOW)["cards"]
    assert len(ids) == 4 and {card["bin"] for card in cards} == {BIN_CALC} and all(c["main"]["bulk_ok"] for c in cards)
    with pytest.raises(BrainShapeError):  # 상담팀장은 ⑤ 를 한꺼번에 못 한다
        bulk_apply(db_session, ids, actor=lead, now=NOW)
    db_session.rollback()
    with catalog_source(synth):
        out = bulk_apply(db_session, ids, actor=admin, now=NOW)
    db_session.commit()
    assert len(out["applied"]) == 4 and out["failed"] == []
    links = file_catalog()  # 반영 뒤 다음 차례 — 계산기 값 링크
    views = inbox(db_session, viewer_of(admin), now=NOW)["cards"]
    assert len(links) == 4 and {card["bin"] for card in views} == {BIN_CALC}
    with catalog_source(synth):
        assert len(bulk_apply(db_session, links, actor=admin, now=NOW)["applied"]) == 4
    db_session.commit()
    ends = {(link.from_key, link.to_key) for link in db_session.execute(select(BrainLink)).scalars()}
    assert ("product_line/haud-7", "calc:product/7") in ends


def test_old_four_bins_keep_their_bulk_rule_without_ends():
    assert bulk_ok_any_grade("create", "product_line", CREATE, None) is False
    assert bulk_ok_any_grade("create", "product_line", CREATE, None, **IMPORT) is True
