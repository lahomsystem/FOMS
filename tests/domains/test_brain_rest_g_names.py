"""회사 지식 남은 영어 이름 · 정렬 고치기(남은 후보 3차 — 일꾼 G: G1 · G2).

- G1: 지식 표 '이름 순' = 화면 이름 순(한글 이름표가 있으면 그것, 없으면 저장 이름 — :func:`.labels.pref_of` 와 같은 규칙).
  DB 정렬식 하나(:func:`.browse.pref_name`)라 질의 수가 그대로다. 대조군: 저장 이름 순이면 차례가 다르다.
- G2: 카드 '연결된 지식' 줄 · 승인 대기 '이어진 지식' 이름 · 링크 제안의 두 끝 이름이 한글 이름 먼저(이름표 없는 끝은 저장
  이름 · 바깥 자리 끝은 사본 자리 이름표 — 대조군). 이미 읽는 질의의 칸 식이라 줄이 늘어도 질의 수가 같다.
- SQLite 는 바로 돌리고, PostgreSQL 은 같은 식이 방언(``->>``)으로 바뀌는지 글로 본다(PG 레인은 총괄 몫).
합성 계정 · 합성 항목만(금액 · 손님 글 · 직원 이름 없음).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import aliased

from db import db_session
from foms.persistence.brain.models import BrainObject
from foms.services.brain.browse import TableQuery, _table_order, pref_name, table_page
from foms.services.brain.card import item_card, link_groups
from foms.services.brain.inbox import inbox
from foms.services.brain.proposals import Proposer, propose_link, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.db_url_resolver import PGDialect_psycopg_plain_binds
from tests.support.brain_screen_support import TODAY
from tests.support.brain_support import NOW, REASON, agent_judge, create, link, person
from tests.domains.test_brain_review_js import NODE, _node

LATER = NOW + datetime.timedelta(minutes=5)


@pytest.fixture(autouse=True)
def _agent_judge():
    with agent_judge():
        yield


def _statements(fn):
    seen = []
    engine = db_session.get_bind()

    def count(*_args):
        seen.append(1)

    event.listen(engine, "before_cursor_execute", count)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return len(seen)


# ── G1 지식 표 '이름 순' ────────────────────────────────────────────────
@pytest.fixture
def named(app):
    admin = person(db_session, "brest_g_admin")
    create(db_session, admin, "common/g-zeta", item_type="term", name="zeta-key", text="합성 첫째 뜻",
           payload={"pref_label": "가나 낱말"})
    create(db_session, admin, "common/g-alpha", item_type="term", name="alpha-key", text="합성 둘째 뜻")
    create(db_session, admin, "common/g-mid", item_type="term", name="mid-key", text="합성 셋째 뜻",
           payload={"pref_label": "  "})  # 빈 이름표 → 저장 이름
    create(db_session, admin, "common/g-beta", item_type="term", name="beta-key", text="합성 넷째 뜻",
           payload={"pref_label": " 다라 낱말 "})  # 앞뒤 빈칸은 뺀다
    db_session.commit()
    return admin


def test_name_sort_follows_the_shown_name(named):
    viewer = viewer_of(named)
    rows = table_page(db_session, viewer, TableQuery("term", sort="name"), today=TODAY)["rows"]
    shown = [r["name"] for r in rows]
    assert shown == ["alpha-key", "mid-key", "가나 낱말", "다라 낱말"]
    assert shown == sorted(shown)  # 화면 이름과 차례가 맞는다
    stored = [r[0] for r in db_session.execute(
        select(BrainObject.name).where(BrainObject.item_type == "term", BrainObject.superseded_at.is_(None))
        .order_by(BrainObject.name))]
    assert stored == ["alpha-key", "beta-key", "mid-key", "zeta-key"]  # 대조군: 저장 이름 순은 다른 차례
    first = table_page(db_session, viewer, TableQuery("term", sort="name", per_page=2), today=TODAY)
    second = table_page(db_session, viewer, TableQuery("term", sort="name", page=2, per_page=2), today=TODAY)
    assert [r["name"] for r in first["rows"] + second["rows"]] == shown  # 쪽을 나눠도 같은 차례


def test_name_sort_adds_no_query(named):
    viewer = viewer_of(named)
    by_usage = _statements(lambda: table_page(db_session, viewer, TableQuery("term"), today=TODAY))
    by_name = _statements(lambda: table_page(db_session, viewer, TableQuery("term", sort="name"), today=TODAY))
    one = _statements(lambda: table_page(db_session, viewer, TableQuery("term", sort="name", per_page=1), today=TODAY))
    assert by_name == by_usage == one


def _sql(clause, dialect):
    return str(clause.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def test_shown_name_expression_fits_sqlite_and_postgresql():
    pg = PGDialect_psycopg_plain_binds()  # 운영 방언(psycopg · 바인드 꼴 없음)
    assert _sql(pref_name(), pg) == ("coalesce(nullif(trim(CAST(brain_objects.payload ->> 'pref_label' AS VARCHAR)), ''), "
                                     "brain_objects.name)")
    assert _sql(pref_name(), sqlite.dialect()) == (
        "coalesce(nullif(trim(JSON_EXTRACT(brain_objects.payload, '$.\"pref_label\"')), ''), brain_objects.name)")
    assert "other.payload ->> 'pref_label'" in _sql(pref_name(aliased(BrainObject, name="other")), pg)
    order = _sql(select(BrainObject.id).order_by(*_table_order("name")), pg)
    assert order.endswith("ORDER BY coalesce(nullif(trim(CAST(brain_objects.payload ->> 'pref_label' AS VARCHAR)), ''), "
                          "brain_objects.name), brain_objects.item_key")
    assert "->>" in _sql(pref_name(), postgresql.dialect())  # 기본 PG 방언도 같은 꼴


# ── G2 카드 '연결된 지식' · 승인 대기 '이어진 지식' · 링크 제안 끝 이름 ─────────
@pytest.fixture
def linked(app):
    admin = person(db_session, "brest_g_link_admin")
    create(db_session, admin, "common/g-top", item_type="term", name="top-key", text="합성 윗 뜻",
           payload={"pref_label": "윗 낱말"})
    for key, name, label in (("common/g-n1", "aaa-key", "하늘 낱말"), ("common/g-n2", "zzz-key", "가지 낱말"),
                             ("common/g-n3", "mmm-key", None), ("common/g-n4", "nnn-key", "넷째 낱말")):
        create(db_session, admin, key, item_type="term", name=name, text="합성 아래 뜻",
               payload={"pref_label": label} if label else None)
    for key in ("common/g-n1", "common/g-n2", "common/g-n3"):
        link(db_session, admin, "broader", key, "common/g-top")
    db_session.commit()
    return admin


def test_card_link_names_are_shown_names_in_shown_order(linked):
    card = item_card(db_session, viewer_of(linked), "common/g-top", today=TODAY)
    group = next(g for g in card["links"] if (g["kind"], g["direction"]) == ("broader", "in"))
    assert [i["name"] for i in group["items"]] == ["mmm-key", "가지 낱말", "하늘 낱말"]  # 이름표 없는 끝은 저장 이름(대조군)
    assert [i["key"] for i in group["items"]] == ["common/g-n3", "common/g-n2", "common/g-n1"]  # 키는 링크용 그대로
    out = next(g for g in link_groups(db_session, viewer_of(linked), "common/g-n1", today=TODAY)
               if g["direction"] == "out")
    assert out["items"][0]["name"] == "윗 낱말"


def test_card_links_add_no_query_per_link(linked):
    viewer = viewer_of(linked)
    three = _statements(lambda: item_card(db_session, viewer, "common/g-top", today=TODAY))
    one = _statements(lambda: item_card(db_session, viewer, "common/g-n1", today=TODAY))
    assert three == one


def _propose(admin):
    top = current_object(db_session, "common/g-top")
    propose_update(db_session, key="common/g-top", base_version=top.version, after={"text": "합성 윗 새 뜻"},
                   reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")
    propose_link(db_session, op="link_add", kind="broader", from_key="common/g-n4", to_key="common/g-top",
                 reason=REASON, proposer=Proposer.user(admin.id), now=NOW)
    propose_link(db_session, op="link_add", kind="copy_in", from_key="common/g-n3", to_key="form:lahom-option-table",
                 reason=REASON, proposer=Proposer.user(admin.id), now=NOW)
    db_session.commit()


def test_inbox_touch_and_link_end_names_are_shown_names(linked):
    _propose(linked)
    cards = inbox(db_session, viewer_of(linked), now=LATER)["cards"]
    top = next(c for c in cards if c["key"] == "common/g-top" and c["main"]["link"] is None)
    assert top["touches"]["total"] == 3
    assert [i["name"] for i in top["touches"]["items"]] == ["mmm-key", "가지 낱말", "하늘 낱말"]
    links = {c["main"]["link"]["to"]: c["main"]["link"] for c in cards if c["main"]["link"]}
    assert links["common/g-top"]["from_label"] == "넷째 낱말" and links["common/g-top"]["to_label"] == "윗 낱말"
    assert links["common/g-top"]["from"] == "common/g-n4"  # 키는 그대로(넣기 · 링크용)
    copy = links["form:lahom-option-table"]
    assert copy["from_label"] == "mmm-key" and copy["to_label"] == "기본 옵션표"  # 대조군: 이름표 없음 · 바깥 자리


def test_inbox_link_names_add_no_query_per_card(linked):
    admin = linked
    propose_link(db_session, op="link_add", kind="broader", from_key="common/g-n4", to_key="common/g-top",
                 reason=REASON, proposer=Proposer.user(admin.id), now=NOW)
    db_session.commit()
    viewer = viewer_of(admin)
    one = _statements(lambda: inbox(db_session, viewer, now=LATER))
    _propose_more(admin)
    three = _statements(lambda: inbox(db_session, viewer, now=LATER))
    assert len(inbox(db_session, viewer, now=LATER)["cards"]) == 3 and one == three


def _propose_more(admin):
    for key, to in (("common/g-n3", "form:lahom-option-table"), ("common/g-n2", "form:lahom-option-table")):
        propose_link(db_session, op="link_add", kind="copy_in", from_key=key, to_key=to, reason=REASON,
                     proposer=Proposer.user(admin.id), now=NOW)
    db_session.commit()


# ── G2 화면 글(brain-review-view.js) ───────────────────────────────────
@NODE
def test_review_lines_use_shown_names_and_the_word_knowledge():
    named = {"kind": "broader", "from": "common/a", "to": "common/b", "from_label": "넷째 낱말", "to_label": "윗 낱말"}
    bare = {"kind": "broader", "from": "a", "to": "b"}
    got = _node("[r.summary({type: 'term', name: 'x', main: {op: 'link_add', fields: [], link: data.named}}, {}),"
                " r.summary({type: 'term', name: 'x', main: {op: 'link_add', fields: [], link: data.bare}}, {}),"
                " r.touchText({total: 1, items: [{name: '가지 낱말'}]}, 0, {}), r.touchText({total: 0, items: []}, 0, {})]",
                {"named": named, "bare": bare})
    assert got[0].endswith(": 넷째 낱말 → 윗 낱말") and "common/" not in got[0]
    assert got[1].endswith(": a → b")  # 대조군: 이름 없으면 지금처럼 키
    assert got[2] == "이어진 지식 1개: 가지 낱말" and got[3] == "함께 닿는 지식 없음"
