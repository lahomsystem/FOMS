"""도면 마법사 자재표 계산 칸 — 배치 안 A 화면 계약(가짜 DOM, node).

사용성 평가(2026-10-25) 큼-3·보통-3·보통-4·보통-7·작음 항목을 브라우저 없이 확인한다.
- 칸 맨 위 '계산 결과'(줄마다 계산 값 + 칩 한 줄, 6줄 넘으면 '더 보기'), 그 아래 스크롤 구역
  '모듈 N개 · 폭 합 · 남는 폭 [+ 모듈]'(펼침) · '제품·치수'(값이 차면 한 줄 요약으로 접힘) · '계산식 보기'(접힘) ·
  '규칙 N판 사용 중 [규칙 고치기]'(고칠 수 없는 사람은 [규칙 보기]).
- 화면 글은 짧게, 하는 일로(사용자 피드백 2026-10-27 '머리 글이 어색하다'): 배지 '참고용', 빈 모듈은 '모듈',
  모듈 합이 전체 폭을 넘으면 '넘는 폭 N', 입력 이름 '제품 종류'·'문 높이(비우면 자동)'·'옆벽 SR 왼쪽·오른쪽'.
- 규칙 창: mm 단위 · 표준 문 높이 한 줄 전체 · 바꾼 칸 '기본 35' · 저장 확인('규칙 2판 → 3판') · 뒤 단축키로 키가 새지 않음
  (초점이 창 밖 body 로 빠져도) · 창이 열린 채 Ctrl+S 는 도면을 저장하지 않고 안내만(실화면 QA 2026-10-25 V1).
- '더 보기'로 펼칠 때 포커스가 칸을 내리지 않고(preventScroll), 다시 그려도 보던 자리 그대로(실화면 QA V2).
- '옆벽 SR 에 나눠 넣기(80·80)'는 계산 입력만 채우고, [+ 모듈] 뒤 새 줄 폭 칸에 커서가 간다.
- 열어 보기만 해서는 시트 calc 가 생기지 않는다(그림자 판 데이터 모양은 그대로).
"""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [ROOT / f"static/js/drawing/{n}.js"
           for n in ("bom-calc", "bom-rules", "bom-rules-dialog", "bom-results", "bom-form", "bom-panel")]
RULES = {
    "door_gap_phoenix_pair": 34, "door_gap_phoenix_single": 30, "door_gap_other_pair": 8, "door_gap_other_single": 4,
    "door_std_heights": [1960, 2060, 2160, 2260, 2360], "door_ceiling_margin": 90, "nomold_cut": 45, "nomold_step": 5,
    "rod_cut": 35, "maida_w_cut": 5, "maida_h_cut": 15, "drawer_zone": 753, "sr_small_gap": 55, "sr_small_value": 60,
    "sr_minus": 30, "sr_step": 10, "sheet_len": 2440, "ep_plus_hinged": 10,
}
SAVE_NOTE = "규칙은 [규칙 저장] 단추로 저장합니다. 도면 저장(Ctrl+S)은 규칙 창을 닫은 뒤에 해 주세요."
SAVE_NOTE_VIEW = "규칙 창이 열려 있어 도면을 저장하지 않았습니다. 창을 닫은 뒤 Ctrl+S 를 눌러 주세요."

RUNNER = r"""
class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.childNodes = []; this.parentNode = null; this._text = '';
    this._attrs = {}; this._cls = []; this._on = {}; this.hidden = false; this.disabled = false; this.value = '';
    this.id = ''; this.title = ''; this.open = false;
    const self = this;
    this.style = { props: {}, setProperty(k, v) { this.props[k] = v; } };
    this.classList = {
      add: c => { if (!self._cls.includes(c)) { self._cls.push(c); } },
      remove: c => { self._cls = self._cls.filter(x => x !== c); },
      contains: c => self._cls.includes(c),
      toggle: (c, force) => { const on = force === undefined ? !self._cls.includes(c) : !!force; if (on) { self.classList.add(c); } else { self.classList.remove(c); } return on; },
    };
  }
  get className() { return this._cls.join(' '); }
  set className(v) { this._cls = String(v).split(/\s+/).filter(Boolean); }
  get firstChild() { return this.childNodes[0] || null; }
  get textContent() { return this._text + this.childNodes.map(c => c.textContent).join(''); }
  set textContent(v) { this.childNodes.forEach(c => { c.parentNode = null; }); this.childNodes = []; this._text = String(v); this.scrollTop = 0; }   // 비우면 스크롤도 맨 위(브라우저와 같게)
  get isConnected() { let n = this; while (n.parentNode) { n = n.parentNode; } return n === document.body; }
  appendChild(c) { return this.insertBefore(c, null); }
  insertBefore(c, ref) {
    if (c.parentNode) { c.parentNode.childNodes = c.parentNode.childNodes.filter(x => x !== c); }
    const i = ref ? this.childNodes.indexOf(ref) : -1;
    if (i < 0) { this.childNodes.push(c); } else { this.childNodes.splice(i, 0, c); }
    c.parentNode = this;
    return c;
  }
  setAttribute(k, v) { this._attrs[k] = String(v); if (k === 'open') { this.open = true; } }
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; }
  removeAttribute(k) { delete this._attrs[k]; if (k === 'open') { this.open = false; } }
  addEventListener(t, fn) { (this._on[t] = this._on[t] || []).push(fn); }
  fire(t, extra) {
    const ev = Object.assign({ type: t, target: this, stopped: false, prevented: false,
      preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } }, extra || {});
    (this._on[t] || []).forEach(fn => fn(ev));
    return ev;
  }
  focus(o) { document.activeElement = this; this.focusOpts = o || null; }
  contains(n) { while (n) { if (n === this) { return true; } n = n.parentNode; } return false; }
  scrollIntoView() { this.scrolled = (this.scrolled || 0) + 1; }
  select() {}
  setPointerCapture() {}
  showModal() { this.open = true; }
  close() { this.open = false; this.fire('close'); }
}
const all = (root, ok, acc = []) => { root.childNodes.forEach(c => { if (ok(c)) { acc.push(c); } all(c, ok, acc); }); return acc; };
const one = (root, ok) => all(root, ok)[0] || null;
const cls = name => e => e.classList.contains(name);
const button = text => e => e.tagName === 'BUTTON' && e.textContent === text;
const tick = () => new Promise(r => setTimeout(r, 0));
global.window = global;
global.document = { body: new El('body'), activeElement: null, createElement: t => new El(t),
  getElementById(id) { return one(this.body, e => e.id === id); } };
document.activeElement = document.body;
// window 잡는 단계 keydown(규칙 창이 초점이 창 밖으로 빠진 키를 막는 자리) — winKey 는 body 에서 누른 키
const winOn = [];
global.addEventListener = (type, fn, capture) => { winOn.push({ type, fn, capture: !!capture }); };
const winKey = extra => {
  const ev = Object.assign({ type: 'keydown', target: document.body, stopped: false, prevented: false,
    preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } }, extra || {});
  winOn.filter(l => l.type === 'keydown' && l.capture).forEach(l => l.fn(ev));
  return ev;
};
global.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
const job = JSON.parse(process.argv[process.argv.length - 1]);
const confirms = [], calls = [], toasts = [], opens = [];
global.confirm = msg => { confirms.push(msg); return true; };
global.fetch = (url, opts) => {
  const post = !!(opts && opts.method === 'POST');
  const sent = post ? JSON.parse(opts.body) : null;
  calls.push({ url, post, sent });
  const data = post ? { rules: Object.assign({}, job.rules, sent.rules), label: 's3', version: 3, defaults: job.rules,
      changed_at: '2026-10-25 15:10', changed_by: '저장한 사람' }
    : { rules: job.rules, label: job.label, version: job.version, defaults: job.rules, can_edit: job.can_edit,
      changed_at: job.changed_at || null, changed_by: job.changed_by || null };
  return Promise.resolve({ status: 200, json: () => Promise.resolve({ success: true, data, error: null }) });
};
process.argv.slice(1, -1).forEach(f => require(f));   // node -e 는 argv[1] 부터 인자

(async () => {
  const host = document.body.appendChild(new El('aside'));
  host.hidden = true;
  const appBtn = document.body.appendChild(new El('button'));
  const sheet = job.sheet;
  let changes = 0;
  const out = {};
  out.ok = window.FomsBomPanel.init({ host, button: appBtn, getSheet: () => sheet, getProduct: () => job.product,
    canSave: () => job.can_save, onChange: () => { changes += 1; }, toast: m => toasts.push(m), onOpenChange: o => opens.push(o) });
  appBtn.fire('click');
  out.loading = host.textContent.includes('계산 규칙을 불러오는 중입니다');
  await tick(); await tick();
  const [head, note, top, body, grip] = host.childNodes;
  out.head = head.textContent;
  const badge = one(head, cls('dws-calc-badge'));
  out.badge = { text: badge.textContent, title: badge.title };
  out.noteHidden = note.hidden;
  one(head, cls('dws-calc-info')).fire('click');
  out.noteShown = !note.hidden;
  out.calcCreated = !!sheet.calc;
  out.top = top.textContent;
  out.topRows = all(top, cls('dws-calc-res')).map(r => r.textContent);
  out.score = (one(top, cls('dws-calc-score')) || { textContent: null }).textContent;
  const more = one(top, cls('dws-calc-more'));
  out.more = more && more.textContent;
  if (more) {
    more.fire('click');
    out.moreRows = all(top, cls('dws-calc-res')).length;
    const fold = one(top, cls('dws-calc-more'));
    out.moreAfter = fold.textContent;
    // 펼칠 때 '접기'로 옮기는 포커스가 칸을 내리지 않는다(1366×657 에서 제목·요약 칩이 숨었다 — 실화면 QA V2)
    out.expanded = { focused: document.activeElement === fold, preventScroll: !!(fold.focusOpts && fold.focusOpts.preventScroll),
      scrollTop: top.scrollTop };
    top.scrollTop = 40;   // 펼친 칸을 사람이 내려 둔 자리 — 시트가 바뀌어 다시 그려도 그대로
    window.FomsBomPanel.sync();
    out.keptScroll = top.scrollTop;
    top.scrollTop = 114;   // 펼친 채 칸을 내려 둔 자리(1366 실화면 QA) — 접으면 맨 위로 돌아와야 한다
    one(top, cls('dws-calc-more')).fire('click');
    const again = one(top, cls('dws-calc-more'));
    out.collapsed = { rows: all(top, cls('dws-calc-res')).length, scrollTop: top.scrollTop, label: again.textContent,
      focused: document.activeElement === again };
  }
  out.folds = all(body, cls('dws-calc-fold-label')).map(e => e.textContent);
  out.foldOpen = all(body, cls('dws-calc-fold-body')).map(e => !e.hidden);
  out.why = one(body, e => e.id === 'dws-calc-fold-why').textContent;
  out.modsBody = one(body, e => e.id === 'dws-calc-fold-mods').textContent;
  const split = one(body, cls('dws-calc-split'));
  out.split = split && !split.hidden ? split.textContent : null;
  out.addBtn = !!one(body, button('+ 모듈'));
  out.disabledInputs = all(body, e => e.tagName === 'INPUT' && e.disabled).length;
  out.rulesRow = one(body, cls('dws-calc-rules-row')).textContent;
  // 규칙 줄 단추는 고칠 수 있는지에 따라 글이 달라서 글이 아니라 자리(규칙 줄 안 단추)로 찾는다
  const rulesBtn = () => one(one(host, cls('dws-calc-rules-row')), e => e.tagName === 'BUTTON');
  out.rulesBtn = { text: rulesBtn().textContent, title: rulesBtn().title };
  // 제품·치수 입력 이름 [안내 글] — 숨은 칸(무몰딩 문 높이)은 빼고
  out.fields = all(body, cls('dws-calc-field')).filter(f => !f.hidden).map(f => {
    const box = one(f, e => e.tagName === 'INPUT');
    return one(f, cls('dws-calc-field-name')).textContent + (box ? ' [' + box.placeholder + ']' : '');
  });
  out.rest = one(body, cls('dws-calc-sum')).textContent;
  out.width = host.style.props['--dws-calc-w'];
  if (out.split) {
    split.fire('click');
    out.afterSplit = { sr: [sheet.calc.in.sr_l, sheet.calc.in.sr_r], mods: one(host, cls('dws-calc-fold-label')).textContent,
      hidden: one(host, cls('dws-calc-split')).hidden, out: sheet.calc.out, mode: sheet.calc.mode, changed: changes > 0 };
  }
  if (out.addBtn) {
    one(host, button('+ 모듈')).fire('click');
    const widths = all(host, e => e.tagName === 'INPUT' && / 모듈 폭$/.test(e.getAttribute('aria-label') || ''));
    const last = widths[widths.length - 1];
    out.added = { count: sheet.calc.in.mods.length, focused: document.activeElement === last, label: last.getAttribute('aria-label'),
      value: last.value, visible: (last.scrolled || 0) > 0 };
  }
  const openBtn = rulesBtn();
  openBtn.focus();
  openBtn.fire('click');
  const dlg = document.getElementById('dws-calc-rules-dialog');
  out.dialog = { open: dlg.open, title: one(dlg, e => e.tagName === 'H2').textContent, mm: all(dlg, cls('dws-calc-unit')).length,
    fields: all(dlg, cls('dws-calc-rule')).length, wide: all(dlg, cls('dws-calc-rule-wide')).map(e => e.textContent),
    save: !!one(dlg, button('규칙 저장')), hint: dlg.textContent.includes('도면팀·관리자만 고칠 수 있습니다'),
    meta: (one(dlg, cls('dws-calc-rules-meta')) || { textContent: null }).textContent,
    intro: !!one(dlg, cls('dws-calc-rules-intro')) };
  out.keyStopped = dlg.fire('keydown', { key: 'Delete' }).stopped;
  // 창 안 Ctrl+S — 도면 저장(문서 keydown)까지 가지 않고 안내만
  out.saveKey = (ev => ({ stopped: ev.stopped, prevented: ev.prevented }))(dlg.fire('keydown', { key: 's', ctrlKey: true }));
  // 초점이 창 밖(body)으로 빠진 채 누른 키 — Ctrl+Z·T 는 뒤 그림에 닿지 않고, Ctrl+S(한글 자판 'ㄴ' 포함)는 막고 안내,
  // 창 안의 키는 창의 keydown 몫으로 둔다(입력 칸 글자·되돌리기는 그대로)
  out.outside = { undo: winKey({ key: 'z', ctrlKey: true }).stopped, tool: winKey({ key: 't' }).stopped,
    save: (ev => ev.stopped && ev.prevented)(winKey({ key: 's', ctrlKey: true })),
    hangulSave: (ev => ev.stopped && ev.prevented)(winKey({ key: 'ㄴ', code: 'KeyS', ctrlKey: true, repeat: true })),
    inside: winKey({ key: 'z', ctrlKey: true, target: one(dlg, e => e.tagName === 'INPUT') }).stopped };
  out.saveNotes = toasts.filter(t => t.indexOf('Ctrl+S') >= 0);   // 꾹 누름 반복은 안내를 더 띄우지 않는다
  if (out.dialog.save) {
    const rod = all(dlg, cls('dws-calc-rule')).find(l => l.textContent.startsWith('옷봉 · 모듈에서 빼기'));
    const base = one(rod, cls('dws-calc-rule-base'));
    out.rodBefore = { changed: rod.classList.contains('dws-calc-changed'), baseHidden: base.hidden };
    const box = one(rod, e => e.tagName === 'INPUT');
    box.value = '40';
    box.fire('input');
    out.rodAfter = { changed: rod.classList.contains('dws-calc-changed'), base: base.textContent, baseHidden: base.hidden };
    one(dlg, button('규칙 저장')).fire('click');
    await tick(); await tick();
    out.confirms = confirms.slice();
    out.posted = calls.filter(c => c.post).map(c => c.sent);
    out.dialogClosed = !dlg.open;
    out.rulesRowAfter = one(host, cls('dws-calc-rules-row')).textContent;
    const ae = document.activeElement;
    out.focusBack = !!(ae && ae === rulesBtn() && ae.isConnected);
    rulesBtn().fire('click');   // 저장 응답의 '마지막 고침'으로 바뀌었나
    out.metaAfterSave = (one(dlg, cls('dws-calc-rules-meta')) || { textContent: null }).textContent;
    one(dlg, button('닫기')).fire('click');
  } else {
    one(dlg, button('닫기')).fire('click');
    out.dialogClosed = !dlg.open;
  }
  out.toasts = toasts.slice();
  out.outsideAfterClose = winKey({ key: 'z', ctrlKey: true }).stopped;   // 창을 닫으면 뒤 단축키가 다시 먹는다
  out.windowGuards = winOn.filter(l => l.type === 'keydown' && l.capture).length;   // 창을 두 번 열어도 하나
  grip.fire('keydown', { key: 'ArrowLeft' });
  out.widthAfterKey = host.style.props['--dws-calc-w'];
  one(head, cls('dws-calc-close')).fire('click');
  out.opens = opens.slice();
  out.hiddenAfterClose = host.hidden;
  out.calcAfter = sheet.calc ? Object.keys(sheet.calc).sort() : null;
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""

S11 = {"line": "mold", "handle": "phoenix", "nomold": "ceiling", "W": 3660, "D": 570, "H": 2300, "zone": 753,
       "door_h": 0, "ep": 0, "sr_l": 0, "sr_r": 0,
       "mods": [{"w": 1000, "doors": 2, "drawers": 3, "rods": 1}, {"w": 1000, "doors": 2, "drawers": 0, "rods": 2},
                {"w": 1000, "doors": 2, "drawers": 0, "rods": 2}, {"w": 500, "doors": 1, "drawers": 0, "rods": 2}]}


def _run(job):
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, "-e", RUNNER, *map(str, SCRIPTS), json.dumps(job)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_layout_a_editor_flow():
    """도면팀이 입력한 시트: 결과가 맨 위, 접힌 제품·치수 요약, 옆벽 SR 나눔, 새 모듈 커서, 규칙 창 저장 확인."""
    sheet = {"id": "s-1", "calc": {"in": json.loads(json.dumps(S11)), "mode": "shadow"},
             "objects": [{"type": "text", "text": "[SR]\n110*2440=3"},
                         {"type": "text", "text": "[DOOR]\n483*2060=4\nㄴ피닉스바 2EA\n483*1407=2"},
                         {"type": "text", "text": "[옷봉]"}]}
    got = _run({"rules": RULES, "label": "s2", "version": 2, "can_edit": True, "can_save": True,
                "changed_at": "2026-10-24 09:30", "changed_by": "도면팀장",
                "product": {"name": "몰딩 여닫이장", "spec": "3660×570×2300"}, "sheet": sheet})
    assert got["ok"] is True and got["loading"] is True
    # 머리 줄: 제목 · ⓘ · 배지 '참고용'(예전 '시험 계산' — 시험인지 무엇인지 몰랐다, 사용자 피드백 2026-10-27) · 닫기
    assert got["head"] == "자재표 계산ⓘ참고용✕" and "그림자" not in got["head"]
    assert got["badge"] == {"text": "참고용", "title": "계산만 보여 주고 시트에는 넣지 않습니다"}
    assert got["noteHidden"] is True and got["noteShown"] is True          # 안내 글은 ⓘ 로 펼친다
    # 계산 결과 — 계산 값과 칩이 한 줄, 높이만 다른 줄은 한 줄로 묶임
    assert got["top"].startswith("계산 결과") and "맞춰 보기" not in got["top"]
    # 다름 5 = SR 수량 · 문 높이 · 빠진 문 470 과 그 피닉스바 · 1407 문 밑 피닉스바 줄 없음, 아직 안 침 3 = 옷봉 2 · 마이다 1
    assert got["score"] == "10줄 중 2줄 같음 · 다름 5 · 아직 안 침 3"
    # 차이는 여유·짧음처럼 시트 − 계산(시트 2060 이 계산 2160 보다 낮으면 −, 실화면 QA V2)
    assert got["topRows"][:3] == ["SR110*2440=2수량 다름(시트 3)", "DOOR483*2160=4높이 -100(시트 2060)", "ㄴ피닉스바 2EA같음"]
    assert len(got["topRows"]) == 6 and got["more"] == "더 보기(4줄 · 다름 1)"   # 접힌 줄에 다른 줄이 있으면 알린다
    assert got["moreRows"] == 10 and got["moreAfter"] == "접기"
    # 펼치면 '접기'에 포커스를 주되 칸은 내리지 않고(제목·요약 칩이 머리 줄 밑에 숨지 않게), 다시 그려도 보던 자리 그대로
    assert got["expanded"] == {"focused": True, "preventScroll": True, "scrollTop": 0}
    assert got["keptScroll"] == 40
    # 접으면 칸 스크롤이 맨 위로 — 제목·요약 칩이 다시 보이고, 다시 그린 '더 보기'에 포커스(실화면 QA 2026-10-25)
    assert got["collapsed"] == {"rows": 6, "scrollTop": 0, "label": "더 보기(4줄 · 다름 1)", "focused": True}
    # 스크롤 구역: 모듈(펼침) · 제품·치수(값이 차서 한 줄 요약으로 접힘) · 계산식(접힘)
    assert got["folds"] == ["모듈 4개 · 폭 합 3500 · 남는 폭 160", "제품·치수: 몰딩 여닫이 · 피닉스바 · 3660×570×2300", "계산식 보기"]
    assert got["foldOpen"] == [True, False, False]
    assert got["rest"] == "남는 폭 160 은 옆벽 SR 로 채울 폭입니다."
    assert "(1000 − 쌍문 틈 34) ÷ 2 내림" in got["why"]                     # 계산식 숫자에 규칙 이름
    # 입력 이름은 하는 일 그대로 — '제품 계열'·'문 높이 직접(비우면 계산)'·'옆벽 SR 좌/우' 를 고쳤다
    assert got["fields"] == ["제품 종류", "손잡이", "전체 폭 [mm]", "깊이 [mm]", "천장 높이 [mm]", "서랍 칸 높이 [753]",
                             "문 높이 [비우면 자동]", "드러난 옆면(EP)", "옆벽 SR 왼쪽 [없으면 비움]", "옆벽 SR 오른쪽 [없으면 비움]"]
    # 규칙 줄: 쓰는 규칙 + 고칠 수 있는 사람에게는 [규칙 고치기](예전 '· 도면팀·관리자만 고침 [규칙 창 열기]')
    assert got["rulesRow"] == "규칙 2판 사용 중규칙 고치기"
    assert got["rulesBtn"] == {"text": "규칙 고치기", "title": "고친 숫자는 도면팀 전체 계산에 바로 적용됩니다"}
    assert got["width"] == "340px"                                         # 기억 못 하는 브라우저는 340
    # 옆벽 SR 에 나눠 넣기 — 계산 입력만 채운다(시트 글자는 그대로, 그림자 판 유지)
    assert got["split"] == "옆벽 SR 에 나눠 넣기(80·80)"
    split = got["afterSplit"]
    assert split["sr"] == [80, 80] and split["hidden"] is True and split["changed"] is True
    assert split["mods"] == "모듈 4개 · 폭 합 3500 · 남는 폭 0" and split["mode"] == "shadow"
    assert "80*2440=2" in split["out"].split("\n")
    # [+ 모듈] 뒤 새 줄 폭 칸에 커서(앞 모듈 폭을 이어 받음) — 위 결과 칸이 자라도 그 칸이 보이게 스크롤
    assert got["added"] == {"count": 5, "focused": True, "label": "5번 모듈 폭", "value": "500", "visible": True}
    # 규칙 창
    dialog = got["dialog"]
    assert dialog["open"] is True and dialog["title"] == "계산 규칙 숫자 · 규칙 2판"
    assert dialog["meta"] == "마지막 고침: 도면팀장 · 2026-10-24 09:30" and dialog["intro"] is True   # 보통-4
    assert dialog["fields"] == 18 and dialog["mm"] == 18 and dialog["save"] is True
    assert dialog["wide"] == ["표준 문 높이(쉼표로 나눔)mm기본 1960, 2060, 2160, 2260, 2360"]   # 한 줄 전체 폭 칸(값은 입력 칸 안)
    assert got["keyStopped"] is True                                       # 뒤 캔버스 단축키로 새지 않음
    # 창이 열린 채 Ctrl+S — 도면을 저장하지 않고(초점이 창 밖으로 빠지지 않게) '[규칙 저장] 단추로' 안내(실화면 QA V1)
    assert got["saveKey"] == {"stopped": True, "prevented": True}
    assert got["outside"] == {"undo": True, "tool": True, "save": True, "hangulSave": True, "inside": False}
    assert got["saveNotes"] == [SAVE_NOTE, SAVE_NOTE]
    assert got["outsideAfterClose"] is False and got["windowGuards"] == 1
    assert got["rodBefore"] == {"changed": False, "baseHidden": True}
    assert got["rodAfter"] == {"changed": True, "base": "기본 35", "baseHidden": False}
    assert got["confirms"] == ["도면팀 전체 계산에 바로 적용됩니다(규칙 2판 → 3판). 저장할까요?"]
    assert len(got["posted"]) == 1 and got["posted"][0]["rules"]["rod_cut"] == 40 and got["posted"][0]["settings_version"] == 2
    assert got["dialogClosed"] is True and got["rulesRowAfter"] == "규칙 3판 사용 중규칙 고치기"
    assert "계산 규칙을 저장했습니다(규칙 3판)." in got["toasts"]
    assert got["focusBack"] is True                                        # 다시 그려진 [규칙 고치기]로 포커스
    assert got["metaAfterSave"] == "마지막 고침: 저장한 사람 · 2026-10-25 15:10"   # 저장 응답으로 바로 바뀜
    assert got["widthAfterKey"] == "350px"
    assert got["opens"] == [True, False] and got["hiddenAfterClose"] is True
    assert got["calcAfter"] == ["in", "mode", "out", "rules"]               # 데이터 모양 그대로


def test_layout_a_sheet_without_typed_bom_marks_rows_grey():
    """시트에 자재표를 아직 하나도 안 쳤으면 빨강 없이 줄마다 회색 '아직 안 침', 요약 칩도 회색 안내."""
    sheet = {"id": "s-2", "calc": {"in": json.loads(json.dumps(S11)), "mode": "shadow"}, "objects": []}
    got = _run({"rules": RULES, "label": "d1", "version": 0, "can_edit": True, "can_save": True,
                "product": None, "sheet": sheet})
    assert got["score"] == "계산 10줄 · 시트에 아직 안 침"
    assert got["topRows"][:2] == ["SR110*2440=2아직 안 침", "DOOR483*2160=4아직 안 침"]
    assert got["more"] == "더 보기(4줄)" and "머리글 아래에 줄을 치면 줄마다 맞춰 봅니다" in got["top"]
    assert got["collapsed"]["label"] == "더 보기(4줄)" and got["collapsed"]["scrollTop"] == 0
    assert got["confirms"] == ["도면팀 전체 계산에 바로 적용됩니다(기본 규칙 → 규칙 1판). 저장할까요?"]


def test_layout_a_view_only_fresh_sheet():
    """보기만 하는 사람·새 시트: 열어도 calc 가 생기지 않고, 제품·치수 칸은 펼쳐 있고, 규칙 창은 보기만."""
    sheet = {"id": "s-9", "objects": []}
    got = _run({"rules": RULES, "label": "d1", "version": 0, "can_edit": False, "can_save": False,
                "product": None, "sheet": sheet})
    assert got["calcCreated"] is False and got["calcAfter"] is None
    assert got["top"] == "계산 결과아래에 치수와 모듈을 넣으면 계산이 나옵니다."
    assert got["score"] is None and got["more"] is None
    # 빈 모듈 묶음은 '모듈 0개 · 합 0' 대신 '모듈' 한 낱말(스크린샷 2026-10-27)
    assert got["folds"] == ["모듈", "제품·치수", "계산식 보기"]
    assert got["why"] == "계산이 나오면 줄마다 계산식을 보여 줍니다."
    assert got["rest"] == "전체 폭을 넣으면 남는 폭을 알려 줍니다."
    assert "모듈이 없습니다." in got["modsBody"]                              # 빈 표 머리 대신 한 줄 안내
    assert got["foldOpen"] == [True, True, False]                          # 폭·깊이·높이가 비어 제품·치수를 펼친다
    assert got["split"] is None and got["addBtn"] is False and got["disabledInputs"] == 7   # 제품·치수 숫자 칸 7개
    # 고칠 수 없는 사람에게는 [규칙 보기] — 누가 고치는지는 단추 풀이와 규칙 창 안내가 말한다
    assert got["rulesRow"] == "기본 규칙 사용 중규칙 보기"
    assert got["rulesBtn"] == {"text": "규칙 보기", "title": "규칙은 도면팀·관리자만 고칠 수 있습니다"}
    dialog = got["dialog"]
    assert dialog["title"] == "계산 규칙 숫자 · 기본 규칙" and dialog["save"] is False and dialog["hint"] is True
    assert dialog["meta"] is None                                          # 아직 아무도 안 고쳤으면 줄이 없다
    assert got["dialogClosed"] is True
    assert got["saveNotes"] == [SAVE_NOTE_VIEW, SAVE_NOTE_VIEW]            # [규칙 저장]이 없는 사람에게는 창 닫고 저장하라고만
    assert got["outside"]["undo"] is True and got["outsideAfterClose"] is False
    assert got["opens"] == [True, False]


def test_module_title_says_over_width_and_stays_quiet_without_modules():
    """모듈 합이 전체 폭을 넘으면 '남는 폭 -500' 대신 '넘는 폭 500'. 모듈이 아직 없으면 제목은 '모듈'뿐이고,
    전체 폭을 통째로 '옆벽 SR 로 채울 폭'이라 하거나 SR 나눔(300·300)을 권하지 않는다(사용자 피드백 2026-10-27)."""
    over = json.loads(json.dumps(S11))
    over["W"] = 3000                                                       # 모듈 합 3500 > 전체 폭 3000
    got = _run({"rules": RULES, "label": "s2", "version": 2, "can_edit": True, "can_save": True,
                "product": None, "sheet": {"id": "s-over", "calc": {"in": over, "mode": "shadow"}, "objects": []}})
    assert got["folds"][0] == "모듈 4개 · 폭 합 3500 · 넘는 폭 500"
    assert got["rest"] == "모듈 폭 합이 전체 폭보다 500 큽니다." and got["split"] is None
    empty = dict(json.loads(json.dumps(S11)), W=600, mods=[])               # 폭은 있고 모듈은 아직 없음
    got = _run({"rules": RULES, "label": "d1", "version": 0, "can_edit": False, "can_save": True,
                "product": None, "sheet": {"id": "s-empty", "calc": {"in": empty, "mode": "shadow"}, "objects": []}})
    assert got["folds"][0] == "모듈" and got["addBtn"] is True
    assert got["rest"] == "" and got["split"] is None
    assert "아직 모듈이 없습니다. [+ 모듈]로 한 줄씩 더하세요." in got["modsBody"]


def test_calc_panel_word_scripts_are_repinned():
    """글을 바꾼 세 파일은 ?v= 를 올려 브라우저가 옛 글(시험 계산·결과 · 맞춰 보기)을 들고 있지 않게 한다."""
    html = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
    for name in ("bom-results", "bom-form", "bom-panel"):
        assert "js/drawing/" + name + ".js') }}?v=20261027d" in html, name
