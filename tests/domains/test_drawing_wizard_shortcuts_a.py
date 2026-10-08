"""마법사 포토샵식 단축키 A 계약: 전체 선택·해제·제자리 복제·층 순서·도구 키."""
from pathlib import Path

JS = Path("static/js/drawing/wizard.js").read_text(encoding="utf-8")


def test_select_all_and_deselect():
    assert "function selectAllOnSheet()" in JS
    assert "e.code === 'KeyA')) {\n        e.preventDefault(); selectAllOnSheet(); return;" in JS
    assert "e.code === 'KeyD')) {\n        e.preventDefault(); deselect(); return;" in JS


def test_duplicate_in_place_guards():
    assert "function duplicateSelectedInPlace()" in JS
    assert "e.preventDefault(); if (canSave) { duplicateSelectedInPlace(); } return;" in JS
    body = JS.split("function duplicateSelectedInPlace()", 1)[1].split("function reorderSelected", 1)[0]
    assert "objs.length + src.length > 200" in body
    assert body.index("> 200") < body.index("recordUndo();")
    assert "markDirty();" in body and "selectedIds = ids;" in body


def test_layer_reorder_persists_array_order():
    assert "function reorderSelected(dir)" in JS
    body = JS.split("function reorderSelected(dir)", 1)[1].split("function pastePlainTextAsObject", 1)[0]
    assert "cs.objects = next;" in body
    for s in ("recordUndo();", "markDirty();", "rebuildAnno();"):
        assert s in body
    assert "reorderSelected(fwd ? (e.shiftKey ? 'front' : 'up') : (e.shiftKey ? 'back' : 'down'));" in JS
    assert "e.code === 'BracketRight'" in JS


def test_tool_keys_click_buttons():
    for code, bid in (("KeyV", "dws-btn-select"), ("KeyU", "dws-btn-shape"),
                      ("KeyP", "dws-btn-pen"), ("KeyE", "dws-btn-eraser"),
                      ("KeyI", "dws-file-input")):
        assert f"e.code === '{code}') {{ toolBtnId = '{bid}'; }}" in JS
    assert "toolBtn.click();" in JS


def test_shortcuts_after_editing_guard():
    keydown = JS.split("document.addEventListener('keydown'", 1)[1]
    assert keydown.index("if (editing) { return; }") < keydown.index("selectAllOnSheet();")
