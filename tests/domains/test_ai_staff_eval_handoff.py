"""'AI 시험' 넘김 까닭 가르기(설계서 2026-11-23-brain-learning-upgrade 4.3) — 결과 줄 ``handoffs`` 옆 ``handoff_kinds``.

완료 기준:
- 옳은 넘김(늘 사람 몫 넷)은 가르지 않는다. 규칙 까닭(일정 · 사람인지 물음 · 사진만)은 판정자를 부르지 않고 '늘 사람 몫 규칙'.
- 그 밖의 넘김은 판정 한 번 — 재료 충분 → '몸 사림', 모자람 → '지식이 없음', 부르기 실패 · 꼴 틀림 · 가림 검사 → '판정 못 받음'.
  판정자는 가린 질문 · 직원 답 · 앞 대화와 **두뇌가 받은 지식 글 그대로**를 받는다(찾기 단계가 없어 '있는데 못 찾음'은 없다).
- 까닭 판정도 같은 한 번 상한 안 — 넘치면 그 차례는 세지 않고 '상한에서 멈춤'(채점 줄도 없다).
- 결과 줄에는 까닭별 수만(글 · 판정 까닭 없음).
합성 차례 · 합성 지식 · 합성 판정자만(바깥 호출 없음).
"""

from __future__ import annotations

import json

from sqlalchemy import select

from db import db_session
from foms.persistence.graft.models import AiStaffEvalMark
from foms.services.ai_staff import evals, evals_handoff, evals_meaning
from foms.services.cs_agent import brain_prompt, brain_spend
from foms.services.cs_agent.brain_spend import BrainUnavailable, SpendCapReached
from models import SystemSetting
from tests.domains.test_ai_staff_evals import (  # noqa: F401 — world 는 fixture
    ANSWERS, ASKED, KNOWLEDGE, FakeClient, _results, _run, _settings, _turn, world,
)

TIMEOUT = "부르기 실패"
#: (표식, 넘긴 까닭, 합성 판정자 답 — ``None`` 이면 부르면 안 된다). '없음'은 넘기지 않았다면서 빈 초안(세기는 넘김).
CASES = (("가", "unsure", "enough"), ("나", "other", "missing"), ("다", "none", "broken"), ("라", "unsure", TIMEOUT),
         ("마", "asked_if_ai", None), ("바", "photo", None), ("사", "schedule", None), ("아", "complaint", None))


def _hand(monkeypatch, cases=CASES):
    plan = {}
    for n, (mark, reason, answer) in enumerate(cases, start=1):
        key = f"합성 넘김 차례 {mark}"
        monkeypatch.setitem(ANSWERS, key, ("", [], reason != "none", reason))
        _turn(n, key, held_out=True, reply=f"합성 직원 답 {n}번입니다", context="[손님] 합성 앞 말")
        plan[key] = answer
    return plan


def test_each_needless_handoff_gets_one_kind_and_rule_reasons_cost_nothing(world, monkeypatch):
    plan = _hand(monkeypatch)
    _settings(past=20, risk=0)
    seen = []

    def judge(question, staff, context, material):
        seen.append((question, staff, context, material))
        answer = plan[next(key for key in plan if key in question)]
        assert answer is not None, "규칙 까닭 · 옳은 넘김에는 부르지 않는다"
        if answer == TIMEOUT:
            raise BrainUnavailable("timeout")
        return answer

    client = FakeClient()
    with evals_handoff.handoff_source(judge), evals_meaning.meaning_source(lambda *texts: "pass"):
        assert _run(client)["status"] == evals.DONE
    assert len(client.calls) == len(plan) and client.cause_calls == []  # 초안만 — 합성 판정자는 모델 · 돈 없음
    assert len(seen) == 4 and all(q.startswith(ASKED) for q, *_rest in seen)
    assert {context for _q, _s, context, _m in seen} == {"[손님] 합성 앞 말"}
    assert {material for *_rest, material in seen} == {brain_prompt.knowledge_text(KNOWLEDGE)}  # 두뇌가 받은 지식 그대로
    run = _results()[0]
    assert run["handoff_kinds"] == {"held_back": 1, "missing": 1, "unknown": 2, "rule": 3}
    assert sum(run["handoff_kinds"].values()) == run["codes"]["past"]["handoff"]  # 옳은 넘김(불만)은 가르지 않는다
    assert run["codes"]["past"] == {"handoff": 7, "right_handoff": 1}
    assert run["handoffs"] == {"unsure": 2, "other": 1, "asked_if_ai": 1, "photo": 1, "schedule": 1,
                               "complaint": 1}  # '까닭 없는 빈 초안'은 넘긴 것이 아니라 넘김 까닭 수에 없다
    stored = json.dumps(db_session.get(SystemSetting, evals.RESULTS_KEY).setting_value, ensure_ascii=False)
    assert "합성" not in stored and ASKED not in stored


def test_a_cause_judge_at_the_cap_stops_the_run_without_counting_that_turn(world, monkeypatch):
    _hand(monkeypatch, CASES[:1])
    _settings(past=5, risk=0)

    def capped(*_texts):
        raise SpendCapReached(brain_spend.DAILY_CAP_REACHED)

    with evals_handoff.handoff_source(capped):
        result = _run(FakeClient())
    assert result["status"] == evals.CAP_STOPPED and result["code"] == brain_spend.DAILY_CAP_REACHED
    run = _results()[0]
    assert run["past"]["done"] == 0 and run["handoffs"] == {} and run["handoff_kinds"] == {}
    assert list(db_session.scalars(select(AiStaffEvalMark))) == []


def test_a_masked_field_that_still_leaks_is_unknown_and_never_judged(world, monkeypatch):
    _hand(monkeypatch, CASES[:1])
    _settings(past=5, risk=0)

    def leaks(_text):
        raise evals_handoff.MaskLeak({"전화": 1})

    monkeypatch.setattr(evals_handoff, "require_masked", leaks)
    calls = []
    with evals_handoff.handoff_source(lambda *texts: calls.append(texts) or "enough"):
        assert _run(FakeClient())["status"] == evals.DONE
    assert calls == [] and _results()[0]["handoff_kinds"] == {"unknown": 1}


def test_the_model_path_sends_one_cached_knowledge_block_and_pays_on_the_eval_line(world, monkeypatch):
    _hand(monkeypatch, CASES[:1])
    _settings(past=5, risk=0)
    client = FakeClient()
    assert _run(client)["status"] == evals.DONE
    sent = client.cause_calls
    assert len(sent) == 1 and sent[0]["model"] == evals_handoff.MODEL
    assert sent[0]["output_config"]["format"]["schema"]["properties"]["verdict"]["enum"] == ["enough", "missing"]
    assert [block.get("cache_control") for block in sent[0]["system"]] == [None, {"type": "ephemeral", "ttl": "5m"}]
    assert "합성 직원 답 1번입니다" in sent[0]["messages"][0]["content"]
    run = _results()[0]
    assert run["handoff_kinds"] == {"missing": 1} and run["cost_usd"] == "2.000000"  # 초안 1 + 까닭 1
    assert db_session.get(SystemSetting, brain_spend.EVAL_SPEND_KEY).setting_value["calls"] == 2
    assert db_session.get(SystemSetting, brain_spend.SPEND_KEY) is None  # 상담 초안 하루 돈 줄은 그대로
