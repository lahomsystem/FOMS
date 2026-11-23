/**
 * PC 출고 탭 세부 창(서랍) — 표 줄을 마우스로 누르면 오른쪽에 열린다.
 * 설계서 docs/specs/2026-11-23-pc-shipment-card-table_SPEC.md §4.2.
 * 태블릿(손가락)은 tablet-side-sheet.js 가 맡는다 — 여기는 PC(마우스) 문지기만.
 * 본문 = /erp/shipment/tablet-sheet/<id> 조각(.foms-ship-sheet). 시간 단추는 tablet-ship-sheet.js 가 그대로 받는다.
 * 저장은 construction_time 만 보낸다 — 현장 메모(site_extra)는 PC 표가 여러 줄 · 색을 가지므로 보내지 않는다.
 */
(function () {
  'use strict';
  if (window.__FOMS_PC_SHIP_SHEET_BOUND) return;
  window.__FOMS_PC_SHIP_SHEET_BOUND = true;

  var PC_QUERY = '(min-width: 992px) and (pointer: fine)';
  var ROW_SEL = '#shipment-dashboard-table tr.shipment-row[data-order-id][data-foms-sheet-url]';
  var SKIP_SEL = 'a, button, input, select, textarea, label, .shipment-edit-list, .shipment-site-extra-list, ' +
    '[data-ship-worker-cell], .erp-ship-change, .col-resize-handle';
  var drawer = null;
  var openRow = null;
  var loadSeq = 0;

  function isPc() {
    return !!(window.matchMedia && window.matchMedia(PC_QUERY).matches);
  }
  function hasSelection() {
    var sel = window.getSelection ? window.getSelection() : null;
    return !!(sel && String(sel).trim());
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function ensureDrawer() {
    if (drawer && drawer.isConnected) return drawer;
    drawer = el('aside', 'foms-pc-ship-drawer');
    drawer.setAttribute('aria-label', '출고 세부');
    drawer.hidden = true;
    var head = el('div', 'foms-pc-ship-drawer__head');
    head.appendChild(el('span', 'foms-pc-ship-drawer__title', '출고 세부'));
    var open = el('a', 'foms-pc-ship-drawer__open', '주문 열기');
    open.hidden = true;
    head.appendChild(open);
    var x = el('button', 'foms-pc-ship-drawer__close', '닫기');
    x.type = 'button';
    x.setAttribute('data-pc-ship-close', '');
    head.appendChild(x);
    drawer.appendChild(head);
    drawer.appendChild(el('div', 'foms-pc-ship-drawer__body'));
    document.body.appendChild(drawer);
    return drawer;
  }
  function body() { return ensureDrawer().querySelector('.foms-pc-ship-drawer__body'); }

  function setMessage(text, retry) {
    var b = body();
    b.textContent = '';
    b.appendChild(el('p', 'foms-pc-ship-drawer__msg', text));
    if (retry) {
      var btn = el('button', 'foms-pc-ship-drawer__retry', '다시 시도');
      btn.type = 'button';
      btn.addEventListener('click', function () { if (openRow) load(openRow); });
      b.appendChild(btn);
    }
  }

  function sheetUrl(row) {
    var url = row.getAttribute('data-foms-sheet-url');
    var cfg = document.getElementById('shipment-dashboard-config');
    var date = cfg ? cfg.getAttribute('data-selected-date') : '';
    if (date && url.indexOf('date=') === -1) url += (url.indexOf('?') === -1 ? '?' : '&') + 'date=' + encodeURIComponent(date);
    return url;
  }

  function setOpenLink(row) {
    var link = drawer.querySelector('.foms-pc-ship-drawer__open');
    var src = row.querySelector('td:first-child a[title="주문 상세"]') || row.querySelector('a[title="주문 상세"]');
    if (src && src.getAttribute('href')) {
      link.href = src.getAttribute('href');
      link.hidden = false;
    } else {
      link.removeAttribute('href');
      link.hidden = true;
    }
  }

  async function load(row) {
    var seq = ++loadSeq;
    setMessage('불러오는 중이에요…', false);
    try {
      var res = await fetch(sheetUrl(row), {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var html = await res.text();
      if (seq !== loadSeq || openRow !== row) return;
      var b = body();
      b.innerHTML = html;
      adaptForPc(b);
    } catch (err) {
      console.error('[pc-ship-sheet] 세부 불러오기 실패:', err);
      if (seq === loadSeq && openRow === row) setMessage('세부를 못 불러왔어요', true);
    }
  }

  function adaptForPc(b) {
    Array.prototype.forEach.call(b.querySelectorAll('a[href^="tel:"]'), function (a) {
      var phone = a.getAttribute('href').slice(4);
      var btn = el('button', a.className, '복사');
      btn.type = 'button';
      btn.addEventListener('click', function () { copyText(btn, phone); });
      a.replaceWith(btn);
    });
    Array.prototype.forEach.call(b.querySelectorAll('input[data-tablet-assign-memo]'), function (inp) {
      var text = el('div', 'foms-ship-sheet__text', (inp.value || '').trim() || '-');
      inp.replaceWith(text);
      text.after(el('p', 'foms-ship-sheet__hint', '현장 메모는 표에서 고쳐요'));
    });
    var box = b.querySelector('[data-ship-as-log-url]');
    if (box) loadAsLog(box);
  }

  function copyText(btn, text) {
    var done = function (ok) { btn.textContent = ok ? '복사됨' : '복사 실패'; };
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) { done(false); return; }
      navigator.clipboard.writeText(text).then(function () { done(true); }, function (err) {
        console.error('[pc-ship-sheet] 복사 실패:', err);
        done(false);
      });
    } catch (err) {
      console.error('[pc-ship-sheet] 복사 실패:', err);
      done(false);
    }
  }

  async function loadAsLog(box) {
    var url = box.getAttribute('data-ship-as-log-url');
    if (!url) return;
    try {
      var res = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'foms-ship-sheet' } });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var html = await res.text();
      if (!box.isConnected) return;
      box.innerHTML = html;
      Array.prototype.forEach.call(box.querySelectorAll('.as-rchart-field--billing, .as-billing-state'), function (n) { n.remove(); });
      if (!box.querySelector('.as-rchart')) box.innerHTML = '<p class="foms-ship-sheet__muted">AS 기록이 없어요</p>';
    } catch (err) {
      console.error('[pc-ship-sheet] AS 기록 불러오기 실패:', err);
      if (box.isConnected) box.innerHTML = '<p class="foms-ship-sheet__muted">AS 기록을 못 불러왔어요</p>';
    }
  }

  function open(row) {
    ensureDrawer();
    if (openRow) openRow.classList.remove('is-sheet-open');
    openRow = row;
    row.classList.add('is-sheet-open');
    setOpenLink(row);
    drawer.hidden = false;
    load(row);
  }
  function close() {
    loadSeq++;
    if (openRow) openRow.classList.remove('is-sheet-open');
    openRow = null;
    if (drawer) {
      drawer.hidden = true;
      body().textContent = '';
    }
  }

  function showSaveError(text) {
    var foot = body().querySelector('.foms-ship-sheet__foot');
    var msg = body().querySelector('.foms-pc-ship-drawer__err');
    if (!msg) {
      msg = el('p', 'foms-pc-ship-drawer__err');
      msg.setAttribute('role', 'alert');
      if (foot) foot.before(msg); else body().appendChild(msg);
    }
    msg.textContent = text;
  }

  function refreshDay() {
    var shell = window.FOMS_ERP_SHELL;
    if (shell && typeof shell.navigateByShell === 'function') {
      shell.navigateByShell(window.location.pathname + window.location.search + window.location.hash, { bypassCache: true });
      return;
    }
    window.location.reload();
  }

  async function save(btn) {
    var orderId = btn.getAttribute('data-order-id');
    var timeInput = body().querySelector('[data-tablet-assign-time]');
    var payload = { construction_time: timeInput ? timeInput.value.trim() : '' };
    btn.disabled = true;
    try {
      var res = await fetch('/api/erp/shipment/update/' + encodeURIComponent(orderId), {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify(payload),
      });
      if (res.status === 403) { showSaveError('고칠 권한이 없어요'); return; }
      var data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      if (!res.ok || !data || !data.success) {
        showSaveError((data && (data.message || data.error)) || '저장하지 못했어요');
        return;
      }
      close();
      refreshDay();
    } catch (err) {
      console.error('[pc-ship-sheet] 저장 실패:', err);
      showSaveError('연결이 끊겨 저장하지 못했어요');
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener('click', function (ev) {
    if (!isPc()) return;
    var t = ev.target;
    if (!(t instanceof Element)) return;
    if (drawer && drawer.contains(t)) {
      if (t.closest('[data-pc-ship-close], [data-tablet-sheet-action="sheet-cancel"]')) { close(); return; }
      var sv = t.closest('[data-tablet-sheet-action="shipment-save"]');
      if (sv) save(sv);
      return;
    }
    var row = t.closest(ROW_SEL);
    if (!row) { if (openRow && !t.closest('tr.shipment-row, .foms-ship-names, .modal, .dropdown-menu')) close(); return; }
    if (t.closest(SKIP_SEL) || hasSelection()) return;
    if (row === openRow) close(); else open(row);
  });

  document.addEventListener('keydown', function (ev) {
    if (!openRow || !isPc()) return;
    if (ev.key === 'Escape') { close(); return; }
    if (ev.key !== 'ArrowUp' && ev.key !== 'ArrowDown') return;
    var a = document.activeElement;
    if (a && a.closest && a.closest('input, textarea, select, [contenteditable="true"]')) return;
    var rows = Array.prototype.slice.call(document.querySelectorAll(ROW_SEL));
    var next = rows[rows.indexOf(openRow) + (ev.key === 'ArrowDown' ? 1 : -1)];
    if (!next) return;
    ev.preventDefault();
    open(next);
    next.scrollIntoView({ block: 'nearest' });
  });

  document.addEventListener('foms:erp-shell-fragment-swapped', function () {
    if (openRow && !openRow.isConnected) close();
  });
})();
