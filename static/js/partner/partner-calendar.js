/**
 * 협력사 시공 달력 — 날짜 칸을 누르면 그날 내 회사 주문 시트(우리 모바일 홈 달력과 같은 시트).
 * 목록은 서버가 날마다 <template data-pp-day-list="YYYY-MM-DD"> 로 미리 싣는다(그 달 것만) — 여기서는 옮기기만 한다.
 * 템플릿: templates/partner/partials/construction_calendar.html · calendar_day_sheet.html
 */
(function () {
  'use strict';

  var DOW = ['일', '월', '화', '수', '목', '금', '토'];

  function label(iso) {
    var p = iso.split('-');
    var d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
    return Number(p[1]) + '월 ' + Number(p[2]) + '일 (' + DOW[d.getDay()] + ')';
  }

  function init() {
    var cal = document.querySelector('[data-pp-cal]');
    var sheet = document.querySelector('[data-pp-day-sheet]');
    if (!cal || !sheet) {
      return;
    }
    var body = sheet.querySelector('[data-pp-day-body]');
    var tiles = Array.prototype.slice.call(cal.querySelectorAll('[data-pp-day-tile]'));
    var state = { index: -1, opener: null };

    function fill(sel, text) {
      var el = sheet.querySelector(sel);
      if (el) {
        el.textContent = text;
      }
      return el;
    }

    function show(index) {
      var tile = tiles[index];
      if (!tile) {
        return;
      }
      state.index = index;
      var iso = tile.getAttribute('data-iso');
      var list = document.querySelector('template[data-pp-day-list="' + iso + '"]')
        || document.querySelector('template[data-pp-day-empty]');
      body.innerHTML = '';
      if (list) {
        body.appendChild(list.content.cloneNode(true));
      }
      body.scrollTop = 0;
      fill('[data-pp-day-title]', label(iso));
      fill('[data-pp-day-own]', String(body.querySelectorAll('.foms-tower__field').length));
      fill('[data-pp-day-count]', tile.getAttribute('data-count') || '0');
      var amount = tile.getAttribute('data-amount') || '';
      fill('[data-pp-day-amount]', amount ? amount + '원' : '');
      sheet.querySelector('[data-pp-day-amount-wrap]').hidden = !amount;
      sheet.querySelector('[data-pp-day-today]').hidden = !tile.classList.contains('is-today');
      sheet.querySelector('[data-pp-day-step="-1"]').disabled = index <= 0;
      sheet.querySelector('[data-pp-day-step="1"]').disabled = index >= tiles.length - 1;
      tiles.forEach(function (t, i) { t.classList.toggle('is-active', i === index); });
    }

    function open(tile) {
      state.opener = tile;
      sheet.hidden = false;
      document.body.classList.add('foms-tower-sheet-open');
      show(tiles.indexOf(tile));
      var close = sheet.querySelector('.foms-tower__sheet-icon[data-pp-sheet-close]');
      if (close) {
        close.focus();
      }
    }

    function close() {
      if (sheet.hidden) {
        return;
      }
      sheet.hidden = true;
      document.body.classList.remove('foms-tower-sheet-open');
      tiles.forEach(function (t) { t.classList.remove('is-active'); });
      if (state.opener && state.opener.isConnected) {
        state.opener.focus();
      }
    }

    // 홈 [오늘 목록] — 달력 칸과 같은 시트(우리 모바일 홈 오늘 목록 단추).
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-pp-day-open]');
      if (!btn) return;
      var tile = cal.querySelector('[data-pp-day-tile][data-iso="' + btn.getAttribute('data-pp-day-open') + '"]');
      if (tile) open(tile);
    });
    cal.addEventListener('click', function (ev) {
      var tile = ev.target.closest('[data-pp-day-tile]');
      if (tile) {
        open(tile);
      }
    });
    sheet.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-pp-sheet-close]')) {
        close();
        return;
      }
      var step = ev.target.closest('[data-pp-day-step]');
      if (step && !step.disabled) {
        show(state.index + Number(step.getAttribute('data-pp-day-step')));
      }
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        close();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
