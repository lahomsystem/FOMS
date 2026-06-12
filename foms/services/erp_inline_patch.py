"""Partial structured_data field patches for mobile inline edit (P1-04)."""

from __future__ import annotations

import copy
import re
from typing import Any

CRITICAL_FIELD_SUFFIXES = frozenset(
    {
        "parties.customer.phone",
        "site.address_full",
        "schedule.measurement.date",
        "schedule.construction.date",
        "price",
        "measurement_date",
        "construction_date",
    }
)

_ITEM_FIELD_RE = re.compile(r"^items\.(\d+)\.([a-z_]+)$")


def is_critical_field(field: str) -> bool:
    """Return whether a dotted field path requires explicit save UX."""
    normalized = (field or "").strip()
    if normalized in CRITICAL_FIELD_SUFFIXES:
        return True
    match = _ITEM_FIELD_RE.match(normalized)
    if not match:
        return False
    return match.group(2) in {"price", "measurement_date", "construction_date"}


def _ensure_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _ensure_items(structured: dict[str, Any], index: int) -> dict[str, Any]:
    items = structured.get("items")
    if not isinstance(items, list):
        items = []
        structured["items"] = items
    while len(items) <= index:
        items.append({})
    item = items[index]
    if not isinstance(item, dict):
        item = {}
        items[index] = item
    return item


def apply_field_patch(structured_data: dict[str, Any], field: str, value: Any) -> dict[str, Any]:
    """Apply one dotted-path patch onto a deep-copied structured_data dict."""
    if not isinstance(structured_data, dict):
        raise ValueError("structured_data must be an object")
    path = (field or "").strip()
    if not path:
        raise ValueError("field required")

    updated = copy.deepcopy(structured_data)
    item_match = _ITEM_FIELD_RE.match(path)
    if item_match:
        idx = int(item_match.group(1))
        key = item_match.group(2)
        item = _ensure_items(updated, idx)
        if key == "spec_rows" and isinstance(value, list):
            item[key] = value
        else:
            item[key] = "" if value is None else str(value)
        return updated

    if path == "parties.customer.phone":
        customer = _ensure_dict(_ensure_dict(updated, "parties"), "customer")
        customer["phone"] = "" if value is None else str(value)
        return updated
    if path == "parties.customer.name":
        customer = _ensure_dict(_ensure_dict(updated, "parties"), "customer")
        customer["name"] = "" if value is None else str(value)
        return updated
    if path == "site.address_full":
        site = _ensure_dict(updated, "site")
        site["address_full"] = "" if value is None else str(value)
        return updated
    if path.startswith("schedule."):
        parts = path.split(".")
        if len(parts) != 3:
            raise ValueError(f"unsupported schedule path: {path}")
        bucket = _ensure_dict(_ensure_dict(updated, "schedule"), parts[1])
        bucket[parts[2]] = "" if value is None else str(value)
        return updated
    if path == "notes":
        updated["notes"] = "" if value is None else str(value)
        return updated

    raise ValueError(f"unsupported field path: {path}")
