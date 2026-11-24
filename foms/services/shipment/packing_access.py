"""출고 패킹을 누가 보고 누가 체크하나 — 한 곳 규칙(설계서 2026-11-23 '승인 때 고친 것' 6 ①, 사장님 "패킹 체크는 생산, 시공, 관리자").

정책 엔진 문지기(``PACKING_WRITE`` 의 ``gate``) · 패킹 API 의 읽기 문(GET) · 줄마다 공장 문 · 화면 단추가 모두 이 함수들을 본다.
둘이 어긋나면 단추는 있는데 서버가 막거나, 쓰기는 되는데 목록을 못 읽는다(예전 — 생산팀 매니저는 POST 는 되는데 GET 이 403).

* **체크(쓰기)** = 관리자 · 매니저(팀 무관 — 지금 그대로) · 출고 · CS(회계 별칭) · 영업 · 시공 팀 직원(지금 그대로)
  + **생산팀 중 카드 · 공정을 쓰는 계정**(파트 계정 · 반장 — ``part_access.writable_factories`` 가 빈 것이 아닌 계정, 새로).
  파트도 반장도 아닌 생산팀(보기만) · VIEWER · 협력사 · 꺼진 계정은 안 된다.
* **공장 몫** = 생산팀 계정(관리자 아님)은 자기 계정 공장 줄만(``part_access.user_factory``), 그 밖은 두 공장. 2공장 장이 없는 주문은
  모든 줄이 1공장 몫이다(``packing_factory``).
* **보기(GET)** = 체크할 수 있는 사람 + 예전 읽기 문이 열어 주던 출고 · CS · 영업 · 시공 팀 조회 전용(VIEWER) — 그 사람들 화면은 그대로.

생산 쪽 규칙(``foms/services/production/part_access.py``)은 읽기만 한다(그 파일은 고치지 않는다).
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.order_mutation_policy import team_has_capability
from foms.services.production.factory_constants import FACTORIES, factory_label
from foms.services.production.part_access import user_factory, writable_factories

#: 지금 패킹 권한이 있던 팀(``PACKING_WRITE`` 의 teams 와 같은 값) — 두 공장.
PACKING_TEAMS: tuple[str, ...] = ("CS", "SALES", "SHIPMENT", "CONSTRUCTION")
#: 공장 몫으로 묶이는 팀.
PRODUCTION_TEAMS: tuple[str, ...] = ("PRODUCTION",)

#: 읽기 문 거절 글(지금 글 그대로).
PACKING_DENIED_MESSAGE = "출고 패킹 수정 권한이 없습니다."
#: 남의 공장 줄 체크 거절(403).
FACTORY_FORBIDDEN_CODE = "PACKING_FACTORY_FORBIDDEN"


def _role(user: Any) -> str:
    return str(getattr(user, "role", None) or "").strip().upper()


def _live(user: Any) -> bool:
    if user is None or getattr(user, "is_active", None) is False:
        return False
    return getattr(user, "partner_org_id", None) is None


def is_production_account(user: Any) -> bool:
    """생산팀 계정(관리자 아님)인지 — 패킹은 자기 공장 몫만."""
    return _role(user) != "ADMIN" and team_has_capability(getattr(user, "team", None), PRODUCTION_TEAMS)


def can_write_packing(user: Any) -> bool:
    """출고 패킹 줄을 체크(쓰기)할 수 있는지 — 정책 ``PACKING_WRITE`` 문지기 · 화면 단추가 같이 본다.

    Args:
        user: 사용자 객체(None 허용). 이미 읽은 행의 칸만 본다 — 쿼리 0.

    Returns:
        관리자 · 매니저 · 출고 · CS · 영업 · 시공 팀 직원(지금 그대로)이거나, 카드 · 공정을 쓰는 생산팀 계정(파트 계정 · 반장)이면 True.
    """
    if not _live(user):
        return False
    role = _role(user)
    if role in ("ADMIN", "MANAGER"):
        return True
    if role != "STAFF":
        return False
    if team_has_capability(getattr(user, "team", None), PACKING_TEAMS):
        return True
    return bool(writable_factories(user))


def can_view_packing(user: Any) -> bool:
    """패킹 목록(GET)을 열 수 있는지 — 체크할 수 있는 사람 + 출고 · CS · 영업 · 시공 팀 조회 전용(예전 읽기 문 그대로)."""
    if can_write_packing(user):
        return True
    return _live(user) and _role(user) == "VIEWER" and team_has_capability(getattr(user, "team", None), PACKING_TEAMS)


def packing_factories(user: Any) -> tuple[int, ...]:
    """이 사람이 체크할 수 있는 공장 줄 — 생산팀 계정은 자기 공장 하나, 그 밖 체크하는 사람은 두 공장, 못 하면 빈 tuple."""
    if not can_write_packing(user):
        return ()
    if is_production_account(user):
        return (user_factory(user),)
    return FACTORIES


def factory_forbidden_message(factory: int, mine: tuple[int, ...]) -> str:
    """남의 공장 줄을 체크하려 할 때의 글 — "1공장 줄은 1공장에서 체크해요. 내 공장(2공장) 줄만 체크할 수 있어요."."""
    label = factory_label(factory)
    if len(mine) == 1:
        return f"{label} 줄은 {label}에서 체크해요. 내 공장({factory_label(mine[0])}) 줄만 체크할 수 있어요."
    return f"{label} 줄은 체크할 수 없어요."
