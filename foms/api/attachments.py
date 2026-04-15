"""Canonical attachments API surface."""

from foms.services.order_attachment_thumbnail import schedule_order_attachment_thumbnail_generation
from foms.services.storage import get_storage
from foms.services.user_deletion import ensure_order_attachment_user_fk_set_null

from foms.api.attachments_internal.blueprint import (
    ASYNC_ATTACHMENT_THUMBNAIL,
    USE_DIRECT_UPLOAD,
    attachments_bp,
)
from foms.api.attachments_internal.common import (
    ATTACHMENT_CATEGORIES,
    DRAWING_ATTACHMENT_EXTRA_EXTENSIONS,
    _att_key,
    allowed_erp_attachment_file,
    get_erp_media_max_size,
    normalize_attachment_category,
    parse_attachment_item_index,
    resolve_attachment_category,
    serialize_attachment,
)
from foms.api.attachments_internal.direct_upload import (
    api_order_attachments_complete,
    api_upload_session,
    api_upload_session_batch,
)
from foms.api.attachments_internal.legacy import (
    ensure_order_attachments_category_column,
    ensure_order_attachments_item_index_column,
    ensure_order_attachments_user_id_column,
)
from foms.api.attachments_internal.order_routes import (
    api_order_attachments_delete,
    api_order_attachments_list,
    api_order_attachments_patch,
    api_order_attachments_upload,
)
from foms.api.attachments_internal.search import api_search_attachments

__all__ = [
    "ASYNC_ATTACHMENT_THUMBNAIL",
    "ATTACHMENT_CATEGORIES",
    "DRAWING_ATTACHMENT_EXTRA_EXTENSIONS",
    "USE_DIRECT_UPLOAD",
    "_att_key",
    "allowed_erp_attachment_file",
    "api_order_attachments_complete",
    "api_order_attachments_delete",
    "api_order_attachments_list",
    "api_order_attachments_patch",
    "api_order_attachments_upload",
    "api_search_attachments",
    "api_upload_session",
    "api_upload_session_batch",
    "attachments_bp",
    "ensure_order_attachments_category_column",
    "ensure_order_attachments_item_index_column",
    "ensure_order_attachments_user_id_column",
    "ensure_order_attachment_user_fk_set_null",
    "get_erp_media_max_size",
    "get_storage",
    "normalize_attachment_category",
    "parse_attachment_item_index",
    "resolve_attachment_category",
    "schedule_order_attachment_thumbnail_generation",
    "serialize_attachment",
]
