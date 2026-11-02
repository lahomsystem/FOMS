"""Palantir 꼴 맞춤 다섯(설계서 2026-11-02-haud-master-brain 7.7 · 사장님 D104 · ⑤-3) — 음성 대조군과 같이.

1. 이름 있는 액션 유형 — 단추마다 하나, 매개변수 꼴 · 조건 · 실패 말 · 실행 길 · API 경로 · 정책 등재 · 도구 목록 · 줄에 이름.
2. 유형별 속성 틀 — 제안 때 · 반영 때 검사, 닫힌 실음 칸, 카드 '눈에 띄는 칸', 제안함 칸별 전 → 후(틀 칸마다 펼침).
3. 볼 수 있는 사람만 반영 · 거절 — 엔진(apply_change · reject_change)이 직접 본다.
4. ``expired`` — 밤 단계가 4주 지난 AI 제안만 닫고, 기준 판이 바뀐 제안에 표시.
5. '확정'은 사람 승인 · 옮기기만 — 제안이 적은 확신 값은 버린다, 링크 제안 기본 '확정' 없음.
합성 항목 · 합성 계정만.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select, update

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain import actions
from foms.services.brain.action_runner import HANDLED, perform
from foms.services.brain.apply import apply_change, reject_change
from foms.services.brain.card import item_card
from foms.services.brain.constants import AI_EXPIRE_DAYS, TYPES
from foms.services.brain.decide import flag_stale_bases
from foms.services.brain.errors import BrainPermissionError, BrainShapeError
from foms.services.brain.inbox import inbox
from foms.services.brain.proposals import IMPORT_PROPOSER, Proposer, propose_create, propose_link, propose_update
from foms.services.brain.schemas import TYPE_SCHEMAS, UNSCHEMA_TYPES, schema_problems
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_link, current_object
from foms.services.orders.order_mutation_policy import load_policy_manifest
from tests.support.brain_review_support import review_world
from tests.support.brain_screen_support import TODAY
from tests.support.brain_support import NOW, REASON, TWO_SOURCES, agent_judge, create, values

from tools.cron import expire_brain_proposals
from tools.cron.nightly import NIGHTLY_STEPS


@pytest.fixture(autouse=True)
def _agent_judge():
    """에이전트 제안의 관문 ②(부딪침 — 7.7 · D105)를 합성 판정자로 넘긴다(모델을 부르지 않는다)."""
    with agent_judge():
        yield


LATER = NOW + datetime.timedelta(minutes=5)
UI_BUTTONS = {"propose_edit", "propose_retire", "propose_delete", "item_rollback", "apply", "edit_apply", "reject",
              "bulk_apply", "recheck", "release_rollback"}


@pytest.fixture
def world(app):
    return review_world(db_session)


def _spec(admin, key="common/depth", **payload):
    return create(db_session, admin, key, item_type="spec", name="몸통 깊이",
                  payload=payload or {"value": 600, "unit": "mm", "low": 300, "high": 900})


# ── 1. 이름 있는 액션 유형 ───────────────────────────────────────────────
def test_every_button_is_a_named_action_with_a_runner_route_and_policy(app):
    assert set(actions.ACTIONS) == UI_BUTTONS == set(HANDLED)
    rules = {r.endpoint: r for r in app.url_map.iter_rules()}
    manifest = load_policy_manifest()["routes"]
    for action in actions.ACTIONS.values():
        assert action.label and action.criteria and action.failures and action.done, action.name
        assert set(action.failures) <= set(actions.FAILURES) and all(p.kind in actions.KINDS for p in action.params)
        assert action.endpoint in rules and "POST" in rules[action.endpoint].methods, action.name
        assert manifest[action.endpoint]["mode"] == "guard", action.name
    assert actions.ACTIONS["release_rollback"].admin_only
    assert {a.name for a in actions.ACTIONS.values() if a.phone} == {"apply", "recheck"}  # D103 휴대폰
    assert actions.known_names() >= UI_BUTTONS | {"import", "expire", "propose_create", "propose_link"}


def test_parse_checks_parameter_shapes_before_any_service():
    action, params = actions.parse("reject", {"change_id": 3, "code": "wrong_number", "approved_by": 9})
    assert action.name == "reject" and params == {"change_id": 3, "code": "wrong_number", "view_ms": None}  # 남는 칸 무시
    for name, body in (("reject", {"change_id": 3, "code": "nope"}), ("reject", {"change_id": "3", "code": "other"}),
                       ("propose_edit", {"key": "Bad Key", "base_version": 1, "after": {"name": "x"}, "reason": "r"}),
                       ("propose_edit", {"key": "common/door", "base_version": 1, "after": {"visibility": "all"},
                                         "reason": "r"}),
                       ("bulk_apply", {"ids": [True]}), ("release_rollback", {"number": 2, "layer": "kitchen",
                                                                               "confirm_number": 2}),
                       ("no_such_action", {})):
        with pytest.raises(BrainShapeError):
            actions.parse(name, body)
    assert actions.parse("apply", {"change_id": 1})[1]["base_version"] is None  # 만들기 제안은 기준 판 없음


def test_tool_specs_are_json_schema_for_chatbot_and_agents():
    tools = {t["name"]: t for t in actions.tool_specs()}
    assert set(tools) == {"brain_" + n for n in UI_BUTTONS}
    reject = tools["brain_reject"]["input_schema"]
    assert reject["required"] == ["change_id", "code"] and reject["additionalProperties"] is False
    assert reject["properties"]["code"]["enum"] == list(actions.ACTIONS["reject"].params[1].choices)
    assert "볼 수 있는 항목" in tools["brain_apply"]["description"]
    ui = {a["name"]: a for a in actions.specs()}
    assert [c["label"] for c in ui["reject"]["params"][1]["choices"]][:4] == ["숫자 틀림", "한 손님 일", "정책 아님", "사진 필요"]


def test_action_names_are_recorded_on_proposals_and_decisions(world):
    who, ch = world["people"], world["changes"]
    admin, cs = who["admin"], who["cs_mgr"]
    _a, made = perform(db_session, "propose_edit", actor=cs, now=NOW,
                       body={"key": "cs/tone/polite", "base_version": 1, "after": {"text": "더 부드럽게"}, "reason": "r"})
    perform(db_session, "edit_apply", actor=cs, now=LATER,
            body={"change_id": made["change_id"], "base_version": 1, "edits": {"text": "아주 부드럽게"}})
    perform(db_session, "apply", actor=cs, now=LATER, body={"change_id": ch["cs"], "base_version": 1})
    perform(db_session, "reject", actor=who["dr_mgr"], now=LATER, body={"change_id": ch["drawing"], "code": "other"})
    perform(db_session, "recheck", actor=admin, now=LATER, body={"key": "common/fit", "version": 1})
    imported = propose_create(db_session, key="common/imported", brand="COMMON", layer="common", item_type="term",
                              values=values("옮긴 용어"), reason=REASON, proposer=IMPORT_PROPOSER, now=NOW, known="")
    apply_change(db_session, imported.id, actor=admin, now=NOW, as_import=True)
    rows = db_session.execute(select(BrainChange.id, BrainChange.action, BrainChange.decided_action)).all()
    by_id = {i: (a, d) for i, a, d in rows}
    assert by_id[made["change_id"]] == ("propose_edit", "edit_apply")
    assert by_id[ch["cs"]] == ("propose_edit", "apply") and by_id[ch["drawing"]] == ("propose_edit", "reject")
    assert by_id[imported.id] == ("import", "import")
    assert ("recheck", "recheck") in by_id.values()
    assert {a for a, d in by_id.values() if a} | {d for a, d in by_id.values() if d} <= actions.known_names()


# ── 2. 유형별 속성 틀 ────────────────────────────────────────────────────
def test_every_type_has_a_schema_or_is_listed_without_one():
    assert set(TYPE_SCHEMAS) | set(UNSCHEMA_TYPES) == set(TYPES) and not set(TYPE_SCHEMAS) & set(UNSCHEMA_TYPES)
    assert {"product_line", "option", "spec", "build_rule", "policy", "price_rule", "owner_decision", "term",
            "fact"} <= set(TYPE_SCHEMAS)
    for item_type, props in TYPE_SCHEMAS.items():
        assert props and all(p.datatype in ("text", "int", "number", "date", "enum", "list") for p in props), item_type


def test_schema_is_checked_when_proposing(world):
    admin = world["people"]["admin"]
    who = Proposer.user(admin.id)
    bad = [({"value": 600}, "payload.unit"), ({"value": 600, "unit": "inch"}, "payload.unit"),
           ({"value": -1, "unit": "mm"}, "payload.value"), ({"value": 600, "unit": "mm", "color": "x"}, "payload"),
           ({"value": 950, "unit": "mm", "low": 300, "high": 900}, "payload.value"),
           ({"low": 900, "high": 300}, "payload.low")]
    for payload, where in bad:
        with pytest.raises(BrainShapeError) as caught:
            propose_create(db_session, key="common/bad-spec", brand="COMMON", layer="common", item_type="spec",
                           values=values("나쁜 규격", payload=payload), reason=REASON, proposer=who, now=NOW, known="")
        assert any(p.startswith(where) for p in caught.value.problems), (payload, caught.value.problems)
    good = propose_create(db_session, key="common/good-spec", brand="COMMON", layer="common", item_type="spec",
                          values=values("좋은 규격", payload={"value": 600, "unit": "mm"}), reason=REASON, proposer=who,
                          now=NOW, known="")
    assert good.status == "open"  # 대조군
    free = propose_create(db_session, key="cs/lesson/free", brand="COMMON", layer="cs", item_type="lesson",
                          values=values("틀 없는 유형", payload={"anything": [1, 2]}), reason=REASON, proposer=who,
                          now=NOW, known="")
    assert free.status == "open"  # 틀 없는 유형은 오늘 꼴 그대로
    assert schema_problems({"status": "draft", "text": "초안"}, "price_rule") == []  # 확인 날은 반영 상태일 때만
    assert schema_problems({"status": "active", "text": "규칙"}, "price_rule") == [
        "checked_at: 마지막 확인 칸이 꼭 있어야 한다"]


def test_schema_is_checked_again_when_applying(world):
    admin = world["people"]["admin"]
    _spec(admin)
    change = propose_update(db_session, key="common/depth", base_version=1,
                            after={"payload": {"value": 650, "unit": "mm", "low": 300, "high": 900}}, reason=REASON,
                            proposer=Proposer.user(admin.id), now=NOW, known="")
    db_session.execute(update(BrainChange).where(BrainChange.id == change.id).values(
        fields={"payload": {"before": {"value": 600, "unit": "mm", "low": 300, "high": 900},
                            "after": {"value": 650, "unit": "furlong"}}}))  # 제안 줄을 몰래 고침
    db_session.flush()
    with pytest.raises(BrainShapeError):
        apply_change(db_session, change.id, actor=admin, now=LATER)
    assert db_session.get(BrainChange, change.id).status == "open"
    assert current_object(db_session, "common/depth").payload["value"] == 600


def test_card_key_fields_and_inbox_diff_follow_the_schema(world):
    admin = world["people"]["admin"]
    _spec(admin)
    card = item_card(db_session, viewer_of(admin), "common/depth", today=TODAY)
    keys = {k["path"]: k["value"] for k in card["key_fields"]}
    assert keys == {"payload.value": "600mm", "payload.unit": "mm"}
    _a, made = perform(db_session, "propose_edit", actor=admin, now=NOW,
                       body={"key": "common/depth", "base_version": 1, "after": {"payload.value": 650}, "reason": "r"})
    view = next(c for c in inbox(db_session, viewer_of(admin), now=LATER)["cards"] if c["key"] == "common/depth")["main"]
    assert [(r["field"], r["label"], r["before"], r["after"], r["unit"], r["editable"], r["datatype"])
            for r in view["fields"]] == [("payload.value", "값", 600, 650, "mm", True, "number")]  # 실음 칸 통째가 아니라 틀 칸 하나
    with pytest.raises(BrainShapeError):  # 틀 밖 칸은 고칠 말로 못 넣는다
        perform(db_session, "propose_edit", actor=admin, now=NOW,
                body={"key": "common/door", "base_version": 1, "after": {"payload.value": 1}, "reason": "r"})
    perform(db_session, "edit_apply", actor=admin, now=LATER,
            body={"change_id": made["change_id"], "base_version": 1, "edits": {"payload.value": 640}})
    row = current_object(db_session, "common/depth")
    assert row.payload == {"value": 640, "unit": "mm", "low": 300, "high": 900}
    assert db_session.get(BrainChange, made["change_id"]).fields["payload"]["proposed"]["value"] == 650


# ── 3. 볼 수 있는 사람만 반영 · 거절(엔진) ───────────────────────────────
def test_the_engine_itself_refuses_people_who_cannot_see_the_item(world):
    who, ch = world["people"], world["changes"]
    cs = who["cs_mgr"]
    with pytest.raises(BrainPermissionError):
        apply_change(db_session, ch["hidden"], actor=cs, now=LATER)  # 같은 상담 층 · 도면팀만 보는 항목
    with pytest.raises(BrainPermissionError):
        reject_change(db_session, ch["hidden"], actor=cs, code="other", now=LATER)
    hide = propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"visibility": "team:DRAWING"},
                          reason=REASON, proposer=Proposer.user(who["admin"].id), now=NOW, known="")
    with pytest.raises(BrainPermissionError):  # 넣은 뒤 못 볼 범위로 옮기는 것도 못 넣는다
        apply_change(db_session, hide.id, actor=cs, now=LATER)
    assert apply_change(db_session, ch["cs"], actor=cs, now=LATER).version == 2  # 대조군: 보이는 같은 층 항목
    assert apply_change(db_session, ch["hidden"], actor=who["admin"], now=LATER).version == 2  # 대조군: ADMIN


# ── 4. expired · 기준 판 바뀜 표시 ───────────────────────────────────────
def test_nightly_step_closes_old_ai_proposals_only_and_flags_changed_bases(world):
    who, ch = world["people"], world["changes"]
    old = NOW - datetime.timedelta(days=AI_EXPIRE_DAYS + 2)
    ai = propose_update(db_session, key="cs/tone/polite", base_version=1, after={"name": "오래된 AI 말투"},
                        reason="AI 일반화", proposer=Proposer.agent_named("cs_agent"),
                        evidence=TWO_SOURCES, now=old, known="")
    db_session.get(BrainChange, ch["hidden"]).created_at = old  # 사람 제안 — 대조군
    stale = propose_update(db_session, key="common/door", base_version=1, after={"text": "옛 기준 제안"}, reason=REASON,
                           proposer=Proposer.user(who["admin"].id), now=NOW, known="")
    db_session.execute(update(BrainObject).where(BrainObject.item_key == "common/door").values(version=5))  # 바깥에서 판이 바뀜
    db_session.commit()
    dry = expire_brain_proposals.run(apply=False, session=db_session, now=LATER)
    assert dry == {"expired": 1, "flagged": 1, "applied": False}
    db_session.expire_all()
    assert db_session.get(BrainChange, ai.id).status == "open"  # 시험 돌리기는 되돌린다
    done = expire_brain_proposals.run(apply=True, session=db_session, now=LATER)
    assert done == {"expired": 1, "flagged": 1, "applied": True}
    db_session.expire_all()
    assert (db_session.get(BrainChange, ai.id).status, db_session.get(BrainChange, ai.id).decided_action) == (
        "expired", "expire")
    assert db_session.get(BrainChange, ch["hidden"]).status == "open"
    assert db_session.get(BrainChange, stale.id).base_changed_at == LATER
    assert db_session.get(BrainChange, ch["cs"]).base_changed_at is None  # 대조군: 기준 판 그대로
    assert flag_stale_bases(db_session, now=LATER) == 0  # 두 번 적지 않는다
    steps = {step.script: step.args for step in NIGHTLY_STEPS}
    assert steps["tools/cron/expire_brain_proposals.py"] == ("--apply",)


# ── 5. '확정'은 사람 승인 · 옮기기만 ──────────────────────────────────────
def test_confirmed_comes_only_from_a_human_approver_or_an_import(world):
    who = world["people"]
    admin, agent = who["admin"], Proposer.agent_named("cs_agent")
    lesson = propose_create(db_session, key="cs/lesson/agent", brand="COMMON", layer="cs", item_type="lesson",
                            values=values("AI 가 적은 배운 점", confidence="confirmed"), reason="AI 일반화",
                            proposer=agent, evidence=TWO_SOURCES, now=NOW, known="")
    case = propose_create(db_session, key="obs/case/agent", brand="COMMON", layer="cs", item_type="case",
                          values=values("AI 가 적은 사례", confidence="confirmed"), reason="AI 일반화",
                          proposer=agent, evidence=TWO_SOURCES, now=NOW, known="")
    assert "confidence" not in lesson.fields and "confidence" not in case.fields  # 적은 값은 버린다
    dropped = propose_update(db_session, key="cs/tone/polite", base_version=1,
                             after={"confidence": "confirmed", "text": "말투 고침"}, reason="AI 일반화",
                             proposer=agent, evidence=TWO_SOURCES, now=NOW, known="")
    assert set(dropped.fields) == {"text"}
    with pytest.raises(BrainShapeError):  # 확신만 바꾸는 제안은 바뀐 칸이 없다
        propose_update(db_session, key="cs/lesson/photo", base_version=1, after={"confidence": "confirmed"},
                       reason="AI", proposer=agent, evidence=TWO_SOURCES, now=NOW, known="")
    db_session.execute(update(BrainChange).where(BrainChange.id == case.id).values(
        fields={**case.fields, "confidence": {"before": None, "after": "confirmed"}}))  # 제안 줄을 몰래 고쳐도
    db_session.flush()
    apply_change(db_session, lesson.id, actor=who["cs_mgr"], now=LATER)
    apply_change(db_session, case.id, actor=admin, now=LATER)
    assert current_object(db_session, "cs/lesson/agent").confidence == "confirmed"  # 사람 승인자가 넣음
    assert current_object(db_session, "obs/case/agent").confidence == "observed"  # 관찰은 늘 관찰
    link = propose_link(db_session, op="link_add", kind="evidence_of", from_key="obs/case/agent",
                        to_key="cs/lesson/agent", reason=REASON, proposer=agent, evidence=TWO_SOURCES, now=NOW)
    assert "confidence" not in link.fields  # 링크 제안 기본 '확정' 없음
    apply_change(db_session, link.id, actor=who["cs_mgr"], now=LATER)
    assert current_link(db_session, "evidence_of", "obs/case/agent", "cs/lesson/agent").confidence == "confirmed"
    imported = propose_create(db_session, key="common/imported-term", brand="COMMON", layer="common", item_type="term",
                              values=values("옮긴 관찰 용어", confidence="observed"), reason=REASON,
                              proposer=IMPORT_PROPOSER, now=NOW, known="")
    apply_change(db_session, imported.id, actor=admin, now=NOW, as_import=True)
    assert current_object(db_session, "common/imported-term").confidence == "observed"  # 옮기기는 옮긴 값(D102)
