"""도면 마법사 — 전달본 지문 · 시트 사이 그림 id 겹침(설계서 docs/plans/2026-10-26-drawing-wizard-sheet-integrity-spec.md).

B. [저장](sheet-png POST)이 그림 지문 ``sig``('v2:' + sheetSig)를 함께 보내면 전달 대기함 항목에 남고 목록이 돌려준다.
   다시 연 창은 목록의 지문을 기준으로 '전달본 예전 것'을 가린다 — 예전에는 불러온 그대로를 기준으로 삼아
   '넣고 → 더 고치고 → 자동 저장 → 창 닫음 → 다시 엶'이면 첫 편집 전까지 초록 '전달 대기함'이었다.
   형식이 틀린 지문은 거절하지 않고 버린다(옛 브라우저·옛 항목은 지금 동작 그대로).
A-2. 불러올 때와 저장할 때 앞 시트에 이미 있는 객체 id 를 뒤에서 만나면 새 id 로 뗀다(그림은 지우지 않는다).
"""
from __future__ import annotations

import io
import json
import subprocess

import pytest

import foms.api.drawing.wizard as wizard_api
from tests.domains.test_drawing_wizard_save_reopen import JS, RELOAD_RUNNER, ROOT, SS_PATH, _calls, _fn, _node
from tests.domains.test_drawing_wizard_sheet_png_key_safety import _Storage, _as, _sd, _setup

IDS_PATH = ROOT / "static/js/drawing/sheet-ids.js"
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(wizard_api, "get_storage", lambda: fake)
    return fake


def _post(client, oid, **extra):
    data = {"file": (io.BytesIO(b"\x89PNG\r\n\x1a\nfake"), "a.png"), "sheet_id": "s-1", "sheet_name": "시트1"}
    data.update(extra)
    return client.post(f"/api/orders/{oid}/drawing-wizard/sheet-png", data=data, content_type="multipart/form-data")


def _listed(client, oid):
    r = client.get(f"/api/orders/{oid}/drawing-wizard/pending")
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["pending"]


# ── B. 서버: 지문 칸 ─────────────────────────────────────────────────────────


def test_sheet_png_keeps_sig_and_pending_list_returns_it(client, storage):
    drafter, oid = _setup("sig1")
    _as(client, drafter)
    assert _post(client, oid, sig="v1:3k.1a2b3c4d5e").status_code == 200
    assert _sd(oid)["drawing_wizard"]["pending"]["s-1"]["sig"] == "v1:3k.1a2b3c4d5e"
    assert _listed(client, oid)[0]["sig"] == "v1:3k.1a2b3c4d5e"


@pytest.mark.parametrize("bad", ["", "1:abc", "v1:", "v100:abc", "v1:ABC", "v1:a b", "v1:" + "a" * 33, "<script>"])
def test_sheet_png_drops_bad_sig_but_still_saves(client, storage, bad):
    drafter, oid = _setup("sig2")
    _as(client, drafter)
    r = _post(client, oid, sig=bad)
    assert r.status_code == 200, r.get_json()                       # 지문이 틀려도 저장은 된다
    entry = _sd(oid)["drawing_wizard"]["pending"]["s-1"]
    assert entry["key"] and "sig" not in entry
    assert "sig" not in _listed(client, oid)[0]


def test_sheet_png_without_sig_and_old_entry_keep_old_shape(client, storage):
    drafter, oid = _setup("sig3")
    _as(client, drafter)
    assert _post(client, oid).status_code == 200                    # 옛 브라우저(안 보냄)
    assert set(_listed(client, oid)[0]) == {"sheet_id", "key", "filename", "at", "sheet_name"}
    sd = {"drawing_wizard": {"pending": {"a": {"key": "k", "sig": "v1:<bad>"}, "b": {"key": "k2", "sig": "v2:zz"}}}}
    listed = wizard_api._pending_list(sd)
    assert "sig" not in listed[0] and listed[1]["sig"] == "v2:zz"   # 옛 항목의 틀린 값은 빼고, 다른 판은 그대로 싣는다


def test_resave_without_sig_drops_previous_sig(client, storage):
    """지문 없이 다시 넣으면 예전 지문이 남아 새 전달본을 '예전 것'으로 가리면 안 된다."""
    drafter, oid = _setup("sig4")
    _as(client, drafter)
    assert _post(client, oid, sig="v1:3k.abc").status_code == 200
    assert _post(client, oid).status_code == 200
    assert "sig" not in _sd(oid)["drawing_wizard"]["pending"]["s-1"]


# ── B. 브라우저: 판 표시와 목록 지문 ──────────────────────────────────────────


def test_tag_sig_and_apply_server_sigs():
    out = _calls([
        ["tagSig", ["3k.abc"]], ["tagSig", [""]],
        ["applyServerSigs", [{"s1": "mine", "s9": "keep"}, [
            {"sheet_id": "s1", "sig": "v2:srv1"},          # 목록 지문이 기준(다른 창이 넣었어도 정확히)
            {"sheet_id": "s2", "sig": "v1:old"},           # 판이 다르면 건드리지 않는다(v1 = 칸 순서가 들어간 옛 지문)
            {"sheet_id": "s3", "sig": "v2:"},              # 빈 지문
            {"sheet_id": "s4"}, None, {"sig": "v2:x"}]]],
    ])
    assert out[0] == "v2:3k.abc" and out[1] == ""
    assert out[2] == {"s1": "srv1", "s9": "keep"}


def test_reopened_window_uses_server_sig_before_first_edit():
    names = ["currentSheet", "hhmm", "updateDeleteSavedBtn", "queuedStateOf", "noteQueued", "rememberLoadedSheets",
             "syncSheetSaveUi", "renderSaveStatus", "refreshPending", "renderPending", "deletePending"]
    head = RELOAD_RUNNER[:RELOAD_RUNNER.index("(async () => {")]
    runner = head + r"""
(async () => {
  const out = {};
  const S = window.FomsSaveStatus;
  rememberLoadedSheets(); hydrated = true;
  // 넣은 뒤 고치고 자동 저장한 다음 다시 열었다: 목록 지문(넣을 때) ≠ 지금 그림
  replies.push(ok([{ key: 'k1', sheet_id: 's1', sheet_name: '도면 1', at: TODAY + ' 14:33', sig: 'v2:old.123' },
                   { key: 'k8', sheet_id: 's8', sheet_name: '도면 8', at: TODAY + ' 14:34', sig: S.tagSig(S.sheetSig(state.sheets[1])) }]));
  refreshPending(); await tick(); out.edited = snap();
  current = 1; syncSheetSaveUi(); out.same = snap();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
"""
    proc = subprocess.run([_node(), "-e", runner, str(SS_PATH)], input=json.dumps([_fn(n) for n in names]),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["edited"] == {"x": True, "chip": "전달본 예전 것", "kind": "dws-save-status-stale"}   # 예전엔 '전달 대기함'
    assert out["same"] == {"x": True, "chip": "전달 대기함 HH:MM", "kind": "dws-save-status-queued"}


def test_wizard_sends_sig_on_both_save_paths():
    post = _fn("postSheetPngBlob")
    assert "function postSheetPngBlob(blob, sheet, sig)" in post and "fd.append('sig', window.FomsSaveStatus.tagSig(sig))" in post
    assert "return postSheetPngBlob(blob, sheet, sig);" in _fn("pushSheetPng")
    assert "pushSheetPng(sheet, sig)" in _fn("saveSheetPng")
    assert "postSheetPngBlob(blob, s, sig)" in _fn("saveAll")
    pend = _fn("renderPending")
    assert pend.index("applyServerSigs(queuedSigBySheet, list)") < pend.index("seedQueuedSigs(")   # 목록 지문이 먼저, 모르는 것만 불러온 그대로


SIG_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const S = window.FomsSaveStatus;
const a = { id: 's1', name: '도면', form: { b: '1', a: '2' }, objects: [{ id: 'o', type: 'rect', x: 1, y: 2 }] };
const b = { objects: [{ y: 2, x: 1, type: 'rect', id: 'o' }], form: { a: '2', b: '1' }, name: '도면', id: 's1' };
const out = { order: S.sheetSig(a) === S.sheetSig(b) };
S.setCanon((s) => ({ id: s.id, objects: s.objects }));      // 저장 모양만 본다(화면 안 칸 차이는 지문에 안 든다)
out.canon = S.sheetSig(Object.assign({}, a, { form: { z: 'x' } })) === S.sheetSig(a);
out.moved = S.sheetSig(a) !== S.sheetSig(Object.assign({}, a, { objects: [{ id: 'o', type: 'rect', x: 9, y: 2 }] }));
S.setCanon(null);
out.reset = S.sheetSig(Object.assign({}, a, { form: { z: 'x' } })) !== S.sheetSig(a);
process.stdout.write(JSON.stringify(out));
"""


def test_sheet_sig_ignores_key_order_and_uses_saved_shape():
    """서버(JSONB)는 칸 순서를 바꿔 돌려준다 — v1 지문은 [저장] 뒤 고치지 않고 다시 열어도 '전달본 예전 것'이었다(스테이징 10-26)."""
    proc = subprocess.run([_node(), "-e", SIG_RUNNER, str(SS_PATH)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"order": True, "canon": True, "moved": True, "reset": True}
    load = _fn("load")
    assert load.index("window.FomsSaveStatus.setCanon(serializeSheet);") < load.index("jsonFetch(")


# ── A-2. 시트 사이 그림 id 겹침 떼기 ─────────────────────────────────────────


IDS_RUNNER = r"""
global.window = {};
require(process.argv[1]);
let n = 0;
const make = () => (++n === 1 ? 'a' : 'new' + n);   // 첫 새 id 는 이미 있는 값 — 다시 만든다
const sheets = [
  { id: 's1', objects: [{ id: 'a', type: 'image', key: 'k1' }, { id: 'b', type: 'text' }] },
  { id: 's2', objects: [{ id: 'a', type: 'image', key: 'k1' }, { id: 'c', type: 'rect' }, { id: 'c', type: 'rect' }, {}] },
  { id: 's3' }, null];
const count = window.FomsSheetIds.splitDupIds(sheets, make);
const again = window.FomsSheetIds.splitDupIds(sheets, make);
process.stdout.write(JSON.stringify({ count, again, ids: sheets.slice(0, 2).map((s) => s.objects.map((o) => o.id || null)),
  len: sheets[1].objects.length, key: sheets[1].objects[0].key }));
"""


def test_split_dup_ids_renames_later_copies_and_keeps_pictures():
    proc = subprocess.run([_node(), "-e", IDS_RUNNER, str(IDS_PATH)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["count"] == 2 and out["again"] == 0
    assert out["ids"] == [["a", "b"], ["new2", "c", "new3", None]]   # 앞 시트는 그대로, 뒤쪽 것만 새 id(겹치는 새 id 는 다시)
    assert out["len"] == 4 and out["key"] == "k1"                     # 그림은 지우지 않는다


def test_wizard_splits_dup_ids_on_load_and_before_save():
    load = _fn("load")
    i = load.index("splitIds = window.FomsSheetIds ? window.FomsSheetIds.splitDupIds(state.sheets, newObjId) : 0;")
    assert load.index("state = normalizeState(d.state);") < i < load.index("rememberLoadedSheets();")   # 지문은 뗀 뒤에 잰다
    j = load.index("if (splitIds) {")
    assert load.index("dirty = false;") < j < load.index("hydrated = true;")                         # 저장만 켜고 자동 저장은 안 한다
    assert "뒤쪽 시트의 그림 ' + splitIds + '장을 따로 떼었어요" in load
    save = _fn("save")
    assert save.index("splitDupIds(state.sheets, newObjId)") < save.index("serializeState()")
    assert "rebuildAnno();" in save and "deselect()" not in save        # 자동 저장도 도구·선택을 건드리지 않는다
    assert "function newObjId() { return rid('o-'); }" in JS
    assert TPL.index("js/drawing/sheet-ids.js') }}?v=20261026a") < TPL.index("js/drawing/wizard.js') }}?v=20261026f")
    assert "js/drawing/save-status.js') }}?v=20261026b" in TPL


def test_node_check_sheet_ids():
    proc = subprocess.run([_node(), "--check", str(IDS_PATH)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr


# ── A-3. 서버: 겹친 id 는 1판에서 기록만 ──────────────────────────────────────


def _rect(oid, x=10):
    return {"id": oid, "type": "rect", "x": x, "y": 10, "w": 100, "h": 50, "stroke": "#000000", "strokeWidth": 2}


@pytest.mark.parametrize("sheets, dup", [
    ([[_rect("a"), _rect("b")], [_rect("a", 30)]], 1),                 # 시트 사이
    ([[_rect("a"), _rect("a", 30)], [_rect("c")]], 1),                 # 한 시트 안
    ([[_rect("a"), _rect("b")], [_rect("c")]], 0),                     # 음성 대조군
])
def test_put_logs_dup_object_ids_but_still_saves(client, caplog, sheets, dup):
    drafter, oid = _setup(f"dup{dup}{len(sheets[0])}{sheets[0][1]['id']}")
    _as(client, drafter)
    state = {"v": 1, "sheets": [{"id": f"s-{i}", "name": f"도면 {i}", "form": {}, "objects": objs}
                                for i, objs in enumerate(sheets)]}
    with caplog.at_level("WARNING", logger=wizard_api.logger.name):
        r = client.put(f"/api/orders/{oid}/drawing-wizard", json={"state": state, "base_updated_at": None})
    assert r.status_code == 200, r.get_json()                       # 1판은 거절하지 않는다
    lines = [rec.getMessage() for rec in caplog.records if "DRAWING_WIZARD_DUP_OBJECT_ID" in rec.getMessage()]
    assert lines == ([f"DRAWING_WIZARD_DUP_OBJECT_ID order={oid} dup={dup}"] if dup else [])
    saved = _sd(oid)["drawing_wizard"]["sheets"]
    assert [o["id"] for s in saved for o in s["objects"]] == [o["id"] for objs in sheets for o in objs]
