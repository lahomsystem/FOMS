/**
 * 새 지식 카드(판 ⑧ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 5.3 · 5.4) — templates/brain/ds/item.html 의 [data-ds-item].
 *
 * - 탭(한눈에 · 수정 기록 · 연결된 지식 · 뇌 보기): 패널을 보이고 숨긴다(Bootstrap 없음). 그림 위젯 스크립트(옛 brain-neighbours.js ·
 *   brain3d-tab.js — 고치지 않고 싣는다)가 듣는 옛 탭 단추(같은 id)에 'shown.bs.tab' · 'hidden.bs.tab' 을 쏜다 — 그 스크립트가
 *   탭을 열 때만 Cytoscape · three.js 를 import() 한다. 주소 끝 #neighbours · #brain3d · #history 면 그 탭으로 연다(뇌 보기는 그
 *   스크립트가 탭을 보일 때만). 화살표 키로 탭을 옮긴다.
 * - '이웃 지도' 단추 → 연결된 지식 탭. '옛 판으로 되돌리기 제안' → 지난 판 단추 목록을 펼친다(보내기는 brain-item-actions.js).
 * - 쓰인 곳(설계서 3.8): 화면에 data-usage-url 이 있을 때만(접목판 erp_read 스위치 — 서버가 정한다) 그 주소를 읽어 읽은 쪽마다
 *   수 · 막대(<progress> — 인라인 스타일 없음) · 최근 줄(가린 글만 — 서버가 거른다) · ERP 물건과 이어짐을 그린다.
 * 요청은 brain-dom.js getJson 한 곳, 글은 textContent 만, 전역 듣개는 한 번만(window.__FOMS_DS_ITEM_BOUND).
 */
(function () {
  'use strict';

  if (window.__FOMS_DS_ITEM_BOUND) return;
  var root = document.querySelector('[data-ds-item]');
  var dom = window.FOMS_BRAIN_DOM;
  var sv = window.FOMS_DS_SEARCH_VIEW;
  if (!root || !dom || !sv) return;
  window.__FOMS_DS_ITEM_BOUND = true;

  var card = document.querySelector('[data-brain-card]');
  var display = dom.safeJsonParse(card ? card.getAttribute('data-display') : '', {});
  var HASH_TABS = { '#neighbours': 'neighbours', '#brain3d': 'brain3d', '#history': 'history' };
  var current = 'main';

  function tabButton(name) {
    return root.querySelector('[data-ds-item-tab="' + name + '"]');
  }

  function fire(button, type) {
    if (button) button.dispatchEvent(new CustomEvent(type, { bubbles: true }));
  }

  /** 탭 하나를 연다 — 숨긴 탭(뇌 보기를 못 그리는 기기)은 열지 않는다. */
  function show(name, focus) {
    var button = tabButton(name);
    if (!button || button.hidden || name === current) return;
    var before = tabButton(current);
    root.querySelectorAll('[data-ds-item-tab]').forEach(function (tab) {
      var on = tab === button;
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.setAttribute('tabindex', on ? '0' : '-1');
    });
    root.querySelectorAll('[data-ds-item-panel]').forEach(function (panel) {
      panel.hidden = panel.getAttribute('data-ds-item-panel') !== name;
    });
    current = name;
    if (focus) button.focus();
    fire(before, 'hidden.bs.tab');
    fire(button, 'shown.bs.tab');
  }

  root.addEventListener('click', function (event) {
    var tab = event.target.closest('[data-ds-item-tab]');
    var opener = event.target.closest('[data-ds-item-open]');
    if (tab) show(tab.getAttribute('data-ds-item-tab'));
    else if (opener) show(opener.getAttribute('data-ds-item-open'), true);
  });

  root.querySelector('[data-ds-item-tabs]').addEventListener('keydown', function (event) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    var tabs = Array.prototype.filter.call(root.querySelectorAll('[data-ds-item-tab]'), function (t) { return !t.hidden; });
    var at = tabs.indexOf(tabButton(current));
    var to = tabs[(at + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    if (to) {
      event.preventDefault();
      show(to.getAttribute('data-ds-item-tab'), true);
    }
  });

  var toggle = document.querySelector('[data-ds-item-rollback-toggle]');
  var olders = document.querySelector('[data-ds-item-rollback]');
  if (toggle && olders) {
    toggle.addEventListener('click', function () {
      var open = olders.hidden;
      olders.hidden = !open;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // ── 쓰인 곳 ─────────────────────────────────────────────────────────
  function bars(usage) {
    var grid = dom.el('div', { cls: 'fb-usage' });
    sv.usageBars(usage.by_reader).forEach(function (bar) {
      var col = dom.el('div', { cls: 'f-col f-gap4', attrs: { 'data-ds-usage-reader': bar.key } });
      col.appendChild(dom.el('span', { cls: 'f-small f-muted', text: bar.label }));
      col.appendChild(dom.el('span', { cls: 'f-h3 f-num', text: sv.num(bar.n) }));
      col.appendChild(dom.el('progress', { cls: 'fb-bar', attrs: { max: '100', value: String(bar.pct),
                                                                  'aria-label': bar.label + ' ' + bar.n } }));
      grid.appendChild(col);
    });
    return grid;
  }

  function recent(usage) {
    var list = dom.el('ul', { cls: 'f-col f-gap4' });
    (usage.recent || []).forEach(function (row) {
      var li = dom.el('li', { cls: 'fb-recent' });
      li.appendChild(dom.el('span', { cls: 'f-small f-muted f-num', text: sv.shortDay(row.day) }));
      li.appendChild(dom.el('span', { cls: 'f-ai-mark', text: row.agent_label }));
      li.appendChild(dom.el('span', { cls: 'f-small f-ellipsis', text: row.text || '—' }));
      li.appendChild(dom.el('span', { cls: 'f-tag ' + sv.toneCls(row.tone), text: row.state }));
      list.appendChild(li);
    });
    if (!(usage.recent || []).length) list.appendChild(dom.el('li', { cls: 'f-small f-muted', text: '지난 2주 동안 쓰인 기록이 없어요.' }));
    return list;
  }

  function erpLinks(usage) {
    var list = dom.el('ul', { cls: 'f-col f-gap4' });
    (usage.erp_links || []).forEach(function (link) {
      var c = sv.erpChip(link);
      var info = (display.links || {})[link.rel];
      var li = dom.el('li', { cls: 'f-row-nw' });
      li.appendChild(dom.el('span', { cls: 'f-small f-muted fb-erp-rel', text: info ? info.out : String(link.rel || '') }));
      var chip = dom.el('span', { cls: 'f-chip' });
      chip.appendChild(dom.el('span', { cls: 'f-i i-' + c.icon, attrs: { 'aria-hidden': 'true' } }));
      chip.appendChild(document.createTextNode(c.text));
      li.appendChild(chip);
      if (c.note) li.appendChild(dom.el('span', { cls: 'f-small f-muted', text: c.note }));
      list.appendChild(li);
    });
    if (!(usage.erp_links || []).length) list.appendChild(dom.el('li', { cls: 'f-small f-muted', text: '이어진 ERP 물건이 없어요.' }));
    return list;
  }

  async function loadUsage() {
    var url = root.getAttribute('data-usage-url');
    var body = root.querySelector('[data-ds-item-usage-body]');
    var status = root.querySelector('[data-ds-item-usage-status]');
    if (!url || !body) return;
    var res = await dom.getJson(url);
    if (!res.ok || !res.data || !res.data.by_reader) {
      dom.setStatus(status, res.ok ? '쓰인 곳을 읽지 못했어요.' : res.error, 'error');
      return;
    }
    dom.clear(body);
    body.appendChild(bars(res.data));
    body.appendChild(recent(res.data));
    body.appendChild(dom.el('hr', { cls: 'f-divider' }));
    body.appendChild(dom.el('span', { cls: 'f-h6', text: 'ERP 물건과 이어짐' }));
    body.appendChild(erpLinks(res.data));
  }

  /** 그림 위젯 스크립트(뒤에 실린다)가 듣개를 단 뒤에 주소 끝의 탭을 연다. */
  function start() {
    var name = HASH_TABS[window.location.hash];
    if (name) show(name);
    loadUsage();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
