/**
 * 도면 마법사 — 자재표 계산 칸(오른쪽에 여닫는 칸, 그림자 판).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.6
 * - 시트마다 전체 폭·깊이·천장 높이·제품 계열·손잡이·모듈 목록을 받아 [SR][EP][DOOR][옷봉][마이다]
 *   줄을 계산해 보여 주고, 시트에 사람이 친 자재표와 줄마다 맞춰 본다.
 * - 그림자 판: 도면팀이 규칙을 확인하기 전에는 시트에 넣지도, 복사하게 하지도 않는다.
 *   사람이 따로 친 자재표와 계산을 맞춰 본 기록(시트 calc)이 규칙을 검증하는 자료이기 때문이다.
 * - 입력을 처음 바꿀 때 시트에 calc 를 만든다(열어 보기만 해서는 시트가 바뀌지 않는다).
 *
 * window.FomsBomPanel = { init(opts), sync(), toggle() }
 *   opts: { host, button, getSheet(), getProduct(sheet), canSave(), onChange(), toast(msg) }
 */
(function () {
  'use strict';
  if (window.FomsBomPanel) { return; }

  var NOTE = '계산만 보여 줍니다. 자재표는 지금처럼 직접 쳐 주세요. 둘을 맞춰 본 기록으로 계산 규칙을 고치고, ' +
    '도면팀이 규칙을 확인하면 시트에 넣는 단추를 엽니다.';
  var HANDLE_NAMES = { phoenix: '피닉스바', other: '그 밖(푸쉬 등)' };
  var NOMOLD_NAMES = { ceiling: '천장까지(천장 − 45)', std: '표준 문(2160 등)' };
  var MOD_COLS = [['w', '폭'], ['doors', '문 짝', [0, 1, 2]], ['drawers', '서랍', [0, 1, 2, 3, 4]], ['rods', '옷봉', [0, 1, 2]]];
  var KIND_NAMES = { ok: '같음', warn: '여유', bad: '다름', extra: '시트에만' };
  var C = null, R = null, ctx = null, info = null, loading = null, isOpen = false;
  var els = {}, inp = null, lastSheetId = null, lastCalc;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = text; }
    return e;
  }
  function section(title) {
    var s = el('section', 'dws-calc-sec');
    s.appendChild(el('h3', 'dws-calc-sec-title', title));
    els.body.appendChild(s);
    return s;
  }
  function editable() { return !!(ctx && ctx.canSave()); }

  /** 입력 한 칸이 바뀜 — 처음이면 시트에 calc 를 붙이고, 다시 계산하고, 저장할 것으로 표시한다. */
  function edit(key, value) {
    var s = ctx.getSheet();
    if (!s || !editable()) { return; }
    inp[key] = value;
    if (!s.calc || s.calc.in !== inp) { s.calc = { in: inp, mode: 'shadow' }; }
    lastCalc = s.calc;
    refresh();
    ctx.onChange();
  }
  function intOf(v) { var n = Math.round(Number(v)); return isFinite(n) && n > 0 ? n : 0; }

  function choice(host, label, key, names, numeric) {
    var wrap = el('label', 'dws-calc-field');
    wrap.appendChild(el('span', null, label));
    var sel = el('select');
    Object.keys(names).forEach(function (k) { var o = el('option', null, names[k]); o.value = k; sel.appendChild(o); });
    sel.value = String(inp[key]);
    sel.disabled = !editable();
    sel.addEventListener('change', function () { edit(key, numeric ? intOf(sel.value) : sel.value); syncVisibility(); });
    wrap.appendChild(sel);
    host.appendChild(wrap);
    return wrap;
  }
  function numBox(value) {
    var box = el('input');
    box.type = 'number'; box.min = '0'; box.step = '1'; box.inputMode = 'numeric';
    box.value = value > 0 ? String(value) : '';
    box.disabled = !editable();
    return box;
  }
  function number(host, label, key, hint) {
    var wrap = el('label', 'dws-calc-field');
    wrap.appendChild(el('span', null, label));
    var box = numBox(inp[key]);
    box.placeholder = hint || '';
    box.addEventListener('input', function () { edit(key, intOf(box.value)); });
    wrap.appendChild(box);
    host.appendChild(wrap);
    return wrap;
  }
  function syncVisibility() { if (els.nomold) { els.nomold.hidden = inp.line !== 'nomold'; } }

  function renderBasics(product) {
    var sec = section('기본');
    var grid = el('div', 'dws-calc-grid');
    var lines = {};
    C.LINES.forEach(function (k) { lines[k] = C.LINE_NAMES[k]; });
    choice(grid, '제품 계열', 'line', lines);
    choice(grid, '손잡이', 'handle', HANDLE_NAMES);
    number(grid, '전체 폭', 'W', 'mm');
    number(grid, '깊이', 'D', 'mm');
    number(grid, '천장 높이', 'H', 'mm');
    els.nomold = choice(grid, '무몰딩 문 높이', 'nomold', NOMOLD_NAMES);
    number(grid, '서랍 칸 높이', 'zone', String(info.rules.drawer_zone));
    number(grid, '문 높이 직접', 'door_h', '비우면 계산');
    choice(grid, '드러난 옆면(EP)', 'ep', { 0: '0', 1: '1', 2: '2' }, true);
    number(grid, '옆벽 SR 좌', 'sr_l', '없으면 비움');
    number(grid, '옆벽 SR 우', 'sr_r', '없으면 비움');
    sec.appendChild(grid);
    syncVisibility();
    var spec = product && C.parseSpec(product.spec);
    if (spec && editable()) {
      var again = el('button', 'dws-btn dws-calc-small', '제품 규격 다시 넣기 (' + product.spec + ')');
      again.type = 'button';
      again.addEventListener('click', function () {
        inp.W = spec.W; inp.D = spec.D; edit('H', spec.H);
        render();
      });
      sec.appendChild(again);
    }
  }

  function renderMods() {
    var sec = section('모듈 · 스케치업에서 따로 저장한 장 한 칸마다 한 줄');
    var table = el('table', 'dws-calc-mods');
    var hrow = el('tr');
    ['#'].concat(MOD_COLS.map(function (c) { return c[1]; })).concat(['']).forEach(function (t) { hrow.appendChild(el('th', null, t)); });
    table.appendChild(el('thead')).appendChild(hrow);
    var body = el('tbody');
    inp.mods.forEach(function (m, i) {
      var tr = el('tr');
      tr.appendChild(el('td', 'dws-calc-no', String(i + 1)));
      MOD_COLS.forEach(function (c) {
        var box = c[2] ? el('select') : numBox(m[c[0]]);
        if (c[2]) {
          c[2].forEach(function (v) { var o = el('option', null, String(v)); o.value = String(v); box.appendChild(o); });
          box.value = String(m[c[0]] || 0);
          box.disabled = !editable();
        }
        box.setAttribute('aria-label', (i + 1) + '번 모듈 ' + c[1]);
        box.addEventListener(c[2] ? 'change' : 'input', function () { m[c[0]] = intOf(box.value); edit('mods', inp.mods); });
        tr.appendChild(el('td')).appendChild(box);
      });
      var del = el('button', 'dws-calc-del', '빼기');
      del.type = 'button';
      del.disabled = !editable();
      del.setAttribute('aria-label', (i + 1) + '번 모듈 빼기');
      del.addEventListener('click', function () { inp.mods.splice(i, 1); edit('mods', inp.mods); render(); });
      tr.appendChild(el('td')).appendChild(del);
      body.appendChild(tr);
    });
    table.appendChild(body);
    sec.appendChild(table);
    var row = el('div', 'dws-calc-actions');
    if (editable()) {
      var addBtn = el('button', 'dws-btn dws-calc-small', '모듈 더하기');
      addBtn.type = 'button';
      addBtn.addEventListener('click', function () {
        var last = inp.mods[inp.mods.length - 1];
        inp.mods.push({ w: last ? last.w : 1000, doors: 2, drawers: 0, rods: 1 });
        edit('mods', inp.mods);
        render();
      });
      row.appendChild(addBtn);
    }
    els.sum = el('span', 'dws-calc-sum');
    row.appendChild(els.sum);
    sec.appendChild(row);
  }

  function renderSum() {
    var sum = inp.mods.reduce(function (t, m) { return t + (m.w || 0); }, 0);
    var text = '모듈 합 ' + sum;
    if (inp.W > 0) {
      var rest = inp.W - sum - inp.sr_l - inp.sr_r;
      text += ' · 남는 폭 ' + rest + (rest > 0 ? '(옆벽 SR 로 채울 폭)' : '');
    }
    els.sum.textContent = text;
  }

  function renderOut(lines) {
    var box = els.out;
    while (box.childNodes.length > 1) { box.removeChild(box.lastChild); }
    if (!lines.length) { box.appendChild(el('p', 'dws-calc-empty', '전체 폭·천장 높이와 모듈을 넣으면 계산이 나옵니다.')); return; }
    lines.forEach(function (l) {
      if (l.head) { box.appendChild(el('div', 'dws-calc-head-line', '[' + l.head + ']')); return; }
      var row = el('div', 'dws-calc-line');
      row.appendChild(el('span', 'dws-calc-val', l.text));
      row.appendChild(el('span', 'dws-calc-why', l.why));
      box.appendChild(row);
      if (l.ea) {
        var sub = el('div', 'dws-calc-line');
        sub.appendChild(el('span', 'dws-calc-val', 'ㄴ피닉스바 ' + l.ea + 'EA'));
        sub.appendChild(el('span', 'dws-calc-why', '문 ' + l.q + '짝 ÷ 2 올림'));
        box.appendChild(sub);
      }
    });
  }

  function renderCmp(lines, sheet) {
    var box = els.cmp;
    while (box.childNodes.length > 1) { box.removeChild(box.lastChild); }
    var texts = (sheet.objects || []).filter(function (o) { return o.type === 'text'; }).map(function (o) { return o.text; });
    var rows = C.parseBom(texts);
    if (rows.orphans) {
      box.appendChild(el('p', 'dws-calc-hint', '머리글 없이 친 줄 ' + rows.orphans + '개는 맞춰 보지 못했습니다. [DOOR] 같은 머리글과 한 글자 상자에 써 주세요.'));
    }
    if (!rows.length) {
      box.appendChild(el('p', 'dws-calc-empty', '시트에 친 자재표가 아직 없습니다. [SR]·[DOOR] 같은 머리글 아래 줄을 읽어 맞춰 봅니다.'));
      return;
    }
    var res = C.compare(lines, rows);
    var mine = res.filter(function (r) { return r.kind !== 'extra'; });
    var same = mine.filter(function (r) { return r.kind === 'ok'; }).length;
    var extra = res.length - mine.length;
    box.appendChild(el('p', 'dws-calc-score', '계산한 ' + mine.length + '줄 중 ' + same + '줄 같음' + (extra ? ' · 시트에만 있는 줄 ' + extra : '')));
    res.forEach(function (r) {
      var row = el('div', 'dws-calc-cmp');
      row.appendChild(el('span', 'dws-calc-sec-name', r.sec));
      row.appendChild(el('span', 'dws-calc-val', r.text));
      var chip = el('span', 'dws-calc-chip dws-calc-chip-' + r.kind, r.kind === 'ok' ? KIND_NAMES.ok : r.note);
      chip.title = KIND_NAMES[r.kind];
      row.appendChild(chip);
      box.appendChild(row);
    });
  }

  /** 다시 계산 — 시트에 calc 가 있으면 계산 글자·규칙 판도 갱신한다(저장 때 같이 나간다). */
  function refresh() {
    var s = ctx.getSheet();
    if (!s || !info || !inp || !els.out) { return; }
    var lines = C.calc(inp, info.rules);
    if (s.calc && s.calc.in === inp) { s.calc.out = C.toText(lines); s.calc.rules = info.label; }
    renderSum();
    renderOut(lines);
    renderCmp(lines, s);
  }

  function render() {
    var s = ctx.getSheet();
    els.body.textContent = '';
    els.out = null;
    lastSheetId = s ? s.id : null;
    lastCalc = s ? s.calc : undefined;
    if (!info) {
      els.body.appendChild(el('p', 'dws-calc-empty', loading ? '계산 규칙을 불러오는 중입니다…' : '계산 규칙을 불러오지 못했습니다. 칸을 닫았다가 다시 열어 주세요.'));
      return;
    }
    if (!s) { els.body.appendChild(el('p', 'dws-calc-empty', '왼쪽에서 제품을 골라 시트를 먼저 여세요.')); return; }
    var product = ctx.getProduct(s);
    inp = (s.calc && s.calc.in) ? s.calc.in : C.emptyInputs(info.rules, product);
    if (!Array.isArray(inp.mods)) { inp.mods = []; }
    els.body.appendChild(el('p', 'dws-calc-note', NOTE));
    renderBasics(product);
    renderMods();
    els.out = section('계산 결과');
    els.cmp = section('시트 자재표와 맞춰 보기');
    var rulesHost = el('div');
    els.body.appendChild(rulesHost);
    R.renderEditor(rulesHost, info, function (next) { info = next; render(); }, ctx.toast);
    refresh();
  }

  /** 칸 열기·닫기. 처음 열 때 규칙 숫자를 받는다(성능 가드 G2: 쓸 때 받기). */
  function setOpen(on) {
    isOpen = on;
    ctx.host.hidden = !on;
    if (ctx.button) { ctx.button.setAttribute('aria-expanded', String(on)); ctx.button.classList.toggle('dws-btn-on', on); }
    if (!on) { return; }
    if (!info && !loading) {
      loading = R.load().then(function (d) { info = d; loading = null; if (isOpen) { render(); } });
    }
    render();
  }
  function toggle() { setOpen(!isOpen); }

  /** 마법사가 시트를 다시 그릴 때마다 부른다 — 시트·calc 가 바뀌었으면 새로 그리고, 아니면 맞춰 보기만 갱신. */
  function sync() {
    if (!isOpen || !ctx) { return; }
    var s = ctx.getSheet();
    if (!s || s.id !== lastSheetId || s.calc !== lastCalc) { render(); return; }
    refresh();
  }

  function init(opts) {
    C = window.FomsBomCalc;
    R = window.FomsBomRules;
    ctx = opts;
    if (!C || !R || !ctx || !ctx.host) { return false; }
    var head = ctx.host.appendChild(el('div', 'dws-calc-head'));
    head.appendChild(el('span', 'dws-calc-title', '자재표 계산'));
    head.appendChild(el('span', 'dws-calc-badge', '그림자 판'));
    var close = head.appendChild(el('button', 'dws-calc-close', '✕'));
    close.type = 'button';
    close.title = '닫기';
    close.setAttribute('aria-label', '자재표 계산 닫기');
    close.addEventListener('click', function () { setOpen(false); });
    els.body = ctx.host.appendChild(el('div', 'dws-calc-body'));
    if (ctx.button) { ctx.button.addEventListener('click', toggle); }
    return true;
  }

  window.FomsBomPanel = { init: init, sync: sync, toggle: toggle };
})();
