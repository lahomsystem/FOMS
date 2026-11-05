"""채널톡 안 작은 창(WAM)이 부르는 앱 함수 — [보내기] · [수정하기]를 데스크 안에서(설계서 17.2.2 · 사장님 11-05).

함수 받는 곳(:mod:`foms.api.channel.channel_functions`)이 서명 · 채널 · 부른 상담원을 본 뒤 이 모듈의 :func:`handle` 만 부른다.
누른 사람은 서명된 ``context.caller`` 의 상담원 번호뿐이다 — ``params`` 에 실린 값으로 사람을 정하지 않는다.

단계 S1(시험 장치): ``cs.draft.ping`` 하나 — 작은 창이 서명 함수를 부를 수 있는지 · 부른 상담원이 실려 오는지만 답한다(글 ·
손님 정보 없음). 보내기 · 고치기 함수는 S2 · S3 에서 더한다.

응답 꼴은 채널톡 앱 함수 약속 그대로: 성공 ``{"result": ...}``, 예상한 실패 ``{"error": {"code", "type", "message"}}``.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = ["FUNCTION_SCHEMAS", "METHODS", "handle"]

PING = "cs.draft.ping"
#: 채널톡이 함수 목록을 물을 때(``extension.core.function.getFunctions``) 답하는 꼴(이름 · 입력 틀).
FUNCTION_SCHEMAS: tuple[dict[str, Any], ...] = (
    {"name": PING, "description": "AI 초안 작은 창 연결 확인",
     "inputSchema": {"type": "object", "properties": {"turn": {"type": "integer"}}}},
)
METHODS = frozenset(schema["name"] for schema in FUNCTION_SCHEMAS)
_TURN_MAX = 2 ** 31 - 1


def _error(code: int, kind: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "type": kind, "message": message}}


def _turn(params: Any) -> Optional[int]:
    """``params.turn`` — 양의 정수만(그 밖은 ``None``)."""
    value = params.get("turn") if isinstance(params, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if 0 < number <= _TURN_MAX else None


def handle(method: str, params: Any, manager_id: Optional[str]) -> dict[str, Any]:
    """서명을 지난 함수 한 번 — 상담원이 부른 것만 받는다(봇 · 손님 · 빈 caller 는 권한 없음)."""
    if not manager_id:
        return _error(4, "unauthorized", "상담원만 쓸 수 있어요.")
    if method == PING:
        return {"result": {"ok": True, "turn": _turn(params)}}
    return _error(-32601, "methodNotFound", "없는 함수예요.")
