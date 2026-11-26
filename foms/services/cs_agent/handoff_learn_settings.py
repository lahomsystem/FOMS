"""관리 패널 '넘긴 상담 배우기 → 회사 지식' 칸 묶음 — 직원이 직접 한 답을 날마다 배운다(사장님 11-11 · 11-19).

칸은 :mod:`.settings` 의 ``FIELDS`` 끝에 붙는다(같은 읽기 · 쓰기 · 수정 기록 길 — 말 끝남 판단 :mod:`.turn_end_settings` 와 같은
꼴). 처음 값은 **끔**이다. 켜면 밤마다(:mod:`.handoff_learning`) 지난 7일 넘긴 상담 가운데 직원이 직접 답한 사례를 **새 것부터
남김없이** 읽어(한 번에 '한 번에 읽는 사례 수'만 — 밤 창 안에서 여러 번) 회사 지식 제안(사실 · 정책 · 상황 · 제작 조건 · 비슷한
말 · 잇기)을 만든다. '배운 것 바로 반영'이 꺼져 있으면 '승인 대기' 카드로만 들어가고, 켜면 관문을 지난 안을 그 자리에서 반영한다
(사장님 11-19 — 지금 지식과 다른 말은 덮어쓰지 않고 승인 대기 ③ 에 엇갈림 카드로 모은다). 비상 정지 · 초안 끔 · 학습 돈 상한은
이 칸과 상관없이 막는다(:func:`.learning_brain.off_reason`). 모델은 주간 고침 안 모델 칸을 같이 쓴다.
"""

from __future__ import annotations

from foms.services.cs_agent.settings_field import KIND_BOOL, KIND_INT, Field

__all__ = ["AUTO_FIELD", "CACHE_FIELD", "CASES_FIELD", "EDIT_LEARN_FIELD", "GROUP_HANDOFF_LEARN", "HANDOFF_LEARN_FIELD",
           "HANDOFF_LEARN_FIELDS", "LINK_CALLS_FIELD", "LINK_FIELD"]

GROUP_HANDOFF_LEARN = "넘긴 상담 배우기 → 회사 지식 제안"
HANDOFF_LEARN_FIELD, CASES_FIELD = "handoff_learn_enabled", "handoff_learn_cases"
EDIT_LEARN_FIELD = "edit_learn_enabled"
AUTO_FIELD = "learn_auto_enabled"
#: 밤 배우기 지식 목록 아껴 보내기(설계 글 2026-11-26 6절 — :mod:`.handoff_learning_cache`). 처음 끔 — 끄면 요청 꼴이 예전 그대로.
CACHE_FIELD = "handoff_learn_cache_enabled"
#: 밤 배우기 끝에 지식 이어 붙이기(설계 글 2026-11-26 7.1 · 7.2 — :mod:`.handoff_learning_link`). 처음 끔 — 끄면 모델을 부르지
#: 않는다. 한 밤 부르기 횟수 상한(한 번에 지식 20개까지).
LINK_FIELD, LINK_CALLS_FIELD = "handoff_learn_link_enabled", "handoff_learn_link_calls"

HANDOFF_LEARN_FIELDS: tuple[Field, ...] = (
    Field(HANDOFF_LEARN_FIELD, "넘긴 상담 배우기", KIND_BOOL, False, GROUP_HANDOFF_LEARN,
          help="밤마다 AI 가 몰라서 직원에게 넘긴 상담 가운데 직원이 직접 답한 것을 그 상담 전체 대화 · 손님 사진 설명과 같이 "
               "읽고 회사 지식(사실 · 정책 · 상황 · 제작 조건 · 손님이 쓰는 다른 이름)을 만들어요. 새 상담부터 남김없이 읽어요"
               "(불만 · 주문 조회 · 할인 · 환불 · 사람만 말하는 금액은 안 배워요)"),
    Field(CASES_FIELD, "한 번에 읽는 사례 수", KIND_INT, 20, GROUP_HANDOFF_LEARN, low=2, high=40, unit="개",
          help="한 번 부를 때 읽는 사례 수예요. 밤 창 안에서 남은 사례가 없을 때까지 여러 번 불러요. 한 번 읽은 사례는 다시 안 "
               "읽어요. 줄이면 사례마다 전체 대화를 더 길게 읽어요"),
    Field(EDIT_LEARN_FIELD, "초안이 나간 상담도 배우기", KIND_BOOL, False, GROUP_HANDOFF_LEARN,
          help="켜면 같은 밤에 AI 초안을 직원이 고쳐 보냈거나, 초안을 안 쓰고 직접 답한 상담도 읽어요(전체 대화 · AI 초안 · "
               "직원 답 · 적어 둔 고친 까닭). '넘긴 상담 배우기'가 켜져 있어야 돌아요"),
    Field(AUTO_FIELD, "배운 것 바로 반영", KIND_BOOL, False, GROUP_HANDOFF_LEARN,
          help="켜면 배운 것을 승인 없이 그 밤에 회사 지식에 넣어요. 넣은 것은 회사 지식 'AI 가 배운 것'에서 보고 고치거나 "
               "지울 수 있어요. 지금 지식과 다른 말은 덮어쓰지 않고 '승인 대기'에 따로 모아요. 한 손님에게만 말한 금액 · "
               "날짜와 개인정보는 안 넣어요"),
    Field(CACHE_FIELD, "밤 배우기 지식 목록 아껴 보내기", KIND_BOOL, False, GROUP_HANDOFF_LEARN,
          help="켜면 회사 지식 목록을 그 밤 첫 번에 맡겨 두고, 한 시간 안에 다시 부르면 맡겨 둔 목록을 훨씬 싼 값으로 다시 써요. "
               "그 밤에 새로 들어가거나 바뀐 지식은 따로 붙여 보내요. 맡기는 첫 번(모델마다 한 번)은 보통의 2배 값이에요"),
    Field(LINK_FIELD, "밤 배우기 끝에 지식 이어 붙이기", KIND_BOOL, False, GROUP_HANDOFF_LEARN,
          help="켜면 밤 배우기가 끝난 뒤 그 밤 새로 배우거나 고친 지식을 이미 있는 회사 지식에 이어요. 글에 상대 이름이 그대로 "
               "있고 가리키는 지식이 하나뿐인 뻔한 연결은 '배운 것 바로 반영'이 켜져 있을 때 바로 넣고('AI 가 배운 것'에서 지울 "
               "수 있어요), 나머지는 '승인 대기'에 올려요. 금액 · 수량이 걸린 연결 · '같이 안 돼요' 연결 · 두 지식 합치기는 늘 "
               "여쭤요"),
    Field(LINK_CALLS_FIELD, "이어 붙이기 한 밤 횟수", KIND_INT, 3, GROUP_HANDOFF_LEARN, low=1, high=10, unit="번",
          help="한 밤에 이어 붙이기를 부르는 횟수 상한이에요. 한 번에 지식 20개까지 봐요. 학습 돈 상한 안에서만 불러요"),
)
