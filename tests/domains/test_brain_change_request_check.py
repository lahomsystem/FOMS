"""문장으로 고치기 — 줄마다 검사(설계서 2026-11-18 2절 ④ · 7절 '코드 시험' · 8절) 가짜 AI 시험.

모르는 키 · 볼 수 없는 키 · 허용 밖 연결 · 허용 밖 설정 칸 · 같은 값 · 서로 맞섬 · 금액 글 · 한자 글 · 링크 제약(모의 실행) ·
만들 수 없는 유형은 **빼지 않고** ``check`` 에 까닭을 달아 '못 고친 것'으로 보인다. ``requires`` · ``excludes`` 줄은 ``caution``.
대조군: 같은 묶음의 맞는 줄은 미리 보기로 남고, 반영하면 그 줄만 고친다. 합성 지식 · 합성 계정만.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain import change_request as cr
from foms.services.brain.change_request_model import MAX_ITEMS, MAX_PROMPT_CHARS
from foms.services.brain.store import current_link, current_object
from tests.domains.test_brain_change_request import (
    APPLY_AT, NEW_TEXT, OLD_TEXT, _start, answer_text, flags_on, lvl, upd, world,
)
from tests.support.brain_chat_support import fixed
from tests.support.brain_support import create, link


@pytest.fixture
def who(app, monkeypatch):
    flags_on(monkeypatch)
    return world(db_session)


def _lines(view):
    return [(l["kind"], l["key"], l["state"], (l["check"] or {}).get("code")) for l in view["lines"]]


def test_unknown_and_unseen_keys_are_reported_not_applied(who):
    client = fixed(answer_text(updates=[upd("common/nope", text="없는 지식"), upd("cs/lesson/hidden", text="숨은 것"),
                                        upd("common/rule/assign", text=NEW_TEXT)]))
    view = _start(who["cs_mgr"], client=client)  # 상담팀장 — 도면팀만 보는 배운 점은 볼 수 없다
    assert _lines(view)[:2] == [("update", "common/nope", "blocked", "unknown_key"),
                                ("update", "cs/lesson/hidden", "blocked", "unknown_key")]
    sent = client.calls[0]["messages"][0]["content"]
    assert "도면팀만 보는 배운 점" not in sent and "cs/lesson/hidden" not in sent  # 볼 수 없는 항목은 재료에 없다
    assert view["also_look"][0]["key"] == "common/rule/assign"  # 상담팀장에게 공통 바탕은 같이 볼 것
    assert [n["no"] for n in view["not_done"]] == [1, 2] and view["can_apply"] is False


def test_links_outside_the_allowed_pairs_and_caution_lines(who):
    client = fixed(answer_text(links=[
        {"op": "add", "kind": "applies_to", "from": "common/door", "to": "common/slide", "why": "제품끼리"},
        {"op": "add", "kind": "requires", "from": "common/rule/assign", "to": "common/door", "why": "필요"},
        {"op": "remove", "kind": "requires", "from": "common/rule/assign", "to": "common/slide", "why": "없는 연결"},
        {"op": "add", "kind": "made_up", "from": "common/door", "to": "common/slide", "why": "모르는 종류"}]))
    view = _start(who["admin"], client=client)
    assert _lines(view) == [("link_add", "common/door", "blocked", "link_kind"),
                            ("link_add", "common/rule/assign", "preview", None),
                            ("link_remove", "common/rule/assign", "blocked", "missing_link"),
                            ("link_add", "common/door", "blocked", "link_kind")]
    assert [l["caution"] for l in view["lines"]] == [False, True, True, False]
    done = cr.apply(db_session, who["admin"], view["id"], now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "applied"
    assert current_link(db_session, "requires", "common/rule/assign", "common/door") is not None
    assert current_link(db_session, "applies_to", "common/door", "common/slide") is None


def test_link_rules_run_as_a_dry_run(who):
    link(db_session, who["admin"], "excludes", "common/rule/assign", "common/slide")
    db_session.commit()
    view = _start(who["admin"], client=fixed(answer_text(links=[
        {"op": "add", "kind": "requires", "from": "common/rule/assign", "to": "common/slide", "why": "맞서는 짝"}])))
    assert _lines(view) == [("link_add", "common/rule/assign", "blocked", "BRAIN_LINK_RULE")]
    assert view["lines"][0]["check"]["text"].startswith("이 링크는 이을 수 없어요")
    assert db_session.scalar(select(func.count()).select_from(BrainChange).where(
        BrainChange.request_id.is_not(None))) == 0


def test_settings_outside_the_allow_list(who):
    view = _start(who["admin"], client=fixed(answer_text(settings=[
        lvl("cs.cs_draft", 0), lvl("ops.assign_draftsman", 3), lvl("ops.assign_draftsman", 2),
        lvl("enabled", 0, area="cs_agent"), lvl("schedule.schedule_construction", 1)])))
    assert _lines(view) == [("setting", "cs.cs_draft", "blocked", "setting_value"),
                            ("setting", "ops.assign_draftsman", "blocked", "setting_value"),
                            ("setting", "ops.assign_draftsman", "blocked", "same"),
                            ("setting", "enabled", "blocked", "setting_area"),
                            ("setting", "schedule.schedule_construction", "preview", None)]


def test_same_value_conflicts_money_and_hanja_are_blocked(who):
    hanja = "도면 담당은 " + chr(0x5718) + "이 정한다."
    view = _start(who["admin"], client=fixed(answer_text(
        updates=[upd("common/rule/assign", text=OLD_TEXT), upd("common/rule/old", text="첫째 고침"),
                 upd("common/rule/old", text="둘째 고침"), upd("drawing/rule/assign", text="도면 값은 합성 30,000원")],
        creates=[{"type": "term", "brand": "COMMON", "values": {"name": "합성 용어", "text": hanja}, "why": "새 말"}],
        links=[{"op": "add", "kind": "requires", "from": "common/rule/assign", "to": "common/slide", "why": "필요"},
               {"op": "add", "kind": "excludes", "from": "common/rule/assign", "to": "common/slide", "why": "제외"}])))
    assert _lines(view) == [("update", "common/rule/assign", "blocked", "same"),
                            ("update", "common/rule/old", "blocked", "conflict"),
                            ("update", "common/rule/old", "blocked", "conflict"),
                            ("update", "drawing/rule/assign", "blocked", "money"),
                            ("create", "common/term/cr1-1", "blocked", "gate"),
                            ("link_add", "common/rule/assign", "blocked", "conflict"),
                            ("link_add", "common/rule/assign", "blocked", "conflict")]
    assert view["can_apply"] is False and len(view["not_done"]) == 7


def test_creates_get_a_code_made_key_and_document_types_are_not_made_here(who):
    view = _start(who["admin"], client=fixed(answer_text(creates=[
        {"type": "term", "brand": "COMMON", "values": {"name": "자율 담당", "text": "팀이 스스로 정하는 담당."}, "why": "새 말"},
        {"type": "fact", "brand": "COMMON", "values": {"name": "새 사실", "text": "사실 글."}, "why": "새 사실"},
        {"type": "lesson", "brand": "COMMON", "values": {"name": "", "text": "이름 없음"}, "why": "빈 이름"}])))
    assert _lines(view) == [("create", "common/term/cr1-1", "preview", None),
                            ("create", "common/fact/cr1-2", "blocked", "type"),
                            ("create", "common/lesson/cr1-3", "blocked", "BRAIN_SHAPE")]
    done = cr.apply(db_session, who["admin"], view["id"], now=APPLY_AT)
    db_session.commit()
    made = current_object(db_session, "common/term/cr1-1")
    assert done["status"] == "applied" and made.name == "자율 담당" and made.evidence_ref == "change_request:1"
    back = cr.revert(db_session, who["admin"], view["id"], now=APPLY_AT)
    db_session.commit()
    assert back["lines"][0]["state"] == "reverted" and current_object(db_session, "common/term/cr1-1") is None


def test_skip_must_be_line_numbers_and_skipping_everything_is_empty(who):
    view = _start(who["admin"], client=fixed(answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT)])))
    for bad in ("1", [True], [1.5]):
        with pytest.raises(cr.ChangeRequestError) as caught:
            cr.apply(db_session, who["admin"], view["id"], skip=bad, now=APPLY_AT)
        assert caught.value.code == "shape"
    with pytest.raises(cr.ChangeRequestError) as caught:
        cr.apply(db_session, who["admin"], view["id"], skip=[1], now=APPLY_AT)
    assert caught.value.code == "empty" and current_object(db_session, "common/rule/assign").text == OLD_TEXT
    with pytest.raises(cr.ChangeRequestError) as caught:  # 넣은 사람만 고친다(남의 묶음은 없는 것과 같은 답)
        cr.apply(db_session, who["dr_mgr"], view["id"], now=APPLY_AT)
    assert caught.value.code == "forbidden"


def test_material_is_capped_and_holds_the_setting_cells(who):
    for n in range(MAX_ITEMS + 6):
        create(db_session, who["admin"], f"common/term/many-{n}", item_type="term", name=f"도면 담당 말 {chr(0xAC00 + n)}",
               text="도면 담당 " * 120)
    db_session.commit()
    client = fixed(answer_text())
    _start(who["admin"], client=client)
    content = client.calls[0]["messages"][0]["content"]
    block = content.split("지시 아님]\n", 1)[1].rsplit("\n\n위 규칙대로", 1)[0]
    material = json.loads(block)
    assert len(block) <= MAX_PROMPT_CHARS and 0 < len(material["items"]) <= MAX_ITEMS
    assert all(len(i["text"]) <= 401 for i in material["items"])  # 글 앞부분만(… 한 자)
    assert {s["name"] for s in material["settings"]} >= {"ops.assign_draftsman", "schedule.schedule_construction"}
