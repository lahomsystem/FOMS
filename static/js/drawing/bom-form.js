/**
 * 도면 마법사 — 자재표 계산 칸의 입력 묶음(모듈 · 제품·치수)과 접는 묶음 틀.
 *
 * 보고서 2026-10-25 '계산 칸 배치 안 A': 칸 맨 위 '계산 결과' 아래 스크롤 구역에
 * - '모듈 N개 · 폭 합 3500 · 남는 폭 160 [+ 모듈]'(펼침) — 가장 자주 고치는 곳이라 위에 둔다.
 * - '제품·치수'(시트마다 한 번 — 폭·깊이·높이가 차 있으면 '몰딩 여닫이 · 피닉스바 · 3660×600×2300' 한 줄로 접고,
 *   눌러서 편다). 치는 도중에는 접지 않는다(다시 그릴 때만 판단).
 * - 남는 폭이 있고 옆벽 SR 왼쪽·오른쪽이 비었으면 '옆벽 SR 에 나눠 넣기(80·80)'를 권한다(계산 입력만 채운다).
 * - 화면 글은 짧게(사용자 피드백 2026-10-27): 묶음 '기본' → '제품·치수', 빈 모듈 '모듈 0개 · 합 0' → '모듈',
 *   모듈 합이 전체 폭을 넘으면 '남는 폭 -140' 대신 '넘는 폭 140'. 입력 이름 '제품 계열' → '제품 종류',
 *   '문 높이 직접'(비우면 계산) → '문 높이'(비우면 자동), '옆벽 SR 좌·우' → '옆벽 SR 왼쪽·오른쪽'.
 *
 * window.FomsBomForm = { fold(host, key, open?, extra?), build(host, f), refresh() }
 *   f: { C, inp, rules, product, editable, edit(key, value), render(), sheetId }
 */
(function () {
  'use strict';
  if (window.FomsBomForm) { return; }

  var HANDLE_NAMES = { phoenix: '피닉스바', other: '그 밖(푸쉬 등)' };
  var NOMOLD_NAMES = { ceiling: '천장까지(천장 − 45)', std: '표준 문(2160 등)' };
  var MOD_COLS = [['w', '폭'], ['doors', '문 짝', [0, 1, 2]], ['drawers', '서랍', [0, 1, 2, 3, 4]], ['rods', '옷봉', [0, 1, 2]]];
  var MAX_MODS = 24;     // 서버 _validate_calc 모듈 상한(bom-calc.js MAX_MODS 와 같다)
  var SPLIT_MAX = 600;   // 남는 폭이 이보다 크면 모듈을 덜 넣은 것으로 보고 옆벽 SR 나눔을 권하지 않는다
  var opened = { mods: true };   // 사람이 접고 편 상태(다시 그려도 그대로)
  var basicsFor = null;          // '제품·치수' 묶음을 사람이 접고 편 시트 { id, open }
  var f = null, refs = {}, focusNew = false;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = text; }
    return e;
  }
  function intOf(v) { var n = Math.round(Number(v)); return isFinite(n) && n > 0 ? n : 0; }
  function button(cls, text) { var b = el('button', cls, text); b.type = 'button'; return b; }

  /** 접는 묶음 — [▸/▾ 제목] 단추 + 덧붙일 단추 + 몸통. open 을 안 주면 사람이 마지막에 둔 상태. */
  function fold(host, key, open, extra) {
    var box = host.appendChild(el('section', 'dws-calc-fold'));
    var head = box.appendChild(el('div', 'dws-calc-fold-head'));
    var btn = head.appendChild(button('dws-calc-fold-btn'));
    var mark = btn.appendChild(el('span', 'dws-calc-fold-mark'));
    var label = btn.appendChild(el('span', 'dws-calc-fold-label'));
    if (extra) { head.appendChild(extra); }
    var body = box.appendChild(el('div', 'dws-calc-fold-body'));
    body.id = 'dws-calc-fold-' + key;
    btn.setAttribute('aria-controls', body.id);
    var api = { body: body, label: label, onToggle: null, isOpen: function () { return !body.hidden; } };
    function set(on) {
      body.hidden = !on;
      mark.textContent = on ? '▾' : '▸';
      btn.setAttribute('aria-expanded', String(on));
    }
    btn.addEventListener('click', function () {
      set(body.hidden);
      opened[key] = !body.hidden;
      if (api.onToggle) { api.onToggle(!body.hidden); }
    });
    set(open == null ? !!opened[key] : open);
    return api;
  }

  /* ---- 제품·치수 ---- */
  function choice(host, label, key, names, numeric) {
    var wrap = host.appendChild(el('label', 'dws-calc-field'));
    wrap.appendChild(el('span', 'dws-calc-field-name', label));
    var sel = wrap.appendChild(el('select'));
    Object.keys(names).forEach(function (k) { var o = el('option', null, names[k]); o.value = k; sel.appendChild(o); });
    sel.value = String(f.inp[key]);
    sel.disabled = !f.editable;
    sel.addEventListener('change', function () { f.edit(key, numeric ? intOf(sel.value) : sel.value); syncNomold(); });
    return wrap;
  }
  function numBox(value) {
    var box = el('input');
    box.type = 'number'; box.min = '0'; box.step = '1'; box.inputMode = 'numeric';
    box.value = value > 0 ? String(value) : '';
    box.disabled = !f.editable;
    return box;
  }
  function number(host, label, key, hint) {
    var wrap = host.appendChild(el('label', 'dws-calc-field'));
    wrap.appendChild(el('span', 'dws-calc-field-name', label));
    var box = wrap.appendChild(numBox(f.inp[key]));
    box.placeholder = hint || '';
    box.addEventListener('input', function () { f.edit(key, intOf(box.value)); });
    return wrap;
  }
  function syncNomold() { if (refs.nomold) { refs.nomold.hidden = f.inp.line !== 'nomold'; } }
  function filled(inp) { return inp.W > 0 && inp.D > 0 && inp.H > 0; }
  function basicsText(inp) {
    var t = [f.C.LINE_NAMES[inp.line] || '', HANDLE_NAMES[inp.handle] || '',
      [inp.W, inp.D, inp.H].map(function (v) { return v > 0 ? v : '—'; }).join('×')];
    if (inp.ep > 0) { t.push('EP ' + inp.ep); }
    if (inp.sr_l > 0 || inp.sr_r > 0) { t.push('옆벽 SR ' + inp.sr_l + '·' + inp.sr_r); }
    if (inp.door_h > 0) { t.push('문 높이 ' + inp.door_h); }
    return t.join(' · ');
  }

  function renderBasics(host) {
    var grid = host.appendChild(el('div', 'dws-calc-grid'));
    var lines = {};
    f.C.LINES.forEach(function (k) { lines[k] = f.C.LINE_NAMES[k]; });
    choice(grid, '제품 종류', 'line', lines);
    choice(grid, '손잡이', 'handle', HANDLE_NAMES);
    number(grid, '전체 폭', 'W', 'mm');
    number(grid, '깊이', 'D', 'mm');
    number(grid, '천장 높이', 'H', 'mm');
    refs.nomold = choice(grid, '무몰딩 문 높이', 'nomold', NOMOLD_NAMES);
    number(grid, '서랍 칸 높이', 'zone', String(f.rules.drawer_zone));
    number(grid, '문 높이', 'door_h', '비우면 자동');   // 넣으면 이 값으로(무몰딩 문 높이·표준 문 계산보다 먼저)
    choice(grid, '드러난 옆면(EP)', 'ep', { 0: '0', 1: '1', 2: '2' }, true);
    number(grid, '옆벽 SR 왼쪽', 'sr_l', '없으면 비움');
    number(grid, '옆벽 SR 오른쪽', 'sr_r', '없으면 비움');
    syncNomold();
    var spec = f.product && f.C.parseSpec(f.product.spec);
    if (spec && f.editable) {
      var again = host.appendChild(button('dws-btn dws-calc-small', '제품 규격 다시 넣기 (' + f.product.spec + ')'));
      again.addEventListener('click', function () {
        f.inp.W = spec.W; f.inp.D = spec.D; f.edit('H', spec.H);
        f.render();
      });
    }
  }

  /* ---- 모듈 ---- */
  function addButton() {
    if (!f.editable) { return null; }
    var add = button('dws-btn dws-calc-small dws-calc-add', '+ 모듈');
    add.title = '모듈 한 줄 더하기(앞 모듈 폭을 이어 받음)';
    add.disabled = f.inp.mods.length >= MAX_MODS;
    add.addEventListener('click', function () {
      var mods = f.inp.mods, last = mods[mods.length - 1];
      mods.push({ w: last ? last.w : 1000, doors: 2, drawers: 0, rods: 1 });
      opened.mods = true;
      focusNew = true;
      f.edit('mods', mods);
      f.render();
    });
    return add;
  }

  function renderMods(host) {
    var inp = f.inp, last = null;
    host.appendChild(el('p', 'dws-calc-hint dws-calc-mods-note', '스케치업에서 따로 저장한 장 한 칸마다 한 줄'));
    if (!inp.mods.length) {
      host.appendChild(el('p', 'dws-calc-empty', f.editable ? '아직 모듈이 없습니다. [+ 모듈]로 한 줄씩 더하세요.' : '모듈이 없습니다.'));
    }
    var table = host.appendChild(el('table', 'dws-calc-mods'));
    table.hidden = !inp.mods.length;
    var hrow = el('tr');
    ['#'].concat(MOD_COLS.map(function (c) { return c[1]; })).concat(['']).forEach(function (t) { hrow.appendChild(el('th', null, t)); });
    table.appendChild(el('thead')).appendChild(hrow);
    var body = table.appendChild(el('tbody'));
    inp.mods.forEach(function (m, i) {
      var tr = body.appendChild(el('tr'));
      tr.appendChild(el('td', 'dws-calc-no', String(i + 1)));
      MOD_COLS.forEach(function (c) {
        var box = c[2] ? el('select') : numBox(m[c[0]]);
        if (c[2]) {
          c[2].forEach(function (v) { var o = el('option', null, String(v)); o.value = String(v); box.appendChild(o); });
          box.value = String(m[c[0]] || 0);
          box.disabled = !f.editable;
        } else { last = box; }
        box.setAttribute('aria-label', (i + 1) + '번 모듈 ' + c[1]);
        box.addEventListener(c[2] ? 'change' : 'input', function () { m[c[0]] = intOf(box.value); f.edit('mods', inp.mods); });
        tr.appendChild(el('td')).appendChild(box);
      });
      var del = tr.appendChild(el('td')).appendChild(button('dws-calc-del', '빼기'));
      del.disabled = !f.editable;
      del.setAttribute('aria-label', (i + 1) + '번 모듈 빼기');
      del.addEventListener('click', function () { inp.mods.splice(i, 1); f.edit('mods', inp.mods); f.render(); });
    });
    var row = host.appendChild(el('div', 'dws-calc-actions'));
    refs.rest = row.appendChild(el('span', 'dws-calc-sum'));
    refs.split = row.appendChild(button('dws-btn dws-calc-small dws-calc-split'));
    refs.split.addEventListener('click', function () {
      var half = refs.split.half;
      if (!half) { return; }
      inp.sr_l = half[0];
      f.edit('sr_r', half[1]);
      f.render();
    });
    if (focusNew && last) { last.focus(); if (last.select) { last.select(); } }   // 새 줄 폭 칸에 바로 치게
    focusNew = false;
  }

  /** 모듈 묶음 제목 — 모듈이 없으면 '모듈', 있으면 '모듈 4개 · 폭 합 3500 · 남는 폭 160'(넘치면 '넘는 폭 140'). */
  function modsTitle(n, sum, rest) {
    if (!n) { return '모듈'; }
    var t = '모듈 ' + n + '개 · 폭 합 ' + sum;
    if (rest != null) { t += rest < 0 ? ' · 넘는 폭 ' + (-rest) : ' · 남는 폭 ' + rest; }
    return t;
  }

  /** 입력이 바뀔 때마다 — 묶음 제목(모듈 폭 합·남는 폭, 제품·치수 요약)과 옆벽 SR 나눔 제안을 고친다.
      모듈이 아직 없으면 남는 폭 안내·나눔 제안을 하지 않는다(전체 폭을 통째로 SR 로 채우라는 말이 된다). */
  function refresh() {
    if (!f || !refs.modsLabel) { return; }
    var inp = f.inp, n = inp.mods.length;
    var sum = inp.mods.reduce(function (t, m) { return t + (m.w || 0); }, 0);
    var rest = inp.W > 0 ? inp.W - sum - inp.sr_l - inp.sr_r : null;
    refs.modsLabel.textContent = modsTitle(n, sum, rest);
    var restText = '';
    if (rest == null) { restText = '전체 폭을 넣으면 남는 폭을 알려 줍니다.'; }
    else if (n && rest > 0) { restText = '남는 폭 ' + rest + ' 은 옆벽 SR 로 채울 폭입니다.'; }
    else if (n && rest < 0) { restText = '모듈 폭 합이 전체 폭보다 ' + (-rest) + ' 큽니다.'; }
    refs.rest.textContent = restText;
    var split = f.editable && n > 0 && rest > 0 && rest <= SPLIT_MAX && !inp.sr_l && !inp.sr_r;
    refs.split.half = split ? [Math.floor(rest / 2), rest - Math.floor(rest / 2)] : null;
    refs.split.hidden = !split;
    if (split) { refs.split.textContent = '옆벽 SR 에 나눠 넣기(' + refs.split.half.join('·') + ')'; }
    refs.basics.label.textContent = refs.basics.isOpen() ? '제품·치수' : '제품·치수: ' + basicsText(inp);
  }

  /** 스크롤 구역에 모듈 · 제품·치수 묶음을 그린다. */
  function build(host, fctx) {
    f = fctx;
    refs = {};
    var mods = fold(host, 'mods', opened.mods !== false, addButton());
    refs.modsLabel = mods.label;
    renderMods(mods.body);
    var basics = fold(host, 'basics', (basicsFor && basicsFor.id === f.sheetId) ? basicsFor.open : !filled(f.inp));
    basics.onToggle = function (on) { basicsFor = { id: f.sheetId, open: on }; refresh(); };
    refs.basics = basics;
    renderBasics(basics.body);
    refresh();
  }

  window.FomsBomForm = { fold: fold, build: build, refresh: refresh };
})();
