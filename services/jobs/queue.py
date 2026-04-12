"""Legacy queue shim for the canonical namespaced jobs queue."""

from foms.services.jobs.queue import (
    enqueue_channeltalk_inbound,
    enqueue_channeltalk_push,
    enqueue_geocode_order_address,
    enqueue_thumbnail_generation,
    get_rq_queue,
    get_rq_runtime_status,
    get_rq_worker_count,
)

__all__ = [
    "get_rq_queue",
    "get_rq_worker_count",
    "get_rq_runtime_status",
    "enqueue_thumbnail_generation",
    "enqueue_geocode_order_address",
    "enqueue_channeltalk_push",
    "enqueue_channeltalk_inbound",
]

