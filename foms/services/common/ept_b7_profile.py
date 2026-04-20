"""EPT-B7: optional server timing headers for template render (profiling; not a cache)."""

from __future__ import annotations

import logging

from flask import Response

logger = logging.getLogger(__name__)

HEADER_ROUTE = "X-FOMS-EPT-B7-ROUTE"
HEADER_RENDER_MS = "X-FOMS-EPT-B7-RENDER-MS"


def apply_ept_b7_render_headers(response: Response, *, route_id: str, render_ms: float) -> None:
    """Attach render-only timing. Safe for proxies: diagnostic, not authorization."""
    response.headers[HEADER_ROUTE] = route_id
    response.headers[HEADER_RENDER_MS] = f"{render_ms:.1f}"
    logger.info("[EPT-B7] route=%s render_ms=%.1f", route_id, render_ms)
