"""도면 마법사 자동 배치 '시트 나누기' 계약 테스트(실화면 재평가 2026-10-25 QA3 큼·보통·작음).

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.2 (다 안 들어가면 더 줄이지 않고 나누기)
- part-split.js(순수 계산): 시트마다 치수 글자 8px 이상을 지키는 나누기 계획 — 짝은 함께, 정면 모듈은 순서대로,
  필요한 시트 수를 한 번에 센다(나눈 뒤 또 '더 옮기기' 창이 뜨지 않게).
- wizard.js 연결은 함수를 떼어 node vm 에서 가짜 시트로 끝까지 돌린다: 마법사가 새 시트를 만들어 옮기고,
  원래 시트에서 Ctrl+Z 한 번이면 새 시트까지 함께 되돌아가 그림이 두 시트에 겹치지 않는다.
  같이 올린 여러 장은 되돌리기 한 번에 지워지고(마지막 한 장만 사라지지 않게), 돌리거나 잠근 그림은 알린다.
"""

import functools
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "static/js/drawing"
AREA = {"x0": 51, "y0": 103, "x1": 1429, "y1": 887}
GEO = {"area": AREA, "obstacles": [{"x": 1366, "y": 32, "w": 82, "h": 65}], "reserve": {"x": 620, "y": 103, "w": 809, "h": 250}}


def _node_json(runner, args, payload):
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, "-e", runner] + [str(a) for a in args], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_part_split_script_stays_under_ratchet():
    assert len((D / "part-split.js").read_text(encoding="utf-8").splitlines()) < 300   # 새 JS 300줄 래칫


SPLIT_RUNNER = r"""
global.window = {};
for (const f of ['part-pack.js', 'part-layout.js', 'part-split.js']) require(process.argv[1] + '/' + f);
const job = JSON.parse(require('fs').readFileSync(0, 'utf8')), L = window.FomsPartLayout;
process.stdout.write(JSON.stringify(job.cases.map(c => {
  const plan = window.FomsPartSplit.plan(c.items, job.geo, job.geo, { minText: 8, maxSheets: c.max });
  const fit = plan.sheets.map(ids => L.arrange(c.items.filter(it => ids.indexOf(it.id) >= 0), job.geo.area, job.geo.obstacles,
    { reserve: job.geo.reserve }).crowded);
  return { plan: plan, again: window.FomsPartSplit.plan(c.items, job.geo, job.geo, { minText: 8, maxSheets: c.max }), crowded: fit };
})));
"""


def _pairs(n, tx):
    out = []
    for i in range(n):
        out.append({"id": f"in{i}", "nw": 370, "nh": 598, "label": "정면·내부", "order": 2 * i, "tx": tx})
        out.append({"id": f"dr{i}", "nw": 370, "nh": 598, "label": "정면·도어", "order": 2 * i + 1, "tx": tx})
    return out


def _qa3_twenty():
    """실화면 QA3 '20장'(모듈 4짝 + 큰 정면 2 + 입체 5 + 평면 2 + 서랍 2 + 사진 1)과 같은 크기·글자 높이."""
    spec = [("m1-in", 370, 598, "정면·내부", 27), ("m1-door", 370, 598, "정면·도어", 27), ("m2-in", 232, 580, "정면·내부", 27),
            ("m2-door", 232, 580, "부품 상세", 27), ("m3-in", 234, 580, "정면·내부", 27), ("m3-door", 234, 580, "부품 상세", 27),
            ("m4-in", 292, 598, "정면·내부", 27), ("m4-door", 292, 598, "정면·도어", 27), ("s16-in", 1440, 610, "정면·내부", 23.4),
            ("s17-in", 1396, 784, "정면·내부", 27.9), ("s16-door", 1392, 826, "입체·도어", 24.4),
            ("s13-iso-in", 1222, 652, "입체·내부", 24.4), ("s13-iso-door", 1222, 652, "입체·도어", 24.4),
            ("s1-iso-in", 1614, 864, "입체·내부", 22.2), ("s1-iso-door", 1614, 865, "입체·도어", 24.2),
            ("s13-plan", 1004, 832, "평면·상판", 26.4), ("s1-plan", 1069, 549, "평면·상판", 16),
            ("s12-drawer", 401, 336, "서랍 단면", 22), ("s13-drawer", 598, 300, "서랍 단면", 26), ("s12-photo", 390, 520, "사진", 21)]
    return [{"id": i, "nw": w, "nh": h, "label": lab, "order": k, "tx": tx} for k, (i, w, h, lab, tx) in enumerate(spec)]


def test_split_plan_keeps_text_pairs_and_module_order():
    cases = [{"items": _pairs(16, 26), "max": 10}, {"items": _qa3_twenty(), "max": 10}, {"items": _pairs(30, 26), "max": 2}]
    many, qa3, limited = _node_json(SPLIT_RUNNER, [D], {"geo": GEO, "cases": cases})
    for res, case in ((many, cases[0]), (qa3, cases[1])):
        plan = res["plan"]
        assert plan == res["again"]                                             # 같은 입력이면 같은 계획
        ids = [i for sheet in plan["sheets"] for i in sheet]
        assert sorted(ids) == sorted(it["id"] for it in case["items"])           # 빠짐·겹침 없이 한 번씩
        assert plan["ok"] is True and len(plan["sheets"]) >= 2
        assert res["crowded"] == [False] * len(plan["sheets"])                  # 시트마다 치수 글자 8px 이상
        assert [c["n"] for c in plan["counts"]] == [len(s) for s in plan["sheets"]]
    sheet_of = {i: k for k, sheet in enumerate(many["plan"]["sheets"]) for i in sheet}
    assert all(sheet_of[f"in{i}"] == sheet_of[f"dr{i}"] for i in range(16))     # 짝은 갈라 옮기지 않는다
    qs = {i: k for k, sheet in enumerate(qa3["plan"]["sheets"]) for i in sheet}
    fronts = [qs[i] for i in ("m1-in", "m2-in", "m3-in", "m4-in", "s16-in", "s17-in")]
    assert fronts == sorted(fronts)                                              # 정면 모듈은 고른 순서대로만
    assert qs["s13-iso-in"] == qs["s13-iso-door"] and qs["s1-iso-in"] == qs["s1-iso-door"]
    assert len(qa3["plan"]["sheets"]) == 3                                       # 예전: 9장 남기고 11장 → 다시 '8장 더 옮기기'
    assert qa3["plan"]["counts"][0]["front"] >= 5                               # 모듈 = 정면 묶음 수(짝은 1개)
    plan = limited["plan"]                                                      # 시트가 모자라면 남은 그림은 마지막 시트에
    assert len(plan["sheets"]) == 2 and plan["ok"] is False and sum(map(len, plan["sheets"])) == 60


PHOTO_RUNNER = r"""
global.window = {};
for (const f of ['part-pack.js', 'part-layout.js', 'part-split.js']) require(process.argv[1] + '/' + f);
const job = JSON.parse(require('fs').readFileSync(0, 'utf8')), L = window.FomsPartLayout;
const lay = items => L.arrange(items, job.geo.area, job.geo.obstacles, { reserve: job.geo.reserve });
process.stdout.write(JSON.stringify(job.cases.map(items => {
  const plan = window.FomsPartSplit.plan(items, job.geo, job.geo, { maxSheets: 10 });
  return { all: lay(items), plan: plan, sheets: plan.sheets.map(ids => lay(items.filter(it => ids.indexOf(it.id) >= 0))) };
})));
"""


def _v3_twenty():
    """실화면 V3 '20장' 나누기 재현: QA3 20장 + 파일 대화 상자 이름순(자연 정렬) 고른 순서, 입체 도어 하나는 미분류.
    예전 계획은 원래 시트에 15장을 두며 사진을 63×84 로 줄였다(V62-split-original.png 와 같은 자리)."""
    nat = ["m1-door", "m1-in", "m2-door", "m2-in", "m3-door", "m3-in", "m4-door", "m4-in", "s1-iso-door", "s1-iso-in", "s1-plan",
           "s12-drawer", "s12-photo", "s13-drawer", "s13-iso-door", "s13-iso-in", "s13-plan", "s16-door", "s16-in", "s17-in"]
    items = [dict(it, order=nat.index(it["id"])) for it in _qa3_twenty()]
    for it in items:
        if it["id"] == "s13-iso-door":
            it["label"] = "미분류"
    return items


def test_split_moves_photo_when_it_would_shrink_below_min_height():
    photos = [{"id": f"p{i}", "nw": 520 if i % 2 else 390, "nh": 390 if i % 2 else 520, "label": "사진", "order": i, "tx": 0}
              for i in range(40)]
    pile = _pairs(1, 27) + [dict(p, order=p["order"] + 2) for p in photos]
    twenty, many = _node_json(PHOTO_RUNNER, [D], {"geo": GEO, "cases": [_v3_twenty(), pile]})
    by = {it["id"]: it for it in _v3_twenty()}
    for res in (twenty, many):
        assert res["plan"]["ok"] is True and len(res["plan"]["sheets"]) >= 2
        for sheet in res["sheets"]:                                              # 나눈 시트마다: 글자 8px 이상 · 사진 높이 120 이상
            assert sheet["crowded"] is False and (sheet["minText"] is None or sheet["minText"] >= 8)
            assert sheet["photo"] is None or sheet["photo"] >= 120, sheet["photo"]
    first = twenty["plan"]["sheets"][0]
    assert "s12-photo" not in first and len(first) == 14                        # 사진은 원래 시트(15장 → 14장)에서 새 시트로
    assert sum(c["photo"] for c in twenty["plan"]["counts"][1:]) == 1           # 창 글 '… · 사진 1장' 으로 센다
    assert twenty["all"]["crowded"] is True and twenty["all"]["why"] == "text"  # 다 넣으면 글자부터 작아진다
    # 그림 한 짝 + 사진 40장: 글자는 되지만 사진이 우표만 해진다 → 까닭 'photo', '그래도 이 시트에' 는 글자를 지킨 배치(사진만 작게)
    keep = many["all"]
    assert keep["crowded"] is True and keep["why"] == "photo" and keep["minText"] >= 8 and 40 <= keep["photo"] < 120
    assert by["s12-photo"]["label"] == "사진"


GLUE_RUNNER = r"""
const fs = require('fs'), vm = require('vm'), NL = String.fromCharCode(10);
const dir = process.argv[1], src = fs.readFileSync(dir + '/wizard.js', 'utf8').split(String.fromCharCode(13)).join('');
function fn(name) {
  const s = src.indexOf(NL + '  function ' + name + '(') + 1;
  if (s < 1) { throw new Error('no fn ' + name); }
  const eol = src.indexOf(NL, s), first = src.slice(s, eol);
  if (/\}\s*$/.test(first) && first.split('{').length === first.split('}').length) { return first; }
  return src.slice(s, src.indexOf(NL + '  }' + NL, s) + 4);
}
function line(prefix) { const s = src.indexOf(NL + '  ' + prefix) + 1; if (s < 1) { throw new Error('no ' + prefix); } return src.slice(s, src.indexOf(NL, s)); }
const LOG = { toasts: [], tabs: 0, sel: null, asked: null };
const ctx = { console, Promise, setTimeout, Math, JSON, Object, Array, isFinite, String, Number, LOG };
ctx.window = ctx;
vm.createContext(ctx);
for (const f of ['part-pack.js', 'part-layout.js', 'part-split.js', 'part-arrange.js']) { vm.runInContext(fs.readFileSync(dir + '/' + f, 'utf8'), ctx); }
vm.runInContext([
  'var state = { sheets: [] }, current = 0, undoStack = [], redoStack = [], sheetHistories = {}, RID = 0, CHOICE = null;',
  "var UI = 'v1'; function emitCore() {}",   // V1 화면 — V2 연결 사건은 아무도 듣지 않는다(설계서 2026-10-26 V2)
  'var canSave = true, selected = null, selectedIds = [], nodeById = {}, partTextH = {}, partUploadSeq = {}, partBatchNo = 0;',
  "var defaults = { page_no: '', product_name: '', checks: { d_site: false } };",
  'var els = { form: { querySelector: function () { return { offsetTop: 43, offsetHeight: 52 }; } } };',
  'function rid(p) { RID += 1; return p + RID; }',
  'function cloneForm(d) { return JSON.parse(JSON.stringify(d || {})); }',
  "function seedPresetObjects() { return ['[SR]', '[EP]', '[DOOR]', '[옷봉]', '[마이다]'].map(function (t, i) {",
  "  return { id: rid('o-'), type: 'text', x: 628 + 170 * i, y: 120, w: 1, text: t + '\\n', size: 20 }; }); }",
  "function newSheet(name, d) { return { id: rid('s-'), name: name, form: cloneForm(d), objects: seedPresetObjects(), presets_seeded: true }; }",
  'function loadPreferredTextSize() { return 20; }',
  "function uniqueSheetName(want) { var names = state.sheets.map(function (s) { return s.name; }), n = 2, name = want;",
  "  while (names.indexOf(name) >= 0) { name = want + ' ' + n; n += 1; } return name; }",
  'function isFiniteNum(v) { return typeof v === "number" && isFinite(v); }',
  'function toast(m) { LOG.toasts.push(m); }',
  'function markDirty() {} function renderForm() {} function renderTabs() { LOG.tabs += 1; } function syncProductActive() {}',
  'function deselect() { selectedIds = []; } function applySelection() { LOG.sel = selectedIds.slice(); }',
  'function rebuildAnno() { nodeById = {}; (currentSheet() ? currentSheet().objects : []).forEach(function (o) { nodeById[o.id] = mkNode(o); }); }',
  'function mkNode(o) { return { image: function () { return null; }, getClientRect: function () {',
  "  if (o.type === 'text') { return { x: o.x, y: o.y, width: 40, height: String(o.text).split('\\n').length * 25 }; }",
  '  return o.rotation ? { x: o.x - o.h, y: o.y, width: o.h, height: o.w } : { x: o.x, y: o.y, width: o.w, height: o.h }; } }; }',
  'window.FomsPartBadges = { refresh: function () {} };',
  'window.FomsPartTextSize = { fromImage: function () { return 26; } };',
  'window.FomsPartArrange.ask = function (o) { LOG.asked = o; return Promise.resolve(CHOICE); };',
  "function img(id, nw, nh, label) { partTextH['k-' + id] = 26; return { id: id, type: 'image', x: 289, y: 120, w: nw, h: nh, key: 'k-' + id,",
  "  natural_w: nw, natural_h: nh, rotation: 0, part: { label: label, src: 'ai' } }; }",
  'function sheetWithPairs(n) { var s = { id: rid("s-"), name: "도면 1", form: { page_no: "1", product_name: "붙박이장", checks: { d_site: true } },',
  '  objects: seedPresetObjects() }; for (var i = 0; i < n; i++) { s.objects.push(img("in" + i, 370, 598, "정면·내부")); s.objects.push(img("dr" + i, 370, 598, "정면·도어")); } return s; }',
  'function reset(s) { state.sheets = [s]; current = 0; sheetHistories = {}; partSplitLinks = []; partSplitGone = null; bindSheetHistory();',
  '  rebuildAnno(); LOG.toasts = []; LOG.sel = null; }',
  'function imageIds() { return state.sheets.reduce(function (a, s) { return a.concat(s.objects.filter(function (o) { return o.type === "image"; })',
  '  .map(function (o) { return o.id; })); }, []); }',
  'function view() { return state.sheets.map(function (s) { return { id: s.id, name: s.name, form: s.form,',
  "  texts: s.objects.filter(function (o) { return o.type === 'text'; }).length,",
  "  imgs: s.objects.filter(function (o) { return o.type === 'image'; }).map(function (o) { return [o.id, o.x, o.y, o.w, o.h, o.rotation || 0]; }) }; }); }",
].join(NL), ctx);
const names = ['currentSheet', 'cloneSheet', 'findObj', 'bindSheetHistory', 'pushUndoSnapshot', 'recordUndo', 'swapInHistory', 'undo', 'redo',
  'normalizeRotation', 'sizeOrDefault', 'num', 'sanitizePart', 'partWith', 'partTextOf', 'newPartBatch', 'recordBatchUndo', 'partTableTop',
  'partObjRect', 'partArea', 'partPad', 'partItem', 'partArrangePlan', 'partFreshPlan', 'partArrangedText', 'autoArrangeImages',
  'askCrowdedArrange', 'partSplitPlan', 'splitPartSheets', 'partSheetSig', 'partSplitUndone', 'applyPartArrangement', 'partPlace',
  'refreshPartBadges', 'partSplitSource', 'partSplitHint', 'restoreDeletedSheet'];
vm.runInContext([line('var PART_FRAME ='), line('var PART_BORDER ='), line('var PART_LABELS ='), line('var LAYOUT_DEFAULT ='),
  line('var ALLOWED_SIZES ='), line('var partSplitLinks ='), line('var partSplitGone =')].concat(names.map(fn)).join(NL), ctx);
const run = code => vm.runInContext(code, ctx), tick = () => new Promise(r => setTimeout(r, 5)), out = {};
(async () => {
  run('reset(sheetWithPairs(16)); CHOICE = "split"; autoArrangeImages(false);');
  await tick();
  out.asked = { title: LOG.asked.title, lines: LOG.asked.lines, buttons: LOG.asked.buttons.map(b => [b.id, b.label, !!b.primary]) };
  out.split = { sheets: run('view()'), toast: LOG.toasts.slice(-1)[0], undo: run('undoStack.length'), links: run('partSplitLinks.length') };
  run('undo();');
  out.undone = { sheets: run('view()'), toast: LOG.toasts.slice(-1)[0], redo: run('redoStack.length'), links: run('partSplitLinks.length') };
  run('reset(sheetWithPairs(16)); CHOICE = "split"; autoArrangeImages(false);');
  await tick();
  run('state.sheets[1].objects.filter(function (o) { return o.type === "text"; })[0].text = "[SR]\\n110*2440=2\\n";' +
    'sheetHistories[state.sheets[1].id] = { undo: [1], redo: [] }; undo();');
  out.edited = { sheets: run('view()'), toast: LOG.toasts.slice(-1)[0], hist: run('JSON.stringify(sheetHistories[state.sheets[1].id])') };
  run('reset({ id: "b0", name: "x", form: {}, objects: [] }); var b = newPartBatch(3);' +
    'recordBatchUndo(b); currentSheet().objects.push(img("a1", 300, 300, "사진"));' +
    'recordBatchUndo(b); currentSheet().objects.push(img("a2", 300, 300, "사진")); LOG.n1 = undoStack.length;' +
    'recordUndo(); currentSheet().objects.push({ id: "t9", type: "text", x: 60, y: 600, text: "메모" });' +
    'recordBatchUndo(b); currentSheet().objects.push(img("a3", 300, 300, "사진")); LOG.n2 = undoStack.length; LOG.after = [];' +
    'for (var u = 0; u < 3; u++) { undo(); LOG.after.push(currentSheet().objects.map(function (o) { return o.id; }).join(",")); }');
  out.batch = { n1: LOG.n1, n2: LOG.n2, after: LOG.after };
  out.texts = run('[partArrangedText(null), partArrangedText({ late: 3, ids: [1, 2, 3] }), partArrangedText({ late: 1, ids: [1, 2, 3] })]');
  run('var s5 = sheetWithPairs(2), r = img("rot", 390, 520, "사진"); r.x = 10; r.y = 600; r.rotation = 90; s5.objects.push(r);' +
    'reset(s5); CHOICE = null; autoArrangeImages(false);');
  out.rotated = { toast: LOG.toasts.slice(-1)[0], sel: LOG.sel, rot: run('JSON.stringify(view()[0].imgs.filter(function (i) { return i[0] === "rot"; })[0])') };
  run('var s6 = sheetWithPairs(1); s6.objects.push(img("pd", 232, 580, "부품 상세"), img("pi", 232, 580, "정면·내부")); reset(s6);' +
    'autoArrangeImages(false);');
  out.guess = { toast: LOG.toasts.slice(-1)[0], label: run('findObj("pd").part.label + "/" + findObj("pd").part.src') };
  run('reset(sheetWithPairs(16)); CHOICE = null; LOG.before = JSON.stringify(view()); autoArrangeImages(false);');
  await tick();
  out.later = { toast: LOG.toasts.slice(-1)[0], same: run('JSON.stringify(view())') === LOG.before, undo: run('undoStack.length') };
  // 실화면 V3: 나누기로 생긴 시트에서 Ctrl+Z·Ctrl+Y(이력이 빔) — 어느 시트에서 되돌리는지 알리고 그림·시트는 그대로
  run('reset(sheetWithPairs(16)); CHOICE = "split"; autoArrangeImages(false);');
  await tick();
  run('LOG.toasts = []; current = 1; bindSheetHistory(); LOG.before = JSON.stringify(view()); undo(); redo();');
  out.fresh = { toasts: LOG.toasts.slice(), same: run('JSON.stringify(view())') === LOG.before };
  // 원래 시트에서 나누기를 되돌린 뒤 Ctrl+Y(다시 하기 칸은 일부러 비움) — 다시 나누는 길을 알리고, 그 뒤 손을 대면 조용히
  run('LOG.toasts = []; current = 0; bindSheetHistory(); undo(); LOG.mid = JSON.stringify(view()); redo();');
  out.redo = { toasts: LOG.toasts.slice(), same: run('JSON.stringify(view())') === LOG.mid };
  run('LOG.toasts = []; recordUndo(); redo(); current = 0; undo(); undo();');
  out.quiet = LOG.toasts.slice();
  // 나누기로 생긴 시트를 지우고(되살리기 기다림) 원래 시트에서 나누기를 되돌린 뒤 되살리면 — 옮겼던 그림은 빼고 되살린다
  run('reset(sheetWithPairs(16)); CHOICE = "split"; autoArrangeImages(false);');
  await tick();
  run('var gone = state.sheets[1]; LOG.entry = { sheet: cloneSheet(gone), index: 1, wasCurrent: false,' +
    ' hist: { undo: [cloneSheet(gone)], redo: [] } }; state.sheets.splice(1, 1); delete sheetHistories[gone.id];' +
    'LOG.toasts = []; undo(); restoreDeletedSheet(LOG.entry);');
  out.restore = { ids: run('imageIds()'), sheets: run('view()'), toasts: LOG.toasts.slice(),
    hist: run('JSON.stringify(sheetHistories[LOG.entry.sheet.id])') };
  run('reset({ id: "r0", name: "도면 3", form: {}, objects: [img("solo", 300, 300, "사진")] }); var e2 = { sheet: { id: "r1", name: "도면 4",' +
    ' form: {}, objects: [img("own", 300, 300, "사진")] }, index: 1, wasCurrent: false, hist: { undo: [1], redo: [] } }; restoreDeletedSheet(e2);');
  out.restorePlain = { toast: LOG.toasts.slice(-1)[0], hist: run('sheetHistories.r1.undo.length'), ids: run('imageIds()') };
  // 나누기 알림에도 돌리거나 잠가 그대로 둔 그림·짝 자리 짐작을 붙이고(테두리 밖이면 골라 둔다), 창 글에 그대로 둘 그림 수를 적는다
  run('var s7 = sheetWithPairs(16), r7 = img("rot", 390, 520, "사진"); r7.x = 10; r7.y = 600; r7.rotation = 90; s7.objects.push(r7);' +
    's7.objects.push(img("pd", 232, 580, "부품 상세"), img("pi", 232, 580, "정면·내부")); reset(s7); CHOICE = "split"; autoArrangeImages(false);');
  await tick();
  out.notes = { lines: LOG.asked.lines, toast: LOG.toasts.slice(-1)[0], sel: LOG.sel, ids: run('imageIds()') };
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""


def _overlap(a, b):
    return a[1] < b[1] + b[3] and b[1] < a[1] + a[3] and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]


@functools.lru_cache(maxsize=1)
def _glue():
    """wizard.js 연결 러너는 한 번만 돌리고 결과를 시험끼리 나눠 읽는다(읽기만 한다)."""
    return _node_json(GLUE_RUNNER, [D], {})


def test_wizard_splits_into_new_sheets_and_one_undo_restores_both():
    res = _glue()
    asked = res["asked"]
    assert asked["title"] == "그림이 많아 글자가 작아져요"
    labels = [b[1] for b in asked["buttons"]]
    assert labels[0] == "나중에 (겹친 채 두기)" and labels[1] == "그래도 이 시트에"            # 닫기 = 겹친 채 둔다는 것을 단추에
    assert asked["buttons"][2][0] == "split" and asked["buttons"][2][2] is True and labels[2].endswith("장으로 나누기")
    n = int(labels[2].split("시트 ")[1].split("장")[0])
    assert asked["lines"][1] == f"시트 {n}장으로 나누면 치수 글자를 모두 8px 이상으로 놓을 수 있어요."
    # 나누기: 마법사가 새 시트를 지금 시트 바로 뒤에 만들어 옮기고 시트마다 다시 배치한다
    sheets = res["split"]["sheets"]
    assert len(sheets) == n and [s["name"] for s in sheets[1:]] == ["도면 1 2", "도면 1 3"][:n - 1]
    ids = [i[0] for s in sheets for i in s["imgs"]]
    assert sorted(ids) == sorted([f"in{i}" for i in range(16)] + [f"dr{i}" for i in range(16)])   # 한 번씩만
    for s in sheets:
        for k, a in enumerate(s["imgs"]):
            assert 51 <= a[1] and a[1] + a[3] <= 1429 and 103 <= a[2] and a[2] + a[4] <= 887, a
            assert all(not _overlap(a, b) for b in s["imgs"][k + 1:]), (a, s["name"])
    for s in sheets[1:]:
        assert s["texts"] == 5 and s["form"]["product_name"] == "붙박이장"             # 자리표·머리칸 글은 이어받고
        assert s["form"]["checks"] == {"d_site": False} and s["form"]["page_no"] == ""   # 확인 표시·쪽번호는 새로
    assert res["split"]["undo"] == 1 and res["split"]["links"] == 1
    # 실화면 V3: 새 시트로 가서 Ctrl+Z 를 누른 사람이 어디서 되돌리는지 알게 시트 이름을 넣는다
    assert res["split"]["toast"].startswith("그림 ")
    assert res["split"]["toast"].endswith('으로 옮겨 배치했어요 · 되돌리기: "도면 1" 시트에서 Ctrl+Z')
    # 원래 시트에서 Ctrl+Z 한 번 → 새 시트까지 사라지고 그림 32장이 원래 시트에 한 번씩(두 시트에 겹치지 않음)
    undone = res["undone"]
    assert len(undone["sheets"]) == 1 and len(undone["sheets"][0]["imgs"]) == 32
    assert undone["redo"] == 0 and undone["links"] == 0                         # 한쪽만 다시 나누는 Ctrl+Y 는 막는다
    assert undone["toast"] == ("나누기를 되돌렸어요 — 옮긴 그림 " + str(32 - len(sheets[0]["imgs"])) + "장이 이 시트로 돌아왔어요"
                               " · 다시 나누려면 위의 [자동 배치]")
    # 새 시트에 손댄 뒤 원래 시트에서 되돌리면: 그 시트는 남기고 옮긴 그림만 빼며 그 시트 이력은 비운다
    edited = res["edited"]
    left = [i[0] for s in edited["sheets"] for i in s["imgs"]]
    assert len(left) == 32 and len(set(left)) == 32 and edited["sheets"][1]["imgs"] == []
    assert edited["hist"] == json.dumps({"undo": [], "redo": []}, separators=(",", ":"))
    assert "손댄 새 시트(도면 1 2)는 남기고 옮긴 그림만 뺐어요" in edited["toast"]


def test_wizard_split_hints_redo_note_restore_without_duplicates_and_notes():
    """실화면 V3 남은 문제: 새 시트 Ctrl+Z·되돌린 뒤 Ctrl+Y 무반응(알림 없음), 지운 새 시트를 되살리면 같은 그림이 두 시트에,
    나누기 알림·창 글에 돌리거나 잠근 그림·짝 자리 짐작 안내가 빠짐."""
    res = _glue()
    fresh = res["fresh"]                                                         # 새 시트: 이력이 비면 원래 시트 이름으로 안내
    assert fresh["toasts"] == ['나누기로 생긴 시트예요 — 나누기를 되돌리려면 "도면 1" 시트에서 Ctrl+Z'] and fresh["same"] is True
    redo = res["redo"]                                                           # 되돌린 뒤 Ctrl+Y: 다시 나누는 길
    assert redo["toasts"][-1] == "나누기는 다시 하기(Ctrl+Y)로 되살리지 않아요 — 다시 나누려면 위의 [자동 배치]를 눌러 주세요"
    assert redo["toasts"][0].endswith(" · 다시 나누려면 위의 [자동 배치]") and redo["same"] is True
    assert res["quiet"] == []                                                    # 그 뒤 손을 댔거나 나누기와 상관없으면 예전처럼 조용히
    restore = res["restore"]                                                     # 지운 새 시트를 되살려도 그림은 한 번씩만
    assert len(restore["ids"]) == 32 and len(set(restore["ids"])) == 32
    assert [len(s["imgs"]) for s in restore["sheets"]] == [32, 0] and restore["sheets"][1]["texts"] == 5
    moved = restore["toasts"][0].split("옮긴 그림 ")[1].split("장")[0]
    assert restore["toasts"][-1] == "시트를 되돌렸어요 — 다른 시트에 이미 있는 그림 " + moved + "장은 빼고 되살렸어요"
    assert restore["hist"] == json.dumps({"undo": [], "redo": []}, separators=(",", ":"))   # 되돌리기로 다시 생기지 않게
    plain = res["restorePlain"]                                                  # 겹치는 그림이 없으면 예전 그대로
    assert plain["toast"] == "시트를 되돌렸습니다." and plain["hist"] == 1 and plain["ids"] == ["solo", "own"]
    notes = res["notes"]
    assert "돌리거나 잠근 그림 1장은 그대로 둬요." in notes["lines"]
    assert notes["lines"][-1].startswith("나누면 시트마다 다시 배치해요.")
    assert notes["toast"].endswith('시트에서 Ctrl+Z · 돌리거나 잠근 그림 1장은 그대로 두었어요 — 테두리 밖 1장을 골라 두었어요'
                                   ' · 크기가 같아 도어 자리에 놓은 그림 1장 — 맞으면 골라서 숫자키 2')
    assert notes["sel"] == ["rot"] and len(notes["ids"]) == len(set(notes["ids"])) == 35


def test_wizard_batch_undo_late_text_skipped_note_and_later():
    res = _glue()
    # 같이 올린 여러 장은 한 번에 — 그 사이 다른 일을 하면 그 뒤 그림은 새 기록
    assert res["batch"]["n1"] == 1 and res["batch"]["n2"] == 3
    assert res["batch"]["after"] == ["a1,a2,t9", "a1,a2", ""]
    assert res["texts"] == ["종류에 맞춰 배치했습니다 (되돌리기 Ctrl+Z)",
                            "종류를 아직 몰라 크기대로 놓았어요 — 종류가 오면 다시 놓을게요",
                            "그림 1장은 종류를 아직 몰라 크기대로 놓았어요 — 종류가 오면 다시 놓을게요"]
    rot = res["rotated"]
    assert rot["toast"] == ("종류에 맞춰 배치했습니다 (되돌리기 Ctrl+Z) · 돌리거나 잠근 그림 1장은 그대로 두었어요"
                            " — 테두리 밖 1장을 골라 두었어요")
    assert rot["sel"] == ["rot"] and json.loads(rot["rot"])[:3] == ["rot", 10, 600]   # 돌린 그림은 제자리
    assert res["guess"]["toast"].endswith(" · 크기가 같아 도어 자리에 놓은 그림 1장 — 맞으면 골라서 숫자키 2")
    assert res["guess"]["label"] == "부품 상세/ai"                             # 이름표는 바꾸지 않는다(학습 자료는 사람이 굳힌 것만)
    later = res["later"]
    assert later["toast"] == "겹친 채 두었어요 — 위의 [자동 배치]로 언제든 다시 정리할 수 있어요"
    assert later["same"] is True and later["undo"] == 0
