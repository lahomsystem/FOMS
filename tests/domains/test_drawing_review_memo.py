"""도면 마법사 AI 도면팀원 검수 메모 — 규칙(review-memo.js) · 카드(review-card.js) · 저장 연결 · 서버 계약 시험.

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 A1 (2026-10-27 사용자 승인 "추천대로")
- 확실한 것만 메모한다: 머리칸 빈칸 · 미분류 · 같은 그림 두 번 · 테두리 밖 · 치수 글자 8px 아래 · 자재표 계산 칸과 다른 줄.
- 메모는 시트 그림을 고치지 않는다. [끄기] 한 key 는 그 시트에서 다시 메모하지 않고(review.off), 보인 key 는 review.seen 에 남는다.
- 기록은 그림 지문(sheetSig)에 들어가지 않는다 — 메모를 꺼도 전달 대기함 그림이 '예전 것'이 되지 않는다.
- V1 · V2 가 같은 [저장] 단추 · 같은 엔진(wizard.js)을 쓰므로 연결은 엔진에 있다.
"""

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.drawing import wizard as wizard_api
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
MEMO = ROOT / "static/js/drawing/review-memo.js"
CARD = ROOT / "static/js/drawing/review-card.js"
BOM = ROOT / "static/js/drawing/bom-calc.js"
SAVE_STATUS = ROOT / "static/js/drawing/save-status.js"
WIZ = ROOT / "static/js/drawing/wizard.js"
TPL = ROOT / "templates/drawing/wizard.html"
CSS = ROOT / "static/css/contexts/drawing/wizard.css"
_SEQ = [0]


def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _run(script, *args):
    proc = subprocess.run([_node(), "-e", script, *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("path", [MEMO, CARD])
def test_node_check_and_size(path):
    proc = subprocess.run([_node(), "--check", str(path)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert len(path.read_text(encoding="utf-8").splitlines()) < 300   # tests/harness 새 JS 300줄 래칫


# --------------------------------------------------------------------------- #
# 1. 규칙
# --------------------------------------------------------------------------- #
RULES_RUNNER = r"""
global.window = {};
require(process.argv[1]);
require(process.argv[2]);
const M = window.FomsReviewMemo, C = window.FomsBomCalc;
const img = (id, key, label, extra) => Object.assign({ id, type: 'image', key, x: 100, y: 120, w: 200, h: 100,
  natural_w: 400, natural_h: 200 }, label ? { part: { label, src: 'ai' } } : {}, extra || {});
const tx = { 'k-small': 12, 'k-ok': 30, 'k-photo': 4 };   // 원본 px — 시트에서는 w/natural_w(0.5)배
const border = { x0: 40, y0: 40, x1: 1440, y1: 1000 };
const ctx = { unsure: '미분류', border, minText: 8, bom: C,
  rectOf: (o) => o.rot ? null : { x: o.x, y: o.y, w: o.w, h: o.h }, textOf: (o) => tx[o.key] || 0 };
const base = () => ({ id: 's1', name: '붙박이장', form: { customer_name: '김고객', phone: '', address: ' ', sales_manager: '이영업' },
  objects: [
    img('a', 'k-ok', '정면·내부'),
    img('b', 'k-small', '정면·도어'),                     // 12 × 0.5 = 6px → 작음
    img('c', 'k-ok', '미분류'),                           // a 와 같은 그림 + 미분류
    img('d', 'k-photo', '사진', { x: 1300 }),             // 1300 + 200 > 1440 → 밖 · 사진은 글자를 안 본다
    img('e', 'k-x', '평면·상판', { x: 1400, rot: 30 }),   // 테두리를 모르는 그림은 안 본다
    img('f', 'k-edge', '부품 상세', { x: 39, y: 39 }),    // 테두리에 딱 붙임(2px 여유) → 밖 아님
    { id: 't1', type: 'text', x: 0, y: 0, w: 100, text: '[SR]\n60*2440=1' },
  ],
  calc: { in: {}, out: '[SR]\n60*2440=2\n[옷봉]\n925=3', mode: 'shadow' } });
const out = {};
out.memos = M.check(base(), ctx);
const offed = base(); offed.review = { off: ['head:phone', 'dup', 'bad key!'], seen: ['x'] };
out.offed = M.check(offed, ctx).map((m) => m.rule + ':' + m.keys.join(','));
out.note = M.note(offed, out.memos);
out.off = M.off(offed, out.memos[1]);
out.empty = [M.note({}, []), M.sanitize({ off: [], seen: ['나쁜 key'] }), M.sanitize('x'), M.sanitize(null)];
const many = []; for (let i = 0; i < 45; i++) many.push('k' + i);
out.capped = M.sanitize({ off: many.concat(['k3']), seen: ['a', 'a', 'b'] });
out.keyOf = [M.keyOf('기타 선반'), M.keyOf('a*b'), M.keyOf(''), M.keyOf('손잡이'), M.keyOf('x'.repeat(50)).length];
// 규칙 하나가 터져도 나머지 메모는 그대로
const boom = Object.assign({}, ctx, { textOf: () => { throw new Error('boom'); } });
out.boom = M.check(base(), boom).map((m) => m.rule);
// 계산 칸을 안 쓴 시트 · 계산 모듈이 없을 때 · 맞는 자재표
const nocalc = base(); delete nocalc.calc;
const same = base(); same.objects[6].text = '[SR]\n60*2440=2\n[옷봉]\n925=3';
out.bomless = [M.check(nocalc, ctx).some((m) => m.rule === 'bom'), M.check(base(), Object.assign({}, ctx, { bom: null })).some((m) => m.rule === 'bom'),
  M.check(same, ctx).some((m) => m.rule === 'bom')];
out.bare = M.check({ objects: [img('a', 'k1'), img('b', 'k1')], form: { customer_name: 'a', phone: 'b', address: 'c', sales_manager: 'd' } }, {}).map((m) => m.rule);
out.re = M.KEY_RE.source;
process.stdout.write(JSON.stringify(out));
"""


def _rules():
    return _run(RULES_RUNNER, BOM, MEMO)


def test_rules_find_each_certain_problem_in_order():
    memos = _rules()["memos"]
    by = {m["rule"]: m for m in memos}
    assert [m["rule"] for m in memos] == ["head", "unsorted", "dup", "outside", "text", "bom"]
    assert by["head"]["keys"] == ["head:phone", "head:address"] and by["head"]["field"] == "phone"
    assert by["head"]["text"] == "머리칸이 비었어요 — 연락처 · 주소"
    assert by["unsorted"]["ids"] == ["c"] and by["unsorted"]["text"] == "미분류 그림 1장 — 종류를 골라 주세요"
    assert by["dup"]["ids"] == ["c"]
    assert by["outside"]["ids"] == ["d"]   # e(돌린 그림 · 테두리 모름) · f(2px 여유 안) 는 아니다
    assert by["text"]["ids"] == ["b"] and "약 6px" in by["text"]["text"] and "8px 보다 작은 그림 1장" in by["text"]["text"]
    assert by["bom"]["keys"] == ["bom:SR"]   # 옷봉은 시트에 아직 안 친 칸(todo) — 다름이 아니다
    assert by["bom"]["text"].startswith("자재표가 계산 칸과 달라요 — SR ")


def test_off_keys_hide_memos_and_records_merge():
    r = _rules()
    assert r["offed"] == ["head:head:address", "unsorted:unsorted", "outside:outside", "text:text", "bom:bom:SR"]
    assert r["note"] == {"off": ["head:phone", "dup"],
                         "seen": ["x", "head:phone", "head:address", "unsorted", "dup", "outside", "text", "bom:SR"]}
    assert r["off"] == {"off": ["head:phone", "dup", "unsorted"], "seen": ["x", "unsorted"]}
    assert r["empty"] == [None, None, None, None]
    assert r["capped"]["off"][0] == "k5" and len(r["capped"]["off"]) == 40 and r["capped"]["off"][-1] == "k44"
    assert r["capped"]["seen"] == ["a", "b"]
    assert r["keyOf"] == ["기타_선반", "ab", "x", "손잡이", 30]


def test_rule_failure_and_missing_inputs_stay_quiet():
    r = _rules()
    assert r["boom"] == ["head", "unsorted", "dup", "outside", "bom"]
    assert r["bomless"] == [False, False, False]
    assert r["bare"] == ["dup"]


def test_key_pattern_matches_server_contract():
    js = _rules()["re"]
    assert js == wizard_api._REVIEW_KEY_RE.pattern.replace("\\Z", "$")
    assert wizard_api._MAX_REVIEW_KEYS == 40


# --------------------------------------------------------------------------- #
# 2. 카드
# --------------------------------------------------------------------------- #
CARD_RUNNER = r"""
function El(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.on = {}; this.hidden = false; this.textContent = ''; this.className = ''; }
El.prototype.appendChild = function (c) { this.children.push(c); c.parentNode = this; return c; };
El.prototype.removeChild = function (c) { this.children.splice(this.children.indexOf(c), 1); return c; };
Object.defineProperty(El.prototype, 'firstChild', { get() { return this.children[0] || null; } });
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.addEventListener = function (t, fn) { (this.on[t] = this.on[t] || []).push(fn); };
El.prototype.fire = function (t, e) { (this.on[t] || []).forEach((fn) => fn(Object.assign({ stopPropagation() {} }, e || {}))); };
global.document = { createElement: (t) => new El(t), body: new El('body') };
global.window = {};
require(process.argv[1]);
const K = window.FomsReviewCard;
const find = (root, cls) => { const out = []; (function walk(n) { if ((' ' + n.className + ' ').indexOf(' ' + cls + ' ') >= 0) out.push(n); n.children.forEach(walk); })(root); return out; };
const calls = [];
const on = { look: (sid, m) => calls.push('look ' + sid + ' ' + m.rule), off: (sid, m) => calls.push('off ' + sid + ' ' + m.rule) };
const m = (rule, ids, field) => ({ rule, keys: [rule], text: rule + ' 메모', ids: ids || [], field: field || null });
const out = {};
K.show([], on); out.emptyOpen = K.isOpen();
K.show([{ sheetId: 's1', sheetName: '붙박이장', memos: [m('unsorted', ['a']), m('head', [], 'phone'), m('dup', [])] }], on);
const card = find(document.body, 'dws-review-card')[0];
out.open = [K.isOpen(), find(card, 'dws-review-item').length, find(card, 'dws-review-sub')[0].textContent,
  find(card, 'dws-review-look').length, card.attrs.role, card.attrs['aria-label']];
find(card, 'dws-review-look')[1].fire('click');
find(card, 'dws-review-off')[0].fire('click');
out.afterOff = [find(card, 'dws-review-item').length, find(card, 'dws-review-sub')[0].textContent];
find(card, 'dws-review-off')[0].fire('click'); find(card, 'dws-review-off')[0].fire('click');
out.allOff = K.isOpen();
K.show([{ sheetId: 's1', sheetName: '시트 1', memos: [m('dup')] }, { sheetId: 's2', sheetName: '', memos: [m('bom'), m('text', ['x'])] },
  { sheetId: 's3', sheetName: '빈 시트', memos: [] }], on);
out.many = [find(card, 'dws-review-sheet').map((e) => e.textContent), find(card, 'dws-review-sub')[0].textContent,
  find(card, 'dws-review-look').length, find(document.body, 'dws-review-card').length];
card.fire('keydown', { key: 'Enter' }); out.enter = K.isOpen();
card.fire('keydown', { key: 'Escape' }); out.esc = K.isOpen();
K.show([{ sheetId: 's1', sheetName: 'a', memos: [m('dup')] }], on);
find(card, 'dws-review-close')[0].fire('click'); out.closed = K.isOpen();
out.calls = calls;
process.stdout.write(JSON.stringify(out));
"""


def test_card_shows_memos_and_off_look_close():
    r = _run(CARD_RUNNER, CARD)
    assert r["emptyOpen"] is False
    assert r["open"] == [True, 3, "검수 메모 3개 · 붙박이장", 2, "region", "AI 도면팀원 검수 메모"]   # dup(그림 없음)은 [보기] 없음
    assert r["afterOff"] == [2, "검수 메모 2개 · 붙박이장"]
    assert r["allOff"] is False
    assert r["many"] == [["시트 1", "도면"], "검수 메모 3개", 2, 1]   # 빈 시트 묶음은 안 보인다 · 카드는 하나만 만든다
    assert r["enter"] is True and r["esc"] is False and r["closed"] is False
    assert r["calls"] == ["look s1 head", "off s1 unsorted", "off s1 head", "off s1 dup"]


# --------------------------------------------------------------------------- #
# 3. 저장 연결 · 지문 · 템플릿
# --------------------------------------------------------------------------- #
def _fn(src, name):
    start = src.index(f"  function {name}(")
    end = src.index("\n  function ", start + 10)
    return src[start:end]


def test_wizard_runs_review_before_body_and_shows_after_save():
    src = WIZ.read_text(encoding="utf-8")
    save = _fn(src, "save")
    assert save.index("var memos = auto ? null : reviewSheets([sheet]);") < save.index("var body = { state: serializeState()")
    assert save.index("refreshPending();") < save.index("showReview(memos);")
    assert save.count("showReview(") == 1   # 자동 저장 · 실패 길에서는 카드를 안 띄운다
    save_all = _fn(src, "saveAll")
    assert save_all.index("var memos = reviewSheets(state.sheets);") < save_all.index("var body = { state: serializeState()")
    assert "showReview(memos);" in save_all
    ser = _fn(src, "serializeSheet")
    assert "window.FomsReviewMemo.sanitize(s.review)" in ser and "out.review = review;" in ser
    assert "sheet.review = s.review;" in _fn(src, "normalizeState")
    off = _fn(src, "reviewOff")
    assert "markDirty();" in off and "recordUndo" not in off   # 메모 끄기는 그림 고치기가 아니다
    look = _fn(src, "reviewLook")
    assert "switchSheet(i)" in look and "data-dws-form-key" in look and "FomsBomPanel.toggle()" in look
    assert "canSave" in _fn(src, "reviewSheets")


SIG_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const S = window.FomsSaveStatus;
const sheet = { id: 's1', name: '도면', form: { customer_name: 'a' }, objects: [{ id: 'o', type: 'rect', x: 1, y: 2, w: 3, h: 4 }] };
const marked = Object.assign({}, sheet, { review: { off: ['dup'], seen: ['dup', 'unsorted'] } });
process.stdout.write(JSON.stringify([S.sheetSig(sheet), S.sheetSig(marked)]));
"""


def test_review_record_is_not_part_of_sheet_signature():
    a, b = _run(SIG_RUNNER, SAVE_STATUS)
    assert a and a == b


def test_template_loads_review_scripts_before_wizard_and_css():
    tpl = TPL.read_text(encoding="utf-8")
    memo = tpl.index("js/drawing/review-memo.js') }}?v=20261027c")
    card = tpl.index("js/drawing/review-card.js') }}?v=20261027c")
    assert memo < card < tpl.index("js/drawing/wizard.js') }}?v=20261029a")
    assert "css/contexts/drawing/wizard.css') }}?v=20261027c" in tpl
    assert "js/drawing/save-status.js') }}?v=20261027c" in tpl
    css = CSS.read_text(encoding="utf-8")
    block = css[css.index(".dws-review-card {"):]
    assert "position: fixed;" in block[:400] and "z-index: 128;" in block[:400]   # 알림(130) 아래 · 계산 칸(120) 위
    assert ".dws-review-card[hidden] { display: none; }" in css


# --------------------------------------------------------------------------- #
# 4. 서버 계약 — 시트 review
# --------------------------------------------------------------------------- #
def _login(client):
    _SEQ[0] += 1
    user = User(username=f"review-{_SEQ[0]}", password=generate_password_hash("x"),
                role="ADMIN", team="DRAWING", name=f"review-{_SEQ[0]}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _order_id():
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="시험", phone="010-0000-0000",
        address="대구", product="붙박이장", status="DRAWING", is_erp_order=True,
        structured_data={"parties": {"customer": {"name": "시험"}}, "items": [{"product_name": "몰딩 여닫이장"}]},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _state(review):
    return {"v": 1, "sheets": [{"id": "s-1", "name": "도면 1", "form": {}, "objects": [], "review": review}]}


def test_put_keeps_sheet_review(client):
    _login(client)
    order_id = _order_id()
    review = {"off": ["head:phone"], "seen": ["head:phone", "bom:SR", "bom:옷봉", "unsorted"]}
    resp = client.put(f"/api/orders/{order_id}/drawing-wizard", json={"state": _state(review), "base_updated_at": None})
    assert resp.status_code == 200, resp.get_json()
    saved = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    assert saved["sheets"][0]["review"] == review


@pytest.mark.parametrize("review", [
    "dup",
    {"off": "dup"},
    {"off": ["dup", "dup"]},
    {"off": ["bad key"]},
    {"off": ["dup\n"]},
    {"off": [1]},
    {"seen": ["a" * 41]},
    {"seen": [f"k{i}" for i in range(41)]},
    {"extra": []},
])
def test_put_rejects_bad_sheet_review(client, review):
    _login(client)
    order_id = _order_id()
    resp = client.put(f"/api/orders/{order_id}/drawing-wizard", json={"state": _state(review), "base_updated_at": None})
    assert resp.status_code == 400, resp.get_json()


def test_validate_review_unit():
    assert wizard_api._validate_review({}) is None
    assert wizard_api._validate_review({"off": None, "seen": ["dup"]}) is None
    assert re.fullmatch(wizard_api._REVIEW_KEY_RE, "head:customer_name")
