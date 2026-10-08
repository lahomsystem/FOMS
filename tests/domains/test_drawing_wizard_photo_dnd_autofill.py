"""도면 마법사 — 실측 사진 끌어놓기 · 자동 채움 다이얼로그 문자열 계약."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
HTML = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    start = JS.index(f"function {name}(")
    nxt = JS.find("\n  function ", start + 10)
    return JS[start:nxt]


def test_photo_drag_uses_custom_type_and_keeps_file_drop():
    assert "PHOTO_DRAG_TYPE = 'application/x-dws-photo'" in JS
    dnd = _fn("bindCanvasDnd")
    assert "isPhotoDrag" in dnd and "isFileDrag" in dnd
    assert "getData(PHOTO_DRAG_TYPE)" in dnd
    assert "dropLogicalPos(e)" in dnd
    assert "addImagesFromFiles(files, dropLogicalPos(e))" in dnd


def test_photo_thumbnail_draggable_on_desktop_only_and_click_kept():
    assert "setData(PHOTO_DRAG_TYPE, photo.key)" in JS
    assert "!isTouchOnly()" in JS
    assert "cell.addEventListener('click', function () { onPhotoClick(photo, cell); })" in JS


def test_photo_insert_default_480_long_side_via_import_attachment():
    assert "PHOTO_MAX_LONG = 480" in JS
    click = _fn("onPhotoClick")
    assert "function onPhotoClick(photo, cell, pos)" in click
    assert "/drawing-wizard/import-attachment" in click
    assert "placeImageFromKey(r.data.data.key, pos || null, 0, PHOTO_MAX_LONG)" in click
    assert "function placeImageFromKey(key, pos, cascade, maxLong)" in JS


def test_autofill_uses_dialog_not_confirm():
    af = _fn("autofill")
    assert "confirm(" not in af
    assert "dws-autofill-dialog" in af
    for label in ("빈 칸만 채우기", "모두 덮어쓰기", "이 시트만", "모든 시트"):
        assert label in HTML
    assert 'id="dws-autofill-mode-empty" value="empty" checked' in HTML
    assert 'id="dws-autofill-scope-current" value="current" checked' in HTML
    assert 'id="dws-autofill-count"' in HTML


def test_autofill_counts_changes_and_uses_per_sheet_product_data():
    assert "바뀔 칸 " in _fn("refreshAutofillPreview")
    fetch = _fn("fetchSheetDefaults")
    assert "'/drawing-wizard?item=' + idx" in fetch
    assert "sheet.product_index" in fetch


def test_autofill_apply_records_undo_and_marks_dirty():
    apply = _fn("applyAutofill")
    assert "recordUndo()" in apply
    assert "markDirty()" in apply


def test_autofill_dialog_styles_in_css_no_inline_style():
    assert ".dws-autofill-group" in CSS
    start = HTML.index('id="dws-autofill-dialog"')
    block = HTML[start:HTML.index("</dialog>", start)]
    assert "style=" not in block
