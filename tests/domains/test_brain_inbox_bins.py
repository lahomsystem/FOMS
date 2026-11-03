"""'확인할 것' 네 묶음 · 한글 제목 · 첫 탭 · 쉬운 말(설계서 7.9 단계 1 · 사장님 11-03 "사용법이 너무 어려워").

묶음은 서버가 정한다 — 이름표 칸만 바뀌는 고침 ① · 엇갈림 · 질문 만들기 ③ · 사본 자리 링크 ④ · 그 밖 ②(대조군: 이름표 + 다른 칸,
글 고침, 다른 링크는 ②). ① · ④ 는 '금액이 바뀔 수 있어요' 대신 '글과 금액은 그대로'를 보인다.
"""

from __future__ import annotations

import datetime
from pathlib import Path

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
ROOT_JS = Path(__file__).resolve().parents[2] / "static/js/brain"


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


# ── 2단계: ① 이름 표 · ④ 한 번에(D151) ──────────────────────────────────
def _label_change(admin, key, label):
    row = current_object(db_session, key)
    return propose_update(db_session, key=key, base_version=row.version,
                          after={"payload": {**(row.payload or {}), "pref_label": label}},
                          reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")


def _tpl(admin):
    from tests.support.brain_review_support import DOC
    from tests.support.brain_support import create
    return create(db_session, admin, "lahom/tpl", item_type="template", layer="cs", brand="LAHOM", name="greeting",
                  text="안녕하세요", payload={"doc_id": "tpl", "intents": ["hours"], **DOC})


def test_admin_bulk_approves_label_only_changes_of_any_grade_and_refuses_mixed_batches(app):
    from foms.persistence.brain.models import BrainChange
    from foms.services.brain.decide import bulk_apply
    from foms.services.brain.errors import BrainShapeError

    world = review_world(db_session)
    admin, cs_mgr = world["people"]["admin"], world["people"]["cs_mgr"]
    _tpl(admin)
    tpl = _label_change(admin, "lahom/tpl", "첫인사 상용구")  # 상용구 = 등급 B
    price = _label_change(admin, "common/shipping", "운임 추가비")  # 가격 규칙 = 등급 B
    db_session.commit()
    assert {tpl.grade, price.grade} == {"B"}
    with pytest.raises(BrainShapeError):  # 글이 바뀌는 등급 B(운임 글 고침)가 섞이면 통째 거절
        bulk_apply(db_session, [tpl.id, world["changes"]["price"]], actor=admin, now=LATER)
    with pytest.raises(BrainShapeError):  # 관리자가 아니면 이름표만이어도 등급 A 만
        bulk_apply(db_session, [tpl.id], actor=cs_mgr, now=LATER)
    db_session.rollback()
    assert db_session.get(BrainChange, tpl.id).status == "open"  # 아무것도 안 썼다
    out = bulk_apply(db_session, [tpl.id, price.id], actor=admin, now=LATER)
    db_session.commit()
    assert sorted(a["id"] for a in out["applied"]) == sorted([tpl.id, price.id]) and out["failed"] == []
    assert current_object(db_session, "lahom/tpl").payload["pref_label"] == "첫인사 상용구"
    assert current_object(db_session, "lahom/tpl").text == "안녕하세요"  # 글은 그대로


def test_inbox_marks_label_only_b_changes_bulk_ok_for_the_admin_only(app):
    world = review_world(db_session)
    admin = world["people"]["admin"]
    _tpl(admin)
    tpl = _label_change(admin, "lahom/tpl", "첫인사 상용구")
    db_session.commit()
    card = next(c for c in inbox(db_session, viewer_of(admin), now=LATER)["cards"] if c["main"]["id"] == tpl.id)
    assert card["bin"] == "names" and card["main"]["bulk_ok"] is True and card["title"] == "첫인사 상용구"
    assert card["main"]["confirm"] == {"field": "payload.pref_label", "value": "첫인사 상용구"}  # JSON 이 아니라 이름 칸
    price = next(c for c in inbox(db_session, viewer_of(admin), now=LATER)["cards"]
                 if c["main"]["id"] == world["changes"]["price"])
    assert price["main"]["bulk_ok"] is False  # 글이 바뀌는 등급 B 는 한 장씩(대조군)
    pref = next(r for r in card["main"]["fields"] if r["field"] == "payload.pref_label")
    assert pref["editable"] is True and pref["label"] == "한글 이름"


def test_renamed_label_is_approved_with_the_edited_name_on_a_type_without_schema(app):
    from foms.services.brain.decide import apply_decision

    world = review_world(db_session)
    admin = world["people"]["admin"]
    _tpl(admin)
    tpl = _label_change(admin, "lahom/tpl", "첫인사 상용구")
    db_session.commit()
    apply_decision(db_session, tpl.id, actor=admin, base_version=tpl.base_version, now=LATER,
                   edits={"payload.pref_label": "첫 인사 상용구"},
                   confirm={"field": "payload.pref_label", "value": "첫 인사 상용구"})
    db_session.commit()
    assert current_object(db_session, "lahom/tpl").payload["pref_label"] == "첫 인사 상용구"


def test_copy_targets_read_as_place_names():
    from foms.services.brain.inbox_bins import ref_label
    assert ref_label("form:lahom-option-table") == "기본 옵션표"
    assert ref_label("store:lahom-main") == "스마트스토어 상세 · lahom-main"
    assert ref_label("lahom/ep") == "lahom/ep" and ref_label(None) == ""


# ── 3단계: ② 문장 카드 ───────────────────────────────────────────────────
def test_content_card_carries_sentence_price_line_and_who_can_see(app):
    from foms.services.brain.external import catalog_source
    from foms.services.brain.proposals import propose_create
    from tests.support.brain_support import synth_catalog, values

    world = review_world(db_session)
    admin = world["people"]["admin"]
    made = propose_create(db_session, key="common/handle-extra", brand="COMMON", layer="common", item_type="price_rule",
                          values=values("손잡이 추가비", text="손잡이를 바꾸는 옵션이에요. 금액은 견적 계산기 값을 따라요.",
                                        checked_at="2026-11-03", payload={"doc_id": "handle-extra", "basis": "calc",
                                                                         "approved_by": "합성", "approved_at": "2026-11-03"}),
                          reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="",
                          evidence=["plan:synth#handle", "calc:option/3:5"])
    db_session.commit()
    with catalog_source(synth_catalog):
        cards = {c["main"]["id"]: c for c in inbox(db_session, viewer_of(admin), now=LATER)["cards"]}
    main = cards[made.id]["main"]
    assert cards[made.id]["bin"] == "content"
    assert main["sentence"] == "손잡이를 바꾸는 옵션이에요. 금액은 견적 계산기 값을 따라요."
    assert len(main["prices"]) == 1 and main["prices"][0]["exists"] is True and "300" in main["prices"][0]["value"]
    assert main["visible_to"] == "내부 모두"
    shipping = cards[world["changes"]["price"]]["main"]  # 글 고침 제안 — 새 글, 계산기 자리 없음(대조군)
    assert shipping["sentence"] == "지역별 운임 새 기준" and shipping["prices"] == []


# ── 4단계: ③ 질문 카드(D152) ─────────────────────────────────────────────
def _question(admin, about_key, text="스토어 상세는 '2주 이내', 회사 지식은 '실측일로부터 5~7일'"):
    from foms.services.brain.proposals import propose_create
    from tests.support.brain_support import values
    return propose_create(db_session, key="conflict/lahom-synth1", brand="COMMON", layer="common", item_type="conflict",
                          values=values("시공 기간이 두 곳에 다르게 적혀 있어요", text=text),
                          reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="",
                          evidence=["plan:synth#c1", f"about:{about_key}", "about:common/missing"])


def test_question_card_shows_the_knowledge_side_and_answer_codes_close_it(app):
    from foms.persistence.brain.models import BrainChange
    from foms.services.brain.decide import apply_decision, reject_decision

    world = review_world(db_session)
    admin = world["people"]["admin"]
    q = _question(admin, "common/door")
    db_session.commit()
    card = next(c for c in inbox(db_session, viewer_of(admin), now=LATER)["cards"] if c["main"]["id"] == q.id)
    door = current_object(db_session, "common/door")
    assert card["bin"] == "decide"
    assert card["main"]["about"] == [{"key": "common/door", "title": door.name, "text": door.text or "",
                                      "version": door.version}]  # 없는 항목은 빠진다(대조군)
    assert "2주 이내" in card["main"]["sentence"]
    # '바깥 글이 맞아요' = 지식 글 고침 제안 → 바로 승인 → 질문을 그 까닭으로 닫음(화면이 부르는 차례 그대로)
    edit = propose_update(db_session, key="common/door", base_version=door.version, after={"text": "실측 뒤 2주 안"},
                          reason="사장님 답 — 바깥 글이 맞아요", proposer=Proposer.user(admin.id), now=LATER, known="")
    apply_decision(db_session, edit.id, actor=admin, base_version=door.version, now=LATER,
                   confirm={"field": "text", "value": "실측 뒤 2주 안"})
    reject_decision(db_session, q.id, actor=admin, code="outside_right", now=LATER)
    db_session.commit()
    assert current_object(db_session, "common/door").text == "실측 뒤 2주 안"
    closed = db_session.get(BrainChange, q.id)
    assert closed.status == "rejected" and closed.reject_code == "outside_right"
    from foms.services.brain.errors import BrainRejectedError
    with pytest.raises(BrainRejectedError):  # 같은 질문은 다시 열리지 않는다(거절 기록 — 7.5)
        _question(admin, "common/door")


def test_answer_codes_are_known_reject_codes_and_hidden_from_plain_reject_chips():
    from foms.services.brain.constants import ANSWER_CODES, REJECT_CODES
    from foms.services.brain.display import REJECT_LABELS
    assert set(ANSWER_CODES) <= set(REJECT_CODES) and all(code in REJECT_LABELS for code in REJECT_CODES)
    question = (ROOT_JS / "brain-inbox-question.js").read_text(encoding="utf-8")
    card = (ROOT_JS / "brain-inbox-card.js").read_text(encoding="utf-8")
    assert all(f"'{code}'" in question for code in ANSWER_CODES)
    assert "FOMS_BRAIN_INBOX_QUESTION" in card and "answers.indexOf(choice.value) < 0" in card


# ── 5단계: 지식 한 개 화면(설계서 7.9 화면 6) ────────────────────────────
def test_item_page_puts_people_words_first_and_machine_detail_inside_more(app):
    world = review_world(db_session)
    admin = world["people"]["admin"]
    _tpl(admin)
    tpl = _label_change(admin, "lahom/tpl", "첫인사 상용구")
    db_session.commit()
    from foms.services.brain.decide import apply_decision
    row = current_object(db_session, "lahom/tpl")
    after_aliases = {**(row.payload or {}), "aliases": ["인사말", "안녕하세요"]}
    apply_decision(db_session, tpl.id, actor=admin, base_version=tpl.base_version, now=LATER,
                   confirm={"field": "payload.pref_label", "value": "첫인사 상용구"})
    db_session.commit()
    row = current_object(db_session, "lahom/tpl")
    propose_update(db_session, key="lahom/tpl", base_version=row.version, after={"payload": after_aliases},
                          reason=REASON, proposer=Proposer.user(admin.id), now=LATER, known="")
    db_session.commit()
    html = _client(app, admin.id).get("/brain/items/lahom/tpl").get_data(as_text=True)
    head, rest = html.split('<details class="brain-prop__drawer" data-brain-card-more>', 1)
    assert '<h1 class="brain-card__title">첫인사 상용구</h1>' in head  # 영어 키(greeting)가 아니라 한글 이름
    assert "사용 중" in head and "승인을 기다리는 수정 1개" in head and "안녕하세요" in head
    assert "라홈 상담 · 상용구" in head and "어디에 쓰이나" in head and "data-brain-propose-open" in head
    assert "확신 " not in head and "lahom/tpl · 판" not in head  # 기계 칸은 자세히 보기 안
    assert "확신 " in rest and "lahom/tpl · 판" in rest and "근거 · 만든 이 · 승인자" in rest
    assert "한눈에" in html and "수정 기록(" in html and "연결된 지식(" in html
