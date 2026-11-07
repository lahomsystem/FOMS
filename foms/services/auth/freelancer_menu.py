"""FCOMM-01 3단계 겹 5 메뉴: 켜진 프리랜서에게 보이는 메뉴 항목(문지기 허용 목록 안만).

PC 위 메뉴 · ERP 서브 내비(``layout_nav.html`` · ``erp_sub_nav.html`` 의 ``freelancer_nav_items()``)와 태블릿 레일
(:func:`foms.services.foms_split_view.build_split_side_items`)이 이 목록을 쓴다. 휴대폰 아래 탭 · 서랍
(``erp_mobile_shell.html``)은 같은 셋(홈 · 실측 · 내 수수료)을 id 로 적는다.
허용 목록(:data:`foms.services.auth.freelancer_scope.FREELANCER_ALLOWED_ENDPOINTS`) 밖 항목은 싣지 않는다
(시험: tests/domains/test_freelancer_menus.py).

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 5
"""
from __future__ import annotations

from typing import Any

from flask import url_for

from foms.services.auth.freelancer_scope import FREELANCER_ALLOWED_ENDPOINTS

#: (id, 글, endpoint, 아이콘) — 화면 순서(회사 영업 메뉴와 같은 순서). 문지기 허용 목록에 든 것만 보인다 — 판 화면 묶음
#: (foms/services/auth/freelancer_screens/)이 열리면 메뉴에도 저절로 나타난다(D27).
FREELANCER_MENU: tuple[tuple[str, str, str, str], ...] = (
    ("dashboard", "대시보드", "erp_dashboard.erp_dashboard", "fas fa-layer-group"),
    ("measurement", "실측", "erp_measurement_dashboard.erp_measurement_dashboard", "fas fa-ruler-combined"),
    ("drawing", "도면", "erp_drawing_workbench.erp_drawing_workbench_dashboard", "fas fa-drafting-compass"),
    ("production", "생산", "erp_production_page.erp_production_dashboard", "fas fa-industry"),
    ("shipment", "출고", "erp_shipment_page.erp_shipment_dashboard", "fas fa-truck"),
    ("as", "AS", "erp_as_page.erp_as_dashboard", "fas fa-tools"),
    ("construction", "시공", "erp_construction_page.erp_construction_dashboard", "fas fa-hammer"),
    ("completion", "완료", "erp_completion_page.erp_completion_dashboard", "fas fa-check-circle"),
    ("history", "이력", "erp_history.history_dashboard", "fas fa-history"),
    ("wdcalculator", "견적 계산기", "wdcalculator.wdcalculator", "fas fa-calculator"),
    ("my_commission", "내 수수료", "sales_commission_web.my_commission", "fas fa-coins"),
)


def freelancer_menu_items() -> list[dict[str, Any]]:
    """메뉴 항목 목록 — ``id`` · ``name``(=``label``) · ``url``(=``href``) · ``icon``. 요청 문맥 안에서 부른다.

    문지기가 여는 화면만 싣는다(열리지 않은 묶음은 메뉴에도 없다)."""
    items = []
    for item_id, label, endpoint, icon in FREELANCER_MENU:
        if endpoint not in FREELANCER_ALLOWED_ENDPOINTS:
            continue
        href = url_for(endpoint)
        items.append({"id": item_id, "name": label, "label": label, "url": href, "href": href, "icon": icon})
    return items


__all__ = ["FREELANCER_MENU", "freelancer_menu_items"]
