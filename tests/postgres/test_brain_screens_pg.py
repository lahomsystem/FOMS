"""'회사 지식' 화면 읽기 PostgreSQL 레인 — 찾기 묶음(창 함수 + pg_trgm 비슷함 순) · 지식 표(확인 날 없음 먼저 · 열린 제안 상관
부분 질의) · 카드 링크(두 방향 UNION + 창 함수) · 판 수(범위로 거른 반영 UNION). SQLite 메인 레인과 같은 답인지 진짜
PostgreSQL 에서 본다. ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다. 합성 항목만.
"""

from __future__ import annotations

from foms.services.brain.browse import TableQuery, search_grouped, table_page
from foms.services.brain.card import item_card
from foms.services.brain.release_view import release_diff, release_page
from foms.services.brain.scope import viewer_of
from models import User
from tests.support.brain_screen_support import TODAY, world
from tests.support.brain_support import create


def test_screen_reads_filter_by_scope_on_postgres(pg_session):
    who = {name: viewer_of(user) for name, user in world(pg_session).items()}
    admin = search_grouped(pg_session, who["admin"], "문짝", today=TODAY)
    cs = search_grouped(pg_session, who["cs_mgr"], "문짝", today=TODAY)
    assert admin["total"] == 7 and cs["total"] == 4  # 초안 · 은퇴는 기본 읽기 거르기가 뺀다(점검 지금 1)
    assert [g["type"] for g in cs["groups"]] == ["product_line", "build_rule"]
    # 부분 일치가 아니라 비슷함(%)으로만 닿는 찾기도 묶음에 들어온다(레인 클러스터는 C 로케일이라 영문 합성 이름으로 본다)
    create(pg_session, pg_session.query(User).filter_by(username="bs_admin").one(), "common/hinge",
           name="hinged door panel")
    typo = search_grouped(pg_session, who["admin"], "hinged door panle", today=TODAY)
    assert [(g["type"], [i["key"] for i in g["items"]]) for g in typo["groups"]] == [("product_line", ["common/hinge"])]

    checked = table_page(pg_session, who["admin"], TableQuery("build_rule", sort="checked"), today=TODAY)
    assert [r["key"] for r in checked["rows"]] == ["common/draft", "common/old", "common/fit", "common/fresh"]
    needs = table_page(pg_session, who["admin"], TableQuery("build_rule", check="needs_check"), today=TODAY)
    assert [r["key"] for r in needs["rows"]] == ["common/fit"]
    assert table_page(pg_session, who["cs_mgr"], TableQuery("price_rule"), today=TODAY)["total"] == 0

    card = item_card(pg_session, who["cs_mgr"], "common/door", today=TODAY)
    applies = next(g for g in card["links"] if (g["kind"], g["direction"]) == ("applies_to", "in"))
    assert applies["count"] == 1 and [i["key"] for i in applies["items"]] == ["common/fit"]
    assert len(card["external"]) == 2

    admin_rel, cs_rel = release_page(pg_session, who["admin"]), release_page(pg_session, who["cs_mgr"])
    admin_common = next(x for x in admin_rel["items"][0]["layers"] if x["layer"] == "common")
    cs_common = next(x for x in cs_rel["items"][0]["layers"] if x["layer"] == "common")
    assert (admin_common["counts"]["create"], cs_common["counts"]["create"]) == (9, 7)  # 위 영문 합성 항목 포함
    keys = {c["key"] for layer in release_diff(pg_session, who["cs_mgr"], 1)["layers"] for c in layer["changes"]}
    assert "common/discount" not in keys and "common/door" in keys
