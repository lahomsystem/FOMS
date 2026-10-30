"""초안 차례 결과 숫자 — 15분 바퀴(:mod:`.drafting`)와 빠른 길(:mod:`.realtime`)이 같이 쓴다.

:mod:`.drafting` 이 500줄 상한에 닿아 따로 뒀다(drafting_read · drafting_post 와 같은 꼴). 숫자와 코드 이름만 담는다 —
상담 id · 글은 싣지 않는다.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

__all__ = ["DraftSummary"]


@dataclass
class DraftSummary:
    """한 바퀴 초안 결과 — 숫자만(상담 id · 글 없음). :meth:`counts` 가 바퀴 요약 JSON 의 ``drafting`` 칸이다."""

    candidates: int = 0  # 고른 상담
    too_old: int = 0  # 마지막 손님 글이 운영일 하루를 넘겨 고르지 않은 상담
    claimed: int = 0  # 이번에 선점한 차례(실패 줄 다시 집음 포함)
    already: int = 0  # 차례가 이미 있어 건너뜀(손님 글 하나에 초안 하나)
    brain_calls: int = 0
    cache_cold: int = 0  # 캐시 표시를 실은 두뇌 호출인데 캐시 읽기 0(앞부분 캐시가 안 먹는다 — R7-12)
    stored: int = 0
    posted: int = 0
    reposted: int = 0  # 보내기 실패로 다시 집어 저장된 초안을 다시 놓음(두뇌 안 부름 — R7-5)
    unverified: int = 0  # 올렸지만 비공개를 확인 못 함(ERROR 로그 · 스위치 바꿈 · 알림)
    unknown: int = 0  # 닿았는지 모름 — '올리는 중' 그대로
    not_allowed: int = 0  # 메모 스위치지만 운영 밖 시험 상담 허용 목록 밖이라 저장만
    failed: int = 0
    released: int = 0  # 시도를 세지 않고 돌려놓음(준비 안 됨 · 401 · 403 · 돈 상한 — R7-4)
    recovered: int = 0  # 오래 남은 선점 → 실패(다시 집음)
    stale_posting: int = 0  # 오래 남은 '올리는 중'(복구 단계 몫)
    superseded: int = 0  # 빠른 길: 손님이 더 써서 '지난 초안'으로 바꾼 차례
    staff_replied: int = 0  # 빠른 길: 직원이 먼저 공개 답을 해 닫은 차례
    asked_human: int = 0  # 빠른 길: 손님이 'AI 냐 사람이냐' 물어 두뇌 없이 사람에게 넘긴 차례
    skipped: dict[str, int] = field(default_factory=dict)  # 건너뜀 코드 → 수
    halted: dict[str, int] = field(default_factory=dict)  # 이번 바퀴를 멈춘 까닭(하나)

    def counts(self) -> dict[str, Any]:
        """JSON 한 덩어리 — 숫자와 코드 이름 → 숫자만."""
        return dataclasses.asdict(self)
