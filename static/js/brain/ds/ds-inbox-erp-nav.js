/**
 * 승인 대기 왼쪽 길잡이의 AI 직원별 수 — '다시 확인' · '판 · 기록' 보기용(점검 2차 w1-01 — 세 보기가 같은 수).
 * templates/brain/ds/partials/inbox_erp_nav.html 이 승인 대기 보기 밖에서만 싣는다(승인 대기 보기는 ds-inbox-erp.js 가 같은
 * 일을 카드와 함께 한다).
 *
 * GET /api/erp-actions/inbox 한 번 → [data-erp-agent-count] 수(0 은 흐리게) · 바탕(ds-inbox.js)에 setCount('actions' · 'snoozed')
 * (위 줄 · '모두' · '나중에 볼 것' 수). 요청은 brain-dom.js 한 곳(try/catch + data.success), 글은 textContent 만.
 */
(function () {
  'use strict';

  var nav = document.querySelector('[data-erp-nav-api]');
  if (!nav || document.querySelector('[data-erp-section]') || window.__FOMS_DS_INBOX_ERP_NAV_BOUND) return;
  window.__FOMS_DS_INBOX_ERP_NAV_BOUND = true;
  var started = false;

  function paint(counts) {
    var by = counts.by_agent || {};
    Array.prototype.slice.call(document.querySelectorAll('[data-erp-agent-nav]')).forEach(function (item) {
      var key = item.getAttribute('data-erp-agent-nav');
      var n = item.querySelector('[data-erp-agent-count]');
      if (n) n.textContent = String(by[key] || 0);
      item.classList.toggle('fb-nav-item--muted', !by[key]);
    });
    var inbox = window.FOMS_DS_INBOX;
    if (!inbox) return;
    inbox.setCount('actions', counts.total || 0);
    inbox.setCount('snoozed', counts.snoozed || 0);
  }

  async function start() {
    var dom = window.FOMS_BRAIN_DOM;
    if (started || !dom) return;
    started = true;
    var res = await dom.getJson(nav.getAttribute('data-erp-nav-api') + '/inbox');
    if (res.ok && res.data) paint(res.data.counts || {});
  }

  var root = document.querySelector('[data-ds-inbox]');
  if (root && root.getAttribute('data-ds-inbox-ready') === '1') start();
  else {
    if (root) root.addEventListener('ds:inbox-ready', start, { once: true });
    document.addEventListener('DOMContentLoaded', start, { once: true });
  }
})();
