"""Canonical orders service surface.

패키지 import 만으로 ``erp_order_detail`` 등을 끌어오면 ``erp_display`` 로딩 중에
순환 import 가 난다(SIDEFX worker 가 알림톡 handler 를 부를 때 재현). 쓰는 이름만
늦게 불러 그 순환을 끊는다.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "erp_order_detail",
    "estimate_service",
    "order_date_sync",
    "order_date_sync_event",
    "order_display_utils",
    "order_geocode",
    "order_storage_cleanup",
]

_EXPORTS = {
    "erp_order_detail": "foms.services.erp_order_detail",
    "estimate_service": "foms.services.estimate_service",
    "order_date_sync": "foms.services.order_date_sync",
    "order_date_sync_event": "foms.services.order_date_sync_event",
    "order_display_utils": "foms.services.order_display_utils",
    "order_geocode": "foms.services.order_geocode",
    "order_storage_cleanup": "foms.services.order_storage_cleanup",
}


def __getattr__(name: str) -> Any:
    """공개 이름만 늦게 불러 순환 import 를 피한다."""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(target)
    globals()[name] = module
    return module
