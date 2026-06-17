from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from flask import Flask, g

import foms.services.context_processors as context_processors
import foms.services.menu_config as menu_config_module
from foms.services.menu_config import invalidate_menu_config_cache, load_menu_config


@pytest.fixture(autouse=True)
def restore_menu_config_module_state():
    original_path = menu_config_module._MENU_CONFIG_PATH
    original_cache = menu_config_module._MENU_CONFIG_CACHE
    original_mtime = menu_config_module._MENU_CONFIG_MTIME

    try:
        yield
    finally:
        menu_config_module._MENU_CONFIG_PATH = original_path
        menu_config_module._MENU_CONFIG_CACHE = original_cache
        menu_config_module._MENU_CONFIG_MTIME = original_mtime


def _reset_menu_cache(tmp_path) -> None:
    menu_config_module._MENU_CONFIG_PATH = str(tmp_path)
    menu_config_module._MENU_CONFIG_CACHE = None
    menu_config_module._MENU_CONFIG_MTIME = 0


def test_load_menu_config_returns_default_when_file_is_missing(tmp_path) -> None:
    _reset_menu_cache(tmp_path / "missing_menu_config.json")

    menu = load_menu_config()

    assert "main_menu" in menu
    assert "admin_menu" in menu
    assert menu["main_menu"][0]["id"] == "order_list"


def test_load_menu_config_reloads_json_after_cache_invalidation(tmp_path) -> None:
    menu_path = tmp_path / "menu_config.json"
    _reset_menu_cache(menu_path)
    menu_path.write_text(
        json.dumps({"main_menu": [{"id": "one", "name": "첫 메뉴", "url": "/one"}], "admin_menu": []}),
        encoding="utf-8",
    )

    first_menu = load_menu_config()

    menu_path.write_text(
        json.dumps({"main_menu": [{"id": "two", "name": "둘 메뉴", "url": "/two"}], "admin_menu": []}),
        encoding="utf-8",
    )
    invalidate_menu_config_cache()
    second_menu = load_menu_config()

    assert first_menu["main_menu"][0]["id"] == "one"
    assert second_menu["main_menu"][0]["id"] == "two"


def test_load_menu_config_falls_back_to_default_and_logs_when_json_is_invalid(tmp_path, caplog) -> None:
    menu_path = tmp_path / "menu_config.json"
    _reset_menu_cache(menu_path)
    menu_path.write_text("{broken", encoding="utf-8")

    with caplog.at_level("WARNING"):
        menu = load_menu_config()

    assert menu["main_menu"][0]["id"] == "order_list"
    assert "Failed to load menu config" in caplog.text


def test_inject_menu_limits_construction_team_navigation(monkeypatch) -> None:
    app = Flask(__name__)
    monkeypatch.setattr(
        context_processors,
        "load_menu_config",
        lambda: {
            "main_menu": [{"id": "order_list", "name": "전체 주문", "url": "/"}],
            "admin_menu": [],
        },
    )
    monkeypatch.setattr(
        context_processors,
        "url_for",
        lambda endpoint: {
            "erp_shipment_page.erp_shipment_dashboard": "/erp/shipment",
            "erp_construction_page.erp_construction_dashboard": "/erp/construction",
            "erp_completion_page.erp_completion_dashboard": "/erp/completion",
            "erp_history.history_dashboard": "/erp/history",
        }[endpoint],
    )

    with app.test_request_context("/"):
        g.current_user = SimpleNamespace(team="CONSTRUCTION")
        injected = context_processors.inject_menu()

    assert injected["menu"]["main_menu"] == [
        {"id": "shipment", "name": "출고", "url": "/erp/shipment"},
        {"id": "construction", "name": "시공", "url": "/erp/construction"},
        {"id": "completion", "name": "완료", "url": "/erp/completion"},
        {"id": "history", "name": "이력", "url": "/erp/history"},
    ]


def test_inject_menu_preserves_loaded_menu_for_non_construction(monkeypatch) -> None:
    app = Flask(__name__)
    source_menu = {
        "main_menu": [{"id": "order_list", "name": "전체 주문", "url": "/"}],
        "admin_menu": [],
    }
    monkeypatch.setattr(context_processors, "load_menu_config", lambda: source_menu)

    with app.test_request_context("/"):
        g.current_user = SimpleNamespace(team="SALES")
        injected = context_processors.inject_menu()

    assert injected["menu"] == source_menu
