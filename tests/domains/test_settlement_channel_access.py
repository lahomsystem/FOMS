"""NAVER-SETTLE-01 §1: 채널(네이버) 정산 열람 게이트 판정 매트릭스.

채널 정산 탭은 **ADMIN 과 회계팀(ACCOUNTING)만** 본다. 정책 엔진으로는 이 집합을 표현할 수
없다 — `evaluate_policy` 가 ``MANAGER`` 를 team 검사보다 **먼저** 통과시키기 때문이다
(운영 실측상 회계 업무 담당 예정자 2명이 바로 MANAGER·team=CS 조합이라, 엔진에 맡기면
"CS 팀 매니저 전원"이 회계 자료를 연다). 그래서 판정 SSOT 는
:func:`foms.services.settlement_channel_access.can_view_channel_settlement` 이고,
이 파일이 그 함수의 매트릭스를 못박는다.

여기서 잠그는 것 셋:
1. **매트릭스 8행** — 통과 3 / 거부 5. 특히 `MANAGER+CS` 거부가 이 게이트의 존재 이유다.
2. **엔진과 같은 답을 낸다는 사실** — 2026-09-03 부터 정책 등재가 ``gate`` 로 이 함수를
   가리키므로 ``user_can(SETTLEMENT_CHANNEL_READ, ...)`` 도 같은 답을 낸다. gate 를 떼면
   MANAGER role override 가 되살아나 CS 팀 매니저가 열린다 — 그 회귀를 잡는다.
3. **정책 등재 자체** — 미등재 policy_id 는 ``user_can`` 이 조용히 False 를 준다.
   manifest·가드 pre-filter 가 이 id 를 참조하므로 등재 누락은 무음 장애가 된다.
"""

from __future__ import annotations

import pytest

from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, user_can
from foms.services.settlement_channel_access import (
    ACCOUNTING_TEAM,
    SETTLEMENT_CHANNEL_POLICY_ID,
    SETTLEMENT_CHANNEL_SYNC_POLICY_ID,
    can_view_channel_settlement,
)
from tests.domains.test_auth_finance import _make_user

#: (role, team, is_active, 기대) 8행. 계약서 §1 매트릭스 그대로다.
_MATRIX = [
    ("ADMIN", None, True, True),
    ("MANAGER", ACCOUNTING_TEAM, True, True),
    ("STAFF", ACCOUNTING_TEAM, True, True),
    ("MANAGER", "CS", True, False),
    ("STAFF", "CS", True, False),
    ("VIEWER", ACCOUNTING_TEAM, True, False),
    ("STAFF", ACCOUNTING_TEAM, False, False),
    (None, None, None, False),  # 미인증(user=None)
]

_MATRIX_IDS = [
    "admin",
    "manager+accounting",
    "staff+accounting",
    "manager+cs",
    "staff+cs",
    "viewer+accounting",
    "inactive-staff+accounting",
    "anonymous",
]


def _actor(role, team, is_active):
    """매트릭스 한 행을 사용자 객체(또는 None)로 만든다.

    Args:
        role: role 문자열. ``None`` 이면 미인증을 뜻한다.
        team: team 문자열.
        is_active: 활성 여부.

    Returns:
        생성한 ``User`` 또는 ``None``.
    """
    if role is None:
        return None
    user = _make_user(role=role, team=team)
    if not is_active:
        user.is_active = False
    return user


@pytest.mark.parametrize("role,team,is_active,expected", _MATRIX, ids=_MATRIX_IDS)
def test_channel_settlement_gate_matrix(app, role, team, is_active, expected):
    """게이트 함수가 8행 매트릭스대로 판정한다."""
    user = _actor(role, team, is_active)

    assert can_view_channel_settlement(user) is expected, (role, team, is_active)


def test_manager_outside_accounting_is_denied_by_gate_and_engine(app):
    """`MANAGER+CS` 는 게이트에서도, 정책 엔진에서도 거부된다.

    게이트 함수가 따로 있는 이유는 엔진의 role override 다 — MANAGER 는 team 검사보다
    먼저 통과하므로 ``teams=("ACCOUNTING",)`` 만으로는 CS 팀 매니저가 열린다(운영 실측
    2026-09-02). 2026-09-03 부터는 정책 등재에 ``gate`` 를 달아 엔진도 같은 함수로
    판정하므로 둘 다 거부여야 한다. 어느 한쪽이라도 True 면 회계 자료가 새는 것이다.
    """
    user = _make_user(role="MANAGER", team="CS")

    assert user_can(SETTLEMENT_CHANNEL_POLICY_ID, user) is False, "엔진이 CS 매니저를 열었다"
    assert can_view_channel_settlement(user) is False


def test_channel_policies_are_registered(app):
    """읽기·동기화 policy_id 두 개가 ``POLICY_REGISTRY`` 에 등재돼 있다.

    ``user_can`` 은 미등록 id 에 조용히 False 를 주므로, 등재 누락은 "아무도 못 쓰는 기능"
    이라는 무음 장애로 나타난다. manifest·before_request pre-filter 가 이 id 를 참조한다.
    """
    for policy_id in (SETTLEMENT_CHANNEL_POLICY_ID, SETTLEMENT_CHANNEL_SYNC_POLICY_ID):
        assert policy_id in POLICY_REGISTRY, policy_id
        policy = POLICY_REGISTRY[policy_id]
        assert policy.policy_id == policy_id
        assert tuple(policy.teams) == (ACCOUNTING_TEAM,), policy
        assert policy.viewer is False, "VIEWER 하드 deny"
        assert policy.anonymous is False
        assert policy.assignment is None


def test_accounting_team_is_a_real_team_code(app):
    """``ACCOUNTING`` 이 사용자 관리 화면의 팀 SSOT 에 실제로 있다.

    게이트가 아무 문자열이나 team 으로 받으면, 그 팀을 **아무도 배정할 수 없어** 기능이
    영원히 잠긴다(화면 드롭다운은 ``TEAMS`` 를 그대로 렌더한다).
    """
    from foms.web.auth.routes import TEAMS

    assert ACCOUNTING_TEAM in TEAMS
    assert TEAMS[ACCOUNTING_TEAM] == "회계팀"
