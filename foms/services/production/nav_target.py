"""생산 메뉴 · 알림 · 바로가기가 어디로 가나 — 한 곳 규칙(설계서 2026-11-21-production-pc-viewer §9 · R1).

* 새 첫 화면(``/erp/production/home``)을 볼 수 있고(:func:`can_view_production_home`) 켜진 프리랜서가 아니면 → 첫 화면.
* 그 밖(켜진 프리랜서 · 첫 화면을 못 보는 사람) → 옛 보드(``/erp/production/dashboard``). 프리랜서는 문지기 허용 목록에
  보드만 있고 첫 화면에는 '내 것만' 이 없다(§9-12, 3단계에서 옮긴다).

주문 하나를 가리키는 링크는 첫 화면이면 ``?order=<id>``(날짜 탭이 그 주문의 날을 고른다, §9-10), 보드면 예전대로
``?focus_order=<id>`` 다. 옛 보드 라우트는 지우지 않는다 — 넘겨주기(R2)는 2주 뒤 접속 기록을 보고 따로 정한다(§13 결정 4).

PC 둘째 줄 메뉴 · 폰 아래 메뉴(템플릿 전역 ``production_nav_href`` — ``foms/web/production/dashboard.py`` 가 등록) · 태블릿 · split 레일(``foms_split_view``) · 주문 목록의
'생산 화면 열기'(``board_state_display``) · 검색 바로가기 · 돌아가기 열쇠(``erp_order_deeplink``)가 이 모듈을 본다.
"""

from __future__ import annotations

from typing import Any

from flask import g, has_request_context

from foms.services.auth.freelancer_scope import could_be_freelancer, is_freelancer_user
from foms.services.production.home_access import PRODUCTION_HOME_PATH, can_view_production_home

#: 옛 생산 보드 주소(라우트 ``erp_production_page.erp_production_dashboard``).
PRODUCTION_BOARD_PATH = "/erp/production/dashboard"
PRODUCTION_HOME_ENDPOINT = "erp_production_page.erp_production_home"
PRODUCTION_BOARD_ENDPOINT = "erp_production_page.erp_production_dashboard"
#: 첫 화면이 읽는 주문 고르기 인자(§9-10). 보드는 예전 이름 ``focus_order`` 그대로.
HOME_ORDER_PARAM = "order"
BOARD_ORDER_PARAM = "focus_order"
#: 생산 변경 알림(``PRODUCTION_ORDER_CHANGED``) 폰 알림이 여는 곳 — 첫 화면 '바뀐 것' 탭(§9-6).
PRODUCTION_CHANGES_HREF = f"{PRODUCTION_HOME_PATH}?tab=changes"


def request_user() -> Any:
    """요청 안이면 지금 사용자(``g.current_user``), 요청 밖(순수 함수 시험 · 작업자)이면 None."""
    return getattr(g, "current_user", None) if has_request_context() else None


def _is_active_freelancer(user: Any) -> bool:
    """켜진 프리랜서인지. 요청 밖이거나 프리랜서가 될 수 없는 계정이면 설정을 읽지 않는다(``foms_split_view`` 와 같은 판정)."""
    if user is None or not has_request_context():
        return False
    return could_be_freelancer(user) and is_freelancer_user(user)


def production_home_open_for(user: Any) -> bool:
    """생산 메뉴 · 바로가기가 새 첫 화면으로 갈지 — 볼 수 있고 켜진 프리랜서가 아니면 True."""
    return can_view_production_home(user) and not _is_active_freelancer(user)


def production_nav_href(user: Any) -> str:
    """생산 메뉴 칸 주소 — 첫 화면 또는 옛 보드."""
    return PRODUCTION_HOME_PATH if production_home_open_for(user) else PRODUCTION_BOARD_PATH


def production_order_link(order_id: int, user: Any) -> tuple[str, dict[str, int]]:
    """주문 하나를 생산 화면에서 여는 ``(endpoint, url_for 인자)`` — 첫 화면 ``order=`` 또는 보드 ``focus_order=``."""
    oid = int(order_id)
    if production_home_open_for(user):
        return PRODUCTION_HOME_ENDPOINT, {HOME_ORDER_PARAM: oid}
    return PRODUCTION_BOARD_ENDPOINT, {BOARD_ORDER_PARAM: oid}


def production_order_href(order_id: int, user: Any) -> str:
    """:func:`production_order_link` 의 주소 글(``url_for`` 없이 — 요청 밖에서도 같은 글)."""
    endpoint, params = production_order_link(order_id, user)
    base = PRODUCTION_HOME_PATH if endpoint == PRODUCTION_HOME_ENDPOINT else PRODUCTION_BOARD_PATH
    (key, value), = params.items()
    return f"{base}?{key}={value}"


__all__ = [
    "BOARD_ORDER_PARAM",
    "PRODUCTION_CHANGES_HREF",
    "HOME_ORDER_PARAM",
    "PRODUCTION_BOARD_ENDPOINT",
    "PRODUCTION_BOARD_PATH",
    "PRODUCTION_HOME_ENDPOINT",
    "production_home_open_for",
    "production_nav_href",
    "production_order_href",
    "production_order_link",
    "request_user",
]
