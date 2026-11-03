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
    shell = (ROOT / "static/js/drawing/v2-shell.js").read_text(encoding="utf-8")
    assert "['trimmed', 'orderbox'].forEach(function (ev) { core.on(ev, function () { if (laidNow()) { scheduleArrange(ev); } }); });" in shell
    assert JS.count("    form.order_list_on = '';") == 2 and JS.count("    form.order_list = '';") == 2   # V1 · V2 나누기
    assert "partFormBoxes(s)" in _fn(JS, "partArrangePlan") and "partFormBoxes(s)" in _fn(JS, "partFreshPlan")


def test_presets_seed_at_top_center_and_legacy_untouched_ones_move_up():
    assert "x: PRESET_TOP_X0 + i * PRESET_TOP_GAP, y: PRESET_TOP_Y" in _fn(JS, "seedPresetObjects")
    m = _fn(JS, "moveLegacySeedRight")
    assert "o.x !== 48 + i * PRESET_SEED_GAP && o.x !== right" in m and "o.y = PRESET_TOP_Y;" in m
    x0 = int(re.search(r"var PRESET_TOP_X0 = (\d+);", JS).group(1))
    gap = int(re.search(r"var PRESET_TOP_GAP = (\d+);", JS).group(1))
    assert x0 + 4 * gap + 110 < 1074                                                    # [마이다]까지 발주 리스트 칸 앞에서 끝난다


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
