"""승인 대기 카드의 기계 말 숨기기 · 고르기 값 이름표(node — 점검 F02 · F03 · 일꾼 C).

- ``brain-review-view.js`` valueText: 고르기 값은 서버 표시 표(``display.choices`` = schemas.CHOICE_LABELS)의 한글 이름표 —
  값 하나 · 목록 · 확인 칸처럼 ' · ' 로 이은 글 모두. 이름표 없는 칸 · 모르는 값은 그대로(대조군).
- ``brain-inbox-card.js``: 근거 목록에서 기계 근거(customer · case · plan · brain_questions · photo_relearn · 지식 문서 판 …)는
  안 보이고 사람이 쓴 근거 · 바깥 주소는 남는다. 확인 칸 글 · 고쳐서 승인 고르기 칸 글은 이름표, 보내는 값은 그대로.
가짜 DOM(요소 = 글 · 속성 · 자식만)으로 실제 카드 그리기를 한 번 돌린다. 합성 값만.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.brain.display import display_table

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "static/js/brain/brain-review-view.js"
CARD = ROOT / "static/js/brain/brain-inbox-card.js"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")

RUN_CARD = r"""
const vm = require('vm');
const fs = require('fs');
const [reviewPath, cardPath, raw] = process.argv.slice(1);
const data = JSON.parse(raw);
function node(tag) {
  return { tag: tag, cls: '', text: '', attrs: {}, children: [], hidden: false, value: '',
           appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; } };
}
function el(tag, o) {
  const n = node(tag);
  o = o || {};
  if (o.cls) n.cls = o.cls;
  if (o.text !== undefined && o.text !== null) n.text = String(o.text);
  Object.keys(o.attrs || {}).forEach(k => { const v = o.attrs[k]; if (v !== undefined && v !== null && v !== false) n.attrs[k] = String(v); });
  (o.children || []).forEach(c => { if (c) n.children.push(c); });
  return n;
}
const window = { performance: { now: () => 0 },
                 FOMS_BRAIN_DOM: { el: el, typeChip: () => el('span') }, FOMS_BRAIN_VIEW: { itemHref: () => '/x' } };
const context = vm.createContext({ window: window, console: console });
vm.runInContext(fs.readFileSync(reviewPath, 'utf8'), context);
vm.runInContext(fs.readFileSync(cardPath, 'utf8'), context);
const li = window.FOMS_BRAIN_INBOX_CARD.build(data.card, data.ctx, false);
const all = [];
(function walk(n) { all.push(n); n.children.forEach(walk); })(li);
const refs = all.filter(n => n.cls === 'brain-prop__ref').map(n => n.text);
const confirm = all.filter(n => n.cls === 'brain-prop__confirm').map(n => n.children[1].text);
const select = all.filter(n => n.tag === 'select' && n.attrs['data-brain-edit'] === 'payload.basis')[0];
const options = select.children.map(o => [o.attrs.value === undefined ? '' : o.attrs.value, o.text]);
const cells = all.filter(n => n.cls === 'brain-diff__after').map(n => n.text);
process.stdout.write(JSON.stringify({ refs: refs, confirm: confirm, options: options, cells: cells,
                                      texts: all.map(n => n.text).filter(Boolean) }));
"""


def _review(expr: str, data: object = None):
    script = (f"const r = require({json.dumps(str(REVIEW))});"
              f"const data = {json.dumps(data, ensure_ascii=False)};"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         check=True).stdout
    return json.loads(out)


@NODE
def test_value_text_uses_choice_labels_for_single_list_and_joined_values():
    d = display_table()
    got = _review("[r.valueText('payload.basis', 'calc', data),"
                  " r.valueText('payload.door_kinds', ['hinged', 'sliding'], data),"
                  " r.valueText('payload.door_kinds', 'hinged · folding', data),"
                  " r.valueText('payload.erp_stage', 'RECEIVED', data),"
                  " r.valueText('payload.basis', '새값', data), r.valueText('payload.unit', 'mm', data),"
                  " r.valueText('name', 'calc', data), r.valueText('status', 'active', data),"
                  " r.diffRows([{field: 'payload.stage', label: '값 단계', before: 'base', after: 'discount'}], data)]", d)
    assert got[:4] == ["견적 계산기 값", "여닫이 · 슬라이딩", "여닫이 · 폴딩", "주문접수"]
    assert got[4:8] == ["새값", "mm", "calc", "사용 중"]  # 대조군: 모르는 값 · 이름표 없는 칸 · 다른 칸
    assert (got[8][0]["before"], got[8][0]["after"]) == ("기본 금액", "할인")


def _card():
    evidence = ["customer:0a1b2c3d4e", "case:12", "plan:synth#1", "brain_questions:3", "photo_relearn:9",
                "about:common/x", "person:4", "cs_agent_knowledge_lahom@v3", "사람이 적은 근거", "https://example.com/a"]
    main = {"id": 1, "op": "update", "grade": "B", "ai": True, "base_version": 1, "base": {"changed": False, "current": 1},
            "fields": [{"field": "payload.basis", "label": "근거 종류", "before": None, "after": "calc", "editable": True,
                        "datatype": "enum", "choices": ["calc", "brain", "derived", "setting"]}],
            "edit_extra": [], "photos": [], "evidence": evidence, "confirm": {"field": "payload.basis", "value": "calc"},
            "gates": [], "proposer": "AI(사진 다시 배우기)", "created_at": "2026-11-08 10:00", "reason": "합성 까닭",
            "phone_ok": False, "bulk_ok": False, "rollback_of": None, "meaning": "", "link": None}
    return {"id": "c1", "key": "common/x", "type": "price_rule", "exists": True, "title": "합성 운임", "name": "x",
            "bin": "decide", "main": main, "attached": [], "similar": None, "touches": None}


@NODE
def test_inbox_card_hides_machine_evidence_and_shows_choice_labels():
    ctx = {"display": display_table(), "itemBase": "/brain/items/",
           "actions": [{"name": "apply", "label": "승인", "params": []},
                       {"name": "edit_apply", "label": "고쳐서 승인", "params": []},
                       {"name": "reject", "label": "거절", "params": [{"name": "code", "choices": []}]}]}
    out = subprocess.run(["node", "-e", RUN_CARD, str(REVIEW), str(CARD),
                          json.dumps({"card": _card(), "ctx": ctx}, ensure_ascii=False)],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    got = json.loads(out.stdout)
    assert got["refs"] == ["사람이 적은 근거", "https://example.com/a"]  # 대조군: 사람 글 · 바깥 주소는 남는다
    assert got["confirm"] == ["근거 종류 확인했어요: 견적 계산기 값"]
    assert got["options"] == [["", "(없음)"], ["calc", "견적 계산기 값"], ["brain", "회사 지식에 적은 값"],
                              ["derived", "두 값의 차이"], ["setting", "설정 값"]]  # 값은 그대로 · 글만 이름표
    assert got["cells"] == ["견적 계산기 값"]
    joined = " ".join(got["texts"])
    assert "customer:" not in joined and "photo_relearn" not in joined and ": calc" not in joined
