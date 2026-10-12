"""도면 마법사 기본 프리셋 자리표 계약.

새 시트는 기본 프리셋 5개([SR]·[EP]·[DOOR]·[옷봉]·[마이다])를 시트 머리 확인칸 아래에 미리 깔고,
라벨만 있는 자리표는 클릭 한 번에 아랫줄 입력, 손대지 않은 자리표는 Delete·삭제 버튼으로 지운다.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / 'static/js/drawing/wizard.js').read_text(encoding='utf-8')
CSS = (ROOT / 'static/css/contexts/drawing/wizard.css').read_text(encoding='utf-8')


def test_default_presets_include_maida():
    assert "MAIDA: '[마이다]'" in JS
    for label in ("'[SR]'", "'[EP]'", "'[DOOR]'", "'[옷봉]'"):
        assert label in JS


def test_new_sheet_seeds_preset_placeholders():
    assert "objects: seedPresetObjects() }" in JS
    assert 'function isPresetPlaceholder(o)' in JS


def test_placeholder_click_starts_edit_at_caret_end():
    assert "node.on('click tap'" in JS
    assert 'startEditText(node, false, true)' in JS
    assert 'function caretToEnd(area)' in JS


def test_placeholder_delete_paths():
    assert "e.key === 'Delete' && placeholder" in JS
    assert '.dws-minitoolbar.dws-mt-editing.dws-mt-placeholder #dws-mt-del-text' in CSS
