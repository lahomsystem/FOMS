"""Compatibility shim for the canonical `foms.services.channel_wam_view_models` module."""

from foms.services.channel_wam_view_models import (
    AttachmentGroupVM,
    AttachmentItemVM,
    WamActionVM,
    WamBadgeVM,
    WamPageVM,
    WamRequestContext,
    WamSectionVM,
    WamStickyActionBarVM,
    vm_to_dict,
)

__all__ = [
    "WamRequestContext",
    "WamBadgeVM",
    "WamActionVM",
    "AttachmentItemVM",
    "AttachmentGroupVM",
    "WamSectionVM",
    "WamStickyActionBarVM",
    "WamPageVM",
    "vm_to_dict",
]
