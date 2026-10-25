"""도면 마법사 저장 상태 칩 — 다시 연 창(새로고침·다음 날) 계약.

실화면 QA 3차(2026-10-25, V1):
- 보통: '전달본 예전 것'은 그 창에서 [저장]한 시트만 가렸다. 다시 열어 대기함 시트를 고치고 자동 저장해도
  칩이 '전달 대기함 14:33'(초록)이라 고친 내용이 전달본에 들어간 줄 알았다
  → 불러온 직후 그림 지문을 재 두고(rememberLoadedSheets), 첫 전달 대기함 목록에서 이 창이 넣지 않은
    전달본의 기준으로 삼는다(save-status.js seedQueuedSigs).
- 작음: 새로고침 직후 대기함에 없는 시트는 첫 편집 전까지 칩이 비어 있었다 → 목록을 받으면 '전달본 없음'.
칩 글(save-status.js)은 순수 계산이라 node 로, 창 흐름은 wizard.js 의 실제 함수를 잘라 가짜 화면에서 돌린다.
(test_drawing_wizard_save_status.py 와 같은 방식 — 그 파일이 500줄 래칫에 닿아 나눴다)
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SS_PATH = ROOT / "static/js/drawing/save-status.js"
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")

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
  return S[fn].apply(null, args);
});
process.stdout.write(JSON.stringify(out));
"""


def _calls(calls: list) -> list:
    return _run(CALL_RUNNER, str(SS_PATH), json.dumps(calls, ensure_ascii=False))


NOW = [2026, 10, 25, 9, 20]
SAVED = [2026, 10, 25, 9, 15]


def test_chip_right_after_reload_and_while_box_unknown():
    base = {"canSave": True, "now": NOW}
    cases = [
        dict(base, onServer=True),                                     # 막 열었고 대기함에 없는 시트(예전엔 숨김)
        dict(base, onServer=True, boxKnown=False),                     # 목록을 아직 못 받음 → 숨김('없음'이 깜빡이지 않게)
        dict(base, onServer=True, boxKnown=False, queued=True, queuedAt="2026-10-25 09:12"),   # 이 창이 넣은 것은 말한다
        dict(base, savedAt=SAVED, savedAuto=True, boxKnown=False),     # 목록을 못 읽음: 저장만 말하고 '없음'은 빼기
        dict(base, savedAt=SAVED, savedAuto=False, boxKnown=False),
        dict(base, onServer=True, dirty=True),                         # 고치면 '저장 안 됨'이 먼저
        dict(base, onServer=True, queued=True, queuedAt="2026-10-25 08:33", queuedFresh=False),   # 다시 열어 고침
        dict(base, onServer=True, queued=True, queuedAt="2026-10-25 08:33"),
        dict(base),                                                    # onServer 를 안 주면 예전처럼 숨김(시트 0장 등)
    ]
    got = _calls([["chip", [c]] for c in cases])
    assert [(g["label"], g["kind"]) for g in got] == [
        ("전달본 없음", "none"),
        ("", ""),
        ("전달 대기함 09:12", "queued"),
        ("자동 저장 09:15", "saved"),
        ("작업 저장 09:15", "saved"),
        ("저장 안 됨", "dirty"),
        ("전달본 예전 것", "stale"),
        ("전달 대기함 08:33", "queued"),
        ("", ""),
    ]
    assert got[0]["title"] == "작업 내용은 저장돼 있어요. 이 시트는 아직 전달 대기함에 없어요 — [저장]을 누르면 들어가요."
    for g in got[3:5]:   # 모르는 것을 '없어요'라고 하지 않는다
        assert "아직 전달 대기함에 없어요" not in g["title"] and "전달 대기함은 아직 확인하지 못했어요" in g["title"]
    assert "[저장]을 눌러야 들어가요" in got[6]["title"] and "08:33에" in got[6]["title"]
    assert all("저장됨" not in g["label"] for g in got)


def test_sheet_sig_ignores_remeasured_auto_text_width_and_stays_short():
    text = {"id": "t1", "type": "text", "x": 5, "y": 5, "w": 120, "text": "도어 600", "size": 18}
    image = {"id": "i1", "type": "image", "x": 1, "y": 1, "w": 300, "h": 200, "key": "k"}
    sheet = {"id": "s1", "name": "도면 1", "objects": [text, image]}

    def variant(fn):
        s = json.loads(json.dumps(sheet))
        fn(s)
        return s

    remeasured = variant(lambda s: s["objects"][0].update(w=121))      # 그릴 때 글꼴로 다시 잰 폭(컴퓨터마다 1px 다름)
    retyped = variant(lambda s: s["objects"][0].update(text="도어 650"))
    fixed = variant(lambda s: s["objects"][0].update(autoWidth=False))
    fixed_wider = variant(lambda s: s["objects"][0].update(autoWidth=False, w=160))   # 폭을 정한 글자는 폭이 그림이다
    image_wider = variant(lambda s: s["objects"][1].update(w=301))
    big = variant(lambda s: s["objects"].append({"id": "p1", "type": "pen", "points": list(range(4000))}))
    sigs = _calls([["sheetSig", [s]] for s in (sheet, remeasured, retyped, fixed, fixed_wider, image_wider, big)])
    a, b, c, d, e, f, g = sigs
    assert a == b                      # 다시 연 뒤 손대지 않았는데 '고침'으로 보이면 안 된다
    assert len({a, c, d, e, f, g}) == 6
    assert all(isinstance(x, str) and 0 < len(x) < 24 for x in sigs)   # 시트 글 전체가 아니라 짧은 지문만 들고 있다


SEED_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const S = window.FomsSaveStatus;
const out = {};
out.sigs = S.sheetSigs([{ id: 'a', objects: [] }, { name: 'id 없음' }, null, { id: 'b', objects: [{ id: 'o', type: 'rect', x: 1 }] }]);
// 이 창에서 넣은 s1 은 그대로 · 다시 연 창이 처음 본 s2 는 불러온 기준 · 불러온 기준이 없는 s4 는 모름(새것)
out.fromSet = S.seedQueuedSigs({ s1: 'mine' }, { s1: 'L1', s2: 'L2', s3: 'L3' }, new Set(['s1', 's2', 's4']));
out.fromArray = S.seedQueuedSigs({}, { s2: 'L2' }, ['s2']);
out.noLoaded = S.seedQueuedSigs({ s1: 'mine' }, null, ['s1', 's2']);
out.sameObject = (function () { const q = {}; return S.seedQueuedSigs(q, { s2: 'L2' }, ['s2']) === q; })();
process.stdout.write(JSON.stringify(out));
"""


def test_seed_queued_sigs_uses_loaded_baseline_only_where_unknown():
    out = _run(SEED_RUNNER, str(SS_PATH))
    assert sorted(out["sigs"]) == ["a", "b"] and out["sigs"]["a"] != out["sigs"]["b"]
    assert out["fromSet"] == {"s1": "mine", "s2": "L2"}
    assert out["fromArray"] == {"s2": "L2"}
    assert out["noLoaded"] == {"s1": "mine"}
    assert out["sameObject"] is True   # wizard.js 의 queuedSigBySheet 를 그 자리에서 채운다


RELOAD_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const fs = require('fs');
const src = JSON.parse(fs.readFileSync(0, 'utf8'));
function el(tag) {
  const e = { tagName: String(tag || 'div').toUpperCase(), children: [], hidden: true, title: '', className: '' };
  let text = '';
  Object.defineProperty(e, 'textContent', { get: () => text, set: (v) => { text = String(v); e.children = []; } });   // 글을 넣으면 안의 칸이 비워진다
  e.appendChild = (n) => { e.children.push(n); return n; };
  e.addEventListener = () => {};
  return e;
}
const classes = new Set();
var document = { createElement: el };
var API_BASE = '/api', canSave = true, current = 0, hydrated = false;
var saveInFlight = false, saveFailed = false, dirty = false, autosaveStopped = false, autosaveSuspended = false;
var lastSavedAt = null, lastSaveAuto = false;
var pendingSheetIds = new Set(), pendingAtBySheet = {}, queuedSigBySheet = {}, loadedSigBySheet = null, pendingKnown = false, pendingNames = [];
var state = { sheets: [
  { id: 's1', name: '도면 1', objects: [{ id: 'o1', type: 'image', x: 10, y: 10, w: 300, h: 200, key: 'k' },
                                       { id: 't1', type: 'text', x: 5, y: 5, w: 120, text: '도어 600', size: 18 }] },
  { id: 's8', name: '도면 8', objects: [] }] };
var els = {
  delSavedBtn: { hidden: true }, pending: el('div'), pendingGrid: el('div'), pendingTitle: el('span'),
  saveStatus: { hidden: true, textContent: '', title: '', classList: { toggle: (k, on) => { if (on) { classes.add(k); } else { classes.delete(k); } } } }
};
const replies = [], toasts = [];
function jsonFetch() { return replies.length ? replies.shift() : Promise.reject(new Error('no reply')); }
function ok(list) { return Promise.resolve({ status: 200, data: { success: true, data: { pending: list } } }); }
function viewUrl(k) { return '/v/' + k; }
function openLightbox() {} function confirmDeleteQueued() { return true; }
function toast(m) { toasts.push(m); } function serverErrorText(r, d) { return d; }
console.warn = () => {};
eval(src.join('\n'));
const snap = () => ({ x: !els.delSavedBtn.hidden, chip: els.saveStatus.hidden ? '' : els.saveStatus.textContent.replace(/\d\d:\d\d$/, 'HH:MM'),
  kind: [...classes].join(' ') });
const tick = () => new Promise((r) => setTimeout(r, 0));
(async () => {
  const out = {};
  // 새로고침: load() 가 서버 내용을 받은 직후 — 아직 전달 대기함 목록 전
  rememberLoadedSheets(); syncSheetSaveUi(); out.beforeList = snap();
  hydrated = true;
  replies.push(ok([{ key: 'k1', sheet_id: 's1', sheet_name: '도면 1', at: '2026-10-25 14:33' }]));
  refreshPending(); await tick(); out.listed = snap();
  // 그릴 때 자동 폭 글자를 다시 잼(손대지 않음) → 그대로 '전달 대기함'
  state.sheets[0].objects[1].w = 123; syncSheetSaveUi(); out.remeasured = snap();
  // 대기함에 없는 시트: 첫 편집 전에도 '전달본 없음'
  current = 1; syncSheetSaveUi(); out.notQueued = snap();
  // 다시 연 뒤 대기함 시트를 1px 옮기고 자동 저장 → '전달본 예전 것'
  current = 0; state.sheets[0].objects[0].x = 11; dirty = true; syncSheetSaveUi(); out.dirty = snap();
  dirty = false; lastSavedAt = new Date(); lastSaveAuto = true; syncSheetSaveUi(); out.autosaved = snap();
  current = 1; syncSheetSaveUi(); out.otherAutosaved = snap(); current = 0;
  // [저장]으로 다시 넣으면 새 기준 → '전달 대기함'
  noteQueued(state.sheets[0], window.FomsSaveStatus.sheetSig(state.sheets[0])); lastSaveAuto = false;
  syncSheetSaveUi(); out.requeued = snap();
  // 다음 목록: 첫 목록 기준은 다시 깔지 않는다 · 다른 창이 넣은 s8 은 기준을 모른다(새것으로 본다)
  replies.push(ok([{ key: 'k1b', sheet_id: 's1', sheet_name: '도면 1', at: '2026-10-25 14:50' },
                   { key: 'k8', sheet_id: 's8', sheet_name: '도면 8', at: '2026-10-25 14:51' }]));
  refreshPending(); await tick(); out.afterSave = snap();
  current = 1; syncSheetSaveUi(); out.otherWindow = snap(); current = 0;
  // 목록을 못 읽으면(끊김·서버 오류) 알던 것을 지우지 않는다
  replies.push(Promise.reject(new Error('net'))); refreshPending(); await tick(); out.netFail = snap();
  replies.push(Promise.resolve({ status: 500, data: null })); refreshPending(); await tick(); out.serverFail = snap();
  out.panelKept = !els.pending.hidden && els.pendingGrid.children.length;
  // 전달본 지우기: 다시 읽기가 실패해도 ×·칩이 바로 따른다
  replies.push(Promise.resolve({ status: 200, data: { success: true } }), Promise.reject(new Error('net')));
  deletePending('s1'); await tick(); out.deleted = snap();
  out.toasts = toasts;
  // 다시 불러오기(충돌 뒤 load): 기준·목록 확인을 비우고 새로 잰다
  rememberLoadedSheets();
  out.reloaded = { known: pendingKnown, queued: Object.keys(queuedSigBySheet).length, loaded: Object.keys(loadedSigBySheet || {}).sort() };
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
"""


def test_reopened_window_marks_edited_queued_sheet_stale():
    names = ["currentSheet", "hhmm", "updateDeleteSavedBtn", "queuedStateOf", "noteQueued", "rememberLoadedSheets",
             "syncSheetSaveUi", "renderSaveStatus", "refreshPending", "renderPending", "deletePending"]
    proc = subprocess.run([_node(), "-e", RELOAD_RUNNER, str(SS_PATH)], input=json.dumps([_fn(n) for n in names]),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["beforeList"] == {"x": False, "chip": "", "kind": ""}            # 목록 전에는 '없음'을 말하지 않는다
    assert out["listed"] == {"x": True, "chip": "전달 대기함 HH:MM", "kind": "dws-save-status-queued"}
    assert out["remeasured"] == out["listed"]
    assert out["notQueued"] == {"x": False, "chip": "전달본 없음", "kind": "dws-save-status-none"}   # 예전엔 숨김
    assert out["dirty"]["chip"] == "저장 안 됨"
    assert out["autosaved"] == {"x": True, "chip": "전달본 예전 것", "kind": "dws-save-status-stale"}   # 예전엔 '전달 대기함 14:33'
    assert out["otherAutosaved"]["chip"] == "자동 저장 HH:MM"
    assert out["requeued"]["chip"] == "전달 대기함 HH:MM"
    assert out["afterSave"] == {"x": True, "chip": "전달 대기함 HH:MM", "kind": "dws-save-status-queued"}
    assert out["otherWindow"] == {"x": True, "chip": "전달 대기함 HH:MM", "kind": "dws-save-status-queued"}
    assert out["netFail"] == out["afterSave"] and out["serverFail"] == out["afterSave"]
    assert out["panelKept"] == 2
    assert out["deleted"] == {"x": False, "chip": "전달본 없음", "kind": "dws-save-status-none"}
    assert out["toasts"] == ["전달본을 지웠어요. 시트 그림은 그대로예요."]
    assert out["reloaded"] == {"known": False, "queued": 0, "loaded": ["s1", "s8"]}


def test_load_takes_baseline_before_auto_fills_and_chip_gets_box_state():
    load = _fn("load")
    i = load.index("rememberLoadedSheets();")
    assert load.index("state = normalizeState(d.state);") < i < load.index("d.drew_assignee_en")
    assert i < load.index("s.form.page_no = '-'") and i < load.index("refreshPending();")
    assert "dirty = true" not in load.splitlines()[load[:i].count("\n")]   # 자동 저장 가드(dirty 줄 2개)는 그대로
    chip = _fn("renderSaveStatus")
    assert "boxKnown: pendingKnown" in chip and "onServer: hydrated && !!currentSheet()" in chip
    refresh = _fn("refreshPending")
    assert "renderPending([])" not in refresh                                   # 못 읽었다고 알던 전달본을 지우지 않는다
    assert refresh.index("pendingKnown = true;") < refresh.index("renderPending(r.data.data.pending);")
    pend = _fn("renderPending")
    assert "seedQueuedSigs(queuedSigBySheet, loadedSigBySheet, pendingSheetIds)" in pend
    assert pend.index("loadedSigBySheet = null;") < pend.index("syncSheetSaveUi();")
    assert "var loadedSigBySheet = null;" in JS and "var pendingKnown = false;" in JS
