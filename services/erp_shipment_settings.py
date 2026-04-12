"""Compatibility shim for the canonical `foms.services.erp_shipment_settings` module."""

from foms.services.erp_shipment_settings import (
    DEFAULT_ERP_WORKER_CAPACITY,
    ERP_SHIPMENT_SETTINGS_KEY,
    ERP_SHIPMENT_SETTINGS_PATH,
    is_order_assigned_to_user_for_construction,
    is_order_mine_for_user,
    load_erp_shipment_settings,
    normalize_erp_shipment_workers,
    normalize_measurement_managers,
    save_erp_shipment_settings,
)

__all__ = [
    "ERP_SHIPMENT_SETTINGS_KEY",
    "ERP_SHIPMENT_SETTINGS_PATH",
    "DEFAULT_ERP_WORKER_CAPACITY",
    "normalize_measurement_managers",
    "normalize_erp_shipment_workers",
    "is_order_assigned_to_user_for_construction",
    "is_order_mine_for_user",
    "load_erp_shipment_settings",
    "save_erp_shipment_settings",
]

