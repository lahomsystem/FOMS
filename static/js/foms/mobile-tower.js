/**
 * 모바일 홈 컨트롤 타워 — '현장 일정' 인라인 swap.
 *  - 주간 타일 클릭 → 해당 날짜 일정 로드 (Task2)
 *  - 실측/시공/AS/전체 탭 → 타입 필터 + 그날 전체 로드 (Task3)
 * 단일 소스: GET /erp/dashboard/field-ops (JSON: html/count/label/queue_href).
 * '내작업' 토글 상태(data-tower-mine)는 fetch에 그대로 반영.
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

  function bindTower(root) {
    var endpoint = root.getAttribute('data-foms-day-endpoint') || '/erp/dashboard/field-ops';
    var listEl = root.querySelector('[data-foms-day-ops-list]');
    var titleEl = root.querySelector('[data-foms-day-title]');
    var queueEl = root.querySelector('[data-foms-day-queue]');
    var tabs = Array.prototype.slice.call(root.querySelectorAll('[data-foms-day-tab]'));
    var tiles = Array.prototype.slice.call(document.querySelectorAll('[data-foms-day-tile]'));

    var state = {
      iso: root.getAttribute('data-day-iso') || '',
      field: 'all',
      mine: (window.FOMS_ERP_MINE_ONLY && window.FOMS_ERP_MINE_ONLY.isActive())
        || root.getAttribute('data-tower-mine') === '1',
    };

    function setTabActive(field) {
      tabs.forEach(function (tab) {
        var on = tab.getAttribute('data-foms-day-tab') === field;
        tab.classList.toggle('is-active', on);
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    }

    function setTileActive(iso) {
      tiles.forEach(function (tile) {
        tile.classList.toggle('is-active', tile.getAttribute('data-iso') === iso);
      });
    }

    function setCounts(data) {
      var map = {
        all: data.count,
        measure: data.measure_count,
        construction: data.construction_count,
        as: data.as_count,
      };
      root.querySelectorAll('[data-foms-tabcount]').forEach(function (span) {
        var key = span.getAttribute('data-foms-tabcount');
        if (map[key] != null) {
          span.textContent = map[key];
        }
      });
    }

    function load() {
      var url = endpoint
        + '?date=' + encodeURIComponent(state.iso)
        + '&field=' + encodeURIComponent(state.field)
        + (state.mine ? '&tower_mine=1' : '');
      if (listEl) {
        listEl.classList.add('is-loading');
      }
      fetch(url, { headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' })
        .then(function (res) { return res.json(); })
        .then(function (res) {
          if (!res || !res.success || !res.data) {
            throw new Error('field-ops load failed');
          }
          var data = res.data;
          if (listEl) {
            listEl.innerHTML = data.html;
          }
          if (titleEl && data.label) {
            titleEl.textContent = '📍 ' + data.label;
          }
          if (queueEl && data.queue_href) {
            queueEl.setAttribute('href', data.queue_href);
            queueEl.textContent = data.count + '건 →';
          }
          setCounts(data);
        })
        .catch(function () {
          /* 실패 시 기존 목록 유지 (증상 숨김 아님: 콘솔로 노출) */
          if (window.console && window.console.warn) {
            window.console.warn('[mobile-tower] field-ops load failed', url);
          }
        })
        .finally(function () {
          if (listEl) {
            listEl.classList.remove('is-loading');
          }
        });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        state.field = tab.getAttribute('data-foms-day-tab') || 'all';
        setTabActive(state.field);
        load();
      });
    });

    tiles.forEach(function (tile) {
      tile.addEventListener('click', function () {
        var iso = tile.getAttribute('data-iso');
        if (!iso) {
          return;
        }
        state.iso = iso;
        state.field = 'all';
        setTabActive('all');
        setTileActive(iso);
        load();
        if (root.scrollIntoView) {
          root.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });

    return {
      root: root,
      setMine: function (active) {
        state.mine = active;
        root.setAttribute('data-tower-mine', active ? '1' : '0');
        load();
      },
    };
  }

  function initTower() {
    var root = document.querySelector('[data-foms-day-ops]');
    if (!root) {
      activeTower = null;
      return;
    }
    if (root.dataset.fomsTowerBound === '1') {
      return;
    }
    root.dataset.fomsTowerBound = '1';
    activeTower = bindTower(root);
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
