/* 협력사 단가표 편집 화면(설계서 2026-11-03-partner-statement §5.1).
 *
 * GET {api} 판 목록 + 지금 판 → 사용자가 쓰던 "통합 단가표" 모양(왼쪽 · 오른쪽 카테고리 표)으로 그린다.
 * "편집하기" = 이름 · 금액 칸 바로 고치기 · 줄 넣기/빼기 · 위아래. 줄 계산 정보는 partner-price-list-panel.js.
 * "HTML 불러오기" = POST {api}/import (저장 안 함), "저장 (새 판)" = POST {api} {sheet, label, effective_from, base_id}.
 * CSRF 토큰은 공용 fetch 래퍼가 붙인다. 글은 textContent 로만 넣는다(innerHTML 없음).
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-pl-root]');
  if (!root) return;
  var api = root.getAttribute('data-api-url');
  var panel = window.FomsPriceListPanel;
  var KIND_LABEL = {};
  (panel ? panel.kinds : []).forEach(function (k) { KIND_LABEL[k[0]] = k[1]; });

  var state = { versions: [], active: null, viewing: null, sheet: null, editing: false, dirty: false, sel: null, imported: null };
  var $ = function (sel) { return root.querySelector(sel); };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function status(text, kind) {
    $('[data-pl-status]').textContent = text || '';
    $('[data-pl-status]').className = 'foms-pl__status small' + (kind ? ' foms-pl__status--' + kind : '');
  }

  function message(kind, text, list) {
    var box = $('[data-pl-message]');
    box.replaceChildren();
    if (!text) { box.className = 'alert d-none foms-pl__message'; return; }
    box.className = 'alert foms-pl__message alert-' + kind;
    box.appendChild(el('div', 'fw-bold', text));
    var ul = box.appendChild(el('ul', 'mb-0 small'));
    (list && list.length > 1 ? list : []).forEach(function (t) { ul.appendChild(el('li', null, t)); });
  }

  async function requestJson(url, init) {
    var response, data = null;
    init = Object.assign({ credentials: 'same-origin' }, init || {});
    init.headers = Object.assign({ 'Accept': 'application/json' }, init.headers || {});
    try { response = await fetch(url, init); } catch (err) {
      return { ok: false, error: '서버에 닿지 못했습니다. 인터넷 연결을 확인해 주세요.' };
    }
    try { data = await response.json(); } catch (err) { data = null; }
    if (!data || typeof data !== 'object') return { ok: false, error: '서버 응답을 읽지 못했습니다. 잠시 뒤 다시 해 주세요.' };
    if (!response.ok || !data.success) {
      return { ok: false, status: response.status, error: data.error || '처리하지 못했습니다.', errors: data.data && data.data.errors };
    }
    return { ok: true, data: data.data || {} };
  }

  // ── 값 · 표시 ─────────────────────────────────────────────────────────
  function priceOf(row, item) {
    var v = row.cells[item.price_col];
    if (v === '' || v == null) return null;
    var n = typeof v === 'number' ? v : parseInt(String(v).replace(/[,\s원]/g, ''), 10);
    return isNaN(n) ? v : n;
  }
  function fmt(v) { return typeof v === 'number' ? v.toLocaleString('ko-KR') : (v == null ? '' : String(v)); }
  function itemAt(sel) {
    if (!sel || !state.sheet) return null;
    var row = state.sheet.categories[sel.ci].rows[sel.ri];
    return row ? { row: row, item: row.items[sel.ii] } : null;
  }
  function editable() { return !!state.sheet && (!state.viewing || state.viewing.status === 'ACTIVE' || state.imported); }

  var ctx = {
    editable: editable,
    changed: function () { setDirty(); renderSheet(); },
    describe: function (item) {
      var hit = findRow(item);
      var price = hit ? priceOf(hit, item) : null;
      return { name: hit ? String(hit.cells[item.name_col] || '') : '', included: !price,
               priceText: price == null || price === 0 ? '금액 빈칸 · 0원 (기본 포함)' : fmt(price) + '원 · VAT 포함' };
    },
    overItems: function () {
      var out = [];
      eachItem(function (row, item) { if (item.kind === 'over') out.push({ key: item.key, name: String(row.cells[item.name_col] || '') }); });
      return out;
    }
  };
  function eachItem(fn) {
    (state.sheet ? state.sheet.categories : []).forEach(function (cat) {
      cat.rows.forEach(function (row) { row.items.forEach(function (item) { fn(row, item); }); });
    });
  }
  function findRow(target) {
    var found = null;
    eachItem(function (row, item) { if (item === target) found = row; });
    return found;
  }
  function setDirty() { state.dirty = true; status('● 아직 저장하지 않았습니다 — "저장 (새 판)"을 눌러 주세요', 'dirty'); }

  // ── 그리기 ────────────────────────────────────────────────────────────
  function badge(row, item) {
    var price = priceOf(row, item);
    var span = el('span', 'foms-pl-kb foms-pl-kb--' + (price ? item.kind : 'included'), price ? (KIND_LABEL[item.kind] || item.kind) : '기본 포함');
    if (item.pickable === false) span.classList.add('foms-pl-kb--hidden');
    return span;
  }

  function cellNode(cat, row, col, ci, ri) {
    var isPrice = cat.types[col] === 'price';
    var td = el('td', isPrice ? 'foms-pl__pr' : 'foms-pl__nm');
    var item = row.items.filter(function (it) { return it.name_col === col; })[0];
    if (state.editing) {
      var input = el('input', 'form-control form-control-sm');
      input.value = fmt(row.cells[col]);
      input.setAttribute('aria-label', (cat.headers[col] || '칸') + ' 고치기');
      input.addEventListener('change', function () {
        var raw = input.value.trim();
        var num = raw.replace(/[,\s원]/g, '');
        row.cells[col] = isPrice && /^\d+$/.test(num) ? parseInt(num, 10) : raw;
        if (!isPrice && !item && raw && cat.types[col + 1] === 'price') addItem(row, col, cat);
        ctx.changed();
      });
      td.appendChild(input);
    } else {
      td.appendChild(el('span', null, fmt(row.cells[col])));
    }
    if (item) {
      td.classList.add('foms-pl__pick');
      td.appendChild(badge(row, item));
      var ii = row.items.indexOf(item);
      if (state.sel && state.sel.ci === ci && state.sel.ri === ri && state.sel.ii === ii) td.classList.add('is-selected');
      td.addEventListener('click', function (e) {
        if (e.target.tagName === 'INPUT') return;
        state.sel = { ci: ci, ri: ri, ii: ii };
        renderSheet();
        if (panel) panel.show(item, ctx);
      });
    }
    return td;
  }

  function addItem(row, col, cat) {
    state.sheet.seq = (state.sheet.seq || 0) + 1;
    var product = /기본 제품/.test(cat.title || '');
    row.items.push({ key: 'r' + state.sheet.seq, name_col: col, price_col: col + 1, role: product ? 'product' : 'option',
                     unit: product ? '자' : '개', kind: product ? 'ja' : 'count', cond: {}, partner_label: '',
                     pick_names: [], for_products: [], pickable: true });
  }

  function rowTools(cat, ri) {
    var td = el('td', 'foms-pl__tools');
    [['↑', -1, '위로'], ['↓', 1, '아래로'], ['✕', 0, '줄 빼기']].forEach(function (t) {
      var b = el('button', 'foms-pl__tool', t[0]);
      b.type = 'button'; b.setAttribute('aria-label', t[2]);
      b.addEventListener('click', function () {
        if (t[1] === 0) cat.rows.splice(ri, 1);
        else if (cat.rows[ri + t[1]]) cat.rows.splice(ri + t[1], 0, cat.rows.splice(ri, 1)[0]);
        state.sel = null;
        if (panel) panel.clear();
        ctx.changed();
      });
      td.appendChild(b);
    });
    return td;
  }

  function categoryNode(cat, ci) {
    var sec = el('section', 'foms-pl__cat');
    sec.appendChild(el('div', 'foms-pl__cathead', cat.title));
    var table = el('table', 'foms-pl__tab');
    var tr = el('tr');
    cat.headers.forEach(function (h, i) { tr.appendChild(el('th', cat.types[i] === 'price' ? 'foms-pl__pr' : null, h)); });
    if (state.editing) tr.appendChild(el('th'));
    table.appendChild(el('thead')).appendChild(tr);
    var tbody = table.appendChild(el('tbody'));
    cat.rows.forEach(function (row, ri) {
      var line = el('tr');
      cat.headers.forEach(function (_h, col) { line.appendChild(cellNode(cat, row, col, ci, ri)); });
      if (state.editing) line.appendChild(rowTools(cat, ri));
      tbody.appendChild(line);
    });
    sec.appendChild(table);
    if (state.editing) {
      var add = el('button', 'btn btn-outline-secondary btn-sm mt-1', '+ 줄 넣기');
      add.type = 'button';
      add.addEventListener('click', function () {
        cat.rows.push({ cells: cat.headers.map(function () { return ''; }), items: [] });
        ctx.changed();
      });
      sec.appendChild(add);
    }
    return sec;
  }

  function renderSheet() {
    var left = $('[data-pl-side="left"]'), right = $('[data-pl-side="right"]');
    left.replaceChildren(); right.replaceChildren();
    $('[data-pl-empty]').hidden = !!state.sheet;
    $('[data-pl-logo]').textContent = state.sheet ? (state.sheet.brand || '').toUpperCase() : '';
    $('[data-pl-sheet]').classList.toggle('is-editing', state.editing);
    $('[data-pl-edit]').textContent = state.editing ? '편집 끝' : '편집하기';
    $('[data-pl-edit]').disabled = !editable();
    $('[data-pl-save-open]').disabled = !state.sheet || !editable();
    if (!state.sheet) return;
    state.sheet.categories.forEach(function (cat, ci) {
      (cat.side === 'right' ? right : left).appendChild(categoryNode(cat, ci));
    });
  }

  function renderVersions() {
    var box = $('[data-pl-version]');
    box.replaceChildren();
    if (!state.versions.length) box.appendChild(el('option', null, '저장한 판 없음'));
    state.versions.forEach(function (v) {
      var o = el('option', null, v.label + ' (' + v.version + '번째) · ' + (v.effective_from || '') + '부터' + (v.status === 'ACTIVE' ? ' · 지금 쓰는 판' : ''));
      o.value = String(v.id);
      if (state.viewing && state.viewing.id === v.id) o.selected = true;
      box.appendChild(o);
    });
  }

  function show(detail, note) {
    Object.assign(state, { viewing: detail, sheet: detail ? clone(detail.sheet) : null, editing: false, dirty: false, sel: null, imported: null });
    if (panel) panel.clear();
    renderVersions();
    renderSheet();
    status(note || (detail ? (detail.status === 'ACTIVE' ? '지금 쓰는 판' : '옛 판 — 볼 수만 있음') + (detail.created_by ? ' · ' + detail.created_by + ' 저장' : '') : ''));
  }

  async function load(note) {
    var res = await requestJson(api);
    if (!res.ok) { message('danger', res.error); return; }
    state.versions = res.data.versions || [];
    state.active = res.data.active;
    show(state.active, note);
  }

  // ── 불러오기 · 저장 ──────────────────────────────────────────────────
  function useImported(brand) {
    Object.assign(state, { sheet: clone(state.imported.sheets[brand]), dirty: true, editing: false, sel: null });
    if (panel) panel.clear();
    renderSheet();
    status('● ' + brand + ' 단가표를 불러왔습니다 — 계산 방법을 확인하고 "저장 (새 판)"을 눌러 주세요', 'dirty');
  }

  $('[data-pl-import-btn]').addEventListener('click', function () { $('[data-pl-import-file]').click(); });
  $('[data-pl-import-file]').addEventListener('change', async function () {
    var file = this.files && this.files[0];
    this.value = '';
    if (!file) return;
    var form = new FormData(); form.append('file', file);
    status('불러오는 중…');
    var res = await requestJson(api + '/import', { method: 'POST', body: form });
    if (!res.ok) { status(''); message('danger', res.error, res.errors); return; }
    message(null);
    state.imported = res.data;
    var brands = res.data.brands || [];
    var pick = $('[data-pl-brand]');
    pick.replaceChildren();
    brands.forEach(function (b) { var o = el('option', null, b); o.value = b; pick.appendChild(o); });
    pick.hidden = brands.length < 2;
    if (brands.length) useImported(brands[0]);
  });
  $('[data-pl-brand]').addEventListener('change', function () { if (state.imported) useImported(this.value); });

  $('[data-pl-edit]').addEventListener('click', function () { state.editing = !state.editing; renderSheet(); });
  $('[data-pl-version]').addEventListener('change', async function () {
    if (state.dirty && !window.confirm('저장하지 않은 변경이 사라집니다. 다른 판을 열까요?')) { renderVersions(); return; }
    var res = await requestJson(api + '/' + this.value);
    if (res.ok) show(res.data); else message('danger', res.error);
  });

  var saveForm = $('[data-pl-save-form]');
  $('[data-pl-save-open]').addEventListener('click', function () {
    var now = new Date();
    if (!$('[data-pl-label]').value) $('[data-pl-label]').value = (now.getMonth() + 1) + '월판';
    if (!$('[data-pl-from]').value) $('[data-pl-from]').value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    saveForm.hidden = false;
    $('[data-pl-label]').focus();
  });
  $('[data-pl-save-cancel]').addEventListener('click', function () { saveForm.hidden = true; });
  saveForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    var body = { sheet: state.sheet, label: $('[data-pl-label]').value, effective_from: $('[data-pl-from]').value,
                 base_id: state.active ? state.active.id : null };
    status('저장하는 중…');
    var res = await requestJson(api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!res.ok) { status('● 저장하지 못했습니다', 'dirty'); message('danger', res.error, res.errors); return; }
    saveForm.hidden = true;
    message('success', res.data.label + ' 저장했습니다. ' + res.data.effective_from + ' 출고부터 이 단가로 계산하고, 이미 나간 명세서는 바뀌지 않습니다.');
    await load('✓ ' + res.data.label + ' 저장');
  });

  window.addEventListener('beforeunload', function (e) { if (state.dirty) { e.preventDefault(); e.returnValue = ''; } });
  load();
})();
