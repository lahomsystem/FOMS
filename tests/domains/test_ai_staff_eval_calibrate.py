"""'AI 시험' 채점하는 AI 맞추기(설계서 2026-11-23-brain-learning-upgrade 4.2 · 7절 '두 비율과 바로잡은 통과율 셈') — 손으로 셈한
값과 견준다 · 판 ⑪ 지난 상담 줄 글 한 구절 · 옛 결과 줄.

완료 기준:
- Rogan–Gladen: (0.5 + 0.7 − 1) ÷ (0.8 + 0.7 − 1) = 0.4 · 0 밑 · 1 위는 자른다 · 분모 0 이하는 정하지 않는다.
- 이항 누적 표(n 4 · p ½ = 1/16 · 5/16 · 11/16 · 15/16 · 1) · 백분위수 선형 보간 · 붓스트랩은 같은 재료면 같은 값이고, 뽑을 것이
  하나뿐이면(민감도 · 특이도 1 · 본 통과율 0 이나 1) 폭이 그 값 하나다.
- 30개 · 저마다 5개 전에는 수만(비율 없음).
- 화면: 채점 수 → 모이면 두 비율 · 바로잡은 통과율(오차 폭) · 넘김은 '늘 사람 몫' 분류와 같은 수. 새 줄은 "보내도 되는 답",
  옛 줄(``judge`` 칸 없음)은 옛 글 그대로이고 바로잡지 않는다. '지난번'은 같은 자끼리만.
합성 줄만 — 바깥 호출 없음.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.persistence.graft.models import AiStaffEvalMark
from foms.services.ai_staff import evals, evals_view
from foms.services.ai_staff.evals_calibrate import (
    MIN_EACH, MIN_GRADED, binomial_cdf, bootstrap_range, calibrate, quantile, rogan_gladen,
)
from foms.services.brain.scope import viewer_of
from foms.services.datetime_kst import now_utc_naive
from models import SystemSetting
from tests.domains.test_ai_staff_evals import NOW, world  # noqa: F401 — world 는 fixture

#: 사장님 '보내도 돼요' 20(AI 통과 16 · 실패 4) · '안 돼요' 10(AI 실패 7 · 통과 3) → 민감도 0.8 · 특이도 0.7.
PAIRS = [(True, True)] * 16 + [(True, False)] * 4 + [(False, False)] * 7 + [(False, True)] * 3


# ── 셈 ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("observed, sensitivity, specificity, expected", [
    (0.5, 0.8, 0.7, 0.4),  # (0.5 + 0.7 − 1) / (0.8 + 0.7 − 1) = 0.2 / 0.5
    (0.6, 0.9, 0.9, 0.625),  # 0.5 / 0.8
    (0.1, 0.8, 0.7, 0.0),  # −0.2 / 0.5 → 0 으로 자름
    (0.95, 0.8, 0.7, 1.0),  # 0.65 / 0.5 = 1.3 → 1 로 자름
    (0.5, 0.4, 0.6, None),  # 분모 0
    (0.5, 0.3, 0.5, None),  # 분모 −0.2
])
def test_rogan_gladen_matches_hand_values(observed, sensitivity, specificity, expected):
    got = rogan_gladen(observed, sensitivity, specificity)
    assert got == expected if expected is None else got == pytest.approx(expected)


def test_binomial_table_and_quantile_match_hand_values():
    assert binomial_cdf(4, 0.5) == pytest.approx([1 / 16, 5 / 16, 11 / 16, 15 / 16, 1.0])
    assert binomial_cdf(3, 0.0) == [1.0] * 4 and binomial_cdf(3, 1.0) == [0.0, 0.0, 0.0, 1.0]
    assert binomial_cdf(2000, 0.003)[-1] == 1.0  # 큰 n 도 넘치지 않는다
    assert quantile([0.0, 10.0], 0.25) == pytest.approx(2.5)
    assert quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.975) == pytest.approx(4.9)
    assert quantile([7.0], 0.025) == 7.0


def test_calibration_numbers_match_hand_values_and_the_range_is_seeded():
    cal = calibrate(PAIRS, (10, 5))
    assert (cal.graded, cal.ok, cal.bad, cal.ready) == (30, 20, 10, True)
    assert cal.passed_ok == pytest.approx(0.8) and cal.caught == pytest.approx(0.7)
    assert cal.observed == pytest.approx(0.5) and cal.corrected == pytest.approx(0.4)
    assert 0.0 <= cal.low < cal.corrected < cal.high <= 1.0  # 30개 · 10차례면 폭이 넓다(0 ~ 1 가까이)
    assert calibrate(PAIRS, (10, 5)) == cal  # 씨앗이 같으면 같은 폭
    big = calibrate(PAIRS * 5, (200, 100))  # 같은 비율 · 다섯 배 채점 · 200차례 — 값은 같고 폭은 좁다
    assert big.corrected == pytest.approx(0.4) and cal.low <= big.low < 0.4 < big.high <= cal.high
    assert big.high - big.low < cal.high - cal.low
    assert bootstrap_range((200, 100), (100, 80), (50, 35), seed=7) != (big.low, big.high)  # 대조군 — 씨앗이 다르면 다르다


def test_a_range_with_only_one_possible_draw_is_that_value():
    perfect = [(True, True)] * 25 + [(False, False)] * 5
    for observed, value in (((8, 8), 1.0), ((8, 0), 0.0)):
        cal = calibrate(perfect, observed)
        assert (cal.passed_ok, cal.caught, cal.corrected, cal.low, cal.high) == (1.0, 1.0, value, value, value)
    assert bootstrap_range((8, 4), (5, 0), (5, 0)) is None  # 민감도 · 특이도 0 — 정해지는 판이 없다


def test_numbers_wait_for_thirty_with_five_of_each():
    assert MIN_GRADED == 30 and MIN_EACH == 5
    short = calibrate(PAIRS[:29], (10, 5))
    assert (short.graded, short.ready, short.caught, short.corrected) == (29, False, None, None)
    few_bad = calibrate([(True, True)] * 26 + [(False, False)] * 4, (10, 5))
    assert (few_bad.graded, few_bad.ready, few_bad.caught) == (30, False, None)
    no_run = calibrate(PAIRS, (0, 0))  # 판정받은 초안이 없는 시험(옛 자) — 두 비율만
    assert no_run.ready and no_run.caught == pytest.approx(0.7) and no_run.corrected is None


# ── 판 ⑪ 지난 상담 줄 글 ─────────────────────────────────────────────────
def _store(*runs):
    """결과 줄들(오래된 것부터) — ``(번호, judge, past)``. judge 가 ``None`` 이면 옛 줄(칸 없음)."""
    rows = []
    for run_id, judge, past in runs:
        row = {"id": run_id, "status": evals.DONE, "code": None, "actor_id": None, "started_at": "2026-11-16T00:00:00",
               "heartbeat_at": "2026-11-16T00:10:00", "finished_at": "2026-11-16T00:10:00", "model": None,
               "cost_usd": "0", "target_pct": 0, "past": past, "risk": {"total": 0, "done": 0, "bad": 0}, "failures": []}
        if judge is not None:
            row["judge"] = judge
        rows.append(row)
    db_session.merge(SystemSetting(setting_key=evals.RESULTS_KEY, setting_value={"runs": rows}))
    db_session.commit()


def _marks(run_id, items):
    """채점 줄들 — ``(채점 코드, 사장님 답)``(답이 ``None`` 이면 채점 전)."""
    start = db_session.query(AiStaffEvalMark).count()
    for n, (code, answer) in enumerate(items, start=start + 1):
        db_session.add(AiStaffEvalMark(run_id=run_id, turn_id=n, brand="LAHOM", draft="합성 초안", judge_code=code,
                                       owner_answer=answer, graded_by=1 if answer else None,
                                       graded_at=now_utc_naive() if answer else None))
    db_session.commit()


def _past_text(world):
    return evals_view.eval_view(db_session, viewer_of(world.admin), now=NOW, erp=False)["rows"][0]["text"]


PAST = {"total": 12, "done": 12, "passed": 5, "right_handoff": 2}


def test_the_row_shows_the_count_then_the_calibrated_numbers(world):
    _store((1, evals.JUDGE_VERSION, PAST), (2, evals.JUDGE_VERSION, PAST))
    _marks(1, [("pass", "ok"), ("copied", "ok"), ("judge_unknown", "bad"), ("pass", "ok")])  # = PAIRS[:3] + 판정 못 받음
    head = "보내도 되는 답 50% (10차례 · 옳은 넘김 2 · 지난번 50%)"
    assert _past_text(world) == head + " · 사장님 채점 3개"  # 판정 못 받은 초안은 견주지 않는다
    codes = {(True, True): "pass", (True, False): "fail_conflict", (False, False): "fail_unanswered",
             (False, True): "copied"}
    _marks(1, [(codes[pair], "ok" if pair[0] else "bad") for pair in PAIRS[3:]])
    _marks(2, [("pass", None)] * 4 + [("copied", None)] + [("fail_promise", None)] * 3 + [("number_not_allowed", None)] * 2
           + [("handoff", None), ("right_handoff", None), ("judge_unknown", None)])  # 보이는 시험 — 초안 10 · 통과 5
    cal = calibrate(PAIRS, (10, 5))
    assert cal.corrected == pytest.approx(0.4)
    spread = f"({round(cal.low * 100)}~{round(cal.high * 100)}%)"
    assert _past_text(world) == (head + " · 사장님 채점 30개 · 안 되는 답 70% 잡음 · 되는 답 80% 통과 · "
                                 f"사장님 기준 초안 통과 40%{spread}")


def test_handoff_grades_count_agreement_with_the_always_human_rule(world):
    _store((1, evals.JUDGE_VERSION, PAST))
    _marks(1, [("right_handoff", "handoff_right"), ("handoff", "should_answer"), ("right_handoff", "should_answer"),
               ("refused", "handoff_right"), ("handoff", None)])
    assert _past_text(world).endswith(" · 넘김 4개 가운데 2개 사장님과 같음")  # 채점 전 줄은 세지 않는다


def test_a_judge_that_disagrees_too_much_is_not_corrected(world):
    _store((1, evals.JUDGE_VERSION, PAST))
    flipped = [("fail_conflict", "ok")] * 20 + [("pass", "bad")] * 10  # 민감도 0 · 특이도 0
    _marks(1, flipped)
    assert _past_text(world).endswith(" · 사장님 채점 30개 · 안 되는 답 0% 잡음 · 되는 답 0% 통과 · "
                                      "채점이 사장님과 너무 달라 바로잡지 못해요")


def test_old_rows_keep_their_words_and_are_not_compared_across_judges(world):
    old = {"total": 4, "done": 4, "passed": 1, "partial": 1}  # 옛 줄 — '같은 뜻' 자 · 덜 말함 칸
    _store((1, None, old))
    assert _past_text(world) == "AI 답이 직원 답과 같은 뜻 25% (4차례 · 옳은 넘김 0)"
    _store((1, None, old), (2, evals.JUDGE_VERSION, PAST))
    assert _past_text(world) == "보내도 되는 답 50% (10차례 · 옳은 넘김 2)"  # 옛 자 25% 와 견주지 않는다
    _store((1, None, old), (2, None, {"total": 4, "done": 4, "passed": 2}))
    assert _past_text(world) == "AI 답이 직원 답과 같은 뜻 50% (4차례 · 옳은 넘김 0 · 지난번 25%)"  # 옛 자끼리는 그대로
    _marks(2, [("pass", "ok")] * 25 + [("fail_conflict", "bad")] * 5)
    assert _past_text(world).endswith(" · 사장님 채점 30개 · 안 되는 답 100% 잡음 · 되는 답 100% 통과")  # 옛 시험은 안 바로잡음
