"""도면 마법사 V2 — 왼쪽 칸 사용성(2026-10-27 도면팀원 눈 평가): 확인할 그림 상자 · 사실대로 쉬운 글 · 자재 카드 · 그림 밑 딱지.

설계서: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §1
- '확인할 그림' 상자는 왼쪽 칸 맨 위(탭 바로 밑)에, 고를 그림이 있을 때만 — 셈은 앱바 '미분류 N장 ›' 칩과 같다(v2-check.js).
  예전 미분류 상자는 카드 목록 맨 끝이라 작은 화면에선 안 보였다.
- 종류 단추 2~4개 = AI 첫 짐작 → 칸 짐작 · 첫 짐작의 칸 식구 → 큰 그림 넷, 나머지는 '그 밖 ▾'. 누르면 바로 바꾸고 다음 그림으로.
- 제품 종류 글은 detectKind 가 실제로 보는 것(제품 · 시트 이름)을 말한다. 탭 '그림 N' = 종이에 놓인 그림 수.
- 자재 카드: 눌리지 않는 '직접 입력' 칩 없음 · 자재표 글자가 없으면 [자재표 칸 넣기](엔진 addPresets — 되돌리기 한 번, 글 편집기 안 엶).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "static/js/drawing"
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
LEFT_TPL = (ROOT / "templates/drawing/partials/wizard_v2_left.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard-v2.css").read_text(encoding="utf-8")
ENGINE = (JS_DIR / "wizard.js").read_text(encoding="utf-8")
LABELS = ["정면·내부", "정면·도어", "입체·내부", "입체·도어", "평면·상판", "서랍 단면", "부품 상세", "사진", "그림 아님", "탑뷰", "사이드뷰"]   # 탑뷰 · 사이드뷰 2026-10-28


def _js(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


RUNNER = r"""
global.window = {};
const dir = process.argv[1];
require(dir + '/v2-slots.js');
require(dir + '/v2-check.js');
const C = window.FomsV2Check;
const out = {};
const img = (id, x, y, part) => ({ id, type: 'image', key: id + '.png', x, y, w: 300, h: 200, part });
"""


def _run(body: str) -> dict:
    script = RUNNER + body + "\nprocess.stdout.write(JSON.stringify(out));"
    proc = subprocess.run([_node(), "-e", script, str(JS_DIR)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_node_check_new_and_changed_modules():
    for name in ("v2-check.js", "v2-left.js", "wizard.js"):
        proc = subprocess.run([_node(), "--check", str(JS_DIR / name)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, (name, proc.stderr)


def test_check_box_sits_first_under_tabs_and_starts_hidden():
    pane = LEFT_TPL[LEFT_TPL.index('data-v2-pane="slots"'):LEFT_TPL.index('data-v2-pane="photos"')]
    assert pane.index('id="dws-v2-unsorted"') < pane.index('id="dws-v2-kind"') < pane.index('id="dws-v2-cards"')   # 탭 바로 밑
    assert re.search(r'<section class="dws-v2-unsorted" id="dws-v2-unsorted"[^>]*\shidden>', pane)
    assert "style=" not in LEFT_TPL
    assert ".dws-v2-unsorted[hidden] { display: none; }" in CSS          # 상자의 display: flex 가 hidden 을 덮지 않게


def test_left_texts_say_what_the_code_does():
    assert '>그림 <span data-v2-count="slots">' in LEFT_TPL and '>칸 <span' not in LEFT_TPL
    assert "(제품 · 시트 이름을 보고 골랐어요)" in LEFT_TPL and "그림을 보고 자동으로" not in LEFT_TPL
    # detectKind 가 받는 글 = 엔진 productText = 제품 이름 + 시트 이름(그림은 보지 않는다)
    assert "productText: function () { return sheetProductText(currentSheet()); }," in ENGINE
    assert "return (p.name || '') + ' ' + ((s && s.name) || '');" in ENGINE
    assert "var kindAuto = S().detectKind(ctx && ctx.productText);" in _js("v2-plan.js")
    left = _js("v2-left.js")
    assert "계산해 보기 (참고용)" in left and "자재표 계산 열기" not in left and "직접 입력" not in left
    assert "실측 사진 탭에서 눌러 넣어요" in left
    assert "setCount('slots', g.main.length + g.iso.length + g.detail.length + g.plan.length + g.unsorted.length);" in left
    assert "' · 큰 그림 '" not in left and "(k.key === plan.kindAuto ? ' (자동)' : '')" in left   # 항목엔 종류 이름만


def test_pending_matches_app_bar_chip_count_and_reading_order():
    out = _run(r"""
const sheet = { objects: [
  img('a', 600, 300, { label: '미분류', src: 'ai', ai: '정면·도어', conf: 0.36 }),
  img('b', 100, 320, { label: '미분류', src: 'user' }),
  img('c', 50, 60, { label: '부품 상세', src: 'ai', ai: '부품 상세', conf: 0.9 }),
  img('d', 900, 40, undefined),
  img('e', 400, 50, { label: '그림 아님', src: 'ai', ai: '그림 아님', conf: 0.8 }),
  { id: 't', type: 'text', text: '[SR]', x: 0, y: 0 }] };
out.idle = C.pending(sheet, false).map(o => o.id);
out.busy = C.pending(sheet, true).map(o => o.id);
out.empty = C.pending(null, false).length;
""")
    assert out["idle"] == ["d", "b", "a"]    # 위 줄(y 40) → 아래 줄(y 300~320)은 왼쪽부터 · 확신 이름표 · 그림 아님 · 글자는 빼고
    assert out["busy"] == ["b", "a"]         # 알아보는 중이면 이름표 없는 그림은 아직 세지 않는다(칩과 같다)
    assert out["empty"] == 0


def test_choice_buttons_follow_ai_guess_then_slot_family():
    out = _run(r"""
const g = { guess: { gf: { fam: 'f', conf: 0.71 }, gd: { fam: 'd', conf: 0.66 } } };
const unsure = (ai, src) => ({ label: '미분류', src: src || 'ai', ai: ai, conf: 0.3 });
out.front = C.choices(img('gf', 0, 0, unsure('입체·도어')), g, false);
out.frontKitchen = C.choices(img('gf', 0, 0, unsure('정면·도어')), g, true);
out.detail = C.choices(img('gd', 0, 0, unsure('부품 상세')), g, false);
out.noGuess = C.choices(img('u', 0, 0, unsure('서랍 단면')), g, false);
out.photo = C.choices(img('p', 0, 0, unsure('사진')), g, false);
out.none = C.choices(img('n', 0, 0, { label: '미분류', src: 'user' }), g, false);
""")
    assert out["front"]["quick"] == ["입체·도어", "정면·내부", "정면·도어", "입체·내부"]   # AI 첫 짐작 → 짐작 칸(정면) 식구 → 입체
    assert out["frontKitchen"]["quick"] == ["정면·도어", "정면·내부"]                      # 주방은 짐작 칸의 둘만
    assert out["detail"]["quick"] == ["부품 상세", "서랍 단면"]
    assert out["noGuess"]["quick"] == ["서랍 단면", "부품 상세"]                           # 칸 짐작이 없으면 첫 짐작의 칸 식구
    assert out["photo"]["quick"] == ["사진", "정면·내부", "정면·도어", "입체·내부"]         # 식구가 없으면 큰 그림으로 채운다
    assert out["none"]["quick"] == ["정면·내부", "정면·도어", "입체·내부", "입체·도어"]
    for v in out.values():
        assert 2 <= len(v["quick"]) <= 4 and "미분류" not in v["rest"]
        assert sorted(v["quick"] + v["rest"]) == sorted(LABELS)                            # '그 밖 ▾' = 나머지 전부


def test_check_box_relabels_moves_focus_points_on_paper_and_takes_the_chip():
    chk = _js("v2-check.js")
    pick = chk[chk.index("  function pick("):chk.index("  function row(")]
    assert pick.index("want = ") < pick.index("api.relabel(id, label);")   # 바로 바꾸고, 다시 그린 뒤 다음 그림으로 초점
    render = chk[chk.index("  function render("):chk.index("  function show(")]
    assert render.index("if (s !== sig) {") < render.index("draw(items, plan);")   # 고를 것이 그대로면 새로 만들지 않는다
    assert "focusRow(w, null, true);" in render
    assert "'dws-v2-point dws-ui'" in chk and "document.getElementById('dws-stage')" in chk   # 종이 위 짚기는 화면에만
    assert re.search(r"\.dws-v2-point \{[^}]*pointer-events: none;", CSS)
    wiz_css = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
    assert ".dws-exporting .dws-ui { display: none !important; }" in wiz_css                 # PNG · 저장 그림에서 숨는 규칙
    assert "document.addEventListener('click', onChip, true);" in chk                        # 앱바 칩은 캡처 단계에서 받는다
    chip = chk[chk.index("  function onChip("):chk.index("  function init(")]
    assert chip.index("els.box.hidden") < chip.index("e.preventDefault();") < chip.index("show(null);")
    # 막지 않고 표시만 — 문서 클릭(⋯ 메뉴 · V1 메뉴 닫기)이 돈다. 예전엔 stopPropagation 이라 메뉴가 열린 채 남았다(10-27)
    assert "e.stopPropagation()" not in chip
    status = _js("part-status.js")
    assert "unsure.addEventListener('click', function (e) { if (!e.defaultPrevented && on.next) { on.next(); } });" in status
    assert "그림을 보고 종류를 골라 주세요" in chk and "'그 밖 ▾'" in chk
    left = _js("v2-left.js")
    assert "window.FomsV2Check.init(a);" in left and "check.render(view);" in left
    assert "window.FomsV2Check.show(o.id);" in left                                          # 카드의 '?' · 미분류 딱지 → 확인할 그림
    assert "renderUnsorted" not in left and "dws-v2-unsorted-select" not in left             # 맨 아래 미분류 상자는 없다


def test_card_tag_sits_right_under_each_thumb():
    left = _js("v2-left.js")
    card = left[left.index("  function card("):left.index("  function lowPct(")]
    assert card.index("f.appendChild(thumb(o, view));") < card.index("f.appendChild(tag(o, view));")
    assert "list.slice(0, 4)" not in left                    # 작은 그림을 4장에서 자르지 않는다(딱지와 짝이 맞게)
    assert ".dws-v2-fig { display: flex; flex-direction: column;" in CSS
    cards = left[left.index("  function renderCards("):left.index("  function renderKind(")]
    assert "slots.sort(" in cards and "L[k[0]] || (k[0] === 'main' ? '' : '~')" in cards   # 카드는 칸 글자 순서(빈 큰 그림 칸은 맨 앞)
    assert "[['현장규격', f.site_spec], ['색상', f.color]]" in cards                         # 곁글에 아래 띠 칸 이름(1500 이 무엇인지)


def test_bom_card_adds_preset_placeholders_with_one_undo():
    left = _js("v2-left.js")
    tools = left[left.index("  function bomTools("):left.index("  function renderCards(")]
    assert tools.index("if (!n) {") < tools.index("'자재표 칸 넣기'")           # 자재표 글자가 없을 때만
    add = left[left.index("  function addBom("):left.index("  function bomTools(")]
    assert add.index("core.addPresets()") < add.index("api.arrange('bom', {})")   # 넣은 뒤 V2 배치(따로 되돌리기 없음)
    assert "sh.form.v2_layout" in add
    eng = ENGINE[ENGINE.index("  function v2AddPresets("):ENGINE.index("  function exposeCore() {")]
    assert eng.count("recordUndo();") == 1
    assert eng.index("recordUndo();") < eng.index("insertPresetText(PRESETS[k] + '\\n', false, true)")
    assert "startEditText" not in eng
    assert "addPresets: v2AddPresets," in ENGINE[ENGINE.index("  function exposeCore() {"):ENGINE.index("emitCore('ready'")]
    ins = ENGINE[ENGINE.index("  function insertPresetText("):ENGINE.index("  function addPreset(")]
    assert "if (!quiet) { recordUndo(); }" in ins
    assert ins.index("if (quiet) { return o; }") < ins.index("startEditText(nodeById[o.id], true);")   # 조용히 넣기는 편집기를 안 연다
    assert "insertPresetText(label + '\\n', false);" in ENGINE                   # 메뉴 프리셋(V1)은 예전처럼 편집기를 연다


def test_assets_pinned_and_check_module_loaded_before_shell():
    assert "js/drawing/v2-left.js') }}?v=20261028a" in TPL
    assert "css/contexts/drawing/wizard-v2.css') }}?v=20261028b" in TPL   # 10-28 알림 띠 탭 줄 · 내 문구 단추
    assert "js/drawing/v2-check.js') }}?v=20261028a" in TPL   # 10-27 작은 고침(장 번호 · ⋯ 메뉴 닫힘)
    assert "js/drawing/wizard.js') }}?v=20261029a" in TPL    # 10-28 moved · 줄여 그린 그림 고운 필터 · 확대 해상도
    pos = [TPL.index(f"js/drawing/{name}") for name in ("wizard.js", "v2-check.js", "v2-left.js", "v2-shell.js")]
    assert pos == sorted(pos)
