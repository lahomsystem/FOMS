/**
 * B7 공용 쓰기 래퍼 + sync 배지 컨트롤러.
 *
 * window.fomsWriteFetch(url, opts):
 *   - fetch 시도. HTTP 응답(성공/4xx/5xx)은 그대로 반환한다.
 *   - 네트워크 실패(TypeError)면 오프라인 게이트 활성 시 sync.js 큐(fomsOfflineEnqueueRequest)
 *     에 적재하고 { queued: true } 를 반환 + foms:sync-changed 이벤트를 발행한다.
 *     게이트 off(운영 기본)면 원 에러를 그대로 재throw 한다.
 *
 * window.fomsSyncPendingCount(): IndexedDB pending-writes 큐 항목 수(Promise<number>).
 *   sync.js 는 openDb/count 를 export 하지 않으므로 동일 DB(name/store/version)를 소형 open 한다.
 *
 * v2 셸 헤더의 sync 배지([data-foms-sync-badge], 3상태: 숨김/대기 N건/전송 실패)를
 * foms:sync-changed·online·visibilitychange 에 맞춰 갱신한다.
 * ERP shell fragment 재실행 대비 window.__FOMS_WRITE_BOUND 싱글톤 가드(perf guard G4).
 */
(function () {
  'use strict';

  // sync.js 와 동일한 오프라인 큐 DB (SSOT: DB_NAME/STORE/version 일치).
  var DB_NAME = 'foms-offline-v1';
  var STORE = 'pending-writes';

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        if (!req.result.objectStoreNames.contains(STORE)) {
          req.result.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  // 큐 항목 수 — 배지 카운트 SSOT. 어떤 실패도 0 으로 안전 폴백(배지는 부가정보라 무해).
  window.fomsSyncPendingCount = function () {
    if (!('indexedDB' in window)) return Promise.resolve(0);
    return openDb().then(function (db) {
      return new Promise(function (resolve) {
        try {
          var tx = db.transaction(STORE, 'readonly');
          var req = tx.objectStore(STORE).count();
          req.onsuccess = function () { resolve(req.result || 0); };
          req.onerror = function () { resolve(0); };
        } catch (err) {
          resolve(0);
        }
      });
    }).catch(function () { return 0; });
  };

  function dispatchSyncChanged(detail) {
    try {
      window.dispatchEvent(new CustomEvent('foms:sync-changed', { detail: detail || {} }));
    } catch (err) {
      // CustomEvent 미지원 등 — 배지 갱신 실패는 무해(다음 트리거에서 재시도).
    }
  }

  // 공용 쓰기 래퍼. 오프라인(네트워크 실패)일 때만 큐 적재로 폴백한다.
  window.fomsWriteFetch = function (url, opts) {
    opts = opts || {};
    return fetch(url, opts).catch(function (err) {
      var offline = window.fomsOfflineEnabled && window.fomsOfflineEnabled();
      if (err instanceof TypeError && offline && window.fomsOfflineEnqueueRequest) {
        return window.fomsOfflineEnqueueRequest(url, opts).then(function () {
          dispatchSyncChanged({ source: 'enqueue' });
          return { queued: true };
        });
      }
      throw err;
    });
  };

  // ------------------------------------------------------------------
  // sync 배지 컨트롤러 (헤더 [data-foms-sync-badge]).
  //   - 0건        → 숨김
  //   - 대기 N건   → warn (색+텍스트)
  //   - 전송 실패  → danger (flush 실패 신호를 받은 뒤)
  // ------------------------------------------------------------------
  var lastFailed = false;

  function badgeEl() {
    return document.querySelector('[data-foms-sync-badge]');
  }

  function paint(count) {
    var el = badgeEl();
    if (!el) return;
    if (!count) {
      lastFailed = false;
      el.hidden = true;
      el.textContent = '';
      el.classList.remove('foms-sync-badge--warn', 'foms-sync-badge--danger');
      return;
    }
    el.hidden = false;
    if (lastFailed) {
      el.textContent = '전송 실패';
      el.classList.add('foms-sync-badge--danger');
      el.classList.remove('foms-sync-badge--warn');
    } else {
      el.textContent = '대기 ' + count + '건';
      el.classList.add('foms-sync-badge--warn');
      el.classList.remove('foms-sync-badge--danger');
    }
  }

  function refresh() {
    if (!window.fomsSyncPendingCount) return;
    window.fomsSyncPendingCount().then(paint);
  }

  function onSyncChanged(ev) {
    var detail = (ev && ev.detail) || {};
    if (detail.failed) {
      lastFailed = true;
    } else if (detail.source === 'enqueue') {
      lastFailed = false;
    }
    refresh();
  }

  if (window.__FOMS_WRITE_BOUND) return;
  window.__FOMS_WRITE_BOUND = true;

  window.addEventListener('foms:sync-changed', onSyncChanged);
  window.addEventListener('online', refresh);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) refresh();
  });
  document.addEventListener('DOMContentLoaded', refresh);
  // deferred 로드가 DOMContentLoaded 이후에 실행될 수 있어 즉시 1회 동기화.
  if (document.readyState !== 'loading') refresh();
})();
