/**
 * 출고 화면 협력사 희망 시공일 2주 판 — 접기 · 정하기 창 · 끌어 놓기 · 5초 되돌리기.
 * 마크업: templates/shipment/partials/partner_request_board.html · 설계서
 * docs/specs/2026-11-04-shipment-partner-request-board_SPEC.md §2.1 · §2.2 · §2.4.
 *
 * [확정]을 눌러도 5초 동안은 서버에 아무것도 보내지 않는다 — 협력사 푸시는 저장 커밋 직후 나가서
 * 거둘 수 없으니, 되돌리기는 "늦게 보내기"로 한다. 그 사이 화면을 떠나면 keepalive 로 바로 보낸다.
 * shipment-entry.js 가 싣는다. 클릭은 document 위임이라 셸 탭 스왑 뒤에도 다시 붙일 것이 없다.
 */
(function () {
  'use strict';
  if (window.__fomsPartnerRequestBoardBound) return;
  window.__fomsPartnerRequestBoardBound = true;

  var FOLD_KEY = 'foms.partnerRequestBoard.folded';
  var UNDO_MS = 5000;
  var TIMES = ['오전', '오후', '종일'];
  var DOW = ['일', '월', '화', '수', '목', '금', '토'];
  var pending = null;   // { id, date, time, chip, timer }
  var toastTimer = null;
  var dragId = null;

  function board() { return document.querySelector('[data-prb]'); }
  function canSet() { var b = board(); return !!b && b.getAttribute('data-can-set') === '1'; }
  function esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function mdDow(s) {
    if (!s) return '';
    var p = s.split('-'), d = new Date(+p[0], +p[1] - 1, +p[2]);
    return s.slice(5) + ' (' + DOW[d.getDay()] + ')';
  }
  function isOff(s) {
    var c = cellOf(s);
    if (c) return c.classList.contains('is-off');
    var p = s.split('-'), w = new Date(+p[0], +p[1] - 1, +p[2]).getDay();
    return w === 0 || w === 6;
  }
  function cellOf(s) { return s ? document.querySelector('[data-prb-cell="' + s + '"]') : null; }
  function chipData(chip) {
    return {
      id: chip.getAttribute('data-prb-chip'), name: chip.getAttribute('data-name') || '',
      hope: chip.getAttribute('data-hope') || '', time: chip.getAttribute('data-time') || '',
      units: parseFloat(chip.getAttribute('data-units') || '0') || 0,
      product: chip.getAttribute('data-product') || '', address: chip.getAttribute('data-address') || '',
      partner: chip.getAttribute('data-partner') || (board() && board().getAttribute('data-partner')) || '협력사'
    };
  }

  function init() {
    var b = board();
    if (!b) return;
    var folded = false;
    try { folded = window.localStorage.getItem(FOLD_KEY) === '1'; } catch (e) { folded = false; }
    b.classList.toggle('is-folded', folded);
    var btn = b.querySelector('[data-prb-fold]');
    if (btn) btn.setAttribute('aria-expanded', folded ? 'false' : 'true');
    [].forEach.call(b.querySelectorAll('[data-prb-fill]'), function (el) {
      el.style.setProperty('--prb-fill', (parseInt(el.getAttribute('data-prb-fill'), 10) || 0) + '%');
    });
  }

  // ── 알림 ──
  function hideToast() { clearTimeout(toastTimer); var t = document.getElementById('prb-toast'); if (t) t.remove(); }
  function toast(msg, undoable, ms) {
    hideToast();
    var el = document.createElement('div');
    el.className = 'prb-toast'; el.id = 'prb-toast'; el.setAttribute('role', 'status');
    el.innerHTML = '<span>' + esc(msg) + '</span>' + (undoable ? '<button type="button" data-prb-undo>되돌리기</button>' : '');
    document.body.appendChild(el);
    if (ms) toastTimer = setTimeout(hideToast, ms);
  }

  // ── 정하기 창 ──
  function closePop() { var p = document.getElementById('prb-pop'); if (p) p.remove(); }
  function loadText(it, s) {
    if (!s) return { text: '날짜를 골라 주세요.', tight: false };
    var c = cellOf(s), tightAt = parseFloat((board() && board().getAttribute('data-tight')) || '15');
    var text = mdDow(s), tight = false;
    if (c) {
      var n = parseFloat(c.getAttribute('data-remaining') || '0') - (s !== it.hope ? it.units : 0);
      n = Math.round(n * 10) / 10;
      tight = n < tightAt;
      text += ' 남은 자수 ' + n + (n < 0 ? ' — 자수가 넘쳐요' : tight ? ' — 거의 찼어요' : '');
    }
    if (c && c.getAttribute('data-holiday') === '1') text += ' · 휴일이에요';
    else if (isOff(s)) text += ' · ' + mdDow(s).slice(-2, -1) + '요일이에요';
    return { text: text, tight: tight };
  }
  function openPop(chip, preset) {
    closePop();
    var it = chipData(chip), date = preset || it.hope || '';
    var pop = document.createElement('div');
    pop.className = 'prb-pop'; pop.id = 'prb-pop'; pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', '#' + it.id + ' 시공일 정하기');
    pop.innerHTML =
      '<div class="prb-pop__title">#' + esc(it.id) + ' ' + esc(it.name) + ' 시공일 정하기</div>' +
      '<div class="prb-muted">' + esc([it.product && it.product + ' ' + it.units + '자', it.address].filter(Boolean).join(' · ')) +
      ' · 희망 ' + (it.hope ? mdDow(it.hope) : '날짜 없음') + (it.time ? ' ' + esc(it.time) : '') + '</div>' +
      '<div class="prb-pop__row"><label for="prb-pop-date">날짜</label><input id="prb-pop-date" type="date" class="form-control form-control-sm" data-prb-pop-date value="' + esc(date) + '"></div>' +
      '<div class="prb-pop__row"><label>시간</label><div class="prb-seg" data-prb-pop-time>' +
      TIMES.map(function (t) { return '<button type="button" class="' + (it.time === t ? 'is-on' : '') + '">' + t + '</button>'; }).join('') + '</div></div>' +
      '<div class="prb-pop__load" data-prb-pop-load></div>' +
      '<div class="prb-muted">확정하면 ' + esc(it.partner) + '에 시공일 안내가 가요.</div>' +
      '<div class="prb-pop__btns"><button type="button" class="btn btn-sm btn-outline-secondary" data-prb-pop-close>닫기</button>' +
      '<button type="button" class="btn btn-sm btn-primary" data-prb-pop-ok>확정</button></div>';
    document.body.appendChild(pop);
    var r = chip.getBoundingClientRect();
    pop.style.left = Math.max(8, Math.min(window.scrollX + r.left, window.scrollX + document.documentElement.clientWidth - 336)) + 'px';
    pop.style.top = (window.scrollY + r.bottom + 6) + 'px';
    var input = pop.querySelector('[data-prb-pop-date]');
    function refresh() {
      var l = loadText(it, input.value), el = pop.querySelector('[data-prb-pop-load]');
      el.textContent = l.text; el.classList.toggle('is-tight', l.tight);
      pop.querySelector('[data-prb-pop-ok]').disabled = !input.value;
    }
    input.addEventListener('input', refresh); input.addEventListener('change', refresh);
    pop.querySelector('[data-prb-pop-time]').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      [].forEach.call(this.children, function (c) { c.classList.toggle('is-on', c === b && !c.classList.contains('is-on')); });
    });
    pop.querySelector('[data-prb-pop-close]').addEventListener('click', closePop);
    pop.querySelector('[data-prb-pop-ok]').addEventListener('click', function () {
      var on = pop.querySelector('[data-prb-pop-time] .is-on');
      schedule(chip, it, input.value, on ? on.textContent : '');
    });
    refresh();
    input.focus();
  }

  // ── 5초 늦게 보내기 ──
  function schedule(chip, it, date, time) {
    if (!date) return;
    closePop();
    if (pending) flush(false);   // 앞 건은 바로 보낸다(되돌리기 기회는 하나만).
    chip.classList.add('is-saving');
    pending = { id: it.id, name: it.name, partner: it.partner, date: date, time: time, chip: chip };
    pending.timer = setTimeout(function () { flush(false); }, UNDO_MS);
    toast('#' + it.id + ' ' + it.name + ' 시공일을 ' + mdDow(date) + (time ? ' ' + time : '') + '로 정해요 · 5초 뒤 저장', true);
  }
  function undo() {
    if (!pending) return;
    clearTimeout(pending.timer);
    pending.chip.classList.remove('is-saving');
    pending = null;
    toast('되돌렸어요. 저장하지 않았어요.', false, 2500);
  }
  function flush(leaving) {
    var job = pending;
    if (!job) return;
    clearTimeout(job.timer);
    pending = null;
    var req = fetch('/api/erp/shipment/partner-requests/' + encodeURIComponent(job.id) + '/confirm', {
      method: 'POST', credentials: 'same-origin', keepalive: true,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ date: job.date, time: job.time })
    });
    if (leaving) return;
    req.then(function (res) { return res.json().then(function (data) { return { status: res.status, data: data }; }); })
      .then(function (r) {
        if (r.data && r.data.success === true) {
          var d = r.data.data || {};
          toast('#' + job.id + ' ' + job.name + ' 시공일을 ' + mdDow(d.date) + (d.time ? ' ' + d.time : '') + '로 정했어요. ' + job.partner + '에 알림이 갔어요.', false);
          setTimeout(function () { window.location.reload(); }, 1500);
          return;
        }
        job.chip.classList.remove('is-saving');
        toast((r.data && (r.data.error || r.data.message)) || '시공일을 저장하지 못했어요.', false, 5000);
        if (r.status === 409) setTimeout(function () { window.location.reload(); }, 1500);
      })
      .catch(function () {
        job.chip.classList.remove('is-saving');
        toast('시공일을 저장하지 못했어요. 인터넷 연결을 확인해 주세요.', false, 5000);
      });
  }
  window.addEventListener('pagehide', function () { if (pending) flush(true); });

  // ── 이벤트(위임) ──
  document.addEventListener('click', function (e) {
    var t = e.target, el;
    if (t.closest('[data-prb-undo]')) return undo();
    if ((el = t.closest('[data-prb-fold]'))) {
      var b = board(), folded = !b.classList.contains('is-folded');
      b.classList.toggle('is-folded', folded);
      el.setAttribute('aria-expanded', folded ? 'false' : 'true');
      try { window.localStorage.setItem(FOLD_KEY, folded ? '1' : '0'); } catch (err) { /* 저장 못 해도 이번 화면은 접힌다 */ }
      return;
    }
    if ((el = t.closest('[data-prb-more]'))) {
      [].forEach.call(document.querySelectorAll('[data-prb-more-row]'), function (row) { row.classList.remove('d-none'); });
      el.remove();
      return;
    }
    if ((el = t.closest('[data-prb-chip]')) && canSet()) {
      e.preventDefault();
      if (el.classList.contains('is-saving')) return;
      return openPop(el, '');
    }
    if (!t.closest('#prb-pop')) closePop();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closePop(); });
  document.addEventListener('dragstart', function (e) {
    var c = e.target.closest && e.target.closest('[data-prb-chip]');
    if (!c || !canSet()) return;
    dragId = c.getAttribute('data-prb-chip');
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', dragId); } catch (err) { /* 일부 브라우저 */ }
  });
  document.addEventListener('dragover', function (e) {
    var c = e.target.closest && e.target.closest('[data-prb-cell]');
    if (c && dragId) { e.preventDefault(); c.classList.add('is-over'); }
  });
  document.addEventListener('dragleave', function (e) {
    var c = e.target.closest && e.target.closest('[data-prb-cell]');
    if (c) c.classList.remove('is-over');
  });
  document.addEventListener('drop', function (e) {
    var c = e.target.closest && e.target.closest('[data-prb-cell]');
    if (!c || !dragId) return;
    e.preventDefault();
    c.classList.remove('is-over');
    var chip = document.querySelector('[data-prb-chip="' + dragId + '"]');
    dragId = null;
    if (chip) openPop(chip, c.getAttribute('data-prb-cell'));   // 놓기만으로는 저장하지 않는다
  });
  document.addEventListener('dragend', function () { dragId = null; });

  document.addEventListener('foms:erp-shell-fragment-swapped', init);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
