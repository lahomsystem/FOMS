"""Shared GET context for order edit full page and HTMX split fragments."""

from __future__ import annotations

import json
from typing import Any

from models import Order
from foms.services.erp_order_flags import is_erp_order_record


def build_order_edit_get_context(order: Order, user: Any | None = None) -> dict[str, Any]:
    """
    Build template variables for ``edit_order_body`` on GET.

    Args:
        order: Loaded Order ORM instance.

    Returns:
        Dict passed to ``render_template`` for edit surfaces.
    """
    # AUDIT-GAP-01 후속(2026-09-02): 이 폼은 flat 컬럼을 그대로 prefill 한다
    # (``value="{{ order.customer_name }}"``·``order.phone``). ERP 주문의 정본은
    # ``structured_data`` 인데 두 컬럼은 저장 경로에 따라 옛 값이 남아 있을 수 있어
    # (운영 활성 주문 130건), 그대로 두면 담당자가 **옛 번호를 보고 그대로 저장**해
    # 어긋남이 정본 쪽으로 되돌아간다. 대시보드 읽기 경로들이 이미 쓰는 표시 오버레이를
    # 여기서도 태워 **화면이 말하는 값 = 정본** 으로 맞춘다.
    if is_erp_order_record(order):
        from foms.services.erp_display import apply_erp_display_fields

        apply_erp_display_fields(order)

    option_type = "online"
    online_options = ""
    direct_options = {
        "product_name": "",
        "standard": "",
        "internal": "",
        "color": "",
        "option_detail": "",
        "handle": "",
        "misc": "",
        "quote": "",
    }

    options_raw = getattr(order, "options", None)
    if options_raw:
        try:
            options_data = json.loads(str(options_raw))
            if isinstance(options_data, dict):
                if "option_type" in options_data:
                    option_type = options_data["option_type"]
                    if option_type == "direct" and "details" in options_data:
                        for key in direct_options:
                            if key in options_data["details"]:
                                direct_options[key] = options_data["details"][key]
                    elif option_type == "online" and "online_options_summary" in options_data:
                        online_options = options_data["online_options_summary"]
                elif any(k in options_data for k in direct_options):
                    option_type = "direct"
                    for key in direct_options:
                        if key in options_data:
                            direct_options[key] = options_data[key]
                elif any(
                    k in options_data
                    for k in ["제품명", "규격", "내부", "색상", "상세옵션", "손잡이", "기타", "견적내용"]
                ):
                    option_type = "direct"
                    key_map = {
                        "제품명": "product_name",
                        "규격": "standard",
                        "내부": "internal",
                        "색상": "color",
                        "상세옵션": "option_detail",
                        "손잡이": "handle",
                        "기타": "misc",
                        "견적내용": "quote",
                    }
                    for kor, eng in key_map.items():
                        if kor in options_data:
                            direct_options[eng] = options_data[kor]
                else:
                    option_type = "online"
                    online_options = str(options_raw or "")
            else:
                option_type = "online"
                online_options = str(options_raw or "")
        except json.JSONDecodeError:
            option_type = "online"
            online_options = str(options_raw or "") if options_raw else ""

    erp_bootstrap = None
    if is_erp_order_record(order):
        from foms.web.orders.edit import _build_erp_order_bootstrap

        erp_bootstrap = _build_erp_order_bootstrap(order, user=user)

    # AS 기준 일정 드리프트 배너(주문 상세 최상단). 세 표면(전체 편집 페이지 · 태블릿 split
    # 패널 · HTMX 상세 fragment)이 모두 이 컨텍스트를 거치므로 여기 한 곳에서 계산한다.
    # 지연 import: as_dashboard_display 는 models/foms.api.files 를 끌고 와 모듈 로드 순환을
    # 만들 수 있다(이 모듈은 edit.py·fragment.py 가 import 시점에 로드한다).
    from db import get_db
    from foms.services.as_dashboard_display import build_schedule_link_drift

    return {
        "order": order,
        "option_type": option_type,
        "online_options": online_options,
        "direct_options": direct_options,
        "erp_bootstrap": erp_bootstrap,
        "erp_order_active": bool(is_erp_order_record(order)),
        "as_schedule_drift": build_schedule_link_drift(
            getattr(order, "structured_data", None), get_db()
        ),
    }
