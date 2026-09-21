/**
 * 관리자 강제 진행 재시도 컨트롤러 (ADMIN-OVERRIDE-01 C8).
 *
 * 업무 게이트에 막힌 응답(409/400/403)을 받은 화면이 이 함수 하나를 부른다.
 * 관리자면 공용 사유 시트를 띄워 사유를 받고, 같은 요청에
 * {admin_override: true, override_reason: "<사유>"} 를 실어 딱 한 번 다시 보낸다.
 *
 * 절대 뚫지 않는 것(권한 축이 아니라 정합 축이다):
 *   - If-Match / REV 충돌 409 (헤더는 원래 값 그대로 다시 보낸다)
 *   - ALREADY_STARTED 같은 중복 발급 계열
 *   - ADMIN_ONLY / REASON_REQUIRED (뚫기 자체가 거부된 응답)
 *   - 재시도 응답이 또 거부일 때 (2차 재시도 없음)
 *
 * 공개 API:
 *   window.FomsAdminOverride.canOverride()
 *   window.FomsAdminOverride.retry({url, method, headers, body, code, message, title})
 *     -> Promise<{retried, ok, status, data, reason}>
 *
 * 마크업은 templates/partials/shared/foms_reason_sheet.html 이고 컨트롤러는
 * static/js/foms/foms-reason-sheet.js 다. 둘 중 하나라도 없으면 무음으로
 * 넘어가지 않고 {retried:false, reason:'no-sheet'} 를 돌려준다.
 */
(function () {
  'use strict';

  var SHEET_SEL = '[data-foms-reason-sheet]';

  // 사유를 받아 다시 보낼 수 있는 거부 코드. 이 밖은 손대지 않는다.
  var RETRYABLE_CODES = [
    'USE_CS_COMPLETE',
    'INVALID_STAGE',
    'QUEST_INCOMPLETE',
    'HOLD_ACTIVE',
    'AS_ACTIVE',
    'COMMAND_REQUIRED',
    'DRAWING_STATUS',
    'EVIDENCE_MISSING',
    'OVERRIDE_BLOCK'
  ];

  function canOverride() {
    return String(window.MY_ROLE || '').toUpperCase() === 'ADMIN';
  }

  function isRetryable(code) {
    var c = String(code || '').trim().toUpperCase();
    if (!c) {
      return false;
    }
    return RETRYABLE_CODES.indexOf(c) !== -1;
  }

  // 재시도 본문은 원래 본문과 달라진다 — 같은 멱등 키를 다시 쓰면 서버가
  // request_hash 불일치로 409 를 낸다. 그래서 키를 새로 만든다.
  function newIdempotencyKey() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
      }
    } catch (_) { /* 구형 브라우저는 아래 대체 경로 */ }
    return 'ovr-' + Date.now() + '-' + Math.random().toString(16).slice(2, 10);
  }

  function cloneHeaders(headers) {
    var out = {};
    var src = headers || {};
    Object.keys(src).forEach(function (k) {
      if (String(k).toLowerCase() === 'idempotency-key') {
        return;
      }
      out[k] = src[k];
    });
    if (!out['Content-Type']) {
      out['Content-Type'] = 'application/json';
    }
    return out;
  }

  function cloneBody(body) {
    var out = {};
    if (body && typeof body === 'object') {
      Object.keys(body).forEach(function (k) {
        out[k] = body[k];
      });
    }
    return out;
  }

  /**
   * 사유 시트를 띄우고 사용자가 적은 사유를 돌려준다(취소하면 빈 문자열).
   * 시트에는 취소 콜백이 없어서 hidden 속성 변화를 지켜본다.
   */
  function askReason(opts) {
    return new Promise(function (resolve) {
      var sheet = document.querySelector(SHEET_SEL);
      if (!sheet || !window.FomsReasonSheet || typeof window.FomsReasonSheet.open !== 'function') {
        resolve(null);
        return;
      }
      var settled = false;
      var observer = null;

      function finish(value) {
        if (settled) {
          return;
        }
        settled = true;
        if (observer) {
          observer.disconnect();
        }
        resolve(value);
      }

      var label = '사유(필수)';
      if (opts.message) {
        label = label + ' — ' + opts.message;
      }

      window.FomsReasonSheet.open({
        title: opts.title || '관리자 권한으로 진행',
        actionLabel: '사유 적고 강제 진행',
        reasons: null,
        detailLabel: label,
        // 빈 사유 제출은 시트가 막는다 — 그래야 아래 hidden 감시가 오직 '취소' 만 잡는다.
        requireDetail: true,
        onSubmit: function (_reason, detail) {
          finish(String(detail || '').trim());
        }
      });

      if (typeof window.MutationObserver === 'function') {
        observer = new window.MutationObserver(function () {
          if (sheet.hidden) {
            finish('');
          }
        });
        observer.observe(sheet, { attributes: true, attributeFilter: ['hidden'] });
      }
    });
  }

  /**
   * 거부 응답을 받은 호출부가 부르는 재시도 진입점.
   * @param {Object} opts url·method·headers·body·code·message·title
   * @returns {Promise<Object>} {retried, ok, status, data, reason}
   */
  function retry(opts) {
    var options = opts || {};
    if (!canOverride()) {
      return Promise.resolve({ retried: false, reason: 'not-admin' });
    }
    if (!isRetryable(options.code)) {
      return Promise.resolve({ retried: false, reason: 'not-retryable' });
    }
    if (!document.querySelector(SHEET_SEL)) {
      return Promise.resolve({ retried: false, reason: 'no-sheet' });
    }

    return askReason({ title: options.title, message: options.message }).then(function (reason) {
      if (reason === null) {
        return { retried: false, reason: 'no-sheet' };
      }
      if (!reason) {
        return { retried: false, reason: 'cancelled' };
      }

      var headers = cloneHeaders(options.headers);
      headers['Idempotency-Key'] = newIdempotencyKey();
      var body = cloneBody(options.body);
      body.admin_override = true;
      body.override_reason = reason;
      if (Object.prototype.hasOwnProperty.call(body, 'idempotency_key')) {
        body.idempotency_key = headers['Idempotency-Key'];
      }

      return sendOnce(options, headers, body, reason);
    });
  }

  // 딱 한 번만 다시 보낸다. 또 거부면 그대로 돌려준다(2차 재시도 없음).
  function sendOnce(options, headers, body, reason) {
    return fetch(options.url, {
      method: String(options.method || 'POST').toUpperCase(),
      headers: headers,
      body: JSON.stringify(body)
    })
      .then(function (res) {
        return res.json()
          .catch(function () { return null; })
          .then(function (data) {
            var ok = !!(res.ok && data && data.success);
            return {
              retried: true,
              ok: ok,
              status: res.status,
              data: data,
              reason: reason
            };
          });
      })
      .catch(function (err) {
        return {
          retried: true,
          ok: false,
          status: 0,
          data: null,
          reason: reason,
          error: String((err && err.message) || err || '네트워크 오류')
        };
      });
  }

  window.FomsAdminOverride = {
    canOverride: canOverride,
    retry: retry,
    RETRYABLE_CODES: RETRYABLE_CODES.slice()
  };
})();
