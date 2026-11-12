"""견적 계산기 정본 → 제품 라인 · 옵션 만들기 제안(설계서 2026-11-12 온톨로지 4절 1 · D179 · D180).

계획에 금액이 없음 · 키 · 브랜드 · 값 단위 · 값 방식 · 다시 돌리면 0 · 반영 전엔 링크 대기 → 반영 뒤 다음 차례에 계산기 정본
``value_from`` · 하우드 제품은 하우드 브랜드. 합성 계산기만(꾸민 수 · 실제 이름 없음).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainLink
from foms.services.brain.apply import apply_change
from foms.services.brain.catalog_plan import PLAN_SCHEMA, catalog_plan
from foms.services.brain.external import catalog_source
from foms.services.brain.plan_proposals import file_plan
from foms.services.brain.store import current_object
from foms.services.wdcalculator.catalog import Catalog
from tests.support.brain_support import NOW, person

CATALOG = Catalog(
    products=({"id": 1, "name": "  합성\t제품  하나 ", "pricing_type": "30cm", "price_30cm": 123457, "price_1cm": 4111},
              {"id": 7, "name": "하우드합성 문짝", "pricing_type": "1m", "price_1m": 765433},
              {"id": 9, "name": "", "pricing_type": "30cm"}),  # 이름 없는 제품은 넘긴다
    option_categories=({"id": 3, "name": "합성 묶음", "options": [{"id": 5, "name": "합성 손잡이", "price": 98761},
                                                              {"id": 6, "name": "합성 기본 선반", "price": 0}]},))


def synth():
    return CATALOG


@pytest.fixture
def admin(app):
    return person(db_session, "catalog_plan_admin")


def run(apply=True):
    with catalog_source(synth):
        out = file_plan(db_session, catalog_plan(CATALOG), brand="LAHOM", apply=apply, now=NOW)
    db_session.commit()
    return out


def test_plan_has_no_amounts_and_stable_keys():
    plan = catalog_plan(CATALOG)
    text = json.dumps(plan, ensure_ascii=False)
    assert plan["schema"] == PLAN_SCHEMA and not plan["items"] and not plan["conflicts"]
    for amount in ("123457", "4111", "765433", "98761"):
        assert amount not in text  # 금액은 계산기만(D179)
    got = {row["key"]: row for row in plan["new_items"]}
    assert sorted(got) == ["option/3-5", "option/3-6", "product_line/haud-7", "product_line/lahom-1"]
    assert got["product_line/lahom-1"]["pref_label"] == "합성 제품 하나"  # 탭 · 겹친 빈칸 정리
    assert (got["product_line/haud-7"]["brand"], got["product_line/haud-7"]["props"]) == ("HAUD", {"price_unit": "1m"})
    assert got["option/3-6"]["props"]["price_kind"] == "included" and got["option/3-5"]["props"]["price_kind"] == "extra"
    assert got["option/3-5"]["value_from_hint"] == ["calc:option/3:5"]


def test_proposals_then_calculator_links_after_approval(admin):
    dry = run(apply=False)
    assert dry["filed"] == {"create": 4} and db_session.scalar(select(BrainChange.id)) is None  # 모의 실행은 쓰기 0
    out = run()
    assert out["filed"] == {"create": 4} and out["deferred"] == {"awaiting_create": 4}
    rows = db_session.execute(select(BrainChange).where(BrainChange.status == "open")).scalars().all()
    assert {(c.item_key, c.item_type, c.brand) for c in rows} == {
        ("product_line/lahom-1", "product_line", "LAHOM"), ("product_line/haud-7", "product_line", "HAUD"),
        ("option/3-5", "option", "COMMON"), ("option/3-6", "option", "COMMON")}
    assert run()["filed_total"] == 0  # 다시 돌리면 0
    with catalog_source(synth):
        for change in rows:
            apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    line = current_object(db_session, "product_line/lahom-1")
    assert (line.name, line.payload["price_unit"]) == ("합성 제품 하나", "30cm")  # 대표 이름 = 항목 이름
    assert current_object(db_session, "option/3-6").payload["option_kind"] == "part"
    after = run()
    assert after["filed"] == {"link_add:value_from": 4} and after["deferred"] == {}
    links = db_session.execute(select(BrainChange).where(BrainChange.op == "link_add")).scalars().all()
    with catalog_source(synth):
        for change in links:
            apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    ends = {(l.from_key, l.to_key) for l in db_session.execute(select(BrainLink)).scalars()}
    assert ("product_line/lahom-1", "calc:product/1") in ends and ("option/3-5", "calc:option/3:5") in ends


def _script(script, capsys, source, *argv):
    with catalog_source(source):
        code = script.run(list(argv))
    printed = capsys.readouterr().out
    return code, printed, json.loads(printed)


def test_script_from_catalog_dry_run_then_apply_prints_counts_only(admin, capsys):
    from tests.domains.test_brain_plan_proposals import load_script
    script = load_script()
    code, _printed, out = _script(script, capsys, synth, "--from-catalog")
    assert code == 0 and out["applied"] is False and out["filed"] == {"create": 4}
    code, printed, out = _script(script, capsys, synth, "--from-catalog", "--apply")
    assert code == 0 and out["applied"] is True and "합성" not in printed  # 출력은 수만(이름 없음)
    evidence = db_session.execute(select(BrainChange.evidence)).scalars().first()
    assert evidence[0].startswith("plan:calc_catalog_plan#")
    code, _printed, out = _script(script, capsys, lambda: None, "--from-catalog")
    assert (code, out["error"]) == (1, "CATALOG_UNREADABLE")
