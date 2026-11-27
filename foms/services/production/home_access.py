"""생산 첫 화면(``/erp/production/home``)을 볼 수 있는 사람 — 한 곳 규칙(D19, 2026-11-10).

``foms/web/production/home.py`` 의 문지기(``_require_home_user``)와 태블릿 레일
(``foms.services.foms_split_view.build_tablet_rail_items``)이 같이 쓴다. 둘이 어긋나면
레일이 403 화면으로 보낸다. 이 모듈은 팀 권한 판정(``order_mutation_policy``)만 읽어
순환 import 가 없다.

보기와 쓰기는 다르다(설계서 2026-11-21-production-pc-viewer §5 · §13): 보는 팀은 관리자 + CS(회계 별칭) · 영업 · 생산에
2026-11-21 부터 도면 · 시공 · 출고를 더했고, 쓰는 사람은 관리자 + 생산팀뿐이다(``write_access.can_write_production``).
협력사 계정은 보지 않는다. 켜진 프리랜서는 여기서는 True 지만 문지기 허용 목록에 첫 화면이 없어 옛 보드를 쓴다
(메뉴 · 바로가기 주소는 ``foms/services/production/nav_target.py``).

**팀 없는 직원 계정**(팀 값이 ``None`` · 빈 글 · 공백)도 2026-11-27 부터 **보기만** 한다(설계서 옛 생산 보드 없애기 §4,
사장님 "새 화면을 보기만 열어 주기"). 그 사람은 보는 팀이 아니므로 [확인했어요]도 없다 — 확인은
:func:`can_view_production_home_as_team` (관리자 · 보는 팀)만(``write_access.can_ack_production_change``). 쓰기는 원래대로 막힌다.
목록 밖 다른 팀 글자는 넓히지 않는다(§13 — 팀 값이 있는데 보는 팀이 아니면 그대로 False).
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.order_mutation_policy import team_has_capability

#: 팀 없이도 보기만 하는 직원 역할(관리자는 팀과 상관없이 본다). 협력사(PARTNER) · 그 밖의 역할 글자는 넓히지 않는다.
TEAMLESS_VIEW_ROLES = ("STAFF", "MANAGER", "VIEWER")

#: 생산 첫 화면 주소(라우트 ``erp_production_page.erp_production_home``, 시험이 url_for 와 같은지 본다).
PRODUCTION_HOME_PATH = "/erp/production/home"
#: 볼 수 있는 팀(능력 이름 — 별칭 팀도 ``team_has_capability`` 가 같이 판정한다). 도면 · 시공 · 출고는 2026-11-21 더함(§9-1).
PRODUCTION_HOME_TEAMS = ("CS", "SALES", "PRODUCTION", "DRAWING", "CONSTRUCTION", "SHIPMENT")
#: 이 문지기(:func:`can_view_production_home`)가 지키는 보기 화면 주소 앞부분 — 첫 화면 · 전체 화면 작업 시트 · 인쇄 · 도면 카드 그림.
#: 시공팀 화면 이동 제한(``foms/platform/http.py`` ``_erp_construction_team_restrict``)이 이 주소들만 열어 준다(그 밖 /erp/ 주소는 출고로).
PRODUCTION_VIEW_PATH_PREFIXES = (
    PRODUCTION_HOME_PATH,
    "/erp/production/sheet/",
    "/erp/production/print/",
    "/erp/production/parts/thumb/",
)


def can_view_production_home_as_team(user: Any) -> bool:
    """관리자이거나 보는 팀(CS · 회계 별칭 · 영업 · 실측 별칭 · 생산 · 도면 · 시공 · 출고)이면 True. 협력사 · 로그인 없음 · 팀 없음은 False.

    [확인했어요](``write_access.can_ack_production_change``)가 이것을 본다 — 팀 없는 계정은 보기만 하고 확인 단추는 없다(§4).
    """
    if not user or getattr(user, "partner_org_id", None) is not None:
        return False
    return getattr(user, "role", None) == "ADMIN" or team_has_capability(
        getattr(user, "team", None), PRODUCTION_HOME_TEAMS
    )


def _is_teamless_staff(user: Any) -> bool:
    """협력사가 아니고 팀 값이 빈(``None`` · 빈 글 · 공백) 직원 역할(:data:`TEAMLESS_VIEW_ROLES`) 계정인지."""
    if getattr(user, "partner_org_id", None) is not None:
        return False
    if str(getattr(user, "role", None) or "").strip().upper() not in TEAMLESS_VIEW_ROLES:
        return False
    return not str(getattr(user, "team", None) or "").strip()


def can_view_production_home(user: Any) -> bool:
    """생산 첫 화면을 볼 수 있는지 — 관리자 · 보는 팀(:func:`can_view_production_home_as_team`) 또는 팀 없는 직원(보기만, §4).

    협력사 계정 · 로그인 없음 · 목록 밖 팀 글자는 False.
    """
    if not user:
        return False
    return can_view_production_home_as_team(user) or _is_teamless_staff(user)
