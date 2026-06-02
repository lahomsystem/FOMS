"""Order event display SSOT — Korean timeline localization tests."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from foms.services import erp_mobile_order_display as mobile_display
from foms.services.order_event_display import (
    format_timeline_meta,
    translate_event_type_to_korean,
)


def test_translate_drawing_status_changed() -> None:
    assert translate_event_type_to_korean("DRAWING_STATUS_CHANGED") == "도면 상태 변경"


def test_unknown_event_type_falls_back_to_misc() -> None:
    assert translate_event_type_to_korean("TOTALLY_UNKNOWN_EVENT") == "기타 변경"


def test_stage_auto_transitioned_meta_uses_korean_stage() -> None:
    meta = format_timeline_meta(
        "STAGE_AUTO_TRANSITIONED",
        {"from": "MEASURE", "to": "DRAWING"},
        actor_name="홍길동",
        created_at=datetime(2026, 6, 2, 10, 30),
    )
    assert "도면" in meta
    assert "DRAWING" not in meta
    assert "실측" in meta
    assert "MEASURE" not in meta


def test_mobile_timeline_events_localizes_title_and_meta() -> None:
    ev = SimpleNamespace(
        event_type="STAGE_AUTO_TRANSITIONED",
        payload={"from": "MEASURE", "to": "DRAWING"},
        created_by=SimpleNamespace(name="김담당"),
        created_at=datetime(2026, 6, 2, 9, 0),
    )
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        ev
    ]

    items = mobile_display.mobile_timeline_events(mock_db, 1, limit=5)
    assert len(items) == 1
    assert items[0]["title"] == "단계 자동 전환"
    assert "도면" in items[0]["meta"]
    assert "DRAWING" not in items[0]["meta"]
