"""Compatibility shim for the canonical `foms.services.rate_limit` module."""

from foms.services.rate_limit import init_limiter

__all__ = ["init_limiter"]
