"""Compatibility shim for the canonical `foms.services.channel_inbound` module."""

from foms.services.channel_inbound import (
    extract_keys,
    generate_payload_hash,
    parse_order_text,
    process_inbound_job,
    receive_webhook,
)

__all__ = [
    "generate_payload_hash",
    "extract_keys",
    "receive_webhook",
    "parse_order_text",
    "process_inbound_job",
]
