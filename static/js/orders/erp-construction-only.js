/**
 * 출고팀 주문 화면 — 다 잠그고 시공일 · 시공시간만 연다(설계서 docs/specs/2026-11-04-shipment-partner-request-board_SPEC.md §2.3-b).
 *
 * 서버가 #erp-order-config[data-erp-construction-only="true"] 를 줄 때만 움직인다. 폼 전체 저장(PUT)은 서버가 CS · 영업
 * 전용으로 막고, 이 화면은 [시공일 저장]으로 POST /api/orders/<id>/construction-schedule 만 부른다. 품목 칸처럼 뒤에
 * 그려지는 입력도 MutationObserver 로 같이 잠근다. 시공일을 바꿔서 사유가 필요하면 기존 사유 창(order-change-reason.js)을 띄운다.
 * 시공일이 둘 이상이면 "어느 날을 옮길까요" 고르기를 더해 from_date 를 같이 보낸다(서버가 data-erp-construction-dates 로
 * 날 목록을 줄 때만 — 설계서 docs/specs/2026-11-21-item-construction-done_SPEC.md 8절).
 */
(function () {
  'use strict';
  var config = document.getElementById('erp-order-config');
  if (!config || config.getAttribute('data-erp-construction-only') !== 'true') return;
  if (window.__fomsErpConstructionOnly) return;
  window.__fomsErpConstructionOnly = true;

  var orderId = config.getAttribute('data-order-id');
  var OPEN_IDS = ['erp-construction-date', 'erp-construction-date-open', 'erp-construction-time-select', 'erp-construction-time', 'erp-construction-only-save', 'erp-construction-only-from'];
  var TIMES = ['', '오전', '오후', '종일'];

  function safeJsonParse(val, fb) {
    try { var v = JSON.parse(val); return v == null ? fb : v; } catch (e) { return fb; }
  }
  function splitDates(text) {
    return String(text || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
  }
  // 이 주문의 시공일(YYYY-MM-DD) — 둘 이상일 때만 옮길 날을 고른다.
  var knownDates = safeJsonParse(config.getAttribute('data-erp-construction-dates'), []);
  if (!Array.isArray(knownDates)) knownDates = [];

  function todayIso() {
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function shortLabel(iso) {
    var p = iso.split('-');
    return p.length === 3 ? Number(p[1]) + '/' + Number(p[2]) : iso;
  }
  // 고르기 칸을 날 목록으로 다시 채운다 — 기본값은 오늘 이후 가장 가까운 날(모두 지났으면 마지막 날).
  function fillFromSelect(sel) {
    var today = todayIso();
    var upcoming = knownDates.filter(function (d) { return d >= today; });
    var pick = upcoming.length ? upcoming[0] : knownDates[knownDates.length - 1];
    sel.innerHTML = '';
    knownDates.forEach(function (d) {
      var o = document.createElement('option');
      o.value = d;
      o.textContent = shortLabel(d) + ' (' + d + ')';
      if (d === pick) o.selected = true;
      sel.appendChild(o);
    });
  }
  function fromBox() {
    var wrap = document.getElementById('erp-construction-only-from-wrap');
    if (wrap) wrap.classList.toggle('d-none', knownDates.length < 2);
    return knownDates.length >= 2 ? document.getElementById('erp-construction-only-from') : null;
  }

  function root() { return config.closest('.card') || document.getElementById('main-content') || document.body; }
  function isOpen(el) {
    if (OPEN_IDS.indexOf(el.id) >= 0) return true;
    // 탭 · 접기 단추는 보기 위한 것이라 둔다.
    return !!el.closest('[data-bs-toggle="tab"], [data-bs-toggle="pill"], [data-bs-toggle="collapse"], .nav-link, .flatpickr-calendar');
  }
  function lock(scope) {
    [].forEach.call((scope || root()).querySelectorAll('input, select, textarea, button'), function (el) {
      if (isOpen(el) || el.hasAttribute('data-erp-co-locked')) return;
      el.setAttribute('data-erp-co-locked', '');
      el.disabled = true;
    });
    [].forEach.call((scope || root()).querySelectorAll('[contenteditable="true"]'), function (el) { el.setAttribute('contenteditable', 'false'); });
    var save = document.getElementById('erp-save-btn');
    if (save) save.classList.add('d-none');
  }

  function note(text, isError) {
    var el = document.getElementById('erp-construction-only-msg');
    if (!el) return;
    el.textContent = text;
    el.className = 'small mt-1 ' + (isError ? 'text-danger' : 'text-muted');
  }
  function readTime() {
    if (typeof window.erpReadScheduleTimeValue === 'function') return window.erpReadScheduleTimeValue('erp-construction-time-select', 'erp-construction-time');
    var sel = document.getElementById('erp-construction-time-select');
    return sel ? sel.value : '';
  }
  function save() {
    var dateEl = document.getElementById('erp-construction-date');
    var dates = splitDates(dateEl && dateEl.value);
    var fromSel = fromBox();
    if (fromSel && dates.length > 1) {
      // 날이 여럿인 주문 — 달력에 새로 더한 날 하나가 옮길 새 날이다.
      var added = dates.filter(function (d) { return knownDates.indexOf(d) < 0; });
      if (added.length === 1) dates = added;
    }
    if (dates.length !== 1) {
      note(dates.length ? (fromSel ? '새 시공일을 하루만 골라 주세요.' : '여기서는 시공일을 하루만 정할 수 있어요. 여러 날은 CS팀에 말해 주세요.') : '시공일을 골라 주세요.', true);
      return;
    }
    var payload = { date: dates[0], time: '' };
    if (fromSel && fromSel.value) payload.from_date = fromSel.value;
    var time = String(readTime() || '').trim();
    if (TIMES.indexOf(time) < 0) { note('시간은 오전 · 오후 · 종일 중에서 골라 주세요.', true); return; }
    payload.time = time;
    var btn = document.getElementById('erp-construction-only-save');
    btn.disabled = true;
    note('저장하는 중이에요…', false);
    fetch('/api/orders/' + encodeURIComponent(orderId) + '/construction-schedule', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        btn.disabled = false;
        if (!data || data.success !== true) { note((data && (data.error || data.message)) || '저장하지 못했어요.', true); return; }
        var d = data.data || {};
        note('저장했어요 — 시공일 ' + d.date + (d.time ? ' ' + d.time : ''), false);
        if (fromSel) {
          knownDates = splitDates(d.date);
          var sel = fromBox();
          if (sel) fillFromSelect(sel);
        }
        if (d.change_reason_required === true && d.change_set) {
          document.dispatchEvent(new CustomEvent('foms:change-reason-required', {
            detail: { orderId: orderId, changeSet: d.change_set, mode: 'full' }
          }));
        }
      })
      .catch(function () { btn.disabled = false; note('저장하지 못했어요. 인터넷 연결을 확인해 주세요.', true); });
  }

  function addSave() {
    var timeSel = document.getElementById('erp-construction-time-select');
    if (!timeSel || document.getElementById('erp-construction-only-save')) return;
    [].forEach.call(timeSel.options, function (o) { if (o.value === '__direct__') o.remove(); });
    var wrap = document.createElement('div');
    wrap.className = 'mt-2';
    wrap.innerHTML = '<div id="erp-construction-only-from-wrap" class="mb-2 d-none">' +
      '<label class="form-label small mb-1" for="erp-construction-only-from">어느 날을 옮길까요</label>' +
      '<select class="form-select form-select-sm" id="erp-construction-only-from"></select></div>' +
      '<button type="button" class="btn btn-sm btn-primary" id="erp-construction-only-save">시공일 저장</button>' +
      '<div id="erp-construction-only-msg" class="small mt-1 text-muted">출고팀은 시공일 · 시공시간만 바꿀 수 있어요. 다른 칸은 CS · 영업팀이 고쳐요.</div>';
    var field = timeSel.closest('.col-md-6') || timeSel.parentNode;
    field.appendChild(wrap);
    document.getElementById('erp-construction-only-save').addEventListener('click', save);
    var fromSel = fromBox();
    if (fromSel) fillFromSelect(fromSel);
  }

  function start() {
    addSave();
    lock();
    new MutationObserver(function (records) {
      records.forEach(function (r) { [].forEach.call(r.addedNodes, function (n) { if (n.nodeType === 1) lock(n.parentNode || n); }); });
    }).observe(root(), { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
