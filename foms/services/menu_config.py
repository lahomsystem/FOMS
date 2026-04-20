"""메뉴 설정 서비스."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

__all__ = [
    "load_menu_config",
    "invalidate_menu_config_cache",
]

logger = logging.getLogger(__name__)

_MENU_CONFIG_CACHE = None
_MENU_CONFIG_MTIME = 0
_MENU_CONFIG_PATH = "data/admin/menu_config.json"


def load_menu_config() -> dict[str, Any]:
    """menu_config.json 로드, 없으면 기본 메뉴 반환 (캐시 지원)."""
    global _MENU_CONFIG_CACHE, _MENU_CONFIG_MTIME
    try:
        if os.path.exists(_MENU_CONFIG_PATH):
            mtime = os.path.getmtime(_MENU_CONFIG_PATH)
            if _MENU_CONFIG_CACHE is None or mtime != _MENU_CONFIG_MTIME:
                with open(_MENU_CONFIG_PATH, "r", encoding="utf-8") as file_obj:
                    _MENU_CONFIG_CACHE = json.load(file_obj)
                _MENU_CONFIG_MTIME = mtime
            return _MENU_CONFIG_CACHE
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load menu config from %s: %s", _MENU_CONFIG_PATH, exc)

    if _MENU_CONFIG_CACHE is None:
        return _default_menu_config()
    return _MENU_CONFIG_CACHE


def invalidate_menu_config_cache() -> None:
    """관리자 메뉴 저장 시 캐시 무효화"""
    global _MENU_CONFIG_CACHE
    _MENU_CONFIG_CACHE = None


def _default_menu_config() -> dict[str, Any]:
    """기본 메뉴 설정."""
    return {
        "main_menu": [
            {"id": "order_list", "name": "전체 주문", "url": "/"},
            {"id": "received", "name": "접수", "url": "/?status=RECEIVED"},
            {"id": "measured", "name": "실측", "url": "/?status=MEASURE"},
            {"id": "metro_orders", "name": "수도권 주문", "url": "/?region=metro"},
            {"id": "regional_orders", "name": "지방 주문", "url": "/?region=regional"},
            {"id": "storage_dashboard", "name": "수납장 대시보드", "url": "/storage_dashboard"},
            {"id": "regional_dashboard", "name": "지방 주문 대시보드", "url": "/regional_dashboard"},
            {
                "id": "self_measurement_dashboard",
                "name": "자가실측 대시보드",
                "url": "/self_measurement_dashboard",
            },
            {
                "id": "metropolitan_dashboard",
                "name": "수도권 주문 대시보드",
                "url": "/metropolitan_dashboard",
            },
            {"id": "trash", "name": "휴지통", "url": "/trash"},
            {"id": "chat", "name": "채팅", "url": "/chat"},
        ],
        "admin_menu": [
            {"id": "user_management", "name": "사용자 관리", "url": "/admin/users"},
            {"id": "security_logs", "name": "보안 로그", "url": "/admin/security-logs"},
        ],
    }
