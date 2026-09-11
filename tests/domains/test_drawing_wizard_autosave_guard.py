"""도면 마법사 자동저장 가드 계약 (W2).

2026-09-10 주문 5177 사고의 방어 몫이다. 진짜 원인(폼 저장이 서버 소유
`structured_data['drawing_wizard']` 를 통째로 지운 것)은 서버에서 고친다 —
여기서 못박는 것은 클라이언트가 **아직 못 불러온 상태를 서버에 써 넣지 않는다**는
기간계다.

계약 축 3개:
1. 하이드레이션 게이트 — `load()` 가 200 으로 렌더까지 마쳐야(`hydrated`) 저장이 나간다.
2. 사용자 변경 게이트 — `userDirty`(사람이 만든 변경)만 자동저장 대상이다.
   `load()` 안에서 켜는 `dirty`(drew 동기화·page_no 자동번호)는 저장 버튼만 켜고
   자동저장은 시키지 않는다.
3. 충돌 후 억제 — 충돌을 "내 버전 유지"로 넘기면 `autosaveSuspended` 로 자동저장을 끈다.
   덮어쓰기는 사람이 저장 버튼을 눌러야만 가능하다.

빈 `objects` 저장 금지 같은 내용 기반 차단은 **넣지 않는다**(사용자가 전부 지우는 것은
정당한 편집이다). 문자열 계약 양식은 tests/domains/test_erp_order_shared_form_scripts.py
를 따른다 — 렌더 없이 소스 텍스트만 읽는다.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WIZARD_JS = REPO_ROOT / "static" / "js" / "drawing" / "wizard.js"
WIZARD_TPL = REPO_ROOT / "templates" / "drawing" / "wizard.html"

JS = WIZARD_JS.read_text(encoding="utf-8")
TPL = WIZARD_TPL.read_text(encoding="utf-8")

#: wizard.js 의 최상위 함수 선언 들여쓰기(IIFE 안 2칸). 슬라이스 종료 마커로 쓴다.
_FN_DECL = chr(10) + "  function "


def _fn_slice(src: str, decl: str) -> str:
    """`decl` 로 시작하는 함수 본문을, 다음 최상위 함수 선언 직전까지 잘라 돌려준다."""
    start = src.index(decl)
    nxt = src.find(_FN_DECL, start + len(decl))
    return src[start:] if nxt < 0 else src[start:nxt]


def test_tick_autosave_gate_requires_hydration_and_user_edit() -> None:
    """자동저장 틱 최상단이 하이드레이션·사용자변경·충돌억제를 먼저 본다."""
    tick = _fn_slice(JS, "function tickAutosave() {")

    assert "if (!hydrated || !userDirty || autosaveSuspended) { return; }" in tick
    # 기존 게이트는 한 줄도 지우지 않는다.
    assert "if (!dirty || !canSave || saveInFlight) { return; }" in tick
    assert "if (!state.sheets.length) { return; }" in tick
    assert "if (editingTextarea || editCtx) { return; }" in tick
    assert "if (annoMode !== 'select') { return; }" in tick
    assert "if (dragActive) { return; }" in tick


def test_guard_flags_are_declared_at_module_scope() -> None:
    """게이트 변수 3개가 모듈 스코프 선언으로 존재한다(함수 지역 변수 금지)."""
    assert "var hydrated = false;" in JS
    assert "var userDirty = false;" in JS
    assert "var autosaveSuspended = false;" in JS


def test_load_sets_hydrated_only_after_render() -> None:
    """load() 는 요청 직전에 hydrated 를 내리고, 성공 핸들러 마지막에 올린다."""
    load = _fn_slice(JS, "function load() {")

    assert "hydrated = false;" in load
    assert "hydrated = true;" in load
    # 요청 직전 해제 → 렌더 뒤 설정 순서.
    assert load.index("hydrated = false;") < load.index("jsonFetch(")
    assert load.index("refreshPending();") < load.index("hydrated = true;")
    # dirty 를 내리는 자리에서 사용자 변경·충돌 억제도 함께 내린다.
    assert "userDirty = false; autosaveSuspended = false;" in load


def test_load_synced_changes_never_mark_user_dirty() -> None:
    """load() 가 스스로 켜는 dirty 2곳(drew 동기화·page_no 자동번호)은 userDirty 를 켜지 않는다.

    사용자가 하지 않은 변경을 사용자 대신 서버에 써 넣지 않는다 — 저장 버튼은 켜되
    자동저장 대상은 아니다.
    """
    load = _fn_slice(JS, "function load() {")

    dirty_lines = [ln for ln in load.splitlines() if "dirty = true" in ln]
    assert len(dirty_lines) == 2, dirty_lines
    for line in dirty_lines:
        assert "userDirty" not in line, line
    assert "userDirty = true" not in load


def test_mark_dirty_sets_user_dirty() -> None:
    """사용자 조작 경로(markDirty)만 userDirty 를 켠다."""
    mark = _fn_slice(JS, "function markDirty() {")

    assert "dirty = true;" in mark
    assert "userDirty = true;" in mark


def test_save_blocks_before_hydration_and_sends_auto_flag() -> None:
    """save() 는 하이드레이션 전 쓰기를 막고, PUT body 최상위에 auto 를 싣는다."""
    save = _fn_slice(JS, "function save(opts) {")

    assert "if (!hydrated) {" in save
    assert "도면을 불러오는 중입니다. 잠시 후 저장해 주세요." in save
    assert "auto: auto" in save
    assert "base_updated_at: baseUpdatedAt" in save
    assert "userDirty = false;" in save


def test_save_all_clears_user_dirty() -> None:
    """일괄 저장도 사용자 변경 플래그를 내린다(직후 자동저장 재발 금지)."""
    save_all = _fn_slice(JS, "function saveAll() {")

    assert "dirty = false;" in save_all
    assert "userDirty = false;" in save_all


def test_handle_conflict_suspends_autosave_and_reads_conflict_reason() -> None:
    """[취소](내 버전 유지)는 자동저장을 끄고, 'vanished' 충돌을 따로 안내한다."""
    conflict = _fn_slice(JS, "function handleConflict(cdata) {")

    assert "autosaveSuspended = true;" in conflict
    assert "conflict_reason" in conflict
    assert "'vanished'" in conflict
    assert "서버에 저장돼 있던 도면 상태가 사라졌습니다." in conflict


def test_wizard_js_asset_pin_bumped_for_autosave_guard() -> None:
    """wizard.js 내용이 바뀌었으므로 ?v= 핀을 올렸다(SW staticCacheFirst 스테일 봉합)."""
    assert "js/drawing/wizard.js') }}?v=20260910a" not in TPL
    assert "js/drawing/wizard.js') }}?v=20260911a" in TPL


def test_no_content_based_empty_canvas_block() -> None:
    """'빈 objects 면 저장 금지' 같은 내용 기반 차단을 넣지 않았다(음성 대조군).

    사용자가 도면을 전부 지우는 것은 정당한 편집이다. 우리가 막는 것은
    '아직 못 불러온 상태에서 나가는 쓰기'뿐이다.
    """
    save = _fn_slice(JS, "function save(opts) {")
    tick = _fn_slice(JS, "function tickAutosave() {")

    for src in (save, tick):
        assert "objects.length" not in src
        assert "objects || []).length" not in src
    # 자동저장 자체는 살아 있다(기능을 끄지 않았다).
    assert "autosaveTimer = setInterval(tickAutosave, AUTOSAVE_INTERVAL_MS);" in JS
