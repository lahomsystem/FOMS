"""안 타는 생산 화면 코드 지움(2026-11-27, 옛 생산 보드 · 옆 시트 지운 뒤 — 설계서 2026-11-27-production-legacy-board-removal §6-3 · §6-4).

지운 것: 작업 시트 공정 칸 JS 의 공정 GET 갈래(옆 시트는 자료가 안 실려 칸을 켤 때 GET 했다 — 이제 자료 없는 화면이 없다) · 풀어 쓴
응답(expanded) 글(doneText · expandedNote · 첫 화면 줄 · 판의 알림 갈래 — 서버가 도면 있는 주문 켜기를 409 로 막아 응답에 안 온다) ·
옆 시트 [제작 완료] 단추 갈래(.foms-prod-sheet) · 옆 시트 CSS(.foms-prod-sheet__*) · PC 창 [모두 완료 처리](서버 ``all`` 이 늘 거짓).
남긴 것: 공정 POST · 도면 0장 주문 칸 켜기 · [모두 완료 취소](손 체크 끄기) · PC 창 자료 칸(data-foms-sheet-parts).

되돌리면 실패: 지운 이름 · 주소가 다시 나타남 · 자료 없는 화면에서 칸 켜기가 GET 을 보냄 · 핀이 싣는 곳마다 다름. 이름은 지어낸 값.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PARTS = "static/js/production/foms-production-sheet-parts.js"
PAGE = "static/js/production/foms-production-sheet-page.js"
HOME = "static/js/production/foms-production-home.js"
STEPS = "static/js/production/foms-production-home-steps.js"
PC = "static/js/production/foms-production-pc-sheet.js"
PC_WRITE = "static/js/production/foms-production-pc-sheet-write.js"
CSS = "static/css/contexts/production/sheet.css"
PIN = "20261127x"
WORDS_PIN = "20261127z"
PARTS_PIN = "20261128b"  # 11-28 b: 바뀐 기록 겹친 완료 빼기 · 11-28 a: 도면 없는 주문 안내 글(test_production_wording_1127_z1)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_지운_길이_다시_안_나타난다() -> None:
    parts = _read(PARTS)
    assert "fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })" in parts  # 바뀐 기록 GET 은 남는다
    assert "/production/steps" not in parts and "function load(" not in parts
    for gone in ("doneText", "expandedNote", "payload.expanded"):
        assert gone not in parts, gone
    for rel in (HOME, STEPS):
        src = _read(rel)
        assert ".expanded" not in src and "doneText" not in src and "holdInPlace" not in src and "u.notice" not in src, rel
        assert "/production/steps'" in src  # 공정 POST 는 그대로
    page = _read(PAGE)
    assert ".foms-prod-sheet" not in page and "foms-prod-sheet__btn" not in page
    assert "var completeBtn = page.querySelector('[data-foms-sheet-complete]');" in page
    pc, write = _read(PC), _read(PC_WRITE)
    assert "'모두 완료 처리'" not in pc and "kind === 'all'" not in pc and "askAll" not in pc + write
    assert "actButton('모두 완료 취소', 'hand-off'" in pc and "W.stepSet(S.data, false)" in pc and "function stepSet(d, on)" in write


def test_옆_시트_CSS_는_없고_어떤_화면도_그_클래스를_안_만든다() -> None:
    assert ".foms-prod-sheet__" not in _read(CSS) and ".foms-prod-sheet ." not in _read(CSS)
    hits = []
    for base in ("templates", "static/js", "foms"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix in (".html", ".js", ".py") and path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                if 'class="foms-prod-sheet' in text or "'foms-prod-sheet" in text or '"foms-prod-sheet' in text:
                    hits.append(path.relative_to(ROOT).as_posix())
    assert hits == []


def test_고친_파일_핀은_싣는_곳마다_같다() -> None:
    sheet = _read("templates/production/sheet.html")
    scripts = _read("templates/production/partials/home_scripts.html")
    for name in ("foms-production-pc-sheet.js", "foms-production-pc-sheet-write.js"):
        assert f"js/production/{name}') }}}}?v={PIN}" in sheet, name
    for name, pin in (("foms-production-sheet-parts.js", PARTS_PIN), ("foms-production-sheet-page.js", WORDS_PIN)):  # 11-27 z: 바뀐 기록 낱말 · 공정 칸 알림(test_production_record_words_tone_1127)
        assert f"js/production/{name}') }}}}?v={pin}" in sheet, name
    assert "css/contexts/production/sheet.css') }}?v=20261128a" in sheet  # 11-28 a: 수정 제작 고르기 창 줄
    assert scripts.count(f"foms-production-sheet-parts.js') }}}}?v={PARTS_PIN}") == 2
    for name in ("foms-production-home.js", "foms-production-pc-sheet.js", "foms-production-pc-sheet-write.js"):
        assert f"js/production/{name}') }}}}?v={PIN}" in scripts, name
    assert f"foms-production-sheet-page.js') }}}}?v={WORDS_PIN}" in _read("templates/production/partials/home_body.html")
    assert f"foms-production-home-steps.js') }}}}?v={PIN}" in _read("templates/production/partials/home_early.html")


_NODE = r"""
'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const calls = [];
function el(attrs) {
  return { attrs: attrs || {}, hidden: true, textContent: '',
    hasAttribute(n) { return n in this.attrs; }, getAttribute(n) { return n in this.attrs ? this.attrs[n] : null; },
    setAttribute(n, v) { this.attrs[n] = String(v); }, querySelector() { return null; } };
}
const ctx = { console, JSON, Date, Promise, CustomEvent: function () {}, fetch: (u) => { calls.push(u); return Promise.resolve({ ok: true, json: () => ({}) }); },
  document: { addEventListener() {}, querySelector() { return null; }, contains() { return true; } } };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx);
const sp = ctx.FomsSheetParts;
const want = JSON.parse(process.argv[3]);
// 자료 없는 화면(도면 0장 · 자료 칸 없음) — 묻지 않고 바로 보낸다, GET 0
let went = 0;
const bare = el({ 'data-order-id': '7' });
const btn = el({ 'data-foms-sheet-step': 'cut' });
sp.beforeToggle(bare, btn, true, () => { went += 1; }, () => { throw new Error('no'); });
assert.strictEqual(went, 1);
// 도면 있는 주문 자료(per_sheet) — 칸 아래 서버 글만, 요청 0
const msg = el({});
const drawn = el({ 'data-foms-sheet-parts': JSON.stringify({ sheets: 2, parts: { cut: { uses_cards: false } }, per_sheet: want.per_sheet }) });
drawn.querySelector = (s) => (s === '[data-foms-sheet-stepmsg]' ? msg : null);
let refused = 0;
sp.beforeToggle(drawn, btn, true, () => { throw new Error('go'); }, () => { refused += 1; });
assert.strictEqual(refused, 1);
assert.strictEqual(msg.textContent, want.per_sheet);
assert.strictEqual(msg.hidden, false);
// 끄기는 늘 바로
sp.beforeToggle(drawn, btn, false, () => { went += 1; });
assert.strictEqual(went, 2);
assert.deepStrictEqual(calls, [], '공정 GET 없음');
assert.strictEqual(typeof sp.doneText, 'undefined');
console.log('OK');
"""


def test_칸_켜기는_화면_자료만_읽고_GET_을_안_보낸다_Node(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    script = tmp_path / "check.js"
    script.write_text(_NODE, encoding="utf-8")
    want = {"per_sheet": "도면이 있는 주문은 도면 화면에서 완료해 주세요."}
    proc = subprocess.run([node, str(script), str(ROOT / PARTS), json.dumps(want, ensure_ascii=False)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr
