"""Compatibility shim for the canonical `foms.services.map_snapshot` module."""

from foms.services.map_snapshot import (
    build_measurement_map_query,
    build_measurement_snapshot,
)

__all__ = ["build_measurement_map_query", "build_measurement_snapshot"]
