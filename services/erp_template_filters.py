"""Compatibility shim for the canonical `foms.services.erp_template_filters` module."""

from foms.services.erp_template_filters import (
    format_phone_filter,
    item_spec_w300_display,
    item_spec_w300_value,
    payment_confirmed_bool,
    register_erp_template_filters,
    schedule_datetime_display,
    spec_w300_filter,
    spec_w300_value,
    split_count_filter,
    split_list_filter,
    strip_product_w_filter,
)

__all__ = [
    "split_count_filter",
    "split_list_filter",
    "strip_product_w_filter",
    "spec_w300_filter",
    "format_phone_filter",
    "spec_w300_value",
    "item_spec_w300_display",
    "item_spec_w300_value",
    "schedule_datetime_display",
    "payment_confirmed_bool",
    "register_erp_template_filters",
]
