"""Canonical channel API surface."""

from foms.api.channel.channel_functions import channel_functions_bp
from foms.api.channel.channel_integration import channel_integration_bp
from foms.api.channel.channel_webhooks import channel_webhooks_bp
from foms.api.channel.channel_wam import (
    channel_shortlink_bp,
    channel_wam_api_bp,
    channel_wam_bp,
)

__all__ = [
    "channel_integration_bp",
    "channel_functions_bp",
    "channel_webhooks_bp",
    "channel_shortlink_bp",
    "channel_wam_bp",
    "channel_wam_api_bp",
]
