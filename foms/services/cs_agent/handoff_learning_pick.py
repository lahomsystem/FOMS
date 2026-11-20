"""넘긴 상담 배우기 — 이번에 읽을 묶음 · 학습 모델 고르기(사장님 11-20 '학습 모델은 난이도에 따라 알아서 배정').

:mod:`.handoff_learning` 이 부른다(500줄 상한으로 나눴다). 두뇌를 더 부르지 않고 사례의 겉모습만으로 가른다 — 고르는 데 돈이 들지
않고, 같은 사례는 늘 같은 갈래다.

- **갈래는 상담마다**: 한 상담의 사례는 전체 대화를 한 번만 싣고 서로 가리키므로(:func:`.handoff_learning._talks`) 갈라 보내지
  않는다. 그 상담의 사례 가운데 하나라도 어려우면 상담 전체가 어려운 갈래다.
- **어려운 사례**(:func:`hard_case`): 넘긴 까닭이 :data:`HARD_REASONS`(AI 초안을 직원이 고침 · 불만 · 할인 환불 · 사람이 정하는
  금액 · 보내기 전 검사 걸림 · 사진 · 제작 조건)이거나, AI 초안이 같이 있거나(초안과 직원 답을 견줘야 한다), 손님 글 + 직원 답이
  :data:`LONG_CHARS` 자를 넘는다. 상담에 손님 사진 설명이 있거나 사례가 :data:`BUSY_CHAT` 개 이상인 상담도 어렵다.
- **묶음**(:func:`pick_batch`): 가장 새 사례의 갈래를 이번 묶음 갈래로 하고, 새 것부터 그 갈래 상담의 사례만 담는다(어려운 묶음은
  작게 — 사례마다 더 깊이 읽게). 다른 갈래는 다음 바퀴가 읽는다.
- **모델**(:func:`model_for`): 어려운 묶음은 가장 센 모델(:data:`.brain_prompt.MODEL`), 쉬운 묶음은 한 단계 아래
  (:data:`.brain_prompt.MODEL_SONNET`). 생각 세기는 둘 다 보통 — 출력 상한 · 시간 상한 안에 끝나게(운영에서 여유를 본 뒤 올린다).
  값표(:data:`.brain_prompt.PRICES`)에 있는 모델만 쓴다.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from foms.services.cs_agent import brain_prompt as prompt

__all__ = ["BUSY_CHAT", "EASY", "HARD", "HARD_REASONS", "HARD_SHARE", "LONG_CHARS", "hard_case", "hard_chats",
           "model_for", "pick_batch"]

HARD, EASY = "hard", "easy"
#: 어려운 넘긴 까닭 — 고쳐 보냄 · 불만 · 할인 환불 · 사람이 정하는 금액 · 보내기 전 검사 걸림 · 사진 · 제작 조건.
HARD_REASONS: frozenset[str] = frozenset({"edited", "complaint", "discount_refund", "human_only_amount", "check_failed",
                                          "photo", "constraint"})
LONG_CHARS, BUSY_CHAT = 700, 3
#: 어려운 묶음 크기 = 쉬운 묶음(패널 '한 번에 읽는 사례 수')의 이 몫(적어도 :data:`HARD_MIN`).
HARD_SHARE, HARD_MIN = 3, 4
_MODELS = {HARD: (prompt.MODEL, "medium"), EASY: (prompt.MODEL_SONNET, "medium")}


def hard_case(case: dict[str, Any]) -> bool:
    """사례 하나가 어려운가(모듈 설명)."""
    if case.get("reason") in HARD_REASONS or case.get("draft"):
        return True
    return len(case.get("question") or "") + len(case.get("reply") or "") > LONG_CHARS


def hard_chats(cases: Sequence[dict[str, Any]], photo_chats: Iterable[str] = ()) -> set[str]:
    """어려운 갈래 상담 id — 어려운 사례가 있거나 · 손님 사진 설명이 있거나 · 사례가 많은 상담."""
    counts: dict[str, int] = {}
    hard = {str(chat) for chat in photo_chats}
    for case in cases:
        chat = str(case.get("chat_id") or "")
        counts[chat] = counts.get(chat, 0) + 1
        if hard_case(case):
            hard.add(chat)
    return hard | {chat for chat, n in counts.items() if n >= BUSY_CHAT}


def pick_batch(cases: Sequence[dict[str, Any]], photo_chats: Iterable[str], cap: int) -> tuple[str, list[dict[str, Any]]]:
    """(갈래, 이번 묶음) — ``cases`` 는 새 것부터. 가장 새 사례의 갈래만 담는다. 사례가 없으면 (쉬움, 빈 목록)."""
    if not cases:
        return EASY, []
    hard = hard_chats(cases, photo_chats)
    tier = HARD if str(cases[0].get("chat_id") or "") in hard else EASY
    size = max(HARD_MIN, cap // HARD_SHARE) if tier == HARD else cap
    mine = [case for case in cases if (str(case.get("chat_id") or "") in hard) == (tier == HARD)]
    return tier, mine[:size]


def model_for(tier: str) -> tuple[str, str]:
    """(모델 id, 생각 세기) — 어려운 묶음은 가장 센 모델, 쉬운 묶음은 한 단계 아래."""
    return _MODELS[HARD if tier == HARD else EASY]
