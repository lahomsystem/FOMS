"""WAM page/attachment view models and recursive serialization helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

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


@dataclass
class WamRequestContext:
    manager_id: str | None
    order_id: int
    request_token: str = ""
    issued_at: float | None = None
    token_type: str = "wam_launch"
    scopes: tuple[str, ...] = ("page", "attachments")
    source: str = "launch_token"
    mapped_foms_user_id: int | None = None
    allowed_sections: tuple[str, ...] = ()
    attachment_scope: str = "order"
    nonce: str | None = None

    def allows(self, scope: str) -> bool:
        return not self.scopes or scope in self.scopes

    def allows_section(self, section_key: str) -> bool:
        return not self.allowed_sections or section_key in self.allowed_sections

    def allows_attachment_order(self, order_id: int) -> bool:
        if self.attachment_scope == "none":
            return False
        if self.attachment_scope == "all":
            return True
        return self.attachment_scope == "order" and self.order_id == int(order_id)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "manager_id": self.manager_id,
            "order_id": self.order_id,
            "issued_at": self.issued_at,
            "token_type": self.token_type,
            "scopes": list(self.scopes),
            "source": self.source,
            "allowed_sections": list(self.allowed_sections),
            "attachment_scope": self.attachment_scope,
        }


@dataclass
class WamBadgeVM:
    label: str
    tone: str = "default"


@dataclass
class WamActionVM:
    key: str
    label: str
    href: str = "#"
    tone: str = "secondary"
    icon: str | None = None
    target: str | None = None
    disabled: bool = False
    visible: bool = True
    external: bool = False
    copy_value: str | None = None
    copy_label: str | None = None
    open_section: str | None = None
    scroll_target: str | None = None
    icon_only: bool = False
    aria_label: str | None = None


@dataclass
class AttachmentItemVM:
    id: int
    name: str
    file_type: str
    category: str
    category_label: str
    item_index: int | None
    created_at_label: str | None
    size_label: str | None
    open_url: str
    download_url: str
    thumbnail_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return vm_to_dict(self)


@dataclass
class AttachmentGroupVM:
    key: str
    title: str
    count: int
    preview_items: list[AttachmentItemVM] = field(default_factory=list)
    items: list[AttachmentItemVM] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return vm_to_dict(self)


@dataclass
class WamSectionVM:
    key: str
    title: str
    state: str = "ready"
    payload: dict[str, Any] = field(default_factory=dict)
    folded: bool = False
    expanded: bool | None = None
    group: str | None = None
    eyebrow: str | None = None
    description: str | None = None
    badge_label: str | None = None
    badge_tone: str = "neutral"
    meta: dict[str, Any] = field(default_factory=dict)
    empty_title: str | None = None
    empty_message: str | None = None
    error_title: str | None = None
    error_message: str | None = None
    lazy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return vm_to_dict(self)


@dataclass
class WamStickyActionBarVM:
    state: str = "hidden"
    primary_action: WamActionVM | None = None
    secondary_actions: list[WamActionVM] = field(default_factory=list)


@dataclass
class WamPageVM:
    page_state: str
    order_id: int
    header: dict[str, Any]
    summary_strip: dict[str, Any]
    sections: list[WamSectionVM]
    sticky_action_bar: WamStickyActionBarVM | dict[str, Any] | None
    title: str | None = None
    primary_sections: list[WamSectionVM] = field(default_factory=list)
    folded_sections: list[WamSectionVM] = field(default_factory=list)
    page_error: dict[str, Any] | None = None
    page_empty: dict[str, Any] | None = None
    flags: dict[str, Any] = field(default_factory=dict)
    info_banner: dict[str, Any] | None = None
    telemetry: dict[str, Any] = field(default_factory=dict)

    def get_section(self, key: str) -> WamSectionVM | None:
        for section in self.sections:
            if section.key == key:
                return section
        return None

    def to_dict(self) -> dict[str, Any]:
        return vm_to_dict(self)


def vm_to_dict(value: Any) -> Any:
    """Recursively convert WAM dataclasses into JSON-friendly dict/list structures."""
    if is_dataclass(value):
        return {key: vm_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: vm_to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [vm_to_dict(item) for item in value]
    return value
