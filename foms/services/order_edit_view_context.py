"""Shared GET context for order edit full page and HTMX split fragments."""

from __future__ import annotations

import json
from typing import Any

from models import Order
from foms.services.erp_order_flags import is_erp_order_record


def build_order_edit_get_context(order: Order) -> dict[str, Any]:
    """
    Build template variables for ``edit_order_body`` on GET.

    Args:
        order: Loaded Order ORM instance.

    Returns:
        Dict passed to ``render_template`` for edit surfaces.
    """
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

        erp_bootstrap = _build_erp_order_bootstrap(order)

    return {
        "order": order,
        "option_type": option_type,
        "online_options": online_options,
        "direct_options": direct_options,
        "erp_bootstrap": erp_bootstrap,
        "erp_order_active": bool(is_erp_order_record(order)),
    }
