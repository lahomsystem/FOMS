"""회사 지식 물어보기 — 틀림 신고 · AI 제안 관문 셋 · 다른 이름 찾기 · 쓰인 횟수 · 평가 묶음 · 빈 지식 · 보관(설계서 10.3 ·
6절 · 7.7 · D105) + 사장님 D106(AI 제안 주 상한은 층마다) · D109(설정 값 요약은 그 층 승인자 팀장까지).

합성 지식 · 합성 계정 · 가짜 모델 · 가짜 판정자만.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainObject, BrainQuestion, BrainUsage, BrainWrongReport
from foms.services.brain import actions
from foms.services.brain.ai_gates import JudgeUnavailable, judge_source
from foms.services.brain.ai_gates import people as distinct_people
from foms.services.brain.around import brain_points
from foms.services.brain.browse import TableQuery, search_grouped, table_page
from foms.services.brain.card import item_card
from foms.services.brain.chat_answer import ask
from foms.services.brain.chat_gaps import GAPS_KEY, run_weekly_gaps
from foms.services.brain.chat_log import ChatFeedbackError, purge_questions, record_feedback
from foms.services.brain.chat_reports import reported_keys
from foms.services.brain.chat_retrieve import retrieve
from foms.services.brain.chat_tools import AGENT_TOOLS, READ_TOOL_SPECS, run_read_tool, search_objects
from foms.services.brain.constants import AI_WEEKLY_CAP
from foms.services.brain.errors import BrainGateError
from foms.services.brain.eval_set import parse_questions, run_eval, store_questions
from foms.services.brain.external import catalog_source
from foms.services.brain.inbox import ai_week, inbox
from foms.services.brain.proposals import Proposer, propose_create, propose_retire, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.usage import count_doc_reads, count_reads, usage_of
from models import SystemSetting
from tests.support.brain_chat_eval_set import questions as eval_questions
from tests.support.brain_chat_eval_set import seed as eval_seed
from tests.support.brain_chat_support import NOW_KST, chat_on, chat_world, fixed, reader_client, reply
from tests.support.brain_support import NOW, REASON, TWO_SOURCES, create, link, person, setting, synth_catalog, values
from tools.cron import brain_chat_gaps, purge_brain_questions
from tools.cron.nightly import NIGHTLY_STEPS

TODAY = datetime.date(2026, 11, 2)
NOW_UTC = NOW_KST.astimezone(datetime.timezone.utc).replace(tzinfo=None)
AGENT = Proposer.agent_named("cs_agent")


@pytest.fixture
def people(app):
    return chat_world(db_session)


def _ask_cited(user, key="common/sliding", question="슬라이딩 깊이는?"):
    out = ask(db_session, user, question, client=fixed(reply(answer="합성 규격 650mm", evidence_ids=[key], unknown=False)),
              now=NOW_KST)
    db_session.commit()
    return out


# ── 틀림 신고 → 서로 다른 사람 둘 이상이면 제안(이름 있는 에이전트 액션) ──────────────
def test_two_distinct_people_saying_wrong_raise_one_proposal(people):
    first = _ask_cited(people["admin"])
    again = _ask_cited(people["admin"])
    record_feedback(db_session, question_id=first["id"], asker_id=people["admin"].id, feedback="wrong",
                    note="깊이는 600 이에요", now_utc=NOW_UTC)
    record_feedback(db_session, question_id=again["id"], asker_id=people["admin"].id, feedback="wrong", note=None,
                    now_utc=NOW_UTC)
    db_session.commit()
    raised = select(func.count()).select_from(BrainChange).where(BrainChange.action == "report_conflict")
    assert db_session.scalar(raised) == 0  # 같은 사람 둘은 올리지 않는다
    assert reported_keys(db_session, ["common/sliding"]) == set()
    other = _ask_cited(people["admin2"])
    result = record_feedback(db_session, question_id=other["id"], asker_id=people["admin2"].id, feedback="wrong",
                             note="고객 010-2345-6789 집은 다름", now_utc=NOW_UTC)
    db_session.commit()
    assert result["raised"] == ["common/sliding"]
    change = db_session.execute(select(BrainChange).where(BrainChange.action == "report_conflict")).scalar_one()
    assert (change.op, change.item_type, change.action, change.proposed_by) == ("create", "conflict", "report_conflict",
                                                                               "agent:brain_chat")
    assert sorted(change.evidence) == sorted([f"person:{people['admin'].id}", f"person:{people['admin2'].id}"])
    assert change.gates["evidence"] == "pass" and change.gates["conflict"] == "skipped"
    text = change.fields["text"]["after"]
    assert "2345" not in text and "(가림)" in text and "[전화]" not in text  # 고칠 말은 가린 글만(표시는 풀어 씀)
    assert change.fields["payload"]["after"]["target"] == "common/sliding"
    assert reported_keys(db_session, ["common/sliding"]) == {"common/sliding"}  # 이제 '확인 필요'
    assert "report_conflict" in actions.known_names() and "report_conflict" not in actions.ACTIONS
    reports = db_session.execute(select(BrainWrongReport.change_id)).scalars().all()
    assert set(reports) == {change.id}
    third = _ask_cited(people["admin"])
    record_feedback(db_session, question_id=third["id"], asker_id=people["admin"].id, feedback="wrong", note=None,
                    now_utc=NOW_UTC)
    assert db_session.scalar(raised) == 1  # 열린 신고 제안이 있으면 또 올리지 않는다
    with pytest.raises(ChatFeedbackError):  # 남의 질문에는 피드백 못 함
        record_feedback(db_session, question_id=third["id"], asker_id=people["admin2"].id, feedback="helpful", note=None,
                        now_utc=NOW_UTC)
    with pytest.raises(ChatFeedbackError) as bad:
        record_feedback(db_session, question_id=third["id"], asker_id=people["admin"].id, feedback="nope", note=None,
                        now_utc=NOW_UTC)
    assert bad.value.code == "shape"


def test_wrong_report_with_retrieval_marks_the_item_as_needs_check(people):
    for name in ("admin", "admin2"):
        row = _ask_cited(people[name])
        record_feedback(db_session, question_id=row["id"], asker_id=people[name].id, feedback="wrong", note=None,
                        now_utc=NOW_UTC)
    db_session.commit()
    found = retrieve(db_session, viewer_of(people["admin"]), "슬라이딩 깊이", today=TODAY)
    assert [(c.key, c.usable, c.why) for c in found.candidates] == [("common/sliding", False, "reported")]


# ── AI 제안 관문 셋(D105) ────────────────────────────────────────────────
def test_three_gates_actually_run_for_agent_proposals_only(people):
    asked = []

    def judge(_session, first, second):
        asked.append((first, second))
        return "엇갈림" in first or "엇갈림" in second

    with pytest.raises(BrainGateError) as few:  # 근거 한 곳 — ③ 떨어짐
        with judge_source(judge):
            propose_update(db_session, key="common/sliding", base_version=1, after={"text": "슬라이딩 깊이 합성 650mm 확인"},
                           reason=REASON, proposer=AGENT, evidence=["case:a", "case:a#2"], now=NOW, known="650")
    assert "evidence" in few.value.failed and distinct_people(["case:a", "case:a#2", "doc:x", "chat:a"]) == {"customer:a"}
    assert distinct_people(["person:3", "user:3", "staff:4"]) == {"staff:3", "staff:4"}  # 근거 id 수가 아니라 사람 수
    asked.clear()
    with judge_source(judge):
        ok = propose_update(db_session, key="common/sliding", base_version=1,
                            after={"text": "슬라이딩 깊이 합성 650mm 확인"}, reason=REASON, proposer=AGENT,
                            evidence=TWO_SOURCES, now=NOW, known="650")
    assert ok.gates["conflict"] == "pass" and ok.gates["evidence"] == "pass" and ok.gates["eval"] == "unavailable"
    assert len(asked) == 2 and asked[0] == (asked[1][1], asked[1][0])  # 두 순서로
    create(db_session, people["admin"], "common/sliding-discount", item_type="price_rule", name="슬라이딩 깊이 재량 값",
           text="슬라이딩 깊이 재량 합성 규칙", visibility="price", checked_at="2026-10-30",
           payload={"doc_id": "sliding-discount", "approved_by": "합성", "approved_at": "2026-10-30"})
    asked.clear()
    with judge_source(judge):
        propose_update(db_session, key="common/sliding", base_version=1, after={"text": "슬라이딩 깊이 합성 650mm 다시"},
                       reason=REASON, proposer=AGENT, evidence=TWO_SOURCES, now=NOW, known="650")
    assert asked and all("재량" not in a + b for a, b in asked)  # 가격 재량 글은 판정자에게도 안 보낸다
    with pytest.raises(BrainGateError) as clash, judge_source(judge):
        propose_create(db_session, key="common/clash", brand="COMMON", layer="common", item_type="build_rule",
                       values=values("슬라이딩 엇갈림 규칙", text="슬라이딩 깊이 엇갈림 합성"), reason=REASON,
                       proposer=AGENT, evidence=TWO_SOURCES, now=NOW, known="")
    assert clash.value.failed == ("conflict",)

    def down(_session, _a, _b):
        raise JudgeUnavailable("judge_off")

    with pytest.raises(BrainGateError) as off, judge_source(down):  # 판정을 못 하면 넣지 않는다
        propose_create(db_session, key="common/new", brand="COMMON", layer="common", item_type="build_rule",
                       values=values("슬라이딩 새 규칙", text="슬라이딩 깊이 새 합성"), reason=REASON, proposer=AGENT,
                       evidence=TWO_SOURCES, now=NOW, known="")
    assert off.value.failed == ("conflict",)
    with pytest.raises(BrainGateError):  # 운영 판정자는 설정 '부딪침 판정'이 꺼져 있으면(처음 값) 부르지 않는다
        propose_create(db_session, key="common/new2", brand="COMMON", layer="common", item_type="build_rule",
                       values=values("슬라이딩 새 규칙 둘", text="슬라이딩 깊이 새 합성 둘"), reason=REASON, proposer=AGENT,
                       evidence=TWO_SOURCES, now=NOW, known="")
    human = propose_create(db_session, key="common/new3", brand="COMMON", layer="common", item_type="build_rule",
                           values=values("슬라이딩 사람 규칙", text="슬라이딩 엇갈림 사람 합성"), reason=REASON,
                           proposer=Proposer.user(people["admin"].id), now=NOW, known="")
    assert (human.gates["conflict"], human.gates["evidence"], human.gates["eval"]) == ("not_run", "not_run",
                                                                                         "unavailable")


def test_eval_gate_reruns_affected_questions(people):
    store_questions(db_session, parse_questions([{"id": "e1", "q": "슬라이딩 깊이는?", "expect": ["common/sliding"]},
                                                 {"id": "e2", "q": "주차 요금", "expect": []}]))
    db_session.commit()
    with judge_source(lambda *_a: False):
        with pytest.raises(BrainGateError) as lost:
            propose_update(db_session, key="common/sliding", base_version=1,
                           after={"name": "문짝 안쪽 치수", "text": "몸통 안쪽 합성 치수"}, reason=REASON,
                           proposer=AGENT, evidence=TWO_SOURCES, now=NOW, known="")
        assert lost.value.failed == ("eval",)  # 고친 뒤 그 질문이 이 항목을 못 찾는다
        kept = propose_update(db_session, key="common/sliding", base_version=1,
                              after={"text": "슬라이딩 문 장의 몸통 깊이 합성 규격"}, reason=REASON, proposer=AGENT,
                              evidence=TWO_SOURCES, now=NOW, known="")
        assert kept.gates["eval"] == "pass"
        with pytest.raises(BrainGateError) as gone:
            propose_retire(db_session, key="common/sliding", base_version=1, reason=REASON, proposer=AGENT,
                           evidence=TWO_SOURCES, now=NOW)
        assert gone.value.failed == ("eval",)
        other = propose_retire(db_session, key="common/hinge", base_version=1, reason=REASON, proposer=AGENT,
                               evidence=TWO_SOURCES, now=NOW)
        assert other.gates["eval"] == "pass" and other.gates["conflict"] == "skipped"  # 대조군: 기대하는 질문 없음


# ── SKOS 꼴 다른 이름 ────────────────────────────────────────────────────
def test_alt_labels_are_found_by_screen_search_and_chat_search(people):
    who = viewer_of(people["admin"])
    grouped = search_grouped(db_session, who, "빌트인", today=TODAY)
    assert [i["key"] for g in grouped["groups"] for i in g["items"]] == ["common/term-builtin"]
    assert search_grouped(db_session, who, "다락장", today=TODAY)["total"] == 0  # 대조군: 없는 다른 이름
    hits = search_objects(db_session, who, "벽장 문은 어떻게 해요", today=TODAY)
    assert hits[0]["key"] == "common/term-builtin" and "벽장" in hits[0]["matched"]
    create(db_session, people["admin"], "common/builtin-depth", item_type="spec", name="붙박이장 깊이",
           text="붙박이장 깊이 합성 규격 600mm", payload={"value": 600, "unit": "mm"})
    expanded = [h["key"] for h in search_objects(db_session, who, "빌트인장 깊이", today=TODAY)]
    assert "common/builtin-depth" in expanded  # 다른 이름 → 대표 이름으로 넓혀 찾는다
    for item_type in ("term", "product_line", "option"):
        from foms.services.brain.schemas import prop_of
        assert prop_of(item_type, "payload.aliases") and prop_of(item_type, "payload.broader"), item_type


# ── 쓰인 횟수(따로 세기) ──────────────────────────────────────────────────
def test_usage_count_is_a_separate_counter_shown_everywhere(people):
    admin = people["admin"]
    create(db_session, admin, "common/doc-fact", item_type="fact", name="합성 사실", text="합성 사실 글",
           payload={"doc_id": "fact-synth", "approved_by": "합성", "approved_at": "2026-10-30"}, checked_at="2026-10-30")
    before = db_session.scalar(select(func.count()).select_from(BrainObject))
    count_reads(db_session, ["common/sliding", "common/sliding", "common/hinge"], "chatbot", now=NOW_UTC)
    count_reads(db_session, ["common/sliding"], "chatbot", now=NOW_UTC)
    assert count_doc_reads(db_session, "LAHOM", ["fact-synth", "no-such-doc"], now=NOW_UTC) == 1
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(BrainObject)) == before  # 판 줄은 그대로
    assert usage_of(db_session, ["common/sliding", "common/hinge", "common/doc-fact"]) == {
        "common/doc-fact": 1, "common/hinge": 1, "common/sliding": 2}
    rows = db_session.execute(select(BrainUsage.item_key, BrainUsage.reader, BrainUsage.count)
                              .order_by(BrainUsage.item_key, BrainUsage.reader)).all()
    assert ("common/doc-fact", "cs_brain", 1) in rows
    who = viewer_of(admin)
    card = item_card(db_session, who, "common/sliding", today=TODAY)
    assert card["item"]["usage_count"] == 2 and card["item"]["usage_readers"] == {"chatbot": 2}
    page = table_page(db_session, who, TableQuery(item_type="spec"), today=TODAY)
    assert page["rows"][0]["key"] == "common/sliding" and page["rows"][0]["usage_count"] == 2
    points = brain_points(db_session, who, today=TODAY)
    assert points["rows"][0][0] == "common/sliding" and points["rows"][0][3] == 2


# ── 평가 묶음(30 + 10) 실행 ──────────────────────────────────────────────
def test_eval_runner_on_the_synthetic_set(app):
    admin = person(db_session, "ev_admin")
    eval_seed(db_session, admin)
    chat_on(db_session)
    qs = eval_questions()
    assert len([q for q in qs if q.answerable]) == 30 and len([q for q in qs if not q.answerable]) == 10
    from foms.services.brain.chat_answer import answer_masked
    from foms.services.brain.chat_settings import read_chat_settings
    from foms.services.cs_agent.masking import mask

    cfg = read_chat_settings(db_session)
    client = reader_client()

    def answer(question):
        verified, _r, _m = answer_masked(db_session, viewer_of(admin), mask(question.q), cfg=cfg, now=NOW_KST,
                                         client=client)
        return {"unknown": verified.unknown, "evidence": verified.evidence}

    score = run_eval(qs, answer)
    assert score.passed and score.hit == 30 and score.unknown_ok == 10 and score.unsupported == 0, score.as_dict()
    assert len(client.calls) == 30  # 지식에 없는 질문은 후보가 없어 두뇌를 부르지 않는다
    retrieval = run_eval(qs, lambda q: {"unknown": not retrieve(db_session, viewer_of(admin), q.q, today=TODAY).usable,
                                        "evidence": [c.key for c in retrieve(db_session, viewer_of(admin), q.q,
                                                                             today=TODAY).usable]})
    assert retrieval.hit == 30 and retrieval.unknown_ok == 10


# ── 빈 지식 · 보관 · 밤 단계 ──────────────────────────────────────────────
def test_weekly_gaps_cluster_unknown_and_wrong_questions(people):
    for question in ("주차 요금은?", "점심 메뉴는?"):
        ask(db_session, people["admin"], question, client=fixed(reply()), now=NOW_KST)
    row = _ask_cited(people["admin"])
    record_feedback(db_session, question_id=row["id"], asker_id=people["admin"].id, feedback="wrong", note=None,
                    now_utc=NOW_UTC)
    db_session.commit()
    assert run_weekly_gaps(db_session, now=NOW_KST) == {"off": True}  # 처음 끔
    chat_on(db_session, gap_enabled=True)
    seen = []

    def clusterer(_session, rows, _cfg, _now):
        seen.extend(rows)
        ids = [r["id"] for r in rows]
        return [{"label": "사무 생활 질문", "layer": "common", "question_ids": ids[:2] + [9999]}]

    done = run_weekly_gaps(db_session, now=NOW_KST, clusterer=clusterer)
    db_session.commit()
    assert done["questions"] == 3 and all("asker" not in r for r in seen)
    stored = db_session.get(SystemSetting, GAPS_KEY).setting_value
    common = stored["layers"]["common"]
    assert common[0]["label"] == "사무 생활 질문" and common[0]["count"] == 2 and 9999 not in common[0]["question_ids"]
    assert sum(g["count"] for g in common) == 3  # 남은 질문은 '그 밖'
    assert run_weekly_gaps(db_session, now=NOW_KST, clusterer=clusterer)["skipped"] == "done"  # 이번 주는 한 번
    summary = brain_chat_gaps.run(apply=False, session=db_session, now=NOW_KST, clusterer=clusterer)
    assert summary["skipped"] == "done"


def test_questions_are_kept_one_year_then_purged(people):
    old = ask(db_session, people["admin"], "주차 요금은?", client=fixed(reply()), now=NOW_KST)
    db_session.get(BrainQuestion, old["id"]).asked_at = NOW_UTC - datetime.timedelta(days=366)
    fresh = _ask_cited(people["admin"])
    record_feedback(db_session, question_id=fresh["id"], asker_id=people["admin"].id, feedback="wrong", note=None,
                    now_utc=NOW_UTC)
    db_session.commit()
    dry = purge_brain_questions.run(apply=False, session=db_session, now=NOW_UTC)
    assert dry["questions"] == 1 and db_session.get(BrainQuestion, old["id"]) is not None
    done = purge_brain_questions.run(apply=True, session=db_session, now=NOW_UTC)
    assert done["questions"] == 1 and db_session.get(BrainQuestion, old["id"]) is None
    assert db_session.get(BrainQuestion, fresh["id"]) is not None  # 대조군: 1년 안
    assert purge_questions(db_session, now_utc=NOW_UTC)["questions"] == 0
    steps = {step.script: step.args for step in NIGHTLY_STEPS}
    for script in ("tools/cron/purge_brain_questions.py", "tools/cron/brain_chat_gaps.py", "tools/cron/brain_embed.py"):
        assert steps[script] == ("--apply",), script


# ── 에이전트 도구 = 읽기만 ───────────────────────────────────────────────
def test_agent_tools_are_read_only_and_scope_filtered(people):
    assert {t["name"] for t in READ_TOOL_SPECS} == set(AGENT_TOOLS) and actions.AGENT_EXPOSED_WRITES == ()
    cs = viewer_of(people["cs_mgr"])
    assert run_read_tool(db_session, cs, "brain_get_object", {"key": "common/discount"}, today=TODAY) is None
    assert run_read_tool(db_session, viewer_of(people["admin"]), "brain_get_object", {"key": "common/discount"},
                         today=TODAY)["name"] == "재량 할인 폭"
    assert [h["key"] for h in run_read_tool(db_session, cs, "brain_search_objects", {"query": "재량 할인 폭"},
                                            today=TODAY)] == []
    with pytest.raises(ValueError):
        run_read_tool(db_session, cs, "brain_propose_edit", {}, today=TODAY)


# ── D106 · D109 ──────────────────────────────────────────────────────────
def test_d106_ai_weekly_cap_is_per_layer(people):
    admin = people["admin"]
    for layer, team_type in (("cs", "tone"), ("drawing", "drawing_rule")):
        for n in range(AI_WEEKLY_CAP + 2):
            key = f"{layer}/ai/t{n:02d}"
            create(db_session, admin, key, item_type=team_type, layer=layer, brand="LAHOM" if layer == "cs" else "COMMON",
                   name=f"합성 {layer} 항목 {chr(0xAC00 + n)}")
            with judge_source(lambda *_a: False):
                propose_update(db_session, key=key, base_version=1, after={"text": "합성 고침 제안"}, reason="AI",
                               proposer=AGENT, evidence=TWO_SOURCES, now=NOW, known="")
    db_session.commit()
    later = NOW + datetime.timedelta(minutes=5)
    cs = inbox(db_session, viewer_of(people["cs_mgr"]), now=later)
    dr = inbox(db_session, viewer_of(people["dr_mgr"]), now=later)
    assert len([c for c in cs["cards"] if c["main"]["ai"]]) == AI_WEEKLY_CAP == 20  # 상담 층 20
    assert len([c for c in dr["cards"] if c["main"]["ai"]]) == 20  # 도면 층도 따로 20
    assert cs["ai"]["layers"] == {"cs": {"used": 0, "left": 20}} and cs["ai"]["cap"] == 20
    everyone = ai_week(db_session, later, viewer_of(admin))
    assert everyone["cap"] == 80 and set(everyone["layers"]) == {"common", "cs", "drawing", "production"}
    admin_cards = inbox(db_session, viewer_of(admin), now=later)["cards"]
    assert len([c for c in admin_cards if c["main"]["ai"]]) == 40


def test_d109_setting_summary_is_visible_to_the_layer_approver_manager(people):
    admin = people["admin"]
    create(db_session, admin, "drawing/bom-rule", item_type="bom_rule", layer="drawing", name="합성 자재표 규칙")
    setting(db_session, "synthetic_bom_rules")
    link(db_session, admin, "value_from", "drawing/bom-rule", "setting:synthetic_bom_rules")
    db_session.commit()
    with catalog_source(synth_catalog):
        cards = {name: {e["ref"]: e for e in item_card(db_session, viewer_of(people[name]), "drawing/bom-rule",
                                                       today=TODAY)["external"]}
                 for name in ("admin", "dr_mgr", "cs_mgr")}
    ref = "setting:synthetic_bom_rules"
    assert cards["admin"][ref]["value"] == "칸 1개 — 합성"
    assert cards["dr_mgr"][ref]["value"] == "칸 1개 — 합성" and not cards["dr_mgr"][ref]["value_hidden"]  # 도면 층 팀장
    assert cards["cs_mgr"][ref]["value"] is None and cards["cs_mgr"][ref]["value_hidden"]  # 대조군: 다른 층 팀장
    with catalog_source(synth_catalog):
        common = {e["ref"]: e for e in item_card(db_session, viewer_of(people["dr_mgr"]), "common/sliding",
                                                 today=TODAY)["external"]}
    assert common == {}
