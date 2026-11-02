"""Palantir 꼴 맞춤 D105(설계서 7.7) — 연결 개수 규칙 · 유효 기간으로 읽기 · 바깥 정본 가리킴 실재 확인 · 카드의 지금 값.

1. 연결 개수 — 최대는 반영 때 막고(제안은 받는다), 최소는 카드 '빠진 링크' · 품질 수로 알린다(보기 범위 안에서 센다).
2. 유효 기간 — 끝 날이 지난 항목 · 링크는 찾기 · 표 · 수 · 이웃 · 바탕 점에서 빠지고, 키로 바로 연 카드만 ``ended``.
3. 바깥 정본 — ``calc:`` · ``setting:`` 끝이 없으면 제안 · 반영 모두 막는다(계산기 정본을 못 읽어도 막는다). 빼기는 막지 않는다.
4. 카드의 지금 값 — 계산기 값(가격)은 가격 재량 범위를 볼 수 있는 사람만, 설정 값은 관리 범위만(화면 HTML 까지).
음성 대조군을 같은 모집단에서 같이 센다. 합성 항목 · 합성 계산기 정본(꾸민 수) · 합성 계정만.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.brain.apply import apply_change
from foms.services.brain.around import AroundQuery, brain_points, search_around
from foms.services.brain.browse import TableQuery, search_grouped, table_page
from foms.services.brain.card import item_card
from foms.services.brain.constants import ALLOWED_LINKS, LINK_CARDINALITY, cardinality
from foms.services.brain.errors import BrainExternalRefError, BrainLinkLimitError
from foms.services.brain.external import catalog_source
from foms.services.brain.proposals import Proposer, propose_link
from foms.services.brain.quality import missing_links, quality_counts
from foms.services.brain.read import count_items
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_link
from models import SystemSetting
from tests.support.brain_screen_support import TODAY, world
from tests.support.brain_support import NOW, REASON, create, link, setting, synth_catalog

DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}


@pytest.fixture
def made(app):
    users = world(db_session)
    return {"users": users, "who": {name: viewer_of(u) for name, u in users.items()},
            "ids": {name: u.id for name, u in users.items()}}


def _price_rule(admin, key="common/shipping", **extra):
    return create(db_session, admin, key, item_type="price_rule", name="합성 운임 규칙", checked_at="2026-10-20",
                  visibility="price", payload={"doc_id": key.split("/")[-1], **DOC}, **extra)


def _propose(admin, kind, src, dst, **values):
    with catalog_source(synth_catalog):
        return propose_link(db_session, op="link_add", kind=kind, from_key=src, to_key=dst, reason=REASON,
                            proposer=Proposer.user(admin.id), now=NOW, values=values or None)


def _apply(admin, change):
    with catalog_source(synth_catalog):
        return apply_change(db_session, change.id, actor=admin, now=NOW)


# ── 1. 연결 개수 ─────────────────────────────────────────────────────────
def test_cardinality_table_uses_only_allowed_pairs():
    for (from_type, kind), (low, high) in LINK_CARDINALITY.items():
        assert from_type in ALLOWED_LINKS[kind][0], (from_type, kind)
        assert 0 <= low and (high is None or high >= max(low, 1))
    assert cardinality("price_rule", "value_from") == (1, 1) and cardinality("spec", "value_from") == (0, 1)
    assert cardinality("product_line", "value_from") == (0, None)  # 적지 않은 짝 — 끝없음


def test_max_is_blocked_at_apply_even_when_both_proposals_were_accepted(made):
    admin = made["users"]["admin"]
    _price_rule(admin)
    first = _propose(admin, "value_from", "common/shipping", "calc:product/1")
    second = _propose(admin, "value_from", "common/shipping", "calc:product/7")  # 제안은 받는다(빼고 더하는 순서 자유)
    _apply(admin, first)
    with pytest.raises(BrainLinkLimitError) as caught:
        _apply(admin, second)
    assert caught.value.code == "BRAIN_LINK_LIMIT" and caught.value.limit == 1
    assert current_link(db_session, "value_from", "common/shipping", "calc:product/7") is None
    # 대조군: 상한 없는 짝(제품 라인 → 계산기 · 설정)은 둘째도 들어간다(world 의 문짝이 이미 둘)
    assert current_link(db_session, "value_from", "common/door", "setting:drawing_wizard_bom_rules") is not None
    # 규격은 하나까지
    create(db_session, admin, "common/depth", item_type="spec", name="합성 깊이", payload={"value": 600, "unit": "mm"})
    link(db_session, admin, "value_from", "common/depth", "calc:product/1")
    with pytest.raises(BrainLinkLimitError):
        link(db_session, admin, "value_from", "common/depth", "calc:option/3:5")


def test_ended_links_do_not_count_toward_the_max(made):
    admin = made["users"]["admin"]
    _price_rule(admin)
    _apply(admin, _propose(admin, "value_from", "common/shipping", "calc:product/1", valid_to="2026-01-31"))
    _apply(admin, _propose(admin, "value_from", "common/shipping", "calc:product/7"))  # 끝난 링크는 세지 않는다
    assert current_link(db_session, "value_from", "common/shipping", "calc:product/7") is not None


def test_min_is_flagged_on_the_card_and_in_quality_counts_within_scope(made, app):
    admin, who = made["users"]["admin"], made["who"]
    _price_rule(admin)
    _price_rule(admin, "common/install")
    card = item_card(db_session, who["admin"], "common/shipping", today=TODAY)
    assert card["missing_links"] == [{"kind": "value_from", "min": 1, "max": 1, "have": 0}]
    counts = {(r["type"], r["kind"]): r for r in quality_counts(db_session, who["admin"], today=TODAY)["rules"]}
    assert counts[("price_rule", "value_from")]["items"] == 3 and counts[("price_rule", "value_from")]["missing"] == 3
    link(db_session, admin, "value_from", "common/shipping", "calc:product/1")
    assert item_card(db_session, who["admin"], "common/shipping", today=TODAY)["missing_links"] == []  # 대조군
    after = {(r["type"], r["kind"]): r for r in quality_counts(db_session, who["admin"], today=TODAY)["rules"]}
    assert after[("price_rule", "value_from")]["missing"] == 2
    cs = {(r["type"], r["kind"]): r for r in quality_counts(db_session, who["cs_mgr"], today=TODAY)["rules"]}
    assert cs[("price_rule", "value_from")] == {"type": "price_rule", "kind": "value_from", "min": 1, "max": 1,
                                                "items": 0, "missing": 0, "over": 0}  # 가격 재량 항목 수는 새지 않는다
    assert missing_links(db_session, who["admin"], {"key": "common/door", "type": "product_line"}, today=TODAY) == []
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = made["ids"]["admin"]
    html = client.get("/brain/items/common/install").get_data(as_text=True)
    assert 'data-brain-missing="value_from"' in html


# ── 2. 유효 기간으로 읽기 ────────────────────────────────────────────────
def test_ended_items_and_links_leave_default_reads_but_open_directly(made):
    admin, who = made["users"]["admin"], made["who"]
    create(db_session, admin, "common/oldfit", item_type="build_rule", name="문짝 끝난 규칙", valid_to="2026-10-31")
    create(db_session, admin, "common/nextfit", item_type="build_rule", name="문짝 오늘까지 규칙", valid_to="2026-11-02")
    link(db_session, admin, "applies_to", "common/oldfit", "common/door")
    link(db_session, admin, "applies_to", "common/nextfit", "common/door")
    with catalog_source(synth_catalog):
        _apply(admin, _propose(admin, "applies_to", "common/fresh", "common/door", valid_to="2026-10-01"))
    v = who["admin"]
    keys = {i["key"] for g in search_grouped(db_session, v, "문짝", today=TODAY)["groups"] for i in g["items"]}
    assert "common/oldfit" not in keys and "common/nextfit" in keys  # 끝 날 = 그날까지(대조군)
    rows = {r["key"] for r in table_page(db_session, v, TableQuery("build_rule", per_page=50), today=TODAY)["rows"]}
    assert "common/oldfit" not in rows and "common/nextfit" in rows
    assert count_items(db_session, v, today=TODAY)["types"]["build_rule"] == 5  # 넷 + 오늘까지 하나
    around = search_around(db_session, v, AroundQuery("common/door"), today=TODAY)
    reached = {i["key"] for i in around["items"]}
    assert "common/oldfit" not in reached and "common/nextfit" in reached
    assert "common/fresh" not in reached  # 끝난 링크로는 닿지 않는다
    assert not any(e["from"] == "common/fresh" for e in around["edges"])
    assert "common/oldfit" not in {r[0] for r in brain_points(db_session, v, today=TODAY)["rows"]}
    door = item_card(db_session, v, "common/door", today=TODAY)
    linked = {i["key"] for g in door["links"] for i in g["items"]}
    assert "common/oldfit" not in linked and "common/fresh" not in linked and "common/nextfit" in linked
    ended = item_card(db_session, v, "common/oldfit", today=TODAY)  # 키로 바로 열면 보인다
    assert ended["item"]["ended"] is True and item_card(db_session, v, "common/nextfit", today=TODAY)["item"]["ended"] is False
    later = TODAY + datetime.timedelta(days=1)
    assert "common/nextfit" not in {r[0] for r in brain_points(db_session, v, today=later)["rows"]}


# ── 3. 바깥 정본 실재 확인 ───────────────────────────────────────────────
def test_missing_external_ref_rejects_the_proposal(made):
    admin = made["users"]["admin"]
    create(db_session, admin, "common/panel", name="합성 판")
    for ref in ("calc:product/999", "calc:option/3:9", "calc:option/3", "calc:nope/1", "setting:no_such_key"):
        with pytest.raises(BrainExternalRefError) as caught:
            _propose(admin, "value_from", "common/panel", ref)
        assert caught.value.refs == (ref,) and not caught.value.unavailable
    assert _propose(admin, "value_from", "common/panel", "calc:option/3:5").id  # 대조군: 있는 옵션

    def broken():
        raise OSError("계산기 정본 없음")

    with catalog_source(broken), pytest.raises(BrainExternalRefError) as down:
        propose_link(db_session, op="link_add", kind="value_from", from_key="common/panel", to_key="calc:product/1",
                     reason=REASON, proposer=Proposer.user(admin.id), now=NOW)
    assert down.value.unavailable  # 확인할 수 없으면 넣지 않는다


def test_external_ref_is_checked_again_at_apply_and_removal_is_free(made):
    admin = made["users"]["admin"]
    create(db_session, admin, "drawing/bom", item_type="bom_rule", layer="drawing", name="합성 자재표 규칙")
    setting(db_session, "synthetic_bom_key")
    change = _propose(admin, "value_from", "drawing/bom", "setting:synthetic_bom_key")
    db_session.delete(db_session.get(SystemSetting, "synthetic_bom_key"))
    db_session.flush()
    with pytest.raises(BrainExternalRefError):
        _apply(admin, change)  # 제안 뒤 자리가 사라졌다
    # 이미 이어진 링크의 자리가 사라져도 빼기(끊기)는 된다
    door = current_link(db_session, "value_from", "common/door", "setting:drawing_wizard_bom_rules")
    db_session.delete(db_session.get(SystemSetting, "drawing_wizard_bom_rules"))
    db_session.flush()
    removal = propose_link(db_session, op="link_remove", kind="value_from", from_key="common/door",
                           to_key="setting:drawing_wizard_bom_rules", reason=REASON, proposer=Proposer.user(admin.id),
                           now=NOW, base_version=door.version)
    apply_change(db_session, removal.id, actor=admin, now=NOW)
    assert current_link(db_session, "value_from", "common/door", "setting:drawing_wizard_bom_rules") is None


# ── 4. 카드의 지금 값 — 보기 범위 안에서만 ───────────────────────────────
def test_price_and_setting_values_show_only_inside_their_scope(made, app):
    who = made["who"]
    with catalog_source(synth_catalog):
        admin = {e["ref"]: e for e in item_card(db_session, who["admin"], "common/door", today=TODAY)["external"]}
        cs = {e["ref"]: e for e in item_card(db_session, who["cs_mgr"], "common/door", today=TODAY)["external"]}
    assert admin["calc:product/7"]["value"] == "1m 단위 · 1m 값 2,000원" and admin["calc:product/7"]["label"] == "합성 문짝 제품"
    assert cs["calc:product/7"]["value"] is None and cs["calc:product/7"]["value_hidden"] is True  # 가격 재량 밖
    assert cs["calc:product/7"]["label"] == "합성 문짝 제품" and cs["calc:product/7"]["exists"] is True  # 이름은 보인다
    assert admin["setting:drawing_wizard_bom_rules"]["value"] == "칸 1개 — 합성"
    assert cs["setting:drawing_wizard_bom_rules"]["value"] is None and cs["setting:drawing_wizard_bom_rules"]["value_hidden"]
    pages = {}
    for name in ("admin", "cs_mgr"):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = made["ids"][name]
        with catalog_source(synth_catalog):
            pages[name] = client.get("/brain/items/common/door").get_data(as_text=True)
    assert "2,000원" in pages["admin"] and "2,000원" not in pages["cs_mgr"]  # 대조군 · 숨김
    assert "지금 값은 볼 수 있는 사람만" in pages["cs_mgr"]
    with catalog_source(lambda: (_ for _ in ()).throw(OSError("down"))):
        down = {e["ref"]: e for e in item_card(db_session, who["admin"], "common/door", today=TODAY)["external"]}
    assert down["calc:product/7"]["exists"] is None and down["calc:product/7"]["value"] is None  # 확인 못 함
