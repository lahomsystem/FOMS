"""생산 첫 화면(``/erp/production/home``)을 볼 수 있는 사람 — 한 곳 규칙(D19, 2026-11-10).

``foms/web/production/home.py`` 의 문지기(``_require_home_user``)와 태블릿 레일
(``foms.services.foms_split_view.build_tablet_rail_items``)이 같이 쓴다. 둘이 어긋나면
레일이 403 화면으로 보낸다. 이 모듈은 팀 권한 판정(``order_mutation_policy``)만 읽어
순환 import 가 없다.
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.order_mutation_policy import team_has_capability

#: 생산 첫 화면 주소(라우트 ``erp_production_page.erp_production_home``, 시험이 url_for 와 같은지 본다).
PRODUCTION_HOME_PATH = "/erp/production/home"
#: 볼 수 있는 팀(능력 이름 — 별칭 팀도 ``team_has_capability`` 가 같이 판정한다).
PRODUCTION_HOME_TEAMS = ("CS", "SALES", "PRODUCTION")


def can_view_production_home(user: Any) -> bool:
    """관리자이거나 CS·영업·생산 능력을 가진 팀이면 True. 협력사 계정 · 로그인 없음은 False."""
    if not user or getattr(user, "partner_org_id", None) is not None:
        return False
    return getattr(user, "role", None) == "ADMIN" or team_has_capability(
        getattr(user, "team", None), PRODUCTION_HOME_TEAMS
    )
