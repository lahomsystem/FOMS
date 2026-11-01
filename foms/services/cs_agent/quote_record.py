"""견적 계산 기록 — 그 차례 계산기 값(상태 · 두뇌 줄 · 허용 금액 줄)을 차례 줄 ``quote_lines`` 칸에 남기고 다시 읽는다.

플랜 C10-6 · 검수 R17-1 · R17-2. 초안 차례가 견적 계산을 넣었으면 그 값을 ``CsAgentTurn.quote_lines``(csagent_03 — C10-6 몫으로
비워 둔 칸)에 한 번 남긴다. [보내기] 다시 검사(:mod:`.send_flow`) · '고칠 말' 다시 쓰기(:mod:`.rewrite`) · 다시 올리기
(:mod:`.drafting`)는 이 값을 허용 목록에 더한다 — **상태가 '계산됨 · 확인됨'(``ok``)일 때만**(확인 필요 · 묻기 · 사람에게면
더하지 않는다). 글은 코드가 만든 계산기 줄뿐이다(손님 글 없음 — 공간 이름 · 문 방식은 정한 값, 제품 이름은 계산기 설정).
무거운 import 가 없다(보내기 길이 web 에서 읽는다).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "RECORD_VERSION", "STATUS_ASK", "STATUS_CHECK", "STATUS_HUMAN", "STATUS_NOT_QUOTE", "STATUS_OK", "STATUSES",
    "allowed_from", "lines_from", "record_value",
]

RECORD_VERSION = 1
STATUS_OK, STATUS_CHECK, STATUS_ASK, STATUS_HUMAN = "ok", "needs_check", "ask", "human"
STATUS_NOT_QUOTE = "not_quote"
STATUSES: tuple[str, ...] = (STATUS_OK, STATUS_CHECK, STATUS_ASK, STATUS_HUMAN, STATUS_NOT_QUOTE)
_MAX_LINES = 40


def _texts(value: Any) -> Optional[list[str]]:
    """글 목록(꼴이 틀리면 ``None``)."""
    if not isinstance(value, list) or len(value) > _MAX_LINES or not all(isinstance(v, str) for v in value):
        return None
    return list(value)


def record_value(status: str, *, lines: Sequence[str] = (), allowed: Sequence[str] = (),
                 code: Optional[str] = None) -> dict[str, Any]:
    """차례 줄에 남길 값(JSON 꼴). 모르는 상태면 ``ValueError``."""
    if status not in STATUSES:
        raise ValueError("모르는 견적 상태")
    return {"v": RECORD_VERSION, "status": status, "lines": list(lines)[:_MAX_LINES],
            "allowed": list(allowed)[:_MAX_LINES], "code": code}


def _ok(value: Any) -> Optional[Mapping[str, Any]]:
    """상태가 '계산됨 · 확인됨'인 기록(아니면 ``None``)."""
    if not isinstance(value, Mapping) or value.get("v") != RECORD_VERSION or value.get("status") != STATUS_OK:
        return None
    return value


def allowed_from(value: Any) -> tuple[str, ...]:
    """다시 검사가 허용 목록에 더할 계산기 값 줄 — '계산됨 · 확인됨'일 때만, 꼴이 틀리면 빈 묶음."""
    record = _ok(value)
    texts = _texts(record.get("allowed")) if record is not None else None
    return tuple(texts or ())


def lines_from(value: Any) -> tuple[str, ...]:
    """두뇌 재료로 다시 쓸 계산 결과 줄('고칠 말' 다시 쓰기) — '계산됨 · 확인됨'일 때만."""
    record = _ok(value)
    texts = _texts(record.get("lines")) if record is not None else None
    return tuple(texts or ())
