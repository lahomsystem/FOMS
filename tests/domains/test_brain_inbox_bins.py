"""'확인할 것' 네 묶음 · 한글 제목 · 첫 탭 · 쉬운 말(설계서 7.9 단계 1 · 사장님 11-03 "사용법이 너무 어려워").

묶음은 서버가 정한다 — 이름표 칸만 바뀌는 고침 ① · 엇갈림 · 질문 만들기 ③ · 사본 자리 링크 ④ · 그 밖 ②(대조군: 이름표 + 다른 칸,
글 고침, 다른 링크는 ②). ① · ④ 는 '금액이 바뀔 수 있어요' 대신 '글과 금액은 그대로'를 보인다.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.brain.display import approval_meaning
from foms.services.brain.inbox import inbox
from foms.services.brain.inbox_bins import bulk_ok_any_grade, card_bin
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.schemas import diff_rows
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from tests.support.brain_review_support import items, people, review_world
from tests.support.brain_support import NOW, REASON, agent_judge

LATER = NOW + datetime.timedelta(minutes=5)


@pytest.fixture(autouse=True)
def _agent_judge():
    with agent_judge():
        yield


def _payload(before, after):
    return {"payload": {"before": before, "after": after}}


LABELS_ONLY = _payload({"doc_id": "x", "pref_label": None}, {"doc_id": "x", "pref_label": "첫인사 상용구",
                                                             "aliases": ["인사말"]})


@pytest.mark.parametrize("op, item_type, fields, link_kind, want", [
    ("update", "template", LABELS_ONLY, None, "names"),
    ("update", "price_rule", _payload({"pref_label": "가"}, {"pref_label": "나", "basis": "calc"}), None, "content"),
    ("update", "template", {**LABELS_ONLY, "text": {"before": "가", "after": "나"}}, None, "content"),
    ("update", "template", _payload({"pref_label": "가"}, {"pref_label": "가"}), None, "content"),  # 바뀐 칸 없음
    ("create", "conflict", {"name": {"before": None, "after": "엇갈림"}}, None, "decide"),
    ("create", "question", {"name": {"before": None, "after": "질문"}}, None, "decide"),
    ("create", "price_rule", {"name": {"before": None, "after": "새 값"}}, None, "content"),
    ("link_add", None, None, "copy_in", "mark"),
    ("link_add", None, None, "value_from", "content"),
    ("retire", "policy", None, None, "content"),
])
def test_bins_are_decided_by_what_changes(op, item_type, fields, link_kind, want):
    assert card_bin(op, item_type, fields, link_kind) == want
    assert bulk_ok_any_grade(op, item_type, fields, link_kind) is (want in ("names", "mark"))


def test_meaning_drops_the_price_warning_only_when_amounts_cannot_change():
    names = approval_meaning("update", "price_rule", "names")
    assert "글과 금액은 그대로" in names and "금액이 바뀔 수 있어요" not in names
    assert "금액이 바뀔 수 있어요" in approval_meaning("update", "price_rule", "content")  # 대조군
    assert approval_meaning("link_add", None, "mark").startswith("승인하면 두 지식이 이어져요.")
    assert "넣으면" not in approval_meaning("create", "template")


def test_label_changes_of_a_type_without_schema_are_shown_as_named_rows_not_json():
    rows = diff_rows("template", LABELS_ONLY)
    assert [(r["label"], r["after"]) for r in rows] == [("한글 이름", "첫인사 상용구"), ("찾는 말", ["인사말"])]
    mixed = diff_rows("template", _payload({"doc_id": "x"}, {"doc_id": "y", "pref_label": "가"}))
    assert [r["label"] for r in mixed] == ["한글 이름", "그 밖 세부 칸"]  # 이름표 밖 칸은 한 줄로(대조군)


def test_inbox_cards_carry_bin_and_korean_title(app):
    world = review_world(db_session)
    admin = world["people"]["admin"]
    door = current_object(db_session, "common/door")
    labels = propose_update(db_session, key="common/door", base_version=door.version,
                            after={"payload": {**(door.payload or {}), "pref_label": "여닫이 문"}},
                            reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")
    db_session.commit()
    cards = {c["main"]["id"]: c for c in inbox(db_session, viewer_of(admin), now=LATER)["cards"]}
    assert cards[labels.id]["bin"] == "names" and cards[labels.id]["title"] == "여닫이 문"
    assert "글과 금액은 그대로" in cards[labels.id]["main"]["meaning"]
    price = cards[world["changes"]["price"]]
    assert price["bin"] == "content" and price["title"] == price["name"]  # 한글 이름이 없으면 이름(대조군)


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def test_first_tab_is_inbox_only_when_there_is_something_to_decide(app):
    who = people(db_session)
    items(db_session, who["admin"])
    db_session.commit()
    empty = _client(app, who["admin"].id).get("/brain").get_data(as_text=True)
    assert 'nav-link active" id="brain-tab-search-btn"' in empty  # 결정할 것이 없으면 찾기
    propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"name": "사진 먼저 꼭 받기"}, reason=REASON,
                   proposer=Proposer.user(who["admin"].id), now=NOW, known="")
    db_session.commit()
    html = _client(app, who["admin"].id).get("/brain").get_data(as_text=True)
    assert 'nav-link active" id="brain-tab-inbox-btn"' in html
    assert "확인할 것" in html and "지식 찾기" in html and "더 보기" in html and "brain-inbox-bins.js" in html
    assert html.index('id="brain-tab-inbox-btn"') < html.index('id="brain-tab-search-btn"') < html.index("더 보기")
    assert 'class="dropdown-item" id="brain-tab-table-btn"' in html  # 지식 표는 더 보기 안
    assert "넣기" not in html.split('id="brain-tab-inbox"')[1].split("</section>")[0]  # 확인할 것 칸 글에 '넣기' 없음
