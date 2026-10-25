"""도면 마법사 자재표 계산 칸 — 실화면 QA(2026-10-25 V1·V2) 남은 문제 계약(node).

- V2 한 치수 차이 한도: 수량이 같고 한 치수만 다른 짝에 한도가 없어 서로 다른 물건이 한 줄로 묶였다
  (옷봉 465 ↔ 시트 1200 '길이 -735', 문 470 ↔ 시트 900 '너비 -430') → ±100 넘으면(문 높이만 ±200)
  '시트에 없음'·'계산에 없음' 두 줄로 가른다.
- V2 부호 방향: 같은 결과 칸 안에서 '높이 -100(시트 2260)' 바로 아래 '여유 +10(시트 975=4)' — 한 치수 다름은
  계산 − 시트, 여유·짧음은 시트 − 계산이었다 → 모두 시트 − 계산(시트가 크면 +).
- V1 모달 창 키: 규칙 창을 연 채 Ctrl+S 로 도면을 저장하면 초점이 창 밖(body)으로 빠져, 그 뒤 Ctrl+Z 가 흐린 바탕
  뒤 그림의 이름표를 되돌렸다 → 마법사 문서 keydown 은 모달 창이 열려 있으면 Ctrl+S 말고는 받지 않고, 규칙 창은
  Ctrl+S 도 스스로 막고 안내한다(창 동작 자체는 test_drawing_bom_panel_ui.py 가 가짜 DOM 으로 본다).
"""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CALC_JS = ROOT / "static/js/drawing/bom-calc.js"
DIALOG_JS = ROOT / "static/js/drawing/bom-rules-dialog.js"
WIZARD_JS = ROOT / "static/js/drawing/wizard.js"

COMPARE_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const C = window.FomsBomCalc;
const line = (sec, a, b, q) => ({ sec, a, b, q, text: (b == null ? a : a + '*' + b) + '=' + q });
const show = (lines, sheet) => C.compare(lines, C.parseBom(sheet)).map(r => r.kind + ' ' + r.text + ' ' + r.note);
process.stdout.write(JSON.stringify({
  far_rod: show([line('옷봉', 465, null, 1)], ['[옷봉]\n1200=1']),
  far_door: show([line('DOOR', 483, 2160, 6), line('DOOR', 470, 2160, 1)], ['[DOOR]\n483*2260=6\n900*2160=1']),
  edge: show([line('DOOR', 483, 2160, 2), line('옷봉', 965, null, 2)], ['[DOOR]\n382*2160=2\n[옷봉]\n1065=2']),
  door_h: show([line('DOOR', 483, 2160, 4), line('DOOR', 483, 1407, 2)], ['[DOOR]\n483*2360=4\n483*1700=2']),
  sr: show([line('SR', 110, 2440, 2)], ['[SR]\n60*2440=2']),
  signs: show([line('DOOR', 483, 2160, 6), line('옷봉', 965, null, 4), line('DOOR', 483, 1407, 2)],
    ['[DOOR]\n483*2260=6\n483*1400=2\n[옷봉]\n975=4']),
}));
"""

MODAL_RUNNER = r"""
const src = process.argv[1];
const cases = [[], [{ modal: true }], [{ modal: false }], [{ modal: false }, { modal: 'old' }]];
process.stdout.write(JSON.stringify(cases.map(list => {
  const document = { querySelectorAll: sel => (sel === 'dialog[open]' ? list.map(d => ({
    matches(s) { if (d.modal === 'old') { throw new SyntaxError(s); } return s === ':modal' && d.modal; } })) : []) };
  return new Function('document', src + '\nreturn modalDialogOpen();')(document);
})));
"""


def _node(*args):
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, "-e", *args], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_one_dimension_pair_has_limit():
    """서로 다른 물건은 두 줄로 가르고, 같은 물건의 한 치수 차이(±100, 문 높이 ±200)만 한 줄로 묶는다."""
    res = _node(COMPARE_RUNNER, str(CALC_JS))
    assert res["far_rod"] == ["bad 465=1 시트에 없음", "extra 1200=1 계산에 없음"]
    assert res["far_door"] == ["bad 483*2160=6 높이 +100(시트 2260)", "bad 470*2160=1 시트에 없음",
                               "extra 900*2160=1 계산에 없음"]
    # 한도 경계: 문 너비 101 차이는 가르고, 옷봉 길이 100 차이는 묶는다
    assert res["edge"] == ["bad 483*2160=2 시트에 없음", "bad 965=2 길이 +100(시트 1065)", "extra 382*2160=2 계산에 없음"]
    # 문 높이는 표준 높이 두 칸(200)까지 묶고, 넘으면(293) 가른다
    assert res["door_h"] == ["bad 483*2160=4 높이 +200(시트 2360)", "bad 483*1407=2 시트에 없음",
                             "extra 483*1700=2 계산에 없음"]
    assert res["sr"] == ["bad 110*2440=2 폭 -50(시트 60)"]   # SR 위 판 폭 50 차이는 같은 판


def test_sign_direction_matches_margin_and_short():
    """같은 결과 칸 안: 시트가 크면 한 치수 다름·여유 모두 +, 시트가 작으면 짧음·한 치수 다름 모두 −."""
    res = _node(COMPARE_RUNNER, str(CALC_JS))
    assert res["signs"] == ["bad 483*2160=6 높이 +100(시트 2260)", "warn 965=4 여유 +10(시트 975=4)",
                            "bad 483*1407=2 짧음 -7(시트 483*1400=2)"]


def test_document_shortcuts_skip_while_modal_dialog_open():
    """마법사 문서 keydown: 모달 창이 열려 있으면 Ctrl+S 말고는 받지 않는다(라이트박스·도움말 다음, 저장보다 앞)."""
    wjs = WIZARD_JS.read_text(encoding="utf-8")
    helper = "function modalDialogOpen() {" + wjs.split("function modalDialogOpen() {", 1)[1].split("\n  }\n", 1)[0] + "\n  }"
    # 열린 창 없음 · 모달 창 · 모달 아닌 창 · :modal 을 모르는 옛 브라우저(열린 창은 모달로 본다)
    assert _node(MODAL_RUNNER, helper) == [False, True, False, True]
    handler = wjs.split("if (isHelpOpen()) {", 1)[1]
    guard = handler.index("if (modalDialogOpen() && !((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S'))) { return; }")
    assert guard < handler.index("if (meta && (e.key === 's' || e.key === 'S')) { e.preventDefault(); save(); return; }")
    assert guard < handler.index("setAnnoMode('text');") and guard < handler.index("redo();")
    # 규칙 창은 window 잡는 단계에서 먼저 막는다 — 초점이 창 밖이어도 문서 처리(저장·되돌리기)까지 가지 않게
    assert "window.addEventListener('keydown', guardOutside, true)" in DIALOG_JS.read_text(encoding="utf-8")
