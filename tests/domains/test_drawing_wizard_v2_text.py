"""도면 마법사 V2 — 칸 머리 위 글자(v2-text.js · v2-notes.js 강조 문구 내 단추 · 알림 띠 탭 줄, node 로 돌린다).

사용자 보고(2026-10-28, 스테이징 주문 4385):
4) '자재 입력 시 자동 간격 조절 안 됨' — [SR] 칸에 1000*2450 을 쓰자 글 폭 35 → 97px 인데 옆 [EP] 가 그 자리에 남아 겹쳤다
   (글을 고쳐도 다시 배치가 돌지 않았다).
5) '특이 사항 추가 시 간격이 자동으로 돌아가 버려' — 질문 창 답 '손으로 벌린 간격이 되돌아감': 글자는 고정이 없어 다시 배치가 옮겼다.
   → 손으로 옮긴 자재표(줄 전체) · 특이 · 강조는 폼 v2_pin 으로 고정, [고정 풀고 모두 다시]가 함께 푼다.
6) '강조 문구는 내가 추가 할 수 있게' — 질문 창 답 '내 문구를 단추로 남기기': 직접 쓴 문구가 단추로 남는다(이 컴퓨터, × 로 지움).
1) 알림 띠 '가장 작은 그림이 45%예요 · 시트 2장으로 나누기'를 탭 줄로 — 마우스를 올리면 다 보인다(title).
"""
from __future__ import annotations

from pathlib import Path

from tests.domains.test_drawing_wizard_v2_layout import _run as _run_pure
from tests.domains.test_drawing_wizard_v2_right_ux import UI
from tests.domains.test_drawing_wizard_v2_right_ux import _run as _run_ui

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "static/js/drawing"
ENGINE = (JS_DIR / "wizard.js").read_text(encoding="utf-8")
SHELL = (JS_DIR / "v2-shell.js").read_text(encoding="utf-8")

HEAD = UI.replace("'v2-size.js', 'v2-right.js', 'v2-chrome.js', 'v2-shell.js'",
                  "'v2-size.js', 'v2-notes.js', 'v2-text.js', 'v2-right.js', 'v2-chrome.js', 'v2-shell.js'")
HEAD = HEAD.replace("'dws-v2-relayout', 'dws-v2-rearrange', 'dws-v2-unpin',", "'dws-v2-relayout', 'dws-v2-rearrange', 'dws-v2-unpin', 'dws-v2-banner',")
HEAD = HEAD.replace("window.FomsWizardCore = core;", """let rid = 0;
core.rid = p => p + 'x' + (++rid);
core.normalize = o => o;
core.customer = () => '고객';
core.split = () => [];
core.zoom = () => 1;
window.FomsWizardCore = core;""")
assert "v2-text.js" in HEAD and "'dws-v2-banner'" in HEAD and "core.rid" in HEAD

BOM = r"""
const txt = (id, text, x, y, w, size) => ({ id, type: 'text', x, y, w, text, size: size || 20, color: '#000000', bold: false, align: 'left' });
function laidBom() {
  state.sheets = [{ id: 's1', name: '붙박이장', form: {}, objects: [img('c1', '입체·내부', 1700, 1200, 0), img('f1', '정면·내부', 1500, 1100, 1),
    img('d1', '서랍 단면', 500, 400, 2), img('t1', '평면·상판', 1300, 1000, 4),
    txt('b1', '[SR]\n', 1100, 120, 35), txt('b2', '[EP]\n', 1270, 120, 34), txt('b3', '[DOOR]\n', 1440, 120, 70)] }];
  emit('batch', { ids: state.sheets[0].objects.filter(o => o.type === 'image').map(o => o.id), sheetId: 's1' });
  tick(100);
  emit('render'); tick(10);   // 그린 뒤 — 지문을 잡는다
  return core.sheet();
}
const obj = id => core.sheet().objects.find(o => o.id === id);
const xs = () => ['b1', 'b2', 'b3'].map(id => obj(id).x);
const gapOk = () => { const b = ['b1', 'b2', 'b3'].map(obj).sort((p, q) => p.x - q.x); return b.every((o, i) => !i || o.x >= b[i - 1].x + b[i - 1].w + 18); };
"""


def test_pure_signature_respace_and_pin():
    out = _run_pure(r"""
require(process.argv[1] + '/v2-fill.js'); require(process.argv[1] + '/v2-text.js');
const T = window.FomsV2Text;
const sh = { id: 's', form: {}, objects: [txt('b1', '[SR]\n1000*2450', 433, 77, 97), txt('b2', '[EP]\n', 486, 77, 34),
  txt('b3', '[DOOR]\n', 538, 77, 70), txt('n-1', '테스트', 791, 80, 51, 17), txt('st-1', '원도어', 1345, 63, 72, 24), txt('memo', '메모', 10, 10, 40)] };
out.sig = T.sig(sh);
const bom = sh.objects.filter(o => S.role(o) === 'bom');
out.moved = T.respace(bom); out.xs = bom.map(o => o.x);
const wide = [txt('a', '[A]', 100, 0, 30), txt('b', '[B]', 300, 0, 30)];
T.respace(wide); out.wide = wide[1].x;                                          // 사람이 넓게 벌린 틈은 그대로
const lk = [txt('a', '[A]', 100, 0, 80), Object.assign(txt('b', '[B]', 120, 0, 30), { locked: true }), txt('c', '[C]', 130, 0, 30)];
T.respace(lk); out.locked = lk.map(o => o.x);                                   // 잠긴 열은 그대로 · 그 뒤는 민다
out.pinBom = T.pin(sh, ['b2']); out.pinNote = T.pin(sh, ['n-1']); out.pinMemo = T.pin(sh, ['memo']); out.again = T.pin(sh, ['b1']);
out.form = sh.form.v2_pin;
const g = S.group(sh.objects, { pins: S.parsePins(sh.form.v2_pin) }), g0 = S.group(sh.objects, { pins: S.parsePins(sh.form.v2_pin), lockMoved: false });
out.stay = Object.keys(g.stay).sort(); out.pins = Object.keys(g.pins).sort(); out.off = Object.keys(g0.stay).length;
out.parse = Object.keys(S.parsePins('o-a  n-b <x> ' + 'z'.repeat(60))).sort();
""")
    assert out["sig"] == "b1:97x50 b2:34x50 b3:70x50 n-1:51x21 st-1:72x30"           # 메모 글자는 빼고 · 자리는 빼고
    assert out["moved"] == 2 and out["xs"] == [433, 548, 600]                        # 433+97+18 · 548+34+18
    assert out["wide"] == 300 and out["locked"] == [100, 120, 198]
    assert (out["pinBom"], out["pinNote"], out["pinMemo"], out["again"]) == (3, 1, 0, 0)   # 자재표는 한 열만 옮겨도 줄 전체
    assert sorted(out["form"].split(" ")) == ["b1", "b2", "b3", "n-1"]
    assert out["stay"] == ["b1", "b2", "b3", "n-1"] and out["pins"] == out["stay"] and out["off"] == 0   # '손으로 옮긴 그림은 고정'을 끄면 글자도
    assert out["parse"] == ["n-b", "o-a"]


def test_editing_a_material_rearranges_once_and_waits_while_typing():
    out = _run_ui(HEAD, BOM + r"""
const sh = laidBom();
out.before = { xs: xs(), gap: gapOk() };
core.editing = () => true;                                   // 글을 쓰는 중
obj('b1').text = '[SR]\n1000*2450'; obj('b1').w = 97;      // 엔진: 글 고치기 → 다시 그리며 자연 폭(97)
emit('render'); tick(600);
out.typing = xs();
core.editing = () => false;
tick(600);
out.after = { xs: xs(), gap: gapOk() };
const n = toasts.length;
emit('render'); tick(600);                                   // 크기가 그대로면 다시 놓지 않는다
out.quiet = toasts.length === n;
state.sheets = [JSON.parse(JSON.stringify(sh))]; state.sheets[0].id = 's2'; obj('b2').w = 200;
emit('render'); tick(600);                                   // 다른 시트를 열었다 — 지문만 새로 잡는다
out.switched = obj('b2').x === sh.objects.find(o => o.id === 'b2').x;
""")
    assert out["before"]["gap"], out
    assert out["typing"] == out["before"]["xs"], out           # 쓰는 동안은 기다린다
    assert out["after"]["gap"] and out["after"]["xs"] != out["before"]["xs"], out   # [EP] · [DOOR] 가 비켜 간격이 맞는다
    assert out["quiet"] and out["switched"], out


def test_moved_header_text_is_pinned_kept_on_rearrange_and_unpinned_by_unpin_all():
    out = _run_ui(HEAD, BOM + r"""
const sh = laidBom();
obj('b2').x += 40; obj('b3').x += 80;                        // 손으로 간격을 벌렸다(끌기 끝 → 엔진 moved)
const want = xs();
emit('moved', { ids: ['b2'] }); tick(100);
out.pin = (sh.form.v2_pin || '').split(' ').sort();
out.toast = toasts[toasts.length - 1] || '';
V2.arrange('button', { undo: true }); tick(100);             // 다시 자동 배치(특이 사항 더하기와 같은 길)
out.kept = JSON.stringify(xs()) === JSON.stringify(want);
out.unpinText = dom['dws-v2-unpin'].textContent; out.unpinHidden = dom['dws-v2-unpin'].hidden;
const imgs = sh.objects.filter(o => o.type === 'image'), boxes = ['b1', 'b2', 'b3'].map(id => window.FomsV2Slots.textBox(obj(id)));
out.clear = imgs.every(o => boxes.every(b => !(o.x < b.x + b.w && b.x < o.x + o.w && o.y < b.y + b.h && b.y < o.y + o.h)));
V2.unpinAll(); tick(100);
out.after = { pin: sh.form.v2_pin || null, back: JSON.stringify(xs()) !== JSON.stringify(want) };
""")
    assert out["pin"] == ["b1", "b2", "b3"], out
    assert "옮긴 글자를 고정했어요" in out["toast"] and "[고정 풀고 모두 다시]" in out["toast"], out
    assert out["kept"] and out["clear"], out                  # 다시 배치해도 그 자리 · 그림은 비켜 놓인다
    assert out["unpinText"] == "고정 풀고 모두 다시 (고정 글자 3)" and out["unpinHidden"] is False, out
    assert out["after"] == {"pin": None, "back": True}, out    # 함께 풀고 칸에 다시 놓는다


def test_stamp_custom_phrases_become_buttons_on_this_computer():
    out = _run_ui(HEAD, BOM + r"""
const sh = laidBom(), N = window.FomsV2Notes, KEY = 'foms.dws.v2.stamps';
const find = (n, re) => { if (re.test(n.className || '')) { return n; } for (const c of n.children || []) { const r = find(c, re); if (r) { return r; } } return null; };
const all = (n, re, acc) => { acc = acc || []; if (re.test(n.className || '')) { acc.push(n); } (n.children || []).forEach(c => all(c, re, acc)); return acc; };
const card = () => N.card({ plan: V2.plan() }, V2);
let c = card(), input = find(c, /dws-v2-stamp-input/);
out.empty = [input.value || '', input.placeholder];
input.value = '  상판   별도 '; (find(c, /dws-v2-stamp-add/).children[1]).click(); tick(100);
out.stamp = (sh.objects.find(o => /^st-/.test(o.id)) || {}).text;
out.store = JSON.parse(store[KEY] || '[]');
c = card();
out.buttons = all(c, /dws-v2-stamp-quick/).map(b => b.textContent);
out.label = find(c, /dws-v2-stamp-label/).textContent;
N.remember('원도어'); N.remember('상판 별도'); for (let i = 0; i < 10; i++) { N.remember('문구' + i); }
out.capped = N.mine().length; out.noQuick = N.mine().indexOf('원도어') < 0;
const chip = all(card(), /dws-v2-stamp-mine/).find(n => n.children[0].textContent === '문구9');
chip.children[1].click();
out.forgot = N.mine().indexOf('문구9') < 0;
""")
    assert out["empty"] == ["", "내 문구 쓰기 (예: 상판 별도)"], out         # 쓰는 칸은 늘 비어 있다(지금 문구는 머리 글에)
    assert out["stamp"] == "상판 별도" and out["store"] == ["상판 별도"], out
    assert out["buttons"][:3] == ["비규격", "원도어", "현장 확인"] and "상판 별도" in out["buttons"] and "빼기" in out["buttons"], out
    assert out["label"] == "강조 문구 (오른쪽 위 빨간 상자): 상판 별도", out
    assert out["capped"] == 8 and out["noQuick"] and out["forgot"], out


def test_stamp_buttons_survive_blocked_storage():
    out = _run_ui(HEAD, BOM + r"""
laidBom();
const N = window.FomsV2Notes;
N.remember('상판 별도');
out.mine = N.mine();
out.card = !!N.card({ plan: V2.plan() }, V2);
""", pre={"blocked": True})
    assert out == {"mine": [], "card": True}, out


def test_banner_lives_in_tab_row_with_full_text_on_hover_and_pin_message():
    out = _run_ui(HEAD, BOM + r"""
laidBom();
V2.refresh(); tick(100);
const b = dom['dws-v2-banner'];
out.title = b.title; out.width = b.style.width || '';
const C = window.FomsV2Chrome, plan = { g: { fixed: {} }, stay: 0, out: { best: 'band' } };
out.pin = [C.arrangeText('pin', { n: 2, any: true }, plan), C.arrangeText('pin', { n: 0, any: false }, plan), C.arrangeText('text', null, plan)];
""")
    assert out["title"].startswith("가장 작은 그림이 ") and " — 시트 2장으로 나누면" in out["title"], out   # 좁으면 설명이 줄어든다 — 올리면 다 보인다
    assert out["width"] == "", out                                               # 종이 폭에 맞추던 너비는 없다(탭 줄 안)
    assert out["pin"][0] == "옮긴 글자를 고정했어요 — 다시 배치해도 그 자리예요 · 그림 2장은 비켜 놓았어요 · 풀기 [고정 풀고 모두 다시]"
    assert out["pin"][1].startswith("옮긴 글자를 고정했어요") and "비켜" not in out["pin"][1]
    assert out["pin"][2].startswith("칸에 놓을 자리가 없어요")                   # 글 고친 뒤 못 놓으면 말한다


def test_engine_reports_text_moves_and_measures_rich_text_width():
    emit = ENGINE[ENGINE.index("  function emitMoved(nodes) {"):ENGINE.index("emitCore('moved', { ids: ids });")]
    assert "(o.type === 'image' || o.type === 'text')" in emit
    rich = ENGINE[ENGINE.index("  function buildRichText(o) {"):ENGINE.index("  function buildRichText(o) {") + 2400]
    assert "if (o.w !== Math.round(groupWidth)) { o.w = Math.round(groupWidth); }" in rich   # 색 섞인 글도 폭을 바로 맞춘다
    unpin = SHELL[SHELL.index("  function unpinAll() {"):SHELL.index("  function laidNow()")]
    assert "delete sh.form.v2_pin;" in unpin
    assert "['FomsV2Chrome', 'FomsV2Left', 'FomsV2Right', 'FomsV2Text'].forEach" in SHELL
