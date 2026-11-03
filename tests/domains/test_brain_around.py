"""이웃 찾기(Search Around — 설계서 7.7 · D105) · 뇌 보기 바탕 점(7.6) · 이웃 지도 · 뇌 보기 탭 화면(7.5 화면 9).

- 걸음 · 상한 · 종류 거르기 · 꼴 밖 물음 400 · 볼 수 없는 시작 404.
- **보기 범위는 점 · 선 · 수 모두에**: 같은 모집단(문짝 둘레)에서 ADMIN 은 가격 재량 · 도면팀 항목과 그 선 · 수를 보고(대조군),
  상담팀 MANAGER 는 셋 다 0. 바탕 점도 같다(이름은 싣지 않는다).
- 카드 화면: 이웃 지도 1걸음 목록은 서버가 그린다(진짜 화면), 뇌 보기 탭은 숨겨 그린다. 합성 항목 · 합성 계정만.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.brain.around import AroundQuery, AroundQueryError, brain_points, parse_around, search_around
from foms.services.brain.scope import viewer_of
from tests.support.brain_screen_support import TODAY, world


@pytest.fixture
def made(app):
    users = world(db_session)
    return {"who": {name: viewer_of(u) for name, u in users.items()}, "ids": {name: u.id for name, u in users.items()}}


@pytest.fixture
def who(made):
    return made["who"]


@pytest.fixture
def people(made):
    return made["ids"]  # 요청마다 세션이 닫혀 객체 대신 번호


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _around(viewer, key="common/door", **kw):
    return search_around(db_session, viewer, AroundQuery(key=key, **kw), today=TODAY)


def test_depth_limit_and_kind_filter(who):
    one = _around(who["admin"])
    assert [(i["key"], i["depth"]) for i in one["items"]] == [
        ("common/discount", 1), ("common/fit", 1), ("drawing/rule", 1)]
    assert one["counts"] == {"applies_to": 3} and one["total"] == 3 and not one["truncated"]
    assert one["start"]["key"] == "common/door" and "text" not in one["start"] and "payload" not in one["items"][0]
    two = _around(who["admin"], depth=2)
    assert [(i["key"], i["depth"]) for i in two["items"]][-1] == ("common/slide", 2)  # 맞춤 규칙 → 필요 → 미닫이
    assert two["counts"] == {"applies_to": 3, "requires": 1} and two["total"] == 4
    capped = _around(who["admin"], depth=2, limit=2)
    assert len(capped["items"]) == 2 and capped["total"] == 4 and capped["truncated"]
    only = _around(who["admin"], kinds=("requires",), depth=2)
    assert only["total"] == 0 and only["items"] == [] and only["edges"] == []  # 문짝에서 '필요'로 바로 닿는 것 없음
    fit = _around(who["admin"], key="common/fit", kinds=("requires",))
    assert [i["key"] for i in fit["items"]] == ["common/slide"] and fit["kinds"] == ["requires"]
    # 선 — 시작 + 실은 항목 사이만(종류 · 양 끝)
    assert {(e["kind"], e["from"], e["to"]) for e in two["edges"]} == {
        ("applies_to", "common/fit", "common/door"), ("applies_to", "drawing/rule", "common/door"),
        ("applies_to", "common/discount", "common/door"), ("requires", "common/fit", "common/slide")}


def test_scope_filters_nodes_edges_and_counts_with_a_negative_control(who):
    admin, cs = _around(who["admin"], depth=2), _around(who["cs_mgr"], depth=2)
    hidden = {"common/discount", "drawing/rule"}
    assert hidden <= {i["key"] for i in admin["items"]}  # 대조군: 같은 모집단에 있다
    assert hidden <= {k for e in admin["edges"] for k in (e["from"], e["to"])}
    assert {i["key"] for i in cs["items"]} == {"common/fit", "common/slide"}  # 점 0
    assert not hidden & {k for e in cs["edges"] for k in (e["from"], e["to"])}  # 선 0
    assert cs["counts"] == {"applies_to": 1, "requires": 1} and cs["total"] == 2  # 수 0
    drawing = _around(who["dr_mgr"])
    assert {i["key"] for i in drawing["items"]} == {"common/fit", "drawing/rule"}  # 도면팀은 도면 규칙을 본다
    assert _around(who["cs_mgr"], key="drawing/rule") is None  # 볼 수 없는 시작 항목


def test_points_are_scope_filtered_without_names(who):
    admin, cs = brain_points(db_session, who["admin"], today=TODAY), brain_points(db_session, who["cs_mgr"], today=TODAY)
    admin_keys, cs_keys = {r[0] for r in admin["rows"]}, {r[0] for r in cs["rows"]}
    assert {"common/discount", "common/ask", "drawing/rule"} <= admin_keys  # 대조군
    assert not {"common/discount", "common/ask", "drawing/rule"} & cs_keys
    assert admin["total"] == 9 and cs["total"] == 6 and not admin["capped"]
    assert all(len(r) == 4 and isinstance(r[1], int) for r in admin["rows"])  # 키 · 유형 번호 · 표시 · 쓰인 횟수 — 이름 없음
    flags = {r[0]: r[2] for r in admin["rows"]}
    assert flags["common/draft"] == 1 and flags["common/old"] == 2 and flags["common/fit"] == 4
    assert admin["rows"][0][0] == "common/fresh"  # 쓰인 횟수 많은 순
    small = brain_points(db_session, who["admin"], today=TODAY, cap=2)
    assert len(small["rows"]) == 2 and small["total"] == 9 and small["capped"]


def test_parse_rejects_out_of_shape_queries():
    assert parse_around({"key": "common/door"}) == AroundQuery("common/door")
    assert parse_around({"key": "common/door", "kinds": "requires,applies_to,requires", "depth": "2", "limit": "5"}) == (
        AroundQuery("common/door", ("requires", "applies_to"), 2, 5))
    for bad in ({"key": "Bad Key"}, {"key": "common/door", "depth": "3"}, {"key": "common/door", "depth": "0"},
                {"key": "common/door", "kinds": "nope"}, {"key": "common/door", "kinds": ","},
                {"key": "common/door", "limit": "999"}, {"key": "common/door", "limit": "-1"}):
        with pytest.raises(AroundQueryError):
            parse_around(bad)


def test_api_answers_in_the_shared_shape_and_hides_out_of_scope(app, people):
    admin, cs = _client(app, people["admin"]), _client(app, people["cs_mgr"])
    ok = admin.get("/api/brain/around?key=common/door&depth=2&limit=50").get_json()
    assert ok["success"] is True and ok["error"] is None and ok["data"]["total"] == 4
    seen = cs.get("/api/brain/around?key=common/door&depth=2").get_json()["data"]
    assert "common/discount" not in str(seen) and "drawing/rule" not in str(seen)
    assert cs.get("/api/brain/around?key=drawing/rule").status_code == 404
    assert admin.get("/api/brain/around?key=common/door&depth=3").get_json() == {
        "success": False, "data": None, "error": "고르기 값이 맞지 않습니다."}
    assert _client(app, people["cs_staff"]).get("/api/brain/around?key=common/door&depth=3").status_code == 404
    points = cs.get("/api/brain/points").get_json()["data"]
    assert points["total"] == 6 and "문짝" not in str(points)  # 이름 없음
    assert admin.get("/api/brain/quality").get_json()["success"] is True


def test_card_page_renders_the_neighbour_list_and_hides_the_3d_tab(app, people):
    html = _client(app, people["cs_mgr"]).get("/brain/items/common/door").get_data(as_text=True)
    assert 'data-brain-nb-key="common/fit"' in html  # 서버가 그린 1걸음 목록(진짜 화면)
    assert "drawing/rule" not in html and "문짝 재량 규칙" not in html  # 범위 밖은 목록에도 없다
    assert "연결된 지식(1)" in html and 'hidden data-brain3d-tab-item' in html
    assert 'data-three-url="/static/vendor/three-0.187.0/three.module.js"' in html  # 폴더가 판 — ?v= 없음
    admin = _client(app, people["admin"]).get("/brain/items/common/door").get_data(as_text=True)
    assert "연결된 지식(3)" in admin and 'data-brain-nb-key="drawing/rule"' in admin  # 대조군
