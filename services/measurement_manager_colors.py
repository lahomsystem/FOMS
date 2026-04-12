"""Compatibility shim for the canonical `foms.services.measurement_manager_colors` module."""

from foms.services.measurement_manager_colors import (
    DEFAULT_MEASUREMENT_MANAGER_BG_COLOR,
    DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR,
    MEASUREMENT_MANAGER_PALETTE,
    build_measurement_manager_color_map,
    build_measurement_manager_sort_order_map,
    normalize_measurement_manager_key,
    resolve_measurement_manager_color,
)

__all__ = [
    "MEASUREMENT_MANAGER_PALETTE",
    "DEFAULT_MEASUREMENT_MANAGER_BG_COLOR",
    "DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR",
    "normalize_measurement_manager_key",
    "build_measurement_manager_sort_order_map",
    "build_measurement_manager_color_map",
    "resolve_measurement_manager_color",
]
