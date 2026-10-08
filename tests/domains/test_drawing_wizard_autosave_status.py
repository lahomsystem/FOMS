"""도면 마법사 자동 저장 확대 · 로컬 비상 백업 · 저장 상태 칩 · 오류 토스트 계약.

렌더 없이 소스 텍스트만 읽는 문자열 계약이다(test_drawing_wizard_autosave_guard.py 양식).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JS = (REPO_ROOT / "static" / "js" / "drawing" / "wizard.js").read_text(encoding="utf-8")
TPL = (REPO_ROOT / "templates" / "drawing" / "wizard.html").read_text(encoding="utf-8")
CSS = (REPO_ROOT / "static" / "css" / "contexts" / "drawing" / "wizard.css").read_text(encoding="utf-8")

_FN_DECL = chr(10) + "  function "


def _fn_slice(src: str, decl: str) -> str:
    start = src.index(decl)
    nxt = src.find(_FN_DECL, start + len(decl))
    return src[start:] if nxt < 0 else src[start:nxt]


# ---- (2a) 펜·도형 모드에서도 자동 저장, 진행 중 제스처만 보류 ----

def test_tick_autosave_no_longer_requires_select_mode() -> None:
    tick = _fn_slice(JS, "function tickAutosave() {")
    assert "annoMode" not in tick
    assert "if (isDrawingPen || shapeDrawActive) { return; }" in tick
    assert "if (editingTextarea || editCtx) { return; }" in tick
    assert "if (dragActive) { return; }" in tick


def test_shape_draft_flag_brackets_gesture() -> None:
    assert "var shapeDrawActive = false;" in JS
    shape = _fn_slice(JS, "function startDrawShape(e) {")
    assert "shapeDrawActive = true;" in shape
    assert shape.index("shapeDrawActive = false;") < shape.index("finishDrawShape(draft")


def test_auto_save_does_not_touch_tool_mode() -> None:
    save = _fn_slice(JS, "function save(opts) {")
    assert "setAnnoMode" not in save
    assert "deselect()" not in save


# ---- (2b) 로컬 비상 백업 ----

def test_mark_dirty_schedules_backup() -> None:
    assert "function markDirty() { dirty = true; userDirty = true; updateSaveState(); scheduleBackup(); }" in JS
    assert "var BACKUP_DEBOUNCE_MS = 2000;" in JS
    assert "var BACKUP_MAX_CHARS = 4 * 1024 * 1024;" in JS


def test_backup_respects_read_only_and_size() -> None:
    sched = _fn_slice(JS, "function scheduleBackup() {")
    assert "if (!canSave || !hydrated) { return; }" in sched
    write = _fn_slice(JS, "function writeBackup() {")
    assert "localStorage.setItem(backupKey()" in write
    assert "raw.length > BACKUP_MAX_CHARS" in write
    assert "try {" in write and "catch (e)" in write
    assert "'dws-backup:' + String(ORDER_ID" in JS


def test_backup_cleared_after_successful_save() -> None:
    save = _fn_slice(JS, "function save(opts) {")
    assert "clearBackup();" in save
    save_all = _fn_slice(JS, "function saveAll() {")
    assert "clearBackup();" in save_all


def test_restore_banner_offered_after_load() -> None:
    load = _fn_slice(JS, "function load() {")
    assert load.index("offerBackupRestore();") < load.index("hydrated = true;")
    offer = _fn_slice(JS, "function offerBackupRestore() {")
    assert "if (!canSave) { return; }" in offer
    assert "저장되지 않은 작업이 있습니다 (" in offer
    restore = _fn_slice(JS, "function restoreBackup() {")
    assert "markDirty();" in restore
    for el_id in ("dws-restore-banner", "dws-btn-restore", "dws-btn-restore-discard"):
        assert f'id="{el_id}"' in TPL
    assert ">복원<" in TPL and ">버리기<" in TPL


# ---- (3) 저장 상태 칩 ----

def test_save_status_chip_states() -> None:
    assert 'id="dws-save-status"' in TPL
    chip = _fn_slice(JS, "function renderSaveStatus() {")
    for label in ("'저장 중…'", "'저장 실패'", "'저장 안 됨'", "'저장됨 '", "자동 저장 멈춤"):
        assert label in chip
    assert "if (!canSave) { el.hidden = true; return; }" in chip
    assert "renderSaveStatus();" in _fn_slice(JS, "function updateSaveState() {")
    for kind in ("saved", "saving", "dirty", "paused", "failed"):
        assert f".dws-save-status.dws-save-status-{kind}" in CSS


def test_save_flags_failure_and_success() -> None:
    save = _fn_slice(JS, "function save(opts) {")
    assert "saveFailed = true;" in save
    assert "saveFailed = false;" in save
    assert "lastSavedAt = new Date();" in save
    # 기존 '저장 *' 버튼 동작은 유지
    assert "els.saveBtn.textContent = dirty ? '저장 *' : '저장';" in JS


# ---- (8) 오류 토스트 ----

def test_error_toast_persists_with_close_and_retry() -> None:
    toast = _fn_slice(JS, "function toast(msg, opts) {")
    assert "if (opts.error) { return errorToast(msg, opts.retry); }" in toast
    assert "}, 2600);" in toast   # 일반 토스트는 그대로 2.6초
    err = _fn_slice(JS, "function errorToast(msg, retry) {")
    assert "setTimeout(function () { t.classList.remove" not in err   # 자동으로 사라지지 않는다
    assert "'다시 시도'" in err
    assert "'×'" in err
    assert ".dws-toast.dws-toast-error" in CSS
    assert "pointer-events: auto;" in CSS


def test_failure_text_distinguishes_network_and_server() -> None:
    ft = _fn_slice(JS, "function failureText(what, r) {")
    assert "인터넷 연결" in ft
    assert "st >= 500" in ft
    assert "st === 401 || st === 403" in ft


def test_error_toast_used_for_key_failures() -> None:
    for what in ("'저장 실패'", "'일괄 저장 실패'", "'이미지 업로드 실패'", "'실측 사진 삽입 실패'", "'도면방 PUSH 실패'"):
        assert f"failureText({what}" in JS, what
    assert "toast('저장 오류')" not in JS
    assert JS.count("{ error: true, retry:") >= 8


def test_no_inline_styles_added_to_template() -> None:
    for el_id in ("dws-save-status", "dws-restore-banner"):
        line = next(ln for ln in TPL.splitlines() if f'id="{el_id}"' in ln)
        assert "style=" not in line
