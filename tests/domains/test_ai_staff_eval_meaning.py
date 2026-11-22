"""'AI 시험' 뜻 판정 · 옳은 넘김 · 까닭 코드 수 · 매주 한 번(설계서 2026-11-22-ai-eval-meaning-judge 4 — D281).

완료 기준:
- 합성 판정자(:func:`.evals_meaning.meaning_source`)로 same · partial · different · 부르기 실패 · 꼴 틀림 · 돈 상한을 센다 —
  통과는 same 하나, partial 은 따로 센다, 실패 · 꼴 틀림은 '판정 못 받음', 돈 상한이면 평가가 '상한에서 멈춤'.
- 늘 사람 몫인 넘김 넷은 분모에서 빠지고(옳은 넘김), 그 밖의 넘김은 실패다.
- 글자 '복사'면 판정자를 부르지 않는다(부른 수 0). ``codes`` 합 = 본 수.
- 가짜 두뇌가 낸 꼴 틀린 판정 답은 '판정 못 받음'이고 돈은 평가 줄에 적힌다.
- 판 ⑪ 글: "AI 답이 직원 답과 같은 뜻 N% (M차례 · 옳은 넘김 K · 지난번 P%)" — 새 칸이 없는 옛 결과 줄도 그린다.
- 매주 단계: 월요일이 아니면 · 6일 안에 돈 결과가 있으면 · 준비가 안 됐으면 · 도는 줄이 있으면 넣지 않는다, 맞으면 한 번만 넣는다.
- 밤 바퀴 단계는 여섯이고 마지막이 ``weekly_eval`` 이다.
합성 차례 · 합성 지식만 — 바깥 호출 없음(모델 · 큐 모두 가짜).
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from db import db_session
from foms.services.ai_staff import evals, evals_meaning, evals_view, evals_weekly
from foms.services.brain.scope import viewer_of
from foms.services.cs_agent import brain_prompt, brain_spend, learning_pass
from foms.services.cs_agent.brain_spend import BrainUnavailable, SpendCapReached
from foms.services.cs_agent.state import KST
from models import SystemSetting
from tests.domains.test_ai_staff_evals import (  # noqa: F401 — world 는 fixture
    ANSWERS, ASKED, NOW, STAFF, FakeClient, _results, _run, _settings, _turn, world,
)

MONDAY = datetime.datetime(2026, 11, 23, 0, 20, tzinfo=KST)
TUESDAY = MONDAY + datetime.timedelta(days=1)


def _past_text():
    return evals_view.eval_view(db_session, viewer_of(_admin()), now=NOW, erp=False)["rows"][0]


def _admin():
    from models import User
    return db_session.query(User).filter(User.username == "ev_admin").one()


def _plant(monkeypatch, keys, start):
    """표식마다 '지난 상담' 한 차례(초안은 직원 답과 글자가 다르다)."""
    ids = {}
    for n, key in enumerate(keys, start=start):
        monkeypatch.setitem(ANSWERS, key, ("다른 안내 문장을 길게 적어 드립니다", ["hours-day"], False))
        ids[key] = _turn(n, key, held_out=True, reply=f"합성 직원 답 {n}번입니다")
    return ids


# ── 뜻 판정 ──────────────────────────────────────────────────────────────
def test_the_meaning_judge_counts_same_partial_different_and_unknown(world, monkeypatch):
    plan = {"합성 뜻 같음": "same", "합성 뜻 덜함": "partial", "합성 뜻 다름": "different", "합성 뜻 꼴틀림": "maybe"}
    ids = _plant(monkeypatch, [*plan, "합성 뜻 모름"], 11)
    _turn(10, "합성 질문 같음", held_out=True, reply=STAFF)  # 글자 복사 — 판정자를 부르지 않는다
    _settings(past=10, risk=0, target=0)
    seen = []

    def fake(question, staff, draft):
        seen.append((question, staff, draft))
        key = next(k for k in ids if k in question)
        if key == "합성 뜻 모름":
            raise BrainUnavailable("timeout")
        return plan[key]

    client = FakeClient()
    with evals_meaning.meaning_source(fake):
        assert _run(client)["status"] == evals.DONE
    assert len(client.calls) == 6 and client.judge_calls == []  # 합성 판정자 — 모델을 부르지 않는다
    assert len(seen) == 5 and all(question.startswith(ASKED) for question, _s, _d in seen)
    assert {staff for _q, staff, _d in seen} == {f"합성 직원 답 {n}번입니다" for n in range(11, 16)}
    run = _results()[0]
    assert run["past"] == {"total": 6, "done": 6, "passed": 2, "right_handoff": 0, "partial": 1}
    assert run["codes"]["past"] == {"copied": 1, "same": 1, "partial": 1, "different": 1, "judge_unknown": 2}
    assert sum(run["codes"]["past"].values()) == run["past"]["done"]
    assert sorted((f["turn"], f["code"]) for f in run["failures"]) == sorted([
        (ids["합성 뜻 덜함"], "partial"), (ids["합성 뜻 다름"], "different"), (ids["합성 뜻 꼴틀림"], "judge_unknown"),
        (ids["합성 뜻 모름"], "judge_unknown")])
    assert run["cost_usd"] == "6.000000"  # 초안 6 — 합성 판정자는 돈을 쓰지 않는다
    row = _past_text()
    assert row["pct"] == 33 and row["text"] == "AI 답이 직원 답과 같은 뜻 33% (6차례 · 옳은 넘김 0)"
    assert row["verdict"] == {"text": "33%", "tone": "primary"}


def test_a_spend_cap_inside_the_judge_stops_the_run(world, monkeypatch):
    _plant(monkeypatch, ["합성 뜻 같음"], 11)
    _settings(past=10, risk=0)

    def capped(*_texts):
        raise SpendCapReached(brain_spend.DAILY_CAP_REACHED)

    with evals_meaning.meaning_source(capped):
        result = _run(FakeClient())
    assert result["status"] == evals.CAP_STOPPED and result["code"] == brain_spend.DAILY_CAP_REACHED
    assert _results()[0]["past"]["done"] == 0  # 그 차례는 세지 않았다


def test_a_copy_never_calls_the_judge(world):
    _turn(10, "합성 질문 같음", held_out=True, reply=STAFF)
    _settings(past=10, risk=0)
    calls = []
    with evals_meaning.meaning_source(lambda *texts: calls.append(texts) or "different"):
        assert _run(FakeClient())["status"] == evals.DONE
    run = _results()[0]
    assert calls == [] and run["past"]["passed"] == 1 and run["codes"]["past"] == {"copied": 1}


def test_a_bad_judge_answer_from_the_model_is_unknown_and_paid_on_the_eval_line(world, monkeypatch):
    _plant(monkeypatch, ["합성 뜻 꼴틀림"], 11)  # 가짜 두뇌 판정표(JUDGED)에 없는 표식 → 꼴 틀린 답
    _settings(past=10, risk=0)
    client = FakeClient()
    assert _run(client)["status"] == evals.DONE
    assert len(client.judge_calls) == 1
    sent = client.judge_calls[0]
    assert sent["model"] == evals_meaning.MODEL and sent["system"][0]["text"] == evals_meaning.SYSTEM
    run = _results()[0]
    assert run["codes"]["past"] == {"judge_unknown": 1} and run["past"]["passed"] == 0
    assert run["cost_usd"] == "2.000000" and db_session.get(SystemSetting, brain_spend.EVAL_SPEND_KEY).setting_value[
        "calls"] == 2
    assert db_session.get(SystemSetting, brain_spend.SPEND_KEY) is None  # 상담 초안 하루 돈 줄은 그대로


# ── 옳은 넘김 ────────────────────────────────────────────────────────────
def test_always_human_handoffs_leave_the_denominator_and_others_fail(world, monkeypatch):
    assert evals_meaning.RIGHT_HANDOFF_REASONS <= set(brain_prompt.HANDOFF_REASONS)
    reasons = ["complaint", "order_lookup", "discount_refund", "human_only_amount", "schedule"]
    ids = {}
    for n, reason in enumerate(reasons, start=21):
        monkeypatch.setitem(ANSWERS, f"합성 넘김 {reason}", ("", [], True, reason))
        ids[reason] = _turn(n, f"합성 넘김 {reason}", held_out=True, reply=f"합성 직원 답 {n}번입니다")
    _turn(20, "합성 질문 같음", held_out=True, reply=STAFF)
    _settings(past=10, risk=0, target=50)

    def never(*_texts):
        raise AssertionError("넘김 · 복사에는 판정자를 부르지 않는다")

    with evals_meaning.meaning_source(never):
        assert _run(FakeClient())["status"] == evals.DONE
    run = _results()[0]
    assert run["past"] == {"total": 6, "done": 6, "passed": 1, "right_handoff": 4, "partial": 0}
    assert run["codes"]["past"] == {"right_handoff": 4, "handoff": 1, "copied": 1}
    assert sum(run["codes"]["past"].values()) == run["past"]["done"]
    assert [(f["turn"], f["code"]) for f in run["failures"]] == [(ids["schedule"], "handoff")]
    row = _past_text()
    assert row["pct"] == 50 and row["text"] == "AI 답이 직원 답과 같은 뜻 50% (2차례 · 옳은 넘김 4) · 기준 50%"
    assert row["verdict"] == {"text": "통과", "tone": "success"}


# ── 화면 글(옛 줄 포함) ──────────────────────────────────────────────────
def _stored(*pasts):
    runs = [{"id": n, "status": evals.DONE, "code": None, "actor_id": None, "started_at": "2026-11-16T00:00:00",
             "heartbeat_at": "2026-11-16T00:10:00", "finished_at": "2026-11-16T00:10:00", "model": None,
             "cost_usd": "0", "target_pct": 0, "past": past, "risk": {"total": 0, "done": 0, "bad": 0},
             "failures": [{"set": "past", "turn": 9, "code": "direct"}]}
            for n, past in enumerate(pasts, start=1)]
    db_session.merge(SystemSetting(setting_key=evals.RESULTS_KEY, setting_value={"runs": runs}))
    db_session.commit()


def test_the_past_row_shows_the_last_run_and_old_rows_still_render(world):
    old = {"total": 4, "done": 4, "passed": 1}  # 새 칸(옳은 넘김 · 덜 말함 · codes) 없는 옛 줄
    _stored(old)
    view = evals_view.eval_view(db_session, viewer_of(_admin()), now=NOW, erp=False)
    assert view["rows"][0]["text"] == "AI 답이 직원 답과 같은 뜻 25% (4차례 · 옳은 넘김 0)"
    assert view["failures"][0]["reason"] == "직원 답과 많이 다름"
    _stored(old, {"total": 4, "done": 4, "passed": 2, "right_handoff": 2, "partial": 0})
    assert _past_text()["text"] == "AI 답이 직원 답과 같은 뜻 100% (2차례 · 옳은 넘김 2 · 지난번 25%)"
    _stored({"total": 2, "done": 2, "passed": 0, "right_handoff": 2, "partial": 0})
    row = _past_text()
    assert row["pct"] is None and row["text"] == "견줄 차례가 아직 없어요 (옳은 넘김 2)"


# ── 매주 한 번 ───────────────────────────────────────────────────────────
def _queue(monkeypatch, ok=True):
    put = []
    monkeypatch.setattr(evals, "enqueue_run", lambda run_id: put.append(run_id) or ok)
    return put


def _weekly(at=MONDAY):
    return evals_weekly.run_weekly_eval(db_session, now=at)


def test_weekly_needs_monday_and_ready_settings_and_queues_once(world, monkeypatch):
    assert MONDAY.weekday() == 0
    put = _queue(monkeypatch)
    assert _weekly() == {"off": "not_ready"} and put == []
    _settings()
    assert _weekly(TUESDAY) == {"off": "not_monday"} and put == []
    first = _weekly()
    assert first == {"queued": first["queued"]} and put == [first["queued"]]
    stored = _results()[0]
    assert stored["actor_id"] is None and stored["status"] == evals.QUEUED
    assert _weekly(MONDAY + datetime.timedelta(minutes=15)) == {"off": "already_this_week"}
    evals.update_run(db_session, first["queued"], MONDAY, status=evals.NOT_READY, code="no_api_key")
    db_session.commit()
    assert _weekly(MONDAY + datetime.timedelta(minutes=30)) == {"off": "already_this_week"}  # 돈 없이 끝나도 한 번만
    assert put == [first["queued"]]
    next_week = _weekly(MONDAY + datetime.timedelta(days=7))
    assert next_week["queued"] == first["queued"] + 1


def _manual(days_ago, status, **fields):
    """사람이 누른 결과 줄 하나(``days_ago`` 일 전 시작 · 끝 상태)."""
    at = MONDAY - datetime.timedelta(days=days_ago)
    run = evals.add_run(db_session, actor_id=_admin().id, now=at, settings=evals.read_eval_settings(db_session))
    evals.update_run(db_session, run["id"], at, status=status, **fields)
    db_session.commit()


def test_weekly_skips_when_a_paid_run_is_within_six_days(world, monkeypatch):
    put = _queue(monkeypatch)
    _settings()
    _manual(5, evals.DONE, cost_usd="0.5")
    assert _weekly() == {"off": "already_this_week"} and put == []


def test_weekly_ignores_older_paid_runs_and_unpaid_clicks(world, monkeypatch):
    put = _queue(monkeypatch)
    _settings()
    _manual(8, evals.DONE, cost_usd="0.5")  # 6일보다 오래됨
    _manual(1, evals.FAILED, code="queue_unavailable")  # 사람이 눌렀지만 돈을 쓰지 않음
    assert _weekly()["queued"] is not None and len(put) == 1


def test_weekly_does_not_queue_while_a_run_is_waiting(world, monkeypatch):
    put = _queue(monkeypatch)
    _settings()
    evals.add_run(db_session, actor_id=_admin().id, now=MONDAY, settings=evals.read_eval_settings(db_session))
    db_session.commit()
    assert _weekly(MONDAY + datetime.timedelta(minutes=5)) == {"off": "busy"} and put == []


def test_a_failed_weekly_enqueue_releases_the_row_and_waits_a_week(world, monkeypatch):
    _queue(monkeypatch, ok=False)
    _settings()
    assert _weekly() == {"queued": None, "code": "queue_unavailable"}
    stored = _results()[0]
    assert stored["status"] == evals.FAILED and stored["code"] == "queue_unavailable"
    assert _weekly(MONDAY + datetime.timedelta(minutes=15)) == {"off": "already_this_week"}


def test_the_learning_pass_has_six_steps_ending_with_weekly_eval(monkeypatch):
    order = []
    names = {"run_photo_desc": "photo_desc", "run_weekly_fix": "weekly_fix", "run_photo_learning": "photo_learning",
             "run_handoff_learning": "handoff_learning", "resort_cards": "card_resort",
             "run_weekly_eval": "weekly_eval"}
    for attr, name in names.items():
        monkeypatch.setattr(learning_pass, attr, lambda *_a, _n=name, **_k: order.append(_n) or {"off": "x"})
    session = SimpleNamespace(rollback=lambda: None)
    assert learning_pass.run_learning(session, now=MONDAY, stop_check=lambda: None) is None  # 모두 꺼짐 — 요약 없음
    assert order == list(names.values())
    monkeypatch.setattr(learning_pass, "run_weekly_eval", lambda *_a, **_k: {"queued": 3})
    assert learning_pass.run_learning(session, now=MONDAY, stop_check=lambda: None) == {"weekly_eval": {"queued": 3}}
