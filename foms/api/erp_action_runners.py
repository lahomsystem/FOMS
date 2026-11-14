"""ERP 할 일 실행기 — api 층 기능을 부르는 것(설계서 2026-11-14-foms-graft 3.1 · 3.11 · 3.12 ``RUNNERS``).

층 방향 래칫 때문에 services 는 api 를 import 할 수 없다. 그래서 api 층에 있는 본체(지금은 AS 접수
``register_as_from_payload``)를 부르는 실행기는 여기 두고, 표 :data:`RUNNERS` 는 services 실행기 표에 이것을 더한 것이다.
화면의 승인 API(:mod:`foms.api.erp_actions`)가 이 표를 쓴다(채널톡 작은 창은 services 표만 쓴다).

본체는 요청 본문 · 사용자 번호를 받아 Flask 답을 돌려준다. :func:`outcome_from_response` 가 그 답의 상태 코드와
``success`` · ``code`` · ``message`` 를 실행 결과로 옮긴다 — 2xx 면 실행, 5xx 면 실패, 그 밖(4xx)은 주문이 바뀌지 않은
것이므로 **막힘**(제안은 ``open`` 에 남고 409 ``ACTION_PRECONDITION`` + 그 말). 본체는 스스로 커밋한다(두 걸음 승인의 까닭).
본체는 요청 맥락 안에서 돈다(요청 세션 ``get_db()`` · 머리글) — 승인 API 안에서만 부른다. 뒤 일감(T14)이 여기에 실행기 셋을
더한다.
"""

from __future__ import annotations

from typing import Any

from foms.api.cs.as_orders import register_as_from_payload
from foms.services.erp_actions import preview
from foms.services.erp_actions.registry import message
from foms.services.erp_actions.runners import SERVICE_RUNNERS, RunOutcome, RunRequest, Runner
from models import Order

__all__ = ["RUNNERS", "outcome_from_response", "run_register_as"]


def outcome_from_response(response: Any, *, done_message: str) -> RunOutcome:
    """본체가 돌려준 Flask 답(응답 또는 ``(응답, 상태)``)을 실행 결과로 옮긴다.

    Args:
        response: 본체의 반환값.
        done_message: 2xx 인데 답에 말이 없을 때 쓸 화면 말.

    Returns:
        2xx 이고 ``success`` 가 거짓이 아니면 실행 · 5xx 면 실패(``ACTION_FAILED`` — 예외 글을 옮기지 않는다) · 그 밖은 막힘.
    """
    resp, status = (response[0], int(response[1])) if isinstance(response, tuple) else (response, response.status_code)
    payload = resp.get_json(silent=True) if hasattr(resp, "get_json") else None
    payload = payload if isinstance(payload, dict) else {}
    if 200 <= status < 300 and payload.get("success") is not False:
        return RunOutcome.executed(str(payload.get("message") or done_message), http_status=status)
    if status >= 500:
        return RunOutcome.failed(http_status=status)
    words = payload.get("message") or payload.get("error")
    text = words if isinstance(words, str) and words else message("ACTION_PRECONDITION")
    return RunOutcome.blocked(text, code=str(payload.get("code") or "ACTION_PRECONDITION"), http_status=status)


def run_register_as(session: Any, req: RunRequest) -> RunOutcome:
    """AS 접수 — 접수 API 와 같은 본체(``register_as_from_payload``)를 같은 본문 꼴로 부른다.

    출처는 접수 화면 칸 ``source_screen = 'erp_action:<제안 번호>'``(접수 이벤트에 남는다), 같은 제안 · 같은 값의 다시 실행은
    REV-00 영수증 열쇠로 두 번 접수하지 않는다. 열린 AS 가 있으면 막는 조건이 먼저 거른다(열린 건 다시 접수는 접수 글을 덮는다).
    """
    order = session.get(Order, req.order_id)
    problem = preview.check(req.action, order, req.params)
    if problem:
        session.rollback()
        return RunOutcome.blocked(problem)
    data = {"as_content": req.params.get("as_content"), "source_screen": req.source,
            "idempotency_key": req.idempotency_key()}
    return outcome_from_response(register_as_from_payload(int(order.id), data, req.actor_id),
                                 done_message="AS 접수를 했어요.")


#: 실행기 표 — services 표 + api 층 실행기(화면 승인 API 가 쓴다).
RUNNERS: dict[str, Runner] = {**SERVICE_RUNNERS, "register_as": run_register_as}
