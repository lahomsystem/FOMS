"""ERP mobile v2 display helpers — attachment URL strategy."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from foms.services import erp_mobile_order_display as display

ROOT = Path(__file__).resolve().parents[2]


def test_attachment_urls_split_thumb_and_full_view() -> None:
    att = SimpleNamespace(
        storage_key="orders/1/photo.jpg",
        thumbnail_key="orders/1/thumb_photo.jpg",
        file_type="image",
        filename="photo.jpg",
    )
    with patch.object(display, "build_file_view_url", side_effect=lambda k: f"/view/{k}"):
        assert display._attachment_thumbnail_url(att) == "/view/orders/1/thumb_photo.jpg"
        assert display._attachment_full_view_url(att) == "/view/orders/1/photo.jpg"
        assert display._attachment_image_url(att) == "/view/orders/1/thumb_photo.jpg"


def test_mobile_attachment_items_splits_thumb_and_full_view() -> None:
    att = SimpleNamespace(
        id=7,
        order_id=1,
        filename="photo.jpg",
        file_type="image",
        category="measurement",
        storage_key="orders/1/photo.jpg",
        thumbnail_key="orders/1/thumb_photo.jpg",
        created_at=None,
    )
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        att
    ]

    with patch.object(display, "build_file_view_url", side_effect=lambda k: f"/view/{k}"):
        with patch.object(display, "build_file_download_url", return_value="/dl/photo.jpg"):
            items = display.mobile_attachment_items(mock_db, 1, limit=8)

    assert len(items) == 1
    assert items[0]["thumb_url"] == "/view/orders/1/thumb_photo.jpg"
    assert items[0]["view_url"] == "/view/orders/1/photo.jpg"
    assert items[0]["thumb_url"] != items[0]["view_url"]


def test_mobile_detail_partial_prefers_view_url_for_grid_img() -> None:
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert 'src="{{ att.view_url or att.thumb_url }}"' in partial
    assert 'data-foms-attachment-view-url="{{ att.view_url or att.thumb_url }}"' in partial


def test_erp_mobile_tile_prefers_view_url_for_grid_src() -> None:
    shared_js = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "const gridImageSrc =" in shared_js
    assert "isMobileLayout" in shared_js
    assert "(a.view_url || a.thumbnail_view_url || '')" in shared_js
