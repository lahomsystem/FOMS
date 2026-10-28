/**
 * 도면 마법사 V2 — 특이 사항 · 강조 문구 카드(왼쪽 칸)와 그 글자 객체 만들기 · 고치기 · 지우기.
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §2 · §4
 * - 특이 사항 = 빨간 굵은 글자 객체, id 'n-'(실선 상자 · 제작) · 'nc-'(점선 상자 · 현장/고객). 강조 문구 = id 'st-'(오른쪽 위 빨간 테두리).
 *   V1 화면에서 열어도 빨간 글자로 보인다(데이터가 숨지 않는다).
 * - 자동 배치 모드에서 칸으로 정리한 시트면 고칠 때마다 칸을 다시 놓고, 아니면(자유 배치) 왼쪽 위에 놓고 사람이 옮긴다.
 * - 강조 문구 내 단추(사용자 요청 2026-10-28 '강조 문구는 내가 추가 할 수 있게' · 질문 창 답 '내 문구를 단추로 남기기'): 직접 쓴 문구를
 *   [넣기]하면 [비규격][원도어][현장 확인] 옆에 단추로 남는다(이 컴퓨터 localStorage 'foms.dws.v2.stamps', 8개까지, × 로 지운다).
 *   쓰는 칸은 늘 비어 있다 — 예전엔 지금 문구를 넣어 두어 단추처럼 보였고 직접 쓰는 칸을 못 찾았다.
 *
 * window.FomsV2Notes = { card(view, api) → 카드 DOM, add(api, text, kind), setStamp(api, text), mine() → [내 문구], remember(text), forget(text) }
 */
(function () {
  'use strict';
  if (window.FomsV2Notes) { return; }

  var RED = '#d2232a', NOTE_SIZE = 17, STAMP_SIZE = 24, MAX = 80, QUICK = ['비규격', '원도어', '현장 확인'];
  var MINE_KEY = 'foms.dws.v2.stamps', MINE_MAX = 8, STAMP_MAX = 24;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }
  function button(label, cls, onClick, aria) {
    var b = el('button', cls, label);
    b.type = 'button';
    if (aria) { b.setAttribute('aria-label', aria); }
    b.addEventListener('click', onClick);
    return b;
  }
  function find(sheet, id) {
    var list = (sheet && sheet.objects) || [];
    for (var i = 0; i < list.length; i++) { if (list[i].id === id) { return list[i]; } }
    return null;
  }

  function after(api) {
    var core = api.core, sh = core.sheet();
    core.markDirty();
    if (api.mode() === 'auto' && sh && sh.form && sh.form.v2_layout) { api.arrange('note', {}); } else { core.redraw(); api.refresh(); }
  }

  function textObj(api, prefix, text, size) {
    return api.core.normalize({ id: api.core.rid(prefix), type: 'text', x: 70, y: 70, w: 1, text: text, size: size,
      color: RED, bold: true, align: 'left', rotation: 0 });
  }

  function add(api, text, kind) {
    var core = api.core, sh = core.sheet(), t = String(text || '').replace(/\s+/g, ' ').trim().slice(0, MAX);
    if (!sh || !t || !core.canSave()) { return; }
    core.recordUndo();
    sh.objects.push(textObj(api, kind === 'site' ? 'nc-' : 'n-', t, NOTE_SIZE));
    after(api);
  }

  function edit(api, id, text) {
    var core = api.core, sh = core.sheet(), o = find(sh, id), t = String(text || '').replace(/\s+/g, ' ').trim().slice(0, MAX);
    if (!o || o.runs || !core.canSave() || t === o.text) { return; }
    core.recordUndo();
    if (!t) { sh.objects = sh.objects.filter(function (x) { return x !== o; }); } else { o.text = t; o.w = 1; }
    after(api);
  }

  function toggle(api, id) {
    var core = api.core, o = find(core.sheet(), id);
    if (!o || !core.canSave()) { return; }
    core.recordUndo();
    o.id = core.rid(/^nc-/.test(o.id) ? 'n-' : 'nc-');
    after(api);
  }

  function remove(api, id) {
    var core = api.core, sh = core.sheet();
    if (!sh || !find(sh, id) || !core.canSave()) { return; }
    core.recordUndo();
    sh.objects = sh.objects.filter(function (x) { return x.id !== id; });
    after(api);
  }

  function clean(text) { return String(text || '').replace(/\s+/g, ' ').trim().slice(0, STAMP_MAX); }

  /** 내 문구 단추 — 이 컴퓨터에만 남는다(사생활 보호 모드면 이번 창에서만 · 못 읽으면 없음). */
  function mine() {
    try {
      var list = JSON.parse(window.localStorage.getItem(MINE_KEY) || '[]');
      return Array.isArray(list) ? list.map(clean).filter(function (t, i, a) { return t && a.indexOf(t) === i; }).slice(0, MINE_MAX) : [];
    } catch (e) { return []; }
  }
  function saveMine(list) {
    try { window.localStorage.setItem(MINE_KEY, JSON.stringify(list.slice(0, MINE_MAX))); } catch (e) { /* 저장 막힘 — 이번 화면만 */ }
  }
  function remember(text) {
    var t = clean(text), list = mine();
    if (t && QUICK.indexOf(t) < 0 && list.indexOf(t) < 0) { saveMine([t].concat(list)); }
  }
  function forget(text) { saveMine(mine().filter(function (x) { return x !== text; })); }

  function setStamp(api, text) {
    var core = api.core, sh = core.sheet(), t = clean(text);
    if (!sh || !core.canSave()) { return; }
    var o = (sh.objects || []).filter(function (x) { return x.type === 'text' && /^st-/.test(x.id); })[0] || null;
    if (!o && !t) { return; }
    if (o && t === o.text) { return; }
    core.recordUndo();
    if (!t) { sh.objects = sh.objects.filter(function (x) { return x !== o; }); }
    else if (o) { o.text = t; o.w = 1; }
    else { sh.objects.push(textObj(api, 'st-', t, STAMP_SIZE)); }
    after(api);
  }

  function commitOnEnter(input) {
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); input.blur(); } });
  }

  function noteRow(o, api, editable) {
    var row = el('div', 'dws-v2-note-row'), site = /^nc-/.test(o.id);
    var input = el('input', 'dws-v2-note-input');
    input.type = 'text';
    input.maxLength = MAX;
    input.value = o.text || '';
    input.disabled = !editable || !!o.runs;
    input.setAttribute('aria-label', '특이 사항');
    commitOnEnter(input);
    input.addEventListener('change', function () { edit(api, o.id, input.value); });
    row.appendChild(input);
    if (editable) {
      var k = button(site ? '점선' : '실선', 'dws-v2-note-kind' + (site ? ' dws-v2-note-kind-site' : ''), function () { toggle(api, o.id); });
      k.title = site ? '점선 = 현장 · 고객 몫 (누르면 실선)' : '실선 = 제작 몫 (누르면 점선)';
      row.appendChild(k);
      row.appendChild(button('×', 'dws-v2-note-del', function () { remove(api, o.id); }, '특이 사항 지우기'));
    }
    return row;
  }

  function card(view, api) {
    var g = view.plan.g, editable = api.core.canSave(), c = el('div', 'dws-v2-card dws-v2-card-notes');
    c.setAttribute('data-slot', 'notes');
    var h = el('div', 'dws-v2-card-head');
    h.appendChild(el('span', 'dws-v2-card-badge dws-v2-card-badge-word', '특이'));
    h.appendChild(el('span', 'dws-v2-card-title', '특이 사항 ' + g.notes.length));
    c.appendChild(h);
    g.notes.forEach(function (o) { c.appendChild(noteRow(o, api, editable)); });
    if (editable) {
      var addRow = el('div', 'dws-v2-note-row dws-v2-note-add'), input = el('input', 'dws-v2-note-input');
      input.type = 'text';
      input.maxLength = MAX;
      input.placeholder = '특이 사항 더하기 (예: 좌벽 스라 맞춤)';
      input.setAttribute('aria-label', '특이 사항 더하기');
      input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); add(api, input.value, 'make'); } });
      addRow.appendChild(input);
      addRow.appendChild(button('더하기', 'dws-v2-note-addbtn', function () { add(api, input.value, 'make'); }));
      c.appendChild(addRow);
    }
    c.appendChild(stampRow(g.stamp, api, editable));
    return c;
  }

  /** 강조 문구 줄 — 지금 문구 · [빼기], 기본 단추 셋 + 내 문구 단추(×), 직접 쓰기 칸 [넣기](넣으면 내 문구 단추로 남는다). */
  function stampRow(st, api, editable) {
    var srow = el('div', 'dws-v2-stamp-row');
    srow.appendChild(el('span', 'dws-v2-stamp-label', '강조 문구 (오른쪽 위 빨간 상자)' + (st ? ': ' + st.text : ' — 없음')));
    if (!editable) { return srow; }
    QUICK.forEach(function (q) { srow.appendChild(button(q, 'dws-v2-stamp-quick', function () { setStamp(api, q); })); });
    mine().forEach(function (q) {
      var chip = el('span', 'dws-v2-stamp-mine');
      chip.appendChild(button(q, 'dws-v2-stamp-quick', function () { setStamp(api, q); }));
      chip.appendChild(button('×', 'dws-v2-stamp-forget', function () { forget(q); api.refresh(); }, '내 문구 단추 지우기: ' + q));
      srow.appendChild(chip);
    });
    if (st) { srow.appendChild(button('빼기', 'dws-v2-stamp-quick', function () { setStamp(api, ''); })); }
    var add = el('div', 'dws-v2-stamp-add'), si = el('input', 'dws-v2-note-input dws-v2-stamp-input');
    si.type = 'text';
    si.maxLength = STAMP_MAX;
    si.placeholder = '내 문구 쓰기 (예: 상판 별도)';
    si.setAttribute('aria-label', '강조 문구 직접 쓰기 — 넣으면 단추로 남아요');
    function put() {
      var t = clean(si.value);
      if (!t) { return; }
      remember(t);
      setStamp(api, t);
      api.refresh();   // 같은 문구면 다시 배치가 없어 새 단추가 안 보였다
    }
    si.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); put(); } });
    add.appendChild(si);
    add.appendChild(button('넣기', 'dws-v2-note-addbtn', put));
    srow.appendChild(add);
    return srow;
  }

  window.FomsV2Notes = { card: card, add: add, setStamp: setStamp, mine: mine, remember: remember, forget: forget };
})();
