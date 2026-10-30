"""두뇌 재료의 '비슷한 지난 상담' 칸 — 꼴 맞추기 · 글 덩어리 만들기(순수 함수, 네트워크 · DB 없음).

설계서 17.2 · 17.6 L0 · 플랜 C10-4. 고르기(같은 브랜드 · 끝난 꼴 · 비슷함)는 :mod:`.case_memory` 가 하고, 여기서는
:class:`.brain_prompt.DraftRequest` 의 ``cases`` 칸 꼴과 :func:`.brain_prompt.task_text` 의 바뀌는 부분(마지막 캐시 표시 뒤)에
들어갈 줄만 만든다 — :mod:`.brain_prompt` 500줄 상한으로 나눴다.

- 사례 하나 = (가린 손님 질문, 사람이 보낸 가린 답). 두 글 모두 모델에 가기 전에 가림 검사(:func:`.masking.require_masked`)를
  한 번 더 지난다 — 가림이 고장 나도 남의 정보가 모델에 닿지 않게(꺼지면 :class:`.masking.MaskLeak`).
- 머리말이 쓰임을 못 박는다: 말투 · 순서만 참고, 다른 손님의 날짜 · 금액 · 이름은 쓰지 않는다. 사례 글의 금액 · 날짜는 허용
  목록에 넣지 않으므로(:mod:`.drafting` — 승인 지식 글만) 새 초안에 옮겨 쓰면 보내기 전 검사가 막는다.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from foms.services.cs_agent.masking import require_masked

__all__ = ["CASES_HEAD", "MAX_CASES", "case_lines", "case_pairs"]

CASES_HEAD = "비슷한 지난 상담(사람이 보낸 답 — 말투 · 순서만 참고, 다른 손님의 날짜 · 금액 · 이름은 쓰지 않는다):"
#: 한 요청에 싣는 사례 상한(설계서 17.2 '비슷한 사례 3~5').
MAX_CASES = 5


def case_pairs(value: Any) -> tuple[tuple[str, str], ...]:
    """사례 목록 → (질문, 답) 짝 튜플(:data:`MAX_CASES` 개까지). 꼴이 틀리면 ``ValueError`` — 칸 이름만 싣는다."""
    if isinstance(value, (str, bytes)):
        raise ValueError("cases 는 (질문, 답) 짝 목록이다")
    pairs = tuple(tuple(pair) for pair in value)
    if len(pairs) > MAX_CASES or any(len(p) != 2 or not all(isinstance(t, str) for t in p) for p in pairs):
        raise ValueError(f"cases 는 (질문, 답) 글 짝 {MAX_CASES}개까지다")
    return pairs  # type: ignore[return-value]


def case_lines(cases: Sequence[tuple[str, str]], block: Callable[[str, str], list[str]]) -> list[str]:
    """사례 칸 줄 — 머리말 + 사례마다 손님 글 · 사람 답(``block`` 이 다음 줄을 들여 써 표시를 흉내 내지 못한다). 없으면 빈 목록.

    Raises:
        MaskLeak: 사례 글에 가림 검사가 0 이 아닌 꼴이 남았다(모델을 부르지 않는다 — 칸별 숫자만).
    """
    if not cases:
        return []
    lines = [CASES_HEAD]
    for number, (question, answer) in enumerate(cases, start=1):
        lines += block(f"- 사례 {number} 손님 글:", require_masked(question.strip()))
        lines += block(f"  사례 {number} 사람 답:", require_masked(answer.strip()))
    return lines
