"""
ERP Policy (룰/정책) — legacy import path.

Canonical implementation lives in ``foms.services.erp_policy``.
"""

from foms.services.erp_policy import *  # noqa: F403

import foms.services.erp_policy as _canonical

__all__ = list(_canonical.__all__)
