"""master brain 읽기 — 보기 범위는 찾는 단계에서(결과 · 수 · 이웃 모두 — 설계서 4절 · 12절) · 이웃 걸음 · 상한 · 종류.

음성 대조군을 같은 모집단에서 같이 센다: 숨긴 항목은 ADMIN 에게는 보이고(있다는 대조), 볼 수 없는 사람에게는 결과 · 수 0.
"""

from __future__ import annotations

from types import SimpleNamespace

from db import db_session
from foms.services.brain.read import count_items, current_item, item_history, neighbours, search
from foms.services.brain.scope import NOBODY, scope_clause, viewer_of
from models import User
from tests.support.brain_support import create, link, person


def _graph():
    """제품 둘 · 규칙 셋(범위 모두 · 도면팀 · 가격 재량) · 관리 항목 하나 — 링크로 잇는다."""
    admin = person(db_session, "rd_admin")
    create(db_session, admin, "common/door", name="여닫이 문짝")
    create(db_session, admin, "common/slide", name="미닫이 문짝")
    create(db_session, admin, "common/fit", item_type="build_rule", name="문짝 맞춤 규칙")
    create(db_session, admin, "drawing/rule", item_type="drawing_rule", layer="drawing", brand="COMMON",
           name="문짝 도면 규칙", visibility="team:DRAWING")
    create(db_session, admin, "common/discount", item_type="price_rule", name="문짝 재량 규칙", visibility="price",
           checked_at="2026-10-20",
           payload={"doc_id": "discount", "approved_by": "합성", "approved_at": "2026-10-20"})
    create(db_session, admin, "common/ask", item_type="question", name="문짝 물어볼 것", visibility="admin")
    link(db_session, admin, "applies_to", "common/fit", "common/door")
    link(db_session, admin, "applies_to", "drawing/rule", "common/door")
    link(db_session, admin, "applies_to", "drawing/rule", "common/slide")
    link(db_session, admin, "applies_to", "common/discount", "common/door")
    db_session.commit()
    return admin


def _viewers():
    return {
        "admin": viewer_of(db_session.query(User).filter_by(username="rd_admin").one()),
        "cs": viewer_of(person(db_session, "rd_cs", role="STAFF", team="CS")),
        "drawing": viewer_of(person(db_session, "rd_dr", role="VIEWER", team="DRAWING")),
        "partner": viewer_of(person(db_session, "rd_partner", role="PARTNER", team="DRAWING", partner_org_id=7)),
        "off": viewer_of(person(db_session, "rd_off", role="ADMIN", active=False)),
    }


def test_visibility_is_filtered_in_results_and_counts(app):
    _graph()
    v = _viewers()
    every = ["common/ask", "common/discount", "common/door", "common/fit", "common/slide", "drawing/rule"]
    seen = {name: sorted(i["key"] for i in search(db_session, viewer, "문짝", limit=50)["items"])
            for name, viewer in v.items()}
    assert seen["admin"] == every  # 대조군: 숨긴 항목도 모집단에 있다
    assert seen["cs"] == ["common/door", "common/fit", "common/slide"]
    assert seen["drawing"] == ["common/door", "common/fit", "common/slide", "drawing/rule"]
    assert seen["partner"] == seen["off"] == []
    totals = {name: search(db_session, viewer, "문짝", limit=1)["total"] for name, viewer in v.items()}
    assert totals == {"admin": 6, "cs": 3, "drawing": 4, "partner": 0, "off": 0}  # 수도 범위대로(상한과 무관)
    assert count_items(db_session, v["cs"]) == {"total": 3, "types": {"build_rule": 1, "product_line": 2}}
    assert count_items(db_session, v["admin"])["types"]["price_rule"] == 1
    assert count_items(db_session, v["cs"])["types"].get("price_rule", 0) == 0  # 가격 재량 항목 수도 새지 않는다
    assert count_items(db_session, v["partner"]) == {"total": 0, "types": {}}
    assert current_item(db_session, v["cs"], "common/discount") is None
    assert current_item(db_session, v["admin"], "common/discount")["visibility"] == "price"
    assert item_history(db_session, v["cs"], "common/ask") == []
    assert len(item_history(db_session, v["admin"], "common/ask")) == 1


def test_neighbour_counts_skip_items_the_viewer_cannot_see(app):
    _graph()
    v = _viewers()
    admin = neighbours(db_session, v["admin"], "common/door")
    cs = neighbours(db_session, v["cs"], "common/door")
    assert [i["key"] for i in admin["items"]] == ["common/discount", "common/fit", "drawing/rule"]
    assert admin["counts"] == {"applies_to": 3} and admin["total"] == 3
    assert [i["key"] for i in cs["items"]] == ["common/fit"]  # 가격 재량 · 도면팀 항목은 결과에서 0
    assert cs["counts"] == {"applies_to": 1} and cs["total"] == 1  # 수에서도 0
    assert neighbours(db_session, v["cs"], "drawing/rule") is None  # 볼 수 없는 시작 항목
    assert neighbours(db_session, v["partner"], "common/door") is None


def test_neighbours_depth_limit_and_kinds(app):
    _graph()
    v = _viewers()
    one = neighbours(db_session, v["admin"], "common/slide", depth=1)
    assert [(i["key"], i["depth"]) for i in one["items"]] == [("drawing/rule", 1)]
    two = neighbours(db_session, v["admin"], "common/slide", depth=2)
    assert [(i["key"], i["depth"]) for i in two["items"]] == [("drawing/rule", 1), ("common/door", 2)]
    capped = neighbours(db_session, v["admin"], "common/slide", depth=9)  # 걸음은 2 까지
    assert capped["total"] == 2
    # 도면팀 규칙을 볼 수 없는 사람은 그 항목을 지나 2걸음 이웃에도 닿지 않는다
    assert neighbours(db_session, v["cs"], "common/slide", depth=2)["total"] == 0
    limited = neighbours(db_session, v["admin"], "common/door", depth=2, limit=1)
    assert len(limited["items"]) == 1 and limited["total"] == 4  # 상한은 목록만, 수는 전체(문 → 규칙들 → 미닫이)
    assert neighbours(db_session, v["admin"], "common/door", kinds=["supersedes"])["total"] == 0
    assert limited["items"][0]["via"] == ["applies_to"]


def test_scope_clause_closes_for_nobody_and_partners():
    assert str(scope_clause(NOBODY, SimpleNamespace())) == "false"
    partner = viewer_of(SimpleNamespace(id=1, role="PARTNER", team=None, is_active=True, partner_org_id=None))
    assert not partner.internal
