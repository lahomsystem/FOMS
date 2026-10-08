"""마법사 텍스트 Enter=편집 끝, Shift+드래그=축 고정 이동 계약(포토샵 동작)."""
from pathlib import Path

JS = Path("static/js/drawing/wizard.js").read_text(encoding="utf-8")


def test_enter_commits_text_edit_but_not_during_ime_or_shift():
    assert "e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229" in JS
    assert "e.preventDefault(); area.blur();" in JS


def test_shift_drag_locks_axis_on_nodes_and_group_back():
    assert "function wireAxisLock(node)" in JS
    assert "wireAxisLock(node);" in JS
    assert "transformer.findOne('.back')" in JS
    assert "axis === 'x' ? { x: pos.x, y: s.y } : { x: s.x, y: pos.y }" in JS
    assert "node.setAttr('dragAxis', axis);" in JS  # 축 고정 유지(튐 방지)
