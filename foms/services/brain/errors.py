"""master brain 오류 — 부르는 쪽이 ``code`` 로 가른다. 글에는 키 · 칸 이름 · 까닭만 싣고 항목 글은 싣지 않는다."""

from __future__ import annotations

from typing import Sequence

MAX_PROBLEMS = 30


class BrainError(RuntimeError):
    """brain 쓰기를 진행할 수 없다."""

    code = "BRAIN_ERROR"


class BrainShapeError(BrainError):
    """꼴이 틀렸다(값 목록 · 길이 · 날짜 · 유형과 층 · 지식 문서 칸). ``problems`` 는 자리 · 까닭만."""

    code = "BRAIN_SHAPE"

    def __init__(self, problems: Sequence[str]) -> None:
        """문제 목록을 상한까지만 싣는다."""
        shown = list(problems[:MAX_PROBLEMS])
        if len(problems) > MAX_PROBLEMS:
            shown.append(f"… 그 밖에 {len(problems) - MAX_PROBLEMS}건")
        super().__init__("; ".join(shown))
        self.problems: tuple[str, ...] = tuple(shown)


class BrainTargetError(BrainError):
    """대상이 맞지 않다(없는 항목 · 이미 있는 키 · 허용 밖 링크 짝 · 정체 칸이 다름 · 열린 제안 아님)."""

    code = "BRAIN_TARGET"


class BrainConflictError(BrainError):
    """제안의 기준 판과 지금 판이 다르다 — 제안을 만든 뒤 항목이 바뀌었다(7.5 '기준 판 비교')."""

    code = "BRAIN_BASE_CHANGED"

    def __init__(self, current_version: int | None) -> None:
        """지금 판(없으면 ``None``)을 싣는다."""
        super().__init__(f"기준 판이 다르다 — 지금 판 {current_version}")
        self.current_version = current_version


class BrainPermissionError(BrainError):
    """반영할 권한이 없다(사람 아님 · 꺼진 계정 · 바깥 역할 · 사장님 몫 · 층 승인자 아님)."""

    code = "BRAIN_FORBIDDEN"


class BrainGateError(BrainError):
    """에이전트 제안이 글 관문(개인정보 · 한자 · 숫자)을 넘지 못했다 — 제안함에 넣지 않는다."""

    code = "BRAIN_GATE"

    def __init__(self, failed: Sequence[str]) -> None:
        """떨어진 관문 이름만 싣는다."""
        super().__init__("관문 미통과: " + ", ".join(failed))
        self.failed: tuple[str, ...] = tuple(failed)
