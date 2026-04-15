"""Tests for ERP product item helpers."""

from types import SimpleNamespace

import models

import foms.services.erp_product_items as erp_product_items


class _FakeColumn:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def in_(self, values):
        return ("in", self.name, tuple(values))

    def desc(self):
        return ("desc", self.name)


class _FakeOrderAttachment:
    order_id = _FakeColumn("order_id")
    category = _FakeColumn("category")
    created_at = _FakeColumn("created_at")


class _FakeQuery:
    def __init__(self, attachments) -> None:
        self._attachments = attachments

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return list(self._attachments)


class _FakeDb:
    def __init__(self, attachments) -> None:
        self.attachments = attachments

    def query(self, _model):
        return _FakeQuery(self.attachments)


def _patch_order_attachment_model(monkeypatch) -> None:
    monkeypatch.setattr(models, "OrderAttachment", _FakeOrderAttachment)
    monkeypatch.setattr(erp_product_items, "OrderAttachment", _FakeOrderAttachment)


def test_build_product_items_for_order_normalizes_dimensions_and_maps_photos(monkeypatch) -> None:
    _patch_order_attachment_model(monkeypatch)
    db = _FakeDb(
        [
            SimpleNamespace(
                order_id=11,
                filename="front.jpg",
                storage_key="files/front",
                item_index="0",
                created_at="2026-04-08T09:00:00",
            ),
            SimpleNamespace(
                order_id=11,
                filename="ignored.jpg",
                storage_key="files/ignored",
                item_index="bad-index",
                created_at="2026-04-08T08:00:00",
            ),
        ]
    )
    order = SimpleNamespace(
        id=11,
        structured_data={
            "items": [
                {"name": "Upper", "spec_width": "1200", "depth": "600"},
                "skip-me",
                {"name": "Lower", "width": "800", "spec_height": "900"},
            ]
        },
    )

    product_items = erp_product_items.build_product_items_for_order(db, order)

    assert len(product_items) == 2
    assert product_items[0]["width"] == "1200"
    assert product_items[0]["depth"] == "600"
    assert product_items[0]["height"] == ""
    assert product_items[0]["measurement_images"] == [
        {
            "filename": "front.jpg",
            "view_url": "/api/files/view/files/front",
            "download_url": "/api/files/download/files/front",
            "key": "files/front",
            "item_index": 0,
        }
    ]
    assert product_items[1]["width"] == "800"
    assert product_items[1]["depth"] == ""
    assert product_items[1]["height"] == "900"
    assert product_items[1]["measurement_images"] == []


def test_build_product_items_for_orders_batches_attachment_mapping(monkeypatch) -> None:
    _patch_order_attachment_model(monkeypatch)
    db = _FakeDb(
        [
            SimpleNamespace(
                order_id=21,
                filename="item-1.jpg",
                storage_key="files/item-1",
                item_index="1",
                created_at="2026-04-08T09:00:00",
            ),
            SimpleNamespace(
                order_id=22,
                filename="item-2.jpg",
                storage_key="files/item-2",
                item_index="0",
                created_at="2026-04-08T08:30:00",
            ),
        ]
    )
    orders = [
        SimpleNamespace(
            id=21,
            structured_data={"products": [{"name": "A"}, {"name": "B", "spec_depth": "700"}]},
        ),
        SimpleNamespace(
            id=22,
            structured_data={"product_items": {"name": "Single", "spec_width": "500"}},
        ),
    ]

    erp_product_items.build_product_items_for_orders(db, orders)

    assert orders[0].product_items[0]["measurement_images"] == []
    assert orders[0].product_items[1]["depth"] == "700"
    assert orders[0].product_items[1]["measurement_images"] == [
        {
            "filename": "item-1.jpg",
            "view_url": "/api/files/view/files/item-1",
            "download_url": "/api/files/download/files/item-1",
            "key": "files/item-1",
            "item_index": 1,
        }
    ]
    assert len(orders[1].product_items) == 1
    assert orders[1].product_items[0]["spec_width"] == "500"
    assert orders[1].product_items[0]["width"] == "500"
    assert orders[1].product_items[0]["depth"] == ""
    assert orders[1].product_items[0]["height"] == ""
    assert orders[1].product_items[0]["measurement_images"] == [
        {
            "filename": "item-2.jpg",
            "view_url": "/api/files/view/files/item-2",
            "download_url": "/api/files/download/files/item-2",
            "key": "files/item-2",
            "item_index": 0,
        }
    ]


def test_build_product_items_for_orders_sets_empty_lists_when_ids_are_missing(monkeypatch) -> None:
    _patch_order_attachment_model(monkeypatch)
    db = _FakeDb([])
    orders = [
        SimpleNamespace(id=None, structured_data={"items": [{"name": "No ID"}]}),
        SimpleNamespace(structured_data={}),
    ]

    erp_product_items.build_product_items_for_orders(db, orders)

    assert orders[0].product_items == []
    assert orders[1].product_items == []
