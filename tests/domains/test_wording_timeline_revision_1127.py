"""글 고침 둘(사장님 2026-11-27 질문 창 답 그대로) — 사람이 읽는 글만, 동작 · 받는 사람 · 보내는 길은 그대로.

1. 주문 기록(타임라인)의 '생산' → '제작'("낱말만 '제작'으로"): 보여 줄 때 만드는 글이라 옛 기록도 새 글로 보인다.
2. 영업 · 협력사 도면 수정 요청 알림 글을 공장 요청 글과 맞춘다("공장 요청 글과 맞추기"):
   "… 도면 수정 요청이 접수됐어요. 대상: 도면 2. 메모: …" — 번호 꼴은 공장 글의 ``numbers_label``, "메모" 낱말은 그대로.

이름은 모두 가짜(정하늘 · 김도면 · 박반장).
"""

from __future__ import annotations

import pytest

from foms.services.order_event_display import generate_change_description


# ── 1. 주문 기록 글 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("event_type", "text"),
    [
        ("PRODUCTION_STARTED", "제작을 시작했습니다"),
        ("PRODUCTION_COMPLETED", "제작을 완료 처리했습니다"),
        ("PRODUCTION_CANCELLED", "제작 시작을 취소했습니다 (제작 대기로 돌아감)"),
    ],
)
def test_timeline_production_lines_say_jejak(event_type, text):
    """세 줄 원문 — 말투 '~했습니다' 그대로, 낱말만 '제작'."""
    assert generate_change_description(event_type, "", "", "", {}) == text
    # 옛 기록(payload 에 무엇이 있든)도 보여 줄 때 같은 글이 된다 — 저장된 글을 읽지 않는다.
    assert generate_change_description(event_type, "", "", "", {"message": "생산을 시작했습니다"}) == text
