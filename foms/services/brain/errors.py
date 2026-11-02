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


class BrainRejectedError(BrainTargetError):
    """같은 항목 · 같은 동작 · 같은 새 값의 제안이 이미 거절됐다 — 다시 올리지 않는다(7.5 거절 까닭 칩)."""

    code = "BRAIN_REJECTED_BEFORE"

    def __init__(self, reject_code: str | None) -> None:
        """앞 거절의 까닭 칩을 싣는다."""
        super().__init__(f"같은 제안이 이미 거절됐다 — 까닭 {reject_code}")
        self.reject_code = reject_code


class BrainOpenProposalError(BrainTargetError):
    """그 항목에 열린 제안이 있다 — '아직 맞음'은 제안함에서 그 제안을 먼저 결정한 뒤에."""

    code = "BRAIN_OPEN_PROPOSAL"


class BrainConfirmError(BrainError):
    """등급 B 제안은 핵심 값 하나를 직접 확인해야 넣는다(7.5 '등급 B 는 핵심 값 하나를 직접 확인'). ``field`` 는 칸 이름만."""

    code = "BRAIN_CONFIRM"

    def __init__(self, field: str | None) -> None:
        """확인할 칸 이름을 싣는다."""
        super().__init__(f"핵심 값 확인이 필요하다: {field}")
        self.field = field


class BrainRollbackBlockedError(BrainError):
    """판 되돌리기를 할 수 없다 — 뒤 판이 같은 항목 · 링크를 또 고쳤다(항목마다 되돌리기로). ``count`` 는 막힌 수만."""

    code = "BRAIN_ROLLBACK_BLOCKED"

    def __init__(self, count: int) -> None:
        """막힌 항목 · 링크 수를 싣는다."""
        super().__init__(f"뒤 판이 같은 항목을 고쳤다 — {count}개")
        self.count = count


class BrainGateError(BrainError):
    """에이전트 제안이 글 관문(개인정보 · 한자 · 숫자)을 넘지 못했다 — 제안함에 넣지 않는다."""

    code = "BRAIN_GATE"

    def __init__(self, failed: Sequence[str]) -> None:
        """떨어진 관문 이름만 싣는다."""
        super().__init__("관문 미통과: " + ", ".join(failed))
        self.failed: tuple[str, ...] = tuple(failed)


class BrainLinkLimitError(BrainTargetError):
    """연결 개수 상한을 넘는다(7.7 · D105 — 허용 짝의 최대). ``kind`` · ``limit`` 는 종류 이름 · 수만."""

    code = "BRAIN_LINK_LIMIT"

    def __init__(self, kind: str, limit: int) -> None:
        """링크 종류와 상한을 싣는다."""
        super().__init__(f"연결 개수 상한을 넘는다 — {kind} 최대 {limit}개")
        self.kind = kind
        self.limit = limit


class BrainLinkRuleError(BrainTargetError):
    """링크 제약에 걸렸다(7.8 다음 1 · 14 — 근거 종류와 맞지 않는 끝 · 같은 짝 필요 + 제외 · 고리). ``rule`` 은 규칙 이름만."""

    code = "BRAIN_LINK_RULE"

    def __init__(self, rule: str, message: str) -> None:
        """규칙 이름(``basis_end`` · ``opposed`` · ``cycle``)과 키 · 종류만 든 글."""
        super().__init__(message)
        self.rule = rule


class BrainExternalRefError(BrainTargetError):
    """가리킨 바깥 정본 자리(``calc:`` · ``setting:``)가 없거나 지금 확인할 수 없다(7.7 · D105). ``refs`` 는 키만."""

    code = "BRAIN_EXTERNAL_MISSING"

    def __init__(self, refs: Sequence[str], *, unavailable: bool = False) -> None:
        """없는 키 목록(또는 확인 못 함)을 싣는다."""
        shown = list(refs[:MAX_PROBLEMS])
        reason = "확인할 수 없다" if unavailable else "없다"
        super().__init__(f"바깥 정본 자리가 {reason}: {', '.join(shown)}")
        self.refs: tuple[str, ...] = tuple(shown)
        self.unavailable = unavailable
