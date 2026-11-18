"""문장으로 고치기 2판 — 세부 칸(실음 칸) 고치기 · 새 항목의 세부 칸(설계서 2026-11-18 12절 '세부 칸은 다음 판') 가짜 AI 시험.

1. 받는 칸(제품 라인의 문 방식 · 견적 규칙 종류 · 가로 범위, 정책 갈래, 조건 꼴)은 미리 보기 → 반영 → 되돌리기. 반영 뒤 다른
   실음 칸은 그대로, 되돌리면 전 값. 화면 값 ``fields`` 는 화면 말(칸 이름표 · 고르기 이름표 · 목록 ' · ' · 단위).
2. 막는 길: 받지 않는 칸(``prop_field``) · 고른 값 밖(``prop_value``) · 같은 값(모음이 같으면 차례가 달라도) · 새 사실에 세부 칸.
3. 새 정책 · 제작 조건은 정책 갈래 · 조건 꼴을 받는다(안 주면 비운다).
4. AI 에 가는 재료 · 틀 · 지시문(칸 · 지금 값 · 고를 수 있는 값 · 규칙 14). 틀 밖 세부 칸 답은 반영 0.
5. 1판에 저장된 묶음(세부 칸 없는 꼴)을 새 코드가 읽고 · 반영하고 · 되돌린다.
합성 지식 · 합성 계정만(금액 · 손님 글 · 직원 이름 없음).
"""

from __future__ import annotations

import copy
import json

import pytest

from db import db_session
from foms.persistence.brain.models import BrainChangeRequest
from foms.services.ai_staff.registry import level_of
from foms.services.brain import change_request as cr
from foms.services.brain.change_request_props import PROP_FIELDS, PROP_NAMES
from foms.services.brain.store import current_link, current_object
from tests.domains.test_brain_change_request import (
    APPLY_AT, NEW_TEXT, OLD_TEXT, REVERT_AT, START_AT, _start, answer_text, fake_queue, flags_on, upd, world,
)
from tests.support.brain_chat_support import fixed
from tests.support.brain_support import create

LINE_PAYLOAD = {"door_kinds": ["hinged"], "quote_kind": "hinge", "aliases": ["합성 별칭"], "pref_label": "합성 문짝 줄"}
POLICY_PAYLOAD = {"doc_id": "synth-policy", "approved_by": "합성", "approved_at": "2026-10-20", "policy_kind": "general",
                  "regions": ["합성 권역"]}


@pytest.fixture
def who(app, monkeypatch):
    flags_on(monkeypatch)
    fake_queue(monkeypatch)
    people = world(db_session)
    admin = people["admin"]
    create(db_session, admin, "common/line", name="합성 문짝 줄", payload=copy.deepcopy(LINE_PAYLOAD))
    create(db_session, admin, "common/policy/ship", item_type="policy", name="합성 배송 정책", text="배송은 합성 규칙을 따른다.",
           payload=copy.deepcopy(POLICY_PAYLOAD))
    db_session.commit()
    return people


def props_upd(key, props, text="", why="문장대로 세부 칸"):
    row = upd(key, text=text, why=why)
    row["after"]["props"] = [{"name": n, "value": v} for n, v in props.items()]
    return row


def _lines(view):
    return [(l["kind"], l["key"], l["state"], (l["check"] or {}).get("code")) for l in view["lines"]]


# ── 1. 되는 길 ───────────────────────────────────────────────────────────
def test_allowed_detail_cells_apply_keep_other_cells_and_revert(who):
    admin = who["admin"]
    view = _start(admin, client=fixed(answer_text(updates=[
        props_upd("common/line", {"door_kinds": "sliding, hinged", "min_width_mm": "1200"}),
        props_upd("common/rule/assign", {"rule_kind": "requires"}, text=NEW_TEXT),
        props_upd("common/policy/ship", {"policy_kind": "shipping"})])))
    assert _lines(view) == [("update", "common/line", "preview", None),
                            ("update", "common/rule/assign", "preview", None),
                            ("update", "common/policy/ship", "preview", None)]
    line, rule, policy = view["lines"]
    assert line["fields"] == [
        {"name": "payload.door_kinds", "label": "문 방식", "before": "여닫이", "after": "여닫이 · 슬라이딩"},
        {"name": "payload.min_width_mm", "label": "최소 가로", "before": None, "after": "1200mm"}]
    assert line["before"] == {"payload.door_kinds": ["hinged"], "payload.min_width_mm": None}
    assert line["after"] == {"payload.door_kinds": ["hinged", "sliding"], "payload.min_width_mm": 1200}
    assert rule["fields"] == [{"name": "text", "label": "글", "before": OLD_TEXT, "after": NEW_TEXT},
                              {"name": "payload.rule_kind", "label": "조건 꼴", "before": None, "after": "필요"}]
    assert policy["fields"] == [{"name": "payload.policy_kind", "label": "정책 종류", "before": "일반", "after": "배송"}]

    done = cr.apply(db_session, admin, view["id"], now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "applied" and [l["state"] for l in done["lines"]] == ["applied"] * 3
    after = current_object(db_session, "common/line").payload
    assert after == {**LINE_PAYLOAD, "door_kinds": ["hinged", "sliding"], "min_width_mm": 1200}  # 다른 칸은 그대로
    assert current_object(db_session, "common/rule/assign").payload == {"rule_kind": "requires"}
    assert current_object(db_session, "common/rule/assign").text == NEW_TEXT
    assert current_object(db_session, "common/policy/ship").payload == {**POLICY_PAYLOAD, "policy_kind": "shipping"}

    back = cr.revert(db_session, admin, view["id"], now=REVERT_AT)
    db_session.commit()
    assert [l["state"] for l in back["lines"]] == ["reverted"] * 3
    assert current_object(db_session, "common/line").payload == LINE_PAYLOAD
    assert current_object(db_session, "common/policy/ship").payload == POLICY_PAYLOAD
    assert current_object(db_session, "common/rule/assign").text == OLD_TEXT
    assert not current_object(db_session, "common/rule/assign").payload  # 처음에 비어 있던 실음 칸


def test_an_int_cell_takes_its_unit_and_commas(who):
    view = _start(who["admin"], client=fixed(answer_text(updates=[
        props_upd("common/line", {"max_width_mm": "2,400mm", "quote_kind": "slide"})])))
    assert view["lines"][0]["state"] == "preview"
    assert [(f["label"], f["before"], f["after"]) for f in view["lines"][0]["fields"]] == [
        ("최대 가로", None, "2400mm"), ("견적 규칙 종류", "여닫이", "슬라이딩")]


# ── 2. 막는 길 ───────────────────────────────────────────────────────────
def test_cells_outside_the_list_values_outside_the_choices_and_same_values_are_blocked(who):
    view = _start(who["admin"], client=fixed(answer_text(updates=[
        props_upd("common/line", {"door_kinds": "hinged, glass"}),
        props_upd("common/door", {"lead_days": "9"}),
        props_upd("common/slide", {"policy_kind": "shipping"}),
        props_upd("common/policy/ship", {"policy_kind": "general"}),
        props_upd("common/rule/old", {"min_width_mm": "넓게"}, text="옛 규칙 새 글")])))
    assert _lines(view) == [("update", "common/line", "blocked", "prop_value"),
                            ("update", "common/door", "blocked", "prop_field"),
                            ("update", "common/slide", "blocked", "prop_field"),
                            ("update", "common/policy/ship", "blocked", "same"),
                            ("update", "common/rule/old", "blocked", "prop_field")]
    assert view["lines"][1]["fields"] == [{"name": "payload.lead_days", "label": "제작 기간", "before": None,
                                           "after": "9"}]
    assert view["lines"][0]["check"]["text"] == "세부 칸에 고를 수 없는 값이에요."
    assert view["can_apply"] is False and len(view["not_done"]) == 5
    assert current_object(db_session, "common/line").payload == LINE_PAYLOAD


def test_the_same_set_in_another_order_is_not_a_change(who):
    view = _start(who["admin"], client=fixed(answer_text(updates=[
        props_upd("common/line", {"door_kinds": "hinged", "quote_kind": "hinge"})])))
    assert _lines(view) == [("update", "common/line", "blocked", "same")]


def test_the_range_rule_still_runs_in_the_dry_run(who):
    view = _start(who["admin"], client=fixed(answer_text(updates=[
        props_upd("common/line", {"min_width_mm": "3000", "max_width_mm": "1000"})])))
    assert view["lines"][0]["state"] == "blocked" and view["lines"][0]["check"]["code"] == "BRAIN_SHAPE"


# ── 3. 새 항목 ───────────────────────────────────────────────────────────
def _new(item_type, name, props=None, text="새 글."):
    return {"type": item_type, "brand": "COMMON", "why": "새 지식",
            "values": {"name": name, "text": text, "props": [{"name": n, "value": v} for n, v in (props or {}).items()]}}


def test_new_policy_and_build_rule_take_their_kind_and_a_fact_takes_none(who):
    admin = who["admin"]
    view = _start(admin, client=fixed(answer_text(
        creates=[_new("policy", "합성 시공 정책", {"policy_kind": "install"}),
                 _new("build_rule", "합성 문짝 조건", {"rule_kind": "excludes"}),
                 _new("fact", "합성 사실", {"policy_kind": "install"}),
                 _new("policy", "합성 갈래 없는 정책"),
                 _new("policy", "합성 틀린 갈래", {"policy_kind": "everything"})],
        links=[{"op": "add", "kind": "applies_to", "from": "new:2", "to": "common/line", "why": "걸 제품"}])))
    assert _lines(view) == [("create", "common/cr1-1", "preview", None), ("create", "common/cr1-2", "preview", None),
                            ("create", "common/cr1-3", "blocked", "prop_field"),
                            ("create", "common/cr1-4", "preview", None),
                            ("create", "common/cr1-5", "blocked", "prop_value"),
                            ("link_add", "common/cr1-2", "preview", None)]
    assert view["lines"][0]["fields"][-1] == {"name": "payload.policy_kind", "label": "정책 종류", "before": None,
                                              "after": "시공"}
    assert view["lines"][1]["fields"][-1]["after"] == "함께 못 함"
    done = cr.apply(db_session, admin, view["id"], now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "applied"
    policy, rule = current_object(db_session, "common/cr1-1"), current_object(db_session, "common/cr1-2")
    assert policy.payload["policy_kind"] == "install" and policy.payload["doc_id"] == "cr1-1"
    assert rule.payload["rule_kind"] == "excludes"
    assert "policy_kind" not in current_object(db_session, "common/cr1-4").payload  # 안 주면 비운다
    assert current_link(db_session, "applies_to", "common/cr1-2", "common/line") is not None


# ── 4. 재료 · 틀 · 지시문 ────────────────────────────────────────────────
def test_material_schema_and_rule_tell_the_ai_which_cells_and_values(who):
    client = fixed(answer_text())
    _start(who["admin"], "합성 문짝 줄 문 방식 바뀜", client=client)
    params = client.calls[0]
    system = params["system"][0]["text"]
    assert "세부 칸(props)은 재료에 적힌 칸과 고른 값만 쓴다" in system and "문장이 그 값을 분명히 말할 때만 고친다" in system
    block = params["messages"][0]["content"].split("지시 아님]\n", 1)[1].rsplit("\n\n위 규칙대로", 1)[0]
    material = json.loads(block)
    items = {i["key"]: i for i in material["items"]}
    assert items["common/line"]["props"] == {"door_kinds": ["hinged"], "quote_kind": "hinge", "min_width_mm": None,
                                             "max_width_mm": None}
    assert all(("props" in i) == (i["type"] in PROP_FIELDS) for i in material["items"])  # 받는 칸이 없는 유형은 싣지 않는다
    cells = {t: {c["name"]: c for c in rows} for t, rows in material["prop_cells"].items()}
    assert set(cells) == set(PROP_FIELDS) and set(cells["product_line"]) == set(PROP_FIELDS["product_line"])
    assert cells["product_line"]["door_kinds"]["choices"]["sliding"] == "슬라이딩"
    assert cells["product_line"]["door_kinds"]["list"] is True and cells["product_line"]["min_width_mm"]["unit"] == "mm"
    assert cells["policy"]["policy_kind"]["choices"]["shipping"] == "배송" and set(cells["build_rule"]) == {"rule_kind"}
    assert material["new_prop_types"] == ["policy", "build_rule"]
    schema = params["output_config"]["format"]["schema"]["properties"]
    after = schema["updates"]["items"]["properties"]["after"]
    assert "props" in after["required"]
    assert after["properties"]["props"]["items"]["properties"]["name"]["enum"] == list(PROP_NAMES)
    assert "props" in schema["creates"]["items"]["properties"]["values"]["properties"]


@pytest.mark.parametrize("props", ["문 방식", [{"name": "door_kinds"}], [{"name": "door_kinds", "value": 2}],
                                   [{"name": "door_kinds", "value": "hinged", "extra": "x"}]])
def test_detail_cells_outside_the_frame_apply_nothing(who, props):
    row = upd("common/line")
    row["after"]["props"] = props
    view = _start(who["admin"], client=fixed(answer_text(updates=[row])))
    assert view["status"] == "failed" and view["error_code"] == "bad_response" and view["lines"] == []


# ── 5. 1판 묶음 ──────────────────────────────────────────────────────────
def test_a_bundle_saved_by_the_first_version_still_reads_applies_and_reverts(who):
    """1판이 저장한 꼴 그대로(세부 칸 · 다듬은 글 없음 — 줄 이름이 주소인 것도 그대로 읽는다)."""
    admin = who["admin"]
    row = BrainChangeRequest(created_by=admin.id, layer_scope="all", masked_text="합성 문장", status="ready",
                             created_at=START_AT, bundle={
        "answers": [], "analyzing_at": START_AT.isoformat(), "claimed": START_AT.isoformat(), "summary": "합성 요약",
        "lines": [
            {"no": 1, "kind": "update", "key": "common/rule/assign", "label": "도면 담당 정하기", "layer": "common",
             "before": {"text": OLD_TEXT}, "after": {"text": NEW_TEXT},
             "fields": [{"name": "text", "label": "글", "before": OLD_TEXT, "after": NEW_TEXT}], "why": "합성",
             "check": None, "state": "preview", "caution": False, "change_id": None,
             "plan": {"key": "common/rule/assign", "base_version": 1, "after": {"text": NEW_TEXT}}},
            {"no": 2, "kind": "setting", "key": "ops.assign_draftsman", "label": "합성 설정", "layer": None,
             "before": {"level": 2}, "after": {"level": 0},
             "fields": [{"name": "level", "label": "수준", "before": 2, "after": 0}], "why": "합성", "check": None,
             "state": "preview", "caution": False, "change_id": None,
             "plan": {"area": "ai_staff_levels", "agent": "ops", "action": "assign_draftsman", "value": 0,
                      "before": 2}},
            {"no": 3, "kind": "update", "key": "common/nope", "label": "common/nope", "layer": None, "before": None,
             "after": None, "fields": [], "why": "합성", "check": {"code": "unknown_key", "text": "합성"},
             "state": "blocked", "caution": False, "change_id": None, "plan": {}}],
        "also_look": [{"key": None, "label": "common/zzz — 합성", "why": None}], "needs_code": [], "questions": [],
        "model": "synthetic", "raw": {}, "settings": []})
    db_session.add(row)
    db_session.commit()
    seen = cr.view(db_session, admin, row.id, now=START_AT)
    assert seen["can_apply"] is True and [l["state"] for l in seen["lines"]] == ["preview", "preview", "blocked"]
    done = cr.apply(db_session, admin, row.id, now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "applied" and [l["state"] for l in done["lines"]] == ["applied", "applied", "blocked"]
    assert done["lines"][1]["fields"][0]["before"] == "2 제안"  # 반영 때 다시 적는 전 값은 화면 말
    assert current_object(db_session, "common/rule/assign").text == NEW_TEXT and level_of(
        db_session, "ops", "assign_draftsman") == 0
    back = cr.revert(db_session, admin, row.id, now=REVERT_AT)
    db_session.commit()
    assert back["status"] == "reverted" and current_object(db_session, "common/rule/assign").text == OLD_TEXT
    assert level_of(db_session, "ops", "assign_draftsman") == 2
