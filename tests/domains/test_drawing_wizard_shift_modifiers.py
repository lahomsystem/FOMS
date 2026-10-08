"""마법사 Shift 보조키 계약(포토샵 동작): 그리기 제약·비율 유지 리사이즈·15° 회전 스냅."""
from pathlib import Path

JS = Path("static/js/drawing/wizard.js").read_text(encoding="utf-8")


def test_shift_draw_constrains_square_circle_and_45_degree_lines():
    assert "function constrainShapeEnd(mode, start, p, shift)" in JS
    assert "var side = Math.max(Math.abs(dx), Math.abs(dy));" in JS
    assert "Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4)" in JS
    # 미리보기(mousemove)와 확정(mouseup)이 같은 제약을 거친다
    assert "var p = constrainShapeEnd(mode, start, pointerLogical(nativeEvt), !!nativeEvt.shiftKey);" in JS
    assert "finishDrawShape(draft, mode, start, constrainShapeEnd(mode, start, pointerLogical(nativeEvt), !!nativeEvt.shiftKey));" in JS


def test_shift_resize_keeps_ratio_via_konva_shift_behavior():
    assert "keepRatio: false," in JS
    assert "shiftBehavior: 'default'," in JS


def test_shift_rotate_snaps_to_15_degrees_and_restores():
    assert "for (var rs = 0; rs < 360; rs += 15) { ROTATION_SNAPS_SHIFT.push(rs); }" in JS
    assert "transformer.rotationSnaps(shiftHeld ? ROTATION_SNAPS_SHIFT : ROTATION_SNAPS_DEFAULT);" in JS
    assert "transformer.rotationSnapTolerance(shiftHeld ? 7.5 : 6);" in JS
    assert "shiftHeld = !!e.shiftKey; syncShiftRotationSnaps();" in JS
    assert "shiftHeld = false; syncShiftRotationSnaps();" in JS
