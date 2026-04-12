"""Compatibility shim for the canonical `foms.services.channel_wam_telemetry` module."""

from foms.services.channel_wam_telemetry import (
    ALLOWED_EVENTS,
    record_wam_telemetry,
)

__all__ = [
    "ALLOWED_EVENTS",
    "record_wam_telemetry",
]
