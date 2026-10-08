"""도면 마법사 — 시트별 실행 취소 이력 · 시트 삭제 되돌리기 · 재전송 변경 내용 모달 문자열 계약."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
HTML = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    m = re.search(r"\n  function " + name + r"\(.*?\n  }\n", JS, re.S)
    assert m, name
    return m.group(0)


def test_시트_전환_추가_복제_삭제가_이력을_지우지_않는다():
    assert "undoStack.length = 0" not in JS
    # 새 편집이 redo 를 비우는 것(pushUndoSnapshot)만 남는다
    assert JS.count("redoStack.length = 0") == 1
    assert "redoStack.length = 0" in _fn("pushUndoSnapshot")
    assert "var sheetHistories = {};" in JS
    for name in ("switchSheet", "addSheet", "duplicateSheet", "deleteSheet"):
        assert "bindSheetHistory();" in _fn(name), name


def test_이력은_시트_id_로_묶이고_상한을_유지한다():
    bind = _fn("bindSheetHistory")
    assert "sheetHistories[cs.id]" in bind
    assert "undoStack = h.undo;" in bind and "redoStack = h.redo;" in bind
    assert "if (undoStack.length > 50) { undoStack.shift(); }" in _fn("pushUndoSnapshot")


def test_삭제된_시트의_이력은_지우고_되돌리기에서_복원한다():
    delete = _fn("deleteSheet")
    assert "delete sheetHistories[removed.id];" in delete
    assert "showSheetUndoBar(" in delete
    restore = _fn("restoreDeletedSheet")
    assert "state.sheets.splice(idx, 0, sheet);" in restore
    assert "cloneSheet(entry.sheet)" in restore
    assert "sheetHistories[sheet.id] =" in restore
    assert "markDirty();" in restore


def test_되돌리기_바는_10초_동안_토스트_스타일로_뜬다():
    assert "var SHEET_UNDO_MS = 10000;" in JS
    bar = _fn("showSheetUndoBar")
    assert "'dws-toast dws-toast-action'" in bar
    assert "'되돌리기'" in bar
    assert "setTimeout(hideSheetUndoBar, SHEET_UNDO_MS)" in bar
    assert ".dws-toast.dws-toast-action" in CSS
    assert ".dws-toast-undo-btn" in CSS


def test_재전송_변경_내용은_prompt_대신_모달로_받는다():
    push = _fn("pushDrawingRoom")
    assert "prompt(" not in push
    assert "askChangeNote()" in push
    ask = _fn("askChangeNote")
    assert "err.hidden = false" in ask          # 빈 입력 = 안내, 조용한 취소 아님
    assert "'cancel'" in ask                     # Esc 닫기
    assert "var CHANGE_NOTE_MAX = 500;" in JS
    for el_id in ("dws-note-dialog", "dws-note-input", "dws-note-count",
                  "dws-note-error", "dws-note-send", "dws-note-cancel"):
        assert f'id="{el_id}"' in HTML, el_id
    assert 'maxlength="500"' in HTML
    assert ">보내기</button>" in HTML and ">취소</button>" in HTML
    assert ".dws-note-input" in CSS


def test_새_마크업에_인라인_스타일이_없다():
    m = re.search(r'<dialog class="dws-dialog dws-note-dialog.*?</dialog>', HTML, re.S)
    assert m and "style=" not in m.group(0)
