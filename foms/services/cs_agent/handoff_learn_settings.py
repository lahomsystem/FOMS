"""관리 패널 '넘긴 상담 배우기 → 회사 지식 제안' 칸 묶음 — AI 가 사람에게 넘긴 상담에서 직원이 직접 한 답을 배운다(사장님 11-11).

칸은 :mod:`.settings` 의 ``FIELDS`` 끝에 붙는다(같은 읽기 · 쓰기 · 수정 기록 길 — 말 끝남 판단 :mod:`.turn_end_settings` 와 같은
꼴). 처음 값은 **끔**이다. 켜면 밤마다 한 번(:mod:`.handoff_learning`) 지난 7일 넘긴 상담 가운데 직원이 직접 답한 사례를 읽어
회사 지식 제안(사실 · 정책 새로 만들기 · 고치기)을 '승인 대기' 카드로만 넣는다 — 승인 전엔 아무것도 바뀌지 않는다. 비상 정지 ·
초안 끔 · 학습 돈 상한은 이 칸과 상관없이 막는다(:func:`.learning_brain.off_reason`). 모델은 주간 고침 안 모델 칸을 같이 쓴다.
"""

from __future__ import annotations

from foms.services.cs_agent.settings_field import KIND_BOOL, KIND_INT, Field

__all__ = ["CASES_FIELD", "GROUP_HANDOFF_LEARN", "HANDOFF_LEARN_FIELD", "HANDOFF_LEARN_FIELDS"]

GROUP_HANDOFF_LEARN = "넘긴 상담 배우기 → 회사 지식 제안"
HANDOFF_LEARN_FIELD, CASES_FIELD = "handoff_learn_enabled", "handoff_learn_cases"

HANDOFF_LEARN_FIELDS: tuple[Field, ...] = (
    Field(HANDOFF_LEARN_FIELD, "넘긴 상담 배우기", KIND_BOOL, False, GROUP_HANDOFF_LEARN,
          help="밤마다 한 번, AI 가 몰라서 직원에게 넘긴 상담 가운데 직원이 직접 답한 것을 앞뒤 대화와 같이 읽고 회사 지식 "
               "제안(사실 · 정책)을 만들어요. 서로 다른 손님 둘 이상에게 같은 말을 한 것만 내요. '승인 대기' 카드로만 "
               "들어가고 승인 전엔 아무것도 안 바뀌어요(불만 · 주문 조회 · 할인 · 환불 · 사람만 말하는 금액은 안 배워요)"),
    Field(CASES_FIELD, "한 번에 읽는 사례 수", KIND_INT, 20, GROUP_HANDOFF_LEARN, low=2, high=40, unit="개",
          help="한 밤에 오래된 사례부터 이만큼만 읽어요. 남은 사례는 다음 밤에 읽고, 한 번 읽은 사례는 다시 안 읽어요. "
               "늘리면 학습 돈이 늘어요"),
)
