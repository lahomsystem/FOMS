/**
 * 새 회사 지식 화면 틀(설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 5.2 · 5.5) — templates/brain/ds/layout.html 이 싣는다.
 *
 * - 지금 탭 표시: 틀의 data-ds-section 과 같은 [data-ds-tab] 에 aria-current · is-active(서버가 그린 것과 같게 맞춘다).
 * - 위 줄 찾기 칸: GET /brain?tab=search&q=<글>(폼 그대로) — 빈 글이면 보내지 않는다.
 * - 폰 아래 탭 '나': 이름 · FOMS 로 돌아가기 창을 열고 닫는다(바깥 누름 · Esc 로 닫힘).
 * - 승인 대기 수: 서버가 넣은 지식 수 그대로. 틀에 data-badge-url 이 있을 때만(접목판 actions 스위치) 그 주소의 total 로 고친다.
 *   window.FOMS_DS_SHELL.setCount(n) 으로 다른 화면 스크립트도 고칠 수 있다.
 * - 화면 크기: FOMS 와 같은 저장 열쇠(foms-ui-zoom:<사람>:<pc|touch>)의 값을 html 에 붙인다(혼자 서는 문서라 layout_head 가 없다).
 * 글은 textContent 로만. 요청은 brain-dom.js 의 getJson 한 곳. 전역 듣개는 한 번만(window.__FOMS_DS_SHELL_BOUND).
 */
(function () {
  'use strict';

  var ZOOM_MIN = 70;
  var ZOOM_MAX = 130;

  function shell() {
    return document.querySelector('[data-ds-shell]');
  }

  /** FOMS 화면 크기 — layout_head.html 의 첫 그림 전 boot 와 같은 열쇠 · 같은 값 범위 · 같은 html 표시. */
  function applyZoom(root) {
    var html = document.documentElement;
    var uid = root.getAttribute('data-ds-uid') || '';
    var fine = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    var key = 'foms-ui-zoom:' + (uid || 'anon') + ':' + (fine ? 'pc' : 'touch');
    html.setAttribute('data-foms-ui-zoom-key', key);
    var pct = 100;
    try {
      pct = parseInt(window.localStorage.getItem(key) || '', 10);
    } catch (e) {
      pct = 100; // 저장 막힘 = 100%
    }
    if (pct >= ZOOM_MIN && pct <= ZOOM_MAX && pct !== 100) {
      html.setAttribute('data-foms-ui-zoom', String(pct / 100));
      html.style.setProperty('--foms-ui-zoom', String(pct / 100));
    }
  }

  function markCurrent(root) {
    var section = root.getAttribute('data-ds-section') || '';
    root.querySelectorAll('[data-ds-tab]').forEach(function (tab) {
      var on = tab.getAttribute('data-ds-tab') === section;
      tab.classList.toggle('is-active', on);
      if (on) tab.setAttribute('aria-current', 'page');
      else tab.removeAttribute('aria-current');
    });
  }

  function setCount(n) {
    var value = Math.max(0, Number(n) || 0);
    document.querySelectorAll('[data-ds-count="inbox"]').forEach(function (node) {
      node.textContent = value > 999 ? '999+' : String(value);
      if (node.closest('[data-ds-tabs], .fb-nav-phone-count')) node.classList.toggle('f-count-primary', value > 0);
    });
  }

  async function refreshBadge(root) {
    var url = root.getAttribute('data-badge-url');
    var dom = window.FOMS_BRAIN_DOM;
    if (!url || !dom) return;
    var res = await dom.getJson(url);
    if (res.ok && res.data && typeof res.data.total === 'number') setCount(res.data.total);
  }

  function bindSearch(root) {
    var form = root.querySelector('[data-ds-search]');
    if (!form) return;
    form.addEventListener('submit', function (event) {
      var input = form.querySelector('input[name="q"]');
      var text = input ? input.value.trim() : '';
      if (!text) {
        event.preventDefault();
        if (input) input.focus();
        return;
      }
      if (input) input.value = text.slice(0, 100);
    });
  }

  function bindMe(root) {
    var toggle = root.querySelector('[data-ds-me-toggle]');
    var panel = root.querySelector('[data-ds-me-panel]');
    if (!toggle || !panel) return;
    function setOpen(open) {
      panel.hidden = !open;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.classList.toggle('is-active', open);
    }
    toggle.addEventListener('click', function () { setOpen(panel.hidden); });
    if (window.__FOMS_DS_SHELL_BOUND) return;
    window.__FOMS_DS_SHELL_BOUND = true;
    document.addEventListener('click', function (event) {
      if (panel.hidden || panel.contains(event.target) || toggle.contains(event.target)) return;
      setOpen(false);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !panel.hidden) {
        setOpen(false);
        toggle.focus();
      }
    });
  }

  function init() {
    var root = shell();
    if (!root || root.getAttribute('data-ds-shell-ready') === '1') return;
    root.setAttribute('data-ds-shell-ready', '1');
    applyZoom(root);
    markCurrent(root);
    bindSearch(root);
    bindMe(root);
    refreshBadge(root);
  }

  window.FOMS_DS_SHELL = { setCount: setCount };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
