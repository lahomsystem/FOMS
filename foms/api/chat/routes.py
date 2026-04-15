"""Legacy chat API route wrapper (Quest 3~10)."""

from foms.services.storage import get_storage

from foms.api.chat.blueprint import chat_bp
from foms.api.chat.routes_files import (  # noqa: F401
    api_chat_download,
    api_chat_preview,
    api_chat_upload,
    api_chat_upload_complete,
    api_chat_upload_session,
)
from foms.api.chat.routes_messages import (  # noqa: F401
    api_chat_get_message,
    api_chat_mark_read,
    api_chat_search,
    api_chat_send_message,
    api_chat_users_list,
)
from foms.api.chat.routes_pages import (  # noqa: F401
    USE_DIRECT_UPLOAD,
    _chat_use_direct_upload,
    chat,
    chat_scripts_js,
)
from foms.api.chat.routes_rooms import (  # noqa: F401
    api_chat_order_detail,
    api_chat_rooms_add_member,
    api_chat_rooms_create,
    api_chat_rooms_delete,
    api_chat_rooms_detail,
    api_chat_rooms_list,
    api_chat_rooms_remove_member,
    api_chat_rooms_update,
    api_chat_search_orders,
)


__all__ = [
    "USE_DIRECT_UPLOAD",
    "_chat_use_direct_upload",
    "api_chat_download",
    "api_chat_get_message",
    "api_chat_mark_read",
    "api_chat_order_detail",
    "api_chat_preview",
    "api_chat_rooms_add_member",
    "api_chat_rooms_create",
    "api_chat_rooms_delete",
    "api_chat_rooms_detail",
    "api_chat_rooms_list",
    "api_chat_rooms_remove_member",
    "api_chat_rooms_update",
    "api_chat_search",
    "api_chat_search_orders",
    "api_chat_send_message",
    "api_chat_upload",
    "api_chat_upload_complete",
    "api_chat_upload_session",
    "api_chat_users_list",
    "chat",
    "chat_bp",
    "chat_scripts_js",
    "get_storage",
]
