/**
 * nav 네이버 수집 확인 대기 뱃지 — 페이지가 뜬 뒤에 숫자를 채운다.
 *
 * 왜 서버에서 안 세는가: 이 숫자는 컨텍스트 프로세서가 계산해 **모든 전체 문서 렌더**에
 * 실렸는데, 워크벤치 코호트 안에서는 콜드마다 약 400ms 였다(2026-09-11 스테이징 실측:
 * /erp/dashboard render 423ms 중 nvbadge 382ms). 뱃지는 숫자 하나짜리 부가 정보인데
 * 사용자가 첫 화면을 보기까지의 시간을 그만큼 밀고 있었다. 숫자가 조금 늦게 뜨는 값을
 * 치르고 첫 화면을 앞당긴다.
 *
 * 0 이면 뱃지를 계속 숨긴다 — 빨간 뱃지에 0 을 띄우면 "할 일이 있다"는 거짓 신호가 된다
 * (서버 렌더 시절의 `{% if naver_triage_pending %}` 와 같은 판정).
 *
 * 실패하면 조용히 숨긴 채 둔다. 뱃지 하나 때문에 화면에 오류를 띄우지 않는다.
 */
(function () {
  'use strict';

  var ENDPOINT = '/admin/naver-ingest/triage/pending-count';
  var SELECTOR = '[data-foms-nav-triage-badge]';

  // ERP 셸은 프래그먼트를 갈아 끼우며 이 스크립트를 다시 평가할 수 있다. nav 는 프래그먼트
  // 밖이라 한 번만 채우면 된다 — entry singleton 이 이 저장소의 표준(erp-dashboard-entry.js).
  if (window.__FOMS_NAV_TRIAGE_BADGE_BOUND) return;
  window.__FOMS_NAV_TRIAGE_BADGE_BOUND = true;

  function paint(count) {
    var nodes = document.querySelectorAll(SELECTOR);
    for (var i = 0; i < nodes.length; i++) {
      if (count > 0) {
        nodes[i].textContent = String(count);
        nodes[i].hidden = false;
      } else {
        nodes[i].hidden = true;
      }
    }
  }

  function load() {
    if (!document.querySelector(SELECTOR)) return; // 뱃지 자리가 없는 화면이면 요청도 안 한다
    fetch(ENDPOINT, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success || !data.data) return;
        paint(Number(data.data.count) || 0);
      })
      .catch(function () {
        /* 뱃지는 부가 정보다 — 숨긴 채로 둔다 */
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
