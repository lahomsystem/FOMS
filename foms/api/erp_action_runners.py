"""ERP 할 일 실행기 — api 층 기능을 부르는 것(설계서 2026-11-14-foms-graft 3.1 · 3.11 · 3.12 ``RUNNERS``).

층 방향 래칫 때문에 services 는 api 를 import 할 수 없다. 그래서 api 층에 있는 본체(AS 접수 ``register_as_from_payload`` ·
D206 에서 요청에서 떼어 낸 현재 작업 승인 · 도면 담당 지정 · 칸 고치기)를 부르는 실행기는 여기 두고, 표 :data:`RUNNERS` 는
services 실행기 표에 이것을 더한 것이다. 화면의 승인 API(:mod:`foms.api.erp_actions`)가 이 표를 쓴다(채널톡 작은 창은 services
표만 쓴다).

본체는 요청 본문 · 사용자 번호를 받아 Flask 답을 돌려준다. :func:`outcome_from_response` 가 그 답의 상태 코드와
``success`` · ``code`` · ``message`` 를 실행 결과로 옮긴다 — 2xx 면 실행, 5xx 면 실패, 그 밖(4xx)은 주문이 바뀌지 않은
것이므로 **막힘**(제안은 ``open`` 에 남고 409 ``ACTION_PRECONDITION`` + 그 말). 본체는 스스로 커밋한다(두 걸음 승인의 까닭).
본체는 요청 맥락 안에서 돈다(요청 세션 ``get_db()``) — 승인 API 안에서만 부른다.

D206 실행기 셋(단계 넘기기 · 도면 담당 맡기기 · 방문 옮기기(실측))은 지금 길과 같은 본체를 부르되, 지금 길이 본체 앞뒤에서
하던 일을 여기서 같게 한다:

- **앞 문지기**: 본체를 바로 부르면 그 길의 before_request 주문 정책 가드를 지나지 않는다 — 길 목록 JSON 의 정책으로 같은
  엔진(:func:`evaluate_policy`)을 가드가 꺼진 맥락에서도 다시 본다. 현재 작업 승인은 길의 역할 장식자(``role_required``)도.
- **줄 잠금 아래 검사**: 주문 줄을 잠그고 막는 조건(:func:`.preview.check`)을 다시 본 뒤 같은 트랜잭션에서 본체를 부른다.
- **본문**: 검사를 지난 넣을 값으로만 만든다 — 팀 · ``emergency_override`` · ``admin_override`` · 다른 칸 이름을 넘길 길이 없다.
- **요청 끝 되감기**: 지금 길은 요청이 끝나면 본체가 커밋하지 않은 것을 되감는다 — 본체가 돌아오면 같게 되감는다.
- 본체 안에서 요청 맥락을 따로 읽는 곳(감사 줄의 대리 로그인 표식 · 날짜 표 훅의 출처 ``request.endpoint``)은 승인 API
  요청의 값이 된다 — 출처는 ``erp_actions_api.erp_actions_approve``.
"""

from __future__ import annotations

from typing import Any, Optional

from foms.api.cs.as_orders import register_as_from_payload
from foms.api.drawing.erp_orders_draftsman import assign_draftsman_from_payload
from foms.api.orders.field_update import update_order_field_from_payload
from foms.api.quest import approve_quest_from_payload
from foms.services.erp_actions import preview
from foms.services.erp_actions.registry import message
from foms.services.erp_actions.runners import OUTCOME_EXECUTED, SERVICE_RUNNERS, RunOutcome, RunRequest, Runner
from foms.services.erp_display import clean_dict_like_name
from foms.services.orders.assignment import active_assignee_ids
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy, policy_id_for_endpoint
from foms.services.orders.quest_approve_authz import QUEST_APPROVE_ROLES
from foms.services.orders.revision import lock_order_row
from models import Order

__all__ = [
    "ASSIGN_DRAFTSMAN_ENDPOINT", "QUEST_APPROVE_ENDPOINT", "RUNNERS", "UPDATE_FIELD_ENDPOINT", "outcome_from_response",
    "run_advance_stage", "run_assign_draftsman", "run_move_measurement", "run_register_as",
]

#: 감싼 지금 길의 Flask 끝점 이름 — 길 목록 JSON(앞 문지기 정책)의 열쇠.
QUEST_APPROVE_ENDPOINT = "quest.api_order_quest_approve"
ASSIGN_DRAFTSMAN_ENDPOINT = "erp_orders_draftsman.api_order_assign_draftsman"
UPDATE_FIELD_ENDPOINT = "orders.update_order_field"
_ROLE_DENIED = "현재 작업 승인은 관리자 · 매니저 · 직원만 할 수 있어요."
_NOT_MOVED = "단계를 넘기지 못했어요 — 주문 화면에서 확인해 주세요."


def _response_parts(response: Any) -> tuple[dict[str, Any], int]:
    """본체 반환값(응답 또는 ``(응답, 상태)``) → (JSON 본문 dict — 아니면 빈 dict, 상태 코드)."""
    resp, status = (response[0], int(response[1])) if isinstance(response, tuple) else (response, response.status_code)
    payload = resp.get_json(silent=True) if hasattr(resp, "get_json") else None
    return (payload if isinstance(payload, dict) else {}), status


def outcome_from_response(response: Any, *, done_message: str) -> RunOutcome:
    """본체가 돌려준 Flask 답(응답 또는 ``(응답, 상태)``)을 실행 결과로 옮긴다.

    Args:
        response: 본체의 반환값.
        done_message: 2xx 인데 답에 말이 없을 때 쓸 화면 말.

    Returns:
        2xx 이고 ``success`` 가 거짓이 아니면 실행 · 5xx 면 실패(``ACTION_FAILED`` — 예외 글을 옮기지 않는다) · 그 밖은 막힘.
    """
    payload, status = _response_parts(response)
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


# ── D206 — 요청에서 떼어 낸 지금 처리기 본체 셋 ─────────────────────────────
def _guard_denied(session: Any, endpoint: str, actor: Any, order_id: int) -> Optional[str]:
    """감싼 길 앞 문지기(``enforce_order_mutation_policy``)와 같은 정책 판정 — 가드가 꺼진 맥락에서도 본다.

    Args:
        session: 요청 세션. endpoint: 감싼 길의 끝점 이름. actor: 승인한 사람. order_id: 대상 주문.

    Returns:
        막히면 정책 엔진의 까닭 글, 지나면 ``None``. 길 목록에 없거나 면제인 끝점은 가드의 기본 정책(``STAFF_MUTATION``).
    """
    policy = POLICY_REGISTRY.get(policy_id_for_endpoint(endpoint) or "", POLICY_REGISTRY["STAFF_MUTATION"])
    ids = active_assignee_ids(session, order_id, policy.assignment) if policy.assignment else None
    decision = evaluate_policy(policy, actor, active_assignee_ids=ids)
    return None if decision.allowed else decision.reason


def _locked_checked(session: Any, req: RunRequest, endpoint: str) -> tuple[Optional[Any], Optional[RunOutcome]]:
    """줄 잠금 → 앞 문지기 정책 → 막는 조건(잠금 아래). 막히면 (None, 막힘 결과) — 되감은 뒤."""
    order = lock_order_row(session, req.order_id)
    problem = _guard_denied(session, endpoint, req.actor, req.order_id) or preview.check(req.action, order, req.params)
    if problem:
        session.rollback()
        return None, RunOutcome.blocked(problem)
    return order, None


def _settled(session: Any, outcome: RunOutcome, **extra: Any) -> RunOutcome:
    """본체가 돌아온 뒤 — 지금 길의 요청 끝처럼 커밋하지 않은 것을 되감고, 실행됐으면 결과에 코드 · 수를 더한다."""
    session.rollback()
    if outcome.status != OUTCOME_EXECUTED:
        return outcome
    return RunOutcome.executed(outcome.message, **outcome.result, **extra)


def run_advance_stage(session: Any, req: RunRequest) -> RunOutcome:
    """단계 넘기기 — 현재 작업 승인 본체를 승인한 사람으로 부른다(본문은 영수증 열쇠뿐 — 팀 · 뚫기 칸 없음).

    막는 조건이 '승인을 다 받았는데 단계가 그대로'인 주문만 지나게 하므로 본체는 재전이 길을 탄다(승인 기록은 새로 쓰지
    않는다). 2xx 인데 단계가 넘어가지 않았으면(CS 완료 막힘 · 영수증 되풀이) 주문은 그대로라 막힘이다.
    """
    if getattr(req.actor, "role", None) not in QUEST_APPROVE_ROLES:  # 길의 role_required 와 같은 비교(정규화 없음)
        return RunOutcome.blocked(_ROLE_DENIED)
    order, stop = _locked_checked(session, req, QUEST_APPROVE_ENDPOINT)
    if stop is not None:
        return stop
    before = str(order.erp_stage_code or "")
    response = approve_quest_from_payload(int(order.id), {"idempotency_key": req.idempotency_key()}, req.actor_id,
                                          getattr(req.actor, "username", None))
    payload, _status = _response_parts(response)
    outcome = outcome_from_response(response, done_message="단계를 넘겼어요.")
    if outcome.status == OUTCOME_EXECUTED and not payload.get("auto_transitioned"):
        blocked = payload.get("completion_blocked")
        words = blocked.get("message") if isinstance(blocked, dict) else None
        outcome = RunOutcome.blocked(words if isinstance(words, str) and words else _NOT_MOVED, **outcome.result)
    after = str(order.erp_stage_code or "") if outcome.status == OUTCOME_EXECUTED else before  # 본체가 커밋한 단계
    return _settled(session, outcome, from_stage=before, to_stage=after)


def run_assign_draftsman(session: Any, req: RunRequest) -> RunOutcome:
    """도면 담당 맡기기 — 도면 담당 지정 본체를 승인한 사람으로 부른다(본문은 승인하는 사람이 고른 ``user_ids`` 뿐).

    아무도 고르지 않았으면 본체가 400(담당자를 선택해주세요) — 주문이 그대로라 막힘(409)이다.
    """
    order, stop = _locked_checked(session, req, ASSIGN_DRAFTSMAN_ENDPOINT)
    if stop is not None:
        return stop
    user_ids = [int(uid) for uid in req.params.get("user_ids") or []]
    response = assign_draftsman_from_payload(int(order.id), {"user_ids": user_ids}, req.actor_id)
    return _settled(session, outcome_from_response(response, done_message="도면 담당을 정했어요."), count=len(user_ids))


def run_move_measurement(session: Any, req: RunRequest) -> RunOutcome:
    """방문 옮기기(실측) — 칸 고치기 본체를 본문 ``{"order_id", "field": "measurement_date", "value"}`` 로만 부른다."""
    order, stop = _locked_checked(session, req, UPDATE_FIELD_ENDPOINT)
    if stop is not None:
        return stop
    day = str(req.params.get("date"))
    data = {"order_id": int(order.id), "field": "measurement_date", "value": day}
    response = update_order_field_from_payload(data, req.actor_id, getattr(req.actor, "username", None),
                                               clean_dict_like_name=clean_dict_like_name)
    return _settled(session, outcome_from_response(response, done_message="실측일을 옮겼어요."), date=day)


#: 실행기 표 — services 표 + api 층 실행기(화면 승인 API 가 쓴다).
RUNNERS: dict[str, Runner] = {
    **SERVICE_RUNNERS, "register_as": run_register_as, "advance_stage": run_advance_stage,
    "assign_draftsman": run_assign_draftsman, "move_measurement": run_move_measurement,
}
