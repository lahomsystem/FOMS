"""생산 첫 화면(``/erp/production/home``)을 볼 수 있는 사람 — 한 곳 규칙(D19, 2026-11-10).

``foms/web/production/home.py`` 의 문지기(``_require_home_user``)와 태블릿 레일
(``foms.services.foms_split_view.build_tablet_rail_items``)이 같이 쓴다. 둘이 어긋나면
레일이 403 화면으로 보낸다. 이 모듈은 팀 권한 판정(``order_mutation_policy``)만 읽어
순환 import 가 없다.

보기와 쓰기는 다르다(설계서 2026-11-21-production-pc-viewer §5 · §13): 보는 팀은 관리자 + CS(회계 별칭) · 영업 · 생산에
2026-11-21 부터 도면 · 시공 · 출고를 더했고, 쓰는 사람은 관리자 + 생산팀뿐이다(``write_access.can_write_production``).
협력사 계정은 보지 않는다. 켜진 프리랜서는 여기서는 True 지만 문지기 허용 목록에 첫 화면이 없어 옛 보드를 쓴다
(메뉴 · 바로가기 주소는 ``foms/services/production/nav_target.py``).
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.order_mutation_policy import team_has_capability

#: 생산 첫 화면 주소(라우트 ``erp_production_page.erp_production_home``, 시험이 url_for 와 같은지 본다).
PRODUCTION_HOME_PATH = "/erp/production/home"
#: 볼 수 있는 팀(능력 이름 — 별칭 팀도 ``team_has_capability`` 가 같이 판정한다). 도면 · 시공 · 출고는 2026-11-21 더함(§9-1).
PRODUCTION_HOME_TEAMS = ("CS", "SALES", "PRODUCTION", "DRAWING", "CONSTRUCTION", "SHIPMENT")
#: 이 문지기(:func:`can_view_production_home`)가 지키는 보기 화면 주소 앞부분 — 첫 화면 · 전체 화면 작업 시트 · 인쇄 · 도면 카드 그림.
#: 시공팀 화면 이동 제한(``foms/platform/http.py`` ``_erp_construction_team_restrict``)이 이 주소들만 열어 준다(옛 보드는 그대로 막음).
PRODUCTION_VIEW_PATH_PREFIXES = (
    PRODUCTION_HOME_PATH,
    "/erp/production/sheet/",
    "/erp/production/print/",
    "/erp/production/parts/thumb/",
)


def can_view_production_home(user: Any) -> bool:
    """관리자이거나 보는 팀(CS · 영업 · 생산 · 도면 · 시공 · 출고)이면 True. 협력사 계정 · 로그인 없음 · 팀 없음은 False."""
    if not user or getattr(user, "partner_org_id", None) is not None:
        return False
    return getattr(user, "role", None) == "ADMIN" or team_has_capability(
        getattr(user, "team", None), PRODUCTION_HOME_TEAMS
    )
