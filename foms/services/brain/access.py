"""'회사 지식' 화면 · API 를 여는 사람(설계서 7.5 끝 '판 1 은 ADMIN · 승인자만' · 사장님 D101)과 **결정할 수 있는 사람**.

- 켜진 내부 ADMIN(사장님 포함), 그리고 **층 승인자 팀의 켜진 MANAGER**(상담 = CS · 도면 = DRAWING · 생산 = PRODUCTION —
  :data:`.constants.LAYER_APPROVER_TEAMS`)만 연다.
- 그 밖(다른 팀 MANAGER · STAFF · VIEWER · PARTNER · 협력사 직원 · 꺼진 계정)은 화면 · API 모두 404 — 있는지도 알리지 않는다.
- 연 사람이 무엇을 보는지는 따로다 — 모든 읽기는 :mod:`.scope` 의 보기 범위로 질의 단계에서 거른다(승인자 MANAGER 는 '내부
  모두' + 자기 팀 범위만, 가격 재량 · 관리 항목은 ADMIN 만).
- **결정(반영 · 거절) 판정은 :func:`approval_problem` 하나**다(5절 · D101) — 반영 동작(:mod:`.apply`)과 제안함 · 다시 확인
  질의(:func:`approver_layers`)가 같은 규칙을 쓴다: ADMIN 은 모두, 가격 규칙 · 정책 · 사장님 결정과 공통 바탕 은퇴 · 지우기는
  ADMIN 만, 그 밖은 그 층 승인자 팀의 MANAGER. 이름표 칸만 바뀌는 고침은 상담팀장도(층 · 유형 상관없이 — D167).
  **승인 대기 ③(엇갈림 · 물어볼 것 항목 만들기)은 ADMIN 만**(D167 '① 만 상담팀장, 나머지는 사장님' · D152 — 층과 상관없이).
  ③ 질문 카드의 답(회사 지식이 맞음 · 바깥 글이 맞음 · 둘 다)은 그 제안의 거절이라 같은 판정을 지난다.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.brain.constants import (LAYER_APPROVER_TEAMS, LAYER_COMMON, NAME_APPROVER_TEAM, OP_DELETE, OP_RETIRE,
                                           OWNER_ONLY_TYPES)
from foms.services.brain.inbox_bins import ADMIN_WIDE_BINS, BIN_NAMES, owner_decides
from foms.services.brain.scope import ROLE_MANAGER, Viewer, viewer_of

#: 화면을 여는 MANAGER 의 팀(층 승인자 팀).
APPROVER_TEAMS: frozenset[str] = frozenset(LAYER_APPROVER_TEAMS.values())


def screen_viewer(user: Any) -> Optional[Viewer]:
    """화면을 열 수 있으면 그 사람의 :class:`Viewer`, 아니면 ``None``.

    Args:
        user: 로그인 사용자(없으면 ``None``).

    Returns:
        켜진 내부 ADMIN 또는 층 승인자 팀 MANAGER 의 Viewer, 그 밖은 ``None``.
    """
    viewer = viewer_of(user)
    if not viewer.internal or viewer.user_id is None:
        return None
    if viewer.is_admin or (viewer.role == ROLE_MANAGER and viewer.team in APPROVER_TEAMS):
        return viewer
    return None


def can_open_screen(user: Any) -> bool:
    """메뉴에 '회사 지식'을 보일지 — :func:`screen_viewer` 와 같은 판정(DB 를 읽지 않는다)."""
    return screen_viewer(user) is not None


def name_approver(viewer: Viewer) -> bool:
    """이름표 칸만 바뀌는 고침을 층 · 유형과 상관없이 결정하는 상담팀장인가(D167 — ADMIN 은 따로 모두)."""
    return viewer.internal and viewer.role == ROLE_MANAGER and viewer.team == NAME_APPROVER_TEAM


def wide_bins(viewer: Viewer) -> frozenset[str]:
    """등급과 상관없이 한꺼번에 승인하는 묶음 — 관리자 ① · ④(D151) · ⑤ 계산기 제품 · 옵션(D192) · ⑥ 규칙 잇기(D194 · D202), 상담팀장 ①(D167), 그 밖은 없음
    (등급 A 만)."""
    if viewer.internal and viewer.is_admin:
        return ADMIN_WIDE_BINS
    return frozenset({BIN_NAMES}) if name_approver(viewer) else frozenset()


def approval_problem(viewer: Viewer, *, op: str, layer: Optional[str],
                     types: Iterable[Optional[str]], label_only: bool = False) -> Optional[str]:
    """이 사람이 이 제안을 결정(반영 · 거절)할 수 없는 까닭 — 할 수 있으면 ``None``.

    Args:
        viewer: 결정하는 사람.
        op: 제안 동작.
        layer: 제안의 층(링크면 시작 항목의 층).
        types: 닿는 유형들(링크면 양 끝 유형).
        label_only: 이름표 칸만 바뀌는 고침인가(:func:`.inbox_bins.label_only_change`) — 상담팀장도 결정(D167).

    Returns:
        정한 글 하나(사람 아님 · 사장님 몫 · 층 승인자 아님) 또는 ``None``.
    """
    types = tuple(types)
    if not viewer.internal or viewer.user_id is None:
        return "켜진 내부 사람 계정만 반영한다"
    if viewer.is_admin:
        return None
    if any(owner_decides(op, t) for t in types):
        return "사장님(ADMIN)만 정한다 — 승인 대기 ③ 엇갈림 · 물어볼 것"
    if label_only and name_approver(viewer):
        return None
    if any(t in OWNER_ONLY_TYPES for t in types) or (op in (OP_RETIRE, OP_DELETE) and layer == LAYER_COMMON):
        return "사장님(ADMIN)만 반영한다 — 가격 · 정책 · 사장님 결정 · 공통 바탕 은퇴 · 지우기"
    team = LAYER_APPROVER_TEAMS.get(layer or "")
    if viewer.role == ROLE_MANAGER and team is not None and viewer.team == team:
        return None
    return "이 층 승인자가 아니다"


def approver_layers(viewer: Viewer) -> Optional[tuple[str, ...]]:
    """질의 거르기용 — ``None`` = 모든 층(ADMIN), 아니면 이 사람이 결정하는 층들(빈 묶음 = 없음).

    층 승인자 MANAGER 라도 사장님 몫 유형(:data:`OWNER_ONLY_TYPES`)과 ③ 엇갈림 · 물어볼 것 만들기(:func:`.inbox_bins.owner_decides`)는
    따로 빼야 한다(호출자 몫).
    """
    if not viewer.internal or viewer.user_id is None:
        return ()
    if viewer.is_admin:
        return None
    if viewer.role != ROLE_MANAGER:
        return ()
    return tuple(layer for layer, team in LAYER_APPROVER_TEAMS.items() if team == viewer.team)
