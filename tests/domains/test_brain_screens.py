"""'회사 지식' 화면 읽기(설계서 2026-11-02-haud-master-brain 7.5 화면 1 · 2 · 3 · 6 · 7 · ⑤-2) — 찾기 묶음 · 지식 표 ·
카드 · 유형 지도 · 판. **보기 범위는 모든 질의 · 수에서** 거른다(4절 · 12절).

음성 대조군을 같은 모집단에서 같이 센다: 숨긴 항목(가격 재량 · 관리 · 도면팀)은 ADMIN 에게 보이고(있다는 대조), CS 팀장
에게는 결과 · 유형별 수 · 링크 수 · 판 수에서 0. 합성 항목만(금액 · 손님 글 · 직원 이름 없음).
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.brain import browse
from foms.services.brain.browse import (
    TableQuery, TableQueryError, parse_table_query, search_grouped, table_page, type_map, type_map_data,
)
from foms.services.brain.card import item_card
from foms.services.brain.constants import ALLOWED_LINKS, LINK_KINDS, TYPES
from foms.services.brain.display import TYPE_DISPLAY
from foms.services.brain.release_view import release_diff, release_page
from foms.services.brain.scope import viewer_of
from models import User
from tests.support.brain_screen_support import TODAY, world
from foms.services.brain.external import catalog_source
from tests.support.brain_support import NOW, create, synth_catalog


@pytest.fixture
def who(app):
    people = world(db_session)
    return {name: viewer_of(user) for name, user in people.items()}


def _keys(rows):
    return [r["key"] for r in rows]


def test_search_groups_by_type_and_counts_only_what_the_viewer_may_see(who):
    admin = search_grouped(db_session, who["admin"], "문짝", today=TODAY)
    cs = search_grouped(db_session, who["cs_mgr"], "문짝", today=TODAY)
    drawing = search_grouped(db_session, who["dr_mgr"], "문짝", today=TODAY)
    assert [g["type"] for g in admin["groups"]] == ["product_line", "build_rule", "price_rule", "drawing_rule",
                                                    "question"]  # 유형 차례(TYPES)
    assert admin["total"] == 9
    assert [g["type"] for g in cs["groups"]] == ["product_line", "build_rule"]  # 가격 재량 · 관리 · 도면팀 0
    assert cs["total"] == 6
    assert "drawing_rule" in [g["type"] for g in drawing["groups"]] and drawing["total"] == 7
    rules = next(g for g in admin["groups"] if g["type"] == "build_rule")
    flags = {i["key"]: (i["status"], i["stale"], i["needs_check"]) for i in rules["items"]}
    assert flags["common/fit"] == ("active", True, True)  # 낡음 + 열린 제안
    assert flags["common/draft"][0] == "draft" and flags["common/old"][0] == "retired"
    assert flags["common/fresh"] == ("active", False, False)  # 대조군
    assert search_grouped(db_session, who["admin"], "   ", today=TODAY) == {"query": "", "total": 0, "groups": []}


def test_search_caps_items_per_type_but_keeps_the_full_count(who):
    actor = db_session.query(User).filter_by(username="bs_admin").one()
    for n in "가나다라마바":
        create(db_session, actor, f"common/extra-{ord(n)}", name=f"문짝 더 {n}")
    db_session.commit()
    got = search_grouped(db_session, who["admin"], "문짝", today=TODAY, per_type=5)
    lines = next(g for g in got["groups"] if g["type"] == "product_line")
    assert len(lines["items"]) == 5 and lines["count"] == 8


def test_table_filters_sorts_and_pages_within_scope(who):
    rules = table_page(db_session, who["admin"], TableQuery("build_rule"), today=TODAY)
    assert _keys(rules["rows"])[:2] == ["common/fresh", "common/fit"]  # 쓰인 횟수 많은 순
    assert rules["total"] == 4
    checked = table_page(db_session, who["admin"], TableQuery("build_rule", sort="checked"), today=TODAY)
    assert _keys(checked["rows"]) == ["common/draft", "common/old", "common/fit", "common/fresh"]  # 확인 날 없음 먼저
    stale = table_page(db_session, who["admin"], TableQuery("build_rule", check="stale"), today=TODAY)
    assert _keys(stale["rows"]) == ["common/fit"]
    needs = table_page(db_session, who["admin"], TableQuery("build_rule", check="needs_check"), today=TODAY)
    assert _keys(needs["rows"]) == ["common/fit"] and needs["rows"][0]["needs_check"] is True
    assert _keys(table_page(db_session, who["admin"], TableQuery("build_rule", status="retired"),
                            today=TODAY)["rows"]) == ["common/old"]
    paged = table_page(db_session, who["admin"], TableQuery("build_rule", sort="name", page=2, per_page=3), today=TODAY)
    assert paged["page"] == 2 and paged["pages"] == 2 and len(paged["rows"]) == 1
    beyond = table_page(db_session, who["admin"], TableQuery("build_rule", page=99), today=TODAY)
    assert beyond["page"] == 1  # 쪽 수를 넘으면 마지막 쪽
    hidden = table_page(db_session, who["cs_mgr"], TableQuery("price_rule"), today=TODAY)
    assert hidden["total"] == 0 and hidden["rows"] == []
    assert "price_rule" not in hidden["type_counts"] and "question" not in hidden["type_counts"]
    assert table_page(db_session, who["admin"], TableQuery("price_rule"), today=TODAY)["total"] == 1  # 대조군


def test_table_query_accepts_only_listed_values():
    query = parse_table_query({"type": "build_rule", "layer": "common", "check": "stale", "sort": "checked",
                               "page": "2", "per_page": "999"})
    assert (query.layer, query.check, query.sort, query.page, query.per_page) == ("common", "stale", "checked", 2, 50)
    assert parse_table_query({"type": "spec", "brand": ""}).brand is None
    for bad in ({"type": "nope"}, {}, {"type": "spec", "layer": "kitchen"}, {"type": "spec", "sort": "random"},
                {"type": "spec", "check": "all"}):
        with pytest.raises(TableQueryError):
            parse_table_query(bad)


def test_card_groups_links_hides_out_of_scope_ends_and_shows_external_refs(who):
    with catalog_source(synth_catalog):
        admin = item_card(db_session, who["admin"], "common/door", today=TODAY)
    groups = {(g["kind"], g["direction"]): g for g in admin["links"]}
    assert groups[("applies_to", "in")]["count"] == 3
    assert sorted(_keys(groups[("applies_to", "in")]["items"])) == ["common/discount", "common/fit", "drawing/rule"]
    assert [(e["kind"], e["ref"], e["ext_type"], e["exists"]) for e in admin["external"]] == [
        ("value_from", "calc:product/7", "ext_calculator", True),
        ("value_from", "setting:drawing_wizard_bom_rules", "ext_setting", True)]
    assert admin["copies"] == ["매크로 문짝 안내", "스토어 상세 문짝 칸"]
    assert "payload" not in admin["item"] and admin["item"]["version"] == 2
    assert [h["version"] for h in admin["history"]] == [2, 1]
    assert admin["history"][0]["changed"] == ["text"] and admin["history"][1]["changed"] == []
    assert admin["approver"] == "합성" and admin["created_by"] == "합성"
    cs = item_card(db_session, who["cs_mgr"], "common/door", today=TODAY)
    cs_groups = {(g["kind"], g["direction"]): g for g in cs["links"]}
    assert _keys(cs_groups[("applies_to", "in")]["items"]) == ["common/fit"]
    assert cs_groups[("applies_to", "in")]["count"] == 1  # 수에서도 0
    fit = item_card(db_session, who["cs_mgr"], "common/fit", today=TODAY)
    assert fit["item"]["stale"] is True and fit["item"]["needs_check"] is True and fit["item"]["open_changes"] == 1
    assert {(g["kind"], g["direction"]) for g in fit["links"]} == {("applies_to", "out"), ("requires", "out")}


def test_card_is_none_for_hidden_and_missing_items_alike(who):
    assert item_card(db_session, who["cs_mgr"], "common/discount", today=TODAY) is None
    assert item_card(db_session, who["cs_mgr"], "common/nothing", today=TODAY) is None
    assert item_card(db_session, who["dr_mgr"], "drawing/rule", today=TODAY) is not None  # 대조군: 자기 팀 범위
    assert item_card(db_session, who["admin"], "common/discount", today=TODAY)["item"]["visibility"] == "price"


def test_type_map_counts_by_scope_and_lists_every_type_and_link_kind(who):
    admin, cs = type_map(db_session, who["admin"]), type_map(db_session, who["cs_mgr"])
    counts = {t["type"]: t["count"] for g in admin["groups"] for t in g["types"]}
    cs_counts = {t["type"]: t["count"] for g in cs["groups"] for t in g["types"]}
    assert set(TYPES) <= set(counts) and len(counts) == len(TYPES) + 2  # 바깥 정본 둘
    assert counts["price_rule"] == 1 and cs_counts["price_rule"] == 0 and cs_counts["question"] == 0
    assert admin["total"] == 9 and cs["total"] == 6
    assert [link["kind"] for link in admin["links"]] == list(LINK_KINDS)
    for link in admin["links"]:
        starts, ends = ALLOWED_LINKS[link["kind"]]
        assert len(link["pairs"]) == len(starts) * len(ends)
    evidence = next(link for link in admin["links"] if link["kind"] == "evidence_of")
    assert evidence["from"] == [{"group": "observation"}]
    assert evidence["to"] == [{"group": "common"}, {"group": "cs"}, {"group": "drawing"}]
    assert set(admin["display"]["types"]) == set(TYPE_DISPLAY)


def test_type_map_data_is_pure_and_compresses_whole_groups():
    data = type_map_data({"spec": 3})
    assert data["total"] == 3
    copy_in = next(link for link in data["links"] if link["kind"] == "copy_in")
    assert copy_in["from"] == [{"group": "common"}] and copy_in["to"] == [{"type": "template"}]
    assert browse.compress_types(["case", "spec"]) == [{"type": "spec"}, {"type": "case"}]


def test_releases_count_only_changes_the_viewer_may_see(who):
    actor = db_session.query(User).filter_by(username="bs_admin").one()
    create(db_session, actor, "common/discount2", item_type="price_rule", name="숨은 재량 규칙", visibility="price",
           now=NOW + datetime.timedelta(days=1), checked_at="2026-11-03",
           payload={"doc_id": "discount2", "approved_by": "합성", "approved_at": "2026-11-03"})
    db_session.commit()
    admin = release_page(db_session, who["admin"])
    cs = release_page(db_session, who["cs_mgr"])
    assert [r["number"] for r in admin["items"]] == [2, 1] and admin["total"] == 2
    assert [r["number"] for r in cs["items"]] == [1] and cs["total"] == 1  # 숨은 바뀜뿐인 판은 안 나온다
    admin_common = next(layer for layer in admin["items"][1]["layers"] if layer["layer"] == "common")
    cs_common = next(layer for layer in cs["items"][0]["layers"] if layer["layer"] == "common")
    assert admin_common["counts"]["create"] == 8 and cs_common["counts"]["create"] == 6
    assert admin_common["counts"]["link_add"] == 5 and cs_common["counts"]["link_add"] == 4
    assert release_diff(db_session, who["cs_mgr"], 2) is None
    diff = release_diff(db_session, who["cs_mgr"], 1)
    keys = {c["key"] for layer in diff["layers"] for c in layer["changes"]}
    assert "common/discount" not in keys and "common/ask" not in keys and "drawing/rule" not in keys
    assert {"common/door", "common/fit"} <= keys
    link_rows = [c for layer in diff["layers"] for c in layer["changes"] if c["link_kind"] == "value_from"]
    assert {c["link_to"] for c in link_rows} == {"calc:product/7", "setting:drawing_wizard_bom_rules"}
    admin_keys = {c["key"] for layer in release_diff(db_session, who["admin"], 1)["layers"] for c in layer["changes"]}
    assert {"common/discount", "common/ask", "drawing/rule"} <= admin_keys  # 대조군
