"""회사 지식 화면 영어 이름 · 기계 말 고치기(점검 F01 · F02 · F03 · F11 · F12 · F13 — 일꾼 C).

- F01: 지식 표 · 찾기 결과 · 다시 확인 · 이웃 줄 이름 = 카드 제목과 같은 규칙(한글 이름표 먼저, 없으면 이름 — 대조군).
  이미 읽은 줄의 실음 칸에서 꺼낸다 — 줄 수가 늘어도 질의 수가 같다(줄마다 다시 읽지 않는다).
- F03 · F11: 고르기 값은 한글 이름표로 보이고 저장 값은 그대로(고칠 말 고르기 칸 · 카드 '자세히 보기' · 챗봇 글은 값 그대로).
- F12: '자세히 보기'에 키 없음 · 기계 꼴 근거 위치 숨김(사람 글은 보임 — 대조군) · 같은 칸 한 번.
- F13: 만든 이 에이전트 코드 이름 대신 한글 이름표(모르는 이름은 'AI').
합성 계정 · 합성 항목만(금액 · 손님 글 · 직원 이름 없음).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from sqlalchemy import event, update

from db import db_session
from foms.persistence.brain.models import BrainObject
from foms.services.brain.around import AroundQuery, search_around
from foms.services.brain.browse import TableQuery, light_item, search_grouped, table_page
from foms.services.brain.card import actor_label, evidence_place
from foms.services.brain.chat_reports import CHAT_AGENT
from foms.services.brain.constants import PRICE_BASES
from foms.services.brain.display import AGENT_LABELS, display_table
from foms.services.brain.photo_cards import AGENT as PHOTO_AGENT
from foms.services.brain.recheck import recheck_list
from foms.services.brain.schemas import (
    CHOICE_LABELS, SPEC_BASES, TYPE_SCHEMAS, choice_label, key_fields,
)
from foms.services.brain.scope import viewer_of
from foms.services.cs_agent.photo_learning import AGENT as LEARN_AGENT
from foms.services.cs_agent.quote_brain import DOORS, HANDLES
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from tests.support.brain_screen_support import TODAY
from tests.support.brain_support import create, link, person

#: 단위 칸은 값이 이미 사람 말(mm · 자 · 통 …)이라 이름표가 없다.
SELF_NAMED = {"payload.unit", "payload.price_unit"}
HANJA = re.compile(r"[㐀-鿿豈-﫿]")
CODE = re.compile(r"[a-z]+_[a-z]+")


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


# ── F03 · F11 고르기 값 이름표 ───────────────────────────────────────────
def test_every_choice_field_has_korean_labels_and_reuses_existing_words():
    for item_type, props in TYPE_SCHEMAS.items():
        for prop in props:
            if not prop.choices or prop.path in SELF_NAMED:
                continue
            assert set(prop.choices) <= set(CHOICE_LABELS[prop.path]), (item_type, prop.path)
    for names in CHOICE_LABELS.values():
        for value, label in names.items():
            assert label and not HANJA.search(label) and not CODE.search(label), (value, label)
    assert not set(SPEC_BASES) & set(PRICE_BASES)  # 한 자리(payload.basis)를 두 유형이 써도 값이 안 겹친다
    assert CHOICE_LABELS["payload.basis"]["inner"] == "내경(안쪽 치수)"  # 사장님 D158
    assert CHOICE_LABELS["payload.erp_stage"] == STAGE_LABELS  # 주문 단계 이름 그대로
    assert {k: CHOICE_LABELS["payload.door_kinds"][k] for k in ("hinged", "sliding")} == {
        k: DOORS[k] for k in ("hinged", "sliding")}  # 견적 뽑기 이름과 같은 말
    assert {k: CHOICE_LABELS["payload.handle_default"][k] for k in ("push", "bar", "other")} == {
        k: HANDLES[k] for k in ("push", "bar", "other")}
    assert display_table()["choices"] == CHOICE_LABELS  # 모든 화면에 싣는 표 한 덩어리
    assert choice_label("payload.basis", "calc") == "견적 계산기 값"
    assert choice_label("payload.unit", "mm") == "mm"  # 대조군: 이름표 없는 칸은 값 그대로
    assert choice_label("payload.basis", "새값") == "새값"  # 대조군: 모르는 값은 그대로


def test_card_key_fields_show_labels_but_keep_values_for_the_chatbot():
    spec = {"payload": {"value": 600, "unit": "mm", "basis": "inner"}}
    fields = {f["path"]: f for f in key_fields(spec, "spec")}
    assert fields["payload.basis"]["shown"] == "내경(안쪽 치수)" and fields["payload.basis"]["value"] == "inner"
    assert fields["payload.value"]["shown"] == fields["payload.value"]["value"] == "600mm"  # 대조군: 수 · 단위 그대로
    line = {"payload": {"door_kinds": ["hinged", "sliding"], "quote_kind": "linear"}}
    shown = {f["path"]: f["shown"] for f in key_fields(line, "product_line")}
    assert shown["payload.door_kinds"] == "여닫이 · 슬라이딩" and shown["payload.quote_kind"] == "cm 비례"
    assert shown["payload.molding_default"] == ""  # 빈 칸은 빈 글


# ── F13 에이전트 이름표 · F12 근거 위치 ──────────────────────────────────
def test_agent_actor_shows_a_korean_label_not_the_code_name():
    assert {PHOTO_AGENT, LEARN_AGENT, CHAT_AGENT} <= set(AGENT_LABELS)  # 이름 정본과 맞춘다
    assert actor_label("agent:cs_photo", {}) == "AI(사진 다시 배우기)"
    assert actor_label(f"agent:{CHAT_AGENT}", {}) == AGENT_LABELS[CHAT_AGENT]
    assert actor_label("agent:new_bot", {}) == "AI"  # 모르는 에이전트
    assert actor_label("import", {}) == "지식 문서에서 옮김" and actor_label("user:3", {3: "합성"}) == "합성"  # 대조군
    for label in AGENT_LABELS.values():
        assert not CODE.search(label) and not HANJA.search(label)


@pytest.mark.parametrize("ref", ["plan:synth#3", "cs_agent_knowledge_lahom", "photo_relearn:abc", "brain_questions:4"])
def test_machine_evidence_places_are_hidden(ref):
    assert evidence_place(ref) is None


def test_human_evidence_places_stay():
    assert evidence_place(" D115 ") == "D115" and evidence_place("합성 원장 줄") == "합성 원장 줄"
    assert evidence_place(None) is None and evidence_place("") is None


# ── F01 목록 이름 = 카드 제목 규칙 ──────────────────────────────────────
def _row(**extra):
    base = {"item_key": "common/x", "name": "install-date-confirm", "item_type": "policy", "layer": "common",
            "brand": "COMMON", "status": "active", "confidence": "confirmed", "risk_grade": None, "version": 1,
            "usage_count": 0, "checked_at": None, "stale_after": None, "text": "합성 글", "payload": None}
    base.update(extra)
    return SimpleNamespace(**base)


def test_light_item_name_follows_the_card_title_rule():
    assert light_item(_row(payload={"pref_label": " 시공일 확정 시점 "}), today=TODAY)["name"] == "시공일 확정 시점"
    assert light_item(_row(), today=TODAY)["name"] == "install-date-confirm"  # 대조군: 한글 이름 없음
    assert light_item(_row(payload={"pref_label": "  "}), today=TODAY)["name"] == "install-date-confirm"  # 빈 이름표
    assert light_item(_row(payload={"pref_label": "가"}), today=TODAY)["key"] == "common/x"  # 키는 링크용 그대로


@pytest.fixture
def labelled(app):
    admin = person(db_session, "fixn_admin")
    create(db_session, admin, "common/install-date", item_type="term", name="install-date-confirm",
           text="합성 시공일 뜻", payload={"pref_label": "시공일 확정 시점"})
    create(db_session, admin, "common/plain-term", item_type="term", name="plain-term", text="합성 시공일 다른 뜻")
    create(db_session, admin, "common/door-word", item_type="term", name="door-word", text="합성 문 낱말",
           payload={"pref_label": "문 낱말"})
    link(db_session, admin, "broader", "common/door-word", "common/install-date")
    db_session.commit()
    return admin


def test_table_search_recheck_and_around_use_the_korean_name(labelled):
    viewer = viewer_of(labelled)
    rows = {r["key"]: r["name"] for r in table_page(db_session, viewer, TableQuery("term"), today=TODAY)["rows"]}
    assert rows == {"common/install-date": "시공일 확정 시점", "common/plain-term": "plain-term",
                    "common/door-word": "문 낱말"}
    found = {i["key"]: i["name"] for g in search_grouped(db_session, viewer, "시공일", today=TODAY)["groups"]
             for i in g["items"]}
    assert found == {"common/install-date": "시공일 확정 시점", "common/plain-term": "plain-term"}
    around = search_around(db_session, viewer, AroundQuery(key="common/door-word"), today=TODAY)
    assert around["start"]["name"] == "문 낱말" and [i["name"] for i in around["items"]] == ["시공일 확정 시점"]
    db_session.execute(update(BrainObject).where(BrainObject.item_type == "term").values(stale_after=TODAY))
    names = {i["key"]: i["name"] for i in recheck_list(db_session, viewer, today=TODAY)["items"]}
    assert names["common/install-date"] == "시공일 확정 시점" and names["common/plain-term"] == "plain-term"


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


def test_list_names_add_no_query_per_row(labelled):
    viewer = viewer_of(labelled)
    one = _statements(lambda: table_page(db_session, viewer, TableQuery("term", per_page=1), today=TODAY))
    three = _statements(lambda: table_page(db_session, viewer, TableQuery("term", per_page=3), today=TODAY))
    assert one == three  # 이름표는 이미 읽은 줄의 실음 칸 — 줄마다 다시 읽지 않는다


# ── F12 · F11 카드 화면 ─────────────────────────────────────────────────
@pytest.fixture
def card_world(app):
    admin = person(db_session, "fixn_card_admin")
    create(db_session, admin, "common/depth-x", item_type="spec", name="depth-x", evidence_ref="plan:synth#1",
           payload={"value": 600, "unit": "mm", "basis": "inner", "pref_label": "몸통 깊이"})
    create(db_session, admin, "common/policy-x", item_type="policy", name="policy-x", evidence_ref="합성 원장 줄",
           checked_at="2026-10-20", valid_from="2026-10-01", valid_to="2027-12-31",
           payload={"doc_id": "policy-x", "approved_by": "합성", "approved_at": "2026-10-20", "policy_kind": "general"})
    db_session.execute(update(BrainObject).where(BrainObject.item_key == "common/depth-x")
                       .values(created_by="agent:cs_photo"))
    db_session.commit()
    return admin.id


def test_card_details_hide_machine_words_and_show_each_field_once(app, card_world):
    html = _client(app, card_world).get("/brain/items/common/depth-x").get_data(as_text=True)
    assert "버전 1" in html and "common/depth-x · 버전" not in html  # 키는 주소에만
    assert 'data-brain-key-field="payload.basis">내경(안쪽 치수)<' in html
    assert '<option value="inner">내경(안쪽 치수)</option>' in html and ">inner<" not in html  # 값은 그대로 · 글만 이름표
    assert "plan:synth" not in html  # 기계 꼴 근거 위치
    assert "AI(사진 다시 배우기)" in html and "cs_photo" not in html  # 만든 이 · 수정 기록
    policy = _client(app, card_world).get("/brain/items/common/policy-x").get_data(as_text=True)
    assert "근거 위치 합성 원장 줄" in policy  # 대조군: 사람이 쓴 근거 위치는 보인다
    assert policy.count("<dt>마지막 확인</dt>") == 1 and "<dt>유효 시작</dt>" not in policy  # 같은 칸 한 번
    assert "<dt>유효 기간</dt>" in policy and 'data-brain-key-field="payload.policy_kind">일반<' in policy
