"""도면 마법사 V2 — 주 그림 크기 막대(v2-size.js · v2-hero.js refine, node 로 돌린다).

사용자 요청(2026-10-28): 숫자가 몇 px 이면 안 읽히는지 기준을 정하자는 물음에 '아냐 컴퍼넌트 사이즈는 자유로 조절 가능하게' →
'막대로 크기 정하기'를 골랐다. 오른쪽 칸 '그림 크기' 아래 막대를 끌면 주 그림이 고르게 때 높이의 100% ~ 큰 그림 칸이 허락하는
만큼(시트 폼 v2_hero_size) 커지고 나머지는 남은 자리에 맞춰 줄어든다. 숫자 8px 기준 · 두드러짐(1.3배) · 1.15배 문턱으로 막지 않고,
나머지는 주 그림보다 크게 놓지 않는다. 손을 떼면 한 번 다시 배치(되돌리기 한 번), [자동으로]는 예전 자동으로.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tests.domains.test_drawing_wizard_v2_hero import HERO
from tests.domains.test_drawing_wizard_v2_layout import ARRANGE, INPUT
from tests.domains.test_drawing_wizard_v2_layout import _run as _run_layout
from tests.domains.test_drawing_wizard_v2_right_ux import UI
from tests.domains.test_drawing_wizard_v2_right_ux import _run as _run_ui

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "static/js/drawing"
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
RIGHT_TPL = (ROOT / "templates/drawing/partials/wizard_v2_right.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard-v2.css").read_text(encoding="utf-8")


def test_node_check_v2_size():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, "--check", str(JS_DIR / "v2-size.js")], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr


def test_slider_value_sets_main_picture_size_and_the_rest_fits_without_overlap():
    """4385 꼴 시트: 자동은 148%(칸 끝 164%). 막대 값대로 주 그림 높이가 정해지고, 범위 밖은 끝으로 붙는다.
    나머지는 주 그림보다 크게 놓지 않고, 위 띠(사진 · 상세 · 평면)는 그대로다."""
    out = _run_layout(ARRANGE + HERO + r"""
const even = heroSheet(); even.form.v2_style = 'even';
const auto = heroSheet(), a = arrange(auto), e = arrange(even);
const E = find(even, 'hero').h;
out.auto = [a.res.size, Math.round(100 * find(auto, 'hero').h / E)];
out.evenSize = e.res.size.pct;
out.cases = [100, 120, 130, 999, 50].map(v => {
  const s = heroSheet(); s.form.v2_hero_size = String(v); const r = arrange(s);
  const sc = id => find(s, id).h / find(s, id).natural_h;
  return { v, size: r.res.size, hero: r.res.hero, pct: Math.round(100 * find(s, 'hero').h / E), overlaps: overlaps(s).length,
    restLe: ['g1', 'g2'].every(id => sc(id) <= sc('hero') + 1e-6),
    band: ['ph', 'd1', 'd2', 'd3', 'p1', 'u1'].every(id => rectOf(find(s, id)) === rectOf(find(auto, id))) };
});
""")
    size, pct = out["auto"]
    assert size == {"min": 100, "max": 164, "pct": 148, "manual": False} and pct == 148
    assert out["evenSize"] == 100                                     # 고르게 시트는 100% 로 보인다
    want = {100: 100, 120: 120, 130: 130, 999: 164, 50: 100}         # 범위 밖은 끝으로
    for c in out["cases"]:
        assert c["size"]["manual"] is True and c["size"]["pct"] == want[c["v"]] and c["pct"] == want[c["v"]], c
        assert c["hero"] == ["hero"] and c["overlaps"] == 0 and c["restLe"] and c["band"], c


def test_slider_is_not_held_back_by_number_floor_or_close_sizes():
    """자동은 나머지 숫자 8px 에서 멈추지만(165%) 막대는 칸 끝(178%)까지 — 숫자가 5.5px 로 작아져도 따른다(알림은 그대로).
    원본 넓이가 비슷해 자동이 주 그림을 안 고르는 시트도 막대를 끌면 가장 큰 그림을 주 그림으로 키운다."""
    out = _run_layout(INPUT + r"""
const tiny = [{ slot: 'main', members: [{ id: 'a', nw: 1067, nh: 1049, tx: 20 }] }, { slot: 'main', members: [{ id: 'h', nw: 1696, nh: 1223, tx: 20 }] },
  { slot: 'main', members: [{ id: 'b', nw: 1049, nh: 1049, tx: 20 }] }];
const wrap = units => ({ units, photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [] });
const h = (r, id) => r.moves.find(m => m.id === id).h;
const auto = L.compute(wrap(tiny), {}).band, keep = L.compute(wrap(tiny), { hero: false }).band, max = L.compute(wrap(tiny), { heroSize: 999 }).band;
out.floor = [auto.size, h(auto, 'a') === h(keep, 'a'), max.size.pct, 20 * h(max, 'a') / 1049, max.crowded];
const close = [{ slot: 'main', members: [{ id: 'a', nw: 1200, nh: 1000, tx: 0 }] }, { slot: 'main', members: [{ id: 'b', nw: 1100, nh: 1000, tx: 0 }] },
  { slot: 'main', members: [{ id: 'c', nw: 1000, nh: 900, tx: 0 }] }];
const c0 = L.compute(wrap(close), {}).band, c1 = L.compute(wrap(close), { heroSize: 130 }).band, ck = L.compute(wrap(close), { hero: false }).band;
out.close = [c0.hero || null, c0.size, c1.hero, Math.round(100 * h(c1, 'a') / h(ck, 'a'))];
""")
    auto, same, top, text, crowded = out["floor"]
    assert auto == {"min": 100, "max": 178, "pct": 165, "manual": False} and same    # 자동: 나머지는 8px 하한에서 멈춤
    assert top == 178 and text < 8 and crowded is True                                # 막대: 숫자 기준으로 막지 않음 · 알림은 남음
    hero0, size0, hero1, pct1 = out["close"]
    assert hero0 is None and size0["max"] > 100 and size0["pct"] == 100
    assert hero1 == ["a"] and pct1 == 130


def test_slider_drag_release_undo_auto_and_even_switch():
    """끄는 동안은 % 글자만, 손을 떼면 한 번 다시 배치(되돌리기 한 번). [자동으로]는 폼 값을 지운다. 고르게 시트에서 끌면 주 그림 크게로."""
    out = _run_ui(UI, r"""
state.sheets = [{ id: 's1', name: '붙박이장', form: {}, objects: [img('h1', '입체·내부', 1696, 1223, 0), img('g1', '정면·도어', 1067, 1049, 1),
  img('g2', '입체·내부', 1049, 1049, 2), img('d1', '서랍 단면', 490, 403, 3), img('t1', '평면·상판', 1335, 1065, 4)] }];
emit('batch', { ids: state.sheets[0].objects.map(o => o.id), sheetId: 's1' });
tick(100);
const box = dom['dws-v2-size'], h = id => core.sheet().objects.find(o => o.id === id).h;
const range = () => box.children.find(n => n.className === 'dws-v2-size-range');
const autoBtn = () => box.children[0].children.find(n => n.className === 'dws-v2-size-auto') || null;
const fire = (n, ev) => (n.handlers[ev] || []).forEach(fn => fn({}));
const styles = () => dom['dws-v2-styles'].children.filter(n => n.className === 'dws-v2-tpl');
out.first = [box.hidden, range().type, range().min, Number(range().max) > Number(range().value), Number(range().value) > 100, box.textContent, !!autoBtn()];
const autoH = h('h1'), depth = undo.length;
range().value = range().min; fire(range(), 'input');
out.typing = [box.textContent.indexOf('100%') >= 0, h('h1') === autoH, undo.length - depth];
fire(range(), 'change'); tick(100);
out.low = [core.sheet().form.v2_hero_size, h('h1') < autoH, undo.length - depth, box.textContent, !!autoBtn(), toasts[toasts.length - 1] || ''];
autoBtn().click(); tick(100);
out.auto = [core.sheet().form.v2_hero_size || '', h('h1') === autoH, !!autoBtn()];
core.undo(); tick(100);
out.undone = core.sheet().form.v2_hero_size || '';
styles()[1].click(); tick(100);
out.evenNote = box.textContent;
range().value = '120'; fire(range(), 'change'); tick(100);
out.fromEven = [core.sheet().form.v2_style, core.sheet().form.v2_hero_size, styles().map(c => c.textContent)];
""")
    hidden, kind, lo, below_max, above_100, text, has_auto = out["first"]
    assert hidden is False and kind == "range" and lo == "100" and below_max and above_100
    assert "주 그림 크기" in text and "자동으로 정한 크기예요" in text and "고르게 때 크기" in text and not has_auto
    assert out["typing"] == [True, True, 0]                                     # 끄는 동안은 글자만
    form, smaller, undos, text, has_auto, toast = out["low"]
    assert form == "100" and smaller and undos == 1 and "직접 정한 크기예요" in text and has_auto and "되돌리기" in toast
    assert out["auto"] == ["", True, False]                                     # [자동으로] = 예전 자동
    assert out["undone"] == "100"
    assert "지금은 고르게예요" in out["evenNote"]
    style, value, cards = out["fromEven"]
    assert style == "hero" and value == "120" and "지금 쓰는 스타일" in cards[0]   # 고르게에서 끌면 주 그림 크게로


def test_slider_wiring_template_css_and_pins():
    plan = (JS_DIR / "v2-plan.js").read_text(encoding="utf-8")
    chrome = (JS_DIR / "v2-chrome.js").read_text(encoding="utf-8")
    right = (JS_DIR / "v2-right.js").read_text(encoding="utf-8")
    assert '<div class="dws-v2-size" id="dws-v2-size" hidden></div>' in RIGHT_TPL
    assert RIGHT_TPL.index('id="dws-v2-styles"') < RIGHT_TPL.index('id="dws-v2-size"')
    assert TPL.index("js/drawing/v2-size.js') }}?v=20261028a") < TPL.index("js/drawing/v2-right.js') }}?v=20261028d")
    for asset in ("js/drawing/v2-hero.js') }}?v=20261028c", "js/drawing/v2-pack.js') }}?v=20261028b",
                  "css/contexts/drawing/wizard-v2.css') }}?v=20261028a"):
        assert asset in TPL, asset
    assert ".dws-v2-size[hidden] { display: none; }" in CSS                    # display:flex 가 hidden 을 이기지 않게
    assert "heroSize: parseInt(form.v2_hero_size, 10) || 0" in plan
    assert "style: 1, size: 1 }" in chrome
    assert "window.FomsV2Size.render(els.size, res, api, plan.style)" in right
