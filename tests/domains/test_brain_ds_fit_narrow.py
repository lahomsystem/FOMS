"""새 회사 지식 화면 좁은 칸 대비(접목판 점검 3차 B1 · B3).

- B1 온톨로지 표(지식 유형 속성 7칸 · 연결 · 능력 질문 · 속성 ↔ 지금 칸 · 할 일 종류): 표가 담긴 칸보다 넓으면 줄마다 카드
  (``.is-stacked``)로 바꾼다 — ``ds-onto-kit.js`` 가 칸 폭을 재서(ResizeObserver) 단다. 칸마다 머리 이름(``data-label``)이 붙어
  카드에서 값 앞에 보인다. 넓으면 표 그대로(PC 100% · 2400 은 고치기 전과 같은 그림).
- B3 ``@container`` 를 모르는 옛 브라우저(크롬 105 · 사파리 16 아래): AI 직원 할 일 표 · 'AI 시험' 줄은
  ``@supports not (container-type: inline-size)`` 안의 폰 폭(640px 아래) 미디어 질의로 좁은 모습을 받는다.
DOM 은 node 의 가짜 요소로만(브라우저 없음). 실제 화면 잰 값은 스크래치패드 audit2/fix3-brain.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CSS = ROOT / "static/css/contexts/brain/ds"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")

FAKE_DOM = r"""
function el(tag, o) {
  o = o || {};
  const n = { tag, attrs: Object.assign({}, o.attrs || {}), children: (o.children || []).filter(Boolean), text: o.text,
              classes: new Set(String(o.cls || '').split(' ').filter(Boolean)), clientWidth: 0, scrollWidth: 0, isConnected: true,
              setAttribute(k, v) { this.attrs[k] = v; }, get firstChild() { return this.children[0]; } };
  n.classList = { add: (c) => n.classes.add(c), remove: (c) => n.classes.delete(c), contains: (c) => n.classes.has(c) };
  return n;
}
let ro = null;
global.ResizeObserver = class { constructor(cb) { this.cb = cb; this.seen = []; ro = this; } observe(t) { this.seen.push(t); } unobserve() {} };
global.document = { querySelectorAll: () => [] };
global.window = { FOMS_BRAIN_DOM: { el }, FOMS_DS_ONTO_VIEW: {}, addEventListener() {} };
"""


def _run(body: str):
    script = FAKE_DOM + f"require({json.dumps(str(ROOT / 'static/js/brain/ds/ds-onto-kit.js'))});" + body
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60, check=True).stdout
    return json.loads(out)


@NODE
def test_onto_table_turns_into_cards_only_when_it_is_wider_than_its_box():
    got = _run(r"""
const kit = window.FOMS_DS_ONTO_KIT;
const row = el('tr', { children: [el('td', { text: '문 방식' }), el('td', { text: '목록' }), el('td', { text: '—' })] });
const box = kit.table(['칸', '자료형', '꼭'], [row]);
const t = box.firstChild;
const out = { labels: row.children.map((c) => c.attrs['data-label'] || null), observed: ro.seen[0] === box,
              cls: [...t.classes].sort(), box: [...box.classes].sort() };
const fire = (cw, sw) => { box.clientWidth = cw; box.scrollWidth = sw; ro.cb([{ target: box }]); return t.classList.contains('is-stacked'); };
out.narrow = fire(358, 765);   // 폰 390 — 7칸 표가 칸보다 넓다
out.wide = fire(832, 765);     // PC 1440 · 100%
out.hidden = fire(0, 0);       // 숨은 탭(폭 0)은 재지 않는다 — 그대로
out.again = fire(500, 765);    // 화면 크기 130%
process.stdout.write(JSON.stringify(out));
""")
    assert got["labels"] == [None, "자료형", "꼭"]  # 첫 칸은 카드 제목 — 이름표 없음
    assert got["observed"] is True and "fb-onto-table" in got["cls"] and "fb-onto-table-box" in got["box"]
    assert got["narrow"] is True and got["wide"] is False and got["hidden"] is False and got["again"] is True


def test_onto_cards_css_hides_head_row_for_eyes_only_and_shows_labels():
    css = (CSS / "brain-ds-onto.css").read_text(encoding="utf-8")
    assert ".fb-onto .fb-onto-table.is-stacked thead { position: absolute;" in css  # 머리 줄은 화면 읽기 프로그램에만
    assert "td[data-label]::before" in css and "content: attr(data-label)" in css
    assert "@container" not in css  # 칸 폭은 JS 가 잰다 — 옛 브라우저에서도 같다


def _fallback(css: str) -> str:
    hit = re.search(r"@supports not \(container-type: inline-size\) \{\s*@media \(max-width: 639\.98px\) \{(.*?)\n  \}\n\}", css, re.S)
    return hit.group(1) if hit else ""


def test_old_browsers_without_container_queries_get_the_narrow_phone_layout():
    agents = _fallback((CSS / "brain-ds-agents.css").read_text(encoding="utf-8"))
    assert ".fb-agents-duties thead { position: absolute;" in agents and ".fb-agents-duties tr { display: grid;" in agents
    assert ".fb-agents-duties .fb-agents-label { display: inline;" in agents  # 카드의 칸 이름표
    evals = _fallback((CSS / "brain-ds-agents-evals.css").read_text(encoding="utf-8"))
    assert ".fb-evals-row { grid-template-columns: minmax(0, 1fr) max-content;" in evals
    assert ".fb-evals-form { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }" in evals
