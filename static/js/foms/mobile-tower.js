/**
 * 모바일 홈 컨트롤 타워 — 월간 현장 달력 + 그날 현장 시트.
 *  - 달력 ‹ › / 이번 달 → GET /erp/dashboard/field-calendar?month=YYYY-MM (달력 조각 swap)
 *  - 날짜 칸·[오늘 목록] → 시트 열기 + GET /erp/dashboard/field-ops (목록 조각 swap)
 *  - 시트 ‹ › = 하루 이동, 탭 = 종류 필터, 닫기 = 배경·닫기 버튼·Esc
 * '내작업' 토글 상태(data-tower-mine)는 두 fetch 에 그대로 반영.
 * 근거: docs/specs/2026-10-14-mobile-home-month-calendar_SPEC.md
 *
 * 셸 공용 스크립트라 문서당 한 번만 실행된다(erp-shell.js data-foms-run-once). 탭 스왑으로 새 타워가
 * 들어오면 foms:main-content-swapped 에서 다시 연결한다 — 예전엔 스왑마다 파일 전체를 다시 실행해 연결했다.
 */
(function () {
  'use strict';

  if (window.__FOMS_MOBILE_TOWER_BOUND) {
    return;
  }
  window.__FOMS_MOBILE_TOWER_BOUND = true;

  /** 지금 화면의 타워 제어기. 타워가 없는 화면으로 가면 비워서 옛 DOM 을 붙잡지 않는다. */
  var activeTower = null;

  function getJson(url) {
    return fetch(url, { headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' })
      .then(function (res) { return res.json(); })
      .then(function (res) {
        if (!res || !res.success || !res.data) {
          throw new Error('mobile-tower load failed');
        }
        return res.data;
      });
  }

  function warn(url) {
    /* 실패 시 기존 화면 유지 (증상 숨김 아님: 콘솔로 노출) */
    if (window.console && window.console.warn) {
      window.console.warn('[mobile-tower] load failed', url);
    }
  }

  function shiftIso(iso, days) {
    var parts = iso.split('-');
    var d = new Date(Date.UTC(+parts[0], +parts[1] - 1, +parts[2] + days));
    return d.toISOString().slice(0, 10);
  }

  function bindTower(tower, sheet) {
    var endpoint = sheet.getAttribute('data-foms-day-endpoint') || '/erp/dashboard/field-ops';
    var calRoot = tower.querySelector('[data-foms-cal-root]');
    var calEndpoint = (calRoot && calRoot.getAttribute('data-foms-cal-endpoint')) || '/erp/dashboard/field-calendar';
    var listEl = sheet.querySelector('[data-foms-day-ops-list]');
    var titleEl = sheet.querySelector('[data-foms-day-title]');
    var todayBadge = sheet.querySelector('[data-foms-day-today]');
    var amountEl = sheet.querySelector('[data-foms-day-amount]');
    var queueEl = sheet.querySelector('[data-foms-day-queue]');
    var tabs = Array.prototype.slice.call(sheet.querySelectorAll('[data-foms-day-tab]'));

    var state = {
      iso: sheet.getAttribute('data-day-iso') || '',
      field: 'all',
      mine: (window.FOMS_ERP_MINE_ONLY && window.FOMS_ERP_MINE_ONLY.isActive())
        || sheet.getAttribute('data-tower-mine') === '1',
      opener: null,
      seq: 0,
    };

    function mineQuery() {
      return state.mine ? '&tower_mine=1' : '';
    }

    function markActiveCell() {
      tower.querySelectorAll('.foms-tower__cal-cell[data-iso]').forEach(function (cell) {
        cell.classList.toggle('is-active', !sheet.hidden && cell.getAttribute('data-iso') === state.iso);
      });
    }

    function setTabActive(field) {
      tabs.forEach(function (tab) {
        var on = tab.getAttribute('data-foms-day-tab') === field;
        tab.classList.toggle('is-active', on);
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    }

    function setCounts(data) {
      var map = {
        all: data.count,
        measure: data.measure_count,
        construction: data.construction_count,
        as: data.as_count,
      };
      sheet.querySelectorAll('[data-foms-tabcount]').forEach(function (span) {
        var key = span.getAttribute('data-foms-tabcount');
        if (map[key] != null) {
          span.textContent = map[key];
        }
      });
    }

    function loadDay() {
      var url = endpoint
        + '?date=' + encodeURIComponent(state.iso)
        + '&field=' + encodeURIComponent(state.field)
        + mineQuery();
      var seq = ++state.seq;
      if (listEl) {
        listEl.classList.add('is-loading');
      }
      getJson(url)
        .then(function (data) {
          if (seq !== state.seq) {
            return; /* 더 늦게 누른 날짜·탭의 응답만 반영 */
          }
          if (listEl) {
            listEl.innerHTML = data.html;
            listEl.scrollTop = 0;
          }
          if (titleEl && data.label) {
            titleEl.textContent = data.label;
          }
          if (todayBadge) {
            todayBadge.hidden = !data.is_today;
          }
          if (amountEl && data.amount_label) {
            amountEl.textContent = data.amount_label;
          }
          if (queueEl && data.queue_href) {
            queueEl.setAttribute('href', data.queue_href);
            queueEl.textContent = '작업 큐에서 ' + data.count + '건 보기 →';
          }
          setCounts(data);
        })
        .catch(function () { warn(url); })
        .finally(function () {
          if (listEl && seq === state.seq) {
            listEl.classList.remove('is-loading');
          }
        });
    }

    function loadMonth(month) {
      if (!calRoot) {
        return;
      }
      var url = calEndpoint + '?month=' + encodeURIComponent(month || '') + mineQuery();
      calRoot.classList.add('is-loading');
      getJson(url)
        .then(function (data) {
          calRoot.innerHTML = data.html;
          markActiveCell();
        })
        .catch(function () { warn(url); })
        .finally(function () { calRoot.classList.remove('is-loading'); });
    }

    function currentMonth() {
      var cal = calRoot && calRoot.querySelector('[data-foms-cal]');
      return cal ? cal.getAttribute('data-month') || '' : '';
    }

    function openSheet(iso, opener) {
      state.iso = iso;
      state.field = 'all';
      state.opener = opener || null;
      setTabActive('all');
      sheet.hidden = false;
      document.body.classList.add('foms-tower-sheet-open');
      markActiveCell();
      loadDay();
      var closeBtn = sheet.querySelector('.foms-tower__sheet-icon[data-foms-sheet-close]');
      if (closeBtn) {
        closeBtn.focus();
      }
    }

    function closeSheet() {
      if (sheet.hidden) {
        return;
      }
      sheet.hidden = true;
      document.body.classList.remove('foms-tower-sheet-open');
      markActiveCell();
      if (state.opener && state.opener.isConnected) {
        state.opener.focus();
      }
    }

    tower.addEventListener('click', function (ev) {
      var tile = ev.target.closest('[data-foms-day-tile]');
      if (tile && tile.getAttribute('data-iso')) {
        openSheet(tile.getAttribute('data-iso'), tile);
        return;
      }
      var monthBtn = ev.target.closest('[data-foms-cal-month]');
      if (monthBtn && !monthBtn.disabled) {
        loadMonth(monthBtn.getAttribute('data-foms-cal-month'));
      }
    });

    sheet.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-foms-sheet-close]')) {
        closeSheet();
        return;
      }
      var step = ev.target.closest('[data-foms-day-step]');
      if (step && state.iso) {
        state.iso = shiftIso(state.iso, parseInt(step.getAttribute('data-foms-day-step'), 10) || 0);
        markActiveCell();
        loadDay();
        return;
      }
      var tab = ev.target.closest('[data-foms-day-tab]');
      if (tab) {
        state.field = tab.getAttribute('data-foms-day-tab') || 'all';
        setTabActive(state.field);
        loadDay();
      }
    });

    sheet.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        closeSheet();
      }
    });

    return {
      root: tower,
      setMine: function (active) {
        state.mine = active;
        sheet.setAttribute('data-tower-mine', active ? '1' : '0');
        loadMonth(currentMonth());
        if (!sheet.hidden) {
          loadDay();
        }
      },
    };
  }

  function initTower() {
    var root = document.querySelector('[data-foms-tower]');
    var sheet = root ? root.querySelector('[data-foms-day-ops]') : null;
    if (!root) {
      activeTower = null;
      /* 시트를 연 채 다른 탭으로 가면 스크롤 잠금만 남는다 — 타워가 없으면 푼다. */
      document.body.classList.remove('foms-tower-sheet-open');
      return;
    }
    if (root.dataset.fomsTowerBound === '1' || !sheet) {
      return;
    }
    root.dataset.fomsTowerBound = '1';
    activeTower = bindTower(root, sheet);
  }

  window.__FOMS_MOBILE_TOWER_ON_MINE_CHANGED = function (active) {
    if (activeTower && activeTower.root.isConnected) {
      activeTower.setMine(active);
    }
  };

  // 옛 버전과 같은 가드 이름을 유지한다 — 배포 직후 열린 창에서 옛·새 파일이 겹쳐도 리스너는 하나.
  if (!window.__FOMS_MOBILE_TOWER_MINE_BOUND) {
    window.__FOMS_MOBILE_TOWER_MINE_BOUND = true;
    document.addEventListener('foms:erp-mine-only-changed', function (ev) {
      var handler = window.__FOMS_MOBILE_TOWER_ON_MINE_CHANGED;
      if (typeof handler !== 'function') {
        return;
      }
      var active = ev && ev.detail
        ? !!ev.detail.active
        : !!(window.FOMS_ERP_MINE_ONLY && window.FOMS_ERP_MINE_ONLY.isActive());
      handler(active);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTower);
  } else {
    initTower();
  }
  document.addEventListener('foms:main-content-swapped', initTower);
})();
