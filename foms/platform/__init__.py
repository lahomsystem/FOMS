"""Platform bootstrap helpers for the Flask app entrypoint."""

from .app_factory import AppFactoryResult, build_app
from .blueprints import BlueprintBindings, register_blueprints
from .realtime import RealtimeBindings, init_realtime_bootstrap

__all__ = [
    "AppFactoryResult",
    "BlueprintBindings",
    "RealtimeBindings",
    "build_app",
    "init_realtime_bootstrap",
    "register_blueprints",
]
"""Platform namespace for future runtime bootstrap modules."""

