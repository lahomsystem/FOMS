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
  // ERR-UX-01: 공용 mutation 에러 parser.
  //   production/tablet/construction 쓰기 호출이 각자 ad-hoc 으로 처리하던 실패
  //   (timeout·네트워크 오류·malformed JSON·403·409·428)를 한 곳에서 분류한다.
  //   window.fomsMutationFetch(url, opts) 는 절대 reject 하지 않고 항상
  //   { ok, kind, status, data, message } 를 resolve 한다 — 호출자는 result.ok
  //   만 보면 되므로 무음 실패(누락된 catch)가 구조적으로 불가능해진다.
  //     kind: 'ok' | 'queued'(오프라인 큐 적재) | 'timeout' | 'network' |
  //           'malformed' | '403' | '409' | '428' | 'error'(기타 4xx/5xx)
  //   API policy/state 는 건드리지 않는다 — 서버 응답을 그대로 분류만 한다
  //   (API-ERROR-01 의 {success,error|message} 4xx 형식과 정합).
  // ------------------------------------------------------------------
  window.FOMS_MUTATION_TIMEOUT_MS = 15000;

  var STATUS_MESSAGES = {
    403: '권한이 없습니다.',
    409: '다른 요청과 충돌했습니다. 새로고침 후 다시 시도하세요.',
    428: '최신 정보가 아닙니다. 새로고침 후 다시 시도하세요.'
  };

  // 서버 4xx 응답은 {error: string}(신규) 와 {message: string}(레거시)이 혼재한다 —
  // 둘 다 지원(API-ERROR-01 은 500 만 통일했고 4xx 도메인 매핑은 보존했다).
  function extractServerMessage(data) {
    if (!data) return '';
    if (typeof data.error === 'string' && data.error) return data.error;
    if (data.error && typeof data.error === 'object' && data.error.message) return data.error.message;
    if (typeof data.message === 'string' && data.message) return data.message;
    return '';
  }

  window.fomsMutationFetch = function (url, opts) {
    opts = opts || {};
    var timeoutMs = opts.timeoutMs || window.FOMS_MUTATION_TIMEOUT_MS;
    var controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timer = null;
    var fetchOpts = opts;
    if (controller) {
      fetchOpts = {};
      for (var k in opts) { if (opts.hasOwnProperty(k)) fetchOpts[k] = opts[k]; }
      if (!fetchOpts.signal) fetchOpts.signal = controller.signal;
      timer = setTimeout(function () { controller.abort(); }, timeoutMs);
    }
    var clearTimer = function () { if (timer) clearTimeout(timer); };

    return window.fomsWriteFetch(url, fetchOpts).then(function (res) {
      clearTimer();
      if (res && res.queued) {
        return { ok: true, kind: 'queued', status: 0, data: {}, message: '' };
      }
      return res.json().catch(function () { return null; }).then(function (data) {
        if (data === null) {
          return { ok: false, kind: 'malformed', status: res.status, data: {}, message: '서버 응답을 해석하지 못했습니다.' };
        }
        if (res.ok && data.success !== false) {
          return { ok: true, kind: 'ok', status: res.status, data: data, message: '' };
        }
        var kind = (res.status === 403 || res.status === 409 || res.status === 428) ? String(res.status) : 'error';
        var message = extractServerMessage(data) || STATUS_MESSAGES[res.status] || ('처리에 실패했습니다. (HTTP ' + res.status + ')');
        return { ok: false, kind: kind, status: res.status, data: data, message: message };
      });
    }).catch(function (err) {
      clearTimer();
      if (err && err.name === 'AbortError') {
        return { ok: false, kind: 'timeout', status: 0, data: {}, message: '요청 시간이 초과되었습니다. 다시 시도하세요.' };
      }
      return { ok: false, kind: 'network', status: 0, data: {}, message: '네트워크 오류가 발생했습니다. 다시 시도하세요.' };
    });
  };

  // ------------------------------------------------------------------
  // sync 배지 컨트롤러 (헤더 [data-foms-sync-badge]).
  //   - 0건        → 숨김
  //   - 대기 N건   → warn (색+텍스트)
  //   - 전송 실패  → danger (flush 실패 신호를 받은 뒤)
  // ------------------------------------------------------------------
  var lastFailed = false;

  // 배지는 다중 존재 가능(v2 셸 헤더 + v3 앱바). 두 셸이 한 페이지에 공존하진 않지만
  // querySelectorAll 로 전수 갱신해 셸 종류와 무관하게 동일 3상태 계약을 적용한다.
  function badgeEls() {
    return document.querySelectorAll('[data-foms-sync-badge]');
  }

  function paint(count) {
    if (!count) lastFailed = false;
    badgeEls().forEach(function (el) {
      if (!count) {
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
    });
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
