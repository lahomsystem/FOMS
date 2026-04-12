"""Legacy tasks shim for the canonical namespaced jobs tasks."""

from foms.services.jobs.tasks import (
    create_thumbnail_for_attachment,
    geocode_order_address,
    process_channeltalk_inbound,
    push_order_to_channeltalk,
)

__all__ = [
    "create_thumbnail_for_attachment",
    "geocode_order_address",
    "push_order_to_channeltalk",
    "process_channeltalk_inbound",
]
