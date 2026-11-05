"""도면 마법사 그림 자르기(포토샵 자르기 도구처럼) 계약.

사용자 요청(2026-11-03, 스테이징 주문 4385): '이미지를 자를 수 있는 기능을 넣어 줘(like photoshop)'.
미니 툴바 [자르기] → 그림 위 자르기 틀(8 손잡이 · 틀 밖 어둡게) → Enter 적용 · Esc 취소.
적용은 화면에 보이는 그대로 잘라 새 에셋(trim=0)으로 올리고, 코어 applyCrop 이 자리 · 되돌리기 · V2 다시 놓기를 맡는다.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
CROP = (ROOT / "static/js/drawing/image-crop.js").read_text(encoding="utf-8")
CORE = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")


def test_crop_button_bar_and_script_order():
    assert TPL.index('id="dws-mt-crop"') < TPL.index('id="dws-mt-trim"')   # 이미지 툴바, 여백 자르기 옆
    assert 'id="dws-crop-bar"' in TPL and 'id="dws-crop-apply"' in TPL and 'id="dws-crop-cancel"' in TPL
    assert TPL.index("js/drawing/wizard.js') }}?v=20261106a") < TPL.index("js/drawing/image-crop.js') }}?v=20261103a")


def test_core_exposes_crop_entry_and_apply_keeps_place():
    for k in ("selectedId:", "find: findObj", "layer: function () { return konvaLayer; }", "upload: uploadAsset", "applyCrop: applyImageCrop"):
        assert k in CORE, k
    body = CORE[CORE.index("  function applyImageCrop(id, data, box) {"):CORE.index("  /** 선택한 이미지의 여백을 잘라")]
    assert "recordUndo();" in body and "cur.locked" in body
    assert "box.x * c - box.y * sn" in body and "box.x * sn + box.y * c" in body   # 돌린 그림도 남긴 부분이 제자리
    assert "delete cur.flipX; delete cur.flipY;" in body                            # 뒤집기는 잘라 낸 그림에 들어 있다
    assert "emitCore('trimmed'" in body
    assert "if (opts && opts.noTrim) { fd.append('trim', '0'); }" in CORE


def test_crop_module_blocks_shortcuts_and_stage_clicks():
    assert "window.addEventListener('keydown', onKey, true);" in CROP
    assert "e.stopImmediatePropagation();" in CROP
    assert "e.cancelBubble = true;" in CROP
    assert "{ noTrim: true }" in CROP
    assert len(CROP.splitlines()) < 300

