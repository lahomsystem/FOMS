"""협력사 '도면 작업 중' 목록 — 도면팀이 저장한 도면 썸네일.

다른 단계 · 다른 주문 키 · 그림이 아닌 파일은 빠진다.
"""

from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Order, User
from tests.security.partner_fixtures import (  # noqa: F401
    _client,
    _create,
    _to_stage,
    world,
)
from tests.security.test_partner_order_list import _board, _order


def _save_drawings(order_id: int, pending: dict, files: list | None = None) -> None:
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data or {})
    sd["drawing_wizard"] = {"pending": pending, "sheets": [{"id": "s", "objects": [{"t": 1}]}]}
    if files is not None:
        sd["drawing_current_files"] = files
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def test_drawing_stage_lists_saved_images_only(app, world):
    """저장 PNG 와 전달된 그림만. PDF · 다른 주문 · 시트 JSON 은 빠진다."""
    drawing = _order(app, world["partner_a"], "도면고객")
    measure = _order(app, world["partner_a"], "접수고객")
    _to_stage(drawing, "DRAWING")
    own = f"orders/{drawing}/drawing_wizard/exports/molding.png"
    transferred = f"orders/{drawing}/drawing/sent.jpg"
    _save_drawings(drawing, {
        "s1": {"key": own, "filename": "molding.png", "sheet_name": "몰딩"},
        "pdf": {"key": f"orders/{drawing}/drawing_wizard/exports/note.pdf", "filename": "note.pdf"},
        "other": {"key": "orders/999/drawing_wizard/exports/x.png", "filename": "x.png"},
        "dot": {"key": f"orders/{drawing}/drawing_wizard/../exports/z.png", "filename": "z.png"},
    }, files=[
        {"key": transferred, "filename": "sent.jpg"},
        {"key": own, "filename": "molding.png"},
    ])
    _save_drawings(measure, {
        "s1": {"key": f"orders/{measure}/drawing_wizard/exports/a.png", "filename": "a.png", "sheet_name": "초안"},
    })

    rows = {row["id"]: row for row in _board(world, stage="도면 작업 중")["orders"]}
    thumbs = rows[drawing]["drawing_thumbs"]
    assert [t["label"] for t in thumbs] == ["몰딩", "sent.jpg"]
    assert thumbs[0]["url"].endswith(f"orders/{drawing}/drawing_wizard/exports/molding.png")
    assert rows[drawing]["drawing_thumbs_more"] == 0
    assert measure not in rows

    measure_row = next(row for row in _board(world)["orders"] if row["id"] == measure)
    assert measure_row["drawing_thumbs"] == []


def test_extra_sheets_are_counted_not_all_loaded(app, world):
    """다섯 장이면 썸네일 4장과 남은 수 1이다."""
    drawing = _order(app, world["partner_a"], "여러장")
    _to_stage(drawing, "DRAWING")
    pending = {
        f"s{i}": {
            "key": f"orders/{drawing}/drawing_wizard/exports/{i}.png",
            "filename": f"{i}.png",
            "sheet_name": f"시트{i}",
        }
        for i in range(5)
    }
    _save_drawings(drawing, pending)

    row = _board(world, stage="도면 작업 중")["orders"][0]
    assert len(row["drawing_thumbs"]) == 4
    assert row["drawing_thumbs_more"] == 1


def test_list_page_renders_the_thumbnail(app, world):
    """도면 작업 중 화면에 저장 도면 주소가 있고, 다른 단계 화면에는 없다."""
    drawing = _order(app, world["partner_a"], "그림고객")
    _to_stage(drawing, "DRAWING")
    key = f"orders/{drawing}/drawing_wizard/exports/sheet.png"
    _save_drawings(drawing, {"s1": {"key": key, "filename": "sheet.png", "sheet_name": "장"}})

    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get("/partner?stage=도면 작업 중").get_data(as_text=True)
    assert f"/api/files/view/{key}" in page
    assert 'class="pp-draw-thumbs"' in page
    assert "그림고객" in page
    other = client.get("/partner?stage=접수 확인 중").get_data(as_text=True)
    assert key not in other
