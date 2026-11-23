"""상담 AI 평가 묶음(설계서 2026-11-14-foms-graft 3.15 · D209 — T16) — 묶음 · 세기 · 돈 상한 · 결과 · 줄 일.

완료 기준:
- 묶음은 가린 칸만 읽는다 — 원문 칸(옛 초안 · 고칠 말 · 자세한 이유 · 수신 원본)에 넣은 지어낸 표식이 묶음 · 모델 인자 · 결과 ·
  로그 어디에도 없고, 묶음 질의가 그 칸을 고르지 않는다. 가린 질문 표식은 모델에만 가고 결과 · 로그에는 없다.
- ``held_out`` 이 없으면 '지난 상담'은 0(배우기 차례로 채우지 않는다).
- 가짜 두뇌로 세 줄: 지난 상담(글자 복사 · 판정 '어긋남' · 넘김 — 판정자 · 넘김 까닭 판정자도 같은 가짜 두뇌 · 같은 평가 돈 줄) ·
  위험 문장(검사가 막음 · 근거 있음 · 근거 없는 약속) · 능력 질문.
- 상한 0 이면 돌지 않는다(모델 0번) · 상한에서 멈춤(예약이 넘치면 그 차례부터 안 부름) · 열쇠 없음 → '준비 안 됨'(줄 일 길 포함).
- 보내기 · 메모 · 배우기 · 쓰인 횟수 · 제안 · 차례 줄 고치기 함수는 한 번도 안 불린다 · 상담 초안 하루 돈 줄 · 학습 돈 줄은 그대로.
- 결과에 글 없음 · 최근 10번만 · 한 번에 하나(도는 중 거절 · 오래 멈춘 줄은 풀림).
- 줄 일이 WORKER 의 RQ 에서 돈다(계약): 경로 → 함수 · ``default`` 줄 · 그 줄을 꺼내는 것은 감독받는 WORKER 큐 소비자뿐 ·
  큐가 없으면 넣지 않음(web 에서 대신 돌리지 않는다).
돈은 뜻 없는 작은 수(최악값 3 · 한 번 1)로 바꿔 끼운다. 합성 차례 · 합성 지식만 — 바깥 호출 없음(모델 · 큐 모두 가짜).
"""

from __future__ import annotations

import copy
import datetime
import json
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest
from anthropic.types.beta import BetaMessage
from sqlalchemy import event, select
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.ai_staff import evals, evals_handoff, evals_meaning, evals_run, evals_view
from foms.services.brain.scope import viewer_of
from foms.services.cs_agent import brain_prompt, brain_spend
from foms.services.cs_agent.knowledge_doc import ApprovedKnowledge, KnowledgeItem
from foms.services.cs_agent.state import KST
from foms.services.datetime_kst import now_utc_naive
from models import ChannelInboundEventLog, CsAgentTurn, SystemSetting, User
from tests.support.worker_jobs import jobs, worker_branch_of_start_sh

RAW = "보라원문표지"  # 원문 칸에만 둔다 — 어디에도 나오면 안 된다
ASKED = "초록질문표지"  # 가린 질문에 둔다 — 모델에만 가야 한다
STAFF = "합성 직원 답 하나입니다"
NOW = datetime.datetime.now(KST).replace(microsecond=0)


def _item(item_id, *, kind="template", intents=("hours",)):
    return KnowledgeItem(item_id=item_id, kind=kind, status="approved", text=f"합성 안내 {item_id}",
                         intents=tuple(intents), approved_by="synthetic-owner", approved_at="2026-10-20")


KNOWLEDGE = ApprovedKnowledge("LAHOM", 3, (_item("hours-day"), _item("fact-size", kind="fact", intents=())))
#: 질문 표식 → (초안, 근거, 넘김[, 넘김 까닭]) — 가짜 두뇌가 모델 인자에서 표식을 찾아 고른다.
ANSWERS = {
    "합성 질문 같음": (STAFF, ["hours-day"], False),
    "합성 질문 다름": ("다른 안내 문장을 길게 적어 드립니다", ["hours-day"], False),
    "합성 질문 넘김": ("", [], True),
    "합성 위험 막힘": ("결제 취소해 드리겠습니다", ["hours-day"], False),
    "합성 위험 근거": ("안녕하세요 고객님 영업시간 안내드립니다.", ["hours-day"], False),
    "합성 위험 없음": ("안녕하세요 고객님 영업시간 안내드립니다.", [], False),
}
#: 질문 표식 → 판정자 답(가짜 두뇌가 판정 지시문을 보면 이것을 낸다 — 없는 표식이면 꼴이 틀린 답).
JUDGED = {"합성 질문 다름": "fail_conflict"}
#: 질문 표식 → 넘김 까닭 판정자 답(없는 표식이면 '재료 없음').
CAUSED = {"합성 질문 넘김": "missing"}
WHY = "판정까닭표지"  # 판정 까닭 — 결과 · 로그에 남으면 안 된다


def _wrap(text, model=brain_prompt.MODEL):
    return BetaMessage.model_validate({
        "id": "msg_synthetic", "type": "message", "role": "assistant", "model": model,
        "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
        "stop_sequence": None, "stop_details": None,
        "usage": {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0}})


def _message(draft, evidence, handoff, reason=None):
    out = {"intent": "hours", "draft": draft, "evidence_ids": evidence, "handoff": handoff,
           "handoff_reason": (reason or "unsure") if handoff else "none", "staff_note": ""}
    return _wrap(json.dumps(out, ensure_ascii=False))


def _judged(text):
    """뜻 판정 답 — 표식이 :data:`JUDGED` 에 있으면 그 판정, 없으면 꼴이 틀린 글."""
    key = next((k for k in JUDGED if k in text), None)
    body = json.dumps({"verdict": JUDGED[key], "why": WHY}, ensure_ascii=False) if key else "꼴이 틀린 답"
    return _wrap(body, model=evals_meaning.MODEL)


def _caused(text):
    """넘김 까닭 판정 답 — 표식이 :data:`CAUSED` 에 있으면 그 답, 없으면 '재료 없음'."""
    key = next((k for k in CAUSED if k in text), None)
    return _wrap(json.dumps({"verdict": CAUSED.get(key, "missing"), "why": WHY}, ensure_ascii=False),
                 model=evals_handoff.MODEL)


class FakeClient:
    """``anthropic.Anthropic`` 흉내 — 받은 인자를 적고 질문 표식에 맞는 답을 낸다. 네트워크 없음."""

    def __init__(self):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def with_options(self, **_options):
        return self

    @property
    def judge_calls(self):
        return [call for call in self.calls if call["system"][0]["text"] == evals_meaning.SYSTEM]

    @property
    def cause_calls(self):
        return [call for call in self.calls if call["system"][0]["text"] == evals_handoff.SYSTEM]

    def _create(self, **params):
        self.calls.append(copy.deepcopy(params))
        text = json.dumps(params["messages"], ensure_ascii=False)
        if params["system"][0]["text"] == evals_meaning.SYSTEM:
            return _judged(text)
        if params["system"][0]["text"] == evals_handoff.SYSTEM:
            return _caused(text)
        key = next(k for k in ANSWERS if k in text)
        return _message(*ANSWERS[key])


@pytest.fixture
def world(app, monkeypatch):
    """합성 지식 · 뜻 없는 작은 돈(최악값 3 · 한 번 1) · 가짜 큐."""
    monkeypatch.setattr(evals_run, "load_approved", lambda _session, _brand: KNOWLEDGE)
    monkeypatch.setattr(brain_prompt, "worst_case_cost", lambda _params: Decimal("3"))
    real_usage = brain_prompt.usage_cost
    monkeypatch.setattr(brain_prompt, "usage_cost", lambda response, model: (real_usage(response, model=model)[0],
                                                                             Decimal("1")))
    admin = User(username="ev_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                 is_active=True)
    db_session.add(admin)
    db_session.commit()
    return SimpleNamespace(admin=admin, admin_id=admin.id)


def _settings(cap="100", past=3, risk=3, target=50):
    db_session.add(SystemSetting(setting_key=evals.SETTINGS_KEY, setting_value={
        "cap_usd": cap, "past_size": past, "risk_size": risk, "past_target_pct": target}))
    db_session.commit()


def _turn(n, question, *, held_out=False, reply=None, codes=None, outcome=None, context=None):
    if held_out and reply is not None and outcome is None:
        outcome = "edited"  # '지난 상담'은 직원이 고치거나 직접 쓴 답만(그대로 · 복사는 정답이 AI 글 자신)
    row = CsAgentTurn(brand="LAHOM", chat_id=f"ev-chat-{n}", last_user_message_id=f"ev-m-{n}", state="posted",
                      masked_question=f"{ASKED} {question}", masked_context=context, staff_reply_masked=reply,
                      held_out=held_out, check_codes=codes, outcome=outcome, masked_draft=f"{RAW} 옛 초안",
                      rewrite_note_masked=f"{RAW} 고칠 말", edit_detail_masked=f"{RAW} 자세한 이유",
                      created_at=now_utc_naive() - datetime.timedelta(hours=1))
    db_session.add(row)
    db_session.commit()
    return row.id


def _world_turns():
    """지난 상담 셋(같음 · 다름 · 넘김) · 위험 문장 셋(막힘 · 근거 · 없음) · 배우기 차례 하나 · 수신 원본 하나."""
    ids = {"same": _turn(1, "합성 질문 같음", held_out=True, reply=STAFF, context="[직원] 안녕하세요\n[손님] 합성 앞 말"),
           "diff": _turn(2, "합성 질문 다름", held_out=True, reply="합성 직원 답 둘입니다"),
           "hand": _turn(3, "합성 질문 넘김", held_out=True, reply="합성 직원 답 셋입니다"),
           "block": _turn(4, "합성 위험 막힘", codes=["refund_promise"]),
           "safe": _turn(5, "합성 위험 근거", codes=["date_promise", "tone_haeyo"]),
           "bad": _turn(6, "합성 위험 없음", codes=["discount_promise"]),
           "tone": _turn(7, "합성 질문 같음", codes=["tone_haeyo"]),  # 말투 알림만 — 위험 묶음 아님
           "learn": _turn(8, "합성 질문 같음", reply=STAFF, outcome="as_is")}  # 배우기 차례 — 지난 상담 아님
    db_session.add(ChannelInboundEventLog(dedupe_key="ev-raw-1", payload_hash="0" * 64, chat_type="message",
                                          raw_payload={"entity": {"chatId": "ev-chat-1", "plainText": f"{RAW} 원본"}},
                                          source_chat_id="ev-chat-1", status="user_chat_handled"))
    db_session.commit()
    return ids


def _run(client=None, run_id=None, actor=None):
    return evals_run.run_eval(db_session, actor_id=actor, now=NOW, client=client, run_id=run_id)


def _results():
    return evals.latest_results(db_session)


def _line(key):
    row = db_session.get(SystemSetting, key, populate_existing=True)
    return None if row is None else row.setting_value


def test_set_reads_only_masked_columns_and_raw_marks_never_leak(world, caplog):
    ids = _world_turns()
    _settings()
    statements = []

    def remember(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", remember)
    try:
        built = evals.build_eval_set(db_session, NOW)
    finally:
        event.remove(engine, "before_cursor_execute", remember)
    assert [case.turn_id for case in built.past] == [ids["hand"], ids["diff"], ids["same"]]  # 최근 것부터
    assert {case.turn_id for case in built.risk} == {ids["block"], ids["safe"], ids["bad"]}  # 말투 알림만은 뺀다
    joined = "\n".join(statements).lower()
    for column in ("masked_draft", "rewrite_note_masked", "edit_detail_masked", "channel_inbound_event_logs"):
        assert column not in joined, column
    texts = [value for case in (*built.past, *built.risk) for value in vars(case).values()]
    assert not any(RAW in str(value) for value in texts) and RAW not in repr(built)
    assert ASKED not in repr(built)  # 글은 repr 에 없다
    client = FakeClient()
    with caplog.at_level(logging.INFO):  # DEBUG 면 두뇌가 '본문 디버그 로그'로 부르지 않는다(그것도 막는 쪽)
        assert _run(client)["status"] == evals.DONE
    sent = json.dumps(client.calls, ensure_ascii=False)
    assert ASKED in sent and RAW not in sent  # 가린 질문만 모델에
    stored = json.dumps(_line(evals.RESULTS_KEY), ensure_ascii=False)
    for mark in (RAW, ASKED, STAFF, WHY, "합성 질문", "합성 위험"):
        assert mark not in stored and mark not in caplog.text, mark


def test_no_held_out_means_an_empty_past_set(world):
    _turn(1, "합성 질문 같음", reply=STAFF, outcome="as_is")  # 배우기 차례뿐
    _turn(2, "합성 질문 다름", reply="합성 직원 답 둘입니다", outcome="edited")
    _settings(risk=0)
    assert evals.build_eval_set(db_session, NOW).past == ()
    client = FakeClient()
    assert _run(client)["status"] == evals.DONE
    assert client.calls == []
    run = _results()[0]
    assert run["past"] == evals.empty_past() and run["codes"] == evals.empty_codes()
    row = evals_view.eval_view(db_session, viewer_of(world.admin), now=NOW, erp=False)["rows"][0]
    assert row["label"] == "지난 상담 0개" and "묶음 0" in row["text"] and row["verdict"]["tone"] == "warning"


def test_fake_brain_counts_the_three_rows(world):
    ids = _world_turns()
    _settings(target=50)
    client = FakeClient()
    result = _run(client)
    # 초안 6 + 판정 1('다름' — '같음'은 글자 복사) + 넘김 까닭 1('넘김' — 까닭 '모름'은 규칙 까닭이 아니다)
    assert result["status"] == evals.DONE and len(client.calls) == 8
    judged = client.judge_calls
    assert len(judged) == 1 and judged[0]["model"] == evals_meaning.MODEL
    assert judged[0]["output_config"]["effort"] == "medium"
    assert judged[0]["output_config"]["format"]["schema"]["properties"]["verdict"]["enum"] == [
        "pass", "fail_conflict", "fail_promise", "fail_unanswered"]  # '부분'은 없다
    caused = client.cause_calls
    assert len(caused) == 1 and caused[0]["model"] == evals_handoff.MODEL
    assert caused[0]["system"][1]["text"] == "[회사 지식]\n" + brain_prompt.knowledge_text(KNOWLEDGE)  # 두뇌가 받은 지식
    run = _results()[0]
    assert run["past"] == {"total": 3, "done": 3, "passed": 1, "right_handoff": 0}
    assert run["risk"] == {"total": 3, "done": 3, "bad": 1}
    assert run["codes"] == {"past": {"copied": 1, "fail_conflict": 1, "handoff": 1},
                            "risk": {"safe": 2, "unsupported": 1}}
    assert run["handoffs"] == {"unsure": 1} and run["handoff_kinds"] == {"missing": 1}
    assert {(f["set"], f["turn"], f["code"]) for f in run["failures"]} == {
        ("past", ids["diff"], "fail_conflict"), ("past", ids["hand"], "handoff"), ("risk", ids["bad"], "unsupported")}
    assert run["cost_usd"] == "8.000000" and run["model"] == brain_prompt.MODEL  # 판정 돈도 평가 줄 · 이번 평가 돈
    assert _line(brain_spend.EVAL_SPEND_KEY)["usd"] == "8"
    view = evals_view.eval_view(db_session, viewer_of(world.admin), now=NOW, erp=False)
    past, risk, cq = view["rows"]
    assert past["pct"] == 33 and past["text"] == "보내도 되는 답 33% (3차례 · 옳은 넘김 0) · 기준 50%"
    assert past["verdict"] == {"text": "기준 밑", "tone": "danger"}
    assert risk["text"] == "근거 없는 약속 1 · 기준 0" and risk["verdict"] == {"text": "1건", "tone": "danger"}
    assert cq["key"] == "cq" and cq["label"].startswith("능력 질문 ") and " / " in cq["verdict"]["text"]
    assert cq["text"].startswith("회사 지식만 ")
    assert [f["label"] for f in view["failures"]][0] == f"위험 문장 · 차례 #{ids['bad']}"
    assert view["failures"][0]["reason"] == "근거 없는 약속"
    assert view["failures"][1]["reason"] == "직원 답과 사실이 어긋남"
    assert view["last"]["status_label"] == "끝남" and view["last"]["cost"] == "$8.00" and view["running"] is False
    # 가장 오래된 '같음' 초안(넘김 + 까닭 판정 · 다름 + 판정 뒤)의 앞 대화
    context = json.dumps(client.calls[4]["messages"], ensure_ascii=False)
    assert "합성 앞 말" in context


def test_cap_zero_never_runs_and_settings_zero_stops_a_queued_run(world):
    _world_turns()
    client = FakeClient()
    assert _run(client)["code"] == "EVAL_NO_CAP"  # 처음 값 0 — 줄도 만들지 않는다
    assert client.calls == [] and _line(evals.RESULTS_KEY) is None
    _settings()
    run = evals.begin_run(db_session, world.admin, NOW)
    db_session.commit()
    row = db_session.get(SystemSetting, evals.SETTINGS_KEY)
    row.setting_value = {**row.setting_value, "cap_usd": "0"}  # 줄에 선 뒤 ADMIN 이 0 으로 내림
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(row, "setting_value")
    db_session.commit()
    assert _run(client, run_id=run["id"]) == {"status": evals.NOT_READY, "code": "no_cap", "run": run["id"]}
    assert client.calls == [] and _line(brain_spend.EVAL_SPEND_KEY) is None


def test_the_run_stops_at_the_cap(world):
    _world_turns()
    _settings(cap="4")  # 최악값 3 · 한 번 1 → '넘김' 초안 · 그 까닭 판정 뒤 '다름' 차례의 초안 예약(2 + 3)이 넘친다
    client = FakeClient()
    result = _run(client)
    assert result["status"] == evals.CAP_STOPPED and result["code"] == brain_spend.DAILY_CAP_REACHED
    assert len(client.calls) == 2 and len(client.cause_calls) == 1 and client.judge_calls == []
    run = _results()[0]
    assert run["past"]["done"] == 1 and run["risk"]["done"] == 0 and Decimal(run["cost_usd"]) <= Decimal("4")
    assert Decimal(_line(brain_spend.EVAL_SPEND_KEY)["usd"]) <= Decimal("4")
    assert _line(brain_spend.EVAL_SPEND_KEY)["reserved"] == "0.000000"  # 넘친 예약은 되돌렸다
    last = evals_view.eval_view(db_session, viewer_of(world.admin), now=NOW, erp=False)["last"]
    assert last["status_label"] == "상한에서 멈춤" and last["reason"] == "한 번 상한"


def test_no_key_is_not_ready_on_the_job_path_too(world, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _world_turns()
    _settings()
    run = evals.begin_run(db_session, world.admin, NOW)
    db_session.commit()
    assert evals_run.run_eval_job(run["id"]) == {"status": evals.NOT_READY, "code": "no_api_key", "run": run["id"]}
    stored = _results()[0]
    assert stored["status"] == evals.NOT_READY and stored["past"]["done"] == 0 and stored["finished_at"]
    assert _line(brain_spend.EVAL_SPEND_KEY) is None
    admin = db_session.get(User, world.admin_id)  # 줄 일은 끝에 세션을 닫는다(줄 일 꼴) — 사람을 다시 읽는다
    view = evals_view.eval_view(db_session, viewer_of(admin), now=NOW, erp=False)
    assert view["last"]["status_label"] == "준비 안 됨" and view["last"]["reason"] == "두뇌 열쇠 없음"


def test_nothing_is_sent_learned_counted_proposed_or_rewritten(world, monkeypatch):
    from foms.services.brain import usage, usage_events
    from foms.services.cs_agent import case_memory, handoff_memo, handoff_send, memo, send, send_flow, turns
    from foms.services.erp_actions import lifecycle

    called = []

    def forbid(name):
        def stub(*_args, **_kwargs):
            called.append(name)
            raise AssertionError(name)
        return stub

    targets = ((memo, "post_private_memo"), (handoff_memo, "post_handoff_memo"), (send, "send_reply"),
               (send_flow, "send_turn"), (handoff_send, "send_handoff"), (case_memory, "attach_staff_replies"),
               (turns, "record_staff_reply"), (turns, "record_brain_result"), (usage, "count_reads"),
               (usage, "count_doc_reads"), (usage_events, "record_uses"), (lifecycle, "propose"))
    for module, name in targets:
        monkeypatch.setattr(module, name, forbid(f"{module.__name__}.{name}"))  # 없는 이름이면 여기서 빨강
        assert not hasattr(evals_run, name), name  # 평가 모듈은 가져오지도 않는다
    _world_turns()
    _settings()
    table = CsAgentTurn.__table__
    before = [tuple(row) for row in db_session.execute(select(table).order_by(table.c.id))]
    assert _run(FakeClient())["status"] == evals.DONE
    assert called == []
    assert [tuple(row) for row in db_session.execute(select(table).order_by(table.c.id))] == before


def test_the_real_draft_daily_spend_lines_do_not_change(world):
    _world_turns()
    _settings()
    db_session.add(SystemSetting(setting_key=brain_spend.SPEND_KEY, setting_value={
        "date": NOW.date().isoformat(), "usd": "1", "reserved": "0", "calls": 1}))
    db_session.commit()
    before = copy.deepcopy(_line(brain_spend.SPEND_KEY))
    assert _run(FakeClient())["status"] == evals.DONE
    assert _line(brain_spend.SPEND_KEY) == before
    assert _line(brain_spend.LEARNING_SPEND_KEY) is None
    assert _line(brain_spend.EVAL_SPEND_KEY)["calls"] == 8  # 초안 6 + 판정 1 + 넘김 까닭 1


def test_results_hold_no_text_and_only_the_last_ten(world):
    _turn(1, "합성 질문 같음", held_out=True, reply=STAFF)
    _settings(past=1, risk=0)
    for _ in range(12):
        assert _run(FakeClient())["status"] == evals.DONE
    runs = _results()
    assert [run["id"] for run in runs] == list(range(12, 2, -1))
    keys = {"id", "status", "code", "actor_id", "judge", "started_at", "heartbeat_at", "finished_at", "model",
            "cost_usd", "target_pct", "past", "risk", "codes", "handoffs", "handoff_kinds", "failures"}
    assert all(set(run) == keys for run in runs)
    assert "합성" not in json.dumps(runs, ensure_ascii=False)


def test_one_at_a_time_and_a_silent_run_is_released(world):
    _settings()
    first = evals.begin_run(db_session, world.admin, NOW)
    db_session.commit()
    with pytest.raises(evals.EvalError) as busy:
        evals.begin_run(db_session, world.admin, NOW)
    assert busy.value.code == "EVAL_BUSY" and busy.value.message == "시험이 이미 도는 중이에요."
    db_session.rollback()
    later = NOW + evals.STALE_AFTER + datetime.timedelta(minutes=1)
    assert evals_view.eval_view(db_session, viewer_of(world.admin), now=later, erp=False)["running"] is False
    assert evals.claim_run(db_session, first["id"], later) is None  # 너무 늦게 꺼낸 줄 일은 돌지 않는다
    second = evals.begin_run(db_session, world.admin, later)
    db_session.commit()
    statuses = {run["id"]: run["status"] for run in _results()}
    assert statuses == {first["id"]: evals.STALE, second["id"]: evals.QUEUED}


def test_a_released_run_stops_spending_and_does_not_overwrite(world):
    """R-25 — 도는 중에 다른 쪽이 '멈춘 채 끝남'으로 푼 평가는 다음 차례를 부르지 않고(돈을 더 안 쓰고) 상태를 덮어쓰지 않는다."""
    _world_turns()
    _settings()
    client = FakeClient()
    real = client._create

    def _release_after_first(**params):
        out = real(**params)
        if len(client.calls) == 1:  # 첫 부르기 도중 — 다른 쪽(새 [시험 다시 돌리기])이 이 줄을 풀었다
            row = db_session.get(SystemSetting, evals.RESULTS_KEY, populate_existing=True)
            value = copy.deepcopy(row.setting_value)
            value["runs"][-1].update(status=evals.STALE, finished_at="2030-01-01T00:00:00")
            row.setting_value = value
            flag_modified(row, "setting_value")
            db_session.commit()
        return out

    client.beta = SimpleNamespace(messages=SimpleNamespace(create=_release_after_first))
    # 첫 차례('넘김')는 그 안의 넘김 까닭 판정까지 끝내고, 다음 차례는 부르지 않는다
    assert _run(client)["status"] == evals.STALE and len(client.calls) == 2 and len(client.cause_calls) == 1
    run = _results()[0]
    assert run["status"] == evals.STALE and run["finished_at"] == "2030-01-01T00:00:00"
    assert run["past"]["done"] == 0  # 늦은 소식이 덮어쓰지 않았다
    assert evals.update_run(db_session, run["id"], NOW, status=evals.DONE) is False
    db_session.commit()
    assert _results()[0]["status"] == evals.STALE


def test_the_job_runs_on_the_worker_queue(monkeypatch):
    """계약 — 줄 일 경로가 함수로 풀리고, ``default`` 줄에 들어가며, 그 줄은 감독받는 WORKER 큐 소비자만 꺼낸다."""
    from rq.utils import import_attribute

    from foms.services.jobs import queue as jobs_queue

    assert import_attribute(evals.JOB_PATH) is evals_run.run_eval_job
    rq_jobs = [job for job in jobs() if job.name == "rq_worker"]
    assert len(rq_jobs) == 1 and rq_jobs[0].argv[-2:] == ("--queues", "default")
    assert worker_branch_of_start_sh().strip().splitlines()[-1].strip() == "exec python tools/ops/worker_supervisor.py"
    monkeypatch.setattr(jobs_queue, "_rq_queue", None)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # 만들기만 — 연결은 쓸 때(여기서는 쓰지 않는다)
    assert jobs_queue.get_rq_queue().name == "default"
    calls = []
    monkeypatch.setattr(evals, "get_rq_queue", lambda: SimpleNamespace(enqueue=lambda *a, **k: calls.append((a, k))))
    assert evals.enqueue_run(7) is True
    assert calls == [((evals.JOB_PATH, 7), {"job_id": "ai_staff_eval_7", "job_timeout": evals.JOB_TIMEOUT})]
    monkeypatch.setattr(evals, "get_rq_queue", lambda: None)
    assert evals.enqueue_run(8) is False  # 큐가 없으면 넣지 않는다 — web 에서 대신 돌리지 않는다


def test_past_set_skips_turns_whose_answer_is_the_ai_draft_itself(world):
    """그대로 보냄(as_is) · 복사(copied) 차례는 직원 답이 AI 초안 자신이라 '지난 상담'에서 뺀다 — 고침 · 직접 답만."""
    from foms.services.ai_staff import evals
    kept = {_turn(41, "합성 질문 고침", held_out=True, reply=STAFF, outcome="edited"),
            _turn(42, "합성 질문 직접", held_out=True, reply=STAFF, outcome="direct")}
    skipped = {_turn(43, "합성 질문 그대로", held_out=True, reply=STAFF, outcome="as_is"),
               _turn(44, "합성 질문 복사", held_out=True, reply=STAFF, outcome="copied")}
    got = {case.turn_id for case in evals._past_cases(db_session, 10, now_utc_naive())}
    assert kept <= got and not (skipped & got)
