"""도면 마법사 저장 표시 · 전달본 지우기 × · 빈 화면 안내 · 탭 이름 바꾸기 계약.

평가 보고서 이름표: 보통-5('저장됨' 두 뜻 · 빨간 × · 새 시트에 × 남음) · 작음(제품 없는 주문 안내 · 이름 바꾸기 안내).
실화면 QA 2차(2026-10-25): 빈 화면 글이 낱말 가운데서 끊기고 연회색 · [저장] 풍선 말 · 새 시트 이름 겹침('도면 10' 셋).
- 저장은 두 가지다: 자동 저장(작업 내용만) · [저장](지금 시트 그림을 전달 대기함에 넣기 = 전달본).
  칩은 지금 시트 기준으로 '자동 저장 09:15' · '전달 대기함 09:12' · '전달본 없음' · '전달본 예전 것' 을 가른다.
- 칩 글(save-status.js)은 순수 계산이라 node 로 돌린다. 시트를 바꿀 때 ×·칩이 따라오는지는
  wizard.js 의 실제 함수를 잘라 node 에서 작은 가짜 화면으로 돌려 본다.
- 다시 연 창(새로고침 뒤 '전달본 예전 것'·'전달본 없음')은 test_drawing_wizard_save_reopen.py(500줄 래칫으로 나눔).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SS_PATH = ROOT / "static/js/drawing/save-status.js"
WIZ_PATH = ROOT / "static/js/drawing/wizard.js"
JS = WIZ_PATH.read_text(encoding="utf-8")
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")

_FN_DECL = "\n  function "


def _fn(name: str) -> str:
    """wizard.js 최상위 함수 하나의 소스(다음 최상위 function 직전까지)."""
    start = JS.index("  function " + name + "(")
    nxt = JS.find(_FN_DECL, start + 3)
    return JS[start:] if nxt < 0 else JS[start:nxt]


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _run(script: str, *args: str) -> object:
    proc = subprocess.run([_node(), "-e", script, *args], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


CALL_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const S = window.FomsSaveStatus;
const toDate = (a) => Array.isArray(a) ? new Date(a[0], a[1] - 1, a[2], a[3], a[4]) : a;
const out = JSON.parse(process.argv[2]).map(([fn, args]) => {
  if (fn === 'chip') { const st = Object.assign({}, args[0]); st.savedAt = toDate(st.savedAt); st.now = toDate(st.now); return S.chip(st); }
  if (fn === 'atText') { return S.atText(args[0], toDate(args[1])); }
  return S[fn].apply(null, args);
});
process.stdout.write(JSON.stringify(out));
"""


def _calls(calls: list) -> list:
    return _run(CALL_RUNNER, str(SS_PATH), json.dumps(calls, ensure_ascii=False))


NOW = [2026, 10, 25, 9, 20]
SAVED = [2026, 10, 25, 9, 15]


def test_node_check_save_status():
    proc = subprocess.run([_node(), "--check", str(SS_PATH)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert len(SS_PATH.read_text(encoding="utf-8").splitlines()) < 300   # 새 JS 300줄 래칫


def test_chip_separates_auto_save_from_queue_per_sheet():
    base = {"canSave": True, "now": NOW}
    cases = [
        dict(base, savedAt=SAVED, savedAuto=True),                                   # 자동 저장 뒤, 전달본 없음
        dict(base, savedAt=SAVED, savedAuto=False, queued=True, queuedAt="2026-10-25 09:12", queuedFresh=True),
        dict(base, savedAt=SAVED, savedAuto=False),                                  # [저장]은 다른 시트였다
        dict(base, savedAt=SAVED, savedAuto=True, queued=True, queuedAt="2026-10-25 09:12", queuedFresh=False),
        dict(base, queued=True, queuedAt="2026-10-24 17:05"),                         # 어제 넣음(이 창 저장 전)
        dict(base),                                                                  # 막 열었고 저장·전달본 없음
        dict(base, dirty=True, savedAt=SAVED, queued=True, queuedAt="2026-10-25 09:12"),
        dict(base, dirty=True, paused=True),
        dict(base, saving=True), dict(base, failed=True),
        {"canSave": False, "savedAt": SAVED},
    ]
    got = _calls([["chip", [c]] for c in cases])
    assert [(g["label"], g["kind"]) for g in got] == [
        ("자동 저장 09:15", "saved"),
        ("전달 대기함 09:12", "queued"),
        ("전달본 없음", "none"),
        ("전달본 예전 것", "stale"),
        ("전달 대기함 10/24", "queued"),
        ("", ""),
        ("저장 안 됨", "dirty"),
        ("저장 안 됨 · 자동 저장 멈춤", "paused"),
        ("저장 중…", "saving"), ("저장 실패", "failed"),
        ("", ""),
    ]
    assert all("저장됨" not in g["label"] for g in got)
    # 풍선 말은 칩만 봐서는 모르는 쪽(전달본 없음·예전 것)을 말로 풀어 준다.
    assert "아직 전달 대기함에 없어요" in got[0]["title"] and "아직 전달 대기함에 없어요" in got[2]["title"]
    assert "[저장]을 눌러야 들어가요" in got[3]["title"]
    assert "2026-10-24 17:05" in got[4]["title"]


def test_at_text_josa_and_toasts_name_the_sheet():
    got = _calls([
        ["atText", ["2026-10-25 09:12", NOW]], ["atText", ["2026-10-24 17:05", NOW]], ["atText", ["", NOW]],
        ["objJosa", ["도면 1"]], ["objJosa", ["도면 2"]], ["objJosa", ["주방"]], ["objJosa", ["안방 장"]],
        ["objJosa", ["도면 (v2 복원)"]], ["objJosa", ["L"]], ["objJosa", ["★"]],
        ["queuedToast", ["도면 1"]], ["queuedToast", ["도면 2"]], ["queuedToast", [""]],
        ["queueFailToast", ["주방"]],
        ["allQueuedToast", [3, 3, []]], ["allQueuedToast", [2, 3, ["도면 2"]]],
    ])
    assert got[:3] == ["09:12", "10/24", ""]
    assert got[3:10] == ["을", "를", "을", "을", "을", "을", "을(를)"]
    assert got[10] == "'도면 1'을 전달 대기함에 넣었어요"
    assert got[11] == "'도면 2'를 전달 대기함에 넣었어요"
    assert got[12] == "'도면'을 전달 대기함에 넣었어요"
    assert got[13] == "작업 내용은 저장했지만 '주방'을 전달 대기함에 넣지 못했어요"
    assert got[14] == "시트 3장을 모두 전달 대기함에 넣었어요"
    assert got[15] == "시트 3장 중 2장을 넣었어요 · 못 넣은 시트: 도면 2"


def test_sheet_sig_ignores_calc_and_part_labels_but_sees_drawing():
    sheet = {"id": "s1", "name": "도면 1", "calc": {"w": 1000},
             "objects": [{"id": "o1", "type": "image", "x": 10, "part": {"label": "사진", "src": "ai"}}]}
    relabeled = json.loads(json.dumps(sheet))
    relabeled["calc"] = {"w": 2000}
    relabeled["objects"][0]["part"] = {"label": "평면·상판", "src": "user", "arr": [1, 2, 3, 4]}
    moved = json.loads(json.dumps(sheet))
    moved["objects"][0]["x"] = 11
    a, b, c = _calls([["sheetSig", [sheet]], ["sheetSig", [relabeled]], ["sheetSig", [moved]]])
    assert a == b      # 계산 칸 숫자·AI 이름표는 전달본 그림에 안 찍힌다 → 넣은 뒤 고침이 아니다
    assert a != c      # 그림을 옮기면 전달본이 예전 것이 된다


def test_empty_copy_by_products_and_permission():
    no_products, with_products, read_only = _calls([
        ["emptyCopy", [0, True]], ["emptyCopy", [3, True]], ["emptyCopy", [0, False]]])
    assert no_products["title"] == "제품이 없는 주문이에요"
    assert "[빈 시트 추가]" in no_products["sub"] and "[+ 시트]" in no_products["sub"]
    assert "좌측에서 제품을 선택" not in no_products["title"] + no_products["sub"]
    assert with_products["title"] == "좌측에서 제품을 선택해 도면을 시작하세요"
    assert "열람 전용" in read_only["sub"]
    upd = _fn("updateEmptyOverlay")
    assert "emptyCopy(products.length, canSave)" in upd
    assert ".dws-empty-title" in upd and ".dws-empty-sub" in upd


# ---- 시트를 바꾸면 ×·칩이 지금 시트를 따른다(wizard.js 실제 함수, 가짜 화면) ----

SHEET_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const fs = require('fs');
const src = JSON.parse(fs.readFileSync(0, 'utf8'));
const classes = new Set();
var state = { sheets: [{ id: 's1', name: '도면 1', objects: [{ id: 'o1', type: 'text', x: 1 }] }] };
var current = 0, canSave = true;
var saveInFlight = false, saveFailed = false, dirty = false, autosaveStopped = false, autosaveSuspended = false;
var lastSavedAt = null, lastSaveAuto = false;
var pendingSheetIds = new Set(), pendingAtBySheet = {}, queuedSigBySheet = {};
var pendingKnown = true, hydrated = true;   // 불러오기·전달 대기함 목록을 받은 뒤
var els = {
  delSavedBtn: { hidden: true },
  saveStatus: { hidden: true, textContent: '', title: '', classList: { toggle: (k, on) => { if (on) { classes.add(k); } else { classes.delete(k); } } } }
};
eval(src.join('\n'));
const snap = () => ({ x: !els.delSavedBtn.hidden, chip: els.saveStatus.hidden ? '' : els.saveStatus.textContent.replace(/\d\d:\d\d/, 'HH:MM'), kind: [...classes].join(' ') });
const out = {};
// [저장] 성공: 작업 내용 저장 + 시트 1 전달본
lastSavedAt = new Date(); lastSaveAuto = false;
noteQueued(state.sheets[0], window.FomsSaveStatus.sheetSig(state.sheets[0]));
syncSheetSaveUi(); out.saved = snap();
// 새 시트 추가(addSheet 와 같은 순서: push → current → renderTabs → syncSheetSaveUi)
state.sheets.push({ id: 's2', name: '도면 2', objects: [] }); current = 1; syncSheetSaveUi(); out.added = snap();
// 자동 저장 뒤에도 시트 2 는 전달본 없음
lastSaveAuto = true; syncSheetSaveUi(); out.autosaved = snap();
// 시트 1 로 돌아가면 다시 전달 대기함
current = 0; syncSheetSaveUi(); out.back = snap();
// 시트 1 을 고치고 자동 저장 → 전달본 예전 것(× 는 그대로: 전달본은 있다)
state.sheets[0].objects[0].x = 2; syncSheetSaveUi(); out.edited = snap();
// 서버 목록이 비면(전달본 지움) × 가 사라진다
pendingSheetIds = new Set(); pendingAtBySheet = {}; syncSheetSaveUi(); out.deleted = snap();
// 열람 전용: × 와 칩 모두 숨김
pendingSheetIds.add('s1'); canSave = false; syncSheetSaveUi(); out.readonly = snap();
process.stdout.write(JSON.stringify(out));
"""


def test_switching_sheets_recomputes_delete_button_and_chip():
    names = ["currentSheet", "hhmm", "updateDeleteSavedBtn", "queuedStateOf", "noteQueued",
             "syncSheetSaveUi", "renderSaveStatus"]
    proc = subprocess.run([_node(), "-e", SHEET_RUNNER, str(SS_PATH)], input=json.dumps([_fn(n) for n in names]),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["saved"] == {"x": True, "chip": "전달 대기함 HH:MM", "kind": "dws-save-status-queued"}
    assert out["added"] == {"x": False, "chip": "전달본 없음", "kind": "dws-save-status-none"}   # 예전엔 × 가 남았다
    assert out["autosaved"] == {"x": False, "chip": "자동 저장 HH:MM", "kind": "dws-save-status-saved"}
    assert out["back"] == {"x": True, "chip": "전달 대기함 HH:MM", "kind": "dws-save-status-queued"}
    assert out["edited"] == {"x": True, "chip": "전달본 예전 것", "kind": "dws-save-status-stale"}
    assert out["deleted"]["x"] is False and out["deleted"]["chip"] == "자동 저장 HH:MM"
    assert out["readonly"]["x"] is False and out["readonly"]["chip"] == ""


def test_every_sheet_change_path_goes_through_render_tabs():
    tabs = _fn("renderTabs")
    assert "syncSheetSaveUi();" in tabs
    sync = _fn("syncSheetSaveUi")
    assert "updateDeleteSavedBtn();" in sync and "renderSaveStatus();" in sync
    for name in ("addSheet", "switchSheet", "duplicateSheet", "deleteSheet", "restoreDeletedSheet", "load"):
        assert "renderTabs();" in _fn(name), name
    assert "syncSheetSaveUi();" in _fn("renderPending")
    assert "pendingAtBySheet[it.sheet_id] = String(it.at || '')" in _fn("renderPending")


def test_manual_save_names_sheet_and_guards_sheet_switch():
    png = _fn("saveSheetPng")
    assert "cs.id !== sheet.id" in png                       # 저장 중 다른 시트로 옮기면 그 그림을 찍지 않는다
    assert "noteQueued(sheet, sig);" in png and "SS.sheetSig(cs)" in png
    assert "SS.queuedToast(name)" in png
    assert "SS.queueFailToast(name)" in png and "{ error: true, retry:" in png
    assert "저장됨 · 전달 대기함에 보관" not in JS and "저장됨 (도면 이미지 저장 실패)" not in JS
    save_all = _fn("saveAll")
    assert "noteQueued(s, sig)" in save_all and "SS.allQueuedToast(" in save_all
    assert "confirmDeleteQueued(cs.name)" in JS                # 캔버스 × 확인 창이 시트 이름·그림 남음을 말한다
    assert "시트 그림은 그대로 남아요" in _fn("confirmDeleteQueued")


def test_delete_saved_button_is_calm_with_tooltip():
    line = next(ln for ln in TPL.splitlines() if 'id="dws-btn-delete-saved"' in ln)
    assert 'title="이 시트의 전달본 지우기"' in line and 'aria-label="이 시트의 전달본 지우기"' in line
    assert "style=" not in line
    block = re.search(r"\n\.dws-del-saved \{(.*?)\n\}", CSS, re.S).group(1)
    assert "rgba(224, 49, 49" not in block and "color: #ffffff" not in block   # 빨강 바탕·흰 × 는 오류처럼 보였다
    assert "background: rgba(255, 255, 255" in block
    hover = re.search(r"\n\.dws-del-saved:hover \{([^}]*)\}", CSS).group(1)
    assert "color: #c0261b" in hover                         # 지우기는 올렸을 때만 빨강


def test_tab_title_hint_and_inline_rename():
    tabs = _fn("renderTabs")
    assert "tab.title = tabTitle(s.name);" in tabs
    assert "renameSheet(i, tab)" in tabs
    assert "두 번 눌러 이름 바꾸기" in _fn("tabTitle")
    ren = _fn("renameSheet")
    assert "prompt(" not in ren                              # 브라우저 기본 창 대신 탭 안에서 고친다
    for frag in ("'dws-sheet-rename'", "e.key === 'Enter'", "e.key === 'Escape'", "input.maxLength = 50;",
                 "markDirty();", "addEventListener('blur'", "e.stopPropagation();",
                 "e.isComposing || e.keyCode === 229", "addEventListener('keyup'"):   # 한글 조합 중 Enter 도 한 번에
        assert frag in ren, frag
    assert ".dws-sheet-rename {" in CSS and "button.dws-sheet-renaming { display: none; }" in CSS


RENAME_RUNNER = r"""
const fs = require('fs');
const src = JSON.parse(fs.readFileSync(0, 'utf8'));
function el(tag) {
  const e = { tagName: tag.toUpperCase(), children: [], parentNode: null, hidden: false, title: '', textContent: '', value: '',
    listeners: {}, classes: new Set() };
  e.classList = { add: (c) => e.classes.add(c), remove: (c) => e.classes.delete(c) };
  e.setAttribute = (k, v) => { e[k] = v; };
  e.addEventListener = (t, f) => { (e.listeners[t] = e.listeners[t] || []).push(f); };
  e.fire = (t, ev) => (e.listeners[t] || []).forEach((f) => f(Object.assign({ preventDefault() {}, stopPropagation() {} }, ev || {})));
  e.insertBefore = (n, ref) => { e.children.splice(e.children.indexOf(ref), 0, n); n.parentNode = e; };
  e.removeChild = (n) => { e.children.splice(e.children.indexOf(n), 1); n.parentNode = null; };
  e.appendChild = (n) => { e.children.push(n); n.parentNode = e; };
  e.focus = () => {}; e.select = () => {};
  Object.defineProperty(e, 'firstChild', { get: () => e.children[0] || null });
  return e;
}
global.document = { createElement: el };
var canSave = true, dirtyCount = 0;
var state = { sheets: [{ id: 's1', name: '도면 1' }] };
function markDirty() { dirtyCount += 1; }
eval(src.join('\n'));
const bar = el('div'), tab = el('button'), label = el('span');
label.textContent = '도면 1'; tab.appendChild(label); bar.appendChild(tab);
const open = () => { renameSheet(0, tab); return bar.children[0]; };
const look = () => ({ name: state.sheets[0].name, label: label.textContent, title: tab.title, hidden: tab.hidden,
  renaming: tab.classes.has('dws-sheet-renaming'), boxes: bar.children.length, dirty: dirtyCount });
const out = {};
let input = open();
out.opened = { hidden: tab.hidden, renaming: tab.classes.has('dws-sheet-renaming'), value: input.value, cls: input.className, boxes: bar.children.length };
input.value = '  주방 시트 '; input.fire('keydown', { key: 'Enter' }); input.fire('keyup', { key: 'Enter' }); out.enter = look();
input = open(); input.value = '버릴 이름'; input.fire('keydown', { key: 'Escape' }); input.fire('blur'); out.esc = look();
input = open(); input.value = '안방 장'; input.fire('keydown', { key: 'Process', keyCode: 229, isComposing: true }); out.composing = look();
input.fire('keyup', { key: 'Enter' }); out.composed = look();
input = open(); input.value = '드레스룸'; input.fire('blur'); out.blur = look();
input = open(); input.value = '   '; input.fire('keydown', { key: 'Enter' }); out.empty = look();
canSave = false; renameSheet(0, tab); out.readonly = look();
process.stdout.write(JSON.stringify(out));
"""


def test_inline_rename_enter_escape_ime_and_blur():
    proc = subprocess.run([_node(), "-e", RENAME_RUNNER], input=json.dumps([_fn("tabTitle"), _fn("renameSheet")]),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["opened"] == {"hidden": True, "renaming": True, "value": "도면 1", "cls": "dws-sheet-rename", "boxes": 2}
    assert out["enter"] == {"name": "주방 시트", "label": "주방 시트", "title": "주방 시트 · 두 번 눌러 이름 바꾸기",
                            "hidden": False, "renaming": False, "boxes": 1, "dirty": 1}
    assert out["esc"]["name"] == "주방 시트" and out["esc"]["dirty"] == 1 and out["esc"]["boxes"] == 1   # 취소 = 그대로
    assert out["composing"]["name"] == "주방 시트" and out["composing"]["boxes"] == 2   # 조합 중 Enter 는 아직 아님
    assert out["composed"]["name"] == "안방 장" and out["composed"]["boxes"] == 1 and out["composed"]["dirty"] == 2
    assert out["blur"]["name"] == "드레스룸" and out["blur"]["dirty"] == 3
    assert out["empty"]["name"] == "드레스룸" and out["empty"]["dirty"] == 3 and out["empty"]["hidden"] is False
    assert out["readonly"]["boxes"] == 1 and out["readonly"]["dirty"] == 3


def test_template_loads_save_status_before_wizard():
    tag = re.search(r'<script src="[^"]*js/drawing/save-status\.js[^"]*"[^>]*>', TPL)
    assert tag and "?v=" in tag.group(0) and " defer" in tag.group(0)
    assert TPL.index("js/drawing/save-status.js") < TPL.index("js/drawing/wizard.js")


# ---- 실화면 QA 2차: 빈 화면 글 줄바꿈·색 · [저장] 풍선 말 ----

def _css_block(selector: str) -> str:
    """wizard.css 최상위 규칙 하나의 본문(들여쓴 미디어 쿼리 안 규칙은 빼고)."""
    m = re.search(r"\n" + re.escape(selector) + r" \{(.*?)\n\}", CSS, re.S)
    assert m, selector
    return m.group(1)


def _color_of(block: str) -> str:
    m = re.search(r"\n\s*color: (#[0-9a-fA-F]{6});", block)
    assert m, block
    return m.group(1).lower()


def _contrast_on_white(hex_color: str) -> float:
    """WCAG 대비(흰 바탕). 글자 기준 4.5 이상."""
    def lin(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 1.05 / (0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b) + 0.05)


def test_empty_texts_wrap_at_spaces_and_read_clearly():
    box = _css_block(".dws-empty-box")
    assert "word-break: keep-all;" in box          # '만들어 시/작하세요' 처럼 낱말 가운데서 끊기지 않게
    assert "overflow-wrap: break-word;" in box     # 띄어쓰기 없는 아주 긴 글만 칸 끝에서 끊는다
    for sel in (".dws-empty-title", ".dws-empty-sub"):
        assert "word-break" not in _css_block(sel), sel   # 상자에서 물려받은 keep-all 을 덮지 않는다
    assert "<p class=\"dws-empty-title\">" in TPL and "<p class=\"dws-empty-sub\">" in TPL   # 둘 다 상자 안 글
    assert _contrast_on_white("#86868b") < 4.5     # 예전 색(3.6) — 흐리다
    for sel in (".dws-empty-sub", ".dws-product-empty"):   # 빈 화면 설명 · 제품 목록 '제품 없음'
        color = _color_of(_css_block(sel))
        assert color == "#6e6e73" and _contrast_on_white(color) >= 4.5, (sel, color)


def test_save_button_tooltip_names_queue_and_shortcut():
    line = next(ln for ln in TPL.splitlines() if 'id="dws-btn-save"' in ln)
    assert 'title="지금 시트를 전달 대기함에 넣기 (Ctrl+S)"' in line
    assert ">저장</button>" in line and "style=" not in line   # 단추 글은 '저장' 그대로, 뜻은 풍선 말이 푼다
    assert "(e.key === 's' || e.key === 'S')) { e.preventDefault(); save();" in JS   # 풍선 말의 Ctrl+S 는 정말 [저장]이다


# ---- 실화면 QA 2차: 새 시트 이름이 겹치지 않는다(wizard.js 실제 함수, 가짜 화면) ----

NAME_RUNNER = r"""
const fs = require('fs');
const src = JSON.parse(fs.readFileSync(0, 'utf8'));
function el(tag) {
  const e = { tagName: String(tag).toUpperCase(), children: [], parentNode: null, listeners: {}, textContent: '', className: '' };
  e.classList = { add() {}, remove() {} };
  e.addEventListener = (t, f) => { (e.listeners[t] = e.listeners[t] || []).push(f); };
  e.fire = (t) => (e.listeners[t] || []).forEach((f) => f({ preventDefault() {}, stopPropagation() {} }));
  e.appendChild = (n) => { e.children.push(n); n.parentNode = e; return n; };
  e.removeChild = (n) => { e.children.splice(e.children.indexOf(n), 1); n.parentNode = null; };
  return e;
}
const out = (function () {
  var document = { createElement: el };
  var setTimeout = function () { return 1; }, clearTimeout = function () {}, requestAnimationFrame = function (f) { f(); };
  var confirm = function () { return true; };
  var canSave = true, current = 0, defaults = {}, toasts = [], sheetHistories = {}, seq = 0, pendingNames = [];
  var state = { sheets: [] };
  var els = { toastHost: el('div') };
  function rid(p) { seq += 1; return p + seq; }
  function newSheet(name) { return { id: rid('s-'), name: name, objects: [] }; }
  function toast(m) { toasts.push(m); }
  function bindSheetHistory() {} function deselect() {} function markDirty() {} function renderTabs() {}
  function renderForm() {} function rebuildAnno() {} function syncProductActive() {}
  eval(src.join('\n'));
  const names = () => state.sheets.map((s) => s.name);
  const make = (pre, list) => list.map((n, i) => ({ id: pre + i, name: n, objects: [] }));
  const res = {};
  // ① QA3 그대로: 9장에서 [+ 시트] → 하나 지우고 [+ 시트] → 또 지우고 [+ 시트] (예전엔 '도면 10' 이 셋)
  state.sheets = make('k', [1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => '도면 ' + n)); current = 0;
  addSheet(); res.first = names()[9];
  deleteSheet(2); hideSheetUndoBar(); addSheet();
  deleteSheet(0); hideSheetUndoBar(); addSheet();
  res.qa3 = names();
  // ② 되돌리기를 기다리는 동안 [+ 시트] — 지운 시트 이름을 가져가지 않아서 되살려도 안 겹친다
  state.sheets = make('u', ['도면 1', '도면 2', '도면 3']); current = 0;
  deleteSheet(2); addSheet(); res.whileUndo = names();
  sheetUndoBar.children[1].fire('click'); res.restored = names(); res.undoName = sheetUndoName;
  // ③ 전달 대기함에 남은 그림 이름(지운 시트 것)도 피한다
  state.sheets = make('p', ['도면 1']); current = 0; pendingNames = ['도면 2'];
  addSheet(); res.pending = names(); pendingNames = [];
  // ④ 복제를 두 번 하면 '… 복사' · '… 복사 2'
  state.sheets = make('d', ['주방']); current = 0;
  duplicateSheet(0); duplicateSheet(0); res.dup = names();
  // ⑤ 이름을 줄 때(제품·버전 복원) — 끝 숫자(치수)는 올리지 않고 ' 2' · 50자 · 빈 이름 · 객체 속성 이름 · 앞뒤 칸
  state.sheets = make('g', ['붙박이장 1200', 'x'.repeat(50), '도면 1']);
  res.given = [uniqueSheetName('붙박이장 1200'), uniqueSheetName('x'.repeat(50)), uniqueSheetName('  '),
               uniqueSheetName('constructor'), uniqueSheetName(' 안방 ')];
  res.toasts = toasts;
  return res;
})();
process.stdout.write(JSON.stringify(out));
"""


def test_new_sheet_names_skip_taken_ones():
    names = ["uniqueSheetName", "addSheet", "duplicateSheet", "deleteSheet", "hideSheetUndoBar",
             "showSheetUndoBar", "restoreDeletedSheet", "cloneSheet"]
    proc = subprocess.run([_node(), "-e", NAME_RUNNER], input=json.dumps([_fn(n) for n in names]),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["first"] == "도면 10"                                   # 겹치지 않으면 예전처럼 '시트 수 + 1'
    assert out["qa3"] == ["도면 2", "도면 4", "도면 5", "도면 6", "도면 7", "도면 8", "도면 9",
                          "도면 10", "도면 11", "도면 12"]
    assert len(set(out["qa3"])) == len(out["qa3"])
    assert out["whileUndo"] == ["도면 1", "도면 2", "도면 4"]            # '도면 3' 은 되돌리기 몫
    assert out["restored"] == ["도면 1", "도면 2", "도면 3", "도면 4"] and out["undoName"] == ""
    assert out["pending"] == ["도면 1", "도면 3"]
    assert out["dup"] == ["주방", "주방 복사 2", "주방 복사"]
    long_name = out["given"][1]
    assert out["given"][0] == "붙박이장 1200 2"                         # '붙박이장 1201' 이 되면 치수가 바뀐다
    assert len(long_name) == 50 and long_name.endswith(" 2")
    assert out["given"][2:] == ["도면 4", "constructor", "안방"]
    assert "시트는 최대 10장까지 만들 수 있습니다." not in out["toasts"]


def test_every_sheet_creation_path_uses_unique_name():
    for name in ("addSheet", "duplicateSheet", "onProductClick", "restoreVersion"):
        assert "uniqueSheetName(" in _fn(name), name
    calls = [ln for ln in JS.splitlines() if "newSheet(" in ln and "function newSheet(" not in ln]
    assert calls and all("uniqueSheetName(" in ln for ln in calls), calls   # 새로 생기는 시트 길도 같은 문을 지난다
    assert "'도면 ' + (state.sheets.length + 1)" not in JS
    assert "pendingNames.push(name.trim());" in _fn("renderPending")
    assert "sheetUndoName = String(entry.sheet.name || '').trim();" in _fn("showSheetUndoBar")
    assert "sheetUndoName = '';" in _fn("hideSheetUndoBar")
