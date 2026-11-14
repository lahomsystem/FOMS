"""ERP 할 일 제안을 **보는 사람 · 결정하는 사람** 판정 한 곳(설계서 2026-11-14-foms-graft 3.5).

- 보는 사람 = 그 할 일을 실행할 수 있는 사람: 켜진 내부 계정 + ``actions`` 스위치(:func:`.graft_flags.enabled` — ``brain_ui``
  까지 같이 본다) + 할 일의 ``policy_id`` 통과(:func:`evaluate_policy` — 감싼 길과 같은 정책) + 그 주문 읽기 권한
  (:func:`user_can_read_order` — 프리랜서는 자기 주문만, 협력사는 못 본다).
- 결정(승인 · 거절 · 나중에)은 :func:`can_decide` — 보는 사람 규칙에서 **사람별 화면 스위치만 뺀 것**이다. 채널톡 작은 창
  (설계서 3.9)은 FOMS 로그인이 없어 사람별 스위치를 쓸 수 없고 상담 관리 칸 스위치로 따로 막는다. 화면 API 는
  :func:`actions_viewer` 를 먼저 본 뒤 생명주기 함수를 부른다.
- ``mode = human`` 인 할 일(사람만)은 아무에게도 보이지 않는다(제안 · 실행 길이 없다).
- 질의 거르기: :func:`runnable_actions` (이 사람이 실행할 수 있는 할 일 이름) · :func:`scoped_reader` (주문을 모두 읽는
  사람이면 ``None``, 연결 표로 좁혀 읽는 사람이면 그 사용자 번호). 볼 수 없는 제안은 질의 단계에서 거른다.
- DB 를 직접 읽지 않는다(프리랜서 판정 · 주문 읽기 권한은 정책 모듈이 읽는다).
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.brain.scope import viewer_of
from foms.services.erp_actions.registry import ACTIONS, MODE_HUMAN, ActionSpec
from foms.services.graft_flags import enabled
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy, user_can_read_order

__all__ = [
    "actions_viewer", "can_decide", "can_run", "internal_user", "policy_allows", "runnable_actions", "scoped_reader",
]


def internal_user(user: Any) -> bool:
    """켜진 내부 계정인가(없음 · 꺼짐 · 협력사 계정 · 협력사 직원은 아니다 — 회사 지식 보기 판정과 같다)."""
    viewer = viewer_of(user)
    return viewer.internal and viewer.user_id is not None


def policy_allows(user: Any, spec: ActionSpec) -> bool:
    """그 할 일의 ``policy_id`` 를 지나는가(사람만 할 일 · 정책 없는 할 일 · 조회 전용 계정은 거짓).

    조회 전용(VIEWER)은 정책과 상관없이 거짓이다 — 할 일은 모두 주문을 바꾸는 일인데, 문지기 함수가 있는 정책
    (``CONSTRUCTION_SCHEDULE_EDIT``)은 엔진에서 VIEWER 막기보다 먼저 돌아 CS · 영업 팀 VIEWER 를 통과시킨다.

    Args:
        user: 로그인 사용자.
        spec: 할 일(:data:`.registry.ACTIONS` 의 값).

    Returns:
        감싼 길과 같은 정책 판정(:func:`evaluate_policy`)이 허용이면 True.
    """
    if spec.mode == MODE_HUMAN or not spec.policy_id:
        return False
    if str(getattr(user, "role", "") or "").strip().upper() == "VIEWER":
        return False
    policy = POLICY_REGISTRY.get(spec.policy_id)
    return policy is not None and evaluate_policy(policy, user).allowed


def runnable_actions(user: Any) -> tuple[str, ...]:
    """이 사람이 실행할 수 있는 할 일 이름(목록 차례) — 내부 계정이 아니면 빈 묶음."""
    if not internal_user(user):
        return ()
    return tuple(name for name, spec in ACTIONS.items() if policy_allows(user, spec))


def actions_viewer(user: Any) -> bool:
    """ERP 할 일 제안을 볼 수 있는 사람인가 — 켜진 내부 계정 + ``actions`` 스위치 + 통과하는 정책이 하나라도.

    Args:
        user: 로그인 사용자(없으면 ``None``).

    Returns:
        새 API · 승인 대기 'AI 할 일 제안' 칸을 열어도 되면 True. 스위치가 꺼졌으면 늘 거짓(지금과 같다).
    """
    if not internal_user(user) or not enabled("actions", user):
        return False
    return bool(runnable_actions(user))


def scoped_reader(user: Any) -> Optional[int]:
    """주문 읽기 범위 — 모든 주문을 읽는 사람이면 ``None``, 연결 표로 좁혀 읽는 사람(켜진 프리랜서)이면 사용자 번호.

    :func:`user_can_read_order` 는 주문 없이 물으면 전역으로 읽는 사람에게만 참이다(협력사 · 프리랜서는 주문마다 판정).
    협력사는 :func:`internal_user` 에서 이미 빠지므로 여기서 거짓이면 프리랜서다.
    """
    return None if user_can_read_order(user, None) else int(getattr(user, "id"))


def can_decide(user: Any, spec: ActionSpec, order: Any) -> bool:
    """이 주문의 이 할 일 제안을 결정(승인 · 거절 · 나중에)할 수 있나 — 사람별 화면 스위치는 보지 않는다.

    Args:
        user: 결정하는 로그인 사용자.
        spec: 할 일.
        order: 대상 주문(없으면 거짓 — 지워진 주문의 제안은 아무도 결정하지 않는다).

    Returns:
        켜진 내부 계정 + 정책 통과 + 그 주문 읽기 권한이면 True.
    """
    if order is None or not internal_user(user) or not policy_allows(user, spec):
        return False
    return bool(user_can_read_order(user, order))


def can_run(user: Any, spec: ActionSpec, order: Any) -> bool:
    """이 주문의 이 할 일 제안을 볼 · 실행할 수 있나 — :func:`actions_viewer` + :func:`can_decide`."""
    return actions_viewer(user) and can_decide(user, spec, order)
