"""생산 메뉴 · 알림 · 바로가기가 어디로 가나 — 한 곳 규칙(설계서 2026-11-21-production-pc-viewer §9 · 2026-11-27 옛 보드 없애기 §5-1).

* 누구든 새 첫 화면(``/erp/production/home``)으로 간다. 옛 생산 보드는 없앴다(2026-11-27 사장님 "legacy 보드 없애") —
  켜진 프리랜서는 첫 화면에서 '내 주문만', 팀 없는 직원은 보기만 한다(볼 수 있는지는 첫 화면 문지기가 본다).

주문 하나를 가리키는 링크는 ``?order=<id>``(날짜 탭이 그 주문의 날을 고른다, §9-10).

PC 둘째 줄 메뉴 · 폰 아래 메뉴(템플릿 전역 ``production_nav_href``) · 태블릿 · split 레일(``foms_split_view``) · 주문 목록의
'생산 화면 열기'(``board_state_display``) · 검색 바로가기 · 돌아가기 열쇠(``erp_order_deeplink``)가 이 모듈을 본다.
"""

from __future__ import annotations

from typing import Any

from flask import g, has_request_context

from foms.services.production.home_access import PRODUCTION_HOME_PATH

PRODUCTION_HOME_ENDPOINT = "erp_production_page.erp_production_home"
#: 첫 화면이 읽는 주문 고르기 인자(§9-10).
HOME_ORDER_PARAM = "order"
#: 생산 변경 알림(``PRODUCTION_ORDER_CHANGED``) 폰 알림이 여는 곳 — 첫 화면 '바뀐 것' 탭(§9-6).
PRODUCTION_CHANGES_HREF = f"{PRODUCTION_HOME_PATH}?tab=changes"


def request_user() -> Any:
    """요청 안이면 지금 사용자(``g.current_user``), 요청 밖(순수 함수 시험 · 작업자)이면 None."""
    return getattr(g, "current_user", None) if has_request_context() else None


def production_nav_href(user: Any = None) -> str:
    """생산 메뉴 칸 주소 — 누구든 첫 화면(``user`` 는 부르는 쪽 서명을 지키려고 받기만 한다)."""
    return PRODUCTION_HOME_PATH


def production_order_link(order_id: int, user: Any = None) -> tuple[str, dict[str, int]]:
    """주문 하나를 생산 화면에서 여는 ``(endpoint, url_for 인자)`` — 첫 화면 ``order=``."""
    return PRODUCTION_HOME_ENDPOINT, {HOME_ORDER_PARAM: int(order_id)}


def production_order_href(order_id: int, user: Any = None) -> str:
    """:func:`production_order_link` 의 주소 글(``url_for`` 없이 — 요청 밖에서도 같은 글)."""
    return f"{PRODUCTION_HOME_PATH}?{HOME_ORDER_PARAM}={int(order_id)}"


__all__ = [
    "PRODUCTION_CHANGES_HREF",
    "HOME_ORDER_PARAM",
    "PRODUCTION_HOME_ENDPOINT",
    "production_nav_href",
    "production_order_href",
    "production_order_link",
    "request_user",
]
