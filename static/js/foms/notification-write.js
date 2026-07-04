/**
 * 알림 write 요청 공용 helper.
 *
 * 모든 알림 상태 변경(read/archive/ack/send/urgent-mention/archive-all) POST 는 이 helper 를
 * 경유해 same-origin 증명 헤더(X-FOMS-Notification-Write: 1)를 자동 첨부한다. 서버의
 * require_same_origin_write guard 와 짝을 이뤄, 크로스 사이트 form POST 가 세션 쿠키를
 * 조용히 재사용하는 것을 차단한다.
 *
 * 사용: window.FOMSNotificationWrite.fetch(url, options) -> Promise<Response>
 */
(function () {
  'use strict';

  var HEADER = 'X-FOMS-Notification-Write';

  if (window.FOMSNotificationWrite) {
    return;
  }

  window.FOMSNotificationWrite = {
    /**
     * fetch 래퍼: write 헤더 + credentials same-origin 강제.
     * @param {string} url 요청 URL
     * @param {object} [options] fetch 옵션
     * @returns {Promise<Response>}
     */
    fetch: function (url, options) {
      options = options || {};
      var headers = new Headers(options.headers || {});
      headers.set(HEADER, '1');
      var merged = Object.assign({}, options, {
        headers: headers,
        credentials: 'same-origin'
      });
      return window.fetch(url, merged);
    }
  };
})();
