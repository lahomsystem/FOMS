"""FCOMM-01 3단계 겹 5 메뉴: 켜진 프리랜서에게 보이는 메뉴 항목(문지기 허용 목록 안만).

PC 위 메뉴 · ERP 서브 내비(``layout_nav.html`` · ``erp_sub_nav.html`` 의 ``freelancer_nav_items()``)와 태블릿 레일
(:func:`foms.services.foms_split_view.build_split_side_items`)이 이 목록을 쓴다. 휴대폰 아래 탭 · 서랍
(``erp_mobile_shell.html``)은 같은 셋(홈 · 실측 · 내 수수료)을 id 로 적는다.
모든 항목의 endpoint 는 :data:`foms.services.auth.freelancer_scope.FREELANCER_ALLOWED_ENDPOINTS` 안에 있어야 한다
(시험: tests/domains/test_freelancer_menus.py).

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 5
"""
from __future__ import annotations

from typing import Any

from flask import url_for

#: (id, 글, endpoint, 아이콘) — 화면 순서.
FREELANCER_MENU: tuple[tuple[str, str, str, str], ...] = (
    ("dashboard", "대시보드", "erp_dashboard.erp_dashboard", "fas fa-layer-group"),
    ("measurement", "실측", "erp_measurement_dashboard.erp_measurement_dashboard", "fas fa-ruler-combined"),
    ("my_commission", "내 수수료", "sales_commission_web.my_commission", "fas fa-coins"),
)


def freelancer_menu_items() -> list[dict[str, Any]]:
    """메뉴 항목 목록 — ``id`` · ``name``(=``label``) · ``url``(=``href``) · ``icon``. 요청 문맥 안에서 부른다."""
    items = []
    for item_id, label, endpoint, icon in FREELANCER_MENU:
        href = url_for(endpoint)
        items.append({"id": item_id, "name": label, "label": label, "url": href, "href": href, "icon": icon})
    return items


__all__ = ["FREELANCER_MENU", "freelancer_menu_items"]
