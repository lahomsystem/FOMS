"""밤 배우기 끝 이어 붙이기(설계 글 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 7.1 · 7.2 · 사장님 11-26 '뻔한 것은
AI가 바로') — 처음 끔이면 표도 모델도 안 건드린다 · 뻔한 잇기만 바로 들어가 'AI 가 배운 것'에 뜨고 지울 수 있다 · 조건 다섯 가운데
하나라도 빠지면 열린 제안(⑥ 규칙 잇기 칸 · 금액 · 같이 안 됨은 ②) · 코드가 대상을 까닭별로 거른다 · 같은 내용 · 어긋남은 수만 ·
한 밤 부르기 상한 · 돈 상한이면 넣지 않는다 · 요청 꼴(캐시 끔 · 켬 — 켜면 밤 배우기와 같은 앞부분).

합성 지식 · 가짜 학습 모델만(네트워크 0 — 모델 API 는 부르지 않는다). 손님 글 · 직원 이름 · 금액 · 회사 지식 글 없음.
"""

from __future__ import annotations

import json
import logging

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain import learned
from foms.services.brain.apply import AutoLearn, apply_change
from foms.services.brain.inbox_bins import card_bin, change_ends
from foms.services.brain.proposals import Proposer, propose_create, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_link, current_object
from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import handoff_learning_cache as cache
from foms.services.cs_agent import handoff_learning_link as link
from foms.services.cs_agent import handoff_learning_link_prompt as lp
from foms.services.cs_agent import handoff_learning_prompt as hp
from foms.services.cs_agent import photo_learning_prompt as onto_prompt
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD, CACHE_FIELD, LINK_CALLS_FIELD, LINK_FIELD
from foms.services.cs_agent.handoff_learning_gates import AGENT, _doc_values
from foms.services.cs_agent.settings import read_settings
from models import SystemSetting
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_handoff_learning import on
from tests.domains.test_cs_weekly_fix import into_brain
from tests.support.brain_support import agent_judge, create, link as tie, person
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys, naive  # noqa: F401 — keys 는 fixture

DAY, LEARNED, NIGHT = "2026-11-11", at(11, 1), at(11, 3)
DOOR, STEP, TERM = "common/synth-door", "process_step/synth-measure", "common/term-tong"
FACT = "lahom/handoff-synth-a"
EVIDENCE = ["case:1", "case:2", "staff:mgr-1"]
WHY = "합성 글이 그 문 이야기를 한다"


def learned_item(admin, key, text, *, item_type="fact", name=None, when=LEARNED):
    """학습 에이전트가 그 밤 바로 넣은 지식(넘긴 상담 배우기와 같은 제안 → 바로 반영 길)."""
    doc_id, name = key.split("/", 1)[1], name or f"합성 배운 지식 {key[-1]}"
    if item_type in ("fact", "policy"):
        layer, values = "common", _doc_values(item_type, name, text, doc_id, "2026-11-11")
    else:
        layer = "cs" if item_type == "situation" else "common"
        values = {"name": name, "text": text, "status": "active", "visibility": "all", "evidence_kind": "case"}
    with agent_judge():
        change = propose_create(db_session, key=key, brand="LAHOM", layer=layer, item_type=item_type, values=values,
                                reason="합성", proposer=Proposer.agent_named(AGENT), evidence=EVIDENCE, now=naive(when),
                                known="")
    apply_change(db_session, change.id, actor=None, now=naive(when), auto=AutoLearn(admin.id))
    db_session.commit()
    return current_object(db_session, key)


def ln(kind, target, why=WHY):
    return {"kind": kind, "target": target, "why": why}


def answer(*items):
    return {"items": [{"key": key, "links": list(links), "same": [], "clash": []} for key, *links in items]}


def night(client, now=NIGHT):
    return hl.run_handoff_learning(db_session, now=now, client=client)


def filed():
    db_session.expire_all()
    return list(db_session.scalars(select(BrainChange).where(
        BrainChange.proposed_by == f"agent:{AGENT}", BrainChange.op == "link_add").order_by(BrainChange.id)))


def user_text(params):
    return params["messages"][0]["content"][-1]["text"]


def as_json(value):
    return json.dumps(value, ensure_ascii=False)


@pytest.fixture
def world(channel):  # noqa: F811
    """승인 지식을 표로 옮기고(운영처럼 — 바로 반영이 지식 문서를 다시 쓴다) 잇기 대상(제품 · 공정 단계 · 용어)이 있고 그 밤
    사례 읽기가 끝났다."""
    admin = person(db_session, "link-admin")
    into_brain(admin)
    create(db_session, admin, DOOR, name="합성 여닫이문")
    create(db_session, admin, STEP, item_type="process_step", name="합성 실측 방문", payload={"erp_stage": "MEASURE"})
    create(db_session, admin, TERM, item_type="term", name="합성 통 단위", text="합성 용어 글")
    db_session.commit()
    hl.close_day(db_session, DAY)
    return admin


# ── 끔(처음 값) ──────────────────────────────────────────────────────────
def test_off_by_default_never_calls_the_model_nor_touches_the_row(world):
    cfg = read_settings(db_session, log=False)
    assert (cfg.get(LINK_FIELD), cfg.get(LINK_CALLS_FIELD)) == (False, 3)
    learned_item(world, FACT, "합성 여닫이문은 문짝을 경첩으로 단다")
    on()  # 넘긴 상담 배우기만 켬
    client = FakeAnthropic(answer((FACT, ln("applies_to", DOOR))))
    assert night(client) == {"off": "already_today"}  # 밤 배우기 결과 꼴이 예전 그대로
    assert client.params == [] and db_session.get(SystemSetting, link.STORE_KEY) is None and filed() == []
    assert link.run_link(db_session, DAY, now=NIGHT, cfg=read_settings(db_session, log=False), client=client) == {
        "off": "link_off"}


# ── 뻔한 것은 바로 — 'AI 가 배운 것'에서 지운다 ─────────────────────────────
def test_an_obvious_link_goes_in_at_once_shows_in_learned_and_undo_takes_it_out(world, caplog):
    learned_item(world, FACT, "합성 여닫이문은 문짝을 경첩으로 단다")
    on(**{LINK_FIELD: True, AUTO_FIELD: True})
    caplog.set_level(logging.INFO, logger=link.logger.name)
    out = night(FakeAnthropic(answer((FACT, ln("applies_to", DOOR)))))
    counts = out["link"]
    assert (out["off"], counts["items"], counts["calls"], counts["ai"], counts["matched"]) == ("already_today", 1, 1, 1, 1)
    assert (counts["auto"], counts["proposed"], counts["dropped"], counts["halted"]) == (1, 0, {}, None)
    (change,) = filed()
    assert (change.status, change.decided_action, change.decided_by, change.link_kind) == (
        "applied", "auto_learn", None, "applies_to")
    tied = current_link(db_session, "applies_to", FACT, DOOR)
    assert tied is not None and tied.created_by == f"agent:{AGENT}" and tied.human_approver_id is None
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("[CS 붙이기]"))
    assert line == ("[CS 붙이기] day=2026-11-11 items=1 calls=1 ai=1 matched=1 auto=1 proposed=0 dropped={} same=0 "
                    "clash=0 halted=None cache_read=0 cache_write=0")  # 숫자 · 코드만(키 · 글 없음)
    rows = learned.learned_list(db_session, viewer_of(world))["items"]
    assert [(r["id"], r["kind"], r["state"]) for r in rows if r["id"] == change.id] == [(change.id, "잇기", "live")]
    learned.undo(db_session, change.id, actor=world, now=naive(NIGHT))
    db_session.commit()
    assert current_link(db_session, "applies_to", FACT, DOOR) is None
    # 지운 잇기는 다시 넣지 않는다 — 같은 지식을 그 밤 또 고쳐 다시 보내도
    row = current_object(db_session, FACT)
    with agent_judge():
        again = propose_update(db_session, key=FACT, base_version=row.version, after={"text": f"{row.text} 합성 더한 글"},
                               reason="합성", proposer=Proposer.agent_named(AGENT), evidence=EVIDENCE,
                               now=naive(at(11, 4)), known="")
    apply_change(db_session, again.id, actor=None, now=naive(at(11, 4)), auto=AutoLearn(world.id))
    db_session.commit()
    second = night(FakeAnthropic(answer((FACT, ln("applies_to", DOOR)))), now=at(11, 4, 15))["link"]
    assert (second["auto"], second["proposed"], second["dropped"]) == (0, 0, {"refused_before": 1})
    assert current_link(db_session, "applies_to", FACT, DOOR) is None


# ── 음성 대조군 — 조건 하나씩 빠뜨리면 바로 넣지 않고 제안으로 ──────────────
def _ai_only(admin):
    learned_item(admin, FACT, "합성 문짝은 경첩으로 단다")  # 글에 상대 이름이 없다(① — AI 말만)
    return "applies_to", DOOR, "rules", {}


def _shared(admin):
    create(db_session, admin, "common/synth-door-twin", name="합성 여닫이문")  # 같은 이름이 둘(②)
    learned_item(admin, FACT, "합성 여닫이문은 문짝을 경첩으로 단다")
    return "applies_to", DOOR, "rules", {"glyph_shared": 1}  # 쌍둥이 쪽은 글자 맞춤만 · 이름이 둘 — 올리지도 않는다


def _kind(admin):
    learned_item(admin, "lahom/handoff-synth-rule", "합성 여닫이문은 손잡이와 꼭 같이 만든다", item_type="build_rule")
    return "requires", DOOR, "content", {}  # ③ — 꼭 같이(늘 사장님께, ② 한 장씩)


def _brand(admin):
    create(db_session, admin, "haud/synth-door", brand="HAUD", name="합성 하우드 문짝")  # ④ — 브랜드를 넘는다
    learned_item(admin, FACT, "합성 하우드 문짝은 경첩으로 단다")
    return "applies_to", "haud/synth-door", "rules", {}


def _scope(admin):
    create(db_session, admin, "common/synth-door-hidden", name="합성 숨은 문짝", visibility="admin")  # ④ — 모두가 안 봄
    learned_item(admin, FACT, "합성 숨은 문짝은 경첩으로 단다")
    return "applies_to", "common/synth-door-hidden", "rules", {}


@pytest.mark.parametrize("setup", [_ai_only, _shared, _kind, _brand, _scope])
def test_each_missing_condition_files_an_open_proposal_instead(world, setup):
    kind, target, bin_name, dropped = setup(world)
    db_session.commit()
    source = next(row.item_key for row in link.night_sources(db_session, DAY, frozenset()))
    on(**{LINK_FIELD: True, AUTO_FIELD: True})
    counts = night(FakeAnthropic(answer((source, ln(kind, target)))))["link"]
    assert (counts["auto"], counts["proposed"], counts["dropped"]) == (0, 1, dropped)
    (change,) = filed()
    assert (change.status, change.link_kind, change.link_to) == ("open", kind, target)
    assert current_link(db_session, kind, source, target) is None
    assert card_bin(change.op, change.item_type, change.fields, change.link_kind, **change_ends(change)) == bin_name


def test_with_auto_apply_off_even_an_obvious_link_waits_for_the_owner(world):
    learned_item(world, FACT, "합성 여닫이문은 문짝을 경첩으로 단다")
    on(**{LINK_FIELD: True})  # '배운 것 바로 반영' 끔
    counts = night(FakeAnthropic(answer((FACT, ln("applies_to", DOOR)))))["link"]
    assert (counts["auto"], counts["proposed"]) == (0, 1) and filed()[0].status == "open"


# ── 코드가 거른다 · 글자 맞춤만 · 같은 내용 · 어긋남 ─────────────────────────
def test_the_code_drops_bad_targets_and_counts_each_reason(world):
    create(db_session, world, "common/synth-old", name="합성 옛 문", status="retired")
    rule = learned_item(world, "lahom/handoff-synth-rule", "합성 규칙 글", item_type="build_rule")
    tie(db_session, world, "excludes", rule.item_key, DOOR)
    learned_item(world, FACT, "합성 사실 글")
    tie(db_session, world, "uses", FACT, TERM)
    db_session.commit()
    on(**{LINK_FIELD: True, AUTO_FIELD: True})
    raw = answer((FACT, ln("applies_to", "common/none"), ln("applies_to", FACT), ln("applies_to", "common/synth-old"),
                  ln("uses", TERM), ln("applies_to", TERM), ln("broader", DOOR), ln("at_step", STEP),
                  ln("at_step", STEP), ln("applies_to", DOOR, why="합성 연락처 010-1234-5678")),
                 (rule.item_key, ln("requires", DOOR)), ("lahom/not-tonight", ln("applies_to", DOOR)))
    counts = night(FakeAnthropic(raw))["link"]
    assert counts["dropped"] == {"exists": 1, "form": 1, "mask": 1, "not_allowed": 1, "repeat": 1, "retired": 1,
                                 "rule": 1, "self": 1, "source": 1, "unknown": 1}
    assert (counts["ai"], counts["proposed"], counts["auto"]) == (10, 1, 0)  # 공정 단계 잇기 하나만(AI 말만 — 제안)
    assert [(c.link_kind, c.link_to, c.status) for c in filed()] == [("at_step", STEP, "open")]


def test_glyph_only_matches_go_to_the_owner_when_exactly_one_kind_fits(world):
    create(db_session, world, "common/synth-term-twin", item_type="term", name="합성 통 단위")  # 같은 이름이 둘
    learned_item(world, FACT, "합성 여닫이문은 합성 실측 방문 때 합성 통 단위로 잰다")
    learned_item(world, "lahom/handoff-synth-rule", "합성 여닫이문은 문짝 두 장이다", item_type="build_rule")
    db_session.commit()
    on(**{LINK_FIELD: True, AUTO_FIELD: True})
    counts = night(FakeAnthropic({"items": []}))["link"]
    assert (counts["ai"], counts["matched"], counts["auto"], counts["proposed"]) == (0, 5, 0, 2)
    assert counts["dropped"] == {"glyph_shared": 2, "no_kind": 1}  # 이름이 둘 · 제작 조건 → 제품은 종류가 셋
    assert sorted((c.link_from, c.link_kind, c.link_to, c.status) for c in filed()) == [
        (FACT, "applies_to", DOOR, "open"), (FACT, "at_step", STEP, "open")]
    assert all(card_bin(c.op, c.item_type, c.fields, c.link_kind, **change_ends(c)) == "rules" for c in filed())


def test_same_and_clash_candidates_are_counted_and_never_linked(world):
    other = learned_item(world, "lahom/handoff-synth-b", "합성 다른 사실 글", name="합성 다른 사실")
    learned_item(world, FACT, "합성 사실 글")
    on(**{LINK_FIELD: True, AUTO_FIELD: True})
    raw = {"items": [{"key": FACT, "links": [], "same": [other.item_key, "common/none", FACT], "clash": [DOOR]}]}
    counts = night(FakeAnthropic(raw))["link"]
    assert (counts["same"], counts["clash"], counts["auto"], counts["proposed"]) == (1, 1, 0, 0) and filed() == []


# ── 한 밤 상한 · 돈 상한 · 읽기가 끝난 뒤만 ────────────────────────────────
def test_the_call_cap_holds_across_ticks_and_each_call_sends_new_items(world, monkeypatch):
    monkeypatch.setattr(link, "MAX_ITEMS", 1)
    learned_item(world, FACT, "합성 사실 글")
    learned_item(world, "lahom/handoff-synth-b", "합성 다른 사실 글", name="합성 다른 사실", when=at(11, 2))
    on(**{LINK_FIELD: True, LINK_CALLS_FIELD: 2})
    client = FakeAnthropic({"items": []})
    first, second = night(client)["link"], night(client, now=at(11, 3, 15))["link"]
    assert (first["calls"], second["calls"]) == (1, 2)
    sent = [user_text(p).split(lp.SOURCE_HEAD + "\n", 1)[1].split("]")[0] for p in client.params]
    assert sent == ["[lahom/handoff-synth-b", f"[{FACT}"]  # 새 것부터 · 보낸 판은 다시 안 보낸다
    assert night(client, now=at(11, 3, 30)) == {"off": "already_today"} and len(client.params) == 2
    cfg = read_settings(db_session, log=False)
    assert link.run_link(db_session, DAY, now=at(11, 3, 45), cfg=cfg, client=client) == {"off": "night_done"}


def test_the_spend_guard_stops_the_call_and_nothing_goes_in(world):
    learned_item(world, FACT, "합성 여닫이문은 문짝을 경첩으로 단다")
    on(**{LINK_FIELD: True, AUTO_FIELD: True, "learning_cap_usd_panel": "0"})
    client = FakeAnthropic(answer((FACT, ln("applies_to", DOOR))))
    counts = night(client)["link"]
    assert counts["halted"] == "daily_cap_reached" and client.params == [] and filed() == []
    assert db_session.get(SystemSetting, link.STORE_KEY, populate_existing=True).setting_value["done"] is True
    assert night(client, now=at(11, 3, 15)) == {"off": "already_today"} and client.params == []


def test_it_waits_until_the_nights_reading_is_over(world):
    learned_item(world, FACT, "합성 사실 글")
    on(**{LINK_FIELD: True})
    cfg = read_settings(db_session, log=False)
    client = FakeAnthropic({"items": []})
    assert link.run_link(db_session, "2026-11-12", now=at(12, 3), cfg=cfg, client=client) == {"off": "reading"}
    assert hl.claim_day(db_session, "2026-11-12", at(12, 6, 50))  # 다른 바퀴가 부르는 중
    assert link.run_link(db_session, "2026-11-12", now=at(12, 6, 50), cfg=cfg, client=client) == {"off": "reading"}
    hl.release(db_session)
    assert link.reading_done(db_session, "2026-11-12", at(12, 6, 50))  # 창 마지막 바퀴
    assert link.run_link(db_session, "2026-11-12", now=at(12, 6, 50), cfg=cfg, client=client) == {"off": "no_items"}
    assert client.params == []


# ── 요청 꼴 ──────────────────────────────────────────────────────────────
def test_request_shape_with_the_cache_off(world):
    learned_item(world, FACT, "합성 여닫이문은 문짝을 경첩으로 단다")
    on(**{LINK_FIELD: True})
    client = FakeAnthropic({"items": []})
    night(client)
    (params,) = client.params
    model, effort = "claude-sonnet-5-5", "medium"  # 밤 배우기 쉬운 묶음 모델 · 세기(:func:`.handoff_learning_pick.model_for`)
    assert (params["model"], params["thinking"], params["output_config"]["effort"]) == (model, {"type": "adaptive"}, effort)
    assert params["output_config"]["format"] == {"type": "json_schema", "schema": lp.schema()}
    assert params["max_tokens"] == hp.MAX_TOKENS and params["fallbacks"] == "default"
    assert params["system"] == [{"type": "text", "text": lp.INSTRUCTIONS}] and "cache_control" not in as_json(params)
    lines = user_text(params).split("\n")
    assert lines[0] == lp.LIST_HEADS[0] and lp.LIST_HEADS[1] in lines and f"[{FACT}] 사실 합성 배운 지식 a: " \
        "합성 여닫이문은 문짝을 경첩으로 단다" in lines
    targets = {t.split("]")[0][1:] for t in lines[lines.index(lp.TARGET_HEAD) + 1:lines.index(lp.SOURCE_HEAD)]}
    assert {TERM, STEP} <= targets and DOOR not in targets and FACT not in targets  # 밤 배우기 목록에 없는 끝 유형만
    assert bp.worst_case_cost(params) > 0


def test_request_shape_with_the_cache_on_shares_the_nights_frozen_prefix(world):
    on(**{LINK_FIELD: True, CACHE_FIELD: True})
    cfg = read_settings(db_session, log=False)
    frozen = cache.night_lists(db_session, cfg, DAY, hp.knowledge_rows(db_session),
                               onto_prompt.knowledge_rows(db_session))  # 그 밤 첫 배우기 부르기가 굳힌 목록
    learned_item(world, FACT, "합성 여닫이문은 문짝을 경첩으로 단다")  # 그 뒤 배운 지식
    client = FakeAnthropic({"items": []})
    night(client)
    (params,) = client.params
    night_call = hp.build_params([["사례 1 합성:", "| 합성 사례 글"]], [], [], model=params["model"], cfg=cfg,
                                 frozen=frozen)
    assert as_json(params["system"]) == as_json(night_call["system"])  # 글자까지 같은 캐시 앞부분
    assert params["system"][1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "cache_control" not in as_json(params["messages"])
    text = user_text(params)
    assert text.startswith(lp.OVERRIDE + "\n" + lp.INSTRUCTIONS.rstrip())
    tail = text.split(hp.TAIL_HEADS[0] + "\n", 1)[1].split("\n" + hp.TAIL_HEADS[1], 1)[0].split("\n")
    assert [line.split("]")[0] for line in tail] == [f"[{FACT}"]  # 굳힌 뒤 들어간 지식은 꼬리 줄로
    assert lp.LIST_HEADS[0] not in text
