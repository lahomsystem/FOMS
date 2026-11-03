"""도면 마법사 — 발주 리스트 칸(2026-11-03, 사용자 목업 확정 뒤 '이대로 구현 · V2도 적용').

- V1 양식: 도면팀 · 생산팀 체크리스트를 지우고 오른쪽 위에 빨간 굵은 ㄴ자 '**발주 리스트**' 칸(쪽번호 칸이 모서리를 파고든다),
  시트 위 '발주 리스트' 체크로 켜고 끈다(form.order_list_on = '1'). 껐을 때 쪽번호 칸은 원래 굵기. 자재표 자리표는 맨 위 가운데.
- V2 양식: 아래 띠 체크 칸을 지우고 같은 빨간 칸(쪽번호는 아래 띠라 홈 없이 네모). 켜면 칸 배치가 그 칸을 비켜 간다
  (v2-plan ORDER_BOX → 장애물 corner — 위 띠 · 오른쪽 위 자재 · 특이 · 강조는 그 앞에서 끝나고 그림 칸은 room 이 비켜 간다).
- 끈 시트는 배치가 그대로, V2 % 기준(v1Baseline)은 예전 V1 양식으로 잰다(체크리스트를 지워도 % · 틀 고르기가 안 흔들린다).
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.domains.test_drawing_wizard_v2_hero_pick import FIXTURES
from tests.domains.test_drawing_wizard_v2_layout import _run

ROOT = Path(__file__).resolve().parents[2]
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
V2_FORM = (ROOT / "templates/drawing/partials/wizard_v2_form.html").read_text(encoding="utf-8")
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
CSS_V2 = (ROOT / "static/css/contexts/drawing/wizard-v2.css").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    i = src.index(f"  function {name}(")
    j = src.index("\n  }\n", i)
    return src[i:j]


def test_v1_form_drops_checklist_and_adds_red_order_box_with_toggle():
    v1 = TPL[TPL.index('<div class="dws-form" id="dws-form">'):TPL.index("{% endif %}", TPL.index('<div class="dws-form" id="dws-form">'))]
    assert "data-dws-check" not in v1 and "도면팀" not in v1 and "생산팀" not in v1     # 체크리스트 삭제
    assert '<div class="dws-orderbox-title">**발주 리스트**</div>' in v1
    assert 'data-dws-form-key="order_list"' in v1 and 'class="dws-pagebox"' in v1       # 쪽번호 칸은 늘 있다
    assert 'id="dws-orderlist-on"' in TPL and 'class="dws-orderlist-toggle" id="dws-orderlist-toggle" hidden' in TPL
    assert ".dws-form.dws-order-on .dws-orderbox { display: flex; }" in CSS              # 켰을 때만
    box = CSS[CSS.index(".dws-orderbox {"):CSS.index("}", CSS.index(".dws-orderbox {"))]
    assert "border: 9px solid #dc2626" in box and "display: none" in box
    pb_on = CSS[CSS.index(".dws-form.dws-order-on .dws-pagebox {"):CSS.index("}", CSS.index(".dws-form.dws-order-on .dws-pagebox {"))]
    assert "border-left: 9px solid #dc2626" in pb_on and "border-bottom: 9px solid #dc2626" in pb_on   # ㄴ자 안쪽 선
    pb = CSS[CSS.index("\n.dws-pagebox {"):CSS.index("}", CSS.index("\n.dws-pagebox {"))]
    assert "border: 3px solid #000" in pb                                                # 껐을 때는 원래 굵기


def test_v2_form_drops_strip_checks_and_adds_the_same_box():
    assert "data-dws-check" not in V2_FORM and "dws-v2-checks" not in V2_FORM
    assert 'class="dws-orderbox dws-v2-orderbox" id="dws-orderbox"' in V2_FORM and 'data-dws-form-key="order_list"' in V2_FORM
    assert "grid-template-columns: 984px 297px minmax(0, 1fr);" in CSS_V2                 # 체크 칸 몫을 정보 칸에
    assert ".dws-v2-checks" not in CSS_V2


def test_toggle_saves_on_sheet_rearranges_v2_and_split_does_not_copy_it():
    r = _fn(JS, "renderOrderList")
    assert "form.order_list_on === '1'" in r and "classList.toggle('dws-order-on', on)" in r and "els.orderToggle.hidden = !canSave" in r
    t = _fn(JS, "toggleOrderList")
    assert t.index("recordUndo()") < t.index("cs.form.order_list_on =") < t.index("markDirty()") < t.index("emitCore('orderbox'")
    assert "UI !== 'v2'" in t and "orderBoxCovered(cs) > 0" in t and "[자동 배치]" in t       # V1 은 옮기지 않고 걸린 그림을 알린다
    shell = (ROOT / "static/js/drawing/v2-shell.js").read_text(encoding="utf-8")
    assert "['trimmed', 'orderbox'].forEach(function (ev) { core.on(ev, function () { if (laidNow()) { scheduleArrange(ev); } }); });" in shell
    assert JS.count("    form.order_list_on = '';") == 2 and JS.count("    form.order_list = '';") == 2   # V1 · V2 나누기
    assert "partFormBoxes(s)" in _fn(JS, "partArrangePlan") and "partFormBoxes(s)" in _fn(JS, "partFreshPlan")


def _bom_js(body: str) -> dict:
    """seedPresetObjects · moveBomRowTop 을 node 로 — 글자 폭은 글자 수 × 크기 × 0.62(measureRunWidth 가 없으면 쓰는 어림)."""
    import json
    import subprocess
    names = ["seedPresetObjects", "bomTextBox", "bomRowXs", "moveBomRowTop", "bomObjBox", "partFormBoxes"]
    consts = "\n".join(re.search(rf"  var {n} = [^;]+;", JS).group(0) for n in ("PRESET_TOP_Y", "PRESET_ROW_RIGHT", "PRESET_ROW_LEFT"))
    src = "\n".join(_fn(JS, n) + "\n  }" for n in names)
    js = f"""
var PRESETS = {{ SR: '[SR]', EP: '[EP]', DOOR: '[DOOR]', ROD: '[옷봉]', MAIDA: '[마이다]' }}, ALLOWED_SIZES = [14, 17, 20, 24, 28, 32, 36, 40];
var PART_FRAME = {{ pageBox: {{ x: 1374, y: 40, w: 66, h: 49 }}, orderBox: {{ x: 1074, y: 40, w: 366, h: 190 }} }}, UI = 'v1', SIZE = 20, n = 0;
function rid(p) {{ n += 1; return p + n; }}
function loadPreferredTextSize() {{ return SIZE; }}
function measureRunWidth() {{ throw new Error('no canvas'); }}
function isFiniteNum(v) {{ return typeof v === 'number' && isFinite(v); }}
function sizeOrDefault(s) {{ return ALLOWED_SIZES.indexOf(s) >= 0 ? s : 20; }}
function normalizeRotation(r) {{ r = Math.round(Number(r) || 0); return ((r % 360) + 360) % 360; }}
{consts}
{src}
var out = {{}};
{body}
process.stdout.write(JSON.stringify(out));
"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_preset_row_ends_before_the_order_box_with_even_gaps():
    """사용자 그림(11-03): 맨 위 한 줄, 칸 사이 고른 간격(글자 크기 × 3), 오른쪽 끝은 발주 리스트 칸 — 칸에 붙어 있어 24px 띄운다."""
    out = _bom_js("""
for (const size of [14, 20, 28, 40]) {
  SIZE = size;
  const objs = seedPresetObjects(), boxes = objs.map(bomTextBox);
  out[size] = { xs: objs.map(o => o.x), ys: objs.map(o => o.y), ends: objs.map((o, i) => o.x + boxes[i].w), ws: boxes.map(b => b.w) };
}
""")
    for size, r in out.items():
        assert set(r["ys"]) == {52}, (size, r)
        assert 1040 <= r["ends"][-1] <= 1051, (size, r)                                   # 칸(1074) 앞 24px
        gaps = [r["xs"][i + 1] - r["ends"][i] for i in range(4)]
        assert max(gaps) - min(gaps) <= 2 and all(g >= 24 for g in gaps), (size, gaps)    # 고른 간격
        assert r["xs"][0] >= 60, (size, r)
    assert out["28"]["xs"][0] < out["20"]["xs"][0]                                        # 글자가 크면 줄이 왼쪽으로 길어진다


def test_written_sheets_move_their_bom_row_up_once_unless_something_is_in_the_way():
    out = _bom_js("""
const text = (t, x, y) => ({ id: rid('t'), type: 'text', x, y, text: t, size: 20 });
const filled = () => [text('[SR]\\n60*2440=2', 628, 120), text('[EP]\\n18*600', 798, 120), text('[DOOR]', 968, 120),
  { id: 'img', type: 'image', x: 60, y: 300, w: 500, h: 400 }];
let s = { form: {}, objects: filled() };
out.moved = moveBomRowTop(s);
out.rows = s.objects.filter(o => o.type === 'text').map(o => [o.text.split('\\n')[0], o.x, o.y]);
out.flag = s.form.bom_row;
s.objects[0].x = 200; s.objects[0].y = 400;                       // 사람이 옮긴 뒤 다시 열어도 그대로
out.again = moveBomRowTop(s); out.kept = [s.objects[0].x, s.objects[0].y];
let b = { form: {}, objects: filled().concat([{ id: 'img2', type: 'image', x: 700, y: 45, w: 200, h: 120 }]) };   // 자리에 그림이 있다
out.blocked = moveBomRowTop(b); out.blockedFlag = b.form.bom_row || ''; out.blockedX = b.objects[0].x;
let v2 = { form: { v2_layout: 'band' }, objects: filled() };
out.v2 = moveBomRowTop(v2);
let lock = { form: {}, objects: filled() }; lock.objects[0].locked = true;
moveBomRowTop(lock); out.lockedX = lock.objects[0].x;
let rot = { form: {}, objects: filled().concat([{ id: 'r', type: 'image', x: 60, y: 750, w: 100, h: 100, rotation: 90 }]) };
out.rot = moveBomRowTop(rot);
""")
    assert out["moved"] is True and out["flag"] == "1"
    assert [r[0] for r in out["rows"]] == ["[SR]", "[EP]", "[DOOR]"] and {r[2] for r in out["rows"]} == {52}
    assert out["rows"][0][1] < out["rows"][1][1] < out["rows"][2][1] < 1074
    assert out["again"] is False and out["kept"] == [200, 400]                           # 한 번만
    assert out["blocked"] is False and out["blockedFlag"] == "" and out["blockedX"] == 628   # 걸리면 그대로(다음에 다시 본다)
    assert out["v2"] is False and out["lockedX"] == 628 and out["rot"] is False             # V2 · 잠근 글자 · 돌린 그림 있으면 손대지 않음
    assert "moveBomRowTop(sheet)" in JS and "form.bom_row = '1';   // 자재표 줄은 새 자리에" in JS
    status = (ROOT / "static/js/drawing/save-status.js").read_text(encoding="utf-8")
    assert "k === 'bom_row'" in status                                                   # 옮김 표시만으로 '전달본 예전 것'이 되지 않게


def test_v2_baseline_keeps_the_old_v1_frame():
    assert "fresh = partBasePlan(s)" in _fn(JS, "v1Baseline")
    b = _fn(JS, "partBasePlan")
    assert "y0: 95 + 8" in b and "o.y = PRESET_SEED_Y;" in b and "[partPad(PART_FRAME.pageBox)]" in b   # 발주 리스트 칸 · 새 자리표와 무관


def test_v2_layout_avoids_the_order_box_and_keeps_off_sheets_unchanged():
    """켜면 그림 · 칸 머리 · 자재 · 특이 · 강조 어느 것도 칸에 닿지 않고, 왼쪽 위 띠를 통째로 비우지 않는다(대조군: 장애물만 주면 빈칸 18%).
    끈 시트(corner 없음)가 예전과 같은 자리인지는 11-03 스테이징 덤프 16가지 × 두 스타일로 고치기 전 코드와 견줘 32/32 같음을 확인했다."""
    out = _run(FIXTURES + r"""
const BOX = { x: 1074, y: 40, w: 366, h: 190 }, OB = { x: 1064, y: 40, w: 376, h: 200, corner: true };
const res = {};
for (const [name, base] of [['4385', IN_4385], ['4465', IN_4465]]) {
  for (const hero of [true, false]) for (const prefer of ['band', 'column']) {
    const o = { hero, prefer }, off = L.compute(copy(base), o), on = L.compute(Object.assign(copy(base), { obstacles: [OB] }), o);
    const plain = L.compute(Object.assign(copy(base), { obstacles: [Object.assign({}, OB, { corner: false })] }), o);
    const r = on[on.best], p = plain[plain.best];
    res[name + (hero ? 'H' : 'E') + prefer] = {
      hitMoves: r.moves.filter(m => hit(m, BOX)).length, hitSlots: r.slots.filter(s => hit(s, BOX)).length, clashes: clashes(r), inside: inside(r),
      blank: F.blank(r, A, [OB]), plainBlank: F.blank(p, A, [OB]), offBest: !!off[off.best] };
  }
}
out.res = res;
""")
    for k, v in out["res"].items():
        assert v["hitMoves"] == 0 and v["hitSlots"] == 0, (k, v)                         # 칸에 아무것도 안 닿는다
        assert v["clashes"] == [] and v["inside"], (k, v)
        assert v["blank"] < 0.14, (k, v)                                                 # 왼쪽 위 띠를 쓴다
        assert v["offBest"], k
    assert max(v["plainBlank"] for v in out["res"].values()) >= 0.15                    # 대조군: 그냥 장애물이면 띠가 칸 아래로 밀려 비었다


def test_v2_waits_for_pictures_uses_the_column_under_the_box_and_pins_are_bumped():
    """11-03 '노란 칸(발주 리스트 칸 밑) 온전히': 칸을 켤 때 그림이 뜨기 전에 배치하면 치수 글자 높이를 0 으로 알고 놓아 칸 밑이 비고
    글자가 7px 이 됐다 → 다시 배치는 그림이 뜰 때까지(9초까지) 기다린다. 큰 그림 칸은 배율이 3% 안이면 칸 밑까지 넓은 쪽,
    왼쪽 기둥형 빈자리 채우기도 칸 밑까지 찾는다. PR #712 는 v2-pack · v2-layout 을 고치고 핀을 안 올려 캐시가 섞이면 멈출 수 있었다."""
    shell = (ROOT / "static/js/drawing/v2-shell.js").read_text(encoding="utf-8")
    assert "(tries < 20 && unloaded())" in shell and "!core.image(x.id)" in shell
    pack = (ROOT / "static/js/drawing/v2-pack.js").read_text(encoding="utf-8")
    assert "wide = obs.some(function (b) { return b.corner; }) ? 0.97 : 1" in pack
    lay = (ROOT / "static/js/drawing/v2-layout.js").read_text(encoding="utf-8")
    assert "fillIn(res, inp, mv, cw ? { x: rx, y: by, w: RW, h: A.y1 - by } : room, same, big)" in lay
    for asset in ("v2-pack.js", "v2-layout.js", "v2-plan.js"):
        v = re.search(rf"js/drawing/{asset}'\) }}}}\?v=(\d{{8}})", TPL).group(1)
        assert v >= "20261103", asset                                                   # 발주 리스트 칸 뒤 핀
