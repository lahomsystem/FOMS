"""코드 값 넷을 설정으로(master brain 설계서 7.8 다음 4 · 다음 10 · 사장님 D116) — 견적 최소 길이 · 반통 기준 · 그림 읽기 벽 쪽 값.

**대조군이 핵심**: 설정 줄이 없으면 견적 · 그림 읽기 결과가 지금(코드 상수)과 똑같다. 설정이 있고 맞으면 그 값, 틀리면 그 칸만
처음 값. brain 의 ``setting:<키>#<칸>`` 가리킴은 칸까지 실재를 보고(줄이 없어도 처음 값이 있는 칸은 있음), 카드에는 지금 값.
합성 mm 값만(금액은 적지 않는다 — 비교는 계산 가로 · 범위로).
"""

from __future__ import annotations

import json

import pytest

from db import db_session
from foms.services.brain.card import item_card
from foms.services.brain.errors import BrainExternalRefError
from foms.services.brain.external import missing_refs
from foms.services.brain.proposals import Proposer, propose_link
from foms.services.brain.scope import viewer_of
from foms.services.cs_agent import image_rules as ir
from foms.services.cs_agent import loop, quote_calc as qc, quote_record as qrec, quote_rules as qr, quote_step as qs
from foms.services.cs_agent import rule_settings as rs
from foms.services.cs_agent.drafting_summary import DraftSummary
from foms.services.cs_agent.image_read import _ranges
from models import SystemSetting
from tests.domains.test_cs_quote import _request
from tests.support.brain_screen_support import TODAY
from tests.support.brain_support import NOW, REASON, create, link, person, setting
from tests.support.cs_image_support import answer, room, wall
from tests.support.cs_quote_support import (
    MOLD, QUOTE_TEXT, SLIDING, FakeQuoter, ask, catalog, checked, evaluate, space, switch,
)
from tests.support.cs_quote_support import NOW as QUOTE_NOW


def _read(*spaces):
    return ir.read_result(json.dumps(answer(*spaces)))


# ── 순수 읽기 — 설정 없음 = 지금 값 ──────────────────────────────────────
def test_defaults_equal_the_code_constants():
    assert rs.limits_from(None) == qr.DEFAULT_LIMITS == qr.QuoteLimits(qr.HINGE_MIN_MM, qr.SLIDE_MIN_MM, qr.HINGE_HALF_MM)
    assert qr.DEFAULT_LIMITS.unknown_min_mm == qr.UNKNOWN_MIN_MM
    assert rs.wall_side_from(None) == ir.WALL_SIDE_MM == 150
    assert rs.KNOWN_FIELDS == {"cs_quote_rules": {"hinge_min_mm": 1500, "slide_min_mm": 2400, "hinge_half_mm": 1200},
                               "drawing_dimension_rules": {"wall_side_mm": 150}}


@pytest.mark.parametrize("stored", [None, {}, {"other": 1}, "깨진 값", [1, 2]])
def test_missing_or_broken_settings_change_nothing(stored):
    """대조군 — 줄 없음 · 빈 줄 · 모르는 칸 · 깨진 꼴이면 견적 · 그림 읽기 결과가 지금과 같다."""
    limits = rs.limits_from(stored)
    assert limits == qr.DEFAULT_LIMITS
    for product, width in ((SLIDING, 1800), (MOLD, 2405), (MOLD, 2000)):
        same = evaluate(ask(space(product["id"], width)))
        got = qc.evaluate(ask(space(product["id"], width)), catalog(), (), check=checked(), now=QUOTE_NOW,
                          limits=limits)
        assert (got.status, got.code, got.lines, got.allowed) == (same.status, same.code, same.lines, same.allowed)
    read = _read(room("안방", wall(2700)), room("거실", wall(3000, ends="one_wall")))
    assert _ranges(read, rs.wall_side_from(stored)) == _ranges(read)


def test_valid_fields_are_used_and_wrong_fields_fall_back_alone():
    limits = rs.limits_from({"slide_min_mm": 2100, "hinge_min_mm": "1400", "hinge_half_mm": True})
    assert (limits.slide_min_mm, limits.hinge_min_mm, limits.hinge_half_mm) == (2100, 1500, 1200)  # 틀린 칸만 처음 값
    assert limits.unknown_min_mm == 2100  # '모름' 최소는 슬라이딩 최소를 따른다
    assert rs.limits_from({"hinge_half_mm": 1600}) == qr.DEFAULT_LIMITS  # 반통 기준 ≥ 여닫이 최소면 둘 다 처음 값
    assert rs.limits_from({"slide_min_mm": 99_999}).slide_min_mm == 2400  # 범위 밖
    assert rs.rule_values({"hinge_min_mm": "x"}, rs.QUOTE_FIELDS)[1] == ["hinge_min_mm"]
    got = qr.price(SLIDING, 1800, [], [SLIDING], limits=limits)
    assert (got.width_used, "슬라이딩 최소 2,100mm 값" in got.note) == (2100, True)
    assert qr.price(SLIDING, 1800, [], [SLIDING]).width_used == 2400  # 대조군
    with pytest.raises(qr.NeedsHuman):
        qr.price(MOLD, 2000, [], [MOLD])  # 모름 2400 미만 — 사람에게
    assert qr.price(MOLD, 2150, [], [MOLD], limits=limits).width_used == 2150  # 설정 2100 이상이면 계산
    assert rs.wall_side_from({"wall_side_mm": 100}) == 100 and rs.wall_side_from({"wall_side_mm": -5}) == 150
    cut = ir.wall_range(_read(room("안방", wall(3000, basis="center_line"))).spaces[0].walls[0], 100)
    assert cut[2] == 200 and ir.wall_range(_read(room("안방", wall(3000, basis="center_line"))).spaces[0].walls[0])[2] == 300


# ── DB 읽기 · 견적 넣기 길 ────────────────────────────────────────────────
def test_quote_step_reads_the_setting_row(app):
    switch()
    assert rs.quote_limits(db_session) == qr.DEFAULT_LIMITS and rs.wall_side_mm(db_session) == 150  # 줄 없음

    def step():
        return qs.prepare(session=db_session, knowledge=_request().knowledge, request=_request(), texts=[QUOTE_TEXT],
                          now=QUOTE_NOW, stop=loop.StopFlag(), summary=DraftSummary(),
                          quoter=FakeQuoter(ask(space(SLIDING["id"], 1800))), catalog_reader=catalog,
                          price_check=lambda *_a, **_k: checked())

    before = step()
    assert before.status == qrec.STATUS_OK and any("계산 가로 2,400mm" in line for line in before.allowed)
    db_session.add(SystemSetting(setting_key=rs.QUOTE_RULES_KEY, setting_value={"slide_min_mm": 2100}))
    db_session.add(SystemSetting(setting_key=rs.DIMENSION_RULES_KEY, setting_value={"wall_side_mm": 120}))
    db_session.commit()
    after = step()
    assert any("계산 가로 2,100mm" in line for line in after.allowed)  # 설정이 있으면 그 값(재배포 없이)
    assert rs.wall_side_mm(db_session) == 120


# ── brain 가리킴 — setting:<키>#<칸> ────────────────────────────────────
def test_setting_field_refs_check_the_field(app):
    setting(db_session, "synthetic_rules", {"known_mm": 10})
    assert missing_refs(db_session, ["setting:cs_quote_rules#hinge_min_mm", "setting:drawing_dimension_rules#wall_side_mm",
                                     "setting:drawing_dimension_rules", "setting:synthetic_rules#known_mm",
                                     "setting:synthetic_rules"]) == ([], False)  # 줄이 없어도 처음 값이 있는 칸
    wrong = ["setting:cs_quote_rules#nope", "setting:synthetic_rules#nope", "setting:no_row#x", "setting:no_row"]
    assert missing_refs(db_session, wrong) == (wrong, False)


def test_a_common_spec_points_at_the_wall_side_setting(app):
    admin = person(db_session, "d129_rule_admin")
    cs = person(db_session, "d129_rule_cs", role="MANAGER", team="CS")
    create(db_session, admin, "common/wall-side", item_type="spec", name="벽 포함 치수 벽 쪽 값",
           payload={"value": 150, "unit": "mm", "basis": "wall_incl"})
    link(db_session, admin, "value_from", "common/wall-side", "setting:drawing_dimension_rules#wall_side_mm")
    with pytest.raises(BrainExternalRefError):
        propose_link(db_session, op="link_add", kind="value_from", from_key="common/wall-side",
                     to_key="setting:drawing_dimension_rules#wall_mm", reason=REASON,
                     proposer=Proposer.user(admin.id), now=NOW)
    chip = item_card(db_session, viewer_of(admin), "common/wall-side", today=TODAY)["external"][0]
    assert chip["exists"] is True and chip["value"] == "150(처음 값)" and chip["label"] == "drawing_dimension_rules · wall_side_mm"
    hidden = item_card(db_session, viewer_of(cs), "common/wall-side", today=TODAY)["external"][0]
    assert hidden["value"] is None and hidden["value_hidden"] is True  # 관리 범위 밖은 값 칸 없음
    db_session.add(SystemSetting(setting_key=rs.DIMENSION_RULES_KEY, setting_value={"wall_side_mm": 140}))
    db_session.flush()
    chip = item_card(db_session, viewer_of(admin), "common/wall-side", today=TODAY)["external"][0]
    assert chip["value"] == "140"  # 설정 줄이 생기면 그 값
