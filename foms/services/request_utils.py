"""Request-related helpers for preserving list filter state."""

from typing import Any

__all__ = ["get_preserved_filter_args"]


def get_preserved_filter_args(request_args: Any) -> dict[str, Any]:
    """Return redirect query params that should survive list/detail actions."""
    redirect_args: dict[str, Any] = {}
    preserved_params = [
        "search",
        "status",
        "region",
        "page",
        "sort",
        "direction",
        "sort_by",
        "sort_order",
    ]
    preserved_params += [key for key in request_args.keys() if key.startswith("filter_")]
    for key in preserved_params:
        if key in request_args:
            redirect_args[key] = request_args.get(key)
    return redirect_args
