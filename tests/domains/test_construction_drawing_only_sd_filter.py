"""시공 카드 drawing_only 미리보기: drawing_current_files의 비도면 첨부 유출 차단.

production 버그: drawing_only=True 시공 카드가 sd['drawing_current_files']를 무조건
포함해 실측/일반 첨부(orders/<id>/attachments/*)가 카드에 노출됐다(삭제 파일은 404
깨진 썸네일). 진짜 도면은 orders/<id>/drawing/ 또는 orders/<id>/drawing_wizard/.
key 경로만으로 필터하므로 DB 없이 순수 함수로 검증한다.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from foms.services.construction_dashboard_display import (
    _collect_preview_items,
    _is_drawing_file_entry,
)


def test_is_drawing_file_entry_by_key_path():
    assert _is_drawing_file_entry({"key": "orders/1/drawing/d.png"}) is True
    assert _is_drawing_file_entry({"key": "orders/1/drawing_wizard/w.png"}) is True
    assert _is_drawing_file_entry({"key": "orders/1/attachments/m.png"}) is False
    assert _is_drawing_file_entry({}) is False
    assert _is_drawing_file_entry(
        {"view_url": "/api/files/view/orders/1/drawing/d.png"}
    ) is True


@patch(
    "foms.services.construction_dashboard_display.build_file_view_url",
    side_effect=lambda key: f"/files/{key}",
)
def test_collect_preview_items_drawing_only_filters_non_drawing_files(_mock_url):
    # order_id 없는 row → DB 조회 경로 우회, sd.drawing_current_files만 검증(순수).
    row = {
        "structured_data": {
            "drawing_current_files": [
                {"key": "orders/1/attachments/m.png", "filename": "m.png"},
                {"key": "orders/1/drawing/d.png", "filename": "d.png"},
                {"key": "orders/1/drawing_wizard/w.png", "filename": "w.png"},
            ]
        }
    }

    items_drawing_only = _collect_preview_items(row, MagicMock(), drawing_only=True)
    views = [item["view"] for item in items_drawing_only]
    assert not any("attachments/m.png" in v for v in views), views
    assert any("drawing/d.png" in v for v in views), views
    assert any("drawing_wizard/w.png" in v for v in views), views

    items_all = _collect_preview_items(row, MagicMock(), drawing_only=False)
    views_all = [item["view"] for item in items_all]
    assert any("attachments/m.png" in v for v in views_all), views_all
    assert any("drawing/d.png" in v for v in views_all), views_all
    assert any("drawing_wizard/w.png" in v for v in views_all), views_all
