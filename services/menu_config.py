"""Compatibility shim for the canonical `foms.services.menu_config` module."""

from foms.services.menu_config import (
    invalidate_menu_config_cache,
    load_menu_config,
)

__all__ = [
    "load_menu_config",
    "invalidate_menu_config_cache",
]
